# Btrfs Tool Findings Pending Review

Date: 2026-07-23

This document records new btrfs findings surfaced by the failure-path filesystem
metadata residual analyzer and then checked manually against source. They are kept
separate from `outputs/confirmed_bugs.md` until reproduction, duplicate search,
and patch review are complete.

## Version status

All three code shapes are present in both local source snapshots:

- Linux v6.14: upstream commit `38fec10eb60d687e30c8c6b5420d86e8149f7557`
- Linux v7.1: official tag archive at upstream commit
  `8cd9520d35a6c38db6567e97dd93b1f11f185dc6`

Therefore these findings are not fixed through Linux v7.1. A live upstream
`master` query failed because the remote connection was reset, so current
`master`, btrfs `for-next`, and mailing-list duplicate status must be checked
again before reporting or submitting patches.

## Summary

| ID | Function/path | Analyzer provenance | Source classification | v7.1 status |
|---|---|---|---|---|
| P1 | `btrfs_reconfigure()` | Direct candidate | In-scope runtime metadata/state residual | Present |
| P2 | `btrfs_init_dev_replace_tgtdev()` | Direct candidate | Real resource-lifetime leak; outside the core metadata claim | Present |
| P3 | `btrfs_dev_replace_start()` after `mark_block_group_to_copy()` | UNKNOWN surfaced by the analyzer, manually confirmed through the callee/caller chain | In-scope device topology and accounting residual | Present |

The analyzer did not automatically prove these bugs. It identified the failure
points and residual state. The final classifications below are source-level
manual conclusions and still need targeted reproduction.

## P1: `BTRFS_FS_STATE_REMOUNTING` remains set after validation failure

### Tool evidence

The analyzer emitted an `UNCLOSED_METADATA_RESIDUAL` candidate for
`btrfs_reconfigure()`:

- effect: `SET fs_info->fs_state.bit:BTRFS_FS_STATE_REMOUNTING`
- failure: `btrfs_check_features(...)`
- error exit: direct `return ret`
- cancellation on that path: none

The adjacent `btrfs_check_options()` failure has the same source-level issue,
although it was not emitted as a separate final candidate in the current run.

### Source evidence

Linux v6.14, `fs/btrfs/super.c`:

- line 1506 sets `BTRFS_FS_STATE_REMOUNTING`
- lines 1508-1509 return `-EINVAL` directly if option validation fails
- lines 1511-1513 return directly if feature validation fails
- the bit is cleared only on the later success and `restore` paths at lines
  1556 and 1562

Linux v7.1 has the same structure at lines 1519-1526, with cleanup only at
lines 1569 and 1575.

The stale bit is observable by long-lived background behavior:

- auto-defrag stops or drops work while remounting
- qgroup rescan stops while remounting
- asynchronous space reclaim is suppressed while remounting

Because a failed remount leaves the original mount active, the stale bit can
outlive the failed operation instead of being discarded with a failed mount.

### Proposed reproduction

1. Mount a writable btrfs filesystem with auto-defrag and/or qgroups enabled.
2. Attempt a remount whose parsed options fail `btrfs_check_options()`, such as
   a read-write remount with a read-only-only option.
3. Confirm the remount returns an error.
4. Use temporary instrumentation, drgn, or a focused debug patch to inspect
   `fs_info->fs_state` and verify `BTRFS_FS_STATE_REMOUNTING` remains set.
5. Verify at least one consumer path remains suppressed after the failed
   remount.

### Minimal fix direction

Route both early validation failures through a shared exit that clears
`BTRFS_FS_STATE_REMOUNTING`. Do not run restore logic that assumes
`btrfs_ctx_to_info()` has already changed live filesystem state.

## P2: allocated replacement target device leaks on initialization failure

### Tool evidence

The analyzer emitted an `UNCLOSED_METADATA_RESIDUAL` candidate for
`btrfs_init_dev_replace_tgtdev()` at `btrfs_get_dev_zone_info()` with 16
uncancelled effects rooted at `device`, including device state bits, geometry,
accounting fields, filesystem pointers, and block-device ownership fields.

The residual field values are not themselves the main defect because the
object has not yet been linked into `fs_devices`. Manual review identified the
underlying resource-lifetime leak.

### Source evidence

Linux v6.14, `fs/btrfs/dev-replace.c`:

- line 293 allocates `device` with `btrfs_alloc_device()`
- line 299 can fail in `lookup_bdev()`
- line 322 can fail in `btrfs_get_dev_zone_info()`
- lines 335-337 release only `bdev_file` and return
- `*device_out` is assigned only after successful list insertion, so the caller
  cannot recover the failed allocation

