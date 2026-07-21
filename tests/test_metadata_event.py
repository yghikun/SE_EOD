import json
from pathlib import Path

from src.frontend.tree_sitter_frontend import TreeSitterFrontend
from src.metadata_event import EventStrength, MetadataEventKind, ObjectIdentity, extract_metadata_events
from src.metadata_protocol import MetadataProtocol


def _protocol(entry: str, callees: list[str]) -> MetadataProtocol:
    return MetadataProtocol.from_dict(
        {
            "schema_version": 1,
            "protocol_version": "1.0.0",
            "protocol_id": "test.events",
            "filesystems": ["fixture"],
            "linux_versions": ["test"],
            "phases": ["ENTRY", "SUCCESS", "FAILURE"],
            "operations": [
                {
                    "operation_id": "op",
                    "entry_functions": [entry],
                    "principal_objects": [{"role": "object", "selector": "arg0"}],
                    "callee_roles": [
                        {
                            "role_id": "step",
                            "callees": callees,
                            "necessary": True,
                            "return_contract_ids": ["fail", "success"],
                        }
                    ],
                }
            ],
            "return_contracts": [
                {"contract_id": "fail", "operation_id": "op", "guard": "ret != 0", "outcome": "failure"},
                {"contract_id": "success", "operation_id": "op", "guard": "ret == 0", "outcome": "success"},
            ],
            "effects": [],
            "compensations": [],
            "handlers": [],
            "accounting_constraints": [],
            "legal_exits": [
                {"exit_id": "success", "operation_id": "op", "kind": "success", "phases": ["SUCCESS"], "completion_modes": ["COMMITTED"], "return_outcomes": ["success"]},
                {"exit_id": "failure", "operation_id": "op", "kind": "failure", "phases": ["FAILURE"], "completion_modes": ["ROLLED_BACK"], "return_outcomes": ["failure"]},
            ],
        }
    )


def _parse(tmp_path: Path, source: str, name: str = "work"):
    path = tmp_path / "fixture.c"
    path.write_text(source, encoding="utf-8")
    unit = TreeSitterFrontend(source_root=tmp_path).parse(path)
    return next(item for item in unit.functions if item.name == name)


def test_direct_call_and_assignment_events_are_deterministic(tmp_path):
    function = _parse(
        tmp_path,
        "int work(struct obj *o) { int ret; ret = necessary(o); o->field = 1; return ret; }",
    )
    protocol = _protocol("work", ["necessary"])

    first = extract_metadata_events(function, protocol)
    second = extract_metadata_events(function, protocol)

    assert [item.event_id for item in first] == [item.event_id for item in second]
    call = next(item for item in first if item.callee == "necessary")
    assert call.result_symbol == "ret"
    assert call.strength is EventStrength.MUST
    assert call.object_ref.identity is ObjectIdentity.EXACT
    assert any(item.field_or_member == "field" for item in first)


def test_list_and_counter_calls_are_normalized(tmp_path):
    function = _parse(
        tmp_path,
        "void work(struct obj *o) { list_add(&o->node, &head); atomic_inc(&o->count); list_del(&o->node); }",
    )
    protocol = _protocol("work", ["unused"])

    kinds = [item.kind for item in extract_metadata_events(function, protocol)]

    assert MetadataEventKind.MEMBERSHIP_ADD in kinds
    assert MetadataEventKind.MEMBERSHIP_REMOVE in kinds
    assert MetadataEventKind.COUNTER_UPDATE in kinds


def test_unknown_object_is_may_and_keeps_uncertainty(tmp_path):
    payload = _protocol("work", ["necessary"]).to_dict()
    payload["operations"][0]["principal_objects"][0]["selector"] = "arg9"
    protocol = MetadataProtocol.from_dict(payload)
    function = _parse(tmp_path, "int work(void *o) { return necessary(o); }")

    event = next(item for item in extract_metadata_events(function, protocol) if item.callee)

    assert event.strength is EventStrength.MAY
    assert event.object_ref.identity is ObjectIdentity.UNKNOWN
    assert "unknown_object_identity" in event.uncertainty_causes


def test_non_entry_function_produces_no_events(tmp_path):
    function = _parse(tmp_path, "int other(void *o) { return necessary(o); }", "other")

    assert extract_metadata_events(function, _protocol("work", ["necessary"])) == ()


def test_event_payload_is_json_serializable(tmp_path):
    function = _parse(tmp_path, "int work(void *o) { int ret = necessary(o); return ret; }")
    events = extract_metadata_events(function, _protocol("work", ["necessary"]))

    json.dumps([item.to_dict() for item in events])
