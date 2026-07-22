import json
from pathlib import Path

import pytest

from src.cfg import build_cfg
from src.frontend.model import (
    FRONTEND_IR_SCHEMA_VERSION,
    ControlFlowGraphIR,
    FrontendNode,
    TranslationUnitIR,
)
from src.frontend.tree_sitter_frontend import TreeSitterFrontend
from src.parser import ParsedFile


SOURCE = """
static int work(struct obj *obj, void (*callback)(void *), int err)
{
    void *ptr = kmalloc(obj->size);
    if (!ptr)
        return -ENOMEM;
    callback(ptr);
    if (err)
        return err;
    obj->field = ptr;
    kfree(ptr);
    return 0;
}
"""


def _write_source(root: Path) -> Path:
    path = root / "fs" / "ext4" / "frontend_ir.c"
    path.parent.mkdir(parents=True)
    path.write_text(SOURCE, encoding="utf-8")
    return path


def test_tree_sitter_frontend_populates_versioned_ir(tmp_path: Path):
    path = _write_source(tmp_path)
    unit = TreeSitterFrontend(tmp_path).parse(path)

    assert unit.schema_version == FRONTEND_IR_SCHEMA_VERSION
    assert unit.identity_path == "fs/ext4/frontend_ir.c"
    assert unit.frontend_name == "tree-sitter"
    assert unit.frontend_mode == "tree-sitter"
    assert unit.compile_command is None
    assert len(unit.functions) == 1

    function = unit.functions[0]
    assert function.frontend_schema_version == FRONTEND_IR_SCHEMA_VERSION
    assert function.frontend_name == "tree-sitter"
    assert function.frontend_mode == "tree-sitter"
    assert function.return_type == "int"
    assert function.parse_tree is None
    assert isinstance(function.ast_node, FrontendNode)
    assert function.body_node is not None
    assert function.body_node.source_file == "fs/ext4/frontend_ir.c"
    assert [(symbol.name, symbol.kind) for symbol in function.symbols] == [
        ("obj", "parameter"),
        ("callback", "parameter"),
        ("err", "parameter"),
        ("ptr", "local"),
    ]
    assert [symbol.parameter_index for symbol in function.symbols[:3]] == [0, 1, 2]

    calls = {call.callee_spelling: call for call in function.calls}
    assert calls["kmalloc"].callee_kind == "direct"
    assert calls["kmalloc"].possible_targets == ("kmalloc",)
    assert calls["callback"].callee_kind == "indirect"
    assert calls["callback"].possible_targets == ()
    assert calls["kfree"].arguments == ("ptr",)
    assert any(
        path.spelling == "obj->size" and path.role == "rvalue"
        for path in function.access_paths
    )
    assert any(
        path.spelling == "obj->field" and path.role == "lvalue"
        for path in function.access_paths
    )


def test_translation_unit_ir_json_round_trip_preserves_analysis_nodes(tmp_path: Path):
    unit = TreeSitterFrontend(tmp_path).parse(_write_source(tmp_path))
    restored = TranslationUnitIR.from_json(unit.to_json())

    assert restored.to_dict() == unit.to_dict()
    function = restored.functions[0]
    assert function.body_node is not None
    if_node = next(node for node in function.body_node.walk() if node.type == "if_statement")
    assert if_node.child_by_field_name("condition") is not None
    assert function.file_bytes == SOURCE.encode("utf-8")

    invalid = unit.to_dict()
    invalid["schema_version"] = FRONTEND_IR_SCHEMA_VERSION + 1
    with pytest.raises(ValueError, match="unsupported frontend IR schema"):
        TranslationUnitIR.from_dict(invalid)


