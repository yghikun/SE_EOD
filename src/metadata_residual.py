"""Lightweight data model for failure-path filesystem metadata residual analysis."""

from __future__ import annotations

import re
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
    LIVE = "LIVE"
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


class OwnershipRelation(str, Enum):
    EMBEDDED = "EMBEDDED"
    UNIQUE_POINTER = "UNIQUE_POINTER"
    CONTAINER_OWNED = "CONTAINER_OWNED"
    ARRAY_ELEMENT = "ARRAY_ELEMENT"


class EscapeState(str, Enum):
    PRIVATE = "PRIVATE"
    PUBLISHED = "PUBLISHED"
    ESCAPED = "ESCAPED"
    UNKNOWN = "UNKNOWN"


class EffectProvenanceKind(str, Enum):
    PRIVATE_OWNER = "PRIVATE_OWNER"
    WRITE_ONLY_OUTPUT = "WRITE_ONLY_OUTPUT"
    OPERATION_DESCRIPTOR = "OPERATION_DESCRIPTOR"
    PROGRESS_CURSOR = "PROGRESS_CURSOR"
    RETRY_STATE = "RETRY_STATE"


class EffectVisibility(str, Enum):
    PRIVATE_RUNTIME = "PRIVATE_RUNTIME"
    OWNER_LOCAL = "OWNER_LOCAL"
    TRANSACTION_LOCAL = "TRANSACTION_LOCAL"
    RECOVERY_VISIBLE = "RECOVERY_VISIBLE"
    PERSISTENT_EXTERNAL = "PERSISTENT_EXTERNAL"
    UNKNOWN = "UNKNOWN"


class OwnerScopeKind(str, Enum):
    PRIVATE_OWNER = "PRIVATE_OWNER"
    FAILED_CONSTRUCTION = "FAILED_CONSTRUCTION"
    UNPUBLISHED_MOUNT_CONSTRUCTION = "UNPUBLISHED_MOUNT_CONSTRUCTION"
    WRITE_ONLY_OUTPUT = "WRITE_ONLY_OUTPUT"
    OPERATION_DESCRIPTOR = "OPERATION_DESCRIPTOR"


class DemandSummaryRequirement(str, Enum):
    MUST_CANCEL = "MUST_CANCEL"
    MUST_PROTECT = "MUST_PROTECT"
    OWNER_BINDING = "OWNER_BINDING"
    RETURN_BINDING = "RETURN_BINDING"
    ERROR_PARTITION = "ERROR_PARTITION"
    TERMINAL_ACTION = "TERMINAL_ACTION"
    READ_ONLY = "READ_ONLY"
    CONTAINER_DRAIN = "CONTAINER_DRAIN"
    OWNER_TEARDOWN = "OWNER_TEARDOWN"


class FailureDomainKind(str, Enum):
    """Why a real function-boundary residual cannot remain live."""

    FAILED_OBJECT_TEARDOWN = "FAILED_OBJECT_TEARDOWN"
    TRANSACTION_ABORT = "TRANSACTION_ABORT"
    FATAL_SHUTDOWN = "FATAL_SHUTDOWN"
    CHECKPOINT_STOP = "CHECKPOINT_STOP"
    CALLER_CONTAINMENT = "CALLER_CONTAINMENT"


@dataclass(frozen=True)
class EffectSemanticProvenance:
    kind: EffectProvenanceKind
    subject: str
    site: "SourceSite"
    source_identity: str
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "subject": self.subject,
            "site": self.site.to_dict(),
            "source_identity": self.source_identity,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class OwnershipEdge:
    child: str
    parent: str
    relation: OwnershipRelation
    acquisition_site: "SourceSite"
    publication_sites: tuple["SourceSite", ...] = ()
    escape_state: EscapeState = EscapeState.UNKNOWN
    source_identity: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "child": self.child,
            "parent": self.parent,
            "relation": self.relation.value,
            "acquisition_site": self.acquisition_site.to_dict(),
            "publication_sites": [item.to_dict() for item in self.publication_sites],
            "escape_state": self.escape_state.value,
            "source_identity": self.source_identity,
        }


@dataclass(frozen=True)
class FailureDomainScope:
    action: FailureDomainKind
    allowed_planes: tuple[MetadataPlane, ...]
    allowed_visibility: tuple[EffectVisibility, ...]
    forbidden_categories: tuple[str, ...] = ()
    required_owner_relation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "allowed_planes": [item.value for item in self.allowed_planes],
            "allowed_visibility": [item.value for item in self.allowed_visibility],
            "forbidden_categories": list(self.forbidden_categories),
            "required_owner_relation": self.required_owner_relation,
        }


