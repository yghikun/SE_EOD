from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .frontend_orphan_common import load_orphan_binding
from .orphan_allpath import run_manifest as run_phase4_manifest
from .orphan_candidate import run_manifest as run_phase3_manifest
from .orphan_phase6 import run_manifest as run_phase6_manifest
from .orphan_phase7 import run_manifest as run_phase7_manifest
from .orphan_phase8 import run_manifest as run_phase8_manifest
from .report import count_bug_specific_conditions, write_json, write_markdown
from .scope import ScopeAssessment, assess_scope_files


CLOSED = "CLOSED"
BLOCKED = "BLOCKED"
COMMON_FREEZE = "QUALIFIED_COMMON_NARROW_FREEZE"


@dataclass(frozen=True)
class FilesystemQualification:
    filesystem: str
    validation_role: str
    operation_family: str
    configuration_scope: str
    applicability_predicate_closed: bool
    correspondence_closed: bool
    source_witness_closed: bool
    replay_closed: bool
    proof_closure_closed: bool
    status: str
    blockers: Tuple[str, ...] = ()

    @property
    def closed(self) -> bool:
        return self.status == CLOSED and not self.blockers


@dataclass(frozen=True)
class Phase9Assessment:
    scope: ScopeAssessment
    filesystems: Tuple[FilesystemQualification, ...]
    independent_operation_families: bool
    phase7_scope_preserved: bool
    ubifs_is_freeze_member_not_post_common_heldout: bool
    common_heldout_validated: bool
    status: str
    blockers: Tuple[str, ...]

    @property
    def closed(self) -> bool:
        return self.status == CLOSED and not self.blockers

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["scope"] = self.scope.to_dict()
        for item, source in zip(value["filesystems"], self.filesystems):
            item["closed"] = source.closed
        value["closed"] = self.closed
        value["blockers"] = list(self.blockers)
        return value


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path: str) -> Dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _verify_hashes(values: Dict[str, str]) -> Dict[str, bool]:
    if not values:
        raise ValueError("Phase 9 artifact hash lock must not be empty")
    result: Dict[str, bool] = {}
    for path, expected in values.items():
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"Phase 9 artifact hash mismatch for {path}: {actual} != {expected}")
        result[path] = True
    return result


def _replay_passed(summary: Dict[str, Any], case_ids: Sequence[str]) -> bool:
    cases = {item["id"]: item for item in summary["replay"]["cases"]}
    return all(
        case_id in cases
        and cases[case_id]["passed"]
        and cases[case_id]["actual"] == cases[case_id]["expected"]
        for case_id in case_ids
    )


def _filesystem_entry(declaration: Dict[str, Any], filesystem: str) -> Dict[str, Any]:
    matches = [item for item in declaration["filesystems"] if item["filesystem"] == filesystem]
    if len(matches) != 1:
        raise ValueError(f"Phase 9 requires exactly one scope entry for {filesystem}")
    return matches[0]


def _qualification(
    entry: Dict[str, Any],
    *,
    expected_predicate: str,
    source_closed: bool,
    replay_closed: bool,
    proof_closed: bool,
) -> FilesystemQualification:
    correspondence = all(bool(value) for value in entry["correspondence"].values())
    predicate_closed = entry.get("applicability_predicate") == expected_predicate
    blockers: List[str] = []
    filesystem = entry["filesystem"]
    if entry.get("applicability") != "APPLICABLE":
        blockers.append(f"PHASE9_{filesystem.upper()}_NOT_APPLICABLE")
    if not predicate_closed:
        blockers.append(f"PHASE9_{filesystem.upper()}_PREDICATE_NOT_CLOSED")
    if not correspondence:
        blockers.append(f"PHASE9_{filesystem.upper()}_CORRESPONDENCE_NOT_CLOSED")
    if not source_closed:
        blockers.append(f"PHASE9_{filesystem.upper()}_SOURCE_NOT_CLOSED")
    if not replay_closed:
        blockers.append(f"PHASE9_{filesystem.upper()}_REPLAY_NOT_CLOSED")
    if not proof_closed:
        blockers.append(f"PHASE9_{filesystem.upper()}_PROOF_NOT_CLOSED")
    closed = not blockers
    return FilesystemQualification(
        filesystem,
        entry["validation_role"],
        entry["operation_family"],
        entry["configuration_scope"],
        predicate_closed,
        correspondence,
        source_closed,
        replay_closed,
        proof_closed,
        CLOSED if closed else BLOCKED,
        tuple(blockers),
    )


