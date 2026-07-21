# SE-EOD / MOCC-SE Resource and Metadata Effect State Model

This document defines the ownership semantics used by the function-local and
interprocedural analyses. In MOCC-SE, resource ownership is one special case of
the broader metadata effect ledger. A reported result must be explainable as
state transitions and responsibility transfers rather than as a function-name
exception. The full target model is documented in
[`../MOCC_SE_FULL_ARCHITECTURE.md`](../MOCC_SE_FULL_ARCHITECTURE.md).

Metadata effects additionally carry `scope`, `owner`, `compensation`, and
`status`. Transaction abort only resolves effects explicitly marked
`TRANSACTION_SCOPED`; it does not automatically resolve global pointers,
container membership, or filesystem topology changes.

## States

| State | Meaning |
|---|---|
| `UNSEEN` | The path has not observed the resource. |
| `ACQUIRED` | The current function owns a live resource. |
| `BORROWED` | The function may use the resource but does not own it. |
| `TRANSFERRED` | Ownership was passed to another function or object. |
| `RELEASED` | The owned resource was released. |
| `ESCAPED` | The resource was stored or returned beyond the analyzed scope. |
| `UNKNOWN` | Available evidence cannot establish a safe definite state. |

## Transitions

An acquisition moves `UNSEEN` to `ACQUIRED`; receiving a borrowed parameter
moves it to `BORROWED`. A release, ownership transfer, field store, or return
moves an `ACQUIRED` resource to `RELEASED`, `TRANSFERRED`, or `ESCAPED`.
Releasing a borrowed resource and unsupported transitions produce `UNKNOWN`.
Joining distinct non-empty states also produces `UNKNOWN`.

At an error-path endpoint, an `ACQUIRED` resource is a `missing_cleanup`
violation. `TRANSFERRED`, `RELEASED`, and `ESCAPED` are not missing-cleanup
violations. `UNKNOWN` is retained as uncertainty and must not be silently
treated as safe.

## Function Summaries

Each summary contains parameter-level or return-value effects:

```json
{
  "function": "wrapper_put",
  "parameters": ["item"],
  "effects": [
    {
      "resource": "arg0",
      "action": "release",
      "condition": "always",
      "resource_type": "memory",
      "evidence": ["direct call kfree(item)"]
    }
  ]
}
```

The current implementation infers direct release, out-parameter acquisition,
return-value acquisition, simple conditional return acquisition, argument
return/transfer, and field escape effects. Reviewed external API effects can be
seeded through `interprocedural_effect_seeds`; for example, callback registration
can transfer a resource argument to deferred cleanup without hard-coding the API
inside the tracker. These seeds are active only in interprocedural mode and their
effects propagate through local wrappers like inferred summaries. Conditional return acquisition is
used for reusable-buffer patterns such as `arg ? *arg : NULL` followed by
allocation under `if (!local)`: the summary records `argN == NULL`, and callers
only treat the return value as newly acquired when the actual argument is
definitely null. It builds a filesystem-local call graph and propagates callee
effects to a fixed point. Every propagated effect carries its call-chain
evidence. Calls that receive a resource parameter but cannot be resolved are
recorded in `unresolved_calls`; they do not imply release or transfer.

Direct effect guards are normalized from parameter names to `argN` and remapped
when propagated through a wrapper. At a call site, the current implementation
can prove simple guards of the forms `argN`, `!argN`, `argN == NULL/0`, and
`argN != NULL/0`. Integer and Boolean literals are evaluated directly. A
positive guard on the resource argument is also true for a successfully held
resource. Unknown flags and compound guards are not assumed true, so their
conditional release or transfer effects remain unapplied.

Run the analysis with `--enable-interprocedural` and set
`--function-summaries-out` to retain the machine-readable summaries. Historical
experiment baselines remain unchanged unless the flag is enabled.

## Retry Backedges

A `goto` path is not treated as a function exit when label resolution revisits a
label before reaching a return and the original branch condition implies the
backedge guard. This covers direct `goto retry` backedges and indirect chains
such as `error -> retry -> error`. A conditional fallback retry is not filtered
when its stronger guard is not implied by the original error. Forward cleanup
labels and fallthrough function exits remain eligible paths.

## Cross-Version Fix Evidence

Candidate generation remains independent of later-version source. A reviewed
historical-fix database can subsequently match an existing candidate by file,
function, candidate type, and affected source line. A match records the affected
and fixed versions plus the later cleanup lines, promotes the ranking evidence
to `E3_HISTORICAL_FIX_CONFIRMED`, and closes the `repair_patch` and
`upstream_confirmation` evidence gaps. It does not suppress the candidate or
claim dynamic reproduction.