@dataclass(frozen=True)
class FailureDomainProof:
    kind: FailureDomainKind
    site: "SourceSite"
    owner: str = ""
    via_function: str = ""
    evidence: str = ""
    covered_effects: tuple["MetadataEffect", ...] = ()
    scope: FailureDomainScope | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "site": self.site.to_dict(),
            "owner": self.owner,
            "via_function": self.via_function,
            "evidence": self.evidence,
            "covered_effects": [item.to_dict() for item in self.covered_effects],
            "scope": self.scope.to_dict() if self.scope else None,
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
class OwnerScopeProof:
    kind: OwnerScopeKind
    owner: str
    site: SourceSite
    covered_effects: tuple["MetadataEffect", ...] = ()
    ownership_edges: tuple[OwnershipEdge, ...] = ()
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "owner": self.owner,
            "site": self.site.to_dict(),
            "covered_effects": [item.to_dict() for item in self.covered_effects],
            "ownership_edges": [item.to_dict() for item in self.ownership_edges],
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class OwnerLivenessProof:
    owner: str
    site: SourceSite
    continuation_site: SourceSite
    covered_effects: tuple["MetadataEffect", ...] = ()
    via_function: str = ""
    state: OwnerLivenessState = OwnerLivenessState.OWNER_LIVE
    evidence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "site": self.site.to_dict(),
            "continuation_site": self.continuation_site.to_dict(),
            "covered_effects": [item.to_dict() for item in self.covered_effects],
            "via_function": self.via_function,
            "state": self.state.value,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class DemandSummaryRequest:
    report_id: str
    helper: str
    call_site: SourceSite
    expected_root: str
    required_semantics: DemandSummaryRequirement
    transitive_body_budget: int = 3
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "helper": self.helper,
            "call_site": self.call_site.to_dict(),
            "expected_root": self.expected_root,
            "required_semantics": self.required_semantics.value,
            "transitive_body_budget": self.transitive_body_budget,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class IndirectTargetSet:
    call_site: SourceSite
    receiver_type: str
    ops_table: str
    possible_targets: tuple[str, ...]
    complete: bool
    source_evidence: tuple[SourceSite, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_site": self.call_site.to_dict(),
            "receiver_type": self.receiver_type,
            "ops_table": self.ops_table,
            "possible_targets": list(self.possible_targets),
            "complete": self.complete,
            "source_evidence": [item.to_dict() for item in self.source_evidence],
        }


@dataclass(frozen=True)
class LexicalSuppressionEvidence:
    helper: str
    lexical_rule: str
    suppressed_expression: str
    site: SourceSite
    source_body_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "helper": self.helper,
            "lexical_rule": self.lexical_rule,
            "suppressed_expression": self.suppressed_expression,
            "site": self.site.to_dict(),
            "source_body_available": self.source_body_available,
        }


@dataclass(frozen=True)
class AggregateSnapshotRelation:
    """Source proof that a saved owner field is restored on an error path."""

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
    visibility: EffectVisibility = EffectVisibility.TRANSACTION_LOCAL
    escape_state: EscapeState = EscapeState.PRIVATE
    abort_footprint: tuple[MetadataPlane, ...] = (
        MetadataPlane.STRUCTURAL,
        MetadataPlane.ACCOUNTING,
        MetadataPlane.RECOVERY,
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_root": self.transaction_root,
            "owned_root": self.owned_root,
            "primitive": self.primitive,
            "site": self.site.to_dict(),
            "source_identity": self.source_identity,
            "visibility": self.visibility.value,
            "escape_state": self.escape_state.value,
            "abort_footprint": [item.value for item in self.abort_footprint],
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
    semantic_provenance: tuple[EffectSemanticProvenance, ...] = ()
    visibility: EffectVisibility = EffectVisibility.UNKNOWN

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
        if self.semantic_provenance:
            data["semantic_provenance"] = [
                item.to_dict() for item in self.semantic_provenance
            ]
        data["visibility"] = self.visibility.value
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
    ownership_edges: tuple[OwnershipEdge, ...] = ()
    transitively_destroyed_children: tuple[str, ...] = ()
    nonclosable_effects: tuple[MetadataEffect, ...] = ()

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
            "ownership_edges": [item.to_dict() for item in self.ownership_edges],
            "transitively_destroyed_children": list(
                self.transitively_destroyed_children
            ),
            "nonclosable_effects": [
                effect.to_dict() for effect in self.nonclosable_effects
            ],
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
    owner_scope_proofs: tuple[OwnerScopeProof, ...] = ()
    owner_liveness_proofs: tuple[OwnerLivenessProof, ...] = ()
    demand_summary_requests: tuple[DemandSummaryRequest, ...] = ()
    lexical_suppressions: tuple[LexicalSuppressionEvidence, ...] = ()
    semantic_blockers: tuple[str, ...] = ()

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
            "owner_scope_proofs": [
                item.to_dict() for item in self.owner_scope_proofs
            ],
            "owner_liveness_proofs": [
                item.to_dict() for item in self.owner_liveness_proofs
            ],
            "demand_summary_requests": [
                item.to_dict() for item in self.demand_summary_requests
            ],
            "lexical_suppressions": [
                item.to_dict() for item in self.lexical_suppressions
            ],
            "semantic_blockers": list(self.semantic_blockers),
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
    elif residual_slice.residuals and residual_slice.state in {
        ResidualState.EXPOSED,
        ResidualState.LIVE,
    }:
        uncontained = _uncontained_residuals(residual_slice)
        review_owners = _semantic_review_owners(residual_slice)
        kind = (
            ReportKind.METADATA_RESIDUAL_REVIEW
            if residual_slice.state is ResidualState.EXPOSED
            and uncontained
            and all(_leading_effect_owner(effect.root) in review_owners for effect in uncontained)
            else
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


def _semantic_review_owners(residual_slice: ResidualSlice) -> set[str]:
    prefixes = (
        "owner_scope_escape_review:",
        "conditional_shutdown_review:",
    )
    return {
        blocker.removeprefix(prefix)
        for blocker in residual_slice.semantic_blockers
        for prefix in prefixes
        if blocker.startswith(prefix)
    }


def _leading_effect_owner(root: str) -> str:
    match = re.match(r"[&*()\s]*([A-Za-z_]\w*)", root)
    return match.group(1) if match else ""


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
        if residual_slice.state is ResidualState.LIVE:
            return ResidualClassification.LIVE_METADATA_RESIDUAL
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
