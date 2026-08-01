# Domain Traceability Matrix v0.5

| Rule | Design/source semantics | Negative witness | Repaired/safe | Boundary |
|---|---|---|---|---|
| CMRC-I1 | `btrfs_zoned_activate_one_bg()` can return `1` as success while reservation uses `!ret` as the success guard | Bug #15 positive-success path skips reservation | fixed replay normalizes success before reservation | success-domain compatibility, not raw return equality |
| CMRC-I2 | chunk-tree metadata update and transaction reservation accounting must both be visible in the source footprint | publication/update without a matching reservation footprint is not enough for conformance | `reserve_chunk_space()` and `btrfs_grow_device()` source witnesses close update + reservation + release footprints | source witness must be structural, not Bug-ID selected |
| CMRC-I3 | committed chunk-tree metadata update requires `chunk_metadata_reservation.completed=true` | Bug #15 commits after skipped reservation | normal/fixed reservation replay and device-item update replay | `BEFORE_COMMIT` |
| CMRC-O1 | publication/update activates a nondelegable reservation obligation | `ChunkReservationSkipped` leaves obligation live at commit | `ChunkMetadataReserved` discharges the obligation | `MUST_DISCHARGE` before commit |

No rule or binding contains a Bug ID, patch ID, target line, source line, or
case-specific acceptance clause.

