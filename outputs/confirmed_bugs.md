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
| 6 | btrfs | `__add_reloc_root()` | `mapping_node` leak on duplicate insert | patch v2 submitted; reviewer reply received | `[PATCH v2] btrfs: free mapping node on duplicate reloc root insert` |
| 7 | btrfs | `btrfs_recover_relocation()` | missing `reloc_root` cleanup on recovery failure path | QEMU fault-injection confirmed under condition; patch submitted | `[PATCH] btrfs: drop recovered reloc root refs on recovery failure`, `outputs/linux-v6.8/btrfs/recover_relocation_qemu_report.md` |
| 8 | xfs | `xfs_rtcopy_summary()` | swallowed summary-copy error | source-level confirmed in v6.8; fixed in later mainline | v6.8 returns `0` from `out:`; current mainline returns `error` |
| 9 | ext4 | `ext4_dx_add_entry()` | `bh2` `buffer_head` leak | source-level confirmed in v6.8; fixed in later mainline | v6.8 htree split error paths omitted `brelse(bh2)`; later code adds it |
| 10 | ext4 | `ext4_ext_shift_extents()` | `ext4_ext_path` leak | source-level confirmed in v6.14; fixed in latest mainline | latest mainline sends `!extent` to `out:` and releases `path` |
| 11 | F2FS | `f2fs_rename()` with `RENAME_WHITEOUT` | `f2fs_filename` crypto / casefold buffer leak | source-level confirmed in v6.14; fixed in latest mainline | latest mainline calls `f2fs_free_filename(&fname)` after whiteout creation |
| 12 | XFS | `xfs_qm_quotacheck_dqadjust()` | dquot reference leak | source-level confirmed in v6.14; fixed in latest mainline | latest mainline routes attach-buffer failure through `xfs_qm_dqrele(dqp)` |
| 13 | XFS | `xfs_rtginode_ensure()` | swallowed `xfs_rtginode_load()` error | patch submitted | `[PATCH] xfs: propagate errors from xfs_rtginode_load`, linux-xfs thread shown in local submission screenshot |
| 14 | F2FS | `f2fs_get_new_data_folio()` | `ifolio` leak on `f2fs_reserve_block()` failure | patch submitted | `[PATCH v2] f2fs: fix ifolio leak in f2fs_get_new_data_folio`, Message-ID `<20260713061601.712-1-3497809730@qq.com>` |
| 15 | F2FS | `find_in_level()` | `dentry_folio` leak on `find_in_block()` error | patch submitted | `[PATCH] f2fs: fix dentry folio leak in find_in_level`, Message-ID `<20260713063633.555-1-3497809730@qq.com>` |
| 16 | F2FS | `f2fs_move_inline_dirents()` | `ifolio` leak on `f2fs_reserve_block()` failure | patch submitted | `[PATCH] f2fs: fix ifolio leak in f2fs_move_inline_dirents`, Message-ID `<20260713064043.1837-1-3497809730@qq.com>` |
| 17 | btrfs | `reserve_chunk_space()` | zoned positive-success return skips chunk metadata reservation | patch v2 submitted; Reviewed-by received | `[PATCH v2] btrfs: zoned: fix missing chunk metadata reservation`, lore Message-ID `tencent_7498732A1B9E13C552CFF1101E377288C407@qq.com` |
| 18 | btrfs | `btrfs_init_new_device()` | failed sprout device left on transaction update list | patch submitted | `[PATCH 1/3] btrfs: detach failed sprout device from transaction update list`, lore Message-ID `tencent_3DBB43FCDD4420406266A92678AE15833C09@qq.com` |
| 19 | btrfs | `btrfs_init_new_device()` | active device pointers left on failed sprout device | patch submitted | `[PATCH 2/3] btrfs: restore active device pointers after failed sprout`, lore Message-ID `tencent_3A451E4FED103C3756888298712A161E2607@qq.com` |
| 20 | btrfs | `btrfs_init_new_device()` | sprout fs_devices state not rolled back after device-add failure | patch submitted | `[PATCH 3/3] btrfs: roll back sprout setup after device add failure`, lore Message-ID `tencent_AA3028EA782A8414BAC141E8C40C52FDF30A@qq.com` |

As of 2026-07-14, 6 of the 20 confirmed bug records are already fixed
upstream.  The other 14 records are covered by submitted patches or patch
series, but are not recorded here as upstream merged.  Bugs #1 and #2 share
one ext4 patch, and bugs #18-#20 are covered by one 3-patch btrfs sprout
rollback series.

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

