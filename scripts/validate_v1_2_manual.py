"""Validate SE-EOD v1.2 review-feedback ranking."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.manual_review import review_source_for


DEFAULT_BASELINE = "outputs/ranked_candidates_v1_2_no_manual.jsonl"
DEFAULT_FEEDBACK = "outputs/ranked_candidates.jsonl"
DEFAULT_LABELS = "outputs/manual_review_labels.jsonl"
DEFAULT_REPORT = "outputs/v1_2_review_feedback_report.md"


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
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


def candidate_id(row: dict[str, Any]) -> str:
    return str(row.get("candidate_id", ""))


def manual_review(row: dict[str, Any]) -> dict[str, Any]:
    review = row.get("manual_review")
    return review if isinstance(review, dict) else {}


def verdict(row: dict[str, Any]) -> str:
    return str(manual_review(row).get("verdict") or "unlabeled")


def source_of_review(review: dict[str, Any]) -> str:
    return review_source_for(review.get("review_source"), review.get("reviewer"))


def top_verdict_counter(rows: list[dict[str, Any]], limit: int) -> Counter[str]:
    return Counter(verdict(row) for row in rows[:limit])


def counter_lines(title: str, counter: Counter[Any]) -> list[str]:
    lines = [f"## {title}", ""]
    if not counter:
        lines.extend(["_none_", ""])
        return lines
    for key, value in counter.most_common():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    return lines


def rank_index(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {candidate_id(row): index + 1 for index, row in enumerate(rows)}


def average_rank_change(
    baseline_rows: list[dict[str, Any]],
    feedback_rows: list[dict[str, Any]],
) -> list[str]:
    before = rank_index(baseline_rows)
    after = rank_index(feedback_rows)
    by_id = {candidate_id(row): row for row in feedback_rows}
    grouped: dict[str, list[tuple[int, int, int]]] = {}
    for cid, new_rank in after.items():
        row = by_id[cid]
        review = manual_review(row)
        if not review:
            continue
        old_rank = before.get(cid)
        if not old_rank:
            continue
        grouped.setdefault(str(review.get("verdict", "unknown")), []).append(
            (old_rank, new_rank, new_rank - old_rank)
        )

    lines = ["## Average Rank Change", ""]
    if not grouped:
        lines.extend(["_no labeled candidates found in both rankings_", ""])
        return lines
    for key in sorted(grouped):
        values = grouped[key]
        lines.append(
            f"- `{key}`: count={len(values)}, "
            f"avg_before={mean(v[0] for v in values):.1f}, "
            f"avg_after={mean(v[1] for v in values):.1f}, "
            f"avg_delta={mean(v[2] for v in values):+.1f}"
        )
    lines.append("")
    return lines


def top_rows(
    title: str,
    rows: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
    limit: int,
) -> list[str]:
    before = rank_index(baseline_rows)
    lines = [f"## {title}", ""]
    for index, row in enumerate(rows[:limit], 1):
        review = manual_review(row)
        base_rank = before.get(candidate_id(row), "?")
        lines.append(
            f"{index}. score={row.get('evidence_score')} "
            f"base_rank={base_rank} adj={row.get('manual_score_adjustment', 0)} "
            f"review={review.get('verdict', 'unlabeled')} "
            f"source={source_of_review(review) if review else 'unlabeled'} "
            f"level={row.get('evidence_level')} severity={row.get('severity')} "
            f"type={row.get('candidate_type')} "
            f"{row.get('file')}::{row.get('function')}:{row.get('error_line')}"
        )
    lines.append("")
    return lines


def rank_changes(
    baseline_rows: list[dict[str, Any]],
    feedback_rows: list[dict[str, Any]],
    limit: int,
) -> list[str]:
    before = rank_index(baseline_rows)
    after = rank_index(feedback_rows)
    by_id = {candidate_id(row): row for row in feedback_rows}
    changes: list[tuple[int, str]] = []
    for cid, old_rank in before.items():
        if cid in after:
            changes.append((after[cid] - old_rank, cid))

    lines = ["## Largest Rank Changes", "", "### Demoted", ""]
    for delta, cid in sorted(changes, reverse=True)[:limit]:
        row = by_id[cid]
        review = manual_review(row)
        lines.append(
            f"- +{delta}: {before[cid]} -> {after[cid]} "
            f"review={review.get('verdict', 'unlabeled')} "
            f"source={source_of_review(review) if review else 'unlabeled'} "
            f"adj={row.get('manual_score_adjustment', 0)} "
            f"{row.get('file')}::{row.get('function')}:{row.get('error_line')}"
        )
    lines.extend(["", "### Promoted", ""])
    for delta, cid in sorted(changes)[:limit]:
        row = by_id[cid]
        review = manual_review(row)
        lines.append(
            f"- {delta}: {before[cid]} -> {after[cid]} "
            f"review={review.get('verdict', 'unlabeled')} "
            f"source={source_of_review(review) if review else 'unlabeled'} "
            f"adj={row.get('manual_score_adjustment', 0)} "
            f"{row.get('file')}::{row.get('function')}:{row.get('error_line')}"
        )
    lines.append("")
    return lines


def manual_label_counters(
    rows: list[dict[str, Any]], labels: list[dict[str, Any]]
) -> dict[str, Counter[Any]]:
    reviews = [manual_review(row) for row in rows if manual_review(row)]
    return {
        "Review Verdicts": Counter(review.get("verdict") for review in reviews),
        "Review Confidence": Counter(review.get("confidence") for review in reviews),
        "Labels By Reviewer": Counter(
            label.get("reviewer") for label in labels if label.get("candidate_id")
        ),
        "Labels By Review Source": Counter(
            review_source_for(label.get("review_source"), label.get("reviewer"))
            for label in labels
            if label.get("candidate_id")
        ),
        "Applied By Review Source": Counter(
            source_of_review(review) for review in reviews
        ),
        "Confirmed Exception Types": Counter(
            review.get("confirmed_exception_type") for review in reviews
        ),
        "Next Actions": Counter(review.get("next_action") for review in reviews),
        "Validation Hints": Counter(review.get("validation_hint") for review in reviews),
    }


def score_adjustment_by_source(rows: list[dict[str, Any]]) -> list[str]:
    grouped: dict[str, list[int]] = {}
    for row in rows:
        review = manual_review(row)
        if not review:
            continue
        source = source_of_review(review)
        try:
            adjustment = int(row.get("manual_score_adjustment", 0))
        except (TypeError, ValueError):
            adjustment = 0
        grouped.setdefault(source, []).append(adjustment)

    lines = ["## Score Adjustment By Source", ""]
    if not grouped:
        lines.extend(["_none_", ""])
        return lines
    for source in sorted(grouped):
        values = grouped[source]
        lines.append(
            f"- `{source}`: count={len(values)}, sum={sum(values):+d}, "
            f"avg={mean(values):+.1f}, min={min(values):+d}, max={max(values):+d}"
        )
    lines.append("")
    return lines


def build_report(
    baseline_rows: list[dict[str, Any]],
    feedback_rows: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    limit: int,
) -> str:
    feedback_applied = [row for row in feedback_rows if manual_review(row)]
    lines = [
        "# SE-EOD Review Feedback Report",
        "",
        (
            "This report compares SE-EOD ranking before and after "
            "source-aware review-feedback scoring. Review labels are triage "
            "signals, not candidate deletion rules or upstream confirmation."
        ),
        "",
        "## Summary",
        "",
        f"- baseline_candidates: {len(baseline_rows)}",
        f"- feedback_candidates: {len(feedback_rows)}",
        f"- review_label_records: {sum(1 for item in labels if item.get('candidate_id'))}",
        f"- review_feedback_applied: {len(feedback_applied)}",
        f"- E2_API_PROTOCOL_SUPPORTED: {sum(1 for row in feedback_rows if row.get('evidence_level') == 'E2_API_PROTOCOL_SUPPORTED')}",
        f"- exception_hints: {sum(1 for row in feedback_rows if row.get('has_exception_hints'))}",
        "",
        "## Top-N Verdict Mix",
        "",
        f"- baseline top {limit}: {dict(top_verdict_counter(baseline_rows, limit))}",
        f"- review-feedback top {limit}: {dict(top_verdict_counter(feedback_rows, limit))}",
        "",
    ]
    for title, counter in manual_label_counters(feedback_rows, labels).items():
        lines.extend(counter_lines(title, counter))
    lines.extend(score_adjustment_by_source(feedback_rows))
    lines.extend(average_rank_change(baseline_rows, feedback_rows))
    lines.extend(
        top_rows(
            f"Top {limit} After Review Feedback",
            feedback_rows,
            baseline_rows,
            limit,
        )
    )
    lines.extend(rank_changes(baseline_rows, feedback_rows, limit))
    return "\n".join(lines).rstrip() + "\n"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a SE-EOD source-aware review-feedback validation report."
    )
    parser.add_argument("--baseline-ranked", default=DEFAULT_BASELINE)
    parser.add_argument(
        "--feedback-ranked",
        "--manual-ranked",
        dest="feedback_ranked",
        default=DEFAULT_FEEDBACK,
    )
    parser.add_argument(
        "--review-labels",
        "--manual-labels",
        dest="review_labels",
        default=DEFAULT_LABELS,
    )
    parser.add_argument("--report-out", default=DEFAULT_REPORT)
    parser.add_argument("--limit", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    baseline_rows = load_jsonl(args.baseline_ranked)
    feedback_rows = load_jsonl(args.feedback_ranked)
    labels = load_jsonl(args.review_labels)
    report = build_report(baseline_rows, feedback_rows, labels, max(1, args.limit))
    target = Path(args.report_out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(report, encoding="utf-8")
    print(f"baseline_ranked={len(baseline_rows)}")
    print(f"feedback_ranked={len(feedback_rows)}")
    print(f"review_labels={sum(1 for item in labels if item.get('candidate_id'))}")
    print(f"report_out={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
