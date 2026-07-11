# Confirmed Bugs

Date: 2026-07-11

This file records the ext4, btrfs, and XFS issues that we have checked beyond raw
static ranking.  "Confirmed" here means source-level confirmation plus either a
submitted patch, reproduction evidence, or targeted fault-injection evidence.
It does not mean upstream acceptance unless explicitly stated.

## Summary

| # | FS | Function | Bug type | Status | Evidence |
|---:|---|---|---|---|---|
| 1 | ext4 | `ext4_fc_replay_add_range()` | swallowed error | patch submitted | `/root/bug_submit/linux/0001-ext4-propagate-errors-from-fast-commit-range-replay.patch` |
| 2 | ext4 | `ext4_fc_replay_del_range()` | swallowed error | patch submitted | `/root/bug_submit/linux/0001-ext4-propagate-errors-from-fast-commit-range-replay.patch` |
| 3 | ext4 | `ext4_init_orphan_info()` | `buffer_head` leak | patch submitted | `/root/bug_submit/patches/orphan-v2/v2-0001-ext4-fix-buffer_head-leak-in-ext4_init_orphan_inf.patch` |
| 4 | ext4 | `ext4_expand_extra_isize_ea()` | stale error after successful retry | patch submitted / under review | `/root/bug_submit/patches/xattr-stale-error/0001-ext4-clear-error-before-retrying-inode-xattr-space-f.patch` |
| 5 | ext4 | `ext4_fc_replay_inode()` | `iloc.bh` leak plus swallowed error | already fixed upstream / duplicate finding | upstream commit `ec0a7500d8ea` |
| 6 | btrfs | `__add_reloc_root()` | `mapping_node` leak on duplicate insert | source-level confirmed | `fs/btrfs/relocation.c` duplicate `rb_simple_insert()` path |
| 7 | btrfs | `btrfs_recover_relocation()` | missing `reloc_root` cleanup on recovery failure path | QEMU fault-injection confirmed under condition | `outputs/linux-v6.8/btrfs/recover_relocation_qemu_report.md` |
| 8 | xfs | `xfs_rtcopy_summary()` | swallowed summary-copy error | source-level confirmed in v6.8; fixed in later mainline | v6.8 returns `0` from `out:`; current mainline returns `error` |

## ext4

### 1. `fs/ext4/fast_commit.c::ext4_fc_replay_add_range`

Bug type: swallowed error during fast-commit replay.

`ext4_fc_replay_add_range()` used a common `out:` path that returned `0` even
after internal failures.  This can hide errors from:

- `ext4_fc_record_modified_inode()`
- `ext4_map_blocks()`
- `ext4_find_extent()`
- `ext4_ext_insert_extent()`
- `ext4_ext_replay_update_ex()`

Impact: a failed `ADD_RANGE` replay can be treated as successful, allowing fast
commit recovery to continue after a partially failed range operation.

Evidence:

- Patch: `/root/bug_submit/linux/0001-ext4-propagate-errors-from-fast-commit-range-replay.patch`
- Patch subject: `ext4: propagate errors from fast commit range replay`
- Current patch branch seen locally: `/root/bug_submit/linux`, commit
  `33b4ecd48982 ext4: propagate errors from fast commit range replay`

Status: confirmed and patch submitted.

### 2. `fs/ext4/fast_commit.c::ext4_fc_replay_del_range`

Bug type: swallowed error during fast-commit replay.

`ext4_fc_replay_del_range()` also returned `0` from its common `out:` path even
after internal failures.  This hides errors from:

- `ext4_fc_record_modified_inode()`
- `ext4_map_blocks()`
- `ext4_ext_remove_space()`

Impact: this is especially risky for delete replay because the code may already
have updated replay-side block bitmap state before `ext4_ext_remove_space()`
fails.  If the error is swallowed, recovery may continue from a partially
applied delete-range operation.

Evidence:

- Patch: `/root/bug_submit/linux/0001-ext4-propagate-errors-from-fast-commit-range-replay.patch`
- Same submitted patch as the `ADD_RANGE` fix.

Status: confirmed and patch submitted.

### 3. `fs/ext4/orphan.c::ext4_init_orphan_info`

Bug type: `buffer_head` reference leak.

`ext4_init_orphan_info()` reads orphan-file blocks with `ext4_bread()` and
stores the returned `buffer_head` in `oi->of_binfo[i].ob_bh`.  If the current
block passes the read but then fails magic or checksum validation, the function
jumps to `out_free`.

The old cleanup loop started from `i - 1`, so it released previously loaded
buffers but skipped the current buffer at index `i`.  That leaks the
`buffer_head` reference obtained by `ext4_bread()` on the bad magic and bad
checksum paths.

Evidence:

- Patch v2: `/root/bug_submit/patches/orphan-v2/v2-0001-ext4-fix-buffer_head-leak-in-ext4_init_orphan_inf.patch`
- Patch subject: `ext4: fix buffer_head leak in ext4_init_orphan_info`
- The submitted fix tracks a `loaded` count and releases exactly the buffers
  that were successfully read.