Status: confirmed and patch submitted.  Latest mainline HEAD checked on
2026-07-13 (`a13c140cc289c0b7b3770bce5b3ad42ab35074aa`) still used the
`for (i--; i >= 0; i--)` cleanup pattern, so the submitted fix did not appear
merged in that tree.

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
- Mailing-list evidence checked on 2026-07-13 shows a reply from Qu Wenruo to
  `[PATCH v2] btrfs: free mapping node on duplicate reloc root insert`.

Status: confirmed source-level bug candidate and patch v2 submitted.  A
reviewer reply has been received; this is not yet recorded as upstream merged.

### 7. `fs/btrfs/relocation.c::btrfs_recover_relocation`

Bug type: missing cleanup of `fs_root->reloc_root` on a recovery failure path.

During relocation recovery, the function assigns:

```c
fs_root->reloc_root = btrfs_grab_root(reloc_root);
```

This happens before the first recovery `btrfs_commit_transaction(trans)`. If
that recovery path fails and jumps to `out_unset` before the normal
`clean_dirty_subvols(rc)` path, `btrfs_recover_relocation()` itself does not
locally clear `fs_root->reloc_root` or drop the grabbed relocation-root
reference.

The later root teardown path only drops `root->reloc_root` under the
`BTRFS_FS_ERROR(fs_info)` branch. That means cleanup currently depends on the
failure setting `BTRFS_FS_ERROR`; a caller-visible recovery failure that does
not set that flag can leave the relocation-root reference attached.

Evidence:

- QEMU/fault-injection report:
  `outputs/linux-v6.8/btrfs/recover_relocation_qemu_report.md`
- Follow-up fix patch:
  `/root/bug_submit/linux-btrfs-recover-relocation`
  - commit `08f1ccb98abb`
  - patch file `/tmp/btrfs-recover-relocation-cleanup-v1/0001-btrfs-drop-recovered-reloc-root-refs-on-recovery-fai.patch`
- Mailing-list evidence checked on 2026-07-13 shows the submitted patch from
  Guanghui Yang with subject
  `[PATCH] btrfs: drop recovered reloc root refs on recovery failure`.
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
condition, with a follow-up fix locally validated and submitted upstream.  It
is not yet recorded as upstream merged.

### 17. `fs/btrfs/block-group.c::reserve_chunk_space`

Bug type: positive zoned activation success return skips chunk metadata
reservation.

In Linux 6.14, `reserve_chunk_space()` reuses the local variable `ret` for both
system chunk creation state and the return value of
`btrfs_zoned_activate_one_bg()`:

```c
bg = btrfs_create_chunk(trans, flags);
if (IS_ERR(bg)) {
        ret = PTR_ERR(bg);
} else {
        ret = btrfs_zoned_activate_one_bg(fs_info, info, true);
        if (ret < 0)
                return;

        btrfs_chunk_alloc_add_chunk_item(trans, bg);
}
...
if (!ret) {
        ret = btrfs_block_rsv_add(fs_info, &fs_info->chunk_block_rsv,
                                  bytes, BTRFS_RESERVE_NO_FLUSH);
        if (!ret)
                trans->chunk_bytes_reserved += bytes;
}
```

`btrfs_zoned_activate_one_bg()` returns `1` when it successfully activates a
block group.  That is a successful result, but the positive value remains in
`ret`, so the later `if (!ret)` condition is false and
`btrfs_block_rsv_add()` is skipped.

This is not a block group lifetime bug and not a missing
`btrfs_put_block_group()` case.  The newly created block group is already
inserted into btrfs structures and queued on `trans->new_bgs`.  The real issue
is that a positive successful zoned activation result leaks into the later
reservation condition.

Reproducer evidence:

- Host-managed zoned `null_blk` device with `zone_size=256MiB` and
  `zone_max_active=8`.
- Instrumented Linux 6.14 `reserve_chunk_space()` before the fix:

```text
BTRFS_REPRO zoned_activate ret=1 before_add_chunk_item chunk_reserved=0
BTRFS_REPRO skip chunk_block_rsv_add ret=1 chunk_reserved=0
```

- After normalizing the non-negative activation result back to `0`:

```c
ret = btrfs_zoned_activate_one_bg(fs_info, info, true);
if (ret < 0)
        return;
ret = 0;
```

the same workload showed:

```text
BTRFS_REPRO zoned_activate ret=1 before_add_chunk_item chunk_reserved=0
BTRFS_REPRO chunk_block_rsv_add ret=0 chunk_reserved=393216
```

