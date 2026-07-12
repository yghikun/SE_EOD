"""Create a blank, separate reviewer label file from a benchmark pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.evaluate_benchmark import load_jsonl
except ModuleNotFoundError:  # Direct execution: python scripts/prepare_benchmark_review.py
    from evaluate_benchmark import load_jsonl


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reviewer", required=True)
    args = parser.parse_args()

    rows = load_jsonl(args.pilot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            label = {
                "sample_id": row["sample_id"],
                "candidate_id": row["candidate_id"],
                "verdict": None,
                "confidence": None,
                "reason": None,
                "evidence": [],
                "upstream_status": "unknown",
                "reviewer": args.reviewer,
                "reviewed_at": None,
            }
            handle.write(json.dumps(label, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"review_samples={len(rows)}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
