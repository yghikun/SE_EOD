from pathlib import Path

from src.error_path_extractor import ErrorPathExtractor
from src.function_extractor import extract_functions
from src.parser import parse_c_file
from src.resource_tracker import ResourceTracker


RESOURCE_MAP = {
    "acquire_functions": {
        "kmalloc": {"resource_type": "memory", "release": ["kfree"]}
    }
}


def _extract(tmp_path: Path, source: str):
    path = tmp_path / "retry.c"
    path.write_text(source, encoding="utf-8")
    function = extract_functions(parse_c_file(path))[0]
    return ErrorPathExtractor(ResourceTracker(RESOURCE_MAP)).extract(function)


def test_direct_retry_backedge_is_not_an_error_exit(tmp_path: Path):
    rows = _extract(
        tmp_path,
        """
int retry_work(void)
{
    void *ptr = NULL;
    int err = 0;
retry:
    if (err && !ptr)
        ptr = kmalloc(8);
    err = do_work(ptr);
    if (err)
        goto retry;
    kfree(ptr);
    return 0;
}
""",
    )

    assert not any(row.condition == "err" and row.target_label == "retry" for row in rows)


def test_indirect_error_retry_label_cycle_is_not_an_error_exit(tmp_path: Path):
    rows = _extract(
        tmp_path,
        """
int retry_work(void)
{
    void *ptr = NULL;
    int err = 0;
retry:
    if (err && !ptr)
        ptr = kmalloc(8);
    err = do_work(ptr);
    if (err)
        goto error;
error:
    unlock();
    if (err)
        goto retry;
    kfree(ptr);
    return 0;
}
""",
    )

    assert not any(row.condition == "err" and row.target_label == "error" for row in rows)


def test_retry_backedge_to_label_with_early_error_return_is_not_exit(tmp_path: Path):
    rows = _extract(
        tmp_path,
        """
int retry_with_early_failure(void)
{
    void *ptr;
    int ret;
again:
    ptr = kmalloc(8);
    if (!ptr)
        return -ENOMEM;
    ret = do_work(ptr);
    if (ret == -EAGAIN)
        goto again;
    if (ret)
        goto out;
    kfree(ptr);
    return 0;
out:
    kfree(ptr);
    return ret;
}
""",
    )

    assert not any(
        row.condition == "ret == -EAGAIN" and row.target_label == "again"
        for row in rows
    )


def test_restart_backedge_after_cleanup_is_not_error_exit(tmp_path: Path):
    rows = _extract(
        tmp_path,
        """
int restart_after_cleanup(int restart)
{
    void *ptr;
    int err = 0;
again:
    ptr = kmalloc(8);
    err = do_work(ptr);
cleanup:
    kfree(ptr);
    if (restart && err == 0)
        goto again;
    return err;
}
""",
    )

    assert not any(
        row.condition == "restart && err == 0" and row.target_label == "again"
        for row in rows
    )


def test_forward_cleanup_label_still_resolves_to_return(tmp_path: Path):
    rows = _extract(
        tmp_path,
        """
int fail_work(void)
{
    void *ptr;
    int err;

    ptr = kmalloc(8);
    err = do_work(ptr);
    if (err)
        goto out;
    use(ptr);
out:
    kfree(ptr);
    return err;
}
""",
    )

    matching = [row for row in rows if row.condition == "err" and row.target_label == "out"]
    assert matching
    assert matching[0].final_return_expr == "err"
    assert matching[0].missing_cleanup_candidates == []


def test_conditional_retry_not_implied_by_error_still_reaches_return(tmp_path: Path):
    rows = _extract(
        tmp_path,
        """
int maybe_retry(void)
{
    void *ptr;
    int err;
retry:
    ptr = kmalloc(8);
    err = do_work(ptr);
    if (err)
        goto out;
out:
    kfree(ptr);
    if (err == -ENOMEM && should_retry())
        goto retry;
    return err;
}
""",
    )

    matching = [row for row in rows if row.condition == "err" and row.target_label == "out"]
    assert matching
    assert matching[0].final_return_expr == "unknown"
