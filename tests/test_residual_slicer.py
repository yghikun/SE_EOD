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
    assert residual_slice.out_of_scope_effects
    assert (
        residual_slice.out_of_scope_effects[0].semantic_provenance[0].kind.value
        == "PRIVATE_OWNER"
    )


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


def test_error_path_transaction_abort_does_not_contain_value_related_effect(
    tmp_path: Path,
):
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

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.residuals
    assert residual_slice.containment_proofs == ()


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

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.residuals[0].key == "last_trans"
    assert "remain after error-path normalization" in residual_slice.rationale
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


def test_whole_owner_teardown_closes_fresh_unpublished_summary_effect(tmp_path: Path):
    init_obj, work = _functions(
        tmp_path,
        """
static void init_obj(struct fs_object *obj)
{
    obj->inode_flags = 1;
}

int work(void)
{
    struct fs_object *obj = kzalloc(sizeof(*obj), GFP_KERNEL);
    int ret;

    init_obj(obj);
    ret = fail_metadata();
    if (ret)
        goto out;
    return 0;
out:
    kfree(obj);
    return ret;
}
""",
    )
    summaries = build_same_file_summaries((init_obj, work))
    assert [effect.key for effect in summaries["init_obj"].opens] == ["inode_flags"]

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert residual_slice.residuals == ()
    assert len(residual_slice.owner_teardown_proofs) == 1
    proof = residual_slice.owner_teardown_proofs[0]
    assert proof.owner == "obj"
    assert proof.deallocator == "kfree"
    assert proof.allocation_site is not None
    assert [effect.key for effect in proof.closed_effects] == ["inode_flags"]


