# SE-EOD v1.1 Validation Report

This report validates exception-aware protocol ranking without changing candidates.

## Summary

- total: 140

### Evidence Levels

- `E2_API_PROTOCOL_SUPPORTED`: 111
- `E0_STATIC_RULE_ONLY`: 15
- `E1_LLM_TRUE_CANDIDATE`: 14

### Candidate Types

- `missing_cleanup`: 96
- `error_swallowed`: 32
- `partial_cleanup`: 12

### Severity

- `P2`: 74
- `P1`: 66

### Has Exception Hints

- `False`: 103
- `True`: 37

### Protocols

- `memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree`: 60
- `lock.down_write.up_write`: 24
- `lock.down_read.up_read`: 24
- `buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse`: 10
- `lock.mutex_lock.unlock`: 3
- `journal.ext4_journal_start.stop`: 1

### Exception Hints

- `ownership_transferred`: 169
- `released_by_wrapper`: 1

## Acceptance Checklist

- all candidates retained in ranked output: True (140)
- E2_API_PROTOCOL_SUPPORTED candidates present: True (111)
- exception-hint candidates retained: True (37)
- score_explanation present: True (140/140)
- v1.1 evidence fields present: True (140/140)

## V1 vs V1.1 Rank Changes

### Dropped Most After Exception Hints

- +63: 44 -> 107 | score=45 exception=True | ('fs/ext4/namei.c', 'ext4_rename', 3888, 'missing_cleanup')
- +44: 51 -> 95 | score=53 exception=True | ('fs/ext4/xattr.c', 'ext4_xattr_block_set', 2122, 'missing_cleanup')
- +44: 50 -> 94 | score=53 exception=True | ('fs/ext4/xattr.c', 'ext4_xattr_block_set', 2086, 'missing_cleanup')
- +44: 47 -> 91 | score=53 exception=True | ('fs/ext4/orphan.c', 'ext4_init_orphan_info', 615, 'missing_cleanup')
- +44: 46 -> 90 | score=53 exception=True | ('fs/ext4/orphan.c', 'ext4_init_orphan_info', 610, 'missing_cleanup')
- +30: 79 -> 109 | score=33 exception=True | ('fs/ext4/inode.c', 'ext4_bread_batch', 931, 'missing_cleanup')
- +30: 78 -> 108 | score=33 exception=True | ('fs/ext4/inode.c', 'ext4_bread_batch', 923, 'missing_cleanup')
- +13: 101 -> 114 | score=33 exception=True | ('fs/ext4/super.c', 'parse_apply_sb_mount_options', 2536, 'partial_cleanup')
- +13: 100 -> 113 | score=33 exception=True | ('fs/ext4/super.c', 'parse_apply_sb_mount_options', 2536, 'missing_cleanup')
- +13: 99 -> 112 | score=33 exception=True | ('fs/ext4/super.c', 'parse_apply_sb_mount_options', 2532, 'partial_cleanup')
- +13: 98 -> 111 | score=33 exception=True | ('fs/ext4/super.c', 'parse_apply_sb_mount_options', 2532, 'missing_cleanup')
- +13: 97 -> 110 | score=33 exception=True | ('fs/ext4/resize.c', 'alloc_flex_gd', 245, 'missing_cleanup')
- +12: 103 -> 115 | score=33 exception=True | ('fs/ext4/sysfs.c', 'ext4_init_sysfs', 584, 'missing_cleanup')
- +11: 124 -> 135 | score=33 exception=True | ('fs/ext4/xattr.c', 'ext4_xattr_block_set', 2190, 'missing_cleanup')
- +11: 123 -> 134 | score=33 exception=True | ('fs/ext4/xattr.c', 'ext4_xattr_block_set', 2178, 'missing_cleanup')
- +11: 122 -> 133 | score=33 exception=True | ('fs/ext4/xattr.c', 'ext4_xattr_block_set', 2161, 'missing_cleanup')
- +11: 121 -> 132 | score=33 exception=True | ('fs/ext4/xattr.c', 'ext4_xattr_block_set', 2152, 'missing_cleanup')
- +11: 120 -> 131 | score=33 exception=True | ('fs/ext4/xattr.c', 'ext4_xattr_block_set', 2145, 'missing_cleanup')
- +11: 119 -> 130 | score=33 exception=True | ('fs/ext4/xattr.c', 'ext4_xattr_block_set', 2128, 'missing_cleanup')
- +11: 118 -> 129 | score=33 exception=True | ('fs/ext4/xattr.c', 'ext4_xattr_block_set', 2097, 'missing_cleanup')

