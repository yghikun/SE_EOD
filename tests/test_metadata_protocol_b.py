from pathlib import Path

from src.frontend.tree_sitter_frontend import TreeSitterFrontend
from src.metadata_event import ObjectIdentity, ResolvedObjectRef, extract_metadata_events
from src.metadata_protocol import (
    CompletionMode,
    EffectKind,
    EffectScope,
    EffectStatus,
    MetadataProtocol,
)
from src.metadata_protocol_analyzer import analyze_function, analyze_source_file
from src.metadata_tracker import EffectRecord, MetadataOperationInstance


ROOT = Path(__file__).parents[1]
PROTOCOL_B = (
    ROOT
    / "configs"
    / "metadata_protocols"
    / "protocol_b_device_topology_v1.json"
)


def _function(tmp_path: Path, source: str, name: str):
    path = tmp_path / "protocol_b_fixture.c"
    path.write_text(source, encoding="utf-8")
    unit = TreeSitterFrontend(source_root=tmp_path).parse(path)
    return next(item for item in unit.functions if item.name == name)


def _relocation_fixture(*, compensated: bool) -> str:
    cleanup = "fs_root->reloc_root = NULL;" if compensated else ""
    return f"""
int btrfs_recover_relocation(struct fs_info *fs_info)
{{
    struct root *fs_root;
    struct root *reloc_root;
    int err;
    fs_root->reloc_root = btrfs_grab_root(reloc_root);
    err = btrfs_commit_transaction(trans);
    if (err)
        goto out;
    return 0;
out:
    {cleanup}
    return err;
}}
"""


def test_protocol_b_loads_all_device_topology_effects():
    protocol = MetadataProtocol.read_json(PROTOCOL_B)

    assert protocol.protocol_id == "mocc.protocol_b.device_topology_rollback"
    assert {item.effect_id for item in protocol.effects} == {
        "reloc.root_pointer",
        "sprout.fs_devices_topology",
        "sprout.active_s_bdev",
        "sprout.active_latest_dev",
        "sprout.post_commit_membership",
        "sprout.device_dev_membership",
        "sprout.device_alloc_membership",
    }


def test_relocation_pointer_open_on_failure_is_reported(tmp_path):
    protocol = MetadataProtocol.read_json(PROTOCOL_B)
    function = _function(
        tmp_path,
        _relocation_fixture(compensated=False),
        "btrfs_recover_relocation",
    )

    result = analyze_function(function, protocol)

    assert result is not None
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.violation_type.value == "incomplete_failure_completion"
    assert {item["spec_effect_id"] for item in candidate.open_effects} == {
        "reloc.root_pointer"
    }
    kinds = [item["kind"] for item in candidate.representative_witness]
    assert kinds.index("effect_created") < kinds.index("necessary_step")
    assert kinds.index("necessary_step") < kinds.index("failure") < kinds.index("exit")


def test_relocation_pointer_compensation_closes_matching_effect(tmp_path):
    protocol = MetadataProtocol.read_json(PROTOCOL_B)
    function = _function(
        tmp_path,
        _relocation_fixture(compensated=True),
        "btrfs_recover_relocation",
    )

    result = analyze_function(function, protocol)

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_real_relocation_and_sprout_sources_expose_expected_rollback_state():
    protocol = MetadataProtocol.read_json(PROTOCOL_B)
    relocation = analyze_source_file(
        str(ROOT / "linux-sources" / "linux-v6.8-fs" / "fs" / "btrfs" / "relocation.c"),
        protocol,
        source_version="linux-v6.8",
        function_names=["btrfs_recover_relocation"],
    )[0]
    sprout = analyze_source_file(
        str(ROOT / "linux-sources" / "linux-v6.8-fs" / "fs" / "btrfs" / "volumes.c"),
        protocol,
        source_version="linux-v6.8",
        function_names=["btrfs_init_new_device"],
    )[0]

    assert any(
        {item["spec_effect_id"] for item in candidate.open_effects}
        == {"reloc.root_pointer"}
        for candidate in relocation.candidates
    )
    sprout_open_sets = [
        {item["spec_effect_id"] for item in candidate.open_effects}
        for candidate in sprout.candidates
    ]
    assert {
        "sprout.fs_devices_topology",
        "sprout.active_s_bdev",
        "sprout.active_latest_dev",
    } in sprout_open_sets
    event_ids = {
        item["effect_spec_id"] or item["compensation_spec_id"]
        for item in sprout.events
    }
    assert {
        "sprout.device_dev_membership",
        "sprout.device_alloc_membership",
        "sprout.detach_device_dev_list",
        "sprout.detach_device_alloc_list",
    } <= event_ids
    assert not any(
        effect_id in open_set
        for open_set in sprout_open_sets
        for effect_id in {
            "sprout.device_dev_membership",
            "sprout.device_alloc_membership",
        }
    )
    assert any("may_effect_summary" in item.reasons for item in sprout.unknown)


