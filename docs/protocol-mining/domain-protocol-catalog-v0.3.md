# Domain Protocol Catalog v0.3

Version: `0.3.0`; status: `FROZEN_NARROW_SCOPE`; date: 2026-08-01.

## RelocationRootAttachmentSettlement

**Intent:** a runtime relocation merge that observes a preexisting
`fs_root.reloc_root` attachment must restore the entry relation and owned
reference before return, or transfer to the named teardown authority and have
that authority complete settlement.

- Anchors: `operation`, `fs_root`; epoch=`operation_root + retry_generation`.
- Relation: `fs_root.reloc_root` plus root-reference ownership.
- Phases: `ATTACHED -> FAILURE_PENDING -> RESTORED/DELEGATED -> SETTLED`.
- Rule `RRM-I1`: at settlement the attachment is `DETACHED`.
- Rule `RRM-O1`: a checked merge failure activates one prestate obligation;
  only `relocation_teardown` may discharge it.
- Deadlines: operation return, owner termination and protocol completion are
  independent settlement boundaries.
- Evidence: confirmed Bug/fix source pair, selected origin-to-cleanup normal
  chain, structured replay and generic binding. Fixed-source all-path closure
  remains an explicit assumption boundary.

## DeviceShrinkSpaceAccounting

**Intent:** a writable device shrink updates free capacity by the actual loss
of writable free space and restores all changed accounting relations on
failure.

- Anchors: `operation`, `device`; related roles `fs_devices`, `fs_info`.
- Relations: `device.total_bytes`, `device.bytes_used`,
  `fs_devices.total_rw_bytes`, `fs_info.free_chunk_space`.
- Phases: `STABLE -> MUTATING -> ROLLBACK_PENDING -> RESTORED -> SETTLED`.
- Rule `DSSA-I1`: forward free-space delta equals the change in writable free
  capacity, with used bytes accounted for.
- Rule `DSSA-I2`: aggregate rollback is guarded by writable state and reuses
  the same computed delta.
- Rule `DSSA-O1`: after shrink failure every changed relation matches prestate
  at settlement.
- Deadlines: `ALWAYS` for accounting invariants; `AT_SETTLEMENT` for rollback.
- Evidence: confirmed Bug/fix patch provenance, independent Btrfs design and
  normal-source witnesses, four replay classes and generic binding.

## Scope and generalization

Both protocols are frozen narrowly and have one operation family each.
`generalization_eligible=false` and no held-out claim is made. Adding a second
family or cross-filesystem rule requires Catalog v0.4; v0.1/v0.2 hashes remain
unchanged.
