from pathlib import Path

from src.failure_points import find_failure_points
from src.function_extractor import extract_functions
from src.parser import parse_c_file


def _function(tmp_path: Path, source: str):
    path = tmp_path / "failure_points.c"
    path.write_text(source, encoding="utf-8")
    return extract_functions(parse_c_file(path))[0]


def test_detects_ret_if_goto_error_exit(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(void)
{
    int ret;

    ret = prepare_metadata();
    if (ret)
        goto out;
    commit_metadata();
out:
    return ret;
}
""",
    )

    points = find_failure_points(function)

    assert len(points) == 1
    point = points[0]
    assert point.callee == "prepare_metadata"
    assert point.result_symbol == "ret"
    assert point.check_kind == "nonzero"
    assert point.call_site.expression == "prepare_metadata()"
    assert point.error_edge.kind == "true"
    assert point.error_edge.exit_expression == "ret"


def test_detects_negative_ret_return_on_error_edge(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(void)
{
    int ret = reserve_blocks();

    if (ret < 0)
        return ret;
    return 0;
}
""",
    )

    points = find_failure_points(function)

    assert len(points) == 1
    assert points[0].callee == "reserve_blocks"
    assert points[0].check_kind == "<0"
    assert points[0].error_edge.exit_expression == "ret"


def test_detects_is_err_ptr_err_return(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(void)
{
    struct obj *ptr;

    ptr = allocate_obj();
    if (IS_ERR(ptr))
        return PTR_ERR(ptr);
    attach_obj(ptr);
    return 0;
}
""",
    )

    points = find_failure_points(function)

    assert len(points) == 1
    assert points[0].callee == "allocate_obj"
    assert points[0].result_symbol == "ptr"
    assert points[0].check_kind == "IS_ERR"
    assert points[0].error_edge.exit_expression == "PTR_ERR(ptr)"


def test_detects_direct_call_comparison_return_error(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(void)
{
    if (write_metadata() < 0)
        return -EIO;
    return 0;
}
""",
    )

    points = find_failure_points(function)

    assert len(points) == 1
    assert points[0].callee == "write_metadata"
    assert points[0].result_symbol == "write_metadata()"
    assert points[0].error_edge.exit_expression == "-EIO"


def test_shared_out_label_yields_one_failure_per_checked_call(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(void)
{
    int ret;

    ret = first_step();
    if (ret)
        goto out;
    ret = second_step();
    if (ret)
        goto out;
out:
    return ret;
}
""",
    )

    points = find_failure_points(function)

    assert [point.callee for point in points] == ["first_step", "second_step"]
    assert {point.error_edge.exit_expression for point in points} == {"ret"}


def test_non_error_success_branch_is_ignored(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(void)
{
    int ret;

    ret = prepare_metadata();
    if (!ret)
        return 0;
    return ret;
}
""",
    )

    assert find_failure_points(function) == ()


def test_outcome_extension_can_report_return_zero_on_error_edge(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(void)
{
    int ret;

    ret = prepare_metadata();
    if (ret)
        return 0;
    return 0;
}
""",
    )

    assert find_failure_points(function) == ()
    points = find_failure_points(function, include_outcome_success=True)

    assert len(points) == 1
    assert points[0].error_edge.outcome_extension is True
    assert points[0].error_edge.exit_expression == "0"


def test_detects_exact_negative_error_comparison(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(void)
{
    int ret = prepare_metadata();

    if (ret == -EIO)
        return ret;
    return 0;
}
""",
    )

    points = find_failure_points(function)

    assert len(points) == 1
    assert points[0].result_symbol == "ret"
    assert points[0].check_kind == "eq:-EIO"


def test_detects_ptr_err_exact_comparison_on_pointer_result(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(void)
{
    struct page *page = get_page();

    if (PTR_ERR(page) == -EIO)
        return -EIO;
    return 0;
}
""",
    )

    points = find_failure_points(function)

    assert len(points) == 1
    assert points[0].callee == "get_page"
    assert points[0].result_symbol == "page"
    assert points[0].check_kind == "eq:-EIO"


def test_detects_constant_switch_error_case(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(void)
{
    int ret = prepare_metadata();

    switch (ret) {
    case -EIO:
        return ret;
    default:
        return 0;
    }
}
""",
    )

    points = find_failure_points(function)

    assert len(points) == 1
    assert points[0].callee == "prepare_metadata"
    assert points[0].check_kind == "eq:-EIO"


def test_exact_comparison_rejects_retry_path_that_can_rebind_result(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(void)
{
    int ret;

retry:
    ret = prepare_metadata();
    if (ret == -ENOMEM)
        goto retry;
    return ret;
}
""",
    )

    assert find_failure_points(function) == ()


def test_exact_comparison_rejects_normalized_error_value(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(void)
{
    int error;

    error = reserve_metadata();
    if (error == -ENOSPC)
        error = 0;
    return error;
}
""",
    )

    assert find_failure_points(function) == ()


def test_exact_comparison_rejects_rewritten_special_error_return(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(void)
{
    int ret;

    ret = finish_metadata();
    if (ret == -EINPROGRESS)
        ret = RESULT_STILL_RUNNING;
    return ret;
}
""",
    )

    assert find_failure_points(function) == ()
