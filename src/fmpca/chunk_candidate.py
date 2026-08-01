from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .dsl import load_protocol
from .frontend_chunk import (
    analyze_chunk_update_source,
    analyze_chunk_release_source,
    analyze_chunk_reservation_source,
    load_chunk_binding,
)
from .model import EvidenceEvent
from .proof import analyze_state
from .report import count_bug_specific_conditions, write_json, write_markdown
from .semantics import ProtocolEngine


def _run_fixture(protocol_path: str, fixture_path: str) -> Dict[str, Any]:
    protocol = load_protocol(protocol_path)
    fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    closure = fixture.get("closure", {})
    state = ProtocolEngine(protocol).run(
        EvidenceEvent.from_dict(item) for item in fixture["events"]
    )
    report = analyze_state(
        state,
        path_model_closed=closure.get("path_model_closed", True),
        all_paths_closed=closure.get("all_paths_closed", False),
        repair_slice_closed=closure.get("repair_slice_closed", True),
        alias_closed=closure.get("alias_closed", True),
    )
    expected = fixture.get("expected_result")
    return {
        "fixture": fixture_path,
        "expected": expected,
        "actual": report.result.value,
        "passed": expected is None or expected == report.result.value,
        "violation_rules": report.violation_rules,
        "unknown_rules": report.unknown_rules,
        "coverage": report.coverage,
    }


def _failed(required: Sequence[str], gates: Dict[str, bool]) -> Sequence[str]:
    missing = set(required) - set(gates)
    if missing:
        raise ValueError(f"missing CMRC readiness gates: {sorted(missing)}")
    return sorted(name for name in required if not gates[name])


