# Manual Bug Candidates To Verify

These are the candidates we manually promoted from DeepSeek output for
follow-up verification. They are still not final confirmed bugs until each item
is checked against current upstream code, patch history, and, when possible,
fault-injection or image-based reproduction.

## Summary

| Group | Function | JSONL Lines | Current Verification Note |
|---|---|---:|---|
| FC-INODE | `ext4_fc_replay_inode` | 10-14 | Strong in v6.8; latest tree appears to have `out_brelse` and `return ret`, so check as fixed/duplicate. |
| FC-ADD | `ext4_fc_replay_add_range` | 15-18 | Submitted. |
| FC-DEL | `ext4_fc_replay_del_range` | 27-29 | Submitted. |
| ORPHAN | `ext4_init_orphan_info` | 103-105 | Submitted/fixed-looking in latest tree via `loaded++` cleanup count. |
| XATTR-EXTRA | `ext4_expand_extra_isize_ea` | 140 | Still suspicious in latest tree: stale `-ENOSPC` can survive a retry that reaches `shift:`. |

## Candidates

| ID | JSONL Line | task_id | Function | Type | Confidence | Suspected Issue | Verification Status |
|---|---:|---|---|---|---|---|---|
| FC-INODE-01 | 10 | `llm_review_e99672f2009b` | `ext4_fc_replay_inode` | `error_swallowed` | high | `ext4_fc_record_modified_inode()` error is swallowed. | duplicate/fixed |
| FC-INODE-02 | 11 | `llm_review_41b034187f74` | `ext4_fc_replay_inode` | `error_swallowed` | high | `ext4_get_fc_inode_loc()` error is swallowed. | duplicate/fixed |
| FC-INODE-03 | 12 | `llm_review_265190733128` | `ext4_fc_replay_inode` | `error_swallowed` | high | `ext4_handle_dirty_metadata()` error is swallowed; also related to `iloc.bh` not being released on this path. | duplicate/fixed |
| FC-INODE-04 | 13 | `llm_review_d50479b0e5bd` | `ext4_fc_replay_inode` | `error_swallowed` | high | `sync_dirty_buffer()` error is swallowed; also related to `iloc.bh` not being released on this path. | duplicate/fixed |
| FC-INODE-05 | 14 | `llm_review_60ab69805414` | `ext4_fc_replay_inode` | `error_swallowed` | high | `ext4_mark_inode_used()` error is swallowed; also related to `iloc.bh` not being released on this path. | duplicate/fixed |
| FC-ADD-01 | 15 | `llm_review_dbbcfe37c464` | `ext4_fc_replay_add_range` | `error_swallowed` | medium | `ext4_fc_record_modified_inode()` error is swallowed. | submitted |
| FC-ADD-02 | 16 | `llm_review_0bee7caf6376` | `ext4_fc_replay_add_range` | `error_swallowed` | high | `ext4_map_blocks()` negative error is swallowed. | submitted |
| FC-ADD-03 | 17 | `llm_review_63c4fa28d90e` | `ext4_fc_replay_add_range` | `error_swallowed` | high | Multiple replay error paths reach `out:` and return success. | submitted |
| FC-ADD-04 | 18 | `llm_review_cc57e01ef056` | `ext4_fc_replay_add_range` | `error_swallowed` | high | `ext4_map_blocks()`, `ext4_find_extent()`, or `ext4_ext_insert_extent()` errors are swallowed. | submitted |
| FC-DEL-01 | 27 | `llm_review_7fb6f5389cec` | `ext4_fc_replay_del_range` | `error_swallowed` | medium | `ext4_fc_record_modified_inode()` error is swallowed. | submitted |
| FC-DEL-02 | 28 | `llm_review_ffec52cad42c` | `ext4_fc_replay_del_range` | `error_swallowed` | medium | `ext4_map_blocks()` negative error is swallowed. | submitted |
| FC-DEL-03 | 29 | `llm_review_9c191269f23a` | `ext4_fc_replay_del_range` | `error_swallowed` | high | `ext4_ext_remove_space()` error is swallowed after replay-side block bitmap updates may already have occurred. | submitted |
| ORPHAN-01 | 103 | `llm_review_81b21364332d` | `ext4_init_orphan_info` | `missing_cleanup` | high | Current `ob_bh` leaks on bad magic/checksum paths. | submitted |
| ORPHAN-02 | 104 | `llm_review_65d848d5f1fd` | `ext4_init_orphan_info` | `missing_cleanup` | high | Bad magic path does not release current `ob_bh`. | submitted |
| ORPHAN-03 | 105 | `llm_review_f3e8e44a00d3` | `ext4_init_orphan_info` | `missing_cleanup` | high | Bad checksum path does not release current `ob_bh`. | submitted |
| XATTR-EXTRA-01 | 140 | `llm_review_167d182b60aa` | `ext4_expand_extra_isize_ea` | `error_swallowed` | high | A stale `-ENOSPC` from `ext4_xattr_make_inode_space()` can survive `goto retry`; if the retry reaches `shift:` directly, `i_extra_isize` is updated but the function can still return the old error. | pending |

## Lower-Priority Or Rejected DeepSeek True Candidates

| JSONL Line | Function | Status | Note |
|---:|---|---|---|
| 50 | `ext4_bread` | likely false positive | `put_bh(bh)` is effectively the buffer-head reference drop used by `brelse()`; no separate cleanup seems missing. |
| 66, 69 | `ext4_mb_init` | false positive | Latest code's `out:` frees `s_mb_offsets` and `s_mb_maxs`. |
| 111 | `ext4_fill_flex_info` | likely false positive | The caller treats `0` as flex-info initialization failure and converts it to `-ENOMEM`; this is a boolean-style helper. |
| 123, 126, 130, 132, 133 | `ext4_xattr_block_set` | likely false positive | Cleanup reaches `kfree(s->base)` unless `s->base` aliases the existing block buffer (`bs->bh->b_data`), where it is not owned. |

## Verification Checklist

- Check whether the issue still exists in `/root/bug_submit/linux`.
- Check whether the issue is already fixed in upstream or stable history.
- Confirm the intended return-value convention from the direct caller.
- Identify whether the error path can be reached under fault injection.
- Decide final status: `confirmed`, `submitted`, `duplicate/fixed`, `false_positive`, or `needs_more_evidence`.

## Source Files

- DeepSeek reviews: `/root/se_eod/outputs/deepseek_reviews.jsonl`
- Filtered DeepSeek true candidates: `/root/se_eod/outputs/deepseek_true_candidates.jsonl`
- v6.8 sparse source: `/root/se_eod/linux-v6.8-fs/fs/ext4/`
- Latest source under review: `/root/bug_submit/linux/fs/ext4/`
