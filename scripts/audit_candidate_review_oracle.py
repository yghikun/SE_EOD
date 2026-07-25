#!/usr/bin/env python3
"""Audit the M32d report-level review oracle against a current full run."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.candidate_review_oracle import audit_oracle, compare_audit_safety, load_jsonl


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "current",
        nargs="+",
        help="one or more current full evaluation output directories",
    )
    parser.add_argument(
        "--oracle",
        default=str(ROOT / "outputs" / "candidate_review_oracle.jsonl"),
    )
    parser.add_argument("--output", help="optional JSON audit artifact")
    parser.add_argument(
        "--baseline-audit",
        help="optional prior audit used to distinguish new from pre-existing issues",
    )
    parser.add_argument("--fail-on-safety-regression", action="store_true")
    args = parser.parse_args(argv)

    audit = audit_oracle(load_jsonl(args.oracle), args.current)
    if args.baseline_audit:
        baseline = json.loads(Path(args.baseline_audit).read_text(encoding="utf-8"))
        compare_audit_safety(audit, baseline)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(audit["summary"], indent=2, sort_keys=True))
    safety_count = audit["summary"].get(
        "new_safety_regression_count",
        audit["summary"]["safety_regression_count"],
    )
    if args.fail_on_safety_regression and safety_count:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