def test_effect_instances_for_two_principal_objects_are_compensated_independently():
    state = MetadataOperationInstance("op", "protocol")
    first = ResolvedObjectRef("device", "device_a", ObjectIdentity.EXACT, "a")
    second = ResolvedObjectRef("device", "device_b", ObjectIdentity.EXACT, "b")
    for instance_id, object_ref in (("membership@a", first), ("membership@b", second)):
        state.add_effect(
            EffectRecord(
                instance_id,
                EffectKind.MEMBERSHIP_ADD,
                object_ref,
                EffectScope.IN_MEMORY_GLOBAL,
                "device_list",
                EffectStatus.OPEN,
                instance_id,
                spec_effect_id="membership",
            )
        )

    assert state.compensate("membership", first)
    assert state.effect_ledger["membership@a"].status is EffectStatus.COMPENSATED
    assert state.effect_ledger["membership@b"].status is EffectStatus.OPEN


def test_abort_leaves_global_effect_open_while_transferring_transaction_effect():
    state = MetadataOperationInstance("op", "protocol")
    object_ref = ResolvedObjectRef("device", "device", ObjectIdentity.EXACT, "device")
    state.add_effect(
        EffectRecord(
            "transaction",
            EffectKind.METADATA_UPDATE,
            object_ref,
            EffectScope.TRANSACTION_SCOPED,
            "transaction",
            EffectStatus.OPEN,
            "transaction_event",
        )
    )
    state.add_effect(
        EffectRecord(
            "topology",
            EffectKind.POINTER_UPDATE,
            object_ref,
            EffectScope.IN_MEMORY_GLOBAL,
            "function",
            EffectStatus.OPEN,
            "topology_event",
        )
    )

    state.abort_transaction("transaction_manager", "abort_called")

    assert state.completion_mode is CompletionMode.ABORTED
    assert state.effect_ledger["transaction"].status is EffectStatus.TRANSFERRED
    assert state.effect_ledger["topology"].status is EffectStatus.OPEN


def test_abort_handler_does_not_hide_global_topology_candidate(tmp_path):
    protocol = MetadataProtocol.read_json(PROTOCOL_B)
    payload = protocol.to_dict()
    payload["effects"].append(
        {
            "event_id": "sprout.transaction.open",
            "effect_id": "sprout.transaction_update",
            "operation_id": "btrfs_sprout_device_add",
            "kind": "METADATA_UPDATE",
            "object": {"role": "fs_devices", "selector": "fs_devices"},
            "scope": "TRANSACTION_SCOPED",
            "owner": "transaction",
            "phase": "ENTRY",
            "match_callees": ["begin_update"],
        }
    )
    payload["handlers"] = [
        {
            "event_id": "sprout.abort",
            "handler_id": "sprout.abort_handler",
            "operation_id": "btrfs_sprout_device_add",
            "completion_mode": "ABORTED",
            "object": {"role": "fs_devices", "selector": "fs_devices"},
            "owner": "transaction_manager",
            "guard": "abort_called",
            "handles_effect_ids": ["sprout.transaction_update"],
            "match_callees": ["btrfs_abort_transaction"],
        }
    ]
    protocol = MetadataProtocol.from_dict(payload)
    function = _function(
        tmp_path,
        """
int btrfs_init_new_device(struct fs_info *fs_info)
{
    struct fs_devices *fs_devices;
    int ret;
    begin_update(fs_devices);
    btrfs_setup_sprout(fs_info, seed_devices);
    ret = btrfs_add_dev_item(trans, device);
    if (ret) {
        btrfs_abort_transaction(trans, ret);
        return ret;
    }
    return 0;
}
""",
        "btrfs_init_new_device",
    )

    result = analyze_function(function, protocol)

    assert result is not None
    assert len(result.candidates) == 1
    assert {item["spec_effect_id"] for item in result.candidates[0].open_effects} == {
        "sprout.fs_devices_topology"
    }