Suggested fix direction: do not let a positive success return from
`btrfs_zoned_activate_one_bg()` control the later chunk block reservation.
Either reset `ret` to `0` after the `ret < 0` check, or use a separate local
variable for the zoned activation result.

Submitted patch:

- Subject: `[PATCH v2] btrfs: zoned: fix missing chunk metadata reservation`
- Lore:
  `https://lore.kernel.org/linux-btrfs/tencent_7498732A1B9E13C552CFF1101E377288C407@qq.com/`
- v1 Lore:
  `https://lore.kernel.org/linux-btrfs/tencent_860054603C488A379E3D21126EA610D63108@qq.com/`
- Review:
  Johannes Thumshirn provided
  `Reviewed-by: Johannes Thumshirn <johannes.thumshirn@wdc.com>`.
- v2 testing:
  targeted zoned `null_blk` reproducer with a 4G host-managed device,
  256MiB zones and `zone_max_active=8`; `btrfs_zoned_activate_one_bg()`
  returned `1` and `btrfs_block_rsv_add()` reserved 393216 bytes.  xfstests
  was not run because the reproduction host did not have an xfstests tree.

Status: confirmed by targeted zoned-device reproduction on Linux 6.14 and
patch v2 submitted.  Not recorded as upstream merged.

### 18. `fs/btrfs/volumes.c::btrfs_init_new_device`

Bug type: failed sprout device remains linked on the transaction device update
list.

When creating the first writable chunks for a sprout filesystem,
`btrfs_create_chunk()` can add the newly allocated device to the current
transaction's device update list through `device->post_commit_list`.  If the
subsequent system chunk creation fails, `btrfs_init_new_device()` aborts the
transaction and releases the device while `post_commit_list` is still linked.

The observed failure was:

```text
WARN_ON(!list_empty(&device->post_commit_list))
```

in `btrfs_free_device()`.  This is not a `meta_bg` local reference leak; the
pending block group is drained from `trans->new_bgs` by the transaction abort
path.

Submitted patch:

- Subject: `[PATCH 1/3] btrfs: detach failed sprout device from transaction update list`
- Lore:
  `https://lore.kernel.org/linux-btrfs/tencent_3DBB43FCDD4420406266A92678AE15833C09@qq.com/`

Status: confirmed by targeted seed/sprout fault injection and patch submitted
as part of `[PATCH 0/3] btrfs: fix failed sprout device add rollback`.  Not
recorded as upstream merged.

### 19. `fs/btrfs/volumes.c::btrfs_init_new_device`

Bug type: active device pointers left on a failed sprout device.

During sprout setup, `btrfs_init_new_device()` switches `latest_dev` and
possibly `s_bdev` from the seed device to the new sprout device before the
first writable chunks are fully created.  If the later chunk creation or sprout
setup path fails, the old error path releases the new device without switching
those active device pointers back to the seed device.

The reproduced failure reached `btrfs_show_devname()` with a stale/freed active
device pointer and triggered a NULL pointer dereference.

Submitted patch:

- Subject: `[PATCH 2/3] btrfs: restore active device pointers after failed sprout`
- Lore:
  `https://lore.kernel.org/linux-btrfs/tencent_3A451E4FED103C3756888298712A161E2607@qq.com/`

Status: confirmed by targeted seed/sprout fault injection and patch submitted
as part of `[PATCH 0/3] btrfs: fix failed sprout device add rollback`.  Not
recorded as upstream merged.

### 20. `fs/btrfs/volumes.c::btrfs_init_new_device`

Bug type: sprout `fs_devices` state is not rolled back after device-add
failure.

`btrfs_setup_sprout()` moves the seed devices out of `fs_info->fs_devices`,
clears the seeding state and installs a new fsid for the sprout filesystem.
If creating the first writable chunks fails afterwards, the old error path
removes the failed new device but leaves the mounted filesystem in the
partially initialized sprout `fs_devices` state.  The new sprout container then
has no open devices.

The reproduced failure triggered:

```text
assertion failed: nr_devices, in fs/btrfs/super.c
kernel BUG at fs/btrfs/super.c
```

The final fault-injection run after the 3-patch series showed:

```text
volumes.c post_commit_list WARN      0
free_fs_devices WARN                0
btrfs_show_devname                  0
BUG: kernel NULL pointer dereference 0
assertion failed: nr_devices        0
kernel BUG at fs/btrfs/super.c      0
REPRO_DONE
```

Submitted patch:

