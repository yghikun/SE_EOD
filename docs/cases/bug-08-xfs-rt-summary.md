# Bug #8: XFS Realtime Summary Copy Outcome

Status: `HELD_OUT` until Protocol Catalog v0.1 is frozen.

## Evidence

- Historical record: `docs/corpus/confirmed-bugs-source.md`, Bug #8.
- Bug source: Linux v6.8 `fs/xfs/xfs_rtalloc.c`, function starts at line 88.
- Fixed source: Linux v7.1 returns `error` and adds corruption validation.
- Exact diff: `docs/corpus/evidence/bug-08-xfs-function-diff.md`.
- Caller evidence: `xfs_growfs_rt()` checks the result and cancels the
  transaction on error.

## Unified Semantic Record

- OperationRoot: XFS realtime grow operation.
- Roles: old/new summary metadata, transaction, growfs owner, outcome consumer.
- Candidate anchors: grow operation epoch plus realtime metadata identity.
- Entry assumptions: realtime summary migration is required.
- Typed events: `TransitionStart`, one or more `MetadataStep`,
  `FailureObserved`, `ReportOutcome(SUCCESS)`, `OperationReturn`.
- Relation/local deltas: source/destination summary counters can be partially
  changed.
- Obligation: propagate a failed summary read or update to the growfs owner.
- Isolation/observability: transaction cancellation is available only if the
  helper reports failure.
- Responsibility transfer: none when returning success.
- Outcome/terminal: partial copy reported as success.
- Deadline: `AT_SETTLEMENT(OperationReturn)`.

