from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .report import write_json, write_markdown


def _sha256(path: str | Path) -> str:
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


def _verify_source_manifest(source: Dict[str, Any]) -> Dict[str, bool]:
    root = Path(source["source_root"])
    locks = {**source["registered_files"], **source["structural_files"]}
    return _verify_hashes(
        {str(root / path): digest for path, digest in locks.items()}, "JFS source"
    )


def _verify_anchors(root: Path, anchors: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for anchor in anchors:
        lines = (root / anchor["path"]).read_text(encoding="utf-8").splitlines()
        line = lines[anchor["line"] - 1] if anchor["line"] <= len(lines) else ""
        matched = anchor["contains"] in line
        results.append({**anchor, "actual_line": line.strip(), "matched": matched})
    return results


def run_manifest(path: str) -> Dict[str, Any]:
    manifest = _load(path)
    artifacts = _verify_hashes(manifest["artifact_hashes"], "Phase 16 artifact")
    phase15 = _load(manifest["phase15_summary"])
    preregistration = _load(manifest["preregistration"])
    amendment = _load(manifest["source_amendment"])
    source = _load(manifest["source_manifest"])
    source_locks = _verify_source_manifest(source)
    source_root = Path(source["source_root"])
    anchors = _verify_anchors(source_root, manifest["evidence_anchors"])

    registered_match = set(source["registered_files"]) == set(
        preregistration["registered_target_sources"]
    )
    structural_amendment_closed = (
        amendment["amendment_kind"] == "STRUCTURAL_RECOVERY_IMPLEMENTATION_PATH_ONLY"
        and amendment["requested_recovery_source_status"]
        == "ABSENT_AT_PINNED_REVISION"
        and amendment["added_target_sources"] == ["fs/jfs/Makefile"]
        and not any(
            amendment[key]
            for key in (
                "semantic_dimensions_changed",
                "candidate_changed",
                "source_revision_changed",
                "decision_partition_changed",
                "controlled_reasons_changed",
                "stop_policy_changed",
            )
        )
    )
    searched_paths = [
        source_root / item
        for item in [*source["registered_files"], *source["structural_files"]]
    ]
    forbidden_tokens = ("orphan", "next_orphan", "prev_orphan", "orphan_file")
    token_hits = {
        token: [str(item) for item in searched_paths if token in item.read_text(encoding="utf-8").lower()]
        for token in forbidden_tokens
    }
    persistent_registry_absent = not any(token_hits.values())
    screening = manifest["screening"]
    dimensions_closed = (
        [item["dimension"] for item in screening]
        == ["object", "relation", "lifecycle", "authority", "deadline"]
        and screening[0]["status"] == "NOT_SATISFIED"
        and screening[0]["reason_code"] == "PERSISTENT_CLEANUP_OBJECT_NOT_FOUND"
        and all(item["closed"] for item in screening)
    )
    decision_closed = (
        manifest["applicability"] == "NON_APPLICABLE"
        and manifest["controlled_reason_code"]
        in preregistration["controlled_non_applicable_reasons"]
        and manifest["controlled_reason_code"]
        == "PERSISTENT_CLEANUP_OBJECT_NOT_FOUND"
        and manifest["conformance"] == "NOT_EVALUABLE"
        and manifest["diagnostic_disposition"] == "NOT_APPLICABLE"
        and not manifest["replay_required"]
        and not manifest["candidate_replaced"]
        and manifest["stop_policy_honored"]
    )
    phase16_closed = (
        all(artifacts.values())
        and phase15["phase15_preregistration_closed"]
        and phase15["source_unrevealed_at_freeze"]
        and phase15["selected_candidate"] == "JFS"
        and source["git_commit"] == preregistration["source_version"]["git_commit"]
        and registered_match
        and structural_amendment_closed
        and all(source_locks.values())
        and all(item["matched"] for item in anchors)
        and persistent_registry_absent
        and dimensions_closed
        and decision_closed
    )
    return {
        "schema_version": 1,
        "evaluation_id": manifest["evaluation_id"],
        "manifest": path,
        "manifest_sha256": _sha256(path),
        "artifact_hashes_verified": all(artifacts.values()),
        "phase15_preregistration_preserved": phase15["phase15_preregistration_closed"],
        "source_revision": source["git_commit"],
        "registered_sources_acquired": registered_match and len(source["registered_files"]) == 10,
        "source_hashes_verified": all(source_locks.values()),
        "structural_amendment_closed": structural_amendment_closed,
        "absent_recovery_path": amendment["requested_recovery_source"],
        "evidence_anchors": anchors,
        "evidence_anchors_closed": all(item["matched"] for item in anchors),
        "persistent_registry_token_hits": token_hits,
        "persistent_registry_absent": persistent_registry_absent,
        "source_stages": manifest["source_stages"],
        "screening": screening,
        "applicability": manifest["applicability"],
        "controlled_reason_code": manifest["controlled_reason_code"],
        "conformance": manifest["conformance"],
        "diagnostic_disposition": manifest["diagnostic_disposition"],
        "replay_required": manifest["replay_required"],
        "candidate_replaced": manifest["candidate_replaced"],
        "stop_policy_honored": manifest["stop_policy_honored"],
        "common_v0_2_validated": False,
        "phase16_heldout_evaluation_closed": phase16_closed,
        "next_phase_plan": manifest["next_phase_plan"],
        "interpretation": manifest["interpretation"],
    }


def _markdown(summary: Dict[str, Any]) -> str:
    lines = [
        "# OIDS Phase 16 JFS Blind Held-out Evaluation",
        "",
        f"Applicability: `{summary['applicability']}`",
        f"Reason: `{summary['controlled_reason_code']}`",
        f"Conformance: `{summary['conformance']}`",
        f"Candidate replaced: `{summary['candidate_replaced']}`",
        "",
        "## Screening",
        "",
        "| Dimension | Status | Reason | Closed |",
        "|---|---|---|---|",
    ]
    for item in summary["screening"]:
        lines.append(
            f"| {item['dimension']} | {item['status']} | {item['reason_code']} | `{item['closed']}` |"
        )
    lines.extend(
        [
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
    parser = argparse.ArgumentParser(prog="python -m src.fmpca.orphan_phase16")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json-out", required=True)
    parser.add_argument("--markdown-out", required=True)
    args = parser.parse_args(argv)
    summary = run_and_write(args.manifest, args.json_out, args.markdown_out)
    print(
        f"evaluation_closed={summary['phase16_heldout_evaluation_closed']} "
        f"applicability={summary['applicability']} "
        f"reason={summary['controlled_reason_code']}"
    )
    return 0 if summary["phase16_heldout_evaluation_closed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
