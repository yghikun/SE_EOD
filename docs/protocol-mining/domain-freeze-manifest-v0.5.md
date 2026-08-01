# Domain Semantic Freeze v0.5

Freeze date: 2026-08-01. Machine lock:
`configs/freeze/domain-semantic-freeze-v0.5.json`.

The freeze covers CMRC v0.5 protocol, binding, readiness manifest, source
frontend, runner, tests, replay fixtures, Catalog, traceability, evidence,
manual replay and split documents. Frozen v0.1-v0.4 files remain unchanged and
are referenced as predecessor freezes.

Changing a CMRC role, relation, invariant, obligation, authority, deadline,
source-binding primitive or acceptance condition requires a later catalog
version. New provenance notes that do not alter semantics may be added only
with a new evidence revision and regenerated machine lock.

The freeze claims narrow cross-operation-family qualification across:

```text
btrfs-chunk-metadata-reservation
btrfs-device-item-update
```

It does not claim post-freeze held-out or cross-filesystem generalization.

