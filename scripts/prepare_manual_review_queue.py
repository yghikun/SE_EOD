"""Prepare a review feedback queue from ranked SE-EOD candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_RANKED = "outputs/ext4/ranked_candidates.jsonl"
DEFAULT_TASKS = "outputs/ext4/llm_review_tasks.jsonl"
DEFAULT_QUEUE_JSONL = "outputs/ext4/manual_review_queue.jsonl"
DEFAULT_QUEUE_MD = "outputs/ext4/manual_review_queue.md"
DEFAULT_LABEL_TEMPLATE = "outputs/ext4/manual_review_labels_todo.jsonl"


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.exists():
        return []
    rows: list[dict[str, Any]] = []
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


def task_index(tasks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(task.get("task_id")): task
        for task in tasks
        if task.get("task_id")
    }


def review_candidates(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}

    def add(row: dict[str, Any], bucket: str) -> None:
        candidate_id = str(row.get("candidate_id", ""))
        if not candidate_id:
            return
        if candidate_id not in selected:
            selected[candidate_id] = dict(row)
            selected[candidate_id]["review_buckets"] = []
        buckets = selected[candidate_id]["review_buckets"]
        if bucket not in buckets:
            buckets.append(bucket)

    for row in rows[:limit]:
        add(row, "top_ranked")
    exception_rows = [row for row in rows if row.get("has_exception_hints")]
    for row in exception_rows[:limit]:
        add(row, "exception_hint")
    return list(selected.values())


def compact_candidate(
    row: dict[str, Any], task: dict[str, Any] | None, index: int
) -> dict[str, Any]:
    return {
        "queue_index": index,
        "review_buckets": row.get("review_buckets", []),
        "candidate_id": row.get("candidate_id", ""),
        "llm_task_id": row.get("llm_task_id", ""),
        "file": row.get("file", ""),
        "function": row.get("function", ""),
        "error_line": row.get("error_line", ""),
        "candidate_type": row.get("candidate_type", ""),
        "severity": row.get("severity", ""),
        "evidence_level": row.get("evidence_level", ""),
        "evidence_score": row.get("evidence_score", 0),
        "has_exception_hints": bool(row.get("has_exception_hints")),
        "matched_protocols": [
            evidence.get("protocol_id", "")
            for evidence in row.get("protocol_evidence", [])
            if isinstance(evidence, dict)
        ],
        "exception_hints": row.get("exception_hints", []),
        "wrapper_evidence": row.get("wrapper_evidence", []),
        "ownership_transfer_hints": row.get("ownership_transfer_hints", []),
        "score_explanation": row.get("score_explanation", []),
        "condition": row.get("condition", ""),
        "final_return_expr": row.get("final_return_expr", ""),
        "manual_label_template": {
            "candidate_id": row.get("candidate_id", ""),
            "verdict": "true_candidate | false_positive | uncertain",
            "confidence": "high | medium | low",
            "reason": "",
            "confirmed_exception": False,
            "confirmed_exception_type": None,
            "suggested_rule_update": None,
            "next_action": (
                "add_wrapper_summary | add_ownership_rule | "
                "runtime_validation | upstream_history_check | no_action"
            ),
            "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
            "review_source": (
                "codex_static_review | human_manual_review | upstream_confirmed"
            ),
            "reviewer": "manual",
            "notes": "",
        },
        "source_context": task.get("source_context", "") if task else "",
    }


def write_queue_jsonl(items: list[dict[str, Any]], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def write_label_template(items: list[dict[str, Any]], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "_comment": (
                        "Fill these TODO labels, then copy reviewed JSON objects "
                        "to outputs/ext4/manual_review_labels.jsonl."
                    )
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        for item in items:
            template = dict(item["manual_label_template"])
            template["_review_queue_index"] = item["queue_index"]
            template["_location"] = (
                f"{item['file']}::{item['function']}:{item['error_line']}"
            )
            fh.write(json.dumps(template, ensure_ascii=False) + "\n")


def write_queue_md(items: list[dict[str, Any]], path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SE-EOD Review Feedback Queue",
        "",
        "Review top-ranked candidates plus top exception-hint candidates.",
        "Copy completed labels into `outputs/ext4/manual_review_labels.jsonl`.",
        "",
        f"- total queue items: {len(items)}",
        "",
    ]
    for item in items:
        lines.extend(
            [
                f"## {item['queue_index']}. {item['candidate_id']}",
                "",
                (
                    f"- buckets: {', '.join(item['review_buckets'])}\n"
                    f"- score: {item['evidence_score']} {item['evidence_level']}\n"
                    f"- type/severity: {item['candidate_type']} / {item['severity']}\n"
                    f"- location: {item['file']}::{item['function']}:{item['error_line']}\n"
                    f"- exception hints: {item['has_exception_hints']}"
                ),
                "",
                f"- protocols: `{item['matched_protocols']}`",
                f"- score explanation: `{item['score_explanation']}`",
                f"- exception_hints: `{item['exception_hints']}`",
                "",
                "Label template:",
                "",
                "```json",
                json.dumps(item["manual_label_template"], ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        )
        context = item.get("source_context", "")
        if context:
            lines.extend(["Source context:", "", "```c", context, "```", ""])
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a review feedback queue from ranked candidates."
    )
    parser.add_argument("--ranked", default=DEFAULT_RANKED)
    parser.add_argument("--llm-tasks", default=DEFAULT_TASKS)
    parser.add_argument("--queue-jsonl-out", default=DEFAULT_QUEUE_JSONL)
    parser.add_argument("--queue-md-out", default=DEFAULT_QUEUE_MD)
    parser.add_argument("--label-template-out", default=DEFAULT_LABEL_TEMPLATE)
    parser.add_argument("--limit", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    ranked = load_jsonl(args.ranked)
    tasks = task_index(load_jsonl(args.llm_tasks))
    selected = review_candidates(ranked, max(1, args.limit))
    items = [
        compact_candidate(row, tasks.get(str(row.get("llm_task_id", ""))), index)
        for index, row in enumerate(selected, 1)
    ]
    write_queue_jsonl(items, args.queue_jsonl_out)
    write_queue_md(items, args.queue_md_out)
    write_label_template(items, args.label_template_out)
    print(f"ranked_in={len(ranked)}")
    print(f"queue_items={len(items)}")
    print(f"queue_jsonl_out={args.queue_jsonl_out}")
    print(f"queue_md_out={args.queue_md_out}")
    print(f"label_template_out={args.label_template_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
