# OIDS Phase 11 ReiserFS Post-COMMON Held-out Evaluation

Manifest: `configs/evaluation/oids-phase11-reiserfs-heldout-v0.1.json`

Applicability: `APPLICABLE`
Conformance decision: `NON_CONFORMANT_HELDOUT`
Screening closed: `True`
Candidate conformant: `False`
COMMON held-out validated: `False`

## Source stages

| Stage | Status | Closed |
|---|---|---|
| registration | `CLOSED` | `True` |
| settlement | `CLOSED` | `True` |
| recovery | `CLOSED` | `True` |

## Failure partitions

| Profile | Stage | Result | Rule |
|---|---|---|---|
| SAVE_LINK_ENOSPC_UNPROPAGATED | registration | `VIOLATION_UNDER_LOADED_SPEC` | OIDS-O1 |
| SAVE_LINK_REMOVAL_ERROR_IGNORED | settlement | `INCOMPLETE_UNDER_LOADED_SPEC` | - |
| RECOVERY_ERROR_EXPOSURE_REACHABLE | recovery | `VIOLATION_UNDER_LOADED_SPEC` | OIDS-O3 |

## Correspondence

| Dimension | Status | Closed |
|---|---|---|
| object | `CLOSED` | `True` |
| relation | `CLOSED` | `True` |
| lifecycle | `CLOSED` | `True` |
| authority | `CLOSED` | `True` |
| deadline | `CLOSED` | `True` |

## Replay

| Profile | Expected | Actual | Closed |
|---|---|---|---|
| SUCCESSFUL_LIVE_DELETION | `CONFORMANT_UNDER_LOADED_SPEC` | `CONFORMANT_UNDER_LOADED_SPEC` | `True` |
| SUCCESSFUL_RW_RECOVERY_EXPOSURE | `CONFORMANT_UNDER_LOADED_SPEC` | `CONFORMANT_UNDER_LOADED_SPEC` | `True` |
| SAVE_LINK_ENOSPC_UNPROPAGATED | `VIOLATION_UNDER_LOADED_SPEC` | `VIOLATION_UNDER_LOADED_SPEC` | `True` |
| SAVE_LINK_REMOVAL_ERROR_IGNORED | `INCOMPLETE_UNDER_LOADED_SPEC` | `INCOMPLETE_UNDER_LOADED_SPEC` | `True` |
| RECOVERY_ERROR_EXPOSURE_REACHABLE | `VIOLATION_UNDER_LOADED_SPEC` | `VIOLATION_UNDER_LOADED_SPEC` | `True` |

## Decision

ReiserFS is a valid post-COMMON blind held-out candidate and all five OIDS correspondence dimensions close. Its successful live deletion and successful RW recovery profiles conform under the unchanged specification. The full candidate is nevertheless NON_CONFORMANT_HELDOUT: add_save_link can lose ENOSPC while unlink commits, producing OIDS-O1, and finish_unfinished can return cleanup failure that fill_super ignores before successful exposure, producing OIDS-O3. A save-link retirement error is additionally retained as incomplete. Phase 11 therefore closes the screening procedure without establishing COMMON_HELDOUT_VALIDATED, while preserving the Phase 9 COMMON narrow freeze byte-for-byte.

Outcome-dependent narrowing rejected: The success of add_save_link, remove_save_link, or finish_unfinished is an execution outcome, not a pre-existing filesystem/profile applicability predicate. Those failure paths remain inside the frozen Phase 9 COMMON scope.

Next phase: Phase 12 will freeze the Phase 11 counterexample result, build a cross-filesystem claim-disposition matrix, independently audit the OIDS-O1 and OIDS-O3 source-to-replay slices, and separate COMMON semantic applicability from COMMON conformance. Any repaired protocol must be a new version with a new evaluation split; v0.1 will not be changed post hoc.
