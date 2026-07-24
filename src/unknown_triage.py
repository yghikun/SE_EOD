"""Triage helpers for METADATA_RESIDUAL_UNKNOWN reports."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


UNKNOWN_TRIAGE_SCHEMA_VERSION = 1


def unknown_cause_category(cause: str) -> str:
    """Return the stable category label used by evaluation summaries."""

    text = cause.strip()
    if text.startswith("unresolved metadata helper on error path:"):
        return "unresolved_metadata_helper_on_error_path"
    if text.startswith("indirect call on error path:"):
        return "indirect_call_on_error_path"
    if ": " in text:
        _, detail = text.split(": ", 1)
    else:
        detail = text
    category = detail.split(":", 1)[0].strip()
    return re.sub(r"[^A-Za-z0-9_]+", "_", category).strip("_") or "unknown"


def build_unknown_triage(
    reports: Iterable[dict[str, Any]],
    *,
    top_n: int = 10,
    examples_per_item: int = 3,
) -> dict[str, Any]:
    """Aggregate UNKNOWN reports by cause, detail, and containing function."""

    unknown_reports = [
        report
        for report in reports
        if report.get("kind") == "METADATA_RESIDUAL_UNKNOWN"
    ]
    category_counts: Counter[str] = Counter()
    detail_counts: dict[str, Counter[str]] = defaultdict(Counter)
    function_counts: dict[str, Counter[str]] = defaultdict(Counter)
    detail_examples: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    function_examples: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for report in unknown_reports:
        function = str(report.get("function", "unknown")) or "unknown"
        for cause in _unknown_causes(report):
            category = unknown_cause_category(cause)
            detail = _unknown_cause_detail(cause, category)
            example = _report_example(report, cause)

            category_counts[category] += 1
            detail_counts[category][detail] += 1
            function_counts[category][function] += 1
            _append_example(
                detail_examples[category][detail], example, examples_per_item
            )
            _append_example(
                function_examples[category][function], example, examples_per_item
            )

    categories = []
    for category, count in _rank_counts(category_counts, limit=None):
        categories.append(
            {
                "category": category,
                "count": count,
                "top_details": [
                    {
                        "detail": detail,
                        "count": detail_count,
                        "examples": detail_examples[category][detail],
                    }
                    for detail, detail_count in _rank_counts(
                        detail_counts[category],
                        limit=top_n,
                    )
                ],
                "top_functions": [
                    {
                        "function": function,
                        "count": function_count,
                        "examples": function_examples[category][function],
                    }
                    for function, function_count in _rank_counts(
                        function_counts[category],
                        limit=top_n,
                    )
                ],
            }
        )

    return {
        "schema_version": UNKNOWN_TRIAGE_SCHEMA_VERSION,
        "unknown_reports": len(unknown_reports),
        "unknown_cause_mentions": sum(category_counts.values()),
        "cause_categories": categories,
    }


def load_reports(path: str | Path) -> list[dict[str, Any]]:
    """Load reports from an all_reports.json path or an evaluation output dir."""

    reports_path = _resolve_reports_path(Path(path))
    payload = json.loads(reports_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"expected a JSON list in {reports_path}")
    return [item for item in payload if isinstance(item, dict)]


def write_unknown_triage(
    evaluation_output: str | Path,
    *,
    output_dir: str | Path | None = None,
    top_n: int = 10,
    examples_per_item: int = 3,
) -> dict[str, Path]:
    """Write unknown_triage.json and unknown_triage.md for an evaluation output."""

    input_path = Path(evaluation_output)
    reports_path = _resolve_reports_path(input_path)
    reports = load_reports(reports_path)
    triage = build_unknown_triage(
        reports,
        top_n=top_n,
        examples_per_item=examples_per_item,
    )
    triage["source_reports"] = reports_path.as_posix()

    destination = (
        Path(output_dir)
        if output_dir is not None
        else _default_output_dir(input_path, reports_path)
    )
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "unknown_triage.json"
    markdown_path = destination / "unknown_triage.md"
    json_path.write_text(
        json.dumps(triage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(triage_to_markdown(triage), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def triage_to_markdown(triage: dict[str, Any]) -> str:
    """Render an UNKNOWN triage summary as Markdown."""

    lines = [
        "# Metadata Residual UNKNOWN Triage",
        "",
        f"- Unknown reports: `{triage.get('unknown_reports', 0)}`",
        f"- Unknown cause mentions: `{triage.get('unknown_cause_mentions', 0)}`",
    ]
    source_reports = triage.get("source_reports")
    if source_reports:
        lines.append(f"- Source reports: `{source_reports}`")

    for category in triage.get("cause_categories", []):
        lines.extend(
            [
                "",
                f"## {category.get('category', 'unknown')} ({category.get('count', 0)})",
                "",
                "### Top Details",
                "",
                "| Detail | Count | Example |",
                "|---|---:|---|",
            ]
        )
        for item in category.get("top_details", []):
            lines.append(
                "| "
                f"{_md_escape(str(item.get('detail', 'unknown')))} | "
                f"{item.get('count', 0)} | "
                f"{_md_escape(_example_text(item.get('examples', [])))} |"
            )
        lines.extend(
            [
                "",
                "### Top Functions",
                "",
                "| Function | Count | Example |",
                "|---|---:|---|",
            ]
        )
        for item in category.get("top_functions", []):
            lines.append(
                "| "
                f"{_md_escape(str(item.get('function', 'unknown')))} | "
                f"{item.get('count', 0)} | "
                f"{_md_escape(_example_text(item.get('examples', [])))} |"
            )

    return "\n".join(lines).rstrip() + "\n"


def _resolve_reports_path(path: Path) -> Path:
    if path.is_dir():
        return path / "reports" / "all_reports.json"
    return path


def _default_output_dir(input_path: Path, reports_path: Path) -> Path:
    if input_path.is_dir():
        return input_path
    if reports_path.parent.name == "reports":
        return reports_path.parent.parent
    return reports_path.parent


def _unknown_causes(report: dict[str, Any]) -> tuple[str, ...]:
    causes = report.get("unknown_causes", ())
    if not isinstance(causes, list):
        return ()
    return tuple(str(cause) for cause in causes if str(cause).strip())


def _unknown_cause_detail(cause: str, category: str) -> str:
    text = cause.strip()
    if text.startswith("unresolved metadata helper on error path:"):
        return text.split(":", 1)[1].strip() or category
    if text.startswith("indirect call on error path:"):
        return text.split(":", 1)[1].strip() or category

    origin = ""
    detail = text
    if ": " in text:
        origin, detail = text.split(": ", 1)
    if ":" in detail:
        label, value = detail.split(":", 1)
        if unknown_cause_category(label) == category:
            return value.strip() or label.strip()
    if unknown_cause_category(detail) == category and origin:
        return origin.strip()
    return detail.strip() or category


def _report_example(report: dict[str, Any], cause: str) -> dict[str, Any]:
    residual_slice = report.get("residual_slice")
    if not isinstance(residual_slice, dict):
        residual_slice = {}
    return {
        "function": str(report.get("function", "unknown")) or "unknown",
        "cause": cause,
        "failure_site": _site_dict(residual_slice.get("failure_site")),
        "exit_site": _site_dict(residual_slice.get("exit_site")),
    }


def _site_dict(site: Any) -> dict[str, Any]:
    if not isinstance(site, dict):
        return {}
    return {
        "file": site.get("file", ""),
        "line": site.get("line", ""),
        "expression": site.get("expression", ""),
    }


def _append_example(
    examples: list[dict[str, Any]],
    example: dict[str, Any],
    limit: int,
) -> None:
    if limit <= 0 or len(examples) >= limit:
        return
    examples.append(example)


def _rank_counts(
    counts: Counter[str],
    *,
    limit: int | None,
) -> list[tuple[str, int]]:
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ranked if limit is None else ranked[:limit]


def _example_text(examples: Any) -> str:
    if not examples:
        return ""
    example = examples[0]
    if not isinstance(example, dict):
        return ""
    site = example.get("failure_site")
    if not isinstance(site, dict):
        site = {}
    location = _site_location(site)
    expression = _truncate(str(site.get("expression", "")), 90)
    function = example.get("function", "unknown")
    if expression:
        return f"{function} @ {location} `{expression}`"
    return f"{function} @ {location}"


def _site_location(site: dict[str, Any]) -> str:
    file = str(site.get("file", "") or "unknown")
    line = site.get("line", "")
    return f"{file}:{line}" if line else file


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _md_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
