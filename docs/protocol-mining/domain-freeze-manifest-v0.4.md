# Domain Semantic Freeze v0.4

Freeze date: 2026-08-01. Machine lock:
`configs/freeze/domain-semantic-freeze-v0.4.json`.

The freeze covers WDC, the executable DTC composition spec and checker,
capacity source adapter/binding, readiness, E4 manifest, replay fixtures,
Catalog, traceability, evidence and split documents. Frozen v0.1-v0.3 files
remain unchanged.

Changing a WDC/DTC relation, identity rule, formula, authority or deadline
requires Catalog v0.5. New source witnesses that do not alter semantics may be
added only with a new implementation/evidence revision and regenerated lock.

The freeze claims cross-operation-family validation across membership change
and capacity resize. It does not claim post-freeze held-out or
cross-filesystem generalization.
