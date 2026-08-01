# ChunkMetadataReservationCompletion v0.5

Date: 2026-08-01. Status: frozen narrow Catalog entry.

## Task understanding

Bug #15 should not be forced into WDC/DTC. Its semantic object is not
`device -> writable capacity contribution`, but:

```text
chunk/block-group publication
-> transaction-scoped chunk metadata reservation
-> release of trans->chunk_bytes_reserved after chunk-btree updates
-> commit-time settlement
```

The protocol is therefore `ChunkMetadataReservationCompletion` (CMRC). It is
admitted into Catalog v0.5 only after a second independent operation family
closed the same reservation/update/release lifecycle.

## First-principles rule

When an operation publishes or queues chunk-tree metadata, the filesystem must
have enough reserved system metadata space to complete that chunk-tree update.
The reservation is transaction-scoped because `trans->chunk_bytes_reserved`
tracks how much chunk metadata reservation must later be released.

The crucial constraint is the success domain:

```text
btrfs_zoned_activate_one_bg success domain = nonnegative return
reservation guard in reserve_chunk_space = ret == 0
positive success ret == 1
-> publication can occur while the companion reservation is skipped
```

That is why this is not just an outcome bug and not just a resource leak. The
metadata relation is: published/queued chunk metadata must have a matching
transaction reservation before commit.

## Frozen specification

Protocol artifact:
`configs/protocols/chunk-metadata-reservation-completion-v0.5.json`

Binding artifact:
`configs/bindings/chunk-metadata-reservation-completion-v0.5.json`

Core obligations:

```text
CMRC-I1  reservation success-domain predicates must be compatible with helper success
CMRC-I2  source footprint must include chunk publication and reservation accounting
CMRC-I3  before TransactionCommit, chunk_metadata_reservation.completed must be true
CMRC-O1  ChunkItemPublication activates a MUST_DISCHARGE reservation obligation
```

Roles:

```text
operation
transaction
block_group
chunk_item
chunk_block_rsv
```

## Evidence closed for freeze

Source witness:

```text
reserve_chunk_space()
    calls btrfs_chunk_alloc_add_chunk_item()
    calls btrfs_zoned_activate_one_bg()
    later guards btrfs_block_rsv_add() with if (!ret)
    increments trans->chunk_bytes_reserved only when the reservation call succeeds

btrfs_zoned_activate_one_bg()
    can return 1 on successful activation
    can return 0 on ordinary success/no activation

btrfs_trans_release_chunk_metadata()
    checks trans->chunk_bytes_reserved
    releases fs_info->chunk_block_rsv
    clears trans->chunk_bytes_reserved to 0

btrfs_grow_device()
    reserves chunk metadata before btrfs_update_device()
    updates a chunk-tree device item
    releases transaction chunk metadata after the update
```

Replay fixtures:

```text
cmrc-bug-v0.5.json                  -> VIOLATION_UNDER_LOADED_SPEC
cmrc-fixed-v0.5.json                -> CONFORMANT_UNDER_LOADED_SPEC
cmrc-normal-v0.5.json               -> CONFORMANT_UNDER_LOADED_SPEC
cmrc-device-update-normal-v0.5.json -> CONFORMANT_UNDER_LOADED_SPEC
cmrc-unknown-v0.5.json              -> INCOMPLETE_UNDER_LOADED_SPEC
```

## Why this is a narrow freeze

The TOC bottleneck was not whether #15 was real. It is real and confirmed.
The bottleneck was independent-family evidence, because a protocol frozen from
one bug path would risk turning an incidental local control-flow bug into a
general rule.

The second family is now closed:

```text
btrfs_grow_device()
-> btrfs_reserve_chunk_metadata()
-> btrfs_update_device()
-> btrfs_trans_release_chunk_metadata()
```

It is independent from #15 because it updates a chunk-tree device item rather
than allocating/publishing the block group in `reserve_chunk_space()`. It still
shares the same semantic lifecycle: chunk-tree metadata update, transaction
metadata reservation, and transaction release settlement.

Freeze result:

```text
candidate_ready = true
freeze_eligible = true
operation_family_count = 2
```

Still not claimed:

```text
held_out_generalization_eligible = false
cross_filesystem_generalization_eligible = false
```

## Runner

```powershell
python -m src.fmpca.chunk_candidate `
  --manifest configs/evaluation/cmrc-v0.5-readiness.json `
  --json-out outputs/fmpca-cmrc-v0.5-freeze-readiness/results.json `
  --markdown-out outputs/fmpca-cmrc-v0.5-freeze-readiness/report.md
```
