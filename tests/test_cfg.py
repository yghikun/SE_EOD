from pathlib import Path

from src.cfg import build_cfg
from src.dataflow import solve_forward, solve_forward_disjunctive
from src.function_extractor import extract_functions
from src.parser import parse_c_file
from src.resource_state import ResourceState, join_states


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


def test_dataflow_join_preserves_possible_acquired_state(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(int release)
{
    if (release)
        put();
    use();
    return 0;
}
""",
    )
    cfg = build_cfg(function)

    def transfer(block, state):
        if "put()" in block.text:
            return ResourceState.RELEASED
        return state

    result = solve_forward(
        cfg,
        ResourceState.ACQUIRED,
        transfer,
        join_states,
        lambda state: state,
    )
    use_block = next(block for block in cfg.blocks.values() if block.text == "use();")

    assert result.in_states[use_block.id] is ResourceState.MAY_ACQUIRED
    assert result.truncated is False


def test_dataflow_join_with_unseen_is_possibly_acquired(tmp_path: Path):
    assert (
        join_states(ResourceState.UNSEEN, ResourceState.ACQUIRED)
        is ResourceState.MAY_ACQUIRED
    )


def test_disjunctive_dataflow_preserves_branch_states_until_bound(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(int release)
{
    if (release)
        put();
    use();
    return 0;
}
""",
    )
    cfg = build_cfg(function)
    result = solve_forward_disjunctive(
        cfg,
        ResourceState.ACQUIRED,
        lambda block, state: ResourceState.RELEASED if "put()" in block.text else state,
        join_states,
        lambda state: state,
    )
    use_block = next(block for block in cfg.blocks.values() if block.text == "use();")
    assert set(result.in_states[use_block.id]) == {
        ResourceState.ACQUIRED,
        ResourceState.RELEASED,
    }
