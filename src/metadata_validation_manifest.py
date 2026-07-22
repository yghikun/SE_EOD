"""Freeze protocol inputs and validate contamination-free evaluation manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

from .function_extractor import extract_functions
from .metadata_protocol import MetadataProtocol
from .metadata_rule_registry import (
    EvidenceUsage,
    MetadataRuleRegistry,
    SourceKind,
)
from .parser import parse_c_file


PROTOCOL_FREEZE_SCHEMA_VERSION = 1
VALIDATION_MANIFEST_SCHEMA_VERSION = 1
DEFAULT_FREEZE = Path("configs/validation/protocol_freeze_v1.json")
DEFAULT_MANIFEST = Path("configs/validation/validation_manifest_v1.json")
DEFAULT_REGISTRY = Path("configs/metadata_rules/rule_registry_v2.json")
DEFAULT_PROTOCOL_DIRECTORY = Path("configs/metadata_protocols")

_DIGEST = re.compile(r"[0-9a-f]{64}")
_SEMVER = re.compile(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)")
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*")
_CONSTRUCTION_LOCATOR = re.compile(
    r"linux:v(?P<version>[^:]+):(?P<path>(?:fs|Documentation)/[^#]+)"
    r"(?:#(?P<symbols>.+))?"
)
_LOCAL_LINUX_SOURCE = re.compile(
    r"linux-sources/linux-v(?P<version>[^/]+)-fs/(?P<path>fs/.+)"
)


class MetadataValidationManifestError(ValueError):
    """A freeze or evaluation manifest violates an isolation invariant."""

    def __init__(self, path: str, message: str) -> None:
        self.path = path
        self.message = message
        super().__init__(f"{path}: {message}")


@dataclass(frozen=True)
class FreezeArtifact:
    path: str
    artifact_kind: str
    logical_id: str
    schema_version: int
    semantic_version: str
    content_sha256: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str) -> "FreezeArtifact":
        value = _mapping(data, path)
        _known_keys(
            value,
            {
                "path",
                "artifact_kind",
                "logical_id",
                "schema_version",
                "semantic_version",
                "content_sha256",
            },
            path,
        )
        artifact_path = _portable_path(value, "path", path)
        artifact_kind = _choice(
            value,
            "artifact_kind",
            path,
            {"registry", "protocol_manifest", "family", "binding", "operation"},
        )
        digest = _text(value, "content_sha256", path)
        if not _DIGEST.fullmatch(digest):
            raise MetadataValidationManifestError(
                f"{path}.content_sha256", "expected a lowercase SHA-256 digest"
            )
        semantic_version = _text(value, "semantic_version", path)
        if not _SEMVER.fullmatch(semantic_version):
            raise MetadataValidationManifestError(
                f"{path}.semantic_version", "expected MAJOR.MINOR.PATCH"
            )
        return cls(
            path=artifact_path,
            artifact_kind=artifact_kind,
            logical_id=_identifier(value, "logical_id", path),
            schema_version=_positive_integer(value, "schema_version", path),
            semantic_version=semantic_version,
            content_sha256=digest,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "artifact_kind": self.artifact_kind,
            "logical_id": self.logical_id,
            "schema_version": self.schema_version,
            "semantic_version": self.semantic_version,
            "content_sha256": self.content_sha256,
        }


@dataclass(frozen=True)
class ProtocolFreeze:
    schema_version: int
    freeze_id: str
    created_at: str
    status: str
    registry_path: str
    protocol_directory: str
    artifacts: tuple[FreezeArtifact, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProtocolFreeze":
        value = _mapping(data, "freeze")
        _known_keys(
            value,
            {
                "schema_version",
                "freeze_id",
                "created_at",
                "status",
                "registry_path",
                "protocol_directory",
                "artifacts",
            },
            "freeze",
        )
        schema_version = _positive_integer(value, "schema_version", "freeze")
        if schema_version != PROTOCOL_FREEZE_SCHEMA_VERSION:
            raise MetadataValidationManifestError(
                "freeze.schema_version",
                f"expected {PROTOCOL_FREEZE_SCHEMA_VERSION}",
            )
        artifacts = tuple(
            FreezeArtifact.from_dict(item, f"freeze.artifacts[{index}]")
            for index, item in enumerate(_object_list(value, "artifacts", "freeze"))
        )
        if not artifacts:
            raise MetadataValidationManifestError(
                "freeze.artifacts", "must not be empty"
            )
        _unique((item.path for item in artifacts), "freeze.artifacts", "path")
        _unique(
            (
                f"{item.artifact_kind}:{item.logical_id}"
                for item in artifacts
            ),
            "freeze.artifacts",
            "logical artifact",
        )
        return cls(
            schema_version=schema_version,
            freeze_id=_identifier(value, "freeze_id", "freeze"),
            created_at=_date(value, "created_at", "freeze"),
            status=_choice(value, "status", "freeze", {"frozen"}),
            registry_path=_portable_path(value, "registry_path", "freeze"),
            protocol_directory=_portable_path(
                value, "protocol_directory", "freeze"
            ),
            artifacts=artifacts,
        )

    @classmethod
    def read_json(cls, path: str | Path) -> "ProtocolFreeze":
        return cls.from_dict(_read_json(path))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "freeze_id": self.freeze_id,
            "created_at": self.created_at,
            "status": self.status,
            "registry_path": self.registry_path,
            "protocol_directory": self.protocol_directory,
            "artifacts": [item.to_dict() for item in self.artifacts],
        }


@dataclass(frozen=True)
class ValidationSample:
    sample_id: str
    protocol_id: str
    candidate_rule_ids: tuple[str, ...]
    filesystem: str
    source_version: str
    source_path: str
    source_sha256: str
    functions: tuple[str, ...]
    selection_kind: str
    selection_rationale: str
    label_status: str
    reviewer_slots: tuple[str, ...]
    allowed_verdicts: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], path: str) -> "ValidationSample":
        value = _mapping(data, path)
        _known_keys(
            value,
            {
                "sample_id",
                "protocol_id",
                "candidate_rule_ids",
                "filesystem",
                "source_version",
                "source_path",
                "source_sha256",
                "functions",
                "selection_kind",
                "selection_rationale",
                "label_status",
                "reviewer_slots",
                "allowed_verdicts",
            },
            path,
        )
        digest = _text(value, "source_sha256", path)
        if not _DIGEST.fullmatch(digest):
            raise MetadataValidationManifestError(
                f"{path}.source_sha256", "expected a lowercase SHA-256 digest"
            )
        reviewer_slots = _identifier_tuple(
            value, "reviewer_slots", path, nonempty=True
        )
        if len(reviewer_slots) < 2:
            raise MetadataValidationManifestError(
                f"{path}.reviewer_slots", "requires at least two independent reviewers"
            )
        verdicts = _choice_tuple(
            value,
            "allowed_verdicts",
            path,
            {"legal", "violation", "analysis_unknown", "out_of_scope"},
            nonempty=True,
        )
        required_verdicts = {"legal", "violation", "analysis_unknown"}
        if not required_verdicts.issubset(verdicts):
            raise MetadataValidationManifestError(
                f"{path}.allowed_verdicts",
                "must include legal, violation, and analysis_unknown",
            )
        return cls(
            sample_id=_identifier(value, "sample_id", path),
            protocol_id=_identifier(value, "protocol_id", path),
            candidate_rule_ids=_identifier_tuple(
                value, "candidate_rule_ids", path, nonempty=True
            ),
            filesystem=_identifier(value, "filesystem", path),
            source_version=_text(value, "source_version", path),
            source_path=_portable_path(value, "source_path", path),
            source_sha256=digest,
            functions=_identifier_tuple(value, "functions", path, nonempty=True),
            selection_kind=_choice(
                value,
                "selection_kind",
                path,
                {"fresh_discovery", "near_neighbor"},
            ),
            selection_rationale=_text(value, "selection_rationale", path),
            label_status=_choice(
                value,
                "label_status",
                path,
                {"unlabeled", "independently_labeled", "adjudicated"},
            ),
            reviewer_slots=reviewer_slots,
            allowed_verdicts=verdicts,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "protocol_id": self.protocol_id,
            "candidate_rule_ids": list(self.candidate_rule_ids),
            "filesystem": self.filesystem,
            "source_version": self.source_version,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "functions": list(self.functions),
            "selection_kind": self.selection_kind,
            "selection_rationale": self.selection_rationale,
            "label_status": self.label_status,
            "reviewer_slots": list(self.reviewer_slots),
            "allowed_verdicts": list(self.allowed_verdicts),
        }


@dataclass(frozen=True)
class ValidationManifest:
    schema_version: int
    manifest_version: str
    manifest_id: str
    freeze_id: str
    dataset_split: str
    label_visibility: str
    protocol_revision_policy: str
    construction_overlap_policy: str
    samples: tuple[ValidationSample, ...]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ValidationManifest":
        value = _mapping(data, "manifest")
        _known_keys(
            value,
            {
                "schema_version",
                "manifest_version",
                "manifest_id",
                "freeze_id",
                "dataset_split",
                "label_visibility",
                "protocol_revision_policy",
                "construction_overlap_policy",
                "samples",
            },
            "manifest",
        )
        schema_version = _positive_integer(value, "schema_version", "manifest")
        if schema_version != VALIDATION_MANIFEST_SCHEMA_VERSION:
            raise MetadataValidationManifestError(
                "manifest.schema_version",
                f"expected {VALIDATION_MANIFEST_SCHEMA_VERSION}",
            )
        manifest_version = _text(value, "manifest_version", "manifest")
        if not _SEMVER.fullmatch(manifest_version):
            raise MetadataValidationManifestError(
                "manifest.manifest_version", "expected MAJOR.MINOR.PATCH"
            )
        samples = tuple(
            ValidationSample.from_dict(item, f"manifest.samples[{index}]")
            for index, item in enumerate(_object_list(value, "samples", "manifest"))
        )
        if not samples:
            raise MetadataValidationManifestError(
                "manifest.samples", "must not be empty"
            )
        _unique((item.sample_id for item in samples), "manifest.samples", "sample_id")
        manifest = cls(
            schema_version=schema_version,
            manifest_version=manifest_version,
            manifest_id=_identifier(value, "manifest_id", "manifest"),
            freeze_id=_identifier(value, "freeze_id", "manifest"),
            dataset_split=_choice(
                value, "dataset_split", "manifest", {"validation", "frozen_test"}
            ),
            label_visibility=_choice(
                value, "label_visibility", "manifest", {"blind", "unblinded"}
            ),
            protocol_revision_policy=_choice(
                value,
                "protocol_revision_policy",
                "manifest",
                {"frozen_before_label_access"},
            ),
            construction_overlap_policy=_choice(
                value,
                "construction_overlap_policy",
                "manifest",
                {"reject_version_path_function_overlap"},
            ),
            samples=samples,
        )
        if manifest.label_visibility == "blind" and any(
            item.label_status != "unlabeled" for item in samples
        ):
            raise MetadataValidationManifestError(
                "manifest.samples",
                "blind manifests may only contain unlabeled samples",
            )
        return manifest

    @classmethod
    def read_json(cls, path: str | Path) -> "ValidationManifest":
        return cls.from_dict(_read_json(path))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "manifest_version": self.manifest_version,
            "manifest_id": self.manifest_id,
            "freeze_id": self.freeze_id,
            "dataset_split": self.dataset_split,
            "label_visibility": self.label_visibility,
            "protocol_revision_policy": self.protocol_revision_policy,
            "construction_overlap_policy": self.construction_overlap_policy,
            "samples": [item.to_dict() for item in self.samples],
        }


@dataclass(frozen=True)
class ValidationCoverage:
    frozen_artifacts: int
    samples: int
    functions: int
    protocols: int
    filesystems: int
    fresh_discovery_samples: int
    near_neighbor_samples: int
    construction_overlaps: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "frozen_artifacts": self.frozen_artifacts,
            "samples": self.samples,
            "functions": self.functions,
            "protocols": self.protocols,
            "filesystems": self.filesystems,
            "fresh_discovery_samples": self.fresh_discovery_samples,
            "near_neighbor_samples": self.near_neighbor_samples,
            "construction_overlaps": self.construction_overlaps,
        }


def discover_freeze_artifacts(
    workspace: str | Path,
    registry_path: str | Path = DEFAULT_REGISTRY,
    protocol_directory: str | Path = DEFAULT_PROTOCOL_DIRECTORY,
) -> tuple[FreezeArtifact, ...]:
    root = Path(workspace).resolve()
    registry_file = _resolve_workspace_path(root, Path(registry_path).as_posix())
    protocol_dir = _resolve_workspace_path(root, Path(protocol_directory).as_posix())
    registry = MetadataRuleRegistry.read_json(registry_file)

    by_protocol_id: dict[str, Path] = {}
    for path in sorted(protocol_dir.glob("*.json")):
        protocol = MetadataProtocol.read_json(path)
        by_protocol_id[protocol.protocol_id] = path

    missing = sorted(set(registry.active_protocol_ids) - set(by_protocol_id))
    if missing:
        raise MetadataValidationManifestError(
            "freeze.protocol_directory",
            "active protocol manifest(s) missing: " + ", ".join(missing),
        )

    paths: dict[Path, str] = {registry_file: "registry"}
    for protocol_id in registry.active_protocol_ids:
        manifest_path = by_protocol_id[protocol_id]
        paths[manifest_path] = "protocol_manifest"
        payload = _read_json(manifest_path)
        if "protocol_package_schema_version" not in payload:
            continue
        paths[_package_reference(manifest_path, payload["family"])] = "family"
        for value in payload["bindings"]:
            paths[_package_reference(manifest_path, value)] = "binding"
        for value in payload["operations"]:
            paths[_package_reference(manifest_path, value)] = "operation"

    return tuple(
        _freeze_artifact(root, path, kind)
        for path, kind in sorted(paths.items(), key=lambda item: item[0].as_posix())
    )


def validate_protocol_freeze(
    freeze: ProtocolFreeze, workspace: str | Path
) -> tuple[FreezeArtifact, ...]:
    root = Path(workspace).resolve()
    expected = discover_freeze_artifacts(
        root, freeze.registry_path, freeze.protocol_directory
    )
    if tuple(item.to_dict() for item in freeze.artifacts) != tuple(
        item.to_dict() for item in expected
    ):
        expected_by_path = {item.path: item for item in expected}
        frozen_by_path = {item.path: item for item in freeze.artifacts}
        missing = sorted(set(expected_by_path) - set(frozen_by_path))
        extra = sorted(set(frozen_by_path) - set(expected_by_path))
        drifted = sorted(
            path
            for path in set(expected_by_path) & set(frozen_by_path)
            if expected_by_path[path] != frozen_by_path[path]
        )
        details = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if extra:
            details.append("extra=" + ",".join(extra))
        if drifted:
            details.append("drifted=" + ",".join(drifted))
        raise MetadataValidationManifestError(
            "freeze.artifacts",
            "frozen configuration differs from the workspace: " + "; ".join(details),
        )
    return expected


def validate_validation_manifest(
    manifest: ValidationManifest,
    freeze: ProtocolFreeze,
    workspace: str | Path,
) -> ValidationCoverage:
    root = Path(workspace).resolve()
    artifacts = validate_protocol_freeze(freeze, root)
    if manifest.freeze_id != freeze.freeze_id:
        raise MetadataValidationManifestError(
            "manifest.freeze_id", "does not reference the supplied freeze"
        )

    registry = MetadataRuleRegistry.read_json(
        _resolve_workspace_path(root, freeze.registry_path)
    )
    protocol_dir = _resolve_workspace_path(root, freeze.protocol_directory)
    protocols = {
        protocol.protocol_id: protocol
        for protocol in (
            MetadataProtocol.read_json(path)
            for path in sorted(protocol_dir.glob("*.json"))
        )
        if protocol.protocol_id in set(registry.active_protocol_ids)
    }
    rules = {item.rule_id: item for item in registry.rules}
    construction = _construction_functions(registry)
    seen_functions: set[tuple[str, str, str, str]] = set()

    for index, sample in enumerate(manifest.samples):
        sample_path = f"manifest.samples[{index}]"
        protocol = protocols.get(sample.protocol_id)
        if protocol is None:
            raise MetadataValidationManifestError(
                f"{sample_path}.protocol_id", "is not an active frozen protocol"
            )
        if sample.filesystem not in protocol.filesystems:
            raise MetadataValidationManifestError(
                f"{sample_path}.filesystem", "is outside protocol applicability"
            )
        if not _version_applies(sample.source_version, protocol.linux_versions):
            raise MetadataValidationManifestError(
                f"{sample_path}.source_version", "is outside protocol applicability"
            )
        for rule_id in sample.candidate_rule_ids:
            rule = rules.get(rule_id)
            if rule is None:
                raise MetadataValidationManifestError(
                    f"{sample_path}.candidate_rule_ids", f"unknown rule {rule_id!r}"
                )
            bound_protocols = {binding.protocol_id for binding in rule.bindings}
            if sample.protocol_id not in bound_protocols:
                raise MetadataValidationManifestError(
                    f"{sample_path}.candidate_rule_ids",
                    f"rule {rule_id!r} is not bound to {sample.protocol_id!r}",
                )
            if sample.filesystem not in rule.filesystems:
                raise MetadataValidationManifestError(
                    f"{sample_path}.candidate_rule_ids",
                    f"rule {rule_id!r} does not cover {sample.filesystem}",
                )
            if sample.source_version not in rule.linux_versions:
                raise MetadataValidationManifestError(
                    f"{sample_path}.candidate_rule_ids",
                    f"rule {rule_id!r} does not cover version {sample.source_version}",
                )

        source = _resolve_workspace_path(root, sample.source_path)
        if _text_sha256(source) != sample.source_sha256:
            raise MetadataValidationManifestError(
                f"{sample_path}.source_sha256", "source file digest has drifted"
            )
        local_match = _LOCAL_LINUX_SOURCE.fullmatch(sample.source_path)
        if not local_match or local_match.group("version") != sample.source_version:
            raise MetadataValidationManifestError(
                f"{sample_path}.source_path",
                "must match linux-sources/linux-vVERSION-fs/fs/... and source_version",
            )
        kernel_path = local_match.group("path")
        available = {item.name for item in extract_functions(parse_c_file(source))}
        missing_functions = sorted(set(sample.functions) - available)
        if missing_functions:
            raise MetadataValidationManifestError(
                f"{sample_path}.functions",
                "function(s) absent from pinned source: " + ", ".join(missing_functions),
            )
        for function in sample.functions:
            identity = (
                sample.filesystem,
                sample.source_version,
                kernel_path,
                function,
            )
            if identity in construction:
                raise MetadataValidationManifestError(
                    f"{sample_path}.functions",
                    "construction overlap detected for "
                    + f"{sample.filesystem}@{sample.source_version}:{kernel_path}#{function}",
                )
            if identity in seen_functions:
                raise MetadataValidationManifestError(
                    f"{sample_path}.functions", "duplicate validation function identity"
                )
            seen_functions.add(identity)

    covered_protocols = {item.protocol_id for item in manifest.samples}
    missing_protocols = sorted(set(registry.active_protocol_ids) - covered_protocols)
    if missing_protocols:
        raise MetadataValidationManifestError(
            "manifest.samples",
            "first validation batch does not cover active protocol(s): "
            + ", ".join(missing_protocols),
        )
    return ValidationCoverage(
        frozen_artifacts=len(artifacts),
        samples=len(manifest.samples),
        functions=sum(len(item.functions) for item in manifest.samples),
        protocols=len(covered_protocols),
        filesystems=len({item.filesystem for item in manifest.samples}),
        fresh_discovery_samples=sum(
            item.selection_kind == "fresh_discovery" for item in manifest.samples
        ),
        near_neighbor_samples=sum(
            item.selection_kind == "near_neighbor" for item in manifest.samples
        ),
    )


def _construction_functions(
    registry: MetadataRuleRegistry,
) -> set[tuple[str, str, str, str]]:
    identities: set[tuple[str, str, str, str]] = set()
    for rule in registry.rules:
        for source in rule.sources:
            if (
                source.kind is not SourceKind.LINUX_SOURCE
                or source.usage is not EvidenceUsage.CONSTRUCTION
            ):
                continue
            match = _CONSTRUCTION_LOCATOR.fullmatch(source.locator)
            if not match:
                continue
            symbols = tuple(
                item.strip()
                for item in (match.group("symbols") or "").split(",")
                if item.strip()
            )
            for filesystem in source.filesystems:
                for symbol in symbols:
                    identities.add(
                        (
                            filesystem,
                            match.group("version"),
                            match.group("path"),
                            symbol,
                        )
                    )
    return identities


def _version_applies(version: str, constraints: Iterable[str]) -> bool:
    for constraint in constraints:
        if version == constraint:
            return True
        if constraint.startswith(">="):
            lower_bound = constraint.removeprefix(">=").strip()
            if _version_key(version) >= _version_key(lower_bound):
                return True
    return False


def _version_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError as exc:
        raise MetadataValidationManifestError(
            "version", f"unsupported Linux version constraint {version!r}"
        ) from exc


def _freeze_artifact(root: Path, path: Path, kind: str) -> FreezeArtifact:
    payload = _read_json(path)
    if kind == "registry":
        logical_id = payload["registry_id"]
        schema_version = payload["schema_version"]
        semantic_version = payload["registry_version"]
    elif kind == "protocol_manifest":
        logical_id = payload["protocol_id"]
        schema_version = payload.get(
            "protocol_package_schema_version", payload.get("schema_version")
        )
        semantic_version = payload["protocol_version"]
    else:
        prefix = {"family": "family", "binding": "binding", "operation": "operation"}[
            kind
        ]
        logical_id = payload[f"{prefix}_id"]
        schema_version = payload[f"{prefix}_schema_version"]
        semantic_version = f"{schema_version}.0.0"
    return FreezeArtifact(
        path=path.resolve().relative_to(root).as_posix(),
        artifact_kind=kind,
        logical_id=logical_id,
        schema_version=schema_version,
        semantic_version=semantic_version,
        content_sha256=_text_sha256(path),
    )


def _package_reference(manifest: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise MetadataValidationManifestError(
            str(manifest), "package reference must be non-empty text"
        )
    target = (manifest.parent / value).resolve()
    if not target.is_file():
        raise MetadataValidationManifestError(
            str(manifest), f"package reference does not exist: {value}"
        )
    return target


def _resolve_workspace_path(root: Path, value: str) -> Path:
    portable = PurePosixPath(value)
    if portable.is_absolute() or ".." in portable.parts:
        raise MetadataValidationManifestError(value, "path escapes the workspace")
    target = (root / Path(*portable.parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise MetadataValidationManifestError(value, "path escapes the workspace") from exc
    if not target.exists():
        raise MetadataValidationManifestError(value, "path does not exist")
    return target


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _text_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _read_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(
            source.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    except OSError as exc:
        raise MetadataValidationManifestError(str(source), f"cannot read JSON: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MetadataValidationManifestError(
            str(source), f"invalid JSON at line {exc.lineno}: {exc.msg}"
        ) from exc
    if not isinstance(payload, dict):
        raise MetadataValidationManifestError(str(source), "expected a JSON object")
    return payload


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MetadataValidationManifestError(
                "json", f"duplicate JSON field {key!r}"
            )
        result[key] = value
    return result


def _mapping(data: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(data, Mapping):
        raise MetadataValidationManifestError(path, "expected an object")
    return data


def _known_keys(data: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise MetadataValidationManifestError(
            path, "unknown field(s): " + ", ".join(unknown)
        )


def _required(data: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in data:
        raise MetadataValidationManifestError(f"{path}.{key}", "required field missing")
    return data[key]


def _text(data: Mapping[str, Any], key: str, path: str) -> str:
    value = _required(data, key, path)
    if not isinstance(value, str) or not value.strip():
        raise MetadataValidationManifestError(f"{path}.{key}", "expected non-empty text")
    return value.strip()


def _identifier(data: Mapping[str, Any], key: str, path: str) -> str:
    value = _text(data, key, path)
    if not _IDENTIFIER.fullmatch(value):
        raise MetadataValidationManifestError(f"{path}.{key}", "invalid identifier")
    return value


def _positive_integer(data: Mapping[str, Any], key: str, path: str) -> int:
    value = _required(data, key, path)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise MetadataValidationManifestError(f"{path}.{key}", "expected a positive integer")
    return value


def _portable_path(data: Mapping[str, Any], key: str, path: str) -> str:
    value = _text(data, key, path)
    portable = PurePosixPath(value)
    if portable.is_absolute() or ".." in portable.parts or "\\" in value:
        raise MetadataValidationManifestError(
            f"{path}.{key}", "expected a workspace-relative POSIX path"
        )
    return portable.as_posix()


def _date(data: Mapping[str, Any], key: str, path: str) -> str:
    value = _text(data, key, path)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise MetadataValidationManifestError(f"{path}.{key}", "expected YYYY-MM-DD")
    return value


def _choice(
    data: Mapping[str, Any], key: str, path: str, allowed: set[str]
) -> str:
    value = _text(data, key, path)
    if value not in allowed:
        raise MetadataValidationManifestError(
            f"{path}.{key}", "expected one of: " + ", ".join(sorted(allowed))
        )
    return value


def _object_list(data: Mapping[str, Any], key: str, path: str) -> list[Mapping[str, Any]]:
    value = _required(data, key, path)
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise MetadataValidationManifestError(f"{path}.{key}", "expected an object array")
    return value


def _identifier_tuple(
    data: Mapping[str, Any], key: str, path: str, *, nonempty: bool = False
) -> tuple[str, ...]:
    value = _required(data, key, path)
    if not isinstance(value, list):
        raise MetadataValidationManifestError(f"{path}.{key}", "expected an array")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not _IDENTIFIER.fullmatch(item):
            raise MetadataValidationManifestError(
                f"{path}.{key}[{index}]", "invalid identifier"
            )
        result.append(item)
    if nonempty and not result:
        raise MetadataValidationManifestError(f"{path}.{key}", "must not be empty")
    _unique(result, f"{path}.{key}", "value")
    return tuple(result)


def _choice_tuple(
    data: Mapping[str, Any],
    key: str,
    path: str,
    allowed: set[str],
    *,
    nonempty: bool = False,
) -> tuple[str, ...]:
    value = _required(data, key, path)
    if not isinstance(value, list):
        raise MetadataValidationManifestError(f"{path}.{key}", "expected an array")
    result = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or item not in allowed:
            raise MetadataValidationManifestError(
                f"{path}.{key}[{index}]", "unsupported value"
            )
        result.append(item)
    if nonempty and not result:
        raise MetadataValidationManifestError(f"{path}.{key}", "must not be empty")
    _unique(result, f"{path}.{key}", "value")
    return tuple(result)


def _unique(values: Iterable[str], path: str, label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise MetadataValidationManifestError(path, f"duplicate {label} {value!r}")
        seen.add(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate frozen MOCC-SE protocol inputs and blind evaluation samples."
    )
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--freeze", default=str(DEFAULT_FREEZE))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument(
        "--print-current-freeze",
        action="store_true",
        help="Print the currently discovered artifact set instead of validating samples.",
    )
    args = parser.parse_args(argv)
    root = Path(args.workspace).resolve()
    if args.print_current_freeze:
        artifacts = discover_freeze_artifacts(root)
        print(json.dumps([item.to_dict() for item in artifacts], indent=2))
        return 0
    freeze = ProtocolFreeze.read_json(root / args.freeze)
    manifest = ValidationManifest.read_json(root / args.manifest)
    coverage = validate_validation_manifest(manifest, freeze, root)
    print(
        json.dumps(
            {
                "freeze_id": freeze.freeze_id,
                "manifest_id": manifest.manifest_id,
                "dataset_split": manifest.dataset_split,
                "label_visibility": manifest.label_visibility,
                **coverage.to_dict(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
