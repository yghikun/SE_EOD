# Output Layout

`outputs/` contains two different classes of artifacts. They must not be mixed
in evaluation claims.

## Active MOCC-SE evidence

```text
confirmed_bugs.md
mocc-protocol-a-v1/
mocc-protocol-b-v1/
mocc-protocol-c-v1/
mocc-discovery-v2/
mocc-batch-scan-v1/
mocc-validation-v1/
mocc-finding-review-v1/
```

- `mocc-protocol-*-v1/` contains versioned Protocol A/B/C development witnesses.
- `mocc-discovery-v2/` contains the M11 fresh review report, source triage and
  historical ext4 helper fault-model development evidence.
- `mocc-batch-scan-v1/` contains freeze-bound full-source candidate queues,
  initial source triage ledgers and the bug-hunt ranking artifact. It also
  contains the ext4 replay bookkeeping source-fact audit for the two v7.1
  `needs_external_semantics` hits and the XFS tempfile exchange transaction
  source-fact audit for the current top manual-review candidate. These reports explicitly use
  `candidate_queue_not_bug_claims`, `manual_bug_hunt_prioritization_not_bug_claims`
  or `source_facts_not_bug_claims` semantics.
- `mocc-validation-v1/` contains label-blind predictions and protocol
  applicability audits for frozen validation manifests and draft selection
  audits for future blind batches. Batch 1 currently has 2/10 analyzable
  samples after lifecycle discovery expansion and 8/10 out-of-scope samples, so
  its prediction artifact is a failed-coverage diagnostic, not a precision/recall
  result. Batch 2 selection artifacts use
  `selection_audit_not_evaluation` semantics until a manifest is frozen and
  independently labeled. The current selection smoke artifact also records
  that all registered exact-entry identities are construction overlaps, so
  exact-entry sampling is not available under the present freeze.
- `mocc-finding-review-v1/` contains the M8-M10 development review, version
  matrix, repair evidence, bug-hunt report and confirmed-bug linkage.
- `confirmed_bugs.md` records manually/history/dynamically supported findings
  and their distinct submitted/reviewed/accepted states.

The directory name `mocc-discovery-v2` is an experiment-generation label, not
the JSON schema version. Retained reports may use discovery schema v2. Newly
generated reports use schema v5, which separates exact-entry and semantic
applicability counts and records lifecycle terminal callees that were relaxed
for acquire/open-first discovery; historical reports are not rewritten in place.

These artifacts are development and review evidence, not a frozen independent
benchmark. `DISCOVERY_REVIEW` is not equivalent to `PROTOCOL_CANDIDATE` or a
confirmed bug.

## Historical development evidence

```text
mocc-discovery-v1/
mocc-discovery-v1-linux-v6.8.json
mocc-discovery-v1-linux-v6.14.json
mocc-discovery-v1-linux-v7.1.json
experiment-v1.3.3/
linux-v6.8/
linux-v7.1/
f2fs_maintainer_feedback.md
```

`mocc-discovery-v1*` records the exact-entry M7 development stage that preceded
fresh discovery. `experiment-v1.3.3` and the versioned `linux-*` directories are
legacy SE-EOD resource/error-path/ranking outputs. Their runtime modules and
experiment scripts have been removed, so they are retained only to interpret
historical bug provenance and development decisions.

Historical ranking scores, LLM verdicts and manually promoted subsets are not
ground truth and cannot be used to report current MOCC-SE precision or recall.

## Removed outputs

The following superseded directories were removed on 2026-07-22:

```text
experiment-v1.3/
experiment-v1.3.1/
experiment-v1.3.2/
experiment-v1.4/
experiment-v1.4-baseline/
experiment-v1.5-cfg/
linux-v6.14-bug-check/
linux-v6.14-xfs-convergence-check/
```

Do not restore these generated files unless a new, explicit research scope
requires the legacy SE-EOD pipeline.
