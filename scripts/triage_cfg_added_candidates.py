"""Triage candidates introduced by CFG/path-sensitive resource tracking.

The report is intentionally conservative: it classifies newly surfaced
candidates into review families without suppressing them from the analyzer
output.  Candidate-count reduction is not used as a quality metric here.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.compare_experiment_v1_3 import load_jsonl, norm, stable_key
except ModuleNotFoundError:
    from compare_experiment_v1_3 import load_jsonl, norm, stable_key


def _static(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("static_evidence") or {}
    return value if isinstance(value, dict) else {}


def _missing_cleanup(row: dict[str, Any]) -> str:
    missing = _static(row).get("missing_cleanup_candidates") or []
    if isinstance(missing, list):
        return "; ".join(str(item) for item in missing)
    return str(missing)


def _held_resources(row: dict[str, Any]) -> str:
    held = _static(row).get("held_resources") or []
    if not isinstance(held, list):
        return ""
    parts: list[str] = []
    for resource in held:
        if not isinstance(resource, dict):
            continue
        var = norm(resource.get("var"))
        acquire = norm(resource.get("acquire_func"))
        acquire_line = norm(resource.get("acquire_line"))
        resource_type = norm(resource.get("resource_type"))
        parts.append(f"{var}:{resource_type}@{acquire}:{acquire_line}")
    return "; ".join(parts)


def _duplicate_missing_cleanup_id(row: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    for other in rows:
        if other is row:
            continue
        if other.get("candidate_type") != "missing_cleanup":
            continue
        if (
            norm(other.get("file")) == norm(row.get("file"))
            and norm(other.get("function")) == norm(row.get("function"))
            and norm(other.get("path_id")) == norm(row.get("path_id"))
            and norm(other.get("condition")) == norm(row.get("condition"))
            and norm(other.get("error_line")) == norm(row.get("error_line"))
        ):
            return norm(other.get("candidate_id"))
    return ""


def classify_added(row: dict[str, Any], after_rows: list[dict[str, Any]]) -> dict[str, str]:
    function = norm(row.get("function"))
    file_name = norm(row.get("file"))
    candidate_type = norm(row.get("candidate_type"))
    missing = _missing_cleanup(row)

    if (
        file_name == "fs/ext4/ialloc.c"
        and function == "__ext4_new_inode"
        and "ext4_journal_stop(handle)" in missing
    ):
        return {
            "family": "__ext4_new_inode.journal_handle_stop",
            "disposition": "retain_high_value_needs_validation",
            "review_priority": "high",
            "paper_note": (
                "CFG exposes a family of journal-handle paths acquired by "
                "__ext4_journal_start_sb() and returning through out: without "
                "a visible ext4_journal_stop(handle). Do not auto-suppress; "
                "validate ext4 current-handle semantics or reproduce dynamically."
            ),
        }

    if (
        file_name == "fs/ext4/extents.c"
        and function == "ext4_ext_shift_extents"
        and "kfree(path)" in missing
    ):
        return {
            "family": "ext4_ext_shift_extents.path_kfree_direct_return",
            "disposition": "retain_plausible_true_positive",
            "review_priority": "high",
            "paper_note": (
                "Direct error return bypasses the out: cleanup after "
                "ext4_find_extent() produced path; keep as a plausible "
                "resource-leak finding pending patch/dynamic validation."
            ),
        }

    if (
        file_name == "fs/ext4/orphan.c"
        and function == "ext4_init_orphan_info"
        and candidate_type == "partial_cleanup"
    ):
        duplicate_of = _duplicate_missing_cleanup_id(row, after_rows)
        suffix = f" Duplicate of {duplicate_of}." if duplicate_of else ""
        return {
            "family": "ext4_init_orphan_info.partial_cleanup_duplicate",
            "disposition": "duplicate_evidence_retain_missing_cleanup_primary",
            "review_priority": "low",
            "paper_note": (
                "Partial-cleanup view duplicates the same confirmed orphan-file "
                "buffer_head leak already emitted as missing_cleanup; keep the "
                "missing_cleanup row as the primary benchmark-positive ID."
                + suffix
            ),
        }

    if (
        file_name == "fs/ext4/xattr.c"
        and function == "ext4_expand_extra_isize_ea"
        and candidate_type == "stale_error_after_retry"
    ):
        return {
            "family": "ext4_expand_extra_isize_ea.stale_retry_contract",
            "disposition": "known_finding_path_id_renumbered",
            "review_priority": "medium",
            "paper_note": (
                "Known stale-error-after-retry contract finding; the CFG pass "
                "renumbered the path_id, so treat as stable-finding drift rather "
                "than a new semantic regression."
            ),
        }

    return {
        "family": "unclassified_cfg_added",
        "disposition": "manual_review_required",
        "review_priority": "medium",
        "paper_note": "No automatic triage family matched; inspect source before changing rules.",
    }


def summarize_row(row: dict[str, Any], after_rows: list[dict[str, Any]]) -> dict[str, Any]:
    classification = classify_added(row, after_rows)
    return {
        "candidate_id": row.get("candidate_id"),
        "stable_key": list(stable_key(row)),
        "file": row.get("file"),
        "function": row.get("function"),
        "path_id": row.get("path_id"),
        "candidate_type": row.get("candidate_type"),
        "error_line": row.get("error_line"),
        "condition": row.get("condition"),
        "final_return_expr": row.get("final_return_expr"),
        "severity": row.get("severity"),
        "evidence_level": row.get("evidence_level"),
        "evidence_score": row.get("evidence_score"),
        "missing_cleanup": _missing_cleanup(row),
        "held_resources": _held_resources(row),
        **classification,
    }


def build_report(before_rows: list[dict[str, Any]], after_rows: list[dict[str, Any]]) -> dict[str, Any]:
    before_index = {stable_key(row): row for row in before_rows}
    after_index = {stable_key(row): row for row in after_rows}
    added_rows = [after_index[key] for key in sorted(after_index.keys() - before_index.keys())]
    removed_rows = [before_index[key] for key in sorted(before_index.keys() - after_index.keys())]
    added = [summarize_row(row, after_rows) for row in added_rows]
    removed = [
        {
            "candidate_id": row.get("candidate_id"),
            "stable_key": list(stable_key(row)),
            "file": row.get("file"),
            "function": row.get("function"),
            "path_id": row.get("path_id"),
            "candidate_type": row.get("candidate_type"),
            "error_line": row.get("error_line"),
            "condition": row.get("condition"),
            "evidence_level": row.get("evidence_level"),
            "evidence_score": row.get("evidence_score"),
        }
        for row in removed_rows
    ]
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "before": len(before_rows),
            "after": len(after_rows),
            "retained": len(set(before_index) & set(after_index)),
            "added": len(added),
            "removed": len(removed),
            "added_by_family": dict(sorted(Counter(item["family"] for item in added).items())),
            "added_by_disposition": dict(sorted(Counter(item["disposition"] for item in added).items())),
        },
        "added": added,
        "removed": removed,
        "interpretation": (
            "The CFG/path-sensitive implementation is treated as surfacing new review evidence. "
            "Rows classified as duplicate or path-id drift are not automatically removed from raw "
            "candidate output; suppression should require benchmark-safe rule changes."
        ),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "candidate_id",
        "file",
        "function",
        "path_id",
        "candidate_type",
        "error_line",
        "condition",
        "severity",
        "evidence_level",
        "evidence_score",
        "family",
        "disposition",
        "review_priority",
        "missing_cleanup",
        "held_resources",
        "paper_note",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, report: dict[str, Any], before_path: Path, after_path: Path) -> None:
    summary = report["summary"]
    lines = [
        "# CFG-added Candidate Triage",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "Inputs:",
        "",
        f"- Before: `{before_path}`",
        f"- After: `{after_path}`",
        "",
        "## Summary",
        "",
        "| Before | After | Retained | Added | Removed |",
        "|---:|---:|---:|---:|---:|",
        f"| {summary['before']} | {summary['after']} | {summary['retained']} | {summary['added']} | {summary['removed']} |",
        "",
        "Added candidate families:",
        "",
    ]
    for family, count in summary["added_by_family"].items():
        lines.append(f"- `{family}`: {count}")
    lines.extend(
        [
            "",
            "Interpretation: CFG/path-sensitive analysis is surfacing review evidence; "
            "candidate-count increase is not treated as a precision loss, and duplicate/path-id "
            "drift rows are not suppressed from raw analyzer output.",
            "",
            "## Added Candidate Triage",
            "",
            "| Candidate | Location | Type | Evidence | Family | Disposition | Note |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for item in report["added"]:
        location = f"{item['file']}:{item['error_line']} `{item['function']}`"
        evidence = f"{item.get('evidence_level')} / {item.get('evidence_score')}"
        note = str(item["paper_note"]).replace("|", "\\|")
        lines.append(
            f"| `{item['candidate_id']}` | {location} | `{item['candidate_type']}` | "
            f"{evidence} | `{item['family']}` | `{item['disposition']}` | {note} |"
        )
    lines.extend(["", "## Removed Stable Keys", ""])
    if report["removed"]:
        lines.extend(
            [
                "| Candidate | Location | Type | Evidence |",
                "|---|---|---|---|",
            ]
        )
        for item in report["removed"]:
            location = f"{item['file']}:{item['error_line']} `{item['function']}`"
            evidence = f"{item.get('evidence_level')} / {item.get('evidence_score')}"
            lines.append(f"| `{item['candidate_id']}` | {location} | `{item['candidate_type']}` | {evidence} |")
    else:
        lines.append("No stable keys removed.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--json-out", required=True, type=Path)
    parser.add_argument("--csv-out", required=True, type=Path)
    parser.add_argument("--report-out", required=True, type=Path)
    args = parser.parse_args()

    before_rows = load_jsonl(args.before)
    after_rows = load_jsonl(args.after)
    report = build_report(before_rows, after_rows)

    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.csv_out.parent.mkdir(parents=True, exist_ok=True)
    args.report_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(args.csv_out, report["added"])
    write_markdown(args.report_out, report, args.before, args.after)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
