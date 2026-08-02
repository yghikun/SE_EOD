# OIDS Phase 14 v0.2 Diagnostic and Failure-contract Implementation

Manifest: `configs/evaluation/oids-phase14-v0.2-diagnostic-v0.1.json`

Diagnostic implementation closed: `True`
v0.1 mutated: `False`
Held-out validation allowed: `False`

## Development diagnostics

| Case | Rule | Cause | Repair obligation | Safe alternatives proven | Closed |
|---|---|---|---|---|---|
| REISERFS_SAVE_LINK_ENOSPC_UNPROPAGATED | OIDS-O1 | REGISTRATION_ACCEPTANCE_ERROR_SUPPRESSION | REGISTRATION_ACCEPTANCE_FAILURE_CONTRACT | 0 | `True` |
| REISERFS_RECOVERY_ERROR_EXPOSURE_REACHABLE | OIDS-O3 | RECOVERY_CLEANUP_ERROR_SUPPRESSION | RECOVERY_CLEANUP_FAILURE_EXPOSURE_CONTRACT | 0 | `True` |

## Regression boundaries

| Filesystem | Boundary | Actual | Preserved |
|---|---|---|---|
| btrfs | QUALIFIED_SUCCESSFUL_PROFILE | CLOSED | `True` |
| ext4 | FAILSTOP_POSITIVE_AND_ERRORS_CONT_NEGATIVE | PRESERVED | `True` |
| ubifs | LIVE_RW_POSITIVE_AND_READ_ONLY_DEFERRED | PRESERVED | `True` |
| ocfs2 | NON_APPLICABLE_DEADLINE_NOT_ALIGNED | PRESERVED | `True` |

## Interpretation

OIDS v0.2 now provides a validated diagnostic extension over the unchanged v0.1 protocol. It classifies registration and recovery error suppression, maps each ReiserFS development bug to a machine-readable repair obligation and three evidence-bearing safe alternatives, and rejects incomplete evidence. No safe alternative is proven in the evaluated ReiserFS source, so OIDS-O1 and OIDS-O3 remain violations. Btrfs, ext4, UBIFS, and OCFS2 regression boundaries are preserved, applicability is unchanged, and v0.2 held-out validation remains disabled.

Next phase: Phase 15 will freeze the Phase 14 v0.2 diagnostic and regression baseline, audit the unrevealed candidate pool without reading candidate source, and create a separate pre-reveal held-out preregistration. Only after that lock may the selected filesystem source be acquired for a new applicability and diagnostic evaluation.
