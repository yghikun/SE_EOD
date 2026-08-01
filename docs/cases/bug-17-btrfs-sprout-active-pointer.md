# Bug #17: Btrfs Sprout Active Pointer Rollback

Status: `VALIDATION`; exact baseline commit is missing.

## Evidence

- Historical record: `docs/corpus/confirmed-bugs-source.md`, Bug #17.
- Source: Linux v6.14 `fs/btrfs/volumes.c`,
  `btrfs_init_new_device()` at line 2778.
- Dynamic evidence: seed/sprout fault injection reaches
  `btrfs_show_devname()` with a stale/freed active device pointer.
- Repair evidence: patch 2/3 and lore Message-ID in the source record.

## Unified Semantic Record

- OperationRoot: add the first writable device to a seed filesystem.
- Roles: seed device, new device, `latest_dev`, `s_bdev`, fs_devices owner.
- Candidate anchors: device-add epoch plus fs_devices identity.
- Entry assumptions: active pointers are temporarily rebound to the new device.
- Typed events: `RebindActivePointer`, `FailureObserved`, `ReleaseDevice`,
  `LiveExposure`, `OperationReturn`.
- Relation/local deltas: active pointers move from seed to new device.
- Obligation: restore active pointers to a live member before release/exposure.
- Isolation/observability: pointer becomes observable through mount/device-name
  queries; stale exposure is irreversible evidence for that path.
- Responsibility transfer: none established.
- Outcome/terminal: active pointer names a failed/released nonmember.
- Deadline: `BEFORE_EXPOSURE` and `BEFORE_OWNER_TERMINATION`.

