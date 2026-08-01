# Bug #1: ext4 Fast-Commit Add-Range Outcome

Status: `EVIDENCE_INCOMPLETE` (exact baseline commit and locally inspectable
submitted patch are missing).

## Evidence

- Historical record: `docs/corpus/confirmed-bugs-source.md`, Bug #1.
- Bug source: `linux-sources/linux-v6.8-fs/fs/ext4/fast_commit.c`,
  `ext4_fc_replay_add_range()` at line 1718.
- Normal implementation: the same helper completes all requested range updates
  before returning `0`.
- Safe sibling semantics: the dispatcher checks nonzero replay helper returns;
  this helper suppresses those failures.
- Repair evidence: submitted patch branch `33b4ecd48982`; patch body is not in
  this workspace.

## Failure Path

`ext4_fc_replay()` dispatches an add-range tag; modified-inode recording,
mapping, extent lookup/insertion, or extent update fails; control reaches
`out:`; the inode is released; the helper returns `0`.

## Unified Semantic Record

- OperationRoot: fast-commit replay of one logged add-range operation.
- Roles: replay owner, inode, logical range, extent mapping, outcome consumer.
- Candidate anchors: replay epoch plus inode identity and logged range.
- Entry assumptions: a valid add-range replay item is selected.
- Typed events: `TransitionStart`, `MetadataStep`, `FailureObserved`,
  `ReportOutcome(SUCCESS)`, `OperationReturn`.
- Relation/local deltas: zero or more extent/bitmap updates may precede failure.
- Obligation: report `ERROR` unless the replay transition reaches completion.
- Isolation/observability: recovery-internal until the helper outcome is
  consumed; the return makes the outcome observable to the replay driver.
- Responsibility transfer: none established.
- Outcome/terminal: partial or failed transition reported as success.
- Deadline: `AT_SETTLEMENT(OperationReturn)`.

