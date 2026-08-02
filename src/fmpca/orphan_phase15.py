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


def _verify_hashes(values: Dict[str, str], label: str) -> Dict[str, bool]:
    if not values:
        raise ValueError(f"{label} hash lock must not be empty")
    verified: Dict[str, bool] = {}
    for path, expected in values.items():
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"{label} hash mismatch for {path}: {actual} != {expected}")
        verified[path] = True
    return verified


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = _load(path)
    artifacts = _verify_hashes(manifest["artifact_hashes"], "Phase 15 artifact")
    preregistration = _load(manifest["preregistration"])
    pool = _load(preregistration["candidate_pool"])
    regression = _load(preregistration["regression_freeze"])
    phase14 = _load(regression["phase14_summary"])
    pre_reveal = _verify_hashes(preregistration["pre_reveal_locks"], "pre-reveal")

    selected = [
        item for item in pool["candidates"] if item.get("selection") == "SELECTED"
    ]
    revealed = {item.lower() for item in pool["ineligible_revealed_filesystems"]}
    candidate_closed = (
        len(selected) == 1
        and selected[0]["filesystem"] == "JFS"
        and pool["selected_candidate"] == "JFS"
        and selected[0]["eligibility"] == "ELIGIBLE_UNREVEALED"
        and selected[0]["prior_oids_artifact_occurrences"] == 0
        and not selected[0]["prior_source_directory_present"]
        and "jfs" not in revealed
        and not pool["source_inspection_performed"]
        and not pool["candidate_replacement_allowed_after_reveal"]
    )
    regression_closed = (
        phase14["phase14_v0_2_diagnostic_closed"]
        and phase14["regression_boundaries_preserved"]
        and phase14["diagnostic_mappings_closed"]
        and not phase14["heldout_validation_allowed"]
        and not phase14["common_v0_2_validated"]
        and len(regression["regression_boundaries"]) == 4
        and all(item["status"] == "PRESERVED" for item in regression["regression_boundaries"])
        and len(regression["development_violations"]) == 2
        and all(item["status"] == "VIOLATION_PRESERVED" for item in regression["development_violations"])
        and not regression["heldout_partition_assigned"]
        and not regression["common_v0_2_validated"]
    )
    source_root = Path(manifest["future_source_root"])
    source_unrevealed_at_freeze = not source_root.exists()
    preregistration_closed = (
        preregistration["candidate_filesystem"] == "JFS"
        and preregistration["candidate_status_before_reveal"]
        == "UNREVEALED_V0_2_POST_FREEZE_HELDOUT"
        and preregistration["validation_role"]
        == "PREREGISTERED_V0_2_BLIND_HELD_OUT"
        and preregistration["source_version"]["git_commit"]
        == "38fec10eb60d687e30c8c6b5420d86e8149f7557"
        and len(preregistration["registered_target_sources"]) == 10
        and len(set(preregistration["registered_target_sources"])) == 10
        and preregistration["stop_policy"]
        == "ACCEPT_FIRST_COMPLETE_RESULT_WITHOUT_CANDIDATE_REPLACEMENT"
        and all(pre_reveal.values())
    )
    phase15_closed = (
        all(artifacts.values())
        and candidate_closed
        and regression_closed
        and preregistration_closed
        and source_unrevealed_at_freeze
    )
    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "manifest": path,
        "manifest_sha256": _sha256(path),
        "preregistration": manifest["preregistration"],
        "preregistration_sha256": _sha256(manifest["preregistration"]),
        "artifact_hashes_verified": all(artifacts.values()),
        "pre_reveal_locks_verified": all(pre_reveal.values()),
        "phase14_closed": phase14["phase14_v0_2_diagnostic_closed"],
        "regression_freeze_closed": regression_closed,
        "candidate_pool_closed": candidate_closed,
        "selected_candidate": pool["selected_candidate"],
        "candidate_replaced": False,
        "registered_source_count": len(preregistration["registered_target_sources"]),
        "source_unrevealed_at_freeze": source_unrevealed_at_freeze,
        "heldout_validation_allowed": False,
        "common_v0_2_validated": False,
        "phase15_preregistration_closed": phase15_closed,
        "next_phase_plan": manifest["next_phase_plan"],
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    return "\n".join(
        [
            "# OIDS Phase 15 v0.2 Held-out Preregistration Freeze",
            "",
            f"Manifest: `{summary['manifest']}`",
            "",
            f"Preregistration closed: `{summary['phase15_preregistration_closed']}`",
            f"Selected candidate: `{summary['selected_candidate']}`",
            f"Registered sources: `{summary['registered_source_count']}`",
            f"Source unrevealed at freeze: `{summary['source_unrevealed_at_freeze']}`",
            f"Candidate replaced: `{summary['candidate_replaced']}`",
            f"COMMON v0.2 validated: `{summary['common_v0_2_validated']}`",
            "",
            "## Interpretation",
            "",
            summary["interpretation"],
            "",
            "Next phase: " + summary["next_phase_plan"],
            "",
        ]
    )


def run_and_write(manifest: str, json_out: str, markdown_out: str) -> Dict[str, Any]:
    summary = run_manifest(manifest)
    write_json(json_out, summary)
    write_markdown(markdown_out, _markdown(summary))
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_phase15")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"preregistration_closed={summary['phase15_preregistration_closed']} "
        f"candidate={summary['selected_candidate']} "
        f"source_unrevealed={summary['source_unrevealed_at_freeze']}"
    )
    return 0 if summary["phase15_preregistration_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
