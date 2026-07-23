# Failure-Local Metadata Residual Analysis

This project is a lightweight static-analysis scaffold for Linux file-system
error paths.  The active research method is:

```text
Failure-Local Metadata Residual Analysis
```

Chinese name:

```text
面向失败点的元数据残余分析
```

MetaWindow remains the intuition: metadata mutations open a risk window before
later software failures.  The paper method is stronger and more precise: for
each failure point, compute which metadata effects were created, which were
cancelled, which were explicitly transferred to transaction/recovery machinery,
and which residual effects still reach an error exit.

## Core Claim

For a failure point `f`, define:

```text
E_f = metadata effects that can reach f
C_f = cancellation or compensation effects on the error path
T_f = effects explicitly protected by transaction, journal, orphan, recovery,
      or deferred mechanisms

R_f = Normalize(E_f (+) C_f) - T_f
```

If `R_f` is non-empty at an error exit, and the residual is structural,
accounting, or recovery-visible file-system metadata, the analyzer reports a
candidate:

```text
UNCLOSED_METADATA_RESIDUAL
```

The innovation target is not a four-state typestate model.  The four states are
only an implementation lattice.  The method contribution is the failure-local
residual computation:

```text
metadata effect extraction
identity-aware cancellation
failure-anchored bidirectional slicing
explicit protection/transfer recognition
error-exit residual verification
```

## What This Is Not

The project intentionally does not attempt:

```text
complete file-system protocol EFSMs
full crash-consistency verification
fixed API-pair postcondition checking
ordinary memory, buffer, folio, path, or lock cleanup analysis
generic typestate verification
large MOCC-SE rule registries
```

MDR-style differential restoration is retained only as supporting evidence.  It
may explain that another nearby path cancels a similar residual and can provide
a patch hint, but the primary detector does not depend on sibling paths.

## Active Architecture

```text
Linux FS source
  -> frontend-neutral FunctionIR
  -> function-local CFG
  -> metadata scope gate
  -> failure-point discovery
  -> backward slice for E_f
  -> forward error-path slice for C_f and T_f
  -> residual normalization
  -> error-exit verification
  -> optional MDR evidence
```

## Retained Project Shape

```text
src/frontend/                 frontend-neutral C IR and tree-sitter adapter
src/cfg.py                    function-local CFG utilities
src/parser.py                 C parser fallback helpers
src/function_extractor.py     function extraction helpers
src/metadata_scope.py         versioned metadata scope contract
src/metadata_residual.py      residual-analysis data model
configs/metadata_scope/       metadata boundary and confirmed-bug labels
outputs/confirmed_bugs.md     curated evidence ledger
docs/                         current architecture and paper notes
linux-sources/                local Linux source inputs
```

## Evidence Boundary

Primary residual-analysis examples:

```text
#7   btrfs_recover_relocation: relocation-root recovery state remains residual
#16  btrfs_init_new_device: transaction update-list membership remains residual
#17  btrfs_init_new_device: active device pointers remain residual
#18  btrfs_init_new_device: fs_devices sprout topology remains residual
#12  xfs_qm_quotacheck_dqadjust: dquot metadata ownership/reference residual
```

Outcome residual extensions:

```text
#1, #2, #5, #8, #13  metadata failure residual hidden by success outcome
#4                   stale error after successful metadata retry
#15                  positive success skips chunk metadata reservation
```

Out of scope:

```text
#3, #6, #9, #10, #11, #14
```

These are useful historical resource-cleanup findings, but they do not define
the main method.

## Check

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```
