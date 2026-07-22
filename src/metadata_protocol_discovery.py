"""Directory-level semantic discovery for MOCC-SE metadata protocols."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .cfg import build_cfg
from .frontend.model import FunctionIR
from .frontend.tree_sitter_frontend import TreeSitterFrontend
from .metadata_confirmed_bug_linkage import parse_confirmed_bugs_markdown
from .metadata_event import MetadataEvent, extract_metadata_events
from .metadata_protocol import EffectTransition, MetadataProtocol
from .metadata_protocol_analyzer import ProtocolAnalysisResult, analyze_function


DISCOVERY_SCHEMA_VERSION = 5
DEFAULT_CONFIRMED_BUGS = (
    Path(__file__).resolve().parents[1] / "outputs" / "confirmed_bugs.md"
)

_BROAD_NON_FALLIBLE_CALLEES = frozenset(
    {
        "BTRFS_I",
        "READ_ONCE",
        "WRITE_ONCE",
        "btrfs_csum_root",
        "btrfs_sb",
        "clamp",
        "container_of",
        "dir_emit",
        "find_next_block_group",
        "list_to_workspace",
        "max",
        "min",
        "num_online_cpus",
        "time_after",
        "time_after_eq",
        "time_before",
        "time_before_eq",
    }
)
_BROAD_NON_FALLIBLE_PREFIXES = (
    "atomic_",
    "btrfs_fs_",
    "btrfs_is_",
    "btrfs_num_",
    "btrfs_stack_",
    "btrfs_test_",
    "ext4_test_",
    "hlist_",
    "list_",
    "rb_",
    "refcount_",
    "xfs_has_",
)


@dataclass(frozen=True)
class ApplicabilityEvidence:
    operation_id: str
    match_kind: str
    matched_role_ids: tuple[str, ...]
    matched_effect_ids: tuple[str, ...]
    matched_compensation_ids: tuple[str, ...]
    matched_handler_ids: tuple[str, ...]
    unmatched_required_role_ids: tuple[str, ...]
    matched_discovery_callees: tuple[str, ...]
    matched_discovery_fields: tuple[str, ...]
    unmatched_discovery_callees: tuple[str, ...]
    relaxed_terminal_discovery_callees: tuple[str, ...]
    unmatched_discovery_fields: tuple[str, ...]
    forbidden_discovery_callees: tuple[str, ...]
    unique_anchor_ids: tuple[str, ...]
    minimum_role_coverage: float = 0.5

    @property
    def semantic_anchor_count(self) -> int:
        return (
            len(self.matched_role_ids)
            + len(self.matched_effect_ids)
            + len(self.matched_compensation_ids)
            + len(self.matched_handler_ids)
            + len(self.matched_discovery_callees)
            + len(self.matched_discovery_fields)
        )

    @property
    def required_role_coverage(self) -> float:
        role_count = len(self.matched_role_ids)
        required_count = role_count + len(self.unmatched_required_role_ids)
        return role_count / required_count if required_count else 0.0

    @property
    def applicable(self) -> bool:
        if self.match_kind == "exact_entry":
            return True
        if self.forbidden_discovery_callees:
            return False
        if self.unmatched_discovery_callees or self.unmatched_discovery_fields:
            return False
        role_count = len(self.matched_role_ids)
        supporting_count = (
            len(self.matched_effect_ids)
            + len(self.matched_compensation_ids)
            + len(self.matched_handler_ids)
            + len(self.matched_discovery_callees)
            + len(self.matched_discovery_fields)
        )
        return bool(self.unique_anchor_ids) and (
            (
                role_count >= 2
                and self.required_role_coverage >= self.minimum_role_coverage
            )
            or (role_count >= 1 and supporting_count >= 1)
            or (
                role_count == 0
                and self.matched_effect_ids
                and (
                    self.matched_discovery_callees
                    or self.matched_discovery_fields
                )
            )
        )

    def score(self) -> tuple[int, int, int, int, int, int, int]:
        return (
            1 if self.match_kind == "exact_entry" else 0,
            len(self.unique_anchor_ids),
            self.semantic_anchor_count,
            -len(self.unmatched_required_role_ids),
            -len(self.unmatched_discovery_callees),
            -len(self.relaxed_terminal_discovery_callees),
            -len(self.unmatched_discovery_fields),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "match_kind": self.match_kind,
            "matched_role_ids": list(self.matched_role_ids),
            "matched_effect_ids": list(self.matched_effect_ids),
            "matched_compensation_ids": list(self.matched_compensation_ids),
            "matched_handler_ids": list(self.matched_handler_ids),
            "unmatched_required_role_ids": list(self.unmatched_required_role_ids),
            "matched_discovery_callees": list(self.matched_discovery_callees),
            "matched_discovery_fields": list(self.matched_discovery_fields),
            "unmatched_discovery_callees": list(self.unmatched_discovery_callees),
            "relaxed_terminal_discovery_callees": list(
                self.relaxed_terminal_discovery_callees
            ),
            "unmatched_discovery_fields": list(self.unmatched_discovery_fields),
            "forbidden_discovery_callees": list(self.forbidden_discovery_callees),
            "unique_anchor_ids": list(self.unique_anchor_ids),
            "semantic_anchor_count": self.semantic_anchor_count,
            "required_role_coverage": self.required_role_coverage,
            "minimum_role_coverage": self.minimum_role_coverage,
        }


@dataclass(frozen=True)
class DiscoveryAnalysis:
    applicability: ApplicabilityEvidence
    result: ProtocolAnalysisResult
    candidate_records: tuple[dict[str, Any], ...]
    review_records: tuple[dict[str, Any], ...]
    unknown_records: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        payload = self.result.to_dict()
        payload["applicability"] = self.applicability.to_dict()
        payload["candidates"] = list(self.candidate_records)
        payload["discovery_review"] = list(self.review_records)
        payload["unknown"] = list(self.unknown_records)
        return payload


@dataclass(frozen=True)
class DiscoveryQuarantine:
    protocol_id: str
    source_file: str
    function: str
    reason: str
    competing_operations: tuple[ApplicabilityEvidence, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": "DISCOVERY_UNKNOWN",
            "protocol_id": self.protocol_id,
            "source_file": self.source_file,
            "function": self.function,
            "reason": self.reason,
            "competing_operations": [
                item.to_dict() for item in self.competing_operations
            ],
        }


@dataclass(frozen=True)
class BroadDiscoveryReview:
    protocol_id: str
    source_file: str
    source_version: str
    filesystem: str
    function: str
    semantic_pattern: str
    semantic_signals: tuple[str, ...]
    representative_witness: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        root_cause = _stable_id(
            "root_cause",
            self.protocol_id,
            self.semantic_pattern,
            self.semantic_signals,
        )
        return {
            "classification": "DISCOVERY_REVIEW",
            "protocol_id": self.protocol_id,
            "operation_id": "",
            "source_file": self.source_file,
            "source_version": self.source_version,
            "filesystem": self.filesystem,
            "function": self.function,
            "applicability_match_kind": "broad_semantic",
            "semantic_pattern": self.semantic_pattern,
            "semantic_signals": list(self.semantic_signals),
            "review_reason": "broad_semantic_pattern_requires_protocol_review",
            "representative_witness": list(self.representative_witness),
            "root_cause_fingerprint": root_cause,
            "family_fingerprint": _stable_id(
                "family", self.function, root_cause
            ),
            "occurrence_fingerprint": _stable_id(
                "occurrence",
                self.source_file,
                self.function,
                root_cause,
            ),
        }


@dataclass(frozen=True)
class ProtocolDiscoveryReport:
    source_root: str
    source_version: str
    protocol_ids: tuple[str, ...]
    protocol_versions: tuple[str, ...]
    scanned_files: int
    scanned_functions: int
    analyses: tuple[DiscoveryAnalysis, ...]
    broad_reviews: tuple[BroadDiscoveryReview, ...]
    quarantine: tuple[DiscoveryQuarantine, ...]
    excluded_functions: tuple[str, ...]
    skip_reasons: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, Any]:
        candidates = [
            item for analysis in self.analyses for item in analysis.candidate_records
        ]
        review = [
            item for analysis in self.analyses for item in analysis.review_records
        ]
        review.extend(item.to_dict() for item in self.broad_reviews)
        unknown = [
            item for analysis in self.analyses for item in analysis.unknown_records
        ]
        applicability_counts = Counter(
            item.applicability.match_kind for item in self.analyses
        )
        family_counts = Counter(item["family_fingerprint"] for item in candidates)
        review_family_counts = Counter(
            item["family_fingerprint"] for item in review
        )
        fresh_queue = _fresh_review_queue(review)
        return {
            "schema_version": DISCOVERY_SCHEMA_VERSION,
            "source_root": self.source_root,
            "source_version": self.source_version,
            "protocols": [
                {
                    "protocol_id": protocol_id,
                    "protocol_version": protocol_version,
                }
                for protocol_id, protocol_version in zip(
                    self.protocol_ids,
                    self.protocol_versions,
                )
            ],
            "summary": {
                "scanned_files": self.scanned_files,
                "scanned_functions": self.scanned_functions,
                "applicable_functions": len(self.analyses),
                "exact_entry_functions": applicability_counts["exact_entry"],
                "semantic_applicable_functions": applicability_counts["semantic"],
                "protocol_candidate_occurrences": len(candidates),
                "protocol_candidate_families": len(family_counts),
                "discovery_review_occurrences": len(review),
                "discovery_review_families": len(review_family_counts),
                "fresh_review_functions": len(
                    {item["function"] for item in fresh_queue}
                ),
                "fresh_review_root_causes": len(
                    {item["root_cause_fingerprint"] for item in fresh_queue}
                ),
                "fresh_review_queue_entries": len(fresh_queue),
                "excluded_functions": len(self.excluded_functions),
                "analysis_unknown": len(unknown),
                "discovery_unknown": len(self.quarantine),
                "skip_reasons": dict(self.skip_reasons),
            },
            "analyses": [item.to_dict() for item in self.analyses],
            "broad_discovery_review": [
                item.to_dict() for item in self.broad_reviews
            ],
            "quarantine": [item.to_dict() for item in self.quarantine],
            "excluded_function_names": list(self.excluded_functions),
            "fresh_review_queue": fresh_queue,
            "candidate_families": [
                {
                    "family_fingerprint": key,
                    "occurrences": family_counts[key],
                }
                for key in sorted(family_counts)
            ],
            "discovery_review_families": [
                {
                    "family_fingerprint": key,
                    "occurrences": review_family_counts[key],
                }
                for key in sorted(review_family_counts)
            ],
        }


def discover_source_tree(
    source_root: str | Path,
    protocols: Iterable[MetadataProtocol],
    *,
    source_version: str = "",
    include: Iterable[str] = ("*.c",),
    max_files: int | None = None,
    excluded_functions: Iterable[str] = (),
    exclude_regression_seeds: bool = False,
) -> ProtocolDiscoveryReport:
    root = Path(source_root).resolve()
    protocol_list = tuple(protocols)
    paths = _source_paths(root, include)
    if max_files is not None:
        paths = paths[:max_files]
    frontend = TreeSitterFrontend(source_root=root)
    analyses: list[DiscoveryAnalysis] = []
    broad_reviews: list[BroadDiscoveryReview] = []
    quarantine: list[DiscoveryQuarantine] = []
    skips: Counter[str] = Counter()
    scanned_functions = 0
    excluded = {item.strip() for item in excluded_functions if item.strip()}
    if exclude_regression_seeds:
        excluded.update(
            function
            for protocol in protocol_list
            for operation in protocol.operations
            for function in operation.entry_functions
        )

    for path in paths:
        unit = frontend.parse(path)
        for function in unit.functions:
            scanned_functions += 1
            filesystem = _filesystem_for_path(path)
            if function.name in excluded:
                skips["excluded_function"] += 1
                continue
            matched_any = False
            for protocol in protocol_list:
                if filesystem and filesystem not in protocol.filesystems:
                    skips["filesystem_not_applicable"] += 1
                    continue
                evidences = operation_applicability(function, protocol)
                applicable = [item for item in evidences if item.applicable]
                if not applicable:
                    broad = _broad_semantic_reviews(
                        function,
                        protocol,
                        root=root,
                        filesystem=filesystem,
                        source_version=source_version,
                    )
                    if broad:
                        matched_any = True
                        broad_reviews.extend(broad)
                    else:
                        skips["no_semantic_operation_match"] += 1
                    continue
                selected = _select_applicability(applicable)
                if selected is None:
                    matched_any = True
                    quarantine.append(
                        DiscoveryQuarantine(
                            protocol.protocol_id,
                            function.file.as_posix(),
                            function.name,
                            "ambiguous_operation_match",
                            tuple(
                                sorted(
                                    applicable,
                                    key=lambda item: item.operation_id,
                                )
                            ),
                        )
                    )
                    continue
                matched_any = True
                result = analyze_function(
                    function,
                    protocol,
                    operation_id=selected.operation_id,
                    source_version=source_version,
                )
                if result is None:
                    skips["analysis_not_started"] += 1
                    continue
                analyses.append(
                    _discovery_analysis(
                        root,
                        filesystem,
                        selected,
                        result,
                    )
                )
            if not matched_any:
                skips["function_not_applicable"] += 1

    return ProtocolDiscoveryReport(
        root.as_posix(),
        source_version,
        tuple(item.protocol_id for item in protocol_list),
        tuple(item.protocol_version for item in protocol_list),
        len(paths),
        scanned_functions,
        tuple(
            sorted(
                analyses,
                key=lambda item: (
                    item.result.source_file,
                    item.result.function,
                    item.result.protocol_id,
                ),
            )
        ),
        tuple(
            sorted(
                broad_reviews,
                key=lambda item: (
                    item.source_file,
                    item.function,
                    item.protocol_id,
                    item.semantic_pattern,
                ),
            )
        ),
        tuple(
            sorted(
                quarantine,
                key=lambda item: (
                    item.source_file,
                    item.function,
                    item.protocol_id,
                ),
            )
        ),
        tuple(sorted(excluded)),
        tuple(sorted(skips.items())),
    )


def operation_applicability(
    function: FunctionIR,
    protocol: MetadataProtocol,
) -> tuple[ApplicabilityEvidence, ...]:
    anchor_owners = _anchor_owners(protocol)
    evidences: list[ApplicabilityEvidence] = []
    for operation in protocol.operations:
        events = extract_metadata_events(
            function,
            protocol,
            operation_id=operation.operation_id,
        )
        matched_anchor_ids = _matched_anchor_ids(events)
        function_anchor_ids = _function_anchor_ids(function)
        discovery = operation.discovery
        matched_discovery_callees = tuple(
            sorted(
                callee
                for callee in discovery.required_callees
                if f"callee:{callee}" in function_anchor_ids
            )
        )
        matched_discovery_fields = tuple(
            sorted(
                field
                for field in discovery.required_fields
                if f"field:{field}" in function_anchor_ids
            )
        )
        forbidden_discovery_callees = tuple(
            sorted(
                callee
                for callee in discovery.forbidden_callees
                if f"callee:{callee}" in function_anchor_ids
            )
        )
        matched_roles = tuple(
            sorted({item.callee_role_id for item in events if item.callee_role_id})
        )
        matched_effects = tuple(
            sorted({item.effect_spec_id for item in events if item.effect_spec_id})
        )
        matched_compensations = tuple(
            sorted(
                {
                    item.compensation_spec_id
                    for item in events
                    if item.compensation_spec_id
                }
            )
        )
        matched_handlers = tuple(
            sorted({item.handler_spec_id for item in events if item.handler_spec_id})
        )
        terminal_discovery_callees = _terminal_discovery_callees(
            protocol,
            operation.operation_id,
        )
        open_discovery_callees = tuple(
            callee
            for callee in discovery.required_callees
            if callee not in terminal_discovery_callees
        )
        matched_open_discovery = tuple(
            callee
            for callee in matched_discovery_callees
            if callee in open_discovery_callees
        )
        relaxed_terminal_discovery_callees = tuple(
            sorted(
                set(terminal_discovery_callees)
                & set(discovery.required_callees)
                - set(matched_discovery_callees)
            )
            if matched_open_discovery
            else ()
        )
        required_roles = {
            item.role_id for item in operation.callee_roles if item.necessary
        }
        unique_anchors = tuple(
            sorted(
                anchor
                for anchor in (
                    matched_anchor_ids
                    | {f"callee:{callee}" for callee in matched_discovery_callees}
                    | {f"field:{field}" for field in matched_discovery_fields}
                )
                if anchor_owners.get(anchor) == {operation.operation_id}
            )
        )
        evidences.append(
            ApplicabilityEvidence(
                operation.operation_id,
                (
                    "exact_entry"
                    if function.name in operation.entry_functions
                    else "semantic"
                ),
                matched_roles,
                matched_effects,
                matched_compensations,
                matched_handlers,
                tuple(sorted(required_roles - set(matched_roles))),
                matched_discovery_callees,
                matched_discovery_fields,
                tuple(
                    sorted(
                        set(discovery.required_callees)
                        - set(matched_discovery_callees)
                        - set(relaxed_terminal_discovery_callees)
                    )
                ),
                relaxed_terminal_discovery_callees,
                tuple(
                    sorted(
                        set(discovery.required_fields)
                        - set(matched_discovery_fields)
                    )
                ),
                forbidden_discovery_callees,
                unique_anchors,
                discovery.minimum_role_coverage,
            )
        )
    return tuple(evidences)


def _terminal_discovery_callees(
    protocol: MetadataProtocol,
    operation_id: str,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                callee
                for summary in protocol.callee_summaries
                if summary.operation_id == operation_id
                and summary.transition is not EffectTransition.OPEN
                for callee in summary.callees
            }
        )
    )


def _select_applicability(
    evidences: list[ApplicabilityEvidence],
) -> ApplicabilityEvidence | None:
    ranked = sorted(
        evidences,
        key=lambda item: (item.score(), item.operation_id),
        reverse=True,
    )
    if len(ranked) == 1 or ranked[0].score() > ranked[1].score():
        return ranked[0]
    return None


def _anchor_owners(protocol: MetadataProtocol) -> dict[str, set[str]]:
    owners: dict[str, set[str]] = {}
    for operation in protocol.operations:
        for role in operation.callee_roles:
            for callee in role.callees:
                owners.setdefault(f"callee:{callee}", set()).add(
                    operation.operation_id
                )
        specs = (
            *(
                item
                for item in protocol.effects
                if item.operation_id == operation.operation_id
            ),
            *(
                item
                for item in protocol.compensations
                if item.operation_id == operation.operation_id
            ),
            *(
                item
                for item in protocol.handlers
                if item.operation_id == operation.operation_id
            ),
        )
        for spec in specs:
            for callee in getattr(spec, "match_callees", ()):
                owners.setdefault(f"callee:{callee}", set()).add(
                    operation.operation_id
                )
            for field in getattr(spec, "match_fields", ()):
                owners.setdefault(f"field:{field}", set()).add(
                    operation.operation_id
        )
        for callee in operation.discovery.required_callees:
            owners.setdefault(f"callee:{callee}", set()).add(operation.operation_id)
        for field in operation.discovery.required_fields:
            owners.setdefault(f"field:{field}", set()).add(operation.operation_id)
    return owners


def _matched_anchor_ids(events: tuple[MetadataEvent, ...]) -> set[str]:
    anchors: set[str] = set()
    for event in events:
        if event.callee:
            anchors.add(f"callee:{event.callee}")
        if event.field_or_member:
            anchors.add(f"field:{event.field_or_member}")
    return anchors


def _function_anchor_ids(function: FunctionIR) -> set[str]:
    anchors = {f"callee:{call.callee_spelling}" for call in function.calls}
    for access_path in function.access_paths:
        anchors.update(f"field:{field}" for field in access_path.fields)
    return anchors


def _discovery_analysis(
    root: Path,
    filesystem: str,
    applicability: ApplicabilityEvidence,
    result: ProtocolAnalysisResult,
) -> DiscoveryAnalysis:
    relative = _relative_source(result.source_file, root)
    records = _dedupe_records(
        _candidate_record(
            item.to_dict(),
            result,
            relative,
            filesystem,
        )
        for item in result.candidates
    )
    if applicability.match_kind == "exact_entry":
        candidates = records
        review: tuple[dict[str, Any], ...] = ()
    else:
        candidates = ()
        review = tuple(
            {
                **item,
                "classification": "DISCOVERY_REVIEW",
                "review_reason": "semantic_operation_applicability_requires_review",
            }
            for item in records
        )
    unknown = tuple(
        _unknown_record(
            item.to_dict(),
            result,
            relative,
            applicability.match_kind,
        )
        for item in result.unknown
    )
    return DiscoveryAnalysis(applicability, result, candidates, review, unknown)


def _candidate_record(
    candidate: dict[str, Any],
    result: ProtocolAnalysisResult,
    relative_source: str,
    filesystem: str,
) -> dict[str, Any]:
    events = {
        item["event_id"]: item
        for item in result.events
    }
    effect_ids = tuple(
        sorted(
            item.get("spec_effect_id", "")
            for item in candidate["open_effects"]
        )
    )
    failure_roles = []
    for failure in candidate["unresolved_failures"]:
        event = events.get(failure.get("source_event", ""), {})
        failure_roles.append(
            (
                event.get("callee_role_id", ""),
                event.get("callee", ""),
                failure.get("error_class", ""),
            )
        )
    structural = (
        result.protocol_id,
        result.operation_id,
        candidate["violation_type"],
        candidate["exit_kind"],
        candidate.get("return_provenance", ""),
        effect_ids,
        tuple(sorted(failure_roles)),
    )
    enriched = dict(candidate)
    enriched.update(
        {
            "classification": "PROTOCOL_CANDIDATE",
            "source_file": relative_source,
            "source_version": result.source_version,
            "filesystem": filesystem,
            "function": result.function,
            "family_fingerprint": _stable_id(
                "family",
                result.function,
                *structural,
            ),
            "occurrence_fingerprint": _stable_id(
                "occurrence",
                relative_source,
                result.function,
                *structural,
            ),
        }
    )
    return enriched


def _unknown_record(
    unknown: dict[str, Any],
    result: ProtocolAnalysisResult,
    relative_source: str,
    match_kind: str,
) -> dict[str, Any]:
    enriched = dict(unknown)
    if match_kind != "exact_entry":
        enriched["classification"] = "DISCOVERY_REVIEW_UNKNOWN"
    enriched.update(
        {
            "source_file": relative_source,
            "source_version": result.source_version,
            "function": result.function,
            "applicability_match_kind": match_kind,
            "unknown_fingerprint": _stable_id(
                "unknown",
                result.protocol_id,
                result.operation_id,
                relative_source,
                result.function,
                tuple(unknown.get("reasons", ())),
            ),
        }
    )
    return enriched


def _dedupe_records(
    records: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    selected: dict[str, dict[str, Any]] = {}
    for record in records:
        fingerprint = record["occurrence_fingerprint"]
        existing = selected.get(fingerprint)
        if existing is None or len(record["representative_witness"]) < len(
            existing["representative_witness"]
        ):
            selected[fingerprint] = record
    return tuple(selected[key] for key in sorted(selected))


def _broad_semantic_reviews(
    function: FunctionIR,
    protocol: MetadataProtocol,
    *,
    root: Path,
    filesystem: str,
    source_version: str,
) -> tuple[BroadDiscoveryReview, ...]:
    if function.body_node is None:
        return ()

    evidence = _broad_semantic_evidence(function)
    records: list[BroadDiscoveryReview] = []
    seen_patterns: set[str] = set()
    for operation in protocol.operations:
        if not _operation_discovery_context_matches(function, operation):
            continue
        context_terms = _operation_semantic_terms(operation, protocol)
        for pattern in operation.discovery.semantic_patterns:
            if pattern in seen_patterns:
                continue
            required = {
                "failure_return_mismatch": {
                    "fallible_call",
                    "failure_guard",
                    "failure_to_success_exit",
                    "success_exit",
                },
                "mutation_failure_cleanup": {
                    "fallible_call",
                    "failure_guard",
                    "state_mutation",
                    "failure_control",
                },
                "retry_return_provenance": {
                    "fallible_call",
                    "failure_guard",
                    "retry_control",
                    "state_mutation",
                },
                "conditional_accounting": {
                    "fallible_call",
                    "failure_guard",
                    "accounting_operation",
                    "multi_outcome_guard",
                    "state_mutation",
                },
            }[pattern]
            if not required.issubset(evidence):
                continue
            signal_names = tuple(
                sorted(required | ({"compensation"} & evidence.keys()))
            )
            witness = tuple(evidence[name] for name in signal_names)
            if context_terms and not _witness_mentions_any(witness, context_terms):
                continue
            seen_patterns.add(pattern)
            records.append(
                BroadDiscoveryReview(
                    protocol.protocol_id,
                    _relative_source(function.file.as_posix(), root),
                    source_version,
                    filesystem,
                    function.name,
                    pattern,
                    signal_names,
                    witness,
                )
            )
    return tuple(records)


def _operation_discovery_context_matches(
    function: FunctionIR,
    operation: Any,
) -> bool:
    anchors = _function_anchor_ids(function)
    discovery = operation.discovery
    return (
        all(f"callee:{callee}" in anchors for callee in discovery.required_callees)
        and all(f"field:{field}" in anchors for field in discovery.required_fields)
        and not any(
            f"callee:{callee}" in anchors for callee in discovery.forbidden_callees
        )
    )


def _operation_semantic_terms(
    operation: Any,
    protocol: MetadataProtocol,
) -> tuple[str, ...]:
    terms: set[str] = set()
    for role in operation.callee_roles:
        terms.update(role.callees)
    for field in operation.discovery.required_fields:
        terms.add(field)
    for callee in operation.discovery.required_callees:
        terms.add(callee)
    specs = (
        list(protocol.effects)
        + list(protocol.compensations)
        + list(protocol.handlers)
    )
    specs += [
        spec
        for spec in protocol.accounting_constraints
        if spec.operation_id == operation.operation_id
    ]
    for spec in specs:
        if getattr(spec, "operation_id", operation.operation_id) != operation.operation_id:
            continue
        for attr in (
            "match_callees",
            "match_fields",
            "match_arguments",
            "match_rhs",
            "match_results",
        ):
            terms.update(str(item) for item in getattr(spec, attr, ()))
    return tuple(sorted(_semantic_term(term) for term in terms if _semantic_term(term)))


def _semantic_term(term: str) -> str:
    normalized = term.strip().lower()
    if len(normalized) < 4:
        return ""
    if normalized in {"true", "false", "null", "none", "zero", "ret"}:
        return ""
    return normalized


def _witness_mentions_any(
    witness: Iterable[dict[str, Any]],
    terms: Iterable[str],
) -> bool:
    haystack = "\n".join(str(item.get("detail", "")).lower() for item in witness)
    return any(term in haystack for term in terms)


def _broad_semantic_evidence(
    function: FunctionIR,
) -> dict[str, dict[str, Any]]:
    nodes = tuple(function.body_node.walk()) if function.body_node else ()
    assignments = [
        item for item in _call_assignments(nodes) if _is_broad_fallible_call(item[1])
    ]
    cfg = build_cfg(function)
    guarded = _guarded_call_assignments(assignments, cfg)
    success_returns = [
        node
        for node in nodes
        if node.type == "return_statement"
        and re.fullmatch(r"return\s+(?:0|NULL|false)\s*;", node.text.strip())
    ]
    failure_controls = [
        node
        for node in nodes
        if (
            node.type == "goto_statement"
            or (
                node.type == "return_statement"
                and not re.fullmatch(
                    r"return\s+(?:0|NULL|false)\s*;", node.text.strip()
                )
            )
        )
    ]
    mutations = [
        node
        for node in nodes
        if node.type in {"assignment_expression", "update_expression"}
        and _is_state_mutation(node)
    ]
    calls = [node for node in nodes if node.type == "call_expression"]
    compensation_calls = [
        node
        for node in calls
        if _callee_has_keyword(
            node,
            ("abort", "cancel", "clear", "del", "detach", "drop", "free", "put", "release", "restore", "rollback", "undo"),
        )
    ]
    accounting_calls = [
        node
        for node in calls
        if _callee_has_keyword(
            node,
            ("account", "counter", "quota", "reserve", "reservation", "rsv"),
        )
    ]
    result_counts = Counter(symbol for symbol, _ in assignments)
    retry_assignments = [
        (symbol, node)
        for symbol, node in assignments
        if result_counts[symbol] > 1
    ]
    retry_controls = _backward_gotos(nodes)
    multi_outcome_guards = [
        (symbol, matching)
        for symbol in sorted({item[0] for item in guarded})
        if len(
            matching := {
                item[2].text.strip() for item in guarded if item[0] == symbol
            }
        )
        >= 2
    ]
    swallowed_paths = [
        (symbol, call_node, guard, success)
        for symbol, call_node, guard in guarded
        for success in success_returns
        if _failure_branch_reaches(cfg, guard.id, success.start_byte, symbol)
    ]

    evidence: dict[str, dict[str, Any]] = {}
    selected_guard = None
    selected_call = None
    if swallowed_paths:
        symbol, selected_call, selected_guard, _ = swallowed_paths[0]
    elif guarded:
        symbol, selected_call, selected_guard = guarded[0]
    else:
        symbol = ""
    if selected_call is not None:
        evidence["fallible_call"] = _signal_witness(
            "fallible_call",
            selected_call,
            f"{selected_call.text.strip()} assigned to {symbol}",
        )
    if selected_guard is not None:
        evidence["failure_guard"] = {
            "kind": "failure_guard",
            "line": selected_guard.start_line,
            "detail": selected_guard.text.strip(),
            "result_symbol": symbol,
        }
    if success_returns:
        node = success_returns[-1]
        evidence["success_exit"] = _signal_witness(
            "success_exit", node, node.text.strip()
        )
    if swallowed_paths:
        symbol, _, guard, success = swallowed_paths[0]
        evidence["failure_to_success_exit"] = {
            "kind": "failure_to_success_exit",
            "line": guard.start_line,
            "detail": f"failure branch for {symbol} reaches {success.text.strip()}",
        }
    relevant_failure_controls = [
        item
        for item in failure_controls
        if selected_guard is not None and item.start_byte >= selected_guard.start_byte
    ]
    if relevant_failure_controls:
        node = relevant_failure_controls[0]
        evidence["failure_control"] = _signal_witness(
            "failure_control", node, node.text.strip()
        )
    prior_mutations = [
        item
        for item in mutations
        if selected_call is not None and item.start_byte < selected_call.start_byte
        and _node_reaches(cfg, item.start_byte, selected_call.start_byte)
        and selected_guard is not None
        and not _mutation_restored_before_guard(item, nodes, selected_guard)
        and not _cleanup_occurs_between(
            compensation_calls, selected_call.start_byte, selected_guard.start_byte
        )
    ]
    if prior_mutations:
        node = prior_mutations[-1]
        evidence["state_mutation"] = _signal_witness(
            "state_mutation", node, node.text.strip()
        )
    if retry_assignments:
        symbol, node = retry_assignments[-1]
        evidence["retry_assignment"] = _signal_witness(
            "retry_assignment", node, f"result {symbol} assigned by multiple calls"
        )
    if retry_controls:
        node = retry_controls[0]
        evidence["retry_control"] = _signal_witness(
            "retry_control", node, node.text.strip()
        )
    if multi_outcome_guards:
        symbol, guards = multi_outcome_guards[0]
        evidence["multi_outcome_guard"] = {
            "kind": "multi_outcome_guard",
            "line": 0,
            "detail": f"{symbol} has distinct guarded outcomes: {', '.join(sorted(guards))}",
        }
    if compensation_calls:
        node = compensation_calls[0]
        evidence["compensation"] = _signal_witness(
            "compensation", node, node.text.strip()
        )
    if accounting_calls:
        node = accounting_calls[0]
        evidence["accounting_operation"] = _signal_witness(
            "accounting_operation", node, node.text.strip()
        )
    return evidence


def _call_assignments(nodes: Iterable[Any]) -> list[tuple[str, Any]]:
    assignments: list[tuple[str, Any]] = []
    for node in nodes:
        if node.type not in {"assignment_expression", "init_declarator"}:
            continue
        left = node.child_by_field_name("left") or node.child_by_field_name(
            "declarator"
        )
        right = node.child_by_field_name("right") or node.child_by_field_name(
            "value"
        )
        if left is None or right is None:
            continue
        calls = [item for item in right.walk() if item.type == "call_expression"]
        identifiers = re.findall(r"[A-Za-z_]\w*", left.text)
        if calls and identifiers:
            assignments.append((identifiers[-1], calls[0]))
    return assignments


def _guarded_call_assignments(
    assignments: Iterable[tuple[str, Any]],
    cfg: Any,
) -> list[tuple[str, Any, Any]]:
    ordered = sorted(assignments, key=lambda item: item[1].start_byte)
    guards = sorted(
        (
            block
            for block in cfg.blocks.values()
            if block.kind in {"condition", "loop_condition", "switch_condition"}
        ),
        key=lambda item: item.start_byte,
    )
    guarded: list[tuple[str, Any, Any]] = []
    for index, (symbol, call_node) in enumerate(ordered):
        next_assignment = min(
            (
                later_node.start_byte
                for later_symbol, later_node in ordered[index + 1 :]
                if later_symbol == symbol
            ),
            default=None,
        )
        matching = [
            guard
            for guard in guards
            if guard.start_byte >= call_node.start_byte
            and (next_assignment is None or guard.start_byte < next_assignment)
            and _mentions_identifier(guard.text, symbol)
            and _failure_edge_kind(guard.text, symbol) is not None
        ]
        if matching:
            guarded.append((symbol, call_node, matching[0]))
    return guarded


def _is_broad_fallible_call(node: Any) -> bool:
    callee = node.child_by_field_name("function")
    if callee is None:
        return False
    spelling = callee.text.strip()
    if spelling in _BROAD_NON_FALLIBLE_CALLEES:
        return False
    lowered = spelling.lower()
    return not lowered.startswith(_BROAD_NON_FALLIBLE_PREFIXES)


def _is_state_mutation(node: Any) -> bool:
    target_text = _mutation_target_text(node)
    return bool(target_text and any(token in target_text for token in ("->", ".", "[")))


def _mutation_target_text(node: Any) -> str:
    if node.type == "update_expression":
        target = node.child_by_field_name("argument")
        return (target.text if target is not None else node.text).strip()
    else:
        target = node.child_by_field_name("left")
        if target is None:
            return ""
        return target.text.strip()


def _mutation_restored_before_guard(
    mutation: Any,
    nodes: Iterable[Any],
    guard: Any,
) -> bool:
    target_text = _mutation_target_text(mutation)
    if not target_text:
        return False
    for node in nodes:
        if node is mutation:
            continue
        if node.type != "assignment_expression":
            continue
        if node.start_byte <= mutation.start_byte or node.start_byte >= guard.start_byte:
            continue
        if _mutation_target_text(node) == target_text:
            return True
    return False


def _cleanup_occurs_between(
    compensation_calls: Iterable[Any],
    start_byte: int,
    end_byte: int,
) -> bool:
    return any(start_byte < node.start_byte < end_byte for node in compensation_calls)


def _mentions_identifier(text: str, identifier: str) -> bool:
    return bool(re.search(rf"\b{re.escape(identifier)}\b", text))


def _backward_gotos(nodes: Iterable[Any]) -> list[Any]:
    labels: dict[str, int] = {}
    gotos: list[Any] = []
    for node in nodes:
        if node.type == "labeled_statement":
            label = node.child_by_field_name("label")
            if label is not None:
                labels[label.text.strip()] = node.start_byte
        elif node.type == "goto_statement":
            gotos.append(node)
    result = []
    for node in gotos:
        match = re.search(r"\bgoto\s+([A-Za-z_]\w*)", node.text)
        if match and labels.get(match.group(1), node.start_byte) < node.start_byte:
            result.append(node)
    return result


def _failure_branch_reaches(
    cfg: Any,
    guard_id: int,
    success_start_byte: int,
    symbol: str,
) -> bool:
    guard = cfg.blocks[guard_id]
    failure_edge_kind = _failure_edge_kind(guard.text, symbol)
    if failure_edge_kind is None:
        return False
    targets = [
        edge.target
        for edge in cfg.successors(guard_id)
        if edge.kind == failure_edge_kind
    ]
    success_blocks = {
        block.id
        for block in cfg.blocks.values()
        if block.start_byte == success_start_byte
    }
    pending = list(targets)
    seen: set[int] = set()
    while pending:
        block_id = pending.pop()
        if block_id in seen:
            continue
        if block_id in success_blocks:
            return True
        seen.add(block_id)
        pending.extend(edge.target for edge in cfg.successors(block_id))
    return False


def _node_reaches(cfg: Any, source_start_byte: int, target_start_byte: int) -> bool:
    source_blocks = _blocks_containing_byte(cfg, source_start_byte)
    target_blocks = _blocks_containing_byte(cfg, target_start_byte)
    if not source_blocks or not target_blocks:
        return True
    target_set = set(target_blocks)
    pending = list(source_blocks)
    seen: set[int] = set()
    while pending:
        block_id = pending.pop()
        if block_id in seen:
            continue
        if block_id in target_set:
            return True
        seen.add(block_id)
        pending.extend(edge.target for edge in cfg.successors(block_id))
    return False


def _blocks_containing_byte(cfg: Any, start_byte: int) -> list[int]:
    matches = []
    for block in cfg.blocks.values():
        if block.end_byte <= block.start_byte:
            continue
        if block.start_byte <= start_byte < block.end_byte:
            matches.append((block.end_byte - block.start_byte, block.id))
        elif block.condition_start_byte <= start_byte < block.condition_end_byte:
            matches.append((block.condition_end_byte - block.condition_start_byte, block.id))
    if not matches:
        return []
    smallest = min(width for width, _ in matches)
    return [block_id for width, block_id in matches if width == smallest]


def _failure_edge_kind(condition: str, symbol: str) -> str | None:
    compact = re.sub(r"\s+", "", condition)
    escaped = re.escape(symbol)
    if re.search(rf"(?:^|\()!{escaped}(?:\)|$)", compact) or re.search(
        rf"\b{escaped}==0\b", compact
    ):
        return "false"
    failure_forms = (
        rf"^\(*{escaped}\)*$",
        rf"\b{escaped}!=0\b",
        rf"\b{escaped}<=?-\d+\b",
        rf"\b{escaped}<0\b",
        rf"IS_ERR(?:_OR_NULL)?\({escaped}\)",
    )
    if any(re.search(pattern, compact) for pattern in failure_forms):
        return "true"
    return None


def _callee_has_keyword(node: Any, keywords: tuple[str, ...]) -> bool:
    callee = node.child_by_field_name("function")
    spelling = callee.text.lower() if callee is not None else node.text.lower()
    return any(keyword in spelling for keyword in keywords)


def _signal_witness(kind: str, node: Any, detail: str) -> dict[str, Any]:
    return {"kind": kind, "line": node.start_line, "detail": detail}


def _fresh_review_queue(
    records: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected: dict[tuple[str, str], dict[str, Any]] = {}
    for raw in records:
        record = dict(raw)
        root_cause = str(record.get("root_cause_fingerprint", "")) or _stable_id(
            "root_cause",
            record.get("protocol_id", ""),
            record.get("operation_id", ""),
            record.get("violation_type", ""),
            record.get("review_reason", ""),
        )
        record["root_cause_fingerprint"] = root_cause
        key = (str(record.get("function", "")), root_cause)
        existing = selected.get(key)
        if existing is None or str(record.get("occurrence_fingerprint", "")) < str(
            existing.get("occurrence_fingerprint", "")
        ):
            selected[key] = record
    return [selected[key] for key in sorted(selected)]


def confirmed_function_names(path: str | Path) -> tuple[str, ...]:
    source = Path(path)
    records = parse_confirmed_bugs_markdown(source.read_text(encoding="utf-8"))
    names = set()
    for record in records:
        match = re.match(r"([A-Za-z_]\w*)", record.function)
        if match:
            names.add(match.group(1))
    return tuple(sorted(names))


def _source_paths(root: Path, include: Iterable[str]) -> list[Path]:
    if root.is_file():
        return [root]
    paths: set[Path] = set()
    for pattern in include:
        paths.update(path for path in root.rglob(pattern) if path.is_file())
    return sorted(paths, key=lambda item: item.as_posix())


def _filesystem_for_path(path: Path) -> str:
    parts = list(path.parts)
    for index, part in enumerate(parts[:-1]):
        if part == "fs" and index + 1 < len(parts):
            return parts[index + 1]
    return ""


def _relative_source(source_file: str, root: Path) -> str:
    try:
        return Path(source_file).resolve().relative_to(root).as_posix()
    except ValueError:
        return Path(source_file).as_posix()


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(
        payload.encode("utf-8", errors="replace")
    ).hexdigest()[:20]
    return f"mocc_{prefix}_{digest}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Discover MOCC-SE protocol violations in a C source tree"
    )
    parser.add_argument("--protocol", action="append", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--source-version", default="")
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--max-files", type=int)
    parser.add_argument(
        "--exclude-confirmed-functions",
        nargs="?",
        const=str(DEFAULT_CONFIRMED_BUGS),
        default=str(DEFAULT_CONFIRMED_BUGS),
        metavar="MARKDOWN",
        help=(
            "exclude functions in confirmed_bugs.md (defaults to the project "
            "ledger; optionally provide another ledger)"
        ),
    )
    parser.add_argument(
        "--include-confirmed-functions",
        action="store_true",
        help="disable the default confirmed-function exclusion for regression runs",
    )
    parser.add_argument(
        "--include-regression-seeds",
        action="store_true",
        help="include operation entry_functions instead of producing a fresh queue",
    )
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    protocols = [MetadataProtocol.read_json(path) for path in args.protocol]
    excluded_functions: tuple[str, ...] = ()
    if not args.include_confirmed_functions:
        confirmed_path = Path(args.exclude_confirmed_functions)
        if not confirmed_path.is_file():
            parser.error(f"confirmed bug ledger does not exist: {confirmed_path}")
        excluded_functions = confirmed_function_names(confirmed_path)
    report = discover_source_tree(
        args.source_root,
        protocols,
        source_version=args.source_version,
        include=args.include or ("*.c",),
        max_files=args.max_files,
        excluded_functions=excluded_functions,
        exclude_regression_seeds=not args.include_regression_seeds,
    )
    payload = json.dumps(report.to_dict(), indent=2) + "\n"
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
