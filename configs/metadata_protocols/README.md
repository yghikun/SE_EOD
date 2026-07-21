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

IDs are explicit configuration data and remain stable across serialization.
All event IDs are unique across effects, compensations, and handlers. Effects
always declare a scope and owner. A handler always declares its object, guard,
owner, and the effects it owns. `ABORTED` handlers may only own
`TRANSACTION_SCOPED` effects.

Return guards that overlap, or whose mutual exclusion cannot be proven by the
M0 comparison checker, require distinct integer priorities. Higher values take
precedence. Unknown fields and enum values are rejected rather than ignored.

`example_replay_recovery_v1.json` is a schema fixture, not an active analysis
configuration. M0 does not load metadata protocols from `src.main` and does not
change existing SE-EOD candidate output.

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

The development function names occur only in `operation.entry_functions` to
select relevant functions. Candidate semantics come from callee roles, return
contracts, CFG branches, handler ownership, and legal exits.

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
