# Domain Protocol Catalog v0.5

Version: `0.5.0`; status: `FROZEN_NARROW_CROSS_OPERATION_FAMILY`; date:
2026-08-01.

Catalog v0.5 adds one frozen narrow protocol:
`fmpca.chunk_metadata_reservation_completion`.

Frozen v0.1-v0.4 artifacts remain immutable. Catalog v0.5 does not rewrite
`DeviceTopologyRollback`, `RecoveryAttachmentSettlement`,
`RelocationRootAttachmentSettlement`, `DeviceShrinkSpaceAccounting`,
`WritableDeviceCapacityContribution`, or the v0.4 DTR/WDC composition.

## ChunkMetadataReservationCompletion

Intent: a chunk-tree metadata publication, insertion, deletion or update must
complete the companion transaction-scoped chunk metadata reservation before
commit. A helper's nonnegative success value must not be reused in a way that
suppresses the reservation.

- Anchors: `operation`, `transaction`, `block_group`.
- Roles: `chunk_item`, `chunk_block_rsv`.
- Epoch: `operation_root + transaction_epoch + retry_generation`.
- Relations: helper success-domain compatibility, source footprint closure,
  `chunk_metadata_reservation.completed`, release settlement.
- Phases: `STABLE -> RESERVATION_DUE -> RESERVATION_COMPLETE -> SETTLED`.
- `CMRC-I1`: reservation success-domain predicates agree with the helper
  success domain.
- `CMRC-I2`: source witness includes chunk-tree metadata update and
  reservation accounting.
- `CMRC-I3`: before `TransactionCommit`,
  `chunk_metadata_reservation.completed` is true.
- `CMRC-O1`: `ChunkItemPublication` or `ChunkTreeMetadataUpdate` activates a
  `MUST_DISCHARGE` obligation due before commit.

## Evidence boundary

The freeze uses two operation families:

| Operation family | Role | Source |
|---|---|---|
| `btrfs-chunk-metadata-reservation` | development confirmed bug/fixed/normal/unknown replay | `reserve_chunk_space()` plus `btrfs_zoned_activate_one_bg()` |
| `btrfs-device-item-update` | sibling normal source family | `btrfs_grow_device()` device-item update |

The device-item update family is independent from Bug #15 because it updates a
chunk-tree device item under `btrfs_reserve_chunk_metadata()`,
`btrfs_update_device()` and `btrfs_trans_release_chunk_metadata()` rather than
publishing the block group in `reserve_chunk_space()`.

This is cross-operation-family qualification, not post-freeze held-out
generalization and not cross-filesystem generalization.

