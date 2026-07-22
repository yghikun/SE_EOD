"""Prepare MOCC-SE discovery candidates for source-level finding review."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable


REVIEW_QUEUE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ReviewSourceContext:
    source_file: str
    start_line: int
    end_line: int
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "snippet": self.snippet,
        }


@dataclass(frozen=True)
class ReviewQueueItem:
    review_id: str
    classification: str
    protocol_id: str
    operation_id: str
    function: str
    source_file: str
    source_version: str
    violation_type: str
    exit_kind: str
    exit_id: str
    static_certainty: str
    family_fingerprint: str
    occurrence_fingerprint: str
    review_focus: tuple[str, ...]
    missing_summary_hints: tuple[str, ...]
    unresolved_failures: tuple[dict[str, Any], ...]
    open_effects: tuple[dict[str, Any], ...]
    accounting_state: tuple[dict[str, Any], ...]
    witness: tuple[dict[str, Any], ...]
    source_context: tuple[ReviewSourceContext, ...]
    source_review: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "review_id": self.review_id,
            "classification": self.classification,
            "protocol_id": self.protocol_id,
            "operation_id": self.operation_id,
            "function": self.function,
            "source_file": self.source_file,
            "source_version": self.source_version,
            "violation_type": self.violation_type,
            "exit_kind": self.exit_kind,
            "exit_id": self.exit_id,
            "static_certainty": self.static_certainty,
            "family_fingerprint": self.family_fingerprint,
            "occurrence_fingerprint": self.occurrence_fingerprint,
            "review_focus": list(self.review_focus),
            "missing_summary_hints": list(self.missing_summary_hints),
            "unresolved_failures": list(self.unresolved_failures),
            "open_effects": list(self.open_effects),
            "accounting_state": list(self.accounting_state),
            "witness": list(self.witness),
            "source_context": [item.to_dict() for item in self.source_context],
        }
        if self.source_review is not None:
            payload["source_review"] = self.source_review
        else:
            payload["review_template"] = {
                "verdict": "true_candidate | false_positive | uncertain",
                "confidence": "high | medium | low",
                "root_cause": "",
                "needs_protocol_change": False,
                "needs_summary_change": False,
                "needs_frontend_change": False,
                "suggested_change": "",
                "notes": "",
            }
        return payload


@dataclass(frozen=True)
class ReviewQueueReport:
    source_report: str
    source_root: str
    source_version: str
    summary: dict[str, Any]
    items: tuple[ReviewQueueItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REVIEW_QUEUE_SCHEMA_VERSION,
            "source_report": self.source_report,
            "source_root": self.source_root,
            "source_version": self.source_version,
            "summary": self.summary,
            "items": [item.to_dict() for item in self.items],
        }


def build_review_queue(
    discovery_report: dict[str, Any],
    *,
    source_report: str = "",
    source_root: str | Path | None = None,
    context_lines: int = 4,
    include_discovery_review: bool = False,
) -> ReviewQueueReport:
    root = Path(source_root or discovery_report.get("source_root", "")).resolve()
    items: list[ReviewQueueItem] = []
    if include_discovery_review:
        items.extend(
            _review_item(
                {},
                record,
                root,
                context_lines=max(0, context_lines),
            )
            for record in discovery_report.get("fresh_review_queue", [])
        )
    for analysis in discovery_report.get("analyses", []):
        records = list(analysis.get("candidates", []))
        if include_discovery_review:
            records.extend(analysis.get("discovery_review", []))
        for record in records:
            items.append(
                _review_item(
                    analysis,
                    record,
                    root,
                    context_lines=max(0, context_lines),
                )
            )
    items = sorted(
        items,
        key=lambda item: (
            item.source_file,
            item.function,
            item.violation_type,
            item.occurrence_fingerprint,
        ),
    )
    summary = {
        "review_items": len(items),
        "protocol_candidates": sum(
            1 for item in items if item.classification == "PROTOCOL_CANDIDATE"
        ),
        "discovery_reviews": sum(
            1 for item in items if item.classification == "DISCOVERY_REVIEW"
        ),
        "by_protocol": _counts(item.protocol_id for item in items),
        "by_violation_type": _counts(item.violation_type for item in items),
        "source_discovery_summary": discovery_report.get("summary", {}),
    }
    return ReviewQueueReport(
        source_report,
        root.as_posix(),
        str(discovery_report.get("source_version", "")),
        summary,
        tuple(items),
    )


def apply_source_review_annotations(
    report: ReviewQueueReport,
    annotation_document: dict[str, Any],
) -> ReviewQueueReport:
    """Attach development source-review notes to matching queue items.

    Annotation records use a conservative match object.  Empty or omitted match
    fields are wildcards, so a single source-review note can intentionally cover
    a family such as all ext4 replay failures in one function.  The output keeps
    unmatched and conflicting annotations in the summary instead of silently
    treating them as benchmark labels.
    """

    annotations = tuple(annotation_document.get("annotations", ()))
    attached: list[ReviewQueueItem] = []
    matched_by_annotation: dict[int, list[str]] = {index: [] for index in range(len(annotations))}
    conflicts: list[dict[str, Any]] = []
    for item in report.items:
        matches = [
            (index, annotation)
            for index, annotation in enumerate(annotations)
            if _annotation_matches(item, annotation.get("match", {}))
        ]
        if len(matches) > 1:
            conflicts.append(
                {
                    "review_id": item.review_id,
                    "annotation_indices": [index for index, _ in matches],
                }
            )
            attached.append(item)
            continue
        if not matches:
            attached.append(item)
            continue
        index, annotation = matches[0]
        matched_by_annotation[index].append(item.review_id)
        attached.append(replace(item, source_review=_source_review_payload(annotation)))

    reviewed = [item for item in attached if item.source_review is not None]
    unmatched = [
        {
            "annotation_index": index,
            "match": annotations[index].get("match", {}),
        }
        for index, review_ids in matched_by_annotation.items()
        if not review_ids
    ]
    source_review = {
        "annotation_schema_version": annotation_document.get("schema_version", 1),
        "annotations": len(annotations),
        "reviewed_items": len(reviewed),
        "unreviewed_items": len(attached) - len(reviewed),
        "by_verdict": _counts(
            str(item.source_review.get("verdict", "")) for item in reviewed if item.source_review
        ),
        "by_confidence": _counts(
            str(item.source_review.get("confidence", "")) for item in reviewed if item.source_review
        ),
        "needs_protocol_change": sum(
            1 for item in reviewed if item.source_review and item.source_review.get("needs_protocol_change") is True
        ),
        "needs_summary_change": sum(
            1 for item in reviewed if item.source_review and item.source_review.get("needs_summary_change") is True
        ),
        "needs_frontend_change": sum(
            1 for item in reviewed if item.source_review and item.source_review.get("needs_frontend_change") is True
        ),
        "unmatched_annotations": unmatched,
        "conflicting_annotations": conflicts,
    }
    summary = dict(report.summary)
    summary["source_review"] = source_review
    return replace(report, summary=summary, items=tuple(attached))


def write_review_json(report: ReviewQueueReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_review_markdown(report: ReviewQueueReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# MOCC-SE Finding Review Queue",
        "",
        "This is a development review queue, not a frozen benchmark.",
        "",
        f"- source report: `{report.source_report}`",
        f"- source root: `{report.source_root}`",
        f"- source version: `{report.source_version}`",
        f"- review items: {report.summary['review_items']}",
        f"- protocol candidates: {report.summary['protocol_candidates']}",
        f"- discovery reviews: {report.summary['discovery_reviews']}",
        "",
    ]
    for index, item in enumerate(report.items, 1):
        lines.extend(
            [
                f"## {index}. {item.function} / {item.violation_type}",
                "",
                f"- review id: `{item.review_id}`",
                f"- classification: `{item.classification}`",
                f"- protocol: `{item.protocol_id}`",
                f"- operation: `{item.operation_id}`",
                f"- location: `{item.source_file}`",
                f"- exit: `{item.exit_kind}:{item.exit_id}`",
                f"- certainty: `{item.static_certainty}`",
                f"- family: `{item.family_fingerprint}`",
                "",
                "Review focus:",
                "",
            ]
        )
        lines.extend(f"- {focus}" for focus in item.review_focus)
        if item.missing_summary_hints:
            lines.extend(["", "Likely development follow-ups:", ""])
            lines.extend(f"- {hint}" for hint in item.missing_summary_hints)
        if item.source_review:
            lines.extend(["", "Source review:", ""])
            lines.append(f"- verdict: `{item.source_review.get('verdict', '')}`")
            lines.append(f"- confidence: `{item.source_review.get('confidence', '')}`")
            root_cause = item.source_review.get("root_cause", "")
            if root_cause:
                lines.append(f"- root cause: {root_cause}")
            suggested_change = item.source_review.get("suggested_change", "")
            if suggested_change:
                lines.append(f"- suggested change: {suggested_change}")
            notes = item.source_review.get("notes", "")
            if notes:
                lines.append(f"- notes: {notes}")
        lines.extend(["", "Witness:", ""])
        for witness in item.witness:
            line = witness.get("line", 0)
            detail = witness.get("detail", "")
            kind = witness.get("kind", "")
            lines.append(f"- L{line} `{kind}`: {detail}")
        for context in item.source_context:
            lines.extend(
                [
                    "",
                    f"Source context `{context.source_file}:{context.start_line}`:",
                    "",
                    "```c",
                    context.snippet,
                    "```",
                ]
            )
        lines.append("")
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def load_discovery_report(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_annotation_document(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a MOCC-SE source-level finding review queue."
    )
    parser.add_argument("--discovery-report", required=True)
    parser.add_argument("--source-root", default="")
    parser.add_argument("--context-lines", type=int, default=4)
    parser.add_argument("--include-discovery-review", action="store_true")
    parser.add_argument("--annotations", default="")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args(argv)

    discovery = load_discovery_report(args.discovery_report)
    report = build_review_queue(
        discovery,
        source_report=args.discovery_report,
        source_root=args.source_root or None,
        context_lines=args.context_lines,
        include_discovery_review=args.include_discovery_review,
    )
    if args.annotations:
        report = apply_source_review_annotations(
            report,
            load_annotation_document(args.annotations),
        )
    write_review_json(report, args.out_json)
    write_review_markdown(report, args.out_md)
    print(f"review_items={report.summary['review_items']}")
    print(f"protocol_candidates={report.summary['protocol_candidates']}")
    print(f"discovery_reviews={report.summary['discovery_reviews']}")
    if "source_review" in report.summary:
        print(f"reviewed_items={report.summary['source_review']['reviewed_items']}")
    print(f"out_json={args.out_json}")
    print(f"out_md={args.out_md}")
    return 0


def _review_item(
    analysis: dict[str, Any],
    record: dict[str, Any],
    source_root: Path,
    *,
    context_lines: int,
) -> ReviewQueueItem:
    witness = tuple(record.get("representative_witness", ()))
    source_file = str(record.get("source_file") or analysis.get("source_file", ""))
    violation_type = str(
        record.get("violation_type") or record.get("semantic_pattern", "")
    )
    return ReviewQueueItem(
        review_id=f"mocc_review_{record.get('occurrence_fingerprint', '')}",
        classification=str(record.get("classification", "PROTOCOL_CANDIDATE")),
        protocol_id=str(record.get("protocol_id") or analysis.get("protocol_id", "")),
        operation_id=str(
            record.get("operation_id") or analysis.get("operation_id", "")
        ),
        function=str(record.get("function") or analysis.get("function", "")),
        source_file=source_file,
        source_version=str(
            record.get("source_version") or analysis.get("source_version", "")
        ),
        violation_type=violation_type,
        exit_kind=str(record.get("exit_kind", "")),
        exit_id=str(record.get("exit_id", "")),
        static_certainty=str(
            record.get("static_certainty")
            or (
                "review"
                if record.get("classification") == "DISCOVERY_REVIEW"
                else ""
            )
        ),
        family_fingerprint=str(record.get("family_fingerprint", "")),
        occurrence_fingerprint=str(record.get("occurrence_fingerprint", "")),
        review_focus=_review_focus(record),
        missing_summary_hints=_missing_summary_hints(record),
        unresolved_failures=tuple(record.get("unresolved_failures", ())),
        open_effects=tuple(record.get("open_effects", ())),
        accounting_state=tuple(record.get("accounting_state", ())),
        witness=witness,
        source_context=_source_contexts(
            source_root,
            source_file,
            _witness_lines(witness),
            context_lines=context_lines,
        ),
    )


def _review_focus(record: dict[str, Any]) -> tuple[str, ...]:
    violation_type = str(record.get("violation_type", ""))
    focus: list[str] = []
    if violation_type == "failure_reported_as_success":
        focus.append("Confirm whether the failed necessary step can reach a success exit.")
        focus.append("Check for retry, sentinel handling, abort, recovery, or propagated error.")
    elif violation_type == "incomplete_failure_completion":
        focus.append("Confirm whether each open effect is compensated or transferred on failure.")
        focus.append("Check callee summaries for cleanup hidden behind helper calls.")
    elif violation_type == "metadata_state_divergence":
        focus.append("Confirm whether return outcome, metadata effects, and accounting state agree.")
        focus.append("Check whether a missing reservation/accounting effect is hidden in a helper.")
    else:
        focus.append("Review protocol witness and source context for semantic mismatch.")
    if record.get("classification") == "DISCOVERY_REVIEW":
        focus.append("First decide whether this non-entry function is truly the same operation.")
    return tuple(focus)


def _missing_summary_hints(record: dict[str, Any]) -> tuple[str, ...]:
    hints: list[str] = []
    if record.get("unresolved_failures"):
        hints.append("review retry/handler/return-propagation summaries for unresolved failure")
    if record.get("open_effects"):
        hints.append("review compensation or handler summaries for open metadata effects")
    unsatisfied = [
        item
        for item in record.get("accounting_state", [])
        if item.get("satisfied") is False
    ]
    if unsatisfied:
        hints.append("review reservation/accounting summaries for unsatisfied obligation")
    if record.get("static_certainty") != "high":
        hints.append("review may/unknown event provenance before promoting finding")
    return tuple(hints)


def _source_contexts(
    source_root: Path,
    source_file: str,
    lines: Iterable[int],
    *,
    context_lines: int,
) -> tuple[ReviewSourceContext, ...]:
    path = source_root / source_file
    if not path.exists():
        return ()
    source_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    contexts: list[ReviewSourceContext] = []
    seen: set[tuple[int, int]] = set()
    for line in sorted({line for line in lines if line > 0}):
        start = max(1, line - context_lines)
        end = min(len(source_lines), line + context_lines)
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)
        snippet = "\n".join(
            f"{index:5d}: {source_lines[index - 1]}"
            for index in range(start, end + 1)
        )
        contexts.append(
            ReviewSourceContext(source_file, start, end, snippet)
        )
    return tuple(contexts)


def _witness_lines(witness: Iterable[dict[str, Any]]) -> tuple[int, ...]:
    return tuple(
        int(item.get("line", 0))
        for item in witness
        if str(item.get("line", "0")).isdigit()
    )


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _annotation_matches(item: ReviewQueueItem, match: dict[str, Any]) -> bool:
    fields = {
        "review_id": item.review_id,
        "classification": item.classification,
        "protocol_id": item.protocol_id,
        "operation_id": item.operation_id,
        "function": item.function,
        "source_file": item.source_file,
        "violation_type": item.violation_type,
        "exit_kind": item.exit_kind,
        "exit_id": item.exit_id,
        "family_fingerprint": item.family_fingerprint,
        "occurrence_fingerprint": item.occurrence_fingerprint,
    }
    for key, expected in match.items():
        if expected in {"", None}:
            continue
        actual = fields.get(key)
        if isinstance(expected, list):
            if actual not in {str(value) for value in expected}:
                return False
        elif actual != str(expected):
            return False
    return True


def _source_review_payload(annotation: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "verdict",
        "confidence",
        "root_cause",
        "needs_protocol_change",
        "needs_summary_change",
        "needs_frontend_change",
        "suggested_change",
        "notes",
    ]
    payload = {key: annotation.get(key, "") for key in keys}
    for key in ("needs_protocol_change", "needs_summary_change", "needs_frontend_change"):
        payload[key] = bool(annotation.get(key, False))
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
