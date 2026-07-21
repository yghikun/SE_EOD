"""Compare MOCC-SE discovery findings across source versions."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


MATRIX_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class VersionReportInput:
    version: str
    path: str
    report: dict[str, Any]


@dataclass(frozen=True)
class FunctionVersionRow:
    protocol_id: str
    operation_id: str
    function: str
    source_file: str
    version_counts: dict[str, dict[str, int]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "operation_id": self.operation_id,
            "function": self.function,
            "source_file": self.source_file,
            "version_counts": self.version_counts,
        }


@dataclass(frozen=True)
class FindingMatrixReport:
    reports: tuple[VersionReportInput, ...]
    summary: dict[str, Any]
    rows: tuple[FunctionVersionRow, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": MATRIX_SCHEMA_VERSION,
            "reports": [
                {
                    "version": item.version,
                    "path": item.path,
                    "source_version": item.report.get("source_version", ""),
                    "source_root": item.report.get("source_root", ""),
                }
                for item in self.reports
            ],
            "summary": self.summary,
            "rows": [row.to_dict() for row in self.rows],
        }


def load_version_report(spec: str) -> VersionReportInput:
    if "=" not in spec:
        raise ValueError("version report must use VERSION=PATH")
    version, path = spec.split("=", 1)
    if not version or not path:
        raise ValueError("version report must use VERSION=PATH")
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    return VersionReportInput(version, path, report)


def build_finding_matrix(reports: Iterable[VersionReportInput]) -> FindingMatrixReport:
    ordered_reports = tuple(reports)
    versions = [item.version for item in ordered_reports]
    rows_by_key: dict[tuple[str, str, str, str], dict[str, dict[str, int]]] = {}
    for version_report in ordered_reports:
        for analysis in version_report.report.get("analyses", ()):
            key = (
                str(analysis.get("protocol_id", "")),
                str(analysis.get("operation_id", "")),
                str(analysis.get("function", "")),
                _relative_source_file(analysis),
            )
            rows_by_key.setdefault(key, {})
            rows_by_key[key][version_report.version] = {
                "protocol_candidates": len(analysis.get("candidates", ())),
                "discovery_reviews": len(analysis.get("discovery_review", ())),
                "analysis_unknown": len(analysis.get("unknown", ())),
            }
    rows = tuple(
        FunctionVersionRow(
            protocol_id,
            operation_id,
            function,
            source_file,
            {
                version: counts_by_version.get(
                    version,
                    {
                        "protocol_candidates": 0,
                        "discovery_reviews": 0,
                        "analysis_unknown": 0,
                    },
                )
                for version in versions
            },
        )
        for (protocol_id, operation_id, function, source_file), counts_by_version in sorted(rows_by_key.items())
    )
    summary = {
        "versions": versions,
        "version_summaries": {
            item.version: item.report.get("summary", {}) for item in ordered_reports
        },
        "rows": len(rows),
        "candidate_occurrences_by_version": {
            version: sum(
                row.version_counts[version]["protocol_candidates"] for row in rows
            )
            for version in versions
        },
        "persistent_candidate_functions": [
            row.function
            for row in rows
            if all(
                row.version_counts[version]["protocol_candidates"] > 0
                for version in versions
            )
        ],
        "candidate_removed_functions": _candidate_removed_functions(rows, versions),
        "candidate_added_functions": _candidate_added_functions(rows, versions),
    }
    return FindingMatrixReport(ordered_reports, summary, rows)


def write_matrix_json(report: FindingMatrixReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_matrix_markdown(report: FindingMatrixReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# MOCC-SE Discovery Version Matrix",
        "",
        "This is a development comparison across source versions, not a frozen benchmark.",
        "",
        "Versions:",
        "",
    ]
    for item in report.reports:
        summary = item.report.get("summary", {})
        lines.append(
            f"- `{item.version}`: candidates={summary.get('protocol_candidate_occurrences', 0)}, "
            f"unknown={summary.get('analysis_unknown', 0)}, report=`{item.path}`"
        )
    lines.extend(["", "Function matrix:", ""])
    versions = report.summary["versions"]
    header = "| protocol | function | " + " | ".join(versions) + " |"
    separator = "|---|---|" + "|".join("---" for _ in versions) + "|"
    lines.extend([header, separator])
    for row in report.rows:
        cells = [
            row.protocol_id,
            row.function,
            *(
                _format_counts(row.version_counts[version])
                for version in versions
            ),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", "Development deltas:", ""])
    removed = report.summary["candidate_removed_functions"]
    added = report.summary["candidate_added_functions"]
    lines.append(
        "- removed/cleared candidate functions: "
        + (", ".join(f"`{item}`" for item in removed) if removed else "none")
    )
    lines.append(
        "- added candidate functions: "
        + (", ".join(f"`{item}`" for item in added) if added else "none")
    )
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare MOCC-SE discovery reports across source versions."
    )
    parser.add_argument("--report", action="append", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args(argv)

    report = build_finding_matrix(load_version_report(spec) for spec in args.report)
    write_matrix_json(report, args.out_json)
    write_matrix_markdown(report, args.out_md)
    print(f"versions={','.join(report.summary['versions'])}")
    print(f"rows={report.summary['rows']}")
    print(f"out_json={args.out_json}")
    print(f"out_md={args.out_md}")
    return 0


def _relative_source_file(analysis: dict[str, Any]) -> str:
    source_file = str(analysis.get("source_file", ""))
    marker = "/fs/"
    normalized = source_file.replace("\\", "/")
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    return normalized


def _candidate_removed_functions(rows: Iterable[FunctionVersionRow], versions: list[str]) -> list[str]:
    if len(versions) < 2:
        return []
    first, last = versions[0], versions[-1]
    return sorted(
        row.function
        for row in rows
        if row.version_counts[first]["protocol_candidates"] > 0
        and row.version_counts[last]["protocol_candidates"] == 0
    )


def _candidate_added_functions(rows: Iterable[FunctionVersionRow], versions: list[str]) -> list[str]:
    if len(versions) < 2:
        return []
    first, last = versions[0], versions[-1]
    return sorted(
        row.function
        for row in rows
        if row.version_counts[first]["protocol_candidates"] == 0
        and row.version_counts[last]["protocol_candidates"] > 0
    )


def _format_counts(counts: dict[str, int]) -> str:
    return (
        f"C{counts['protocol_candidates']}"
        f"/R{counts['discovery_reviews']}"
        f"/U{counts['analysis_unknown']}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
