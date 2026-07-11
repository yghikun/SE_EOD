# SE-EOD Review Feedback Report

This report compares SE-EOD ranking before and after source-aware review-feedback scoring. Review labels are triage signals, not candidate deletion rules or upstream confirmation.

## Summary

- baseline_candidates: 38
- feedback_candidates: 38
- review_label_records: 40
- review_feedback_applied: 5
- E2_API_PROTOCOL_SUPPORTED: 9
- exception_hints: 2

## Top-N Verdict Mix

- baseline top 20: {'unlabeled': 20}
- review-feedback top 20: {'unlabeled': 15, 'true_candidate': 5}

## Review Verdicts

- `true_candidate`: 5

## Review Confidence

- `medium`: 3
- `high`: 2

## Labels By Reviewer

- `codex_static_review`: 40

## Labels By Review Source

- `codex_static_review`: 40

## Applied By Review Source

- `codex_static_review`: 5

## Confirmed Exception Types

- `None`: 5

## Next Actions

- `upstream_history_check`: 3
- `runtime_validation`: 2

## Validation Hints

- `journal`: 3
- `EIO`: 2

## Score Adjustment By Source

- `codex_static_review`: count=5, sum=+95, avg=+19.0, min=+15, max=+25

## Average Rank Change

- `true_candidate`: count=5, avg_before=23.8, avg_after=12.8, avg_delta=-11.0

## Top 20 After Review Feedback

1. score=80 base_rank=1 adj=0 review=unlabeled source=unlabeled level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup fs/ext4/inode.c::ext4_truncate:4151
2. score=80 base_rank=2 adj=0 review=unlabeled source=unlabeled level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup fs/ext4/orphan.c::ext4_init_orphan_info:605
3. score=78 base_rank=20 adj=25 review=true_candidate source=codex_static_review level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup fs/ext4/orphan.c::ext4_init_orphan_info:610
4. score=78 base_rank=21 adj=25 review=true_candidate source=codex_static_review level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup fs/ext4/orphan.c::ext4_init_orphan_info:615
5. score=70 base_rank=3 adj=0 review=unlabeled source=unlabeled level=E1_LLM_TRUE_CANDIDATE severity=P1 type=error_swallowed fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1745
6. score=70 base_rank=4 adj=0 review=unlabeled source=unlabeled level=E1_LLM_TRUE_CANDIDATE severity=P1 type=error_swallowed fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1764
7. score=70 base_rank=5 adj=0 review=unlabeled source=unlabeled level=E1_LLM_TRUE_CANDIDATE severity=P1 type=error_swallowed fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1767
8. score=70 base_rank=6 adj=0 review=unlabeled source=unlabeled level=E1_LLM_TRUE_CANDIDATE severity=P1 type=error_swallowed fs/ext4/fast_commit.c::ext4_fc_replay_del_range:1862
9. score=70 base_rank=7 adj=0 review=unlabeled source=unlabeled level=E1_LLM_TRUE_CANDIDATE severity=P1 type=error_swallowed fs/ext4/fast_commit.c::ext4_fc_replay_del_range:1873
10. score=70 base_rank=8 adj=0 review=unlabeled source=unlabeled level=E1_LLM_TRUE_CANDIDATE severity=P1 type=error_swallowed fs/ext4/fast_commit.c::ext4_fc_replay_del_range:1890
11. score=70 base_rank=9 adj=0 review=unlabeled source=unlabeled level=E1_LLM_TRUE_CANDIDATE severity=P1 type=error_swallowed fs/ext4/fast_commit.c::ext4_fc_replay_inode:1542
12. score=70 base_rank=10 adj=0 review=unlabeled source=unlabeled level=E1_LLM_TRUE_CANDIDATE severity=P1 type=error_swallowed fs/ext4/fast_commit.c::ext4_fc_replay_inode:1548
13. score=70 base_rank=11 adj=0 review=unlabeled source=unlabeled level=E1_LLM_TRUE_CANDIDATE severity=P1 type=error_swallowed fs/ext4/fast_commit.c::ext4_fc_replay_inode:1574
14. score=70 base_rank=12 adj=0 review=unlabeled source=unlabeled level=E1_LLM_TRUE_CANDIDATE severity=P1 type=error_swallowed fs/ext4/fast_commit.c::ext4_fc_replay_inode:1577
15. score=70 base_rank=13 adj=0 review=unlabeled source=unlabeled level=E1_LLM_TRUE_CANDIDATE severity=P1 type=error_swallowed fs/ext4/fast_commit.c::ext4_fc_replay_inode:1580
16. score=70 base_rank=14 adj=0 review=unlabeled source=unlabeled level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=partial_cleanup fs/ext4/inode.c::ext4_truncate:4151
17. score=70 base_rank=15 adj=0 review=unlabeled source=unlabeled level=E1_LLM_TRUE_CANDIDATE severity=P1 type=error_swallowed fs/ext4/super.c::ext4_fill_flex_info:3205
18. score=65 base_rank=25 adj=15 review=true_candidate source=codex_static_review level=E0_STATIC_RULE_ONLY severity=P1 type=error_swallowed fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1784
19. score=65 base_rank=26 adj=15 review=true_candidate source=codex_static_review level=E0_STATIC_RULE_ONLY severity=P1 type=error_swallowed fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1798
20. score=65 base_rank=27 adj=15 review=true_candidate source=codex_static_review level=E0_STATIC_RULE_ONLY severity=P1 type=error_swallowed fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1819

## Largest Rank Changes

### Demoted

