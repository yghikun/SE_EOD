# ext4 Fast-Commit Replay Bookkeeping Audit

This audit records source-visible facts for batch-scan hits. It is not
a confirmed-bug report and not an active protocol-freeze change.

- source root: `E:/yanjiusheng/阅读论文/file_system/SE_EOD/linux-sources/linux-v7.1-fs/fs`
- source version: `7.1`
- result semantics: `source_facts_not_bug_claims`
- bug claims allowed: `False`

## Summary

- `audited_helpers`: 2
- `helpers_with_public_int_return`: 2
- `helpers_with_ignored_fast_commit_calls`: 2
- `helpers_swallowing_ext4_map_blocks_errors`: 2
- `helpers_with_metadata_bookkeeping_after_failure`: 1
- `helpers_with_partial_metadata_mutation_before_failure`: 1
- `bug_claims_allowed`: 0

## ext4_ext_replay_set_iblocks

- definition: `fs/ext4/extents.c:6140`
- declaration return type: `int`
- definition return type: `int`
- leading comment: Count number of blocks used by this inode and update i_blocks
- conclusion: `needs_external_semantics`
- recommended action: Keep this as an audited source-review item. Promote it only after an independent replay bookkeeping obligation is frozen.
- bug claim allowed: `False`

Facts:

- `definition_return_contract` at `fs/ext4/extents.c:6140`: definition returns int
- `public_declaration_return_contract` at `fs/ext4/ext4.h:3835`: extern declaration returns int
- `ignored_fast_commit_call` at `fs/ext4/fast_commit.c:1600`: ext4_ext_replay_set_iblocks(inode);
- `swallowed_ext4_map_blocks_error` at `fs/ext4/extents.c:6164`: ret = ext4_map_blocks(NULL, inode, &map, 0); then break; function has final return 0
- `metadata_bookkeeping_after_failure` at `fs/ext4/extents.c:6219`: inode->i_blocks = numblks << (inode->i_sb->s_blocksize_bits - 9);
- `metadata_bookkeeping_after_failure` at `fs/ext4/extents.c:6220`: ext4_mark_inode_dirty(NULL, inode);

## ext4_ext_clear_bb

- definition: `fs/ext4/extents.c:6227`
- declaration return type: `int`
- definition return type: `int`
- leading comment: (none found)
- conclusion: `needs_external_semantics`
- recommended action: Keep this as an audited source-review item. Promote it only after an independent replay bookkeeping obligation is frozen.
- bug claim allowed: `False`

Facts:

- `definition_return_contract` at `fs/ext4/extents.c:6227`: definition returns int
- `public_declaration_return_contract` at `fs/ext4/ext4.h:3838`: extern declaration returns int
- `ignored_fast_commit_call` at `fs/ext4/fast_commit.c:1538`: ext4_ext_clear_bb(inode);
- `swallowed_ext4_map_blocks_error` at `fs/ext4/extents.c:6252`: ret = ext4_map_blocks(NULL, inode, &map, 0); then break; function has final return 0
- `partial_metadata_mutation_before_failure` at `fs/ext4/extents.c:6259`: ext4_mb_mark_bb(inode->i_sb, path[j].p_block, 1, false);
- `partial_metadata_mutation_before_failure` at `fs/ext4/extents.c:6261`: ext4_fc_record_regions(inode->i_sb, inode->i_ino, 0, path[j].p_block, 1, 1);
- `partial_metadata_mutation_before_failure` at `fs/ext4/extents.c:6267`: ext4_mb_mark_bb(inode->i_sb, map.m_pblk, map.m_len, false);
- `partial_metadata_mutation_before_failure` at `fs/ext4/extents.c:6268`: ext4_fc_record_regions(inode->i_sb, inode->i_ino, map.m_lblk, map.m_pblk, map.m_len, 1);

## Interpretation

The two helpers expose a suspicious failure-to-success shape, but the
missing piece is semantic authority: ext4 fast-commit replay may treat
some bookkeeping repairs as best effort, or it may require aborting
replay when these helpers cannot complete. MOCC-SE should not promote
these hits into an active protocol instance until that obligation is
supported by independent documentation, maintainer review, an accepted
fix, or a reproducible fault-injection experiment.