### Increased Most

- -36: 125 -> 89 | score=53 exception=True | ('fs/ext4/inode.c', 'ext4_bread', 896, 'missing_cleanup')
- -29: 126 -> 97 | score=50 exception=False | ('fs/ext4/extents.c', 'ext4_ext_replay_set_iblocks', 6032, 'error_swallowed')
- -29: 127 -> 98 | score=50 exception=False | ('fs/ext4/extents.c', 'ext4_fill_es_cache_info', 2224, 'error_swallowed')
- -29: 128 -> 99 | score=50 exception=False | ('fs/ext4/extents.c', 'skip_hole', 5981, 'error_swallowed')
- -29: 129 -> 100 | score=50 exception=False | ('fs/ext4/extents_status.c', '__es_remove_extent', 1416, 'error_swallowed')
- -29: 130 -> 101 | score=50 exception=False | ('fs/ext4/ialloc.c', 'find_group_orlov', 484, 'error_swallowed')
- -29: 131 -> 102 | score=50 exception=False | ('fs/ext4/inline.c', 'ext4_get_max_inline_size', 115, 'error_swallowed')
- -29: 132 -> 103 | score=50 exception=False | ('fs/ext4/inode.c', 'ext4_da_write_begin', 2880, 'error_swallowed')
- -29: 133 -> 104 | score=50 exception=False | ('fs/ext4/inode.c', 'ext4_iomap_begin', 3365, 'error_swallowed')
- -29: 134 -> 105 | score=50 exception=False | ('fs/ext4/inode.c', 'ext4_write_begin', 1147, 'error_swallowed')
- -29: 135 -> 106 | score=50 exception=False | ('fs/ext4/mballoc.c', 'ext4_mb_seq_groups_show', 3045, 'error_swallowed')
- -16: 104 -> 88 | score=60 exception=False | ('fs/ext4/xattr.c', 'ext4_xattr_block_set', 2029, 'missing_cleanup')
- -15: 102 -> 87 | score=60 exception=False | ('fs/ext4/symlink.c', 'ext4_get_link', 95, 'missing_cleanup')
- -10: 80 -> 70 | score=60 exception=False | ('fs/ext4/mballoc-test.c', 'mbt_grp_ctx_init', 95, 'missing_cleanup')
- -10: 81 -> 71 | score=60 exception=False | ('fs/ext4/mballoc.c', 'ext4_mb_add_groupinfo', 3327, 'missing_cleanup')
- -10: 82 -> 72 | score=60 exception=False | ('fs/ext4/mballoc.c', 'ext4_mb_add_groupinfo', 3341, 'missing_cleanup')
- -10: 83 -> 73 | score=60 exception=False | ('fs/ext4/mballoc.c', 'ext4_mb_init', 3585, 'missing_cleanup')
- -10: 84 -> 74 | score=60 exception=False | ('fs/ext4/mballoc.c', 'ext4_mb_init', 3598, 'missing_cleanup')
- -10: 85 -> 75 | score=60 exception=False | ('fs/ext4/mballoc.c', 'ext4_mb_init', 3621, 'missing_cleanup')
- -10: 86 -> 76 | score=60 exception=False | ('fs/ext4/mballoc.c', 'ext4_mb_init', 3639, 'missing_cleanup')

## Top 20 Ranked Candidates

1. score=100 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=error_swallowed exception=False fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1784
   protocols: ['lock.down_write.up_write']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'error_swallowed final return 0 +20', 'journal or lock protocol violation without exception hints +20']

2. score=100 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=error_swallowed exception=False fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1798
   protocols: ['lock.down_write.up_write']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'error_swallowed final return 0 +20', 'journal or lock protocol violation without exception hints +20']

3. score=100 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=error_swallowed exception=False fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1819
   protocols: ['lock.down_write.up_write']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'error_swallowed final return 0 +20', 'journal or lock protocol violation without exception hints +20']

