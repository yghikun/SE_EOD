import json
from pathlib import Path

from src.frontend.tree_sitter_frontend import TreeSitterFrontend
from src.metadata_protocol import MetadataProtocol
from src.metadata_protocol_analyzer import analyze_function, analyze_source_file, main


ROOT = Path(__file__).parents[1]
PROTOCOL_A = ROOT / "configs" / "metadata_protocols" / "protocol_a_replay_recovery_v1.json"


def _mini_protocol(
    entry: str = "work",
    *,
    indirect: bool = False,
    best_effort: bool = False,
) -> MetadataProtocol:
    callee = "step"
    return MetadataProtocol.from_dict(
        {
            "schema_version": 1,
            "protocol_version": "1.0.0",
            "protocol_id": "test.protocol_a",
            "filesystems": ["fixture"],
            "linux_versions": ["test"],
            "phases": ["ENTRY", "SUCCESS", "FAILURE"],
            "operations": [
                {
                    "operation_id": "replay",
                    "entry_functions": [entry],
                    "principal_objects": [{"role": "operation", "selector": "function"}],
                    "callee_roles": [
                        {
                            "role_id": "necessary_step",
                            "callees": [callee],
                            "necessary": not best_effort,
                            "return_contract_ids": ["failure", "success"],
                        }
                    ],
                }
            ],
            "return_contracts": [
                {"contract_id": "failure", "operation_id": "replay", "guard": "ret != 0", "outcome": "failure"},
                {"contract_id": "success", "operation_id": "replay", "guard": "ret == 0", "outcome": "success"},
            ],
            "effects": [], "compensations": [], "handlers": [], "accounting_constraints": [],
            "legal_exits": [
                {"exit_id": "success", "operation_id": "replay", "kind": "success", "phases": ["SUCCESS"], "completion_modes": ["COMMITTED"], "return_outcomes": ["success"]},
                {"exit_id": "failure", "operation_id": "replay", "kind": "failure", "phases": ["FAILURE"], "completion_modes": ["ROLLED_BACK", "ABORTED"], "return_outcomes": ["failure"]},
            ],
        }
    )


def _function(tmp_path: Path, source: str, name: str = "work"):
    path = tmp_path / "fixture.c"
    path.write_text(source, encoding="utf-8")
    unit = TreeSitterFrontend(source_root=tmp_path).parse(path)
    return next(item for item in unit.functions if item.name == name)


def test_failure_then_success_exit_generates_explainable_candidate(tmp_path):
    function = _function(tmp_path, "int work(void) { int ret = step(); if (ret) goto out; out: return 0; }")

    result = analyze_function(function, _mini_protocol())

    assert result is not None
    assert len(result.candidates) == 1
    witness = result.candidates[0].representative_witness
    assert [item["kind"] for item in witness] == ["necessary_step", "branch", "failure", "exit"]
    assert [item["to"] for item in result.candidates[0].control_trace] == [
        "ACTIVE",
        "HANDLING_FAILURE",
        "COMMITTING",
        "EXITED",
    ]


def test_cleanup_label_returning_original_error_is_not_reported(tmp_path):
    function = _function(tmp_path, "int work(void) { int ret = step(); if (ret) goto out; out: return ret; }")

    result = analyze_function(function, _mini_protocol())

    assert result is not None
    assert not result.candidates


def test_successful_second_attempt_resolves_first_failure(tmp_path):
    function = _function(
        tmp_path,
        "int work(void) { int ret = step(); if (ret) { ret = step(); if (ret) return ret; } return 0; }",
    )

    result = analyze_function(function, _mini_protocol())

    assert result is not None
    assert not result.candidates


def test_goto_retry_without_success_does_not_close_failure(tmp_path):
    function = _function(
        tmp_path,
        "int work(void) { int ret; retry: ret = step(); if (ret) goto retry; return 0; }",
    )

    result = analyze_function(function, _mini_protocol())

    assert result is not None
    assert not result.candidates
    assert result.unknown
    assert result.cfg_snapshot["blocks"] > 0


def test_best_effort_failure_is_allowed(tmp_path):
    function = _function(tmp_path, "int work(void) { int ret = step(); if (ret) log(ret); return 0; }")

    result = analyze_function(function, _mini_protocol(best_effort=True))

    assert result is not None
    assert not result.candidates


def test_unresolved_indirect_call_is_unknown_not_candidate(tmp_path):
    function = _function(tmp_path, "int work(int (*step)(void)) { int ret = step(); if (ret) return 0; return 0; }")

    result = analyze_function(function, _mini_protocol())

    assert result is not None
    assert not result.candidates
    assert result.unknown
    assert "unresolved_indirect_call" in result.unknown[0].reasons


