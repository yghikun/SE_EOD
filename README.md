# Failure-Path Filesystem Metadata Residual Analysis

This project is a lightweight static-analysis scaffold for Linux filesystem
error paths. The active research method is:

```text
Failure-Path Filesystem Metadata Residual Analysis
```

MetaWindow is only the intuition. The method is stricter: for each failure
point, compute which filesystem metadata effects were created, which were
cancelled, which were explicitly transferred to transaction or recovery
machinery, and which residual metadata effects still reach an error exit.

## Core Claim

For a failure point `f`, define:

```text
E_f = filesystem metadata effects that can reach f
C_f = cancellation or compensation effects on the error path
T_f = effects explicitly protected by transaction, journal, orphan, recovery,
      or deferred machinery

R_f = Normalize(E_f (+) C_f) - T_f
```

If `R_f` is non-empty at an error exit, and the residual is structural,
accounting, or recovery-visible filesystem metadata, the analyzer reports a
candidate:

```text
UNCLOSED_METADATA_RESIDUAL
```

The innovation target is not a four-state typestate model. The states are only
an implementation lattice. The method contribution is failure-path residual
computation over filesystem metadata state:

```text
metadata effect extraction
identity-aware cancellation
failure-anchored bidirectional slicing
explicit protection and transfer recognition
error-exit residual verification
```

## What This Is Not

The project intentionally does not attempt:

```text
complete filesystem protocol EFSMs
full crash-consistency verification
fixed API-pair postcondition checking
ordinary memory, buffer, folio, path, lock, or generic resource cleanup analysis
generic typestate verification
large MOCC-SE rule registries
```

## Active Architecture

```text
Linux FS source
  -> frontend-neutral FunctionIR
  -> function-local CFG
  -> filesystem metadata scope gate
  -> failure-point discovery
  -> backward slice for E_f
  -> forward error-path slice for C_f and T_f
  -> residual normalization
  -> error-exit verification
  -> witness report
```

## Retained Project Shape

```text
src/frontend/                 frontend-neutral C IR and tree-sitter adapter
src/cfg.py                    function-local CFG utilities
src/parser.py                 C parser fallback helpers
src/function_extractor.py     function extraction helpers for source files
src/metadata_scope.py         versioned filesystem metadata scope contract
src/metadata_residual.py      filesystem metadata residual data model
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
#18  btrfs_init_new_device: fs_devices topology remains residual
#12  xfs_qm_quotacheck_dqadjust: dquot quota metadata ownership/reference residual
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
