# FMPCA E6 CMRC Held-out Screening v0.5

Manifest: `configs\evaluation\e6-v0.5-heldout-screening.json`
Freeze ID: `fmpca-heldout-semantic-freeze-e6-v0.5`

Screening expectations passed: 2 / 2
Eligible held-out families: 1

| Candidate | Family | Decision | Eligible | Replay |
|---|---|---|---|---|
| btrfs-remove-chunk-v7.1 | btrfs-chunk-item-removal | `ELIGIBLE_HELD_OUT_REPLAY` | yes | 4/4 |
| btrfs-add-dev-item-v7.1 | btrfs-device-item-update | `REJECT_NOT_INDEPENDENT` | no | 0/0 |

## Screening Rejections

| Operation family | Status | Reason |
|---|---|---|
| btrfs-device-item-update | `REJECT_NOT_INDEPENDENT` | candidate belongs to a family already used for the v0.5 freeze |

## Guardrails

- Bug-specific condition count: `0`
- Protocol acceptance modifications: `0`
- Checker modifications after freeze: `0`
- E6 uses the frozen CMRC v0.5 protocol and binding unchanged.

E6 is a post-v0.5 held-out applicability screen for CMRC. It keeps the v0.5 protocol and binding frozen, then checks whether a third chunk-tree metadata family can close the same reservation/update/release lifecycle without being one of the two frozen v0.5 families.
