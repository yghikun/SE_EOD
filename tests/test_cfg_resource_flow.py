from dataclasses import asdict
import json
from pathlib import Path

from src.candidate_rules import run_candidate_rules
from src.error_path_extractor import ErrorPathExtractor
from src.function_extractor import extract_functions
from src.function_summary import infer_function_summaries
from src.parser import ParsedFile, parse_c_file
from src.resource_tracker import ResourceTracker
from src.label_resolver import parse_statements, resolve_label


RESOURCE_MAP = {
    "acquire_functions": {
        "kmalloc": {"resource_type": "memory", "release": ["kfree"]},
        "start_handle": {"resource_type": "handle", "release": ["stop_handle"]},
    }
}

STRICT_RESOURCE_MAP = {
    "acquire_functions": {
        "kmalloc": {
            "resource_type": "memory",
            "release": ["kfree"],
            "validity_guard": "{var} != NULL",
        },
    }
}


def _rows(tmp_path: Path, source: str):
    path = tmp_path / "flow.c"
    path.write_text(source, encoding="utf-8")
    function = extract_functions(parse_c_file(path))[0]
    return ErrorPathExtractor(ResourceTracker(RESOURCE_MAP)).extract(function)


def _strict_rows(tmp_path: Path, source: str):
    path = tmp_path / "flow.c"
    path.write_text(source, encoding="utf-8")
    function = extract_functions(parse_c_file(path))[0]
    return ErrorPathExtractor(ResourceTracker(STRICT_RESOURCE_MAP)).extract(function)


def test_cfg_reports_reachable_unreleased_branch(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int release, int err)
{
    void *ptr = kmalloc(8);
    if (release)
        kfree(ptr);
    if (err)
        return err;
    kfree(ptr);
    return 0;
}
""",
    )
    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]


def test_supported_switch_on_candidate_slice_preserves_cfg_confidence(tmp_path: Path):
    rows = _strict_rows(
        tmp_path,
        """
