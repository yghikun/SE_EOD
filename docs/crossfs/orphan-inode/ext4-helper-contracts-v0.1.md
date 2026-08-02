# ext4 OIDS Interprocedural Helper Contracts v0.1

## Scope

This audit refines the Linux v6.14 ext4 OIDS evidence across:

```text
__ext4_unlink
-> ext4_orphan_add
-> ext4_orphan_file_add / legacy orphan list
-> ext4_mark_inode_dirty
-> ext4_journal_stop

ext4_evict_inode
-> ext4_orphan_del
-> ext4_mark_inode_dirty
-> ext4_free_inode / ext4_clear_inode
-> ext4_journal_stop

__ext4_fill_super
-> ext4_orphan_cleanup
-> ext4_orphan_get / ext4_process_orphan
-> ext4_mark_recovery_complete
```

The audit includes `fs/jbd2/transaction.c` and `include/linux/jbd2.h` from the
same Linux v6.14 tag and commit as the filesystem snapshot.

## JBD2 boundary

`jbd2_journal_abort_handle()` only sets `handle->h_aborted = 1`.
`jbd2_journal_stop()` observes an aborted handle and returns `-EIO`, but it
does not call `jbd2_journal_abort()`. Therefore:

```text
HANDLE_ABORTED != JOURNAL_TRANSACTION_ABORTED
HANDLE_STOP_ERROR != ROLLBACK_OF_ALREADY_JOURNALED_METADATA
```

`ext4_handle_error()` separately controls filesystem/journal failstop. With a
non-continuing error policy, it sets shutdown and calls `jbd2_journal_abort()`
for a writable filesystem. With `ERRORS_CONT`, `continue_fs` is true and that
journal-abort branch is skipped.

## Registration

The orphan-file `-ENOSPC` result is a closed fallback to the legacy orphan
list. Journal write-access and dirty-metadata failures mark the supplied
handle aborted. The caller nevertheless ignores `ext4_orphan_add()` and later
stops the same handle.

The non-continuing error-policy profile is failstop-contained. Under
`ERRORS_CONT`, handle abort plus a stop error does not prove that the earlier
directory-entry deletion cannot commit. Universal registration closure is
therefore false.

## Settlement

The successful eviction branch co-settles persistent orphan removal, inode
free, and journal stop on the same handle. A post-removal inode-dirty error
skips `ext4_free_inode()`.

The non-continuing policy aborts the journal or prevents writable progress.
Under `ERRORS_CONT`, partial orphan removal may already be journaled while the
terminal inode free is skipped. A removal-only commit is not excluded, so the
universal settlement proof remains open.

`ext4_orphan_del(NULL, inode)` remains in-memory cleanup only and contributes
no persistent-removal evidence.

## Recovery

The Phase 5 CFG extension parses `__ext4_fill_super()` without suppressing
preprocessor branches. It inserts a null statement only where a C label is
immediately followed by a preprocessor directive, preserving source lines.

The following partitions are closed:

```text
empty registry -> NOT_APPLICABLE
valid orphan -> ext4_process_orphan -> iput-driven eviction
```

An `ext4_orphan_get()` error can leave the void cleanup function and return to
`__ext4_fill_super()`. Under `ERRORS_CONT`, later recovery completion and mount
return are not excluded. For the failstop profile, the remaining proof gap is
the JBD2 journal-flush error propagation into mount failure.

## Decision

This phase does not generate a COMMON freeze manifest. `ERRORS_CONT` is a
valid ext4 configuration branch and cannot be silently removed from an
unqualified cross-filesystem claim. The result is a guarded configuration
boundary, not a direct dynamic violation verdict.
