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
implementation: M43-M46, final2 accepted
code baseline: working tree after 18c0de9
comparison baseline: M38-M41 final8
M37: rejected experiment; excluded from baselines and claims
evaluation schema: 4
oracle records: 539
tests: 329 passed
regression gate: 39 / 39
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
src/effect_extractor.py       metadata effect extraction
src/function_summary.py       interprocedural summaries
src/residual_slicer.py        failure-local slicing and residual proof
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
```

These directories are generated and ignored. Regenerate them when a milestone
comparison is required.

## 11. Next Work

Do not add broad helper-name rules or optimize counts directly.

Select the next family from the 535 pending oracle entries. M43-M46 establish
the partition, target-set, caller-liveness, and evidence infrastructure but do
not reduce the current Linux aggregate. The next milestone should apply these
layers to a reviewed oracle family with concrete cross-function identity or
lifecycle evidence, rather than widening primitive-name extraction.

Every accepted change must preserve:

```text
0 new unreviewed Boundary witnesses
0 unmatched baseline witnesses
6 / 6 manual live residuals
the reviewed Contained fail-stop cases
0 safety regressions
all schema and zero-residual gates
```

Historical M32-M36 details remain available in Git history. M37 is rejected and
must not be reused as a baseline.