int work(int err, int mode)
{
    void *ptr = kmalloc(8);
    if (!ptr)
        return -ENOMEM;
    if (err) {
        switch (mode) {
        case 1:
            return -EAGAIN;
        default:
            break;
        }
        return err;
    }
    kfree(ptr);
    return 0;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.confidence == "high"
    assert error.cfg_witness["cfg_complete"] is True
    assert error.cfg_witness["cfg_slice_complete"] is True
    assert error.cfg_witness["unsupported_nodes_on_reachable_slice"] == []
    assert error.cfg_witness["unsupported_ranges_on_reachable_slice"] == []


def test_unrelated_supported_switch_keeps_function_cfg_complete(
    tmp_path: Path,
):
    rows = _strict_rows(
        tmp_path,
        """
int work(int err, int mode)
{
    void *ptr = kmalloc(8);
    if (!ptr)
        return -ENOMEM;
    if (mode) {
        switch (mode) {
        case 1:
            mode = 0;
            break;
        default:
            break;
        }
    }
    if (err)
        return err;
    kfree(ptr);
    return 0;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.confidence == "high"
    assert error.cfg_witness["cfg_complete"] is True
    assert error.cfg_witness["cfg_slice_complete"] is True
    assert error.cfg_witness["unsupported_nodes_on_reachable_slice"] == []
    assert error.cfg_witness["unsupported_ranges_on_reachable_slice"] == []


def test_switch_case_resource_flow_preserves_only_unreleased_case(tmp_path: Path):
    rows = _strict_rows(
        tmp_path,
        """
int work(int mode)
{
    void *ptr = kmalloc(8);
    if (!ptr)
        return -ENOMEM;
    switch (mode) {
    case 1:
        kfree(ptr);
        return -EIO;
    case 2:
        return -EAGAIN;
    default:
        kfree(ptr);
        break;
    }
    return 0;
}
""",
    )

    case_one = next(row for row in rows if row.final_return_expr == "-EIO")
    case_two = next(row for row in rows if row.final_return_expr == "-EAGAIN")
    assert case_one.missing_cleanup_candidates == []
    assert case_two.missing_cleanup_candidates == ["kfree(ptr)"]
    assert case_two.cfg_witness["cfg_complete"] is True


def test_switch_fallthrough_and_post_switch_cleanup_release_resource(tmp_path: Path):
    rows = _strict_rows(
        tmp_path,
        """
int work(int mode, int err)
{
    void *ptr = kmalloc(8);
    if (!ptr)
        return -ENOMEM;
    switch (mode) {
    case 1:
        prepare(ptr);
    case 2:
        kfree(ptr);
        break;
    default:
        break;
    }
    if (err)
        return err;
    kfree(ptr);
    return 0;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]
    assert error.cfg_witness["cfg_complete"] is True


def test_gnu_case_range_on_candidate_slice_remains_low_confidence(tmp_path: Path):
    rows = _strict_rows(
        tmp_path,
        """
int work(int mode, int err)
{
    void *ptr = kmalloc(8);
    if (!ptr)
        return -ENOMEM;
    if (err) {
        switch (mode) {
        case 1 ... 3:
            return -EIO;
        default:
            break;
        }
        return err;
    }
    kfree(ptr);
    return 0;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.confidence == "low"
    assert error.cfg_witness["cfg_complete"] is False
    assert error.cfg_witness["unsupported_nodes_on_reachable_slice"] == [
        "case_range"
    ]


def test_cfg_does_not_treat_conditional_label_cleanup_as_must_release(
    tmp_path: Path,
):
    rows = _rows(
        tmp_path,
        """
int work(int err, int cleanup)
{
    void *ptr = kmalloc(8);
    if (err)
        goto out;
    return 0;
out:
    if (cleanup)
        kfree(ptr);
    return err;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert "kfree(ptr)" in error.cleanup_calls
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]
    assert "released by kfree(ptr)" not in error.reason
    row = {
        key: json.dumps(value) if isinstance(value, (list, dict)) else str(value)
        for key, value in asdict(error).items()
    }
    assert any(
        candidate["candidate_type"] == "missing_cleanup"
        for candidate in run_candidate_rules(row)
    )


def test_cfg_uses_unconditional_label_cleanup_as_release(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err)
{
    void *ptr = kmalloc(8);
    if (err)
        goto out;
    return 0;
out:
    kfree(ptr);
    return err;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == []


def test_cfg_partial_cleanup_uses_resource_exit_states(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err)
{
    void *first = kmalloc(8);
    void *second = kmalloc(16);
    if (err)
        goto out;
    kfree(second);
    kfree(first);
    return 0;
out:
    kfree(first);
    return err;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.resource_analysis == "cfg"
    assert error.partial_cleanup is True
    assert error.released_cleanup_candidates == ["kfree(first)"]
    assert error.missing_cleanup_candidates == ["kfree(second)"]

    row = {
        key: json.dumps(value) if isinstance(value, (list, dict)) else str(value)
        for key, value in asdict(error).items()
    }
    candidate_types = {
        candidate["candidate_type"] for candidate in run_candidate_rules(row)
    }
    assert candidate_types == {"missing_cleanup", "partial_cleanup"}


def test_partial_cleanup_does_not_union_different_exit_disjuncts(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int which, int err)
{
    void *first = NULL;
    void *second = NULL;
    if (which)
        first = kmalloc(8);
    else
        second = kmalloc(16);
    if (err)
        goto out;
    return 0;
out:
    if (which)
        kfree(first);
    return err;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == ["kfree(second)"]
    assert error.partial_cleanup is False


def test_text_fallback_paths_are_explicitly_low_confidence(tmp_path: Path):
    path = tmp_path / "degraded.c"
    source = """
int work(int err)
{
    void *ptr = kmalloc(8);
    if (err)
        return err;
    return 0;
}
"""
    function = extract_functions(
        ParsedFile(path=path, text=source, tree=None, parser_kind="text")
    )[0]

    rows = ErrorPathExtractor(ResourceTracker(RESOURCE_MAP)).extract(function)
    error = next(row for row in rows if row.condition == "err")

    assert function.analysis_quality == "degraded-text"
    assert error.confidence == "low"
    assert "degraded analysis quality: degraded-text" in error.reason


def test_field_store_after_label_keeps_candidate_at_reduced_confidence(
    tmp_path: Path,
):
    rows = _rows(
        tmp_path,
        """
int work(struct holder *holder, int err)
{
    void *ptr = kmalloc(8);
    if (err)
        goto out;
    return 0;
out:
    holder->ptr = ptr;
    return err;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]
    assert error.confidence == "medium"
    assert error.held_resources[0]["uncertainty_causes"] == [
        "field_store_without_contract",
        "unresolved_acquire_validity",
    ]


def test_field_store_does_not_reestablish_a_released_obligation(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(struct holder *holder, int err)
{
    void *ptr = kmalloc(8);
    kfree(ptr);
    holder->ptr = ptr;
    if (err)
        return err;
    return 0;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.held_resources == []
    assert error.missing_cleanup_candidates == []


def test_cfg_rejects_contradictory_branch_combinations(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int released)
{
    void *ptr = kmalloc(8);
    if (released)
        kfree(ptr);
    if (released)
        return -EIO;
    kfree(ptr);
    return 0;
}
""",
    )
    error = next(row for row in rows if row.condition == "released")
    assert error.missing_cleanup_candidates == []


def test_error_in_else_branch_uses_false_cfg_edge(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int ok)
{
    void *ptr = kmalloc(8);
    if (ok) {
        kfree(ptr);
        return 0;
    } else {
        return -EIO;
    }
}
""",
    )

    error = next(row for row in rows if row.final_return_expr == "-EIO")
    assert error.branch_taken == "false"
    assert error.condition == "!(ok)"
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]
    assert error.cfg_edge_kind == "false"
    assert error.cfg_edge_id
    assert error.cfg_witness["condition_start_byte"] == error.condition_start_byte
    assert error.cfg_witness["exit_states"]
    assert any(
        resource["state"] in {"ACQUIRED", "MAY_ACQUIRED"}
        for exit_block in error.cfg_witness["exit_states"]
        for state in exit_block["states"]
        for resource in state["resources"]
    )


def test_repeated_condition_text_has_distinct_cfg_edge_identity(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int ret, int other)
{
    void *ptr = kmalloc(8);
    if (ret)
        return -EAGAIN;
    ret = other;
    if (ret)
        return -EIO;
    kfree(ptr);
    return 0;
}
""",
    )

    errors = [row for row in rows if row.condition == "ret"]
    assert len(errors) == 2
    assert len({row.cfg_edge_id for row in errors}) == 2
    assert len({row.condition_start_byte for row in errors}) == 2
    assert all(row.cfg_edge_kind == "true" for row in errors)


def test_exit_sensitive_transfer_only_applies_on_success_edge(tmp_path: Path):
    resource_map = {
        **RESOURCE_MAP,
        "interprocedural_effect_seeds": {
            "submit": {
                "resource": "arg0",
                "action": "transfer",
                "strength": "must",
                "exit_class": "success",
                "return_guard": "return == 0",
            }
        },
    }
    summaries = infer_function_summaries([], resource_map)
    path = tmp_path / "exit_sensitive.c"
    path.write_text(
        """
int work(int err)
{
    void *ptr = kmalloc(8);
    int ret = submit(ptr);
    if (ret)
        return ret;
    if (err)
        return err;
    return 0;
}
""",
        encoding="utf-8",
    )
    function = extract_functions(parse_c_file(path))[0]
    rows = ErrorPathExtractor(ResourceTracker(resource_map, summaries)).extract(
        function
    )

    submit_error = next(row for row in rows if row.condition == "ret")
    later_error = next(row for row in rows if row.condition == "err")
    assert submit_error.missing_cleanup_candidates == ["kfree(ptr)"]
    assert later_error.missing_cleanup_candidates == []


def test_reassigned_result_version_cannot_trigger_older_pending_effect(
    tmp_path: Path,
):
    resource_map = {
        **RESOURCE_MAP,
        "interprocedural_effect_seeds": {
            "submit": {
                "resource": "arg0",
                "action": "transfer",
                "strength": "must",
                "exit_class": "success",
                "return_guard": "return == 0",
            }
        },
    }
    summaries = infer_function_summaries([], resource_map)
    path = tmp_path / "pending_versions.c"
    path.write_text(
        """
int work(int err)
{
    void *p1 = kmalloc(8);
    if (!p1)
        return -ENOMEM;
    void *p2 = kmalloc(8);
    if (!p2) {
        kfree(p1);
        return -ENOMEM;
    }
    int ret = submit(p1);
    ret = submit(p2);
    if (ret)
        return ret;
    if (err)
        return err;
    kfree(p1);
    return 0;
}
""",
        encoding="utf-8",
    )
    function = extract_functions(parse_c_file(path))[0]
    rows = ErrorPathExtractor(ResourceTracker(resource_map, summaries)).extract(
        function
    )

    later_error = next(row for row in rows if row.condition == "err")
    assert later_error.missing_cleanup_candidates == ["kfree(p1)"]
    assert {resource["var"] for resource in later_error.held_resources} == {"p1"}


def test_shadowed_result_symbol_does_not_satisfy_outer_pending_guard(
    tmp_path: Path,
):
    resource_map = {
        **RESOURCE_MAP,
        "interprocedural_effect_seeds": {
            "submit": {
                "resource": "arg0",
                "action": "transfer",
                "strength": "must",
                "exit_class": "success",
                "return_guard": "return == 0",
            }
        },
    }
    summaries = infer_function_summaries([], resource_map)
    path = tmp_path / "shadowed_pending.c"
    path.write_text(
        """
int work(int err)
{
    void *ptr = kmalloc(8);
    int ret = submit(ptr);
    {
        int ret = 0;
        if (!ret)
            return -EAGAIN;
    }
    if (err)
        return err;
    kfree(ptr);
    return 0;
}
""",
        encoding="utf-8",
    )
    function = extract_functions(parse_c_file(path))[0]
    rows = ErrorPathExtractor(ResourceTracker(resource_map, summaries)).extract(
        function
    )

    shadow_error = next(row for row in rows if row.final_return_expr == "-EAGAIN")
    later_error = next(row for row in rows if row.condition == "err")
    assert shadow_error.missing_cleanup_candidates == ["kfree(ptr)"]
    assert later_error.missing_cleanup_candidates == ["kfree(ptr)"]
    shadow_states = [
        state
        for exit_block in shadow_error.cfg_witness["exit_states"]
        for state in exit_block["states"]
    ]
    assert any(
        "ret" in state["symbol_ids"]
        and state["symbol_ids"]["ret"].startswith("sid_")
        for state in shadow_states
    )
    assert any(state["representative_trace"] for state in shadow_states)


def test_cfg_witness_trace_keeps_acquire_anchor_when_truncated(tmp_path: Path):
    filler = "\n".join(f"    err += {index};" for index in range(60))
    rows = _rows(
        tmp_path,
        f"""
int work(int err)
{{
    void *ptr = kmalloc(8);
{filler}
    if (err)
        return err;
    kfree(ptr);
    return 0;
}}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    states = [
        state
        for exit_block in error.cfg_witness["exit_states"]
        for state in exit_block["states"]
    ]

    assert any(state["trace_truncated"] for state in states)
    assert any(
        any(
            anchor.get("event") == "acquire"
            and anchor.get("resource_id") == "ptr@4:kmalloc#1"
            for anchor in state["trace_anchors"]
        )
        for state in states
    )


def test_independent_release_condition_keeps_unreleased_path(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int acquire_now, int release_now)
{
    void *ptr = NULL;
    if (acquire_now)
        ptr = kmalloc(8);
    if (release_now)
        kfree(ptr);
    return -EIO;
}
""",
    )

    error = next(row for row in rows if row.final_return_expr == "-EIO")
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]


def test_loop_reacquire_tracks_multiple_instances_conservatively(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int again, int err)
{
    void *ptr = NULL;
    while (again)
        ptr = kmalloc(8);
    kfree(ptr);
    if (err)
        return err;
    return 0;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]
    resource = error.held_resources[0]
    assert resource["multiplicity"] == "many"
    assert "loop_multiple_instances" in resource["uncertainty_causes"]


def test_unresolved_field_function_pointer_keeps_candidate(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(struct operations *ops, int err)
{
    void *ptr = kmalloc(8);
    ops->release(ptr);
    if (err)
        return err;
    return 0;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]
    assert error.held_resources[0]["uncertainty_causes"] == [
        "unknown_indirect_call",
        "unresolved_acquire_validity",
    ]


def test_cfg_invalidates_path_fact_after_reassignment(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err, int other)
{
    void *ptr = kmalloc(8);
    if (err)
        kfree(ptr);
    err = other;
    if (err)
        return -EIO;
    kfree(ptr);
    return 0;
}
""",
    )
    error = next(row for row in rows if row.error_line == 8)
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]


def test_cfg_propagates_ptr_err_acquire_failure_to_later_error_return(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err)
{
    void *handle = start_handle();
    if (IS_ERR(handle)) {
        err = PTR_ERR(handle);
        goto out;
    }
    stop_handle(handle);
out:
    if (err)
        return err;
    return 0;
}
""",
    )
    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == []


def test_cfg_rejects_negative_ptr_err_state_on_nonnegative_branch(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err)
{
    void *handle = start_handle();
    int ret = 1;
    if (IS_ERR(handle)) {
        ret = PTR_ERR(handle);
        goto out;
    }
    stop_handle(handle);
out:
    if (ret >= 0 && more_work()) {
        err = do_fallback();
        if (err < 0)
            return err;
    }
    return ret;
}
""",
    )
    error = next(row for row in rows if row.condition == "err < 0")
    assert error.missing_cleanup_candidates == []


def test_cfg_does_not_report_resource_acquired_later_via_backedge(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int retry)
{
again:
    if (failed_early())
        return -EIO;
    void *ptr = kmalloc(8);
    if (retry)
        goto again;
    return -EIO;
}
""",
    )
    early = next(row for row in rows if row.condition == "failed_early()")
    assert early.missing_cleanup_candidates == []


def test_alias_release_and_swap_update_resource_identity(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err)
{
    void *ptr = kmalloc(8);
    void *alias = ptr;
    void *other = NULL;
    swap(alias, other);
    kfree(other);
    if (err)
        return err;
    return 0;
}
""",
    )
    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == []


def test_reacquire_creates_distinct_resource_instances(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err)
{
    void *ptr = kmalloc(8);
    ptr = kmalloc(16);
    if (err)
        return err;
    return 0;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert len(error.held_resources) == 2
    assert len({resource["resource_id"] for resource in error.held_resources}) == 2


def test_old_alias_release_does_not_release_reacquired_instance(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err)
{
    void *ptr = kmalloc(8);
    void *old = ptr;
    ptr = kmalloc(16);
    kfree(old);
    if (err)
        return err;
    return 0;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert len(error.held_resources) == 1
    assert error.held_resources[0]["acquire_line"] == 6
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]


def test_inner_shadow_release_does_not_discharge_outer_resource(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err)
{
    void *ptr = kmalloc(8);
    if (!ptr)
        return -ENOMEM;
    {
        void *ptr = start_handle();
        if (!IS_ERR(ptr))
            stop_handle(ptr);
    }
    if (err)
        return err;
    kfree(ptr);
    return 0;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]
    assert len(error.held_resources) == 1
    assert error.held_resources[0]["acquire_func"] == "kmalloc"


def test_scope_exit_restores_outer_binding_for_later_release(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err)
{
    void *ptr = kmalloc(8);
    if (!ptr)
        return -ENOMEM;
    {
        void *ptr = start_handle();
        if (!IS_ERR(ptr))
            stop_handle(ptr);
    }
    kfree(ptr);
    if (err)
        return err;
    return 0;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.held_resources == []
    assert error.missing_cleanup_candidates == []


def test_goto_edge_unwinds_shadowed_scope_binding(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err)
{
    void *ptr = kmalloc(8);
    if (!ptr)
        return -ENOMEM;
    {
        void *ptr = start_handle();
        if (!IS_ERR(ptr))
            stop_handle(ptr);
        if (err)
            goto out;
    }
    kfree(ptr);
    return 0;
out:
    return err;
}
""",
    )

    error = next(row for row in rows if row.target_label == "out")
    assert any(
        edge["count"] == 1
        for edge in error.cfg_witness["scope_unwind_edges"]
    )
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]
    assert {resource["acquire_func"] for resource in error.held_resources} == {
        "kmalloc"
    }


def test_break_edge_unwinds_shadowed_scope_before_outer_release(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int again, int stop, int err)
{
    void *ptr = kmalloc(8);
    if (!ptr)
        return -ENOMEM;
    while (again) {
        void *ptr = start_handle();
        stop_handle(ptr);
        if (stop)
            break;
    }
    kfree(ptr);
    if (err)
        return err;
    return 0;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.held_resources == []
    assert error.missing_cleanup_candidates == []


def test_unknown_indirect_call_keeps_possible_ownership_candidate(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err, void (*callback)(void *))
{
    void *ptr = kmalloc(8);
    callback(ptr);
    if (err)
        return err;
    return 0;
}
""",
    )
    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]
    assert error.confidence == "medium"
    assert error.held_resources[0]["uncertainty_causes"] == [
        "unknown_indirect_call",
        "unresolved_acquire_validity",
    ]


def test_resolved_function_pointer_release_is_applied(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err)
{
    void *ptr = kmalloc(8);
    void (*fn)(void *) = kfree;
    fn(ptr);
    if (err)
        return err;
    return 0;
}
""",
    )
    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == []


def test_function_pointer_assignment_release_is_applied(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err)
{
    void *ptr = kmalloc(8);
    void (*fn)(void *);
    fn = kfree;
    fn(ptr);
    if (err)
        return err;
    return 0;
}
""",
    )
    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == []


def test_resolved_non_release_function_pointer_keeps_resource_owned(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err)
{
    void *ptr = kmalloc(8);
    void (*fn)(void *) = inspect;
    fn(ptr);
    if (err)
        return err;
    return 0;
}
""",
    )
    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]