4. score=90 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/fast_commit.c::__track_dentry_update:446
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree', 'lock.mutex_lock.unlock']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20', 'buffer_head or memory protocol violation without exception hints +10']

5. score=90 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/fast_commit.c::__track_dentry_update:448
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree', 'lock.mutex_lock.unlock', 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20', 'buffer_head or memory protocol violation without exception hints +10']

6. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/fast_commit.c::__track_dentry_update:437
   protocols: ['lock.mutex_lock.unlock']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

7. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1784
   protocols: ['lock.down_write.up_write']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

8. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1789
   protocols: ['lock.down_write.up_write']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

9. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1789
   protocols: ['lock.down_write.up_write']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

10. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1798
   protocols: ['lock.down_write.up_write']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

11. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1819
   protocols: ['lock.down_write.up_write']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

12. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/indirect.c::ext4_ind_truncate_ensure_credits:744
   protocols: ['lock.down_write.up_write']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

13. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/indirect.c::ext4_ind_truncate_ensure_credits:746
   protocols: ['lock.down_write.up_write']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

14. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/indirect.c::ext4_ind_truncate_ensure_credits:750
   protocols: ['lock.down_write.up_write']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

15. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/inode.c::ext4_map_blocks:578
   protocols: ['lock.down_read.up_read']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

16. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/inode.c::ext4_map_blocks:580
   protocols: ['lock.down_read.up_read']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

17. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/inode.c::ext4_map_blocks:585
   protocols: ['lock.down_read.up_read']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

18. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/inode.c::ext4_map_blocks:595
   protocols: ['lock.down_read.up_read']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

19. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/inode.c::ext4_map_blocks:601
   protocols: ['lock.down_read.up_read']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

20. score=80 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=False fs/ext4/inode.c::ext4_map_blocks:637
   protocols: ['lock.down_write.up_write']
   score: ['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']

## Top 20 Exception-Hint Candidates

1. score=53 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/inode.c::ext4_bread:896
   protocols: ['buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse']
   score: ['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'released_by_wrapper', 'protocol_id': 'buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse', 'function': 'put_bh', 'resource_kind': 'buffer_head', 'confidence': 'high'}, {'type': 'ownership_transferred', 'resource_kind': 'buffer_head', 'resource_expr': 'bh', 'line': 892, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ext4_buffer_uptodate(bh)', 'protocol_id': 'buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse'}, {'type': 'ownership_transferred', 'resource_kind': 'buffer_head', 'resource_expr': 'bh', 'line': 895, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ext4_read_bh_lock(bh, REQ_META | REQ_PRIO, true)', 'protocol_id': 'buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse'}]

2. score=53 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/orphan.c::ext4_init_orphan_info:610
   protocols: ['buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse']
   score: ['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'buffer_head', 'resource_expr': 'ob_bh', 'line': 609, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ext4_orphan_block_tail(sb, oi->of_binfo[i].ob_bh)', 'protocol_id': 'buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse'}]

3. score=53 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/orphan.c::ext4_init_orphan_info:615
   protocols: ['buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse']
   score: ['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'buffer_head', 'resource_expr': 'ob_bh', 'line': 609, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ext4_orphan_block_tail(sb, oi->of_binfo[i].ob_bh)', 'protocol_id': 'buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse'}]

4. score=53 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/xattr.c::ext4_xattr_block_set:2066
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2031, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2032, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2033, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2034, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2035, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2064, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}]

5. score=53 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/xattr.c::ext4_xattr_block_set:2068
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2031, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2032, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2033, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2034, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2035, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2064, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}]

6. score=53 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/xattr.c::ext4_xattr_block_set:2086
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2031, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2032, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2033, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2034, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2035, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2064, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}]

7. score=53 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/xattr.c::ext4_xattr_block_set:2122
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2031, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2032, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2033, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2034, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2035, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2064, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}]

8. score=53 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/xattr.c::ext4_xattr_block_set:2128
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2031, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2032, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2033, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2034, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2035, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2064, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}]