def test_source_visible_teardown_wrapper_closes_same_fresh_owner(tmp_path: Path):
    init_obj, destroy_obj, work = _functions(
        tmp_path,
        """
static void init_obj(struct fs_object *obj)
{
    obj->inode_flags = 1;
}

static void destroy_obj(struct fs_object *obj)
{
    kfree(obj);
}

int work(void)
{
    struct fs_object *obj = kzalloc(sizeof(*obj), GFP_KERNEL);
    int ret;

    init_obj(obj);
    ret = fail_metadata();
    if (ret)
        goto out;
    return 0;
out:
    destroy_obj(obj);
    return ret;
}
""",
    )
    summaries = build_same_file_summaries((init_obj, destroy_obj, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.CLOSED
    assert len(residual_slice.owner_teardown_proofs) == 1
    proof = residual_slice.owner_teardown_proofs[0]
    assert proof.owner == "obj"
    assert proof.via_function == "destroy_obj"
    assert proof.deallocator == "kfree"


def test_conditional_owner_teardown_cannot_close_effect(tmp_path: Path):
    init_obj, work = _functions(
        tmp_path,
        """
static void init_obj(struct fs_object *obj)
{
    obj->inode_flags = 1;
}

int work(bool cleanup)
{
    struct fs_object *obj = kzalloc(sizeof(*obj), GFP_KERNEL);
    int ret;

    init_obj(obj);
    ret = fail_metadata();
    if (ret) {
        if (cleanup)
            kfree(obj);
        return ret;
    }
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((init_obj, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert [effect.key for effect in residual_slice.residuals] == ["inode_flags"]
    assert residual_slice.owner_teardown_proofs == ()


def test_published_owner_teardown_cannot_close_embedded_effect(tmp_path: Path):
    init_obj, work = _functions(
        tmp_path,
        """
static void init_obj(struct fs_object *obj)
{
    obj->inode_flags = 1;
}

int work(struct fs_holder *holder)
{
    struct fs_object *obj = kzalloc(sizeof(*obj), GFP_KERNEL);
    int ret;

    init_obj(obj);
    holder->inode = obj;
    ret = fail_metadata();
    if (ret) {
        kfree(obj);
        return ret;
    }
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((init_obj, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert any(effect.key == "inode_flags" for effect in residual_slice.residuals)
    assert residual_slice.owner_teardown_proofs == ()


def test_escaped_owner_teardown_cannot_close_embedded_effect(tmp_path: Path):
    init_obj, work = _functions(
        tmp_path,
        """
static void init_obj(struct fs_object *obj)
{
    obj->inode_flags = 1;
}

int work(void)
{
    struct fs_object *obj = kzalloc(sizeof(*obj), GFP_KERNEL);
    int ret;

    init_obj(obj);
    opaque_consumer(obj);
    ret = fail_metadata();
    if (ret) {
        kfree(obj);
        return ret;
    }
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((init_obj, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.residuals
    assert residual_slice.owner_teardown_proofs == ()


def test_owner_teardown_does_not_close_container_membership(tmp_path: Path):
    link_external, work = _functions(
        tmp_path,
        """
static void link_external(
    struct fs_object *obj,
    struct external_object *external)
{
    list_add(&external->link, &obj->children);
}

int work(struct external_object *external)
{
    struct fs_object *obj = kzalloc(sizeof(*obj), GFP_KERNEL);
    int ret;

    link_external(obj, external);
    ret = fail_metadata();
    if (ret) {
        kfree(obj);
        return ret;
    }
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((link_external, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert any(effect.key == "list_membership" for effect in residual_slice.residuals)
    assert residual_slice.owner_teardown_proofs == ()


def test_teardown_of_nonfresh_parameter_cannot_close_effect(tmp_path: Path):
    init_obj, work = _functions(
        tmp_path,
        """
static void init_obj(struct fs_object *obj)
{
    obj->inode_flags = 1;
}

int work(struct fs_object *obj)
{
    int ret;

    init_obj(obj);
    ret = fail_metadata();
    if (ret) {
        kfree(obj);
        return ret;
    }
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((init_obj, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert [effect.key for effect in residual_slice.residuals] == ["inode_flags"]
    assert residual_slice.owner_teardown_proofs == ()


def test_rebound_fresh_local_cannot_use_original_allocation_as_owner_proof(
    tmp_path: Path,
):
    init_obj, work = _functions(
        tmp_path,
        """
static void init_obj(struct fs_object *obj)
{
    obj->inode_flags = 1;
}

int work(void)
{
    struct fs_object *obj = kzalloc(sizeof(*obj), GFP_KERNEL);
    int ret;

    obj = lookup_existing_object();
    init_obj(obj);
    ret = fail_metadata();
    if (ret) {
        kfree(obj);
        return ret;
    }
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((init_obj, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert residual_slice.residuals
    assert residual_slice.owner_teardown_proofs == ()


def test_teardown_wrapper_on_owner_field_cannot_destroy_parent_owner(tmp_path: Path):
    init_holder, destroy_obj, work = _functions(
        tmp_path,
        """
static void init_holder(struct fs_holder *holder)
{
    holder->inode_flags = 1;
}

static void destroy_obj(struct fs_object *obj)
{
    kfree(obj);
}

int work(void)
{
    struct fs_holder *holder = kzalloc(sizeof(*holder), GFP_KERNEL);
    int ret;

    init_holder(holder);
    ret = fail_metadata();
    if (ret) {
        destroy_obj(holder->child);
        return ret;
    }
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((init_holder, destroy_obj, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert [effect.key for effect in residual_slice.residuals] == ["inode_flags"]
    assert residual_slice.owner_teardown_proofs == ()


def test_destroy_named_noop_helper_is_not_owner_teardown(tmp_path: Path):
    init_obj, destroy_obj, work = _functions(
        tmp_path,
        """
static void init_obj(struct fs_object *obj)
{
    obj->inode_flags = 1;
}

static void destroy_obj(struct fs_object *obj)
{
}

int work(void)
{
    struct fs_object *obj = kzalloc(sizeof(*obj), GFP_KERNEL);
    int ret;

    init_obj(obj);
    ret = fail_metadata();
    if (ret) {
        destroy_obj(obj);
        return ret;
    }
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((init_obj, destroy_obj, work))

    residual_slice = slice_function_residuals(work, summaries=summaries).slices[0]

    assert [effect.key for effect in residual_slice.residuals] == ["inode_flags"]
    assert residual_slice.owner_teardown_proofs == ()


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


def test_exact_error_partition_selects_only_terminal_eio_exit(tmp_path: Path):
    helper, eio_caller, enomem_caller = _functions(
        tmp_path,
        """
static int helper(struct fs *fs, int which)
{
    fs->dirty = 1;
    if (which) {
        f2fs_stop_checkpoint(fs, false, REASON);
        return -EIO;
    }
    return -ENOMEM;
}

int eio_caller(struct fs *fs, int which)
{
    int ret = helper(fs, which);

    if (ret == -EIO)
        return ret;
    return 0;
}

int enomem_caller(struct fs *fs, int which)
{
    int ret = helper(fs, which);

    if (ret == -ENOMEM)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((helper, eio_caller, enomem_caller))

    eio_slice = slice_function_residuals(eio_caller, summaries=summaries).slices[0]
    enomem_slice = slice_function_residuals(enomem_caller, summaries=summaries).slices[0]

    assert eio_slice.state is ResidualState.EXPOSED
    assert any(effect.key.startswith("failure_domain:") for effect in eio_slice.protections)
    assert enomem_slice.state is not ResidualState.CONTAINED
    assert not any(
        effect.key.startswith("failure_domain:")
        for effect in enomem_slice.protections
    )


def test_exact_return_code_keeps_direct_residual_and_identity_diagnostic(tmp_path: Path):
    (caller,) = _functions(
        tmp_path,
        """
int caller(struct fs *fs)
{
    int ret;

    fs->dirty = 1;
    ret = fail_metadata();
    if (ret == -EIO)
        return ret;
    return 0;
}
""",
    )

    residual_slice = slice_function_residuals(caller).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED
    assert residual_slice.residuals
    assert (
        "exact_return_code_residual_identity_unproven"
        in residual_slice.semantic_blockers
    )


def test_exact_ptr_err_partition_selects_err_ptr_exit(tmp_path: Path):
    helper, caller = _functions(
        tmp_path,
        """
static struct page *helper(struct fs *fs, int which)
{
    fs->dirty = 1;
    if (which) {
        f2fs_stop_checkpoint(fs, false, REASON);
        return ERR_PTR(-EIO);
    }
    return ERR_PTR(-ENOMEM);
}

int caller(struct fs *fs, int which)
{
    struct page *page = helper(fs, which);

    if (PTR_ERR(page) == -EIO)
        return -EIO;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((helper, caller))

    residual_slice = slice_function_residuals(caller, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED


def test_exact_switch_case_selects_one_error_partition(tmp_path: Path):
    helper, caller = _functions(
        tmp_path,
        """
static int helper(struct fs *fs, int which)
{
    fs->dirty = 1;
    if (which) {
        f2fs_stop_checkpoint(fs, false, REASON);
        return -EIO;
    }
    return -ENOMEM;
}

int caller(struct fs *fs, int which)
{
    int ret = helper(fs, which);

    switch (ret) {
    case -EIO:
        return ret;
    default:
        return 0;
    }
}
""",
    )
    summaries = build_same_file_summaries((helper, caller))

    residual_slice = slice_function_residuals(caller, summaries=summaries).slices[0]

    assert residual_slice.state is ResidualState.EXPOSED


def test_symbolic_error_partition_prevents_exact_selection(tmp_path: Path):
    helper, caller = _functions(
        tmp_path,
        """
static int helper(struct fs *fs, int which)
{
    int ret;

    fs->dirty = 1;
    if (which) {
        f2fs_stop_checkpoint(fs, false, REASON);
        return -EIO;
    }
    ret = fallback_error();
    if (ret)
        return ret;
    return 0;
}

int caller(struct fs *fs, int which)
{
    int ret = helper(fs, which);

    if (ret == -EIO)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((helper, caller))

    residual_slice = slice_function_residuals(caller, summaries=summaries).slices[0]

    assert residual_slice.state is not ResidualState.CONTAINED
    assert not any(
        effect.key.startswith("failure_domain:")
        for effect in residual_slice.protections
    )


def test_duplicate_matching_error_partitions_prevent_exact_selection(tmp_path: Path):
    helper, caller = _functions(
        tmp_path,
        """
static int helper(struct fs *fs, int which)
{
    fs->dirty = 1;
    if (which) {
        f2fs_stop_checkpoint(fs, false, REASON);
        return -EIO;
    }
    return -EIO;
}

int caller(struct fs *fs, int which)
{
    int ret = helper(fs, which);

    if (ret == -EIO)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((helper, caller))

    residual_slice = slice_function_residuals(caller, summaries=summaries).slices[0]

    assert residual_slice.state is not ResidualState.CONTAINED
    assert not any(
        effect.key.startswith("failure_domain:")
        for effect in residual_slice.protections
    )


def test_not_equal_with_multiple_matching_partitions_preserves_must_projection(
    tmp_path: Path,
):
    helper, caller = _functions(
        tmp_path,
        """
static int helper(struct fs *fs, int which)
{
    fs->dirty = 1;
    if (which > 0) {
        f2fs_stop_checkpoint(fs, false, REASON);
        return -EIO;
    }
    if (which < 0)
        return -ENOMEM;
    return -EAGAIN;
}

int caller(struct fs *fs, int which)
{
    int ret = helper(fs, which);

    if (ret != -EAGAIN)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((helper, caller))

    residual_slice = slice_function_residuals(caller, summaries=summaries).slices[0]

    assert residual_slice.state is not ResidualState.CONTAINED
    assert not any(
        effect.key.startswith("failure_domain:")
        for effect in residual_slice.protections
    )


def test_nonexact_failure_check_keeps_existing_common_must_effect(tmp_path: Path):
    helper, caller = _functions(
        tmp_path,
        """
static int helper(struct fs *fs, int which)
{
    fs->dirty = 1;
    if (which) {
        f2fs_stop_checkpoint(fs, false, REASON);
        return -EIO;
    }
    return -ENOMEM;
}

int caller(struct fs *fs, int which)
{
    int ret = helper(fs, which);

    if (ret)
        return ret;
    return 0;
}
""",
    )
    summaries = build_same_file_summaries((helper, caller))

    residual_slice = slice_function_residuals(caller, summaries=summaries).slices[0]

    assert residual_slice.state is not ResidualState.CONTAINED
    assert not any(
        effect.key.startswith("failure_domain:")
        for effect in residual_slice.protections
    )