- Subject: `[PATCH 3/3] btrfs: roll back sprout setup after device add failure`
- Lore:
  `https://lore.kernel.org/linux-btrfs/tencent_AA3028EA782A8414BAC141E8C40C52FDF30A@qq.com/`

Status: confirmed by targeted seed/sprout fault injection and patch submitted
as part of `[PATCH 0/3] btrfs: fix failed sprout device add rollback`.  Not
recorded as upstream merged.

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

### 13. `fs/xfs/xfs_rtalloc.c::xfs_rtginode_ensure`

Bug type: swallowed error from `xfs_rtginode_load()`.

`xfs_rtginode_ensure()` is supposed to load an rtgroup metadata inode, creating
it only when `xfs_rtginode_load()` reports `-ENOENT`.  The old code treated
every error other than `-ENOENT` as success:

```c
error = xfs_rtginode_load(rtg, type, tp);
xfs_trans_cancel(tp);

if (error != -ENOENT)
        return 0;
return xfs_rtginode_create(rtg, type, true);
```

This suppresses real load failures such as allocation errors or metadata
corruption errors, allowing the realtime growfs path to continue as though the
inode had been loaded.

Suggested / submitted fix shape:

```c
if (error != -ENOENT)
        return error;
return xfs_rtginode_create(rtg, type, true);
```

Evidence:

- Source-level confirmation in local Linux v6.14 sparse tree:
  `linux-sources/linux-v6.14-fs/fs/xfs/xfs_rtalloc.c`.
- Latest mainline HEAD checked on 2026-07-13
  (`a13c140cc289c0b7b3770bce5b3ad42ab35074aa`) still had the same swallowed
  error shape.
- Submitted patch evidence from local linux-xfs archive screenshot:
  - Subject: `[PATCH] xfs: propagate errors from xfs_rtginode_load`
  - From: Guanghui Yang `<3497809730@qq.com>`
  - To: `linux-xfs@vger.kernel.org`
  - Cc: Carlos Maiolino, Darrick J. Wong, Christoph Hellwig,
    `linux-kernel@vger.kernel.org`, `stable@vger.kernel.org`
  - Reported fixing target: commit `aa897e0bed0f ("xfs: support creating per-RTG files in growfs")`

Status: confirmed and patch submitted.  Not recorded as fixed in latest
mainline at the time of the 2026-07-13 recheck.

## F2FS

### 14. `fs/f2fs/data.c::f2fs_get_new_data_folio`

Bug type: `ifolio` reference leak on `f2fs_reserve_block()` failure.

`f2fs_get_new_data_folio()` documents that `ifolio` is only set by
`make_empty_dir()`, and that `ifolio` should be released by this function on
any error.  The allocation-failure path already releases `ifolio`, but the
`f2fs_reserve_block()` failure path only released the newly grabbed data folio.

The submitted v2 fix releases `ifolio` only if `dn.inode_folio` is still set,
so it avoids a double put when `f2fs_reserve_block()` has already cleared the
dnode.

Evidence:

- Source-level confirmation in latest mainline sparse checkout based on
  `a13c140cc289c0b7b3770bce5b3ad42ab35074aa`.
- Patch v1 Message-ID: `<20260713055959.1865-1-3497809730@qq.com>`
- Patch v2 Message-ID: `<20260713061601.712-1-3497809730@qq.com>`
- Patch subject: `[PATCH v2] f2fs: fix ifolio leak in f2fs_get_new_data_folio`

Status: confirmed and patch v2 submitted.

### 15. `fs/f2fs/dir.c::find_in_level`

Bug type: `dentry_folio` reference leak on `find_in_block()` error.

`find_in_level()` obtains `dentry_folio` from `f2fs_find_data_folio()` before
calling `find_in_block()`.  If `find_in_block()` returns an error, the function
stores the error in `*res_folio` and breaks out of the loop without dropping
the successfully acquired `dentry_folio`.

Evidence:

- Source-level confirmation in latest mainline sparse checkout based on
  `a13c140cc289c0b7b3770bce5b3ad42ab35074aa`.
- Patch Message-ID: `<20260713063633.555-1-3497809730@qq.com>`
- Patch subject: `[PATCH] f2fs: fix dentry folio leak in find_in_level`

Status: confirmed and patch submitted.

### 16. `fs/f2fs/inline.c::f2fs_move_inline_dirents`

Bug type: `ifolio` reference leak on `f2fs_reserve_block()` failure.

