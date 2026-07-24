from pathlib import Path

from src.function_extractor import extract_functions
from src.metadata_residual import ReportKind
from src.parser import parse_c_file
from src.residual_analyzer import analyze_function_residuals
from src.residual_report import reports_to_json, reports_to_markdown


def _function(tmp_path: Path, source: str):
    path = tmp_path / "analyze.c"
    path.write_text(source, encoding="utf-8")
    return extract_functions(parse_c_file(path))[0]


def test_exposed_residual_emits_candidate_report_and_deterministic_json(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct inode *inode, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
    )

    result = analyze_function_residuals(function)
    encoded_once = reports_to_json(result.reports)
    encoded_twice = reports_to_json(result.reports)

    assert len(result.reports) == 1
    report = result.reports[0]
    assert report.kind is ReportKind.UNCLOSED_METADATA_RESIDUAL
    assert report.confidence == "candidate"
    assert result.candidates == (report,)
    assert encoded_once == encoded_twice
    assert '"source_version"' in encoded_once
    assert '"UNCLOSED_METADATA_RESIDUAL"' in encoded_once


def test_markdown_witness_is_readable(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct inode *inode, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
    )

    markdown = reports_to_markdown(analyze_function_residuals(function).reports)

    assert "# UNCLOSED_METADATA_RESIDUAL: work" in markdown
    assert "## E_f Reaching Effects" in markdown
    assert "## R_f Residuals" in markdown
    assert "inode.i_blocks" in markdown
    assert "fail_metadata()" in markdown


def test_closed_residual_is_not_reported_by_default_but_can_be_audit_record(
    tmp_path: Path,
):
    function = _function(
        tmp_path,
        """
int work(struct inode *inode, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret)
        goto out;
    return 0;
out:
    inode->i_blocks -= nr;
    return ret;
}
""",
    )

    default_result = analyze_function_residuals(function)
    audit_result = analyze_function_residuals(function, include_all=True)

    assert default_result.reports == ()
    assert len(audit_result.reports) == 1
    assert audit_result.reports[0].kind is ReportKind.OUT_OF_SCOPE
    assert audit_result.reports[0].confidence == "review"


def test_unknown_report_is_review_only_and_not_candidate(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct inode *inode, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret)
        goto out;
    return 0;
out:
    dquot_unknown_cleanup(inode);
    return ret;
}
""",
    )

    result = analyze_function_residuals(function)

    assert len(result.reports) == 1
    report = result.reports[0]
    assert report.kind is ReportKind.METADATA_RESIDUAL_UNKNOWN
    assert report.confidence == "review"
    assert result.candidates == ()
    assert report.unknown_causes


def test_error_path_unknown_helper_without_reaching_metadata_is_not_reported(
    tmp_path: Path,
):
    function = _function(
        tmp_path,
        """
int work(struct btrfs_trans_handle *trans)
{
    int ret;

    ret = fail_metadata();
    if (ret)
        goto out;
    return 0;
out:
    btrfs_end_transaction(trans);
    return ret;
}
""",
    )

    result = analyze_function_residuals(function)

    assert result.reports == ()
