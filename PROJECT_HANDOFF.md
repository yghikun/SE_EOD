# Failure-Path Filesystem Metadata Residual Analysis

Updated: 2026-07-27

## 1. Project Goal

This project analyzes Linux filesystem failure paths and reports filesystem
metadata effects that remain residual at an error exit.

For each failure point `f`:

```text
E_f = metadata effects reaching f
C_f = cancellation or compensation on the error path
T_f = effects protected or transferred to transaction, journal, orphan,
      recovery, or deferred machinery

R_f = Normalize(E_f (+) C_f) - T_f
```

A non-empty `R_f` can establish a function-boundary residual. It is not by
itself a bug verdict: owner liveness and normal failure-domain continuation
need separate source proofs.

The project is not a generic cleanup checker, leak detector, API-pair checker,
or full filesystem protocol verifier.

## 2. Current Accepted State

```text
implementation: M43-M48 accepted
semantic baseline: M43-M46 final2
code baseline: current working tree after the M47 structural refactor
comparison baseline: M38-M41 final8
M37: rejected experiment; excluded from baselines and claims
evaluation schema: 4
oracle records: 539
tests: 329 passed
regression gate: 38 / 38
```

M43-M46 final2 Linux v6.14 result:

| Filesystem | Boundary | LIVE | Contained | UNKNOWN | Review | Reports |
|---|---:|---:|---:|---:|---:|---:|
| Btrfs | 266 | 0 | 8 | 125 | 71 | 470 |
| ext4 | 89 | 0 | 0 | 104 | 167 | 360 |
| XFS | 219 | 0 | 4 | 102 | 140 | 465 |
| F2FS | 39 | 0 | 1 | 49 | 37 | 126 |
| Total | 613 | 0 | 13 | 380 | 415 | 1421 |

Accepted deltas:

| Classification | M36 | final7 | final8 | final8 vs M36 |
|---|---:|---:|---:|---:|
| Boundary | 530 | 542 | 578 | +48 |
| Contained | 34 | 23 | 13 | -21 |
| UNKNOWN | 484 | 446 | 380 | -104 |
| Review | 409 | 451 | 450 | +41 |
| Reports | 1457 | 1462 | 1421 | -36 |

M43-M45 add proof capability but do not move a Linux v6.14 report in this run.
M46 upgrades existing exact transaction primitive evidence without creating
effects. This moves 35 XFS reports from Review to Boundary; UNKNOWN, Contained,
LIVE, total reports, and the effect-witness set are unchanged. Do not describe
Boundary as confirmed bugs or claim that M43-M46 reduce UNKNOWN.

## 3. Classification Contract

The primary classifications are:

```text
FUNCTION_BOUNDARY_RESIDUAL
LIVE_METADATA_RESIDUAL
CONTAINED_METADATA_RESIDUAL
METADATA_RESIDUAL_UNKNOWN
FUNCTION_BOUNDARY_RESIDUAL_REVIEW
OUT_OF_SCOPE
CLOSED
PROTECTED
```

Rules:

- Boundary means a residual crosses the current function's error boundary.
- LIVE requires an explicit owner-liveness proof.
- Contained requires effect-scoped terminal failure-domain proof.
- UNKNOWN requires both a non-empty residual and a concrete proof gap.
- Review is used for source-visible evidence that is not strong enough for a
  primary residual verdict.
- Missing semantics with an empty residual remain diagnostic metrics, not
  findings.
- `UNCLOSED_METADATA_RESIDUAL`, `confidence=candidate`, and
  `candidate_count` are compatibility aliases only.

Never guess safe, guess bug, suppress a direct-source effect by name, or turn a
missing current witness into CLOSED.

## 4. Scope

In scope:

```text
inode and private inode fields
extent, directory, namespace, orphan, and topology metadata
bitmap, free-space, block-group, chunk, and device state
quota, reservation, refcount, transaction, journal, replay, and recovery state
deferred metadata work and recovery-visible counters or flags
```

Out of scope unless they carry metadata completion semantics:

```text
ordinary heap memory
temporary buffers and folio references
path or name buffers
locks
logging
pure local variables
generic resource lifetime
```

The versioned scope contract is
`configs/metadata_scope/metadata_scope_v1.json`.

## 5. Implemented Semantic Layers

