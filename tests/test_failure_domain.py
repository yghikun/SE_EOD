from pathlib import Path

from src.function_extractor import extract_functions
from src.metadata_residual import FailureDomainKind, ReportKind, ResidualState
from src.parser import parse_c_file
from src.residual_analyzer import analyze_functions
from src.residual_slicer import slice_function_residuals


def _functions(tmp_path: Path, source: str):
    path = tmp_path / "failure_domain.c"
    path.write_text(source, encoding="utf-8")
    return extract_functions(parse_c_file(path))


def test_terminal_checkpoint_on_must_error_path_contains_real_residual(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct f2fs_sb_info *sbi, struct inode *inode, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret) {
        f2fs_stop_checkpoint(sbi, false, STOP_CP_REASON_META_PAGE);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.CONTAINED
    assert len(residual_slice.residuals) == 1
    assert residual_slice.containment_proofs[0].kind is FailureDomainKind.CHECKPOINT_STOP


def test_write_only_output_residual_is_out_of_scope(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int statfs(struct kstatfs *buf)
{
    int ret;

    buf->f_blocks = 10;
    buf->f_bfree = buf->f_blocks;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.residuals == ()
    assert residual_slice.out_of_scope_effects


def test_conditional_terminal_checkpoint_does_not_prove_containment(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct f2fs_sb_info *sbi, struct inode *inode, long nr, int stop)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret) {
        if (stop)
            f2fs_stop_checkpoint(sbi, false, STOP_CP_REASON_META_PAGE);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is not ResidualState.CONTAINED


def test_callee_terminal_branch_is_not_propagated_to_every_error_return(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
static int maybe_shutdown(struct xfs_mount *mp)
{
    int ret = fail_metadata();

    if (ret == -EFSCORRUPTED)
        xfs_force_shutdown(mp, SHUTDOWN_CORRUPT_INCORE);
    return ret;
}

int work(struct xfs_mount *mp, struct inode *inode, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = maybe_shutdown(mp);
    if (ret)
        return ret;
    return 0;
}
""",
    )

    analyses = {item.function: item for item in analyze_functions(functions)}

    assert analyses["work"].slicing_result.slices[0].state is ResidualState.EXPOSED


def test_callee_terminal_action_propagates_only_when_every_error_exit_is_terminal(
    tmp_path: Path,
):
    functions = _functions(
        tmp_path,
        """
static int stop_on_failure(struct f2fs_sb_info *sbi, int checkpoint_error)
{
    if (checkpoint_error) {
        f2fs_stop_checkpoint(sbi, true);
        return -EIO;
    }
    f2fs_stop_checkpoint(sbi, false);
    return -ENOSPC;
}

int work(
    struct f2fs_sb_info *sbi,
    struct inode *inode,
    long nr,
    int checkpoint_error)
{
    int ret;

    inode->i_blocks += nr;
    ret = stop_on_failure(sbi, checkpoint_error);
    if (ret)
        return ret;
    return 0;
}
""",
    )

    analyses = {item.function: item for item in analyze_functions(functions)}
    residual_slice = analyses["work"].slicing_result.slices[0]

    assert residual_slice.state is ResidualState.CONTAINED
    assert any(
        proof.kind is FailureDomainKind.CHECKPOINT_STOP
        for proof in residual_slice.containment_proofs
    )


def test_dirty_xfs_transaction_cancel_contains_unrestorable_peer_state(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct xfs_trans *tp, struct inode *tip, long nr)
{
    int ret;

    xfs_trans_log_inode(tp, tip, 1);
    tip->i_blocks += nr;
    ret = fail_metadata();
    if (ret) {
        xfs_trans_cancel(tp);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.CONTAINED
    assert any(
        proof.kind is FailureDomainKind.FATAL_SHUTDOWN
        for proof in residual_slice.containment_proofs
    )
    assert any(effect.root == "tip" for effect in residual_slice.residuals)


def test_all_visible_static_callers_must_contain_propagated_error_effects(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
static int mutate(struct inode *inode, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}

int outer(struct inode *inode, long nr)
{
    int ret = mutate(inode, nr);

    if (ret) {
        inode->i_blocks -= nr;
        return ret;
    }
    return 0;
}
""",
    )

    analyses = {item.function: item for item in analyze_functions(functions)}
    inner = analyses["mutate"]

    assert inner.slicing_result.slices[0].state is ResidualState.CONTAINED
    assert inner.reports[0].kind is ReportKind.CONTAINED_METADATA_RESIDUAL
    assert inner.candidates == ()


def test_unchecked_static_call_blocks_caller_containment(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
static int mutate(struct inode *inode, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}

int contained_caller(struct inode *inode, long nr)
{
    int ret = mutate(inode, nr);

    if (ret) {
        inode->i_blocks -= nr;
        return ret;
    }
    return 0;
}

void unchecked_caller(struct inode *inode, long nr)
{
    mutate(inode, nr);
}
""",
    )

    analyses = {item.function: item for item in analyze_functions(functions)}

    assert analyses["mutate"].slicing_result.slices[0].state is ResidualState.EXPOSED
    assert len(analyses["mutate"].candidates) == 1
