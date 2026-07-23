# MetaWindow Paper Roadmap

Updated: 2026-07-23

## Thesis

Linux file-system error paths can leave metadata in an intermediate state when
a metadata effect is exposed before a later operation fails.  MetaWindow
statically detects these unprotected metadata failure windows without building a
complete file-system protocol state machine.

Concise claim:

> We statically detect unprotected metadata failure windows in Linux
> file-system error paths: metadata effects that become exposed before a
> fallible operation and remain neither closed nor explicitly protected at an
> error exit.

## Research Question

Can a lightweight, metadata-scoped dataflow analysis find real Linux
file-system error paths where exposed metadata effects survive failure exits?

Secondary questions:

```text
RQ1: How many curated metadata findings are expressible as failure windows?
RQ2: How much does metadata scope filtering reduce ordinary cleanup noise?
RQ3: How often do reports end in EXPOSED, PROTECTED, CLOSED, or UNKNOWN?
RQ4: Does optional MDR-style restoration evidence improve manual review?
RQ5: What are the remaining false-positive causes?
```

## Method Outline

```text
1. Metadata scope gate
2. Metadata effect extraction
3. Failure window construction
4. Protection and closure tracking
5. Error-exit verification
6. Optional differential restoration evidence
```

The main contribution is MetaWindow.  MDR is used only for supporting evidence
and patch hints.

## Core Definitions

```text
Metadata effect:
  <Root, Key, Plane, Delta, Site>

Plane:
  STRUCTURAL | ACCOUNTING | RECOVERY

State:
  EXPOSED | PROTECTED | CLOSED | UNKNOWN

Unprotected metadata failure window:
  an EXPOSED effect that reaches an error exit after a fallible edge without
  becoming CLOSED or PROTECTED
```

## Expected Contributions

1. A metadata-scoped failure-window abstraction for Linux file-system error
   paths.
2. A lightweight state model that distinguishes exposed, protected, closed, and
   unknown metadata effects without protocol EFSMs.
3. An implementation strategy over frontend-neutral C IR and function-local CFG.
4. An evaluation using curated Linux ext4, XFS, Btrfs, and F2FS findings, with
   ordinary resource-cleanup bugs explicitly excluded from the main claim.
5. Optional MDR-style restoration evidence for more actionable witness reports.

## Development Evidence

Primary MetaWindow examples:

```text
#7   btrfs_recover_relocation
#16  btrfs_init_new_device
#17  btrfs_init_new_device
#18  btrfs_init_new_device
#12  xfs_qm_quotacheck_dqadjust, if framed as quota metadata ownership
```

Outcome-window extension:

```text
#1, #2, #5, #8, #13
#4 and #15 as return/outcome-value variants
```

Out-of-scope resource cleanup:

```text
#3, #6, #9, #10, #11, #14
```

## Related-Work Positioning

MetaWindow is distinct from:

```text
EDP-style error-code propagation:
  MetaWindow tracks metadata effects exposed before failure, not only return
  values.

Runtime consistency checking:
  MetaWindow is static source analysis and focuses on software error exits.

API postcondition mining:
  MetaWindow does not depend on target API pairs as the specification source.

MOCC-SE:
  MetaWindow removes protocol EFSMs, rule registries, owner hierarchies, and
  large accounting systems.

MDR:
  MDR requires comparable paths; MetaWindow uses metadata windows as the primary
  detection entry and uses path comparison only as extra evidence.
```

## Evaluation Plan

Start with the curated ledger in `outputs/confirmed_bugs.md`.

Report:

```text
in-scope confirmed findings expressible as windows
out-of-scope findings rejected by metadata scope
EXPOSED/PROTECTED/CLOSED/UNKNOWN distribution
candidate precision after manual review
main false-positive causes
manual review time with and without MDR evidence
```

Do not report ordinary memory/resource cleanup recall as MetaWindow recall.

## Implementation Plan

Phase 1:

```text
define dataclasses and report schema
parse functions into FunctionIR and CFG
identify simple fallible edges
extract assignment/call-based metadata effects
load metadata scope and confirmed-bug scope labels
```

Phase 2:

```text
propagate EXPOSED/CLOSED/PROTECTED/UNKNOWN over CFG
emit UNCLOSED_METADATA_FAILURE_WINDOW reports
add tests for synthetic ext4/btrfs/xfs-like snippets
```

Phase 3:

```text
add helper summaries for transaction/recovery protection
add optional MDR evidence and restoration hints
evaluate curated findings and a fresh source slice
```

## Paper Non-Claims

Do not claim:

```text
first filesystem error-path checker
complete Linux C soundness
complete crash consistency
automatic bug confirmation
coverage of ordinary resource leaks
large-scale filesystem protocol verification
```
