"""Freeze-bound batch scanning for MOCC-SE candidate queues."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .metadata_protocol import MetadataProtocol
from .metadata_protocol_discovery import (
    DEFAULT_CONFIRMED_BUGS,
    ProtocolDiscoveryReport,
    confirmed_function_names,
    discover_source_tree,
)
from .metadata_rule_registry import MetadataRuleRegistry
from .metadata_validation_labels import (
    AdjudicationSet,
    ReviewerLabelSet,
    validate_adjudication_set,
    validate_reviewer_label_set,
)
from .metadata_validation_manifest import (
    DEFAULT_FREEZE,
    DEFAULT_MANIFEST,
    ProtocolFreeze,
    ValidationManifest,
    _version_applies,
    validate_protocol_freeze,
    validate_validation_manifest,
)


BATCH_SCAN_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class BatchScanReport:
    workspace: str
    source_root: str
    source_version: str
    freeze_id: str
    manifest_id: str
    validation_gate: dict[str, Any]
    discovery: ProtocolDiscoveryReport

    def to_dict(self) -> dict[str, Any]:
        discovery_payload = self.discovery.to_dict()
        summary = discovery_payload["summary"]
        protocol_candidates = [
            item for analysis in discovery_payload["analyses"]
            for item in analysis["candidates"]
        ]
        review_queue = list(discovery_payload["fresh_review_queue"])
        unknown_queue = [
            item for analysis in discovery_payload["analyses"]
            for item in analysis["unknown"]
        ]
        unknown_queue.extend(discovery_payload["quarantine"])
        return {
            "schema_version": BATCH_SCAN_SCHEMA_VERSION,
            "result_semantics": "candidate_queue_not_bug_claims",
            "workspace": self.workspace,
            "source_root": self.source_root,
            "source_version": self.source_version,
            "freeze_id": self.freeze_id,
            "manifest_id": self.manifest_id,
            "validation_gate": self.validation_gate,
            "summary": {
                "scanned_files": summary["scanned_files"],
                "scanned_functions": summary["scanned_functions"],
                "applicable_functions": summary["applicable_functions"],
                "protocol_candidate_occurrences": len(protocol_candidates),
                "discovery_review_queue_entries": len(review_queue),
                "analysis_unknown": summary["analysis_unknown"],
                "discovery_unknown": summary["discovery_unknown"],
                "excluded_functions": summary["excluded_functions"],
                "skip_reasons": summary["skip_reasons"],
            },
            "protocol_candidates": protocol_candidates,
            "review_queue": review_queue,
            "unknown_queue": unknown_queue,
            "discovery_report": discovery_payload,
        }


def scan_source_tree(
    source_root: str | Path,
    *,
    workspace: str | Path = ".",
    source_version: str,
    freeze_path: str | Path = DEFAULT_FREEZE,
    manifest_path: str | Path = DEFAULT_MANIFEST,
    include: Iterable[str] = ("*.c",),
    max_files: int | None = None,
    labels: Iterable[str | Path] = (),
    adjudication: str | Path = "",
    require_complete_labels: bool = False,
    exclude_confirmed_functions: str | Path = DEFAULT_CONFIRMED_BUGS,
    include_confirmed_functions: bool = False,
    include_regression_seeds: bool = False,
) -> BatchScanReport:
    root = Path(workspace).resolve()
    freeze = ProtocolFreeze.read_json(root / freeze_path)
    manifest = ValidationManifest.read_json(root / manifest_path)
    validate_protocol_freeze(freeze, root)
    validate_validation_manifest(manifest, freeze, root)

    label_sets = tuple(ReviewerLabelSet.read_json(root / item) for item in labels)
    for label_set in label_sets:
        validate_reviewer_label_set(
            label_set,
            manifest,
            freeze,
            root,
            require_complete=require_complete_labels,
        )
    adjudication_set = None
    if adjudication:
        adjudication_set = AdjudicationSet.read_json(root / adjudication)
        validate_adjudication_set(
            adjudication_set,
            manifest,
            freeze,
            label_sets,
            root,
            require_complete=require_complete_labels,
        )

    protocols = _active_protocols(root, freeze, source_version)
    excluded_functions: tuple[str, ...] = ()
    if not include_confirmed_functions:
        confirmed = root / exclude_confirmed_functions
        if confirmed.is_file():
            excluded_functions = confirmed_function_names(confirmed)

    discovery = discover_source_tree(
        source_root,
        protocols,
        source_version=source_version,
        include=include,
        max_files=max_files,
        excluded_functions=excluded_functions,
        exclude_regression_seeds=not include_regression_seeds,
    )
    return BatchScanReport(
        workspace=root.as_posix(),
        source_root=Path(source_root).resolve().as_posix(),
        source_version=source_version,
        freeze_id=freeze.freeze_id,
        manifest_id=manifest.manifest_id,
        validation_gate={
            "manifest_validated": True,
            "labels_supplied": len(label_sets),
            "adjudication_supplied": adjudication_set is not None,
            "require_complete_labels": require_complete_labels,
            "rule_maturity": "development",
            "bug_claims_allowed": False,
        },
        discovery=discovery,
    )


def _active_protocols(
    workspace: Path,
    freeze: ProtocolFreeze,
    source_version: str,
) -> tuple[MetadataProtocol, ...]:
    registry = MetadataRuleRegistry.read_json(workspace / freeze.registry_path)
    protocol_dir = workspace / freeze.protocol_directory
    protocols = {
        protocol.protocol_id: protocol
        for protocol in (
            MetadataProtocol.read_json(path)
            for path in sorted(protocol_dir.glob("*.json"))
        )
    }
    rule_applicable_protocol_ids = {
        binding.protocol_id
        for rule in registry.rules
        if source_version in rule.linux_versions
        for binding in rule.bindings
    }
    active = []
    for protocol_id in registry.active_protocol_ids:
        protocol = protocols[protocol_id]
        if (
            protocol_id in rule_applicable_protocol_ids
            and _version_applies(source_version, protocol.linux_versions)
        ):
            active.append(protocol)
    return tuple(active)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a freeze-bound MOCC-SE batch candidate scan."
    )
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--source-version", required=True)
    parser.add_argument("--freeze", default=str(DEFAULT_FREEZE))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--include", action="append", default=[])
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--labels", action="append", default=[])
    parser.add_argument("--adjudication", default="")
    parser.add_argument("--require-complete-labels", action="store_true")
    parser.add_argument(
        "--exclude-confirmed-functions",
        default=str(DEFAULT_CONFIRMED_BUGS),
        help="confirmed bug ledger used for fresh scans",
    )
    parser.add_argument("--include-confirmed-functions", action="store_true")
    parser.add_argument("--include-regression-seeds", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    report = scan_source_tree(
        args.source_root,
        workspace=args.workspace,
        source_version=args.source_version,
        freeze_path=args.freeze,
        manifest_path=args.manifest,
        include=args.include or ("*.c",),
        max_files=args.max_files,
        labels=args.labels,
        adjudication=args.adjudication,
        require_complete_labels=args.require_complete_labels,
        exclude_confirmed_functions=args.exclude_confirmed_functions,
        include_confirmed_functions=args.include_confirmed_functions,
        include_regression_seeds=args.include_regression_seeds,
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
