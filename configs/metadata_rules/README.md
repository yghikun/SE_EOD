# MOCC-SE Metadata Rule Registry

`rule_registry_v2.json` is the evidence and coverage layer above executable
metadata protocols. It does not participate in EFSM state propagation and
cannot suppress or promote a candidate.

The registry separates:

- `rules`: semantic rules with explicit authority, evidence usage, dataset
  split, maturity, and executable protocol-operation bindings;
- `coverage_targets`: planned rule families and validation work that are not
  current analysis capability;
- `supported_fragment`: the semantic boundary shared by the registered rules.

Every active protocol operation must have at least one rule binding. Authority
is `normative`, `confirmed`, or `heuristic`. Evidence is classified as
`contract`, `implementation_evidence`, `historical_fix`,
`maintainer_evidence`, or `mined_hypothesis`; its use is `construction`,
`corroboration`, or `evaluation`; and its split is `external`, `development`,
`validation`, or `frozen_test`.

A normative rule requires contract evidence. A confirmed rule requires at
least two supporting sources from different evidence classes. Construction may
only use external/development data, while evaluation may only use
validation/frozen_test data. A locator cannot be reused for both construction
and evaluation. Maturity upgrades also require evaluation evidence from the
corresponding split.

External kernel documentation, upstream commits, and maintainer discussions
must use versioned or immutable locators and record both a lowercase SHA-256
digest and an exact quoted excerpt. Verify all pinned remote content with:

```powershell
python -m src.metadata_evidence_verifier
```

Validate the registry and all protocol bindings from the repository root:

```powershell
python -m src.metadata_rule_registry
```

Registry v2.2 reports one normative, seven confirmed, and two heuristic
development rules covering all twelve operations in Protocol A/B/C/D/E. The
fourteen pinned external artifacts comprise six versioned documentation
contracts, four historical mainline fixes, and four independent maintainer or
reviewer messages. The per-rule coverage and remaining gaps are recorded in
`EVIDENCE_AUDIT.md`. The registry still reports zero validation or frozen
rules, so this is not a frozen benchmark or evidence of generalization.
