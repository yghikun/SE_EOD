# Failure-Path Filesystem Metadata Residual Analysis

This document defines the current analysis architecture.

## Overview

```text
Linux FS source
  -> frontend-neutral FunctionIR
  -> CFG builder
  -> filesystem metadata scope gate
  -> failure-point discovery
  -> backward slice for E_f
  -> forward error-path slice for C_f and T_f
  -> identity-aware cancellation
  -> residual normalization
  -> error-exit verification
  -> witness report
```

## Residual Equation

For a failure point `f`:

```text
E_f = filesystem metadata effects that can reach f
C_f = cancellation or compensation effects along the error path
T_f = explicitly protected or transferred filesystem metadata effects

R_f = Normalize(E_f (+) C_f) - T_f
```

`R_f` is the residual filesystem metadata state at an error exit.

## Filesystem Metadata Effect

Each effect is represented as:

```text
E = <Root, Key, Plane, Delta, Value, Site>
```

```text
Root:
  inode, superblock, block group, transaction, fs_devices, root, quota object,
  reservation object, recovery object, or unknown.

Key:
  inode id, block id, extent range, device id, quota subject, root id, or
  unknown.

Plane:
  STRUCTURAL, ACCOUNTING, or RECOVERY.

Delta:
  ADD, REMOVE, SET, CLEAR, INC, DEC, RESERVE, RELEASE, PROTECT, CLOSE, or
  UNKNOWN.

Value:
  normalized value source used to match inverse effects.

Site:
  source location and expression.
```

## Identity-Aware Cancellation

The analyzer cancels effects only when object identity is compatible:

```text
same or normalized Root
same or compatible Key
same Plane
inverse Delta
same or equivalent Value source
```

Examples:

```text
INC(inode.i_blocks, n)       cancels with DEC(inode.i_blocks, n)
SET(bitmap, block)           cancels with CLEAR(bitmap, block)
ADD(list, device)            cancels with REMOVE(list, device)
RESERVE(rsv, bytes)          cancels with RELEASE(rsv, bytes)
ATTACH(fs_root.reloc_root)   cancels with DROP(fs_root.reloc_root)
```

## Failure-Anchored Bidirectional Slicing

The analysis is anchored at each failure point.

Backward slice:

```text
find filesystem metadata effects that can reach the failure point -> E_f
```

Forward error-path slice:

```text
find cancellation, compensation, protection, and transfer effects -> C_f, T_f
```

Only the slice relevant to `mutation -> failure -> error exit` is analyzed.

## Protection Set

`T_f` contains effects explicitly protected by:

```text
journal ownership
transaction commit/abort ownership
orphan registration
replay/recovery registration
deferred cleanup ownership
verified invalidation that prevents direct reuse of partial metadata
```

If protection cannot be proven, the effect stays `UNKNOWN`.

## State Labels

The implementation may use:

```text
EXPOSED
PROTECTED
CLOSED
UNKNOWN
```

These are dataflow labels, not the method's main novelty and not a full EFSM.

## Report Kinds

```text
UNCLOSED_METADATA_RESIDUAL
  R_f is non-empty and reaches an error exit.

METADATA_RESIDUAL_UNKNOWN
  The slice reaches aliasing, indirect calls, async handoff, or helper semantics
  that prevent a conservative decision.

OUT_OF_SCOPE
  The effect is ordinary resource cleanup rather than filesystem metadata.
```

## Evidence Boundary

Witness reports are derived from the failure-path residual slice itself:

```text
failure point
error exit
E_f
C_f
T_f
R_f
scope rationale
unknown causes
confidence
```

The detector does not require sibling-path comparison or differential
restoration evidence.
