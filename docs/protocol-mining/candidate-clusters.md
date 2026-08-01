# P0.3 Candidate Protocol Clusters

Date: 2026-07-31

The clustering key is semantic failure shape, not filesystem, function, patch
series, or Bug ID. Bug IDs below are evidence references only.

## Cluster Decisions

| Candidate | Evidence cases | Independent operations / filesystems | Semantic core | Decision |
|---|---|---:|---|---|
| `MetadataTransitionOutcome` | #1, #2, #4, #5, #8, #13 | 6 operations / ext4 and XFS | completion phase, active failure provenance, and externally reported result must agree at settlement | FREEZE |
| `FailureRollbackConformance` | #7, #16, #17, #18 | 2 operations / Btrfs | failure after relational mutation creates restoration or permitted delegation obligations over all affected roles | FREEZE; merges the earlier attachment, transaction-responsibility, and rollback candidates |
| `CompanionMetadataCompletion` | #15 | 1 operation / Btrfs | publication/activation requires companion reservation | DEFER: singleton evidence cannot establish a reusable v0.1 protocol |

## Why The Rollback Candidates Merge

The earlier names `ActiveAttachmentSafety`, `TransactionResponsibility`, and
`FailureRollbackConformance` describe different role projections of one causal
structure:

1. An operation changes a relation before it can fail.
2. Failure activates a restoration obligation over the changed relation.
3. Local cleanup, transaction abort, or owner release may settle only part of
   that obligation.
4. Acceptance requires restoration of the protocol prestate or explicit,
   deadline-bounded delegation to an authority that owns the same semantic
   footprint.

Bug #7 changes the `fs_root`/`reloc_root` attachment. Bugs #16-#18 change update
list ownership, active pointers, and container membership/identity during one
sprout transition. The role vocabulary differs; the obligation and deadline
logic is the same. A single relational protocol therefore removes duplication
without adding a Bug-specific phase.

## Selection Score

Scores use 0 (weak) to 3 (strong). Lower analysis cost is scored higher.

| Candidate | FS metadata specificity | Confirmed cases | Cross-operation reuse | Beyond local pairing | Safe/fixed evidence | Analysis feasibility | Bug-specific bindings | Replay certainty | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `MetadataTransitionOutcome` | 2 | 3 | 3 | 2 | 3 | 3 | 3 | 3 | 22 |
| `FailureRollbackConformance` | 3 | 2 | 2 | 3 | 3 | 2 | 3 | 2 | 20 |
| `CompanionMetadataCompletion` | 3 | 1 | 0 | 2 | 2 | 3 | 2 | 2 | 15 |

`MetadataTransitionOutcome` is the engineering entry and cross-filesystem
control. `FailureRollbackConformance` carries the stronger filesystem-specific
relational and responsibility contribution. Neither protocol relies on a
target function name in its acceptance rules.

