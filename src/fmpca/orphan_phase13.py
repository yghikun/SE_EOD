from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .orphan_phase12 import run_manifest as run_phase12_manifest
from .report import write_json, write_markdown


SOURCE_CONFIRMED_BUG = "SOURCE_CONFIRMED_CORRECTNESS_BUG"


@dataclass(frozen=True)
class BugAssessment:
    case_id: str
    rule: str
    evidence_level: str
    source_anchor_match: bool
    minimal_replay_closed: bool
    unsafe_mechanism_documented: bool
    repair_contract_documented: bool
    source_confirmed: bool
    runtime_reproduced: bool
    upstream_acknowledged: bool
    security_impact_established: bool
    cve_claimed: bool

    @property
    def bug_claim_allowed(self) -> bool:
        return (
            self.evidence_level == SOURCE_CONFIRMED_BUG
            and self.source_anchor_match
            and self.minimal_replay_closed
            and self.unsafe_mechanism_documented
            and self.repair_contract_documented
            and self.source_confirmed
        )

    @property
    def evidence_boundary_preserved(self) -> bool:
        return not any(
            (
                self.runtime_reproduced,
                self.upstream_acknowledged,
                self.security_impact_established,
                self.cve_claimed,
            )
        )

    @property
    def closed(self) -> bool:
        return self.bug_claim_allowed and self.evidence_boundary_preserved

    def to_dict(self) -> Dict[str, Any]:
        value = asdict(self)
        value["bug_claim_allowed"] = self.bug_claim_allowed
        value["evidence_boundary_preserved"] = self.evidence_boundary_preserved
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


def assess_bugs(
    catalog: Dict[str, Any], phase12: Dict[str, Any]
) -> Tuple[BugAssessment, ...]:
    audits = {item["rule"]: item for item in phase12["counterexample_audits"]}
    assessments: List[BugAssessment] = []
    for case in catalog["cases"]:
        audit = audits[case["protocol_rule"]]
        actual_anchors = {
            (item["function"], item["line"]) for item in audit["source_slice"]
        }
        expected_anchors = {
            (item["function"], item["line"]) for item in case["source_anchors"]
        }
        assessments.append(
            BugAssessment(
                case["case_id"],
                case["protocol_rule"],
                case["evidence_level"],
                expected_anchors.issubset(actual_anchors),
                bool(
                    audit["closed"]
                    and audit["actual_result"] == "VIOLATION_UNDER_LOADED_SPEC"
                    and case["minimal_replay_rule"] in audit["violation_rules"]
                    and audit["rule_specific_irreducible"]
                ),
                bool(case["unsafe_mechanism"]),
                bool(case["repair_contract"]),
                bool(case["source_confirmed"]),
                bool(case["runtime_reproduced"]),
                bool(case["upstream_acknowledged"]),
                bool(case["security_impact_established"]),
                bool(case["cve_claimed"]),
            )
        )
    return tuple(assessments)


def _repair_objectives_closed(preregistration: Dict[str, Any]) -> bool:
    objectives = {item["objective_id"]: item for item in preregistration["repair_objectives"]}
    expected = {
        "REGISTRATION_ACCEPTANCE_FAILURE_CONTRACT": "OIDS-O1",
        "RECOVERY_CLEANUP_FAILURE_EXPOSURE_CONTRACT": "OIDS-O3",
    }
    return (
        set(objectives) == set(expected)
        and all(
            objectives[name]["preserved_violation_rule"] == rule
            and len(objectives[name]["required_safe_outcomes"]) >= 3
            and bool(objectives[name]["forbidden_outcome"])
            for name, rule in expected.items()
        )
    )


