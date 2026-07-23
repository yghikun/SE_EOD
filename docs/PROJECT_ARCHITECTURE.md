# Project Architecture

The repository now keeps only the components needed for the MetaWindow
prototype.

## Retained Modules

```text
src/frontend/
  Tree-sitter-backed frontend-neutral C IR.

src/cfg.py
  Function-local CFG construction and control-flow utilities.

src/parser.py
  Parser fallback helpers.

src/function_extractor.py
  Function slicing/extraction helpers for source files.

src/metadata_scope.py
  Versioned metadata scope contract and confirmed-bug scope labels.

src/metawindow.py
  Lightweight MetaWindow data model.
```

## Retained Inputs

```text
configs/metadata_scope/metadata_scope_v1.json
  Metadata boundary and curated confirmed-bug scope decisions.

outputs/confirmed_bugs.md
  Evidence ledger for motivating and evaluating MetaWindow.

linux-sources/
  Local Linux source trees used as analysis inputs.
```

## Removed Direction

The following MOCC-SE components are no longer active project architecture:

```text
protocol families
filesystem bindings
operation instances
rule registry
validation manifests
protocol analyzers
batch discovery/review/ranking pipeline
XFS/ext4 one-off audit scripts
large MOCC output artifacts
```

The removed material belonged to the protocol-EFSM direction.  MetaWindow uses
metadata-window dataflow instead.

## Intended Prototype Flow

```text
source file
  -> FunctionIR
  -> CFG
  -> metadata scope gate
  -> metadata effect extraction
  -> fallible edge detection
  -> EXPOSED/PROTECTED/CLOSED/UNKNOWN propagation
  -> error-exit candidate report
```
