import json
from pathlib import Path

from src.evaluation_harness import (
    load_confirmed_bug_mapping,
    run_batch_evaluation,
    run_evaluation,
)


def test_evaluation_harness_writes_reports_and_summary(tmp_path: Path):
    source = tmp_path / "fs" / "btrfs" / "eval.c"
    source.parent.mkdir(parents=True)
    source.write_text(
        """
static void charge_inode(struct inode *inode, long nr)
{
    inode->i_blocks += nr;
}

int work(struct inode *inode, long nr)
{
    int ret;

    charge_inode(inode, nr);
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
        encoding="utf-8",
    )
    bug_map = tmp_path / "bugs.json"
    bug_map.write_text(
        json.dumps(
            [
                {
                    "bug_id": 99,
                    "fs": "btrfs",
                    "function": "work",
                    "type": "metadata residual",
                    "status": "fixture",
                }
            ]
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    result = run_evaluation(
        source,
        out_dir,
        source_root=tmp_path,
        confirmed_bug_mapping=bug_map,
    )

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    all_reports = json.loads(
        (out_dir / "reports" / "all_reports.json").read_text(encoding="utf-8")
    )
    markdown = (out_dir / "reports" / "all_reports.md").read_text(encoding="utf-8")

    assert result.summary == summary
    assert summary["functions_analyzed"] == 2
    assert summary["candidate_count"] == 1
    assert summary["confirmed_bug_records"] == 1
    assert summary["confirmed_bug_functions_in_source"] == ["work"]
    assert all_reports[0]["kind"] == "UNCLOSED_METADATA_RESIDUAL"
    assert "UNCLOSED_METADATA_RESIDUAL: work" in markdown
    assert list((out_dir / "reports").glob("0001_work_*.json"))
    assert list((out_dir / "reports").glob("0001_work_*.md"))


def test_evaluation_harness_include_all_writes_out_of_scope_audit(tmp_path: Path):
    source = tmp_path / "closed.c"
    source.write_text(
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
        encoding="utf-8",
    )
    out_dir = tmp_path / "audit"

    result = run_evaluation(source, out_dir, include_all=True)

    assert result.summary["out_of_scope_count"] == 1
    report = json.loads(
        (out_dir / "reports" / "all_reports.json").read_text(encoding="utf-8")
    )[0]
    assert report["kind"] == "OUT_OF_SCOPE"


def test_evaluation_harness_removes_stale_numbered_reports(tmp_path: Path):
    source = tmp_path / "rerun.c"
    source.write_text(
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
        encoding="utf-8",
    )
    out_dir = tmp_path / "rerun-out"
    run_evaluation(source, out_dir)
    reports_dir = out_dir / "reports"
    assert list(reports_dir.glob("0001_*.json"))
    (reports_dir / "candidate_triage.md").write_text("keep", encoding="utf-8")

    source.write_text("int work(void) { return 0; }\n", encoding="utf-8")
    run_evaluation(source, out_dir)

    assert not list(reports_dir.glob("[0-9][0-9][0-9][0-9]_*.json"))
    assert not list(reports_dir.glob("[0-9][0-9][0-9][0-9]_*.md"))
    assert (reports_dir / "candidate_triage.md").read_text(encoding="utf-8") == "keep"


def test_evaluation_summary_counts_unknown_cause_categories(tmp_path: Path):
    source = tmp_path / "unknown.c"
    source.write_text(
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
        encoding="utf-8",
    )
    out_dir = tmp_path / "unknown-out"

    result = run_evaluation(source, out_dir)

    assert result.summary["unknown_count"] == 1
    assert result.summary["unknown_cause_counts"] == {
        "unresolved_metadata_helper_on_error_path": 1,
    }
    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["unknown_cause_counts"] == result.summary["unknown_cause_counts"]


def test_batch_evaluation_aggregates_directory_results(tmp_path: Path):
    source_dir = tmp_path / "fs" / "btrfs"
    source_dir.mkdir(parents=True)
    (source_dir / "one.c").write_text(
        """
int one(struct inode *inode, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
        encoding="utf-8",
    )
    (source_dir / "two.c").write_text(
        """
int two(struct inode *inode, long nr)
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
        encoding="utf-8",
    )
    bug_map = tmp_path / "bugs.json"
    bug_map.write_text(
        json.dumps([{"bug_id": 1, "function": "one"}]),
        encoding="utf-8",
    )
    out_dir = tmp_path / "batch"

    result = run_batch_evaluation(
        source_dir,
        out_dir,
        source_root=tmp_path,
        confirmed_bug_mapping=bug_map,
    )

    summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
    all_reports = json.loads(
        (out_dir / "reports" / "all_reports.json").read_text(encoding="utf-8")
    )
    assert result.summary == summary
    assert summary["source_files_analyzed"] == 2
    assert summary["functions_analyzed"] == 2
    assert summary["candidate_count"] == 1
    assert summary["confirmed_bug_functions_in_source"] == ["one"]
    assert len(all_reports) == 1
    assert list((out_dir / "files").glob("*one.c*"))
    assert list((out_dir / "files").glob("*two.c*"))


def test_batch_evaluation_excludes_matching_globs(tmp_path: Path):
    source_dir = tmp_path / "fs" / "btrfs"
    tests_dir = source_dir / "tests"
    tests_dir.mkdir(parents=True)
    (source_dir / "main.c").write_text(
        """
int mainline(struct inode *inode, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
        encoding="utf-8",
    )
    (tests_dir / "fixture.c").write_text(
        """
int fixture(struct inode *inode, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
        encoding="utf-8",
    )

    result = run_batch_evaluation(
        source_dir,
        tmp_path / "batch-filtered",
        source_root=tmp_path,
        exclude_globs=("fs/btrfs/tests/*",),
    )

    assert result.summary["exclude_globs"] == ["fs/btrfs/tests/*"]
    assert result.summary["source_files_analyzed"] == 1
    assert result.summary["source_files"] == [(source_dir / "main.c").as_posix()]
    assert result.summary["candidate_count"] == 1


def test_batch_evaluation_uses_cross_tu_output_summary(tmp_path: Path):
    source_dir = tmp_path / "fs" / "btrfs"
    source_dir.mkdir(parents=True)
    (source_dir / "allocator.c").write_text(
        """
struct device *alloc_device(void)
{
    struct device *device = kzalloc(sizeof(*device), GFP_KERNEL);

    return device;
}
""",
        encoding="utf-8",
    )
    (source_dir / "caller.c").write_text(
        """
int init_target(struct fs_devices *fs_devices, struct device **device_out)
{
    struct device *device = alloc_device();

    if (!device)
        return -ENOMEM;
    list_add(&device->dev_list, &fs_devices->devices);
    fs_devices->num_devices++;
    *device_out = device;
    return 0;
}

int work(struct fs_devices *fs_devices)
{
    struct device *tgt_device;
    int ret;

    ret = init_target(fs_devices, &tgt_device);
    if (ret)
        return ret;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
        encoding="utf-8",
    )

    result = run_batch_evaluation(source_dir, tmp_path / "batch-cross", source_root=tmp_path)

    assert result.summary["candidate_count"] == 1
    work_reports = [report for report in result.reports if report.report.function == "work"]
    assert len(work_reports) == 1
    residuals = work_reports[0].report.residual_slice.residuals
    assert any(effect.value == "tgt_device->dev_list" for effect in residuals)
    assert any(effect.key == "num_devices" for effect in residuals)


def test_confirmed_bug_markdown_mapping_is_loaded(tmp_path: Path):
    mapping = tmp_path / "confirmed_bugs.md"
    mapping.write_text(
        """
| # | FS | Function | Bug type | Status | Evidence |
|---:|---|---|---|---|---|
| 7 | btrfs | `btrfs_recover_relocation()` | residual | confirmed | report |
""",
        encoding="utf-8",
    )

    records = load_confirmed_bug_mapping(mapping)

    assert len(records) == 1
    assert records[0].bug_id == 7
    assert records[0].filesystem == "btrfs"
    assert records[0].function == "btrfs_recover_relocation()"
