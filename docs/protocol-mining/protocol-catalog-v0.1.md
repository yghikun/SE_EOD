# FMPCA Protocol Catalog v0.1

Catalog status: `FROZEN`

Freeze date: 2026-07-31

## Protocol: MetadataTransitionOutcome

- ProtocolId: `fmpca.metadata_transition_outcome`
- SemanticIntent: ensure that the reported binary outcome agrees with the
  proven completion/failure state of one metadata transition at settlement.
- Roles: `operation`, `metadata_subject`, `outcome_owner`, optional
  `transaction_context`.
- AnchorRoles: `operation`, `metadata_subject`.
- EntryPredicates: the operation has a documented success/error partition;
  success means the required metadata transition completed, and no
  completed-with-error result is permitted by the loaded binding.
- Phases: `INITIAL`, `IN_PROGRESS`, `RETRYING`, `COMPLETED`, `FAILED`,
  `SETTLED`.
- TypedEvents: `Begin`, `MetadataStep`, `FailureObserved`, `RetryBegin`,
  `FailureSuperseded`, `TransitionComplete`, `ReportSuccess`, `ReportError`,
  `OperationReturn`.
- Transitions: `Begin` enters `IN_PROGRESS`; failure enters `FAILED` and
  activates MTO-O1; retry enters `RETRYING`; proven completion enters
  `COMPLETED`; report plus return enters `SETTLED`.
- RelationUpdates: maintain `completion` (`NONE|PARTIAL|COMPLETE`),
  `active_failure` (`true|false|unknown`), and `reported_outcome`.
- TemporalInvariants:
  - MTO-R1 at settlement: `reported_outcome == SUCCESS` implies
    `completion == COMPLETE` and `active_failure == false`.
  - MTO-R2 at settlement: `completion == COMPLETE` and
    `active_failure == false` imply `reported_outcome == SUCCESS`.
- SemanticObligations:
  - MTO-O1 `ReportFailureOrProveRecovery`: activated by `FailureObserved`;
    required formula is `ReportError OR (TransitionComplete AND
    FailureSuperseded)`; policy `MUST_DISCHARGE`.
- AllowedAuthorities: none for outcome reporting; the direct outcome owner
  must settle MTO-O1.
- Deadlines: MTO-O1 completion deadline `AT_SETTLEMENT(OperationReturn)`.
- CheckpointTriggers: `OperationReturn`, and `TransactionCommit` when commit
  occurs earlier and exposes the transition.
- TerminalSettlements: `OperationReturn`, `ProtocolComplete`.
- AcceptanceClauses: MTO-R1, MTO-R2, MTO-O1 discharged, no applicable
  irreversible contradiction, and exact/join-preserved evidence for
  completion and outcome.
- FrameConditions: resource releases and unrelated metadata fields do not
  change completion or outcome; a cleanup call does not supersede failure
  unless its typed event proves transition completion.
- SemanticFootprint: metadata writes/updates in the transition, result-variable
  provenance, retry control, transaction outcome, and return partition.
- EvidenceReferences: dossiers #4/#5 (development), #1/#2 (validation),
  #8/#13 (held-out); ext4/XFS v6.8-v7.1 diffs; trace rules MTO-R1/R2/O1/D1.

## Protocol: FailureRollbackConformance

- ProtocolId: `fmpca.failure_rollback_conformance`
- SemanticIntent: after a metadata operation mutates cross-object relations,
  failure must restore the relevant symbolic prestate or transfer every due
  restoration obligation to a permitted authority before its own deadline.
- Roles: `operation`, `container`, `participant`, optional `active_pointer`,
  `transaction_context`, `owner`, `rollback_authority`.
- AnchorRoles: `operation`, `container`; participant identity joins the key for
  per-member obligations.
- EntryPredicates: the prestate relation is known or explicitly unknown; at
  least one typed relation mutation is in the protocol footprint.
- Phases: `STABLE`, `MUTATING`, `FAILURE_OBSERVED`, `ROLLBACK_PENDING`,
  `DELEGATED`, `RESTORED`, `SETTLED`.
- TypedEvents: `SnapshotPrestate`, `Attach`, `Detach`, `MoveMember`,
  `RestoreMember`, `RebindActive`, `RestoreActive`, `AttachTransactionOwner`,
  `DetachTransactionOwner`, `FailureObserved`, `DelegateRollback`,
  `AuthorityComplete`, `ReleaseIsolation`, `LiveExposure`,
  `TransactionCommit`, `TransactionAbort`, `OperationReturn`,
  `OwnerTermination`.
- Transitions: a relation update enters `MUTATING`; failure activates one
  relation-specific FRC-O1 obligation per changed role; restore discharges only
  the matching obligation; permitted delegation enters `DELEGATED` but remains
  due until authority completion; all obligations discharged enters
  `RESTORED`; a deadline event enters `SETTLED`.
- RelationUpdates: symbolic prestate/current relation pairs, participant
  liveness, active-target validity, transaction ownership, authority claims,
  isolation and escape closure.
- TemporalInvariants:
  - FRC-I1 `ALWAYS`: every observable active target is live and role-valid.
  - FRC-I2 `BEFORE_EXPOSURE`: no relation in the footprint may reference a
    failed/released participant.
- SemanticObligations:
  - FRC-O1 `RestoreRelation`: activated by failure after a relation delta;
    required formula is current relation equals symbolic prestate; policy
    `MAY_DELEGATE_TO(teardown_owner, transaction_owner, recovery_owner)` only
    when authority scope covers the same relation.
  - FRC-O2 `CompleteDelegatedRollback`: activated by permitted delegation;
    required formula is authority completion for the delegated relation;
    policy `MUST_DISCHARGE`.
- AllowedAuthorities: protocol binding must prove an allowed authority and its
  footprint. Merely observing a transaction or fail-stop flag is insufficient.
- Deadlines: active-pointer validity `BEFORE_EXPOSURE`; transaction-list
  detachment `BEFORE_OWNER_TERMINATION`; container restoration
  `AT_SETTLEMENT(OperationReturn)`; delegated completion retains the original
  relation deadline.
- CheckpointTriggers: `ReleaseIsolation`, `LiveExposure`, `AuthorityTransfer`,
  `TransactionCommit`, `TransactionAbort`.
- TerminalSettlements: `OperationReturn`, `OwnerTermination`,
  `FailstopBoundary`, `ProtocolComplete`.
- AcceptanceClauses: FRC-I1/I2, all due FRC-O1/O2 obligations discharged,
  permitted delegation safe and in-scope, exposure safe, no irreversible stale
  relation witness, and exact/join-preserved proof closure.
- FrameConditions: generic resource release, transaction abort, or operation
  error does not restore unrelated relations; each relation delta is settled
  independently.
- SemanticFootprint: typed member/container relations, active pointers,
  update-list ownership, object liveness, transaction/recovery authority,
  isolation, escape and settlement events.
- EvidenceReferences: dossiers #7/#16/#18 (development), #17 (validation),
  QEMU Bug/safe report, sprout dynamic/fixed-run record; trace rules
  FRC-I1/O1/O2/D1.

## Catalog Boundary

`CompanionMetadataCompletion` is not frozen in v0.1. Membership remains a
synthetic DSL fixture only. Crash images, persistence ordering, general
durability, arbitrary interleavings, and complete heap/shape analysis are not
claimed. No protocol guard or acceptance clause contains a Bug ID, target
function name, source line, or patch identity.

