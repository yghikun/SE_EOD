from pathlib import Path

from src.function_extractor import extract_functions
from src.function_summary import build_project_summaries, build_same_file_summaries
from src.metadata_residual import MetadataDelta, ResidualState
from src.parser import parse_c_file
from src.residual_slicer import slice_function_residuals


def _functions(tmp_path: Path, source: str):
    path = tmp_path / "slice.c"
    path.write_text(source, encoding="utf-8")
    return extract_functions(parse_c_file(path))


def test_mutation_failure_return_error_leaves_residual(tmp_path: Path):
    function = _functions(
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
    )[0]

    result = slice_function_residuals(function)

    assert len(result.slices) == 1
    residual_slice = result.slices[0]
    assert residual_slice.state is ResidualState.EXPOSED
    assert len(residual_slice.reaching_effects) == 1
    assert len(residual_slice.residuals) == 1
    assert residual_slice.residuals[0].site.expression == "inode->i_blocks += nr"


def test_failure_call_name_guess_is_not_a_reaching_effect(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct trans *trans)
{
    int ret;

    ret = btrfs_commit_transaction(trans);
    if (ret)
        return ret;
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.reaching_effects == ()


def test_unpublished_fresh_local_initialization_is_not_a_residual(tmp_path: Path):
    allocator, initializer = _functions(
        tmp_path,
        """
static struct device *alloc_device(void)
{
    struct device *device = kzalloc(sizeof(*device), GFP_KERNEL);

    return device;
}

static int init_device(struct fs_info *fs_info, struct device **device_out)
{
    struct device *device = alloc_device();
    int ret;

    if (!device)
        return -ENOMEM;
    device->ready = 1;
    ret = fail_metadata();
    if (ret)
        return ret;
    *device_out = device;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((allocator, initializer))

    residual_slice = slice_function_residuals(initializer, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.reaching_effects == ()


def test_published_fresh_local_initialization_remains_reaching(tmp_path: Path):
    allocator, initializer = _functions(
        tmp_path,
        """
static struct device *alloc_device(void)
{
    struct device *device = kzalloc(sizeof(*device), GFP_KERNEL);

    return device;
}

static int init_device(struct fs_info *fs_info, struct device **device_out)
{
    struct device *device = alloc_device();
    int ret;

    if (!device)
        return -ENOMEM;
    device->ready = 1;
    *device_out = device;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((allocator, initializer))

    residual_slice = slice_function_residuals(initializer, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.reaching_effects[0].site.expression == "device->ready = 1"


def test_caller_structural_binding_exposes_fresh_local_before_output(tmp_path: Path):
    allocator, initializer = _functions(
        tmp_path,
        """
static struct device *alloc_device(void)
{
    struct device *device = kzalloc(sizeof(*device), GFP_KERNEL);

    return device;
}

static int init_device(struct fs_info *fs_info, struct device **device_out)
{
    struct device *device = alloc_device();
    int ret;

    if (!device)
        return -ENOMEM;
    device->fs_info = fs_info;
    ret = fail_metadata();
    if (ret)
        return ret;
    *device_out = device;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((allocator, initializer))

    residual_slice = slice_function_residuals(initializer, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.reaching_effects[0].site.expression == "device->fs_info = fs_info"


def test_mutation_failure_compensation_return_error_clears_residual(tmp_path: Path):
    function = _functions(
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
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.residuals == ()
    assert residual_slice.cancellations[0].site.expression.endswith(
        "inode->i_blocks -= nr"
    )


def test_conditional_error_cleanup_is_not_treated_as_must_cancellation(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct inode *inode, long nr, int cleanup)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret)
        goto out;
    return 0;
out:
    if (cleanup)
        inode->i_blocks -= nr;
    return ret;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.UNKNOWN
    assert residual_slice.residuals[0].key == "i_blocks"
    assert "conditional error-path cancellation" in residual_slice.rationale


def test_unrelated_conditional_cleanup_does_not_block_direct_residual(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct inode *inode, struct root *root, long nr, int cleanup)
{
    int ret;

    root->reloc_root = root;
    ret = fail_metadata();
    if (ret) {
        if (cleanup)
            inode->i_blocks -= nr;
        return ret;
    }
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.residuals[0].key == "reloc_root"


def test_transaction_protect_with_explicit_binding_protects_residual(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct trans *trans, struct root *root)
{
    int ret;

    trans->btrfs_record_root_in_trans = root;
    btrfs_record_root_in_trans(trans, root);
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.PROTECTED
    assert residual_slice.residuals == ()
    assert len(residual_slice.protections) == 1


def test_error_path_transaction_abort_protects_transaction_bound_effect(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct trans *trans, struct root *root)
{
    int ret;

    root->last_trans = trans->transid;
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

    assert residual_slice.state is ResidualState.PROTECTED
    assert residual_slice.residuals == ()
    assert any(
        "btrfs_abort_transaction" in effect.site.expression
        for effect in residual_slice.protections
    )


def test_conditional_error_path_protection_is_not_treated_as_must_protection(
    tmp_path: Path,
):
    function = _functions(
        tmp_path,
        """
int work(struct trans *trans, struct root *root, int abort)
{
    int ret;

    root->last_trans = trans->transid;
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
    assert residual_slice.residuals[0].key == "last_trans"
    assert "conditional error-path cancellation/protection" in residual_slice.rationale
    assert residual_slice.protections == ()


def test_error_path_transaction_abort_does_not_protect_unbound_effect(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct trans *trans, struct inode *inode)
{
    int ret;

    inode->i_blocks++;
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
    assert len(residual_slice.residuals) == 1


def test_unknown_helper_on_error_path_yields_unknown(tmp_path: Path):
    function = _functions(
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
    )[0]

    result = slice_function_residuals(function)
    residual_slice = result.slices[0]

    assert residual_slice.state is ResidualState.UNKNOWN
    assert "unresolved metadata helper" in residual_slice.rationale
    assert result.unknown_causes


def test_unknown_error_path_helper_with_different_argument_remains_conservative(
    tmp_path: Path,
):
    function = _functions(
        tmp_path,
        """
int work(struct inode *inode, struct root *root, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret)
        goto out;
    return 0;
out:
    btrfs_unknown_root_cleanup(root);
    return ret;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.UNKNOWN
    assert "btrfs_unknown_root_cleanup" in residual_slice.rationale


def test_reaching_unknown_cannot_cancel_later_direct_effect(tmp_path: Path):
    helper, work = _functions(
        tmp_path,
        """
static void prepare_async(struct root *root, void (*callback)(void *))
{
    callback(root);
}

int work(struct root *root, void (*callback)(void *))
{
    int ret;

    prepare_async(root, callback);
    root->reloc_root = root;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((helper, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.residuals[0].key == "reloc_root"


def test_failure_value_prunes_success_only_unknown_cleanup(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct root *root)
{
    int ret;

    root->reloc_root = root;
    ret = fail_metadata();
    if (ret)
        goto out;
    return 0;
out:
    if (ret == 0)
        btrfs_unknown_root_cleanup(root);
    return ret;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.residuals[0].key == "reloc_root"


def test_known_error_path_effect_call_does_not_also_yield_unknown(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct trans *trans, struct inode *inode, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret)
        goto out;
    return 0;
out:
    btrfs_end_transaction(trans);
    return ret;
}
""",
    )[0]

    result = slice_function_residuals(function)
    residual_slice = result.slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert result.unknown_causes == ()
    assert any(
        effect.site.expression == "btrfs_end_transaction(trans)"
        for effect in residual_slice.cancellations
    )


def test_metadata_accessor_on_error_path_does_not_create_unknown(tmp_path: Path):
    function = _functions(
        tmp_path,
        """
int work(struct root *root)
{
    int ret;

    root->reloc_root = root;
    ret = fail_metadata();
    if (ret)
        goto out;
    return 0;
out:
    btrfs_root_id(root);
    return ret;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.residuals


def test_mutating_count_helper_on_error_path_remains_unknown(tmp_path: Path):
    function = _functions(
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
    inode_dec_link_count(inode);
    return ret;
}
""",
    )[0]

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.UNKNOWN
    assert "inode_dec_link_count" in residual_slice.rationale




def test_source_proven_noop_error_path_helper_does_not_yield_unknown(tmp_path: Path):
    helper, work = _functions(
        tmp_path,
        """
void btrfs_new_inode_args_destroy(struct btrfs_new_inode_args *args)
{
    posix_acl_release(args->acl);
    fscrypt_free_filename(&args->fname);
}

int work(struct inode *inode, struct btrfs_new_inode_args *args, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = fail_metadata();
    if (ret)
        goto out;
    return 0;
out:
    btrfs_new_inode_args_destroy(args);
    return ret;
}
""",
    )
    summaries = build_project_summaries((helper, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert "btrfs_new_inode_args_destroy" not in residual_slice.rationale


def test_same_file_helper_summary_opens_and_cancels_effects(tmp_path: Path):
    charge, uncharge, work = _functions(
        tmp_path,
        """
static void charge_inode(struct inode *inode, long nr)
{
    inode->i_blocks += nr;
}

static void uncharge_inode(struct inode *inode, long nr)
{
    inode->i_blocks -= nr;
}

int work(struct inode *inode, long nr)
{
    int ret;

    charge_inode(inode, nr);
    ret = fail_metadata();
    if (ret)
        goto out;
    return 0;
out:
    uncharge_inode(inode, nr);
    return ret;
}
""",
    )
    summaries = build_same_file_summaries((charge, uncharge, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.reaching_effects[0].site.expression.endswith(
        "inode->i_blocks += nr"
    )
    assert residual_slice.cancellations[0].site.expression.endswith(
        "inode->i_blocks -= nr"
    )


def test_exhaustive_container_cleanup_survives_summary_call_site_projection(
    tmp_path: Path,
):
    drain, work = _functions(
        tmp_path,
        """
static void drain(struct fs_devices *fs_devices)
{
    struct device *curr;
    struct device *next;

    list_for_each_entry_safe(curr, next, &fs_devices->devices, dev_list) {
        list_del(&curr->dev_list);
        kfree(curr);
    }
}

int work(struct fs_devices *fs_devices, struct device *first, struct device *second)
{
    int ret;

    list_add(&first->dev_list, &fs_devices->devices);
    list_add(&second->dev_list, &fs_devices->devices);
    ret = fail_metadata();
    if (ret)
        goto out;
    return 0;
out:
    drain(fs_devices);
    return ret;
}
""",
    )
    summaries = build_same_file_summaries((drain, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert len(residual_slice.reaching_effects) == 2
    cleanup = next(
        effect
        for effect in residual_slice.cancellations
        if effect.container_iteration_cleanup is not None
    )
    assert cleanup.root == "fs_devices->devices"
    assert cleanup.container_iteration_cleanup.container_root == "fs_devices->devices"


def test_summary_effect_on_caller_stack_output_is_out_of_scope(tmp_path: Path):
    helper, work = _functions(
        tmp_path,
        """
static void get_info(struct inode_info *info, struct inode *inode)
{
    info->nlink = inode->i_nlink;
}

int work(struct inode *inode)
{
    struct inode_info info;
    int ret;

    get_info(&info, inode);
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((helper, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.reaching_effects == ()


def test_return_value_summary_binds_helper_effect_to_caller_lvalue(tmp_path: Path):
    helper, work = _functions(
        tmp_path,
        """
static struct dev *make_dev(void)
{
    struct dev *dev;

    dev->ready = 1;
    return dev;
}

int work(void)
{
    struct dev *dev;
    int ret;

    dev = make_dev();
    ret = fail_metadata();
    if (ret)
        goto out;
    return 0;
out:
    dev->ready = 0;
    return ret;
}
""",
    )
    summaries = build_same_file_summaries((helper, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.reaching_effects[0].site.expression.endswith("dev->ready = 1")
    assert residual_slice.cancellations[0].site.expression == "dev->ready = 0"


def test_fresh_transfer_summary_reaches_later_failure(tmp_path: Path):
    helper, work = _functions(
        tmp_path,
        """
static int attach_device(struct fs_devices *fs_devices)
{
    struct device *device = kzalloc(sizeof(*device), GFP_KERNEL);

    if (!device)
        return -ENOMEM;
    list_add(&device->dev_list, &fs_devices->devices);
    fs_devices->num_devices++;
    return 0;
}

int work(struct fs_devices *fs_devices)
{
    int ret;

    ret = attach_device(fs_devices);
    if (ret)
        return ret;
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((helper, work))

    slices = slice_function_residuals(work, summaries=summaries).slices

    assert slices[0].state is ResidualState.CLOSED
    assert "callee_failure_effect_order_unknown" not in slices[0].rationale
    assert slices[1].state is ResidualState.EXPOSED
    assert any(effect.key == "list_membership" for effect in slices[1].residuals)
    assert any(effect.key == "num_devices" for effect in slices[1].residuals)


def test_failure_summary_keeps_pre_failure_effect(tmp_path: Path):
    helper, work = _functions(
        tmp_path,
        """
static int charge_then_fail(struct inode *inode, long nr)
{
    int ret;

    inode->i_blocks += nr;
    ret = reserve_blocks();
    if (ret)
        return ret;
    return 0;
}

int work(struct inode *inode, long nr)
{
    int ret;

    ret = charge_then_fail(inode, nr);
    if (ret)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((helper, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.residuals[0].site.expression.endswith("inode->i_blocks += nr")


def test_failure_summary_does_not_apply_may_cleanup(tmp_path: Path):
    helper, work = _functions(
        tmp_path,
        """
static int charge_then_maybe_cleanup(
    struct inode *inode,
    long nr,
    int cleanup)
{
    int ret;

    inode->i_blocks += nr;
    ret = reserve_blocks();
    if (ret) {
        if (cleanup)
            inode->i_blocks -= nr;
        return ret;
    }
    return 0;
}

int work(struct inode *inode, long nr, int cleanup)
{
    int ret;

    ret = charge_then_maybe_cleanup(inode, nr, cleanup);
    if (ret)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((helper, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.residuals[0].site.expression.endswith("inode->i_blocks += nr")
    assert residual_slice.cancellations == ()


def test_failure_summary_drops_unexposed_fresh_local_fields(tmp_path: Path):
    helper, work = _functions(
        tmp_path,
        """
static int create_space_info(struct fs_info *fs_info)
{
    struct space_info *space_info = kzalloc(sizeof(*space_info), GFP_NOFS);
    int ret;

    space_info->flags = 1;
    ret = fail_sysfs();
    if (ret)
        return ret;
    list_add(&space_info->list, &fs_info->space_info);
    return 0;
}

int work(struct fs_info *fs_info)
{
    int ret;

    ret = create_space_info(fs_info);
    if (ret)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((helper, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.reaching_effects == ()


def test_fresh_transfer_identity_is_unique_per_ast_call_site(tmp_path: Path):
    helper, work = _functions(
        tmp_path,
        """
static void attach_device(struct fs_devices *fs_devices)
{
    struct device *device = kzalloc(sizeof(*device), GFP_KERNEL);

    list_add(&device->dev_list, &fs_devices->devices);
}

int work(struct fs_devices *fs_devices)
{
    int ret;

    attach_device(fs_devices);
    attach_device(fs_devices);
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((helper, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]
    values = [
        effect.value
        for effect in residual_slice.reaching_effects
        if effect.key == "list_membership"
    ]

    assert len(values) == 2
    assert values[0] != values[1]


def test_fresh_transfer_to_caller_local_list_is_out_of_scope(tmp_path: Path):
    allocator, helper, work = _functions(
        tmp_path,
        """
static struct item *alloc_item(void)
{
    struct item *item = kzalloc(sizeof(*item), GFP_KERNEL);

    return item;
}

static void append_item(struct list_head *list)
{
    struct item *item = alloc_item();

    list_add_tail(&item->list, list);
}

int work(void)
{
    LIST_HEAD(temporary_items);
    int ret;

    append_item(&temporary_items);
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((allocator, helper, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.reaching_effects == ()


def test_same_file_unknown_summary_escape_yields_unknown(tmp_path: Path):
    helper, work = _functions(
        tmp_path,
        """
static void charge_async(struct inode *inode, long nr, void (*callback)(void *))
{
    inode->i_blocks += nr;
    callback(inode);
}

int work(struct inode *inode, long nr, void (*callback)(void *))
{
    int ret;

    charge_async(inode, nr, callback);
    ret = fail_metadata();
    if (ret)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((helper, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.UNKNOWN
    assert "function_pointer_parameter_call: callback" in residual_slice.rationale


def test_aggregate_snapshot_restore_cancels_macro_aliased_field_set(tmp_path: Path):
    (function,) = _functions(
        tmp_path,
        """
#define OPTION(state) ((state)->mount_opt)
struct mount_opts { int alloc_mode; int other; };
struct state { struct mount_opts mount_opt; };
int work(struct state *state)
{
    struct mount_opts saved;
    int ret;

    saved = state->mount_opt;
    OPTION(state).alloc_mode = 1;
    OPTION(state).alloc_mode = 2;
    ret = fail_metadata();
    if (ret)
        goto restore;
    return 0;
restore:
    state->mount_opt = saved;
    return ret;
}
""",
    )

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.residuals == ()
    restores = [
        effect
        for effect in residual_slice.cancellations
        if effect.delta is MetadataDelta.RESTORE
    ]
    assert len(restores) == 1
    restore = restores[0]
    assert restore.snapshot_relation is not None
    assert restore.snapshot_relation.snapshot_root == "saved"
    assert restore.snapshot_relation.owner_root == "state"
    assert restore.snapshot_relation.aggregate_key == "mount_opt"
    assert restore.snapshot_relation.source_identity == "state->mount_opt"


def test_aggregate_snapshot_restore_rejects_mutated_target_field(tmp_path: Path):
    (function,) = _functions(
        tmp_path,
        """
struct mount_opts { int alloc_mode; };
struct state { struct mount_opts mount_opt; };
int work(struct state *state)
{
    struct mount_opts saved;
    int ret;

    saved = state->mount_opt;
    state->mount_opt.alloc_mode = 1;
    saved.alloc_mode = 2;
    ret = fail_metadata();
    if (ret)
        goto restore;
    return 0;
restore:
    state->mount_opt = saved;
    return ret;
}
""",
    )

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert not any(effect.delta is MetadataDelta.RESTORE for effect in residual_slice.cancellations)


def test_aggregate_snapshot_restore_rejects_conditional_restore_and_snapshot_escape(tmp_path: Path):
    conditional, escaped = _functions(
        tmp_path,
        """
struct mount_opts { int alloc_mode; };
struct state { struct mount_opts mount_opt; };
int conditional(struct state *state, int choose)
{
    struct mount_opts saved;
    int ret;

    saved = state->mount_opt;
    state->mount_opt.alloc_mode = 1;
    ret = fail_metadata();
    if (ret && choose)
        goto restore;
    if (ret)
        return ret;
    return 0;
restore:
    state->mount_opt = saved;
    return ret;
}

int escaped(struct state *state)
{
    struct mount_opts saved;
    struct mount_opts *alias;
    int ret;

    saved = state->mount_opt;
    state->mount_opt.alloc_mode = 1;
    alias = &saved;
    inspect(alias);
    ret = fail_metadata();
    if (ret)
        goto restore;
    return 0;
restore:
    state->mount_opt = saved;
    return ret;
}
""",
    )

    for function in (conditional, escaped):
        residual_slice = slice_function_residuals(function).slices[0]
        assert residual_slice.residuals
        assert not any(
            effect.delta is MetadataDelta.RESTORE
            for effect in residual_slice.cancellations
        )


def test_aggregate_snapshot_restore_rejects_late_capture_different_owner_and_partial_restore(
    tmp_path: Path,
):
    late_capture, different_owner, partial_restore = _functions(
        tmp_path,
        """
struct mount_opts { int alloc_mode; };
struct state { struct mount_opts mount_opt; };
int late_capture(struct state *state)
{
    struct mount_opts saved;
    int ret;

    state->mount_opt.alloc_mode = 1;
    saved = state->mount_opt;
    ret = fail_metadata();
    if (ret)
        goto restore;
    return 0;
restore:
    state->mount_opt = saved;
    return ret;
}

int different_owner(struct state *left, struct state *right)
{
    struct mount_opts saved;
    int ret;

    saved = left->mount_opt;
    left->mount_opt.alloc_mode = 1;
    ret = fail_metadata();
    if (ret)
        goto restore;
    return 0;
restore:
    right->mount_opt = saved;
    return ret;
}

int partial_restore(struct state *state)
{
    struct mount_opts saved;
    int ret;

    saved = state->mount_opt;
    state->mount_opt.alloc_mode = 1;
    ret = fail_metadata();
    if (ret)
        goto restore;
    return 0;
restore:
    state->mount_opt.alloc_mode = saved.alloc_mode;
    return ret;
}
""",
    )

    for function in (late_capture, different_owner, partial_restore):
        residual_slice = slice_function_residuals(function).slices[0]
        assert residual_slice.residuals
        assert not any(
            effect.delta is MetadataDelta.RESTORE
            for effect in residual_slice.cancellations
        )


def test_aggregate_snapshot_restore_requires_capture_to_dominate_mutation(tmp_path: Path):
    (function,) = _functions(
        tmp_path,
        """
struct mount_opts { int alloc_mode; };
struct state { struct mount_opts mount_opt; };
int work(struct state *state, int capture)
{
    struct mount_opts saved;
    int ret;

    if (capture)
        saved = state->mount_opt;
    state->mount_opt.alloc_mode = 1;
    ret = fail_metadata();
    if (ret)
        goto restore;
    return 0;
restore:
    state->mount_opt = saved;
    return ret;
}
""",
    )

    residual_slice = slice_function_residuals(function).slices[0]

    assert residual_slice.residuals
    assert not any(
        effect.delta is MetadataDelta.RESTORE
        for effect in residual_slice.cancellations
    )
