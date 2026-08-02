# OIDS Phase 13 v0.2 Revision Preregistration and Split Reset

## Decision

The two ReiserFS findings are classified as source-confirmed correctness bugs under the frozen OIDS v0.1 contract. The classification is based on closed source control flow, rule-specific minimal replay, a reachable unsafe checkpoint, and a stated repair contract.

```text
source_confirmed_bug_count = 2
runtime_reproduced_bug_count = 0
upstream_acknowledged_bug_count = 0
security_bug_count = 0
```

This evidence supports the word "bug" in the implementation-correctness sense. It does not support claims of upstream acknowledgement, runtime reproduction, exploitability, or a CVE.

## Versioning boundary

Phase 13 preregisters OIDS v0.2 before any protocol or semantic edit. Version 0.1 remains byte-frozen with OIDS-O1 and OIDS-O3 retained as violations. Version 0.2 is scoped as a diagnostic and failure-handling contract extension; it must not weaken the normative safety outcomes or add success-dependent applicability predicates.

```text
semantic_edits_before_preregistration = 0
v0_1_protocol_mutated = false
v0_2_protocol_implemented = false
normative_safety_outcomes_preserved = true
```

## Repair objectives

### Registration acceptance failure

When persistent orphan registration fails after the final-link transition is staged, a safe implementation must do one of the following:

- propagate failure and prevent namespace commit;
- prove transaction abort or rollback of the final-link transition;
- enter failstop before unsafe success exposure.

Committing namespace removal without persistent cleanup responsibility remains OIDS-O1.

### Recovery cleanup failure

When synchronous orphan recovery reports incomplete cleanup, a safe implementation must do one of the following:

- fail mount before root exposure;
- enter explicit failstop/read-only containment while retaining cleanup responsibility;
- prove deadline-safe delegation before exposure.

Successful exposure with required cleanup incomplete remains OIDS-O3.

## Evaluation split reset

| Partition | Contents |
|---|---|
| development | ReiserFS OIDS-O1 and OIDS-O3 source/CFG/minimal replay cases |
| regression validation | Btrfs qualified profile; ext4 positive/negative policy boundary; UBIFS positive/deferred boundary; OCFS2 controlled non-applicable boundary |
| held-out | empty |

ReiserFS retains its historical v0.1 held-out provenance, but it is revealed evidence and therefore becomes v0.2 development data. XFS, F2FS, Btrfs, ext4, UBIFS, OCFS2, and ReiserFS are all ineligible as future v0.2 held-out filesystems.

No v0.2 held-out claim is allowed until a separate pre-reveal preregistration selects and locks a genuinely unrevealed candidate.

## Phase boundary

Phase 13 closes preregistration, bug classification, repair objectives, and split reset only. It does not implement v0.2 semantics. The next phase may add the preregistered diagnostic schema and failure-handling contracts while retaining all v0.1 results as regression or development evidence.

