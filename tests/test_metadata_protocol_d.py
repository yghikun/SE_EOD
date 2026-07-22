import json
from pathlib import Path

import pytest

from src.frontend.tree_sitter_frontend import TreeSitterFrontend
from src.metadata_event import EffectTransition, EventStrength, ObjectIdentity
from src.metadata_protocol import MetadataProtocol, MetadataProtocolValidationError
from src.metadata_protocol_analyzer import analyze_function, analyze_source_file


ROOT = Path(__file__).parents[1]
PROTOCOL_D = (
    ROOT
    / "configs"
    / "metadata_protocols"
    / "protocol_d_transaction_lifecycle_v2.json"
)


def _protocol() -> MetadataProtocol:
    return MetadataProtocol.read_json(PROTOCOL_D)


def _function(tmp_path: Path, body: str):
    source = f"""
int xfs_acl_set_mode(void *mp, int fail)
{{
    struct xfs_trans *tp;
    struct xfs_trans *other;
    int error;
    {body}
}}
"""
    path = tmp_path / "transaction_fixture.c"
    path.write_text(source, encoding="utf-8")
    unit = TreeSitterFrontend(source_root=tmp_path).parse(path)
    return next(item for item in unit.functions if item.name == "xfs_acl_set_mode")


def _ext4_function(tmp_path: Path, body: str):
    source = f"""
int ext4_begin_enable_verity(void *inode)
{{
    handle_t *handle;
    handle_t *other;
    int err;
    {body}
}}
"""
    path = tmp_path / "ext4_transaction_fixture.c"
    path.write_text(source, encoding="utf-8")
    unit = TreeSitterFrontend(source_root=tmp_path).parse(path)
    return next(
        item for item in unit.functions if item.name == "ext4_begin_enable_verity"
    )


def test_schema_v2_summary_round_trip_preserves_bounded_contract():
    protocol = _protocol()

    assert protocol.schema_version == 2
    assert {item.summary_id for item in protocol.callee_summaries} == {
        "xfs.transaction.alloc",
        "xfs.transaction.commit",
        "xfs.transaction.cancel",
        "ext4.transaction.start",
        "ext4.transaction.stop",
    }
    assert MetadataProtocol.from_json(protocol.to_json()).to_dict() == protocol.to_dict()


def test_schema_v1_rejects_callee_summaries_instead_of_changing_semantics():
    payload = _protocol().to_dict()
    payload["schema_version"] = 1

    with pytest.raises(MetadataProtocolValidationError, match="require.*schema version 2"):
        MetadataProtocol.from_dict(payload)


def test_summary_bound_is_explicitly_one_call():
    payload = _protocol().to_dict()
    payload["callee_summaries"][0]["max_call_depth"] = 2

    with pytest.raises(MetadataProtocolValidationError, match="max_call_depth == 1"):
        MetadataProtocol.from_dict(payload)


