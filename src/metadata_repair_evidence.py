"""Attach cross-version repair evidence to MOCC-SE development triage items."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


REPAIR_EVIDENCE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class RepairEvidence:
    function: str
    source_report: str
    from_version: str
    to_version: str
    semantic_hints: tuple[str, ...]
    removed_returns: tuple[str, ...]
    added_returns: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "function": self.function,
            "source_report": self.source_report,
            "from_version": self.from_version,
            "to_version": self.to_version,
            "semantic_hints": list(self.semantic_hints),
            "removed_returns": list(self.removed_returns),
            "added_returns": list(self.added_returns),
        }


@dataclass(frozen=True)
class RepairEvidenceReport:
    triage_source: str
    repair_sources: tuple[str, ...]
    summary: dict[str, Any]
    items: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": REPAIR_EVIDENCE_SCHEMA_VERSION,
            "triage_source": self.triage_source,
            "repair_sources": list(self.repair_sources),
            "summary": self.summary,
            "items": list(self.items),
        }


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def repair_evidence_from_function_diff(
    report: dict[str, Any],
    *,
    source_report: str = "",
    required_hint: str = "local_return_propagation_repair",
) -> tuple[RepairEvidence, ...]:
    function = str(report.get("function", ""))
    evidence: list[RepairEvidence] = []
    for pair in report.get("pair_diffs", ()):
        hints = tuple(str(item) for item in pair.get("semantic_hints", ()))
        if required_hint not in hints:
            continue
        evidence.append(
            RepairEvidence(
                function=function,
                source_report=source_report,
                from_version=str(pair.get("from_version", "")),
                to_version=str(pair.get("to_version", "")),
                semantic_hints=hints,
                removed_returns=tuple(
                    line
                    for line in pair.get("removed_lines", ())
                    if "return" in str(line)
                ),
                added_returns=tuple(
                    line
                    for line in pair.get("added_lines", ())
                    if "return" in str(line)
                ),
            )
        )
    return tuple(evidence)


def build_repair_evidence_report(
    triage_report: dict[str, Any],
    repair_evidence: Iterable[RepairEvidence],
    *,
    triage_source: str = "",
    repair_sources: Iterable[str] = (),
) -> RepairEvidenceReport:
    evidence_by_function: dict[str, list[RepairEvidence]] = {}
    for evidence in repair_evidence:
        evidence_by_function.setdefault(evidence.function, []).append(evidence)

    items: list[dict[str, Any]] = []
    for item in triage_report.get("items", ()):
        merged = dict(item)
        function = str(item.get("function", ""))
        evidence = tuple(evidence_by_function.get(function, ()))
        if evidence:
            merged["repair_evidence"] = [entry.to_dict() for entry in evidence]
        items.append(merged)

    attached = [item for item in items if item.get("repair_evidence")]
    summary = {
        "triage_items": len(items),
        "items_with_repair_evidence": len(attached),
        "items_without_repair_evidence": len(items) - len(attached),
        "repair_evidence_functions": sorted(evidence_by_function),
        "by_protocol": _counts(
            str(item.get("protocol_id", "")) for item in attached
        ),
        "by_repair_hint": _counts(
            hint
            for item in attached
            for evidence in item.get("repair_evidence", ())
            for hint in evidence.get("semantic_hints", ())
        ),
        "interpretation": (
            "development repair evidence only; do not use as frozen benchmark labels "
            "or confirmed bug claims"
        ),
    }
    return RepairEvidenceReport(
        triage_source,
        tuple(repair_sources),
        summary,
        tuple(items),
    )


def write_repair_evidence_json(report: RepairEvidenceReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_repair_evidence_markdown(report: RepairEvidenceReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# MOCC-SE Repair Evidence Ledger",
        "",
        "This is development repair evidence, not a frozen benchmark or confirmed-bug list.",
        "",
        f"- triage source: `{report.triage_source}`",
        f"- repair sources: {len(report.repair_sources)}",
        f"- triage items: {report.summary['triage_items']}",
        f"- items with repair evidence: {report.summary['items_with_repair_evidence']}",
        "",
        "Repair hints:",
        "",
    ]
    for hint, count in report.summary["by_repair_hint"].items():
        lines.append(f"- `{hint}`: {count}")
    for index, item in enumerate(report.items, 1):
        evidence = item.get("repair_evidence", ())
        if not evidence:
            continue
        lines.extend(
            [
                "",
                f"## {index}. {item.get('function', '')} / {item.get('violation_type', '')}",
                "",
                f"- review id: `{item.get('review_id', '')}`",
                f"- protocol: `{item.get('protocol_id', '')}`",
                f"- triage verdict: `{(item.get('triage') or {}).get('verdict', '')}`",
            ]
        )
        for entry in evidence:
            lines.extend(
                [
                    "",
                    f"Evidence `{entry.get('from_version', '')}` -> `{entry.get('to_version', '')}`:",
                    "",
                ]
            )
            lines.extend(
                f"- hint: `{hint}`" for hint in entry.get("semantic_hints", ())
            )
            if entry.get("removed_returns"):
                lines.append(
                    "- removed returns: "
                    + ", ".join(f"`{value.strip()}`" for value in entry["removed_returns"])
                )
            if entry.get("added_returns"):
                lines.append(
                    "- added returns: "
                    + ", ".join(f"`{value.strip()}`" for value in entry["added_returns"])
                )
            lines.append(f"- source diff: `{entry.get('source_report', '')}`")
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Attach repair evidence to a MOCC-SE source triage ledger."
    )
    parser.add_argument("--triage", required=True)
    parser.add_argument("--function-diff", action="append", required=True)
    parser.add_argument("--required-hint", default="local_return_propagation_repair")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args(argv)

    evidence: list[RepairEvidence] = []
    for path in args.function_diff:
        evidence.extend(
            repair_evidence_from_function_diff(
                load_json(path),
                source_report=path,
                required_hint=args.required_hint,
            )
        )
    report = build_repair_evidence_report(
        load_json(args.triage),
        evidence,
        triage_source=args.triage,
        repair_sources=args.function_diff,
    )
    write_repair_evidence_json(report, args.out_json)
    write_repair_evidence_markdown(report, args.out_md)
    print(f"triage_items={report.summary['triage_items']}")
    print(f"items_with_repair_evidence={report.summary['items_with_repair_evidence']}")
    print(f"out_json={args.out_json}")
    print(f"out_md={args.out_md}")
    return 0


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    raise SystemExit(main())
