# Domain Protocol Catalog v0.4

Version: `0.4.0`; status: `FROZEN_CROSS_OPERATION_FAMILY`; date: 2026-08-01.

## DeviceTopologyRollback

Catalog v0.4 reuses the frozen v0.2 topology component without changing its
rules or hash. It owns topology membership, post-commit membership,
active-device identity, fsid identity and release safety. It no longer carries
an implicit assumption that capacity aggregates follow membership
automatically.

## WritableDeviceCapacityContribution

**Intent:** a device contributes to writable aggregate capacity exactly when
it is a topology member, writable and allocation-eligible. Add/remove and
resize operations must apply the correct aggregate delta and restore every
operation-local contribution delta after failure.

- Anchors: `operation`, `device`; epoch=`operation_root + retry_generation`.
- Roles: `fs_devices`, `fs_info`, optional `capacity_owner`.
- Relations: device membership/writable state, `device.total_bytes`,
  `device.bytes_used`, `fs_devices.total_rw_bytes`,
  `fs_info.free_chunk_space`, terminal capacity contribution.
- Phases: `STABLE -> MUTATING -> ROLLBACK_PENDING -> RESTORED/DELEGATED -> SETTLED`.
- `WDC-I1`: the reported contribution eligibility agrees with the typed
  membership/writable/allocation state available to the component.
- `WDC-I2`: aggregate deltas represent the actual capacity contribution
  change and the same delta is reused for restoration.
- `WDC-I3`: device release requires the capacity contribution to be detached.
- `WDC-O1`: every failed operation-local capacity delta returns to prestate or
  is completed by `capacity_owner` before settlement.

The protocol has two independent operation families:
`btrfs-device-membership-change` and `btrfs-device-capacity-resize`.

## DeviceTopologyCapacityComposition

The composition joins DTR and WDC instances only when their exact `operation`
and `device` identities match.

- `DTC-ID`: imprecise or conflicting shared identity yields `INCOMPLETE`.
- `DTC-C1`: `capacity.eligible` equals `Member && Writable && AllocationEligible`.
- `DTC-C2`: an eligible device has a present capacity contribution; an
  ineligible device has an absent contribution.
- `DTC-C3`: before release, both topology membership and capacity contribution
  are absent.

A component violation remains a composition violation. `UNKNOWN/WIDENED`
component or cross-relation facts cannot prove conformance.

## Version relation

Frozen v0.3 `DeviceShrinkSpaceAccounting` remains immutable and is now
understood as the shrink transition of WDC. It is not deleted or rewritten.
The v0.4 composition adds semantics; it does not retroactively change v0.2 or
v0.3 evaluation claims.

Cross-operation-family validation is closed, but no family was held out after
the v0.4 freeze and no cross-filesystem generalization is claimed.