def test_branch_specific_non_release_function_pointer_path_is_reported(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int release, int err)
{
    void *ptr = kmalloc(8);
    void (*fn)(void *) = inspect;
    if (release)
        fn = kfree;
    fn(ptr);
    if (err)
        return err;
    return 0;
}
""",
    )
    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]


def test_unparsed_function_pointer_assignment_marks_target_set_incomplete(
    tmp_path: Path,
):
    rows = _rows(
        tmp_path,
        """
int work(void (**table)(void *), int mode, int index, int err)
{
    void *ptr = kmalloc(8);
    void (*fn)(void *) = kfree;
    if (mode)
        fn = table[index];
    fn(ptr);
    if (err)
        return err;
    return 0;
}
""",
    )

    error = next(row for row in rows if row.condition == "err")
    assert error.missing_cleanup_candidates == ["kfree(ptr)"]
    causes = {
        cause
        for resource in error.held_resources
        for cause in resource["uncertainty_causes"]
    }
    assert "incomplete_function_pointer_targets" in causes


def test_cfg_excludes_err_ptr_acquisition_failure_with_unrelated_slice(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(int err)
{
    void *ptr = kmalloc(8);
    if (IS_ERR(ptr))
        return PTR_ERR(ptr);
    return 0;
}
""",
    )
    error = next(row for row in rows if "IS_ERR(ptr)" in row.condition)
    assert error.missing_cleanup_candidates == []


