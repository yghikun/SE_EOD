"""Known false-positive contracts learned from static review.

These rules model source-level ownership/cleanup facts.  They are intentionally
kept separate from review labels: labels can change ranking, while these
contracts change the static resource model itself.
"""

from __future__ import annotations

from typing import Any

from .resource_expr import same_resource_expr


def is_contract_restore_acquire(
    function_name: str, acquire_func: str, resource_expr: str
) -> bool:
    """Return True when an acquire-like call restores a caller-owned lock."""

    if (
        function_name == "__track_dentry_update"
        and acquire_func == "mutex_lock"
        and same_resource_expr(resource_expr, "&ei->i_fc_lock")
    ):
        return True
    if (
        function_name == "ext4_ind_truncate_ensure_credits"
        and acquire_func == "down_write"
        and same_resource_expr(resource_expr, "&EXT4_I(inode)->i_data_sem")
    ):
        return True
    return False


def resource_exempt_by_function_contract(
    function_name: str,
    condition: str,
    error_source_expr: str,
    resource: Any,
) -> bool:
    """Return True when a held resource is not locally cleanup-owned."""

    var = str(getattr(resource, "var", "") or "")
    acquire_func = str(getattr(resource, "acquire_func", "") or "")
    resource_type = str(getattr(resource, "resource_type", "") or "")

    if (
        function_name == "ext4_bread_batch"
        and condition.strip() == "!wait"
        and resource_type == "buffer_head"
        and same_resource_expr(var, "bhs")
    ):
        return True

    if (
        function_name == "ext4_rename"
        and error_source_expr.startswith("ext4_whiteout_for_rename(")
        and acquire_func in {"ext4_journal_start", "ext4_journal_start_sb"}
        and same_resource_expr(var, "handle")
    ):
        return True

    return False


def suppresses_missing_cleanup(
    row: dict[str, str],
    missing_action: str,
    missing_arg: str,
    resource: dict[str, Any] | None = None,
) -> bool:
    """Return True when a known function contract explains a missing action."""

    function_name = row.get("function", "")
    condition = row.get("condition", "").strip()
    error_source = row.get("error_source_expr", "")
    file_name = row.get("file", "")

    if (
        function_name == "__track_dentry_update"
        and missing_action == "mutex_unlock"
        and same_resource_expr(missing_arg, "&ei->i_fc_lock")
    ):
        return True

    if (
        function_name == "ext4_ind_truncate_ensure_credits"
        and missing_action == "up_write"
        and same_resource_expr(missing_arg, "&EXT4_I(inode)->i_data_sem")
    ):
        return True

    if (
        function_name == "ext4_bread_batch"
        and condition == "!wait"
        and missing_action == "brelse"
        and same_resource_expr(missing_arg, "bhs")
    ):
        return True

    if (
        function_name == "ext4_rename"
        and error_source.startswith("ext4_whiteout_for_rename(")
        and missing_action == "ext4_journal_stop"
        and same_resource_expr(missing_arg, "handle")
    ):
        return True

    if (
        file_name == "fs/btrfs/extent-tree.c"
        and function_name == "btrfs_lock_cluster"
        and missing_action == "spin_unlock"
        and same_resource_expr(missing_arg, "&cluster->refill_lock")
    ):
        return True

    if (
        file_name == "fs/btrfs/block-group.c"
        and function_name == "reserve_chunk_space"
        and missing_action in {"kfree", "kvfree", "kmem_cache_free"}
        and same_resource_expr(missing_arg, "bg")
        and str(resource.get("acquire_func", "") if resource else "")
        in {"btrfs_create_chunk", "create_chunk"}
    ):
        return True

    if (
        file_name == "fs/btrfs/volumes.c"
        and function_name == "init_first_rw_device"
        and missing_action in {"kfree", "kvfree", "kmem_cache_free"}
        and same_resource_expr(missing_arg, "meta_bg")
        and str(resource.get("acquire_func", "") if resource else "")
        in {"btrfs_create_chunk", "create_chunk"}
    ):
        return True

    return False
