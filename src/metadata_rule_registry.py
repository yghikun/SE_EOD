"""Versioned, evidence-backed metadata rule registry for MOCC-SE."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Type, TypeVar

from .metadata_protocol import MetadataProtocol, load_metadata_protocols


METADATA_RULE_REGISTRY_SCHEMA_VERSION = 2


class RuleMaturity(str, Enum):
    DEVELOPMENT = "development"
    VALIDATION = "validation"
    FROZEN = "frozen"


class SourceKind(str, Enum):
    LINUX_SOURCE = "linux_source"
    KERNEL_DOCUMENTATION = "kernel_documentation"
    UPSTREAM_COMMIT = "upstream_commit"
    KERNEL_TEST = "kernel_test"
    MAINTAINER_DISCUSSION = "maintainer_discussion"
    PAPER = "paper"


class RuleAuthority(str, Enum):
    NORMATIVE = "normative"
    CONFIRMED = "confirmed"
    HEURISTIC = "heuristic"


class EvidenceClass(str, Enum):
    CONTRACT = "contract"
    IMPLEMENTATION_EVIDENCE = "implementation_evidence"
    HISTORICAL_FIX = "historical_fix"
    MAINTAINER_EVIDENCE = "maintainer_evidence"
    MINED_HYPOTHESIS = "mined_hypothesis"


class EvidenceUsage(str, Enum):
    CONSTRUCTION = "construction"
    CORROBORATION = "corroboration"
    EVALUATION = "evaluation"


class EvidenceSplit(str, Enum):
    EXTERNAL = "external"
    DEVELOPMENT = "development"
    VALIDATION = "validation"
    FROZEN_TEST = "frozen_test"


class CoveragePriority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class MetadataRuleRegistryValidationError(ValueError):
    """A registry schema or protocol-binding error with a precise path."""

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


@dataclass(frozen=True)
class RuleFamily:
    family_id: str
    title: str
    description: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str) -> "RuleFamily":
        value = _mapping(data, path)
        _known_keys(value, {"family_id", "title", "description"}, path)
        return cls(
            family_id=_identifier(value, "family_id", path),
            title=_text(value, "title", path),
            description=_text(value, "description", path),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "title": self.title,
            "description": self.description,
        }


@dataclass(frozen=True)
class RuleSource:
    source_id: str
    kind: SourceKind
    evidence_class: EvidenceClass
    usage: EvidenceUsage
    dataset_split: EvidenceSplit
    locator: str
    claim: str
    content_sha256: str
    quoted_text: str
    filesystems: tuple[str, ...]
    linux_versions: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str) -> "RuleSource":
        value = _mapping(data, path)
        _known_keys(
            value,
            {
                "source_id",
                "kind",
                "evidence_class",
                "usage",
                "dataset_split",
                "locator",
                "claim",
                "content_sha256",
                "quoted_text",
                "filesystems",
                "linux_versions",
            },
            path,
        )
        kind = _enum(value, "kind", path, SourceKind)
        evidence_class = _enum(value, "evidence_class", path, EvidenceClass)
        usage = _enum(value, "usage", path, EvidenceUsage)
        dataset_split = _enum(value, "dataset_split", path, EvidenceSplit)
        locator = _text(value, "locator", path)
        locator_version = _validate_source_locator(kind, locator, path)
        content_sha256 = _optional_text(value, "content_sha256", path)
        quoted_text = _optional_text(value, "quoted_text", path)
        linux_versions = _string_tuple(
            value, "linux_versions", path, nonempty=True
        )
        if locator_version and linux_versions != (locator_version,):
            raise MetadataRuleRegistryValidationError(
                f"{path}.linux_versions",
                f"versioned locator v{locator_version} requires exactly [{locator_version!r}]",
            )
        if evidence_class is EvidenceClass.CONTRACT and kind not in {
            SourceKind.KERNEL_DOCUMENTATION,
            SourceKind.MAINTAINER_DISCUSSION,
        }:
            raise MetadataRuleRegistryValidationError(
                f"{path}.evidence_class",
                f"{kind.value} evidence cannot be classified as an external contract",
            )
        if evidence_class is EvidenceClass.CONTRACT and not quoted_text:
            raise MetadataRuleRegistryValidationError(
                f"{path}.quoted_text",
                "contract evidence requires an exact quoted excerpt",
            )
        if (
            dataset_split is EvidenceSplit.EXTERNAL
            and kind
            in {
                SourceKind.KERNEL_DOCUMENTATION,
                SourceKind.UPSTREAM_COMMIT,
                SourceKind.MAINTAINER_DISCUSSION,
            }
        ):
            if not content_sha256 or not re.fullmatch(r"[0-9a-f]{64}", content_sha256):
                raise MetadataRuleRegistryValidationError(
                    f"{path}.content_sha256",
                    "pinned external evidence requires a lowercase SHA-256 digest",
                )
            if not quoted_text:
                raise MetadataRuleRegistryValidationError(
                    f"{path}.quoted_text",
                    "pinned external evidence requires an exact quoted excerpt",
                )
        if usage is EvidenceUsage.CONSTRUCTION and dataset_split not in {
            EvidenceSplit.EXTERNAL,
            EvidenceSplit.DEVELOPMENT,
        }:
            raise MetadataRuleRegistryValidationError(
                f"{path}.dataset_split",
                "construction evidence must be external or development data",
            )
        if usage is EvidenceUsage.EVALUATION and dataset_split not in {
            EvidenceSplit.VALIDATION,
            EvidenceSplit.FROZEN_TEST,
        }:
            raise MetadataRuleRegistryValidationError(
                f"{path}.dataset_split",
                "evaluation evidence must belong to validation or frozen_test",
            )
        if (
            evidence_class is EvidenceClass.CONTRACT
            and dataset_split is not EvidenceSplit.EXTERNAL
        ):
            raise MetadataRuleRegistryValidationError(
                f"{path}.dataset_split", "contract evidence must be external"
            )
        return cls(
            source_id=_identifier(value, "source_id", path),
            kind=kind,
            evidence_class=evidence_class,
            usage=usage,
            dataset_split=dataset_split,
            locator=locator,
            claim=_text(value, "claim", path),
            content_sha256=content_sha256,
            quoted_text=quoted_text,
            filesystems=_identifier_tuple(
                value, "filesystems", path, nonempty=True
            ),
            linux_versions=linux_versions,
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "source_id": self.source_id,
            "kind": self.kind.value,
            "evidence_class": self.evidence_class.value,
            "usage": self.usage.value,
            "dataset_split": self.dataset_split.value,
            "locator": self.locator,
            "claim": self.claim,
            "filesystems": list(self.filesystems),
            "linux_versions": list(self.linux_versions),
        }
        if self.content_sha256:
            result["content_sha256"] = self.content_sha256
        if self.quoted_text:
            result["quoted_text"] = self.quoted_text
        return result


@dataclass(frozen=True)
class ProtocolOperationBinding:
    protocol_id: str
    operation_ids: tuple[str, ...]

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], path: str
    ) -> "ProtocolOperationBinding":
        value = _mapping(data, path)
        _known_keys(value, {"protocol_id", "operation_ids"}, path)
        return cls(
            protocol_id=_identifier(value, "protocol_id", path),
            operation_ids=_identifier_tuple(
                value, "operation_ids", path, nonempty=True
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "operation_ids": list(self.operation_ids),
        }


@dataclass(frozen=True)
class MetadataRule:
    rule_id: str
    family_id: str
    title: str
    summary: str
    maturity: RuleMaturity
    rule_authority: RuleAuthority
    filesystems: tuple[str, ...]
    linux_versions: tuple[str, ...]
    supported_semantics: tuple[str, ...]
    unsupported_semantics: tuple[str, ...]
    sources: tuple[RuleSource, ...]
    bindings: tuple[ProtocolOperationBinding, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str) -> "MetadataRule":
        value = _mapping(data, path)
        _known_keys(
            value,
            {
                "rule_id",
                "family_id",
                "title",
                "summary",
                "maturity",
                "rule_authority",
                "filesystems",
                "linux_versions",
                "supported_semantics",
                "unsupported_semantics",
                "sources",
                "bindings",
            },
            path,
        )
        sources = _object_tuple(value, "sources", path, RuleSource.from_dict)
        bindings = _object_tuple(
            value, "bindings", path, ProtocolOperationBinding.from_dict
        )
        if not sources:
            raise MetadataRuleRegistryValidationError(
                f"{path}.sources", "must contain at least one evidence source"
            )
        if not bindings:
            raise MetadataRuleRegistryValidationError(
                f"{path}.bindings", "must bind at least one executable operation"
            )
        rule_authority = _enum(value, "rule_authority", path, RuleAuthority)
        supporting = tuple(
            item
            for item in sources
            if item.usage
            in {EvidenceUsage.CONSTRUCTION, EvidenceUsage.CORROBORATION}
        )
        if not supporting:
            raise MetadataRuleRegistryValidationError(
                f"{path}.sources", "a rule requires construction or corroboration evidence"
            )
        if rule_authority is RuleAuthority.NORMATIVE and not any(
            item.evidence_class is EvidenceClass.CONTRACT for item in supporting
        ):
            raise MetadataRuleRegistryValidationError(
                f"{path}.sources", "a normative rule requires contract evidence"
            )
        if rule_authority is RuleAuthority.CONFIRMED:
            evidence_classes = {item.evidence_class for item in supporting}
            if len(supporting) < 2 or len(evidence_classes) < 2:
                raise MetadataRuleRegistryValidationError(
                    f"{path}.sources",
                    "a confirmed rule requires at least two supporting sources "
                    "from distinct evidence classes",
                )
        _unique((item.source_id for item in sources), f"{path}.sources", "source_id")
        _unique(
            (item.protocol_id for item in bindings),
            f"{path}.bindings",
            "protocol_id",
        )
        filesystems = _identifier_tuple(value, "filesystems", path, nonempty=True)
        linux_versions = _string_tuple(
            value, "linux_versions", path, nonempty=True
        )
        covered_pairs: set[tuple[str, str]] = set()
        for index, source in enumerate(sources):
            unexpected_filesystems = set(source.filesystems) - set(filesystems)
            if unexpected_filesystems:
                raise MetadataRuleRegistryValidationError(
                    f"{path}.sources[{index}].filesystems",
                    "contains filesystem(s) outside the rule applicability: "
                    + ", ".join(sorted(unexpected_filesystems)),
                )
            unexpected_versions = set(source.linux_versions) - set(linux_versions)
            if unexpected_versions:
                raise MetadataRuleRegistryValidationError(
                    f"{path}.sources[{index}].linux_versions",
                    "contains version(s) outside the rule applicability: "
                    + ", ".join(sorted(unexpected_versions)),
                )
            if source.usage in {
                EvidenceUsage.CONSTRUCTION,
                EvidenceUsage.CORROBORATION,
            }:
                covered_pairs.update(
                    (filesystem, version)
                    for filesystem in source.filesystems
                    for version in source.linux_versions
                )
        required_pairs = {
            (filesystem, version)
            for filesystem in filesystems
            for version in linux_versions
        }
        missing_pairs = sorted(required_pairs - covered_pairs)
        if missing_pairs:
            rendered = ", ".join(
                f"{filesystem}@{version}" for filesystem, version in missing_pairs
            )
            raise MetadataRuleRegistryValidationError(
                f"{path}.sources",
                f"supporting evidence coverage is missing applicability pair(s): {rendered}",
            )
        maturity = _enum(value, "maturity", path, RuleMaturity)
        evaluation_splits = {
            item.dataset_split
            for item in sources
            if item.usage is EvidenceUsage.EVALUATION
        }
        if maturity is RuleMaturity.DEVELOPMENT and evaluation_splits:
            raise MetadataRuleRegistryValidationError(
                f"{path}.sources",
                "development rules must not consume validation or frozen evaluation evidence",
            )
        if (
            maturity is RuleMaturity.VALIDATION
            and EvidenceSplit.VALIDATION not in evaluation_splits
        ):
            raise MetadataRuleRegistryValidationError(
                f"{path}.sources", "validation maturity requires validation evaluation evidence"
            )
        if maturity is RuleMaturity.FROZEN and EvidenceSplit.FROZEN_TEST not in evaluation_splits:
            raise MetadataRuleRegistryValidationError(
                f"{path}.sources", "frozen maturity requires frozen_test evaluation evidence"
            )
        return cls(
            rule_id=_identifier(value, "rule_id", path),
            family_id=_identifier(value, "family_id", path),
            title=_text(value, "title", path),
            summary=_text(value, "summary", path),
            maturity=maturity,
            rule_authority=rule_authority,
            filesystems=filesystems,
            linux_versions=linux_versions,
            supported_semantics=_string_tuple(
                value, "supported_semantics", path, nonempty=True
            ),
            unsupported_semantics=_string_tuple(
                value, "unsupported_semantics", path
            ),
            sources=sources,
            bindings=bindings,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "family_id": self.family_id,
            "title": self.title,
            "summary": self.summary,
            "maturity": self.maturity.value,
            "rule_authority": self.rule_authority.value,
            "filesystems": list(self.filesystems),
            "linux_versions": list(self.linux_versions),
            "supported_semantics": list(self.supported_semantics),
            "unsupported_semantics": list(self.unsupported_semantics),
            "sources": [item.to_dict() for item in self.sources],
            "bindings": [item.to_dict() for item in self.bindings],
        }


@dataclass(frozen=True)
class CoverageTarget:
    target_id: str
    family_id: str
    priority: CoveragePriority
    filesystems: tuple[str, ...]
    rule_goal: str
    required_capabilities: tuple[str, ...]
    exit_criteria: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str) -> "CoverageTarget":
        value = _mapping(data, path)
        _known_keys(
            value,
            {
                "target_id",
                "family_id",
                "priority",
                "filesystems",
                "rule_goal",
                "required_capabilities",
                "exit_criteria",
            },
            path,
        )
        return cls(
            target_id=_identifier(value, "target_id", path),
            family_id=_identifier(value, "family_id", path),
            priority=_enum(value, "priority", path, CoveragePriority),
            filesystems=_identifier_tuple(value, "filesystems", path, nonempty=True),
            rule_goal=_text(value, "rule_goal", path),
            required_capabilities=_string_tuple(
                value, "required_capabilities", path, nonempty=True
            ),
            exit_criteria=_string_tuple(
                value, "exit_criteria", path, nonempty=True
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "family_id": self.family_id,
            "priority": self.priority.value,
            "filesystems": list(self.filesystems),
            "rule_goal": self.rule_goal,
            "required_capabilities": list(self.required_capabilities),
            "exit_criteria": list(self.exit_criteria),
        }


@dataclass(frozen=True)
class RuleRegistryCoverage:
    active_protocols: int
    covered_operations: int
    rules: int
    coverage_targets: int
    maturity_counts: Mapping[str, int]
    authority_counts: Mapping[str, int]
    evidence_class_counts: Mapping[str, int]
    evidence_usage_counts: Mapping[str, int]
    evidence_split_counts: Mapping[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "active_protocols": self.active_protocols,
            "covered_operations": self.covered_operations,
            "rules": self.rules,
            "coverage_targets": self.coverage_targets,
            "maturity_counts": dict(sorted(self.maturity_counts.items())),
            "authority_counts": dict(sorted(self.authority_counts.items())),
            "evidence_class_counts": dict(sorted(self.evidence_class_counts.items())),
            "evidence_usage_counts": dict(sorted(self.evidence_usage_counts.items())),
            "evidence_split_counts": dict(sorted(self.evidence_split_counts.items())),
        }


@dataclass(frozen=True)
class MetadataRuleRegistry:
    schema_version: int
    registry_version: str
    registry_id: str
    active_protocol_ids: tuple[str, ...]
    supported_fragment: tuple[str, ...]
    families: tuple[RuleFamily, ...]
    rules: tuple[MetadataRule, ...]
    coverage_targets: tuple[CoverageTarget, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MetadataRuleRegistry":
        value = _mapping(data, "registry")
        _known_keys(
            value,
            {
                "schema_version",
                "registry_version",
                "registry_id",
                "active_protocol_ids",
                "supported_fragment",
                "families",
                "rules",
                "coverage_targets",
            },
            "registry",
        )
        schema_version = _integer(value, "schema_version", "registry")
        if schema_version != METADATA_RULE_REGISTRY_SCHEMA_VERSION:
            raise MetadataRuleRegistryValidationError(
                "registry.schema_version",
                f"unsupported metadata rule registry schema version {schema_version}; "
                f"expected {METADATA_RULE_REGISTRY_SCHEMA_VERSION}",
            )
        registry_version = _text(value, "registry_version", "registry")
        if not _SEMVER.fullmatch(registry_version):
            raise MetadataRuleRegistryValidationError(
                "registry.registry_version",
                "expected semantic version MAJOR.MINOR.PATCH",
            )
        families = _object_tuple(value, "families", "registry", RuleFamily.from_dict)
        rules = _object_tuple(value, "rules", "registry", MetadataRule.from_dict)
        targets = _object_tuple(
            value, "coverage_targets", "registry", CoverageTarget.from_dict
        )
        if not families:
            raise MetadataRuleRegistryValidationError(
                "registry.families", "must not be empty"
            )
        if not rules:
            raise MetadataRuleRegistryValidationError(
                "registry.rules", "must not be empty"
            )
        _unique((item.family_id for item in families), "registry.families", "family_id")
        _unique((item.rule_id for item in rules), "registry.rules", "rule_id")
        _unique(
            (item.target_id for item in targets),
            "registry.coverage_targets",
            "target_id",
        )
        family_ids = {item.family_id for item in families}
        for index, rule in enumerate(rules):
            if rule.family_id not in family_ids:
                raise MetadataRuleRegistryValidationError(
                    f"registry.rules[{index}].family_id",
                    f"references undefined family {rule.family_id!r}",
                )
        for index, target in enumerate(targets):
            if target.family_id not in family_ids:
                raise MetadataRuleRegistryValidationError(
                    f"registry.coverage_targets[{index}].family_id",
                    f"references undefined family {target.family_id!r}",
                )
        registry = cls(
            schema_version=schema_version,
            registry_version=registry_version,
            registry_id=_identifier(value, "registry_id", "registry"),
            active_protocol_ids=_identifier_tuple(
                value, "active_protocol_ids", "registry", nonempty=True
            ),
            supported_fragment=_string_tuple(
                value, "supported_fragment", "registry", nonempty=True
            ),
            families=families,
            rules=rules,
            coverage_targets=targets,
        )
        registry._validate_global_source_ids()
        registry._validate_evidence_separation()
        return registry

    @classmethod
    def from_json(cls, text: str) -> "MetadataRuleRegistry":
        try:
            data = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
        except json.JSONDecodeError as exc:
            raise MetadataRuleRegistryValidationError(
                "registry", f"invalid JSON: {exc.msg}"
            ) from exc
        return cls.from_dict(data)

    @classmethod
    def read_json(cls, path: str | Path) -> "MetadataRuleRegistry":
        source = Path(path)
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise MetadataRuleRegistryValidationError(
                str(source), f"cannot read registry: {exc}"
            ) from exc
        return cls.from_json(text)

    def validate_protocols(
        self, protocols: Iterable[MetadataProtocol]
    ) -> RuleRegistryCoverage:
        protocol_items = tuple(protocols)
        by_id = {item.protocol_id: item for item in protocol_items}
        if len(by_id) != len(protocol_items):
            raise MetadataRuleRegistryValidationError(
                "protocols", "duplicate protocol_id"
            )
        active_ids = set(self.active_protocol_ids)
        missing_protocols = active_ids - set(by_id)
        if missing_protocols:
            raise MetadataRuleRegistryValidationError(
                "registry.active_protocol_ids",
                "missing configured protocol(s): " + ", ".join(sorted(missing_protocols)),
            )

        covered: set[tuple[str, str]] = set()
        for rule_index, rule in enumerate(self.rules):
            for binding_index, binding in enumerate(rule.bindings):
                path = f"registry.rules[{rule_index}].bindings[{binding_index}]"
                if binding.protocol_id not in active_ids:
                    raise MetadataRuleRegistryValidationError(
                        f"{path}.protocol_id",
                        "binding must reference an active protocol",
                    )
                protocol = by_id[binding.protocol_id]
                if not set(rule.filesystems).issubset(set(protocol.filesystems)):
                    raise MetadataRuleRegistryValidationError(
                        f"registry.rules[{rule_index}].filesystems",
                        f"is not a subset of protocol {protocol.protocol_id!r} filesystems",
                    )
                operation_ids = {item.operation_id for item in protocol.operations}
                unknown = set(binding.operation_ids) - operation_ids
                if unknown:
                    raise MetadataRuleRegistryValidationError(
                        f"{path}.operation_ids",
                        "references undefined operation(s): "
                        + ", ".join(sorted(unknown)),
                    )
                covered.update(
                    (binding.protocol_id, operation_id)
                    for operation_id in binding.operation_ids
                )

        required = {
            (protocol_id, operation.operation_id)
            for protocol_id in self.active_protocol_ids
            for operation in by_id[protocol_id].operations
        }
        missing_operations = sorted(required - covered)
        if missing_operations:
            rendered = ", ".join(
                f"{protocol_id}:{operation_id}"
                for protocol_id, operation_id in missing_operations
            )
            raise MetadataRuleRegistryValidationError(
                "registry.rules", f"active operation(s) have no rule binding: {rendered}"
            )

        maturity_counts = {
            maturity.value: sum(rule.maturity is maturity for rule in self.rules)
            for maturity in RuleMaturity
        }
        sources = tuple(source for rule in self.rules for source in rule.sources)
        return RuleRegistryCoverage(
            active_protocols=len(active_ids),
            covered_operations=len(required),
            rules=len(self.rules),
            coverage_targets=len(self.coverage_targets),
            maturity_counts=maturity_counts,
            authority_counts={
                authority.value: sum(
                    rule.rule_authority is authority for rule in self.rules
                )
                for authority in RuleAuthority
            },
            evidence_class_counts={
                evidence_class.value: sum(
                    source.evidence_class is evidence_class for source in sources
                )
                for evidence_class in EvidenceClass
            },
            evidence_usage_counts={
                usage.value: sum(source.usage is usage for source in sources)
                for usage in EvidenceUsage
            },
            evidence_split_counts={
                split.value: sum(source.dataset_split is split for source in sources)
                for split in EvidenceSplit
            },
        )

    def _validate_global_source_ids(self) -> None:
        _unique(
            (source.source_id for rule in self.rules for source in rule.sources),
            "registry.rules.sources",
            "source_id",
        )

    def _validate_evidence_separation(self) -> None:
        by_locator: dict[str, set[EvidenceUsage]] = {}
        for rule in self.rules:
            for source in rule.sources:
                by_locator.setdefault(source.locator, set()).add(source.usage)
        contaminated = sorted(
            locator
            for locator, usages in by_locator.items()
            if EvidenceUsage.CONSTRUCTION in usages
            and EvidenceUsage.EVALUATION in usages
        )
        if contaminated:
            raise MetadataRuleRegistryValidationError(
                "registry.rules.sources",
                "the same locator cannot be both construction and evaluation evidence: "
                + ", ".join(contaminated),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "registry_version": self.registry_version,
            "registry_id": self.registry_id,
            "active_protocol_ids": list(self.active_protocol_ids),
            "supported_fragment": list(self.supported_fragment),
            "families": [item.to_dict() for item in self.families],
            "rules": [item.to_dict() for item in self.rules],
            "coverage_targets": [item.to_dict() for item in self.coverage_targets],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True) + "\n"

    def write_json(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json(), encoding="utf-8")


EnumT = TypeVar("EnumT", bound=Enum)
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*")
_SEMVER = re.compile(
    r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:[-+][0-9A-Za-z.-]+)?"
)


def _mapping(data: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise MetadataRuleRegistryValidationError(path, "expected an object")
    return data


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MetadataRuleRegistryValidationError(
                "registry", f"duplicate JSON field {key!r}"
            )
        result[key] = value
    return result


def _known_keys(data: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise MetadataRuleRegistryValidationError(
            path, f"unknown field(s): {', '.join(unknown)}"
        )


def _required(data: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in data:
        raise MetadataRuleRegistryValidationError(
            f"{path}.{key}", "required field is missing"
        )
    return data[key]


def _text(data: Mapping[str, Any], key: str, path: str) -> str:
    value = _required(data, key, path)
    if not isinstance(value, str) or not value.strip():
        raise MetadataRuleRegistryValidationError(
            f"{path}.{key}", "expected a non-empty string"
        )
    return value.strip()


def _optional_text(data: Mapping[str, Any], key: str, path: str) -> str:
    if key not in data:
        return ""
    value = data[key]
    if not isinstance(value, str) or not value.strip():
        raise MetadataRuleRegistryValidationError(
            f"{path}.{key}", "expected non-empty text when present"
        )
    return value.strip()


def _identifier(data: Mapping[str, Any], key: str, path: str) -> str:
    value = _text(data, key, path)
    if not _IDENTIFIER.fullmatch(value):
        raise MetadataRuleRegistryValidationError(
            f"{path}.{key}",
            "expected a stable identifier using letters, digits, '.', '_', or '-'",
        )
    return value


def _integer(data: Mapping[str, Any], key: str, path: str) -> int:
    value = _required(data, key, path)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MetadataRuleRegistryValidationError(
            f"{path}.{key}", "expected an integer"
        )
    return value


def _string_tuple(
    data: Mapping[str, Any],
    key: str,
    path: str,
    *,
    nonempty: bool = False,
) -> tuple[str, ...]:
    raw = _required(data, key, path)
    if not isinstance(raw, list):
        raise MetadataRuleRegistryValidationError(
            f"{path}.{key}", "expected a list"
        )
    values: list[str] = []
    for index, value in enumerate(raw):
        if not isinstance(value, str) or not value.strip():
            raise MetadataRuleRegistryValidationError(
                f"{path}.{key}[{index}]", "expected a non-empty string"
            )
        values.append(value.strip())
    if nonempty and not values:
        raise MetadataRuleRegistryValidationError(
            f"{path}.{key}", "must not be empty"
        )
    _unique(values, f"{path}.{key}", "value")
    return tuple(values)


def _identifier_tuple(
    data: Mapping[str, Any],
    key: str,
    path: str,
    *,
    nonempty: bool = False,
) -> tuple[str, ...]:
    values = _string_tuple(data, key, path, nonempty=nonempty)
    for index, value in enumerate(values):
        if not _IDENTIFIER.fullmatch(value):
            raise MetadataRuleRegistryValidationError(
                f"{path}.{key}[{index}]", "invalid identifier"
            )
    return values


def _object_tuple(
    data: Mapping[str, Any],
    key: str,
    path: str,
    parser: Any,
) -> tuple[Any, ...]:
    raw = _required(data, key, path)
    if not isinstance(raw, list):
        raise MetadataRuleRegistryValidationError(
            f"{path}.{key}", "expected a list"
        )
    return tuple(
        parser(item, f"{path}.{key}[{index}]") for index, item in enumerate(raw)
    )


def _enum(
    data: Mapping[str, Any], key: str, path: str, enum_type: Type[EnumT]
) -> EnumT:
    raw = _text(data, key, path)
    try:
        return enum_type(raw)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise MetadataRuleRegistryValidationError(
            f"{path}.{key}",
            f"unknown {enum_type.__name__} {raw!r}; expected one of: {allowed}",
        ) from exc


def _unique(values: Iterable[str], path: str, label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise MetadataRuleRegistryValidationError(
                path, f"duplicate {label} {value!r}"
            )
        seen.add(value)


def _validate_source_locator(
    kind: SourceKind, locator: str, path: str
) -> str | None:
    if kind is SourceKind.LINUX_SOURCE:
        match = re.fullmatch(
            r"linux:v([0-9][^:]*):(?:fs|Documentation)/[^#]+(?:#.+)?", locator
        )
        if not match:
            raise MetadataRuleRegistryValidationError(
                f"{path}.locator",
                "linux_source locator must use linux:vVERSION:path[#symbol]",
            )
        return match.group(1)
    if kind is SourceKind.KERNEL_DOCUMENTATION:
        url_match = re.fullmatch(
            r"https://docs\.kernel\.org/([0-9][^/]*)/[^#]+(?:#.+)?", locator
        )
        tree_match = re.fullmatch(
            r"linux:v([0-9][^:]*):Documentation/[^#]+(?:#.+)?", locator
        )
        if not url_match and not tree_match:
            raise MetadataRuleRegistryValidationError(
                f"{path}.locator",
                "kernel_documentation locator must use a versioned "
                "docs.kernel.org URL or Linux Documentation path",
            )
        return (url_match or tree_match).group(1)
    if kind is SourceKind.UPSTREAM_COMMIT:
        if not re.fullmatch(
            r"https://git\.kernel\.org/pub/scm/linux/kernel/git/torvalds/"
            r"linux\.git/patch/\?id=[0-9a-f]{40}",
            locator,
        ):
            raise MetadataRuleRegistryValidationError(
                f"{path}.locator",
                "upstream_commit locator must use an immutable 40-character "
                "git.kernel.org torvalds/linux patch URL",
            )
        return None
    if kind is SourceKind.MAINTAINER_DISCUSSION:
        if not re.fullmatch(
            r"https://lore\.kernel\.org/[A-Za-z0-9_.-]+/[^/\s]+/raw",
            locator,
        ):
            raise MetadataRuleRegistryValidationError(
                f"{path}.locator",
                "maintainer_discussion locator must use a lore.kernel.org "
                "Message-ID /raw URL",
            )
        return None
    return None


def validate_rule_registry(
    registry_path: str | Path, protocol_directory: str | Path
) -> tuple[MetadataRuleRegistry, RuleRegistryCoverage]:
    registry = MetadataRuleRegistry.read_json(registry_path)
    protocols = load_metadata_protocols(protocol_directory)
    return registry, registry.validate_protocols(protocols)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the evidence-backed MOCC-SE metadata rule registry."
    )
    parser.add_argument(
        "--registry",
        default="configs/metadata_rules/rule_registry_v2.json",
        help="Path to the versioned rule registry JSON.",
    )
    parser.add_argument(
        "--protocol-dir",
        default="configs/metadata_protocols",
        help="Directory containing metadata protocol JSON files.",
    )
    args = parser.parse_args(argv)
    registry, coverage = validate_rule_registry(args.registry, args.protocol_dir)
    result = {
        "registry_id": registry.registry_id,
        "registry_version": registry.registry_version,
        **coverage.to_dict(),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