9. score=45 level=E2_API_PROTOCOL_SUPPORTED severity=P1 type=missing_cleanup exception=True fs/ext4/namei.c::ext4_rename:3888
   protocols: ['journal.ext4_journal_start.stop']
   score: ['E0 static rule base +10', 'E2 API protocol support with exception hints +10', 'P1 severity +20', 'journal or lock protocol violation with exception hints +5']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'journal_handle', 'resource_expr': 'handle', 'line': 3887, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ext4_whiteout_for_rename(idmap, &old, credits, &handle)', 'protocol_id': 'journal.ext4_journal_start.stop'}]

10. score=33 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/inode.c::ext4_bread_batch:923
   protocols: ['buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse']
   score: ['E0 static rule base +10', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'buffer_head', 'resource_expr': 'bhs', 'line': 920, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ext4_buffer_uptodate(bhs[i])', 'protocol_id': 'buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse'}, {'type': 'ownership_transferred', 'resource_kind': 'buffer_head', 'resource_expr': 'bhs', 'line': 921, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ext4_read_bh_lock(bhs[i], REQ_META | REQ_PRIO, false)', 'protocol_id': 'buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse'}]

11. score=33 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/inode.c::ext4_bread_batch:931
   protocols: ['buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse']
   score: ['E0 static rule base +10', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'buffer_head', 'resource_expr': 'bhs', 'line': 920, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ext4_buffer_uptodate(bhs[i])', 'protocol_id': 'buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse'}, {'type': 'ownership_transferred', 'resource_kind': 'buffer_head', 'resource_expr': 'bhs', 'line': 921, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ext4_read_bh_lock(bhs[i], REQ_META | REQ_PRIO, false)', 'protocol_id': 'buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse'}, {'type': 'ownership_transferred', 'resource_kind': 'buffer_head', 'resource_expr': 'bhs', 'line': 928, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'wait_on_buffer(bhs[i])', 'protocol_id': 'buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse'}]

12. score=33 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/resize.c::alloc_flex_gd:245
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'flex_gd', 'line': 244, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'kmalloc(sizeof(*flex_gd), GFP_NOFS)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}]

13. score=33 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/super.c::parse_apply_sb_mount_options:2532
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 's_ctx', 'line': 2528, 'reason': 'resource assigned into a struct field before the error path', 'confidence': 'low', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'fc', 'line': 2531, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'parse_options(fc, s_mount_opts)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}]

14. score=33 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=partial_cleanup exception=True fs/ext4/super.c::parse_apply_sb_mount_options:2532
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 's_ctx', 'line': 2528, 'reason': 'resource assigned into a struct field before the error path', 'confidence': 'low', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'fc', 'line': 2531, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'parse_options(fc, s_mount_opts)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}]

15. score=33 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/super.c::parse_apply_sb_mount_options:2536
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 's_ctx', 'line': 2528, 'reason': 'resource assigned into a struct field before the error path', 'confidence': 'low', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'fc', 'line': 2531, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'parse_options(fc, s_mount_opts)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'fc', 'line': 2535, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ext4_check_opt_consistency(fc, sb)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}]

16. score=33 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=partial_cleanup exception=True fs/ext4/super.c::parse_apply_sb_mount_options:2536
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 's_ctx', 'line': 2528, 'reason': 'resource assigned into a struct field before the error path', 'confidence': 'low', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'fc', 'line': 2531, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'parse_options(fc, s_mount_opts)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'fc', 'line': 2535, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ext4_check_opt_consistency(fc, sb)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}]

17. score=33 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/sysfs.c::ext4_init_sysfs:584
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'ext4_feat', 'line': 576, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'kzalloc(sizeof(*ext4_feat), GFP_KERNEL)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}]

18. score=33 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/xattr.c::ext4_xattr_block_set:2042
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2031, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2032, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2033, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2034, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2035, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}]

19. score=33 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/xattr.c::ext4_xattr_block_set:2045
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2031, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2032, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2033, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2034, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2035, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}]

20. score=33 level=E2_API_PROTOCOL_SUPPORTED severity=P2 type=missing_cleanup exception=True fs/ext4/xattr.c::ext4_xattr_block_set:2056
   protocols: ['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']
   score: ['E0 static rule base +10', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']
   exception_hints: [{'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2031, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2032, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2033, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'header(s->base)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2034, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}, {'type': 'ownership_transferred', 'resource_kind': 'memory', 'resource_expr': 'base', 'line': 2035, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ENTRY(header(s->base)+1)', 'protocol_id': 'memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree'}]
