from pathlib import Path
from typing import Optional

from src.cfg import build_cfg
from src.function_extractor import extract_functions
from src.parser import parse_c_file


def _function(tmp_path: Path, source: str):
    path = tmp_path / "cfg.c"
    path.write_text(source, encoding="utf-8")
    return extract_functions(parse_c_file(path))[0]


def test_cfg_builds_branch_goto_return_and_backedge(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(int retry)
{
again:
    if (retry)
        goto again;
    return 0;
}
""",
    )
    cfg = build_cfg(function)

    assert function.body_node is not None
    assert "again" in cfg.labels
    assert any(edge.kind == "true" for edge in cfg.edges)
    assert any(edge.kind == "false" for edge in cfg.edges)
    assert any(edge.kind == "backedge" for edge in cfg.edges)
    assert any(edge.kind == "return" and edge.target == cfg.exit for edge in cfg.edges)


def _block(cfg, *, kind: str, text: Optional[str] = None):
    return next(
        block
        for block in cfg.blocks.values()
        if block.kind == kind and (text is None or block.text == text)
    )


def test_switch_cfg_builds_cases_default_fallthrough_and_break(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(int mode)
{
    switch (mode) {
    case 1:
    case 2:
        use();
        break;
    case 3:
        prepare();
    default:
        finish();
    }
    return 0;
}
""",
    )
    cfg = build_cfg(function)

    dispatch = _block(cfg, kind="switch_dispatch", text="mode")
    switch_exit = _block(cfg, kind="switch_exit")
    cases = {
        block.text: block
        for block in cfg.blocks.values()
        if block.kind in {"switch_case", "switch_default"}
    }

    assert cfg.unsupported_nodes == []
    assert set(cases) == {"case 1", "case 2", "case 3", "default"}
    assert {
        (edge.kind, edge.condition)
        for edge in cfg.successors(dispatch.id)
    } == {
        ("switch_case", "mode == 1"),
        ("switch_case", "mode == 2"),
        ("switch_case", "mode == 3"),
        ("switch_default", "mode != 1 && mode != 2 && mode != 3"),
    }
    assert any(
        edge.source == cases["case 1"].id
        and edge.target == cases["case 2"].id
        and edge.kind == "case_fallthrough"
        for edge in cfg.edges
    )
    prepare = next(block for block in cfg.blocks.values() if block.text == "prepare();")
    assert any(
        edge.source == prepare.id
        and edge.target == cases["default"].id
        and edge.kind == "case_fallthrough"
        for edge in cfg.edges
    )
    assert any(
        edge.kind == "break" and edge.target == switch_exit.id for edge in cfg.edges
    )


def test_switch_without_default_has_no_match_edge(tmp_path: Path):
    cfg = build_cfg(
        _function(
            tmp_path,
            """
int work(int mode)
{
    switch (mode) {
    case 1:
        use();
        break;
    }
    return 0;
}
""",
        )
    )
    dispatch = _block(cfg, kind="switch_dispatch", text="mode")

    no_match = next(
        edge for edge in cfg.successors(dispatch.id) if edge.kind == "switch_no_match"
    )
    assert no_match.condition == "mode != 1"
    assert cfg.blocks[no_match.target].kind == "scope_exit"


def test_nested_switch_and_loop_bind_break_and_continue_to_nearest_target(
    tmp_path: Path,
):
    cfg = build_cfg(
        _function(
            tmp_path,
            """
int work(int outer, int inner)
{
    while (outer) {
        switch (inner) {
        case 1:
            continue;
        case 2:
            while (inner)
                break;
            break;
        default:
            switch (outer) {
            case 3:
                break;
            default:
                break;
            }
            break;
        }
        outer--;
    }
    return 0;
}
""",
        )
    )
    loop_headers = [
        block for block in cfg.blocks.values() if block.kind == "loop_condition"
    ]
    switch_exits = [
        block for block in cfg.blocks.values() if block.kind == "switch_exit"
    ]

    assert cfg.unsupported_nodes == []
    assert len(loop_headers) == 2
    assert len(switch_exits) == 2
    continue_edge = next(edge for edge in cfg.edges if edge.kind == "continue")
    assert cfg.blocks[continue_edge.target].kind == "loop_condition"
    assert cfg.blocks[continue_edge.target].text in {"outer", "(outer)"}
    break_edges = [edge for edge in cfg.edges if edge.kind == "break"]
    assert any(cfg.blocks[edge.target].kind == "loop_exit" for edge in break_edges)
    assert sum(cfg.blocks[edge.target].kind == "switch_exit" for edge in break_edges) >= 4


def test_switch_case_goto_and_return_keep_non_fallthrough_exits(tmp_path: Path):
    cfg = build_cfg(
        _function(
            tmp_path,
            """
int work(int mode)
{
    switch (mode) {
    case 1:
        goto out;
    default:
        return -1;
    }
out:
    return 0;
}
""",
        )
    )

    assert cfg.unsupported_nodes == []
    assert any(edge.kind == "goto" for edge in cfg.edges)
    assert sum(edge.kind == "return" for edge in cfg.edges) == 2
    goto_edge = next(edge for edge in cfg.edges if edge.kind == "goto")
    assert goto_edge.scope_unwind == 1


def test_gnu_case_range_is_precisely_unsupported(tmp_path: Path):
    cfg = build_cfg(
        _function(
            tmp_path,
            """
int work(int mode)
{
    switch (mode) {
    case 1 ... 3:
        return 1;
    default:
        return 0;
    }
}
""",
        )
    )

    assert cfg.unsupported_nodes == ["case_range"]
    assert len(cfg.unsupported_ranges) == 1
    unsupported = cfg.unsupported_ranges[0]
    assert unsupported["type"] == "case_range"
    assert unsupported["start_line"] == 5
    assert unsupported["end_line"] == 5
