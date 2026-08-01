# Guarded Interprocedural Summary Semantics 0.1

## Summary Relation

```text
Summary_f(input_state) = {
  <guard, outcome, delta, obligations, claims, isolation, precision>, ...
}
```

A summary is a finite guarded relation, not one merged effect set. Each row
contains:

- a DSL formula guard over projected input facts;
- an outcome partition (`SUCCESS`, `ERROR`, `RETRY`, `DEFERRED`, `UNKNOWN`);
- relation deltas and typed events;
- activated/discharged/delegated obligations;
- authority claims and their semantic footprints;
- isolation/escape changes;
- precision provenance.

## Call Application

1. Project caller roles, relations, obligations, transaction context, and
   isolation facts named by the callee footprint.
2. Evaluate every summary guard.
3. Apply each true row; fork unknown rows within budget.
4. Replay row events through ordinary transfer semantics.
5. Project resulting role identities, deltas, obligations, and claims back to
   the caller.
6. Preserve unmatched caller state through frame conditions.

Only an operation root may load protocol entry assumptions. A helper inherits
the caller's intermediate state and cannot restart the protocol from a clean
prestate.

## Composition

Summary composition is relational composition with guard conjunction and
event/delta concatenation. Incompatible guards are dropped. Obligation
composition is conservative: an upstream open obligation remains open unless
the downstream row discharges the same template and relation under
`MUST_ALIAS` identity.

## Recursion And Fixed Point

Recursive strongly connected components iterate from the empty relation.
After the configurable iteration budget, relation values and guards may widen.
Open obligations and irreversible evidence are never widened away. A widened
recursive summary can support an exact violation witness outside the widened
components but cannot prove conformance.

## Transactions And Authority

`TransactionCommit` and `TransactionAbort` occupy distinct outcome partitions.
Neither implies completion or rollback of all relation deltas. A summary may
emit a delegation claim only when it names an allowed authority and the exact
semantic footprint that authority accepts. Caller projection retains the
original completion deadline.

## Unknown Helpers

If a helper may write the semantic footprint but no summary is available, emit
an unknown delta and `UNKNOWN` precision. This blocks conformance and normally
blocks violation unless an independent exact must-fact already closes the
violation witness. A helper outside the footprint is framed without penalty.

