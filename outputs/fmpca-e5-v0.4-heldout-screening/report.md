# FMPCA E5 Held-out Screening v0.4

Manifest: `configs\evaluation\e5-v0.4-heldout-screening.json`

Screening expectations passed: 4 / 4
Eligible held-out families: 0

| Candidate | Family | Decision | Eligible |
|---|---|---|---|
| btrfs-device-grow-v7.1 | btrfs-device-grow | `REJECT_BINDING_GAP` | no |
| btrfs-device-remove-v7.1 | btrfs-device-remove | `REJECT_BINDING_GAP` | no |
| btrfs-device-replace-finish-v7.1 | btrfs-device-replace-finish | `REJECT_OUTSIDE_WDC_DTC_FOOTPRINT` | no |
| bug-15-btrfs-chunk-metadata-reservation | btrfs-chunk-metadata-reservation | `REJECT_OUTSIDE_WDC_DTC_FOOTPRINT` | no |

## Screening Rejections

| Operation family | Status | Reason |
|---|---|---|
| btrfs-device-grow | `REJECT_BINDING_GAP` | the existing WDC binding cannot produce a closed source witness for operation_family=unknown-device-capacity-operation |
| btrfs-device-remove | `REJECT_BINDING_GAP` | the existing WDC binding cannot produce a closed source witness for operation_family=device-membership-change |
| btrfs-device-replace-finish | `REJECT_OUTSIDE_WDC_DTC_FOOTPRINT` | candidate does not bind the frozen device-capacity object model: footprint_gap=['device_identity_substitution', 'replace_target_state'], missing_identity_roles=[] |
| btrfs-chunk-metadata-reservation | `REJECT_OUTSIDE_WDC_DTC_FOOTPRINT` | candidate does not bind the frozen device-capacity object model: footprint_gap=['chunk_block_reservation', 'chunk_item_publication', 'transaction_chunk_bytes_reserved', 'zoned_activation_result'], missing_identity_roles=['device'] |

## Guardrails

- Freeze ID: `fmpca-heldout-semantic-freeze-e5-v0.4`
- Bug-specific condition count: `0`
- Protocol acceptance modifications: `0`
- Checker modifications after freeze: `0`
- Rejected candidates are not replayed as held-out evidence.

E5 is a post-v0.4 held-out applicability screen. It uses the frozen WDC/DTC semantics and binding unchanged. Confirmed or source-motivated candidates that do not bind the frozen device-capacity footprint are rejected as future protocol candidates rather than replayed as held-out evidence.
