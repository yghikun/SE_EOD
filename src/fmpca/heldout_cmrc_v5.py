from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .chunk_candidate import _run_fixture
from .frontend_chunk import analyze_chunk_update_source, load_chunk_binding
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


def _run_candidate_replay(
    protocol_path: str,
    fixtures: Sequence[Dict[str, str]],
) -> Dict[str, Any]:
    cases = [
        {
            "id": fixture["id"],
            "role": fixture["role"],
            **_run_fixture(protocol_path, fixture["fixture"]),
        }
        for fixture in fixtures
    ]
    return {
        "passed": sum(1 for item in cases if item["passed"]),
        "total": len(cases),
        "failed": sum(1 for item in cases if not item["passed"]),
        "roles": sorted({item["role"] for item in cases}),
        "cases": cases,
    }


def _screen_candidate(
    candidate: Dict[str, Any],
    *,
    protocol_path: str,
    binding: Any,
    frozen_families: Sequence[str],
    target_footprint: Sequence[str],
    required_replay_roles: Sequence[str],
) -> Dict[str, Any]:
    witness = analyze_chunk_update_source(
        binding,
        candidate["source"],
        candidate["function"],
        operation_family=candidate["operation_family"],
    )
    candidate_footprint = set(candidate.get("semantic_footprint", []))
    target = set(target_footprint)
    missing_footprint = sorted(target - candidate_footprint)
    extra_footprint = sorted(candidate_footprint - target)
    replay = _run_candidate_replay(
        protocol_path,
        candidate.get("replay_fixtures", []),
    )
    replay_roles_closed = set(required_replay_roles).issubset(set(replay["roles"]))
    replay_closed = replay["failed"] == 0 and replay_roles_closed

    checks = {
        "independent_from_v0_5_freeze_families": (
            candidate["operation_family"] not in set(frozen_families)
        ),
        "target_semantic_footprint_closed": not missing_footprint,
        "source_witness_closed_under_frozen_binding": witness.selected_update_path_closed,
        "replay_closure_closed": replay_closed,
    }

    if all(checks.values()):
        decision = "ELIGIBLE_HELD_OUT_REPLAY"
        reason = "candidate matches frozen CMRC footprint, remains independent from v0.5 freeze families, and closes source plus replay evidence"
    elif not checks["independent_from_v0_5_freeze_families"]:
        decision = "REJECT_NOT_INDEPENDENT"
        reason = "candidate belongs to a family already used for the v0.5 freeze"
    elif not checks["target_semantic_footprint_closed"]:
        decision = "REJECT_FOOTPRINT_GAP"
        reason = f"candidate lacks CMRC target footprint entries: {missing_footprint}"
    elif not checks["source_witness_closed_under_frozen_binding"]:
        decision = "REJECT_BINDING_GAP"
        reason = "frozen CMRC binding cannot close reservation/update/release source order for this candidate"
    else:
        decision = "REJECT_REPLAY_CLOSURE_GAP"
        reason = "candidate source shape closes, but required replay roles or expected replay results are incomplete"

    expected = candidate.get("expected_decision")
    return {
        "id": candidate["id"],
        "operation_family": candidate["operation_family"],
        "source": candidate["source"],
        "source_version": candidate.get("source_version"),
        "function": candidate["function"],
        "expected_decision": expected,
        "actual_decision": decision,
        "passed": expected is None or expected == decision,
        "eligible": decision == "ELIGIBLE_HELD_OUT_REPLAY",
        "reason": reason,
        "checks": checks,
        "missing_footprint": missing_footprint,
        "extra_footprint": extra_footprint,
        "source_witness": {
            "operation_family": witness.operation_family,
            "selected_update_path_closed": witness.selected_update_path_closed,
            "reservation_wrapper_found": witness.reservation_wrapper_found,
            "metadata_update_found": witness.metadata_update_found,
            "release_wrapper_found": witness.release_wrapper_found,
            "order_closed": witness.order_closed,
            "evidence": witness.evidence,
        },
        "replay": replay,
    }


def run_manifest(path: str) -> Dict[str, Any]:
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    freeze = _verify_freeze(manifest["semantic_freeze"])
    binding = load_chunk_binding(manifest["binding"])
    candidates = [
        _screen_candidate(
            candidate,
            protocol_path=manifest["protocol"],
            binding=binding,
            frozen_families=manifest["frozen_operation_families"],
            target_footprint=manifest["target_semantic_footprint"],
            required_replay_roles=manifest["required_replay_roles"],
        )
        for candidate in manifest["candidates"]
    ]
    eligible = [item for item in candidates if item["eligible"]]
    rejections = [
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
        json.loads(Path(manifest["protocol"]).read_text(encoding="utf-8")),
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
        "eligible_candidate_count": len(eligible),
        "rejected_candidate_count": len(rejections),
        "held_out_operation_families": [
            item["operation_family"] for item in eligible
        ],
        "screening_rejections": rejections,
        "protocol_acceptance_modifications": 0,
        "checker_modifications_after_freeze": 0,
        "bug_specific_condition_count": count_bug_specific_conditions(config_values),
        "interpretation": manifest["interpretation"],
        "candidates": candidates,
    }


def _markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# FMPCA E6 CMRC Held-out Screening v0.5",
        "",
        f"Manifest: `{summary['manifest']}`",
        f"Freeze ID: `{summary['freeze_id']}`",
        "",
        f"Screening expectations passed: {summary['passed']} / {summary['total_candidates']}",
        f"Eligible held-out families: {summary['eligible_candidate_count']}",
        "",
        "| Candidate | Family | Decision | Eligible | Replay |",
        "|---|---|---|---|---|",
    ]
    for candidate in summary["candidates"]:
        lines.append(
            "| {id} | {family} | `{decision}` | {eligible} | {passed}/{total} |".format(
                id=candidate["id"],
                family=candidate["operation_family"],
                decision=candidate["actual_decision"],
                eligible="yes" if candidate["eligible"] else "no",
                passed=candidate["replay"]["passed"],
                total=candidate["replay"]["total"],
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
            f"- Bug-specific condition count: `{summary['bug_specific_condition_count']}`",
            f"- Protocol acceptance modifications: `{summary['protocol_acceptance_modifications']}`",
            f"- Checker modifications after freeze: `{summary['checker_modifications_after_freeze']}`",
            "- E6 uses the frozen CMRC v0.5 protocol and binding unchanged.",
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
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.heldout_cmrc_v5")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"{summary['eligible_candidate_count']}/{summary['total_candidates']} "
        "CMRC held-out candidates eligible"
    )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
