from pathlib import Path

from src.error_path_extractor import ErrorPathExtractor
from src.function_extractor import extract_functions
from src.parser import parse_c_file
from src.resource_tracker import ResourceTracker
from src.label_resolver import parse_statements, resolve_label


RESOURCE_MAP = {
    "acquire_functions": {
        "kmalloc": {"resource_type": "memory", "release": ["kfree"]},
        "start_handle": {"resource_type": "handle", "release": ["stop_handle"]},
    }
}


def _rows(tmp_path: Path, source: str):
    path = tmp_path / "flow.c"
    path.write_text(source, encoding="utf-8")
    function = extract_functions(parse_c_file(path))[0]
    return ErrorPathExtractor(ResourceTracker(RESOURCE_MAP)).extract(function)


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


def test_unknown_indirect_call_turns_resource_state_unknown(tmp_path: Path):
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
    assert error.missing_cleanup_candidates == []


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
