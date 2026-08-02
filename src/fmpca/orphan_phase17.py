from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .report import write_json, write_markdown


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path: str) -> Dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _verify_hashes(values: Dict[str, str]) -> bool:
    if not values:
        raise ValueError("Phase 17 artifact hash lock must not be empty")
    for path, expected in values.items():
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"Phase 17 hash mismatch for {path}: {actual} != {expected}")
    return True


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = _load(path)
    artifacts_verified = _verify_hashes(manifest["artifact_hashes"])
    phase16 = _load(manifest["phase16_summary"])
    result_preserved = (
        phase16["phase16_heldout_evaluation_closed"]
        and phase16["applicability"] == manifest["frozen_result"]["applicability"]
        and phase16["controlled_reason_code"]
        == manifest["frozen_result"]["controlled_reason_code"]
        and phase16["conformance"] == manifest["frozen_result"]["conformance"]
        and phase16["diagnostic_disposition"]
        == manifest["frozen_result"]["diagnostic_disposition"]
        and phase16["candidate_replaced"] == manifest["candidate_replaced"]
        and phase16["stop_policy_honored"] == manifest["stop_policy_honored"]
    )
    common_gate = (
        phase16["applicability"] == "APPLICABLE"
        and phase16["conformance"] == "CONFORMANT_HELDOUT"
        and phase16["source_hashes_verified"]
        and phase16["evidence_anchors_closed"]
        and phase16["phase16_heldout_evaluation_closed"]
    )
    claim_matrix_closed = (
        len(manifest["claim_matrix"]) == 4
        and all(item["closed"] for item in manifest["claim_matrix"])
        and manifest["v0_2_claim_disposition"]
        == "HELDOUT_NON_APPLICABLE_NO_COMMON_VALIDATION"
        and not common_gate
        and not manifest["common_v0_2_validated"]
    )
    phase17_closed = (
        artifacts_verified
        and result_preserved
        and claim_matrix_closed
        and not manifest["candidate_replaced"]
        and manifest["stop_policy_honored"]
        and manifest["heldout_attempt_final"]
    )
    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "manifest": path,
        "manifest_sha256": _sha256(path),
        "artifact_hashes_verified": artifacts_verified,
        "phase16_result_preserved": result_preserved,
        "candidate": manifest["candidate"],
        "frozen_result": manifest["frozen_result"],
        "candidate_replaced": manifest["candidate_replaced"],
        "stop_policy_honored": manifest["stop_policy_honored"],
        "heldout_attempt_final": manifest["heldout_attempt_final"],
        "claim_matrix": manifest["claim_matrix"],
        "v0_2_claim_disposition": manifest["v0_2_claim_disposition"],
        "common_validation_gate_satisfied": common_gate,
        "common_v0_2_validated": manifest["common_v0_2_validated"],
        "claim_matrix_closed": claim_matrix_closed,
        "phase17_result_freeze_closed": phase17_closed,
        "next_phase_plan": manifest["next_phase_plan"],
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    result = summary["frozen_result"]
    lines = [
        "# OIDS Phase 17 Held-out Result Freeze",
        "",
        f"Candidate: `{summary['candidate']}`",
        f"Applicability: `{result['applicability']}`",
        f"Reason: `{result['controlled_reason_code']}`",
        f"Claim disposition: `{summary['v0_2_claim_disposition']}`",
        f"COMMON v0.2 validated: `{summary['common_v0_2_validated']}`",
        "",
        "## Claim matrix",
        "",
        "| Claim | Disposition | Closed |",
        "|---|---|---|",
    ]
    for item in summary["claim_matrix"]:
        lines.append(f"| {item['claim']} | {item['disposition']} | `{item['closed']}` |")
    lines.extend(["", "## Interpretation", "", summary["interpretation"], "", "Next phase: " + summary["next_phase_plan"], ""])
    return "\n".join(lines)


def run_and_write(manifest: str, json_out: str, markdown_out: str) -> Dict[str, Any]:
    summary = run_manifest(manifest)
    write_json(json_out, summary)
    write_markdown(markdown_out, _markdown(summary))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_phase17")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"freeze_closed={summary['phase17_result_freeze_closed']} "
        f"disposition={summary['v0_2_claim_disposition']} "
        f"common_v0_2={summary['common_v0_2_validated']}"
    )
    return 0 if summary["phase17_result_freeze_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
