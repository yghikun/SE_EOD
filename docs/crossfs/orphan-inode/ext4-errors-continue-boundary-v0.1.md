# ext4 ERRORS_CONT Configuration Boundary v0.1

## Scope

This Phase 6 audit closes the remaining ext4 failstop-recovery contract and
tests the valid `ERRORS_CONT` configuration separately. It uses Linux v6.14
ext4 and JBD2 source from one tag and commit. The historical semantic kernel
and base source manifest remain byte-frozen.

## Failstop recovery

For a writable filesystem outside `ERRORS_CONT`, `ext4_handle_error()` calls
`jbd2_journal_abort()`. The recovery path then has this error propagation:

```text
jbd2 journal abort
-> jbd2_journal_flush() returns -EIO
-> ext4_mark_recovery_complete() returns the error
-> __ext4_fill_super() goes to failed_mount9
-> mount returns the error
```

This closes the Phase 5 blocker
`EXT4_RECOVERY_FAILSTOP_FLUSH_CONTRACT_NOT_LOCKED`. Registration, settlement,
and recovery are therefore closed for the explicitly qualified failstop
profile.

## Transaction boundary

`jbd2_journal_dirty_metadata()` files a buffer as `BJ_Metadata`.
`__jbd2_journal_file_buffer()` maps that list type to
`transaction->t_buffers`, and the commit loop consumes
`commit_transaction->t_buffers`.

The discard/refile branch in `jbd2_journal_commit_transaction()` is guarded
by `is_journal_aborted(journal)`. It does not test a handle-local abort.
`jbd2_journal_abort_handle()` only sets `handle->h_aborted`, while
`jbd2_journal_stop()` reports that state without calling
`jbd2_journal_abort()`. Consequently, metadata already filed on the
transaction is not rolled back merely because one handle is aborted.

## Negative witnesses

The three witnesses use protocol-declared deadlines through
`ProtocolDeadlineEngine`; the older `semantics.py` remains unchanged.

| Stage | Source outcome under ERRORS_CONT | Replay rule |
|---|---|---|
| registration | directory metadata can commit without orphan registration | `OIDS-O1` |
| settlement | orphan-file removal can commit while inode free is skipped | `OIDS-O2` |
| recovery | mount exposure can follow an orphan lookup error without cleanup completion | `OIDS-O3` |

These are transaction/recovery witnesses under the loaded source model and
protocol. They are not fault-injection measurements and do not claim that
every error reaches the outcome.

## Configuration decision

`ERRORS_CONT` is a valid ext4 configuration and therefore a valid boundary
for an unqualified OIDS conformance claim. Phase 6 permits a qualified
failstop-profile statement, but rejects universal ext4 validation and does
not generate a COMMON freeze manifest.

Any later protocol scope that excludes `ERRORS_CONT` must state that exclusion
in its applicability declaration and evaluation report. It cannot remain an
implicit assumption.
