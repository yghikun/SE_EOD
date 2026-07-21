import json
from pathlib import Path

import pytest

from src.frontend.model import SourceRange
from src.frontend.tree_sitter_frontend import TreeSitterFrontend
from src.metadata_candidate_rules import generate_candidates
from src.metadata_event import (
    EventStrength,
    MetadataEvent,
    MetadataEventKind,
    ObjectIdentity,
    ResolvedObjectRef,
)
from src.metadata_protocol import (
    CompletionMode,
    EffectKind,
    EffectScope,
    EffectStatus,
    LegalExitKind,
    MetadataProtocol,
    MetadataProtocolValidationError,
    ReturnOutcome,
    ViolationType,
)
from src.metadata_protocol_analyzer import analyze_function, analyze_source_file
from src.metadata_tracker import (
    AccountingObligation,
    EffectRecord,
    MetadataOperationInstance,
)


ROOT = Path(__file__).parents[1]
PROTOCOL_C = (
    ROOT
    / "configs"
    / "metadata_protocols"
    / "protocol_c_activation_accounting_v1.json"
)
PROTOCOL_A = ROOT / "configs" / "metadata_protocols" / "protocol_a_replay_recovery_v1.json"
PROTOCOL_B = ROOT / "configs" / "metadata_protocols" / "protocol_b_device_topology_v1.json"


def _function(tmp_path: Path, source: str, name: str):
    path = tmp_path / "protocol_c_fixture.c"
    path.write_text(source, encoding="utf-8")
    unit = TreeSitterFrontend(source_root=tmp_path).parse(path)
    return next(item for item in unit.functions if item.name == name)


def _object(role: str = "fs_info"):
    return ResolvedObjectRef(role, role, ObjectIdentity.EXACT, f"sym_{role}")


def _state() -> MetadataOperationInstance:
    state = MetadataOperationInstance(
        "btrfs_chunk_activation_reservation",
        "mocc.protocol_c.activation_accounting",
    )
    state.principal_objects["fs_info"] = _object()
    state.completion_mode = CompletionMode.COMMITTED
    return state


def _event() -> MetadataEvent:
    return MetadataEvent(
        "event",
        "mocc.protocol_c.activation_accounting",
        "btrfs_chunk_activation_reservation",
        MetadataEventKind.METADATA_UPDATE,
        _object(),
        None,
        "",
        "always",
        EventStrength.MUST,
        SourceRange("fixture.c", 10, 20, 2, 2),
        callee_role_id="chunk_activation",
        callee="btrfs_zoned_activate_one_bg",
        result_symbol="ret",
        necessary=True,
    )


def test_protocol_c_loads_and_round_trips_activation_accounting_schema():
    protocol = MetadataProtocol.read_json(PROTOCOL_C)
    restored = MetadataProtocol.from_json(protocol.to_json())

    assert restored.to_dict() == protocol.to_dict()
    assert protocol.protocol_id == "mocc.protocol_c.activation_accounting"
    assert {item.operation_id for item in protocol.operations} == {
        "ext4_extra_isize_fallback",
        "btrfs_chunk_activation_reservation",
    }
    assert protocol.accounting_constraints[0].trigger_effect_ids == (
        "btrfs.chunk_metadata_pending",
    )
    assert protocol.accounting_constraints[0].satisfying_effect_ids == (
        "btrfs.chunk_metadata_reserved",
    )


def test_protocol_c_rejects_undefined_accounting_effect_reference():
    payload = json.loads(PROTOCOL_C.read_text(encoding="utf-8"))
    payload["accounting_constraints"][0]["satisfying_effect_ids"] = ["missing.effect"]

    with pytest.raises(MetadataProtocolValidationError, match="undefined effect"):
        MetadataProtocol.from_dict(payload)


def test_positive_activation_without_reservation_is_metadata_divergence(tmp_path):
    protocol = MetadataProtocol.read_json(PROTOCOL_C)
    function = _function(
        tmp_path,
        """
void reserve_chunk_space(void)
{
    int fs_info;
    int ret = btrfs_zoned_activate_one_bg(fs_info);
    if (ret < 0)
        return;
    if (!ret) {
        ret = btrfs_block_rsv_add(fs_info);
        if (!ret)
            trans->chunk_bytes_reserved += bytes;
    }
}
""",
        "reserve_chunk_space",
    )

    result = analyze_function(function, protocol)

    assert result is not None
    candidates = [
        item
        for item in result.candidates
        if item.return_provenance == "contract:btrfs.activation.changed"
    ]
    assert len(candidates) == 1
    assert candidates[0].violation_type is ViolationType.METADATA_STATE_DIVERGENCE
    assert candidates[0].accounting_state[0]["observed_state"] == "pending_without_reservation"
    assert candidates[0].accounting_state[0]["satisfied"] is False


