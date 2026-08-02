# OIDS Phase 1 Dossier: Btrfs

Status: `APPLICABLE` for source-level semantic correspondence.
Role: Phase 2 development filesystem. This is not yet a protocol, binding, or
conformance claim.

## Source snapshot

- Linux tag: `v6.14`
- Git commit: `38fec10eb60d687e30c8c6b5420d86e8149f7557`
- Archive SHA-256: `a294b683e7b161bb0517bb32ec7ed1d2ea7603dfbabad135170ed12d00c47670`
- Provenance: `linux-sources/linux-v6.14-fs/SOURCE_MANIFEST.json`

Relevant local files:

| File | SHA-256 |
|---|---|
| `fs/btrfs/orphan.c` | `81f939a4d681a407a480a0d81d676a883fe0d9e5c9f5c64257362e9ec1c54012` |
| `fs/btrfs/inode.c` | `a802ed49f32c5b48da14b474ed6f75c12d2d073f7afaf499fdb15a2a29b680fe` |
| `fs/btrfs/inode-item.c` | `c799d464d7b33359e9db2c357a4b5e5b804460eb8389193f394db5c2db5a9148` |
| `fs/btrfs/disk-io.c` | `ec2f75aef087365b843ffa5c1177e38c7b7dd0da5f4906c1eecb20b884a02a89` |

Line references below are pinned to this snapshot.

## Four required questions

### 1. What is the inode?

The canonical `inode` maps to `struct btrfs_inode` and its VFS inode, scoped by
the Btrfs root. Persistent orphan identity is encoded by a
`BTRFS_ORPHAN_OBJECTID / BTRFS_ORPHAN_ITEM_KEY` key whose offset is the inode
number (`orphan.c:9-23`). The operation must therefore retain at least root
identity plus inode number; the adapter must also carry an inode/allocation
epoch because the orphan key itself does not encode generation.

### 2. What performs the orphan-registry role?

The canonical `orphan_registry` maps to per-root orphan items in the B-tree.
`btrfs_insert_orphan_item()` inserts the key and `btrfs_del_orphan_item()`
removes it (`orphan.c:9-47`). `btrfs_orphan_add()` describes the purpose as
surviving an interrupted unlink and aborts the transaction if insertion fails
(`inode.c:3491-3506`).

The registry is not a homogeneous deletion-only table. Linked inodes can also
have orphan items for incomplete fs-verity metadata or old truncate behavior
(`inode.c:3646-3671`). An OIDS adapter must select `i_nlink == 0` deletion
instances instead of treating every orphan item as an OIDS instance.

### 3. When does deletion responsibility transfer?

For an ordinary unlink, `btrfs_unlink_inode()` removes namespace metadata,
drops the link count and updates the inode (`inode.c:4207-4300`). If the count
reaches zero, `btrfs_unlink()` inserts the orphan item before ending the same
transaction (`inode.c:4319-4354`). Successful insertion is the source-level
acceptance event for persistent cleanup responsibility. Failure aborts the
transaction; it is not a valid delegation.

Normal cleanup authority is exercised at final eviction. Recovery authority is
exercised by `btrfs_orphan_cleanup()`, which resolves each zero-link inode and
drops the reference so that eviction performs deletion (`inode.c:3520-3609`,
`inode.c:3695-3699`).

### 4. When is terminal cleanup externally claimable?

`btrfs_evict_inode()` first commits delayed inode state, kills delayed inode
items and truncates the inode items (`inode.c:5313-5401`). The truncate helper
removes all keys at or above `min_type`; with `min_type == 0` this covers the
inode's persistent item set (`inode-item.c:436-456`, `inode-item.c:523-560`).
Only after that does it attempt `btrfs_orphan_del()` (`inode.c:5403-5417`). If registry removal
cannot be completed, the item is deliberately left for a later mount
(`inode.c:5420-5429`).

Therefore the persistent relation supports this claim:

```text
orphan item absent after cleanup commit
=> deletion cleanup reached the Btrfs terminal removal stage
```

The reverse is intentionally not required: a stale orphan item may remain
after successful deletion, which is a safe retry state rather than proof that
the inode is still live.

## Canonical role mapping

| Canonical role | Btrfs source object |
|---|---|
| `operation` | unlink transaction, final `btrfs_evict_inode()`, or mount cleanup iteration |
| `inode` | `struct btrfs_inode` plus root-scoped inode number |
| `namespace_entry` | B-tree directory item, directory index and inode reference |
| `orphan_registry` | per-root `BTRFS_ORPHAN_ITEM_KEY` item |
| `transaction_or_journal` | `struct btrfs_trans_handle` |
| `deletion_authority` | final eviction; after crash, mount-time `btrfs_orphan_cleanup()` |

## Lifecycle

```text
namespace entry present, nlink > 0
-> unlink transaction removes directory metadata and drops nlink
-> nlink == 0
-> orphan item inserted in the same transaction
-> transaction ends
-> last active reference is released
-> btrfs_evict_inode truncates persistent inode items
-> orphan item removal is attempted
-> transaction ends; inode is cleared
```

Recovery path:

```text
mount discovers orphan item
-> btrfs_orphan_cleanup resolves root + inode number
-> zero-link inode is released through iput
-> eviction performs truncation and registry settlement
-> mount initialization continues
```

`open_ctree()` orders dead-root discovery before orphan cleanup, because early
orphan removal could lose pending deletion responsibility after another crash
(`disk-io.c:3089-3114`). This directly supports recovery safety rather than a
mere cleanup convention.

## Deadline correspondence

| Canonical deadline | Btrfs evidence | Status |
|---|---|---|
| `BEFORE_COMMIT` | Zero-link orphan insertion occurs before `btrfs_end_transaction()` in unlink. | `CLOSED` at transaction settlement |
| `BEFORE_RECOVERY_EXPOSURE` | `open_ctree()` runs root discovery and orphan cleanup during mount initialization. | `CLOSED` |
| `BEFORE_ORPHAN_REGISTRY_REMOVAL` | Persistent inode items are truncated before orphan deletion; failure leaves the record for retry. | `CLOSED` |

`BEFORE_COMMIT` is a transaction-level condition. Source statement order alone
does not represent exposure because namespace removal and registry insertion
belong to the same Btrfs transaction.

## Open adapter obligations

- Bind identity as filesystem/root/inode/allocation epoch; root plus inode
  number alone is insufficient for an analyzer instance key.
- Select only zero-link deletion records; exclude linked-inode truncate and
  fs-verity orphan uses.
- Treat leftover registry records as safe retry state, not as an automatic
  violation.
- Prove the exact transaction boundary in the future source frontend; this
  dossier does not substitute for interprocedural binding.

## Phase 1 decision

Object, relation, lifecycle, authority and deadline correspondence are all
source-supported. Btrfs is `APPLICABLE` as the development side of OIDS Phase
2. Replay, proof closure and a canonical adapter remain intentionally open.
