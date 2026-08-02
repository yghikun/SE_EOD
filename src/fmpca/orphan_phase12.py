from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .c_cfg import FunctionCFG
from .c_cfg_extensions import build_phase5_function_cfg
from .dsl import load_protocol
from .frontend import extract_function
from .model import AnalysisResult, EvidenceEvent
from .orphan_allpath import SourceLocation
from .orphan_phase9 import run_manifest as run_phase9_manifest
from .orphan_phase10 import run_manifest as run_phase10_manifest
from .orphan_phase11 import run_manifest as run_phase11_manifest
from .proof import analyze_state
from .report import count_bug_specific_conditions, write_json, write_markdown
from .semantics_extensions import ProtocolDeadlineEngine


@dataclass(frozen=True)
class MatrixRow:
    filesystem: str
    evaluation_role: str
    applicability: str
    qualified_profile: str
    normal_profile_conformance: str
    failure_path_conformance: str
    heldout_disposition: str


@dataclass(frozen=True)
class CounterexampleAudit:
    rule: str
    source_partition: str
    source_slice: Tuple[SourceLocation, ...]
    source_control_flow_closed: bool
    fixture: str
    event_sequence: Tuple[str, ...]
    expected_result: str
    actual_result: str
    violation_rules: Tuple[str, ...]
    deletion_trials: Tuple[Dict[str, Any], ...]
    rule_specific_irreducible: bool
    source_replay_bridge_closed: bool

    @property
    def closed(self) -> bool:
        return (
            bool(self.source_slice)
            and self.source_control_flow_closed
            and self.actual_result == self.expected_result
            and self.rule in self.violation_rules
            and self.rule_specific_irreducible
            and self.source_replay_bridge_closed
        )

    def to_dict(self) -> Dict[str, Any]:
        value = json.loads(json.dumps(asdict(self)))
        value["closed"] = self.closed
        return value


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path: str) -> Dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _verify_hashes(values: Dict[str, str], label: str) -> Dict[str, bool]:
    if not values:
        raise ValueError(f"{label} hash lock must not be empty")
    result: Dict[str, bool] = {}
    for path, expected in values.items():
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"{label} hash mismatch for {path}: {actual} != {expected}")
        result[path] = True
    return result


def _cfg(source_root: str, relative: str, function_name: str) -> FunctionCFG:
    return build_phase5_function_cfg(str(Path(source_root) / relative), function_name)


def _call(cfg: FunctionCFG, name: str) -> Optional[int]:
    nodes = cfg.find_calls([name])
    return min(nodes, key=lambda node: cfg.nodes[node].line) if nodes else None


def _text(cfg: FunctionCFG, marker: str) -> Optional[int]:
    nodes = cfg.find_text([marker])
    return min(nodes, key=lambda node: cfg.nodes[node].line) if nodes else None


def _loc(cfg: FunctionCFG, node: Optional[int], fact: str) -> Tuple[SourceLocation, ...]:
    if node is None:
        return ()
    value = cfg.nodes[node]
    return (SourceLocation(cfg.source_path, cfg.function_name, value.line, node, fact),)


def _function_loc(path: str, function_name: str, marker: str, fact: str) -> Optional[SourceLocation]:
    source = Path(path).read_text(encoding="utf-8")
    function = extract_function(source, function_name)
    offset = function.masked_text.find(marker)
    if offset < 0:
        return None
    return SourceLocation(path, function_name, function.line_for_offset(offset), -1, fact)


def _healthy(cfgs: Iterable[FunctionCFG]) -> bool:
    return all(not cfg.parse_has_error and not cfg.unresolved_gotos for cfg in cfgs)


def _run_events(
    protocol_path: str, fixture: Dict[str, Any], events: Sequence[Dict[str, Any]]
) -> Tuple[str, Tuple[str, ...]]:
    closure = fixture["closure"]
    state = ProtocolDeadlineEngine(load_protocol(protocol_path)).run(
        EvidenceEvent.from_dict(item) for item in events
    )
    report = analyze_state(
        state,
        path_model_closed=closure["path_model_closed"],
        all_paths_closed=closure["all_paths_closed"],
        repair_slice_closed=closure["repair_slice_closed"],
        alias_closed=closure["alias_closed"],
    )
    return report.result.value, tuple(report.violation_rules)


