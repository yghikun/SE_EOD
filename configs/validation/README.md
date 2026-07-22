# MOCC-SE validation freeze

This directory freezes the protocol/rule inputs and records the first blind
validation batch.  It is a data-split boundary, not an evaluation result.

Files:

- `protocol_freeze_v1.json` pins the active rule registry, active protocol
  manifests, package families, filesystem bindings, and operation instances by
  SHA-256.
- `validation_manifest_v1.json` lists 10 blind, unlabeled source-function
  samples.  Each sample is checked against protocol applicability, exact rule
  applicability, source digests, function existence, duplicate sample identity,
  and construction/evaluation overlap.
- `reviewer_a_labels_v1.json` and `reviewer_b_labels_v1.json` are independent
  reviewer templates.  They intentionally contain only `unlabeled` entries.
- `adjudication_v1.json` is an empty adjudication template that mirrors the two
  reviewer slots.  It must not be treated as a completed result.
- `schemas/` contains human-facing JSON Schemas.  The Python validator remains
  the authoritative checker because it verifies workspace hashes and source
  function presence, reviewer coverage, and adjudication consistency.

Current policy:

- The freeze was created on `2026-07-22`.
- The manifest references freeze id
  `mocc.freeze.protocols_rules.2026_07_22`.
- Blind manifests may only contain `label_status: "unlabeled"`.
- Validation identity is
  `filesystem + Linux version + kernel-relative path + function`.
- The same identity must not appear in construction evidence and validation.
- No validation sample is added back to the rule registry as evaluation evidence.

Run:

```powershell
python -m src.metadata_validation_manifest
python -m src.metadata_validation_labels `
  --labels configs/validation/reviewer_a_labels_v1.json `
  --labels configs/validation/reviewer_b_labels_v1.json `
  --adjudication configs/validation/adjudication_v1.json
```

Next step: two independent reviewers label each sample with one of `legal`,
`violation`, `analysis_unknown`, or `out_of_scope`, followed by adjudication.
Use `--require-complete` only after every reviewer entry and adjudication entry
has been filled with a rationale.
