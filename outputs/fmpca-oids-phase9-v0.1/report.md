# OIDS Phase 9 COMMON Readiness Requalification

Manifest: `configs/evaluation/oids-phase9-common-freeze-v0.1.json`

COMMON candidate ready: `True`
COMMON freeze ready: `True`
COMMON freeze generated: `True`
Cross-filesystem claim allowed: `True`
COMMON held-out validated: `False`

## Freeze members

| Filesystem | Role | Profile | Source | Replay | Proof | Closed |
|---|---|---|---|---|---|---|
| btrfs | DEVELOPMENT | `ZERO_LINK_DELETION_AND_SUCCESSFUL_RW_RECOVERY_EXPOSURE` | `True` | `True` | `True` | `True` |
| ext4 | VALIDATION | `ERRORS_RO_OR_FAILSTOP` | `True` | `True` | `True` | `True` |
| ubifs | VALIDATION | `LIVE_DELETION_AND_SUCCESSFUL_RW_RECOVERY_EXPOSURE` | `True` | `True` | `True` | `True` |

## Gates

Failed candidate gates: none
Failed freeze gates: none
Failed held-out gates: heldout_correspondence_closed, heldout_proof_closure_closed, heldout_replay_closed, heldout_source_witness_closed, no_post_freeze_semantic_modifications, third_filesystem_post_freeze

## Decision

Phase 9 creates a COMMON NARROW_FREEZE for the unchanged OIDS protocol across Btrfs, ext4 ERRORS_RO_OR_FAILSTOP, and UBIFS live/successful-RW recovery. All candidate and freeze gates close with three independent operation families. Existing ext4 ERRORS_CONT and UBIFS read-only recovery boundaries remain explicit. UBIFS helped form the freeze and therefore is not post-COMMON held-out evidence; COMMON_HELDOUT_VALIDATED remains false.

Next held-out requirement: Preregister a different unrevealed filesystem after the Phase 9 COMMON freeze, before reading its source; lock the COMMON scope, protocol, checker, AcceptP, bindings, and tests.
