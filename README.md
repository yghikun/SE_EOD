# MetaWindow

MetaWindow is a lightweight static-analysis prototype for Linux file-system
error paths.  The project now focuses on one research question:

> Does an error exit leave an unprotected file-system metadata effect exposed?

The method is intentionally narrower than the previous MOCC-SE direction.  It
does not verify complete file-system protocol state machines, infer full
metadata invariants, or check ordinary cleanup bugs.  It tracks metadata effects
that become exposed before a fallible operation, then verifies whether the
error path closes the effect, protects it through transaction/recovery
machinery, or must conservatively report an unknown.

## Core Idea

MetaWindow detects unprotected metadata failure windows:

```text
metadata effect opens
  -> later operation may fail
  -> error path exits
  -> effect is not closed, protected, or marked unknown
```

Each tracked effect has a lightweight state:

```text
EXPOSED    metadata was changed and is not yet protected
PROTECTED  transaction, journal, orphan, recovery, or deferred machinery owns it
CLOSED     rollback, compensation, or normal completion closed it
UNKNOWN    aliasing, async handoff, indirect calls, or helper semantics are unclear
```

MDR-style differential restoration is retained only as supporting evidence:
when MetaWindow finds an exposed effect, the tool may look for a nearby path
that closes a similar effect and use it as a patch hint.  MDR is not the main
detection entry.

## Metadata Scope

MetaWindow only analyzes file-system metadata effects:

```text
inode and filesystem-private inode fields
directory entries, extents, B-tree items
block/inode bitmap and free-space state
quota, reservation, and refcount metadata
root, device, chunk, and topology state
journal, transaction, orphan, replay, and recovery state
persistent or recovery-visible counters and flags
```

It excludes ordinary resources:

```text
kmalloc memory
temporary buffer_head or folio references
path/name buffers
locks
logging
pure local variables
generic helper temporaries
```

A normally temporary-looking object can be in scope only when it carries
metadata completion semantics, such as `xfs_trans`, `btrfs_block_rsv`, `dquot`,
`delayed_ref`, `reloc_root`, a journal handle, or a reservation ticket.

## Retained Project Shape

```text
src/frontend/              frontend-neutral C IR and tree-sitter adapter
src/cfg.py                 function-local CFG utilities
src/parser.py              C parser fallback helpers
src/function_extractor.py  function extraction helpers
src/metadata_scope.py      versioned metadata scope contract
src/metawindow.py          lightweight MetaWindow data model
configs/metadata_scope/    metadata boundary and confirmed-bug scope labels
outputs/confirmed_bugs.md  curated evidence ledger used for motivation
docs/                      current architecture and paper notes
linux-sources/             local Linux source inputs, not project logic
```

## Current Evidence Mapping

Primary MetaWindow examples:

```text
#7   btrfs_recover_relocation: relocation-root recovery state left exposed
#16  btrfs_init_new_device: transaction update list membership left exposed
#17  btrfs_init_new_device: active device pointers not restored
#18  btrfs_init_new_device: fs_devices sprout topology not rolled back
#12  xfs_qm_quotacheck_dqadjust: dquot metadata ownership/reference case
```

Outcome-window extensions:

```text
#1, #2, #5, #8, #13  metadata failure reported as success
#4                   stale error after successful metadata retry
#15                  positive success skips chunk metadata reservation
```

Out of scope for the main method:

```text
#3, #6, #9, #10, #11, #14
```

These are useful historical resource-cleanup findings, but they are not
MetaWindow metadata-window evidence.

## Install and Check

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```

The current codebase is a trimmed research scaffold.  It preserves the parser,
frontend, CFG, metadata scope, and evidence inputs needed to implement the
MetaWindow prototype.  Removed MOCC-SE protocol, rule-registry, validation, and
batch-review artifacts should be treated as historical design material, not as
active project state.
