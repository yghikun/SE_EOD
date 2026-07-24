"""CLI for triaging UNCLOSED_METADATA_RESIDUAL reports."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.candidate_triage import write_candidate_triage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize candidate residual reports by function, residual "
            "identity, and plane/delta."
        )
    )
    parser.add_argument(
        "evaluation_output",
        help="evaluation output directory or reports/all_reports.json path",
    )
    parser.add_argument(
        "--output-dir",
        help="directory for candidate_triage.json and candidate_triage.md",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=10,
        help="number of top functions/identities to keep",
    )
    parser.add_argument(
        "--examples-per-item",
        type=int,
        default=3,
        help="number of concrete failure-point examples to retain per row",
    )
    args = parser.parse_args(argv)

    outputs = write_candidate_triage(
        args.evaluation_output,
        output_dir=args.output_dir,
        top_n=args.top_n,
        examples_per_item=args.examples_per_item,
    )
    print(
        json.dumps(
            {name: path.as_posix() for name, path in outputs.items()},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
