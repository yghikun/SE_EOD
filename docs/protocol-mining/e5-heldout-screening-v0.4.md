# E5 Held-out Screening v0.4

Date: 2026-08-01. Target: frozen WDC/DTC v0.4.

## First-principles criterion

A post-freeze held-out family must test the same semantic object, not merely a
nearby filesystem function. For WDC/DTC the object is:

```text
device membership/writable/allocation eligibility
-> device capacity contribution
-> aggregate total_rw_bytes/free_chunk_space delta
-> failure or release-time settlement
```

The required shared identity is `operation + device`. A candidate without a
device identity cannot validate WDC/DTC composition, even if it is Btrfs,
capacity-adjacent, or a confirmed metadata bug.

## Candidates screened

| Candidate | Operation family | Source witness | Decision |
|---|---|---|---|
| `btrfs_grow_device()` | Btrfs device grow | Linux v7.1 `fs/btrfs/volumes.c` | `REJECT_BINDING_GAP` |
| `btrfs_rm_device()` | Btrfs device remove | Linux v7.1 `fs/btrfs/volumes.c` | `REJECT_BINDING_GAP` |
| `btrfs_dev_replace_finishing()` | Btrfs device replace finish | Linux v7.1 `fs/btrfs/dev-replace.c` | `REJECT_OUTSIDE_WDC_DTC_FOOTPRINT` |
| #15 `reserve_chunk_space()` | Btrfs chunk metadata reservation | Linux v6.14 `fs/btrfs/block-group.c` | `REJECT_OUTSIDE_WDC_DTC_FOOTPRINT` |

## Causal chain

### Device grow

```text
btrfs_grow_device binds operation + device
-> it checks BTRFS_DEV_STATE_WRITEABLE
-> it increases fs_devices->total_rw_bytes and fs_info->free_chunk_space by diff
-> local source has no symmetric failure settlement for the already-mutated diff
-> the frozen WDC binding cannot close same-delta rollback/replay evidence
-> this is a binding/closure gap, not proof that WDC needs a new rule
```

### Device remove

```text
btrfs_rm_device removes the writable device from allocation membership locally
-> it delegates capacity removal to btrfs_shrink_device(device, 0)
-> local error_undo restores membership/rw_devices after shrink failure
-> the selected operation root does not expose the total_rw_bytes/free_chunk_space
   contribution delta required by the frozen WDC binding
-> this may become useful with an interprocedural WDC summary
-> current E5 cannot replay it as a held-out family
```

### Device replace finish

```text
btrfs_dev_replace_finishing swaps source and target device identity
-> target inherits devid/uuid/total_bytes/bytes_used
-> target is added to the allocation list and source is removed
-> net writable capacity contribution is intended to remain unchanged
-> the semantic object is identity/topology substitution, not aggregate capacity delta
-> this is outside the WDC/DTC held-out footprint
```

### Chunk metadata reservation (#15)

```text
reserve_chunk_space publishes/queues a new chunk/block group
-> zoned activation returns positive success
-> the positive return is reused as the later reservation condition
-> chunk metadata reservation is skipped
-> the failing relation is chunk publication/reservation completion
-> the anchor object is block_group/transaction, not device
-> WDC's device contribution equations cannot bind the source path
-> DTC's shared operation+device identity cannot close
-> the candidate is real, but not a WDC/DTC held-out case
```

## Machine result

Executable manifest:
`configs/evaluation/e5-v0.4-heldout-screening.json`.

Runner:

```powershell
python -m src.fmpca.heldout_v4 `
  --manifest configs/evaluation/e5-v0.4-heldout-screening.json `
  --json-out outputs/fmpca-e5-v0.4-heldout-screening/results.json `
  --markdown-out outputs/fmpca-e5-v0.4-heldout-screening/report.md
```

Current result:

```text
total_candidates = 4
eligible_candidate_count = 0
rejected_candidate_count = 4
held_out_operation_families = []
protocol_acceptance_modifications = 0
checker_modifications_after_freeze = 0
bug_specific_condition_count = 0
```

## Decision

E5 remains a negative held-out applicability validation for WDC/DTC v0.4.
The grow/remove/replace screening does not justify changing frozen WDC/DTC:
grow and remove fail under the existing binding/closure budget, while
replace-finish is a topology/identity substitution with no aggregate
capacity-delta obligation. The confirmed #15 bug is retained as evidence for a future
`ChunkMetadataReservationCompletion` or broader companion-metadata protocol,
not as held-out generalization evidence for WDC/DTC.
