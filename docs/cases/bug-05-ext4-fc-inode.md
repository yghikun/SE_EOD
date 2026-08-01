# Bug #5: ext4 Fast-Commit Inode Outcome

Status: `READY_FOR_MINING` (`iloc.bh` lifetime subcase is out of scope).

## Evidence

- Historical record: `docs/corpus/confirmed-bugs-source.md`, Bug #5.
- Bug source: Linux v6.8/v6.14 `fs/ext4/fast_commit.c`, function starts at
  v6.8 line 1517.
- Repair source: Linux v7.1 returns `ret` and routes failures through
  `out_brelse`.
- Exact diff: `docs/corpus/evidence/bug-05-ext4-function-diff.md`.
- Normal source: completed replay sets `ret == 0`, releases state, flushes, and
  returns success.

## Failure Path

After the inode location is obtained, metadata write, sync, mark-used, or inode
lookup fails. Linux v6.8 reaches cleanup and unconditionally returns `0`.

## Unified Semantic Record

- OperationRoot: fast-commit replay of one inode record.
- Roles: replay owner, inode location, inode, block device, outcome consumer.
- Candidate anchors: replay epoch and inode number.
- Entry assumptions: inode replay item accepted.
- Typed events: `TransitionStart`, `MetadataStep`, `FailureObserved`,
  `ReportOutcome(SUCCESS)`, `OperationReturn`.
- Relation/local deltas: inode disk state may be written before a later failure.
- Obligation: report failure unless transition completion is established.
- Isolation/observability: replay-local until return; return controls continued
  recovery.
- Responsibility transfer: none.
- Outcome/terminal: failed/partial transition reported as success.
- Deadline: `AT_SETTLEMENT(OperationReturn)`.

