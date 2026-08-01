# P0.6 Evaluation Split

Version: `p0.6-v0.1`

## Development

| Cases | Use |
|---|---|
| #4, #5 | Develop `MetadataTransitionOutcome`, including success-after-failure and error-after-completion directions |
| #7, #16, #18 | Develop `FailureRollbackConformance` across attachment, transaction-list ownership, and container rollback |
| #15 | Develop the deferred `CompanionMetadataCompletion` candidate only; not used by the frozen v0.1 checker |

## Validation

| Cases | Use |
|---|---|
| #1, #2 | Validate that independent ext4 replay helpers satisfy the same outcome rule without new acceptance clauses |
| #17 | Validate active-pointer role projection of rollback conformance |
| #3, #6, #9-#12, #14 | Safe scope negatives: resource lifetime alone must produce `NO_APPLICABLE_PROTOCOL` |

## Held-Out

| Cases | Reveal policy |
|---|---|
| #8, #13 | Their expected checker result is evaluated only against the frozen catalog/config hash. A failure may add a reusable source binding or return `INCOMPLETE`; it may not change `AcceptP` while retaining held-out status. |

The historical corpus necessarily records that #8 and #13 are confirmed bugs.
The withheld information is their use in rule construction and source binding
calibration. Catalog rules and generic binding algorithms are frozen before
their evaluation output is generated.

Singleton candidate #15 has no honest held-out split. It is excluded from the
v0.1 catalog instead of being counted as generalization evidence.

