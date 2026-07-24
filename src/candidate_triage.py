"""Triage helpers for filesystem metadata residual candidate reports."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .unknown_triage import load_reports


CANDIDATE_TRIAGE_SCHEMA_VERSION = 1


def build_candidate_triage(
    reports: list[dict[str, Any]],
    *,
    top_n: int = 10,
    examples_per_item: int = 3,
) -> dict[str, Any]:
    """Aggregate candidate reports by function and residual identity."""

    candidates = [
        report
        for report in reports
        if report.get("kind") == "UNCLOSED_METADATA_RESIDUAL"
    ]
    function_counts: Counter[str] = Counter()
    plane_delta_counts: Counter[str] = Counter()
    identity_counts: Counter[str] = Counter()
    function_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    plane_delta_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    identity_examples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    residual_effects = 0

    for report in candidates:
        function = str(report.get("function", "unknown")) or "unknown"
        function_counts[function] += 1
        report_example = _report_example(report)
        _append_example(function_examples[function], report_example, examples_per_item)

        for effect in _residual_effects(report):
            residual_effects += 1
            plane_delta = _plane_delta(effect)
            identity = _identity(effect)
            effect_example = _report_example(report, effect)

            plane_delta_counts[plane_delta] += 1
            identity_counts[identity] += 1
            _append_example(
                plane_delta_examples[plane_delta],
                effect_example,
                examples_per_item,
            )
            _append_example(
                identity_examples[identity],
                effect_example,
                examples_per_item,
            )

    return {
        "schema_version": CANDIDATE_TRIAGE_SCHEMA_VERSION,
        "candidate_reports": len(candidates),
        "residual_effects": residual_effects,
        "top_functions": [
            {
                "function": function,
                "count": count,
                "examples": function_examples[function],
            }
            for function, count in _rank_counts(function_counts, top_n)
        ],
        "top_plane_deltas": [
            {
                "plane_delta": plane_delta,
                "count": count,
                "examples": plane_delta_examples[plane_delta],
            }
            for plane_delta, count in _rank_counts(plane_delta_counts, top_n)
        ],
        "top_residual_identities": [
            {
                "identity": identity,
                "count": count,
                "examples": identity_examples[identity],
            }
            for identity, count in _rank_counts(identity_counts, top_n)
        ],
    }


def write_candidate_triage(
    evaluation_output: str | Path,
    *,
    output_dir: str | Path | None = None,
    top_n: int = 10,
    examples_per_item: int = 3,
) -> dict[str, Path]:
    """Write candidate_triage.json and candidate_triage.md."""

    input_path = Path(evaluation_output)
    reports = load_reports(input_path)
    triage = build_candidate_triage(
        reports,
        top_n=top_n,
        examples_per_item=examples_per_item,
    )
    triage["source_reports"] = _source_reports_path(input_path).as_posix()
    destination = (
        Path(output_dir)
        if output_dir is not None
        else _default_output_dir(input_path)
    )
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "candidate_triage.json"
    markdown_path = destination / "candidate_triage.md"
    json_path.write_text(
        json.dumps(triage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(triage_to_markdown(triage), encoding="utf-8")
    return {"json": json_path, "markdown": markdown_path}


def triage_to_markdown(triage: dict[str, Any]) -> str:
    lines = [
        "# Filesystem Metadata Residual Candidate Triage",
        "",
        f"- Candidate reports: `{triage.get('candidate_reports', 0)}`",
        f"- Residual effects: `{triage.get('residual_effects', 0)}`",
    ]
    source_reports = triage.get("source_reports")
    if source_reports:
        lines.append(f"- Source reports: `{source_reports}`")

    _append_table(
        lines,
        title="Top Functions",
        key_header="Function",
        key_name="function",
        rows=triage.get("top_functions", []),
    )
    _append_table(
        lines,
        title="Top Plane/Deltas",
        key_header="Plane/Delta",
        key_name="plane_delta",
        rows=triage.get("top_plane_deltas", []),
    )
    _append_table(
        lines,
        title="Top Residual Identities",
        key_header="Identity",
        key_name="identity",
        rows=triage.get("top_residual_identities", []),
    )
    return "\n".join(lines).rstrip() + "\n"


def _append_table(
    lines: list[str],
    *,
    title: str,
    key_header: str,
    key_name: str,
    rows: Any,
) -> None:
    lines.extend(
        [
            "",
            f"## {title}",
            "",
            f"| {key_header} | Count | Example |",
            "|---|---:|---|",
        ]
    )
    for row in rows:
        lines.append(
            "| "
            f"{_md_escape(str(row.get(key_name, 'unknown')))} | "
            f"{row.get('count', 0)} | "
            f"{_md_escape(_example_text(row.get('examples', [])))} |"
        )


def _residual_effects(report: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    residual_slice = report.get("residual_slice")
    if not isinstance(residual_slice, dict):
        return ()
    residuals = residual_slice.get("residuals", ())
    if not isinstance(residuals, list):
        return ()
    return tuple(item for item in residuals if isinstance(item, dict))


def _plane_delta(effect: dict[str, Any]) -> str:
    return f"{effect.get('plane', 'UNKNOWN')} {effect.get('delta', 'UNKNOWN')}"


def _identity(effect: dict[str, Any]) -> str:
    return (
        f"{effect.get('plane', 'UNKNOWN')} "
        f"{effect.get('delta', 'UNKNOWN')} "
        f"{effect.get('root', 'unknown')}.{effect.get('key', 'unknown')}"
    )


def _report_example(
    report: dict[str, Any],
    effect: dict[str, Any] | None = None,
) -> dict[str, Any]:
    residual_slice = report.get("residual_slice")
    if not isinstance(residual_slice, dict):
        residual_slice = {}
    return {
        "function": str(report.get("function", "unknown")) or "unknown",
        "failure_site": _site_dict(residual_slice.get("failure_site")),
        "exit_site": _site_dict(residual_slice.get("exit_site")),
        "effect": effect or {},
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


def _rank_counts(counts: Counter[str], limit: int) -> list[tuple[str, int]]:
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]


def _source_reports_path(path: Path) -> Path:
    if path.is_dir():
        return path / "reports" / "all_reports.json"
    return path


def _default_output_dir(path: Path) -> Path:
    if path.is_dir():
        return path
    if path.parent.name == "reports":
        return path.parent.parent
    return path.parent


def _example_text(examples: Any) -> str:
    if not examples:
        return ""
    example = examples[0]
    if not isinstance(example, dict):
        return ""
    site = example.get("failure_site")
    if not isinstance(site, dict):
        site = {}
    function = example.get("function", "unknown")
    location = _site_location(site)
    expression = _truncate(str(site.get("expression", "")), 90)
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
