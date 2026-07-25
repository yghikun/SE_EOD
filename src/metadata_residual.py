"""Lightweight data model for failure-path filesystem metadata residual analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .transient_provenance import TransientArgumentProvenance


class MetadataPlane(str, Enum):
    STRUCTURAL = "STRUCTURAL"
    ACCOUNTING = "ACCOUNTING"
    RECOVERY = "RECOVERY"


class MetadataDelta(str, Enum):
    ADD = "ADD"
    REMOVE = "REMOVE"
    SET = "SET"
    CLEAR = "CLEAR"
    INC = "INC"
    DEC = "DEC"
    RESERVE = "RESERVE"
    RELEASE = "RELEASE"
    PROTECT = "PROTECT"
    CLOSE = "CLOSE"
    RESTORE = "RESTORE"
    UNKNOWN = "UNKNOWN"


class EffectEvidence(str, Enum):
    DIRECT_SOURCE = "DIRECT_SOURCE"
    EXPLICIT_PRIMITIVE = "EXPLICIT_PRIMITIVE"
    NAME_INFERRED = "NAME_INFERRED"


class ResidualState(str, Enum):
    EXPOSED = "EXPOSED"
    CONTAINED = "CONTAINED"
    PROTECTED = "PROTECTED"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"


class ReportKind(str, Enum):
    """Legacy serialization kind retained for M34 tool compatibility."""

    UNCLOSED_METADATA_RESIDUAL = "UNCLOSED_METADATA_RESIDUAL"
    CONTAINED_METADATA_RESIDUAL = "CONTAINED_METADATA_RESIDUAL"
    METADATA_RESIDUAL_UNKNOWN = "METADATA_RESIDUAL_UNKNOWN"
    METADATA_RESIDUAL_REVIEW = "METADATA_RESIDUAL_REVIEW"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class ResidualClassification(str, Enum):
    """Semantic result classification, independent of legacy Candidate naming."""

    FUNCTION_BOUNDARY_RESIDUAL = "FUNCTION_BOUNDARY_RESIDUAL"
    LIVE_METADATA_RESIDUAL = "LIVE_METADATA_RESIDUAL"
    CONTAINED_METADATA_RESIDUAL = "CONTAINED_METADATA_RESIDUAL"
    FUNCTION_BOUNDARY_RESIDUAL_REVIEW = "FUNCTION_BOUNDARY_RESIDUAL_REVIEW"
    METADATA_RESIDUAL_UNKNOWN = "METADATA_RESIDUAL_UNKNOWN"
    CLOSED = "CLOSED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class OwnerLivenessState(str, Enum):
    OWNER_LIVE = "OWNER_LIVE"
    OWNER_DESTROYED = "OWNER_DESTROYED"
    OWNER_UNPUBLISHED_AND_DISCARDED = "OWNER_UNPUBLISHED_AND_DISCARDED"
    OWNER_ESCAPED = "OWNER_ESCAPED"
    OWNER_LIFETIME_UNKNOWN = "OWNER_LIFETIME_UNKNOWN"


class FailureDomainKind(str, Enum):
    """Why a real function-boundary residual cannot remain live."""

    FAILED_OBJECT_TEARDOWN = "FAILED_OBJECT_TEARDOWN"
    TRANSACTION_ABORT = "TRANSACTION_ABORT"
    FATAL_SHUTDOWN = "FATAL_SHUTDOWN"
    CHECKPOINT_STOP = "CHECKPOINT_STOP"
    CALLER_CONTAINMENT = "CALLER_CONTAINMENT"


@dataclass(frozen=True)
class FailureDomainProof:
    kind: FailureDomainKind
    site: "SourceSite"
    owner: str = ""
    via_function: str = ""
    evidence: str = ""
    covered_effects: tuple["MetadataEffect", ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "site": self.site.to_dict(),
            "owner": self.owner,
            "via_function": self.via_function,
            "evidence": self.evidence,
            "covered_effects": [item.to_dict() for item in self.covered_effects],
        }


@dataclass(frozen=True)
class SourceSite:
    file: str
    line: int
    expression: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "expression": self.expression,
        }


@dataclass(frozen=True)
class AggregateSnapshotRelation:
    """Source proof that an aggregate restore covers a residual field."""

    snapshot_root: str
    owner_root: str
    aggregate_key: str
    capture_site: SourceSite
    capture_block: int | None
    source_identity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_root": self.snapshot_root,
            "owner_root": self.owner_root,
            "aggregate_key": self.aggregate_key,
            "capture_site": self.capture_site.to_dict(),
            "capture_block": self.capture_block,
            "source_identity": self.source_identity,
        }


@dataclass(frozen=True)
class ContainerIterationCleanup:
    """Source proof that one loop removes every member of a container."""

    container_root: str
    iterator: str
    next_iterator: str
    member_field: str
    iteration_site: SourceSite
    source_identity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "container_root": self.container_root,
            "iterator": self.iterator,
            "next_iterator": self.next_iterator,
            "member_field": self.member_field,
            "iteration_site": self.iteration_site.to_dict(),
            "source_identity": self.source_identity,
        }


@dataclass(frozen=True)
class ExistentialMemberIdentity:
    """Opaque identity for some source-visible aggregate member at one call site."""

    placeholder: str
    origin_expression: str
    destination_container: str
    member_field: str
    binding_site: SourceSite
    source_identity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "placeholder": self.placeholder,
            "origin_expression": self.origin_expression,
            "destination_container": self.destination_container,
            "member_field": self.member_field,
            "binding_site": self.binding_site.to_dict(),
            "source_identity": self.source_identity,
        }


@dataclass(frozen=True)
class TransactionOwnershipRelation:
    """Source proof that one metadata owner is registered with a transaction."""

    transaction_root: str
    owned_root: str
    primitive: str
    site: SourceSite
    source_identity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_root": self.transaction_root,
            "owned_root": self.owned_root,
            "primitive": self.primitive,
            "site": self.site.to_dict(),
            "source_identity": self.source_identity,
        }


@dataclass(frozen=True)
class PerCpuSlotRelation:
    """Source proof that a local denotes one slot of a parameter percpu field."""

    base_root: str
    slot_local: str
    index_local: str
    loop_site: SourceSite
    accessor_site: SourceSite
    source_identity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_root": self.base_root,
            "slot_local": self.slot_local,
            "index_local": self.index_local,
            "loop_site": self.loop_site.to_dict(),
            "accessor_site": self.accessor_site.to_dict(),
            "source_identity": self.source_identity,
        }


@dataclass(frozen=True)
class MetadataEffect:
    root: str
    key: str
    plane: MetadataPlane
    delta: MetadataDelta
    value: str
    site: SourceSite
    evidence: EffectEvidence = EffectEvidence.DIRECT_SOURCE
    snapshot_relation: AggregateSnapshotRelation | None = None
    container_iteration_cleanup: ContainerIterationCleanup | None = None
    existential_member_identity: ExistentialMemberIdentity | None = None
    transaction_ownership: TransactionOwnershipRelation | None = None
    percpu_slot_relation: PerCpuSlotRelation | None = None
    transient_provenance: tuple["TransientArgumentProvenance", ...] = ()

    def identity(self) -> tuple[str, str, MetadataPlane]:
        return (self.root, self.key, self.plane)

    def cancellation_key(self) -> tuple[str, str, MetadataPlane, str]:
        return (self.root, self.key, self.plane, self.value)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "root": self.root,
            "key": self.key,
            "plane": self.plane.value,
            "delta": self.delta.value,
            "value": self.value,
            "site": self.site.to_dict(),
            "evidence": self.evidence.value,
        }
        if self.snapshot_relation is not None:
            data["snapshot_relation"] = self.snapshot_relation.to_dict()
        if self.container_iteration_cleanup is not None:
            data["container_iteration_cleanup"] = (
                self.container_iteration_cleanup.to_dict()
            )
        if self.existential_member_identity is not None:
            data["existential_member_identity"] = (
                self.existential_member_identity.to_dict()
            )
        if self.transaction_ownership is not None:
            data["transaction_ownership"] = self.transaction_ownership.to_dict()
        if self.percpu_slot_relation is not None:
            data["percpu_slot_relation"] = self.percpu_slot_relation.to_dict()
        if self.transient_provenance:
            data["transient_provenance"] = [
                item.to_dict() for item in self.transient_provenance
            ]
        return data


@dataclass(frozen=True)
class OwnerTeardown:
    """Source proof that a deallocator destroys one complete in-memory owner."""

    owner: str
    teardown_site: SourceSite
    deallocator: str
    via_function: str = ""
    allocation_site: SourceSite | None = None
    state: OwnerLivenessState = OwnerLivenessState.OWNER_DESTROYED
    closed_effects: tuple[MetadataEffect, ...] = ()
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "teardown_site": self.teardown_site.to_dict(),
            "deallocator": self.deallocator,
            "via_function": self.via_function,
            "allocation_site": (
                self.allocation_site.to_dict() if self.allocation_site else None
            ),
            "state": self.state.value,
            "closed_effects": [effect.to_dict() for effect in self.closed_effects],
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class ResidualSlice:
    failure_site: SourceSite
    reaching_effects: tuple[MetadataEffect, ...]
    cancellations: tuple[MetadataEffect, ...]
    protections: tuple[MetadataEffect, ...]
    residuals: tuple[MetadataEffect, ...]
    state: ResidualState
    exit_site: SourceSite | None = None
    rationale: str = ""
    out_of_scope_effects: tuple[MetadataEffect, ...] = ()
    containment_proofs: tuple[FailureDomainProof, ...] = ()
    owner_teardown_proofs: tuple[OwnerTeardown, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_site": self.failure_site.to_dict(),
            "reaching_effects": [item.to_dict() for item in self.reaching_effects],
            "cancellations": [item.to_dict() for item in self.cancellations],
            "protections": [item.to_dict() for item in self.protections],
            "residuals": [item.to_dict() for item in self.residuals],
            "state": self.state.value,
            "exit_site": self.exit_site.to_dict() if self.exit_site else None,
            "rationale": self.rationale,
            "out_of_scope_effects": [
                item.to_dict() for item in self.out_of_scope_effects
            ],
            "containment_proofs": [
                item.to_dict() for item in self.containment_proofs
            ],
            "owner_teardown_proofs": [
                item.to_dict() for item in self.owner_teardown_proofs
            ],
        }


@dataclass(frozen=True)
class MetadataResidualReport:
    kind: ReportKind
    classification: ResidualClassification
    function: str
    residual_slice: ResidualSlice
    scope_rationale: str
    mdr_evidence: str = ""
    confidence: str = "review"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "classification": self.classification.value,
            "function": self.function,
            "residual_slice": self.residual_slice.to_dict(),
            "scope_rationale": self.scope_rationale,
            "mdr_evidence": self.mdr_evidence,
            "confidence": self.confidence,
        }


def residual_report(
    *,
    function: str,
    residual_slice: ResidualSlice,
    scope_rationale: str,
    mdr_evidence: str = "",
) -> MetadataResidualReport:
    if residual_slice.residuals and residual_slice.state is ResidualState.UNKNOWN:
        kind = ReportKind.METADATA_RESIDUAL_UNKNOWN
    elif residual_slice.residuals and residual_slice.state is ResidualState.CONTAINED:
        kind = ReportKind.CONTAINED_METADATA_RESIDUAL
    elif residual_slice.residuals and residual_slice.state is ResidualState.EXPOSED:
        uncontained = _uncontained_residuals(residual_slice)
        kind = (
            ReportKind.UNCLOSED_METADATA_RESIDUAL
            if any(
                effect.evidence is not EffectEvidence.NAME_INFERRED
                for effect in uncontained
            )
            else ReportKind.METADATA_RESIDUAL_REVIEW
        )
    else:
        kind = ReportKind.OUT_OF_SCOPE
    confidence = "candidate" if kind is ReportKind.UNCLOSED_METADATA_RESIDUAL else "review"
    return MetadataResidualReport(
        kind=kind,
        classification=_residual_classification(residual_slice, kind),
        function=function,
        residual_slice=residual_slice,
        scope_rationale=scope_rationale,
        mdr_evidence=mdr_evidence,
        confidence=confidence,
    )


def _uncontained_residuals(
    residual_slice: ResidualSlice,
) -> tuple[MetadataEffect, ...]:
    covered = {
        effect
        for proof in residual_slice.containment_proofs
        for effect in proof.covered_effects
    }
    return tuple(
        effect for effect in residual_slice.residuals if effect not in covered
    )


def _residual_classification(
    residual_slice: ResidualSlice,
    kind: ReportKind,
) -> ResidualClassification:
    if kind is ReportKind.UNCLOSED_METADATA_RESIDUAL:
        # Owner liveness is intentionally not inferred until M35b.  EXPOSED
        # proves only that R_f crosses this function's error boundary.
        return ResidualClassification.FUNCTION_BOUNDARY_RESIDUAL
    if kind is ReportKind.CONTAINED_METADATA_RESIDUAL:
        return ResidualClassification.CONTAINED_METADATA_RESIDUAL
    if kind is ReportKind.METADATA_RESIDUAL_UNKNOWN:
        return ResidualClassification.METADATA_RESIDUAL_UNKNOWN
    if kind is ReportKind.METADATA_RESIDUAL_REVIEW:
        return ResidualClassification.FUNCTION_BOUNDARY_RESIDUAL_REVIEW
    if residual_slice.out_of_scope_effects:
        return ResidualClassification.OUT_OF_SCOPE
    if residual_slice.state in {ResidualState.CLOSED, ResidualState.PROTECTED}:
        return ResidualClassification.CLOSED
    return ResidualClassification.OUT_OF_SCOPE
