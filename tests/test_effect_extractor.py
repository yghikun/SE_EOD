from pathlib import Path

from src.effect_extractor import (
    extract_metadata_effects,
    extract_metadata_effects_with_skips,
)
from src.function_extractor import extract_functions
from src.metadata_residual import MetadataDelta, MetadataPlane
from src.parser import parse_c_file


def _function(tmp_path: Path, source: str):
    path = tmp_path / "effects.c"
    path.write_text(source, encoding="utf-8")
    return extract_functions(parse_c_file(path))[0]


def _effect_by_expr(effects, expression: str):
    return next(effect for effect in effects if effect.site.expression == expression)


def test_extracts_accounting_field_increment_and_decrement(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct inode *inode, long nr)
{
    inode->i_blocks += nr;
    inode->i_blocks -= nr;
}
""",
    )

    effects = extract_metadata_effects(function)

    inc = _effect_by_expr(effects, "inode->i_blocks += nr")
    dec = _effect_by_expr(effects, "inode->i_blocks -= nr")
    assert (inc.root, inc.key, inc.plane, inc.delta, inc.value) == (
        "inode",
        "i_blocks",
        MetadataPlane.ACCOUNTING,
        MetadataDelta.INC,
        "nr",
    )
    assert (dec.root, dec.key, dec.plane, dec.delta, dec.value) == (
        "inode",
        "i_blocks",
        MetadataPlane.ACCOUNTING,
        MetadataDelta.DEC,
        "nr",
    )


def test_extracts_list_recovery_add_and_remove(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct dev *dev, struct trans *trans)
{
    list_add(&dev->post_commit_list, &trans->dev_update_list);
    list_del_init(&dev->post_commit_list);
}
""",
    )

    effects = extract_metadata_effects(function)

    added = _effect_by_expr(
        effects,
        "list_add(&dev->post_commit_list, &trans->dev_update_list)",
    )
    removed = _effect_by_expr(effects, "list_del_init(&dev->post_commit_list)")
    assert added.plane is MetadataPlane.RECOVERY
    assert added.delta is MetadataDelta.ADD
    assert added.root == "trans->dev_update_list"
    assert added.key == "list_membership"
    assert added.value == "dev->post_commit_list"
    assert removed.plane is MetadataPlane.RECOVERY
    assert removed.delta is MetadataDelta.REMOVE
    assert removed.root == "dev->post_commit_list"


def test_extracts_recovery_pointer_set_and_clear(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct root *fs_root, struct root *reloc_root)
{
    fs_root->reloc_root = reloc_root;
    fs_root->reloc_root = NULL;
}
""",
    )

    effects = extract_metadata_effects(function)

    set_effect = _effect_by_expr(effects, "fs_root->reloc_root = reloc_root")
    clear_effect = _effect_by_expr(effects, "fs_root->reloc_root = NULL")
    assert (set_effect.plane, set_effect.delta, set_effect.value) == (
        MetadataPlane.RECOVERY,
        MetadataDelta.SET,
        "reloc_root",
    )
    assert (clear_effect.plane, clear_effect.delta, clear_effect.value) == (
        MetadataPlane.RECOVERY,
        MetadataDelta.CLEAR,
        "NULL",
    )


def test_ordinary_kfree_is_out_of_scope(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(void *ptr)
{
    kfree(ptr);
}
""",
    )

    result = extract_metadata_effects_with_skips(function)

    assert result.effects == ()
    assert result.skipped_expressions == ("kfree(ptr)",)


def test_temporary_path_field_is_out_of_scope(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct btrfs_path *path)
{
    path->search_commit_root = 1;
}
""",
    )

    assert extract_metadata_effects(function) == ()


def test_local_metadata_alias_is_canonicalized(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct fs_info *fs_info)
{
    struct fs_devices *fs_devices = fs_info->fs_devices;

    fs_devices->num_devices++;
    fs_info->fs_devices->num_devices--;
}
""",
    )

    effects = extract_metadata_effects(function)

    inc = _effect_by_expr(effects, "fs_devices->num_devices++")
    dec = _effect_by_expr(effects, "fs_info->fs_devices->num_devices--")
    assert (inc.root, inc.key, inc.delta) == (
        "fs_info->fs_devices",
        "num_devices",
        MetadataDelta.INC,
    )
    assert (dec.root, dec.key, dec.delta) == (
        "fs_info->fs_devices",
        "num_devices",
        MetadataDelta.DEC,
    )


