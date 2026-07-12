"""Evaluate an SE-EOD pilot and its separate annotation JSONL file."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ALLOWED_VERDICTS = {"true_bug", "false_positive", "uncertain"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"expected object at {path}:{line_number}")
            rows.append(value)
    return rows


def index_by_sample(rows: list[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        sample_id = row.get("sample_id")
        if not isinstance(sample_id, str) or not sample_id:
            raise ValueError(f"{label} row has no sample_id")
        if sample_id in indexed:
            raise ValueError(f"duplicate sample_id in {label}: {sample_id}")
        indexed[sample_id] = row
    return indexed


def precision(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    return sum(row["verdict"] == "true_bug" for row in rows) / len(rows)


def rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def evaluate(pilot_rows: list[dict[str, Any]], label_rows: list[dict[str, Any]]) -> dict[str, Any]:
    pilot = index_by_sample(pilot_rows, "pilot")
    labels = index_by_sample(label_rows, "labels")
    missing = sorted(set(pilot) - set(labels))
    extra = sorted(set(labels) - set(pilot))
    if missing or extra:
        raise ValueError(f"sample mismatch: missing_labels={missing}, extra_labels={extra}")

    joined: list[dict[str, Any]] = []
    for row in pilot_rows:
        label = labels[row["sample_id"]]
        verdict = label.get("verdict")
        if verdict not in ALLOWED_VERDICTS:
            raise ValueError(f"invalid verdict for {row['sample_id']}: {verdict}")
        joined.append(
            {
                "sample_id": row["sample_id"],
                "candidate_type": row.get("candidate_type", "unknown"),
                "verdict": verdict,
            }
        )

    counts = Counter(row["verdict"] for row in joined)
    by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, row in enumerate(joined):
        bucket = "top" if index < len(joined) / 3 else "middle" if index < 2 * len(joined) / 3 else "low"
        by_bucket[bucket].append(row)
        by_type[row["candidate_type"]].append(row)

    return {
        "sample_count": len(joined),
        "verdict_counts": dict(sorted(counts.items())),
        "precision": rounded(precision(joined)),
        "precision_at": {
            str(k): rounded(precision(joined[:k]))
            for k in (10, 20, 50, 100)
            if k <= len(joined)
        },
        "by_rank_bucket": {
            key: {
                "count": len(rows),
                "precision": rounded(precision(rows)),
                "verdict_counts": dict(sorted(Counter(row["verdict"] for row in rows).items())),
            }
            for key, rows in by_bucket.items()
        },
        "by_candidate_type": {
            key: {
                "count": len(rows),
                "precision": rounded(precision(rows)),
                "verdict_counts": dict(sorted(Counter(row["verdict"] for row in rows).items())),
            }
            for key, rows in sorted(by_type.items())
        },
    }


def markdown_report(result: dict[str, Any]) -> str:
    lines = [
        "# Benchmark Evaluation",
        "",
        "> This report evaluates one annotation pass. It is not an independent gold-set result until a second reviewer and adjudication are complete.",
        "",
        f"- Samples: {result['sample_count']}",
        f"- Overall precision: {result['precision']}",
        "",
        "## Verdicts",
        "",
        "| Verdict | Count |",
        "|---|---:|",
    ]
    for verdict, count in result["verdict_counts"].items():
        lines.append(f"| `{verdict}` | {count} |")
    lines.extend(["", "## Precision at K", "", "| K | Precision |", "|---:|---:|"])
    for k, value in result["precision_at"].items():
        lines.append(f"| {k} | {value} |")
    lines.extend(["", "## Rank Buckets", "", "| Bucket | Count | Precision | Verdicts |", "|---|---:|---:|---|"])
    for bucket, data in result["by_rank_bucket"].items():
        verdicts = ", ".join(f"{key}={value}" for key, value in data["verdict_counts"].items())
        lines.append(f"| {bucket} | {data['count']} | {data['precision']} | {verdicts} |")
    lines.extend(["", "## Candidate Types", "", "| Type | Count | Precision | Verdicts |", "|---|---:|---:|---|"])
    for candidate_type, data in result["by_candidate_type"].items():
        verdicts = ", ".join(f"{key}={value}" for key, value in data["verdict_counts"].items())
        lines.append(f"| `{candidate_type}` | {data['count']} | {data['precision']} | {verdicts} |")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--report-out", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = evaluate(load_jsonl(args.pilot), load_jsonl(args.labels))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.report_out:
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(markdown_report(result), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