def test_alloc_then_commit_is_a_legal_success(tmp_path):
    function = _function(
        tmp_path,
        """
    error = xfs_trans_alloc(mp, 0, 0, 0, 0, &tp);
    if (error)
        return error;
    xfs_trans_commit(tp);
    return 0;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown
    transitions = {
        item["summary_id"]: item["effect_transition"]
        for item in result.events
        if item["summary_id"]
    }
    assert transitions["xfs.transaction.alloc"] == EffectTransition.OPEN.value
    assert transitions["xfs.transaction.commit"] == EffectTransition.COMMIT.value


def test_alloc_then_cancel_is_a_legal_failure(tmp_path):
    function = _function(
        tmp_path,
        """
    error = xfs_trans_alloc(mp, 0, 0, 0, 0, &tp);
    if (error)
        return error;
    if (fail) {
        xfs_trans_cancel(tp);
        return -1;
    }
    xfs_trans_commit(tp);
    return 0;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_xfs_cancel_label_is_legal_on_error_exit(tmp_path):
    function = _function(
        tmp_path,
        """
    error = xfs_trans_alloc(mp, 0, 0, 0, 0, &tp);
    if (error)
        return error;
    if (fail)
        goto out_cancel;
    xfs_trans_commit(tp);
    return 0;
out_cancel:
    xfs_trans_cancel(tp);
    return -1;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_xfs_cancel_label_with_symbolic_error_return_is_legal(tmp_path):
    function = _function(
        tmp_path,
        """
    error = xfs_trans_alloc(mp, 0, 0, 0, 0, &tp);
    if (error)
        return error;
    if (fail) {
        error = -1;
        goto out_cancel;
    }
    xfs_trans_commit(tp);
    return 0;
out_cancel:
    xfs_trans_cancel(tp);
    return error;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_xfs_parameter_member_transaction_is_published_on_success(tmp_path):
    function = _function(
        tmp_path,
        """
    error = xfs_trans_alloc(mp, 0, 0, 0, 0, &mp->tp);
    if (error)
        return error;
    return 0;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    opened = next(
        item for item in result.events if item["summary_id"] == "xfs.transaction.alloc"
    )
    assert opened["object_ref"]["expression"] == "mp->tp"
    assert opened["object_ref"]["identity"] == ObjectIdentity.EXACT.value
    assert not result.candidates
    assert not result.unknown


def test_xfs_alloc_call_in_if_failure_branch_does_not_open_transaction(tmp_path):
    function = _function(
        tmp_path,
        """
    if (xfs_trans_alloc(mp, 0, 0, 0, 0, &tp))
        return 0;
    xfs_trans_commit(tp);
    return 0;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_xfs_alloc_call_in_if_success_branch_still_requires_terminal(tmp_path):
    function = _function(
        tmp_path,
        """
    if (xfs_trans_alloc(mp, 0, 0, 0, 0, &tp))
        return 0;
    return 0;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert result.candidates or result.unknown


def test_xfs_defer_capture_commit_wrapper_closes_transaction_on_return(tmp_path):
    function = _function(
        tmp_path,
        """
    void *capture_list;
    error = xfs_trans_alloc(mp, 0, 0, 0, 0, &tp);
    if (error)
        return error;
    return xfs_defer_ops_capture_and_commit(tp, capture_list);
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_xfs_defer_capture_commit_wrapper_assignment_closes_transaction(tmp_path):
    function = _function(
        tmp_path,
        """
    void *capture_list;
    error = xfs_trans_alloc(mp, 0, 0, 0, 0, &tp);
    if (error)
        return error;
    error = xfs_defer_ops_capture_and_commit(tp, capture_list);
    if (error)
        return error;
    return 0;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_xfs_defer_capture_commit_wrapper_of_other_object_does_not_close(tmp_path):
    function = _function(
        tmp_path,
        """
    void *capture_list;
    error = xfs_trans_alloc(mp, 0, 0, 0, 0, &tp);
    if (error)
        return error;
    return xfs_defer_ops_capture_and_commit(other, capture_list);
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert len(result.candidates) == 1
    assert not result.unknown


def test_xfs_scrub_cancel_wrapper_closes_parameter_member_transaction(tmp_path):
    function = _function(
        tmp_path,
        """
    error = xfs_trans_alloc(mp, 0, 0, 0, 0, &mp->tp);
    if (error)
        return error;
    error = -1;
    xchk_trans_cancel(mp);
    return error;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_xfs_scrub_commit_wrapper_closes_parameter_member_transaction(tmp_path):
    function = _function(
        tmp_path,
        """
    error = xfs_trans_alloc(mp, 0, 0, 0, 0, &mp->tp);
    if (error)
        return error;
    return xrep_trans_commit(mp);
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_xfs_scrub_wrapper_of_other_context_does_not_close_member_transaction(tmp_path):
    function = _function(
        tmp_path,
        """
    error = xfs_trans_alloc(mp, 0, 0, 0, 0, &mp->tp);
    if (error)
        return error;
    xchk_trans_cancel(other);
    return error;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert len(result.candidates) == 1
    assert not result.unknown


def test_ext4_stop_label_is_legal_on_error_exit(tmp_path):
    function = _ext4_function(
        tmp_path,
        """
    handle = ext4_journal_start(inode, 1, 2);
    if (IS_ERR(handle))
        return PTR_ERR(handle);
    err = mutate(handle);
    if (err)
        goto out_stop;
    ext4_journal_stop(handle);
    return 0;
out_stop:
    ext4_journal_stop(handle);
    return err;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_ext4_repeated_condition_stop_closes_handle(tmp_path):
    function = _ext4_function(
        tmp_path,
        """
    int credits = 1;
    if (credits) {
        handle = ext4_journal_start(inode, 1, 2);
        if (IS_ERR(handle))
            return PTR_ERR(handle);
    }
    mutate(handle);
    if (credits)
        ext4_journal_stop(handle);
    return err;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown


def test_success_exit_without_commit_or_cancel_reports_open_transaction(tmp_path):
    function = _function(
        tmp_path,
        """
    error = xfs_trans_alloc(mp, 0, 0, 0, 0, &tp);
    if (error)
        return error;
    return 0;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert len(result.candidates) == 1
    assert not result.unknown
    assert result.candidates[0].open_effects[0]["spec_effect_id"] == "xfs.transaction.lifecycle"


def test_commit_of_another_exact_object_does_not_close_transaction(tmp_path):
    function = _function(
        tmp_path,
        """
    error = xfs_trans_alloc(mp, 0, 0, 0, 0, &tp);
    if (error)
        return error;
    xfs_trans_commit(other);
    return 0;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert len(result.candidates) == 1
    assert not result.unknown


def test_unknown_commit_object_is_analysis_unknown(tmp_path):
    function = _function(
        tmp_path,
        """
    error = xfs_trans_alloc(mp, 0, 0, 0, 0, &tp);
    if (error)
        return error;
    xfs_trans_commit(get_transaction());
    return 0;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    commit = next(
        item for item in result.events if item["summary_id"] == "xfs.transaction.commit"
    )
    assert commit["object_ref"]["identity"] == ObjectIdentity.UNKNOWN.value
    assert commit["strength"] == EventStrength.MAY.value
    assert not result.candidates
    assert any("commit_summary_not_proven_must" in item.reasons for item in result.unknown)


def test_reviewed_wrapper_summary_substitutes_caller_argument(tmp_path):
    payload = _protocol().to_dict()
    payload["callee_summaries"][0]["callees"] = ["reviewed_trans_alloc_wrapper"]
    protocol = MetadataProtocol.from_dict(payload)
    function = _function(
        tmp_path,
        """
    error = reviewed_trans_alloc_wrapper(mp, 0, 0, 0, 0, &tp);
    if (error)
        return error;
    xfs_trans_commit(tp);
    return 0;
""",
    )

    result = analyze_function(function, protocol)

    assert result is not None
    opened = next(
        item for item in result.events if item["summary_id"] == "xfs.transaction.alloc"
    )
    assert opened["callee"] == "reviewed_trans_alloc_wrapper"
    assert opened["object_ref"]["expression"] == "tp"
    assert not result.candidates
    assert not result.unknown


def test_ext4_start_then_stop_is_a_legal_success(tmp_path):
    function = _ext4_function(
        tmp_path,
        """
    handle = ext4_journal_start(inode, 1, 2);
    if (IS_ERR(handle))
        return PTR_ERR(handle);
    err = mutate(handle);
    ext4_journal_stop(handle);
    return err;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert not result.candidates
    assert not result.unknown
    events = {
        item["summary_id"]: item
        for item in result.events
        if item["summary_id"] and item["summary_id"].startswith("ext4.")
    }
    assert events["ext4.transaction.start"]["object_ref"]["expression"] == "handle"
    assert events["ext4.transaction.stop"]["object_ref"]["expression"] == "handle"


def test_ext4_success_exit_without_stop_reports_open_handle(tmp_path):
    function = _ext4_function(
        tmp_path,
        """
    handle = ext4_journal_start(inode, 1, 2);
    if (IS_ERR(handle))
        return PTR_ERR(handle);
    return 0;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert len(result.candidates) == 1
    assert not result.unknown
    assert (
        result.candidates[0].open_effects[0]["spec_effect_id"]
        == "ext4.journal_handle.lifecycle"
    )


def test_ext4_stop_of_another_exact_handle_does_not_close_transaction(tmp_path):
    function = _ext4_function(
        tmp_path,
        """
    handle = ext4_journal_start(inode, 1, 2);
    if (IS_ERR(handle))
        return PTR_ERR(handle);
    ext4_journal_stop(other);
    return 0;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    assert len(result.candidates) == 1
    assert not result.unknown


def test_ext4_uncaptured_start_result_is_analysis_unknown(tmp_path):
    function = _ext4_function(
        tmp_path,
        """
    ext4_journal_start(inode, 1, 2);
    return 0;
""",
    )

    result = analyze_function(function, _protocol())

    assert result is not None
    opened = next(
        item for item in result.events if item["summary_id"] == "ext4.transaction.start"
    )
    assert opened["object_ref"]["identity"] == ObjectIdentity.UNKNOWN.value
    assert opened["strength"] == EventStrength.MAY.value
    assert not result.candidates
    assert any("summary_result_not_captured" in item.reasons for item in result.unknown)


def test_result_binding_rejects_argument_index():
    payload = _protocol().to_dict()
    start = next(
        item
        for item in payload["callee_summaries"]
        if item["summary_id"] == "ext4.transaction.start"
    )
    start["object_binding"]["argument_index"] = 0

    with pytest.raises(
        MetadataProtocolValidationError,
        match="result binding must not declare an argument index",
    ):
        MetadataProtocol.from_dict(payload)


def test_result_binding_rejects_output_argument_normalization():
    payload = _protocol().to_dict()
    start = next(
        item
        for item in payload["callee_summaries"]
        if item["summary_id"] == "ext4.transaction.start"
    )
    start["object_binding"]["normalization"] = "address_of_output"

    with pytest.raises(
        MetadataProtocolValidationError,
        match="result binding only supports identity normalization",
    ):
        MetadataProtocol.from_dict(payload)


@pytest.mark.parametrize("version", ["6.8", "6.14", "7.1"])
def test_real_xfs_acl_transaction_is_closed_in_supported_versions(version):
    result = analyze_source_file(
        str(ROOT / "linux-sources" / f"linux-v{version}-fs" / "fs" / "xfs" / "xfs_acl.c"),
        _protocol(),
        source_version=f"linux-v{version}",
        function_names=["xfs_acl_set_mode"],
    )[0]

    assert not result.candidates
    assert not result.unknown
    assert {
        item["summary_id"]
        for item in result.events
        if item["summary_id"]
    } == {"xfs.transaction.alloc", "xfs.transaction.commit"}


@pytest.mark.parametrize("version", ["6.8", "6.14", "7.1"])
def test_real_ext4_verity_transaction_is_closed_in_supported_versions(version):
    result = analyze_source_file(
        str(
            ROOT
            / "linux-sources"
            / f"linux-v{version}-fs"
            / "fs"
            / "ext4"
            / "verity.c"
        ),
        _protocol(),
        source_version=f"linux-v{version}",
        function_names=["ext4_begin_enable_verity"],
    )[0]

    assert not result.candidates
    assert not result.unknown
    assert {
        item["summary_id"]
        for item in result.events
        if item["summary_id"]
    } == {"ext4.transaction.start", "ext4.transaction.stop"}
