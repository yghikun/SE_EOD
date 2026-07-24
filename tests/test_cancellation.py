from src.cancellation import (
    effect_protected_by,
    effects_cancel,
    normalize_residuals,
)
from src.metadata_residual import (
    MetadataDelta,
    MetadataEffect,
    MetadataPlane,
    SourceSite,
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
