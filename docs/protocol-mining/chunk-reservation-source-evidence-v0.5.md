# Chunk Reservation Source Evidence v0.5

Date: 2026-08-01. Status: frozen evidence slice for Catalog v0.5.

## Source slices

| Role | File | Function | Evidence role |
|---|---|---|---|
| Bug path | `linux-sources/linux-v6.14-fs/fs/btrfs/block-group.c` | `reserve_chunk_space` | chunk publication, positive-success reuse, reservation skip |
| Positive success domain | `linux-sources/linux-v6.14-fs/fs/btrfs/zoned.c` | `btrfs_zoned_activate_one_bg` | returns both `1` and `0` as successful outcomes |
| Settlement | `linux-sources/linux-v6.14-fs/fs/btrfs/transaction.c` | `btrfs_trans_release_chunk_metadata` | releases and clears transaction chunk reservation |
| Second family | `linux-sources/linux-v7.1-fs/fs/btrfs/volumes.c` | `btrfs_grow_device` | chunk-tree device-item update under reserve/update/release lifecycle |

## Causal chain

```text
reserve_chunk_space detects insufficient system space
-> creates a system chunk
-> zoned activation may return 1 for successful activation
-> code only treats ret < 0 as activation failure
-> chunk item is added/queued after the positive success
-> the same ret later controls if (!ret)
-> ret == 1 skips btrfs_block_rsv_add
-> trans->chunk_bytes_reserved remains unchanged
-> chunk metadata publication lacks companion reservation before commit
```

The source-level repair direction is to normalize the successful activation
result or split the local variables so that reservation completion is not
controlled by a positive success value from a different semantic step.

## Settlement evidence

`btrfs_trans_release_chunk_metadata()` gives the normal settlement side of the
candidate protocol:

```text
if trans->chunk_bytes_reserved is zero, no release is needed
otherwise release fs_info->chunk_block_rsv for trans->chunk_bytes_reserved
then set trans->chunk_bytes_reserved to zero
```

This supports the transaction-scoped reservation lifecycle but does not count
as a second independent publication family.

## Second-family evidence

`btrfs_grow_device()` is admitted as the second independent operation family
for the narrow CMRC freeze:

```text
btrfs_reserve_chunk_metadata(trans, ...)
-> btrfs_update_device(trans, device)
-> btrfs_trans_release_chunk_metadata(trans)
```

The semantic object is not WDC/DTC capacity contribution in this context. The
same source function also changes device size, but the CMRC-relevant slice is
the chunk-tree device item update protected by transaction-scoped chunk
metadata reservation and release. This is why E5 rejects it as WDC/DTC
held-out while CMRC accepts it as sibling evidence.