def _audit_fixture(
    protocol_path: str,
    fixture_path: str,
    source_slice: Tuple[SourceLocation, ...],
    source_control_flow_closed: bool,
    required_source_facts: Tuple[str, ...],
) -> CounterexampleAudit:
    fixture = _load(fixture_path)
    events = fixture["events"]
    rule = fixture["expected_rule"]
    actual, rules = _run_events(protocol_path, fixture, events)
    trials: List[Dict[str, Any]] = []
    for index, event in enumerate(events):
        reduced = events[:index] + events[index + 1 :]
        result, reduced_rules = _run_events(protocol_path, fixture, reduced)
        trials.append(
            {
                "removed_index": index,
                "removed_event": event["event"],
                "actual_result": result,
                "violation_rules": list(reduced_rules),
                "target_rule_absent": rule not in reduced_rules,
            }
        )
    facts = {item.fact for item in source_slice}
    return CounterexampleAudit(
        rule,
        fixture["source_partition"],
        source_slice,
        source_control_flow_closed,
        fixture_path,
        tuple(item["event"] for item in events),
        fixture["expected"],
        actual,
        rules,
        tuple(trials),
        bool(trials) and all(item["target_rule_absent"] for item in trials),
        set(required_source_facts).issubset(facts),
    )


def audit_counterexamples(manifest: Dict[str, Any]) -> Tuple[CounterexampleAudit, ...]:
    source_root = manifest["source_root"]
    super_path = str(Path(source_root) / "fs/reiserfs/super.c")
    unlink = _cfg(source_root, "fs/reiserfs/namei.c", "reiserfs_unlink")
    add = _cfg(source_root, "fs/reiserfs/super.c", "add_save_link")
    finish = _cfg(source_root, "fs/reiserfs/super.c", "finish_unfinished")
    fill = _cfg(source_root, "fs/reiserfs/super.c", "reiserfs_fill_super")

    insert = _call(add, "reiserfs_insert_item")
    insert_error = _text(add, "(retval)")
    add_call = _call(unlink, "add_save_link")
    unlink_commit = _call(unlink, "journal_end")
    void_signature = _function_loc(
        super_path,
        "add_save_link",
        "void add_save_link",
        "registration helper has no result channel",
    )
    o1_slice = (
        ((void_signature,) if void_signature else ())
        + _loc(add, insert, "persistent registration insertion can fail")
        + _loc(add, insert_error, "failed insertion returns without propagation")
        + _loc(unlink, add_call, "unlink invokes the void registration helper")
        + _loc(unlink, unlink_commit, "namespace transaction commit remains reachable")
    )
    o1_flow = (
        _healthy((unlink, add))
        and all(item is not None for item in (insert, insert_error, add_call, unlink_commit))
        and void_signature is not None
        and add.can_reach(insert, insert_error)
        and unlink.can_reach(add_call, unlink_commit)
    )

    finish_return = _text(finish, "return retval")
    finish_call = _call(fill, "finish_unfinished")
    mount_return = _text(fill, "return (0)")
    ignored_call = _function_loc(
        super_path,
        "reiserfs_fill_super",
        "finish_unfinished(s);",
        "mount discards the recovery cleanup result",
    )
    o3_slice = (
        _loc(finish, finish_return, "recovery scan returns cleanup failure")
        + ((ignored_call,) if ignored_call else ())
        + _loc(fill, finish_call, "synchronous recovery scan is called")
        + _loc(fill, mount_return, "successful mount exposure remains reachable")
    )
    o3_flow = (
        _healthy((finish, fill))
        and all(item is not None for item in (finish_return, finish_call, mount_return))
        and ignored_call is not None
        and fill.can_reach(finish_call, mount_return)
    )

    fixture_by_rule = {item["rule"]: item["fixture"] for item in manifest["counterexamples"]}
    return (
        _audit_fixture(
            manifest["protocol"],
            fixture_by_rule["OIDS-O1"],
            o1_slice,
            o1_flow,
            (
                "registration helper has no result channel",
                "persistent registration insertion can fail",
                "namespace transaction commit remains reachable",
            ),
        ),
        _audit_fixture(
            manifest["protocol"],
            fixture_by_rule["OIDS-O3"],
            o3_slice,
            o3_flow,
            (
                "recovery scan returns cleanup failure",
                "mount discards the recovery cleanup result",
                "successful mount exposure remains reachable",
            ),
        ),
    )


