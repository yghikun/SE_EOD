from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .dsl import load_protocol
from .frontend_orphan_common import (
    analyze_recovery_witness,
    analyze_registration_witness,
    analyze_settlement_witness,
    load_orphan_binding,
)
from .model import EvidenceEvent
from .orphan_composition import OIDSIdentity, compose_source_lifecycle
from .proof import analyze_state
from .report import count_bug_specific_conditions, write_json, write_markdown
from .scope import assess_scope, load_taxonomy
from .semantics_extensions import ProtocolDeadlineEngine


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _verify_artifacts(values: Dict[str, str]) -> Dict[str, bool]:
    result = {}
    for path, expected in values.items():
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"OIDS artifact hash mismatch for {path}: {actual} != {expected}")
        result[path] = True
    return result


def _run_replay(protocol_path: str, case: Dict[str, Any]) -> Dict[str, Any]:
    spec = load_protocol(protocol_path)
    fixture = json.loads(Path(case["fixture"]).read_text(encoding="utf-8"))
    closure = fixture["closure"]
    state = ProtocolDeadlineEngine(spec).run(
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
        "id": case["id"],
        "role": case["role"],
        "fixture": case["fixture"],
        "expected": case["expected"],
        "actual": report.result.value,
        "passed": report.result.value == case["expected"],
        "violation_rules": list(report.violation_rules),
        "unknown_rules": list(report.unknown_rules),
        "coverage": dict(report.coverage),
    }


def _identity(raw: Dict[str, Any]) -> OIDSIdentity:
    return OIDSIdentity(
        filesystem=raw["filesystem"],
        inode=raw["inode"],
        namespace_entry=raw["namespace_entry"],
        orphan_registry=raw["orphan_registry"],
        filesystem_mount=raw["filesystem_mount"],
        inode_allocation_generation=str(raw["inode_allocation_generation"]),
    )


