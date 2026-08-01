# FMPCA Abstract Domain And Transfer Semantics 0.1

## State Product

```text
ProtocolState = <
  SymbolicPreState,
  Phase,
  RoleBindings,
  RelationFacts,
  OperationLocalDeltas,
  Obligations,
  AuthorityClaims,
  TransactionContext,
  IsolationEvidence,
  Observability,
  Outcome,
  IrreversibleViolationEvidence,
  PrecisionProvenance
>
```

Relations map names to `Fact(value, precision, sources)`. Precision order is:

```text
EXACT > JOIN_PRESERVED > WIDENED > UNKNOWN
```

The value lattice is a flat constant lattice with `BOTTOM`, one or more exact
constants, and `TOP`. Joining equal exact constants preserves the value and
uses `JOIN_PRESERVED`; joining unequal constants yields `TOP/WIDENED`.

## Component Orders

- Phase: equal phase remains exact; unequal phases join to the least declared
  common phase when provided, otherwise `UNKNOWN_PHASE`.
- Role binding: same identity remains bound; different identities follow alias
  policy and otherwise become a candidate split or unknown binding.
- Delta: union keyed by relation and generation; conflicting before/after
  values widen only that delta.
- Obligation: `OPEN` dominates `DELEGATED`, which dominates `DISCHARGED` for
  acceptance conservatism. Conflicting statuses join to the less settled one.
- Isolation: `CLOSED` and `ESCAPED` conflict to `INCOMPLETE`.
- Outcome: unequal outcomes join to `UNKNOWN`.
- Irreversible evidence: set union; evidence is never removed by join.

## Transfer

For event `e` and state `s`:

1. Verify required event roles and reconstruct/select an instance.
2. Select transitions whose event and source phase match.
3. Evaluate each guard in three-valued logic.
4. `FALSE` transitions are ignored; `TRUE` transitions apply actions;
   `UNKNOWN` guards fork if budget permits, otherwise widen affected facts.
5. Apply actions in listed order to a copied state.
6. Record event provenance and update the phase.
7. Evaluate every `ALWAYS` invariant.
8. If `e` is a checkpoint or terminal event, evaluate rules and obligations
   due at that deadline.

An `ALWAYS` invariant cannot be postponed by locks, transactions, or closed
isolation. Other rules may defer only when `RelevantEscapeClosure == CLOSED`
and the protocol declares a later deadline.

## Deadline Order

Deadlines are partially ordered by the event trace, not by a universal numeric
ranking. The implementation recognizes:

```text
ALWAYS
BEFORE_EXPOSURE
BEFORE_COMMIT
AT_SETTLEMENT
BEFORE_OWNER_TERMINATION
```

An obligation becomes due when its matching event occurs. The same relation
may have multiple deadlines; the earliest reached deadline controls.

## Settlement

Checkpoint events:

```text
ReleaseIsolation
LiveExposure
AuthorityTransfer
TransactionCommit
TransactionAbort
```

Terminal events:

```text
OperationReturn
OwnerTermination
FailstopBoundary
ProtocolComplete
```

`TransactionAbort` is a typed event, not a global reset. `AuthorityTransfer`
changes responsibility but does not terminate an instance.

## Acceptance

At a reached deadline:

```text
AcceptP =
  AlwaysInvariantsHold
  and DueNonDelegableConditionsHold
  and DueObligationsDischargedOrPermittedDelegated
  and DelegationSafetyHolds
  and ExposureSafe
  and PhaseOutcomeCompatible
  and NoApplicableIrreversibleViolation
  and protocol.acceptance_formula
```

The evaluator returns the value and provenance of each clause. Overall
acceptance is `TRUE` only when every clause is `TRUE`; any `FALSE` is rejection;
otherwise the result is `UNKNOWN`.

## Widening

Widening applies after a configurable per-instance event/loop budget. It may
widen repeated relation values, delta counts, and phases, but it never changes
an open obligation to discharged or removes irreversible evidence. A widened
state can establish a violation only from unaffected exact must-facts; it
cannot establish conformance.