M38, owner and scope:

- effect provenance and visibility;
- parent-child ownership and transitive teardown;
- publication, escape, rebind, and teardown ordering;
- failed unpublished construction;
- write-only output, operation descriptor, progress cursor, and retry state.

M39, transaction and failure domain:

- transaction ownership relations;
- transaction abort, recovery abort, fatal shutdown, checkpoint stop, failed
  owner teardown, and caller containment are distinct domains;
- containment is decided per effect, not per helper or whole slice.

M40, interprocedural proof:

- demand summaries and exact error partitions;
- indirect target sets and member identity;
- lexical evidence can reject name-inferred hypotheses but cannot remove
  direct-source evidence or prove closure.

M41, prioritization and audit:

- owner-liveness proofs and LIVE classification;
- primary versus audit report views;
- exact, compatibility, and retained-slice transition reporting;
- semantic-family metrics in schema v4.

Final8 refinements:

- unbound callee-local cleanup is effect-scoped;
- direct descriptor writes survive conditional transaction close;
- summarized RESERVE can match an outer RELEASE wrapper by owner and resource;
- C scalar casts are not indirect calls;
- dirty evidence requires an opening or write effect;
- conditional XFS shutdown Review blockers are preserved through every output
  path.

M43, precise return partitions:

- error partitions retain source-ordered effects through serialization,
  instantiation, and call-site projection;
- checked returns distinguish exact, negative, positive, nonzero,
  nonpositive, and nonnegative outcomes;
- abstract negative outcomes are not treated as the exact value `-1`.

M44, indirect target sets:

- function-pointer target sets support conditional assignments and local
  aliases;
- ops-table resolution uses receiver-local bindings before the file-wide
  initializer fallback;
- a complete target set exports an effect only when every target has the same
  open, cancel, or protect contract.

M45, caller-sensitive owner liveness:

- failure propagation is followed through at most two caller levels;
- an intermediate wrapper must propagate the failure and must not destroy the
  owner or perform a terminal failure-domain action;
- LIVE still requires a final same-owner metadata continuation followed by a
  successful return.

M46, direct source evidence:

- the existing transaction ownership primitives
  `btrfs_record_root_in_trans`, `xfs_trans_ijoin`, `xfs_trans_log_inode`, and
  `xfs_trans_alloc_dir` now use `EXPLICIT_PRIMITIVE` evidence;
- generic atomic, refcount, percpu, link-count, and `WRITE_ONCE` calls are not
  promoted into new metadata effects;
- this evidence-only policy prevents Candidate surface expansion.

M47, structural refactor only:

- split summary construction into `src/summary/` by model, syntax, control
  flow, partitions, indirect targets, identity, per-CPU, and containers;
- split residual slicing support into `src/slicing/` by model, exact return
  partitions, failure-domain proofs, and owner proofs;
- moved effect vocabulary and primitive tables to `src/effects/vocabulary.py`;
- retained `src.function_summary`, `src.residual_slicer`, and
  `src.effect_extractor` as the stable import paths;
- no extraction rule, proof rule, classification, report, or witness changed.

M48, package layout only:

- moved evaluation, triage, oracle, and blocker-impact implementations into
  `src/evaluation/`;
- moved cancellation, failure-domain primitives, owner proofs, transient
  provenance, aggregate snapshots, and SMT helpers into `src/semantics/`;
- retained the former root module names as thin compatibility entry points;
- internal imports use the new canonical package paths.

## 6. Contained Audit

The remaining 13 Contained reports are reviewed fail-stop cases:

```text
Btrfs
  balance_level (5)
  push_nodes_for_insert (2)
  walk_up_proc (1)

XFS
  xfs_defer_finish_noroll
  xfs_defer_finish
  xfs_swap_extents
  4 reports total

F2FS
  written_valid_blocks (1)
```

Reviewed false Contained families:

```text
CLOSED
  do_chunk_alloc
  __btrfs_run_delayed_items
  xfs_trans_alloc
  btrfs_add_link
  __cow_file_range_inline

OUT_OF_SCOPE
  f2fs_allocate_data_block::fragment_remained_chunk

REVIEW
  xfs_bmap_recover_work:532
  xfs_bmap_recover_work:536
```

