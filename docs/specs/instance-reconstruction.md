# Protocol Instance Reconstruction 0.1

## Identity

```text
SemanticInstanceKey = <protocol_id, anchor_role_identities, base_epoch>
InstanceId = <SemanticInstanceKey, instance_generation>
```

`base_epoch` always contains the operation-root invocation and retry
generation. A protocol may additionally include transaction identity, object
generation, or allocation site through `epoch_policy.include`.

Source function names may label the operation-root invocation in a report, but
they are not protocol predicates. Identity comes from typed arguments, field
accesses, allocations, and binding-provided stable values.

## Event Input

```json
{
  "event": "Begin",
  "roles": {"operation": "call:42", "metadata_subject": "inode:17"},
  "epoch": {"operation_root": "call:42", "retry_generation": 0},
  "data": {},
  "source": {"file": "...", "line": 1},
  "precision": "EXACT"
}
```

Missing required anchor identity produces `INCOMPLETE`; it is never replaced
with a function name or Bug ID.

## Alias Decisions

```text
MUST_ALIAS     bind to the same instance and may discharge matching obligations
MAY_ALIAS      fork candidate bindings
NO_ALIAS       do not match
UNKNOWN_ALIAS  preserve candidates but make closure incomplete
```

Only `MUST_ALIAS` may use one event to discharge an obligation for an existing
identity. `MAY_ALIAS` cannot close an obligation.

## Reconstruction Algorithm

For each typed event:

1. Select protocols declaring that event.
2. Check the entry formula for a new instance or event compatibility for live
   instances.
3. Build available anchor identities and epoch components.
4. Compare with live keys using the binding alias oracle.
5. Attach to every `MUST_ALIAS` match; fork for `MAY_ALIAS`; reject
   `NO_ALIAS`; mark unknown closure for `UNKNOWN_ALIAS`.
6. If no match and entry is true, allocate generation 0. Reuse of the same
   semantic key after a terminal settlement increments `instance_generation`.
7. If candidate count exceeds budget, create a `CandidateInstanceSet`; no
   discharge or conformance proof may depend on which candidate is correct.

## Retry And Transaction Epochs

A retry that supersedes the prior attempt increments `retry_generation` while
remaining in the same operation-root epoch. Protocols may link the attempts
through explicit `RetryBegin`/`FailureSuperseded` events. A transaction object
does not automatically define an instance boundary; it participates only when
the protocol epoch policy names it.

## Projection

At a call boundary, the caller projects only roles and relations referenced by
the callee summary footprint. Returned identities are projected back through
typed return/access paths. Loss of a required anchor during either projection
produces `UNKNOWN_ALIAS` and blocks conformance closure.

