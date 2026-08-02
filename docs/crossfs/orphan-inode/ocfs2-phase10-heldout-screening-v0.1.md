# OIDS Phase 10 OCFS2 Post-COMMON Held-out Screening

## Temporal status

OCFS2 was selected and preregistered after the Phase 9 COMMON narrow freeze and before any `fs/ocfs2` source was read. The preregistration locks the Phase 9 manifest and summary, COMMON scope, qualification catalog, protocol, three freeze-member bindings, checker/AcceptP semantics, CFG frontend, scope logic, and existing tests.

The registered `orphan_dir.c` and `recovery.c` paths do not exist at Linux v6.14. A post-reveal amendment maps their responsibilities to `namei.c` and `journal.c` and adds `ocfs2_fs.h` for persistent structure definitions. It does not modify the candidate, source revision, decision partition, closure gates, or any semantic lock.

## Five-dimensional correspondence

| Dimension | Result | Source conclusion |
|---|---|---|
| object | `CLOSED` | `OCFS2_ORPHANED_FL`, `ORPHAN_DIR_SYSTEM_INODE`, and `i_orphaned_slot` define a persistent, slot-scoped orphan object. |
| relation | `CLOSED` | `ocfs2_orphan_add()` inserts the inode block identity as an orphan-directory entry and records the responsible slot. |
| lifecycle | `CLOSED` | last-link unlink, final eviction, journal replay, and orphan-directory scanning expose the required lifecycle stages. |
| authority | `CLOSED` | cluster-exclusive `ocfs2_delete_inode()` and the recovery worker are explicit deletion authorities. |
| deadline | `BLOCKED` | recovery orphan cleanup is asynchronous after root construction and is not joined before mount exposure. |

The controlled applicability decision is therefore `NON_APPLICABLE / DEADLINE_NOT_ALIGNED`, not `UNRESOLVED`.

## Registration

`ocfs2_unlink()` prepares the slot orphan directory before starting the JBD2 handle. Within one handle it deletes the namespace entry, drops the final link, calls `ocfs2_orphan_add()`, and only then calls `ocfs2_commit_trans()`. `ocfs2_orphan_add()` inserts the orphan dirent, sets `OCFS2_ORPHANED_FL`, records `i_orphaned_slot`, and journals both the orphan directory and dinode.

This closes the successful live registration profile: persistent cleanup responsibility is accepted before the namespace transition can commit.

## Settlement

`ocfs2_wipe_inode()` truncates inode-owned state and dispatches `ocfs2_remove_inode()`. In one delete-inode handle, `ocfs2_remove_inode()` calls `ocfs2_orphan_del()`, stamps deletion time and clears valid/orphan flags, calls `ocfs2_free_dinode()`, and commits the handle. Orphan retirement and terminal dinode deallocation are therefore atomically co-settled, which satisfies the locked OIDS-O2 alternative.

## Recovery boundary

Journal replay itself is synchronous in `ocfs2_check_volume()`, but orphan cleanup is a second recovery half:

```text
ocfs2_fill_super()
-> d_make_root()
-> sb->s_root = root
-> ocfs2_complete_mount_recovery()
   -> ocfs2_queue_recovery_completion()
-> VOLUME_MOUNTED / VOLUME_MOUNTED_QUOTAS
-> return from fill_super

workqueue: ocfs2_complete_recovery()
-> ocfs2_wait_on_quotas()
-> ocfs2_recover_orphans()
-> iput() drives final deletion
```

There is no workqueue flush or recovery join between queueing and the return from `ocfs2_fill_super()`. Consequently, successful RW mount does not prove orphan settlement before normal exposure on all paths. The replay is retained as `INCOMPLETE_UNDER_LOADED_SPEC`; it is not promoted to conformant recovery.

## Decision

Phase 10 closes the blind held-out screening procedure but does not close the COMMON held-out validation gate:

```text
applicability = NON_APPLICABLE
controlled_reason_code = DEADLINE_NOT_ALIGNED
phase10_screening_closed = true
no_post_freeze_semantic_modifications = true
common_heldout_validated = false
```

The Phase 9 COMMON narrow freeze remains valid and unchanged. A different unrevealed filesystem must be preregistered for the next held-out attempt.
