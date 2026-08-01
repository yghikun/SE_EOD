# Bug #4: ext4 Extra-Isize Stale Outcome

Status: `READY_FOR_MINING` for outcome semantics; exact baseline commit remains
an evidence gap.

## Evidence

- Historical record: `docs/corpus/confirmed-bugs-source.md`, Bug #4.
- Source: `linux-sources/linux-v6.14-fs/fs/ext4/xattr.c`,
  `ext4_expand_extra_isize_ea()` at line 2762.
- Reproduction: the patch record reports a targeted 1 KiB ext4 image where
  clearing stale `-ENOSPC` sharply reduced false ioctl failures.
- Normal/fixed pattern: a successful fallback clears stale failure provenance
  before shifting `i_extra_isize`.

## Failure Path

The first xattr-space attempt produces `-ENOSPC`; the fallback using
`s_min_extra_isize` succeeds and updates inode metadata; the stale error value
survives and is returned to the caller.

## Unified Semantic Record

- OperationRoot: requested inode extra-isize expansion from the xattr/ioctl
  operation.
- Roles: inode, xattr space, fallback policy, result owner.
- Candidate anchors: operation epoch plus inode identity.
- Entry assumptions: primary expansion fails with recoverable `ENOSPC` and the
  fallback is permitted.
- Typed events: `TransitionStart`, `RecoverableFailure`, `RetryStart`,
  `MetadataStep`, `TransitionComplete`, `ReportOutcome(ERROR)`.
- Relation/local deltas: `i_extra_isize` advances to the requested fallback.
- Obligation: completed retry must report success and retire stale error
  provenance.
- Isolation/observability: mutation occurs under inode/xattr protection; the
  ioctl return exposes the mismatch.
- Responsibility transfer: none.
- Outcome/terminal: complete metadata transition reported as error.
- Deadline: `AT_SETTLEMENT(OperationReturn)`.

