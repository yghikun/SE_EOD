from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .diagnostics import diagnose_failure, load_diagnostic_extension
from .dsl import load_protocol
from .model import EvidenceEvent
from .orphan_phase6 import run_manifest as run_phase6_manifest
from .orphan_phase8 import run_manifest as run_phase8_manifest
from .orphan_phase9 import run_manifest as run_phase9_manifest
from .orphan_phase10 import run_manifest as run_phase10_manifest
from .orphan_phase13 import run_manifest as run_phase13_manifest
from .proof import analyze_state
from .report import write_json, write_markdown
from .semantics_extensions import ProtocolDeadlineEngine


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


def _run_fixture(protocol_path: str, fixture_path: str) -> Dict[str, Any]:
    fixture = _load(fixture_path)
    closure = fixture["closure"]
    state = ProtocolDeadlineEngine(load_protocol(protocol_path)).run(
        EvidenceEvent.from_dict(item) for item in fixture["events"]
    )
    report = analyze_state(
        state,
        path_model_closed=closure["path_model_closed"],
        all_paths_closed=closure["all_paths_closed"],
        repair_slice_closed=closure["repair_slice_closed"],
        alias_closed=closure["alias_closed"],
    )
    return {
        "fixture": fixture_path,
        "expected": fixture["expected"],
        "expected_rule": fixture["expected_rule"],
        "actual": report.result.value,
        "violation_rules": list(report.violation_rules),
        "preserved": (
            report.result.value == fixture["expected"]
            and fixture["expected_rule"] in report.violation_rules
        ),
    }


def _safe_alternative_status(
    safe_alternatives: Sequence[Dict[str, Any]], observed_facts: Sequence[str]
) -> Tuple[List[str], Dict[str, List[str]]]:
    observed = set(observed_facts)
    proven: List[str] = []
    missing: Dict[str, List[str]] = {}
    for alternative in safe_alternatives:
        absent = sorted(set(alternative["required_facts"]) - observed)
        missing[alternative["id"]] = absent
        if not absent:
            proven.append(alternative["id"])
    return proven, missing


def _diagnose_development_cases(
    extension_path: str,
    mapping_catalog: Dict[str, Any],
    phase13: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], bool]:
    extension = load_diagnostic_extension(extension_path)
    bug_by_case = {item["case_id"]: item for item in phase13["bug_assessments"]}
    diagnostics: List[Dict[str, Any]] = []
    evidence_gate_closed = True
    for mapping in mapping_catalog["development_mappings"]:
        finding = diagnose_failure(
            extension,
            rule=mapping["rule"],
            cause=mapping["cause"],
            evidence_level=mapping["evidence_level"],
            trigger_facts=tuple(mapping["trigger_facts"]),
            evidence_facts=tuple(mapping["evidence_facts"]),
        )
        value = finding.to_dict()
        safe_ids = [item["id"] for item in finding.safe_alternatives]
        proven, missing = _safe_alternative_status(
            finding.safe_alternatives, mapping["observed_repair_facts"]
        )
        incomplete_evidence = tuple(mapping["evidence_facts"][:-1])
        incomplete = diagnose_failure(
            extension,
            rule=mapping["rule"],
            cause=mapping["cause"],
            evidence_level=mapping["evidence_level"],
            trigger_facts=tuple(mapping["trigger_facts"]),
            evidence_facts=incomplete_evidence,
        )
        evidence_gate_closed = evidence_gate_closed and not incomplete.diagnostic_closed
        bug = bug_by_case[mapping["case_id"]]
        mapping_closed = (
            bug["closed"]
            and finding.diagnostic_closed
            and finding.repair_obligation == mapping["expected_repair_obligation"]
            and safe_ids == mapping["expected_safe_alternatives"]
            and not proven
            and mapping["repair_status"] == "REQUIRED_NOT_IMPLEMENTED"
            and mapping["preserved_result"] == "VIOLATION_UNDER_LOADED_SPEC"
        )
        value.update(
            {
                "case_id": mapping["case_id"],
                "expected_safe_alternatives_match": safe_ids
                == mapping["expected_safe_alternatives"],
                "proven_safe_alternatives": proven,
                "missing_repair_facts": missing,
                "repair_status": mapping["repair_status"],
                "preserved_result": mapping["preserved_result"],
                "incomplete_evidence_rejected": not incomplete.diagnostic_closed,
                "mapping_closed": mapping_closed,
            }
        )
        diagnostics.append(value)
    return diagnostics, evidence_gate_closed


