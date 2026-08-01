# Bug #18: Btrfs Sprout Container Rollback

Status: `VALIDATION`; exact baseline commit is missing.

## Evidence

- Historical record: `docs/corpus/confirmed-bugs-source.md`, Bug #18.
- Source: Linux v6.14 `fs/btrfs/volumes.c`,
  `btrfs_init_new_device()` at line 2778.
- Dynamic evidence: failed device add leaves a new sprout container with no
  open devices and triggers `assertion failed: nr_devices`.
- Fixed-run evidence: the 3-patch series removes the recorded WARN/OOPS/BUG
  signatures.

## Unified Semantic Record

- OperationRoot: add the first writable device to a seed filesystem.
- Roles: seed fs_devices, sprout fs_devices, seed devices, new device, fs_info.
- Candidate anchors: device-add epoch plus original fs_devices identity.
- Entry assumptions: `btrfs_setup_sprout()` has moved devices and changed fsid.
- Typed events: `CreateContainer`, `MoveMembers`, `ChangeIdentity`,
  `FailureObserved`, `RollbackAttempt`, `OperationReturn`.
- Relation/local deltas: members, seeding state, fsid, and active container all
  change.
- Obligation: on failed add, restore the pre-operation container relation as a
  unit or validly transfer complete rollback responsibility.
- Isolation/observability: operation internal until return, but invalid
  container state can be observed by mounted filesystem paths.
- Responsibility transfer: transaction abort alone is insufficient.
- Outcome/terminal: error return with partially initialized sprout state.
- Deadline: `AT_SETTLEMENT(OperationReturn)`.
