"""Vocabulary and primitive tables used by metadata effect extraction."""

from __future__ import annotations


ACCOUNTING_TERMS = {
    "account",
    "alloc",
    "block",
    "blocks",
    "byte",
    "bytes",
    "count",
    "counter",
    "dquot",
    "free",
    "i_blocks",
    "i_bytes",
    "i_count",
    "i_nlink",
    "nlink",
    "quota",
    "qgroup",
    "ref",
    "refcount",
    "refs",
    "reserve",
    "reserved",
    "reservation",
    "rsv",
    "space",
    "used",
}


RECOVERY_TERMS = {
    "abort",
    "cancel",
    "commit",
    "defer",
    "deferred",
    "delayed",
    "dirty",
    "journal",
    "log",
    "orphan",
    "ordered",
    "pending",
    "post_commit",
    "recover",
    "recovery",
    "reloc",
    "replay",
    "trans",
    "transaction",
}


STRUCTURAL_TERMS = {
    "bdev",
    "block_group",
    "chunk",
    "dev",
    "device",
    "dir",
    "entry",
    "extent",
    "fs_devices",
    "inode",
    "link",
    "list",
    "mapping",
    "name",
    "namespace",
    "node",
    "root",
    "tree",
    "xarray",
    "xa",
}


FIELD_SCOPE_TERMS = ACCOUNTING_TERMS | RECOVERY_TERMS | STRUCTURAL_TERMS


OUT_OF_SCOPE_ROOTS = {
    "bh",
    "bh2",
    "buffer",
    "dentry_folio",
    "folio",
    "fname",
    "iloc",
    "name",
    "path",
    "tmp",
}


TRANSIENT_CONTEXT_SUFFIXES = {
    "arg",
    "args",
    "cache",
    "check",
    "context",
    "control",
    "ctl",
    "ctx",
    "cache_entry",
    "key",
    "option",
    "options",
    "param",
    "params",
    "path",
    "ref",
    "request",
    "spec",
}


TRANSIENT_OPERATION_TYPE_TOKENS = {
    "scrub",
}


VFS_WIRING_FIELDS = {
    "a_ops",
    "i_fop",
    "i_mapping",
    "i_op",
}


CONTROL_STATUS_FIELDS = {
    "err",
    "error",
    "result",
    "retval",
}


TRANSIENT_RUNTIME_STATUS_SUFFIXES = (
    "_in_progress",
)


RECOVERY_CONTEXT_TERMS = {
    "commit",
    "delayed",
    "journal",
    "orphan",
    "ordered",
    "recover",
    "recovery",
    "reloc",
    "replay",
    "trans",
    "transaction",
}


METADATA_READER_SUFFIXES = (
    "_bytes",
    "_count",
    "_ctransid",
    "_flags",
    "_generation",
    "_gid",
    "_in_tree",
    "_id",
    "_item",
    "_level",
    "_len",
    "_length",
    "_mode",
    "_name",
    "_nlink",
    "_node",
    "_offset",
    "_owner",
    "_parent",
    "_refs",
    "_rdev",
    "_root",
    "_size",
    "_state",
    "_transid",
    "_type",
    "_uid",
)


READONLY_QUOTA_HELPER_SUFFIXES = (
    "_quota_inode",
    "_quota_on",
)


READONLY_TRANSACTION_HELPER_SUFFIXES = (
    "_iget",
    "_iget_handle",
    "_recover_resv",
)


TRANSACTION_HELPER_TOKENS = {
    "delayed",
    "journal",
    "orphan",
    "recover",
    "recovery",
    "replay",
    "trans",
    "transaction",
}


NON_METADATA_OBSERVER_PREFIXES = (
    "trace_",
)


NON_METADATA_OBSERVER_SUFFIXES = (
    "_lock",
    "_unlock",
)


TRANSACTION_OWNERSHIP_PRIMITIVES = {
    # primitive: (transaction argument, owned metadata argument)
    "btrfs_record_root_in_trans": (0, 1),
    "xfs_trans_ijoin": (0, 1),
    "xfs_trans_log_inode": (0, 1),
}


TRANSACTION_OUTPARAM_OWNERSHIP_PRIMITIVES = {
    # primitive: (owned metadata argument, transaction output argument)
    "xfs_trans_alloc_dir": (0, 1),
}


ACCESSOR_VALIDATOR_TOKENS = {
    "can",
    "check",
    "enabled",
    "find",
    "full",
    "get",
    "has",
    "is",
    "should",
    "valid",
}


MUTATING_HELPER_PREFIXES = (
    "abort_",
    "add_",
    "alloc_",
    "clear_",
    "clone_",
    "commit_",
    "create_",
    "del_",
    "delete_",
    "drop_",
    "end_",
    "free_",
    "init_",
    "insert_",
    "load_",
    "mark_",
    "put_",
    "read_",
    "record_",
    "release_",
    "remove_",
    "reserve_",
    "set_",
    "start_",
    "stop_",
    "update_",
    "write_",
)


MUTATING_HELPER_TOKENS = {
    "abort",
    "add",
    "alloc",
    "clear",
    "clone",
    "commit",
    "copy",
    "create",
    "dec",
    "del",
    "delete",
    "drop",
    "end",
    "free",
    "inc",
    "init",
    "insert",
    "link",
    "load",
    "mark",
    "put",
    "record",
    "release",
    "remove",
    "reserve",
    "set",
    "start",
    "stop",
    "unlink",
    "update",
    "write",
}


LIST_ADD_CALLS = {
    "list_add",
    "list_add_tail",
    "hlist_add_head",
    "hlist_add_before",
    "hlist_add_behind",
}


LIST_REMOVE_CALLS = {
    "list_del",
    "list_del_init",
    "hlist_del",
    "hlist_del_init",
    "hlist_del_rcu",
}


BIT_SET_CALLS = {"set_bit", "__set_bit", "test_and_set_bit"}


BIT_CLEAR_CALLS = {"clear_bit", "__clear_bit", "test_and_clear_bit"}


TREE_ADD_CALLS = {
    "rb_link_node",
    "rb_insert_color",
    "rb_add",
    "radix_tree_insert",
    "xa_insert",
    "xa_store",
    "xas_store",
    "xas_create",
}


TREE_REMOVE_CALLS = {
    "rb_erase",
    "radix_tree_delete",
    "xa_erase",
    "xa_release",
    "xas_erase",
    "xas_store_null",
}
