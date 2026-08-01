# DeviceShrinkSpaceAccounting v0.3

状态：`FROZEN_NARROW_SCOPE`; 属于 Catalog v0.3，但不属于 frozen Catalog
v0.2。文件名保留 `draft` 仅为兼容旧引用。

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

The protocol has structured Bug, fixed-success, fixed-failure and unknown
replay. Independent Btrfs design/normal-source evidence is recorded in
`dssa-evidence-v0.3.md`. It remains one `btrfs-device-shrink` family, so it is
frozen narrowly but is not held-out or generalization evidence. The executable
readiness manifest is `configs/evaluation/dssa-v0.3-readiness.json`.
