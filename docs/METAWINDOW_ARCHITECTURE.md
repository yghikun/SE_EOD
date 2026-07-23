# MetaWindow Architecture

MetaWindow is a lightweight static analysis for Linux file-system metadata error
paths.  It detects unprotected metadata failure windows instead of verifying
complete protocol state machines.

## Architecture

```text
Linux FS Source
  -> Frontend + FunctionIR
  -> CFG Builder
  -> Metadata Scope Gate
  -> Metadata Effect Extractor
  -> Fallible Edge Detector
  -> Failure Window Dataflow
  -> Error-Exit Verifier
  -> Optional MDR Evidence
  -> Witness Report
```

## Metadata Effect Model

Each effect is represented as:

```text
E = <Root, Key, Plane, Delta, Site>
```

Fields:

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

Site:
  source location and expression.
```

The model borrows only lightweight identity and plane typing from the rejected
MetaClose design.  It does not infer complete metadata coupling groups.

## State Model

```text
EXPOSED
  A metadata mutation is visible to later code and is not yet protected.

PROTECTED
  A visible journal, transaction, orphan, recovery, or deferred mechanism has
  taken responsibility for the effect.

CLOSED
  Rollback, compensation, or normal completion closed the effect.

UNKNOWN
  The analyzer cannot prove either exposure, protection, or closure because of
  aliasing, indirect calls, async handoff, or missing helper semantics.
```

This is a path-sensitive dataflow state, not an EFSM.  MetaWindow does not use
MOCC-SE operation states such as `COMMITTING`, `HANDLING_FAILURE`, or
`RETRYING`.

## Failure Window

A failure window opens when a metadata effect enters `EXPOSED`.

```text
metadata mutation -> EXPOSED
fallible edge     -> window is checked on the error edge
rollback          -> CLOSED
transaction handoff -> PROTECTED
unknown escape    -> UNKNOWN
normal completion -> CLOSED
```

An error exit reports a candidate only when an effect remains `EXPOSED`.

```text
EXPOSED at error exit   -> UNCLOSED_METADATA_FAILURE_WINDOW
PROTECTED at error exit -> accepted, with protection witness
CLOSED at error exit    -> accepted
UNKNOWN at error exit   -> review/unknown, not a bug claim
```

## Metadata Scope Gate

In scope:

```text
inode and private inode fields
extent, tree item, directory, namespace, and orphan metadata
bitmap, free-space, block group, chunk, and device topology metadata
quota, reservation, and refcount metadata
journal, transaction, replay, recovery, and delayed metadata work
persistent or recovery-visible counters and flags
```

Out of scope:

```text
ordinary kmalloc memory
temporary buffer_head or folio references
path/name buffers
locks
logging
pure local variables
generic helper temporaries
```

Boundary rule:

> A supporting object is in scope only if its lifetime carries metadata
> completion semantics.

Examples: `xfs_trans`, `btrfs_block_rsv`, `dquot`, `delayed_ref`,
`reloc_root`, journal handles, and reservation tickets.

## Fallible Edges

MetaWindow identifies common static failure-frontier shapes:

```text
ret = call(); if (ret) ...
ret = call(); if (ret < 0) ...
ptr = call(); if (IS_ERR(ptr)) ...
if (call(...) < 0) ...
goto out_error
return ret
return error
```

The call name is not the specification.  The analyzer reports only when the
edge can carry an exposed metadata effect to an error exit.

## Optional MDR Evidence

After MetaWindow finds an exposed effect at an error exit, the analyzer may look
for nearby evidence:

```text
another path closes the same Root/Key/Plane effect
a cleanup label contains the missing inverse action
a historical fix inserted a matching restoration fragment
```

This evidence improves witness quality and patch hints, but it is not required
for detection.

## Report Schema

```text
UNCLOSED_METADATA_FAILURE_WINDOW
  function
  source version
  opened effect
  opening site
  fallible edge
  error exit
  final state
  missing closure or protection
  scope rationale
  optional MDR evidence
  confidence
```

Reports are candidates for review.  Confirmation still requires source review,
maintainer feedback, fault injection, historical fixes, or accepted patches.
