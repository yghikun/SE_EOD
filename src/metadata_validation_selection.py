"""Build label-blind, protocol-applicable validation manifest drafts."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .metadata_protocol import MetadataProtocol
from .metadata_protocol_discovery import discover_source_tree
from .metadata_rule_registry import MetadataRuleRegistry
from .metadata_validation_manifest import (
    DEFAULT_FREEZE,
    ProtocolFreeze,
    _construction_functions,
    _text_sha256,
    validate_protocol_freeze,
)


VALIDATION_SELECTION_SCHEMA_VERSION = 1
DEFAULT_SELECTION_ID = "mocc.validation.selection.batch_2.protocol_applicable"
DEFAULT_MANIFEST_ID = "mocc.validation.unseen_batch_2"
DEFAULT_SEED = "mocc.validation.batch_2.seed.2026_07_22"
ALLOWED_VERDICTS = ("legal", "violation", "analysis_unknown", "out_of_scope")


class MetadataValidationSelectionError(ValueError):
    """A protocol-applicable validation draft cannot be produced."""


def build_selection_audit(
    *,
    workspace: str | Path = ".",
    sources: Iterable[tuple[str, str | Path]],
    freeze_path: str | Path = DEFAULT_FREEZE,
    selection_id: str = DEFAULT_SELECTION_ID,
    manifest_id: str = DEFAULT_MANIFEST_ID,
    manifest_version: str = "1.0.0",
    dataset_split: str = "validation",
    seed: str = DEFAULT_SEED,
    samples_per_protocol: int = 2,
    include: Iterable[str] = ("*.c",),
    max_files: int | None = None,
    include_entry_functions: bool = False,
) -> dict[str, Any]:
    root = Path(workspace).resolve()
    freeze = ProtocolFreeze.read_json(root / freeze_path)
    validate_protocol_freeze(freeze, root)
    registry = MetadataRuleRegistry.read_json(root / freeze.registry_path)
    protocols = _frozen_protocols(root, freeze, registry)
    rule_ids = _rule_ids_by_protocol_operation(registry)
    construction = _construction_functions(registry)
    exact_entry_space = _exact_entry_space(protocols, registry, construction)

    pool = []
    rejected = Counter()
    for source_version, source_root in sources:
        source_root_path = Path(source_root)
        if not source_root_path.is_absolute():
            source_root_path = root / source_root_path
        report = discover_source_tree(
            source_root_path,
            protocols,
            source_version=source_version,
            include=include,
            max_files=max_files,
            exclude_regression_seeds=not include_entry_functions,
        )
        for analysis in report.analyses:
            candidate = _candidate_from_analysis(
                root,
                analysis,
                source_version,
                rule_ids,
                construction,
            )
            if candidate is None:
                rejected["construction_overlap_or_unbound_rule"] += 1
                continue
            pool.append(candidate)

    pool = sorted(pool, key=_candidate_sort_key)
    selected = _stratified_select(pool, samples_per_protocol, seed)
    active_protocols = set(registry.active_protocol_ids)
    covered_protocols = {item["protocol_id"] for item in selected}
    missing_protocols = sorted(active_protocols - covered_protocols)
    by_protocol = {
        protocol_id: {
            "candidate_pool": sum(item["protocol_id"] == protocol_id for item in pool),
            "selected": sum(item["protocol_id"] == protocol_id for item in selected),
        }
        for protocol_id in registry.active_protocol_ids
    }
    return {
        "schema_version": VALIDATION_SELECTION_SCHEMA_VERSION,
        "result_semantics": "selection_audit_not_evaluation",
        "selection_id": selection_id,
        "freeze_id": freeze.freeze_id,
        "manifest_id": manifest_id,
        "dataset_split": dataset_split,
        "label_visibility": "blind",
        "selection_policy": {
            "seed": seed,
            "samples_per_protocol": samples_per_protocol,
            "include_entry_functions": include_entry_functions,
            "construction_overlap_policy": "reject_version_path_function_overlap",
            "applicability_gate": (
                "selected samples must have exact or semantic operation analysis; "
                "lifecycle protocols may enter semantic analysis on acquire/open "
                "anchors while terminal actions remain analyzer obligations"
            ),
        },
        "coverage_gate": {
            "status": (
                "ready_for_manifest_freeze"
                if selected and not missing_protocols
                else "insufficient_protocol_applicability"
            ),
            "covered_protocols": sorted(covered_protocols),
            "missing_protocols": missing_protocols,
        },
        "summary": {
            "candidate_pool": len(pool),
            "selected_samples": len(selected),
            "by_protocol": by_protocol,
            "by_match_kind": dict(Counter(item["applicability_match_kind"] for item in pool)),
            "rejected": dict(rejected),
        },
        "exact_entry_space": exact_entry_space,
        "candidate_pool": pool,
        "draft_manifest": _draft_manifest(
            freeze,
            manifest_id,
            manifest_version,
            dataset_split,
            selected,
        ),
    }


def _frozen_protocols(
    root: Path,
    freeze: ProtocolFreeze,
    registry: MetadataRuleRegistry,
) -> tuple[MetadataProtocol, ...]:
    by_id = {}
    for artifact in freeze.artifacts:
        if artifact.artifact_kind != "protocol_manifest":
            continue
        protocol = MetadataProtocol.read_json(root / artifact.path)
        by_id[protocol.protocol_id] = protocol
    return tuple(by_id[protocol_id] for protocol_id in registry.active_protocol_ids)


def _rule_ids_by_protocol_operation(
    registry: MetadataRuleRegistry,
) -> dict[tuple[str, str, str, str], tuple[str, ...]]:
    by_key: dict[tuple[str, str, str, str], list[str]] = defaultdict(list)
    for rule in registry.rules:
        for binding in rule.bindings:
            for operation_id in binding.operation_ids:
                for filesystem in rule.filesystems:
                    for version in rule.linux_versions:
                        by_key[
                            (binding.protocol_id, operation_id, filesystem, version)
                        ].append(rule.rule_id)
    return {key: tuple(sorted(values)) for key, values in by_key.items()}


def _exact_entry_space(
    protocols: tuple[MetadataProtocol, ...],
    registry: MetadataRuleRegistry,
    construction: set[tuple[str, str, str, str]],
) -> dict[str, Any]:
    entries = []
    by_protocol: dict[str, Counter[str]] = defaultdict(Counter)
    for protocol in protocols:
        for operation in protocol.operations:
            for rule in registry.rules:
                bindings = [
                    binding
                    for binding in rule.bindings
                    if binding.protocol_id == protocol.protocol_id
                    and operation.operation_id in binding.operation_ids
                ]
                if not bindings:
                    continue
                for filesystem in rule.filesystems:
                    for version in rule.linux_versions:
                        for entry_function in operation.entry_functions:
                            overlaps = (
                                filesystem,
                                version,
                                _construction_kernel_path(
                                    construction, filesystem, version, entry_function
                                ),
                                entry_function,
                            )
                            construction_overlap = overlaps in construction
                            status = (
                                "construction_overlap"
                                if construction_overlap
                                else "available_exact_entry"
                            )
                            by_protocol[protocol.protocol_id][status] += 1
                            entries.append(
                                {
                                    "protocol_id": protocol.protocol_id,
                                    "operation_id": operation.operation_id,
                                    "rule_id": rule.rule_id,
                                    "filesystem": filesystem,
                                    "source_version": version,
                                    "entry_function": entry_function,
                                    "status": status,
                                }
                            )
    counts = Counter(item["status"] for item in entries)
    return {
        "interpretation": (
            "exact entry functions are unusable for blind validation when their "
            "version/path/function identity is construction evidence"
        ),
        "summary": {
            "registered_exact_entry_identities": len(entries),
            "construction_overlaps": counts["construction_overlap"],
            "available_exact_entries": counts["available_exact_entry"],
            "by_protocol": {
                protocol_id: dict(counter)
                for protocol_id, counter in sorted(by_protocol.items())
            },
        },
        "entries": sorted(
            entries,
            key=lambda item: (
                item["protocol_id"],
                item["operation_id"],
                item["source_version"],
                item["filesystem"],
                item["entry_function"],
            ),
        ),
    }


def _construction_kernel_path(
    construction: set[tuple[str, str, str, str]],
    filesystem: str,
    version: str,
    function: str,
) -> str:
    matches = sorted(
        path
        for fs, source_version, path, symbol in construction
        if fs == filesystem and source_version == version and symbol == function
    )
    return matches[0] if matches else ""


def _candidate_from_analysis(
    root: Path,
    analysis: Any,
    source_version: str,
    rule_ids: dict[tuple[str, str, str, str], tuple[str, ...]],
    construction: set[tuple[str, str, str, str]],
) -> dict[str, Any] | None:
    result = analysis.result
    source = Path(result.source_file).resolve()
    filesystem = _filesystem_for_source(source)
    source_path = source.relative_to(root).as_posix()
    kernel_path = _kernel_path(source_path, source_version)
    identity = (filesystem, source_version, kernel_path, result.function)
    candidate_rule_ids = rule_ids.get(
        (result.protocol_id, result.operation_id, filesystem, source_version),
        (),
    )
    if identity in construction or not candidate_rule_ids:
        return None
    return {
        "selection_key": _stable_id(
            result.protocol_id,
            result.operation_id,
            source_path,
            result.function,
        ),
        "protocol_id": result.protocol_id,
        "operation_id": result.operation_id,
        "candidate_rule_ids": list(candidate_rule_ids),
        "filesystem": filesystem,
        "source_version": source_version,
        "source_path": source_path,
        "source_sha256": _text_sha256(source),
        "function": result.function,
        "applicability_match_kind": analysis.applicability.match_kind,
        "candidate_count": len(result.candidates),
        "unknown_count": len(result.unknown),
        "applicability_evidence": analysis.applicability.to_dict(),
    }


def _stratified_select(
    candidates: list[dict[str, Any]],
    samples_per_protocol: int,
    seed: str,
) -> list[dict[str, Any]]:
    by_protocol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_protocol[candidate["protocol_id"]].append(candidate)
    selected = []
    for protocol_id in sorted(by_protocol):
        ranked = sorted(
            by_protocol[protocol_id],
            key=lambda item: _seeded_key(seed, item),
        )
        selected.extend(ranked if samples_per_protocol == 0 else ranked[:samples_per_protocol])
    return sorted(selected, key=_candidate_sort_key)


def _draft_manifest(
    freeze: ProtocolFreeze,
    manifest_id: str,
    manifest_version: str,
    dataset_split: str,
    selected: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "manifest_version": manifest_version,
        "manifest_id": manifest_id,
        "freeze_id": freeze.freeze_id,
        "dataset_split": dataset_split,
        "label_visibility": "blind",
        "protocol_revision_policy": "frozen_before_label_access",
        "construction_overlap_policy": "reject_version_path_function_overlap",
        "samples": [
            {
                "sample_id": _sample_id(index, item),
                "protocol_id": item["protocol_id"],
                "candidate_rule_ids": item["candidate_rule_ids"],
                "filesystem": item["filesystem"],
                "source_version": item["source_version"],
                "source_path": item["source_path"],
                "source_sha256": item["source_sha256"],
                "functions": [item["function"]],
                "selection_kind": "fresh_discovery",
                "selection_rationale": (
                    "Selected by frozen protocol applicability audit before label "
                    f"access; operation={item['operation_id']}, "
                    f"match={item['applicability_match_kind']}."
                ),
                "label_status": "unlabeled",
                "reviewer_slots": ["reviewer_a", "reviewer_b"],
                "allowed_verdicts": list(ALLOWED_VERDICTS),
            }
            for index, item in enumerate(selected, start=1)
        ],
    }


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        candidate["protocol_id"],
        candidate["operation_id"],
        candidate["source_path"],
        candidate["function"],
    )


def _seeded_key(seed: str, candidate: dict[str, Any]) -> tuple[str, tuple[str, str, str, str]]:
    payload = "|".join(
        [
            seed,
            candidate["protocol_id"],
            candidate["operation_id"],
            candidate["source_path"],
            candidate["function"],
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), _candidate_sort_key(candidate)


def _sample_id(index: int, candidate: dict[str, Any]) -> str:
    protocol_letter = candidate["protocol_id"].split(".")[-1].replace("_", ".")
    function = candidate["function"].replace("_", ".")
    digest = candidate["selection_key"][:8]
    return f"mocc.validation.batch_2.{index:03d}.{protocol_letter}.{function}.{digest}"


def _filesystem_for_source(source: Path) -> str:
    parts = list(source.parts)
    for index, part in enumerate(parts[:-1]):
        if part == "fs" and index + 1 < len(parts):
            return parts[index + 1]
    return ""


def _kernel_path(source_path: str, source_version: str) -> str:
    prefix = f"linux-sources/linux-v{source_version}-fs/"
    if source_path.startswith(prefix):
        return source_path.removeprefix(prefix)
    return source_path


def _stable_id(*parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()[:20]


def _parse_source(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise MetadataValidationSelectionError(
            "--source must use VERSION=PATH, for example 7.1=linux-sources/linux-v7.1-fs/fs"
        )
    version, path = value.split("=", 1)
    if not version.strip() or not path.strip():
        raise MetadataValidationSelectionError("--source requires non-empty VERSION and PATH")
    return version.strip(), Path(path.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Select protocol-applicable blind validation samples."
    )
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--freeze", default=str(DEFAULT_FREEZE))
    parser.add_argument("--source", action="append", required=True, metavar="VERSION=PATH")
    parser.add_argument("--selection-id", default=DEFAULT_SELECTION_ID)
    parser.add_argument("--manifest-id", default=DEFAULT_MANIFEST_ID)
    parser.add_argument("--manifest-version", default="1.0.0")
    parser.add_argument("--dataset-split", default="validation")
    parser.add_argument("--seed", default=DEFAULT_SEED)
    parser.add_argument("--samples-per-protocol", type=int, default=2)
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--include-entry-functions", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    if args.samples_per_protocol < 0:
        parser.error("--samples-per-protocol must be zero or greater")
    try:
        sources = tuple(_parse_source(item) for item in args.source)
        payload = build_selection_audit(
            workspace=args.workspace,
            sources=sources,
            freeze_path=args.freeze,
            selection_id=args.selection_id,
            manifest_id=args.manifest_id,
            manifest_version=args.manifest_version,
            dataset_split=args.dataset_split,
            seed=args.seed,
            samples_per_protocol=args.samples_per_protocol,
            include=args.include or ("*.c",),
            max_files=args.max_files,
            include_entry_functions=args.include_entry_functions,
        )
    except MetadataValidationSelectionError as exc:
        parser.error(str(exc))
    rendered = json.dumps(payload, indent=2) + "\n"
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
