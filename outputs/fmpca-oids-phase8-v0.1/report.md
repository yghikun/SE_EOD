# OIDS Phase 8 UBIFS Independent-family Validation

Manifest: `configs/evaluation/oids-phase8-ubifs-validation-v0.1.json`

Applicability: `APPLICABLE`
Candidate validation closed: `True`
Validated recovery profile: `SUCCESSFUL_RW_RECOVERY_EXPOSURE`
Read-only profile: `RECOVERY_DEFERRED_OUTSIDE_VALIDATED_RW_EXPOSURE`
Phase 7 scope unchanged: `True`
COMMON freeze generated: `False`
Preregistered blind independent-family claim: `True`
COMMON held-out validated: `False`

## Source proof

| Stage | Status | Partitions |
|---|---|---|
| registration | `CLOSED` | pre_write_failure_rollback, successful_journal_group, post_write_failure_read_only_failstop, commit_generation_persistence |
| settlement | `CLOSED` | no_intervening_commit, intervening_commit, orphan_owned_by_active_commit, settlement_error_failstop |
| recovery | `CLOSED` | uncommitted_journal_deletion, committed_orphan_area_deletion, successful_rw_recovery, read_only_recovery_deferred |

## Correspondence

| Dimension | Status |
|---|---|
| object | `CLOSED` |
| relation | `CLOSED` |
| lifecycle | `CLOSED` |
| authority | `CLOSED` |
| deadline | `CLOSED` |

## Replay

| Profile | Expected | Actual | Closed |
|---|---|---|---|
| LIVE_NO_INTERVENING_COMMIT | `CONFORMANT_UNDER_LOADED_SPEC` | `CONFORMANT_UNDER_LOADED_SPEC` | `True` |
| LIVE_POST_COMMIT | `CONFORMANT_UNDER_LOADED_SPEC` | `CONFORMANT_UNDER_LOADED_SPEC` | `True` |
| SUCCESSFUL_RW_RECOVERY_EXPOSURE | `CONFORMANT_UNDER_LOADED_SPEC` | `CONFORMANT_UNDER_LOADED_SPEC` | `True` |
| RECOVERY_DEFERRED_OUTSIDE_VALIDATED_RW_EXPOSURE | `INCOMPLETE_UNDER_LOADED_SPEC` | `INCOMPLETE_UNDER_LOADED_SPEC` | `True` |

## Decision

UBIFS is APPLICABLE to the locked OIDS semantics for live deletion and successful RW recovery exposure. Journal deletion nodes cover pre-commit recovery, the persistent orphan area covers committed zero-link inodes, and RW recovery commits TNC orphan deletions before root exposure. Read-only recovery is explicitly deferred and is preserved as INCOMPLETE rather than promoted to settlement. The preregistered source qualifies as a blind independent-family validation, but not as COMMON_HELDOUT_VALIDATED because Phase 7 has no COMMON freeze. Phase 7 remains an ext4-only narrow freeze and this result does not generate a COMMON freeze.
