"""Versioned scope contract for metadata residual analysis."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


METADATA_SCOPE_SCHEMA_VERSION = 1
SUPPORTED_SCOPE_STATUSES = frozenset({"in_scope", "out_of_scope", "needs_scope_review"})
DEFAULT_METADATA_SCOPE = Path("configs/metadata_scope/metadata_scope_v1.json")
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*")
_SEMVER = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")


class MetadataScopeValidationError(ValueError):
    """Raised when the metadata scope contract is malformed."""


@dataclass(frozen=True)
class MetadataDomain:
    domain_id: str
    title: str
    rule_family_ids: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class ConfirmedBugScopeDecision:
    bug_id: int
    status: str
    domain_ids: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class MetadataScope:
    schema_version: int
    scope_version: str
    scope_id: str
    target_filesystems: tuple[str, ...]
    metadata_domains: tuple[MetadataDomain, ...]
    inclusion_requirements: tuple[str, ...]
    supporting_resource_policy: Mapping[str, Any]
    confirmed_bug_decisions: tuple[ConfirmedBugScopeDecision, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MetadataScope":
        _known_keys(data, {
            "schema_version", "scope_version", "scope_id", "target_filesystems",
            "metadata_domains", "inclusion_requirements", "supporting_resource_policy",
            "confirmed_bug_decisions",
        }, "scope")
        schema_version = _integer(data, "schema_version", "scope")
        if schema_version != METADATA_SCOPE_SCHEMA_VERSION:
            raise MetadataScopeValidationError(
                f"scope.schema_version: expected {METADATA_SCOPE_SCHEMA_VERSION}, got {schema_version}"
            )
        scope_version = _text(data, "scope_version", "scope")
        if not _SEMVER.fullmatch(scope_version):
            raise MetadataScopeValidationError("scope.scope_version: expected MAJOR.MINOR.PATCH")
        scope_id = _identifier(data, "scope_id", "scope")
        filesystems = _string_tuple(data, "target_filesystems", "scope", nonempty=True)
        domains = tuple(
            _parse_domain(item, f"scope.metadata_domains[{index}]")
            for index, item in enumerate(_list(data, "metadata_domains", "scope"))
        )
        if not domains:
            raise MetadataScopeValidationError("scope.metadata_domains: must not be empty")
        _unique((item.domain_id for item in domains), "scope.metadata_domains", "domain_id")
        requirements = _string_tuple(data, "inclusion_requirements", "scope", nonempty=True)
        policy = data.get("supporting_resource_policy")
        if not isinstance(policy, Mapping):
            raise MetadataScopeValidationError("scope.supporting_resource_policy: expected an object")
        decisions = tuple(
            _parse_decision(item, f"scope.confirmed_bug_decisions[{index}]")
            for index, item in enumerate(_list(data, "confirmed_bug_decisions", "scope"))
        )
        _unique((str(item.bug_id) for item in decisions), "scope.confirmed_bug_decisions", "bug_id")
        domain_ids = {item.domain_id for item in domains}
        for index, decision in enumerate(decisions):
            unknown = set(decision.domain_ids) - domain_ids
            if unknown:
                raise MetadataScopeValidationError(
                    f"scope.confirmed_bug_decisions[{index}].domain_ids: unknown domain(s) {sorted(unknown)}"
                )
            if decision.status == "in_scope" and not decision.domain_ids:
                raise MetadataScopeValidationError(
                    f"scope.confirmed_bug_decisions[{index}]: in_scope requires domain_ids"
                )
            if decision.status == "out_of_scope" and decision.domain_ids:
                raise MetadataScopeValidationError(
                    f"scope.confirmed_bug_decisions[{index}]: out_of_scope cannot have domain_ids"
                )
        return cls(
            schema_version=schema_version,
            scope_version=scope_version,
            scope_id=scope_id,
            target_filesystems=filesystems,
            metadata_domains=domains,
            inclusion_requirements=requirements,
            supporting_resource_policy=policy,
            confirmed_bug_decisions=decisions,
        )

    @classmethod
    def read_json(cls, path: str | Path) -> "MetadataScope":
        source = Path(path)
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MetadataScopeValidationError(f"{source}: cannot read scope JSON: {exc}") from exc
        if not isinstance(data, Mapping):
            raise MetadataScopeValidationError("scope: expected an object")
        return cls.from_dict(data)

    def decision_for(self, bug_id: int) -> ConfirmedBugScopeDecision | None:
        return next((item for item in self.confirmed_bug_decisions if item.bug_id == bug_id), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scope_version": self.scope_version,
            "scope_id": self.scope_id,
            "target_filesystems": list(self.target_filesystems),
            "metadata_domains": [
                {
                    "domain_id": item.domain_id,
                    "title": item.title,
                    "rule_family_ids": list(item.rule_family_ids),
                    "description": item.description,
                }
                for item in self.metadata_domains
            ],
            "inclusion_requirements": list(self.inclusion_requirements),
            "supporting_resource_policy": dict(self.supporting_resource_policy),
            "confirmed_bug_decisions": [
                {
                    "bug_id": item.bug_id,
                    "status": item.status,
                    "domain_ids": list(item.domain_ids),
                    "rationale": item.rationale,
                }
                for item in self.confirmed_bug_decisions
            ],
        }

    def domain_by_id(self) -> dict[str, MetadataDomain]:
        return {item.domain_id: item for item in self.metadata_domains}

    def validate_registry(self, registry: Any) -> None:
        registry_filesystems = {
            filesystem for rule in registry.rules for filesystem in rule.filesystems
        }
        unsupported = registry_filesystems - set(self.target_filesystems)
        if unsupported:
            raise MetadataScopeValidationError(
                "scope.target_filesystems: registry uses unsupported filesystem(s) "
                + ", ".join(sorted(unsupported))
            )
        scope_families = {
            family_id
            for domain in self.metadata_domains
            for family_id in domain.rule_family_ids
        }
        registry_families = {family.family_id for family in registry.families}
        missing = registry_families - scope_families
        if missing:
            raise MetadataScopeValidationError(
                "scope.metadata_domains: missing registry family mapping(s) "
                + ", ".join(sorted(missing))
            )


def _parse_domain(data: Any, path: str) -> MetadataDomain:
    value = _mapping(data, path)
    _known_keys(value, {"domain_id", "title", "rule_family_ids", "description"}, path)
    return MetadataDomain(
        domain_id=_identifier(value, "domain_id", path),
        title=_text(value, "title", path),
        rule_family_ids=_identifier_tuple(value, "rule_family_ids", path, nonempty=True),
        description=_text(value, "description", path),
    )


def _parse_decision(data: Any, path: str) -> ConfirmedBugScopeDecision:
    value = _mapping(data, path)
    _known_keys(value, {"bug_id", "status", "domain_ids", "rationale"}, path)
    bug_id = _integer(value, "bug_id", path)
    status = _text(value, "status", path)
    if status not in SUPPORTED_SCOPE_STATUSES:
        raise MetadataScopeValidationError(f"{path}.status: unknown scope status {status!r}")
    domains = _identifier_tuple(value, "domain_ids", path)
    return ConfirmedBugScopeDecision(
        bug_id=bug_id,
        status=status,
        domain_ids=domains,
        rationale=_text(value, "rationale", path),
    )


def _mapping(data: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise MetadataScopeValidationError(f"{path}: expected an object")
    return data


def _known_keys(data: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise MetadataScopeValidationError(f"{path}: unknown field(s): {', '.join(unknown)}")


def _list(data: Mapping[str, Any], key: str, path: str) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list):
        raise MetadataScopeValidationError(f"{path}.{key}: expected a list")
    return value


def _text(data: Mapping[str, Any], key: str, path: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MetadataScopeValidationError(f"{path}.{key}: expected non-empty text")
    return value.strip()


def _integer(data: Mapping[str, Any], key: str, path: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise MetadataScopeValidationError(f"{path}.{key}: expected an integer")
    return value


def _identifier(data: Mapping[str, Any], key: str, path: str) -> str:
    value = _text(data, key, path)
    if not _IDENTIFIER.fullmatch(value):
        raise MetadataScopeValidationError(f"{path}.{key}: invalid identifier")
    return value


def _string_tuple(data: Mapping[str, Any], key: str, path: str, *, nonempty: bool = False) -> tuple[str, ...]:
    values = _list(data, key, path)
    result: list[str] = []
    for index, value in enumerate(values):
        if not isinstance(value, str) or not value.strip():
            raise MetadataScopeValidationError(f"{path}.{key}[{index}]: expected non-empty text")
        result.append(value.strip())
    if nonempty and not result:
        raise MetadataScopeValidationError(f"{path}.{key}: must not be empty")
    _unique(result, f"{path}.{key}", "value")
    return tuple(result)


def _identifier_tuple(data: Mapping[str, Any], key: str, path: str, *, nonempty: bool = False) -> tuple[str, ...]:
    values = _string_tuple(data, key, path, nonempty=nonempty)
    for index, value in enumerate(values):
        if not _IDENTIFIER.fullmatch(value):
            raise MetadataScopeValidationError(f"{path}.{key}[{index}]: invalid identifier")
    return values


def _unique(values: Any, path: str, label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise MetadataScopeValidationError(f"{path}: duplicate {label} {value!r}")
        seen.add(value)
