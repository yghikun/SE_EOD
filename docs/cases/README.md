# FMPCA Case Dossiers

These dossiers are the P0.2 evidence boundary. They normalize confirmed source
records into protocol facts without treating a Bug ID, function name, line
number, or patch version as a protocol predicate.

Evidence status meanings:

- `READY_FOR_MINING`: bug, normal/safe, and repair evidence are sufficient for
  candidate-rule mining.
- `EVIDENCE_INCOMPLETE`: the case remains in the corpus, but missing evidence
  cannot be replaced by an inferred rule.
- `HELD_OUT`: the normalized record is sealed from protocol-rule development
  and used only after the catalog hash is frozen.

Every dossier contains the same semantic record: operation root, roles, entry
assumptions, typed events, relation/local deltas, obligations, isolation and
observability, responsibility transfer, outcome, terminal state, and deadline.