def test_frontend_ids_are_stable_across_workspace_roots(tmp_path: Path):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = TreeSitterFrontend(first_root).parse(_write_source(first_root))
    second = TreeSitterFrontend(second_root).parse(_write_source(second_root))

    assert first.translation_unit_id == second.translation_unit_id
    assert first.functions[0].function_id == second.functions[0].function_id
    assert [symbol.symbol_id for symbol in first.functions[0].symbols] == [
        symbol.symbol_id for symbol in second.functions[0].symbols
    ]
    assert [call.call_id for call in first.functions[0].calls] == [
        call.call_id for call in second.functions[0].calls
    ]


def test_cfg_uses_serializable_frontend_ir_model(tmp_path: Path):
    function = TreeSitterFrontend(tmp_path).parse(_write_source(tmp_path)).functions[0]
    cfg = build_cfg(function)
    restored = ControlFlowGraphIR.from_dict(cfg.to_dict())

    assert restored.to_dict() == cfg.to_dict()
    assert restored.block_at_line(6) is not None
    assert restored.successors(restored.entry)

    invalid = cfg.to_dict()
    invalid["schema_version"] = FRONTEND_IR_SCHEMA_VERSION + 1
    with pytest.raises(ValueError, match="unsupported frontend IR schema"):
        ControlFlowGraphIR.from_dict(invalid)


def test_frontend_ir_semantic_golden(tmp_path: Path):
    unit = TreeSitterFrontend(tmp_path).parse(_write_source(tmp_path))
    function = unit.functions[0]
    cfg = build_cfg(function)
    actual = {
        "schema_version": unit.schema_version,
        "identity_path": unit.identity_path,
        "frontend_name": unit.frontend_name,
        "frontend_mode": unit.frontend_mode,
        "compile_command": unit.compile_command,
        "function": {
            "name": function.name,
            "return_type": function.return_type,
            "symbols": [
                [symbol.name, symbol.kind] for symbol in function.symbols
            ],
            "calls": [
                [call.callee_spelling, call.callee_kind]
                for call in function.calls
            ],
            "access_paths": [
                [path.spelling, path.role, path.precision]
                for path in function.access_paths
            ],
            "cfg_edge_kinds": sorted({edge.kind for edge in cfg.edges}),
        },
    }
    golden_path = (
        Path(__file__).parent / "fixtures" / "frontend_ir_v1_golden.json"
    )
    expected = json.loads(golden_path.read_text(encoding="utf-8"))
    assert actual == expected


def test_frontend_records_error_nodes_with_precise_ranges(tmp_path: Path):
    path = tmp_path / "range.c"
    path.write_text(
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
        encoding="utf-8",
    )
    unit = TreeSitterFrontend(tmp_path).parse(path)
    function = unit.functions[0]

    assert unit.frontend_mode == "degraded-tree-sitter"
    assert function.frontend_mode == "degraded-tree-sitter"
    assert function.unsupported_features == ["tree_sitter_error_node"]
    diagnostic = next(
        item for item in function.diagnostics if item.code == "tree_sitter_error_node"
    )
    assert diagnostic.source_range is not None
    assert diagnostic.source_range.file == "range.c"
    assert diagnostic.source_range.start_line == 5


def test_text_fallback_is_explicit_in_function_ir(tmp_path: Path, monkeypatch):
    import src.frontend.tree_sitter_frontend as adapter_module

    path = tmp_path / "fallback.c"
    source = "int work(void) { return -EIO; }\n"
    path.write_text(source, encoding="utf-8")
    monkeypatch.setattr(
        adapter_module,
        "parse_c_file",
        lambda requested: ParsedFile(
            Path(requested),
            source,
            tree=None,
            parser_kind="text",
            warnings=["tree-sitter unavailable"],
        ),
    )

    unit = adapter_module.TreeSitterFrontend(tmp_path).parse(path)
    function = unit.functions[0]
    assert unit.frontend_mode == "text"
    assert function.frontend_mode == "text"
    assert function.body_node is None
    assert function.unsupported_features == ["no_syntax_tree"]
    assert any(
        item.code == "text_fallback_no_syntax_tree"
        for item in function.diagnostics
    )
