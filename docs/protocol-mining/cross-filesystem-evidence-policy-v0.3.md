# Cross-Filesystem Evidence Policy v0.3

## Decision

Normal source from another filesystem may support a rule only when all of the
following match: object roles, relation direction, units/equation, lifecycle
phase, authority and deadline. Shared vocabulary such as `device`, `inode`,
`dentry`, `free`, or `counter` is not enough.

Cross-filesystem source can provide design semantics and safe-path evidence.
It cannot replace a confirmed Bug witness or the exact repair witness for a
specific Bug, and it cannot turn unrelated object types into one protocol.

## Applied result

`RelocationRootAttachmentSettlement` uses the Btrfs-specific typed relation
`fs_root.reloc_root` and owned root reference. Other filesystems do not provide
an equivalent relation, so no cross-filesystem evidence is counted.

`DeviceShrinkSpaceAccounting` uses Btrfs device capacity, writable aggregate
capacity and allocatable free-chunk capacity. ext4/XFS/F2FS evidence was
screened and rejected as non-equivalent; Btrfs normal add/remove and consumer
paths are retained as design/normal evidence, not held-out validation.

For a historical Bug with no fix, the result is at most a protocol candidate
unless an independently observed safe/repaired path supplies the missing
repair semantics. A normal implementation in another filesystem cannot by
itself prove that the unfixed Bug conforms after repair.
