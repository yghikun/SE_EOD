# Bug #13: XFS Realtime Metadata Inode Ensure Outcome

Status: `HELD_OUT` until Protocol Catalog v0.1 is frozen.

## Evidence

- Historical record: `docs/corpus/confirmed-bugs-source.md`, Bug #13.
- Bug source: Linux v6.14 `fs/xfs/xfs_rtalloc.c`,
  `xfs_rtginode_ensure()` at line 720; the same pattern remains in v7.1.
- Submitted patch evidence and fixing target `aa897e0bed0f` are recorded in the
  source corpus; the patch body is not local.
- Normal semantic branch: `-ENOENT` creates the inode; a loaded inode or
  successful load returns success; all other errors must remain errors.

## Unified Semantic Record

- OperationRoot: realtime growfs metadata-inode preparation.
- Roles: rtgroup, metadata inode role, transaction, growfs owner.
- Candidate anchors: grow operation epoch plus rtgroup and inode type.
- Entry assumptions: the metadata inode is not already cached.
- Typed events: `LoadAttempt`, `FailureObserved(non-ENOENT)`,
  `ReportOutcome(SUCCESS)`, `OperationReturn`.
- Relation/local deltas: required inode relation remains unestablished.
- Obligation: non-absence load failures must propagate; only `ENOENT` may
  activate create responsibility.
- Isolation/observability: transaction is cancelled before return; cancellation
  does not convert load failure into success.
- Responsibility transfer: `ENOENT` transfers to create; other failures do not.
- Outcome/terminal: failed ensure reported as success.
- Deadline: `AT_SETTLEMENT(OperationReturn)`.