def test_cfg_excludes_acquire_failure_checked_through_original_alias(
    tmp_path: Path,
):
    rows = _rows(
        tmp_path,
        """
int work(void)
{
    void *tmp = start_handle();
    void *ptr = tmp;
    if (IS_ERR(tmp))
        return PTR_ERR(tmp);
    stop_handle(ptr);
    return 0;
}
""",
    )

    error = next(row for row in rows if "IS_ERR(tmp)" in row.condition)
    assert error.missing_cleanup_candidates == []
    assert error.held_resources == []


def test_acquire_validity_guard_follows_boolean_is_err_alias(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(void)
{
    void *ptr = start_handle();
    int bad = IS_ERR(ptr);
    if (unlikely(bad))
        return PTR_ERR(ptr);
    stop_handle(ptr);
    return 0;
}
""",
    )

    error = next(row for row in rows if row.condition == "bad")
    assert error.held_resources == []
    assert error.missing_cleanup_candidates == []


def test_out_parameter_acquire_guard_uses_call_return_edge(tmp_path: Path):
    resource_map = {
        "acquire_functions": {
            **RESOURCE_MAP["acquire_functions"],
            "load_item": {
                "resource_type": "memory",
                "release": ["kfree"],
                "out_resource_arg": 0,
                "out_arg_requires_address": True,
                "acquire_success_guard": "return == 0",
            },
        }
    }
    path = tmp_path / "out_guard.c"
    path.write_text(
        """
int work(int err)
{
    void *ptr = NULL;
    int ret = load_item(&ptr);
    if (ret)
        return ret;
    if (err)
        return err;
    kfree(ptr);
    return 0;
}
""",
        encoding="utf-8",
    )
    function = extract_functions(parse_c_file(path))[0]
    rows = ErrorPathExtractor(ResourceTracker(resource_map)).extract(function)

    acquire_error = next(row for row in rows if row.condition == "ret")
    later_error = next(row for row in rows if row.condition == "err")
    assert acquire_error.held_resources == []
    assert later_error.missing_cleanup_candidates == ["kfree(ptr)"]
    assert later_error.held_resources[0]["validity_guard"] == "ret == 0"
    assert later_error.held_resources[0]["validity_guard_source"] == "explicit"
    assert later_error.held_resources[0]["multiplicity"] == "one"
    assert "unresolved_acquire_validity" not in later_error.held_resources[0][
        "uncertainty_causes"
    ]


def test_compatibility_default_guard_cannot_prove_acquire_success(tmp_path: Path):
    resource_map = {
        "acquire_functions": {
            "load_item": {
                "resource_type": "memory",
                "release": ["kfree"],
                "out_resource_arg": 0,
                "out_arg_requires_address": True,
            },
        }
    }
    path = tmp_path / "inferred_out_guard.c"
    path.write_text(
        """
int work(int err)
{
    void *ptr = NULL;
    int ret = load_item(&ptr);
    if (ret)
        return ret;
    if (err)
        return err;
    kfree(ptr);
    return 0;
}
""",
        encoding="utf-8",
    )
    function = extract_functions(parse_c_file(path))[0]
    tracker = ResourceTracker(resource_map)
    rows = ErrorPathExtractor(tracker).extract(function)

    acquire_error = next(row for row in rows if row.condition == "ret")
    later_error = next(row for row in rows if row.condition == "err")
    assert acquire_error.held_resources == []
    assert later_error.held_resources[0]["ownership_state"] == "MAY_ACQUIRED"
    assert later_error.held_resources[0]["validity_guard_source"] == (
        "compatibility_default"
    )
    assert later_error.held_resources[0]["uncertainty_causes"] == [
        "unresolved_acquire_validity"
    ]
    assert tracker.cfg_diagnostics()["inferred_validity_guards"] == 1


def test_cfg_keeps_full_indexed_field_resource_identity(tmp_path: Path):
    rows = _rows(
        tmp_path,
        """
int work(struct holder *h, int i)
{
    h->items[i].ptr = kmalloc(8);
    if (!h->items[i].ptr)
        return -ENOMEM;
    return -EIO;
}
""",
    )
    failure = next(row for row in rows if "!h->items[i].ptr" in row.condition)
    assert failure.missing_cleanup_candidates == []


def test_cleanup_loop_entry_decrement_does_not_release_current_element(tmp_path: Path):
    path = tmp_path / "flow.c"
    path.write_text(
        """
int work(struct holder *h, int i)
{
    h->items[i].ptr = kmalloc(8);
    if (bad)
        goto out;
out:
    for (i--; i >= 0; i--)
        kfree(h->items[i].ptr);
    return -EIO;
}
""",
        encoding="utf-8",
    )
    function = extract_functions(parse_c_file(path))[0]
    statements, labels = parse_statements(function)
    resolution = resolve_label(statements, labels, "out")

    assert "kfree(h->items[i--].ptr)" in resolution.cleanup_calls
    rows = ErrorPathExtractor(ResourceTracker(RESOURCE_MAP)).extract(function)
    error = next(row for row in rows if row.target_label == "out")
    assert error.missing_cleanup_candidates == ["kfree(h->items[i].ptr)"]