def test_allowed_sentinel_fallback_is_not_reported(tmp_path):
    payload = _mini_protocol().to_dict()
    payload["return_contracts"] = [
        {"contract_id": "sentinel", "operation_id": "replay", "guard": "ret == -ENOENT", "outcome": "expected_sentinel", "priority": 100},
        {"contract_id": "failure", "operation_id": "replay", "guard": "ret < 0", "outcome": "failure", "priority": 10},
        {"contract_id": "success", "operation_id": "replay", "guard": "ret == 0", "outcome": "success", "priority": 1},
    ]
    payload["operations"][0]["callee_roles"][0]["return_contract_ids"] = ["sentinel", "failure", "success"]
    protocol = MetadataProtocol.from_dict(payload)
    function = _function(
        tmp_path,
        "int work(void) { int ret = step(); if (ret != -ENOENT) return ret; return create(); }",
    )

    result = analyze_function(function, protocol)

    assert result is not None
    assert not result.candidates


def test_transaction_abort_handler_resolves_failure(tmp_path):
    payload = _mini_protocol().to_dict()
    payload["effects"] = [
        {
            "event_id": "transaction.effect",
            "effect_id": "transaction.update",
            "operation_id": "replay",
            "kind": "METADATA_UPDATE",
            "object": {"role": "operation", "selector": "function"},
            "scope": "TRANSACTION_SCOPED",
            "owner": "transaction",
            "phase": "ENTRY",
            "match_callees": ["begin_update"],
        }
    ]
    payload["handlers"] = [
        {
            "event_id": "transaction.abort",
            "handler_id": "abort.handler",
            "operation_id": "replay",
            "completion_mode": "ABORTED",
            "object": {"role": "operation", "selector": "function"},
            "owner": "transaction_manager",
            "guard": "abort_called",
            "handles_effect_ids": ["transaction.update"],
            "match_callees": ["abort_update"],
        }
    ]
    protocol = MetadataProtocol.from_dict(payload)
    function = _function(
        tmp_path,
        "int work(void) { begin_update(); int ret = step(); if (ret) { abort_update(); return 0; } return 0; }",
    )

    result = analyze_function(function, protocol)

    assert result is not None
    assert not result.candidates


def test_protocol_a_five_development_functions_have_results_and_witnesses():
    protocol = MetadataProtocol.read_json(PROTOCOL_A)
    ext4 = analyze_source_file(
        str(ROOT / "linux-sources" / "linux-v6.8-fs" / "fs" / "ext4" / "fast_commit.c"),
        protocol,
        source_version="linux-v6.8",
        function_names=["ext4_fc_replay_add_range", "ext4_fc_replay_del_range", "ext4_fc_replay_inode"],
    )
    xfs_copy = analyze_source_file(
        str(ROOT / "linux-sources" / "linux-v6.8-fs" / "fs" / "xfs" / "xfs_rtalloc.c"),
        protocol,
        source_version="linux-v6.8",
        function_names=["xfs_rtcopy_summary"],
    )
    xfs_ensure = analyze_source_file(
        str(ROOT / "linux-sources" / "linux-v6.14-fs" / "fs" / "xfs" / "xfs_rtalloc.c"),
        protocol,
        source_version="linux-v6.14",
        function_names=["xfs_rtginode_ensure"],
    )

    results = [*ext4, *xfs_copy, *xfs_ensure]
    assert {item.function for item in results} == {
        "ext4_fc_replay_add_range", "ext4_fc_replay_del_range", "ext4_fc_replay_inode",
        "xfs_rtcopy_summary", "xfs_rtginode_ensure",
    }
    assert all(item.candidates for item in results)
    assert all(candidate.representative_witness for item in results for candidate in item.candidates)


def test_fixed_versions_do_not_repeat_fixed_violation():
    protocol = MetadataProtocol.read_json(PROTOCOL_A)
    ext4 = analyze_source_file(
        str(ROOT / "linux-sources" / "linux-v7.1-fs" / "fs" / "ext4" / "fast_commit.c"),
        protocol,
        source_version="linux-v7.1",
        function_names=["ext4_fc_replay_inode"],
    )[0]
    xfs = analyze_source_file(
        str(ROOT / "linux-sources" / "linux-v7.1-fs" / "fs" / "xfs" / "xfs_rtalloc.c"),
        protocol,
        source_version="linux-v7.1",
        function_names=["xfs_rtcopy_summary"],
    )[0]

    assert not ext4.candidates
    assert not xfs.candidates


def test_cli_writes_dedicated_json_without_touching_baseline_output(tmp_path):
    source = tmp_path / "fixture.c"
    source.write_text("int work(void) { int ret = step(); if (ret) return 0; return 0; }", encoding="utf-8")
    protocol = _mini_protocol()
    protocol_path = tmp_path / "protocol.json"
    protocol.write_json(protocol_path)
    output = tmp_path / "mocc.json"

    assert main(["--protocol", str(protocol_path), "--source", str(source), "--out", str(output)]) == 0

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload[0]["candidates"]
    assert payload[0]["protocol_id"] == "test.protocol_a"