def test_flag_and_counter_compensations_match_by_protocol_specs(tmp_path):
    protocol = MetadataProtocol.read_json(PROTOCOL_B)
    payload = protocol.to_dict()
    payload["operations"][0]["entry_functions"] = ["unused"]
    payload["operations"][1]["entry_functions"] = ["work"]
    payload["operations"][1]["principal_objects"] = [
        {"role": "device", "selector": "arg0"}
    ]
    payload["effects"] = [
        {
            "event_id": "flag.set",
            "effect_id": "device.flag",
            "operation_id": "btrfs_sprout_device_add",
            "kind": "FLAG_SET",
            "object": {"role": "device", "selector": "arg0"},
            "scope": "IN_MEMORY_GLOBAL",
            "owner": "work",
            "phase": "ENTRY",
            "match_callees": ["set_bit"],
        },
        {
            "event_id": "counter.add",
            "effect_id": "device.counter",
            "operation_id": "btrfs_sprout_device_add",
            "kind": "COUNTER_UPDATE",
            "object": {"role": "device", "selector": "arg0"},
            "scope": "IN_MEMORY_GLOBAL",
            "owner": "work",
            "phase": "ENTRY",
            "match_callees": ["atomic_inc"],
        },
    ]
    payload["compensations"] = [
        {
            "event_id": "flag.clear",
            "compensation_id": "clear.flag",
            "operation_id": "btrfs_sprout_device_add",
            "target_effect_id": "device.flag",
            "object": {"role": "device", "selector": "arg0"},
            "guard": "failure_cleanup",
            "phase": "FAILURE",
            "match_callees": ["clear_bit"],
        },
        {
            "event_id": "counter.sub",
            "compensation_id": "subtract.counter",
            "operation_id": "btrfs_sprout_device_add",
            "target_effect_id": "device.counter",
            "object": {"role": "device", "selector": "arg0"},
            "guard": "failure_cleanup",
            "phase": "FAILURE",
            "match_callees": ["atomic_dec"],
        },
    ]
    payload["handlers"] = []
    protocol = MetadataProtocol.from_dict(payload)
    function = _function(
        tmp_path,
        """
int work(struct device *device)
{
    int ret;
    set_bit(1, &device->flags);
    atomic_inc(&device->count);
    ret = btrfs_add_dev_item(trans, device);
    if (ret) {
        clear_bit(1, &device->flags);
        atomic_dec(&device->count);
        return ret;
    }
    return 0;
}
""",
        "work",
    )

    result = analyze_function(function, protocol)

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_reviewed_may_effect_summary_is_unknown_not_candidate(tmp_path):
    protocol = MetadataProtocol.read_json(PROTOCOL_B)
    function = _function(
        tmp_path,
        """
int btrfs_init_new_device(struct fs_info *fs_info)
{
    int ret = init_first_rw_device(trans);
    if (ret)
        return ret;
    return 0;
}
""",
        "btrfs_init_new_device",
    )

    events = extract_metadata_events(function, protocol)
    result = analyze_function(function, protocol)

    summary = next(
        item for item in events if item.effect_spec_id == "sprout.post_commit_membership"
    )
    assert summary.strength.value == "may"
    assert result is not None
    assert not result.candidates
    assert any("may_effect_summary" in item.reasons for item in result.unknown)
