# Bug #16: Btrfs Sprout Transaction Update Ownership

Status: `READY_FOR_MINING` as part of failure rollback; exact baseline commit is
missing.

## Evidence

- Historical record: `docs/corpus/confirmed-bugs-source.md`, Bug #16.
- Source: Linux v6.14 `fs/btrfs/volumes.c`,
  `btrfs_init_new_device()` at line 2778.
- Dynamic evidence: seed/sprout fault injection reaches
  `WARN_ON(!list_empty(&device->post_commit_list))`.
- Repair evidence: patch 1/3 and lore Message-ID in the source record.

## Unified Semantic Record

- OperationRoot: add the first writable device to a seed filesystem.
- Roles: new device, transaction, post-commit update list, fs_devices owner.
- Candidate anchors: device-add epoch plus new-device identity.
- Entry assumptions: sprout setup has begun and chunk creation may enqueue the
  device for post-commit update.
- Typed events: `AttachTransactionUpdate`, `FailureObserved`,
  `TransactionAbort`, `ReleaseDevice`, `OperationReturn`.
- Relation/local deltas: device becomes a member of the transaction update list.
- Obligation: detach from the list or validly transfer ownership before device
  release.
- Isolation/observability: operation/transaction internal; owner termination is
  still a hard deadline.
- Responsibility transfer: transaction abort does not automatically discharge
  post-commit list ownership.
- Outcome/terminal: released device remains attached to transaction state.
- Deadline: `BEFORE_OWNER_TERMINATION`.

