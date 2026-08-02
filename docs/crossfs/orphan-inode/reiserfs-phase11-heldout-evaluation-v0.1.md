# OIDS Phase 11 ReiserFS Post-COMMON Held-out Evaluation

## Temporal status

ReiserFS was selected and preregistered after the Phase 9 COMMON narrow freeze and the Phase 10 OCFS2 negative screening, and before any `fs/reiserfs` source was acquired or read. The preregistration locks the COMMON freeze, protocol, binding-independent checker, AcceptP and semantics, CFG frontend, Phase 9 and Phase 10 results, freeze-member bindings, and existing OIDS tests.

All six registered Linux v6.8 source paths exist. No post-reveal source-path amendment was required. The source acquisition manifest binds the evaluation to commit `e8f897f4afef0031fe618a8e94127a0934896aba` and to byte hashes for `inode.c`, `journal.c`, `namei.c`, `reiserfs.h`, `stree.c`, and `super.c`.

## Five-dimensional correspondence

| Dimension | Result | Source conclusion |
|---|---|---|
| object | `CLOSED` | `MAX_KEY_OBJECTID` reserves the persistent save-link keyspace and `i_link_saved_unlink_mask` tracks accepted cleanup responsibility. |
| relation | `CLOSED` | the save-link key carries the inode object id and its body carries the original directory id. |
| lifecycle | `CLOSED` | last-link unlink, final eviction, journal replay, and synchronous mount scanning expose the required stages. |
| authority | `CLOSED` | `reiserfs_evict_inode()` and `finish_unfinished()`/`iput()` are explicit live and recovery deletion authorities. |
| deadline | `CLOSED` | `finish_unfinished()` runs synchronously before the successful RW `reiserfs_fill_super()` return. |

The applicability decision is therefore `APPLICABLE`. A predicate such as "save-link insertion succeeded" is outcome-dependent and cannot be added after source reveal to exclude the failing executions.

## Registration

The successful `reiserfs_unlink()` path calls `drop_nlink()`, removes the namespace item with `reiserfs_cut_from_item()`, calls `add_save_link()`, and only then ends the journal transaction. This normal path closes persistent registration before commit.

The failure partition does not conform. `add_save_link()` is a `void` function. When `reiserfs_insert_item()` returns `-ENOSPC`, it logs selectively and returns no error to `reiserfs_unlink()`. The unlink transaction can still reach `journal_end()` after namespace removal while no persistent save link exists. The replay closes this source witness as `VIOLATION_UNDER_LOADED_SPEC / OIDS-O1`.

## Settlement

On the successful final-eviction path, `reiserfs_evict_inode()` calls `reiserfs_delete_object()`, commits that transaction with `journal_end()`, and then calls `remove_save_link()`. The latter opens a second transaction, deletes the persistent save-link item, and commits it. The distinct transaction identities are preserved in replay rather than falsely requiring atomic co-settlement.

`remove_save_link()` returns its `journal_end()` result, but `reiserfs_evict_inode()` intentionally ignores it. A removal failure therefore cannot prove settlement and is retained as `INCOMPLETE_UNDER_LOADED_SPEC`; it is not mislabeled as a direct OIDS violation without an exposure event.

## Recovery

The normal RW mount sequence is synchronous:

```text
journal_init()
-> journal_read()
-> d_make_root()
-> finish_unfinished()
   -> enumerate MAX_KEY_OBJECTID save links
   -> iput() drives final eviction
-> successful reiserfs_fill_super() return
```

This closes the normal recovery deadline before exposure. The error partition nevertheless violates the frozen protocol: `finish_unfinished()` returns its cleanup status, but `reiserfs_fill_super()` discards that result and continues to a successful return. The corresponding replay is `VIOLATION_UNDER_LOADED_SPEC / OIDS-O3`.

## Decision

Phase 11 closes a valid blind held-out evaluation and produces a nonconformance result:

```text
applicability = APPLICABLE
conformance_decision = NON_CONFORMANT_HELDOUT
phase11_screening_closed = true
candidate_conformant = false
common_heldout_validated = false
```

Both successful profiles conform under the unchanged loaded specification, while the registered failure partitions remain in scope and defeat universal held-out conformance. The Phase 9 COMMON narrow freeze remains byte-for-byte unchanged.

