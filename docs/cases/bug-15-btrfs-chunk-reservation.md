# Bug #15: Btrfs Chunk Metadata Reservation Completion

Status: `CATALOG_V0.5_NARROW_FREEZE`. The confirmed bug path remains the
development counterexample; the Catalog v0.5 freeze is justified only after
adding an independent `btrfs_grow_device()` device-item update family as
sibling source evidence.

## Evidence

- Historical record: `docs/corpus/confirmed-bugs-source.md`, Bug #15.
- Source: Linux v6.14 `fs/btrfs/block-group.c`, `reserve_chunk_space()` at
  line 4226.
- Dynamic evidence: host-managed zoned `null_blk` returned positive success;
  metadata reservation was skipped before the fix and reached 393216 bytes
  after normalizing success.
- Patch v2 and Reviewed-by are linked in the source record.

## Unified Semantic Record

- OperationRoot: Btrfs chunk allocation/reservation operation.
- Roles: new block group, transaction, chunk item, chunk block reserve.
- Candidate anchors: transaction epoch plus block-group identity.
- Entry assumptions: a new system chunk is created and zoned activation
  returns nonnegative success.
- Typed events: `CreateChunk`, `ActivationComplete`, `PublishChunkItem`,
  `ReservationRequired`, `OperationReturn`.
- Relation/local deltas: block group is published and queued on `new_bgs`.
- Obligation: published chunk metadata requires corresponding transaction
  reservation accounting.
- Isolation/observability: transaction-local; must hold before commit.
- Responsibility transfer: transaction owns the reservation obligation.
- Outcome/terminal: activation succeeds but companion reservation is absent.
- Deadline: `BEFORE_COMMIT`.
