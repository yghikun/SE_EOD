# OIDS Phase 15 JFS Held-out Preregistration

Phase 15 freezes the unchanged OIDS v0.1 protocol, the v0.2 diagnostic extension,
the Phase 14 result, and all established regression boundaries before any JFS source
is acquired or inspected.

JFS at Linux v6.14, commit `38fec10eb60d687e30c8c6b5420d86e8149f7557`, is the
single selected blind held-out candidate. Ten source paths, five applicability
dimensions, the complete decision partitions, controlled non-applicable reasons,
and the first-complete-result stop policy are fixed by the preregistration.

The selection does not predict applicability or conformance. After source reveal,
the first complete `APPLICABLE`, `NON_APPLICABLE`, or controlled `UNRESOLVED` result
is retained. JFS cannot be replaced in response to the result.
