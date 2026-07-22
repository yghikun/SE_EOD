# MOCC-SE Metadata Protocols

This directory contains versioned semantic protocols consumed by
`src.metadata_protocol`. M0 supports strict UTF-8 JSON files. YAML is not
accepted until a versioned YAML loader is implemented.

Every protocol declares:

- `schema_version` and semantic `protocol_version`;
- filesystem and Linux-version applicability;
- operation entries, principal objects, phases, and callee roles;
- return contracts, effects, compensations, handler transfers, accounting
  constraints, and legal exits.
- optional `operation.discovery` anchors used only by source-tree semantic
  discovery.

IDs are explicit configuration data and remain stable across serialization.
All event IDs are unique across effects, compensations, and handlers. Effects
always declare a scope and owner. A handler always declares its object, guard,
owner, and the effects it owns. `ABORTED` handlers may only own
`TRANSACTION_SCOPED` effects.

Return guards that overlap, or whose mutual exclusion cannot be proven by the
M0 comparison checker, require distinct integer priorities. Higher values take
precedence. Unknown fields and enum values are rejected rather than ignored.

`operation.discovery` is a conservative discovery-only context. It can require
additional callees or fields, forbid known out-of-scope callees, and raise the
minimum role coverage needed before a non-entry function is sent to semantic
review. It can also declare broad semantic patterns:
`failure_return_mismatch`, `mutation_failure_cleanup`,
`retry_return_provenance`, and `conditional_accounting`. These anchors and
patterns do not change protocol state propagation, legal exits, or exact-entry
analysis.

`example_replay_recovery_v1.json` is a schema fixture, not an active analysis
configuration. The legacy `src.main` pipeline has been removed; active metadata
protocols are consumed only by the dedicated MOCC-SE analyzer and discovery
entry points.

Protocol files are filesystem-specific instances of the parameterized MOCC-SE
extended state machine. They define object roles, phases, return contracts,
effect scope/owner, compensation or handler transfer, accounting constraints,
and legal exits. Generic propagation and legal-exit verification remain shared;
configuration describes legal behavior instead of encoding a known function as
a bug. This is a method-level formalization, not a claim that an independent
state-machine runtime has been implemented.

`protocol_a_replay_recovery_v1.json` is the active Protocol A MVP. Run it with
the dedicated entry point so the historical SE-EOD CSV/JSONL schemas remain
unchanged:

```powershell
python -m src.metadata_protocol_analyzer `
  --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json `
  --source linux-sources/linux-v6.8-fs/fs/ext4/fast_commit.c `
  --source-version linux-v6.8 `
  --function ext4_fc_replay_add_range `
  --out outputs/mocc/protocol-a-ext4-v6.8.json
```

The development function names in `operation.entry_functions` are regression
seeds. Candidate semantics come from callee roles, return contracts, CFG
branches, handler ownership, and legal exits. M11 broad discovery may use
operation semantic patterns to send non-entry functions to `DISCOVERY_REVIEW`,
but those review items are not protocol-proven candidates.

`protocol_b_device_topology_v1.json` is the active Protocol B MVP. It models
relocation-root attachment, seed/sprout topology, active device pointers,
device-list membership, and the reviewed `post_commit_list` callee summary.
Assignment field/RHS and call result/argument matchers bind effects and
compensations to principal objects. A configured `may` effect remains
`ANALYSIS_UNKNOWN`; it cannot produce a definite candidate or close an effect.
Reproduction commands and versioned output are recorded in
`outputs/mocc-protocol-b-v1/README.md`.

`protocol_c_activation_accounting_v1.json` is the active Protocol C MVP. It
models ext4 fallback return provenance and Btrfs activation/reservation
accounting. The first accounting relation is deliberately boolean:
`pending metadata work exists => matching reservation exists`; it does not
attempt arbitrary metadata arithmetic. `ret < 0`, `ret == 0`, and `ret > 0`
are separate return outcomes. Reproduction commands and versioned output are
recorded in `outputs/mocc-protocol-c-v1/README.md`.
The Btrfs operation also declares discovery-only context requiring both
activation and reservation calls before a renamed non-entry function is treated
as the same operation for review.
