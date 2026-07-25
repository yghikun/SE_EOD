# Failure-Path Filesystem Metadata Residual Analysis

This document defines the current analysis architecture.

The report lattice distinguishes a cancelled effect from a real residual that
cannot escape its failure domain. `CONTAINED_METADATA_RESIDUAL` retains the
residual and a source witness for teardown, transaction abort, forced shutdown,
or checkpoint stop; it is not counted as a Candidate. Terminal primitives are
accepted only when they execute on the current function's must-error path.
Function summaries retain an `ErrorExitPartition` for each classified error
return so a terminal action stays correlated with that return. A terminal
action is projected to an aggregate caller failure only when every complete
error partition is terminal; branch-specific actions remain partition evidence
until the caller slicer can analyze alternatives independently.

## Overview

```text
Linux FS source
  -> frontend-neutral FunctionIR
  -> project call-site provenance
  -> CFG builder
  -> filesystem metadata scope gate
  -> failure-point discovery
  -> backward slice for E_f
  -> forward error-path slice for C_f and T_f
  -> identity-aware cancellation
  -> residual normalization
  -> error-exit verification
  -> witness report
```

## Residual Equation

For a failure point `f`:

```text
E_f = filesystem metadata effects that can reach f
C_f = cancellation or compensation effects along the error path
T_f = explicitly protected or transferred filesystem metadata effects

R_f = Normalize(E_f (+) C_f) - T_f
```

`R_f` is the residual filesystem metadata state at an error exit.

## Filesystem Metadata Effect

Each effect is represented as:

```text
E = <Root, Key, Plane, Delta, Value, Site, Evidence>
```

```text
Root:
  inode, superblock, block group, transaction, fs_devices, root, quota object,
  reservation object, recovery object, or unknown.

Key:
  inode id, block id, extent range, device id, quota subject, root id, or
  unknown.

Plane:
  STRUCTURAL, ACCOUNTING, or RECOVERY.

Delta:
  ADD, REMOVE, SET, CLEAR, INC, DEC, RESERVE, RELEASE, PROTECT, CLOSE,
  RESTORE, or UNKNOWN.

Value:
  normalized value source used to match inverse effects.

Site:
  source location and expression.

Evidence:
  DIRECT_SOURCE, EXPLICIT_PRIMITIVE, or NAME_INFERRED.
```

## Identity-Aware Cancellation

The analyzer cancels effects only when object identity is compatible:

```text
same or normalized Root
same or compatible Key
same Plane
inverse Delta
same or equivalent Value source
```

Examples:

```text
INC(inode.i_blocks, n)       cancels with DEC(inode.i_blocks, n)
SET(bitmap, block)           cancels with CLEAR(bitmap, block)
ADD(list, device)            cancels with REMOVE(list, device)
RESERVE(rsv, bytes)          cancels with RELEASE(rsv, bytes)
ATTACH(fs_root.reloc_root)   cancels with DROP(fs_root.reloc_root)
```

## Aggregate Snapshot Restore

`src/aggregate_snapshot.py` models a whole-aggregate restore as a field-level
`RESTORE` cancellation only when the source proves all of the following:

```text
the snapshot is a local aggregate copied from an exact owner identity
the capture dominates the field mutation and occurs before it
the relevant snapshot field is neither overwritten nor address-escaped
the restore writes the snapshot to the same aggregate owner
the restore dominates every feasible error exit
source-visible function-like macros prove any owner spelling equivalence
```

The relation stores the snapshot and owner roots, aggregate key, capture site
and block, and expanded source identity. Variable names and shallow alias
similarity are never treated as rollback evidence.

## Transient Operation Arguments

`src/transient_provenance.py` proves that a callee parameter denotes an
automatic caller aggregate before direct effects on that aggregate are removed
from metadata-residual scope. The proof requires:

```text
one unique visible callee definition
at least one visible direct call
every visible direct call passes &caller_local
the caller local has automatic, non-static aggregate storage
the caller aggregate type exactly matches the parameter pointee type
the address is not returned or written to source-visible non-local storage
the callee parameter and source-visible pointer/container aliases are not
  returned or written to source-visible non-local storage
```