def _split_assessment(split: Dict[str, Any], preregistration: Dict[str, Any]) -> Dict[str, Any]:
    development = split["development"]
    development_ids = {item["case_id"] for item in development}
    preregistered_ids = {item["case_id"] for item in preregistration["development_cases"]}
    development_rules = {item["rule"] for item in development}
    validation_filesystems = {item["filesystem"].lower() for item in split["regression_validation"]}
    ineligible = {item.lower() for item in split["heldout_ineligible_filesystems"]}
    known_revealed = {"xfs", "f2fs", "btrfs", "ext4", "ubifs", "ocfs2", "reiserfs"}
    heldout_empty = split["heldout"] == []
    contamination_count = sum(
        1
        for item in split["heldout"]
        if item.get("filesystem", "").lower() in ineligible
    )
    closed = (
        development_ids == preregistered_ids
        and development_rules == {"OIDS-O1", "OIDS-O3"}
        and validation_filesystems == {"btrfs", "ext4", "ubifs", "ocfs2"}
        and known_revealed.issubset(ineligible)
        and heldout_empty
        and contamination_count == 0
        and split["heldout_status"]
        == "UNASSIGNED_REQUIRES_SEPARATE_PRE_REVEAL_PREREGISTRATION"
        and split["split_reset_closed"]
    )
    return {
        "development_case_count": len(development),
        "development_case_ids": sorted(development_ids),
        "development_rules": sorted(development_rules),
        "regression_validation_filesystems": sorted(validation_filesystems),
        "heldout_case_count": len(split["heldout"]),
        "heldout_empty": heldout_empty,
        "heldout_contamination_count": contamination_count,
        "known_revealed_filesystems_excluded": known_revealed.issubset(ineligible),
        "split_reset_closed": closed,
    }


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = _load(path)
    preregistration = _load(manifest["preregistration"])
    if _sha256(manifest["preregistration"]) != manifest["preregistration_sha256"]:
        raise ValueError("Phase 13 preregistration hash mismatch")
    pre_edit = _verify_hashes(preregistration["pre_edit_locks"], "Phase 13 pre-edit")
    artifacts = _verify_hashes(manifest["artifact_hashes"], "Phase 13 artifact")
    phase12 = run_phase12_manifest(manifest["phase12_manifest"])
    catalog = _load(manifest["bug_catalog"])
    split = _load(manifest["evaluation_split"])

    bugs = assess_bugs(catalog, phase12)
    bug_cases_closed = len(bugs) == 2 and all(item.closed for item in bugs)
    rules_preserved = {item.rule for item in bugs} == {"OIDS-O1", "OIDS-O3"}
    objectives_closed = _repair_objectives_closed(preregistration)
    split_assessment = _split_assessment(split, preregistration)
    terminology_policy_closed = (
        catalog["terminology_policy"]["allowed_claim"]
        == "source-confirmed correctness bug under the frozen OIDS contract"
        and len(catalog["terminology_policy"]["disallowed_claims_without_additional_evidence"])
        >= 5
        and all(item.evidence_boundary_preserved for item in bugs)
    )
    v0_1_frozen = (
        all(pre_edit.values())
        and preregistration["semantic_edits_before_preregistration"] == 0
        and not preregistration["base_protocol_mutated"]
        and preregistration["normative_safety_outcomes_preserved"]
        and phase12["phase12_claim_disposition_closed"]
        and phase12["failure_path_conformance_refuted"]
    )
    diagnostic_revision_only = (
        preregistration["revision_kind"]
        == "DIAGNOSTIC_AND_FAILURE_HANDLING_CONTRACT_EXTENSION"
        and rules_preserved
        and objectives_closed
        and not manifest["v0_2_protocol_implemented"]
    )
    phase13_closed = (
        all(artifacts.values())
        and v0_1_frozen
        and bug_cases_closed
        and terminology_policy_closed
        and objectives_closed
        and split_assessment["split_reset_closed"]
        and diagnostic_revision_only
    )
    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "manifest": path,
        "manifest_sha256": _sha256(path),
        "preregistration": manifest["preregistration"],
        "preregistration_hash_verified": True,
        "pre_edit_locks_verified": all(pre_edit.values()),
        "artifact_hashes_verified": all(artifacts.values()),
        "phase12_disposition_preserved": phase12["phase12_claim_disposition_closed"],
        "v0_1_frozen": v0_1_frozen,
        "v0_1_protocol_mutated": False,
        "v0_2_protocol_implemented": manifest["v0_2_protocol_implemented"],
        "diagnostic_revision_only": diagnostic_revision_only,
        "bug_assessments": [item.to_dict() for item in bugs],
        "bug_cases_closed": bug_cases_closed,
        "source_confirmed_bug_count": sum(item.bug_claim_allowed for item in bugs),
        "runtime_reproduced_bug_count": sum(item.runtime_reproduced for item in bugs),
        "upstream_acknowledged_bug_count": sum(item.upstream_acknowledged for item in bugs),
        "security_bug_count": sum(item.security_impact_established for item in bugs),
        "terminology_policy_closed": terminology_policy_closed,
        "repair_objectives_closed": objectives_closed,
        "preserved_violation_rules": sorted(item.rule for item in bugs),
        "split_assessment": split_assessment,
        "heldout_validation_allowed": False,
        "common_v0_2_validated": False,
        "phase13_preregistration_closed": phase13_closed,
        "next_phase_plan": manifest["next_phase_plan"],
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# OIDS Phase 13 v0.2 Revision Preregistration and Split Reset",
        "",
        f"Manifest: `{summary['manifest']}`",
        "",
        f"Preregistration closed: `{summary['phase13_preregistration_closed']}`",
        f"v0.1 frozen: `{summary['v0_1_frozen']}`",
        f"v0.2 implemented: `{summary['v0_2_protocol_implemented']}`",
        f"Held-out validation allowed: `{summary['heldout_validation_allowed']}`",
        "",
        "## ReiserFS development bugs",
        "",
        "| Case | Rule | Evidence | Bug claim | Runtime | Upstream | Security |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in summary["bug_assessments"]:
        lines.append(
            f"| {item['case_id']} | {item['rule']} | {item['evidence_level']} | "
            f"`{item['bug_claim_allowed']}` | `{item['runtime_reproduced']}` | "
            f"`{item['upstream_acknowledged']}` | `{item['security_impact_established']}` |"
        )
    split = summary["split_assessment"]
    lines.extend(
        [
            "",
            "## Split reset",
            "",
            f"Development cases: `{split['development_case_count']}`",
            f"Regression validation filesystems: `{', '.join(split['regression_validation_filesystems'])}`",
            f"Held-out cases: `{split['heldout_case_count']}`",
            f"Held-out contamination: `{split['heldout_contamination_count']}`",
            f"Split closed: `{split['split_reset_closed']}`",
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
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_phase13")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"preregistration_closed={summary['phase13_preregistration_closed']} "
        f"source_confirmed_bugs={summary['source_confirmed_bug_count']} "
        f"heldout_allowed={summary['heldout_validation_allowed']}"
    )
    return 0 if summary["phase13_preregistration_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
