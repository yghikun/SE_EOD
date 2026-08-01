from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .frontend_capacity import analyze_capacity_source, load_capacity_binding
from .report import count_bug_specific_conditions, write_json, write_markdown


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _verify_freeze(path: str) -> Dict[str, Any]:
    freeze = json.loads(Path(path).read_text(encoding="utf-8"))
    for artifact, expected in freeze["artifacts"].items():
        actual = _sha256(artifact)
        if actual != expected:
            raise ValueError(
                f"semantic freeze mismatch for {artifact}: {actual} != {expected}"
            )
    return freeze


def _screen_candidate(
    candidate: Dict[str, Any],
    binding: Any,
    target_footprint: Sequence[str],
    development_families: Sequence[str],
    shared_identity_roles: Sequence[str],
) -> Dict[str, Any]:
    witness = analyze_capacity_source(
        binding,
        candidate["source"],
        candidate["function"],
    )
    candidate_footprint = set(candidate.get("semantic_footprint", []))
    target = set(target_footprint)
    footprint_gap = sorted(candidate_footprint - target)
    role_anchors = set(candidate.get("role_anchors", []))
    missing_identity_roles = sorted(set(shared_identity_roles) - role_anchors)
    family_is_new = candidate["operation_family"] not in set(development_families)
    source_witness_closed = witness.selected_source_path_closed
    closure = candidate.get("closure", {})
    closure_closed = bool(
        closure.get("bug_path")
        and closure.get("fixed_or_repair_path")
        and closure.get("normal_or_safe_path")
        and closure.get("paired_replay")
    )
    footprint_closed = not footprint_gap
    identity_closed = not missing_identity_roles

    checks = {
        "independent_from_development": family_is_new,
        "target_semantic_footprint_closed": footprint_closed,
        "target_identity_closed": identity_closed,
        "source_witness_closed_under_existing_binding": source_witness_closed,
        "closure_closed_for_replay": closure_closed,
    }
    if all(checks.values()):
        decision = "ELIGIBLE_HELD_OUT_REPLAY"
        reason = "candidate matches the frozen WDC/DTC footprint, identity, source witness and replay closure requirements"
    elif not footprint_closed or not identity_closed:
        decision = "REJECT_OUTSIDE_WDC_DTC_FOOTPRINT"
        reason = (
            "candidate does not bind the frozen device-capacity object model: "
            f"footprint_gap={footprint_gap}, missing_identity_roles={missing_identity_roles}"
        )
    elif not source_witness_closed:
        decision = "REJECT_BINDING_GAP"
        reason = (
            "the existing WDC binding cannot produce a closed source witness "
            f"for operation_family={witness.operation_family}"
        )
    elif not closure_closed:
        decision = "REJECT_CLOSURE_GAP"
        reason = "candidate lacks bug/fixed/safe paired replay closure"
    else:
        decision = "REJECT_NOT_INDEPENDENT"
        reason = "candidate belongs to a v0.4 development operation family"

    expected = candidate.get("expected_decision")
    return {
        "id": candidate["id"],
        "operation_family": candidate["operation_family"],
        "source": candidate["source"],
        "function": candidate["function"],
        "source_version": candidate.get("source_version"),
        "expected_decision": expected,
        "actual_decision": decision,
        "passed": expected is None or expected == decision,
        "eligible": decision == "ELIGIBLE_HELD_OUT_REPLAY",
        "reason": reason,
        "checks": checks,
        "footprint_gap": footprint_gap,
        "missing_identity_roles": missing_identity_roles,
        "wdc_source_witness": {
            "operation_family": witness.operation_family,
            "selected_source_path_closed": witness.selected_source_path_closed,
            "eligibility_closed": witness.eligibility_closed,
            "aggregate_pair_closed": witness.aggregate_pair_closed,
            "same_delta_closed": witness.same_delta_closed,
            "membership_coupling_closed": witness.membership_coupling_closed,
            "evidence": witness.evidence,
        },
    }


def run_manifest(path: str) -> Dict[str, Any]:
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    freeze = _verify_freeze(manifest["semantic_freeze"])
    binding = load_capacity_binding(manifest["binding"])
    target_footprint = manifest["target_semantic_footprint"]
    development_families = manifest["development_operation_families"]
    shared_identity_roles = manifest["shared_identity_roles"]
    candidates = [
        _screen_candidate(
            candidate,
            binding,
            target_footprint,
            development_families,
            shared_identity_roles,
        )
        for candidate in manifest["candidates"]
    ]
    held_out_families = [
        item["operation_family"] for item in candidates if item["eligible"]
    ]
    screening_rejections = [
        {
            "operation_family": item["operation_family"],
            "candidate_status": item["actual_decision"],
            "reason": item["reason"],
        }
        for item in candidates
        if not item["eligible"]
    ]
    config_values = [
        manifest,
        json.loads(Path(manifest["binding"]).read_text(encoding="utf-8")),
        json.loads(Path(manifest["composition_spec"]).read_text(encoding="utf-8")),
    ]
    return {
        "schema_version": 1,
        "manifest": str(manifest_path),
        "manifest_sha256": _sha256(str(manifest_path)),
        "semantic_freeze": manifest["semantic_freeze"],
        "semantic_freeze_sha256": _sha256(manifest["semantic_freeze"]),
        "freeze_id": freeze["freeze_id"],
        "total_candidates": len(candidates),
        "passed": sum(1 for item in candidates if item["passed"]),
        "failed": sum(1 for item in candidates if not item["passed"]),
        "eligible_candidate_count": len(held_out_families),
        "rejected_candidate_count": len(screening_rejections),
        "held_out_operation_families": held_out_families,
        "screening_rejections": screening_rejections,
        "protocol_acceptance_modifications": 0,
        "checker_modifications_after_freeze": 0,
        "bug_specific_condition_count": count_bug_specific_conditions(config_values),
        "interpretation": manifest["interpretation"],
        "candidates": candidates,
    }


def _markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# FMPCA E5 Held-out Screening v0.4",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"Screening expectations passed: {summary['passed']} / {summary['total_candidates']}",
        f"Eligible held-out families: {summary['eligible_candidate_count']}",
        "",
        "| Candidate | Family | Decision | Eligible |",
        "|---|---|---|---|",
    ]
    for candidate in summary["candidates"]:
        lines.append(
            "| {id} | {family} | `{decision}` | {eligible} |".format(
                id=candidate["id"],
                family=candidate["operation_family"],
                decision=candidate["actual_decision"],
                eligible="yes" if candidate["eligible"] else "no",
            )
        )
    lines.extend(
        [
            "",
            "## Screening Rejections",
            "",
            "| Operation family | Status | Reason |",
            "|---|---|---|",
        ]
    )
    for rejection in summary["screening_rejections"]:
        lines.append(
            "| {operation_family} | `{candidate_status}` | {reason} |".format(
                operation_family=rejection["operation_family"],
                candidate_status=rejection["candidate_status"],
                reason=rejection["reason"],
            )
        )
    lines.extend(
        [
            "",
            "## Guardrails",
            "",
            f"- Freeze ID: `{summary['freeze_id']}`",
            f"- Bug-specific condition count: `{summary['bug_specific_condition_count']}`",
            f"- Protocol acceptance modifications: `{summary['protocol_acceptance_modifications']}`",
            f"- Checker modifications after freeze: `{summary['checker_modifications_after_freeze']}`",
            "- Rejected candidates are not replayed as held-out evidence.",
            "",
            summary["interpretation"],
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
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.heldout_v4")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"{summary['eligible_candidate_count']}/{summary['total_candidates']} "
        "held-out candidates eligible"
    )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
