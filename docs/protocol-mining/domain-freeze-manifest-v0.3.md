# Domain Semantic Freeze v0.3

Freeze date: 2026-08-01. Machine lock: `configs/freeze/domain-semantic-freeze-v0.3.json`.

The lock covers the two v0.3 protocols, the RRAS binding, readiness manifests,
catalog, evidence boundary, traceability, replay and split documents. v0.1
and v0.2 artifacts remain immutable. The freeze is deliberately narrow:
there is no held-out family and no cross-filesystem generalization claim.

Changing a rule, relation, deadline, authority or AcceptP clause requires
Catalog v0.4. Adding source binding or summary without semantic change is an
implementation revision only if the SHA-256 lock is regenerated and the
closure boundary remains unchanged.

The executable v0.3 replay manifest is `configs/evaluation/e3-v0.3.json` and
its generated outputs are retained under `outputs/fmpca-e3-v0.3/`.
