# Btrfs DeepSeek True-Candidate Static Audit

Input: `outputs/btrfs/deepseek_true_candidates.jsonl` (`32` records).

This is a source-level triage pass, not upstream confirmation. I classify a record as:

- `likely_true`: local source evidence supports a real cleanup/error-path issue.
- `uncertain`: plausible, but needs deeper cross-function or reachability validation.
- `false_positive`: DeepSeek/static model missed wrapper cleanup, ownership transfer, caller-owned contract, or intentional return semantics.

## Summary

```text
likely_true: 4 groups / 7 records
uncertain: 2 groups / 3 records
false_positive: 15 groups / 22 records
```

## Likely True

### 1. `fs/btrfs/zoned.c::btrfs_load_block_group_zone_info` lines 1586, 1602, 1607, 1643

Records: tasks `241`, `242`, `243`, `244`.

`zone_info` is allocated at line 1572 and `active` at line 1578. The common `out:` label starts at line 1641, but immediately checks `non SINGLE data profiles without RST` and can return `-EINVAL` at line 1648 before the normal cleanup at lines 1680-1682:

```c
out:
        if ((map->type & BTRFS_BLOCK_GROUP_DATA) &&
            (map->type & BTRFS_BLOCK_GROUP_PROFILE_MASK) &&
            !fs_info->stripe_root) {
                ...
                return -EINVAL;
        }
...
        bitmap_free(active);
        kfree(zone_info);
        btrfs_free_chunk_map(map);
```

This looks like a real early-return cleanup bug if that condition can be true after `active` / `zone_info` / `map` allocation. Needs reachability check for zoned mode and RST feature constraints.

### 2. `fs/btrfs/space-info.c::create_space_info` line 252

Record: task `201`.

`space_info` is allocated at line 232. If `btrfs_sysfs_add_space_info_type()` fails at line 251, the function returns `ret` at line 253 without freeing `space_info` and before adding it to `info->space_info` at line 255.

This is a strong memory-leak candidate unless `btrfs_sysfs_add_space_info_type()` takes ownership even on failure, which would be unusual and should be checked.

### 3. `fs/btrfs/relocation.c::__add_reloc_root` line 648

Record: task `184`.

`node` is allocated at line 637. If `rb_simple_insert()` returns an existing node at line 648, the function returns `-EEXIST` at line 652 without `kfree(node)`.

This looks like a real leak on the duplicate-key error path. The caller has `ASSERT(err != -EEXIST)` in one path, so reachability may be considered impossible, but the local cleanup is still missing for the defensive error branch.

## Uncertain / Needs Deeper Validation

### 4. `fs/btrfs/relocation.c::btrfs_recover_relocation` line 4387

Records: tasks `189`, `190`.

The code assigns `fs_root->reloc_root = btrfs_grab_root(reloc_root)` at line 4382. If `btrfs_commit_transaction(trans)` fails at line 4386, control goes to `out_unset` without the normal `clean_dirty_subvols(rc)` path. `free_reloc_control(rc)` cleans `rc->reloc_roots`, but it is not obvious that it drops every `fs_root->reloc_root` reference created before the commit failure.

This is plausible, but needs a dedicated cross-function refcount trace through `clean_dirty_subvols()`, `free_reloc_control()`, root radix cleanup, and `BTRFS_FS_ERROR` handling.

### 5. `fs/btrfs/ctree.c::btrfs_next_old_leaf` line 4966

Record: task `32`.

The code writes `path->nodes[level] = next` and `path->locks[level] = BTRFS_READ_LOCK` before the nowait `btrfs_try_tree_read_lock(next)` succeeds. On try-lock failure, it goes to `done`, where `unlock_up(path, 0, 1, 0, NULL)` may interpret the path state as locked.

This needs path-state semantics review. It may be a real state bug, but the cleanup behavior depends on `unlock_up()` skip-level logic and path invariants.

## False Positives

### 6. `fs/btrfs/backref.c::resolve_indirect_refs` line 807

Record: task `8`.

DeepSeek claimed `free_leaf_list(parents)` does not free `parents`. Source says otherwise: `free_leaf_list()` iterates inode-list aux data and then calls `ulist_free(ulist)` at lines 707-717. This is wrapper cleanup.

### 7. `fs/btrfs/ctree.c::btrfs_search_old_slot` line 2326

Record: task `26`.

`btrfs_tree_mod_log_rewind()` is called with the input buffer read-locked. Its comment at `tree-mod-log.c:905-910` explicitly says NULL/error cases release the input lock and decrement the refcount. The missing `btrfs_tree_read_unlock(b)` is handled by the callee.

### 8. `fs/btrfs/disk-io.c::open_ctree` line 3484

Record: task `58`.

`subpage_info` is assigned to `fs_info->subpage_info`. `btrfs_free_fs_info()` frees it at `disk-io.c:1291`; mount failure paths eventually free `fs_info` via superblock/fs-context cleanup. This is ownership transfer to `fs_info`, not a local leak.

### 9. `fs/btrfs/extent-tree.c::btrfs_lock_cluster` line 3622

Record: task `71`.

The function has `__acquires(&cluster->refill_lock)` annotation and returns with the lock intentionally held. The caller releases `last_ptr->refill_lock`, e.g. around line 3688 and release paths. This is caller-owned lock contract.

