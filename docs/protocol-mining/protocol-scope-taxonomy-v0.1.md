# Protocol Scope Taxonomy v0.1

Status: executable engineering baseline. This taxonomy controls scope claims;
it does not change any frozen protocol or acceptance formula.

## Purpose

FMPCA separates semantic applicability from freeze strength. A protocol is not
`COMMON` because names, fields or cleanup calls look similar. Promotion follows
this fixed decision order:

```text
object correspondence
-> relation and authority correspondence
-> identity and epoch correspondence
-> source binding correspondence
-> replay and proof closure
-> protocol rule
```

The executable contract is
`configs/catalog/protocol-scope-taxonomy-v0.1.json`; the evaluator is
`src/fmpca/scope.py`.

## Semantic scopes

| Scope | Meaning | Cross-filesystem claim |
|---|---|---|
| `COMMON` | Object, relation, lifecycle, authority and deadline correspondence closes in at least two independent filesystems. | Allowed only after the common-freeze gates pass. |
| `FS_FAMILY` | Semantics close in a named implementation family but not across unrelated filesystems. | No. |
| `FS_SPECIFIC` | Semantics retain one filesystem's native objects and lifecycle. | No. |

`NARROW_FREEZE` is a freeze boundary, not a fourth degree of semantic
generality. It may qualify `FS_SPECIFIC`, `FS_FAMILY` or eventually `COMMON`:
only the evidenced footprint is locked, and the qualifier never widens an
applicability claim.

An `FS_SPECIFIC` declaration requires at least one applicable filesystem. An
`FS_FAMILY` declaration requires a named family and at least two applicable
members whose evidence records carry that same family identity. A `COMMON`
declaration requires all common-freeze gates. These declaration gates prevent
an empty or merely aspirational label from becoming a scope claim.

## Applicability states

| State | Required interpretation |
|---|---|
| `APPLICABLE` | The adapter has a source-backed canonical correspondence. |
| `NON_APPLICABLE` | Source or design evidence establishes a controlled mismatch reason. |
| `UNRESOLVED` | The correspondence has not been established or rejected. It contributes no promotion evidence. |

`NON_APPLICABLE` requires one of: `OBJECT_ABSENT`,
`RELATION_NOT_ISOMORPHIC`, `LIFECYCLE_INCOMPATIBLE`,
`AUTHORITY_NOT_ALIGNED`, or `DEADLINE_NOT_ALIGNED`, plus an evidence note.
Merely failing to find a counterpart remains `UNRESOLVED`.

## Common readiness

### Candidate

A common candidate requires a canonical DSL, bindings, source-witness
definition, one development-filesystem replay closure, and a result partition
that distinguishes negative, fixed and unknown evidence.

### Freeze

Common freeze additionally requires:

- at least two applicable filesystems;
- a distinct operation family in each filesystem;
- closed object, relation, lifecycle, authority and deadline correspondence;
- per-filesystem source witness, replay and proof closure;
- locked protocol, binding and test hashes.

A declaration of `COMMON` is invalid until all freeze gates close.

### Held-out

Held-out validation requires a third filesystem evaluated after freeze, with
the same correspondence and closure requirements. It must not modify the
protocol, binding, or acceptance condition.

## Current conservative assignments

The v0.1 registry makes no `COMMON` claim. CMRC, WDC, the DTC composition,
DTR, DSSA, RRAS and RAS remain Btrfs `FS_SPECIFIC`; CMRC, DSSA and RRAS retain
a `NARROW_FREEZE` boundary. The registry records cross-filesystem status as
`UNRESOLVED`, so future promotion must supply evidence rather than inherit a
name-based claim.

## Usage

List the current registry:

```powershell
python -m src.fmpca.scope `
  --taxonomy configs/catalog/protocol-scope-taxonomy-v0.1.json `
  --list-current
```

Evaluate a scope declaration:

```powershell
python -m src.fmpca.scope `
  --taxonomy configs/catalog/protocol-scope-taxonomy-v0.1.json `
  --declaration path/to/scope-declaration.json
```

The command exits nonzero when a declaration claims `COMMON` before the common
freeze gates close.