def test_compound_initializer_is_not_recorded_as_local_alias(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct block_group *block_group)
{
    struct btrfs_key key = {
        .objectid = BTRFS_FREE_SPACE_TREE_OBJECTID,
        .type = BTRFS_ROOT_ITEM_KEY,
        .offset = 0,
    };

    key.offset = block_group->global_root_id;
    return 0;
}
""",
    )

    assert extract_metadata_effects(function) == ()


def test_stack_request_struct_fields_are_out_of_scope(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct inode *inode, u64 bytenr)
{
    struct btrfs_ref ref;

    ref.bytenr = bytenr;
    ref.num_bytes = inode->i_blocks;
    return submit_ref(inode, &ref);
}
""",
    )

    assert extract_metadata_effects(function) == ()


def test_transient_context_output_fields_are_out_of_scope(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct btrfs_drop_extents_args *args,
         struct btrfs_truncate_control *control)
{
    args->bytes_found += 4096;
    control->sub_bytes++;
    return 0;
}
""",
    )

    assert extract_metadata_effects(function) == ()


def test_transient_context_reachable_metadata_object_remains_in_scope(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct request_ctx *ctx, long nr)
{
    ctx->inode->i_blocks += nr;
    return 0;
}
""",
    )

    effect = extract_metadata_effects(function)[0]
    assert (effect.root, effect.key, effect.delta) == (
        "ctx->inode",
        "i_blocks",
        MetadataDelta.INC,
    )


def test_ctl_context_fields_are_out_of_scope_but_persistent_target_remains(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct btrfs_free_space_ctl *ctl, long nr)
{
    ctl->free_extents += nr;
    ctl->persistent_object->i_blocks += nr;
    return 0;
}
""",
    )

    effects = extract_metadata_effects(function)

    assert len(effects) == 1
    assert (effects[0].root, effects[0].key, effects[0].delta) == (
        "ctl->persistent_object",
        "i_blocks",
        MetadataDelta.INC,
    )


def test_vfs_operation_wiring_is_out_of_residual_scope(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct inode *inode, long nr)
{
    inode->i_op = &fs_inode_operations;
    inode->i_fop = &fs_file_operations;
    inode->i_mapping->a_ops = &fs_aops;
    inode->i_mapping = mapping;
    inode->i_blocks += nr;
    return 0;
}
""",
    )

    effects = extract_metadata_effects(function)

    assert len(effects) == 1
    assert (effects[0].root, effects[0].key, effects[0].delta) == (
        "inode",
        "i_blocks",
        MetadataDelta.INC,
    )


def test_explicitly_reused_aggregate_fields_are_out_of_scope(tmp_path: Path):
    function = _function(
        tmp_path,
        """
/* reused for each extent */
struct reusable_extent_cursor {
    struct inode *persistent_inode;
    u64 offset;
};

int work(struct reusable_extent_cursor *cursor, long nr)
{
    cursor->offset += nr;
    cursor->persistent_inode->i_blocks += nr;
    return 0;
}
""",
    )

    effects = extract_metadata_effects(function)

    assert len(effects) == 1
    assert (effects[0].root, effects[0].key, effects[0].delta) == (
        "cursor->persistent_inode",
        "i_blocks",
        MetadataDelta.INC,
    )


def test_unannotated_aggregate_fields_remain_in_scope(tmp_path: Path):
    function = _function(
        tmp_path,
        """
struct persistent_extent_cursor {
    u64 i_blocks;
};

int work(struct persistent_extent_cursor *cursor, long nr)
{
    cursor->i_blocks += nr;
    return 0;
}
""",
    )

    effect = extract_metadata_effects(function)[0]

    assert (effect.root, effect.key, effect.delta) == (
        "cursor",
        "i_blocks",
        MetadataDelta.INC,
    )


def test_temporary_metadata_helper_types_are_out_of_scope(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct btrfs_key *key,
         struct btrfs_path *path,
         struct btrfs_ref *ref,
         struct btrfs_lru_cache_entry *entry,
         struct inode *inode,
         long nr)
{
    key->offset += nr;
    path->slots[0] += nr;
    ref->num_bytes += nr;
    entry->gen += nr;
    inode->i_blocks += nr;
    return 0;
}
""",
    )

    effects = extract_metadata_effects(function)

    assert len(effects) == 1
    assert (effects[0].root, effects[0].key, effects[0].delta) == (
        "inode",
        "i_blocks",
        MetadataDelta.INC,
    )


def test_recovery_control_is_not_treated_as_generic_context(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct btrfs_reloc_control *control)
{
    control->merge_reloc_tree = 1;
    return 0;
}
""",
    )

    effect = extract_metadata_effects(function)[0]
    assert (effect.root, effect.key, effect.plane, effect.delta) == (
        "control",
        "merge_reloc_tree",
        MetadataPlane.RECOVERY,
        MetadataDelta.SET,
    )


