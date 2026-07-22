import json
from pathlib import Path
from typing import Optional

from src.frontend.tree_sitter_frontend import TreeSitterFrontend
from src.metadata_event import extract_metadata_events
from src.metadata_protocol import MetadataProtocol
from src.metadata_protocol_discovery import (
    confirmed_function_names,
    discover_source_tree,
    _dedupe_records,
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


def _mini_discovery_protocol(*, discovery: Optional[dict] = None) -> MetadataProtocol:
    operation = {
        "operation_id": "semantic_replay",
        "entry_functions": ["work"],
        "principal_objects": [{"role": "operation", "selector": "function"}],
        "callee_roles": [
            {
                "role_id": "step",
                "callees": ["step"],
                "necessary": True,
                "return_contract_ids": ["failure", "success"],
            },
            {
                "role_id": "context",
                "callees": ["context_gate"],
                "necessary": False,
                "return_contract_ids": [],
            },
        ],
    }
    if discovery is not None:
        operation["discovery"] = discovery
    return MetadataProtocol.from_dict(
        {
            "schema_version": 1,
            "protocol_version": "1.0.0",
            "protocol_id": "test.discovery",
            "filesystems": ["fixture"],
            "linux_versions": ["test"],
            "phases": ["ENTRY", "SUCCESS", "FAILURE"],
            "operations": [operation],
            "return_contracts": [
                {
                    "contract_id": "failure",
                    "operation_id": "semantic_replay",
                    "guard": "ret != 0",
                    "outcome": "failure",
                },
                {
                    "contract_id": "success",
                    "operation_id": "semantic_replay",
                    "guard": "ret == 0",
                    "outcome": "success",
                },
            ],
            "effects": [],
            "compensations": [],
            "handlers": [],
            "accounting_constraints": [],
            "legal_exits": [
                {
                    "exit_id": "success",
                    "operation_id": "semantic_replay",
                    "kind": "success",
                    "phases": ["SUCCESS"],
                    "completion_modes": ["COMMITTED"],
                    "return_outcomes": ["success"],
                },
                {
                    "exit_id": "failure",
                    "operation_id": "semantic_replay",
                    "kind": "failure",
                    "phases": ["FAILURE"],
                    "completion_modes": ["ROLLED_BACK"],
                    "return_outcomes": ["failure"],
                },
            ],
        }
    )


def _ambiguous_protocol() -> MetadataProtocol:
    payload = _mini_discovery_protocol().to_dict()
    second = json.loads(json.dumps(payload["operations"][0]))
    second["operation_id"] = "semantic_replay_copy"
    payload["operations"].append(second)
    original_contracts = tuple(payload["return_contracts"])
    payload["return_contracts"].extend(
        {
            **item,
            "contract_id": f"copy.{item['contract_id']}",
            "operation_id": "semantic_replay_copy",
        }
        for item in original_contracts
    )
    original_exits = tuple(payload["legal_exits"])
    payload["legal_exits"].extend(
        {
            **item,
            "exit_id": f"copy.{item['exit_id']}",
            "operation_id": "semantic_replay_copy",
        }
        for item in original_exits
    )
    payload["operations"][1]["callee_roles"][0]["return_contract_ids"] = [
        "copy.failure",
        "copy.success",
    ]
    return MetadataProtocol.from_dict(payload)


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


def test_exact_entry_candidates_are_protocol_candidates(tmp_path):
    protocol = _mini_discovery_protocol()
    _write_source(
        tmp_path,
        "fs/fixture/work.c",
        "int work(void) { int ret = step(); if (ret) return 0; return 0; }",
    )

    report = discover_source_tree(tmp_path, [protocol]).to_dict()
    analysis = report["analyses"][0]

    assert report["summary"]["protocol_candidate_occurrences"] == 1
    assert analysis["applicability"]["match_kind"] == "exact_entry"
    assert analysis["candidates"][0]["classification"] == "PROTOCOL_CANDIDATE"
    assert not analysis["discovery_review"]


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


def test_two_of_five_roles_do_not_overmatch_broad_operation(tmp_path):
    protocol = MetadataProtocol.read_json(PROTOCOL_A)
    path = _write_source(
        tmp_path,
        "fs/ext4/shared.c",
        """
int helper(void)
{
    int ret = ext4_map_blocks();
    if (ret < 0)
        return ret;
    return IS_ERR(ext4_find_extent()) ? -1 : 0;
}
""",
    )
    function = TreeSitterFrontend(source_root=tmp_path).parse(path).functions[0]

    evidence = operation_applicability(function, protocol)
    add = next(
        item for item in evidence if item.operation_id == "ext4_replay_add_range"
    )

    assert add.matched_role_ids == ("find_extent", "map_blocks")
    assert not add.applicable


def test_required_discovery_context_blocks_partial_semantic_match(tmp_path):
    protocol = _mini_discovery_protocol(
        discovery={"required_callees": ["context_gate"]}
    )
    path = _write_source(
        tmp_path,
        "fs/fixture/replay.c",
        "int renamed(void) { int ret = step(); if (ret) return 0; return 0; }",
    )
    function = TreeSitterFrontend(source_root=tmp_path).parse(path).functions[0]

    evidence = operation_applicability(function, protocol)[0]

    assert not evidence.applicable
    assert evidence.unmatched_discovery_callees == ("context_gate",)


def test_required_discovery_context_can_support_semantic_review(tmp_path):
    protocol = _mini_discovery_protocol(
        discovery={"required_callees": ["context_gate"]}
    )
    _write_source(
        tmp_path,
        "fs/fixture/replay.c",
        """
int renamed(void)
{
    context_gate();
    int ret = step();
    if (ret)
        return 0;
    return 0;
}
""",
    )

    report = discover_source_tree(tmp_path, [protocol]).to_dict()
    analysis = report["analyses"][0]

    assert report["summary"]["protocol_candidate_occurrences"] == 0
    assert report["summary"]["discovery_review_occurrences"] == 1
    assert analysis["applicability"]["matched_discovery_callees"] == [
        "context_gate"
    ]
    assert analysis["discovery_review"][0]["classification"] == "DISCOVERY_REVIEW"


def test_semantic_analysis_unknown_is_kept_out_of_protocol_unknown(tmp_path):
    protocol = _mini_discovery_protocol(
        discovery={"required_callees": ["context_gate"]}
    )
    _write_source(
        tmp_path,
        "fs/fixture/replay.c",
        """
int renamed(int (*step)(void))
{
    context_gate();
    int ret = step();
    if (ret)
        return 0;
    return 0;
}
""",
    )

    report = discover_source_tree(tmp_path, [protocol]).to_dict()
    analysis = report["analyses"][0]

    assert not analysis["candidates"]
    assert not analysis["discovery_review"]
    assert analysis["unknown"][0]["classification"] == "DISCOVERY_REVIEW_UNKNOWN"
    assert analysis["unknown"][0]["applicability_match_kind"] == "semantic"


def test_ambiguous_operation_match_is_quarantined(tmp_path):
    protocol = _ambiguous_protocol()
    _write_source(
        tmp_path,
        "fs/fixture/work.c",
        "int work(void) { int ret = step(); if (ret) return 0; return 0; }",
    )

    report = discover_source_tree(tmp_path, [protocol]).to_dict()

    assert not report["analyses"]
    assert report["summary"]["discovery_unknown"] == 1
    assert report["quarantine"][0]["reason"] == "ambiguous_operation_match"
    assert {
        item["operation_id"]
        for item in report["quarantine"][0]["competing_operations"]
    } == {"semantic_replay", "semantic_replay_copy"}


def test_call_specs_from_another_operation_do_not_contaminate_events(tmp_path):
    protocol = MetadataProtocol.read_json(
        ROOT
        / "configs"
        / "metadata_protocols"
        / "protocol_b_device_topology_v1.json"
    )
    path = _write_source(
        tmp_path,
        "fs/btrfs/relocation.c",
        """
int btrfs_recover_relocation(struct btrfs_fs_info *fs_info)
{
    int ret = btrfs_commit_transaction(trans);
    if (ret)
        return ret;
    btrfs_assign_next_active_device(fs_info, device, NULL);
    return 0;
}
""",
    )
    function = TreeSitterFrontend(source_root=tmp_path).parse(path).functions[0]

    events = extract_metadata_events(function, protocol)

    assert not any(
        item.effect_spec_id.startswith("sprout.")
        for item in events
    )


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
    assert first["summary"]["protocol_candidate_occurrences"] == 0
    assert first["summary"]["discovery_review_occurrences"] >= 1
    analysis = first["analyses"][0]
    assert analysis["function"] == "custom_replay_del"
    assert analysis["operation_id"] == "ext4_replay_del_range"
    assert analysis["applicability"]["match_kind"] == "semantic"
    assert not analysis["candidates"]
    assert {
        item["classification"] for item in analysis["discovery_review"]
    } == {"DISCOVERY_REVIEW"}
    assert {
        item["family_fingerprint"] for item in analysis["discovery_review"]
    } == {
        item["family_fingerprint"]
        for item in second["analyses"][0]["discovery_review"]
    }
    assert first["summary"]["skip_reasons"]["filesystem_not_applicable"] >= 1


def test_occurrence_deduplication_keeps_shortest_witness():
    long = {
        "occurrence_fingerprint": "same",
        "representative_witness": [{"kind": "a"}, {"kind": "b"}],
    }
    short = {
        "occurrence_fingerprint": "same",
        "representative_witness": [{"kind": "a"}],
    }

    assert _dedupe_records([long, short]) == (short,)


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
    assert payload["schema_version"] == 3
    assert payload["source_version"] == "fixture-v1"
    assert payload["summary"]["discovery_review_occurrences"] >= 1


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


def test_leave_one_function_out_uses_broad_semantics_without_named_anchor(tmp_path):
    payload = _mini_discovery_protocol().to_dict()
    operation = payload["operations"][0]
    operation["entry_functions"] = []
    operation["callee_roles"] = []
    operation["discovery"] = {
        "semantic_patterns": ["failure_return_mismatch"]
    }
    protocol = MetadataProtocol.from_dict(payload)
    _write_source(
        tmp_path,
        "fs/fixture/replay.c",
        """
int work(void)
{
    int status = opaque_metadata_step();
    if (status < 0)
        goto out;
out:
    return 0;
}
""",
    )

    report = discover_source_tree(tmp_path, [protocol]).to_dict()

    assert report["summary"]["protocol_candidate_occurrences"] == 0
    assert report["summary"]["discovery_review_occurrences"] == 1
    review = report["broad_discovery_review"][0]
    assert review["function"] == "work"
    assert review["applicability_match_kind"] == "broad_semantic"
    assert review["semantic_pattern"] == "failure_return_mismatch"
    assert set(review["semantic_signals"]) == {
        "failure_guard",
        "failure_to_success_exit",
        "fallible_call",
        "success_exit",
    }


def test_broad_semantics_uses_first_result_guard(tmp_path):
    payload = _mini_discovery_protocol().to_dict()
    operation = payload["operations"][0]
    operation["entry_functions"] = []
    operation["callee_roles"] = []
    operation["discovery"] = {
        "semantic_patterns": ["failure_return_mismatch"]
    }
    protocol = MetadataProtocol.from_dict(payload)
    _write_source(
        tmp_path,
        "fs/fixture/positive_result.c",
        """
int positive_result(void)
{
    int ret = opaque_metadata_step();
    if (ret < 0)
        return ret;
    if (ret != 0)
        return 0;
    return 0;
}
""",
    )

    report = discover_source_tree(tmp_path, [protocol]).to_dict()

    assert report["summary"]["discovery_review_occurrences"] == 0


def test_broad_semantics_excludes_nonfallible_kernel_helpers(tmp_path):
    payload = _mini_discovery_protocol().to_dict()
    operation = payload["operations"][0]
    operation["entry_functions"] = []
    operation["callee_roles"] = []
    operation["discovery"] = {
        "semantic_patterns": ["mutation_failure_cleanup"]
    }
    protocol = MetadataProtocol.from_dict(payload)
    helpers = {
        "container_helper": "container_of(ptr, struct item, member)",
        "list_helper": "list_first_entry(head, struct item, member)",
        "inode_helper": "BTRFS_I(inode)",
        "atomic_helper": "atomic_read(counter)",
    }
    for name, call in helpers.items():
        _write_source(
            tmp_path,
            f"fs/fixture/{name}.c",
            f"""
int {name}(struct state *state, void *ptr)
{{
    state->changed = 1;
    void *value = {call};
    if (!value)
        return -1;
    return 0;
}}
""",
        )

    report = discover_source_tree(tmp_path, [protocol]).to_dict()

    assert report["summary"]["discovery_review_occurrences"] == 0


def test_broad_semantics_excludes_boolean_stop_helpers(tmp_path):
    payload = _mini_discovery_protocol().to_dict()
    operation = payload["operations"][0]
    operation["entry_functions"] = []
    operation["callee_roles"] = []
    operation["discovery"] = {
        "semantic_patterns": ["mutation_failure_cleanup"]
    }
    protocol = MetadataProtocol.from_dict(payload)
    _write_source(
        tmp_path,
        "fs/fixture/readdir.c",
        """
int readdir_cursor(struct ctx *ctx)
{
    ctx->pos = 7;
    int over = !dir_emit(ctx, "name", 4, 1, 0);
    if (over)
        return 1;
    ctx->pos++;
    return 0;
}
""",
    )

    report = discover_source_tree(tmp_path, [protocol]).to_dict()

    assert report["summary"]["discovery_review_occurrences"] == 0


def test_mutation_cleanup_ignores_restored_temporary_state(tmp_path):
    payload = _mini_discovery_protocol().to_dict()
    operation = payload["operations"][0]
    operation["entry_functions"] = []
    operation["callee_roles"] = []
    operation["discovery"] = {
        "semantic_patterns": ["mutation_failure_cleanup"]
    }
    protocol = MetadataProtocol.from_dict(payload)
    _write_source(
        tmp_path,
        "fs/fixture/restored_temp.c",
        """
int restored_temp(struct trans *trans, struct state *state)
{
    void *old = trans->block_rsv;
    trans->block_rsv = state->block_rsv;
    int ret = fallible_metadata_step();
    trans->block_rsv = old;
    if (ret)
        return ret;
    return 0;
}
""",
    )

    report = discover_source_tree(tmp_path, [protocol]).to_dict()

    assert report["summary"]["discovery_review_occurrences"] == 0


def test_mutation_cleanup_ignores_cleanup_before_failure_guard(tmp_path):
    payload = _mini_discovery_protocol().to_dict()
    operation = payload["operations"][0]
    operation["entry_functions"] = []
    operation["callee_roles"] = []
    operation["discovery"] = {
        "semantic_patterns": ["mutation_failure_cleanup"]
    }
    protocol = MetadataProtocol.from_dict(payload)
    _write_source(
        tmp_path,
        "fs/fixture/cleanup_before_guard.c",
        """
int cleanup_before_guard(struct state *state)
{
    state->flags |= LOGGING;
    int ret = fallible_metadata_step();
    clear_state_logging(state);
    if (ret)
        return ret;
    return 0;
}
""",
    )

    report = discover_source_tree(tmp_path, [protocol]).to_dict()

    assert report["summary"]["discovery_review_occurrences"] == 0


def test_mutation_cleanup_requires_mutation_to_reach_fallible_call(tmp_path):
    payload = _mini_discovery_protocol().to_dict()
    operation = payload["operations"][0]
    operation["entry_functions"] = []
    operation["callee_roles"] = []
    operation["discovery"] = {
        "semantic_patterns": ["mutation_failure_cleanup"]
    }
    protocol = MetadataProtocol.from_dict(payload)
    _write_source(
        tmp_path,
        "fs/fixture/unreachable_mutation.c",
        """
int unreachable_mutation(struct state *state, int already_done)
{
    if (already_done) {
        state->changed = 1;
        return 0;
    }
    int ret = fallible_metadata_step();
    if (ret)
        return ret;
    return 0;
}
""",
    )

    report = discover_source_tree(tmp_path, [protocol]).to_dict()

    assert report["summary"]["discovery_review_occurrences"] == 0


def test_mutation_cleanup_requires_mutation_before_fallible_call(tmp_path):
    payload = _mini_discovery_protocol().to_dict()
    operation = payload["operations"][0]
    operation["entry_functions"] = []
    operation["callee_roles"] = []
    operation["discovery"] = {
        "semantic_patterns": ["mutation_failure_cleanup"]
    }
    protocol = MetadataProtocol.from_dict(payload)
    _write_source(
        tmp_path,
        "fs/fixture/mutation_after.c",
        """
int mutation_after(struct state *state)
{
    int ret = fallible_metadata_step();
    if (ret)
        return ret;
    state->changed = 1;
    return 0;
}
""",
    )
    _write_source(
        tmp_path,
        "fs/fixture/mutation_before.c",
        """
int mutation_before(struct state *state)
{
    state->changed = 1;
    int ret = fallible_metadata_step();
    if (ret)
        return ret;
    return 0;
}
""",
    )
    _write_source(
        tmp_path,
        "fs/fixture/field_read_before.c",
        """
int field_read_before(struct state *state)
{
    int previous = state->changed;
    int ret = fallible_metadata_step(previous);
    if (ret)
        return ret;
    return 0;
}
""",
    )

    report = discover_source_tree(tmp_path, [protocol]).to_dict()

    assert [
        item["function"] for item in report["broad_discovery_review"]
    ] == ["mutation_before"]


def test_real_known_function_leave_one_out_enters_broad_review():
    payload = MetadataProtocol.read_json(
        ROOT
        / "configs"
        / "metadata_protocols"
        / "protocol_a_replay_recovery_v1.json"
    ).to_dict()
    for operation in payload["operations"]:
        if operation["operation_id"] == "ext4_replay_inode":
            operation["entry_functions"] = []
            operation["callee_roles"] = []
            operation["discovery"] = {
                "semantic_patterns": ["failure_return_mismatch"]
            }
        else:
            operation["discovery"] = {}
    protocol = MetadataProtocol.from_dict(payload)

    report = discover_source_tree(
        ROOT / "linux-sources" / "linux-v6.8-fs" / "fs" / "ext4" / "fast_commit.c",
        [protocol],
        source_version="linux-v6.8",
    ).to_dict()

    reviews = {
        item["function"]: item for item in report["broad_discovery_review"]
    }
    assert reviews["ext4_fc_replay_inode"]["classification"] == "DISCOVERY_REVIEW"
    assert (
        reviews["ext4_fc_replay_inode"]["applicability_match_kind"]
        == "broad_semantic"
    )
    assert reviews["ext4_fc_replay_inode"]["semantic_pattern"] == (
        "failure_return_mismatch"
    )


def test_fresh_queue_excludes_confirmed_and_seed_functions(tmp_path):
    payload = _mini_discovery_protocol().to_dict()
    operation = payload["operations"][0]
    operation["discovery"] = {
        "semantic_patterns": ["failure_return_mismatch"]
    }
    protocol = MetadataProtocol.from_dict(payload)
    source = """
int {name}(void)
{{
    int ret = metadata_step();
    if (ret)
        goto out;
out:
    return 0;
}}
"""
    for name in ("work", "confirmed_case", "fresh_case"):
        _write_source(
            tmp_path,
            f"fs/fixture/{name}.c",
            source.format(name=name),
        )

    report = discover_source_tree(
        tmp_path,
        [protocol],
        excluded_functions=("confirmed_case",),
        exclude_regression_seeds=True,
    ).to_dict()

    assert report["summary"]["excluded_functions"] == 2
    assert report["summary"]["fresh_review_functions"] == 1
    assert [item["function"] for item in report["fresh_review_queue"]] == [
        "fresh_case"
    ]
    assert report["summary"]["skip_reasons"]["excluded_function"] == 2


def test_confirmed_function_names_reads_summary_once(tmp_path):
    ledger = tmp_path / "confirmed.md"
    ledger.write_text(
        """# Confirmed Bugs

## Summary

| # | FS | Function | Bug type | Status | Evidence |
|---:|---|---|---|---|---|
| 1 | ext4 | `known()` | swallowed | fixed | patch |
| 2 | ext4 | `known()` | another occurrence | fixed | patch |
| 3 | xfs | `other()` | swallowed | fixed | patch |
""",
        encoding="utf-8",
    )

    assert confirmed_function_names(ledger) == ("known", "other")