### 10. `fs/btrfs/extent-tree.c::walk_up_proc` lines 5735, 5740

Records: tasks `76`, `77`.

The lock is represented in `path->locks[level]`; callers like `walk_up_tree()` release path-held locks after `walk_up_proc()` succeeds, and outer paths use `btrfs_free_path(path)` / path cleanup. This is path-owned lock state, not necessarily a function-local leak.

### 11. `fs/btrfs/extent-tree.c::btrfs_drop_snapshot` line 5936

Record: task `83`.

DeepSeek missed the label cleanup: `out_end_trans` calls `btrfs_end_transaction_throttle(trans)` at line 6075, then `out_free` calls `btrfs_free_path(path)` at line 6078, which releases path-held locks.

### 12. `fs/btrfs/extent_io.c::__extent_writepage` line 1476

Record: task `94`.

`writepage_delalloc()` explicitly documents that return `1` means I/O has already started and the page is already unlocked. `__extent_writepage_io()` return `1` similarly follows requeue/unlock semantics. This is intentional special return semantics, not swallowed cleanup.

### 13. `fs/btrfs/file.c::btrfs_replace_file_extents` line 2382

Record: task `103`.

`out_trans` handles the transaction: if `ret` is nonzero, it calls `btrfs_end_transaction(trans)` at lines 2582-2584. DeepSeek missed label cleanup.

### 14. `fs/btrfs/file.c::find_desired_extent` line 3659

Record: task `115`.

`private` is assigned to `file->private_data` at line 3499 and released by `btrfs_release_file()` at lines 1710-1718. This is ownership transfer to file lifetime.

### 15. `fs/btrfs/free-space-cache.c::__load_free_space_cache` line 764

Record: task `118`.

Returning `0` from failed cache lookup is consistent with the caller's cache-loading semantics: cache load failure is downgraded to rebuilding/clearing the free-space cache. The outer `load_free_space_cache()` treats negative cache state as nonfatal and logs rebuild behavior.

### 16. `fs/btrfs/free-space-cache.c::insert_into_bitmap` line 2418

Record: task `119`.

`insert_into_bitmap()` is called under `ctl->tree_lock`; the helper temporarily drops and reacquires the lock around allocation. The `out:` label frees `info` and returns while the caller continues to own/release the lock. This is caller-owned lock contract.

### 17. `fs/btrfs/free-space-cache.c::__btrfs_add_free_space` lines 2657, 2659

Records: tasks `120`, `122`, `123`.

The relevant `info` object is passed into `insert_into_bitmap()`. That helper frees `info` on its own `out:` path. The static model lacks callee-consumes-argument semantics here.

### 18. `fs/btrfs/free-space-cache.c::btrfs_alloc_from_cluster` line 3285

Record: task `125`.

This looks like intentional API semantics: offset `0` is used as failure/no-allocation sentinel. DeepSeek's claim that offset 0 can be valid may be theoretically interesting, but Btrfs logical block-group starts are not enough to call this a bug without proving zero is reachable as a valid allocation here.

### 19. `fs/btrfs/inode.c::btrfs_create_new_inode` lines 6319, 6397, 6416

Records: tasks `136`, `137`, `138`, `139`.

`btrfs_grab_root()` stores the root reference in `BTRFS_I(inode)->root`. On discard, `discard_new_inode()` drives inode cleanup; `btrfs_destroy_inode()` eventually calls `btrfs_put_root(inode->root)` at line 8664. This is inode-owned root reference, not a local missing `btrfs_put_root()`.

### 20. `fs/btrfs/lzo.c::lzo_decompress_bio` line 411

Record: task `144`.

`btrfs_decompress_buf2page()` documents return `0` for all needed contents copied and `>0` to continue decompressing. It does not return negative errors. Treating nonzero as continue is intentional.

### 21. `fs/btrfs/qgroup.c::btrfs_read_qgroup_config` lines 557, 561

Records: tasks `155`, `157`.

`add_qgroup_rb()` explicitly documents that ownership of `prealloc` is transferred to the callee. `add_relation_rb()` / `__add_relation_rb()` either attaches `list` to qgroup lists or frees it on missing qgroup. These are ownership-transfer false positives.

## Modeling Rules To Add

- `free_leaf_list(x)` releases `ulist` plus aux inode lists.
- `btrfs_tree_mod_log_rewind(fs_info, path, eb, time_seq)` releases/unlocks input `eb` on NULL/fresh-buffer paths and returns a read-locked buffer on success.
- `btrfs_lock_cluster()` is annotated `__acquires`; returned lock is caller-owned.
- `insert_into_bitmap(ctl, info)` may consume/free `info`; `ctl->tree_lock` is caller-owned.
- `add_qgroup_rb()` and `add_relation_rb()` consume their preallocated argument.
- Assignments to `file->private_data`, `fs_info->subpage_info`, and `BTRFS_I(inode)->root` are ownership transfers to object lifecycle cleanup.
- `btrfs_free_path(path)` releases path-held tree locks; path lock state in `path->locks[]` should not be treated as a plain local lock.
- `writepage_delalloc()` / `__extent_writepage_io()` return `1` with page already unlocked/requeued.
- `btrfs_decompress_buf2page()` returns `0` or positive continue status, not negative errors.