Unique visible callees are checked recursively for explicit publication.
Opaque or indirect calls remain synchronous borrows: a call is not itself
evidence that an automatic object's address was stored. This is deliberately
not claimed as whole-program C escape analysis. Source-visible global/parameter
stores and returns always reject the proof.

The scope exclusion is exact-root and evidence-bounded:

```text
DIRECT_SOURCE effect root == proven transient parameter -> OUT_OF_SCOPE
parameter->persistent_object->field                     -> retained
NAME_INFERRED helper effect rooted at parameter          -> retained
```

Excluded effects remain in `ResidualSlice.out_of_scope_effects` with all
call-site witnesses, so transition auditing matches the old effect to a
current `OUT_OF_SCOPE` witness instead of reporting `UNMATCHED`.

## Exhaustive Container Cleanup

M32c represents a narrowly proven list drain with
`ContainerIterationCleanup`. The relation records the parameter-owned
container, iterator, next iterator, intrusive member field, iteration site,
and a source identity. It is created only for the exact source shape:

```c
list_for_each_entry_safe(curr, next, &param->container, member) {
        list_del(&curr->member);
        ...
}
```

Both iterators must be pointer locals, the container must be a field path
rooted at a function parameter, and the loop body must contain exactly one
top-level matching `list_del()` or `list_del_init()`. Any `break`, `continue`,
`goto`, or `return`, a different member field, a non-parameter container, or a
non-safe iterator rejects the proof.

The relation survives summary parameterization and caller-site projection.
One proven drain may cancel multiple earlier `ADD` effects only when every
effect has the same container root and its value ends in the exact intrusive
member field. It cannot cross containers or member fields. Radix trees,
xarrays, and generic container macros remain outside this rule.

Transition comparison also distinguishes `RETAINED_REACHING`: the source
effect is still present in the current full slice, but the residual projection
selected another certain effect. It is neither a resolution nor an unmatched
witness.

## Per-CPU Slot Identity

M32d represents one source-proven per-CPU slot with `PerCpuSlotRelation`. The
relation records the parameter-owned base, slot and index locals, loop and
accessor sites, and a source identity. It is created only for the exact source
shape:

```c
for_each_possible_cpu(cpu) {
        slot = per_cpu_ptr(param->percpu_field, cpu);
        ... effects rooted at slot ...
}
```

The index must be a local scalar, the slot must be a pointer local, the base
must be a field path rooted at a function parameter, and the accessor must be
the exact two-argument `per_cpu_ptr()` call using the loop index. The accessor
assignment must be unique in the function and the slot cannot have an
initializer or another assignment. `break`, `continue`, `goto`, and `return`
inside the loop reject the proof.

Only effects in the same loop body and strictly after the accessor are bound.
Their root is normalized to `PER_CPU_SLOT(param->percpu_field)`, while the
index remains structured provenance rather than part of the root. This avoids
turning the local index into an unresolved summary identity. Parameterization
and caller-site projection rewrite both the normalized root and the relation's
base without treating the slot as an ordinary owner alias.

Different iteration macros, global bases, mismatched indices, non-pointer
slots, generic accessors, effects before the accessor, and reassigned slots all
remain unresolved. The rule establishes identity completeness only; it does
not claim that a per-CPU CLOSE cancels an unrelated residual.

## Bounded SMT Evidence

`src/smt_solver.py` uses Z3 only for source facts that can be represented
without modeling C memory or alias semantics:

```text
1. Failure-path feasibility: discard a CFG branch only when the failure result
   constraint and the branch predicate are UNSAT together.
2. Counter balance: close visible INC/DEC effects only when their symbolic net
   delta is provably zero.
3. Conditional cleanup/protection: count an error-path effect only when its CFG
   block dominates every feasible error exit after the failed call.
```

Unsupported predicates, pointer/error-pointer checks, aliasing, and opaque
callee behavior remain `UNKNOWN`. Z3 is evidence for these narrow facts, not a
general C verifier; a satisfiable query never proves a cleanup is correct.

## Failure-Anchored Bidirectional Slicing

