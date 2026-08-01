# FMPCA Protocol DSL 0.1

## Purpose

The DSL describes a finite relational metadata protocol independently of Bug
IDs and target functions. A protocol file is UTF-8 JSON. Unknown keys are
rejected so that misspelled semantics cannot silently disappear.

## Top-Level Shape

```json
{
  "schema_version": 1,
  "protocol_id": "fmpca.example",
  "protocol_version": "0.1.0",
  "semantic_intent": "...",
  "roles": [{"id": "operation", "kind": "operation", "anchor": true}],
  "epoch_policy": {"include": ["operation_root", "retry_generation"]},
  "entry_formula": {"op": "literal", "value": true},
  "initial_phase": "INITIAL",
  "phases": ["INITIAL", "SETTLED"],
  "events": ["Begin", "OperationReturn"],
  "transitions": [],
  "invariants": [],
  "obligation_templates": [],
  "allowed_authorities": [],
  "deadlines": ["ALWAYS", "AT_SETTLEMENT"],
  "checkpoint_events": [],
  "terminal_events": ["OperationReturn"],
  "acceptance_formula": {"op": "literal", "value": true},
  "frame_relations": [],
  "semantic_footprint": [],
  "evidence_references": []
}
```

Required top-level keys are all keys shown above. Protocol IDs and versions are
immutable within one catalog freeze.

## Roles And Identity

Each role has:

- `id`: protocol-local identifier;
- `kind`: `operation`, `object`, `container`, `member`, `pointer`,
  `transaction`, `owner`, or `authority`;
- `anchor`: whether its exact identity contributes to `SemanticInstanceKey`;
- `required`: defaults to true;
- `identity_fields`: optional binding-provided typed identity components.

Events supply role bindings as opaque stable strings. Source bindings may
derive them only from typed values/access paths, not Bug IDs.

## Transition Shape

```json
{
  "event": "FailureObserved",
  "from": ["IN_PROGRESS", "RETRYING"],
  "to": "FAILED",
  "guard": {"op": "literal", "value": true},
  "actions": [
    {"op": "set_relation", "name": "active_failure", "value": true},
    {"op": "activate_obligation", "template": "MTO-O1"}
  ]
}
```

Supported actions:

- `set_relation(name,value[,precision])`
- `copy_prestate(name)`
- `add_delta(relation,before,after)`
- `set_outcome(value)`
- `set_isolation(value)`
- `set_escape_closure(value)`
- `activate_obligation(template[,relation])`
- `discharge_obligation(template[,relation])`
- `delegate_obligation(template,relation,authority)`
- `complete_authority(authority[,relation])`
- `record_irreversible_violation(code,relation)`
- `mark_precision(relation,precision)`

An event with no matching transition is recorded as unhandled evidence and
makes conformance closure incomplete if it touches the semantic footprint.

## Formula Grammar

Formulas are JSON objects. No host-language `eval` is permitted.

```text
literal(value)
all(items...)
any(items...)
not(item)
relation_equals(name, value)
relation_in(name, values...)
relation_matches_prestate(name)
phase_in(values...)
outcome_in(values...)
obligation_status(template, statuses..., optional relation)
no_due_obligations(deadline)
no_irreversible_violation
precision_at_least(relation, minimum)
role_bound(role)
authority_allowed(authority)
```

Formula evaluation returns `TRUE`, `FALSE`, or `UNKNOWN`. `UNKNOWN` never
proves conformance. A formula may prove violation only when the facts required
for the false result are `EXACT` or `JOIN_PRESERVED`.

## Invariants And Obligations

Invariant:

```json
{
  "id": "MTO-R1",
  "deadline": "AT_SETTLEMENT",
  "formula": {"op": "..."},
  "evidence": ["trace:MTO-R1"]
}
```

Obligation template:

```json
{
  "id": "MTO-O1",
  "required_formula": {"op": "..."},
  "activation_horizon": "FailureObserved",
  "deadline_policy": "MUST_DISCHARGE",
  "delegation_deadline": null,
  "completion_deadline": "AT_SETTLEMENT",
  "allowed_authorities": []
}
```

`deadline_policy` is `MUST_DISCHARGE` or `MAY_DELEGATE_TO`. Delegation changes
status to `DELEGATED`; it does not make the required formula true and does not
remove the completion deadline.

## Validation

The loader rejects duplicate roles/events/phases/rule IDs, unknown formula or
action operators, invalid phase targets, undeclared authorities, missing
anchor roles, Bug-like top-level predicates (`bug_id`, `target_function`,
`source_line`, `patch_id`), and evidence references placed inside guards.

The two frozen protocols and the Membership synthetic fixture must pass this
same loader. Membership is a test fixture, not catalog evidence.

