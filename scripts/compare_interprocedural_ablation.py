"""Compare a baseline run with the opt-in interprocedural analysis."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.compare_experiment_v1_3 import load_jsonl, stable_key
except ModuleNotFoundError:
    from compare_experiment_v1_3 import load_jsonl, stable_key


def load_labels(path: Path) -> dict[str, str]:
    labels: dict[str, str] = {}
    if not path.exists():
        return labels
    for row in load_jsonl(path):
        sample_id = str(row.get("sample_id", ""))
        verdict = str(row.get("verdict", ""))
        if sample_id and verdict:
            labels[sample_id] = verdict
    return labels


def pilot_candidate_labels(
    manifest_path: Path, labels_path: Path
) -> dict[str, dict[str, str]]:
    labels = load_labels(labels_path)
    result: dict[str, dict[str, str]] = {}
    if not manifest_path.exists():
        return result
    for row in load_jsonl(manifest_path):
        sample_id = str(row.get("sample_id", ""))
        candidate_id = str(row.get("candidate_id", ""))
        verdict = labels.get(sample_id)
        if candidate_id and verdict:
            result[candidate_id] = {"sample_id": sample_id, "verdict": verdict}
    return result


def compare(
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    pilot: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    before_index = {stable_key(row): row for row in before}
    after_index = {stable_key(row): row for row in after}
    retained = before_index.keys() & after_index.keys()
    removed = before_index.keys() - after_index.keys()
    added = after_index.keys() - before_index.keys()
    result: dict[str, Any] = {
        "before": len(before),
        "after": len(after),
        "retained": len(retained),
        "removed": len(removed),
        "added": len(added),
        "reduction": round((len(before) - len(after)) / len(before), 4)
        if before
        else None,
        "removed_by_type": dict(
            sorted(Counter(before_index[key].get("candidate_type", "unknown") for key in removed).items())
        ),
    }

    candidate_ids_after = {str(row.get("candidate_id", "")) for row in after}
    candidate_ids_before = {str(row.get("candidate_id", "")) for row in before}
    eligible = {
        candidate_id: annotation
        for candidate_id, annotation in (pilot or {}).items()
        if candidate_id in candidate_ids_before
    }
    verdict_totals = Counter(item["verdict"] for item in eligible.values())
    verdict_retained = Counter(
        item["verdict"]
        for candidate_id, item in eligible.items()
        if candidate_id in candidate_ids_after
    )
    result["pilot"] = {
        "eligible": len(eligible),
        "not_in_baseline": len(pilot or {}) - len(eligible),
        "by_verdict": dict(sorted(verdict_totals.items())),
        "retained_by_verdict": dict(sorted(verdict_retained.items())),
        "true_positive_retention": _ratio(
            verdict_retained["true_bug"], verdict_totals["true_bug"]
        ),
        "labeled_false_positives_removed": verdict_totals["false_positive"]
        - verdict_retained["false_positive"],
    }
    return result


def markdown(result: dict[str, Any]) -> str:
    reduction = result["reduction"]
    reduction_text = "n/a" if reduction is None else f"{reduction:.1%}"
    pilot = result["pilot"]
    retention = pilot["true_positive_retention"]
    retention_text = "n/a" if retention is None else f"{retention:.1%}"
    return "\n".join(
        [
            "# Interprocedural Ablation",
            "",
            f"Generated: {result['generated_at']}",
            "",
            "| Baseline | Interprocedural | Retained | Removed | Added | Reduction |",
            "|---:|---:|---:|---:|---:|---:|",
            f"| {result['before']} | {result['after']} | {result['retained']} | "
            f"{result['removed']} | {result['added']} | {reduction_text} |",
            "",
            "## Development Pilot Check",
            "",
            f"- Eligible labeled candidates: {pilot['eligible']}",
            f"- Pilot candidates absent from this baseline: {pilot['not_in_baseline']}",
            f"- True-positive retention: {retention_text}",
            f"- Labeled false positives removed: {pilot['labeled_false_positives_removed']}",
            "",
            "This pilot is a development-set safety check, not an independent gold-test result. "
            "Candidate reduction is not interpreted as a precision improvement.",
            "",
        ]
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument(
        "--pilot-manifest",
        type=Path,
        default=Path("benchmark/ext4-v6.8-pilot-manifest.jsonl"),
    )
    parser.add_argument(
        "--pilot-labels",
        type=Path,
        default=Path("benchmark/ext4-v6.8-pilot-labels.jsonl"),
    )
    parser.add_argument("--json-out", required=True, type=Path)
    parser.add_argument("--report-out", required=True, type=Path)
    args = parser.parse_args()

    pilot = pilot_candidate_labels(args.pilot_manifest, args.pilot_labels)
    result = compare(load_jsonl(args.before), load_jsonl(args.after), pilot)
    result["schema_version"] = 1
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["before_path"] = str(args.before)
    result["after_path"] = str(args.after)

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report = markdown(result)
    args.report_out.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
