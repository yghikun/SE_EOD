# Failure-Path Filesystem Metadata Residual Analysis Handoff

Updated: 2026-07-26

This is the current implementation handoff for the reset project. The active
research object is:

```text
Failure-Path Filesystem Metadata Residual Analysis
```

MetaWindow is only the motivating intuition. The project should not be framed
as a generic metadata checker, memory leak detector, resource cleanup checker,
or typestate verifier. The implementation and paper claim center on filesystem
metadata effects that remain residual after a source-visible failure path.

## 1. Current Claim

For each failure point `f`, compute:

```text
E_f = filesystem metadata effects reaching f
C_f = cancellation or compensation effects on the error path
T_f = effects explicitly protected or transferred to transaction, journal,
      orphan, recovery, or deferred machinery

R_f = Normalize(E_f (+) C_f) - T_f
```

Report `FUNCTION_BOUNDARY_RESIDUAL` only when:

```text
R_f is non-empty
and R_f is STRUCTURAL, ACCOUNTING, or RECOVERY filesystem metadata
and R_f reaches an error exit
and the result is not UNKNOWN
```

If object identity, helper semantics, async handoff, return classification, or
transaction ownership cannot be proven from source, keep the report as
`METADATA_RESIDUAL_UNKNOWN`. Do not guess safe and do not guess bug.

`FUNCTION_BOUNDARY_RESIDUAL` is not a bug verdict. It proves only that `R_f`
crosses the current function's error boundary. Owner liveness and normal
failure-domain continuation require separate source proofs; M38-M41 now
compute those proofs, and retain Boundary when they are unavailable.

`UNCLOSED_METADATA_RESIDUAL`, `confidence=candidate`, and `candidate_count`
remain serialized as M34 compatibility aliases. New consumers must use the
`classification` field and `function_boundary_residual_count`.

An UNKNOWN slice is emitted as a finding only when `R_f` is non-empty. Missing
helper or identity semantics with an empty residual remain in diagnostic
metrics and must not be presented as metadata-residual findings.

Current implementation snapshot:

```text
implementation milestone: M38-M41 (current worktree, final8 accepted)
accepted comparison baseline: M36b-M36g (ad06c19)
M37 status: rejected experiment, excluded from all baselines and claims
evaluation schema: 4
UNKNOWN triage schema: 2
semantic blocker impact schema: 1
oracle records: 539
unit tests: 325
M38-M41 regression gate: 40 / 40
```

## 2. Scope Contract

The filesystem metadata scope gate exists to prevent drift into general cleanup
analysis.

In scope:

```text
inode and private inode fields
extent, directory, namespace, orphan metadata
bitmap, free-space, block group, chunk, device topology
quota, dquot, reservation, refcount metadata
journal, transaction, replay, recovery, delayed metadata work
persistent or recovery-visible counters and flags
```

Out of scope unless connected to filesystem metadata completion semantics:

```text
ordinary kmalloc memory
temporary buffer_head or folio references
path/name buffers
locks
logging
pure local variables
generic helper temporaries
ordinary resource lifetime bugs
```

Boundary rule:

> A supporting object is in scope only when its lifetime carries filesystem
> metadata completion semantics.

Current scope files:

```text
configs/metadata_scope/metadata_scope_v1.json
configs/metadata_scope/README.md
src/metadata_scope.py
```

## 3. Repository State

Active source modules:

```text
src/frontend/
src/cfg.py
src/parser.py
src/function_extractor.py
src/failure_points.py
src/effect_extractor.py
src/function_summary.py
src/cancellation.py
src/aggregate_snapshot.py
src/transient_provenance.py
src/smt_solver.py
src/residual_slicer.py
src/residual_analyzer.py
src/residual_report.py
src/metadata_residual.py
src/metadata_scope.py
src/evaluation_harness.py
src/candidate_triage.py
src/unknown_triage.py
src/semantic_blocker_impact.py
```

Active scripts:

```text
scripts/evaluate_residuals.py
scripts/evaluate_residuals_batch.py
scripts/summarize_candidates.py
scripts/summarize_unknowns.py
scripts/compare_residual_runs.py
scripts/audit_candidate_review_oracle.py
scripts/check_m35_regression_gate.py
scripts/profile_semantic_blockers.py
scripts/download_linux_fs.py
scripts/fetch_kernel_source_file.py
```

Active evidence and documentation:

```text
README.md
PAPER_ROADMAP.md
docs/METADATA_RESIDUAL_ARCHITECTURE.md
docs/PROJECT_ARCHITECTURE.md
outputs/confirmed_bugs.md
outputs/candidate_review_oracle.jsonl
outputs/btrfs_tool_findings_pending_review_2026-07-23.md
outputs/linux-v6.8/btrfs/recover_relocation_qemu_report.md
```

Ignored/generated directories:

```text
.pytest_cache/
__pycache__/
outputs/residual-evaluation/
outputs/residual-evaluation-batch/
linux-sources/
```

The generated `outputs/residual-evaluation*` directories were removed from the
working tree cleanup. They are ignored run artifacts and should be regenerated
when a milestone comparison needs them. Do not treat historical paths in old
milestone notes as required repository files.

## 4. Verification

Current unit-test status:

```text
python -m pytest -q
325 passed
```

Runtime dependencies include `z3-solver>=4.13,<5`. If Z3 is unavailable or an
expression is unsupported, SMT queries return `UNKNOWN`; they must never fall
back to an optimistic proof.

When testing after cache cleanup, use:

```text
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -p no:cacheprovider
```

`git diff --check` currently reports only CRLF normalization warnings on this
Windows working tree, not whitespace errors.

## 5. Architecture

Pipeline:

```text
Linux filesystem source
  -> frontend-neutral FunctionIR
  -> project-wide call-site provenance
  -> function-local CFG
  -> filesystem metadata scope gate
  -> failure-point discovery
  -> metadata effect extraction
  -> function summary generation/application
  -> backward slice for E_f
  -> forward error-path slice for C_f and T_f
  -> identity-aware cancellation
  -> bounded SMT feasibility/balance checks
  -> residual normalization
  -> error-exit verification
  -> JSON/Markdown witness report
```

The project intentionally does not use:

```text
MOCC-SE protocol families
filesystem operation EFSMs
rule registries
validation manifests
large hand-maintained API-pair specifications
sibling-path differential cleanup assumptions
```

## 6. Data Model

The active model is in `src/metadata_residual.py`.

Effect:

```text
MetadataEffect = <Root, Key, Plane, Delta, Value, Site>
```

Planes:

```text
STRUCTURAL
ACCOUNTING
RECOVERY
```

Residual states:

```text
EXPOSED
PROTECTED
CLOSED
UNKNOWN
```

Report kinds:

```text
UNCLOSED_METADATA_RESIDUAL
METADATA_RESIDUAL_UNKNOWN
METADATA_RESIDUAL_REVIEW
OUT_OF_SCOPE
```

Canonical semantic classifications (M35a):

```text
FUNCTION_BOUNDARY_RESIDUAL
LIVE_METADATA_RESIDUAL
CONTAINED_METADATA_RESIDUAL
FUNCTION_BOUNDARY_RESIDUAL_REVIEW
METADATA_RESIDUAL_UNKNOWN
CLOSED
OUT_OF_SCOPE
```

M35a intentionally emits zero `LIVE_METADATA_RESIDUAL` reports. That label
requires owner-liveness and failure-domain continuation proofs that are not yet
implemented.

Effect evidence levels:

```text
DIRECT_SOURCE
EXPLICIT_PRIMITIVE
NAME_INFERRED
```

`UNCLOSED_METADATA_RESIDUAL` requires at least one residual effect with direct
source or explicit primitive evidence. A residual composed only of
name-inferred helper effects is `METADATA_RESIDUAL_REVIEW`, not a candidate.

M32b adds audit-only provenance to effects excluded as automatic operation
state. Each `TransientArgumentProvenance` records the parameter/index/pointee
type, caller function/local/type, and call site. The effect is retained in
`ResidualSlice.out_of_scope_effects` so comparison runs can prove
`Candidate -> OUT_OF_SCOPE` rather than treating it as a missing witness.

The state labels are implementation support. They are not a protocol EFSM and
should not be presented as a complete typestate model.

## 7. Summary Model

The main precision work is in `src/function_summary.py` and
`src/residual_slicer.py`.

Current summary fields include:

```text
opens
cancels
protects
error_opens
error_cancels
error_protects
may_fail
returns
output_mapping
ownership_transfer_roots
lifecycle_facts
exposure_facts
cleanup_footprints
owner_teardowns
escaping_parameters
exit_effects
unresolved_calls
unknown_causes
```

Exit-sensitive effects:

```text
success_must
success_may
error_must
error_may
error_complete
```

Only `ERROR_MUST` cancellation/protection is allowed to resolve a failure-path
residual. `MAY` evidence is audit information and must not close a residual.

Exposure facts:

```text
FRESH_LOCAL
PRIVATE_LOCAL
BOUND_TO
RETURNED
OUTPUT_BOUND
PUBLISHED_IN_FIELD
MEMBER_OF_CONTAINER
```

Cleanup footprints:

```text
root_pattern
key_pattern
plane
inverse_delta
value_pattern
owner_or_container
```

Cleanup matching remains footprint-bounded. A helper named `cleanup`,
`destroy`, `release`, or `abort` must not be treated as closing arbitrary
metadata effects.

## 8. UNKNOWN Policy

UNKNOWN is expected and desirable when source evidence is insufficient.

Current taxonomy in `src/unknown_triage.py`:

```text
structural:
  indirect_call
  indirect_call_on_error_path
  function_pointer_parameter_call
  unbound_callee_local_identity
  unresolved_identity
  unclassified_return_exit
  callee_failure_effect_order_unknown
  lifecycle_exit_partition_unproven
  success_only_publication_not_proven_on_error

missing_summary:
  unresolved_metadata_helper_on_error_path
  return_bound_unresolved_helper
  cleanup_effect_scope_unproven
  unresolved_metadata_helper
  source_visible_helper_without_summary

other:
  anything not yet classified
```

Use this taxonomy for milestone reporting. A reduction in UNKNOWN is useful
only if candidate count does not rise for the wrong reason and known findings
remain visible.

Measurement vocabulary:

```text
failure_slices_total:
  every discovered failure-anchored slice

residual_state_counts.UNKNOWN:
  all diagnostic UNKNOWN slices, including slices with no residual

METADATA_RESIDUAL_UNKNOWN / unknown_count:
  emitted UNKNOWN findings with a non-empty residual

UNCLOSED_METADATA_RESIDUAL / candidate_count:
  emitted source-supported candidate findings

METADATA_RESIDUAL_REVIEW / review_count:
  emitted name-inferred residual hypotheses

unknown cause counts:
  cause mentions, not distinct reports; one report can contain several causes
```

Never compare diagnostic UNKNOWN slices directly with emitted candidate count.

## 9. Last Measured State

### Btrfs M30-M31

M30 temporal-UNKNOWN audit:

```text
mainline, fs/btrfs/tests/* excluded:
  failure slices: 2132
  CLOSED: 1443
  PROTECTED: 31
  EXPOSED: 311
  UNKNOWN diagnostic slices: 347

emitted findings:
  221 UNCLOSED_METADATA_RESIDUAL
  155 METADATA_RESIDUAL_UNKNOWN with non-empty residual
  90 METADATA_RESIDUAL_REVIEW
  466 total findings
  0 zero-residual findings

diagnostic-only UNKNOWN:
  192 slices with no residual
```

M30 adds two conservative precision rules. A failure slice carries the failed
result constraint through later `if` conditions, so a success-only cleanup is
not considered reachable from a known error edge. A reaching unknown cannot
cancel a direct effect that source order proves happens later. In all other
cases UNKNOWN remains blocking: argument-name mismatch is not treated as an
alias proof. This reduces residual-bearing UNKNOWN findings by 22 without the
large candidate inflation seen with a shallow identity-disjointness heuristic.

M31 adds bounded Z3 evidence in three places. It prunes a CFG edge only when
the failed-result constraint and branch predicate are UNSAT; it closes a group
of visible `INC`/`DEC` deltas only when their symbolic net is provably zero;
and it accepts an error-path cancellation or protection only when its block
dominates every feasible error exit. Unsupported predicates, pointer aliasing,
error-pointer semantics, and opaque callees stay `UNKNOWN`; Z3 is not used as
a C memory-model or general bug prover.

M31 final comparable run (`linux-v6.14-fs`, `fs/btrfs/tests/*` excluded):

```text
failure slices: 2132
CLOSED / PROTECTED / EXPOSED / diagnostic UNKNOWN: 1443 / 30 / 311 / 348
UNCLOSED_METADATA_RESIDUAL: 221
METADATA_RESIDUAL_UNKNOWN with non-empty residual: 159
METADATA_RESIDUAL_REVIEW: 90
zero-residual findings: 0
```

Compared with M30, candidate count remains 221 and residual-bearing UNKNOWN
changes from 155 to 159. The new conservative cases are bounded conditional
cleanup/protection witnesses, not a broad candidate-to-UNKNOWN conversion.

The old `267 EXPOSED + 368 diagnostic UNKNOWN` presentation was misleading:
191 UNKNOWN slices had no residual. These remain diagnostics only.

### Four-Filesystem M31 Baseline

All runs use Linux v6.14, the same metadata-scope configuration, bounded Z3,
the confirmed-bug mapping, and exclude each filesystem's test subtree.

