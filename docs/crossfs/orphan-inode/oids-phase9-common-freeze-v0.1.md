# OIDS Phase 9 COMMON Narrow Freeze

Status: `QUALIFIED_COMMON_NARROW_FREEZE`.

The unchanged OIDS candidate semantics now close across Btrfs, an explicitly
qualified ext4 failstop profile, and an explicitly qualified UBIFS live/RW
profile. This is a COMMON claim over the shared semantic footprint, not a claim
that every configuration of every filesystem conforms.

## Frozen semantic footprint

```text
zero-link namespace detachment
-> persistent cleanup responsibility accepted before commit
-> final eviction or recovery owns terminal deletion
-> registry removal only after prior durable or atomic terminal settlement
-> successful RW recovery completes before normal exposure
```

The canonical protocol, checker, AcceptP, historical taxonomy, and Phase 7
scope bytes are unchanged. Phase 9 adds a new scope declaration instead of
rewriting historical evidence.

## Freeze members

| Filesystem | Role | Independent operation family | Qualified profile |
|---|---|---|---|
| Btrfs | `DEVELOPMENT` | orphan-item transaction | zero-link deletion and successful RW recovery exposure |
| ext4 | `VALIDATION` | orphan-file/list with JBD2 failstop | `error_policy != ERRORS_CONT` |
| UBIFS | `VALIDATION` | journal plus persistent orphan-area commit | live deletion and successful RW recovery exposure |

All five correspondence dimensions, source witnesses, replay partitions, and
proof closures are true for every freeze member. The operation-family names are
distinct and the historical taxonomy executable gate reports:

```text
common_candidate_ready = true
minimum_two_applicable_filesystems = true
all_correspondence_dimensions_closed = true
independent_operation_family_per_filesystem = true
source_witness_closed_per_filesystem = true
replay_closed_per_filesystem = true
proof_closure_closed_per_filesystem = true
protocol_binding_test_hashes_locked = true
common_freeze_ready = true
```

## Configuration boundaries

ext4 `ERRORS_CONT` remains excluded by the Phase 6 OIDS-O1/O2/O3 negative
witnesses. It is not erased or reinterpreted by the COMMON promotion.

UBIFS read-only recovery remains
`RECOVERY_DEFERRED_OUTSIDE_VALIDATED_RW_EXPOSURE`. Its current TNC view is
cleaned while persistent settlement is deferred, so it is not counted as a
completed COMMON recovery exposure.

The freeze boundary is therefore `NARROW_FREEZE`. Cross-filesystem applicability
is allowed only when the relevant per-filesystem predicate is satisfied.

## Temporal held-out policy

UBIFS was preregistered before source reveal, so its Phase 8 blind independent-
family provenance remains valid. In Phase 9 it participates in forming the
COMMON freeze and has validation role `VALIDATION`, not `HELD_OUT`.

Consequently:

```text
common_freeze_manifest_generated = true
cross_filesystem_claim_allowed = true
common_heldout_validated = false
ubifs_counts_as_post_common_heldout = false
```

A later `COMMON_HELDOUT_VALIDATED` claim requires a different filesystem whose
source is not read until after this Phase 9 freeze and its protocol, binding-
independent checker, AcceptP, scope, and test hashes are preregistered.
