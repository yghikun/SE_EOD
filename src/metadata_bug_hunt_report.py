"""Build a MOCC-SE development bug-hunt report from M9 artifacts."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


BUG_HUNT_REPORT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BugHuntReport:
    reviewed_queue_source: str
    triage_source: str
    matrix_source: str
    repair_evidence_source: str
    summary: dict[str, Any]
    priority_queues: dict[str, list[dict[str, Any]]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": BUG_HUNT_REPORT_SCHEMA_VERSION,
            "reviewed_queue_source": self.reviewed_queue_source,
            "triage_source": self.triage_source,
            "matrix_source": self.matrix_source,
            "repair_evidence_source": self.repair_evidence_source,
            "summary": self.summary,
            "priority_queues": self.priority_queues,
        }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_bug_hunt_report(
    reviewed_queue: dict[str, Any],
    triage: dict[str, Any],
    matrix: dict[str, Any],
    repair: dict[str, Any],
    *,
    reviewed_queue_source: str = "",
    triage_source: str = "",
    matrix_source: str = "",
    repair_evidence_source: str = "",
) -> BugHuntReport:
    repair_items = [item for item in repair.get("items", ()) if item.get("repair_evidence")]
    persistent = set(matrix.get("summary", {}).get("persistent_candidate_functions", ()))
    removed = set(matrix.get("summary", {}).get("candidate_removed_functions", ()))
    added = set(matrix.get("summary", {}).get("candidate_added_functions", ()))
    triage_items = list(triage.get("items", ()))
    repair_functions = sorted({str(item.get("function", "")) for item in repair_items})
    persistent_items = [
        _item_summary(item)
        for item in triage_items
        if str(item.get("function", "")) in persistent
    ]
    repair_queue = [_item_summary(item) for item in repair_items]
    added_queue = [
        {
            "function": row.get("function", ""),
            "protocol_id": row.get("protocol_id", ""),
            "operation_id": row.get("operation_id", ""),
            "source_file": row.get("source_file", ""),
            "version_counts": row.get("version_counts", {}),
        }
        for row in matrix.get("rows", ())
        if str(row.get("function", "")) in added
    ]
    removed_queue = [
        {
            "function": row.get("function", ""),
            "protocol_id": row.get("protocol_id", ""),
            "operation_id": row.get("operation_id", ""),
            "source_file": row.get("source_file", ""),
            "version_counts": row.get("version_counts", {}),
        }
        for row in matrix.get("rows", ())
        if str(row.get("function", "")) in removed
    ]
    summary = {
        "review_items": reviewed_queue.get("summary", {}).get("review_items", 0),
        "triage_items": triage.get("summary", {}).get("triage_items", 0),
        "candidate_survives_initial_review": triage.get("summary", {})
        .get("by_verdict", {})
        .get("candidate_survives_initial_review", 0),
        "items_with_repair_evidence": len(repair_items),
        "repair_evidence_functions": repair_functions,
        "persistent_candidate_functions": sorted(persistent),
        "candidate_removed_functions": sorted(removed),
        "candidate_added_functions": sorted(added),
        "version_candidate_occurrences": matrix.get("summary", {}).get(
            "candidate_occurrences_by_version", {}
        ),
        "interpretation": (
            "development bug-hunt report only; not a frozen benchmark, "
            "not precision/recall evidence, and not a confirmed-bug list"
        ),
    }
    return BugHuntReport(
        reviewed_queue_source,
        triage_source,
        matrix_source,
        repair_evidence_source,
        summary,
        {
            "repair_evidence_first": repair_queue,
            "persistent_candidates_next": persistent_items,
            "removed_or_cleared_functions": removed_queue,
            "added_functions_to_inspect": added_queue,
        },
    )


def write_bug_hunt_json(report: BugHuntReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_bug_hunt_markdown(report: BugHuntReport, path: str | Path) -> None:
    target = Path(path)
    lines = [
        "# MOCC-SE Development Bug-Hunt Report",
        "",
        "This report summarizes development findings only. It is not a frozen benchmark, a precision/recall table, or a confirmed-bug list.",
        "",
        "Inputs:",
        "",
        f"- reviewed queue: `{report.reviewed_queue_source}`",
        f"- triage: `{report.triage_source}`",
        f"- matrix: `{report.matrix_source}`",
        f"- repair evidence: `{report.repair_evidence_source}`",
        "",
        "Summary:",
        "",
        f"- review items: {report.summary['review_items']}",
        f"- candidates surviving initial source review: {report.summary['candidate_survives_initial_review']}",
        f"- items with repair evidence: {report.summary['items_with_repair_evidence']}",
        f"- version candidate occurrences: `{report.summary['version_candidate_occurrences']}`",
        "",
        "Priority 1: repair-evidence-backed candidates",
        "",
    ]
    if report.priority_queues["repair_evidence_first"]:
        for item in report.priority_queues["repair_evidence_first"]:
            lines.append(
                f"- `{item['function']}` / `{item['violation_type']}` / `{item['review_id']}`"
            )
    else:
        lines.append("- none")
    lines.extend(["", "Priority 2: persistent candidates needing patch/source context", ""])
    for item in report.priority_queues["persistent_candidates_next"]:
        lines.append(f"- `{item['function']}` / `{item['violation_type']}`")
    lines.extend(["", "Priority 3: removed/cleared functions to mine for repair patterns", ""])
    for item in report.priority_queues["removed_or_cleared_functions"]:
        lines.append(f"- `{item['function']}` / `{item['protocol_id']}`")
    lines.extend(["", "Priority 4: added functions to inspect for expanded operation context", ""])
    for item in report.priority_queues["added_functions_to_inspect"]:
        lines.append(f"- `{item['function']}` / `{item['protocol_id']}`")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a MOCC-SE development bug-hunt report."
    )
    parser.add_argument("--reviewed-queue", required=True)
    parser.add_argument("--triage", required=True)
    parser.add_argument("--matrix", required=True)
    parser.add_argument("--repair-evidence", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args(argv)

    report = build_bug_hunt_report(
        load_json(args.reviewed_queue),
        load_json(args.triage),
        load_json(args.matrix),
        load_json(args.repair_evidence),
        reviewed_queue_source=args.reviewed_queue,
        triage_source=args.triage,
        matrix_source=args.matrix,
        repair_evidence_source=args.repair_evidence,
    )
    write_bug_hunt_json(report, args.out_json)
    write_bug_hunt_markdown(report, args.out_md)
    print(f"review_items={report.summary['review_items']}")
    print(f"items_with_repair_evidence={report.summary['items_with_repair_evidence']}")
    print(f"out_json={args.out_json}")
    print(f"out_md={args.out_md}")
    return 0


def _item_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "review_id": item.get("review_id", ""),
        "protocol_id": item.get("protocol_id", ""),
        "operation_id": item.get("operation_id", ""),
        "function": item.get("function", ""),
        "source_file": item.get("source_file", ""),
        "violation_type": item.get("violation_type", ""),
        "triage_verdict": (item.get("triage") or {}).get("verdict", ""),
        "repair_evidence": item.get("repair_evidence", []),
    }


if __name__ == "__main__":
    raise SystemExit(main())
