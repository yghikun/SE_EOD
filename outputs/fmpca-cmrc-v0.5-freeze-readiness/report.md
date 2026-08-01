# ChunkMetadataReservationCompletion Freeze Readiness v0.5

Manifest: `configs\evaluation\cmrc-v0.5-readiness.json`

Candidate ready: `True`
Freeze eligible: `True`
Freeze ID: `fmpca-domain-semantic-freeze-v0.5`
Replay: 5 / 5
Second-family screening: 1 / 1

## Replay

| Case | Role | Expected | Actual | Pass |
|---|---|---|---|---|
| cmrc-bug-positive-zoned-success | BUG | `VIOLATION_UNDER_LOADED_SPEC` | `VIOLATION_UNDER_LOADED_SPEC` | PASS |
| cmrc-fixed-normalized-success | FIXED_OR_REPAIR | `CONFORMANT_UNDER_LOADED_SPEC` | `CONFORMANT_UNDER_LOADED_SPEC` | PASS |
| cmrc-normal-chunk-allocation | NORMAL | `CONFORMANT_UNDER_LOADED_SPEC` | `CONFORMANT_UNDER_LOADED_SPEC` | PASS |
| cmrc-second-family-device-item-update | SIBLING_NORMAL | `CONFORMANT_UNDER_LOADED_SPEC` | `CONFORMANT_UNDER_LOADED_SPEC` | PASS |
| cmrc-unknown-no-commit-closure | UNKNOWN | `INCOMPLETE_UNDER_LOADED_SPEC` | `INCOMPLETE_UNDER_LOADED_SPEC` | PASS |

## Second-family screening

| Candidate | Family | Source witness closed | Independent | Pass |
|---|---|---|---|---|
| btrfs-device-item-update-grow-v7.1 | btrfs-device-item-update | `True` | `True` | PASS |

## Gates

| Gate | Value |
|---|---|
| `binding_has_no_case_specialization` | `True` |
| `candidate_ready` | `True` |
| `confirmed_bug_source_witness` | `True` |
| `normal_release_settlement_witness` | `True` |
| `paired_semantic_replay` | `True` |
| `protocol_validated` | `True` |
| `second_family_source_witness_closed` | `True` |
| `second_independent_family_available` | `True` |
| `source_semantic_footprint_closed` | `True` |

## Freeze blockers

none

## Source witness

- Bug path closed: `True`
- Release settlement closed: `True`
- Bug-specific condition count: `0`

CMRC v0.5 is a narrowly frozen Catalog entry. The #15 bug path, fixed/normal/unknown replay, release settlement and second independent device-item update family are closed enough for cross-operation-family qualification; no held-out or cross-filesystem generalization claim is made.
