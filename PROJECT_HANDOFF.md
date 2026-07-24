# Failure-Path Filesystem Metadata Residual Analysis Handoff

Updated: 2026-07-24

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

Report `UNCLOSED_METADATA_RESIDUAL` only when:

```text
R_f is non-empty
and R_f is STRUCTURAL, ACCOUNTING, or RECOVERY filesystem metadata
and R_f reaches an error exit
and the result is not UNKNOWN
```

If object identity, helper semantics, async handoff, return classification, or
transaction ownership cannot be proven from source, keep the report as
`METADATA_RESIDUAL_UNKNOWN`. Do not guess safe and do not guess bug.

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
src/residual_slicer.py
src/residual_analyzer.py
src/residual_report.py
src/metadata_residual.py
src/metadata_scope.py
src/evaluation_harness.py
src/candidate_triage.py
src/unknown_triage.py
```

Active scripts:

```text
scripts/evaluate_residuals.py
scripts/evaluate_residuals_batch.py
scripts/summarize_candidates.py
scripts/summarize_unknowns.py
scripts/compare_residual_runs.py
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
python -m pytest -q -p no:cacheprovider
135 passed
```

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
  -> function-local CFG
  -> filesystem metadata scope gate
  -> failure-point discovery
  -> metadata effect extraction
  -> function summary generation/application
  -> backward slice for E_f
  -> forward error-path slice for C_f and T_f
  -> identity-aware cancellation
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
OUT_OF_SCOPE
```

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

## 9. Last Measured Btrfs State

The last documented mainline measurement was M26. Its output directory has been
cleaned as a generated artifact, so regenerate a fresh baseline before using
these numbers as a comparison point.

M26 documented:

```text
mainline, fs/btrfs/tests/* excluded:
  273 candidates
  393 UNKNOWN
  666 reports

unknown_taxonomy_counts:
  missing_summary: 214
  structural: 459

missing_summary categories:
  unresolved_metadata_helper_on_error_path: 193
  return_bound_unresolved_helper: 21

structural categories:
  callee_failure_effect_order_unknown: 19
  function_pointer_parameter_call: 2
  indirect_call: 27
  unbound_callee_local_identity: 285
  unclassified_return_exit: 126
```

Known mapped behavior should remain visible after every milestone:

```text
btrfs_init_new_device:
  candidate residuals remain visible

btrfs_recover_relocation:
  recovery residual evidence remains traceable through confirmed_bugs.md and
  outputs/linux-v6.8/btrfs/recover_relocation_qemu_report.md

btrfs_dev_replace_start:
  P3 should remain at least candidate/UNKNOWN-visible, not silently removed
```

P2-like ordinary resource lifetime bugs must not be counted as core
filesystem-metadata residual recall unless independently tied to metadata
completion semantics.

## 10. Evaluation Commands

Regenerate a clean btrfs mainline baseline:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python scripts/evaluate_residuals_batch.py `
  linux-sources/linux-v6.14-fs/fs/btrfs `
  --source-root linux-sources/linux-v6.14-fs `
  --confirmed-bug-mapping outputs/confirmed_bugs.md `
  --exclude-glob "fs/btrfs/tests/*" `
  --output-dir outputs/residual-evaluation-batch/linux-v6.14-fs-btrfs-main-m28-baseline
```

Summarize UNKNOWN:

```powershell
python scripts/summarize_unknowns.py `
  outputs/residual-evaluation-batch/linux-v6.14-fs-btrfs-main-m28-baseline
```

Summarize candidates:

```powershell
python scripts/summarize_candidates.py `
  outputs/residual-evaluation-batch/linux-v6.14-fs-btrfs-main-m28-baseline
```

Compare two runs:

```powershell
python scripts/compare_residual_runs.py `
  outputs/residual-evaluation-batch/<baseline> `
  outputs/residual-evaluation-batch/<current> `
  --output outputs/residual-evaluation-batch/<current>/unknown_resolution_matrix.json
```

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
```

Historical detailed run outputs under `outputs/residual-evaluation*` have been
removed from the working tree. The handoff now records milestone intent rather
than treating those directories as persistent project files.

## 12. Next Work

Recommended next milestone:

```text
M28: clean baseline plus missing-summary reduction
```

M28a: regenerate clean baseline.

```text
Re-run btrfs mainline evaluation after the output cleanup.
Record candidate_count, unknown_count, unknown_taxonomy_counts, and mapped
P1/P2/P3 behavior.
```

M28b: review candidate delta.

```text
Diff current candidates against the last measured M26 behavior.
Manually inspect newly promoted candidates before treating UNKNOWN reduction as
precision improvement.
```

M28c: demand-driven helper summaries.

```text
Target unresolved_metadata_helper_on_error_path first.
Analyze only helpers on the active failure slice.
Export MUST_CANCEL or MUST_PROTECT only when source proves the exact residual
footprint.
Keep unresolved nested metadata helpers as UNKNOWN.
```

M28d: return-bound helper summaries.

```text
Target return_bound_unresolved_helper.
Handle pointer returns only.
Bind returned fresh identities to caller lvalues before applying helper
summaries.
Do not treat scalar return values as metadata objects.
```

Likely M29:

```text
Improve return classifier for unclassified_return_exit.
Then revisit structural UNKNOWN, especially unbound_callee_local_identity.
Do not broaden indirect-call recovery beyond bounded source-visible targets
until candidate deltas are reviewed.
```

## 13. Gate Checklist

Every milestone must check:

```text
unit tests pass
UNKNOWN count changes by taxonomy, not only total
candidate count does not rise without review
known mapped findings remain visible
P3 remains candidate/UNKNOWN-visible
P2-like ordinary resource lifetime findings stay out of the core claim
new CLOSED/PROTECTED resolutions have source evidence
generated outputs are not mistaken for active documentation
```

The correct end state is not UNKNOWN equals zero. The correct end state is:

```text
source-provable residuals -> UNCLOSED_METADATA_RESIDUAL
source-provable cancellation/protection -> CLOSED or PROTECTED
source-provable private/non-metadata state -> OUT_OF_SCOPE
insufficient source evidence -> METADATA_RESIDUAL_UNKNOWN
```