def test_accounting_satisfied_and_unknown_states_stay_separate():
    protocol = MetadataProtocol.read_json(PROTOCOL_C)
    state = _state()
    state.accounting_obligations["btrfs.pending_requires_reservation"] = AccountingObligation(
        "btrfs.pending_requires_reservation",
        _object(),
        "pending metadata work exists => matching reservation exists",
        "reserved",
        True,
    )

    candidates, unknown = generate_candidates(
        state,
        protocol,
        phase="SUCCESS",
        outcome=ReturnOutcome.SUCCESS_CHANGED,
        exit_kind=LegalExitKind.SUCCESS,
    )

    assert not candidates
    assert not unknown

    state.accounting_obligations["btrfs.pending_requires_reservation"] = AccountingObligation(
        "btrfs.pending_requires_reservation",
        _object(),
        "pending metadata work exists => matching reservation exists",
    )
    candidates, unknown = generate_candidates(
        state,
        protocol,
        phase="SUCCESS",
        outcome=ReturnOutcome.SUCCESS_CHANGED,
        exit_kind=LegalExitKind.SUCCESS,
    )

    assert not candidates
    assert unknown
    assert unknown[0].to_dict()["classification"] == "ANALYSIS_UNKNOWN"


def test_stale_extra_isize_return_provenance_is_reported(tmp_path):
    protocol = MetadataProtocol.read_json(PROTOCOL_C)
    function = _function(
        tmp_path,
        """
int ext4_expand_extra_isize_ea(struct inode *inode)
{
    int error = 0;
retry:
    if (fallback_ready())
        goto shift;
    error = ext4_xattr_make_inode_space(handle, inode);
    if (error) {
        if (error == -ENOSPC)
            goto retry;
        return error;
    }
shift:
    EXT4_I(inode)->i_extra_isize = new_extra_isize;
    return error;
}
""",
        "ext4_expand_extra_isize_ea",
    )

    result = analyze_function(function, protocol)

    assert result is not None
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.violation_type is ViolationType.METADATA_STATE_DIVERGENCE
    assert candidate.exit_kind is LegalExitKind.FAILURE
    assert candidate.return_provenance == "stale_result_provenance"
    assert [item["kind"] for item in candidate.representative_witness] == [
        "necessary_step",
        "branch",
        "failure",
        "effect_created",
        "stale_result",
        "exit",
        "handler",
    ]


def test_clearing_stale_error_after_metadata_update_removes_same_candidate(tmp_path):
    protocol = MetadataProtocol.read_json(PROTOCOL_C)
    function = _function(
        tmp_path,
        """
int ext4_expand_extra_isize_ea(struct inode *inode)
{
    int error = 0;
retry:
    if (fallback_ready())
        goto shift;
    error = ext4_xattr_make_inode_space(handle, inode);
    if (error) {
        if (error == -ENOSPC)
            goto retry;
        return error;
    }
shift:
    EXT4_I(inode)->i_extra_isize = new_extra_isize;
    error = 0;
    return error;
}
""",
        "ext4_expand_extra_isize_ea",
    )

    result = analyze_function(function, protocol)

    assert result is not None
    assert not any(
        item.return_provenance == "stale_result_provenance"
        for item in result.candidates
    )


def test_protocol_c_real_sources_keep_expected_development_findings():
    protocol = MetadataProtocol.read_json(PROTOCOL_C)
    expected = {
        "linux-v6.8": ("linux-v6.8-fs", 1, 1),
        "linux-v6.14": ("linux-v6.14-fs", 1, 1),
        "linux-v7.1": ("linux-v7.1-fs", 1, 1),
    }
    for version, (tree, ext4_candidates, btrfs_candidates) in expected.items():
        ext4 = analyze_source_file(
            str(ROOT / "linux-sources" / tree / "fs" / "ext4" / "xattr.c"),
            protocol,
            source_version=version,
            function_names=["ext4_expand_extra_isize_ea"],
        )[0]
        btrfs = analyze_source_file(
            str(ROOT / "linux-sources" / tree / "fs" / "btrfs" / "block-group.c"),
            protocol,
            source_version=version,
            function_names=["reserve_chunk_space"],
        )[0]

        assert len(ext4.candidates) == ext4_candidates
        assert ext4.candidates[0].return_provenance == "stale_result_provenance"
        assert len(btrfs.candidates) == btrfs_candidates
        assert btrfs.candidates[0].accounting_state[0]["satisfied"] is False


def test_protocol_a_and_b_regressions_remain_candidate_backed():
    protocol_a = MetadataProtocol.read_json(PROTOCOL_A)
    protocol_b = MetadataProtocol.read_json(PROTOCOL_B)
    replay = analyze_source_file(
        str(ROOT / "linux-sources" / "linux-v6.8-fs" / "fs" / "ext4" / "fast_commit.c"),
        protocol_a,
        source_version="linux-v6.8",
        function_names=["ext4_fc_replay_add_range"],
    )[0]
    relocation = analyze_source_file(
        str(ROOT / "linux-sources" / "linux-v6.8-fs" / "fs" / "btrfs" / "relocation.c"),
        protocol_b,
        source_version="linux-v6.8",
        function_names=["btrfs_recover_relocation"],
    )[0]

    assert replay.candidates
    assert relocation.candidates