def test_heap_allocated_context_fields_are_out_of_scope(tmp_path: Path):
    function = _function(
        tmp_path,
        """
static struct scrub_ctx *setup(int replace)
{
    struct scrub_ctx *sctx;

    sctx = kzalloc(sizeof(*sctx), GFP_KERNEL);
    sctx->is_dev_replace = replace;
    return sctx;
}
""",
    )

    assert extract_metadata_effects(function) == ()


def test_helper_effect_rooted_in_transient_context_is_out_of_scope(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct send_ctx *sctx, u64 ino)
{
    return orphanize_inode(sctx, ino);
}
""",
    )

    assert extract_metadata_effects(function) == ()


def test_metadata_accessor_call_is_not_a_mutating_effect(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct root *root)
{
    return btrfs_root_ctransid(root);
}
""",
    )

    assert extract_metadata_effects(function) == ()


def test_accessor_and_validator_helpers_are_not_guessed_as_mutations(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct fs_info *fs_info, struct root *root, struct inherit *inherit)
{
    if (!btrfs_qgroup_full_accounting(fs_info))
        return 0;
    if (btrfs_get_root_last_trans(root) == 1)
        return 0;
    return btrfs_qgroup_check_inherit(fs_info, inherit, sizeof(*inherit));
}
""",
    )

    assert extract_metadata_effects(function) == ()


def test_extracts_bit_tree_reservation_quota_and_transaction_idioms(tmp_path: Path):
    function = _function(
        tmp_path,
        """
int work(struct dev *dev, struct root *root, struct inode *inode, struct trans *trans)
{
    set_bit(BTRFS_DEV_STATE_IN_FS_METADATA, &dev->dev_state);
    clear_bit(BTRFS_DEV_STATE_IN_FS_METADATA, &dev->dev_state);
    rb_link_node(&inode->rb_node, parent, link);
    xa_erase(&root->ino_cache, ino);
    btrfs_block_rsv_add(root, rsv, num_bytes);
    btrfs_block_rsv_release(root, rsv, num_bytes);
    dquot_reserve_block(inode, nr);
    dquot_release_reservation_block(inode, nr);
    btrfs_record_root_in_trans(trans, root);
    btrfs_end_transaction(trans);
}
""",
    )

    effects = extract_metadata_effects(function)

    assert _effect_by_expr(
        effects,
        "set_bit(BTRFS_DEV_STATE_IN_FS_METADATA, &dev->dev_state)",
    ).delta is MetadataDelta.SET
    assert _effect_by_expr(
        effects,
        "clear_bit(BTRFS_DEV_STATE_IN_FS_METADATA, &dev->dev_state)",
    ).delta is MetadataDelta.CLEAR
    assert _effect_by_expr(
        effects,
        "rb_link_node(&inode->rb_node, parent, link)",
    ).delta is MetadataDelta.ADD
    assert _effect_by_expr(
        effects,
        "xa_erase(&root->ino_cache, ino)",
    ).delta is MetadataDelta.REMOVE
    assert _effect_by_expr(
        effects,
        "btrfs_block_rsv_add(root, rsv, num_bytes)",
    ).delta is MetadataDelta.RESERVE
    assert _effect_by_expr(
        effects,
        "btrfs_block_rsv_release(root, rsv, num_bytes)",
    ).delta is MetadataDelta.RELEASE
    assert _effect_by_expr(
        effects,
        "dquot_reserve_block(inode, nr)",
    ).plane is MetadataPlane.ACCOUNTING
    assert _effect_by_expr(
        effects,
        "dquot_release_reservation_block(inode, nr)",
    ).delta is MetadataDelta.RELEASE
    assert _effect_by_expr(
        effects,
        "btrfs_record_root_in_trans(trans, root)",
    ).delta is MetadataDelta.PROTECT
    assert _effect_by_expr(
        effects,
        "btrfs_end_transaction(trans)",
    ).delta is MetadataDelta.CLOSE
