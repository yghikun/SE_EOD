# Device Protocol Decomposition v0.4

## First-principles decision

DTR and DSSA share real objects, but a flat merge would force shrink-specific
size formulas into topology transitions and topology-specific identity rules
into shrink operations. The correct unit is protocol composition:

```text
DeviceTopologyRollback
    membership / active pointer / fsid / post-commit responsibility
                    |
                    | exact operation + device identity
                    v
WritableDeviceCapacityContribution
    writable eligibility / total_rw_bytes / free_chunk_space / restore
```

Device add/remove instantiates both components. Device shrink instantiates WDC
only. This removes duplicated counter rules while preserving distinct
operation lifecycles and deadlines.

## Cross-object causal chain

```text
topology membership changes
-> allocation eligibility changes
-> capacity contribution must change
-> total_rw_bytes and free_chunk_space must change together
-> failure must restore topology and contribution independently
-> release is legal only after both are detached
```

Restoring membership without restoring capacity leaves nonexistent space
available to allocation. Restoring capacity without membership leaves the
topology and allocator describing different device sets.

## TOC constraint

The current constraint is no longer protocol expression. It is post-freeze
held-out evidence. The add/remove and resize families both participated in
forming v0.4, so they validate cross-operation reuse but cannot be counted as
held-out generalization.
