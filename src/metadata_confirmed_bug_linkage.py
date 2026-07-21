"""Link MOCC-SE development candidates to confirmed bug records."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


CONFIRMED_LINKAGE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ConfirmedBugRecord:
    bug_id: int
    filesystem: str
    function: str
    bug_type: str
    status: str
    evidence: str
    status_class: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "bug_id": self.bug_id,
            "filesystem": self.filesystem,
            "function": self.function,
            "bug_type": self.bug_type,
            "status": self.status,
            "evidence": self.evidence,
            "status_class": self.status_class,
        }


@dataclass(frozen=True)
class CandidateConfirmedLink:
    review_id: str
    function: str
    protocol_id: str
    violation_type: str
    priority_queue: str
    confirmed_bugs: tuple[ConfirmedBugRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "function": self.function,
            "protocol_id": self.protocol_id,
            "violation_type": self.violation_type,
            "priority_queue": self.priority_queue,
            "confirmed_bugs": [item.to_dict() for item in self.confirmed_bugs],
            "linkage_class": _linkage_class(self.confirmed_bugs),
        }


@dataclass(frozen=True)
class ConfirmedLinkageReport:
    bug_hunt_report_source: str
    confirmed_bugs_source: str
    summary: dict[str, Any]
    links: tuple[CandidateConfirmedLink, ...]
    unmatched_confirmed_bugs: tuple[ConfirmedBugRecord, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CONFIRMED_LINKAGE_SCHEMA_VERSION,
            "bug_hunt_report_source": self.bug_hunt_report_source,
            "confirmed_bugs_source": self.confirmed_bugs_source,
            "summary": self.summary,
            "links": [item.to_dict() for item in self.links],
            "unmatched_confirmed_bugs": [
                item.to_dict() for item in self.unmatched_confirmed_bugs
            ],
        }


def parse_confirmed_bugs_markdown(text: str) -> tuple[ConfirmedBugRecord, ...]:
    records: list[ConfirmedBugRecord] = []
    summary_text = _markdown_section(text, "Summary")
    for raw_line in summary_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 6 or not cells[0].strip().isdigit():
            continue
        bug_id = int(cells[0])
        function = _strip_markdown(cells[2]).strip()
        function = re.sub(r"\(\)$", "", function)
        status = _strip_markdown(cells[4]).strip()
        evidence = _strip_markdown(cells[5]).strip()
        records.append(
            ConfirmedBugRecord(
                bug_id=bug_id,
                filesystem=_strip_markdown(cells[1]).strip(),
                function=function,
                bug_type=_strip_markdown(cells[3]).strip(),
                status=status,
                evidence=evidence,
                status_class=_status_class(status, evidence),
            )
        )
    return tuple(records)


def build_confirmed_linkage_report(
    bug_hunt_report: dict[str, Any],
    confirmed_bugs: Iterable[ConfirmedBugRecord],
    *,
    bug_hunt_report_source: str = "",
    confirmed_bugs_source: str = "",
) -> ConfirmedLinkageReport:
    records = tuple(confirmed_bugs)
    records_by_function: dict[str, list[ConfirmedBugRecord]] = {}
    for record in records:
        records_by_function.setdefault(record.function, []).append(record)

    links: list[CandidateConfirmedLink] = []
    linked_bug_ids: set[int] = set()
    for queue_name, item in _iter_bug_hunt_link_items(bug_hunt_report):
        function = str(item.get("function", ""))
        matches = tuple(records_by_function.get(function, ()))
        linked_bug_ids.update(record.bug_id for record in matches)
        links.append(
            CandidateConfirmedLink(
                review_id=str(item.get("review_id", "")),
                function=function,
                protocol_id=str(item.get("protocol_id", "")),
                violation_type=str(item.get("violation_type", "")),
                priority_queue=str(queue_name),
                confirmed_bugs=matches,
            )
        )

    linked = [item for item in links if item.confirmed_bugs]
    unmatched_confirmed = tuple(
        record for record in records if record.bug_id not in linked_bug_ids
    )
    linked_records = tuple(
        record for record in records if record.bug_id in linked_bug_ids
    )
    summary = {
        "candidate_links": len(links),
        "candidates_with_confirmed_bug": len(linked),
        "candidates_without_confirmed_bug": len(links) - len(linked),
        "confirmed_bug_records": len(records),
        "confirmed_bug_records_linked": len(linked_bug_ids),
        "confirmed_bug_records_unmatched": len(unmatched_confirmed),
        "by_linkage_class": _counts(
            _linkage_class(item.confirmed_bugs) for item in links
        ),
        "by_link_source": _counts(item.priority_queue for item in links),
        "by_status_class": _counts(record.status_class for record in records),
        "by_linked_status_class": _counts(
            record.status_class for record in linked_records
        ),
        "interpretation": (
            "development linkage only; confirmed records are motivating examples, "
            "regression targets, or already submitted/fixed bugs, not a frozen "
            "evaluation set"
        ),
    }
    return ConfirmedLinkageReport(
        bug_hunt_report_source,
        confirmed_bugs_source,
        summary,
        tuple(links),
        unmatched_confirmed,
    )


def _iter_bug_hunt_link_items(
    bug_hunt_report: dict[str, Any],
) -> Iterable[tuple[str, dict[str, Any]]]:
    seen: set[tuple[str, str, str, str, str]] = set()

    def emit(
        source_name: str, items: Iterable[dict[str, Any]]
    ) -> Iterable[tuple[str, dict[str, Any]]]:
        for item in items:
            key = (
                source_name,
                str(item.get("review_id", "")),
                str(item.get("function", "")),
                str(item.get("protocol_id", "")),
                str(item.get("violation_type", "")),
            )
            if key in seen:
                continue
            seen.add(key)
            yield source_name, item

    for queue_name, items in bug_hunt_report.get("priority_queues", {}).items():
        yield from emit(str(queue_name), items)

    # Accept early M9 reports that emitted the two version-delta queues at the
    # top level rather than under ``priority_queues``.
    for source_name in (
        "removed_or_cleared_functions",
        "added_functions_to_inspect",
    ):
        yield from emit(source_name, bug_hunt_report.get(source_name, ()))


def write_linkage_json(report: ConfirmedLinkageReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_linkage_markdown(report: ConfirmedLinkageReport, path: str | Path) -> None:
    target = Path(path)
    lines = [
        "# MOCC-SE Confirmed Bug Linkage",
        "",
        "This is a development linkage report, not a frozen benchmark or a new-submission list.",
        "",
        f"- bug-hunt report: `{report.bug_hunt_report_source}`",
        f"- confirmed bugs: `{report.confirmed_bugs_source}`",
        f"- candidate links: {report.summary['candidate_links']}",
        f"- candidates with confirmed bug: {report.summary['candidates_with_confirmed_bug']}",
        f"- candidates without confirmed bug: {report.summary['candidates_without_confirmed_bug']}",
        f"- confirmed bug records: {report.summary['confirmed_bug_records']}",
        f"- confirmed bug records linked: {report.summary['confirmed_bug_records_linked']}",
        f"- confirmed bug records outside this queue: {report.summary['confirmed_bug_records_unmatched']}",
        "",
        "Status classes:",
        "",
    ]
    for status_class, count in report.summary["by_status_class"].items():
        lines.append(f"- `{status_class}`: {count}")
    lines.extend(["", "Candidate links:", ""])
    for link in report.links:
        bug_ids = ", ".join(
            f"#{record.bug_id} `{record.status_class}`"
            for record in link.confirmed_bugs
        )
        if not bug_ids:
            bug_ids = "unmatched"
        lines.append(
            f"- `{link.function}` / `{link.violation_type}` / `{link.priority_queue}` -> {bug_ids}"
        )
    lines.extend(
        [
            "",
            "Confirmed records outside this bug-hunt queue:",
            "",
            "These records remain confirmed; absence here only means that the current M9 queue did not select them.",
            "",
        ]
    )
    if report.unmatched_confirmed_bugs:
        for record in report.unmatched_confirmed_bugs:
            lines.append(
                f"- #{record.bug_id} `{record.function}` / `{record.status_class}`"
            )
    else:
        lines.append("- none")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Link a MOCC-SE bug-hunt report to confirmed bug records."
    )
    parser.add_argument("--bug-hunt-report", required=True)
    parser.add_argument("--confirmed-bugs", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args(argv)

    bug_hunt = json.loads(Path(args.bug_hunt_report).read_text(encoding="utf-8"))
    confirmed = parse_confirmed_bugs_markdown(
        Path(args.confirmed_bugs).read_text(encoding="utf-8")
    )
    report = build_confirmed_linkage_report(
        bug_hunt,
        confirmed,
        bug_hunt_report_source=args.bug_hunt_report,
        confirmed_bugs_source=args.confirmed_bugs,
    )
    write_linkage_json(report, args.out_json)
    write_linkage_markdown(report, args.out_md)
    print(f"candidate_links={report.summary['candidate_links']}")
    print(
        "candidates_with_confirmed_bug="
        f"{report.summary['candidates_with_confirmed_bug']}"
    )
    print(f"out_json={args.out_json}")
    print(f"out_md={args.out_md}")
    return 0


def _strip_markdown(value: str) -> str:
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    return value.replace("\\|", "|")


def _markdown_section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$([\s\S]*?)(?=^##\s+|\Z)",
        re.MULTILINE,
    )
    match = pattern.search(text)
    return match.group(1) if match else text


def _status_class(status: str, evidence: str) -> str:
    text = f"{status} {evidence}".lower()
    if "for-next" in text:
        return "confirmed_for_next"
    if (
        "already fixed" in text
        or "fixed in later" in text
        or "fixed in latest" in text
        or "fixed upstream" in text
    ):
        return "confirmed_fixed_duplicate"
    if "reviewed-by" in text or "reviewed-by received" in text:
        return "confirmed_submitted_reviewed"
    if "patch" in text or "submitted" in text:
        return "confirmed_submitted"
    if "confirmed" in text:
        return "confirmed_source_level"
    return "confirmed_record"


def _linkage_class(records: tuple[ConfirmedBugRecord, ...]) -> str:
    if not records:
        return "needs_confirmation"
    classes = {record.status_class for record in records}
    if "confirmed_for_next" in classes:
        return "confirmed_for_next"
    if classes == {"confirmed_fixed_duplicate"}:
        return "confirmed_fixed_duplicate"
    if any(item.startswith("confirmed_submitted") for item in classes):
        return "confirmed_submitted"
    return "confirmed_linked"


def _counts(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    raise SystemExit(main())