def _regression_matrix(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    phase6 = run_phase6_manifest(manifest["phase6_manifest"])
    phase8 = run_phase8_manifest(manifest["phase8_manifest"])
    phase9 = run_phase9_manifest(manifest["phase9_manifest"])
    phase10 = run_phase10_manifest(manifest["phase10_manifest"])
    formation = {item["filesystem"]: item for item in phase9["assessment"]["filesystems"]}
    return [
        {
            "filesystem": "btrfs",
            "boundary": "QUALIFIED_SUCCESSFUL_PROFILE",
            "expected": "CLOSED",
            "actual": "CLOSED" if formation["btrfs"]["closed"] else "BLOCKED",
            "preserved": formation["btrfs"]["closed"],
        },
        {
            "filesystem": "ext4",
            "boundary": "FAILSTOP_POSITIVE_AND_ERRORS_CONT_NEGATIVE",
            "expected": "PRESERVED",
            "actual": "PRESERVED"
            if phase6["failstop_profile_closed"]
            and phase6["errors_continue_negative_witness_closed"]
            else "REGRESSED",
            "preserved": phase6["failstop_profile_closed"]
            and phase6["errors_continue_negative_witness_closed"],
        },
        {
            "filesystem": "ubifs",
            "boundary": "LIVE_RW_POSITIVE_AND_READ_ONLY_DEFERRED",
            "expected": "PRESERVED",
            "actual": "PRESERVED"
            if phase8["candidate_validation_closed"]
            and phase8["rw_replay_closed"]
            and phase8["deferred_boundary_closed"]
            else "REGRESSED",
            "preserved": phase8["candidate_validation_closed"]
            and phase8["rw_replay_closed"]
            and phase8["deferred_boundary_closed"],
        },
        {
            "filesystem": "ocfs2",
            "boundary": "NON_APPLICABLE_DEADLINE_NOT_ALIGNED",
            "expected": "PRESERVED",
            "actual": "PRESERVED"
            if phase10["applicability"] == "NON_APPLICABLE"
            and phase10["controlled_reason_code"] == "DEADLINE_NOT_ALIGNED"
            and phase10["phase10_screening_closed"]
            else "REGRESSED",
            "preserved": phase10["applicability"] == "NON_APPLICABLE"
            and phase10["controlled_reason_code"] == "DEADLINE_NOT_ALIGNED"
            and phase10["phase10_screening_closed"],
        },
    ]


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = _load(path)
    artifacts = _verify_hashes(manifest["artifact_hashes"], "Phase 14 artifact")
    phase13 = run_phase13_manifest(manifest["phase13_manifest"])
    extension = load_diagnostic_extension(manifest["diagnostic_extension"])
    mapping_catalog = _load(manifest["diagnostic_mapping"])

    diagnostics, evidence_gate_closed = _diagnose_development_cases(
        manifest["diagnostic_extension"], mapping_catalog, phase13
    )
    diagnostic_mappings_closed = (
        len(diagnostics) == 2 and all(item["mapping_closed"] for item in diagnostics)
    )
    base_replays = [
        _run_fixture(extension.raw["base_protocol"]["path"], item)
        for item in manifest["development_fixtures"]
    ]
    violation_results_preserved = all(item["preserved"] for item in base_replays)
    regressions = _regression_matrix(manifest)
    regression_boundaries_preserved = all(item["preserved"] for item in regressions)

    policy = extension.raw["applicability_policy"]
    heldout = extension.raw["heldout_policy"]
    applicability_unchanged = (
        policy["base_scope_preserved"]
        and policy["new_applicability_predicates"] == []
        and set(policy["rejected_outcome_predicates"])
        == {
            "add_save_link_succeeded",
            "remove_save_link_succeeded",
            "finish_unfinished_succeeded",
        }
    )
    heldout_disabled = (
        not heldout["heldout_partition_assigned"]
        and not heldout["heldout_validation_allowed"]
        and not heldout["common_v0_2_validated"]
        and heldout["future_candidate_requires_separate_preregistration"]
        and phase13["split_assessment"]["heldout_empty"]
    )
    mapping_policy_closed = all(mapping_catalog["mapping_policy"].values())
    phase14_closed = (
        all(artifacts.values())
        and phase13["phase13_preregistration_closed"]
        and extension.base_protocol.sha256
        == "c95135df0a9c916cd863d557aedebf64f06ae7bfee5bcf81692ce56f3c263122"
        and diagnostic_mappings_closed
        and evidence_gate_closed
        and mapping_policy_closed
        and violation_results_preserved
        and regression_boundaries_preserved
        and applicability_unchanged
        and heldout_disabled
    )
    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "manifest": path,
        "manifest_sha256": _sha256(path),
        "artifact_hashes_verified": all(artifacts.values()),
        "phase13_preregistration_preserved": phase13["phase13_preregistration_closed"],
        "v0_1_protocol_hash": extension.base_protocol.sha256,
        "v0_1_protocol_mutated": False,
        "v0_2_diagnostic_hash": extension.sha256,
        "v0_2_diagnostic_implemented": True,
        "v0_2_normative_protocol_replaced": False,
        "diagnostic_mappings": diagnostics,
        "diagnostic_mappings_closed": diagnostic_mappings_closed,
        "evidence_gate_closed": evidence_gate_closed,
        "mapping_policy_closed": mapping_policy_closed,
        "development_replays": base_replays,
        "violation_results_preserved": violation_results_preserved,
        "regression_matrix": regressions,
        "regression_boundaries_preserved": regression_boundaries_preserved,
        "applicability_unchanged": applicability_unchanged,
        "heldout_partition_empty": phase13["split_assessment"]["heldout_empty"],
        "heldout_validation_allowed": False,
        "common_v0_2_validated": False,
        "phase14_v0_2_diagnostic_closed": phase14_closed,
        "next_phase_plan": manifest["next_phase_plan"],
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# OIDS Phase 14 v0.2 Diagnostic and Failure-contract Implementation",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"Diagnostic implementation closed: `{summary['phase14_v0_2_diagnostic_closed']}`",
        f"v0.1 mutated: `{summary['v0_1_protocol_mutated']}`",
        f"Held-out validation allowed: `{summary['heldout_validation_allowed']}`",
        "",
        "## Development diagnostics",
        "",
        "| Case | Rule | Cause | Repair obligation | Safe alternatives proven | Closed |",
        "|---|---|---|---|---|---|",
    ]
    for item in summary["diagnostic_mappings"]:
        lines.append(
            f"| {item['case_id']} | {item['rule']} | {item['cause']} | "
            f"{item['repair_obligation']} | {len(item['proven_safe_alternatives'])} | "
            f"`{item['mapping_closed']}` |"
        )
    lines.extend(["", "## Regression boundaries", "", "| Filesystem | Boundary | Actual | Preserved |", "|---|---|---|---|"])
    for item in summary["regression_matrix"]:
        lines.append(
            f"| {item['filesystem']} | {item['boundary']} | {item['actual']} | `{item['preserved']}` |"
        )
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
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_phase14")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"diagnostic_closed={summary['phase14_v0_2_diagnostic_closed']} "
        f"regressions={summary['regression_boundaries_preserved']} "
        f"heldout_allowed={summary['heldout_validation_allowed']}"
    )
    return 0 if summary["phase14_v0_2_diagnostic_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