def _verify_freeze(path: str) -> Dict[str, Any]:
    freeze = json.loads(Path(path).read_text(encoding="utf-8"))
    for artifact, expected in freeze["artifacts"].items():
        actual = hashlib.sha256(Path(artifact).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(
                f"semantic freeze mismatch for {artifact}: {actual} != {expected}"
            )
    return freeze


def run_manifest(path: str) -> Dict[str, Any]:
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    freeze = None
    if manifest.get("semantic_freeze"):
        freeze = _verify_freeze(manifest["semantic_freeze"])
    protocol = load_protocol(manifest["protocol"])
    binding = load_chunk_binding(manifest["binding"])

    reservation_source = manifest["source_witness"]["reservation"]
    positive_source = manifest["source_witness"]["positive_success"]
    release_source = manifest["source_witness"]["release"]
    reservation_witness = analyze_chunk_reservation_source(
        binding,
        reservation_source["source"],
        reservation_source["function"],
        positive_success_source=positive_source["source"],
        positive_success_function=positive_source["function"],
    )
    release_witness = analyze_chunk_release_source(
        binding,
        release_source["source"],
        release_source["function"],
    )
    second_family_results = []
    for candidate in manifest.get("second_family_candidates", []):
        witness = analyze_chunk_update_source(
            binding,
            candidate["source"],
            candidate["function"],
            operation_family=candidate["operation_family"],
        )
        independent = candidate["operation_family"] != reservation_witness.operation_family
        expected = candidate.get("expected_source_witness_closed")
        second_family_results.append(
            {
                "id": candidate["id"],
                "operation_family": candidate["operation_family"],
                "source": candidate["source"],
                "source_version": candidate.get("source_version"),
                "function": candidate["function"],
                "independent_from_development_family": independent,
                "source_witness_closed": witness.selected_update_path_closed,
                "expected_source_witness_closed": expected,
                "passed": expected is None or expected == witness.selected_update_path_closed,
                "evidence": witness.evidence,
            }
        )

    fixture_results = [
        {
            "id": case["id"],
            "role": case["role"],
            **_run_fixture(manifest["protocol"], case["fixture"]),
        }
        for case in manifest["replay_fixtures"]
    ]
    replay_passed = all(item["passed"] for item in fixture_results)

    config_values = [
        manifest,
        protocol.raw,
        binding.raw,
    ]
    bug_specific_count = count_bug_specific_conditions(config_values)
    base_gates = dict(manifest["gates"])
    second_independent_closed = any(
        item["independent_from_development_family"] and item["source_witness_closed"]
        for item in second_family_results
    )
    computed_gates = {
        **base_gates,
        "protocol_validated": True,
        "binding_has_no_case_specialization": bug_specific_count == 0,
        "confirmed_bug_source_witness": reservation_witness.selected_bug_path_closed,
        "source_semantic_footprint_closed": reservation_witness.source_semantic_footprint_closed,
        "normal_release_settlement_witness": release_witness.selected_release_path_closed,
        "paired_semantic_replay": replay_passed,
        "second_independent_family_available": second_independent_closed,
        "second_family_source_witness_closed": second_independent_closed,
    }
    candidate_failed = list(_failed(manifest["candidate_required_gates"], computed_gates))
    candidate_ready = not candidate_failed
    computed_gates["candidate_ready"] = candidate_ready
    freeze_failed = list(_failed(manifest["freeze_required_gates"], computed_gates))
    freeze_eligible = not freeze_failed

    families = [item["family_id"] for item in manifest["operation_families"]]
    if len(families) != len(set(families)):
        raise ValueError("CMRC operation families must be unique")

    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "manifest": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "semantic_freeze": manifest.get("semantic_freeze"),
        "semantic_freeze_sha256": (
            hashlib.sha256(Path(manifest["semantic_freeze"]).read_bytes()).hexdigest()
            if manifest.get("semantic_freeze")
            else None
        ),
        "freeze_id": freeze["freeze_id"] if freeze else None,
        "protocol_id": protocol.protocol_id,
        "protocol_version": protocol.protocol_version,
        "binding_id": binding.binding_id,
        "operation_family_count": len(families),
        "candidate_ready": candidate_ready,
        "freeze_eligible": freeze_eligible,
        "failed_candidate_gates": candidate_failed,
        "failed_freeze_gates": freeze_failed,
        "held_out_family_available": bool(manifest["held_out_family_available"]),
        "second_family_search": manifest["second_family_search"],
        "second_family_candidates": second_family_results,
        "bug_specific_condition_count": bug_specific_count,
        "source_witness": {
            "reservation": {
                "operation_family": reservation_witness.operation_family,
                "selected_bug_path_closed": reservation_witness.selected_bug_path_closed,
                "source_semantic_footprint_closed": reservation_witness.source_semantic_footprint_closed,
                "evidence": reservation_witness.evidence,
            },
            "release": {
                "operation_family": release_witness.operation_family,
                "selected_release_path_closed": release_witness.selected_release_path_closed,
                "evidence": release_witness.evidence,
            },
        },
        "gates": computed_gates,
        "replay": {
            "passed": sum(1 for item in fixture_results if item["passed"]),
            "total": len(fixture_results),
            "failed": sum(1 for item in fixture_results if not item["passed"]),
            "cases": fixture_results,
        },
        "second_family_screening": {
            "passed": sum(1 for item in second_family_results if item["passed"]),
            "total": len(second_family_results),
            "failed": sum(1 for item in second_family_results if not item["passed"]),
            "closed_independent_families": [
                item["operation_family"]
                for item in second_family_results
                if item["independent_from_development_family"] and item["source_witness_closed"]
            ],
        },
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# ChunkMetadataReservationCompletion Freeze Readiness v0.5",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"Candidate ready: `{summary['candidate_ready']}`",
        f"Freeze eligible: `{summary['freeze_eligible']}`",
        f"Freeze ID: `{summary['freeze_id']}`",
        f"Replay: {summary['replay']['passed']} / {summary['replay']['total']}",
        f"Second-family screening: {summary['second_family_screening']['passed']} / {summary['second_family_screening']['total']}",
        "",
        "## Replay",
        "",
        "| Case | Role | Expected | Actual | Pass |",
        "|---|---|---|---|---|",
    ]
    for case in summary["replay"]["cases"]:
        lines.append(
            "| {id} | {role} | `{expected}` | `{actual}` | {passed} |".format(
                id=case["id"],
                role=case["role"],
                expected=case["expected"],
                actual=case["actual"],
                passed="PASS" if case["passed"] else "FAIL",
            )
        )
    lines.extend(
        [
            "",
            "## Second-family screening",
            "",
            "| Candidate | Family | Source witness closed | Independent | Pass |",
            "|---|---|---|---|---|",
        ]
    )
    for candidate in summary["second_family_candidates"]:
        lines.append(
            "| {id} | {family} | `{closed}` | `{independent}` | {passed} |".format(
                id=candidate["id"],
                family=candidate["operation_family"],
                closed=candidate["source_witness_closed"],
                independent=candidate["independent_from_development_family"],
                passed="PASS" if candidate["passed"] else "FAIL",
            )
        )
    lines.extend(
        [
            "",
            "## Gates",
            "",
            "| Gate | Value |",
            "|---|---|",
        ]
    )
    for key, value in sorted(summary["gates"].items()):
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Freeze blockers",
            "",
            ", ".join(f"`{item}`" for item in summary["failed_freeze_gates"]) or "none",
            "",
            "## Source witness",
            "",
            f"- Bug path closed: `{summary['source_witness']['reservation']['selected_bug_path_closed']}`",
            f"- Release settlement closed: `{summary['source_witness']['release']['selected_release_path_closed']}`",
            f"- Bug-specific condition count: `{summary['bug_specific_condition_count']}`",
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
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.chunk_candidate")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"candidate_ready={summary['candidate_ready']} "
        f"freeze_eligible={summary['freeze_eligible']}"
    )
    return 0 if summary["candidate_ready"] and summary["replay"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