Status: confirmed and patch submitted.  Newer code inspected during review
looked fixed by the `loaded++` cleanup-count approach.

### 4. `fs/ext4/xattr.c::ext4_expand_extra_isize_ea`

Bug type: stale error returned after successful fallback retry.

`ext4_xattr_make_inode_space()` can return `-ENOSPC`.  In the fallback path,
`ext4_expand_extra_isize_ea()` retries the expansion using
`s_min_extra_isize`.  If that retry succeeds by finding enough ibody free
space, control can jump directly to `shift:` and update `i_extra_isize`.

Before the fix, the old `-ENOSPC` was still stored in `error`, so the function
could update the inode extra-isize but still return `-ENOSPC` to the caller.

Evidence:

- Patch: `/root/bug_submit/patches/xattr-stale-error/0001-ext4-clear-error-before-retrying-inode-xattr-space-f.patch`
- Patch subject: `ext4: clear error before retrying inode xattr space fallback`
- Reply/explanation: `/root/bug_submit/replies/xattr-sashiko-reply.txt`
- Reproduction note from the patch: an ext4 image with 1 KiB blocks, project
  quota support, 256-byte inodes, and `min_extra_isize` / `want_extra_isize`
  set to 32 reduced `FS_IOC_FSSETXATTR` failures from 802 to 86 after clearing
  the stale error before retry.

Status: confirmed and patch submitted / under review.

## Already Fixed / Duplicate Findings

These are bugs that our scan/review also found, but a newer upstream tree
already contains a fix from someone else.  Keep them in this file because they
are useful validation examples for SE-EOD: the tool rediscovered real bugs, but
they should not be submitted again as new reports.

### 5. `fs/ext4/fast_commit.c::ext4_fc_replay_inode`

Bug type: `iloc.bh` leak on error paths plus swallowed error return.

In Linux 6.8, `ext4_fc_replay_inode()` calls `ext4_get_fc_inode_loc()` and
obtains `iloc.bh`.  Several later failures jumped directly to `out`, where the
function dropped the inode and optionally flushed the block device, but did not
release `iloc.bh`:

- `ext4_handle_dirty_metadata(NULL, NULL, iloc.bh)` failure
- `sync_dirty_buffer(iloc.bh)` failure
- `ext4_mark_inode_used(sb, ino)` failure
- `ext4_iget(sb, ino, EXT4_IGET_NORMAL)` failure after the on-disk inode update

The same old `out:` path also ended with `return 0`, so these failures could be
reported as successful replay.

Evidence from our scan:

- `outputs/linux-v6.8/ext4/manual_bug_candidates_to_verify.md` listed `FC-INODE` as a strong
  v6.8 candidate and then marked it as fixed/duplicate after latest-tree
  review.
- `outputs/linux-v6.8/ext4/ranked_candidates.jsonl` and v1.2 reports contain five
  `ext4_fc_replay_inode` `error_swallowed` candidates from the v6.8 scan.

Upstream fix:

- Commit: `ec0a7500d8eace5b4f305fa0c594dd148f0e8d29`
- Subject: `ext4: fix iloc.bh leak in ext4_fc_replay_inode() error paths`
- Author: Baokun Li `<libaokun@linux.alibaba.com>`
- Commit date: 2026-03-27
- Reported-by: Joseph Qi `<joseph.qi@linux.alibaba.com>`
- Link: `https://patch.msgid.link/20260323060836.3452660-1-libaokun@linux.alibaba.com`

Fix shape observed in the newer local tree:

```c
out_brelse:
        brelse(iloc.bh);
out:
        iput(inode);
        if (!ret)
                blkdev_issue_flush(sb->s_bdev);

        return ret;
```

Status: already fixed upstream.  Treat this as a duplicate / validation hit,
not as a new bug to report.

## btrfs

### 6. `fs/btrfs/relocation.c::__add_reloc_root`

Bug type: memory leak on duplicate relocation-root mapping insert.

`__add_reloc_root()` allocates a `mapping_node` and then inserts it into
`rc->reloc_root_tree`:

```c
node = kmalloc_obj(*node, GFP_NOFS);
...
rb_node = rb_simple_insert(&rc->reloc_root_tree.rb_root, &node->simple_node);
...
if (rb_node) {
        btrfs_err(...);
        return -EEXIST;
}
```

If `rb_simple_insert()` reports a duplicate, the function returns `-EEXIST`
without freeing the newly allocated `node`.

Impact: this leaks the freshly allocated mapping node on the duplicate-key
error branch.  Some callers assert that `-EEXIST` should not happen, so the
natural reachability may be limited, but the defensive error path is still
missing the local cleanup.

Evidence:

- Source-level confirmed in Linux 6.8 sparse tree:
  `linux-sources/linux-v6.8-fs/fs/btrfs/relocation.c`