The two XFS recovery paths retain
`conditional_shutdown_review:ip` and `owner_liveness_unproven`. Conditional
shutdown without preceding dirty or log evidence is not Contained.

## 7. Acceptance Gates

M48 verification against M47:

```text
329 / 329 tests passed
6063 / 6063 EXACT_WITNESS matches
0 compatibility matches
0 new Candidate witnesses
0 unmatched baseline witnesses
539 / 539 oracle entries matched
0 safety regressions
38 / 38 regression checks passed
```

M47 verification against M43-M46 final2:

```text
329 / 329 tests passed
6063 / 6063 EXACT_WITNESS matches
0 compatibility matches
0 new Candidate witnesses
0 unmatched baseline witnesses
539 / 539 oracle entries matched
6 / 6 manual live residuals retained
0 safety regressions
38 / 38 regression checks passed
```

The gate has 38 checks because all four comparisons have zero compatibility
matches. The compatibility-match typing check is conditional and is therefore
not emitted. M47 preserves the accepted aggregate exactly: Boundary 613,
Contained 13, UNKNOWN 380, Review 415, and Reports 1421.

Historical M43-M46 final2 verification against final8:

M43-M46 final2 verification against final8:

```text
329 / 329 tests passed
0 new Candidate witnesses
0 unmatched baseline witnesses
539 / 539 oracle entries matched
0 Candidate -> UNKNOWN transitions
6 / 6 manual live residuals retained
0 lost manual live residuals
0 unmatched oracle entries or effects
0 oracle safety regressions
39 / 39 regression checks passed
```

All 6063 baseline witnesses matched. Btrfs, ext4, and F2FS matched exactly.
XFS has 1474 exact matches and 238 typed `EFFECT_IDENTITY` matches caused only
by M46's evidence upgrade; it has no new or missing effect witness. The
evidence upgrade changes 35 XFS report classifications from Review to Boundary.
The gate contains 39 checks because Btrfs has zero compatibility matches, so
the conditional Btrfs compatibility-typing check is not emitted.

The oracle has 4 entries at their expected final state and 535 retained for
later work. Final8 is an engineering acceptance, not completion of the manual
oracle.

Required invariants:

- direct-source evidence cannot disappear through a lexical rule;
- recovery-visible effects cannot be contained by shutdown alone;
- transaction-external effects cannot be contained by abort alone;
- parent teardown cannot close an escaped or published child;
- compatibility matches must be typed and auditable;
- `RETAINED_SLICE` is never counted as a fix.

## 8. Repository Map

```text
src/frontend/                  C frontend-neutral IR
src/metadata_residual.py      core data model
src/effect_extractor.py       stable effect-extraction entry point
src/effects/                  effect vocabulary and primitive tables
src/evaluation/               evaluation, triage, oracle, and impact tooling
src/function_summary.py       stable interprocedural-summary entry point
src/semantics/                cancellation, ownership, failure-domain, SMT
src/summary/                  summary model and focused construction stages
src/residual_slicer.py        stable failure-local slicing entry point
src/slicing/                  partition, failure-domain, and owner proof stages
src/owner_scope.py            owner and visibility semantics
src/owner_liveness.py         liveness proof
src/failure_domain_primitives.py
src/residual_analyzer.py      analysis orchestration
src/evaluation_harness.py     batch evaluation
src/candidate_review_oracle.py

scripts/evaluate_residuals_batch.py
scripts/compare_residual_runs.py
scripts/audit_candidate_review_oracle.py
scripts/check_m35_regression_gate.py

configs/metadata_scope/
outputs/candidate_review_oracle.jsonl
outputs/confirmed_bugs.md
```

Presentation build directories, render images, inspect files, Python caches,
downloaded sources, and generated evaluation runs are not source code and must
not be committed.

## 9. Commands

Install and test:

```powershell
python -m pip install -r requirements.txt
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -p no:cacheprovider
```

Run one filesystem:

```powershell
python scripts/evaluate_residuals_batch.py `
  linux-sources/linux-v6.14-fs/fs/btrfs `
  --source-root linux-sources/linux-v6.14-fs `
  --output-dir outputs/residual-evaluation-batch/<run-name>
```

Compare runs:

```powershell
python scripts/compare_residual_runs.py <baseline> <current> `
  --output-dir <comparison-output>
```

Audit the oracle:

