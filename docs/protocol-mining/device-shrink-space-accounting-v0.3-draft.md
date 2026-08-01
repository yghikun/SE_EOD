# DeviceShrinkSpaceAccounting v0.3 Draft

状态：`DRAFT_SINGLETON_FAMILY`; 不属于 frozen Catalog v0.2。

## Semantic object

```text
device.total_bytes
fs_devices.total_rw_bytes
fs_info.free_chunk_space
device writable state
```

The protocol is specific to a device-shrink accounting transition. It is not a
generic rule that every counter update must be reversed.

## Rules

- `DSSA-I1`: the forward `free_chunk_space` delta equals the loss of writable
  free capacity, not the entire device-size difference when used bytes occupy
  part of the removed range.
- `DSSA-I2`: rollback changes writable aggregate accounting only when the
  device is writable and reuses the same computed free-space delta.
- `DSSA-O1`: after shrink failure, every changed accounting relation returns
  to its recorded prestate by operation settlement.

## Confirmed evidence

- Bug revision: `efba1454493df546dcee603c4b77db3a230ac054`.
- Fixed commit: `e9fd2c05239ae423af45f99e2964ad086f800e33`.
- Bug/fixed `volumes.c` blobs: `298e5885...` / `8355533f...`.
- The accepted patch identifies both the wrong forward delta and the
  unconditional rollback addition.

The draft has structured Bug, fixed-success, fixed-failure and unknown replay.
It remains a singleton `btrfs_shrink_device` family and cannot be frozen or
used as held-out evidence without independent design/normal-source validation.
The executable readiness manifest is
`configs/evaluation/dssa-v0.3-readiness.json`; its failed required gates are
`independent_design_evidence`, `independent_normal_source` and
`independent_validation_family`.
