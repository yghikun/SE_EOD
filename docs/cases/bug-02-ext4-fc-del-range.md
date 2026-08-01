# Bug #2: ext4 Fast-Commit Delete-Range Outcome

Status: `EVIDENCE_INCOMPLETE` (exact baseline commit and patch body missing).

## Evidence

- Historical record: `docs/corpus/confirmed-bugs-source.md`, Bug #2.
- Bug source: `linux-sources/linux-v6.8-fs/fs/ext4/fast_commit.c`,
  `ext4_fc_replay_del_range()` at line 1839.
- Normal implementation: full delete-range replay returns `0` only after the
  loop completes.
- Safe sibling semantics: the replay dispatcher has a nonzero-error branch.
- Repair evidence: same submitted patch as Bug #1, not locally present.

## Failure Path

The replay loop can mark replay-side block bitmap state, then fail mapping or
extent removal; `goto out` releases the inode and returns literal success.

## Unified Semantic Record

- OperationRoot: fast-commit replay of one logged delete-range operation.
- Roles: replay owner, inode, logical range, block bitmap, extent tree, caller.
- Candidate anchors: replay epoch plus inode identity and logged range.
- Entry assumptions: a valid delete-range replay item is selected.
- Typed events: `TransitionStart`, `MetadataStep`, `FailureObserved`,
  `ReportOutcome(SUCCESS)`, `OperationReturn`.
- Relation/local deltas: bitmap and/or extent changes can be partial.
- Obligation: a failed delete-range transition must not report success.
- Isolation/observability: replay-internal changes become relevant when the
  driver accepts the helper outcome.
- Responsibility transfer: none established.
- Outcome/terminal: partial/failed transition with success outcome.
- Deadline: `AT_SETTLEMENT(OperationReturn)`.

