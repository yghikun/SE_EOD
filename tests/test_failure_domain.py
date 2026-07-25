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
    assert residual_slice.containment_proofs[0].covered_effects == residual_slice.residuals


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


def test_xfs_transaction_cancel_does_not_contain_unregistered_peer_state(
    tmp_path: Path,
):
    function = _functions(
        tmp_path,
        """
int work(struct xfs_trans *tp, struct inode *logged, struct inode *other, long nr)
{
    int ret;

    xfs_trans_log_inode(tp, logged, 1);
    other->i_blocks += nr;
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

    assert residual_slice.state is ResidualState.EXPOSED
    assert [effect.root for effect in residual_slice.residuals] == ["other"]
    assert residual_slice.containment_proofs == ()


def test_xfs_trans_ijoin_binds_inode_effect_to_transaction_cancel(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct xfs_trans *tp, struct inode *ip, long nr)
{
    int ret;

    xfs_trans_ijoin(tp, ip, 0);
    ip->i_delayed_blks += nr;
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
        and any(effect.root == "ip" for effect in proof.covered_effects)
        for proof in residual_slice.containment_proofs
    )


def test_summary_wrapped_xfs_transaction_cancel_contains_bound_state(tmp_path: Path):
    functions = _functions(
        tmp_path,
        """
void xfs_trans_cancel(struct xfs_trans *tp)
{
}

void xchk_trans_cancel(struct xfs_scrub *sc)
{
    xfs_trans_cancel(sc->tp);
    sc->tp = 0;
}

int work(struct xfs_scrub *sc, struct inode *dp)
{
    int ret;

    xfs_trans_alloc_dir(dp, &sc->tp);
    ret = fail_metadata();
    if (ret) {
        xchk_trans_cancel(sc);
        return ret;
    }
    return 0;
}
""",
    )

    analyses = {item.function: item for item in analyze_functions(functions)}
    residual_slice = analyses["work"].slicing_result.slices[0]

    assert residual_slice.state is ResidualState.PROTECTED
    assert residual_slice.residuals == ()
    assert any(
        effect.key == "xfs_trans_alloc_dir"
        and effect.site.expression.endswith("protects transaction-bound effect")
        for effect in residual_slice.protections
    )


def test_conditional_shutdown_does_not_block_must_dirty_transaction_containment(
    tmp_path: Path,
):
    function = _functions(
        tmp_path,
        """
int work(
    struct xfs_mount *mp,
    struct xfs_trans *tp,
    struct inode *tip,
    long nr,
    int force)
{
    int ret;

    xfs_trans_log_inode(tp, tip, 1);
    tip->i_blocks += nr;
    ret = fail_metadata();
    if (ret) {
        xfs_trans_cancel(tp);
        if (force)
            xfs_force_shutdown(mp, SHUTDOWN_CORRUPT_ONDISK);
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


def test_btrfs_abort_contains_only_effect_bound_to_same_transaction(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct btrfs_trans_handle *trans, long nr)
{
    int ret;

    trans->bytes_reserved += nr;
    ret = fail_metadata();
    if (ret) {
        btrfs_abort_transaction(trans, ret);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.CONTAINED
    proof = residual_slice.containment_proofs[0]
    assert proof.kind is FailureDomainKind.TRANSACTION_ABORT
    assert proof.owner == "trans"
    assert proof.covered_effects == residual_slice.residuals


def test_btrfs_abort_does_not_contain_transaction_external_effect(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(
    struct btrfs_trans_handle *trans,
    struct inode *inode,
    long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret) {
        btrfs_abort_transaction(trans, ret);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.containment_proofs == ()


def test_mixed_btrfs_abort_slice_retains_uncovered_effect(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(
    struct btrfs_trans_handle *trans,
    struct inode *inode,
    long nr)
{
    int ret;

    trans->bytes_reserved += nr;
    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret) {
        btrfs_abort_transaction(trans, ret);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert {effect.root for effect in residual_slice.residuals} == {"trans", "inode"}
    proof = residual_slice.containment_proofs[0]
    assert [effect.root for effect in proof.covered_effects] == ["trans"]


def test_conditional_btrfs_abort_does_not_prove_containment(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct btrfs_trans_handle *trans, long nr, int abort)
{
    int ret;

    trans->bytes_reserved += nr;
    ret = fail_metadata();
    if (ret) {
        if (abort)
            btrfs_abort_transaction(trans, ret);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.UNKNOWN
    assert residual_slice.containment_proofs == ()


def test_callee_abort_does_not_hide_transaction_external_failure_effect(
    tmp_path: Path,
):
    functions = _functions(
        tmp_path,
        """
static int mutate(
    struct btrfs_trans_handle *trans,
    struct inode *inode,
    long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret) {
        btrfs_abort_transaction(trans, ret);
        return ret;
    }
    return 0;
}

int outer(
    struct btrfs_trans_handle *trans,
    struct inode *inode,
    long nr)
{
    int ret = mutate(trans, inode, nr);

    if (ret)
        return ret;
    return 0;
}
""",
    )

    analyses = {item.function: item for item in analyze_functions(functions)}
    outer_slice = analyses["outer"].slicing_result.slices[0]

    assert outer_slice.state is ResidualState.EXPOSED
    assert any(effect.root == "inode" for effect in outer_slice.residuals)


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
