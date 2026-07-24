"""CLI for the metadata residual evaluation harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation_harness import run_evaluation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run failure-local metadata residual analysis on one C source file."
    )
    parser.add_argument("source_file", help="C source file to analyze")
    parser.add_argument("--source-root", help="source root for stable identity paths")
    parser.add_argument(
        "--confirmed-bug-mapping",
        help="optional JSON or confirmed_bugs.md mapping used for summary context",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/residual-evaluation",
        help="directory for reports and summary.json",
    )
    parser.add_argument(
        "--include-all",
        action="store_true",
        help="emit CLOSED/PROTECTED audit records as OUT_OF_SCOPE reports",
    )
    args = parser.parse_args(argv)

    result = run_evaluation(
        args.source_file,
        args.output_dir,
        source_root=args.source_root,
        confirmed_bug_mapping=args.confirmed_bug_mapping,
        include_all=args.include_all,
    )
    print(json.dumps(result.summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
