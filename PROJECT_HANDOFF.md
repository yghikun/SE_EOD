# MetaWindow Project Handoff

Updated: 2026-07-23

The project has been reset from the previous MOCC-SE protocol/EFSM direction to
MetaWindow: a lightweight static analysis for unprotected file-system metadata
failure windows.

## Current Claim

MetaWindow is not a general error-path cleanup checker.  It reports only when a
file-system metadata effect becomes exposed before a fallible operation and an
error exit reaches the function boundary without closing, protecting, or
conservatively marking that effect unknown.

The method deliberately avoids:

```text
complete filesystem protocol EFSMs
multi-protocol rule registries
generic owner/handler modeling
large accounting-obligation systems
full crash-consistency proofs
ordinary memory, buffer, folio, path, or lock cleanup bugs
```

## Main Abstractions

```text
Metadata effect
  <Root, Key, Plane, Delta, Site>

Effect state
  EXPOSED | PROTECTED | CLOSED | UNKNOWN

Failure window
  an EXPOSED metadata effect plus a later fallible edge that can reach an
  error exit before the effect is CLOSED or PROTECTED
```

`PROTECTED` must be explicit: journal, transaction, orphan, recovery, deferred
cleanup, or another visible mechanism has taken responsibility for the metadata
effect.  If the transfer cannot be proven, the state is `UNKNOWN`, not legal.

## Active Pipeline

```text
Linux fs source
  -> frontend-neutral FunctionIR
  -> function-local CFG
  -> metadata scope gate
  -> metadata mutation/effect extraction
  -> failure window construction
  -> protection and closure tracking
  -> error-exit verification
  -> optional MDR-style sibling evidence
```

MDR is now only an evidence layer.  It may provide a repair hint when another
nearby path closes a similar effect, but MetaWindow does not depend on finding a
comparable sibling path.

## Files to Care About

```text
README.md
PAPER_ROADMAP.md
PROJECT_HANDOFF.md
docs/METAWINDOW_ARCHITECTURE.md
configs/metadata_scope/metadata_scope_v1.json
outputs/confirmed_bugs.md
src/frontend/
src/cfg.py
src/parser.py
src/function_extractor.py
src/metadata_scope.py
src/metawindow.py
```

The Linux source trees under `linux-sources/` are retained as local inputs.
They are not method code.

## Evidence Boundary

Use `outputs/confirmed_bugs.md` as the curated evidence ledger.  Current mapping:

```text
MetaWindow core:
  #7, #16, #17, #18, maybe #12

Outcome-window extension:
  #1, #2, #5, #8, #13, maybe #4 and #15

Out of scope:
  #3, #6, #9, #10, #11, #14
```

Do not turn historical resource-lifetime bugs into MetaWindow evidence unless an
explicit metadata effect, protection responsibility, and error-exit consequence
can be stated.

## Next Implementation Steps

1. Implement fallible-edge detection over `FunctionIR` and CFG.
2. Implement raw metadata effect extraction independent of MOCC-SE protocols.
3. Map effects through the metadata scope gate into
   `<Root, Key, Plane, Delta, Site>`.
4. Propagate `EXPOSED/PROTECTED/CLOSED/UNKNOWN` states path-sensitively.
5. Report `UNCLOSED_METADATA_FAILURE_WINDOW` only at error exits.
6. Add optional MDR evidence: nearby restoration fragment and patch hint.

## Non-Claims

The current scaffold does not yet prove precision, recall, or broad
generalization across file systems.  It does not claim soundness or completeness
for Linux C, and it does not automatically produce confirmed bugs.
