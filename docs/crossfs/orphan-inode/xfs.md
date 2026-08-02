# OIDS Phase 1 Dossier: XFS

Status: `APPLICABLE` for source-level semantic correspondence.
Role: pre-freeze applicability screening only. Because XFS evidence is
inspected in Phase 1, XFS cannot later be described as a blind or unseen
held-out filesystem.

## Source snapshot

- Linux tag: `v6.14`
- Git commit: `38fec10eb60d687e30c8c6b5420d86e8149f7557`
- Archive SHA-256: `a294b683e7b161bb0517bb32ec7ed1d2ea7603dfbabad135170ed12d00c47670`
- Provenance: `linux-sources/linux-v6.14-fs/SOURCE_MANIFEST.json`

Relevant local files:

| File | SHA-256 |
|---|---|
| `fs/xfs/libxfs/xfs_inode_util.c` | `3976154596b822e9ccc71b3285212022f2edc18bc345eb7b3f2c8879c3153f3e` |
| `fs/xfs/libxfs/xfs_dir2.c` | `985c9aa7877db5064097a16f7555d453348c8103b87499ab9b89e729ef81fa69` |
| `fs/xfs/libxfs/xfs_ialloc.c` | `846f3deea5a18cff41624aa2369ae05e96cc9839bec90b3e04649d04a8fcbf11` |
| `fs/xfs/xfs_inode.c` | `4c06eda52608069cc603bd0b2ef627dbbd239ec2fd20140a8bad388fa77eaaf9` |
| `fs/xfs/xfs_log_recover.c` | `ae13ca85bef042a7d1b860e2346d7e690d7b0a86804c77cf7e480111a4823fcf` |

Line references below are pinned to this snapshot.

## Four required questions

### 1. What is the inode?

The canonical `inode` maps to `struct xfs_inode` and the VFS inode. Persistent
unlinked identity is the allocation-group inode number stored in an AGI bucket
and the inode's on-disk next-unlinked field. A source adapter must retain mount,
AG and inode-generation/allocation epoch in the semantic instance key.

### 2. What performs the orphan-registry role?

The canonical `orphan_registry` maps to the AGI unlinked hash buckets. The
bucket head is `agi_unlinked[bucket]`; each on-disk inode supplies the forward
link. `xfs_iunlink()` states that a zero-link inode is placed on an AGI list and
will be removed when the inode is freed (`xfs_inode_util.c:521-552`).

This is semantically a persistent deletion-responsibility registry even though
XFS calls it an unlinked list and distributes it across allocation groups.

### 3. When does deletion responsibility transfer?

`xfs_droplink()` logs the link-count change and invokes `xfs_iunlink()` when
the count reaches zero (`xfs_inode_util.c:649-677`). In namespace removal,
`xfs_dir_remove_child()` performs that drop before removing the directory name,
but both are part of the same transaction (`xfs_dir2.c:955-1034`).
`xfs_remove()` commits that transaction before returning (`xfs_inode.c:1859-1955`).

The successful AGI-list insertion is the persistent acceptance event. Normal
cleanup authority is `xfs_inactive()` after the last vnode reference; recovery
authority is the log-recovery unlinked-list processor.

### 4. When is terminal cleanup externally claimable?

`xfs_inactive()` truncates an unlinked inode and calls
`xfs_inactive_ifree()` (`xfs_inode.c:1365-1482`). The latter starts the inode
free transaction and commits `xfs_ifree()` (`xfs_inode.c:1188-1275`). Source
comments require the on-disk inode to be removed from the unlinked list
atomically with freeing (`xfs_inode.c:1769-1779`).

`xfs_inode_uninit()` performs `xfs_difree()` and then
`xfs_iunlink_remove()` in that same transaction before marking the in-core
inode free (`xfs_inode_util.c:702-740`). `xfs_difree()` changes the on-disk free
inode btree while leaving in-core cleanup to the caller (`libxfs/xfs_ialloc.c:2314-2318`),
which is why both sides of the atomic settlement are represented in the
evidence. This supplies direct evidence for the
transactional terminal-settlement interpretation also required by ext4.

## Canonical role mapping

| Canonical role | XFS source object |
|---|---|
| `operation` | `xfs_remove()`, inactive inode free, or recovery bucket iteration |
| `inode` | `struct xfs_inode`, allocation group and inode number |
| `namespace_entry` | XFS directory name removed by `xfs_dir_removename()` |
| `orphan_registry` | AGI `agi_unlinked[]` bucket plus on-disk next-unlinked links |
| `transaction_or_journal` | `struct xfs_trans` and XFS log recovery context |
| `deletion_authority` | `xfs_inactive()`/inodegc; after crash, log-recovery iunlink processing |

## Lifecycle

```text
namespace entry present, nlink > 0
-> remove transaction drops nlink
-> nlink == 0 triggers AGI unlinked-list insertion
-> directory name is removed in the same transaction
-> remove transaction commits
-> last active reference invokes xfs_inactive
-> data and attributes are truncated
-> inode free + AGI unlinked-list removal execute atomically
-> inode-free transaction commits
```

Recovery path:

```text
log recovery processes intents and forces the log
-> scans every AGI unlinked bucket
-> loads zero-link, allocated inodes
-> inodegc/inactive fully truncates and frees each inode
-> registry removal is atomic with inode free
-> recovery continues before user modifications are admitted
```

The recovery comment explicitly says that crash-left unlinked inodes are fully
truncated and freed, and that free plus list removal must be atomic
(`xfs_log_recover.c:2780-2788`). `xlog_recover_finish()` invokes this processing
after intent recovery (`xfs_log_recover.c:3505-3535`).

## Deadline correspondence

| Canonical deadline | XFS evidence | Status |
|---|---|---|
| `BEFORE_COMMIT` | Link count, AGI registration and directory removal share the remove transaction. | `CLOSED` at transaction settlement |
| `BEFORE_RECOVERY_EXPOSURE` | Iunlink processing is part of log-recovery finish before normal modifications. | `CLOSED` |
| `BEFORE_ORPHAN_REGISTRY_REMOVAL` | Source comments and `xfs_inode_uninit()` require atomic inode free plus list removal. | `CLOSED_WITH_TRANSACTIONAL_EQUIVALENCE` |

## Open adapter obligations

- Reconstruct distributed AGI bucket identity and forward/back pointers without
  treating in-memory backlinks as the persistent registry.
- Bind both namespace-removal and inactive-free transactions to one inode
  lifecycle while preserving their separate transaction epochs.
- Treat a failed inode-free reservation as retained registry responsibility,
  not completed deletion (`xfs_inode.c:1201-1227`).
- Preserve mount/AG/inode generation in instance identity.

## Held-out boundary

This dossier is intentionally detailed enough to influence the Phase 1
correspondence decision. Therefore XFS is epistemically revealed. After a
Btrfs/ext4 freeze it can still perform a useful zero-modification post-freeze
validation, but that result must be named `POST_FREEZE_XFS_VALIDATED`, not
`COMMON_HELDOUT_VALIDATED` in the strict unseen-data sense. A genuine held-out
claim requires a filesystem not used to shape the canonical rules.

## Phase 1 decision

Object, relation, lifecycle, authority and deadline correspondence are all
source-supported. XFS is `APPLICABLE` as a pre-freeze screening filesystem but
is excluded from the two-filesystem Phase 2 development/validation basis and
from any later claim of blind held-out evidence.
