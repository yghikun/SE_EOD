import json
import shutil
from pathlib import Path

import pytest

from src.metadata_protocol import (
    CompletionMode,
    EffectKind,
    EffectScope,
    EffectStatus,
    MetadataProtocol,
    MetadataProtocolValidationError,
    ReturnOutcome,
    ViolationType,
    load_metadata_protocols,
)


ROOT = Path(__file__).parents[1]
VALID_FIXTURE = ROOT / "configs" / "metadata_protocols" / "example_replay_recovery_v1.json"
INVALID_FIXTURE = ROOT / "tests" / "fixtures" / "metadata_protocol_invalid_duplicate_event.json"


def _payload() -> dict:
    return json.loads(VALID_FIXTURE.read_text(encoding="utf-8"))


def _protocol() -> MetadataProtocol:
    return MetadataProtocol.from_dict(_payload())


def _raises_with(mutator, text: str) -> None:
    payload = _payload()
    mutator(payload)
    with pytest.raises(MetadataProtocolValidationError, match=text):
        MetadataProtocol.from_dict(payload)


def test_valid_fixture_loads_and_exposes_all_m0_sections():
    protocol = _protocol()

    assert protocol.schema_version == 1
    assert protocol.protocol_version == "1.0.0"
    assert protocol.protocol_id == "mocc.replay_recovery.example"
    assert protocol.operations[0].operation_id == "replay_metadata"
    assert protocol.effects[0].scope is EffectScope.PERSISTENT
    assert protocol.handlers[0].completion_mode is CompletionMode.RECOVERY_DELEGATED
    assert protocol.legal_exits[0].kind.value == "success"


def test_json_round_trip_preserves_stable_ids_and_values():
    protocol = _protocol()

    restored = MetadataProtocol.from_json(protocol.to_json())

    assert restored.to_dict() == protocol.to_dict()
    assert [event.event_id for event in restored.effects] == ["replay.effect.created"]
    assert restored.return_contracts[0].outcome is ReturnOutcome.EXPECTED_SENTINEL


def test_json_write_and_read_round_trip(tmp_path):
    protocol = _protocol()
    target = tmp_path / "protocol.json"

    protocol.write_json(target)

    assert MetadataProtocol.read_json(target).to_dict() == protocol.to_dict()
    assert target.read_text(encoding="utf-8").endswith("\n")


def test_operation_discovery_context_is_optional_and_round_trips():
    payload = _payload()
    payload["operations"][0]["discovery"] = {
        "required_callees": ["load_replay_record"],
        "required_fields": ["i_extra_isize"],
        "forbidden_callees": ["bypass_replay"],
        "semantic_patterns": ["failure_return_mismatch"],
        "minimum_role_coverage": 0.75,
    }

    protocol = MetadataProtocol.from_dict(payload)
    discovery = protocol.operations[0].discovery

    assert discovery.required_callees == ("load_replay_record",)
    assert discovery.required_fields == ("i_extra_isize",)
    assert discovery.forbidden_callees == ("bypass_replay",)
    assert discovery.semantic_patterns == ("failure_return_mismatch",)
    assert discovery.minimum_role_coverage == 0.75
    assert MetadataProtocol.from_json(protocol.to_json()).to_dict() == protocol.to_dict()


def test_operation_discovery_context_rejects_invalid_coverage():
    _raises_with(
        lambda payload: payload["operations"][0].update(
            {"discovery": {"minimum_role_coverage": 1.2}}
        ),
        r"minimum_role_coverage: expected a number between 0\.0 and 1\.0",
    )


def test_operation_discovery_rejects_unknown_semantic_pattern():
    _raises_with(
        lambda payload: payload["operations"][0].update(
            {"discovery": {"semantic_patterns": ["function_name_guess"]}}
        ),
        r"semantic_patterns: unsupported semantic pattern",
    )


def test_operation_entry_functions_are_optional_regression_seeds():
    payload = _payload()
    payload["operations"][0]["entry_functions"] = []

    protocol = MetadataProtocol.from_dict(payload)

    assert protocol.operations[0].entry_functions == ()


def test_enum_values_are_explicit_and_do_not_overlap_resource_state_contract():
    assert EffectKind.POINTER_UPDATE.value == "POINTER_UPDATE"
    assert EffectStatus.UNKNOWN.value == "UNKNOWN"
    assert ViolationType.METADATA_STATE_DIVERGENCE.value == "metadata_state_divergence"


def test_invalid_fixture_rejects_duplicate_event_id():
    with pytest.raises(MetadataProtocolValidationError, match="duplicate event_id"):
        MetadataProtocol.from_json(INVALID_FIXTURE.read_text(encoding="utf-8"))


def test_unknown_enum_is_rejected_with_field_path():
    _raises_with(
        lambda payload: payload["effects"][0].update({"scope": "GLOBAL"}),
        r"protocol\.effects\[0\]\.scope: unknown EffectScope",
    )


