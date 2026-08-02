# OIDS Phase 14 v0.2 Diagnostic and Failure-contract Implementation

## Architecture

OIDS v0.2 is implemented as a separately validated diagnostic extension over the byte-frozen v0.1 executable protocol. The strict v0.1 DSL remains unchanged. The extension hash-locks the base protocol and the canonical OIDS-O1/OIDS-O3 obligation objects.

```text
v0.1 executable protocol
-> unchanged transitions, obligations, deadlines, AcceptP and results

v0.2 diagnostic extension
-> evidence levels
-> failure-cause taxonomy
-> repair obligations
-> safe-outcome alternatives
-> diagnostic mappings
```

The extension cannot discharge an obligation, prove a repair, or change applicability.

## Failure causes

| Cause | Rule | Stage | Unsafe checkpoint |
|---|---|---|---|
| `REGISTRATION_ACCEPTANCE_ERROR_SUPPRESSION` | OIDS-O1 | registration | `RegistrationTransactionCommit` |
| `RECOVERY_CLEANUP_ERROR_SUPPRESSION` | OIDS-O3 | recovery | `RecoveryExposure` |

A diagnostic requires all trigger facts for its cause and all facts required by its evidence level. Removing any required evidence fact makes the diagnostic incomplete.

## Repair obligations

### Registration acceptance failure

`REGISTRATION_ACCEPTANCE_FAILURE_CONTRACT` exposes three safe alternatives:

1. propagate failure and prevent namespace commit;
2. prove abort or rollback of the final-link transition;
3. enter failstop and prevent unsafe success exposure.

### Recovery cleanup failure

`RECOVERY_CLEANUP_FAILURE_EXPOSURE_CONTRACT` exposes three safe alternatives:

1. propagate mount failure and prevent root exposure;
2. enter failstop/read-only containment while retaining cleanup responsibility;
3. prove authority, safety, and timing for delegation before exposure.

Each alternative has explicit required facts. Merely recommending an alternative does not prove it was implemented.

## ReiserFS development mapping

Both Phase 13 source-confirmed bugs map successfully to their cause and repair obligation. Their evidence is complete at the source-confirmed level, but neither implementation provides facts proving a safe repair alternative.

```text
OIDS-O1 diagnostic_closed = true
OIDS-O1 proven_safe_alternatives = []
OIDS-O1 repair_status = REQUIRED_NOT_IMPLEMENTED

OIDS-O3 diagnostic_closed = true
OIDS-O3 proven_safe_alternatives = []
OIDS-O3 repair_status = REQUIRED_NOT_IMPLEMENTED
```

Both v0.1 minimal replays remain `VIOLATION_UNDER_LOADED_SPEC`.

## Regression boundaries

| Filesystem | Required boundary | Phase 14 result |
|---|---|---|
| Btrfs | qualified successful profile | preserved |
| ext4 | failstop positive plus `ERRORS_CONT` negative witnesses | preserved |
| UBIFS | live/RW positive plus read-only deferred boundary | preserved |
| OCFS2 | non-applicable / `DEADLINE_NOT_ALIGNED` | preserved |

The diagnostic extension adds no applicability predicate. Success-dependent predicates remain rejected.

## Held-out boundary

The v0.2 held-out partition remains empty. Phase 14 implements and regression-tests diagnostics only:

```text
heldout_validation_allowed = false
common_v0_2_validated = false
```

A separate preregistration must select and lock a genuinely unrevealed filesystem before any new source is read.