`f2fs_move_inline_dirents()` documents that the caller grabs `ifolio`, and that
the function should release it on any error.  The cache-folio allocation
failure path already releases `ifolio`, but the `f2fs_reserve_block()` failure
path only released the newly grabbed folio through the shared `out` label.

The submitted fix releases `ifolio` on this error path when `dn.inode_folio`
is still set, matching the safer conditional-release shape used for
`f2fs_get_new_data_folio()`.

Evidence:

- Source-level confirmation in latest mainline sparse checkout based on
  `a13c140cc289c0b7b3770bce5b3ad42ab35074aa`.
- Patch Message-ID: `<20260713064043.1837-1-3497809730@qq.com>`
- Patch subject: `[PATCH] f2fs: fix ifolio leak in f2fs_move_inline_dirents`

Status: confirmed and patch submitted.

## ext4

### 9. `fs/ext4/namei.c::ext4_dx_add_entry`

Bug type: missing `buffer_head` release on three journal error paths.

Linux v6.8 acquires `bh2` through `ext4_append()` and can jump to
`journal_error` at lines 2570, 2582, and 2602 without calling `brelse(bh2)`.
The first two paths occur before `bh2` can be swapped into `frame->bh`; the
third path also leaks on the branch where the swap condition is false.

Linux v7.1 adds `brelse(bh2)` immediately before the corresponding jumps at
lines 2559, 2573, and 2595. SE-EOD records these mappings in
`configs/ext4_historical_fixes.json`; all three candidates are ranked as
`E3_HISTORICAL_FIX_CONFIRMED` and retain only dynamic validation as missing
evidence.

Status: source-level confirmed historical Linux v6.8 bug, fixed in the Linux
v7.1 source snapshot. The exact fixing commit has not yet been identified.

## Latest-mainline fixed bugs from Linux v6.14 ext4 / XFS / F2FS audit

Date: 2026-07-13

Baseline under recheck:

- Candidate baseline: local Linux v6.14 filesystem sources under
  `linux-sources/linux-v6.14-fs`.
- Latest upstream checked: Torvalds mainline HEAD
  `a13c140cc289c0b7b3770bce5b3ad42ab35074aa`.
- Scope: the source-level true bug clusters from the ext4, XFS, and F2FS
  154-candidate manual audit.

The following entries are source-level bugs from the v6.14 candidate audit that
are already fixed or structurally corrected in the latest mainline tree.  They
should be treated as validation / duplicate findings unless a fixing commit
still needs to be identified for historical tracking.

| Confirmed bug # | FS | Function | Bug type | Latest-mainline status | Evidence |
|---:|---|---|---|---|---|
| 10 | ext4 | `ext4_ext_shift_extents()` | `ext4_ext_path` leak on corrupted / unexpected extent path | fixed in latest mainline | Latest code sends the `!extent` path to `out:` and releases with `ext4_free_ext_path(path)` instead of returning directly. |
| 5 | ext4 | `ext4_fc_replay_inode()` | fast-commit replay error swallowed; earlier versions also leaked `iloc.bh` on error | fixed upstream / duplicate finding | Latest code releases `iloc.bh` at `out_brelse:` and returns `ret`; upstream fix recorded above as commit `ec0a7500d8ea`. Note: sibling `ext4_fc_replay_add_range()` and `ext4_fc_replay_del_range()` still return `0` from their shared `out:` labels in latest mainline, so they are not recorded here as fixed. |
| 9 | ext4 | `ext4_dx_add_entry()` | missing `brelse(bh2)` on htree split journal-error paths | fixed in latest mainline | Latest code adds `brelse(bh2)` before the relevant `goto journal_error` paths. |
| 12 | XFS | `xfs_qm_quotacheck_dqadjust()` | dquot reference leak after `xfs_dquot_attach_buf()` failure | fixed in latest mainline | Latest code routes the attach-buffer failure through `out_unlock`, then calls `xfs_qm_dqrele(dqp)`. |
| 8 | XFS | `xfs_rtcopy_summary()` | swallowed error while copying realtime summary metadata | fixed in latest mainline | Latest code returns `error` from the shared cleanup label instead of unconditionally returning `0`. |
| 11 | F2FS | `f2fs_rename()` with `RENAME_WHITEOUT` | `struct f2fs_filename` crypto / casefold buffer leak | fixed in latest mainline | Latest code calls `f2fs_free_filename(&fname)` immediately after `f2fs_create_whiteout()`. |

Items from the same v6.14 audit that still appear unfixed in latest mainline,
and therefore are not recorded in this fixed-bug table, are intentionally left
for separate confirmation before being promoted here.

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
