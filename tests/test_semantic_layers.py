from pathlib import Path

from src.effect_extractor import extract_metadata_effects_with_skips
from src.frontend.tree_sitter_frontend import TreeSitterFrontend
from src.function_extractor import extract_functions
from src.function_summary import build_same_file_summaries
from src.metadata_residual import (
    EffectEvidence,
    EffectProvenanceKind,
    OwnerScopeKind,
    ReportKind,
    ResidualClassification,
    ResidualState,
    residual_report,
)
from src.parser import parse_c_file
from src.residual_analyzer import analyze_functions
from src.residual_slicer import slice_function_residuals


def _legacy_functions(tmp_path: Path, source: str):
    path = tmp_path / "semantic_layers.c"
    path.write_text(source, encoding="utf-8")
    return extract_functions(parse_c_file(path))


def _frontend_functions(tmp_path: Path, source: str):
    path = tmp_path / "semantic_layers_frontend.c"
    path.write_text(source, encoding="utf-8")
    return TreeSitterFrontend(tmp_path).parse(path).functions


def test_write_only_output_has_auditable_provenance(tmp_path: Path):
    function = _legacy_functions(
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
    assert residual_slice.out_of_scope_effects
    assert all(
        item.semantic_provenance[0].kind is EffectProvenanceKind.WRITE_ONLY_OUTPUT
        for item in residual_slice.out_of_scope_effects
    )


def test_parent_free_does_not_close_separately_allocated_child(tmp_path: Path):
    function = _legacy_functions(
        tmp_path,
        """
int work(void)
{
    struct parent *parent = kzalloc(sizeof(*parent), GFP_KERNEL);
    struct inode *child = kzalloc(sizeof(*child), GFP_KERNEL);
    int ret;

    parent->child = child;
    child->i_blocks += 1;
    ret = fail_metadata();
    if (ret) {
        kfree(parent);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert any(effect.root == "child" for effect in residual_slice.residuals)
    assert not any(
        effect.root == "child"
        for proof in residual_slice.owner_teardown_proofs
        for effect in proof.closed_effects
    )


def test_failed_mount_teardown_records_scope_proof(tmp_path: Path):
    function = _frontend_functions(
        tmp_path,
        """
int build_mount(void)
{
    struct xfs_mount *mp = kzalloc(sizeof(*mp), GFP_KERNEL);
    int ret;

    mp->m_blocks = 1;
    ret = fail_metadata();
    if (ret) {
        kfree(mp);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.owner_scope_proofs
    assert (
        residual_slice.owner_scope_proofs[0].kind
        is OwnerScopeKind.UNPUBLISHED_MOUNT_CONSTRUCTION
    )


def test_success_only_publication_does_not_block_goto_error_teardown(tmp_path: Path):
    function = _legacy_functions(
        tmp_path,
        """
int build(struct result **out)
{
    struct result *item = kzalloc(sizeof(*item), GFP_KERNEL);
    int ret;

    item->name = item->namebuf;
    ret = fail_metadata();
    if (ret)
        goto out_item;
    *out = item;
    return 0;
out_item:
    kfree(item);
    return ret;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.residuals == ()
    assert residual_slice.owner_teardown_proofs
    assert residual_slice.owner_teardown_proofs[0].owner == "item"


def test_fresh_descriptor_copy_is_closed_by_must_owner_teardown(tmp_path: Path):
    function = _legacy_functions(
        tmp_path,
        """
int build(struct context *ctx)
{
    struct descriptor *desc = kzalloc(sizeof(*desc), GFP_KERNEL);
    int ret;

    desc->args.trans = ctx->transaction;
    ret = fail_metadata();
    if (ret) {
        kfree(desc);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.owner_teardown_proofs
    assert residual_slice.owner_teardown_proofs[0].closed_effects[0].semantic_provenance


def test_possible_escape_before_must_teardown_remains_boundary(tmp_path: Path):
    function = _legacy_functions(
        tmp_path,
        """
int build(void)
{
    struct descriptor *desc = kzalloc(sizeof(*desc), GFP_KERNEL);
    int ret;

    desc->count = 1;
    ret = unknown_publish_or_fail(desc);
    if (ret) {
        kfree(desc);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.residuals
    assert residual_slice.owner_teardown_proofs == ()
    assert "owner_scope_escape_review:desc" in residual_slice.semantic_blockers


def test_recovery_effect_is_not_contained_by_shutdown_alone(tmp_path: Path):
    function = _legacy_functions(
        tmp_path,
        """
int work(struct xfs_mount *mp, struct root *root)
{
    int ret;

    root->reloc_root = root;
    ret = fail_metadata();
    if (ret) {
        xfs_force_shutdown(mp, SHUTDOWN_CORRUPT_INCORE);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.containment_proofs == ()


def test_transaction_local_recovery_effect_can_be_contained_by_shutdown(
    tmp_path: Path,
):
    function = _legacy_functions(
        tmp_path,
        """
int work(struct xfs_mount *mp, struct transaction *tp)
{
    int ret;

    xfs_defer_trans_roll(tp);
    ret = fail_metadata();
    if (ret) {
        xfs_force_shutdown(mp, SHUTDOWN_CORRUPT_INCORE);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.CONTAINED
    assert residual_slice.residuals[0].visibility.value == "TRANSACTION_LOCAL"
    assert residual_slice.containment_proofs


def test_owner_teardown_does_not_close_recovery_visible_state(tmp_path: Path):
    function = _legacy_functions(
        tmp_path,
        """
int work(void)
{
    struct root *root = kzalloc(sizeof(*root), GFP_KERNEL);
    int ret;

    root->reloc_root = root;
    ret = fail_metadata();
    if (ret) {
        kfree(root);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.owner_teardown_proofs == ()


def test_lexical_reader_suppression_is_serialized_as_audit_only(tmp_path: Path):
    function = _legacy_functions(
        tmp_path,
        """
int work(struct xfs_mount *mp)
{
    xfs_quota_inode(mp);
    return 0;
}
""",
    )[0]

    extraction = extract_metadata_effects_with_skips(function)

    assert extraction.effects == ()
    assert len(extraction.lexical_suppressions) == 1
    assert extraction.lexical_suppressions[0].helper == "xfs_quota_inode"


def test_equivalent_indirect_cleanup_targets_export_must_cancel(tmp_path: Path):
    cleanup_a, cleanup_b, worker = _legacy_functions(
        tmp_path,
        """
struct ops { void (*cleanup)(struct inode *, long); };

static void cleanup_a(struct inode *inode, long nr)
{
    inode->i_blocks -= nr;
}

static void cleanup_b(struct inode *inode, long nr)
{
    inode->i_blocks -= nr;
}

static const struct ops ops_a = { .cleanup = cleanup_a };
static const struct ops ops_b = { .cleanup = cleanup_b };

static void worker(struct context *ctx, struct inode *inode, long nr)
{
    ctx->ops->cleanup(inode, nr);
}
""",
    )

    summaries = build_same_file_summaries((cleanup_a, cleanup_b, worker))
    summary = summaries["worker"]

    assert summary.unknown_causes == ()
    assert any(effect.key == "i_blocks" for effect in summary.cancels)
    assert len(summary.indirect_target_sets) == 1
    assert summary.indirect_target_sets[0].complete
    assert set(summary.indirect_target_sets[0].possible_targets) == {
        "cleanup_a",
        "cleanup_b",
    }


def test_mixed_indirect_cleanup_targets_remain_unknown(tmp_path: Path):
    cleanup_a, cleanup_b, worker = _legacy_functions(
        tmp_path,
        """
struct ops { void (*cleanup)(struct inode *, long); };

static void cleanup_a(struct inode *inode, long nr)
{
    inode->i_blocks -= nr;
}

static void cleanup_b(struct inode *inode, long nr)
{
    inode->i_blocks = 0;
}

static const struct ops ops_a = { .cleanup = cleanup_a };
static const struct ops ops_b = { .cleanup = cleanup_b };

static void worker(struct context *ctx, struct inode *inode, long nr)
{
    ctx->ops->cleanup(inode, nr);
}
""",
    )

    summary = build_same_file_summaries((cleanup_a, cleanup_b, worker))["worker"]

    assert summary.unknown_causes
    assert summary.cancels == ()
    assert len(summary.indirect_target_sets) == 1
    assert summary.indirect_target_sets[0].complete


def test_unknown_error_helper_emits_demand_summary_request(tmp_path: Path):
    function = _legacy_functions(
        tmp_path,
        """
int work(struct inode *inode)
{
    int ret;

    inode->i_blocks += 1;
    ret = fail_metadata();
    if (ret) {
        dquot_unknown_cleanup(inode);
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.UNKNOWN
    assert residual_slice.demand_summary_requests
    request = residual_slice.demand_summary_requests[0]
    assert request.helper == "dquot_unknown_cleanup"
    assert request.required_semantics.value == "MUST_CANCEL"


def test_handled_failure_and_same_owner_continuation_proves_live_residual(
    tmp_path: Path,
):
    functions = _frontend_functions(
        tmp_path,
        """
static int mutate(struct inode *inode)
{
    int ret;

    inode->i_blocks += 1;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}

int caller(struct inode *inode)
{
    int ret = mutate(inode);

    if (ret) {
        inode->i_state = 1;
        return 0;
    }
    return 0;
}
""",
    )

    analyses = {item.function: item for item in analyze_functions(functions)}
    analysis = analyses["mutate"]
    residual_slice = analysis.slicing_result.slices[0]

    assert residual_slice.state is ResidualState.LIVE
    assert residual_slice.owner_liveness_proofs
    assert analysis.reports[0].report.classification is (
        ResidualClassification.LIVE_METADATA_RESIDUAL
    )


def test_error_return_without_normal_continuation_stays_boundary(tmp_path: Path):
    functions = _frontend_functions(
        tmp_path,
        """
static int mutate(struct inode *inode)
{
    int ret;

    inode->i_blocks += 1;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}

int caller(struct inode *inode)
{
    int ret = mutate(inode);

    if (ret)
        return ret;
    return 0;
}
""",
    )

    analyses = {item.function: item for item in analyze_functions(functions)}
    residual_slice = analyses["mutate"].slicing_result.slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.owner_liveness_proofs == ()


def test_error_partition_records_checked_constraint_and_effect_order(tmp_path: Path):
    helper = _legacy_functions(
        tmp_path,
        """
static int mutate(struct inode *inode)
{
    int ret;

    ret = fail_metadata();
    if (ret) {
        inode->i_blocks += 1;
        return ret;
    }
    return 0;
}
""",
    )[0]

    summary = build_same_file_summaries((helper,))["mutate"]
    partition = summary.error_exit_partitions[0]

    assert partition.return_constraint == "NONZERO"
    assert [effect.key for effect in partition.ordered_effects] == ["i_blocks"]
    assert partition.to_dict()["ordered_effects"][0]["delta"] == "INC"


def test_equivalent_indirect_mutation_targets_export_must_open(tmp_path: Path):
    apply_a, apply_b, worker = _legacy_functions(
        tmp_path,
        """
struct ops { void (*apply)(struct inode *, long); };

static void apply_a(struct inode *inode, long nr)
{
    inode->i_blocks += nr;
}

static void apply_b(struct inode *inode, long nr)
{
    inode->i_blocks += nr;
}

static const struct ops ops_a = { .apply = apply_a };
static const struct ops ops_b = { .apply = apply_b };

static void worker(struct context *ctx, struct inode *inode, long nr)
{
    ctx->ops->apply(inode, nr);
}
""",
    )

    summary = build_same_file_summaries((apply_a, apply_b, worker))["worker"]

    assert summary.unknown_causes == ()
    assert any(effect.key == "i_blocks" for effect in summary.opens)
    assert summary.indirect_target_sets[0].complete


def test_two_level_failure_propagation_proves_owner_live(tmp_path: Path):
    functions = _frontend_functions(
        tmp_path,
        """
static int mutate(struct inode *inode)
{
    int ret;

    inode->i_blocks += 1;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}

static int wrapper(struct inode *inode)
{
    int ret = mutate(inode);

    if (ret)
        return ret;
    return 0;
}

int caller(struct inode *inode)
{
    int ret = wrapper(inode);

    if (ret) {
        inode->i_state = 1;
        return 0;
    }
    return 0;
}
""",
    )

    analyses = {item.function: item for item in analyze_functions(functions)}
    residual_slice = analyses["mutate"].slicing_result.slices[0]

    assert residual_slice.state is ResidualState.LIVE
    assert residual_slice.owner_liveness_proofs
    assert residual_slice.owner_liveness_proofs[0].via_function == "wrapper -> caller"


def test_transaction_ownership_primitive_upgrades_existing_effect_evidence(
    tmp_path: Path,
):
    function = _legacy_functions(
        tmp_path,
        """
void join_inode(struct xfs_trans *tp, struct xfs_inode *ip)
{
    xfs_trans_ijoin(tp, ip, 0);
}
""",
    )[0]

    effects = extract_metadata_effects_with_skips(function).effects

    assert len(effects) == 1
    assert effects[0].key == "xfs_trans_ijoin"
    assert effects[0].evidence is EffectEvidence.EXPLICIT_PRIMITIVE
    assert effects[0].transaction_ownership is not None


def test_same_owner_resource_release_closes_chunk_reservation(tmp_path: Path):
    release, function = _legacy_functions(
        tmp_path,
        """
void btrfs_trans_release_chunk_metadata(struct btrfs_trans_handle *trans)
{
    trans->chunk_bytes_reserved = 0;
}

int work(struct btrfs_trans_handle *trans)
{
    int ret;

    reserve_chunk_space(trans, 4096);
    ret = fail_metadata();
    if (ret) {
        btrfs_trans_release_chunk_metadata(trans);
        return ret;
    }
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((release, function))

    residual_slice = slice_function_residuals(
        function,
        summaries=summaries,
    ).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.residuals == ()
    assert any(
        effect.key == "btrfs_trans_release_chunk_metadata"
        for effect in residual_slice.cancellations
    )


def test_summary_reservation_retains_matching_release_wrapper(tmp_path: Path):
    reserve, release, function = _legacy_functions(
        tmp_path,
        """
static void check_system_chunk(struct btrfs_trans_handle *trans)
{
    reserve_chunk_space(trans, 4096);
}

void btrfs_trans_release_chunk_metadata(struct btrfs_trans_handle *trans)
{
    trans->chunk_bytes_reserved = 0;
}

int work(struct btrfs_trans_handle *trans)
{
    int ret;

    check_system_chunk(trans);
    ret = fail_metadata();
    if (ret) {
        btrfs_trans_release_chunk_metadata(trans);
        return ret;
    }
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((reserve, release, function))

    residual_slice = slice_function_residuals(
        function,
        summaries=summaries,
    ).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.residuals == ()


def test_post_call_precheck_release_is_must_cancellation(tmp_path: Path):
    function = _legacy_functions(
        tmp_path,
        """
int work(struct btrfs_trans_handle *trans)
{
    int ret;

    reserve_chunk_space(trans, 4096);
    ret = fail_metadata();
    btrfs_trans_release_chunk_metadata(trans);
    if (ret)
        return ret;
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.residuals == ()


def test_pointer_snapshot_restores_exact_transaction_field(tmp_path: Path):
    function = _frontend_functions(
        tmp_path,
        """
int work(struct transaction *trans, struct block_rsv *replacement)
{
    struct block_rsv *block_rsv;
    int ret;

    block_rsv = trans->block_rsv;
    trans->block_rsv = replacement;
    ret = fail_metadata();
    if (ret) {
        trans->block_rsv = block_rsv;
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.residuals == ()
    assert any(
        effect.snapshot_relation is not None
        and effect.snapshot_relation.snapshot_root == "block_rsv"
        for effect in residual_slice.cancellations
    )


def test_success_only_callee_effect_is_absent_from_failure_partition(tmp_path: Path):
    functions = _frontend_functions(
        tmp_path,
        """
static int update_inode(struct inode *inode)
{
    int ret = fail_metadata();

    if (ret)
        return ret;
    inode->last_trans = 1;
    return 0;
}

int work(struct inode *inode)
{
    int ret = update_inode(inode);

    if (ret)
        return ret;
    return 0;
}
""",
    )

    analyses = {item.function: item for item in analyze_functions(functions)}
    residual_slice = analyses["work"].slicing_result.slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert not any(effect.key == "last_trans" for effect in residual_slice.reaching_effects)


def test_transaction_cancel_before_later_failure_closes_descriptor_fields(
    tmp_path: Path,
):
    function = _legacy_functions(
        tmp_path,
        """
int work(struct xfs_trans *tp, struct context *ctx)
{
    int ret;

    tp->owner = ctx;
    xfs_trans_cancel(tp);
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state in {ResidualState.CLOSED, ResidualState.PROTECTED}
    assert residual_slice.residuals == ()


def test_entropy_derived_progress_state_is_out_of_scope(tmp_path: Path):
    function = _legacy_functions(
        tmp_path,
        """
int work(struct f2fs_sb_info *sbi)
{
    int ret;

    sbi->fragment_remained_chunk = get_random_u32_below(16);
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
    assert len(residual_slice.out_of_scope_effects) == 1
    assert residual_slice.out_of_scope_effects[0].semantic_provenance[0].kind is (
        EffectProvenanceKind.PROGRESS_CURSOR
    )


def test_non_dirty_transaction_cancel_is_review_not_candidate(tmp_path: Path):
    function = _legacy_functions(
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
    report = residual_report(
        function=function.name,
        residual_slice=residual_slice,
        scope_rationale="focused semantic test",
    )

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.containment_proofs == ()
    assert "conditional_shutdown_review:ip" in residual_slice.semantic_blockers
    assert report.kind is ReportKind.METADATA_RESIDUAL_REVIEW


def test_non_dirty_transaction_review_survives_analysis_refinement(tmp_path: Path):
    functions = _frontend_functions(
        tmp_path,
        """
void xfs_trans_cancel(struct xfs_trans *tp)
{
    bool dirty = tp->t_flags & XFS_TRANS_DIRTY;

    xfs_trans_free_items(tp, dirty);
    xfs_trans_free(tp);
}

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
    )

    analysis = next(
        item for item in analyze_functions(functions) if item.function == "work"
    )
    residual_slice = analysis.slicing_result.slices[0]

    assert "conditional_shutdown_review:ip" in residual_slice.semantic_blockers
    assert analysis.reports[0].report.kind is ReportKind.METADATA_RESIDUAL_REVIEW


def test_scalar_cast_is_not_an_indirect_call_unknown(tmp_path: Path):
    function = _legacy_functions(
        tmp_path,
        """
static void work(u64 *bytes, unsigned long found_bits, u64 unit)
{
    *bytes = (u64)(found_bits) * unit;
}
""",
    )[0]

    summary = build_same_file_summaries((function,))["work"]

    assert not any("indirect_call" in cause for cause in summary.unknown_causes)


def test_unbound_local_cleanup_does_not_block_unrelated_residual(tmp_path: Path):
    cleanup, work = _legacy_functions(
        tmp_path,
        """
static void cleanup_local(long nr)
{
    struct inode *other;
    other->i_blocks -= nr;
}

int work(struct root *root, long nr)
{
    int ret;

    root->reloc_root = root;
    cleanup_local(nr);
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((cleanup, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert [effect.key for effect in residual_slice.residuals] == ["reloc_root"]
