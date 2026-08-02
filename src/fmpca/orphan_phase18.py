from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .report import write_json, write_markdown


def _sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path: str) -> Dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _resolve(value: Dict[str, Any], dotted: str) -> Any:
    current: Any = value
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"missing release assertion path: {dotted}")
        current = current[part]
    return current


def _verify_hashes(values: Dict[str, str]) -> bool:
    if not values:
        raise ValueError("final release artifact hash lock must not be empty")
    for path, expected in values.items():
        actual = _sha256(path)
        if actual != expected:
            raise ValueError(f"final release hash mismatch for {path}: {actual} != {expected}")
    return True


def _verify_phase_chain(entries: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    expected_phases = list(range(1, 18))
    if [item["phase"] for item in entries] != expected_phases:
        raise ValueError("final release must enumerate Phase 1 through Phase 17 exactly")
    for entry in entries:
        actual_hash = _sha256(entry["artifact"])
        if actual_hash != entry["sha256"]:
            raise ValueError(
                f"Phase {entry['phase']} chain hash mismatch: {actual_hash} != {entry['sha256']}"
            )
        assertions_closed = True
        if entry.get("assertions"):
            artifact = _load(entry["artifact"])
            assertions_closed = all(
                _resolve(artifact, dotted) == expected
                for dotted, expected in entry["assertions"].items()
            )
        results.append(
            {
                "phase": entry["phase"],
                "artifact": entry["artifact"],
                "sha256_verified": True,
                "assertions_closed": assertions_closed,
                "closed": assertions_closed,
            }
        )
    return results


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = _load(path)
    artifacts_verified = _verify_hashes(manifest["artifact_hashes"])
    phase_chain = _verify_phase_chain(manifest["phase_chain"])
    phase17 = _load(manifest["phase17_summary"])
    claim_matrix_closed = (
        len(manifest["final_claim_matrix"]) == 6
        and all(item["closed"] for item in manifest["final_claim_matrix"])
        and phase17["phase17_result_freeze_closed"]
        and phase17["v0_2_claim_disposition"]
        == "HELDOUT_NON_APPLICABLE_NO_COMMON_VALIDATION"
        and not phase17["common_v0_2_validated"]
    )
    endpoint_closed = (
        manifest["project_status"] == "COMPLETE"
        and not manifest["further_phase_expansion"]
        and manifest["maintenance_mode"]
        and manifest["hard_endpoint"] == "PHASE_18"
        and manifest["allowed_next_work"]
        == ["bug fixes", "dependency maintenance", "reproducibility maintenance"]
    )
    project_complete = (
        artifacts_verified
        and len(phase_chain) == 17
        and all(item["closed"] for item in phase_chain)
        and claim_matrix_closed
        and endpoint_closed
    )
    return {
        "schema_version": 1,
        "release_id": manifest["release_id"],
        "release_version": manifest["release_version"],
        "manifest": path,
        "manifest_sha256": _sha256(path),
        "artifact_hashes_verified": artifacts_verified,
        "phase_chain": phase_chain,
        "phase_chain_closed": all(item["closed"] for item in phase_chain),
        "final_claim_matrix": manifest["final_claim_matrix"],
        "claim_matrix_closed": claim_matrix_closed,
        "v0_2_claim_disposition": phase17["v0_2_claim_disposition"],
        "common_v0_2_validated": phase17["common_v0_2_validated"],
        "project_status": manifest["project_status"],
        "hard_endpoint": manifest["hard_endpoint"],
        "further_phase_expansion": manifest["further_phase_expansion"],
        "maintenance_mode": manifest["maintenance_mode"],
        "allowed_next_work": manifest["allowed_next_work"],
        "endpoint_closed": endpoint_closed,
        "project_complete": project_complete,
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# OIDS Final Release v0.2",
        "",
        f"Project status: `{summary['project_status']}`",
        f"Hard endpoint: `{summary['hard_endpoint']}`",
        f"Maintenance mode: `{summary['maintenance_mode']}`",
        f"COMMON v0.2 validated: `{summary['common_v0_2_validated']}`",
        "",
        "## Final claim matrix",
        "",
        "| Claim | Disposition | Closed |",
        "|---|---|---|",
    ]
    for item in summary["final_claim_matrix"]:
        lines.append(f"| {item['claim']} | {item['disposition']} | `{item['closed']}` |")
    lines.extend(
        [
            "",
            "## Endpoint",
            "",
            summary["interpretation"],
            "",
            "Further numbered phase expansion is disabled. Only maintenance work is in scope.",
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
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_phase18")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"project_complete={summary['project_complete']} "
        f"status={summary['project_status']} "
        f"maintenance_mode={summary['maintenance_mode']}"
    )
    return 0 if summary["project_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
