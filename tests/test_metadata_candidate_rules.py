from src.frontend.model import SourceRange
from src.metadata_candidate_rules import generate_candidates
from src.metadata_event import EventStrength, MetadataEvent, MetadataEventKind, ObjectIdentity, ResolvedObjectRef
from src.metadata_protocol import CompletionMode, EffectKind, EffectScope, EffectStatus, LegalExitKind, MetadataProtocol, ReturnOutcome, ViolationType
from src.metadata_tracker import (
    AccountingObligation,
    EffectRecord,
    FailureResolution,
    MetadataOperationInstance,
    OperationControlState,
)


def _protocol() -> MetadataProtocol:
    return MetadataProtocol.from_dict(
        {
            "schema_version": 1,
            "protocol_version": "1.0.0",
            "protocol_id": "test.candidates",
            "filesystems": ["fixture"],
            "linux_versions": ["test"],
            "phases": ["SUCCESS", "FAILURE"],
            "operations": [{"operation_id": "op", "entry_functions": ["work"], "principal_objects": [{"role": "inode", "selector": "arg0"}], "callee_roles": []}],
            "return_contracts": [
                {"contract_id": "success", "operation_id": "op", "guard": "ret == 0", "outcome": "success"},
                {"contract_id": "failure", "operation_id": "op", "guard": "ret < 0", "outcome": "failure"},
            ],
            "effects": [], "compensations": [], "handlers": [], "accounting_constraints": [],
            "legal_exits": [
                {"exit_id": "success", "operation_id": "op", "kind": "success", "phases": ["SUCCESS"], "completion_modes": ["COMMITTED"], "return_outcomes": ["success"]},
                {"exit_id": "failure", "operation_id": "op", "kind": "failure", "phases": ["FAILURE"], "completion_modes": ["ROLLED_BACK"], "return_outcomes": ["failure"]},
            ],
        }
    )


def _object():
    return ResolvedObjectRef("inode", "inode", ObjectIdentity.EXACT, "sym_inode")


def _state() -> MetadataOperationInstance:
    state = MetadataOperationInstance("op", "test.candidates")
    state.principal_objects["inode"] = _object()
    return state


def _finish(state: MetadataOperationInstance, mode: CompletionMode) -> None:
    if state.control_state is OperationControlState.INIT:
        state.transition_control(OperationControlState.ACTIVE, "fixture operation")
    state.complete(mode, "fixture completion")
    state.exit_operation("fixture return")


def _event():
    return MetadataEvent("event", "test.candidates", "op", MetadataEventKind.METADATA_UPDATE, _object(), None, "", "always", EventStrength.MUST, SourceRange("fixture.c", 0, 10, 1, 1), callee_role_id="step", callee="necessary", necessary=True)


def test_unresolved_failure_at_success_is_failure_reported_as_success():
    state = _state()
    attempt = state.start_attempt("step", _event())
    state.record_failure(_event(), attempt, "ret < 0", "contract")
    _finish(state, CompletionMode.COMMITTED)

    candidates, unknown = generate_candidates(state, _protocol(), phase="SUCCESS", outcome=ReturnOutcome.SUCCESS, exit_kind=LegalExitKind.SUCCESS)

    assert not unknown
    assert [item.violation_type for item in candidates] == [ViolationType.FAILURE_REPORTED_AS_SUCCESS]
    assert candidates[0].representative_witness


def test_resolved_failure_is_not_a_candidate():
    state = _state()
    attempt = state.start_attempt("step", _event())
    token = state.record_failure(_event(), attempt, "ret < 0", "contract")
    state.resolve_failure(token.failure_id, FailureResolution.PROPAGATED, "returned error")
    _finish(state, CompletionMode.COMMITTED)

    candidates, unknown = generate_candidates(state, _protocol(), phase="SUCCESS", outcome=ReturnOutcome.SUCCESS, exit_kind=LegalExitKind.SUCCESS)

    assert not candidates
    assert not unknown


def test_open_effect_at_failure_is_incomplete_completion():
    state = _state()
    state.add_effect(EffectRecord("effect", EffectKind.METADATA_UPDATE, _object(), EffectScope.PERSISTENT, "op", EffectStatus.OPEN, "event"))
    _finish(state, CompletionMode.ROLLED_BACK)

    candidates, unknown = generate_candidates(state, _protocol(), phase="FAILURE", outcome=ReturnOutcome.FAILURE, exit_kind=LegalExitKind.FAILURE)

    assert not unknown
    assert candidates[0].violation_type is ViolationType.INCOMPLETE_FAILURE_COMPLETION


def test_unknown_effect_is_quarantined_not_reported():
    state = _state()
    state.add_effect(EffectRecord("effect", EffectKind.METADATA_UPDATE, _object(), EffectScope.PERSISTENT, "op", EffectStatus.UNKNOWN, "event"))
    _finish(state, CompletionMode.ROLLED_BACK)

    candidates, unknown = generate_candidates(state, _protocol(), phase="FAILURE", outcome=ReturnOutcome.FAILURE, exit_kind=LegalExitKind.FAILURE)

    assert not candidates
    assert unknown[0].to_dict()["classification"] == "ANALYSIS_UNKNOWN"


def test_illegal_phase_return_combination_is_metadata_divergence():
    state = _state()
    _finish(state, CompletionMode.COMMITTED)

    candidates, unknown = generate_candidates(state, _protocol(), phase="FAILURE", outcome=ReturnOutcome.SUCCESS, exit_kind=LegalExitKind.SUCCESS)

    assert not unknown
    assert candidates[0].violation_type is ViolationType.METADATA_STATE_DIVERGENCE


def test_unknown_accounting_obligation_is_quarantined():
    state = _state()
    state.accounting_obligations["reservation"] = AccountingObligation("reservation", _object(), "pending => reserved")
    _finish(state, CompletionMode.COMMITTED)

    candidates, unknown = generate_candidates(state, _protocol(), phase="SUCCESS", outcome=ReturnOutcome.SUCCESS, exit_kind=LegalExitKind.SUCCESS)

    assert not candidates
    assert unknown


def test_completed_effect_and_satisfied_accounting_allow_exit():
    state = _state()
    state.add_effect(EffectRecord("effect", EffectKind.METADATA_UPDATE, _object(), EffectScope.PERSISTENT, "op", EffectStatus.COMMITTED, "event"))
    state.accounting_obligations["reservation"] = AccountingObligation("reservation", _object(), "pending => reserved", "reserved", True)
    _finish(state, CompletionMode.COMMITTED)

    candidates, unknown = generate_candidates(state, _protocol(), phase="SUCCESS", outcome=ReturnOutcome.SUCCESS, exit_kind=LegalExitKind.SUCCESS)

    assert not candidates
    assert not unknown


def test_completion_without_control_exit_is_analysis_unknown():
    state = _state()
    state.transition_control(OperationControlState.ACTIVE, "fixture operation")
    state.complete(CompletionMode.COMMITTED, "fixture completion")

    candidates, unknown = generate_candidates(
        state,
        _protocol(),
        phase="SUCCESS",
        outcome=ReturnOutcome.SUCCESS,
        exit_kind=LegalExitKind.SUCCESS,
    )

    assert not candidates
    assert unknown
    assert "operation control state has not exited: COMMITTING" in unknown[0].reasons
    assert [item["to"] for item in unknown[0].control_trace] == [
        "ACTIVE",
        "COMMITTING",
    ]