| Filesystem | Failure slices | CLOSED | PROTECTED | EXPOSED | Diagnostic UNKNOWN | Candidate | Residual UNKNOWN | Review |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Btrfs | 2132 | 1443 | 30 | 311 | 348 | 221 | 159 | 90 |
| ext4 | 877 | 444 | 0 | 246 | 187 | 80 | 117 | 166 |
| XFS | 3072 | 2245 | 1 | 463 | 363 | 191 | 171 | 272 |
| F2FS | 539 | 383 | 0 | 78 | 78 | 46 | 55 | 32 |
| Total | 6620 | 4515 | 31 | 1098 | 976 | 538 | 502 | 560 |

Every run has `zero_residual_finding_count = 0`.

Generated run directories:

```text
outputs/residual-evaluation-batch/linux-v6.14-fs-btrfs-main-m31-z3-final
outputs/residual-evaluation-batch/linux-v6.14-fs-ext4-m31-z3
outputs/residual-evaluation-batch/linux-v6.14-fs-xfs-m31-z3
outputs/residual-evaluation-batch/linux-v6.14-fs-f2fs-m31-z3
```

These directories are ignored artifacts and may be absent after cleanup.

### Cross-Filesystem UNKNOWN Audit

The common UNKNOWN causes are source-model gaps, not Z3 failures. Counts below
are cause mentions and can overlap within one report.

| Cause | Btrfs | ext4 | XFS | F2FS | Total |
|---|---:|---:|---:|---:|---:|
| unresolved metadata helper on error path | 107 | 143 | 65 | 79 | 394 |
| unbound callee-local identity | 106 | 56 | 31 | 13 | 206 |
| unclassified return exit | 33 | 16 | 40 | 10 | 99 |
| callee failure-effect order unknown | 9 | 5 | 16 | 1 | 31 |
| indirect call | 4 | 2 | 105 | 0 | 111 |

The first three categories are the best reusable reduction targets. XFS's
indirect-call concentration is important but is not a four-filesystem issue.
Do not resolve any category by trusting helper names or argument-name mismatch.

### Cross-Filesystem Candidate Audit

There is no meaningful exact residual identity shared by all filesystems; their
metadata structures are different. The shared extractor shapes are:

```text
DIRECT_SOURCE STRUCTURAL SET: 408 residual effects
DIRECT_SOURCE ACCOUNTING SET: 369 residual effects
DIRECT_SOURCE RECOVERY SET: 360 residual effects
NAME_INFERRED RECOVERY ADD: 264 residual effects
NAME_INFERRED ACCOUNTING INC: 114 residual effects
```

These are residual-effect counts, not report counts. Broadly suppressing these
shapes would destroy recall. Current manual witnesses instead identify two
source-provable general precision gaps:

```text
aggregate snapshot restore:
  f2fs_remount() saves sbi->mount_opt, changes option fields, then restores the
  aggregate with sbi->mount_opt = org_mount_opt on error. M32a now recognizes
  this rollback through a source-proven snapshot relation.

transient operation arguments:
  xfs_rename() changes src_name->type on a struct xfs_name operation argument;
  this is not persistent filesystem metadata. F2FS uses the same semantics for
  direct fields of caller-local struct dnode_of_data operation state. M32b now
  removes these only through source-derived transient-argument provenance.
```

ext4's largest recurring shape is journal access registration on a caller-owned
`handle`. It requires transaction/journal ownership evidence; it must not be
closed merely because the helper name contains `journal_get_*`.

### Rejected Precision Experiment

An M32 experiment added top-level `fs/*.c` bodies as summary-only inputs for
all four filesystem runs. It reduced a few duplicate cause mentions but changed
none of the four candidate or residual-UNKNOWN totals. The code was reverted.
Do not reintroduce broad shared-summary loading without a fixture showing a
report-level state transition and a real-run count improvement.

Confirmed-bug alignment is currently function-only, not failure-site recall.
For in-scope Btrfs records:

```text
functions in source:
  btrfs_init_new_device
  btrfs_recover_relocation
  reserve_chunk_space

reported:
  btrfs_init_new_device
  btrfs_recover_relocation

missed:
  reserve_chunk_space
```

`confirmed_bugs.md` is deduplicated by bug id. The current ledger contains 18
unique records; 12 are marked in-scope by the metadata scope contract.

Known mapped behavior should remain visible after every milestone:

```text
btrfs_init_new_device:
  the commit failure candidate contains device accounting, seed-list topology,
  and the active `s_bdev` / `latest_dev` pointer updates

btrfs_recover_relocation:
  the btrfs_commit_transaction failure candidate contains the direct
  fs_root->reloc_root residual; recovery evidence remains traceable through
  confirmed_bugs.md and outputs/linux-v6.8/btrfs/recover_relocation_qemu_report.md

btrfs_dev_replace_start:
  P3 is a candidate at mark_block_group_to_copy(), with target device list and
  num_devices/open_devices residuals

btrfs_reconfigure:
  P1 is a candidate at btrfs_check_features(), with the direct
  BTRFS_FS_STATE_REMOUNTING bit residual
```

P2-like ordinary resource lifetime bugs must not be counted as core
filesystem-metadata residual recall unless independently tied to metadata
completion semantics.

## 10. Evaluation Commands

Regenerate one filesystem baseline by setting `$filesystem` to `btrfs`, `ext4`,
`xfs`, or `f2fs`:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$filesystem = 'btrfs'
python scripts/evaluate_residuals_batch.py `
  "linux-sources/linux-v6.14-fs/fs/$filesystem" `
  --source-root linux-sources/linux-v6.14-fs `
  --confirmed-bug-mapping outputs/confirmed_bugs.md `
  --exclude-glob "fs/$filesystem/tests/*" `
  --output-dir "outputs/residual-evaluation-batch/linux-v6.14-fs-$filesystem-current"
```

Summarize UNKNOWN:

```powershell
python scripts/summarize_unknowns.py `
  outputs/residual-evaluation-batch/linux-v6.14-fs-btrfs-current
```

Summarize candidates:

```powershell
python scripts/summarize_candidates.py `
  outputs/residual-evaluation-batch/linux-v6.14-fs-btrfs-current
```

Compare two runs:

```powershell
python scripts/compare_residual_runs.py `
  outputs/residual-evaluation-batch/<baseline> `
  outputs/residual-evaluation-batch/<current> `
  --output-dir outputs/residual-evaluation-batch/<current>/transition-audit
```

The comparison uses per-effect witnesses, not report counts. Its stable key is
the filesystem, function, failure site, error exit, and complete effect source
identity (`root`, `key`, `plane`, `delta`, `value`, evidence, and effect site).
It writes:

```text
report_transition_matrix.json
resolved_candidates.json
resolved_unknowns.json
new_candidates.json
lost_known_witnesses.json
```

`CLOSED` and `PROTECTED` are read from file-level `evaluation.json` slices,
because emitted reports intentionally omit them. A baseline witness missing
from the current output is `UNMATCHED`, never a resolved finding. The old
UNKNOWN taxonomy matrix remains a compatibility projection, but it folds
`UNMATCHED` into its historical `out_of_scope_or_removed` bucket and must not
be used to claim a resolution.

Generated evaluation outputs are ignored and should not be committed unless the
research process explicitly chooses to version a curated, small artifact.

## 11. Milestone History

Condensed history:

```text
M0  Stabilized residual data model and metadata scope.
M1  Added failure point discovery.
M2  Added raw filesystem metadata effect extraction.
M3  Added function summaries.
M4  Added identity-aware cancellation.
M5  Added failure-anchored backward/forward slicing.
M6  Added residual analyzer and witness reports.
M7  Added evaluation harness.
M8  Added real-source precision gates for UNKNOWN safety.
M9  Added batch evaluation.
M10 Split mainline and fs/btrfs/tests evaluation.
M11 Added UNKNOWN triage and relevance gate.
M12 Added known-cleanup de-duplication and initializer alias filtering.
M13 Added candidate triage.
M14 Added transient object lifetime gate.
M15 Improved identity and source-scope precision.
M16 Added source-derived fresh ownership transfer.
M17 Added cross-function summary propagation.
M18 Improved accessor and candidate reduction behavior.
M19 Added source-derived lifecycle facts and exit-sensitive effects.
M20 Added narrow local pointer aliases and fresh-object visibility filtering.
M21 Made callee failure effects stricter with MUST/MAY partitions.
M22 Added exposure-aware identity and UNKNOWN resolution matrix support.
M23 Added source-proven no-op helpers and cleanup footprints.
M24 Added bounded indirect target recovery for no-op callbacks.
M25 Added UNKNOWN taxonomy accounting.
M26 Added header inline summary coverage.
M27 Aligned documentation and output wording to filesystem metadata residual scope.
M28 Added transaction-abort protection, transient scope gates, fresh inode
    publication binding, and runtime-status exclusion.
M29 Separated zero-residual UNKNOWN diagnostics from findings, added effect
    evidence levels and METADATA_RESIDUAL_REVIEW, deduplicated confirmed bugs,
    and added function-level in-scope coverage metrics.
M30 Added failed-value CFG pruning, effect-local temporal UNKNOWN handling,
    caller-site provenance for same-file summaries, and direct summaries for
    externally visible same-file helpers.
M31 Added bounded Z3 failure-branch feasibility and counter balance proofs,
    plus feasible-error-path dominance for conditional cleanup/protection.
M32.0 Added source-stable, per-effect report-transition auditing. It reads
    full file-level slices to distinguish CLOSED and PROTECTED from a missing
    emitted report, records new candidates and lost known witnesses, and keeps
    report-only historical artifacts as an explicitly lower-fidelity fallback.
M32a Added source-proven aggregate snapshot restore. RESTORE is accepted only
    for the same owner aggregate, a dominating pre-mutation capture, an
    unmodified/unescaped snapshot field, and a restore that dominates every
    feasible error exit.
M32b Added project call-site provenance for automatic operation arguments.
    Only DIRECT_SOURCE effects whose root exactly equals a universally proven
    transient parameter move to OUT_OF_SCOPE; reached persistent objects and
    NAME_INFERRED helper effects remain in scope.
M32c Added source-proven exhaustive safe-list cleanup identities. A cleanup
    binds only an unconditional `list_for_each_entry_safe` drain of an exact
    parameter-owned container and intrusive member field. Comparator state
    RETAINED_REACHING prevents a still-visible reaching effect from being
    misreported as UNMATCHED when residual projection selects another effect.
```

Historical detailed run outputs under `outputs/residual-evaluation*` have been
removed from the working tree. The handoff now records milestone intent rather
than treating those directories as persistent project files.

## 12. Milestone Program

Implemented in the current M38-M41 worktree:

```text
M38a: rebuild the decision surface from the accepted M36b-M36g baseline and
      freeze proof/transition contracts
M38b: parent-child owner hierarchy and transitive whole-owner teardown
M38c: unpublished failed-mount construction and teardown
M38d: exact output, operation-state, cursor, and retry provenance
M39:  transaction ownership and effect-scoped failure-domain containment
M40:  exact interprocedural relation closure for residual-bearing UNKNOWNs
M41:  owner-liveness completion and final report prioritization
```

M37 is deliberately excluded from this accepted sequence. The generated M37
semantic-audit runs are a rejected experiment, not a project baseline; see
Section 22. The next accepted milestone number is M38.

This recommendation supersedes both the historical M32 plan below and the old
M36b-only recommendation. M36a correctly showed that broad summary loading is
not justified, while the M32d manual oracle showed a larger paper-level
constraint: 418 reviewed reports awaited owner/scope semantics and 105 awaited
failure-domain semantics. The next program must therefore reduce Boundary and
UNKNOWN populations through reusable source-proven semantic layers, not by
adding helper-name rules. Demand-driven summary closure remains necessary, but
it moves behind the proof contracts and is selected only from post-M36
residual-bearing sole blockers.

M32.0: report-level state-transition audit (implemented).

```text
The unit of comparison is a residual effect witness, not a finding count:
  filesystem + function + failure site + error exit + complete effect identity.

For a current CLOSED/PROTECTED result, the original effect must still be found
in the current slice's reaching effects. Therefore a disappeared report cannot
be silently classified as fixed. Each comparison emits the transition matrix,
resolved candidate/UNKNOWN ledgers, new candidates, and unmatched prior known
witnesses. Review these artifacts before accepting any count reduction.
```

M32a: aggregate snapshot restore (implemented).

```text
AggregateSnapshotRelation records snapshot_root, owner_root, aggregate_key,
capture_site, capture_block, and source_identity. A RESTORE cancellation is
created only when the local aggregate is copied from the exact owner, capture
dominates the field SET, the snapshot field is not overwritten or escaped, and
the same-owner restore dominates every feasible error exit. Function-like
owner macros are expanded only from source-visible local includes; names such
as old/orig/saved provide no evidence.

Negative fixtures cover conditional restore, capture after mutation, capture
that does not dominate mutation, same-field snapshot mutation, address escape,
different-owner restore, and partial field restore.

Linux v6.14 four-filesystem result:

| Filesystem | Candidate M31 -> M32a | Residual UNKNOWN | Review M31 -> M32a | Effect transitions |
|---|---:|---:|---:|---|
| Btrfs | 221 -> 221 | 159 -> 159 | 90 -> 90 | all unchanged |
| ext4 | 80 -> 80 | 117 -> 117 | 166 -> 166 | all unchanged |
| XFS | 191 -> 191 | 171 -> 171 | 272 -> 272 | all unchanged |
| F2FS | 46 -> 41 | 55 -> 55 | 32 -> 36 | 18 Candidate effects -> CLOSED; 24 -> REVIEW |

