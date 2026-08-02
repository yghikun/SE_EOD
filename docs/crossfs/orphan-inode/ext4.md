# OIDS Phase 1 Dossier: ext4

Status: `APPLICABLE` for source-level semantic correspondence.
Role: Phase 2 validation filesystem. This is not yet a protocol, binding, or
conformance claim.

## Source snapshot

- Linux tag: `v6.14`
- Git commit: `38fec10eb60d687e30c8c6b5420d86e8149f7557`
- Archive SHA-256: `a294b683e7b161bb0517bb32ec7ed1d2ea7603dfbabad135170ed12d00c47670`
- Provenance: `linux-sources/linux-v6.14-fs/SOURCE_MANIFEST.json`

Relevant local files:

| File | SHA-256 |
|---|---|
| `fs/ext4/orphan.c` | `1d01da885095a3f909c208ea716bbb566df7afec06e39698e639a9d125a332c3` |
| `fs/ext4/inode.c` | `235f4d1ba3be429853e4cf75c11866121b7882b8311459a52c2c31a44cd2c887` |
| `fs/ext4/ialloc.c` | `ee7bd95271ee1acaa1375a0334e1bfd96c0f0ffbe1bc41c7ed7c61b336bdf119` |
| `fs/ext4/namei.c` | `be2503b69f747a0f31412ca950908118335f99bd422f90ae5e709214fc55e9a1` |
| `fs/ext4/super.c` | `90115e27db094c7abeb41de1466de65c27217c0dc51c8ec137bf3cea2fcc4a6c` |

Line references below are pinned to this snapshot.

## Four required questions

### 1. What is the inode?

The canonical `inode` maps to the VFS inode plus `struct ext4_inode_info` and
its filesystem-scoped inode number. Both ext4 orphan representations store an
inode number. A later adapter must add a mount/allocation epoch because the
registry record itself is not a generation-qualified protocol instance key.

### 2. What performs the orphan-registry role?

The role is a semantic union of two ext4 mechanisms:

- the orphan file, recorded through `EXT4_STATE_ORPHAN_FILE` and
  `i_orphan_idx`;
- the legacy on-disk singly linked list headed by superblock
  `s_last_orphan` and chained through `NEXT_ORPHAN(inode)`.

`ext4_orphan_add()` uses the orphan file when available and falls back to the
legacy list when that file is full (`orphan.c:99-180`). The source comment
states that the record protects unlinked deletion or multi-transaction
truncate across a crash and is consumed during recovery (`orphan.c:87-97`).

An OIDS adapter must filter `i_nlink == 0`. Linked inodes undergoing truncate
share the same registry but are not deletion-settlement instances
(`orphan.c:323-360`).

### 3. When does deletion responsibility transfer?

In `__ext4_unlink()`, the link count is dropped; when it becomes zero,
`ext4_orphan_add()` is called and the inode is dirtied before
`ext4_journal_stop()` (`namei.c:3281-3305`). Thus namespace removal, zero-link
state and registry acceptance belong to one journal transaction. The accepted
registry record transfers cleanup responsibility to final eviction or mount
recovery.

At recovery, `ext4_process_orphan()` truncates linked records but drops the
reference for zero-link records so that normal eviction deletion runs
(`orphan.c:323-360`).

### 4. When is terminal cleanup externally claimable?

`ext4_evict_inode()` runs at final `iput()` for zero-link inodes
(`inode.c:166-190`). It truncates data and removes xattrs, then calls
`ext4_orphan_del()`, records deletion time, dirties the inode, and frees the
inode, all under the same journal handle (`inode.c:228-309`). The final free
path clears the in-core inode before marking its inode bitmap allocation free,
which prevents inode-number aliasing (`ialloc.c:224-235`).

There is an important source-order difference from Btrfs:

```text
ext4_orphan_del(handle, inode)
-> ext4_mark_inode_dirty(handle, inode)
-> ext4_free_inode(handle, inode)
-> ext4_journal_stop(handle)
```

Consequently OIDS must not define `BEFORE_ORPHAN_REGISTRY_REMOVAL` as a literal
C-call ordering rule requiring inode bitmap free before `ext4_orphan_del()`.
The defensible cross-filesystem rule is transactional:

```text
registry removal must not commit unless terminal inode deletion is
already durably settled or atomically co-settled in the same transaction
```

This preserves ext4's atomic settlement and Btrfs's safe prior-settlement
ordering without weakening the semantic deadline into a cleanup-after-return
convention.

## Canonical role mapping

| Canonical role | ext4 source object |
|---|---|
| `operation` | `__ext4_unlink()`, final `ext4_evict_inode()`, or recovery iteration |
| `inode` | VFS inode plus `struct ext4_inode_info` |
| `namespace_entry` | ext4 directory entry removed in the unlink journal handle |
| `orphan_registry` | orphan-file slot or legacy `s_last_orphan` chain |
| `transaction_or_journal` | JBD2 `handle_t` |
| `deletion_authority` | final eviction; after crash, `ext4_orphan_cleanup()` plus eviction |

## Lifecycle

```text
namespace entry present, nlink > 0
-> journaled unlink removes the directory entry and drops nlink
-> nlink == 0
-> orphan-file slot or legacy orphan-list entry is recorded
-> journal handle stops
-> last active reference is released
-> ext4_evict_inode truncates data and xattrs
-> registry removal + inode free are staged in one journal handle
-> journal handle stops; inode is cleared
```

Recovery path:

```text
mount initializes orphan information
-> ext4_orphan_cleanup scans legacy chain and orphan-file slots
-> zero-link records are released through iput
-> eviction performs transactional terminal settlement
-> recovery is marked complete
```

Mount calls orphan cleanup before `ext4_mark_recovery_complete()`
(`super.c:5583-5616`). The cleanup function explicitly walks zero-link inodes
deleted from directories but held open at crash time (`orphan.c:363-380`) and
processes both registry forms (`orphan.c:456-488`).

## Deadline correspondence

| Canonical deadline | ext4 evidence | Status |
|---|---|---|
| `BEFORE_COMMIT` | Zero-link orphan registration and inode dirtying precede `ext4_journal_stop()` in unlink. | `CLOSED` at journal settlement |
| `BEFORE_RECOVERY_EXPOSURE` | Orphan cleanup precedes the recovery-complete marker during mount. | `CLOSED` |
| `BEFORE_ORPHAN_REGISTRY_REMOVAL` | Registry removal and inode free share one final journal handle, although removal is earlier in C statement order. | `CLOSED_WITH_TRANSACTIONAL_EQUIVALENCE` |

## Open adapter obligations

- Normalize orphan-file slots and the legacy chain into one canonical role
  without pretending they are one physical table.
- Select zero-link deletion; exclude linked truncate records.
- Bind journal-handle identity and commit outcome, not only call order.
- Preserve failure behavior where `ext4_orphan_del(NULL, inode)` cleans only
  the in-memory list; this does not prove persistent settlement
  (`orphan.c:259-265`).
- Carry filesystem/inode/allocation epoch for instance identity.

## Phase 1 decision

Object, relation, lifecycle and authority correspondence are source-supported.
Deadline correspondence closes only with the explicit transaction-scoped
interpretation above. Under that interpretation, ext4 is `APPLICABLE` as the
independent validation side of OIDS Phase 2. Replay, proof closure and a source
adapter remain open.
