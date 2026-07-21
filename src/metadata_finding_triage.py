"""Merge MOCC-SE review queues with source-level development triage."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


TRIAGE_SCHEMA_VERSION = 1
TRIAGE_VERDICTS = {
    "candidate_survives_initial_review",
    "likely_false_positive",
    "uncertain",
}
SOURCE_REVIEW_VERDICT_MAP = {
    "likely_true_candidate": "candidate_survives_initial_review",
    "true_candidate": "candidate_survives_initial_review",
    "source_supported_candidate": "candidate_survives_initial_review",
    "false_positive": "likely_false_positive",
    "likely_false_positive": "likely_false_positive",
    "uncertain": "uncertain",
}


@dataclass(frozen=True)
class TriageDecision:
    review_id: str
    verdict: str
    confidence: str
    source_evidence: tuple[str, ...]
    development_followups: tuple[str, ...]
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TriageDecision":
        review_id = str(payload.get("review_id", ""))
        verdict = str(payload.get("verdict", ""))
        if not review_id:
            raise ValueError("triage decision is missing review_id")
        if verdict not in TRIAGE_VERDICTS:
            raise ValueError(f"unknown triage verdict: {verdict}")
        return cls(
            review_id=review_id,
            verdict=verdict,
            confidence=str(payload.get("confidence", "")),
            source_evidence=tuple(str(item) for item in payload.get("source_evidence", ())),
            development_followups=tuple(
                str(item) for item in payload.get("development_followups", ())
            ),
            notes=str(payload.get("notes", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "verdict": self.verdict,
            "confidence": self.confidence,
            "source_evidence": list(self.source_evidence),
            "development_followups": list(self.development_followups),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class TriageItem:
    review_item: dict[str, Any]
    decision: TriageDecision | None

    @property
    def review_id(self) -> str:
        return str(self.review_item.get("review_id", ""))

    @property
    def verdict(self) -> str:
        return self.decision.verdict if self.decision else "unreviewed"

    @property
    def protocol_id(self) -> str:
        return str(self.review_item.get("protocol_id", ""))

    @property
    def function(self) -> str:
        return str(self.review_item.get("function", ""))

    def to_dict(self) -> dict[str, Any]:
        merged = dict(self.review_item)
        merged["triage"] = self.decision.to_dict() if self.decision else None
        return merged


@dataclass(frozen=True)
class TriageReport:
    review_queue: str
    decisions_source: str
    summary: dict[str, Any]
    items: tuple[TriageItem, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": TRIAGE_SCHEMA_VERSION,
            "review_queue": self.review_queue,
            "decisions_source": self.decisions_source,
            "summary": self.summary,
            "items": [item.to_dict() for item in self.items],
        }


def load_review_queue(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_decisions(path: str | Path) -> tuple[TriageDecision, ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload.get("decisions", payload if isinstance(payload, list) else ())
    if not isinstance(records, list):
        raise ValueError("triage decisions must be a list or an object with decisions")
    return tuple(TriageDecision.from_dict(item) for item in records)


def decisions_from_source_reviews(review_queue: dict[str, Any]) -> tuple[TriageDecision, ...]:
    decisions: list[TriageDecision] = []
    for item in review_queue.get("items", ()):
        source_review = item.get("source_review")
        if not source_review:
            continue
        review_id = str(item.get("review_id", ""))
        if not review_id:
            continue
        verdict = SOURCE_REVIEW_VERDICT_MAP.get(
            str(source_review.get("verdict", "")),
            "uncertain",
        )
        evidence = [
            value
            for value in (
                source_review.get("root_cause", ""),
                source_review.get("notes", ""),
            )
            if value
        ]
        followups = [
            value
            for value in (
                source_review.get("suggested_change", ""),
                _change_followup(source_review),
            )
            if value
        ]
        decisions.append(
            TriageDecision(
                review_id,
                verdict,
                str(source_review.get("confidence", "")),
                tuple(str(value) for value in evidence),
                tuple(str(value) for value in followups),
                notes="derived from reviewed queue source_review",
            )
        )
    return tuple(decisions)


def build_triage_report(
    review_queue: dict[str, Any],
    decisions: Iterable[TriageDecision],
    *,
    review_queue_source: str = "",
    decisions_source: str = "",
) -> TriageReport:
    by_review_id: dict[str, TriageDecision] = {}
    for decision in decisions:
        if decision.review_id in by_review_id:
            raise ValueError(f"duplicate triage decision for {decision.review_id}")
        by_review_id[decision.review_id] = decision

    items = tuple(
        TriageItem(item, by_review_id.get(str(item.get("review_id", ""))))
        for item in review_queue.get("items", ())
    )
    queue_ids = {item.review_id for item in items}
    unknown_ids = sorted(set(by_review_id) - queue_ids)
    if unknown_ids:
        raise ValueError(f"triage decisions reference unknown review ids: {', '.join(unknown_ids)}")

    summary = {
        "triage_items": len(items),
        "reviewed_items": sum(1 for item in items if item.decision is not None),
        "unreviewed_items": sum(1 for item in items if item.decision is None),
        "by_verdict": _counts(item.verdict for item in items),
        "by_protocol": _counts(item.protocol_id for item in items),
        "surviving_candidates_by_protocol": _counts(
            item.protocol_id
            for item in items
            if item.verdict == "candidate_survives_initial_review"
        ),
        "followup_topics": _counts(
            followup
            for item in items
            if item.decision is not None
            for followup in item.decision.development_followups
        ),
    }
    return TriageReport(review_queue_source, decisions_source, summary, items)


def write_triage_json(report: TriageReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_triage_markdown(report: TriageReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# MOCC-SE Initial Source Triage",
        "",
        "This is a development triage ledger, not a frozen benchmark or a confirmed-bug list.",
        "",
        f"- review queue: `{report.review_queue}`",
        f"- decisions: `{report.decisions_source}`",
        f"- triage items: {report.summary['triage_items']}",
        f"- reviewed items: {report.summary['reviewed_items']}",
        f"- unreviewed items: {report.summary['unreviewed_items']}",
        "",
        "Verdicts:",
        "",
    ]
    for verdict, count in report.summary["by_verdict"].items():
        lines.append(f"- `{verdict}`: {count}")
    lines.extend(["", "Surviving candidates by protocol:", ""])
    for protocol, count in report.summary["surviving_candidates_by_protocol"].items():
        lines.append(f"- `{protocol}`: {count}")
    lines.append("")

    for index, item in enumerate(report.items, 1):
        decision = item.decision
        lines.extend(
            [
                f"## {index}. {item.function} / {item.review_item.get('violation_type', '')}",
                "",
                f"- review id: `{item.review_id}`",
                f"- protocol: `{item.protocol_id}`",
                f"- location: `{item.review_item.get('source_file', '')}`",
                f"- verdict: `{item.verdict}`",
            ]
        )
        if decision is None:
            lines.extend(["", "No triage decision recorded yet.", ""])
            continue
        lines.append(f"- confidence: `{decision.confidence}`")
        if decision.source_evidence:
            lines.extend(["", "Source evidence:", ""])
            lines.extend(f"- {entry}" for entry in decision.source_evidence)
        if decision.development_followups:
            lines.extend(["", "Development follow-ups:", ""])
            lines.extend(f"- {entry}" for entry in decision.development_followups)
        if decision.notes:
            lines.extend(["", f"Notes: {decision.notes}"])
        lines.append("")
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Merge a MOCC-SE finding review queue with source triage decisions."
    )
    parser.add_argument("--review-queue", required=True)
    parser.add_argument("--decisions", default="")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args(argv)

    queue = load_review_queue(args.review_queue)
    decisions = (
        load_decisions(args.decisions)
        if args.decisions
        else decisions_from_source_reviews(queue)
    )
    report = build_triage_report(
        queue,
        decisions,
        review_queue_source=args.review_queue,
        decisions_source=args.decisions or "<source_review>",
    )
    write_triage_json(report, args.out_json)
    write_triage_markdown(report, args.out_md)
    print(f"triage_items={report.summary['triage_items']}")
    print(f"reviewed_items={report.summary['reviewed_items']}")
    print(f"unreviewed_items={report.summary['unreviewed_items']}")
    print(f"out_json={args.out_json}")
    print(f"out_md={args.out_md}")
    return 0


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _change_followup(source_review: dict[str, Any]) -> str:
    needs: list[str] = []
    if source_review.get("needs_protocol_change") is True:
        needs.append("protocol")
    if source_review.get("needs_summary_change") is True:
        needs.append("summary")
    if source_review.get("needs_frontend_change") is True:
        needs.append("frontend")
    return "needs " + "/".join(needs) + " change" if needs else ""


if __name__ == "__main__":
    raise SystemExit(main())
