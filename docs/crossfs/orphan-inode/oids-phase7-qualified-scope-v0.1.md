# OIDS Phase 7 Qualified Scope v0.1

## Decision

Phase 7 records an explicit, narrow applicability scope for the ext4 evidence:

```text
filesystem == ext4 AND error_policy != ERRORS_CONT
```

The included profile is `ERRORS_RO_OR_FAILSTOP`. `ERRORS_CONT` is explicitly
excluded because Phase 6 closed source-plus-semantic negative witnesses for
`OIDS-O1`, `OIDS-O2`, and `OIDS-O3` under that configuration.

## Scope status

```text
semantic_scope = FS_SPECIFIC
freeze_boundary = NARROW_FREEZE
qualified_scope_closed = true
common_freeze_manifest_generated = false
```

The declaration is evaluated through the existing executable scope taxonomy.
The historical taxonomy and candidate protocol remain byte-frozen; the new
qualification catalog is an overlay that makes the configuration predicate
auditable without rewriting earlier evidence.

## Evidence gates

Phase 5 closes ext4 registration and settlement for the non-continuing
failstop profile. Phase 6 closes recovery failstop propagation and separately
records the `ERRORS_CONT` counterexamples. Therefore the qualified ext4
declaration has closed source, replay, proof, and result-partition gates.

This is not a COMMON declaration. It does not claim that Btrfs and ext4 form a
single implementation family, and it does not use XFS as blind held-out data.
XFS remains `POST_FREEZE_XFS_VALIDATED` under the project policy.

## Next boundary

To make a cross-filesystem or held-out claim, a new filesystem family must be
selected before its source paths are used to modify the protocol or checker.