For F2FS, CLOSED changes 383 -> 384 and EXPOSED 78 -> 77. Every changed
Candidate effect is in f2fs_remount(); no filesystem has a new Candidate or an
UNMATCHED baseline witness. In the parse_options() slice, the three direct
mount-option SET residuals become zero and the slice becomes CLOSED.

Generated comparison directories:
  outputs/residual-evaluation-batch/linux-v6.14-fs-*-m32a-snapshot*/transition-audit
```

M32b: transient operation arguments (implemented).

```text
The proof is universal over visible direct call sites. Every call must pass the
address of a type-compatible automatic aggregate; static locals, caller
parameters, heap/global pointers, mismatched types, multiple callee definitions,
returns, and source-visible non-local stores reject the proof. Direct and
container aliases are followed through unique visible helpers. Opaque calls are
treated only as synchronous borrows: a call is not a storage event, and this is
not a whole-program C escape-analysis claim.

Only a DIRECT_SOURCE effect whose root exactly equals the proven parameter is
excluded. `arg->inode->i_blocks` remains in scope because its root crosses into
a reached object. NAME_INFERRED helper effects also remain in scope.

Negative fixtures cover caller parameters, heap/global/static storage, type
mismatch, any nonlocal caller or callee store, direct and transitive alias
return/publication, duplicate definitions, visible helper publication, and
reached persistent fields. Positive fixtures cover multiple universal call
sites, visible synchronous borrow chains, local aggregate containers, opaque
synchronous borrows, and the XFS-like operation descriptor.

Linux v6.14 M32a -> M32b final result:

| Filesystem | Candidate | Residual UNKNOWN | Review | State changes |
|---|---:|---:|---:|---|
| Btrfs | 221 -> 221 | 159 -> 159 | 90 -> 90 | none |
| ext4 | 80 -> 80 | 117 -> 117 | 166 -> 166 | none |
| XFS | 191 -> 182 | 171 -> 171 | 272 -> 278 | CLOSED 2245 -> 2248; EXPOSED 463 -> 460 |
| F2FS | 41 -> 38 | 55 -> 55 | 36 -> 36 | CLOSED 384 -> 387; EXPOSED 77 -> 74 |

XFS has nine Candidate-effect witnesses -> OUT_OF_SCOPE, all for
`xfs_rename()` and `src_name->type = XFS_DIR3_FT_CHRDEV` at line 2156. The 35
Candidate-effect witnesses -> REVIEW are mixed slices where that same direct
effect is removed and only NAME_INFERRED transaction effects remain. One
already-CLOSED `xfs_trim_gather_extents()` cursor effect also becomes explicitly
OUT_OF_SCOPE.

F2FS has nine Candidate-effect witnesses -> OUT_OF_SCOPE across three reports.
All target direct fields on a caller-local `struct dnode_of_data`: the
`ofs_in_node` cursor in `f2fs_do_zero_range()` / `reserve_compress_blocks()`,
and `node_changed` / `node_page` operation state in `truncate_nodes()` /
`truncate_partial_nodes()`. Effects reached through `dn->inode` or node pages
remain in scope.

Every filesystem has new_candidate_count=0, UNMATCHED=0, no resolved UNKNOWN,
and zero_residual_finding_count=0.

Generated final runs:
  outputs/residual-evaluation-batch/linux-v6.14-fs-*-m32b-transient-final
```

M32c: exhaustive safe-list cleanup identity (implemented).

```text
The accepted relation requires this exact source evidence:
  list_for_each_entry_safe(iter, next, &param->container, member)
  followed by an unconditional top-level list_del(&iter->member) or
  list_del_init(&iter->member) in a loop body with no break, continue, goto,
  or return.

Both iterator variables must be pointer locals. The container must be a field
path rooted at a parameter. The intrusive member field must match exactly.
The relation is preserved through summary parameterization and caller-site
projection. One drain may cancel multiple ADD effects only for the same
container and member field; it cannot cross either identity boundary.

Negative fixtures cover conditional/early-exit drains, a different member
field, a non-parameter/global container, cross-container cancellation, and
cross-member cancellation. The end-to-end fixture proves that one helper drain
retains provenance at the caller and closes two distinct member ADD effects.

The tempting case-insensitive EXT4_SB(sb) extension was tested and rejected.
It reduced ext4 UNKNOWN 117 -> 115 but also produced 88 new Candidate effect
witnesses and 23 unmatched baseline witnesses because collapsing the reached
ext4_sb_info object to sb changed effect identity. Suffix/name evidence is not
enough to justify that alias relation, so the experiment was reverted.

Linux v6.14 M32b -> M32c final result:

| Filesystem | Candidate | Residual UNKNOWN | Review | unbound report causes |
|---|---:|---:|---:|---:|
| Btrfs | 221 -> 231 | 159 -> 148 | 90 -> 91 | 106 -> 78 |
| ext4 | 80 -> 80 | 117 -> 117 | 166 -> 166 | 56 -> 56 |
| XFS | 182 -> 182 | 171 -> 170 | 278 -> 279 | 31 -> 30 |
| F2FS | 38 -> 38 | 55 -> 55 | 36 -> 36 | 13 -> 13 |

Btrfs state counts change CLOSED 1443 -> 1443, EXPOSED 311 -> 322,
UNKNOWN 348 -> 337. free_conflicting_inodes() becomes an exact drain of
ctx->conflict_inodes. In btrfs_log_inode(), 30 effect witnesses move UNKNOWN
-> Candidate, five remain explicitly RETAINED_REACHING, and one separate
Btrfs witness moves UNKNOWN -> Review. This is a precision migration, not a
count-only suppression.

XFS state counts change CLOSED 2248 -> 2249, EXPOSED 460 -> 461,
UNKNOWN 363 -> 361. One xfs_trim_rtextents() witness moves UNKNOWN -> Review
after the source-visible list drain in xfs_discard_free_rtdev_extents() is
bound. ext4 and F2FS are effect-for-effect unchanged. put_gc_inode() binds its
list drain but correctly remains UNKNOWN because its radix-tree cleanup still
depends on the iterated local identity.

All four final comparisons have new_candidate_count=0 and UNMATCHED=0. The
confirmed bug mapping categories are unchanged. Test suite: 198 passed.

Generated final runs:
  outputs/residual-evaluation-batch/linux-v6.14-fs-*-m32c-container-proven-final
```

M32d: exact per-CPU slot identity (implemented).

```text
PerCpuSlotRelation is intentionally separate from ordinary owner aliases. It
records the parameter-field base, pointer slot local, scalar index local, exact
loop/accessor sites, and source identity. The only accepted source shape is a
for_each_possible_cpu(index) body with one top-level
slot = per_cpu_ptr(param->field, index) assignment. The slot has no initializer
or other assignment, and the loop has no break, continue, goto, or return.

Only slot-rooted effects in that same loop body and strictly after the accessor
are rewritten to PER_CPU_SLOT(param->field). The index stays in structured
provenance and is not embedded in the root. The relation survives summary
parameterization and caller projection. Different loop/accessor names, global
bases, index mismatch, non-pointer slots, early effects, and reassignment are
rejected by negative fixtures.

The selected TOC constraint was xfs_inodegc_init_percpu(): its unbound local gc
was the sole blocker for seven xfs_fs_fill_super() reports, while each report's
quota residual was already a DIRECT_SOURCE SET of sb->s_quota_types. The real
Linux v6.14 body now exports:
  PER_CPU_SLOT(arg0->m_inodegc)->work / INIT_DELAYED_WORK / CLOSE
and has no unbound_callee_local_identity cause. This proves helper-local
identity completeness; it does not claim cancellation of the quota residual.

Linux v6.14 M32c -> M32d final result:

| Filesystem | Candidate | Residual UNKNOWN | Review | State changes |
|---|---:|---:|---:|---|
| Btrfs | 231 -> 231 | 148 -> 148 | 91 -> 91 | none |
| ext4 | 80 -> 80 | 117 -> 117 | 166 -> 166 | none |
| XFS | 182 -> 190 | 170 -> 163 | 279 -> 278 | EXPOSED 461 -> 468; UNKNOWN 361 -> 354 |
| F2FS | 38 -> 38 | 55 -> 55 | 36 -> 36 | none |

For XFS, seven quota effect witnesses move UNKNOWN -> Candidate at failure
lines 1618, 1622, 1626, 1630, 1737, 1741, and 1772. At xfs_mountfs() line
1817, the same quota effect was previously RETAINED_REACHING because the slice
already had one certain NAME_INFERRED review residual; after the blocker is
removed, the direct quota residual and that review witness both project as
Candidate. This explains report Candidate 182 -> 190 without a new witness.

XFS unbound-callee-local report mentions fall 30 -> 23 and sole-cause reports
fall 24 -> 17. Witness totals are unchanged for every filesystem (Btrfs 2346,
ext4 1330, XFS 2065, F2FS 634). Every comparator has new_candidate_count=0 and
UNMATCHED=0; confirmed bug mapping categories and zero_residual_finding_count=0
are unchanged. Test suite: 208 passed.

Generated final runs:
  outputs/residual-evaluation-batch/linux-v6.14-fs-*-m32d-percpu-final