def test_effect_without_scope_is_rejected():
    _raises_with(
        lambda payload: payload["effects"][0].pop("scope"),
        r"protocol\.effects\[0\]\.scope: required field is missing",
    )


def test_compensation_must_reference_existing_effect():
    _raises_with(
        lambda payload: payload["compensations"][0].update({"target_effect_id": "missing.effect"}),
        "references undefined effect",
    )


def test_handler_requires_owner():
    _raises_with(
        lambda payload: payload["handlers"][0].pop("owner"),
        r"protocol\.handlers\[0\]\.owner: required field is missing",
    )


def test_abort_only_owns_transaction_scoped_effects():
    payload = _payload()
    payload["handlers"][0]["completion_mode"] = "ABORTED"

    with pytest.raises(MetadataProtocolValidationError, match="non-transaction effect"):
        MetadataProtocol.from_dict(payload)


def test_handler_unknown_completion_mode_is_rejected():
    _raises_with(
        lambda payload: payload["handlers"][0].update({"completion_mode": "COMMITTED"}),
        "handler must transfer",
    )


def test_overlapping_return_contracts_require_distinct_priorities():
    def remove_priorities(payload):
        payload["return_contracts"][0].pop("priority")
        payload["return_contracts"][1].pop("priority")

    _raises_with(remove_priorities, "overlapping guards")


def test_disjoint_return_contracts_need_no_priority():
    payload = _payload()
    payload["return_contracts"][0]["guard"] = "ret == -2"
    payload["return_contracts"][1]["guard"] = "ret < -2"
    payload["return_contracts"][0].pop("priority")
    payload["return_contracts"][1].pop("priority")

    protocol = MetadataProtocol.from_dict(payload)

    assert protocol.return_contracts[0].priority is None


def test_unknown_guard_language_is_conservative_and_requires_priority():
    payload = _payload()
    payload["return_contracts"][2]["guard"] = "ret == 0 && !ctx->failed"
    payload["return_contracts"][2].pop("priority", None)

    with pytest.raises(MetadataProtocolValidationError, match="overlapping guards"):
        MetadataProtocol.from_dict(payload)


def test_undefined_phase_is_rejected():
    _raises_with(
        lambda payload: payload["effects"][0].update({"phase": "NOT_A_PHASE"}),
        "references undefined phase",
    )


def test_undefined_legal_exit_phase_is_rejected():
    _raises_with(
        lambda payload: payload["legal_exits"][0].update({"phases": ["NOT_A_PHASE"]}),
        r"protocol\.legal_exits\.replay\.success_exit\.phases: references undefined phase",
    )


def test_unknown_legal_exit_completion_mode_is_rejected():
    _raises_with(
        lambda payload: payload["legal_exits"][0].update({"completion_modes": ["FINISHED"]}),
        r"protocol\.legal_exits\[0\]\.completion_modes\[0\]: unknown CompletionMode",
    )


def test_object_reference_must_match_declared_principal_object():
    _raises_with(
        lambda payload: payload["effects"][0]["object"].update({"selector": "arg1"}),
        "does not match declared principal object",
    )


def test_legal_exit_must_reference_declared_return_outcome():
    _raises_with(
        lambda payload: payload["legal_exits"][0].update({"return_outcomes": ["success_changed"]}),
        "outcomes have no return contract",
    )


def test_each_operation_needs_success_and_failure_legal_exit():
    payload = _payload()
    payload["legal_exits"] = [payload["legal_exits"][0]]

    with pytest.raises(MetadataProtocolValidationError, match="missing legal exit kind"):
        MetadataProtocol.from_dict(payload)


def test_unknown_fields_are_rejected_instead_of_ignored():
    _raises_with(
        lambda payload: payload.update({"ranking_hint": "never semantic"}),
        "unknown field",
    )


def test_schema_and_protocol_versions_are_validated():
    _raises_with(
        lambda payload: payload.update({"schema_version": 99}),
        "unsupported metadata protocol schema version",
    )
    _raises_with(
        lambda payload: payload.update({"protocol_version": "v1"}),
        "expected semantic version",
    )


def test_directory_loader_rejects_duplicate_protocol_ids(tmp_path):
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    shutil.copyfile(VALID_FIXTURE, first)
    shutil.copyfile(VALID_FIXTURE, second)

    with pytest.raises(MetadataProtocolValidationError, match="duplicate protocol_id"):
        load_metadata_protocols(tmp_path)


def test_directory_loader_is_deterministic_for_distinct_protocols(tmp_path):
    payload = _payload()
    first = tmp_path / "b.json"
    second = tmp_path / "a.json"
    first.write_text(json.dumps(payload), encoding="utf-8")
    payload["protocol_id"] = "mocc.replay_recovery.second"
    second.write_text(json.dumps(payload), encoding="utf-8")

    protocols = load_metadata_protocols(tmp_path)

    assert [item.protocol_id for item in protocols] == [
        "mocc.replay_recovery.second",
        "mocc.replay_recovery.example",
    ]