```powershell
python scripts/audit_candidate_review_oracle.py <four-current-run-paths> `
  --output <audit.json> `
  --fail-on-safety-regression
```

Use `python scripts/check_m35_regression_gate.py --help` for the four-run gate
arguments.

## 10. Accepted Artifacts

```text
outputs/residual-evaluation-batch/linux-v6.14-fs-btrfs-m38-m41-final8-final5
outputs/residual-evaluation-batch/linux-v6.14-fs-ext4-m38-m41-final8-final2
outputs/residual-evaluation-batch/linux-v6.14-fs-xfs-m38-m41-final8-final5
outputs/residual-evaluation-batch/linux-v6.14-fs-f2fs-m38-m41-final8-final2
outputs/residual-evaluation-batch/linux-v6.14-fs-btrfs-m43-m46-final2
outputs/residual-evaluation-batch/linux-v6.14-fs-ext4-m43-m46-final2
outputs/residual-evaluation-batch/linux-v6.14-fs-xfs-m43-m46-final2
outputs/residual-evaluation-batch/linux-v6.14-fs-f2fs-m43-m46-final2
outputs/residual-evaluation-batch/m43-m46-final2-vs-final8/
outputs/residual-evaluation-batch/m43-m46-final2-oracle-audit.json
outputs/residual-evaluation-batch/m43-m46-final2-regression-gate.json
outputs/residual-evaluation-batch/linux-v6.14-fs-btrfs-m47-refactor-final
outputs/residual-evaluation-batch/linux-v6.14-fs-ext4-m47-refactor
outputs/residual-evaluation-batch/linux-v6.14-fs-xfs-m47-refactor
outputs/residual-evaluation-batch/linux-v6.14-fs-f2fs-m47-refactor
outputs/residual-evaluation-batch/m47-refactor-vs-m43-m46-final2/
outputs/residual-evaluation-batch/m47-refactor-oracle-audit.json
outputs/residual-evaluation-batch/m47-refactor-regression-gate.json
outputs/residual-evaluation-batch/linux-v6.14-fs-*-m48-package-layout
outputs/residual-evaluation-batch/m48-package-layout-vs-m47/
outputs/residual-evaluation-batch/m48-package-layout-oracle-audit.json
outputs/residual-evaluation-batch/m48-package-layout-regression-gate.json
```

These directories are generated and ignored. Regenerate them when a milestone
comparison is required.

## 11. Next Work

Do not add broad helper-name rules or optimize counts directly.

The next program is a demand-driven, project-level interprocedural engine.
M43-M46 provide the partition, target-set, caller-liveness, and evidence data
models, but the current bounded project summary builder does not close the
loop from an UNKNOWN demand to source loading, summary solving, call-site
projection, and reslicing.

Current M48 opportunity, counted by unique UNKNOWN reports:

```text
total UNKNOWN                              380
cross-function-related UNKNOWN             359
cross-function-only UNKNOWN                339

SUMMARY_BODY_UNAVAILABLE                   241
ERROR_PARTITION_SELECTION_UNPROVEN          93
INDIRECT_TARGET_SET_UNPROVEN                43
CONDITIONAL_CONTAINMENT_NOT_MUST            28
TRANSACTION_OWNERSHIP_UNPROVEN                6
```

The proof-gap rows overlap and must not be added. Resolving a gap does not
imply safety: the result may become CLOSED, PROTECTED, Contained, Boundary, or
Review. The goal is to replace missing semantics with source proof, not to
force a favorable classification.

### 11.1 Target Architecture

Add a focused package:

```text
src/interproc/model.py          definition, call-edge, demand, and proof keys
src/interproc/source_index.py   project/TU/header/linkage-aware definitions
src/interproc/callgraph.py      direct and indirect call edges
src/interproc/demand.py         requirement-specific work queue
src/interproc/solver.py         SCC and finite-lattice fixpoint
src/interproc/identity.py       must-alias, may-alias, fresh, return, out-param
src/interproc/projection.py     call-site summary instantiation
src/interproc/evidence.py       auditable proof chains and incomplete reasons
```

Required analysis loop:

```text
local slicing
  -> DemandSummaryRequest
  -> exact callee/target resolution
  -> requirement-specific summary solving
  -> caller/callee identity binding
  -> exact error-partition selection
  -> call-site effect projection
  -> reslicing
  -> repeat until fixpoint or a recorded incomplete proof
```

