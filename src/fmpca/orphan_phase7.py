from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple

from .report import count_bug_specific_conditions, write_json, write_markdown
from .scope import ScopeAssessment, assess_scope_files


CLOSED = "CLOSED"
BLOCKED = "BLOCKED"
QUALIFIED_SCOPE = "QUALIFIED_FS_SPECIFIC_SCOPE"


@dataclass(frozen=True)
class Phase7Assessment:
    scope: ScopeAssessment
    applicability_predicate_closed: bool
    errors_cont_explicitly_excluded: bool
    phase6_failstop_closed: bool
    phase6_negative_witnesses_closed: bool
    common_freeze_allowed: bool
    independent_family_status: str
    status: str
    blockers: Tuple[str, ...]

    @property
    def closed(self) -> bool:
        return self.status == CLOSED and not self.blockers

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["scope"] = self.scope.to_dict()
        value["closed"] = self.closed
        value["common_freeze_allowed"] = False
        value["blockers"] = list(self.blockers)
        return value


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path: str) -> Dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _verify_artifacts(values: Dict[str, str]) -> Dict[str, bool]:
    if not values:
        raise ValueError("Phase 7 artifact hash lock must not be empty")
    result = {}
    for path, expected in values.items():
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"Phase 7 artifact hash mismatch for {path}: {actual} != {expected}")
        result[path] = True
    return result


def analyze_phase7(manifest: Dict[str, Any]) -> Phase7Assessment:
    declaration = _load(manifest["scope_declaration"])
    taxonomy = manifest["taxonomy"]
    scope = assess_scope_files(taxonomy, manifest["scope_declaration"])
    phase6 = _load(manifest["phase6_summary"])
    predicate = declaration.get("applicability_predicate", {})
    predicate_closed = (
        predicate.get("filesystem") == "ext4"
        and predicate.get("error_policy") == "ERRORS_RO_OR_FAILSTOP"
        and predicate.get("excluded_error_policies") == ["ERRORS_CONT"]
        and predicate.get("expression") == "filesystem == ext4 AND error_policy != ERRORS_CONT"
    )
    exclusions = declaration.get("excluded_configurations", [])
    errors_cont_excluded = any(
        item.get("filesystem") == "ext4"
        and item.get("configuration") == "ERRORS_CONT"
        and item.get("status") == "EXCLUDED_BY_EXPLICIT_PREDICATE"
        for item in exclusions
    )
    failstop_closed = bool(phase6.get("failstop_profile_closed"))
    negative_closed = bool(phase6.get("errors_continue_negative_witness_closed"))
    blockers = []
    if not scope.declaration_valid:
        blockers.append("PHASE7_SCOPE_DECLARATION_INVALID")
    if scope.declared_semantic_scope != "FS_SPECIFIC":
        blockers.append("PHASE7_SCOPE_NOT_FS_SPECIFIC")
    if scope.freeze_boundary != "NARROW_FREEZE":
        blockers.append("PHASE7_SCOPE_NOT_NARROW_FREEZE")
    if not predicate_closed:
        blockers.append("PHASE7_APPLICABILITY_PREDICATE_NOT_EXPLICIT")
    if not errors_cont_excluded:
        blockers.append("PHASE7_ERRORS_CONT_NOT_EXPLICITLY_EXCLUDED")
    if not failstop_closed:
        blockers.append("PHASE7_PHASE6_FAILSTOP_GATE_NOT_CLOSED")
    if not negative_closed:
        blockers.append("PHASE7_PHASE6_NEGATIVE_WITNESS_GATE_NOT_CLOSED")
    if scope.common_freeze_ready:
        blockers.append("PHASE7_COMMON_FREEZE_GATE_MUST_REMAIN_FALSE")
    status = CLOSED if not blockers else BLOCKED
    return Phase7Assessment(
        scope,
        predicate_closed,
        errors_cont_excluded,
        failstop_closed,
        negative_closed,
        False,
        declaration.get("independent_family_status", "UNKNOWN"),
        status,
        tuple(blockers),
    )


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = _load(path)
    locks = _verify_artifacts(manifest["artifact_hashes"])
    assessment = analyze_phase7(manifest)
    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "manifest": path,
        "manifest_sha256": _sha256(path),
        "artifact_hashes_verified": all(locks.values()),
        "bug_specific_condition_count": count_bug_specific_conditions([manifest]),
        "assessment": assessment.to_dict(),
        "qualified_scope_closed": assessment.closed,
        "common_freeze_manifest_generated": False,
        "blind_held_out_claim_allowed": False,
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    assessment = summary["assessment"]
    scope = assessment["scope"]
    lines = [
        "# OIDS Phase 7 Qualified ext4 Failstop Scope",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"Qualified scope closed: `{summary['qualified_scope_closed']}`",
        f"Semantic scope: `{scope['declared_semantic_scope']}`",
        f"Freeze boundary: `{scope['freeze_boundary']}`",
        f"ERRORS_CONT explicitly excluded: `{assessment['errors_cont_explicitly_excluded']}`",
        f"COMMON freeze generated: `{summary['common_freeze_manifest_generated']}`",
        f"Blind held-out claim allowed: `{summary['blind_held_out_claim_allowed']}`",
        "",
        "## Applicability",
        "",
        "`filesystem == ext4 AND error_policy != ERRORS_CONT`",
        "",
        "The declared scope is `FS_SPECIFIC` and `NARROW_FREEZE`; it covers only the",
        "non-continuing ext4 failstop profile. The Phase 6 ERRORS_CONT witnesses remain",
        "an explicit exclusion and are not hidden assumptions.",
        "",
        "## Gate result",
        "",
        "| Gate | Result |",
        "|---|---|",
        f"| scope declaration | `{scope['declaration_valid']}` |",
        f"| Phase 6 failstop closure | `{assessment['phase6_failstop_closed']}` |",
        f"| Phase 6 negative witnesses | `{assessment['phase6_negative_witnesses_closed']}` |",
        f"| independent family status | `{assessment['independent_family_status']}` |",
        "",
        summary["interpretation"],
        "",
    ]
    return "\n".join(lines)


def run_and_write(manifest: str, json_out: str, markdown_out: str) -> Dict[str, Any]:
    summary = run_manifest(manifest)
    write_json(json_out, summary)
    write_markdown(markdown_out, _markdown(summary))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_phase7")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"qualified_scope_closed={summary['qualified_scope_closed']} "
        f"common_freeze={summary['common_freeze_manifest_generated']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
