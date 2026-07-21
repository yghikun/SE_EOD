import json
from pathlib import Path

from src.frontend.tree_sitter_frontend import TreeSitterFrontend
from src.metadata_protocol import MetadataProtocol
from src.metadata_protocol_discovery import (
    discover_source_tree,
    main,
    operation_applicability,
)


ROOT = Path(__file__).parents[1]
PROTOCOL_A = (
    ROOT
    / "configs"
    / "metadata_protocols"
    / "protocol_a_replay_recovery_v1.json"
)


def _write_source(root: Path, relative: str, source: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _semantic_del_source(function_name: str) -> str:
    return f"""
int {function_name}(void)
{{
    int ret = ext4_map_blocks();
    if (ret < 0)
        return 0;
    ret = ext4_ext_remove_space();
    if (ret)
        return 0;
    return 0;
}}
"""


def test_operation_override_analyzes_semantically_matched_function(tmp_path):
    protocol = MetadataProtocol.read_json(PROTOCOL_A)
    path = _write_source(
        tmp_path,
        "fs/ext4/replay.c",
        _semantic_del_source("custom_replay_del"),
    )
    function = TreeSitterFrontend(source_root=tmp_path).parse(path).functions[0]

    evidence = operation_applicability(function, protocol)
    selected = next(
        item for item in evidence if item.operation_id == "ext4_replay_del_range"
    )

    assert selected.applicable
    assert selected.match_kind == "semantic"
    assert selected.matched_role_ids == ("map_blocks", "remove_space")
    assert "callee:ext4_ext_remove_space" in selected.unique_anchor_ids


def test_single_shared_role_is_not_a_semantic_operation_match(tmp_path):
    protocol = MetadataProtocol.read_json(PROTOCOL_A)
    path = _write_source(
        tmp_path,
        "fs/ext4/shared.c",
        "int helper(void) { return ext4_map_blocks(); }",
    )
    function = TreeSitterFrontend(source_root=tmp_path).parse(path).functions[0]

    evidence = operation_applicability(function, protocol)

    assert not any(item.applicable for item in evidence)


def test_directory_discovery_finds_renamed_operation_and_stable_family(tmp_path):
    protocol = MetadataProtocol.read_json(PROTOCOL_A)
    _write_source(
        tmp_path,
        "fs/ext4/replay.c",
        _semantic_del_source("custom_replay_del"),
    )
    _write_source(
        tmp_path,
        "fs/ext4/unrelated.c",
        "int unrelated(void) { return 0; }",
    )
    _write_source(
        tmp_path,
        "fs/btrfs/not_ext4.c",
        _semantic_del_source("wrong_filesystem"),
    )

    first = discover_source_tree(
        tmp_path,
        [protocol],
        source_version="linux-v1",
    ).to_dict()
    second = discover_source_tree(
        tmp_path,
        [protocol],
        source_version="linux-v2",
    ).to_dict()

    assert first["summary"]["scanned_files"] == 3
    assert first["summary"]["applicable_functions"] == 1
    assert first["summary"]["candidate_occurrences"] >= 1
    analysis = first["analyses"][0]
    assert analysis["function"] == "custom_replay_del"
    assert analysis["operation_id"] == "ext4_replay_del_range"
    assert analysis["applicability"]["match_kind"] == "semantic"
    assert {
        item["family_fingerprint"] for item in analysis["candidates"]
    } == {
        item["family_fingerprint"]
        for item in second["analyses"][0]["candidates"]
    }
    assert first["summary"]["skip_reasons"]["filesystem_not_applicable"] >= 1


def test_discovery_cli_writes_versioned_report(tmp_path):
    _write_source(
        tmp_path,
        "fs/ext4/replay.c",
        _semantic_del_source("custom_replay_del"),
    )
    output = tmp_path / "discovery.json"

    assert (
        main(
            [
                "--protocol",
                str(PROTOCOL_A),
                "--source-root",
                str(tmp_path),
                "--source-version",
                "fixture-v1",
                "--out",
                str(output),
            ]
        )
        == 0
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["source_version"] == "fixture-v1"
    assert payload["summary"]["candidate_occurrences"] >= 1


def test_real_protocol_c_directory_scan_keeps_known_operations():
    protocol = MetadataProtocol.read_json(
        ROOT
        / "configs"
        / "metadata_protocols"
        / "protocol_c_activation_accounting_v1.json"
    )
    report = discover_source_tree(
        ROOT / "linux-sources" / "linux-v6.8-fs" / "fs" / "ext4",
        [protocol],
        source_version="linux-v6.8",
        include=("xattr.c",),
    ).to_dict()

    analyses = {
        item["function"]: item
        for item in report["analyses"]
    }
    assert "ext4_expand_extra_isize_ea" in analyses
    assert analyses["ext4_expand_extra_isize_ea"]["candidates"]