Function lookup must use file, line, name, linkage, translation unit, and
configuration rather than name alone. Static functions resolve only inside
their translation unit; external functions require one exact definition;
header inline definitions are bound in caller context. Multiple definitions,
unresolved preprocessor branches, and macros remain incomplete evidence.

Demand solving must be requirement-specific (`MUST_CANCEL`, `MUST_PROTECT`,
`OWNER_BINDING`, `RETURN_BINDING`, `ERROR_PARTITION`, `TERMINAL_ACTION`,
`CONTAINER_DRAIN`, or `OWNER_TEARDOWN`). Hitting a depth, target, time, or SCC
budget produces UNKNOWN and is never a safety proof.

Effects may close a residual only when they are MUST effects on the selected
error partition and their targets are must-alias. MAY effects, may-alias
bindings, incomplete indirect target sets, and ambiguous return partitions
remain UNKNOWN or Review evidence.

### 11.2 Milestones

M49, production source index and direct-call resolution:

- promote the measurement-only source-definition index into `src/interproc`;
- index `.c` and relevant `.h` definitions with linkage and TU identity;
- resolve same-TU static calls, unique external definitions, and header inline
  bodies without helper-name inference;
- emit typed ambiguity for macros, conditional definitions, and duplicates.

M50, demand-driven cross-TU summaries:

- consume `DemandSummaryRequest` directly from residual slices;
- load and summarize only callees required by a blocking residual;
- cache by source hash, configuration, summary schema, function identity, and
  requested semantic projection;
- iterate demand, projection, and reslicing until no new demand appears.

M51, recursive fixpoint and exact error exits:

- solve acyclic calls bottom-up and recursive call-graph SCCs by monotone
  finite-lattice iteration;
- propagate source-ordered opens, cancels, protects, teardowns, and terminal
  actions per `ErrorExitPartition`;
- select a callee exit only when the caller predicate uniquely proves it;
- keep incomplete or unstable SCC results UNKNOWN.

M52, complete indirect target sets:

- track local function-pointer assignments, conditional assignments, callback
  arguments, receiver-local ops bindings, and cross-file/header initializers;
- export a MUST contract only when the target set is complete and every target
  proves the same contract;
- preserve target and completeness evidence at each indirect call site.

M53, cross-function identity and lifecycle:

- implement must-alias and may-alias with versioned assignments;
- bind parameters, aliases, return identities, output parameters, fresh
  allocation instances, owner fields, container members, and per-CPU slots;
- propagate publication, escape, rebind, and teardown ordering;
- allow cancellation or teardown only for the same proven object instance.

M54, cross-function transaction, owner, and continuation proofs:

- propagate transaction ownership and terminal failure-domain coverage;
- propagate owner teardown only for private, unpublished, unescaped objects;
- follow failure propagation through callers until a source-proven terminal
  action or live same-owner continuation, using bounded fixpoint evidence.

M55, production hardening:

- integrate compilation configuration or `compile_commands.json` when
  available;
- add deterministic persistent caches, proof-chain serialization, performance
  budgets, and typed incomplete states;
- expose per-demand yield and transition audit metrics.

### 11.3 Required Tests

Add focused fixtures for cross-file direct calls, static-name collisions,
header inline functions, multiple external definitions, recursive SCCs,
multi-exit callees, complete and incomplete indirect targets, aliases and
reassignment, return/out-param fresh identities, transaction ownership,
owner escape, and caller continuation. Every safety test needs a paired
near-miss that must remain UNKNOWN.

Every accepted change must preserve:

```text
329 / 329 tests plus new milestone tests
6063 baseline witnesses with typed transitions
0 new unreviewed Boundary witnesses
0 unmatched baseline witnesses
539 / 539 oracle entries
6 / 6 manual live residuals
the reviewed Contained fail-stop cases
0 safety regressions
all schema and zero-residual gates
```

Implement M49-M51 before widening indirect-call or identity propagation. They
target the largest current gaps while keeping the state space bounded. Select
reviewed families from the 535 pending oracle entries for each accepted
transition; do not accept a milestone from aggregate count movement alone.

Historical M32-M36 details remain available in Git history. M37 is rejected and
must not be reused as a baseline.