The analysis is anchored at each failure point.

Backward slice:

```text
find filesystem metadata effects that can reach the failure point -> E_f
```

Forward error-path slice:

```text
find cancellation, compensation, protection, and transfer effects -> C_f, T_f
```

Only the slice relevant to `mutation -> failure -> error exit` is analyzed.

## Protection Set

`T_f` contains effects explicitly protected by:

```text
journal ownership
transaction commit/abort ownership
orphan registration
replay/recovery registration
deferred cleanup ownership
verified invalidation that prevents direct reuse of partial metadata
```

If protection cannot be proven, the effect stays `UNKNOWN`. In particular, a
cleanup or protection that runs only on some feasible error paths cannot close
the residual.

## State Labels

The implementation may use:

```text
EXPOSED
PROTECTED
CLOSED
CONTAINED
UNKNOWN
```

These are dataflow labels, not the method's main novelty and not a full EFSM.

## Semantic Classifications

The canonical result field is `classification`:

```text
FUNCTION_BOUNDARY_RESIDUAL
LIVE_METADATA_RESIDUAL
CONTAINED_METADATA_RESIDUAL
FUNCTION_BOUNDARY_RESIDUAL_REVIEW
METADATA_RESIDUAL_UNKNOWN
CLOSED
OUT_OF_SCOPE
```

`FUNCTION_BOUNDARY_RESIDUAL` means only that a source-supported non-empty
`R_f` reaches this function's error exit. Owner liveness and normal failure-
domain continuation have not yet been proved, so it must not be presented as
a confirmed or likely bug. M35a emits no `LIVE_METADATA_RESIDUAL`; that state
is reserved for the owner-liveness layer.

## Legacy Report Kinds

```text
UNCLOSED_METADATA_RESIDUAL
  Compatibility alias for FUNCTION_BOUNDARY_RESIDUAL.

METADATA_RESIDUAL_UNKNOWN
  R_f is non-empty, but aliasing, indirect calls, async handoff, or helper
  semantics prevent a conservative decision.

METADATA_RESIDUAL_REVIEW
  R_f is non-empty but every residual effect is inferred only from helper
  naming. This is a review hypothesis, not a candidate.

CONTAINED_METADATA_RESIDUAL
  R_f remains non-empty at the function boundary, but a source-proven terminal
  failure domain prevents ordinary live continuation. The residual and its
  containment proof remain in the witness; this is not counted as a Candidate.

OUT_OF_SCOPE
  The effect is ordinary resource cleanup or source-proven automatic operation
  state rather than persistent filesystem metadata.
```

`candidate_count` is likewise a compatibility alias for
`function_boundary_residual_count`. New evaluation output includes both fields
and a `residual_classification_counts` map.

## Manual Review Oracle

The 539-row M32d source review is materialized as
`outputs/candidate_review_oracle.jsonl`. Every entry has
`oracle_granularity=REPORT`, a source-stable failure/exit location, and sorted
structured residual effect identities. The manual verdict remains report-level;
mixed-effect reports are not falsely split into effect-level human truth.

`scripts/audit_candidate_review_oracle.py` matches those records against full
evaluation slices. It reports terminal migrations, retained live residuals,
recognized containment, Candidate-to-UNKNOWN movement, and unmatched effect
witnesses. A prior audit can be supplied to distinguish pre-existing safety
issues from regressions introduced by the current milestone.

An UNKNOWN slice with empty `R_f` is retained as a diagnostic only and is not
emitted as a finding.

UNKNOWN is effect-local for source order: a direct effect that occurs after a
reaching unknown call cannot have been cancelled by that call. Error-path
reachability also carries the known failed result through simple later checks,
so an `if (ret == 0)` cleanup is excluded after a verified failing `ret` edge.
All other unresolved helper effects remain blocking; different argument names
are not accepted as a non-alias proof.

## Evidence Boundary

Witness reports are derived from the failure-path residual slice itself:

```text
failure point
error exit
E_f
C_f
T_f
R_f
scope rationale
unknown causes
confidence
```

The detector does not require sibling-path comparison or differential
restoration evidence.
