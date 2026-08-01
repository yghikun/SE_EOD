# Violation And Conformance Proof Closure 0.1

## Separate Proof Obligations

```text
ViolationProofClosure(instance, witness_path)
ConformanceProofClosure(instance, operation_root)
```

Violation is existential over one feasible witness. Conformance is universal
over all relevant reachable paths. They intentionally use different closure
requirements.

## Influence And Repair Slices

The protocol semantic footprint seeds an influence slice from typed field/API
events, aliases, possible writes, and callee summaries. When a rule first
becomes false, its repair slice contains only operations that can restore or
validly delegate the affected formula before the corresponding deadline.

Cleanup after the deadline cannot repair an earlier live exposure or other
irreversible witness. Absence of an observed escape is not a closed escape
proof; closure is `CLOSED`, `ESCAPED`, or `INCOMPLETE`.

## Violation Closure

A violation is closed when all conditions hold:

1. the witness path is feasible under the path model;
2. the instance anchors are exact enough to identify the affected roles;
3. a due acceptance clause is `FALSE` at its deadline;
4. the facts proving false are `EXACT` or `JOIN_PRESERVED` must-facts;
5. every possible repair/delegation in the pre-deadline repair slice is ruled
   out or shown ineffective;
6. unknown post-deadline code is irrelevant to the already closed witness.

Other paths may remain unexplored. Result:
`VIOLATION_UNDER_LOADED_SPEC`.

## Conformance Closure

Conformance is closed when:

1. all relevant reachable paths from the operation root are enumerated or
   soundly summarized;
2. instance reconstruction and alias projection are closed on every path;
3. every due acceptance clause is `TRUE` on every path;
4. every footprint-affecting helper has a compatible exact or
   join-preserved summary;
5. no conclusion depends on `WIDENED` or `UNKNOWN` facts;
6. coverage and assumptions are reported.

Result: `CONFORMANT_UNDER_LOADED_SPEC`.

## Other Results

- `POSSIBLE_VIOLATION_REVIEW`: a false clause exists but feasibility, identity,
  or repair closure is incomplete.
- `INCOMPLETE_UNDER_LOADED_SPEC`: no closed violation and conformance cannot be
  proved.
- `NO_APPLICABLE_PROTOCOL`: no entry predicate and semantic footprint match.

FMPCA never emits an absolute `SAFE` result.

## Coverage And Assumption Report

Every result includes protocol/config hashes, operation root, source version,
reconstructed instance keys, handled/unhandled events, summary coverage,
alias/escape/isolation status, widened/unknown facts, reached deadlines,
clause-level values, repair-slice disposition, and explicit assumptions.

## Deterministic Decision Order

1. If no protocol applies, return `NO_APPLICABLE_PROTOCOL`.
2. If a closed exact violation exists, return
   `VIOLATION_UNDER_LOADED_SPEC`.
3. If a potential violation lacks closure, return
   `POSSIBLE_VIOLATION_REVIEW`.
4. If universal conformance closes, return
   `CONFORMANT_UNDER_LOADED_SPEC`.
5. Otherwise return `INCOMPLETE_UNDER_LOADED_SPEC`.