Linux v7.1 retains the same problem at lines 285-329. The error path calls only
`bdev_fput(bdev_file)` after the allocation.

The normal `btrfs_free_device()` path releases the device name, allocation
state, zone information, and the device object. That cleanup is absent here.

### Proposed reproduction

1. Prefer the `btrfs_get_dev_zone_info()` failure path because it is easier to
   target than racing `lookup_bdev()` after a successful open.
2. Use a zoned `null_blk` target plus fault injection in zone-info allocation
   or zone reporting.
3. Run device replace repeatedly and verify the ioctl returns the injected
   error.
4. Use kmemleak or targeted allocation counters to confirm one
   `struct btrfs_device` and its owned state remain per failed attempt.

### Minimal fix direction

Add a pre-list-insertion cleanup path for allocated devices. The existing
`btrfs_destroy_dev_replace_tgtdev()` cannot be used for this phase because it
assumes the device is linked and decrements `num_devices` and `open_devices`.
Block-device file ownership must remain single-release on every path.

## P3: replacement target remains linked if block-group marking fails

### Tool evidence

The analyzer kept the `mark_block_group_to_copy()` call in
`btrfs_dev_replace_start()` as `METADATA_RESIDUAL_UNKNOWN` because same-file
callee-local identities were not safely bound. It still exposed the relevant
failure point and the reaching device-list accounting effects. Manual caller
and callee review then confirmed the missing cleanup.

This should be described as a tool-assisted finding, not as a direct candidate
that the analyzer fully classified.

### Source evidence

Linux v6.14, `fs/btrfs/dev-replace.c`:

- lines 326-330 link the target device and increment `num_devices` and
  `open_devices`
- lines 631-634 return only after successful target initialization
- lines 636-638 return directly if `mark_block_group_to_copy()` fails
- the target cleanup at lines 719-721 is bypassed

Linux v7.1 retains the same sequence at lines 318-325 and 620-627. The cleanup
label remains later at lines 708-710.

On zoned filesystems, `mark_block_group_to_copy()` can fail while attaching or
committing a transaction, allocating a path, or iterating the device extents.
The direct return leaves the target device linked, keeps the counters
incremented, and keeps its block device open even though device replacement
never enters the started state.

If iteration fails after setting some `BLOCK_GROUP_FLAG_TO_COPY` bits, those
partial runtime flags also need review. They are not required to establish the
linked-target leak, but a complete fix should decide whether to clear them.

### Proposed reproduction

1. Create a zoned btrfs filesystem using host-managed `null_blk`.
2. Inject failure in `btrfs_alloc_path()` or a btree operation inside
   `mark_block_group_to_copy()` after target initialization succeeds.
3. Run device replace and verify the ioctl returns an error.
4. Inspect the device list and counters, then verify the target block device
   remains held despite replacement never starting.
5. Repeat the operation to check for accumulated devices or an unexpected
   `-EEXIST` result.

### Minimal fix direction

Route failure after successful target initialization through target-device
destruction rather than returning directly. Also audit partial
`BLOCK_GROUP_FLAG_TO_COPY` state before treating a simple `goto leave` as the
complete fix.

## Findings reviewed and not currently treated as bugs

The following candidate families were checked but currently look like missing
analysis semantics rather than defects:

- `write_all_supers()`: backup-root slot rotation occurs before a commit
  attempt; fatal write failures enter filesystem error handling.
- `btrfs_truncate_free_space_cache()`: `BTRFS_DC_CLEAR` is the conservative
  state after truncation failure and the transaction is aborted.
- `btrfs_rebuild_free_space_tree()`: creating/untrusted flags intentionally
  preserve that the free-space tree cannot be trusted after failure.
- `btrfs_get_dev_zone_info()`: its own error path destroys `device->zone_info`
  and clears the pointer.
- `btrfs_orphan_cleanup()`: the permanent started bit is suspicious but its
  documented one-shot/reentrancy semantics are not yet disproved.

## Review checklist for 2026-07-24

- Check live Linus `master`, btrfs `for-next`, lore, and patchwork for fixes or
  duplicate reports.
- Re-evaluate P1 with a naturally rejected remount option and confirm the mount
  remains active with the stale bit.
- Build minimal fault-injection reproductions for P2 and P3.
- Decide whether P2 remains only SE-EOD/resource-lifetime evidence and outside
  the paper's metadata-residual recall claims.
- Check partial `BLOCK_GROUP_FLAG_TO_COPY` rollback for P3.
- Only after reproduction or equivalent targeted evidence, move records into
  `outputs/confirmed_bugs.md` and prepare patches/reports.