- Source-level confirmed in the newer local tree:
  `/root/bug_submit/linux/fs/btrfs/relocation.c`
- The newer local tree still has the same duplicate-return shape in
  `__add_reloc_root(struct btrfs_root *root, struct reloc_control *rc)`.
- Earlier local validation included an ASan/LSan minimal reproduction showing a
  32-byte leak for this duplicate-insert path.

Status: confirmed source-level bug candidate.  Not yet upstream-submitted in
the checked workspace.

### 7. `fs/btrfs/relocation.c::btrfs_recover_relocation`

Bug type: missing cleanup of `fs_root->reloc_root` on a recovery failure path.

During relocation recovery, the function assigns:

```c
fs_root->reloc_root = btrfs_grab_root(reloc_root);
```

This happens before the first recovery `btrfs_commit_transaction(trans)`.  If
that recovery path fails and jumps to `out_unset` before the normal
`clean_dirty_subvols(rc)` path, `btrfs_recover_relocation()` itself does not
locally clear `fs_root->reloc_root` or drop the grabbed relocation-root
reference.

The later root teardown path only drops `root->reloc_root` under the
`BTRFS_FS_ERROR(fs_info)` branch.  That means cleanup currently depends on the
failure setting `BTRFS_FS_ERROR`; a caller-visible recovery failure that does
not set that flag can leave the relocation-root reference attached.

Evidence:

- QEMU/fault-injection report:
  `outputs/linux-v6.8/btrfs/recover_relocation_qemu_report.md`
- Test target: Linux 6.8 Btrfs recovery.
- Pending relocation image contained 25 `TREE_RELOC ROOT_ITEM` records.
- Normal recovery succeeded.
- Injected `recover_noabort` failure:
  - `phase=out_unset_error roots_with_reloc_root=25 fs_error=0`
  - mount failed
  - `drop_and_free_fs_root` logged roots with `reloc_refs=1`
  - no `dropping reloc_root` cleanup lines appeared
- Injected `recover_abort` failure:
  - `fs_error=-5`
  - cleanup emitted `dropping reloc_root` lines

Final classification:

```text
Confirmed by QEMU/fault-injection for recovery failures that do not set
BTRFS_FS_ERROR.  Not proven for every natural btrfs_commit_transaction()
failure.
```

Suggested fix direction: track the filesystem roots whose `reloc_root` is
assigned during `btrfs_recover_relocation()`, and explicitly clear/drop those
references on errors before `clean_dirty_subvols()`, independent of
`BTRFS_FS_ERROR`.

Status: confirmed cleanup-defect candidate under the tested fault-injection
condition.  Not yet upstream-submitted in the checked workspace.

## XFS

### 8. `fs/xfs/xfs_rtalloc.c::xfs_rtcopy_summary`

Bug type: swallowed error while copying realtime summary metadata.

In Linux v6.8, `xfs_rtcopy_summary()` records failures from all three summary
operations and jumps to a shared cleanup label:

```c
error = xfs_rtget_summary(oargs, log, bbno, &sum);
if (error)
        goto out;
...
error = xfs_rtmodify_summary(oargs, log, bbno, -sum);
if (error)
        goto out;
error = xfs_rtmodify_summary(nargs, log, bbno, sum);
if (error)
        goto out;
...
out:
        xfs_rtbuf_cache_relse(oargs);
        return 0;
```

The caller, `xfs_growfs_rt()`, checks the result of `xfs_rtcopy_summary()` and
would cancel its transaction on an error.  The unconditional `return 0` makes
that handling unreachable after a failed summary read or modification, so the
grow operation can continue after a partially completed metadata copy.

Evidence:

- Linux v6.8 source: `linux-sources/linux-v6.8-fs/fs/xfs/xfs_rtalloc.c`, lines 101-118.
- SE-EOD rediscovery: `candidate_343e5e0b9add`,
  `candidate_cfcfe8b9d353`, and `candidate_40ab97ad7725` in
  `outputs/linux-v6.8/xfs/deepseek_true_candidates.jsonl`.
- Later mainline source changes the cleanup return to `return error;`, matching
  the caller's existing `if (error) goto error_cancel;` handling.

Status: source-level confirmed historical Linux v6.8 bug and already fixed in
later upstream mainline.  The exact fixing commit has not been recorded in this
workspace, so this is a validation/duplicate finding rather than a new patch
submission.

## Not Included As Confirmed Bugs

The following candidates should not be presented as confirmed bugs yet:

- `fs/btrfs/zoned.c::btrfs_load_block_group_zone_info`: likely true from local
  cleanup structure, but still needs a reachability check for the zoned/RST
  condition after `active`, `zone_info`, and `map` allocation.
- `fs/btrfs/space-info.c::create_space_info`: strong memory-leak candidate, but
  still needs confirmation that `btrfs_sysfs_add_space_info_type()` does not
  take ownership on failure.
- `fs/btrfs/ctree.c::btrfs_next_old_leaf`: uncertain / likely false positive
  after path-state review; do not count as confirmed.
