"""Stable data model shared by summary construction and residual slicing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..metadata_residual import (
    IndirectTargetSet,
    MetadataDelta,
    MetadataEffect,
    MetadataPlane,
    OwnerTeardown,
    SourceSite,
)


class SummarySource(str, Enum):
    AUTO_LOCAL = "AUTO_LOCAL"
    AUTO_INTERPROCEDURAL = "AUTO_INTERPROCEDURAL"
    PINNED_CORE_SUMMARY = "PINNED_CORE_SUMMARY"
    UNKNOWN = "UNKNOWN"


class LifecycleEvent(str, Enum):
    """A source-derived ownership/lifecycle transition."""

    ALLOCATED = "ALLOCATED"
    PUBLISHED = "PUBLISHED"
    RELEASED = "RELEASED"
    PROTECTED = "PROTECTED"


class LifecycleExit(str, Enum):
    ALL = "ALL"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    BOTH = "BOTH"


class ExposureKind(str, Enum):
    FRESH_LOCAL = "FRESH_LOCAL"
    PRIVATE_LOCAL = "PRIVATE_LOCAL"
    BOUND_TO = "BOUND_TO"
    RETURNED = "RETURNED"
    OUTPUT_BOUND = "OUTPUT_BOUND"
    PUBLISHED_IN_FIELD = "PUBLISHED_IN_FIELD"
    MEMBER_OF_CONTAINER = "MEMBER_OF_CONTAINER"


class OwnerIdentityKind(str, Enum):
    """Source form that makes a callee-local owner caller-bindable."""

    PARAM = "PARAM"
    FIELD = "FIELD"
    RETURN = "RETURN"
    OUT_PARAM = "OUT_PARAM"
    FRESH = "FRESH"


@dataclass(frozen=True)
class LifecycleFact:
    subject: str
    owner: str
    event: LifecycleEvent
    exit: LifecycleExit
    site: SourceSite
    evidence: str

    def to_dict(self) -> dict[str, object]:
        return {
            "subject": self.subject,
            "owner": self.owner,
            "event": self.event.value,
            "exit": self.exit.value,
            "site": self.site.to_dict(),
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class ExposureFact:
    local_identity: str
    summary_identity: str
    kind: ExposureKind
    target: str
    site: SourceSite
    evidence: str

    def to_dict(self) -> dict[str, object]:
        return {
            "local_identity": self.local_identity,
            "summary_identity": self.summary_identity,
            "kind": self.kind.value,
            "target": self.target,
            "site": self.site.to_dict(),
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class OwnerIdentityBinding:
    local_identity: str
    kind: OwnerIdentityKind
    summary_identity: str
    bound_identity: str
    site: SourceSite
    evidence: str

    def to_dict(self) -> dict[str, object]:
        return {
            "local_identity": self.local_identity,
            "kind": self.kind.value,
            "summary_identity": self.summary_identity,
            "bound_identity": self.bound_identity,
            "site": self.site.to_dict(),
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class CleanupFootprint:
    root_pattern: str
    key_pattern: str
    plane: MetadataPlane
    inverse_delta: MetadataDelta
    value_pattern: str
    owner_or_container: str
    site: SourceSite
    evidence: str

    def to_dict(self) -> dict[str, object]:
        return {
            "root_pattern": self.root_pattern,
            "key_pattern": self.key_pattern,
            "plane": self.plane.value,
            "inverse_delta": self.inverse_delta.value,
            "value_pattern": self.value_pattern,
            "owner_or_container": self.owner_or_container,
            "site": self.site.to_dict(),
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class LocalLifecycleBinding:
    local_identity: str
    allocation_line: int
    publication_lines: tuple[int, ...]
    allocation_site: SourceSite | None = None
    escape_lines: tuple[int, ...] = ()
    rebind_lines: tuple[int, ...] = ()


@dataclass(frozen=True)
class ExitSensitiveEffects:
    """Source-derived effect coverage across classified function exits."""

    success_must: tuple[MetadataEffect, ...] = ()
    success_may: tuple[MetadataEffect, ...] = ()
    error_must: tuple[MetadataEffect, ...] = ()
    error_may: tuple[MetadataEffect, ...] = ()
    error_complete: bool = False
    unknown_causes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "success_must": [item.to_dict() for item in self.success_must],
            "success_may": [item.to_dict() for item in self.success_may],
            "error_must": [item.to_dict() for item in self.error_must],
            "error_may": [item.to_dict() for item in self.error_may],
            "error_complete": self.error_complete,
            "unknown_causes": list(self.unknown_causes),
        }


@dataclass(frozen=True)
class ErrorExitPartition:
    """Effects that remain correlated on one exact source-visible error exit."""

    exit_site: SourceSite
    return_expression: str
    return_constraint: str = ""
    opens: tuple[MetadataEffect, ...] = ()
    cancels: tuple[MetadataEffect, ...] = ()
    protects: tuple[MetadataEffect, ...] = ()
    ordered_effects: tuple[MetadataEffect, ...] = ()
    residuals: tuple[MetadataEffect, ...] = ()
    terminal_actions: tuple[MetadataEffect, ...] = ()
    failed_owner_destructions: tuple[LifecycleFact, ...] = ()
    path: tuple[SourceSite, ...] = ()
    complete: bool = False
    unknown_causes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "exit_site": self.exit_site.to_dict(),
            "return_expression": self.return_expression,
            "return_constraint": self.return_constraint,
            "opens": [item.to_dict() for item in self.opens],
            "cancels": [item.to_dict() for item in self.cancels],
            "protects": [item.to_dict() for item in self.protects],
            "ordered_effects": [item.to_dict() for item in self.ordered_effects],
            "residuals": [item.to_dict() for item in self.residuals],
            "terminal_actions": [item.to_dict() for item in self.terminal_actions],
            "failed_owner_destructions": [
                item.to_dict() for item in self.failed_owner_destructions
            ],
            "path": [item.to_dict() for item in self.path],
            "complete": self.complete,
            "unknown_causes": list(self.unknown_causes),
        }


@dataclass(frozen=True)
class FunctionSummary:
    function_name: str
    parameters: tuple[str, ...]
    returns: tuple[str, ...]
    fresh_identities: tuple[str, ...]
    has_ownership_transfer: bool
    ownership_transfer_roots: tuple[str, ...]
    returns_fresh_identity: bool
    opens: tuple[MetadataEffect, ...]
    cancels: tuple[MetadataEffect, ...]
    protects: tuple[MetadataEffect, ...]
    output_identities: tuple[str, ...] = ()
    error_opens: tuple[MetadataEffect, ...] = ()
    error_cancels: tuple[MetadataEffect, ...] = ()
    error_protects: tuple[MetadataEffect, ...] = ()
    failure_effects_complete: bool = False
    error_unknown_causes: tuple[str, ...] = ()
    lifecycle_facts: tuple[LifecycleFact, ...] = ()
    exposure_facts: tuple[ExposureFact, ...] = ()
    cleanup_footprints: tuple[CleanupFootprint, ...] = ()
    owner_teardowns: tuple[OwnerTeardown, ...] = ()
    escaping_parameters: tuple[int, ...] = ()
    exit_effects: ExitSensitiveEffects = ExitSensitiveEffects()
    error_exit_partitions: tuple[ErrorExitPartition, ...] = ()
    error_partitions_exhaustive: bool = False
    unresolved_calls: tuple[str, ...] = ()
    source_file: str = ""
    may_fail: bool = False
    unknown_escape: bool = False
    unknown_causes: tuple[str, ...] = ()
    source: SummarySource = SummarySource.UNKNOWN
    owner_bindings: tuple[OwnerIdentityBinding, ...] = ()
    indirect_target_sets: tuple[IndirectTargetSet, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "function_name": self.function_name,
            "parameters": list(self.parameters),
            "returns": list(self.returns),
            "fresh_identities": list(self.fresh_identities),
            "has_ownership_transfer": self.has_ownership_transfer,
            "ownership_transfer_roots": list(self.ownership_transfer_roots),
            "returns_fresh_identity": self.returns_fresh_identity,
            "opens": [item.to_dict() for item in self.opens],
            "cancels": [item.to_dict() for item in self.cancels],
            "protects": [item.to_dict() for item in self.protects],
            "output_identities": list(self.output_identities),
            "error_opens": [item.to_dict() for item in self.error_opens],
            "error_cancels": [item.to_dict() for item in self.error_cancels],
            "error_protects": [item.to_dict() for item in self.error_protects],
            "failure_effects_complete": self.failure_effects_complete,
            "error_unknown_causes": list(self.error_unknown_causes),
            "lifecycle_facts": [item.to_dict() for item in self.lifecycle_facts],
            "exposure_facts": [item.to_dict() for item in self.exposure_facts],
            "cleanup_footprints": [item.to_dict() for item in self.cleanup_footprints],
            "owner_teardowns": [item.to_dict() for item in self.owner_teardowns],
            "escaping_parameters": list(self.escaping_parameters),
            "exit_effects": self.exit_effects.to_dict(),
            "error_exit_partitions": [
                item.to_dict() for item in self.error_exit_partitions
            ],
            "error_partitions_exhaustive": self.error_partitions_exhaustive,
            "unresolved_calls": list(self.unresolved_calls),
            "source_file": self.source_file,
            "may_fail": self.may_fail,
            "unknown_escape": self.unknown_escape,
            "unknown_causes": list(self.unknown_causes),
            "source": self.source.value,
            "owner_bindings": [item.to_dict() for item in self.owner_bindings],
            "indirect_target_sets": [
                item.to_dict() for item in self.indirect_target_sets
            ],
        }


@dataclass(frozen=True)
class SummaryApplication:
    summary: FunctionSummary
    opens: tuple[MetadataEffect, ...]
    cancels: tuple[MetadataEffect, ...]
    protects: tuple[MetadataEffect, ...]
    error_opens: tuple[MetadataEffect, ...] = ()
    error_cancels: tuple[MetadataEffect, ...] = ()
    error_protects: tuple[MetadataEffect, ...] = ()
    failure_effects_complete: bool = False
    error_unknown_causes: tuple[str, ...] = ()
    lifecycle_facts: tuple[LifecycleFact, ...] = ()
    exposure_facts: tuple[ExposureFact, ...] = ()
    cleanup_footprints: tuple[CleanupFootprint, ...] = ()
    owner_teardowns: tuple[OwnerTeardown, ...] = ()
    exit_effects: ExitSensitiveEffects = ExitSensitiveEffects()
    error_exit_partitions: tuple[ErrorExitPartition, ...] = ()
    error_partitions_exhaustive: bool = False
    returns: tuple[str, ...] = ()
    unresolved_identities: tuple[str, ...] = ()
    ownership_transfer_roots: tuple[str, ...] = ()
    owner_bindings: tuple[OwnerIdentityBinding, ...] = ()
    indirect_target_sets: tuple[IndirectTargetSet, ...] = ()

    @property
    def unknown(self) -> bool:
        return bool(self.unresolved_identities) or bool(self.summary.unknown_causes)

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary.to_dict(),
            "opens": [item.to_dict() for item in self.opens],
            "cancels": [item.to_dict() for item in self.cancels],
            "protects": [item.to_dict() for item in self.protects],
            "error_opens": [item.to_dict() for item in self.error_opens],
            "error_cancels": [item.to_dict() for item in self.error_cancels],
            "error_protects": [item.to_dict() for item in self.error_protects],
            "failure_effects_complete": self.failure_effects_complete,
            "error_unknown_causes": list(self.error_unknown_causes),
            "lifecycle_facts": [item.to_dict() for item in self.lifecycle_facts],
            "exposure_facts": [item.to_dict() for item in self.exposure_facts],
            "cleanup_footprints": [item.to_dict() for item in self.cleanup_footprints],
            "owner_teardowns": [item.to_dict() for item in self.owner_teardowns],
            "exit_effects": self.exit_effects.to_dict(),
            "error_exit_partitions": [
                item.to_dict() for item in self.error_exit_partitions
            ],
            "error_partitions_exhaustive": self.error_partitions_exhaustive,
            "returns": list(self.returns),
            "unresolved_identities": list(self.unresolved_identities),
            "ownership_transfer_roots": list(self.ownership_transfer_roots),
            "owner_bindings": [item.to_dict() for item in self.owner_bindings],
            "indirect_target_sets": [
                item.to_dict() for item in self.indirect_target_sets
            ],
            "unknown": self.unknown,
        }