The next structural constraints are radix/tree iteration and other exact
container relations. Continue demand-first from reports where one helper is a
sole blocking cause. Do not generalize from suffixes, types, argument names, or
local names, and do not repeat the unchanged broad fs/*.c shared-summary
experiment.
```

M32d Candidate source review (completed 2026-07-24).

```text
The review filters each all_reports.json by confidence == candidate before
assigning stable IDs.  It covers all 539 Candidate reports individually:
  Btrfs 231, ext4 80, XFS 190, F2FS 38.

Use two independent axes:
  report_validity = TRUE_RESIDUAL / FALSE_POSITIVE / INCONCLUSIVE
  bug_status = CONFIRMED / LIKELY / NEEDS_REPRO / NO_BUG /
               CONFIRMED_DIFFERENT_DEFECT

A function-boundary residual is not automatically a bug.  The decisive test is
whether a live owner can carry it past transaction abort, filesystem shutdown,
failed-mount teardown, or object destruction and then continue ordinary work.

Source verdict totals:
  true or likely issue       6
  different confirmed defect 2
  contained residual       106
  false alarm              421
  unresolved                 4

Report-validity totals:
  TRUE_RESIDUAL             112
  FALSE_POSITIVE            423
  INCONCLUSIVE                4

The six true/high-value Candidate reports are:
  BTRFS-027 btrfs_dev_replace_start()       pending P3
  BTRFS-162 btrfs_recover_relocation()      confirmed bug #7
  BTRFS-168 btrfs_reconfigure()             pending P1
  BTRFS-216 btrfs_create_uuid_tree()        new, needs reproduction
  BTRFS-220 btrfs_init_new_device()         confirmed bugs #16-#18
  EXT4-046  make_indexed_dir()               new, likely bug

BTRFS-216 causal chain:
  uuid tree commit succeeds -> fs_info->uuid_root remains published ->
  kthread_run(uuid scan) fails -> RO-to-RW remount returns an error -> next
  remount skips create_uuid_tree because uuid_root is non-NULL -> unlike
  open_ctree, btrfs_remount_rw has no generation-mismatch UUID rescan.  Fault
  injection must determine whether an empty/incomplete UUID tree becomes live.

EXT4-046 causal chain:
  ext4_append grows and journals directory size -> old dirents move to bh2 ->
  block zero is rewritten as a dx root -> casefold ext4fs_dirhash can fail its
  PATH_MAX allocation -> direct return bypasses out_frames and its required
  ext4_mark_inode_dirty-on-error handling.  The same shape is present in the
  local v7.1 source.  Add a casefold hash allocation fault-injection test.

BTRFS-026 and BTRFS-146 are FALSE_POSITIVE for the Candidate's metadata effect,
but their paths contain confirmed different defects: the replacement device
resource leak (pending P2) and mapping_node leak (confirmed bug #6).

Four btrfs_orphan_cleanup reports (BTRFS-088..091) remain INCONCLUSIVE.  The
permanent bit has documented one-shot/reentrancy semantics, but this review did
not prove that every early error is safe without retrying cleanup.

F2FS-021 is now resolved as TRUE_RESIDUAL / NO_BUG.  change_curseg() can fail
only after the SSR summary read; the terminal f2fs_get_meta_page_retry failure
calls f2fs_stop_checkpoint(), so the changed SIT/curseg state is quarantined and
cannot continue as an ordinary live update.

Important corrected assumptions:
  create_space_info() is not the suspected leak: sysfs failure calls
  kobject_put(), whose space_info_release() frees the object; earlier linked
  space-info types are removed by failed-mount teardown.
  btrfs_load_block_group_zone_info() frees physical_map, active, and zone_info
  on calculate_alloc_pointer failure, and its caller drops the unpublished
  block-group cache.
  btrfs_advance_sb_log() must retain wp/condition progress because the
  superblock bio was submitted before ZONE_FINISH; rolling the pointer back
  would target the wrong next write location.
  XFS quota reservation Candidates at lines 943 and 949 are explicit unwind
  false positives; unwind_grp/unwind_usr reverse prior reservations.
  XFS dirty transaction residuals are not ordinary recovery: xfs_trans_cancel
  explicitly forces filesystem shutdown when dirty state cannot be restored.

Artifacts:
  outputs/candidate_review_m32d.md     compact 539-row human ledger
  outputs/candidate_review_m32d.csv    full structured ledger
  outputs/candidate_review_m32d.jsonl  full structured ledger
  scripts/build_candidate_review.py    deterministic generator and count gate

Candidate bug precision from this source review is 6 / 539 = 1.11% if the
needs-reproduction UUID-tree item is included, or 5 / 539 = 0.93% without it.
This does not mean the analyzer is useless: 112 reports describe real
function-boundary residuals.  It means the current TOC constraint is lifecycle
and failure-domain modeling, not effect extraction.  The next precision work
should target, in order: failed-object ownership, transaction/fatal containment,
output/cursor provenance, then intentional progress/cache state.  Do not spend
the next milestone expanding effect recall before these Candidate families are
demoted or protected.
```

M32e: exact recall oracles.

```text
Build an exact fixture for reserve_chunk_space bug #15.
Add failure-site/effect expectations to confirmed bug records.
Require a post_commit_list witness for #16 rather than accepting a co-located
commit-path topology candidate as full bug-level recall.
Keep P1, P3, #7, and #16-#18 failure sites explicitly visible during precision
work.
```

For every M32 substep, record before/after values for all four filesystems. A
change is accepted only when the targeted taxonomy or candidate family falls,
known witnesses remain visible, and no unrelated candidate surge occurs.

## 13. Gate Checklist

Every milestone must check:

```text
unit tests pass
M32 transition audit has no unexplained UNMATCHED known witness
UNKNOWN count changes by taxonomy, not only total
candidate count does not rise without review
all four filesystem baselines are compared
known mapped findings remain visible
P3 remains candidate/UNKNOWN-visible
P2-like ordinary resource lifetime findings stay out of the core claim
new CLOSED/PROTECTED resolutions have source evidence
zero_residual_finding_count remains zero
generated outputs are not mistaken for active documentation
```

The correct end state is not UNKNOWN equals zero. The correct end state is:

```text
source-provable residuals -> UNCLOSED_METADATA_RESIDUAL
name-only residual hypotheses -> METADATA_RESIDUAL_REVIEW
source-provable cancellation/protection -> CLOSED or PROTECTED
source-provable private/non-metadata state -> OUT_OF_SCOPE
non-empty residual with insufficient source evidence -> METADATA_RESIDUAL_UNKNOWN
uncertainty with no residual -> diagnostic metric only
```

## 14. M33 Failure-Domain and Output-State Model (2026-07-25)

M33 turns the M32d manual distinction between a real function-boundary
residual and a live bug into an analyzer state. It does not use the 539-row
review ledger as a suppression list.

```text
ResidualState.CONTAINED
ReportKind.CONTAINED_METADATA_RESIDUAL
FailureDomainProof(kind, site, owner, via_function, evidence)
```

A CONTAINED report retains `R_f`; unlike CLOSED or PROTECTED, it says the
mutation is still present at the current function boundary. The attached proof
says why ordinary live execution cannot carry it beyond that boundary.
Witness and evaluation schemas are now version 2.

Implemented source proofs:

```text
1. direct must-error-path terminal primitives
   - xfs_force_shutdown()
   - f2fs_stop_checkpoint()
2. dirty XFS transaction cancellation
   - xfs_trans_cancel(tp) plus a source-bound transaction effect proves that
     unrestorable peer state is quarantined by forced shutdown
3. closed-world static-callee containment
   - every visible call must check failure
   - the callee failure summary must be complete
   - instantiated error effects must actually reach the caller slice
   - every caller error path must be CLOSED, PROTECTED, or CONTAINED
4. write-only output aggregates
   - a pointer parameter is excluded only when at least two distinct direct
     fields are constructed with `=`, every use stays inside those assignments,
     the parameter itself is not read as a value, and it is never supplied as
     a call input
   - a field read is allowed only after that same field was constructed earlier
     in the function; dependence on any pre-call pointee state rejects the proof
   - one-field stores, nested-owner stores, self-referential stores, and any
     compound update remain in scope; local syntax alone cannot prove that an
     ordinary shared owner is an output object
```

Important soundness restrictions:

```text
Terminal failure-domain effects are not propagated through ordinary function
summaries. The current summary contract cannot bind a terminal action to one
exact error return. An attempted propagation incorrectly classified ordinary
xfs_trans_dqresv quota failures as fatal because another corruption return in
the callee calls xfs_force_shutdown(); that experiment was rejected.

Transaction ownership no longer uses effect.site.expression. Provenance text
such as "helper(tp) via helper: tip->field = ..." is not identity evidence.
Only effect root/key/value may bind an effect to the transaction. This keeps
xfs_swap_extents.tip->i_delayed_blks as a real residual and then classifies it
as FATAL_SHUTDOWN containment.

A pointer-to-stack alias experiment was also rejected after full evaluation:
it reduced local effects but changed summary completeness and caused an
unexplained btrfs Candidate/UNKNOWN increase without eliminating a reviewed
family.
```

M32d -> M33f full Linux v6.14 schema-2 results:

| Filesystem | Candidate | Contained | UNKNOWN | Review |
|---|---:|---:|---:|---:|
| btrfs | 231 -> 235 | 0 | 148 -> 152 | 91 -> 92 |
| ext4 | 80 -> 80 | 0 | 117 -> 117 | 166 -> 166 |
| XFS | 190 -> 184 | 9 | 163 -> 146 | 278 -> 188 |
| F2FS | 38 -> 38 | 0 | 55 -> 55 | 36 -> 36 |

The four new btrfs Candidates are explained, not an unexplained surge:

```text
btrfs_start_dirty_block_groups: btrfs_run_delayed_refs failure
btrfs_write_dirty_block_groups: update_block_group_item failure
btrfs_remove_chunk: two failure sites
```

They were previously suppressed only because the summary provenance expression
contained `trans`; after the identity correction, cache.commit_used and
BLOCK_GROUP_FLAG_CHUNK_ITEM_INSERTED remain visible. They need exact fatal-abort
or cleanup ownership proofs and must not be hidden by restoring the old textual
binding.

The nine XFS CONTAINED reports are in xfs_defer_finish,
xfs_bmap_recover_work (2), xfs_swap_extents, xfs_dquot_disk_alloc (3), and
xfs_dax_notify_dev_failure (2). The reviewed xfs_swap_extents residual remains
present and is now classified with the correct
`FailureDomainKind.FATAL_SHUTDOWN` proof. UNKNOWN fell by 17 rather than
receiving Candidate migrations.

Positive precision guards:

```text
tests/test_known_candidate_oracles.py fixes simplified source witnesses for:
  P3 btrfs_dev_replace_start
  #7 btrfs_recover_relocation
  P1 btrfs_reconfigure
  #16-#18 btrfs_init_new_device, including post_commit_list, num_devices,
          and latest_dev effects

The M33f full run also keeps btrfs_create_uuid_tree and ext4 make_indexed_dir
Candidate-visible.
```

Final verification and transition audit:

```text
python -m pytest -q -p no:cacheprovider
222 passed

All four runs: schema_version = 2
All four runs: zero_residual_finding_count = 0
All four M32d -> M33f comparisons: unmatched_baseline_witness_count = 0
All four M32d -> M33f comparisons: new_candidate_count = 0
```

The report-level Candidate increase in btrfs does not mean four new source
effects were extracted. Nine existing effect witnesses moved from PROTECTED
after removing provenance-text transaction binding. They occur in
`btrfs_start_dirty_block_groups`, `btrfs_write_dirty_block_groups`,
`btrfs_replace_file_extents`, and `btrfs_remove_chunk`; one related witness
moved to UNKNOWN. The four report-level increases are the net aggregation of
those witness migrations. Restoring the old binding would lower the count by
reintroducing an unsound identity proof.

Residual-bearing UNKNOWN and diagnostic-only UNKNOWN changed separately:

| Filesystem | Residual UNKNOWN | Diagnostic-only UNKNOWN | Missing-summary mentions | Structural mentions |
|---|---:|---:|---:|---:|
| btrfs | 148 -> 152 | 189 -> 183 | 154 -> 155 | 124 -> 128 |
| ext4 | 117 -> 117 | 70 -> 70 | 151 -> 151 | 81 -> 81 |
| XFS | 163 -> 146 | 191 -> 222 | 65 -> 50 | 184 -> 176 |
| F2FS | 55 -> 55 | 23 -> 23 | 79 -> 79 | 24 -> 24 |

The XFS diagnostic-only increase is not a finding increase. It reflects slices
whose residual effect moved to PROTECTED/CONTAINED while unrelated unresolved
path diagnostics remain recorded. The finding-level UNKNOWN count falls by 17.

Known-witness audit:

```text
Candidate-visible in the full M33f run:
  P3 btrfs_dev_replace_start
  #7 btrfs_recover_relocation
  P1 btrfs_reconfigure
  btrfs_create_uuid_tree
  #17/#18-related btrfs_init_new_device effects, including num_devices and
  latest_dev
  ext4 make_indexed_dir

Function-visible but not exact bug-witness complete:
  #16 btrfs_init_new_device is Candidate-visible, but the real kernel
  post_commit_list effect created below btrfs_create_chunk() is not propagated
  through the full call chain. The simplified oracle protects an already
  visible post_commit_list witness from false demotion; it does not establish
  end-to-end recall for #16.
```

This distinction is a hard evaluation rule: function-level alignment cannot be
reported as exact bug recall. Exact #16 recall requires the same exit-sensitive
interprocedural summary contract needed for safe btrfs/F2FS containment.

Artifacts:

```text
src/failure_domain.py
src/failure_domain_primitives.py
tests/test_failure_domain.py
tests/test_known_candidate_oracles.py
outputs/residual-evaluation-batch/linux-v6.14-fs-*-m33f-schema2
outputs/residual-evaluation-batch/linux-v6.14-fs-*-m33f-schema2/transition-from-m32d
```

The next TOC constraint is exact exit-sensitive interprocedural summaries. A
summary must map each failure return to its own opens, cancellations, terminal
action, and failed-owner destruction. Without that relation, btrfs abort and
F2FS checkpoint-stop proofs cannot be propagated safely. Do not add more fatal
primitive names or function-family suppressions before this contract exists.

## 15. M34a Exact Error-Exit Partition Contract (2026-07-25)

M34a implements the data contract required by the M33 TOC constraint without
changing the aggregate report projection.

```text
ErrorExitPartition:
  exit_site
  return_expression
  opens / cancels / protects / residuals
  terminal_actions
  failed_owner_destructions
  interprocedural path
  complete / unknown_causes
```

Each classified source error return gets its own partition. Only effects that
dominate that exact return enter its automatic open/cancel/protect set. Direct
callee error returns split a caller partition instead of merging their terminal
actions. A prior visible call's `success_must` effects are retained in a later
failure partition, which captures the abstract shape:

```text
helper A succeeds and mutates metadata
  -> helper B fails
  -> A's effect remains correlated with B's error return
```

The aggregate `error_opens/error_cancels/error_protects` projection remains the
existing all-error `MUST` projection. A terminal action is added to that
projection only when every complete error partition has a terminal action.
This makes all-terminal wrappers propagatable while preserving the M33 guard:
one fatal branch cannot contain an ordinary error return from the same callee.

Rejected experiment:

```text
Union every per-exit MAY/residual open into the aggregate caller slice.
```

On Btrfs this changed Candidate 235 -> 281, created 213 new Candidate effect
witnesses, and produced one UNMATCHED baseline witness. The cause was loss of
partition-local cleanup and feasibility correlation. The experiment was
reverted. Do not project a union of partition residuals into the current
single-state caller slice.

M33f -> M34a conservative full Linux v6.14 result:

| Filesystem | Candidate | Contained | Residual UNKNOWN | Review | Witnesses | New Candidate | UNMATCHED |
|---|---:|---:|---:|---:|---:|---:|---:|
| Btrfs | 235 | 0 | 152 | 92 | 2346 | 0 | 0 |
| ext4 | 80 | 0 | 117 | 166 | 1330 | 0 | 0 |
| XFS | 184 | 9 | 146 | 188 | 2065 | 0 | 0 |
| F2FS | 38 | 0 | 55 | 36 | 634 | 0 | 0 |

All four runs keep `zero_residual_finding_count = 0`. Unit tests: 225 passed.

The real Linux v6.14 #16 audit is still not exact. `create_chunk()` adds
`dev->post_commit_list` to the parameter-bound
`trans->transaction->dev_update_list`, but `dev` is a loop local derived from
`devices_info[i].dev`. The current summary drops that ADD because the member
identity is unbound before it reaches the new partition contract. Therefore
M34a must not be described as full `post_commit_list` recall.

The next TOC constraint is the earliest remaining blocker in that chain:
source-proven existential member identity for an exact parameter-bound
container. It must preserve a call-site-scoped opaque member through summaries
without pretending that it equals the failed new device. After that evidence
exists, the caller slicer can consume error alternatives independently rather
than unioning them. Keep P1, P3, #7, #16-#18 and the M33 XFS containment
witnesses visible throughout this work.

## 16. M35a Output Semantics and Manual Oracle (2026-07-25)

M35a fixes the measurement contract before adding more analysis power.

First-principles distinction:

```text
non-empty R_f reaches a function error exit
  != residual owner is still live
  != filesystem can continue normally
  != bug
```

The canonical report field is now `classification`. An EXPOSED residual with
direct source or explicit primitive evidence is classified as
`FUNCTION_BOUNDARY_RESIDUAL`. The legacy `UNCLOSED_METADATA_RESIDUAL` kind,
`confidence=candidate`, and `candidate_count` remain for compatibility.
Evaluation schema 3 adds:

```text
function_boundary_residual_count
live_metadata_residual_count
residual_classification_counts
candidate_count_legacy_alias_of
```

The M32d manual review is now an executable 539-record oracle:

```text
outputs/candidate_review_oracle.jsonl
src/candidate_review_oracle.py
scripts/audit_candidate_review_oracle.py
```

Each record is explicitly `oracle_granularity=REPORT` and contains a stable
failure/exit location plus sorted structured residual effect identities. The
manual verdict is not projected onto individual effects in mixed reports.
The audit reads full `evaluation.json` slices so missing reports/effects remain
`UNMATCHED` rather than being credited as fixes. It also distinguishes
pre-existing safety issues from new milestone regressions when given a prior
audit.

Oracle final-state targets:

| Expected state | Reports |
|---|---:|
| OUT_OF_SCOPE | 417 |
| CLOSED | 6 |
| CONTAINED_METADATA_RESIDUAL | 106 |
| LIVE_METADATA_RESIDUAL | 6 |
| METADATA_RESIDUAL_UNKNOWN | 4 |

M35a full Linux v6.14 result:

| Filesystem | Function-boundary residual | Contained | UNKNOWN | Review | Witnesses | New legacy Candidate | UNMATCHED |
|---|---:|---:|---:|---:|---:|---:|---:|
| Btrfs | 235 | 0 | 152 | 92 | 2346 | 0 | 0 |
| ext4 | 80 | 0 | 117 | 166 | 1330 | 0 | 0 |
| XFS | 184 | 9 | 146 | 188 | 2065 | 0 | 0 |
| F2FS | 38 | 0 | 55 | 36 | 634 | 0 | 0 |

All four runs have schema 3, `candidate_count ==
function_boundary_residual_count`, `live_metadata_residual_count = 0`, and
`zero_residual_finding_count = 0`. Unit tests: 229 passed.

The M34a -> M35a oracle gate reports:

```text
539 / 539 reviewed report locations matched
0 reviewed effect witnesses unmatched
6 / 6 manual live or likely residuals remain visible
0 new safety regressions
```

One pre-existing M32d -> M34a safety issue is now visible rather than silent:
`XFS-186` in `xfs_trans_alloc` moved from Candidate to UNKNOWN because
`xfs_trans_cancel` retains `unbound_callee_local_identity`. M35a did not create
that transition: M34a -> M35a is identity-preserving. Do not count UNKNOWN as
a fix, and do not suppress this record by function name.

The next TOC constraint is M35b owner liveness and whole-owner teardown. The
manual review has 312 `PRIVATE_OR_CLEANED_STATE` reports and 69
`FAILED_OBJECT_TEARDOWN` reports; this 381-report cluster is the largest
precision constraint. Implement source-proven owner destruction/publication
semantics before M35c failure-domain containment, M35d partition consumption,
M35e relational member identity, or M35f demand-driven helper/indirect-call
work. The real #16 exact-recall limitation remains unchanged.

## 17. M35b Owner Liveness and Whole-Owner Teardown (2026-07-25)

M35b adds a source-auditable proof for the only owner-liveness state that can
close an effect without M35c failure-domain reasoning:

```text
field residual exists
  != owner is still live
  != effect remains observable

source-proven OWNER_DESTROYED on every feasible error exit
  -> owner-embedded effect may be CLOSED
```

The implementation records `OwnerTeardown` witnesses in the residual slice and
serializes the owner, allocation site, teardown site, exact deallocator,
source-visible wrapper, closed effects, and evidence. Directly recognized
primitives are deliberately limited to:

```text
kfree(arg0)
kvfree(arg0)
vfree(arg0)
free_percpu(arg0)
kmem_cache_free(cache, arg1)
```

A teardown closes an effect only when all of the following are source-proven:

```text
the owner came from a fresh allocation
the deallocator argument is the exact same bare local identity
the local identity was not rebound after allocation
the owner was not published before teardown
the owner was not passed to a possibly escaping call before teardown
the teardown must execute on the selected error path
the effect is a direct/nested field of that owner
the effect has DIRECT_SOURCE evidence, or is an explicit bit primitive
```

Source-visible wrappers propagate the same proof only when the inner exact
primitive or another proven wrapper dominates every wrapper exit. Helper names
containing `free`, `destroy`, `release`, or `cleanup` provide no evidence.
Instantiated expressions such as `holder->child`, `&owner`, and `*slot` are not
collapsed to the leading variable, because doing so would enlarge owner
identity and could create a false CLOSED result.

Whole-owner teardown does not automatically close:

```text
list/tree/xarray/radix-tree membership
state published into an external owner
shared or persistent state
name-inferred helper effects
effects on a non-fresh parameter owner
effects whose owner escaped or was rebound
```

M35b full Linux v6.14 result:

| Filesystem | Boundary M35a -> M35b | Contained | UNKNOWN | Review | Teardown-proof slices | Fully CLOSED slices |
|---|---:|---:|---:|---:|---:|---:|
| Btrfs | 235 -> 233 | 0 | 152 | 92 | 4 | 2 |
| ext4 | 80 -> 80 | 0 | 117 | 166 | 0 | 0 |
| XFS | 184 -> 182 | 9 | 146 | 188 | 2 | 2 |
| F2FS | 38 -> 38 | 0 | 55 | 36 | 0 | 0 |

The six proof slices close 24 prior effect witnesses: 20 in Btrfs and 4 in XFS.
Two Btrfs slices remain EXPOSED because teardown closes only the fresh owner's
embedded fields while other residual effects remain. The four fully closed
reports are `BTRFS-071`, `BTRFS-072`, `XFS-069`, and `XFS-070` in the manual
oracle.

M35a -> M35b oracle and comparator gates:

```text
539 / 539 reviewed report locations matched
0 reviewed effect witnesses unmatched
4 manual false-positive reports moved to CLOSED
6 / 6 manual live or likely residuals remain visible
0 new safety regressions
0 new Candidate witnesses
0 lost known witnesses
all four runs: zero_residual_finding_count = 0
unit tests: 239 passed
```

The pre-existing `XFS-186` Candidate-to-UNKNOWN transition remains the only
safety issue and is unchanged by M35b. P1, P3, #7, #16-#18,
`btrfs_create_uuid_tree`, ext4 `make_indexed_dir`, and the M33 XFS containment
witness remain visible. The real #16 `post_commit_list` limitation is still not
exact recall.

M35b intentionally does not emit `LIVE_METADATA_RESIDUAL`. Proving that an
owner survives teardown is insufficient to prove normal filesystem
continuation; that requires M35c failure-domain semantics. The next TOC
constraint is therefore M35c transaction abort, fatal shutdown, mount-failure
teardown, and recovery-abort containment. Do not broaden the deallocator set or
infer destruction from helper names to reduce the remaining 418 pending manual
false positives.

## 18. M35c Effect-Scoped Failure-Domain Foundation (2026-07-25)

M35c first fixes a soundness flaw in the existing failure-domain model. A
terminal action previously proved only that some containment action existed;
it did not identify which residual effects that action covered:

```text
one terminal action exists
  -> whole residual slice marked CONTAINED
  -> transaction abort could hide transaction-external effects
```

`FailureDomainProof` now serializes `covered_effects`. A residual slice is
`CONTAINED` only when every current residual is covered by at least one proof.
A mixed slice remains `EXPOSED` or `UNKNOWN`, while each covered effect remains
visible as effect-level containment evidence. Report, oracle, Markdown, static
caller containment, and run comparison consumers all use this scope.

The new explicit primitive contract is deliberately narrow:

```text
btrfs_abort_transaction(arg0) -> TRANSACTION_ABORT

arg0 must normalize to one exact bare symbol
effect.root / effect.key / effect.value must contain that exact token
effect.site.expression is never identity evidence
the abort must execute on the must-error path
conditional abort of a matching effect remains UNKNOWN
transaction-external peer effects remain EXPOSED
```

The same coverage rule is applied when composing exact M34 error-exit
partitions. A transaction terminal action removes only transaction-bound
partition residuals; it no longer erases unrelated callee effects. Existing
accepted M33 contracts are preserved: direct `xfs_force_shutdown`, direct
`f2fs_stop_checkpoint`, and dirty `xfs_trans_cancel` still cover their current
residual set. Recovery/runtime scoping for those primitives remains a separate
soundness task.

Mixed-slice reporting also changed. Candidate versus Review is selected from
the uncontained residual subset, so a covered direct effect cannot promote an
uncovered name-inferred peer from Review to Candidate. The oracle and comparator
make the same effect-level distinction. Comparator schema 3 and oracle audit
schema 2 record exact containment evidence.

M35b -> M35c full Linux v6.14 result:

| Filesystem | Boundary | Contained | UNKNOWN | Review |
|---|---:|---:|---:|---:|
| Btrfs | 233 -> 233 | 0 -> 23 | 152 -> 161 | 92 -> 92 |
| ext4 | 80 -> 80 | 0 -> 0 | 117 -> 117 | 166 -> 166 |
| XFS | 182 -> 182 | 9 -> 9 | 146 -> 146 | 188 -> 188 |
| F2FS | 38 -> 38 | 0 -> 0 | 55 -> 55 | 36 -> 36 |

The 23 Btrfs contained reports and 9 additional Btrfs UNKNOWN reports were
previously suppressed as transaction-protected slices. M35c retains their
function-boundary residuals and distinguishes fully proven from conditional or
partial containment. At effect granularity, 232 prior Btrfs PROTECTED witnesses
move to `CONTAINED_METADATA_RESIDUAL`; the remaining 128 stay PROTECTED.

Final gates:

```text
249 unit tests passed
539 / 539 reviewed report locations matched
0 reviewed effect witnesses unmatched
6 / 6 manual live or likely residuals remain visible
4 manual false-positive reports remain correctly CLOSED
0 new safety regressions
0 new Candidate witnesses in every filesystem comparison
0 lost baseline witnesses in every filesystem comparison
all four runs: zero_residual_finding_count = 0
```

The pre-existing `XFS-186` Candidate-to-UNKNOWN transition remains the only
safety issue. All nine M33 XFS contained slices, P1, P3, #7, #16-#18,
`btrfs_create_uuid_tree`, and ext4 `make_indexed_dir` remain visible. The real
#16 exact-recall limitation is unchanged.

This foundation does not complete the original 106-report manual containment
target: the oracle currently recognizes 1 and retains 105 for later semantic
work. Direct transaction-token matching is sufficient evidence, but it is not
the same as proving that an inode, pending snapshot, log, block group, or quota
effect belongs to the transaction. Btrfs abort also sets the filesystem
read-only, but that fact cannot automatically contain recovery-visible state,
published device topology, or external ownership.

The next TOC constraint is therefore a source-derived relation between an
effect and its failure domain:

```text
transaction ownership / publication escape
fatal runtime-only scope versus recovery-visible state
exact M34 error-partition consumption in the caller (M35d)
```

Do not expand `btrfs_abort_transaction` to all peer residuals, infer ownership
from a helper name, or treat filesystem shutdown as proof that recovery-visible
effects are harmless. F2FS-021 remains the canonical cross-function checkpoint
witness for M35d.

## 19. M35d-M35f Owner Binding, UNKNOWN Proof Gaps, and Real Gates (2026-07-25)

M35d fixes the earliest remaining cross-function identity break. The canonical
real witness was `XFS-186` in `xfs_trans_alloc`:

```text
xfs_trans_cancel(tp)
  -> callee local mp = tp->t_mountp
  -> xfs_force_shutdown(mp, ...)
  -> old summary dropped mp as unbound
  -> caller lost the terminal action owner
  -> reviewed report moved from Candidate to UNKNOWN
```

The summary contract now serializes source-derived `OwnerIdentityBinding`
records with these relation kinds:

```text
PARAM
FIELD
RETURN
OUT_PARAM
FRESH
```

Each record retains the callee local only as audit provenance. The semantic
identity is a parameterized relation such as `arg0->t_mountp`, `__return__`,
`__output1__`, or a call-site-scoped fresh identity. Call-site instantiation
preserves the binding through lifecycle facts, effects, exact error-exit
partitions, and terminal actions.

The direct relation recognizer accepts only one source-visible assignment and
rejects rebound or ambiguous locals. It does not use local names. A critical
scope correction was made during real evaluation: direct owner relations are
owner-only evidence. They may bind terminal actions and owner facts, but do
not rewrite unrelated metadata effect identities. Applying them as a general
effect alias produced 61 new Candidate witnesses and 122 unmatched baseline
witnesses across the four filesystems; that experiment was rejected. Keep this
owner-only boundary.

With the corrected scope, `mp = tp->t_mountp` binds the shutdown action in
`xfs_trans_cancel`. `XFS-186` moves from `METADATA_RESIDUAL_UNKNOWN` to
effect-scoped `CONTAINED_METADATA_RESIDUAL`; the oracle now records it as a
resolved pre-existing safety issue, not as a Candidate-to-UNKNOWN migration.

M35e keeps the old compatibility taxonomy (`structural`, `missing_summary`,
`other`) and adds an actionable proof-gap projection:

```text
OWNER_BINDING_UNPROVEN
OUTPUT_BINDING_UNPROVEN
RETURN_BINDING_UNPROVEN
CALLSITE_ARGUMENT_BINDING_UNPROVEN
ERROR_PARTITION_SELECTION_UNPROVEN
CONDITIONAL_CONTAINMENT_NOT_MUST
TRANSACTION_OWNERSHIP_UNPROVEN
FATAL_SCOPE_UNPROVEN
SUMMARY_BODY_UNAVAILABLE
INDIRECT_TARGET_SET_UNPROVEN
OTHER_PROOF_GAP
```

UNKNOWN triage schema is now 2 and evaluation schema is 4. Evaluation summaries,
triage JSON, Markdown, and run comparisons expose proof-gap counts/resolution.
The current four-filesystem UNKNOWN cause mentions are:

| Proof gap | Mentions |
|---|---:|
| SUMMARY_BODY_UNAVAILABLE | 478 |
| OWNER_BINDING_UNPROVEN | 179 |
| ERROR_PARTITION_SELECTION_UNPROVEN | 125 |
| INDIRECT_TARGET_SET_UNPROVEN | 109 |
| CONDITIONAL_CONTAINMENT_NOT_MUST | 17 |
| OTHER_PROOF_GAP | 12 |
| TRANSACTION_OWNERSHIP_UNPROVEN | 7 |

M35f adds `scripts/check_m35_regression_gate.py`. It consumes only structured
JSON and exits nonzero for a missing filesystem, schema mismatch, a new
Candidate, an unmatched baseline witness, a new oracle safety regression, loss
of any of the six manual live residuals, a nonzero zero-residual finding count,
loss of high-value Btrfs/ext4 functions, or loss of any exact M33 XFS contained
slice. The XFS containment check compares stable function/failure/exit
identities against `linux-v6.14-fs-xfs-m33f-schema2`; it does not accept an
aggregate count as a substitute.

M35c -> M35d-M35f full Linux v6.14 result:

| Filesystem | Boundary | Contained | UNKNOWN | Review | New Candidate | UNMATCHED |
|---|---:|---:|---:|---:|---:|---:|
| Btrfs | 233 | 23 | 161 | 92 | 0 | 0 |
| ext4 | 80 | 0 | 117 | 166 | 0 | 0 |
| XFS | 182 | 10 | 145 | 188 | 0 | 0 |
| F2FS | 38 | 0 | 55 | 36 | 0 | 0 |

Final verification:

```text
254 unit tests passed
539 / 539 reviewed report locations matched
0 reviewed effect witnesses unmatched
6 / 6 manual live or likely residuals retained
0 new safety regressions
XFS-186 resolved
0 new Candidate witnesses in every filesystem comparison
0 lost baseline witnesses in every filesystem comparison
9 / 9 M33 XFS contained slices retained
all four runs: zero_residual_finding_count = 0
M35f regression gate: 34 / 34 checks passed
```

Artifacts:

```text
outputs/residual-evaluation-batch/linux-v6.14-fs-*-m35def-owner-reasons-gate
outputs/residual-evaluation-batch/m35def-comparisons/*
outputs/residual-evaluation-batch/m35def-oracle-audit.json
outputs/residual-evaluation-batch/m35def-regression-gate.json
```

The next TOC constraint is no longer the XFS owner-binding break. The largest
remaining actionable gap is `SUMMARY_BODY_UNAVAILABLE`, followed by the
remaining source-unproven owner relations and exact error-partition selection.
Address those demand-first using residual-bearing reports where the gap is the
only blocker. Do not broaden direct owner aliases into general effect aliases,
infer helper semantics from names, or relax the M35f gate to improve counts.

## 20. M36a Semantic Blocker Impact Profile (2026-07-25)

M36a is measurement-only. It adds `src/semantic_blocker_impact.py` and
`scripts/profile_semantic_blockers.py`, but does not participate in analysis,
classification, suppression, effect identity, or oracle verdicts. The emitted
artifact states this non-interference contract explicitly.

The profiler fixes the decision-unit mismatch left after M35e:

```text
UNKNOWN cause mention
  != UNKNOWN report
  != sole proof-gap report
  != source-resolvable report

oracle pending report
  != UNKNOWN report
  != permission to merge the two populations
```

The four M35d-M35f runs produce:

```text
UNKNOWN reports: 478
UNKNOWN cause mentions: 927
single-cause reports: 289
sole proof-gap reports: 389
multi-gap reports: 89
  two gaps: 82
  three gaps: 7

oracle records: 539
expected state reached: 6
retained for later milestone: 533
new safety regressions: 0
```

The unified decision surface keeps oracle and UNKNOWN populations distinct:

| Constraint | Reports | Sole blocker | Source available |
|---|---:|---:|---:|
| oracle: awaiting owner or scope semantics | 418 | 418 | n/a |
| oracle: awaiting failure-domain semantics | 105 | 105 | n/a |
| oracle: live residual remains visible | 6 | 6 | n/a |
| oracle: manual uncertainty remains visible | 4 | 4 | n/a |
| UNKNOWN: summary body unavailable | 272 | 200 | 173 |
| UNKNOWN: error-partition selection unproven | 98 | 70 | 0 |
| UNKNOWN: owner binding unproven | 129 | 69 | 0 |
| UNKNOWN: indirect target set unproven | 46 | 40 | 0 |
| UNKNOWN: other proof gap | 12 | 8 | 0 |
| UNKNOWN: conditional containment not must | 10 | 2 | 0 |
| UNKNOWN: transaction ownership unproven | 7 | 0 | 0 |

`SUMMARY_BODY_UNAVAILABLE = 478` is therefore 478 mentions across 272 reports,
not 478 reports and not 478 safely resolvable cases. Of its 200 sole-gap
reports, 129 have at least one exact source body available in the snapshot.
The exact body-state breakdown below counts distinct report/blocker pairs, so
repeated mentions in one report cannot inflate priority:

| Body state | Report/blocker pairs |
|---|---:|
| BODY_IN_ANALYSIS_ROOT | 150 |
| BODY_OUTSIDE_ANALYSIS_ROOT | 72 |
| HEADER_INLINE_NOT_LOADED | 60 |
| BODY_IN_CALLER_TRANSLATION_UNIT | 7 |
| NO_EXACT_DEFINITION | 91 |
| MACRO_OR_CONDITIONAL_BODY | 60 |
| MULTIPLE_DEFINITIONS | 23 |

The source index contains 13,611 definitions for 13,353 function names and
2,243 exact function-like macro names, with zero parse failures. It records
locations only; it never infers cleanup, shutdown, ownership, or helper
semantics from names.

The highest-impact source-visible sole summary blocker is
`xchk_trans_cancel`: 20 XFS reports, all with a body inside the analysis root.
Other large rows are `make_bad_inode` (19 sole-gap reports, body outside the
filesystem analysis root), `unlock_new_inode` (15), `xfs_inodegc_flush` (11),
and `evict_inodes` (10). Cross-filesystem reuse is not the dominant signal in
the current data: the only cross-filesystem summary helper row is
`init_special_inode`, with two sole-gap reports. M36b should therefore begin
with a bounded `xchk_trans_cancel` experiment and earn expansion through actual
state transitions, not helper frequency or naming.

Each report row retains its causes, distinct proof gaps, sole-cause/sole-gap
flags, exact failure/exit location, source-body state and definitions, oracle
linkage, expected destination, manual class, root-cause family, and known
witness involvement. Each blocker row adds distinct report count, raw mention
count, filesystem reuse, functions, oracle destinations, definition locations,
and known-witness count.

The 539 oracle records contain 12 duplicate-location groups and only 527 unique
location keys. The profiler therefore never stores a single oracle per
location. It retains all location candidates, collapses exact duplicate stable
reports, and uses complete residual-effect identity to distinguish genuinely
different reports at the same failure/exit pair. A zero-overlap or tied match
is emitted as `AMBIGUOUS_LOCATION`, not guessed. The current UNKNOWN population
has zero oracle-covered and zero oracle-ambiguous reports.

Verification:

```text
260 unit tests passed
M35f regression gate: 34 / 34 checks passed
0 new Candidate witnesses
0 unmatched baseline witnesses
6 / 6 manual live residuals retained
9 / 9 M33 XFS contained slices retained
all four runs: zero_residual_finding_count = 0
```

Generated artifacts:

```text
outputs/residual-evaluation-batch/m36a-semantic-blocker-impact/
  semantic_blocker_impact.json
  semantic_blocker_impact.md
outputs/residual-evaluation-batch/m36a-m35-regression-gate.json
```

The TOC conclusion has two levels. Across the reviewed Boundary population,
owner/scope semantics (418) remains the largest validated constraint, followed
by failure-domain semantics (105). Within UNKNOWN reduction, demand-driven
summary closure is the largest actionable sole-gap pool, but only 129 reports
currently satisfy both sole-gap and source-availability preconditions. Do not
add broad `fs/*.c` summary inputs, infer behavior from helper names, or treat a
body's existence as proof that the summary will change a final report state.

## 21. M36b-M36g Semantic Precision and Real Gate Closure (2026-07-25)

M36b-M36g continued the M36a decision order, but the real bottleneck changed
while testing. The original temptation was to keep expanding summary closure.
The actual TOC constraint became stricter:

```text
Can every count movement be explained by source-visible semantics and retained
oracle evidence, without weakening the M35f regression gate?
```

The answer required four semantic fixes and one comparison-layer fix.

First, several old Candidate/UNKNOWN witnesses were not caused by "cross
function" in the broad sense. Cross-function propagation merely exposed where
identity and helper semantics were incomplete. The concrete causal chains were:

```text
helper name contains quota/recover/trans
  -> NAME_INFERRED effect is created even for accessor/translator/getter helpers
  -> a low-evidence shadow residual enters the same failure slice as real effects
  -> Candidate or UNKNOWN count looks worse than the source semantics justify

helper constructs return_object->field from *out_param and returns object
  -> caller cannot bind returned field identity back to caller local
  -> transaction ownership proof cannot connect owner effect to transaction cancel
  -> contained XFS transaction failure looks like an exposed residual

transaction ownership primitive is stored as a protection effect
  -> containment proof only reads reaching effects
  -> xfs_trans_cancel cannot see the owner relation
  -> covered metadata mutation remains uncontained

zero-residual/protected slice intentionally emits no report
  -> old comparison sees missing effect witness
  -> gate reports UNMATCHED even though structure-level slice state is CLOSED,
     PROTECTED, or retained
```

This means the answer to "are Candidate and UNKNOWN caused by cross-function?"
is: sometimes the symptom appears at a cross-function boundary, but the root
causes are more specific. They are missing source identity, unresolved helper
bodies, exact error-partition uncertainty, owner binding gaps, indirect target
sets, conditional containment, and low-evidence name-inferred shadow effects.
Cross-function is the transport layer, not the explanation.

Implemented semantics:

```text
effect extractor:
  - treats readonly quota helpers ending in _quota_inode / _quota_on as readers
  - treats readonly transaction getters/reservation calculators such as _iget,
    _iget_handle, and _recover_resv as readers
  - uses tokenized transaction-helper matching so "translate" no longer matches
    "trans"
  - records xfs_trans_ijoin(tp, ip, ...) as transaction ownership evidence

function summary:
  - maps return_object->field = *out_param followed by return return_object
    into a caller-visible transfer identity
  - this binds xfs_bui_recover_work's returned work->bi_owner back to ip

residual slicer:
  - removes NAME_INFERRED local call shadows when the same call site has a
    source-visible summary application
  - lets transaction-cancel containment read ownership relations carried by
    protection effects, not only ordinary reaching effects

comparison/gate:
  - adds RETAINED_SLICE for a disappeared effect witness whose failure/exit
    slice is still visible; this is not counted as a fix
  - uses current CLOSED/PROTECTED/CONTAINED slice state for removed
    NAME_INFERRED witnesses only
  - matches source-projection identity when the same source mutation keeps
    function, failure/exit, key, plane, delta, file, and line, but owner root is
    refined by stronger identity binding
  - keeps DIRECT_SOURCE disappearing without source-projection evidence as
    UNMATCHED
  - lets the M33 XFS contained-slice check read structured CLOSED, PROTECTED,
    and CONTAINED states, because zero-residual slices should not continue to
    emit contained reports only to satisfy a historical report projection
```

The XFS spot-checks that drove the final gate were:

```text
xfs_bmap_recover_work:
  old root work->bi_owner is now bound to ip through return-field/out-param
  identity; xfs_trans_ijoin(tp, ip, 0) plus xfs_trans_cancel(tp) contains
  ip->i_delayed_blks.

xfs_dax_notify_dev_failure:
  xfs_dax_translate_range is no longer misread as a transaction helper merely
  because "translate" contains "trans".

xfs_dquot_disk_alloc:
  xfs_quota_inode and xfs_this_quota_on are accessors/validators, not quota
  mutation effects.

xlog_recover_iget / xlog_recover_resv:
  recovery inode getter/reservation helper names no longer create metadata ADD
  residuals by themselves.
```

M35d-M35f -> M36b-M36g full Linux v6.14 result:

| Filesystem | Boundary | Contained | UNKNOWN | Review | Reports | Witnesses | New Candidate | UNMATCHED |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Btrfs | 231 | 27 | 175 | 71 | 504 | 2226 | 0 | 0 |
| ext4 | 75 | 0 | 135 | 155 | 365 | 1255 | 0 | 0 |
| XFS | 187 | 6 | 121 | 148 | 462 | 1679 | 0 | 0 |
| F2FS | 37 | 1 | 53 | 35 | 126 | 612 | 0 | 0 |

Verification:

```text
297 unit tests passed
M35f regression gate: 34 / 34 checks passed
0 new Candidate witnesses in every filesystem comparison
0 unmatched baseline witnesses in every filesystem comparison
6 / 6 manual live residuals retained
9 / 9 M33 XFS contained slices retained
all four runs: zero_residual_finding_count = 0
```

Generated artifacts:

```text
outputs/residual-evaluation-batch/linux-v6.14-fs-*-m36b-m36g
outputs/residual-evaluation-batch/m36b-m36g-comparisons/*
outputs/residual-evaluation-batch/m36b-m36g-regression-gate.json
```

Next constraint:

```text
Do not expand effect extraction to chase count reductions.
```

The next useful work is demand-first semantic closure on residual-bearing
UNKNOWNs, but only when the blocker is sole, source-visible, and has a clear
oracle-preserving transition path. Remaining large classes are still
summary-body unavailability, exact error-partition selection, owner binding,
indirect target sets, and conditional containment. Treat `RETAINED_SLICE` as an
audit state: it preserves visibility across projection changes; it is not a
claim that the old effect was fixed.

## 22. Accepted Post-M36 Program; M37 Excluded (2026-07-26)

This section is the authoritative next-work plan. It combines the M36 evidence,
the 539-record manual oracle, and the useful parts of the external three-layer
proposal. Where they disagree, the existing project claim and accepted M36
measurements take precedence.

### 22.1 Corrected Decision Surface

The accepted M36b-M36g counts are:

```text
FUNCTION_BOUNDARY_RESIDUAL:        530
CONTAINED_METADATA_RESIDUAL:        34
METADATA_RESIDUAL_UNKNOWN:         484
FUNCTION_BOUNDARY_RESIDUAL_REVIEW: 409
```

The external proposal's `533 Boundary / 33 Contained` snapshot is not the
accepted M36 result. Do not repeat it in the paper or later comparisons.

The high-level diagnosis is nevertheless correct. Large-scale precision needs
three reusable, effect-scoped semantic layers:

```text
Owner / Scope:
  which owner carries the effect; whether the owner or a uniquely owned child
  is private, published, escaped, or destroyed

Failure Domain:
  whether the exact effect is isolated by transaction abort, fatal shutdown,
  checkpoint stop, failed-mount teardown, or caller containment

Exact Interprocedural Relation:
  which error partition, object identity, container member, return/out-param
  binding, or indirect target applies at the current call site
```

Owner/scope and failure-domain work primarily reduce Boundary reports. Exact
interprocedural relations primarily reduce residual-bearing UNKNOWNs. These
are interacting layers, not independent suppressors: every state transition
must identify the effect that the proof covers.

### 22.2 M37 Exclusion

Generated directories named `m37-*` exist under the ignored evaluation-output
tree. They were produced after the M36 commit and are not an accepted milestone:

```text
outputs/residual-evaluation-batch/linux-v6.14-fs-*-m37-semantic-audit
outputs/residual-evaluation-batch/m37-comparisons
outputs/residual-evaluation-batch/m37-preflight-comparisons
outputs/residual-evaluation-batch/m37c-semantic-blocker-impact
outputs/residual-evaluation-batch/m37-regression-gate.json
```

The experiment failed its regression gate in all four filesystems because the
comparison required more compatibility matches than the admitted budgets. A
compatibility match is an audited exception, not exact witness retention. The
experiment therefore cannot establish a safe reduction, cannot replace the
M36 baseline, and must not be used for paper counts, oracle claims, or the next
comparison baseline.

No tracked source rollback is required: `main` remains the M36 commit and the
tracked worktree has no M37 source delta. Keep the artifacts only as rejected
experimental evidence. The next accepted implementation label is M38.

### 22.3 Classification Contract

The per-effect decision order is:

```text
non-empty R_f at an error exit
  -> metadata scope proof
     -> source-proven cancellation, aggregate restore, or owner teardown
        -> effect-scoped failure-domain containment
           -> owner liveness and normal-continuation proof
```

The corresponding outcomes are:

```text
not filesystem metadata                         -> OUT_OF_SCOPE
cancelled/restored/destroyed with exact coverage -> CLOSED
isolated by an exact failure domain              -> CONTAINED_METADATA_RESIDUAL
published live owner plus normal continuation    -> LIVE_METADATA_RESIDUAL
effect computation has a proof gap               -> METADATA_RESIDUAL_UNKNOWN
residual proven only across this function         -> FUNCTION_BOUNDARY_RESIDUAL
```

`FUNCTION_BOUNDARY_RESIDUAL` remains a valid intermediate semantic result and
an audit-visible report. It must not be silently relabeled UNKNOWN merely
because owner liveness has not yet been implemented. Keep two uncertainties
separate:

```text
effect/cancellation/identity uncertainty -> METADATA_RESIDUAL_UNKNOWN
liveness or containment not yet proven   -> FUNCTION_BOUNDARY_RESIDUAL with
                                             structured semantic blockers
```

Only after owner-liveness and normal-continuation proofs exist may the primary
user view prioritize `LIVE_METADATA_RESIDUAL` and residual-bearing UNKNOWNs.
The legacy Candidate aliases remain compatibility fields during this program.

Do not add `INTENTIONAL_RESIDUAL` as a paper-level classification yet.
Source-proven write-only output or operation-descriptor state may become
`OUT_OF_SCOPE` with a specific reason. Progress and retry state that records
submitted or completed metadata work remains a Boundary residual with an
audit-only intentional-progress disposition until the oracle and paper claim
justify a separate classification.

### 22.4 M38: Owner and Scope Semantics

M38a is measurement and contract work only. Regenerate the decision surface
from the four accepted M36b-M36g runs; do not reuse M37 outputs. For each proof
gap report:

```text
report count
sole-gap count
source-visible sole-gap count
oracle destination
known-witness involvement
candidate semantic family
```

Rank implementation targets by report-level opportunity, not cause mentions:

```text
priority = sole-gap reports
           x exact source availability
           x expected final-state transition
           x reusable report-family coverage
```

M38a must also freeze a transition schema that records exact and compatibility
matches separately. Every compatibility match needs a typed reason. M38a sets
the accepted budgets from M36 and later milestones must not increase them
without effect-by-effect review.

M38b extends the existing `OwnerIdentityBinding`, `ExposureFact`, and
`OwnerTeardown` models with bounded parent-child ownership relations:

```text
OwnershipEdge:
  child
  parent
  relation = EMBEDDED | UNIQUE_POINTER | CONTAINER_OWNED | ARRAY_ELEMENT
  acquisition_site
  publication_sites
  escape_state

OwnerTeardownClosure:
  destroyed_owner
  transitively_destroyed_children
  externally_published_effects
  nonclosable_effects
```

Close an effect only when the child is uniquely owned, has not escaped, and the
source-visible teardown footprint covers it. Never close external accounting,
persistent/recovery-visible state, shared objects, block-device ownership,
global topology, or membership already published to a global list/tree/xarray.
Implement each ownership relation as a separate source shape; do not build a
general alias engine.

M38c adds an explicit unpublished mount-construction domain. An in-memory
effect may close through failed-mount teardown only when all of these are
proven:

```text
the owner belongs to the filesystem instance under construction
the instance has not reached an active superblock or global registry
every feasible error exit reaches complete teardown
the effect has not reached disk, a device, or another shared owner
no worker, RCU reference, return, output, or other escape survives teardown
```

Persistent, recovery-visible, external-device, and global-topology effects are
never closed merely because mount construction fails.

M38d adds provenance, not name rules, for:

```text
WRITE_ONLY_OUTPUT
OPERATION_DESCRIPTOR
PROGRESS_CURSOR
RETRY_STATE
```

`WRITE_ONLY_OUTPUT` requires caller-provided storage, write-only construction,
no dependence on the incoming pointee, no publication, and no later metadata
consumer. `OPERATION_DESCRIPTOR` must satisfy the existing universal visible
call-site discipline used by transient-argument provenance. Cursor/retry state
must prove that it records submitted or completed progress and that rollback
could repeat work; it is retained for audit unless separately proven outside
the filesystem-metadata completion contract.

Primary modules:

```text
src/metadata_residual.py
src/function_summary.py
src/transient_provenance.py
src/residual_slicer.py
src/candidate_review_oracle.py
src/semantic_blocker_impact.py
```

M38 acceptance requires reviewed family-level migrations, not a target count.
The expected useful transitions are Boundary -> OUT_OF_SCOPE/CLOSED and
Boundary -> UNKNOWN only where exact source analysis exposes an effect,
identity, or containment proof gap. Missing liveness proof alone leaves the
result as a Boundary residual with a structured semantic blocker.

### 22.5 M39: Transaction and Failure-Domain Semantics

M39a extends the existing `TransactionOwnershipRelation`; it does not infer
ownership from `tp`, `trans`, `journal`, or helper names. The proof must carry:

```text
transaction identity
owned effect/root
registration site and primitive
owner object
publication/escape state before abort
effect-specific abort footprint
```

Only an effect registered to the same transaction, not externally published,
and covered by a MUST abort footprint may become contained. Device topology,
active device pointers, global filesystem fields, transaction-external list
membership, and persistent/recovery-visible state remain Boundary or UNKNOWN.

M39b makes terminal actions plane- and visibility-scoped:

```text
FailureDomainScope:
  action
  allowed_planes
  allowed_visibility
  forbidden_categories
  required_owner_relation
```

`xfs_force_shutdown`, `f2fs_stop_checkpoint`, and
`btrfs_abort_transaction` must never contain a complete slice by name. Each
`FailureDomainProof.covered_effects` entry must be justified independently.
In particular, `RECOVERY_VISIBLE` effects cannot be contained by shutdown
alone, and transaction-external effects cannot be contained by abort alone.
A transaction-local lifecycle effect may use the RECOVERY plane while still
being covered by an effect-scoped shutdown or checkpoint proof; visibility,
not the plane label alone, controls this distinction.

M39c keeps failed-mount teardown, recovery abort, transaction abort, checkpoint
stop, and fatal shutdown as distinct domains. Cross-function caller
containment remains valid only when complete propagated error effects are
visible and every source-visible caller seals them.

Primary modules:

```text
src/failure_domain_primitives.py
src/failure_domain.py
src/metadata_residual.py
src/function_summary.py
src/residual_slicer.py
```

### 22.6 M40: Exact Interprocedural UNKNOWN Closure

M40 work is demand-first. Select only residual-bearing reports where the proof
gap is sole or where one shared relation can eliminate a reviewed multi-gap
family. Broad `fs/*.c` summary loading remains rejected.

M40a consumes the existing `ErrorExitPartition` at callers:

```text
CallerConstraint + CalleeReturnPartition -> SelectedErrorAlternative
```

Begin with bounded predicates already compatible with the CFG/SMT layer:

```text
ret == 0, ret != 0, ret < 0, ret > 0
ret == constant errno
switch constant cases
bounded IS_ERR/PTR_ERR forms
```

Each selected alternative independently carries opens, cancels, protects,
terminal actions, failed-owner destructions, and transaction ownership. If two
feasible alternatives differ semantically, keep UNKNOWN.

M40b adds demand-driven summary requests:

```text
DemandSummaryRequest:
  report_id
  helper and exact call site
  expected root
  required semantics
  transitive body budget
```

Allowed required semantics include `MUST_CANCEL`, `MUST_PROTECT`,
`OWNER_BINDING`, `RETURN_BINDING`, `TERMINAL_ACTION`, `READ_ONLY`,
`CONTAINER_DRAIN`, and `OWNER_TEARDOWN`. Load the exact body and only the
minimal transitive dependencies needed for that proof. Body availability is a
precondition, not evidence of a final-state transition.

M40c extends, rather than duplicates, the existing
`ExistentialMemberIdentity`. The first recall target is confirmed bug #16:

```text
devices_info[i].dev
  -> loop-local dev
  -> dev->post_commit_list
  -> trans->transaction->dev_update_list
```

The proof denotes some source-visible member from the container; it must not
claim that this object equals the failed new device without caller provenance.
The same bounded identity form may later support list/tree/radix members.

M40d adds source-derived indirect target sets, initially for repeated XFS
families:

```text
IndirectTargetSet:
  call_site
  receiver_type
  ops_table
  possible_targets
  completeness
```

Accept targets only from exact static ops initializers, dominating assignments,
closed-world types, and compile-time configuration. Resolve only when the set
is complete and all targets provide the same MUST cancellation or containment
semantics. Never choose one likely callback.

Lexical reader suppression remains audit-only throughout M40:

```text
may prevent a NAME_INFERRED effect from being created
may not delete DIRECT_SOURCE or EXPLICIT_PRIMITIVE evidence
may not establish CLOSED, PROTECTED, or CONTAINED
```

Record the helper, lexical rule, suppressed hypothesis, and source-body
availability. High-impact helpers should eventually receive source-derived
`READ_ONLY` summaries; an unavailable body remains Review or UNKNOWN as
appropriate.

### 22.7 M41: Liveness and Report Completion

M41 may emit `LIVE_METADATA_RESIDUAL` only when all three are source-proven:

```text
the exact owner survives the error exit
the owner/effect was published outside a closing or containing domain
the filesystem or relevant owner can continue ordinary work
```

M41 now computes these proofs and separates the primary triage view from the
audit view without removing serialized M34 compatibility aliases. No full-run
final7 effect satisfied all three conditions, so `LIVE_METADATA_RESIDUAL = 0`;
the M36 `FUNCTION_BOUNDARY_RESIDUAL` claim remains the sound classification for
those effects.

### 22.8 Transition Evidence and Gates

Every accepted milestone must report at least:

```text
Boundary -> OUT_OF_SCOPE / CLOSED / CONTAINED / UNKNOWN / LIVE
UNKNOWN  -> OUT_OF_SCOPE / CLOSED / CONTAINED / Boundary / LIVE
Review   -> UNKNOWN / Boundary / OUT_OF_SCOPE
```

Each transition records:

```text
old and new complete effect identity
source proof
owner/scope proof
failure-domain proof
partition or target-set proof
oracle expectation and review status
exact, source-projection, compatibility, or retained-slice match kind
```

Also report family-level yield for owner teardown, mount teardown,
output/operation/progress provenance, transaction ownership, failure-domain
scope, partition selection, summary closure, existential identity, and indirect
targets. A total-count reduction without these attributions is not evidence of
precision.

Keep the existing hard gates:

```text
the complete unit-test suite passes (currently 313 tests)
all four Linux v6.14 filesystem runs and comparisons are present
6 / 6 manually established high-value residuals remain visible
P1, P3, #7, and #16-#18 remain visible at the required evidence level
btrfs_create_uuid_tree and ext4 make_indexed_dir remain visible
9 / 9 exact M33 XFS contained slices remain retained
zero_residual_finding_count = 0
UNMATCHED exact known witnesses = 0
no new oracle safety regression
RETAINED_SLICE is never counted as a fix
```

Add these gates before accepting the corresponding semantic layer:

```text
DIRECT_SOURCE cannot disappear through a lexical rule
RECOVERY_VISIBLE cannot become contained through shutdown alone
transaction-external effects cannot become contained through abort alone
parent teardown cannot close an escaped or published child effect
compatibility-match exceptions are typed, reviewed, and budgeted
```

The existing `0 new Candidate witness` gate remains in force until the oracle
workflow can review new Boundary witnesses in the same run. After that schema
change, replace it with:

```text
0 unreviewed new Boundary witnesses
```

An UNKNOWN -> Boundary transition is allowed only with source proof and an
oracle decision; forbidding every such transition would optimize the count at
the expense of correctness.

The program is successful when large reviewed families move to
OUT_OF_SCOPE/CLOSED/CONTAINED, the few live residuals stay visible, and the
remaining UNKNOWNs correspond to genuine missing source, incomplete target
sets, unresolved object identity, or asynchronous semantics. UNKNOWN equal to
zero and Candidate equal to zero are not objectives.

## 23. M38-M41 Implementation and Final7 Acceptance (2026-07-26)

M38-M41 are implemented in the current worktree and verified against the
accepted M36b-M36g baseline at commit `ad06c19`. No M37 run, comparison, source
delta, or count was used. The rejected M37 artifacts remain untouched only as
historical evidence.

### 23.1 Implemented Semantic Surface

M38 adds effect-scoped owner and scope semantics:

```text
EffectSemanticProvenance and EffectVisibility
OwnershipEdge, OwnerScopeProof, and transitive owner teardown
path-sensitive publication, escape, rebind, and teardown ordering
PRIVATE_OWNER, WRITE_ONLY_OUTPUT, OPERATION_DESCRIPTOR,
PROGRESS_CURSOR, and RETRY_STATE provenance
```

Fresh local descriptors copied from caller state are treated as operation
descriptors rather than as writes to the caller's transaction. Unpublished
fresh-owner effects remain serialized as auditable out-of-scope effects.
Potentially escaped owners retain an exposed result and an effect-level review
reason instead of closing the whole slice.

M39 adds effect-scoped failure-domain and transaction semantics:

```text
TransactionOwnershipRelation
FailureDomainScope and FailureDomainProof.covered_effects
separate transaction abort, recovery abort, fatal shutdown,
checkpoint stop, failed-owner teardown, and caller containment domains
```

Containment is checked per effect using plane, visibility, ownership, and
forbidden categories. A bare transaction owner is `TRANSACTION_LOCAL`, even
when its lifecycle helper uses the RECOVERY plane. This preserves the M33
`xfs_defer_trans_roll(tp)` shutdown-contained slice without allowing a true
`RECOVERY_VISIBLE` effect to be closed by shutdown alone.

M40 adds exact interprocedural audit structures and bounded resolution:

```text
DemandSummaryRequest
error-partition and exact return-code diagnostics
IndirectTargetSet
ExistentialMemberIdentity integration
LexicalSuppressionEvidence
```

Exact return-code or partition identity gaps are attached to demand-summary
and semantic diagnostics; they do not downgrade an otherwise direct residual
effect to UNKNOWN. Lexical suppression can prevent a name-inferred hypothesis,
but cannot delete direct-source evidence or establish closure/containment.

M41 adds `OwnerLivenessProof`, `LIVE_METADATA_RESIDUAL`, effect-level review
selection, primary/audit report views, schema-v4 semantic-family metrics, and
schema-v4 exact/compatibility/retained-slice transition reporting. A historical
lexical witness whose exact effect projection disappears but whose failure/exit
slice remains visible is `RETAINED_SLICE`, never a fix or an unmatched witness.

Primary implementation files:

```text
src/owner_scope.py
src/owner_liveness.py
src/metadata_residual.py
src/effect_extractor.py
src/function_summary.py
src/failure_domain_primitives.py
src/residual_slicer.py
src/residual_analyzer.py
src/residual_report.py
src/evaluation_harness.py
src/candidate_review_oracle.py
scripts/compare_residual_runs.py
scripts/check_m35_regression_gate.py
```

### 23.2 Final7 Linux v6.14 Result

| Filesystem | Boundary | LIVE | Contained | UNKNOWN | Review | Reports | Witnesses |
|---|---:|---:|---:|---:|---:|---:|---:|
| Btrfs | 250 | 0 | 16 | 156 | 83 | 505 | 2349 |
| ext4 | 80 | 0 | 0 | 120 | 165 | 365 | 1255 |
| XFS | 175 | 0 | 6 | 117 | 168 | 466 | 1718 |
| F2FS | 37 | 0 | 1 | 53 | 35 | 126 | 754 |
| Total | 542 | 0 | 23 | 446 | 451 | 1462 | 6076 |

Accepted M36b-M36g totals and final7 deltas:

| Classification | M36 | final7 | Delta |
|---|---:|---:|---:|
| Boundary | 530 | 542 | +12 |
| LIVE | 0 | 0 | 0 |
| Contained | 34 | 23 | -11 |
| UNKNOWN | 484 | 446 | -38 |
| Review | 409 | 451 | +42 |

The result does **not** establish simultaneous aggregate Candidate/Boundary
and UNKNOWN reduction. UNKNOWN fell by 38, but Boundary rose by 12 because the
new semantic layers expose and retain more effect-level evidence. Do not state
that both populations decreased. The accepted result is stronger auditability
and safe UNKNOWN reduction with exact baseline-witness retention, not a
headline Candidate-count reduction.

### 23.3 Transition, Oracle, and Gate Evidence

```text
313 / 313 unit tests passed
5772 / 5772 M36 baseline witnesses retained as EXACT_WITNESS
0 compatibility matches
0 new Candidate witnesses
0 unmatched baseline witnesses
539 / 539 manual oracle entries matched
0 unmatched oracle effects
6 / 6 manual live residuals retained; 0 lost
0 new oracle safety regressions
9 / 9 exact M33 XFS contained slices retained
0 zero-residual findings in all four filesystems
38 / 38 regression-gate checks passed
```

The oracle still records 534 entries as `RETAINED_FOR_LATER_MILESTONE`. Only
five entries reached their expected final state. Therefore final7 is an
engineering acceptance of the M38-M41 semantic contracts and non-regression
gates, not a claim that the manual semantic oracle has been fully discharged.

### 23.4 Generated Artifacts

```text
outputs/residual-evaluation-batch/linux-v6.14-fs-btrfs-m38-m41-final7
outputs/residual-evaluation-batch/linux-v6.14-fs-ext4-m38-m41-final7
outputs/residual-evaluation-batch/linux-v6.14-fs-xfs-m38-m41-final7
outputs/residual-evaluation-batch/linux-v6.14-fs-f2fs-m38-m41-final7
outputs/residual-evaluation-batch/m38-m41-final7-comparisons/*
outputs/residual-evaluation-batch/m38-m41-final7-oracle-audit.json
outputs/residual-evaluation-batch/m38-m41-final7-regression-gate.json
```

### 23.5 Next Constraint

Do not add broad helper-name rules or optimize the aggregate count. The next
accepted work should use the final7 family metrics and the 534 pending oracle
entries to select source-visible, effect-level families that can reach an
oracle-approved final state. Prioritize exact owner teardown/scope families for
Boundary reduction and exact summary/target/identity families for UNKNOWN
reduction, while preserving all final7 exact-witness, manual-live, XFS
containment, compatibility-zero, and safety-regression gates.

## 24. M38-M41 Final8 Contained Audit and Acceptance (2026-07-27)

Final8 completes the manual audit of the latest Contained population. It uses
M36b-M36g and final7 as the only comparison baselines; M37 remains excluded.
The implementation does not add a helper blacklist, suppress reports, or
weaken the oracle. Cleanup, transaction, owner, and failure-domain decisions
are effect-scoped and require source-visible identity and ordering evidence.

### 24.1 Linux v6.14 Result

| Filesystem | Boundary | LIVE | Contained | UNKNOWN | Review | Reports | Witnesses |
|---|---:|---:|---:|---:|---:|---:|---:|
| Btrfs | 266 | 0 | 8 | 125 | 71 | 470 | 2342 |
| ext4 | 89 | 0 | 0 | 104 | 167 | 360 | 1255 |
| XFS | 184 | 0 | 4 | 102 | 175 | 465 | 1712 |
| F2FS | 39 | 0 | 1 | 49 | 37 | 126 | 754 |
| Total | 578 | 0 | 13 | 380 | 450 | 1421 | 6063 |

| Classification | M36 | final7 | final8 | final8 vs M36 | final8 vs final7 |
|---|---:|---:|---:|---:|---:|
| Boundary | 530 | 542 | 578 | +48 | +36 |
| Contained | 34 | 23 | 13 | -21 | -10 |
| UNKNOWN | 484 | 446 | 380 | -104 | -66 |
| Review | 409 | 451 | 450 | +41 | -1 |
| Reports | 1457 | 1462 | 1421 | -36 | -41 |

Final8 therefore compresses Contained and UNKNOWN without claiming that every
newly proven Boundary residual is a bug. Boundary increases because more
effects now have sufficient identity/order evidence to leave UNKNOWN.

### 24.2 Audited Contained Decisions

The remaining 13 Contained reports are source-confirmed fail-stop cases:

```text
Btrfs: balance_level (5), push_nodes_for_insert (2), walk_up_proc (1)
XFS:   xfs_defer_finish_noroll, xfs_defer_finish, xfs_swap_extents (4 total)
F2FS:  written_valid_blocks (1)
```

The reviewed false Contained families migrated as follows:

```text
CLOSED:
  do_chunk_alloc
  __btrfs_run_delayed_items
  xfs_trans_alloc
  btrfs_add_link
  __cow_file_range_inline

OUT_OF_SCOPE:
  f2fs_allocate_data_block::fragment_remained_chunk

REVIEW:
  xfs_bmap_recover_work:532
  xfs_bmap_recover_work:536
```

`do_chunk_alloc` closes because the outer
`btrfs_trans_release_chunk_metadata(trans)` wrapper now matches the summarized
prior reservation for the same owner and resource token. The two XFS recovery
paths remain Review with `conditional_shutdown_review:ip` and
`owner_liveness_unproven`: shutdown is conditional and there is no preceding
open/write dirty or log evidence. They are not silently treated as Contained.

### 24.3 Verification and Artifacts

```text
325 / 325 unit tests passed
0 new Candidate witnesses in all M36 and final7 comparisons
0 unmatched baseline witnesses in all M36 and final7 comparisons
539 / 539 manual oracle entries matched
0 Candidate -> UNKNOWN transitions
6 / 6 manual live residuals retained; 0 lost
0 unmatched oracle entries or effects
0 oracle safety regressions
40 / 40 regression-gate checks passed
```

Final run artifacts:

```text
outputs/residual-evaluation-batch/linux-v6.14-fs-btrfs-m38-m41-final8-final5
outputs/residual-evaluation-batch/linux-v6.14-fs-ext4-m38-m41-final8-final2
outputs/residual-evaluation-batch/linux-v6.14-fs-xfs-m38-m41-final8-final5
outputs/residual-evaluation-batch/linux-v6.14-fs-f2fs-m38-m41-final8-final2
outputs/residual-evaluation-batch/m38-m41-final8-final5-vs-m36-comparisons/*
outputs/residual-evaluation-batch/m38-m41-final8-final5-oracle-audit.json
outputs/residual-evaluation-batch/m38-m41-final8-final5-regression-gate.json
```