def build_matrix(
    phase9: Dict[str, Any], phase10: Dict[str, Any], phase11: Dict[str, Any]
) -> Tuple[MatrixRow, ...]:
    formation = {item["filesystem"]: item for item in phase9["assessment"]["filesystems"]}
    return (
        MatrixRow(
            "btrfs",
            "FREEZE_FORMATION_DEVELOPMENT",
            "APPLICABLE",
            formation["btrfs"]["configuration_scope"],
            "CLOSED" if formation["btrfs"]["closed"] else "BLOCKED",
            "NOT_POST_COMMON_HELDOUT_TESTED",
            "NOT_HELDOUT",
        ),
        MatrixRow(
            "ext4",
            "FREEZE_FORMATION_VALIDATION",
            "APPLICABLE_WITH_EXPLICIT_CONFIGURATION_BOUNDARY",
            formation["ext4"]["configuration_scope"],
            "CLOSED" if formation["ext4"]["closed"] else "BLOCKED",
            "ERRORS_CONT_EXCLUDED_WITH_NEGATIVE_WITNESSES",
            "NOT_HELDOUT",
        ),
        MatrixRow(
            "ubifs",
            "FREEZE_FORMATION_VALIDATION",
            "APPLICABLE_WITH_EXPLICIT_RECOVERY_PROFILE",
            formation["ubifs"]["configuration_scope"],
            "CLOSED" if formation["ubifs"]["closed"] else "BLOCKED",
            "READ_ONLY_RECOVERY_DEFERRED_OUTSIDE_PROFILE",
            "NOT_POST_COMMON_HELDOUT",
        ),
        MatrixRow(
            "ocfs2",
            "POST_COMMON_BLIND_SCREENING",
            phase10["applicability"],
            "RECOVERY_ASYNCHRONOUS_AFTER_MOUNT_EXPOSURE",
            "LIVE_ONLY_CLOSED" if phase10["assessment"]["registration"]["closed"] else "BLOCKED",
            "NOT_EVALUABLE_UNDER_COMMON_DEADLINE",
            "CONTROLLED_NON_APPLICABLE_" + phase10["controlled_reason_code"],
        ),
        MatrixRow(
            "reiserfs",
            "POST_COMMON_BLIND_HELD_OUT",
            phase11["applicability"],
            "LIVE_DELETION_AND_SUCCESSFUL_RW_RECOVERY_EXPOSURE_PLUS_FAILURE_PARTITIONS",
            "CLOSED" if phase11["assessment"]["positive_replays_conform"] else "BLOCKED",
            "REFUTED_BY_OIDS_O1_AND_OIDS_O3"
            if phase11["assessment"]["violation_proof_closed"]
            else "UNRESOLVED",
            phase11["conformance_decision"],
        ),
    )


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = _load(path)
    artifacts = _verify_hashes(manifest["artifact_hashes"], "Phase 12 artifact")
    phase9 = run_phase9_manifest(manifest["phase9_manifest"])
    phase10 = run_phase10_manifest(manifest["phase10_manifest"])
    phase11 = run_phase11_manifest(manifest["phase11_manifest"])
    catalog = _load(manifest["claim_catalog"])
    scope = _load(manifest["phase9_scope"])

    matrix = build_matrix(phase9, phase10, phase11)
    matrix_values = [asdict(item) for item in matrix]
    matrix_matches_catalog = matrix_values == catalog["rows"]
    audits = audit_counterexamples(manifest)
    counterexamples_closed = all(item.closed for item in audits)

    frozen_predicates = " ".join(
        item["applicability_predicate"] for item in scope["filesystems"]
    )
    rejected = catalog["narrowing_audit"]["rejected_outcome_predicates"]
    no_outcome_predicates_in_frozen_scope = all(
        predicate not in frozen_predicates for predicate in rejected
    )
    narrowing_audit_closed = (
        no_outcome_predicates_in_frozen_scope
        and catalog["narrowing_audit"]["decision"]
        == "POST_REVEAL_OUTCOME_NARROWING_REJECTED"
    )

    semantic_applicability_supported = (
        phase9["common_freeze_ready"]
        and phase11["applicability"] == "APPLICABLE"
        and phase11["assessment"]["correspondence_closed"]
        and phase10["applicability"] == "NON_APPLICABLE"
        and phase10["controlled_reason_code"] == "DEADLINE_NOT_ALIGNED"
    )
    normal_profiles_supported = (
        phase9["assessment"]["closed"]
        and phase10["assessment"]["replays"][0]["actual"]
        == AnalysisResult.CONFORMANT.value
        and phase11["assessment"]["positive_replays_conform"]
    )
    failure_path_conformance_refuted = (
        counterexamples_closed
        and phase11["conformance_decision"] == "NON_CONFORMANT_HELDOUT"
        and not phase11["candidate_conformant"]
    )
    disposition = {
        "common_semantic_applicability": "SUPPORTED_UNDER_FROZEN_NARROW_SCOPE"
        if semantic_applicability_supported
        else "UNRESOLVED",
        "common_normal_profile_conformance": "SUPPORTED_FOR_EVALUATED_QUALIFIED_PROFILES"
        if normal_profiles_supported
        else "UNRESOLVED",
        "common_failure_path_conformance": "REFUTED_BY_POST_COMMON_HELDOUT_COUNTEREXAMPLE"
        if failure_path_conformance_refuted
        else "UNRESOLVED",
        "common_heldout_validated": False,
        "universal_filesystem_conformance": "NOT_CLAIMED",
        "protocol_v0_1_disposition": "FROZEN_WITH_RETAINED_COUNTEREXAMPLE",
        "revised_protocol_requirement": "NEW_VERSION_AND_NEW_EVALUATION_SPLIT",
    }
    disposition_matches_catalog = disposition == catalog["claim_disposition"]
    historical_results_preserved = (
        phase9["common_freeze_manifest_generated"]
        and phase10["phase10_screening_closed"]
        and phase11["phase11_screening_closed"]
        and not phase9["common_heldout_validated"]
        and not phase10["common_heldout_validated"]
        and not phase11["common_heldout_validated"]
    )
    phase12_closed = (
        all(artifacts.values())
        and historical_results_preserved
        and matrix_matches_catalog
        and counterexamples_closed
        and narrowing_audit_closed
        and disposition_matches_catalog
        and semantic_applicability_supported
        and normal_profiles_supported
        and failure_path_conformance_refuted
    )
    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "manifest": path,
        "manifest_sha256": _sha256(path),
        "artifact_hashes_verified": all(artifacts.values()),
        "historical_results_preserved": historical_results_preserved,
        "phase9_common_freeze_preserved": phase9["common_freeze_manifest_generated"],
        "phase10_controlled_non_applicable_preserved": phase10["phase10_screening_closed"],
        "phase11_nonconformant_heldout_preserved": phase11["phase11_screening_closed"],
        "matrix": matrix_values,
        "matrix_matches_catalog": matrix_matches_catalog,
        "counterexample_audits": [item.to_dict() for item in audits],
        "counterexamples_closed": counterexamples_closed,
        "no_outcome_predicates_in_frozen_scope": no_outcome_predicates_in_frozen_scope,
        "narrowing_audit_closed": narrowing_audit_closed,
        "claim_disposition": disposition,
        "disposition_matches_catalog": disposition_matches_catalog,
        "semantic_applicability_supported": semantic_applicability_supported,
        "normal_profiles_supported": normal_profiles_supported,
        "failure_path_conformance_refuted": failure_path_conformance_refuted,
        "common_heldout_validated": False,
        "protocol_v0_1_mutated": False,
        "bug_specific_condition_count": count_bug_specific_conditions([manifest]),
        "phase12_claim_disposition_closed": phase12_closed,
        "next_phase_plan": manifest["next_phase_plan"],
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# OIDS Phase 12 COMMON Claim Disposition and Counterexample Audit",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"Disposition closed: `{summary['phase12_claim_disposition_closed']}`",
        f"Historical results preserved: `{summary['historical_results_preserved']}`",
        f"COMMON held-out validated: `{summary['common_heldout_validated']}`",
        "",
        "## Cross-filesystem matrix",
        "",
        "| Filesystem | Role | Applicability | Normal profile | Failure path | Held-out disposition |",
        "|---|---|---|---|---|---|",
    ]
    for row in summary["matrix"]:
        lines.append(
            f"| {row['filesystem']} | {row['evaluation_role']} | {row['applicability']} | "
            f"{row['normal_profile_conformance']} | {row['failure_path_conformance']} | "
            f"{row['heldout_disposition']} |"
        )
    lines.extend(["", "## Counterexample audit", "", "| Rule | Source flow | Replay | Irreducible | Closed |", "|---|---|---|---|---|"])
    for audit in summary["counterexample_audits"]:
        lines.append(
            f"| {audit['rule']} | `{audit['source_control_flow_closed']}` | "
            f"`{audit['actual_result']}` | `{audit['rule_specific_irreducible']}` | "
            f"`{audit['closed']}` |"
        )
    lines.extend(["", "## Claim disposition", ""])
    for name, value in summary["claim_disposition"].items():
        lines.append(f"- `{name}`: `{value}`")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            summary["interpretation"],
            "",
            "Next phase: " + summary["next_phase_plan"],
            "",
        ]
    )
    return "\n".join(lines)


def run_and_write(manifest: str, json_out: str, markdown_out: str) -> Dict[str, Any]:
    summary = run_manifest(manifest)
    write_json(json_out, summary)
    write_markdown(markdown_out, _markdown(summary))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_phase12")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"disposition_closed={summary['phase12_claim_disposition_closed']} "
        f"failure_path={summary['claim_disposition']['common_failure_path_conformance']} "
        f"common_heldout={summary['common_heldout_validated']}"
    )
    return 0 if summary["phase12_claim_disposition_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
