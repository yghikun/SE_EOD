"""Measurement-only impact profiling for unresolved semantic blockers."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..function_extractor import extract_functions
from ..parser import parse_c_file
from .unknown_triage import (
    INDIRECT_TARGET_SET_UNPROVEN,
    SUMMARY_BODY_UNAVAILABLE,
    unknown_cause_category,
    unknown_cause_proof_gap,
)


SEMANTIC_BLOCKER_IMPACT_SCHEMA_VERSION = 1

BODY_IN_CALLER_TRANSLATION_UNIT = "BODY_IN_CALLER_TRANSLATION_UNIT"
BODY_IN_ANALYSIS_ROOT = "BODY_IN_ANALYSIS_ROOT"
BODY_OUTSIDE_ANALYSIS_ROOT = "BODY_OUTSIDE_ANALYSIS_ROOT"
HEADER_INLINE_NOT_LOADED = "HEADER_INLINE_NOT_LOADED"
MACRO_OR_CONDITIONAL_BODY = "MACRO_OR_CONDITIONAL_BODY"
MULTIPLE_DEFINITIONS = "MULTIPLE_DEFINITIONS"
INDIRECT_TARGET_BODY_UNKNOWN = "INDIRECT_TARGET_BODY_UNKNOWN"
NO_EXACT_DEFINITION = "NO_EXACT_DEFINITION"
SOURCE_INDEX_UNAVAILABLE = "SOURCE_INDEX_UNAVAILABLE"
NOT_APPLICABLE = "NOT_APPLICABLE"

SOURCE_AVAILABLE_STATES = {
    BODY_IN_CALLER_TRANSLATION_UNIT,
    BODY_IN_ANALYSIS_ROOT,
    BODY_OUTSIDE_ANALYSIS_ROOT,
    HEADER_INLINE_NOT_LOADED,
}

DEFAULT_KNOWN_WITNESS_FUNCTIONS = {
    "btrfs_dev_replace_start",
    "btrfs_recover_relocation",
    "btrfs_reconfigure",
    "btrfs_create_uuid_tree",
    "btrfs_init_new_device",
    "make_indexed_dir",
}


@dataclass(frozen=True)
class SourceDefinition:
    function: str
    file: str
    line: int
    in_header: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "function": self.function,
            "file": self.file,
            "line": self.line,
            "in_header": self.in_header,
        }


@dataclass(frozen=True)
class SourceDefinitionIndex:
    definitions: dict[str, tuple[SourceDefinition, ...]]
    macros: dict[str, tuple[str, ...]]
    parse_failures: tuple[str, ...]
    source_root: str

    def to_dict(self) -> dict[str, object]:
        return {
            "source_root": self.source_root,
            "definition_count": sum(len(items) for items in self.definitions.values()),
            "function_count": len(self.definitions),
            "macro_count": len(self.macros),
            "parse_failures": list(self.parse_failures),
        }


def build_source_definition_index(source_root: str | Path) -> SourceDefinitionIndex:
    """Index exact source-visible bodies without inferring behavior from names."""

    root = Path(source_root)
    definitions: dict[str, list[SourceDefinition]] = defaultdict(list)
    macros: dict[str, set[str]] = defaultdict(set)
    parse_failures: list[str] = []
    for path in sorted((*root.rglob("*.c"), *root.rglob("*.h"))):
        try:
            for function in extract_functions(parse_c_file(path)):
                definitions[function.name].append(
                    SourceDefinition(
                        function=function.name,
                        file=path.as_posix(),
                        line=function.start_line,
                        in_header=path.suffix.lower() == ".h",
                    )
                )
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                match = re.match(r"\s*#\s*define\s+([A-Za-z_]\w*)\s*\(", line)
                if match:
                    macros[match.group(1)].add(path.as_posix())
        except (OSError, UnicodeError, ValueError) as error:
            parse_failures.append(f"{path.as_posix()}: {type(error).__name__}")
    return SourceDefinitionIndex(
        definitions={
            name: tuple(sorted(items, key=lambda item: (item.file, item.line)))
            for name, items in sorted(definitions.items())
        },
        macros={name: tuple(sorted(files)) for name, files in sorted(macros.items())},
        parse_failures=tuple(parse_failures),
        source_root=root.as_posix(),
    )


def build_semantic_blocker_impact(
    evaluation_outputs: Iterable[str | Path],
    *,
    oracle_records: Iterable[dict[str, Any]] = (),
    oracle_audit: dict[str, Any] | None = None,
    source_index: SourceDefinitionIndex | None = None,
    known_witness_functions: set[str] | None = None,
) -> dict[str, Any]:
    """Build a unified UNKNOWN and oracle-pending decision surface."""

    known_functions = known_witness_functions or DEFAULT_KNOWN_WITNESS_FUNCTIONS
    oracle = list(oracle_records)
    audit = oracle_audit or {}
    oracle_by_location: dict[
        tuple[object, ...], list[dict[str, Any]]
    ] = defaultdict(list)
    for record in oracle:
        oracle_by_location[
            _location_key(_mapping(record.get("stable_report")))
        ].append(record)
    audit_by_id = {
        str(item.get("oracle_id", "")): item
        for item in _sequence(audit.get("transitions"))
    }

    inputs: list[dict[str, object]] = []
    unknown_rows: list[dict[str, Any]] = []
    blocker_accumulators: dict[tuple[str, str, str], dict[str, Any]] = {}
    total_reports = 0
    for output_value in evaluation_outputs:
        output = Path(output_value)
        evaluation_path = output if output.is_file() else output / "evaluation.json"
        evaluation = _load_json(evaluation_path)
        summary = _mapping(evaluation.get("summary"))
        filesystem = _filesystem_from_summary(summary)
        analysis_root = str(summary.get("source_path", ""))
        reports_path = (
            output.parent / "reports" / "all_reports.json"
            if output.is_file()
            else output / "reports" / "all_reports.json"
        )
        reports = _load_json(reports_path)
        if not isinstance(reports, list):
            raise ValueError(f"expected report list in {reports_path}")
        report_dicts = [item for item in reports if isinstance(item, dict)]
        total_reports += len(report_dicts)
        inputs.append(
            {
                "filesystem": filesystem,
                "evaluation": evaluation_path.as_posix(),
                "reports": reports_path.as_posix(),
                "analysis_root": analysis_root,
                "evaluation_schema": summary.get("schema_version"),
            }
        )
        for report in report_dicts:
            if report.get("kind") != "METADATA_RESIDUAL_UNKNOWN":
                continue
            row = _unknown_report_row(
                report,
                filesystem=filesystem,
                analysis_root=analysis_root,
                oracle_by_location=oracle_by_location,
                audit_by_id=audit_by_id,
                source_index=source_index,
                known_functions=known_functions,
            )
            unknown_rows.append(row)
            _accumulate_blockers(blocker_accumulators, row)

    blockers = [_finalize_blocker(item) for item in blocker_accumulators.values()]
    blockers.sort(
        key=lambda item: (
            -int(item["sole_gap_report_count"]),
            -int(item["report_count"]),
            -int(item["mention_count"]),
            str(item["proof_gap"]),
            str(item["category"]),
            str(item["detail"]),
        )
    )
    proof_gaps = _proof_gap_rows(unknown_rows, blockers)
    oracle_constraints = _oracle_constraint_rows(oracle, audit_by_id)
    decision_surface = _decision_surface(proof_gaps, oracle_constraints)
    gap_cardinality = Counter(len(row["proof_gaps"]) for row in unknown_rows)

    return {
        "schema_version": SEMANTIC_BLOCKER_IMPACT_SCHEMA_VERSION,
        "measurement_only": True,
        "non_interference_contract": (
            "This artifact ranks missing evidence only; it must not change analyzer "
            "classification, suppression, effect identity, or oracle verdicts."
        ),
        "inputs": inputs,
        "source_definition_index": (
            source_index.to_dict() if source_index is not None else None
        ),
        "summary": {
            "evaluation_reports": total_reports,
            "unknown_reports": len(unknown_rows),
            "unknown_cause_mentions": sum(len(row["causes"]) for row in unknown_rows),
            "unknown_single_cause_reports": sum(
                len(row["causes"]) == 1 for row in unknown_rows
            ),
            "unknown_sole_gap_reports": sum(
                len(row["proof_gaps"]) == 1 for row in unknown_rows
            ),
            "unknown_multi_gap_reports": sum(
                len(row["proof_gaps"]) > 1 for row in unknown_rows
            ),
            "unknown_gap_cardinality_counts": {
                str(key): value for key, value in sorted(gap_cardinality.items())
            },
            "oracle_records": len(oracle),
            "oracle_reached": sum(
                item.get("status") == "EXPECTED_STATE_REACHED"
                for item in audit_by_id.values()
            ),
            "oracle_pending": sum(
                item.get("status") == "RETAINED_FOR_LATER_MILESTONE"
                for item in audit_by_id.values()
            ),
            "oracle_safety_regressions": sum(
                item.get("status") == "SAFETY_REGRESSION"
                for item in audit_by_id.values()
            ),
            "unknown_oracle_covered_reports": sum(
                bool(row["oracle_ids"]) for row in unknown_rows
            ),
            "unknown_oracle_ambiguous_reports": sum(
                row["oracle_linkage_status"] == "AMBIGUOUS_LOCATION"
                for row in unknown_rows
            ),
            "known_witness_unknown_reports": sum(
                bool(row["known_witness_involvement"]) for row in unknown_rows
            ),
        },
        "decision_surface": decision_surface,
        "oracle_pending_constraints": oracle_constraints,
        "unknown_proof_gaps": proof_gaps,
        "blockers": blockers,
        "unknown_reports": unknown_rows,
    }


def write_semantic_blocker_impact(
    impact: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "semantic_blocker_impact.json"
    markdown_path = destination / "semantic_blocker_impact.md"
    json_path.write_text(
        json.dumps(impact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(
        semantic_blocker_impact_to_markdown(impact),
        encoding="utf-8",
    )
    return {"json": json_path, "markdown": markdown_path}


def semantic_blocker_impact_to_markdown(impact: dict[str, Any]) -> str:
    summary = _mapping(impact.get("summary"))
    lines = [
        "# Semantic Blocker Impact Profile",
        "",
        "This is a measurement-only artifact. Counts from overlapping populations are not additive.",
        "",
        f"- UNKNOWN reports: `{summary.get('unknown_reports', 0)}`",
        f"- UNKNOWN cause mentions: `{summary.get('unknown_cause_mentions', 0)}`",
        f"- Sole-gap UNKNOWN reports: `{summary.get('unknown_sole_gap_reports', 0)}`",
        f"- Multi-gap UNKNOWN reports: `{summary.get('unknown_multi_gap_reports', 0)}`",
        f"- Oracle reached / pending: `{summary.get('oracle_reached', 0)}` / `{summary.get('oracle_pending', 0)}`",
        "",
        "## Decision Surface",
        "",
        "| Constraint | Population | Reports | Sole blocker | Oracle covered | Source available | Tier |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in _sequence(impact.get("decision_surface")):
        lines.append(
            "| "
            f"{_md(row.get('constraint_id', ''))} | {_md(row.get('population', ''))} | "
            f"{row.get('report_count', 0)} | {row.get('sole_blocker_report_count', 0)} | "
            f"{row.get('oracle_covered_report_count', 0)} | "
            f"{row.get('source_available_report_count', 0)} | "
            f"{_md(row.get('priority_tier', ''))} |"
        )
    lines.extend(
        [
            "",
            "## UNKNOWN Proof Gaps",
            "",
            "| Proof gap | Reports | Mentions | Sole gap | Multi gap | Filesystems |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in _sequence(impact.get("unknown_proof_gaps")):
        lines.append(
            "| "
            f"{_md(row.get('proof_gap', ''))} | {row.get('report_count', 0)} | "
            f"{row.get('mention_count', 0)} | {row.get('sole_gap_report_count', 0)} | "
            f"{row.get('multi_gap_report_count', 0)} | {row.get('filesystem_count', 0)} |"
        )
    lines.extend(
        [
            "",
            "## Top Blockers",
            "",
            "| Proof gap | Category | Detail | Reports | Sole gap | Body availability |",
            "|---|---|---|---:|---:|---|",
        ]
    )
    for row in _sequence(impact.get("blockers"))[:30]:
        availability = ", ".join(
            f"{key}={value}"
            for key, value in _mapping(row.get("body_availability_counts")).items()
        )
        lines.append(
            "| "
            f"{_md(row.get('proof_gap', ''))} | {_md(row.get('category', ''))} | "
            f"{_md(row.get('detail', ''))} | {row.get('report_count', 0)} | "
            f"{row.get('sole_gap_report_count', 0)} | {_md(availability)} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def _unknown_report_row(
    report: dict[str, Any],
    *,
    filesystem: str,
    analysis_root: str,
    oracle_by_location: dict[tuple[object, ...], list[dict[str, Any]]],
    audit_by_id: dict[str, dict[str, Any]],
    source_index: SourceDefinitionIndex | None,
    known_functions: set[str],
) -> dict[str, Any]:
    residual_slice = _mapping(report.get("residual_slice"))
    failure_site = _site(residual_slice.get("failure_site"))
    exit_site = _site(residual_slice.get("exit_site"))
    location = {
        "filesystem": filesystem,
        "function": str(report.get("function", "")),
        "failure_site": failure_site,
        "exit_site": exit_site,
    }
    oracle_records, linkage_status, candidate_ids = _matching_oracle_records(
        report,
        oracle_by_location.get(_location_key(location), []),
    )
    oracle_ids = sorted(
        str(item.get("oracle_id", ""))
        for item in oracle_records
        if str(item.get("oracle_id", ""))
    )
    audits = [audit_by_id.get(oracle_id, {}) for oracle_id in oracle_ids]
    causes = [str(item) for item in _sequence(report.get("unknown_causes")) if str(item)]
    proof_gaps = sorted({unknown_cause_proof_gap(cause) for cause in causes})
    blockers = []
    for cause in causes:
        category = unknown_cause_category(cause)
        detail = _cause_detail(cause, category)
        proof_gap = unknown_cause_proof_gap(cause)
        subject = _body_subject(proof_gap, detail)
        availability, definitions = _body_availability(
            proof_gap,
            subject,
            failure_file=str(failure_site.get("file", "")),
            analysis_root=analysis_root,
            source_index=source_index,
        )
        blockers.append(
            {
                "cause": cause,
                "proof_gap": proof_gap,
                "category": category,
                "detail": detail,
                "subject": subject,
                "body_availability": availability,
                "definitions": definitions,
            }
        )
    function = str(report.get("function", ""))
    return {
        "stable_location_key": _stable_hash(location),
        "filesystem": filesystem,
        "function": function,
        "classification": str(report.get("classification", report.get("kind", ""))),
        "failure_site": failure_site,
        "exit_site": exit_site,
        "causes": causes,
        "proof_gaps": proof_gaps,
        "sole_cause": len(causes) == 1,
        "sole_gap": len(proof_gaps) == 1,
        "blockers": blockers,
        "oracle_id": oracle_ids[0] if len(oracle_ids) == 1 else "",
        "oracle_ids": oracle_ids,
        "oracle_linkage_status": linkage_status,
        "oracle_candidate_ids": candidate_ids,
        "oracle_expected_final_states": _distinct_values(
            oracle_records, "expected_final_state"
        ),
        "oracle_manual_classes": _distinct_values(oracle_records, "manual_class"),
        "oracle_root_cause_families": _distinct_values(
            oracle_records, "root_cause_family"
        ),
        "oracle_statuses": _distinct_values(audits, "status"),
        "oracle_pending_reasons": _distinct_values(audits, "reason"),
        "known_witness_involvement": (
            function in known_functions
            or any(bool(item.get("related_finding")) for item in oracle_records)
        ),
    }


def _matching_oracle_records(
    report: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str, list[str]]:
    candidate_ids = sorted(
        str(item.get("oracle_id", ""))
        for item in candidates
        if str(item.get("oracle_id", ""))
    )
    if not candidates:
        return [], "NO_LOCATION_MATCH", []

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        stable_report = _mapping(candidate.get("stable_report"))
        group_key = str(candidate.get("stable_key", "")) or _stable_hash(
            stable_report
        )
        groups[group_key].append(candidate)
    if len(groups) == 1:
        records = next(iter(groups.values()))
        status = "MATCHED_DUPLICATE_RECORDS" if len(records) > 1 else "MATCHED_LOCATION"
        return records, status, candidate_ids

    residual_slice = _mapping(report.get("residual_slice"))
    current_effects = _sequence(residual_slice.get("residuals"))
    if not current_effects:
        current_effects = _sequence(residual_slice.get("reaching_effects"))
    current_keys = {_effect_key(item) for item in current_effects}
    if not current_keys:
        return [], "AMBIGUOUS_LOCATION", candidate_ids

    scores: dict[str, tuple[int, int, int]] = {}
    for group_key, records in groups.items():
        stable_report = _mapping(records[0].get("stable_report"))
        old_keys = {
            _effect_key(item)
            for item in _sequence(stable_report.get("residual_effects"))
        }
        overlap = len(old_keys & current_keys)
        scores[group_key] = (
            int(old_keys == current_keys),
            overlap,
            -len(old_keys ^ current_keys),
        )
    best_score = max(scores.values())
    best_groups = [key for key, score in scores.items() if score == best_score]
    if best_score[1] == 0 or len(best_groups) != 1:
        return [], "AMBIGUOUS_LOCATION", candidate_ids
    return groups[best_groups[0]], "MATCHED_EFFECTS", candidate_ids


def _effect_key(value: Any) -> str:
    source = _mapping(value)
    identity = {
        "root": str(source.get("root", "")),
        "key": str(source.get("key", "")),
        "plane": str(source.get("plane", "")),
        "delta": str(source.get("delta", "")),
        "value": str(source.get("value", "")),
        "site": _site(source.get("site")),
    }
    return json.dumps(identity, sort_keys=True, separators=(",", ":"))


def _distinct_values(items: Iterable[dict[str, Any]], key: str) -> list[str]:
    return sorted(
        {
            str(item.get(key, ""))
            for item in items
            if str(item.get(key, ""))
        }
    )


def _accumulate_blockers(
    accumulators: dict[tuple[str, str, str], dict[str, Any]],
    row: dict[str, Any],
) -> None:
    report_key = str(row["stable_location_key"])
    for blocker in row["blockers"]:
        key = (
            str(blocker["proof_gap"]),
            str(blocker["category"]),
            str(blocker["detail"]),
        )
        item = accumulators.setdefault(
            key,
            {
                "proof_gap": key[0],
                "category": key[1],
                "detail": key[2],
                "subject": blocker["subject"],
                "mention_count": 0,
                "report_keys": set(),
                "sole_cause_keys": set(),
                "sole_gap_keys": set(),
                "filesystems": set(),
                "functions": Counter(),
                "oracle_ids": set(),
                "oracle_report_keys": set(),
                "expected_destinations": Counter(),
                "manual_classes": Counter(),
                "body_availability": Counter(),
                "definition_locations": {},
                "known_witness_keys": set(),
            },
        )
        item["mention_count"] += 1
        if report_key in item["report_keys"]:
            continue
        item["report_keys"].add(report_key)
        if row["sole_cause"]:
            item["sole_cause_keys"].add(report_key)
        if row["sole_gap"]:
            item["sole_gap_keys"].add(report_key)
        item["filesystems"].add(row["filesystem"])
        item["functions"][row["function"]] += 1
        if row["oracle_ids"]:
            item["oracle_report_keys"].add(report_key)
            item["oracle_ids"].update(row["oracle_ids"])
            for destination in row["oracle_expected_final_states"]:
                item["expected_destinations"][destination] += 1
            for manual_class in row["oracle_manual_classes"]:
                item["manual_classes"][manual_class] += 1
        item["body_availability"][blocker["body_availability"]] += 1
        for definition in blocker["definitions"]:
            location_key = f"{definition['file']}:{definition['line']}"
            item["definition_locations"][location_key] = definition
        if row["known_witness_involvement"]:
            item["known_witness_keys"].add(report_key)


def _finalize_blocker(item: dict[str, Any]) -> dict[str, Any]:
    filesystems = sorted(item["filesystems"])
    return {
        "proof_gap": item["proof_gap"],
        "category": item["category"],
        "detail": item["detail"],
        "subject": item["subject"],
        "mention_count": item["mention_count"],
        "report_count": len(item["report_keys"]),
        "sole_cause_report_count": len(item["sole_cause_keys"]),
        "sole_gap_report_count": len(item["sole_gap_keys"]),
        "filesystems": filesystems,
        "filesystem_count": len(filesystems),
        "cross_filesystem_reuse": len(filesystems) > 1,
        "top_functions": [
            {"function": name, "report_count": count}
            for name, count in item["functions"].most_common(10)
        ],
        "oracle_covered_report_count": len(item["oracle_report_keys"]),
        "oracle_ids": sorted(item["oracle_ids"]),
        "expected_destination_counts": dict(sorted(item["expected_destinations"].items())),
        "manual_class_counts": dict(sorted(item["manual_classes"].items())),
        "potential_destination": (
            "ORACLE_VALIDATED"
            if item["oracle_ids"]
            else "UNREVIEWED_DESTINATION_UNKNOWN"
        ),
        "body_availability_counts": dict(sorted(item["body_availability"].items())),
        "definition_locations": [
            item["definition_locations"][key]
            for key in sorted(item["definition_locations"])
        ],
        "known_witness_report_count": len(item["known_witness_keys"]),
    }


def _proof_gap_rows(
    reports: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    gaps = sorted({gap for report in reports for gap in report["proof_gaps"]})
    rows = []
    for gap in gaps:
        matching = [report for report in reports if gap in report["proof_gaps"]]
        matching_blockers = [item for item in blockers if item["proof_gap"] == gap]
        available_keys = {
            report["stable_location_key"]
            for report in matching
            if any(
                blocker["proof_gap"] == gap
                and blocker["body_availability"] in SOURCE_AVAILABLE_STATES
                for blocker in report["blockers"]
            )
        }
        expected = Counter(
            destination
            for report in matching
            for destination in report["oracle_expected_final_states"]
        )
        filesystems = sorted({report["filesystem"] for report in matching})
        rows.append(
            {
                "proof_gap": gap,
                "report_count": len(matching),
                "mention_count": sum(
                    blocker["mention_count"] for blocker in matching_blockers
                ),
                "sole_gap_report_count": sum(report["proof_gaps"] == [gap] for report in matching),
                "multi_gap_report_count": sum(len(report["proof_gaps"]) > 1 for report in matching),
                "oracle_covered_report_count": sum(bool(report["oracle_ids"]) for report in matching),
                "expected_destination_counts": dict(sorted(expected.items())),
                "source_available_report_count": len(available_keys),
                "known_witness_report_count": sum(
                    bool(report["known_witness_involvement"]) for report in matching
                ),
                "filesystems": filesystems,
                "filesystem_count": len(filesystems),
                "top_blockers": matching_blockers[:10],
            }
        )
    return sorted(
        rows,
        key=lambda item: (
            -int(item["sole_gap_report_count"]),
            -int(item["report_count"]),
            str(item["proof_gap"]),
        ),
    )


def _oracle_constraint_rows(
    oracle_records: list[dict[str, Any]],
    audit_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    records_by_id = {str(item.get("oracle_id", "")): item for item in oracle_records}
    groups: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for oracle_id, transition in audit_by_id.items():
        if transition.get("status") != "RETAINED_FOR_LATER_MILESTONE":
            continue
        groups[str(transition.get("reason", "unknown"))].append(
            (records_by_id.get(oracle_id, {}), transition)
        )
    rows = []
    for reason, pairs in groups.items():
        expected = Counter(
            str(record.get("expected_final_state", transition.get("expected_final_state", "")))
            for record, transition in pairs
        )
        manual = Counter(str(record.get("manual_class", "")) for record, _ in pairs)
        roots = Counter(str(record.get("root_cause_family", "")) for record, _ in pairs)
        filesystems = {
            str(_mapping(record.get("stable_report")).get("filesystem", ""))
            for record, _ in pairs
        }
        rows.append(
            {
                "constraint": reason,
                "report_count": len(pairs),
                "expected_destination_counts": dict(sorted(expected.items())),
                "manual_class_counts": dict(sorted(manual.items())),
                "root_cause_family_counts": dict(sorted(roots.items())),
                "filesystem_count": len(filesystems - {""}),
                "oracle_ids": sorted(
                    str(record.get("oracle_id", "")) for record, _ in pairs
                ),
            }
        )
    return sorted(rows, key=lambda item: (-int(item["report_count"]), str(item["constraint"])))


def _decision_surface(
    proof_gaps: list[dict[str, Any]],
    oracle_constraints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = [
        {
            "constraint_id": f"ORACLE:{item['constraint']}",
            "population": "ORACLE_PENDING",
            "report_count": item["report_count"],
            "sole_blocker_report_count": item["report_count"],
            "oracle_covered_report_count": item["report_count"],
            "source_available_report_count": 0,
            "expected_destination_counts": item["expected_destination_counts"],
            "filesystem_count": item["filesystem_count"],
            "priority_tier": "ORACLE_VALIDATED_PENDING",
        }
        for item in oracle_constraints
    ]
    for item in proof_gaps:
        oracle_count = int(item["oracle_covered_report_count"])
        sole_count = int(item["sole_gap_report_count"])
        rows.append(
            {
                "constraint_id": f"UNKNOWN:{item['proof_gap']}",
                "population": "UNKNOWN_REPORTS",
                "report_count": item["report_count"],
                "sole_blocker_report_count": sole_count,
                "oracle_covered_report_count": oracle_count,
                "source_available_report_count": item["source_available_report_count"],
                "expected_destination_counts": item["expected_destination_counts"],
                "filesystem_count": item["filesystem_count"],
                "priority_tier": (
                    "ORACLE_VALIDATED_PENDING"
                    if oracle_count
                    else "UNREVIEWED_SOLE_BLOCKER"
                    if sole_count
                    else "MULTI_BLOCKER_ONLY"
                ),
            }
        )
    tier_order = {
        "ORACLE_VALIDATED_PENDING": 0,
        "UNREVIEWED_SOLE_BLOCKER": 1,
        "MULTI_BLOCKER_ONLY": 2,
    }
    return sorted(
        rows,
        key=lambda item: (
            tier_order[str(item["priority_tier"])],
            -int(item["oracle_covered_report_count"]),
            -int(item["sole_blocker_report_count"]),
            -int(item["report_count"]),
            str(item["constraint_id"]),
        ),
    )


def _body_subject(proof_gap: str, detail: str) -> str:
    if proof_gap == INDIRECT_TARGET_SET_UNPROVEN:
        return detail
    if proof_gap != SUMMARY_BODY_UNAVAILABLE:
        return ""
    return detail if re.fullmatch(r"[A-Za-z_]\w*", detail) else ""


def _body_availability(
    proof_gap: str,
    subject: str,
    *,
    failure_file: str,
    analysis_root: str,
    source_index: SourceDefinitionIndex | None,
) -> tuple[str, list[dict[str, object]]]:
    if proof_gap == INDIRECT_TARGET_SET_UNPROVEN:
        return INDIRECT_TARGET_BODY_UNKNOWN, []
    if proof_gap != SUMMARY_BODY_UNAVAILABLE:
        return NOT_APPLICABLE, []
    if not subject:
        return NO_EXACT_DEFINITION, []
    if source_index is None:
        return SOURCE_INDEX_UNAVAILABLE, []
    definitions = list(source_index.definitions.get(subject, ()))
    serialized = [item.to_dict() for item in definitions]
    if not definitions:
        if subject in source_index.macros:
            return MACRO_OR_CONDITIONAL_BODY, []
        return NO_EXACT_DEFINITION, []
    same_file = [item for item in definitions if _same_path(item.file, failure_file)]
    if len(same_file) == 1:
        return BODY_IN_CALLER_TRANSLATION_UNIT, [same_file[0].to_dict()]
    if len(definitions) > 1:
        return MULTIPLE_DEFINITIONS, serialized
    definition = definitions[0]
    if definition.in_header:
        return HEADER_INLINE_NOT_LOADED, serialized
    if analysis_root and _path_within(definition.file, analysis_root):
        return BODY_IN_ANALYSIS_ROOT, serialized
    return BODY_OUTSIDE_ANALYSIS_ROOT, serialized


def _cause_detail(cause: str, category: str) -> str:
    text = cause.strip()
    for prefix in (
        "unresolved metadata helper on error path:",
        "indirect call on error path:",
    ):
        if text.startswith(prefix):
            return text.split(":", 1)[1].strip() or category
    detail = text.split(": ", 1)[1] if ": " in text else text
    if ":" in detail:
        label, value = detail.split(":", 1)
        if unknown_cause_category(label) == category:
            return value.strip() or label.strip()
    if unknown_cause_category(detail) == category and ": " in text:
        return text.split(": ", 1)[0].strip()
    return detail.strip() or category


def _filesystem_from_summary(summary: dict[str, Any]) -> str:
    source_path = str(summary.get("source_path", ""))
    match = re.search(r"(?:^|[\\/])(btrfs|ext4|xfs|f2fs)(?:[\\/]|$)", source_path)
    return match.group(1) if match else "unknown"


def _location_key(value: dict[str, Any]) -> tuple[object, ...]:
    failure = _site(value.get("failure_site"))
    exit_site = _site(value.get("exit_site"))
    return (
        str(value.get("filesystem", "")),
        str(value.get("function", "")),
        failure["file"],
        failure["line"],
        failure["expression"],
        exit_site["file"],
        exit_site["line"],
        exit_site["expression"],
    )


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _site(value: Any) -> dict[str, object]:
    source = _mapping(value)
    return {
        "file": str(source.get("file", "")),
        "line": source.get("line", ""),
        "expression": str(source.get("expression", "")),
    }


def _path_within(path: str, root: str) -> bool:
    path_value = Path(path).as_posix().rstrip("/")
    root_value = Path(root).as_posix().rstrip("/")
    return path_value == root_value or path_value.startswith(f"{root_value}/")


def _same_path(left: str, right: str) -> bool:
    return Path(left).as_posix().lower() == Path(right).as_posix().lower()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sequence(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