- +5: 19 -> 24 review=unlabeled source=unlabeled adj=0 fs/ext4/symlink.c::ext4_get_link:95
- +5: 16 -> 21 review=unlabeled source=unlabeled adj=0 fs/ext4/mballoc.c::ext4_mb_add_groupinfo:3341
- +5: 18 -> 23 review=unlabeled source=unlabeled adj=0 fs/ext4/orphan.c::ext4_init_orphan_info:601
- +5: 17 -> 22 review=unlabeled source=unlabeled adj=0 fs/ext4/namei.c::__ext4_read_dirblock:154
- +3: 22 -> 25 review=unlabeled source=unlabeled adj=0 fs/ext4/extents.c::ext4_ext_replay_set_iblocks:6032
- +3: 23 -> 26 review=unlabeled source=unlabeled adj=0 fs/ext4/extents.c::ext4_fill_es_cache_info:2224
- +3: 24 -> 27 review=unlabeled source=unlabeled adj=0 fs/ext4/extents.c::skip_hole:5981
- +2: 7 -> 9 review=unlabeled source=unlabeled adj=0 fs/ext4/fast_commit.c::ext4_fc_replay_del_range:1873
- +2: 9 -> 11 review=unlabeled source=unlabeled adj=0 fs/ext4/fast_commit.c::ext4_fc_replay_inode:1542
- +2: 3 -> 5 review=unlabeled source=unlabeled adj=0 fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1745
- +2: 12 -> 14 review=unlabeled source=unlabeled adj=0 fs/ext4/fast_commit.c::ext4_fc_replay_inode:1577
- +2: 14 -> 16 review=unlabeled source=unlabeled adj=0 fs/ext4/inode.c::ext4_truncate:4151
- +2: 8 -> 10 review=unlabeled source=unlabeled adj=0 fs/ext4/fast_commit.c::ext4_fc_replay_del_range:1890
- +2: 6 -> 8 review=unlabeled source=unlabeled adj=0 fs/ext4/fast_commit.c::ext4_fc_replay_del_range:1862
- +2: 5 -> 7 review=unlabeled source=unlabeled adj=0 fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1767
- +2: 13 -> 15 review=unlabeled source=unlabeled adj=0 fs/ext4/fast_commit.c::ext4_fc_replay_inode:1580
- +2: 10 -> 12 review=unlabeled source=unlabeled adj=0 fs/ext4/fast_commit.c::ext4_fc_replay_inode:1548
- +2: 11 -> 13 review=unlabeled source=unlabeled adj=0 fs/ext4/fast_commit.c::ext4_fc_replay_inode:1574
- +2: 15 -> 17 review=unlabeled source=unlabeled adj=0 fs/ext4/super.c::ext4_fill_flex_info:3205
- +2: 4 -> 6 review=unlabeled source=unlabeled adj=0 fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1764

### Promoted

- -17: 20 -> 3 review=true_candidate source=codex_static_review adj=25 fs/ext4/orphan.c::ext4_init_orphan_info:610
- -17: 21 -> 4 review=true_candidate source=codex_static_review adj=25 fs/ext4/orphan.c::ext4_init_orphan_info:615
- -7: 26 -> 19 review=true_candidate source=codex_static_review adj=15 fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1798
- -7: 25 -> 18 review=true_candidate source=codex_static_review adj=15 fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1784
- -7: 27 -> 20 review=true_candidate source=codex_static_review adj=15 fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1819
- 0: 31 -> 31 review=unlabeled source=unlabeled adj=0 fs/ext4/inode.c::ext4_iomap_begin:3365
- 0: 32 -> 32 review=unlabeled source=unlabeled adj=0 fs/ext4/inode.c::ext4_write_begin:1147
- 0: 30 -> 30 review=unlabeled source=unlabeled adj=0 fs/ext4/inode.c::ext4_da_write_begin:2880
- 0: 28 -> 28 review=unlabeled source=unlabeled adj=0 fs/ext4/ialloc.c::find_group_orlov:484
- 0: 33 -> 33 review=unlabeled source=unlabeled adj=0 fs/ext4/mballoc.c::ext4_mb_seq_groups_show:3045
- 0: 2 -> 2 review=unlabeled source=unlabeled adj=0 fs/ext4/orphan.c::ext4_init_orphan_info:605
- 0: 38 -> 38 review=unlabeled source=unlabeled adj=0 fs/ext4/namei.c::ext4_lookup_entry:1766
- 0: 36 -> 36 review=unlabeled source=unlabeled adj=0 fs/ext4/inline.c::ext4_get_first_inline_block:1612
- 0: 1 -> 1 review=unlabeled source=unlabeled adj=0 fs/ext4/inode.c::ext4_truncate:4151
- 0: 35 -> 35 review=unlabeled source=unlabeled adj=0 fs/ext4/fast_commit.c::ext4_fc_reserve_space:738
- 0: 29 -> 29 review=unlabeled source=unlabeled adj=0 fs/ext4/inline.c::ext4_get_max_inline_size:115
- 0: 37 -> 37 review=unlabeled source=unlabeled adj=0 fs/ext4/namei.c::ext4_find_entry:1745
- 0: 34 -> 34 review=unlabeled source=unlabeled adj=0 fs/ext4/fast_commit.c::ext4_fc_reserve_space:708
- 2: 4 -> 6 review=unlabeled source=unlabeled adj=0 fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1764
- 2: 15 -> 17 review=unlabeled source=unlabeled adj=0 fs/ext4/super.c::ext4_fill_flex_info:3205
