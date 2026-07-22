"""Legal-exit verification and conservative MOCC-SE candidate generation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable

from .metadata_protocol import CompletionMode, LegalExitKind, MetadataProtocol, ReturnOutcome, ViolationType
from .metadata_tracker import (
    EffectRecord,
    FailureToken,
    MetadataOperationInstance,
    OperationControlState,
)


@dataclass(frozen=True)
class ExitVerification:
    legal: bool
    analysis_unknown: bool
    reason: str
    exit_id: str = ""


@dataclass(frozen=True)
class MetadataCandidate:
    candidate_id: str
    protocol_id: str
    operation_id: str
    violation_type: ViolationType
    exit_kind: LegalExitKind
    exit_id: str
    principal_objects: tuple[dict[str, Any], ...]
    open_effects: tuple[dict[str, Any], ...]
    unresolved_failures: tuple[dict[str, Any], ...]
    accounting_state: tuple[dict[str, Any], ...]
    representative_witness: tuple[dict[str, Any], ...]
    uncertainty_causes: tuple[str, ...]
    static_certainty: str
    return_attempt_id: str = ""
    return_provenance: str = ""
    control_trace: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "protocol_id": self.protocol_id,
            "operation_id": self.operation_id,
            "violation_type": self.violation_type.value,
            "exit_kind": self.exit_kind.value,
            "exit_id": self.exit_id,
            "principal_objects": list(self.principal_objects),
            "open_effects": list(self.open_effects),
            "unresolved_failures": list(self.unresolved_failures),
            "accounting_state": list(self.accounting_state),
            "representative_witness": list(self.representative_witness),
            "uncertainty_causes": list(self.uncertainty_causes),
            "static_certainty": self.static_certainty,
            "return_attempt_id": self.return_attempt_id,
            "return_provenance": self.return_provenance,
            "control_trace": list(self.control_trace),
        }


@dataclass(frozen=True)
class AnalysisUnknown:
    protocol_id: str
    operation_id: str
    exit_kind: LegalExitKind
    exit_id: str
    reasons: tuple[str, ...]
    witness: tuple[dict[str, Any], ...]
    control_trace: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "operation_id": self.operation_id,
            "exit_kind": self.exit_kind.value,
            "exit_id": self.exit_id,
            "classification": "ANALYSIS_UNKNOWN",
            "reasons": list(self.reasons),
            "representative_witness": list(self.witness),
            "control_trace": list(self.control_trace),
        }


def verify_success_exit(
    state: MetadataOperationInstance,
    protocol: MetadataProtocol,
    phase: str,
    outcome: ReturnOutcome,
) -> ExitVerification:
    control = _verify_control_exit(state)
    if control is not None:
        return control
    exit_spec = _matching_exit(protocol, state.operation_id, LegalExitKind.SUCCESS, phase, outcome)
    if exit_spec is None:
        return ExitVerification(False, False, "phase or return outcome is not a legal success exit")
    if state.completion_mode not in exit_spec.completion_modes:
        return ExitVerification(False, False, "completion mode is not legal for success exit", exit_spec.exit_id)
    if state.uncertainty_causes:
        return ExitVerification(False, True, "state has unresolved uncertainty", exit_spec.exit_id)
    unresolved = [token for token in state.failure_tokens.values() if token.unresolved]
    if unresolved:
        return ExitVerification(False, False, "necessary failure remains unresolved", exit_spec.exit_id)
    open_effects = [effect for effect in state.effect_ledger.values() if effect.required and effect.status.value == "OPEN"]
    if open_effects:
        return ExitVerification(False, False, "required effect remains open", exit_spec.exit_id)
    obligations = tuple(state.accounting_obligations.values())
    if any(obligation.satisfied is False for obligation in obligations):
        return ExitVerification(False, False, "accounting obligation is violated", exit_spec.exit_id)
    if any(obligation.satisfied is None for obligation in obligations):
        return ExitVerification(False, True, "accounting obligation is not definitely satisfied", exit_spec.exit_id)
    return ExitVerification(True, False, "legal success exit", exit_spec.exit_id)


def verify_failure_exit(
    state: MetadataOperationInstance,
    protocol: MetadataProtocol,
    phase: str,
    outcome: ReturnOutcome,
) -> ExitVerification:
    control = _verify_control_exit(state)
    if control is not None:
        return control
    exit_spec = _matching_exit(protocol, state.operation_id, LegalExitKind.FAILURE, phase, outcome)
    if exit_spec is None:
        return ExitVerification(False, False, "phase or return outcome is not a legal failure exit")
    if state.completion_mode not in exit_spec.completion_modes:
        return ExitVerification(False, False, "completion mode is not legal for failure exit", exit_spec.exit_id)
    if "stale_result_provenance" in state.phase_facts:
        return ExitVerification(False, False, "metadata changed after the returned failure attempt", exit_spec.exit_id)
    invalid_effects = [
        effect
        for effect in state.effect_ledger.values()
        if effect.required and effect.status.value in {"OPEN", "UNKNOWN"}
    ]
    if invalid_effects:
        if any(effect.status.value == "UNKNOWN" for effect in invalid_effects):
            return ExitVerification(False, True, "effect completion is unknown", exit_spec.exit_id)
        return ExitVerification(False, False, "required effect remains open", exit_spec.exit_id)
    if state.uncertainty_causes:
        return ExitVerification(False, True, "state has unresolved uncertainty", exit_spec.exit_id)
    return ExitVerification(True, False, "legal failure exit", exit_spec.exit_id)


def generate_candidates(
    state: MetadataOperationInstance,
    protocol: MetadataProtocol,
    *,
    phase: str,
    outcome: ReturnOutcome,
    exit_kind: LegalExitKind,
) -> tuple[tuple[MetadataCandidate, ...], tuple[AnalysisUnknown, ...]]:
    if exit_kind is LegalExitKind.SUCCESS:
        verification = verify_success_exit(state, protocol, phase, outcome)
    else:
        verification = verify_failure_exit(state, protocol, phase, outcome)
    if verification.legal:
        return (), ()
    if verification.analysis_unknown:
        return (), (_unknown(state, exit_kind, verification.exit_id, verification.reason),)

    candidates: list[MetadataCandidate] = []
    if exit_kind is LegalExitKind.SUCCESS:
        unresolved = tuple(token for token in state.failure_tokens.values() if token.unresolved)
        open_effects = tuple(
            effect for effect in state.effect_ledger.values() if effect.required and effect.status.value == "OPEN"
        )
        if unresolved:
            candidates.append(
                _candidate(
                    state,
                    protocol,
                    ViolationType.FAILURE_REPORTED_AS_SUCCESS,
                    exit_kind,
                    verification.exit_id,
                    unresolved,
                    open_effects,
                )
            )
        elif open_effects:
            candidates.append(
                _candidate(
                    state,
                    protocol,
                    ViolationType.INCOMPLETE_FAILURE_COMPLETION,
                    exit_kind,
                    verification.exit_id,
                    (),
                    open_effects,
                )
            )
    else:
        open_effects = tuple(
            effect
            for effect in state.effect_ledger.values()
            if effect.required and effect.status.value in {"OPEN", "UNKNOWN"}
        )
        if open_effects:
            candidates.append(
                _candidate(
                    state,
                    protocol,
                    ViolationType.INCOMPLETE_FAILURE_COMPLETION,
                    exit_kind,
                    verification.exit_id,
                    (),
                    open_effects,
                )
            )
    if not candidates:
        candidates.append(
            _candidate(
                state,
                protocol,
                ViolationType.METADATA_STATE_DIVERGENCE,
                exit_kind,
                verification.exit_id,
                (),
                (),
            )
        )
    return tuple(candidates), ()


def _matching_exit(protocol, operation_id, kind, phase, outcome):
    for exit_spec in protocol.legal_exits:
        if (
            exit_spec.operation_id == operation_id
            and exit_spec.kind is kind
            and phase in exit_spec.phases
            and outcome in exit_spec.return_outcomes
        ):
            return exit_spec
    return None


def _verify_control_exit(
    state: MetadataOperationInstance,
) -> ExitVerification | None:
    if state.control_state is OperationControlState.UNKNOWN:
        return ExitVerification(
            False,
            True,
            "operation control state is unknown",
        )
    if state.control_state is not OperationControlState.EXITED:
        return ExitVerification(
            False,
            True,
            f"operation control state has not exited: {state.control_state.value}",
        )
    return None


def _candidate(
    state: MetadataOperationInstance,
    protocol: MetadataProtocol,
    violation_type: ViolationType,
    exit_kind: LegalExitKind,
    exit_id: str,
    failures: Iterable[FailureToken],
    effects: Iterable[EffectRecord],
) -> MetadataCandidate:
    failure_dicts = tuple(item.to_dict() for item in failures)
    effect_dicts = tuple(item.to_dict() for item in effects)
    candidate_id = _stable_id(
        protocol.protocol_id,
        state.operation_id,
        violation_type.value,
        exit_id,
        tuple(item.failure_id for item in failures),
        tuple(item.effect_id for item in effects),
    )
    certainty = "medium" if state.uncertainty_causes else "high"
    return MetadataCandidate(
        candidate_id=candidate_id,
        protocol_id=protocol.protocol_id,
        operation_id=state.operation_id,
        violation_type=violation_type,
        exit_kind=exit_kind,
        exit_id=exit_id,
        principal_objects=tuple(value.to_dict() for value in state.principal_objects.values()),
        open_effects=effect_dicts,
        unresolved_failures=failure_dicts,
        accounting_state=tuple(value.to_dict() for value in state.accounting_obligations.values()),
        representative_witness=tuple(value.to_dict() for value in state.witness),
        uncertainty_causes=tuple(sorted(state.uncertainty_causes)),
        static_certainty=certainty,
        return_attempt_id=state.return_attempt_id,
        return_provenance=state.return_provenance,
        control_trace=tuple(item.to_dict() for item in state.control_history),
    )


def _unknown(
    state: MetadataOperationInstance,
    exit_kind: LegalExitKind,
    exit_id: str,
    reason: str,
) -> AnalysisUnknown:
    return AnalysisUnknown(
        state.protocol_id,
        state.operation_id,
        exit_kind,
        exit_id,
        tuple(sorted(set(state.uncertainty_causes) | {reason})),
        tuple(value.to_dict() for value in state.witness),
        tuple(value.to_dict() for value in state.control_history),
    )


def _stable_id(*parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return "moc_" + hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()[:20]