def analyze_phase9(manifest: Dict[str, Any]) -> Phase9Assessment:
    declaration = _load(manifest["scope_declaration"])
    scope = assess_scope_files(manifest["taxonomy"], manifest["scope_declaration"])
    phase3 = run_phase3_manifest(manifest["phase3_manifest"])
    phase4 = run_phase4_manifest(manifest["phase4_manifest"])
    phase6 = run_phase6_manifest(manifest["phase6_manifest"])
    phase7 = run_phase7_manifest(manifest["phase7_manifest"])
    phase8 = run_phase8_manifest(manifest["phase8_manifest"])

    for item in declaration["filesystems"]:
        load_orphan_binding(item["binding"] if "binding" in item else manifest["bindings"][item["filesystem"]])

    phase4_by_fs = {item["filesystem"]: item for item in phase4["filesystems"]}
    btrfs = _qualification(
        _filesystem_entry(declaration, "btrfs"),
        expected_predicate="filesystem == btrfs AND zero_link_deletion AND successful_rw_recovery_exposure",
        source_closed=bool(phase4_by_fs["btrfs"]["closed"]),
        replay_closed=_replay_passed(phase3, ("btrfs-fixed-live", "normal-recovery")),
        proof_closed=bool(phase4_by_fs["btrfs"]["closed"]),
    )
    ext4 = _qualification(
        _filesystem_entry(declaration, "ext4"),
        expected_predicate="filesystem == ext4 AND zero_link_deletion AND error_policy != ERRORS_CONT",
        source_closed=bool(phase6["failstop_profile_closed"]),
        replay_closed=(
            _replay_passed(phase3, ("ext4-fixed-live", "normal-recovery"))
            and bool(phase6["errors_continue_negative_witness_closed"])
        ),
        proof_closed=(
            bool(phase6["failstop_profile_closed"])
            and bool(phase7["qualified_scope_closed"])
        ),
    )
    ubifs_assessment = phase8["assessment"]
    ubifs = _qualification(
        _filesystem_entry(declaration, "ubifs"),
        expected_predicate="filesystem == ubifs AND zero_link_deletion AND (live_cleanup OR successful_rw_recovery_exposure)",
        source_closed=bool(ubifs_assessment["source_proof_closed"]),
        replay_closed=(
            bool(phase8["rw_replay_closed"])
            and bool(phase8["deferred_boundary_closed"])
        ),
        proof_closed=bool(phase8["candidate_validation_closed"]),
    )
    filesystems = (btrfs, ext4, ubifs)
    families = [item.operation_family for item in filesystems]
    independent = len(families) == len(set(families))
    phase7_preserved = (
        _sha256(manifest["phase7_scope_declaration"])
        == manifest["historical_freeze_hashes"][manifest["phase7_scope_declaration"]]
        and _sha256(manifest["phase7_manifest"])
        == manifest["historical_freeze_hashes"][manifest["phase7_manifest"]]
    )
    ubifs_entry = _filesystem_entry(declaration, "ubifs")
    ubifs_policy = (
        ubifs_entry["validation_role"] == "VALIDATION"
        and ubifs_entry.get("validation_provenance")
        == "PREREGISTERED_BLIND_INDEPENDENT_FAMILY"
        and not ubifs_entry.get("post_freeze", False)
        and not scope.common_heldout_validated
    )
    blockers: List[str] = []
    for item in filesystems:
        blockers.extend(item.blockers)
    if not independent:
        blockers.append("PHASE9_OPERATION_FAMILIES_NOT_INDEPENDENT")
    if not phase7_preserved:
        blockers.append("PHASE9_PHASE7_HISTORICAL_FREEZE_CHANGED")
    if not ubifs_policy:
        blockers.append("PHASE9_UBIFS_HELDOUT_TEMPORAL_ROLE_INVALID")
    if not scope.declaration_valid:
        blockers.append("PHASE9_COMMON_SCOPE_DECLARATION_INVALID")
    if not scope.common_candidate_ready:
        blockers.append("PHASE9_COMMON_CANDIDATE_NOT_READY")
    if not scope.common_freeze_ready:
        blockers.extend(f"PHASE9_FREEZE_GATE:{gate}" for gate in scope.failed_freeze_gates)
    status = CLOSED if not blockers else BLOCKED
    return Phase9Assessment(
        scope,
        filesystems,
        independent,
        phase7_preserved,
        ubifs_policy,
        False,
        status,
        tuple(dict.fromkeys(blockers)),
    )


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = _load(path)
    locks = _verify_hashes(manifest["artifact_hashes"])
    assessment = analyze_phase9(manifest)
    qualification = _load(manifest["qualification_catalog"])
    decision_closed = qualification["decision"] == COMMON_FREEZE
    freeze_generated = assessment.closed and decision_closed and all(locks.values())
    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "freeze_id": manifest["freeze_id"],
        "manifest": path,
        "manifest_sha256": _sha256(path),
        "artifact_hashes_verified": all(locks.values()),
        "bug_specific_condition_count": count_bug_specific_conditions([manifest]),
        "assessment": assessment.to_dict(),
        "common_candidate_ready": assessment.scope.common_candidate_ready,
        "common_freeze_ready": assessment.scope.common_freeze_ready,
        "common_freeze_manifest_generated": freeze_generated,
        "cross_filesystem_claim_allowed": assessment.scope.cross_filesystem_claim_allowed,
        "common_heldout_validated": False,
        "phase7_scope_unchanged": assessment.phase7_scope_preserved,
        "freeze_members": [item.filesystem for item in assessment.filesystems],
        "next_heldout_requirement": manifest["next_heldout_requirement"],
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    assessment = summary["assessment"]
    scope = assessment["scope"]
    lines = [
        "# OIDS Phase 9 COMMON Readiness Requalification",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"COMMON candidate ready: `{summary['common_candidate_ready']}`",
        f"COMMON freeze ready: `{summary['common_freeze_ready']}`",
        f"COMMON freeze generated: `{summary['common_freeze_manifest_generated']}`",
        f"Cross-filesystem claim allowed: `{summary['cross_filesystem_claim_allowed']}`",
        f"COMMON held-out validated: `{summary['common_heldout_validated']}`",
        "",
        "## Freeze members",
        "",
        "| Filesystem | Role | Profile | Source | Replay | Proof | Closed |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in assessment["filesystems"]:
        lines.append(
            "| {filesystem} | {role} | `{profile}` | `{source}` | `{replay}` | `{proof}` | `{closed}` |".format(
                filesystem=item["filesystem"],
                role=item["validation_role"],
                profile=item["configuration_scope"],
                source=item["source_witness_closed"],
                replay=item["replay_closed"],
                proof=item["proof_closure_closed"],
                closed=item["closed"],
            )
        )
    lines.extend(
        [
            "",
            "## Gates",
            "",
            f"Failed candidate gates: {', '.join(scope['failed_candidate_gates']) or 'none'}",
            f"Failed freeze gates: {', '.join(scope['failed_freeze_gates']) or 'none'}",
            f"Failed held-out gates: {', '.join(scope['failed_heldout_gates']) or 'none'}",
            "",
            "## Decision",
            "",
            summary["interpretation"],
            "",
            f"Next held-out requirement: {summary['next_heldout_requirement']}",
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
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_phase9")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"common_candidate={summary['common_candidate_ready']} "
        f"common_freeze={summary['common_freeze_manifest_generated']} "
        f"common_heldout={summary['common_heldout_validated']}"
    )
    return 0 if summary["common_freeze_manifest_generated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
