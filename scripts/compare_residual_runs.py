"""Compare two residual batch outputs and summarize UNKNOWN resolution."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.unknown_triage import unknown_cause_category, unknown_cause_taxonomy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare all_reports.json files from two residual runs."
    )
    parser.add_argument("baseline", help="baseline output dir or all_reports.json")
    parser.add_argument("current", help="current output dir or all_reports.json")
    parser.add_argument(
        "--output",
        help="optional JSON path for the comparison matrix",
    )
    args = parser.parse_args(argv)

    matrix = compare_runs(_reports_path(args.baseline), _reports_path(args.current))
    text = json.dumps(matrix, indent=2, sort_keys=True)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def compare_runs(baseline_path: Path, current_path: Path) -> dict[str, object]:
    baseline = _load_reports(baseline_path)
    current = _load_reports(current_path)
    current_by_key = {_report_key(report): report for report in current}
    rows: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "to_candidate": 0,
            "to_unknown": 0,
            "to_out_of_scope_or_removed": 0,
        }
    )
    taxonomy_rows: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "to_candidate": 0,
            "to_unknown": 0,
            "to_out_of_scope_or_removed": 0,
        }
    )

    for report in baseline:
        if report.get("kind") != "METADATA_RESIDUAL_UNKNOWN":
            continue
        current_report = current_by_key.get(_report_key(report))
        bucket = _current_bucket(current_report)
        for cause in report.get("unknown_causes") or ("uncategorized",):
            reason = unknown_cause_category(str(cause))
            taxonomy = unknown_cause_taxonomy(str(cause))
            rows[reason][bucket] += 1
            taxonomy_rows[taxonomy][bucket] += 1

    return {
        "baseline": baseline_path.as_posix(),
        "current": current_path.as_posix(),
        "unknown_taxonomy_resolution": [
            {"taxonomy": taxonomy, **counts}
            for taxonomy, counts in sorted(taxonomy_rows.items())
        ],
        "unknown_resolution_matrix": [
            {"taxonomy": _taxonomy_for_reason(reason), "reason": reason, **counts}
            for reason, counts in sorted(rows.items())
        ],
    }


def _reports_path(value: str) -> Path:
    path = Path(value)
    if path.is_file():
        return path
    return path / "reports" / "all_reports.json"


def _load_reports(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _report_key(report: dict[str, Any]) -> tuple[object, ...]:
    residual_slice = report.get("residual_slice") or {}
    failure_site = residual_slice.get("failure_site") or {}
    return (
        report.get("function", ""),
        failure_site.get("file", ""),
        failure_site.get("line", ""),
        failure_site.get("expression", ""),
    )


def _current_bucket(report: dict[str, Any] | None) -> str:
    if report is None:
        return "to_out_of_scope_or_removed"
    kind = report.get("kind")
    if kind == "UNCLOSED_METADATA_RESIDUAL":
        return "to_candidate"
    if kind == "METADATA_RESIDUAL_UNKNOWN":
        return "to_unknown"
    return "to_out_of_scope_or_removed"


def _taxonomy_for_reason(reason: str) -> str:
    return unknown_cause_taxonomy(reason)


if __name__ == "__main__":
    raise SystemExit(main())
