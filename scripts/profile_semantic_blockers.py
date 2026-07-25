#!/usr/bin/env python3
"""Build the M36a measurement-only semantic blocker impact profile."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.candidate_review_oracle import load_jsonl
from src.semantic_blocker_impact import (
    DEFAULT_KNOWN_WITNESS_FUNCTIONS,
    build_semantic_blocker_impact,
    build_source_definition_index,
    write_semantic_blocker_impact,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("current", nargs="+", help="current evaluation output directories")
    parser.add_argument("--oracle", required=True, help="report-level oracle JSONL")
    parser.add_argument("--oracle-audit", required=True, help="current oracle audit JSON")
    parser.add_argument("--source-root", help="source snapshot root for exact body indexing")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--known-witness-function", action="append", default=[])
    args = parser.parse_args(argv)

    source_index = (
        build_source_definition_index(args.source_root)
        if args.source_root
        else None
    )
    known_functions = set(DEFAULT_KNOWN_WITNESS_FUNCTIONS)
    known_functions.update(args.known_witness_function)
    impact = build_semantic_blocker_impact(
        args.current,
        oracle_records=load_jsonl(args.oracle),
        oracle_audit=json.loads(Path(args.oracle_audit).read_text(encoding="utf-8")),
        source_index=source_index,
        known_witness_functions=known_functions,
    )
    outputs = write_semantic_blocker_impact(impact, args.output_dir)
    print(
        json.dumps(
            {
                "summary": impact["summary"],
                "outputs": {name: path.as_posix() for name, path in outputs.items()},
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
