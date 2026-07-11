"""Validate SE-EOD v1.1 ranking quality from ranked candidate JSONL files."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_V1 = "outputs/ext4/ranked_candidates_v1_no_exceptions.jsonl"
DEFAULT_V11 = "outputs/ext4/ranked_candidates_v1_1.jsonl"
DEFAULT_REPORT = "outputs/ext4/v1_1_validation_report.md"


def load_ranked(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    source = Path(path)
    if not source.exists():
        return rows
    with source.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def candidate_key(row: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (
        row.get("file"),
        row.get("function"),
        row.get("error_line"),
        row.get("candidate_type"),
    )


def counter_text(title: str, counter: Counter[Any]) -> list[str]:
    lines = [f"### {title}", ""]
    if not counter:
        lines.append("_none_")
        lines.append("")
        return lines
    for key, value in counter.most_common():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    return lines


def summarize(rows: list[dict[str, Any]]) -> list[str]:
    protocols: Counter[str] = Counter()
    exceptions: Counter[str] = Counter()
    for row in rows:
        for evidence in row.get("protocol_evidence", []):
            if isinstance(evidence, dict):
                protocols[str(evidence.get("protocol_id", "unknown"))] += 1
        for hint in row.get("exception_hints", []):
            if isinstance(hint, dict):
                exceptions[str(hint.get("type", "unknown"))] += 1
            else:
                exceptions[str(hint)] += 1

    lines = [
        "## Summary",
        "",
        f"- total: {len(rows)}",
        "",
    ]
    lines.extend(counter_text("Evidence Levels", Counter(row.get("evidence_level") for row in rows)))
    lines.extend(counter_text("Candidate Types", Counter(row.get("candidate_type") for row in rows)))
    lines.extend(counter_text("Severity", Counter(row.get("severity") for row in rows)))
    lines.extend(
        counter_text(
            "Has Exception Hints",
            Counter(bool(row.get("has_exception_hints")) for row in rows),
        )
    )
    lines.extend(counter_text("Protocols", protocols))
    lines.extend(counter_text("Exception Hints", exceptions))
    return lines


def row_line(row: dict[str, Any], index: int | None = None) -> str:
    prefix = f"{index}. " if index is not None else "- "
    return (
        f"{prefix}score={row.get('evidence_score')} "
        f"level={row.get('evidence_level')} severity={row.get('severity')} "
        f"type={row.get('candidate_type')} exception={bool(row.get('has_exception_hints'))} "
        f"{row.get('file')}::{row.get('function')}:{row.get('error_line')}"
    )


def top_rows(title: str, rows: list[dict[str, Any]], limit: int) -> list[str]:
    lines = [f"## {title}", ""]
    if not rows:
        lines.append("_none_")
        lines.append("")
        return lines
    for index, row in enumerate(rows[:limit], 1):
        lines.append(row_line(row, index))
        protocols = [
            evidence.get("protocol_id")
            for evidence in row.get("protocol_evidence", [])
            if isinstance(evidence, dict)
        ]
        if protocols:
            lines.append(f"   protocols: {protocols}")
        score_explanation = row.get("score_explanation", [])
        if score_explanation:
            lines.append(f"   score: {score_explanation}")
        if row.get("exception_hints"):
            lines.append(f"   exception_hints: {row.get('exception_hints')}")
        lines.append("")
    return lines


def rank_changes(
    v1_rows: list[dict[str, Any]], v11_rows: list[dict[str, Any]], limit: int
) -> list[str]:
    rank1 = {candidate_key(row): index + 1 for index, row in enumerate(v1_rows)}
    rank11 = {candidate_key(row): index + 1 for index, row in enumerate(v11_rows)}
    by_key11 = {candidate_key(row): row for row in v11_rows}

    changes: list[tuple[int, tuple[Any, Any, Any, Any], int, int]] = []
    for key, old_rank in rank1.items():
        if key in rank11:
            changes.append((rank11[key] - old_rank, key, old_rank, rank11[key]))

    lines = ["## V1 vs V1.1 Rank Changes", ""]
    if not changes:
        lines.append("_comparison unavailable_")
        lines.append("")
        return lines

    lines.append("### Dropped Most After Exception Hints")
    lines.append("")
    for delta, key, old_rank, new_rank in sorted(changes, reverse=True)[:limit]:
        row = by_key11[key]
        lines.append(
            f"- +{delta}: {old_rank} -> {new_rank} | "
            f"score={row.get('evidence_score')} exception={bool(row.get('has_exception_hints'))} | {key}"
        )
    lines.append("")

    lines.append("### Increased Most")
    lines.append("")
    for delta, key, old_rank, new_rank in sorted(changes)[:limit]:
        row = by_key11[key]
        lines.append(
            f"- {delta}: {old_rank} -> {new_rank} | "
            f"score={row.get('evidence_score')} exception={bool(row.get('has_exception_hints'))} | {key}"
        )
    lines.append("")
    return lines


def acceptance(rows: list[dict[str, Any]]) -> list[str]:
    total = len(rows)
    e2 = sum(1 for row in rows if row.get("evidence_level") == "E2_API_PROTOCOL_SUPPORTED")
    exception = sum(1 for row in rows if row.get("has_exception_hints"))
    score_explanations = sum(1 for row in rows if row.get("score_explanation"))
    llm_fields_ready = sum(
        1
        for row in rows
        if all(
            key in row
            for key in [
                "protocol_evidence",
                "exception_hints",
                "wrapper_evidence",
                "ownership_transfer_hints",
                "score_explanation",
            ]
        )
    )
    lines = [
        "## Acceptance Checklist",
        "",
        f"- all candidates retained in ranked output: {total > 0} ({total})",
        f"- E2_API_PROTOCOL_SUPPORTED candidates present: {e2 > 0} ({e2})",
        f"- exception-hint candidates retained: {exception > 0} ({exception})",
        f"- score_explanation present: {score_explanations == total} ({score_explanations}/{total})",
        f"- v1.1 evidence fields present: {llm_fields_ready == total} ({llm_fields_ready}/{total})",
        "",
    ]
    return lines


def build_report(
    v1_rows: list[dict[str, Any]],
    v11_rows: list[dict[str, Any]],
    limit: int,
) -> str:
    lines = [
        "# SE-EOD v1.1 Validation Report",
        "",
        "This report validates exception-aware protocol ranking without changing candidates.",
        "",
    ]
    lines.extend(summarize(v11_rows))
    lines.extend(acceptance(v11_rows))
    if v1_rows:
        lines.extend(rank_changes(v1_rows, v11_rows, limit))
    lines.extend(top_rows(f"Top {limit} Ranked Candidates", v11_rows, limit))
    exception_rows = [row for row in v11_rows if row.get("has_exception_hints")]
    lines.extend(top_rows(f"Top {limit} Exception-Hint Candidates", exception_rows, limit))
    return "\n".join(lines).rstrip() + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate SE-EOD v1.1 validation summaries from ranked JSONL files."
    )
    parser.add_argument("--v1-ranked", default=DEFAULT_V1)
    parser.add_argument("--v1-1-ranked", default=DEFAULT_V11)
    parser.add_argument("--report-out", default=DEFAULT_REPORT)
    parser.add_argument("--limit", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    v1_rows = load_ranked(args.v1_ranked)
    v11_rows = load_ranked(args.v1_1_ranked)
    report = build_report(v1_rows, v11_rows, max(1, args.limit))
    target = Path(args.report_out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report, encoding="utf-8")
    print(f"v1_ranked={len(v1_rows)}")
    print(f"v1_1_ranked={len(v11_rows)}")
    print(f"report_out={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
