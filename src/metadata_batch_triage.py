"""Initial source triage for freeze-bound batch scan review queues."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


BATCH_TRIAGE_SCHEMA_VERSION = 1
TRIAGE_VERDICTS = {
    "candidate_for_manual_bug_review",
    "needs_protocol_instance",
    "needs_external_semantics",
    "likely_false_positive",
    "out_of_scope",
    "uncertain",
}


@dataclass(frozen=True)
class BatchTriageDecision:
    review_id: str
    verdict: str
    priority: str
    confidence: str
    rationale: str
    evidence: tuple[str, ...]
    followups: tuple[str, ...]
    bug_claim_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "verdict": self.verdict,
            "priority": self.priority,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "followups": list(self.followups),
            "bug_claim_allowed": self.bug_claim_allowed,
        }


@dataclass(frozen=True)
class BatchTriageReport:
    batch_report: str
    source_version: str
    result_semantics: str
    decisions: tuple[tuple[dict[str, Any], BatchTriageDecision], ...]

    def to_dict(self) -> dict[str, Any]:
        verdicts = Counter(decision.verdict for _, decision in self.decisions)
        priorities = Counter(decision.priority for _, decision in self.decisions)
        protocols = Counter(
            record.get("protocol_id", "") for record, _ in self.decisions
        )
        return {
            "schema_version": BATCH_TRIAGE_SCHEMA_VERSION,
            "batch_report": self.batch_report,
            "source_version": self.source_version,
            "result_semantics": self.result_semantics,
            "bug_claims_allowed": False,
            "summary": {
                "triage_items": len(self.decisions),
                "by_verdict": dict(sorted(verdicts.items())),
                "by_priority": dict(sorted(priorities.items())),
                "by_protocol": dict(sorted(protocols.items())),
                "manual_bug_review_candidates": sum(
                    1
                    for _, decision in self.decisions
                    if decision.verdict == "candidate_for_manual_bug_review"
                ),
                "needs_protocol_instance": sum(
                    1
                    for _, decision in self.decisions
                    if decision.verdict == "needs_protocol_instance"
                ),
                "needs_external_semantics": sum(
                    1
                    for _, decision in self.decisions
                    if decision.verdict == "needs_external_semantics"
                ),
                "likely_false_positive": sum(
                    1
                    for _, decision in self.decisions
                    if decision.verdict == "likely_false_positive"
                ),
            },
            "items": [
                {
                    "record": record,
                    "triage": decision.to_dict(),
                }
                for record, decision in self.decisions
            ],
        }


def build_batch_triage_report(
    batch_report: Mapping[str, Any],
    *,
    batch_report_source: str = "",
) -> BatchTriageReport:
    result_semantics = str(batch_report.get("result_semantics", ""))
    records = list(batch_report.get("protocol_candidates", ()))
    records.extend(batch_report.get("review_queue", ()))
    records.extend(batch_report.get("unknown_queue", ()))
    decisions = tuple((record, triage_record(record)) for record in records)
    return BatchTriageReport(
        batch_report_source,
        str(batch_report.get("source_version", "")),
        result_semantics,
        decisions,
    )


def triage_record(record: Mapping[str, Any]) -> BatchTriageDecision:
    review_id = _review_id(record)
    classification = str(record.get("classification", ""))
    protocol_id = str(record.get("protocol_id", ""))
    pattern = str(record.get("semantic_pattern", ""))
    witness = tuple(record.get("representative_witness", ()))
    evidence = tuple(_witness_line(item) for item in witness)

    if classification == "PROTOCOL_CANDIDATE":
        return BatchTriageDecision(
            review_id,
            "candidate_for_manual_bug_review",
            "P0",
            "medium",
            "Exact protocol analysis produced a candidate; it still requires source review and external confirmation before it can be called a bug.",
            evidence,
            (
                "inspect full function and caller contract",
                "look for historical fix, maintainer discussion, reproducer, or upstream submission evidence",
            ),
        )

    if classification in {"DISCOVERY_REVIEW_UNKNOWN", "DISCOVERY_UNKNOWN"}:
        return BatchTriageDecision(
            review_id,
            "uncertain",
            "P2",
            "medium",
            "The analyzer preserved uncertainty instead of producing a candidate.",
            evidence,
            ("improve alias/callee/operation applicability evidence before bug triage",),
        )

    if (
        classification == "DISCOVERY_REVIEW"
        and protocol_id == "mocc.protocol_a.replay_recovery"
        and pattern == "failure_return_mismatch"
    ):
        if str(record.get("function", "")) in {
            "ext4_ext_clear_bb",
            "ext4_ext_replay_set_iblocks",
        }:
            return BatchTriageDecision(
                review_id,
                "needs_external_semantics",
                "P0",
                "high",
                "The ext4 fast-commit replay helper shape is source-visible, but the missing question is whether replay bookkeeping failures are required to abort replay or may be best-effort.",
                evidence,
                (
                    "run metadata_ext4_replay_bookkeeping_audit on the exact Linux source tree",
                    "seek independent ext4 fast-commit replay contract, maintainer review, accepted fix, or fault-injection evidence",
                    "do not promote into an active protocol instance until that semantic obligation is frozen",
                ),
            )
        return BatchTriageDecision(
            review_id,
            "needs_protocol_instance",
            "P0",
            "medium",
            "The source-visible failure-to-success pattern resembles replay/recovery outcome obligations, but the function is not an exact frozen operation instance.",
            evidence,
            (
                "decide whether this helper belongs to Protocol A or a new ext4 replay bookkeeping operation",
                "only after protocol binding should it be tested as a PROTOCOL_CANDIDATE",
            ),
        )

    if classification == "DISCOVERY_REVIEW" and pattern == "mutation_failure_cleanup":
        mutation = _witness_detail(witness, "state_mutation")
        if _looks_like_local_preparation(mutation):
            return BatchTriageDecision(
                review_id,
                "likely_false_positive",
                "P2",
                "high",
                "The matched mutation is local preparation or local argument state, not a proven durable metadata effect.",
                evidence,
                (
                    "teach broad discovery to distinguish local/search-key/reservation preparation from metadata effects",
                    "do not promote without a protocol object binding",
                ),
            )
        return BatchTriageDecision(
            review_id,
            "uncertain",
            "P1",
            "low",
            "The broad mutation/cleanup pattern needs source review before deciding whether it is a real protocol lifecycle.",
            evidence,
            ("inspect object identity and whether the mutation escapes the local function",),
        )

    return BatchTriageDecision(
        review_id,
        "uncertain",
        "P2",
        "low",
        "No specialized triage rule matched this review record.",
        evidence,
        ("add a triage rule or perform manual source review",),
    )


def write_triage_json(report: BatchTriageReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_triage_markdown(report: BatchTriageReport, path: str | Path) -> None:
    payload = report.to_dict()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# MOCC-SE Batch Scan Triage",
        "",
        "This is an initial source triage ledger. It is not a confirmed-bug list and not a frozen benchmark result.",
        "",
        f"- batch report: `{report.batch_report}`",
        f"- source version: `{report.source_version}`",
        f"- result semantics: `{report.result_semantics}`",
        f"- bug claims allowed: `{payload['bug_claims_allowed']}`",
        "",
        "Summary:",
        "",
    ]
    for key, value in payload["summary"].items():
        lines.append(f"- `{key}`: {value}")
    lines.append("")
    for index, item in enumerate(payload["items"], 1):
        record = item["record"]
        decision = item["triage"]
        lines.extend(
            [
                f"## {index}. {record.get('function', '')}",
                "",
                f"- review id: `{decision['review_id']}`",
                f"- classification: `{record.get('classification', '')}`",
                f"- protocol: `{record.get('protocol_id', '')}`",
                f"- source: `{record.get('source_file', '')}`",
                f"- pattern: `{record.get('semantic_pattern', '')}`",
                f"- verdict: `{decision['verdict']}`",
                f"- priority: `{decision['priority']}`",
                f"- confidence: `{decision['confidence']}`",
                f"- rationale: {decision['rationale']}",
                "",
                "Evidence:",
                "",
            ]
        )
        lines.extend(f"- {entry}" for entry in decision["evidence"])
        lines.extend(["", "Follow-ups:", ""])
        lines.extend(f"- {entry}" for entry in decision["followups"])
        lines.append("")
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected JSON object")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create an initial triage ledger for a MOCC-SE batch scan report."
    )
    parser.add_argument("--batch-report", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args(argv)
    report = build_batch_triage_report(
        load_json(args.batch_report),
        batch_report_source=args.batch_report,
    )
    write_triage_json(report, args.out_json)
    write_triage_markdown(report, args.out_md)
    summary = report.to_dict()["summary"]
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _review_id(record: Mapping[str, Any]) -> str:
    for key in (
        "occurrence_fingerprint",
        "candidate_id",
        "root_cause_fingerprint",
    ):
        value = str(record.get(key, ""))
        if value:
            return value
    parts = (
        record.get("classification", ""),
        record.get("protocol_id", ""),
        record.get("source_file", ""),
        record.get("function", ""),
    )
    return "mocc_triage_" + str(abs(hash(parts)))


def _witness_detail(witness: Iterable[Any], kind: str) -> str:
    for item in witness:
        if isinstance(item, Mapping) and item.get("kind") == kind:
            return str(item.get("detail", ""))
    return ""


def _witness_line(item: Any) -> str:
    if not isinstance(item, Mapping):
        return str(item)
    line = item.get("line", "")
    kind = item.get("kind", "")
    detail = item.get("detail", "")
    return f"{kind} line {line}: {detail}"


def _looks_like_local_preparation(detail: str) -> bool:
    left = detail.split("=", 1)[0].strip()
    if re.match(r"^(?:key|new_key|map|resv|dres|ref)\.", left):
        return True
    if left in {"args->extent_inserted"}:
        return True
    return False


if __name__ == "__main__":
    raise SystemExit(main())
