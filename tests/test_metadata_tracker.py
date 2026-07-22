from src.frontend.model import SourceRange
from src.metadata_event import EventStrength, MetadataEvent, MetadataEventKind, ObjectIdentity, ResolvedObjectRef
from src.metadata_protocol import CompletionMode, EffectKind, EffectScope, EffectStatus
from src.metadata_tracker import (
    EffectRecord,
    FailureResolution,
    MetadataOperationInstance,
    OperationControlState,
    join_operation_states,
    widen_operation_states,
)


def _object(identity=ObjectIdentity.EXACT):
    return ResolvedObjectRef("inode", "inode", identity, "sym_inode")


def _event(event_id="event"):
    return MetadataEvent(
        event_id,
        "protocol",
        "operation",
        MetadataEventKind.METADATA_UPDATE,
        _object(),
        None,
        "",
        "always",
        EventStrength.MUST,
        SourceRange("fixture.c", 10, 20, 2, 2),
        callee_role_id="load",
        callee="load_inode",
        necessary=True,
    )


def test_retry_starts_new_attempt_and_resolves_only_prior_epoch():
    state = MetadataOperationInstance("operation", "protocol")
    first = state.start_attempt("load", _event("first"))
    token = state.record_failure(_event("first"), first, "ret < 0", "contract")
    second = state.start_attempt("load", _event("second"))

    state.resolve_prior_attempts("load", second)

    assert first == "load@1"
    assert second == "load@2"
    assert state.failure_tokens[token.failure_id].resolution is FailureResolution.RETRY_SUCCEEDED
    assert state.control_state is OperationControlState.RETRYING


def test_abort_closes_only_transaction_scoped_effects():
    state = MetadataOperationInstance("operation", "protocol")
    state.add_effect(EffectRecord("transaction", EffectKind.METADATA_UPDATE, _object(), EffectScope.TRANSACTION_SCOPED, "transaction", EffectStatus.OPEN, "event"))
    state.add_effect(EffectRecord("global", EffectKind.POINTER_UPDATE, _object(), EffectScope.IN_MEMORY_GLOBAL, "function", EffectStatus.OPEN, "event"))

    state.abort_transaction("transaction_manager", "abort_called")

    assert state.effect_ledger["transaction"].status is EffectStatus.TRANSFERRED
    assert state.effect_ledger["global"].status is EffectStatus.OPEN


def test_unknown_object_cannot_compensate_exact_effect():
    state = MetadataOperationInstance("operation", "protocol")
    state.add_effect(EffectRecord("effect", EffectKind.METADATA_UPDATE, _object(), EffectScope.PERSISTENT, "operation", EffectStatus.OPEN, "event"))

    assert not state.compensate("effect", _object(ObjectIdentity.UNKNOWN))
    assert state.effect_ledger["effect"].status is EffectStatus.OPEN


def test_join_open_and_completed_effect_becomes_unknown():
    left = MetadataOperationInstance("operation", "protocol")
    right = MetadataOperationInstance("operation", "protocol")
    base = EffectRecord("effect", EffectKind.METADATA_UPDATE, _object(), EffectScope.PERSISTENT, "operation", EffectStatus.OPEN, "event")
    left.add_effect(base)
    right.add_effect(EffectRecord(**{**base.__dict__, "status": EffectStatus.COMMITTED}))

    joined = join_operation_states(left, right)

    assert joined.effect_ledger["effect"].status is EffectStatus.UNKNOWN
    assert "effect_status_join" in joined.uncertainty_causes


def test_failures_from_different_attempts_are_not_text_merged():
    state = MetadataOperationInstance("operation", "protocol")
    event = _event()
    first = state.start_attempt("load", event)
    first_token = state.record_failure(event, first, "-EIO", "contract")
    second = state.start_attempt("load", event)
    second_token = state.record_failure(event, second, "-EIO", "contract")

    assert first_token.failure_id != second_token.failure_id
    assert len(state.failure_tokens) == 2


def test_widening_preserves_obligations_and_records_precision_loss():
    left = MetadataOperationInstance("operation", "protocol")
    right = MetadataOperationInstance("operation", "protocol")
    left.add_effect(EffectRecord("effect", EffectKind.METADATA_UPDATE, _object(), EffectScope.PERSISTENT, "operation", EffectStatus.OPEN, "event"))

    widened = widen_operation_states([left, right])

    assert "effect" in widened.effect_ledger
    assert widened.effect_ledger["effect"].status is EffectStatus.UNKNOWN
    assert widened.completion_mode is CompletionMode.ANALYSIS_UNKNOWN
    assert "widening_precision_loss" in widened.uncertainty_causes
    assert widened.control_state is OperationControlState.UNKNOWN


def test_operation_control_state_reaches_exit_through_failure_retry_and_commit():
    state = MetadataOperationInstance("operation", "protocol")
    event = _event()

    first = state.start_attempt("load", event)
    state.record_failure(event, first, "-EIO", "contract")
    second = state.start_attempt("load", event)
    state.resolve_prior_attempts("load", second)
    state.complete(CompletionMode.COMMITTED, "retry succeeded")
    state.exit_operation("return 0", source="fixture.c", line=3)

    assert state.control_state is OperationControlState.EXITED
    assert [item.to_state for item in state.control_history] == [
        OperationControlState.ACTIVE,
        OperationControlState.HANDLING_FAILURE,
        OperationControlState.RETRYING,
        OperationControlState.COMMITTING,
        OperationControlState.EXITED,
    ]


def test_illegal_transition_after_exit_becomes_unknown():
    state = MetadataOperationInstance("operation", "protocol")
    state.start_attempt("load", _event())
    state.complete(CompletionMode.COMMITTED, "done")
    state.exit_operation("return 0")

    assert not state.transition_control(OperationControlState.ACTIVE, "restart")
    assert state.control_state is OperationControlState.UNKNOWN
    assert "invalid_control_transition:EXITED->ACTIVE" in state.uncertainty_causes


def test_join_of_different_control_states_is_unknown():
    left = MetadataOperationInstance("operation", "protocol")
    right = MetadataOperationInstance("operation", "protocol")
    event = _event()
    left.start_attempt("load", event)
    attempt = right.start_attempt("load", event)
    right.record_failure(event, attempt, "-EIO", "contract")

    joined = join_operation_states(left, right)

    assert joined.control_state is OperationControlState.UNKNOWN
    assert "control_state_join" in joined.uncertainty_causes