def run_manifest(path: str) -> Dict[str, Any]:
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifact_locks = _verify_artifacts(manifest["artifact_hashes"])
    protocol = load_protocol(manifest["protocol"])
    filesystem_results = []
    binding_values = []
    for filesystem in manifest["filesystems"]:
        binding = load_orphan_binding(filesystem["binding"])
        binding_values.append(binding.raw)
        registration_config = filesystem["source_witness"]["registration"]
        settlement_config = filesystem["source_witness"]["settlement"]
        recovery_config = filesystem["source_witness"]["recovery"]
        registration = analyze_registration_witness(
            binding,
            registration_config["source"],
            registration_config["function"],
        )
        settlement = analyze_settlement_witness(
            binding,
            settlement_config["source"],
            settlement_config["function"],
        )
        recovery = analyze_recovery_witness(
            binding,
            recovery_config["cleanup_source"],
            recovery_config["cleanup_function"],
            recovery_config["exposure_source"],
            recovery_config["exposure_function"],
        )
        identity = _identity(filesystem["identity"])
        normal = compose_source_lifecycle(
            protocol,
            binding,
            registration,
            settlement,
            identity,
            identity,
            mode="normal",
        )
        recovered = compose_source_lifecycle(
            protocol,
            binding,
            registration,
            settlement,
            identity,
            identity,
            mode="recovery",
            recovery=recovery,
        )
        compositions = [normal, recovered]
        source_closed = bool(
            registration.registration_safe
            and settlement.removal_safe
            and recovery.recovery_path_closed
            and all(item.selected_path_closed for item in compositions)
        )
        proof_closed = all(
            item.all_paths_closed and item.report.result.value.startswith("CONFORMANT")
            for item in compositions
        )
        filesystem_results.append(
            {
                "filesystem": binding.filesystem,
                "validation_role": filesystem["validation_role"],
                "operation_family": filesystem["operation_family"],
                "source_witness_closed": source_closed,
                "proof_closure_closed": proof_closed,
                "registration_witness": registration.to_dict(),
                "settlement_witness": settlement.to_dict(),
                "recovery_witness": recovery.to_dict(),
                "compositions": [item.to_dict() for item in compositions],
            }
        )

    replay = [_run_replay(manifest["protocol"], case) for case in manifest["replays"]]
    replay_closed = all(item["passed"] for item in replay)
    result_partition_closed = all(
        any(item["actual"] == expected for item in replay)
        for expected in (
            "CONFORMANT_UNDER_LOADED_SPEC",
            "VIOLATION_UNDER_LOADED_SPEC",
            "INCOMPLETE_UNDER_LOADED_SPEC",
        )
    )
    bug_specific_count = count_bug_specific_conditions(
        [manifest, protocol.raw, *binding_values]
    )
    scope_filesystems = []
    for configured, result in zip(manifest["filesystems"], filesystem_results):
        scope_filesystems.append(
            {
                "filesystem": result["filesystem"],
                "applicability": "APPLICABLE",
                "validation_role": result["validation_role"],
                "operation_family": result["operation_family"],
                "correspondence": dict(configured["correspondence"]),
                "source_witness_closed": result["source_witness_closed"],
                "replay_closed": replay_closed,
                "proof_closure_closed": result["proof_closure_closed"],
            }
        )
    declaration = {
        "protocol_id": protocol.protocol_id,
        "semantic_scope": manifest["declared_semantic_scope"],
        "freeze_boundary": manifest["freeze_boundary"],
        "canonical_dsl_defined": True,
        "bindings_defined": len(binding_values) >= 2,
        "source_witness_defined": all(
            item["source_witness_closed"] for item in filesystem_results
        ),
        "result_partition_closed": result_partition_closed,
        "hashes_locked": {
            "protocol": artifact_locks.get(manifest["protocol"], False),
            "binding": all(
                artifact_locks.get(item["binding"], False)
                for item in manifest["filesystems"]
            ),
            "test": artifact_locks.get(manifest["test_artifact"], False),
        },
        "filesystems": scope_filesystems,
    }
    assessment = assess_scope(load_taxonomy(manifest["taxonomy"]), declaration)
    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "manifest": str(manifest_path),
        "manifest_sha256": _sha256(str(manifest_path)),
        "protocol_id": protocol.protocol_id,
        "protocol_version": protocol.protocol_version,
        "artifact_hashes_verified": all(artifact_locks.values()),
        "bug_specific_condition_count": bug_specific_count,
        "result_partition_closed": result_partition_closed,
        "filesystems": filesystem_results,
        "replay": {
            "passed": sum(1 for item in replay if item["passed"]),
            "total": len(replay),
            "failed": sum(1 for item in replay if not item["passed"]),
            "cases": replay,
        },
        "scope_declaration": declaration,
        "scope_assessment": assessment.to_dict(),
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    assessment = summary["scope_assessment"]
    lines = [
        "# OIDS Phase 3 Source Composition and Readiness",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"Common candidate ready: `{assessment['common_candidate_ready']}`",
        f"Common freeze ready: `{assessment['common_freeze_ready']}`",
        f"Replay: {summary['replay']['passed']} / {summary['replay']['total']}",
        "",
        "## Source compositions",
        "",
        "| Filesystem | Role | Mode | Selected path | All paths | Acceptance | Result |",
        "|---|---|---|---|---|---|---|",
    ]
    for filesystem in summary["filesystems"]:
        for composition in filesystem["compositions"]:
            lines.append(
                "| {fs} | {role} | {mode} | `{selected}` | `{all_paths}` | `{acceptance}` | `{result}` |".format(
                    fs=filesystem["filesystem"],
                    role=filesystem["validation_role"],
                    mode=composition["mode"],
                    selected=composition["selected_path_closed"],
                    all_paths=composition["all_paths_closed"],
                    acceptance=composition["acceptance_true"],
                    result=composition["analysis_result"],
                )
            )
    lines.extend(
        [
            "",
            "## Freeze blockers",
            "",
            ", ".join(
                f"`{item}`" for item in assessment["failed_freeze_gates"]
            )
            or "none",
            "",
            "## Replay",
            "",
            "| Case | Role | Expected | Actual | Pass |",
            "|---|---|---|---|---|",
        ]
    )
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
    lines.extend(["", summary["interpretation"], ""])
    return "\n".join(lines)


def run_and_write(manifest: str, json_out: str, markdown_out: str) -> Dict[str, Any]:
    summary = run_manifest(manifest)
    write_json(json_out, summary)
    write_markdown(markdown_out, _markdown(summary))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_candidate")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    assessment = summary["scope_assessment"]
    print(
        f"candidate_ready={assessment['common_candidate_ready']} "
        f"freeze_ready={assessment['common_freeze_ready']}"
    )
    return 0 if assessment["common_candidate_ready"] and not summary["replay"]["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
