# M11 Fresh Queue Initial Source Triage

This is a development source-triage note, not a confirmed-bug ledger and not a
benchmark label set.

Source inputs:

- `outputs/mocc-discovery-v2/linux-v6.8-fresh-review.json`
- `outputs/mocc-discovery-v2/linux-v6.8-fresh-review-queue.json`
- `linux-sources/linux-v6.8-fs/fs`
- `outputs/mocc-discovery-v2/ext4-fc-helper-fault-validation.json`
- `outputs/mocc-discovery-v2/ext4-fc-helper-fault-validation.md`
- `outputs/mocc-discovery-v2/ext4-fc-helper-error-propagation-rfc.patch`

## Current Summary

```text
fresh_review_queue_entries         4
failure_return_mismatch            2
mutation_failure_cleanup           2
high-confidence candidate families 1
confirmed bugs promoted            0
```

Current queue entries:

- `ext4_ext_replay_set_iblocks` / `failure_return_mismatch`
- `ext4_ext_clear_bb` / `failure_return_mismatch`
- `btrfs_reloc_post_snapshot` / `mutation_failure_cleanup`
- `clean_dirty_subvols` / `mutation_failure_cleanup`

## Rule Tightening Applied

This pass reduced the fresh review queue from 10 entries to 4 entries.

The removed entries were matcher noise, not confirmed safe code:

- boolean stop helpers such as `dir_emit()` no longer count as fallible errno
  helpers;
- temporary state updates that are restored before the failure guard no longer
  count as open metadata effects;
- mutation evidence must be CFG-reachable from the selected fallible call, so
  early-return branch mutations do not pair with later calls;
- Protocol B broad discovery now requires operation-specific topology anchors
  such as `reloc_root`, `dev_list`, and `dev_alloc_list`.

Regression coverage was added for all four shapes.

## High-Value Finding Candidate

### ext4 fast-commit replay helper error swallowing

Functions:

- `fs/ext4/extents.c::ext4_ext_replay_set_iblocks`
- `fs/ext4/extents.c::ext4_ext_clear_bb`

Fresh queue entries:

- `ext4_ext_replay_set_iblocks` via `failure_return_mismatch`
- `ext4_ext_clear_bb` via `failure_return_mismatch`

Source observation in Linux v6.8:

- `ext4_ext_replay_set_iblocks()` propagates the first `ext4_find_extent()`
  failure, but later failure paths from `ext4_map_blocks()`, `skip_hole()`, and
  `ext4_find_extent()` use `break` or `goto out`.
- The shared `out:` label still assigns `inode->i_blocks`, dirties the inode,
  and returns `0`.
- `ext4_ext_clear_bb()` similarly breaks out of its block-map loop on
  `ext4_map_blocks()` failure and returns `0`.
- `fs/ext4/fast_commit.c::ext4_fc_replay_inode()` calls both helpers without
  checking their return values.

Relationship to existing confirmed records:

- `confirmed_bugs.md` already contains #5 for
  `fast_commit.c::ext4_fc_replay_inode()` swallowed error / `iloc.bh` cleanup.
- This fresh finding is best treated as a helper-level residual in the same
  fast-commit replay error-propagation family, not as an unrelated new bug.
- It must not be added to `outputs/confirmed_bugs.md` until a patch or real
  fault-injection pass validates the behavior.

Validation status:

- Local fault-model artifacts are saved in
  `ext4-fc-helper-fault-validation.md` and
  `ext4-fc-helper-fault-validation.json`.
- The original modeled caller returns success for all injected helper-failure
  scenarios because the helper return values are ignored.
- The local RFC sketch is saved as
  `ext4-fc-helper-error-propagation-rfc.patch`.

Initial verdict: likely true source-level finding candidate, medium confidence,
pending dynamic validation.

## Remaining Btrfs Review Items

### `btrfs_reloc_post_snapshot`

Current signal:

- `rc->merging_rsv_size += rc->nodes_relocated`
- `btrfs_block_rsv_migrate(...)`
- `if (ret) return ret`

Initial interpretation:

- This is not a clean Protocol B topology rollback witness: the state update is
  reservation/accounting-like, while the configured protocol is about topology
  effects such as `reloc_root` pointer ownership.
- It may be worth revisiting under a future accounting/reservation pattern, but
  the current queue evidence is not enough to call it a high-confidence bug.

Initial verdict: uncertain rule-feedback lead, not promoted.

### `clean_dirty_subvols`

Current signal:

- `root->reloc_root = NULL`
- `btrfs_drop_snapshot(reloc_root, 0, 1)`
- on failure, `btrfs_put_root(reloc_root)` and preserve the first negative
  return in `ret`

Initial interpretation:

- This function is itself a cleanup handler.
- The source comment explicitly describes the failure case: if
  `btrfs_drop_snapshot()` fails, the function drops its held reference itself.
- It returns the negative error instead of reporting success.

Initial verdict: likely false positive / cleanup-handler noise.

## Follow-Up Checklist

1. Keep `outputs/confirmed_bugs.md` unchanged until dynamic validation closes a
   candidate.
2. Use the ext4 helper family as the next dynamic validation target.
3. If Btrfs remains interesting, model `btrfs_reloc_post_snapshot()` under a
   reservation/accounting rule instead of Protocol B topology rollback.
4. Continue treating fresh queue entries as review leads, not benchmark labels.
