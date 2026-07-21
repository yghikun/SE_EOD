"""Protocol state, failure epochs, effect ownership, join, and widening."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable

from .metadata_event import MetadataEvent, ObjectIdentity, ResolvedObjectRef
from .metadata_protocol import CompletionMode, EffectKind, EffectScope, EffectStatus


class FailureResolution(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    PROPAGATED = "PROPAGATED"
    SENTINEL_HANDLED = "SENTINEL_HANDLED"
    RETRY_SUCCEEDED = "RETRY_SUCCEEDED"
    ABORTED = "ABORTED"
    RECOVERY_DELEGATED = "RECOVERY_DELEGATED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FailureToken:
    failure_id: str
    attempt_id: str
    source_event: str
    error_class: str
    resolution: FailureResolution = FailureResolution.UNRESOLVED
    status_origin: str = "static_return_contract"
    object_ref: ResolvedObjectRef | None = None

    @property
    def unresolved(self) -> bool:
        return self.resolution in {FailureResolution.UNRESOLVED, FailureResolution.UNKNOWN}

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_id": self.failure_id,
            "attempt_id": self.attempt_id,
            "source_event": self.source_event,
            "error_class": self.error_class,
            "resolution": self.resolution.value,
            "status_origin": self.status_origin,
            "object_ref": self.object_ref.to_dict() if self.object_ref else None,
        }


@dataclass(frozen=True)
class EffectRecord:
    effect_id: str
    kind: EffectKind
    object_ref: ResolvedObjectRef
    scope: EffectScope
    owner: str
    status: EffectStatus
    source_event: str
    required: bool = True
    spec_effect_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "effect_id": self.effect_id,
            "kind": self.kind.value,
            "object_ref": self.object_ref.to_dict(),
            "scope": self.scope.value,
            "owner": self.owner,
            "status": self.status.value,
            "source_event": self.source_event,
            "required": self.required,
            "spec_effect_id": self.spec_effect_id or self.effect_id,
        }


@dataclass(frozen=True)
class AccountingObligation:
    obligation_id: str
    subject: ResolvedObjectRef
    required_condition: str
    observed_state: str = "unknown"
    satisfied: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "subject": self.subject.to_dict(),
            "required_condition": self.required_condition,
            "observed_state": self.observed_state,
            "satisfied": self.satisfied,
        }


@dataclass(frozen=True)
class WitnessStep:
    kind: str
    source: str
    detail: str
    line: int = 0
    event_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "source": self.source,
            "detail": self.detail,
            "line": self.line,
            "event_id": self.event_id,
        }


@dataclass
class MetadataOperationInstance:
    operation_id: str
    protocol_id: str
    principal_objects: dict[str, ResolvedObjectRef] = field(default_factory=dict)
    phase_facts: set[str] = field(default_factory=set)
    effect_ledger: dict[str, EffectRecord] = field(default_factory=dict)
    failure_tokens: dict[str, FailureToken] = field(default_factory=dict)
    accounting_obligations: dict[str, AccountingObligation] = field(default_factory=dict)
    completion_mode: CompletionMode | None = None
    uncertainty_causes: set[str] = field(default_factory=set)
    current_attempts: dict[str, int] = field(default_factory=dict)
    witness: list[WitnessStep] = field(default_factory=list)
    return_value: str = ""
    return_outcome: str = ""
    return_attempt_id: str = ""
    return_provenance: str = ""

    def clone(self) -> "MetadataOperationInstance":
        return MetadataOperationInstance(
            operation_id=self.operation_id,
            protocol_id=self.protocol_id,
            principal_objects=dict(self.principal_objects),
            phase_facts=set(self.phase_facts),
            effect_ledger=dict(self.effect_ledger),
            failure_tokens=dict(self.failure_tokens),
            accounting_obligations=dict(self.accounting_obligations),
            completion_mode=self.completion_mode,
            uncertainty_causes=set(self.uncertainty_causes),
            current_attempts=dict(self.current_attempts),
            witness=list(self.witness),
            return_value=self.return_value,
            return_outcome=self.return_outcome,
            return_attempt_id=self.return_attempt_id,
            return_provenance=self.return_provenance,
        )

    def start_attempt(self, role_id: str, event: MetadataEvent) -> str:
        number = self.current_attempts.get(role_id, 0) + 1
        self.current_attempts[role_id] = number
        attempt_id = f"{role_id}@{number}"
        self.principal_objects.setdefault(event.object_ref.role, event.object_ref)
        self.uncertainty_causes.update(event.uncertainty_causes)
        self.witness.append(
            WitnessStep(
                "necessary_step" if event.necessary else "best_effort_step",
                event.source_location.file,
                f"{event.callee} starts {attempt_id}",
                event.source_location.start_line,
                event.event_id,
            )
        )
        return attempt_id

    def record_failure(
        self, event: MetadataEvent, attempt_id: str, error_class: str, origin: str
    ) -> FailureToken:
        failure_id = _stable_id("failure", event.event_id, attempt_id, error_class)
        token = FailureToken(
            failure_id=failure_id,
            attempt_id=attempt_id,
            source_event=event.event_id,
            error_class=error_class,
            status_origin=origin,
            object_ref=event.object_ref,
        )
        self.failure_tokens[failure_id] = token
        self.witness.append(
            WitnessStep(
                "failure",
                event.source_location.file,
                f"{event.callee} -> {error_class} ({attempt_id})",
                event.source_location.start_line,
                event.event_id,
            )
        )
        return token

    def resolve_failure(
        self,
        failure_id: str,
        resolution: FailureResolution,
        detail: str,
        *,
        source: str = "",
        line: int = 0,
    ) -> None:
        token = self.failure_tokens[failure_id]
        self.failure_tokens[failure_id] = replace(token, resolution=resolution)
        self.witness.append(WitnessStep("handler", source, detail, line))

    def resolve_prior_attempts(self, role_id: str, successful_attempt: str) -> None:
        for failure_id, token in list(self.failure_tokens.items()):
            if token.attempt_id.startswith(f"{role_id}@") and token.attempt_id != successful_attempt:
                self.failure_tokens[failure_id] = replace(
                    token, resolution=FailureResolution.RETRY_SUCCEEDED
                )

    def add_effect(self, effect: EffectRecord) -> None:
        self.effect_ledger[effect.effect_id] = effect

    def compensate(self, effect_id: str, object_ref: ResolvedObjectRef) -> bool:
        matches = [
            (instance_id, effect)
            for instance_id, effect in self.effect_ledger.items()
            if (instance_id == effect_id or effect.spec_effect_id == effect_id)
            and _same_exact_object(effect.object_ref, object_ref)
        ]
        if not matches:
            self.uncertainty_causes.add("unmatched_compensation_object")
            return False
        for instance_id, effect in matches:
            self.effect_ledger[instance_id] = replace(effect, status=EffectStatus.COMPENSATED)
        return True

    def transfer(
        self,
        effect_ids: Iterable[str],
        object_ref: ResolvedObjectRef,
        mode: CompletionMode,
        owner: str,
        guard: str,
    ) -> None:
        if not owner or not guard or object_ref.identity is ObjectIdentity.UNKNOWN:
            self.uncertainty_causes.add("unproven_handler_transfer")
            return
        for effect_id in effect_ids:
            matches = [
                (instance_id, effect)
                for instance_id, effect in self.effect_ledger.items()
                if (instance_id == effect_id or effect.spec_effect_id == effect_id)
                and _same_exact_object(effect.object_ref, object_ref)
            ]
            if not matches:
                self.uncertainty_causes.add("unmatched_handler_effect")
                continue
            for instance_id, effect in matches:
                if mode is CompletionMode.ABORTED and effect.scope is not EffectScope.TRANSACTION_SCOPED:
                    continue
                self.effect_ledger[instance_id] = replace(
                    effect, status=EffectStatus.TRANSFERRED, owner=owner
                )
        self.completion_mode = mode

    def abort_transaction(self, owner: str, guard: str) -> None:
        for effect_id, effect in list(self.effect_ledger.items()):
            if effect.scope is EffectScope.TRANSACTION_SCOPED:
                self.effect_ledger[effect_id] = replace(
                    effect, status=EffectStatus.TRANSFERRED, owner=owner
                )
        if owner and guard:
            self.completion_mode = CompletionMode.ABORTED
            for failure_id, token in list(self.failure_tokens.items()):
                if token.unresolved:
                    self.failure_tokens[failure_id] = replace(
                        token, resolution=FailureResolution.ABORTED
                    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation_id": self.operation_id,
            "protocol_id": self.protocol_id,
            "principal_objects": {
                key: value.to_dict() for key, value in sorted(self.principal_objects.items())
            },
            "phase_facts": sorted(self.phase_facts),
            "effect_ledger": [self.effect_ledger[key].to_dict() for key in sorted(self.effect_ledger)],
            "failure_tokens": [self.failure_tokens[key].to_dict() for key in sorted(self.failure_tokens)],
            "accounting_obligations": [
                self.accounting_obligations[key].to_dict()
                for key in sorted(self.accounting_obligations)
            ],
            "completion_mode": self.completion_mode.value if self.completion_mode else None,
            "uncertainty_causes": sorted(self.uncertainty_causes),
            "current_attempts": dict(sorted(self.current_attempts.items())),
            "witness": [item.to_dict() for item in self.witness],
            "return_value": self.return_value,
            "return_outcome": self.return_outcome,
            "return_attempt_id": self.return_attempt_id,
            "return_provenance": self.return_provenance,
        }


def join_operation_states(
    left: MetadataOperationInstance, right: MetadataOperationInstance
) -> MetadataOperationInstance:
    if (left.protocol_id, left.operation_id) != (right.protocol_id, right.operation_id):
        raise ValueError("cannot join operation states from different protocols")
    joined = MetadataOperationInstance(left.operation_id, left.protocol_id)
    joined.principal_objects = {}
    for key in sorted(set(left.principal_objects) | set(right.principal_objects)):
        value = left.principal_objects.get(key) or right.principal_objects.get(key)
        assert value is not None
        joined.principal_objects[key] = value
    joined.phase_facts = left.phase_facts & right.phase_facts
    joined.current_attempts = {
        key: max(left.current_attempts.get(key, 0), right.current_attempts.get(key, 0))
        for key in set(left.current_attempts) | set(right.current_attempts)
    }
    joined.uncertainty_causes = left.uncertainty_causes | right.uncertainty_causes
    for effect_id in sorted(set(left.effect_ledger) | set(right.effect_ledger)):
        l_effect = left.effect_ledger.get(effect_id)
        r_effect = right.effect_ledger.get(effect_id)
        if l_effect is None or r_effect is None:
            base = l_effect or r_effect
            assert base is not None
            joined.effect_ledger[effect_id] = replace(base, status=EffectStatus.UNKNOWN)
            joined.uncertainty_causes.add("effect_present_on_subset_of_paths")
        elif l_effect.status is r_effect.status:
            joined.effect_ledger[effect_id] = l_effect
        else:
            joined.effect_ledger[effect_id] = replace(l_effect, status=EffectStatus.UNKNOWN)
            joined.uncertainty_causes.add("effect_status_join")
    for failure_id in sorted(set(left.failure_tokens) | set(right.failure_tokens)):
        l_token = left.failure_tokens.get(failure_id)
        r_token = right.failure_tokens.get(failure_id)
        if l_token is None or r_token is None:
            token = l_token or r_token
            assert token is not None
            joined.failure_tokens[failure_id] = replace(
                token, resolution=FailureResolution.UNKNOWN
            )
            joined.uncertainty_causes.add("failure_present_on_subset_of_paths")
        elif l_token.resolution is r_token.resolution:
            joined.failure_tokens[failure_id] = l_token
        else:
            joined.failure_tokens[failure_id] = replace(
                l_token, resolution=FailureResolution.UNKNOWN
            )
            joined.uncertainty_causes.add("failure_resolution_join")
    joined.accounting_obligations = dict(left.accounting_obligations)
    for key, value in right.accounting_obligations.items():
        existing = joined.accounting_obligations.get(key)
        if existing is None:
            joined.accounting_obligations[key] = replace(value, satisfied=None)
        elif existing.satisfied != value.satisfied:
            joined.accounting_obligations[key] = replace(existing, satisfied=None)
            joined.uncertainty_causes.add("accounting_join")
    joined.completion_mode = (
        left.completion_mode
        if left.completion_mode is right.completion_mode
        else CompletionMode.ANALYSIS_UNKNOWN
    )
    joined.witness = _common_prefix(left.witness, right.witness)
    return joined


def widen_operation_states(states: Iterable[MetadataOperationInstance]) -> MetadataOperationInstance:
    items = list(states)
    if not items:
        raise ValueError("cannot widen an empty state set")
    widened = items[0].clone()
    for state in items[1:]:
        widened = join_operation_states(widened, state)
    widened.uncertainty_causes.add("widening_precision_loss")
    widened.completion_mode = CompletionMode.ANALYSIS_UNKNOWN
    return widened


def _same_exact_object(left: ResolvedObjectRef, right: ResolvedObjectRef) -> bool:
    return (
        left.identity is not ObjectIdentity.UNKNOWN
        and right.identity is not ObjectIdentity.UNKNOWN
        and left.role == right.role
        and left.expression == right.expression
    )


def _common_prefix(left: list[WitnessStep], right: list[WitnessStep]) -> list[WitnessStep]:
    result: list[WitnessStep] = []
    for l_item, r_item in zip(left, right):
        if l_item != r_item:
            break
        result.append(l_item)
    return result


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}_" + hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()[:20]
