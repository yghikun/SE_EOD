# Bug #7: Btrfs Relocation-Root Failure Rollback

Status: `READY_FOR_MINING`.

## Evidence

- Historical record: `docs/corpus/confirmed-bugs-source.md`, Bug #7.
- Bug source: Linux v6.8 `fs/btrfs/relocation.c`,
  `btrfs_recover_relocation()` at line 4250.
- Dynamic Bug and safe-error evidence:
  `docs/corpus/evidence/bug-07-recover-relocation-qemu.md`.
- Repair evidence: patch branch commit `08f1ccb98abb`; accepted into Btrfs
  `for-next` according to maintainer Message-ID in the source record.

## Failure And Safe Paths

Bug path: recovery attaches 25 `fs_root->reloc_root` references; the first
commit fails without `BTRFS_FS_ERROR`; `out_unset` leaves attachments live.

Safe sibling: an aborting failure sets `BTRFS_FS_ERROR`; teardown drops the
relocation roots. Normal recovery completes and balance ends successfully.

## Unified Semantic Record

- OperationRoot: mount-time relocation recovery.
- Roles: fs root, relocation root, recovery owner, transaction, teardown owner.
- Candidate anchors: recovery epoch plus fs-root identity.
- Entry assumptions: pending relocation root item exists.
- Typed events: `AttachActive`, `TransactionAttempt`, `FailureObserved`,
  `TransactionAbort` or non-abort failure, `OwnerTermination`.
- Relation/local deltas: `fs_root.reloc_root` becomes attached and holds a root
  reference.
- Obligation: before failed recovery settles, detach/drop every attachment or
  delegate it to a proven teardown authority.
- Isolation/observability: mount recovery is isolated, but owner termination is
  the deadline; absence of live exposure does not prove relation restoration.
- Responsibility transfer: only an established teardown authority may accept
  the obligation; `BTRFS_FS_ERROR` is evidence for one guarded safe path, not a
  universal transfer.
- Outcome/terminal: failed recovery with outstanding attachment.
- Deadline: `BEFORE_OWNER_TERMINATION`.

