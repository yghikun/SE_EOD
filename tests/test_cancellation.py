from src.cancellation import (
    effect_protected_by,
    effects_cancel,
    normalize_residuals,
)
from src.metadata_residual import (
    ContainerIterationCleanup,
    MetadataDelta,
    MetadataEffect,
    MetadataPlane,
    SourceSite,
)


def _drain_effect(root: str = "ctx->items", member_field: str = "list") -> MetadataEffect:
    site = SourceSite("fs/example.c", 20, "list_del(&curr->list)")
    return MetadataEffect(
        root=root,
        key="list_membership",
        plane=MetadataPlane.STRUCTURAL,
        delta=MetadataDelta.REMOVE,
        value="*",
        site=site,
        container_iteration_cleanup=ContainerIterationCleanup(
            container_root=root,
            iterator="curr",
            next_iterator="next",
            member_field=member_field,
            iteration_site=SourceSite(
                "fs/example.c",
                19,
                "list_for_each_entry_safe(curr, next, &ctx->items, list)",
            ),
            source_identity=f"fs/example.c:19:curr:{root}:{member_field}",
        ),
    )


def _effect(
    *,
    root: str,
    key: str,
    plane: MetadataPlane = MetadataPlane.ACCOUNTING,
    delta: MetadataDelta,
    value: str,
    line: int = 1,
) -> MetadataEffect:
    return MetadataEffect(
        root=root,
        key=key,
        plane=plane,
        delta=delta,
        value=value,
        site=SourceSite("fs/example.c", line, f"{delta.value}({root},{key},{value})"),
    )


def test_inc_cancels_matching_dec():
    inc = _effect(root="inode", key="i_blocks", delta=MetadataDelta.INC, value="nr")
    dec = _effect(root="inode", key="i_blocks", delta=MetadataDelta.DEC, value="nr")

    assert effects_cancel(inc, dec)
    result = normalize_residuals((inc,), (dec,))
    assert result.residuals == ()
    assert result.cancelled[0].opened is inc
    assert result.cancelled[0].closed is dec


def test_inc_does_not_cancel_dec_on_other_root():
    inc = _effect(root="inode", key="i_blocks", delta=MetadataDelta.INC, value="nr")
    dec = _effect(root="other", key="i_blocks", delta=MetadataDelta.DEC, value="nr")

    assert not effects_cancel(inc, dec)
    assert normalize_residuals((inc,), (dec,)).residuals == (inc,)


def test_inc_does_not_cancel_dec_with_different_value_source():
    inc = _effect(root="inode", key="i_blocks", delta=MetadataDelta.INC, value="nr")
    dec = _effect(root="inode", key="i_blocks", delta=MetadataDelta.DEC, value="old_nr")

    assert not effects_cancel(inc, dec)
    assert normalize_residuals((inc,), (dec,)).residuals == (inc,)


def test_z3_closes_multi_effect_counter_balance():
    increments = (
        _effect(root="devices", key="num_devices", delta=MetadataDelta.INC, value="1"),
        _effect(root="devices", key="num_devices", delta=MetadataDelta.INC, value="1"),
    )
    decrement = _effect(root="devices", key="num_devices", delta=MetadataDelta.DEC, value="2")

    result = normalize_residuals(increments, (decrement,))

    assert result.residuals == ()
    assert "SMT proves" in result.cancelled[0].reason


def test_list_add_cancels_matching_remove():
    add = _effect(
        root="list",
        key="list_membership",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.ADD,
        value="device",
    )
    remove = _effect(
        root="list",
        key="list_membership",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.REMOVE,
        value="device",
    )

    assert effects_cancel(add, remove)
    assert normalize_residuals((add,), (remove,)).residuals == ()


def test_list_add_does_not_cancel_remove_from_other_list():
    add = _effect(
        root="list",
        key="list_membership",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.ADD,
        value="device",
    )
    remove = _effect(
        root="other_list",
        key="list_membership",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.REMOVE,
        value="device",
    )

    assert not effects_cancel(add, remove)
    assert normalize_residuals((add,), (remove,)).residuals == (add,)


def test_m2_list_identity_can_match_remove_by_member_head():
    add = _effect(
        root="trans->dev_update_list",
        key="list_membership",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.ADD,
        value="dev->post_commit_list",
    )
    remove = _effect(
        root="dev->post_commit_list",
        key="list_membership",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.REMOVE,
        value="dev",
    )

    assert effects_cancel(add, remove)
    assert normalize_residuals((add,), (remove,)).residuals == ()


def test_exhaustive_list_cleanup_cancels_all_matching_container_members():
    additions = (
        _effect(
            root="ctx->items",
            key="list_membership",
            plane=MetadataPlane.STRUCTURAL,
            delta=MetadataDelta.ADD,
            value="first->list",
        ),
        _effect(
            root="ctx->items",
            key="list_membership",
            plane=MetadataPlane.STRUCTURAL,
            delta=MetadataDelta.ADD,
            value="second->list",
        ),
    )

    result = normalize_residuals(additions, (_drain_effect(),))

    assert result.residuals == ()
    assert len(result.cancelled) == 2


def test_exhaustive_list_cleanup_does_not_cross_container_or_member_field():
    wrong_container = _effect(
        root="other->items",
        key="list_membership",
        plane=MetadataPlane.STRUCTURAL,
        delta=MetadataDelta.ADD,
        value="item->list",
    )
    wrong_member = _effect(
        root="ctx->items",
        key="list_membership",
        plane=MetadataPlane.STRUCTURAL,
        delta=MetadataDelta.ADD,
        value="item->other_list",
    )

    result = normalize_residuals(
        (wrong_container, wrong_member),
        (_drain_effect(),),
    )

    assert result.residuals == (wrong_container, wrong_member)


def test_set_clear_cancels_same_field_even_when_clear_value_is_null():
    set_effect = _effect(
        root="fs_root",
        key="reloc_root",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.SET,
        value="reloc_root",
    )
    clear_effect = _effect(
        root="fs_root",
        key="reloc_root",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.CLEAR,
        value="NULL",
    )

    assert effects_cancel(set_effect, clear_effect)


def test_reserve_cancels_release_only_with_same_accounting_value():
    reserve = _effect(
        root="root",
        key="btrfs_block_rsv_add",
        delta=MetadataDelta.RESERVE,
        value="rsv, num_bytes",
    )
    release = _effect(
        root="root",
        key="btrfs_block_rsv_add",
        delta=MetadataDelta.RELEASE,
        value="rsv, num_bytes",
    )
    wrong_release = _effect(
        root="root",
        key="btrfs_block_rsv_add",
        delta=MetadataDelta.RELEASE,
        value="rsv, old_bytes",
    )

    assert effects_cancel(reserve, release)
    assert not effects_cancel(reserve, wrong_release)


def test_protect_removes_residual_only_with_explicit_binding():
    opened = _effect(
        root="trans",
        key="root_update",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.ADD,
        value="root",
    )
    protection = _effect(
        root="trans",
        key="root_update",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.PROTECT,
        value="root",
    )
    unrelated = _effect(
        root="other_trans",
        key="root_update",
        plane=MetadataPlane.RECOVERY,
        delta=MetadataDelta.PROTECT,
        value="root",
    )

    assert effect_protected_by(opened, protection)
    assert not effect_protected_by(opened, unrelated)
    assert normalize_residuals((opened,), (), (protection,)).residuals == ()
    assert normalize_residuals((opened,), (), (unrelated,)).residuals == (opened,)
