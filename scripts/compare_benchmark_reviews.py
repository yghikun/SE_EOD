"""Compare two independent benchmark review passes."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

try:
    from scripts.evaluate_benchmark import ALLOWED_VERDICTS, index_by_sample, load_jsonl
except ModuleNotFoundError:  # Direct execution: python scripts/compare_benchmark_reviews.py
    from evaluate_benchmark import ALLOWED_VERDICTS, index_by_sample, load_jsonl


def compare(first_rows: list[dict[str, Any]], second_rows: list[dict[str, Any]]) -> dict[str, Any]:
    first = index_by_sample(first_rows, "first review")
    second = index_by_sample(second_rows, "second review")
    if set(first) != set(second):
        missing = sorted(set(first) - set(second))
        extra = sorted(set(second) - set(first))
        raise ValueError(f"sample mismatch: missing_second={missing}, extra_second={extra}")

    pairs: list[tuple[str, str, str]] = []
    for sample_id in first:
        first_verdict = first[sample_id].get("verdict")
        second_verdict = second[sample_id].get("verdict")
        if first_verdict not in ALLOWED_VERDICTS:
            raise ValueError(f"invalid first verdict for {sample_id}: {first_verdict}")
        if second_verdict not in ALLOWED_VERDICTS:
            raise ValueError(f"invalid second verdict for {sample_id}: {second_verdict}")
        pairs.append((sample_id, first_verdict, second_verdict))

    total = len(pairs)
    agreements = sum(first_verdict == second_verdict for _, first_verdict, second_verdict in pairs)
    first_counts = Counter(first_verdict for _, first_verdict, _ in pairs)
    second_counts = Counter(second_verdict for _, _, second_verdict in pairs)
    observed = agreements / total if total else 0.0
    expected = (
        sum((first_counts[label] / total) * (second_counts[label] / total) for label in ALLOWED_VERDICTS)
        if total
        else 0.0
    )
    kappa = (observed - expected) / (1 - expected) if expected < 1 else (1.0 if observed == 1 else 0.0)
    disagreements = [
        {"sample_id": sample_id, "first": first_verdict, "second": second_verdict}
        for sample_id, first_verdict, second_verdict in pairs
        if first_verdict != second_verdict
    ]
    return {
        "sample_count": total,
        "agreement_count": agreements,
        "agreement_rate": round(observed, 4),
        "cohen_kappa": round(kappa, 4),
        "first_verdict_counts": dict(sorted(first_counts.items())),
        "second_verdict_counts": dict(sorted(second_counts.items())),
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", required=True, type=Path)
    parser.add_argument("--second", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = compare(load_jsonl(args.first), load_jsonl(args.second))
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
