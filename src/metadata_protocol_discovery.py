"""Directory-level semantic discovery for MOCC-SE metadata protocols."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .frontend.model import FunctionIR
from .frontend.tree_sitter_frontend import TreeSitterFrontend
from .metadata_event import MetadataEvent, extract_metadata_events
from .metadata_protocol import MetadataProtocol
from .metadata_protocol_analyzer import ProtocolAnalysisResult, analyze_function


DISCOVERY_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ApplicabilityEvidence:
    operation_id: str
    match_kind: str
    matched_role_ids: tuple[str, ...]
    matched_effect_ids: tuple[str, ...]
    matched_compensation_ids: tuple[str, ...]
    matched_handler_ids: tuple[str, ...]
    unmatched_required_role_ids: tuple[str, ...]
    unique_anchor_ids: tuple[str, ...]

    @property
    def semantic_anchor_count(self) -> int:
        return (
            len(self.matched_role_ids)
            + len(self.matched_effect_ids)
            + len(self.matched_compensation_ids)
            + len(self.matched_handler_ids)
        )

    @property
    def applicable(self) -> bool:
        if self.match_kind == "exact_entry":
            return True
        role_count = len(self.matched_role_ids)
        supporting_count = (
            len(self.matched_effect_ids)
            + len(self.matched_compensation_ids)
            + len(self.matched_handler_ids)
        )
        return bool(self.unique_anchor_ids) and (
            role_count >= 2 or (role_count >= 1 and supporting_count >= 1)
        )

    def score(self) -> tuple[int, int, int, int]:
        return (
            1 if self.match_kind == "exact_entry" else 0,
            len(self.unique_anchor_ids),
            self.semantic_anchor_count,
            -len(self.unmatched_required_role_ids),
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
            "unique_anchor_ids": list(self.unique_anchor_ids),
            "semantic_anchor_count": self.semantic_anchor_count,
        }


@dataclass(frozen=True)
class DiscoveryAnalysis:
    applicability: ApplicabilityEvidence
    result: ProtocolAnalysisResult
    candidate_records: tuple[dict[str, Any], ...]
    unknown_records: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        payload = self.result.to_dict()
        payload["applicability"] = self.applicability.to_dict()
        payload["candidates"] = list(self.candidate_records)
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
class ProtocolDiscoveryReport:
    source_root: str
    source_version: str
    protocol_ids: tuple[str, ...]
    protocol_versions: tuple[str, ...]
    scanned_files: int
    scanned_functions: int
    analyses: tuple[DiscoveryAnalysis, ...]
    quarantine: tuple[DiscoveryQuarantine, ...]
    skip_reasons: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, Any]:
        candidates = [
            item for analysis in self.analyses for item in analysis.candidate_records
        ]
        unknown = [
            item for analysis in self.analyses for item in analysis.unknown_records
        ]
        family_counts = Counter(item["family_fingerprint"] for item in candidates)
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
                "candidate_occurrences": len(candidates),
                "candidate_families": len(family_counts),
                "analysis_unknown": len(unknown),
                "discovery_unknown": len(self.quarantine),
                "skip_reasons": dict(self.skip_reasons),
            },
            "analyses": [item.to_dict() for item in self.analyses],
            "quarantine": [item.to_dict() for item in self.quarantine],
            "candidate_families": [
                {
                    "family_fingerprint": key,
                    "occurrences": family_counts[key],
                }
                for key in sorted(family_counts)
            ],
        }


def discover_source_tree(
    source_root: str | Path,
    protocols: Iterable[MetadataProtocol],
    *,
    source_version: str = "",
    include: Iterable[str] = ("*.c",),
    max_files: int | None = None,
) -> ProtocolDiscoveryReport:
    root = Path(source_root).resolve()
    protocol_list = tuple(protocols)
    paths = _source_paths(root, include)
    if max_files is not None:
        paths = paths[:max_files]
    frontend = TreeSitterFrontend(source_root=root)
    analyses: list[DiscoveryAnalysis] = []
    quarantine: list[DiscoveryQuarantine] = []
    skips: Counter[str] = Counter()
    scanned_functions = 0

    for path in paths:
        unit = frontend.parse(path)
        for function in unit.functions:
            scanned_functions += 1
            filesystem = _filesystem_for_path(path)
            matched_any = False
            for protocol in protocol_list:
                if filesystem and filesystem not in protocol.filesystems:
                    skips["filesystem_not_applicable"] += 1
                    continue
                evidences = operation_applicability(function, protocol)
                applicable = [item for item in evidences if item.applicable]
                if not applicable:
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
                quarantine,
                key=lambda item: (
                    item.source_file,
                    item.function,
                    item.protocol_id,
                ),
            )
        ),
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
        required_roles = {
            item.role_id for item in operation.callee_roles if item.necessary
        }
        matched_anchor_ids = _matched_anchor_ids(events)
        unique_anchors = tuple(
            sorted(
                anchor
                for anchor in matched_anchor_ids
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
                unique_anchors,
            )
        )
    return tuple(evidences)


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
    return owners


def _matched_anchor_ids(events: tuple[MetadataEvent, ...]) -> set[str]:
    anchors: set[str] = set()
    for event in events:
        if event.callee:
            anchors.add(f"callee:{event.callee}")
        if event.field_or_member:
            anchors.add(f"field:{event.field_or_member}")
    return anchors


def _discovery_analysis(
    root: Path,
    filesystem: str,
    applicability: ApplicabilityEvidence,
    result: ProtocolAnalysisResult,
) -> DiscoveryAnalysis:
    relative = _relative_source(result.source_file, root)
    candidates = tuple(
        _candidate_record(
            item.to_dict(),
            result,
            relative,
            filesystem,
        )
        for item in result.candidates
    )
    unknown = tuple(
        _unknown_record(item.to_dict(), result, relative)
        for item in result.unknown
    )
    return DiscoveryAnalysis(applicability, result, candidates, unknown)


def _candidate_record(
    candidate: dict[str, Any],
    result: ProtocolAnalysisResult,
    relative_source: str,
    filesystem: str,
) -> dict[str, Any]:
    effect_ids = tuple(
        sorted(
            item.get("spec_effect_id", "")
            for item in candidate["open_effects"]
        )
    )
    failure_roles = tuple(
        sorted(
            item.get("operation_role", "")
            for item in candidate["unresolved_failures"]
        )
    )
    structural = (
        result.protocol_id,
        result.operation_id,
        candidate["violation_type"],
        candidate["exit_kind"],
        candidate.get("return_provenance", ""),
        effect_ids,
        failure_roles,
    )
    enriched = dict(candidate)
    enriched.update(
        {
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
) -> dict[str, Any]:
    enriched = dict(unknown)
    enriched.update(
        {
            "source_file": relative_source,
            "source_version": result.source_version,
            "function": result.function,
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
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    protocols = [MetadataProtocol.read_json(path) for path in args.protocol]
    report = discover_source_tree(
        args.source_root,
        protocols,
        source_version=args.source_version,
        include=args.include or ("*.c",),
        max_files=args.max_files,
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
