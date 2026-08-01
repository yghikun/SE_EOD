# DeviceShrinkSpaceAccounting v0.3 Evidence Boundary

Status: `FROZEN_NARROW_SCOPE`; freeze date: 2026-08-01.

## Object and causal chain

The protocol is the coupled relation between one writable device and its
filesystem aggregates:

```text
device.total_bytes / device.bytes_used
    -> fs_devices.total_rw_bytes
    -> fs_info.free_chunk_space
    -> shrink success or failure settlement
```

The required delta is the loss of writable free capacity, not the raw device
size delta. A shrink failure must restore every changed relation using the
same guarded delta. This is a device-shrink protocol, not a generic counter
rollback rule.

## Independent design and normal-path evidence

The Bug/fix patch is not the only source for these rules. The checksum-verified
v6.14 and v7.1 Btrfs snapshots independently show the normal capacity model:

| Evidence | Source | Semantic fact |
|---|---|---|
| design comment | `fs/btrfs/volumes.c`, `btrfs_shrink_device` | `free_chunk_space` represents `new_size - used`; used bytes must be removed from the delta |
| normal add/remove | `fs/btrfs/volumes.c`, device open/remove paths | writable aggregate and free capacity are updated together and under the device state/lock discipline |
| consumer | `fs/btrfs/space-info.c`, `calc_available_free_space` | the aggregate is consumed as allocatable free capacity, so a stale value changes future allocation decisions |
| field roles | `fs/btrfs/volumes.h`, `fs/btrfs/fs.h` | device size/usage, writable aggregate and free-space aggregate are distinct relations |

These are design and normal-source witnesses, not a second operation family.
The v6.14/v7.1 snapshots are provenance-locked in `SOURCE_MANIFEST.json`.

## Cross-filesystem screening

ext4, XFS and F2FS maintain their own free-space relations, but their units,
allocation policy and ownership differ. None has the same typed relation
`device.total_bytes -> total_rw_bytes -> free_chunk_space` or the same shrink
settlement boundary. They therefore remain corroborating background only and
are not inserted into DSSA guards or AcceptP.

## Freeze limitation

The confirmed Bug/fix pair and four replay classes establish a narrow frozen
protocol. There is one operation family (`btrfs-device-shrink`), so
`generalization_eligible=false` until an independent family is screened after
this freeze. No rule is derived from a Bug ID, function name, line number or
patch identifier.
