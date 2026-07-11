# SE-EOD Review Feedback Queue

Review top-ranked candidates plus top exception-hint candidates.
Copy completed labels into `outputs/manual_review_labels.jsonl`.

- total queue items: 21

## 1. candidate_afaaa172663d

- buckets: top_ranked
- score: 80 E2_API_PROTOCOL_SUPPORTED
- type/severity: missing_cleanup / P1
- location: fs/ext4/inode.c::ext4_truncate:4151
- exception hints: False

- protocols: `['lock.down_write.up_write']`
- score explanation: `['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P1 severity +20', 'journal or lock protocol violation without exception hints +20']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_afaaa172663d",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 4071:  * ext4_truncate() to have another go.  So there will be instantiated blocks
 4072:  * to the right of the truncation point in a crashed ext4 filesystem.  But
 4073:  * that's fine - as long as they are linked from the inode, the post-crash
 4074:  * ext4_truncate() run will find them and release them.
 4075:  */
 4076: int ext4_truncate(struct inode *inode)
 4077: {
 4078: 	struct ext4_inode_info *ei = EXT4_I(inode);
 4079: 	unsigned int credits;
 4080: 	int err = 0, err2;
 4081: 	handle_t *handle;
 4082: 	struct address_space *mapping = inode->i_mapping;
 4083: 
 4084: 	/*
 4085: 	 * There is a possibility that we're either freeing the inode
 4086: 	 * or it's a completely new inode. In those cases we might not
 4087: 	 * have i_rwsem locked because it's not necessary.
 4088: 	 */
 4089: 	if (!(inode->i_state & (I_NEW|I_FREEING)))
 4090: 		WARN_ON(!inode_is_locked(inode));
 4091: 	trace_ext4_truncate_enter(inode);
 4092: 
 4093: 	if (!ext4_can_truncate(inode))
 4094: 		goto out_trace;
 4095: 
 4096: 	if (inode->i_size == 0 && !test_opt(inode->i_sb, NO_AUTO_DA_ALLOC))
 4097: 		ext4_set_inode_state(inode, EXT4_STATE_DA_ALLOC_CLOSE);
 4098: 
 4099: 	if (ext4_has_inline_data(inode)) {
 4100: 		int has_inline = 1;
 4101: 
 4102: 		err = ext4_inline_data_truncate(inode, &has_inline);
 4103: 		if (err || has_inline)
 4104: 			goto out_trace;
 4105: 	}
 4106: 
 4107: 	/* If we zero-out tail of the page, we have to create jinode for jbd2 */
 4108: 	if (inode->i_size & (inode->i_sb->s_blocksize - 1)) {
 4109: 		err = ext4_inode_attach_jinode(inode);
 4110: 		if (err)
 4111: 			goto out_trace;
 4112: 	}
 4113: 
 4114: 	if (ext4_test_inode_flag(inode, EXT4_INODE_EXTENTS))
 4115: 		credits = ext4_writepage_trans_blocks(inode);
 4116: 	else
 4117: 		credits = ext4_blocks_for_truncate(inode);
 4118: 
 4119: 	handle = ext4_journal_start(inode, EXT4_HT_TRUNCATE, credits);
 4120: 	if (IS_ERR(handle)) {
 4121: 		err = PTR_ERR(handle);
 4122: 		goto out_trace;
 4123: 	}
 4124: 
 4125: 	if (inode->i_size & (inode->i_sb->s_blocksize - 1))
 4126: 		ext4_block_truncate_page(handle, mapping, inode->i_size);
 4127: 
 4128: 	/*
 4129: 	 * We add the inode to the orphan list, so that if this
 4130: 	 * truncate spans multiple transactions, and we crash, we will
 4131: 	 * resume the truncate when the filesystem recovers.  It also
 4132: 	 * marks the inode dirty, to catch the new size.
 4133: 	 *
 4134: 	 * Implication: the file must always be in a sane, consistent
 4135: 	 * truncatable state while each transaction commits.
 4136: 	 */
 4137: 	err = ext4_orphan_add(handle, inode);
 4138: 	if (err)
 4139: 		goto out_stop;
 4140: 
 4141: 	down_write(&EXT4_I(inode)->i_data_sem);
 4142: 
 4143: 	ext4_discard_preallocations(inode);
 4144: 
 4145: 	if (ext4_test_inode_flag(inode, EXT4_INODE_EXTENTS))
 4146: 		err = ext4_ext_truncate(handle, inode);
 4147: 	else
 4148: 		ext4_ind_truncate(handle, inode);
 4149: 
 4150: 	up_write(&ei->i_data_sem);
>4151: 	if (err)
 4152: 		goto out_stop;
 4153: 
 4154: 	if (IS_SYNC(inode))
 4155: 		ext4_handle_sync(handle);
 4156: 
 4157: out_stop:
 4158: 	/*
 4159: 	 * If this was a simple ftruncate() and the file will remain alive,
 4160: 	 * then we need to clear up the orphan record which we created above.
 4161: 	 * However, if this was a real unlink then we were called by
 4162: 	 * ext4_evict_inode(), and we allow that function to clean up the
 4163: 	 * orphan info for us.
 4164: 	 */
 4165: 	if (inode->i_nlink)
 4166: 		ext4_orphan_del(handle, inode);
 4167: 
 4168: 	inode_set_mtime_to_ts(inode, inode_set_ctime_current(inode));
 4169: 	err2 = ext4_mark_inode_dirty(handle, inode);
 4170: 	if (unlikely(err2 && !err))
 4171: 		err = err2;
 4172: 	ext4_journal_stop(handle);
 4173: 
 4174: out_trace:
 4175: 	trace_ext4_truncate_exit(inode);
 4176: 	return err;
 4177: }
 4178: 
 4179: static inline u64 ext4_inode_peek_iversion(const struct inode *inode)
 4180: {
 4181: 	if (unlikely(EXT4_I(inode)->i_flags & EXT4_EA_INODE_FL))
 4182: 		return inode_peek_iversion_raw(inode);
 4183: 	else
 4184: 		return inode_peek_iversion(inode);
 4185: }
 4186: 
 4187: static int ext4_inode_blocks_set(struct ext4_inode *raw_inode,
 4188: 				 struct ext4_inode_info *ei)
 4189: {
 4190: 	struct inode *inode = &(ei->vfs_inode);
 4191: 	u64 i_blocks = READ_ONCE(inode->i_blocks);
 4192: 	struct super_block *sb = inode->i_sb;
 4193: 
 4194: 	if (i_blocks <= ~0U) {
 4195: 		/*
 4196: 		 * i_blocks can be represented in a 32 bit variable
 4197: 		 * as multiple of 512 bytes
 4198: 		 */
 4199: 		raw_inode->i_blocks_lo   = cpu_to_le32(i_blocks);
 4200: 		raw_inode->i_blocks_high = 0;
 4201: 		ext4_clear_inode_flag(inode, EXT4_INODE_HUGE_FILE);
 4202: 		return 0;
 4203: 	}
 4204: 
 4205: 	/*
 4206: 	 * This should never happen since sb->s_maxbytes should not have
 4207: 	 * allowed this, sb->s_maxbytes was set according to the huge_file
 4208: 	 * feature in ext4_fill_super().
 4209: 	 */
 4210: 	if (!ext4_has_feature_huge_file(sb))
 4211: 		return -EFSCORRUPTED;
 4212: 
 4213: 	if (i_blocks <= 0xffffffffffffULL) {
 4214: 		/*
 4215: 		 * i_blocks can be represented in a 48 bit variable
 4216: 		 * as multiple of 512 bytes
 4217: 		 */
 4218: 		raw_inode->i_blocks_lo   = cpu_to_le32(i_blocks);
 4219: 		raw_inode->i_blocks_high = cpu_to_le16(i_blocks >> 32);
 4220: 		ext4_clear_inode_flag(inode, EXT4_INODE_HUGE_FILE);
 4221: 	} else {
 4222: 		ext4_set_inode_flag(inode, EXT4_INODE_HUGE_FILE);
 4223: 		/* i_block is stored in file system block size */
 4224: 		i_blocks = i_blocks >> (inode->i_blkbits - 9);
 4225: 		raw_inode->i_blocks_lo   = cpu_to_le32(i_blocks);
 4226: 		raw_inode->i_blocks_high = cpu_to_le16(i_blocks >> 32);
 4227: 	}
 4228: 	return 0;
 4229: }
 4230: 
 4231: static int ext4_fill_raw_inode(struct inode *inode, struct ext4_inode *raw_inode)
```

## 2. candidate_81b21364332d

- buckets: top_ranked
- score: 80 E2_API_PROTOCOL_SUPPORTED
- type/severity: missing_cleanup / P2
- location: fs/ext4/orphan.c::ext4_init_orphan_info:605
- exception hints: False

- protocols: `['buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse']`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'E2 API protocol support without exception hints +30', 'P2 severity +10', 'buffer_head or memory protocol violation without exception hints +10']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_81b21364332d",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
  525: 						struct buffer_head *bh)
  526: {
  527: 	return (struct ext4_orphan_block_tail *)(bh->b_data + sb->s_blocksize -
  528: 				sizeof(struct ext4_orphan_block_tail));
  529: }
  530: 
  531: static int ext4_orphan_file_block_csum_verify(struct super_block *sb,
  532: 					      struct buffer_head *bh)
  533: {
  534: 	__u32 calculated;
  535: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  536: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  537: 	struct ext4_orphan_block_tail *ot;
  538: 	__le64 dsk_block_nr = cpu_to_le64(bh->b_blocknr);
  539: 
  540: 	if (!ext4_has_metadata_csum(sb))
  541: 		return 1;
  542: 
  543: 	ot = ext4_orphan_block_tail(sb, bh);
  544: 	calculated = ext4_chksum(EXT4_SB(sb), oi->of_csum_seed,
  545: 				 (__u8 *)&dsk_block_nr, sizeof(dsk_block_nr));
  546: 	calculated = ext4_chksum(EXT4_SB(sb), calculated, (__u8 *)bh->b_data,
  547: 				 inodes_per_ob * sizeof(__u32));
  548: 	return le32_to_cpu(ot->ob_checksum) == calculated;
  549: }
  550: 
  551: /* This gets called only when checksumming is enabled */
  552: void ext4_orphan_file_block_trigger(struct jbd2_buffer_trigger_type *triggers,
  553: 				    struct buffer_head *bh,
  554: 				    void *data, size_t size)
  555: {
  556: 	struct super_block *sb = EXT4_TRIGGER(triggers)->sb;
  557: 	__u32 csum;
  558: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  559: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  560: 	struct ext4_orphan_block_tail *ot;
  561: 	__le64 dsk_block_nr = cpu_to_le64(bh->b_blocknr);
  562: 
  563: 	csum = ext4_chksum(EXT4_SB(sb), oi->of_csum_seed,
  564: 			   (__u8 *)&dsk_block_nr, sizeof(dsk_block_nr));
  565: 	csum = ext4_chksum(EXT4_SB(sb), csum, (__u8 *)data,
  566: 			   inodes_per_ob * sizeof(__u32));
  567: 	ot = ext4_orphan_block_tail(sb, bh);
  568: 	ot->ob_checksum = cpu_to_le32(csum);
  569: }
  570: 
  571: int ext4_init_orphan_info(struct super_block *sb)
  572: {
  573: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  574: 	struct inode *inode;
  575: 	int i, j;
  576: 	int ret;
  577: 	int free;
  578: 	__le32 *bdata;
  579: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  580: 	struct ext4_orphan_block_tail *ot;
  581: 	ino_t orphan_ino = le32_to_cpu(EXT4_SB(sb)->s_es->s_orphan_file_inum);
  582: 
  583: 	if (!ext4_has_feature_orphan_file(sb))
  584: 		return 0;
  585: 
  586: 	inode = ext4_iget(sb, orphan_ino, EXT4_IGET_SPECIAL);
  587: 	if (IS_ERR(inode)) {
  588: 		ext4_msg(sb, KERN_ERR, "get orphan inode failed");
  589: 		return PTR_ERR(inode);
  590: 	}
  591: 	oi->of_blocks = inode->i_size >> sb->s_blocksize_bits;
  592: 	oi->of_csum_seed = EXT4_I(inode)->i_csum_seed;
  593: 	oi->of_binfo = kmalloc(oi->of_blocks*sizeof(struct ext4_orphan_block),
  594: 			       GFP_KERNEL);
  595: 	if (!oi->of_binfo) {
  596: 		ret = -ENOMEM;
  597: 		goto out_put;
  598: 	}
  599: 	for (i = 0; i < oi->of_blocks; i++) {
  600: 		oi->of_binfo[i].ob_bh = ext4_bread(NULL, inode, i, 0);
  601: 		if (IS_ERR(oi->of_binfo[i].ob_bh)) {
  602: 			ret = PTR_ERR(oi->of_binfo[i].ob_bh);
  603: 			goto out_free;
  604: 		}
> 605: 		if (!oi->of_binfo[i].ob_bh) {
  606: 			ret = -EIO;
  607: 			goto out_free;
  608: 		}
  609: 		ot = ext4_orphan_block_tail(sb, oi->of_binfo[i].ob_bh);
  610: 		if (le32_to_cpu(ot->ob_magic) != EXT4_ORPHAN_BLOCK_MAGIC) {
  611: 			ext4_error(sb, "orphan file block %d: bad magic", i);
  612: 			ret = -EIO;
  613: 			goto out_free;
  614: 		}
  615: 		if (!ext4_orphan_file_block_csum_verify(sb,
  616: 						oi->of_binfo[i].ob_bh)) {
  617: 			ext4_error(sb, "orphan file block %d: bad checksum", i);
  618: 			ret = -EIO;
  619: 			goto out_free;
  620: 		}
  621: 		bdata = (__le32 *)(oi->of_binfo[i].ob_bh->b_data);
  622: 		free = 0;
  623: 		for (j = 0; j < inodes_per_ob; j++)
  624: 			if (bdata[j] == 0)
  625: 				free++;
  626: 		atomic_set(&oi->of_binfo[i].ob_free_entries, free);
  627: 	}
  628: 	iput(inode);
  629: 	return 0;
  630: out_free:
  631: 	for (i--; i >= 0; i--)
  632: 		brelse(oi->of_binfo[i].ob_bh);
  633: 	kfree(oi->of_binfo);
  634: out_put:
  635: 	iput(inode);
  636: 	return ret;
  637: }
  638: 
  639: int ext4_orphan_file_empty(struct super_block *sb)
  640: {
  641: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  642: 	int i;
  643: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  644: 
  645: 	if (!ext4_has_feature_orphan_file(sb))
  646: 		return 1;
  647: 	for (i = 0; i < oi->of_blocks; i++)
  648: 		if (atomic_read(&oi->of_binfo[i].ob_free_entries) !=
  649: 		    inodes_per_ob)
  650: 			return 0;
  651: 	return 1;
  652: }
```

## 3. candidate_dbbcfe37c464

- buckets: top_ranked
- score: 70 E1_LLM_TRUE_CANDIDATE
- type/severity: error_swallowed / P1
- location: fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1745
- exception hints: False

- protocols: `[]`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'P1 severity +20', 'error_swallowed final return 0 +20']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_dbbcfe37c464",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 1665: 		goto out;
 1666: 	set_nlink(inode, 1);
 1667: 	ext4_mark_inode_dirty(NULL, inode);
 1668: out:
 1669: 	iput(inode);
 1670: 	return ret;
 1671: }
 1672: 
 1673: /*
 1674:  * Record physical disk regions which are in use as per fast commit area,
 1675:  * and used by inodes during replay phase. Our simple replay phase
 1676:  * allocator excludes these regions from allocation.
 1677:  */
 1678: int ext4_fc_record_regions(struct super_block *sb, int ino,
 1679: 		ext4_lblk_t lblk, ext4_fsblk_t pblk, int len, int replay)
 1680: {
 1681: 	struct ext4_fc_replay_state *state;
 1682: 	struct ext4_fc_alloc_region *region;
 1683: 
 1684: 	state = &EXT4_SB(sb)->s_fc_replay_state;
 1685: 	/*
 1686: 	 * during replay phase, the fc_regions_valid may not same as
 1687: 	 * fc_regions_used, update it when do new additions.
 1688: 	 */
 1689: 	if (replay && state->fc_regions_used != state->fc_regions_valid)
 1690: 		state->fc_regions_used = state->fc_regions_valid;
 1691: 	if (state->fc_regions_used == state->fc_regions_size) {
 1692: 		struct ext4_fc_alloc_region *fc_regions;
 1693: 
 1694: 		fc_regions = krealloc(state->fc_regions,
 1695: 				      sizeof(struct ext4_fc_alloc_region) *
 1696: 				      (state->fc_regions_size +
 1697: 				       EXT4_FC_REPLAY_REALLOC_INCREMENT),
 1698: 				      GFP_KERNEL);
 1699: 		if (!fc_regions)
 1700: 			return -ENOMEM;
 1701: 		state->fc_regions_size +=
 1702: 			EXT4_FC_REPLAY_REALLOC_INCREMENT;
 1703: 		state->fc_regions = fc_regions;
 1704: 	}
 1705: 	region = &state->fc_regions[state->fc_regions_used++];
 1706: 	region->ino = ino;
 1707: 	region->lblk = lblk;
 1708: 	region->pblk = pblk;
 1709: 	region->len = len;
 1710: 
 1711: 	if (replay)
 1712: 		state->fc_regions_valid++;
 1713: 
 1714: 	return 0;
 1715: }
 1716: 
 1717: /* Replay add range tag */
 1718: static int ext4_fc_replay_add_range(struct super_block *sb,
 1719: 				    struct ext4_fc_tl_mem *tl, u8 *val)
 1720: {
 1721: 	struct ext4_fc_add_range fc_add_ex;
 1722: 	struct ext4_extent newex, *ex;
 1723: 	struct inode *inode;
 1724: 	ext4_lblk_t start, cur;
 1725: 	int remaining, len;
 1726: 	ext4_fsblk_t start_pblk;
 1727: 	struct ext4_map_blocks map;
 1728: 	struct ext4_ext_path *path = NULL;
 1729: 	int ret;
 1730: 
 1731: 	memcpy(&fc_add_ex, val, sizeof(fc_add_ex));
 1732: 	ex = (struct ext4_extent *)&fc_add_ex.fc_ex;
 1733: 
 1734: 	trace_ext4_fc_replay(sb, EXT4_FC_TAG_ADD_RANGE,
 1735: 		le32_to_cpu(fc_add_ex.fc_ino), le32_to_cpu(ex->ee_block),
 1736: 		ext4_ext_get_actual_len(ex));
 1737: 
 1738: 	inode = ext4_iget(sb, le32_to_cpu(fc_add_ex.fc_ino), EXT4_IGET_NORMAL);
 1739: 	if (IS_ERR(inode)) {
 1740: 		ext4_debug("Inode not found.");
 1741: 		return 0;
 1742: 	}
 1743: 
 1744: 	ret = ext4_fc_record_modified_inode(sb, inode->i_ino);
>1745: 	if (ret)
 1746: 		goto out;
 1747: 
 1748: 	start = le32_to_cpu(ex->ee_block);
 1749: 	start_pblk = ext4_ext_pblock(ex);
 1750: 	len = ext4_ext_get_actual_len(ex);
 1751: 
 1752: 	cur = start;
 1753: 	remaining = len;
 1754: 	ext4_debug("ADD_RANGE, lblk %d, pblk %lld, len %d, unwritten %d, inode %ld\n",
 1755: 		  start, start_pblk, len, ext4_ext_is_unwritten(ex),
 1756: 		  inode->i_ino);
 1757: 
 1758: 	while (remaining > 0) {
 1759: 		map.m_lblk = cur;
 1760: 		map.m_len = remaining;
 1761: 		map.m_pblk = 0;
 1762: 		ret = ext4_map_blocks(NULL, inode, &map, 0);
 1763: 
 1764: 		if (ret < 0)
 1765: 			goto out;
 1766: 
 1767: 		if (ret == 0) {
 1768: 			/* Range is not mapped */
 1769: 			path = ext4_find_extent(inode, cur, NULL, 0);
 1770: 			if (IS_ERR(path))
 1771: 				goto out;
 1772: 			memset(&newex, 0, sizeof(newex));
 1773: 			newex.ee_block = cpu_to_le32(cur);
 1774: 			ext4_ext_store_pblock(
 1775: 				&newex, start_pblk + cur - start);
 1776: 			newex.ee_len = cpu_to_le16(map.m_len);
 1777: 			if (ext4_ext_is_unwritten(ex))
 1778: 				ext4_ext_mark_unwritten(&newex);
 1779: 			down_write(&EXT4_I(inode)->i_data_sem);
 1780: 			ret = ext4_ext_insert_extent(
 1781: 				NULL, inode, &path, &newex, 0);
 1782: 			up_write((&EXT4_I(inode)->i_data_sem));
 1783: 			ext4_free_ext_path(path);
 1784: 			if (ret)
 1785: 				goto out;
 1786: 			goto next;
 1787: 		}
 1788: 
 1789: 		if (start_pblk + cur - start != map.m_pblk) {
 1790: 			/*
 1791: 			 * Logical to physical mapping changed. This can happen
 1792: 			 * if this range was removed and then reallocated to
 1793: 			 * map to new physical blocks during a fast commit.
 1794: 			 */
 1795: 			ret = ext4_ext_replay_update_ex(inode, cur, map.m_len,
 1796: 					ext4_ext_is_unwritten(ex),
 1797: 					start_pblk + cur - start);
 1798: 			if (ret)
 1799: 				goto out;
 1800: 			/*
 1801: 			 * Mark the old blocks as free since they aren't used
 1802: 			 * anymore. We maintain an array of all the modified
 1803: 			 * inodes. In case these blocks are still used at either
 1804: 			 * a different logical range in the same inode or in
 1805: 			 * some different inode, we will mark them as allocated
 1806: 			 * at the end of the FC replay using our array of
 1807: 			 * modified inodes.
 1808: 			 */
 1809: 			ext4_mb_mark_bb(inode->i_sb, map.m_pblk, map.m_len, false);
 1810: 			goto next;
 1811: 		}
 1812: 
 1813: 		/* Range is mapped and needs a state change */
 1814: 		ext4_debug("Converting from %ld to %d %lld",
 1815: 				map.m_flags & EXT4_MAP_UNWRITTEN,
 1816: 			ext4_ext_is_unwritten(ex), map.m_pblk);
 1817: 		ret = ext4_ext_replay_update_ex(inode, cur, map.m_len,
 1818: 					ext4_ext_is_unwritten(ex), map.m_pblk);
 1819: 		if (ret)
 1820: 			goto out;
 1821: 		/*
 1822: 		 * We may have split the extent tree while toggling the state.
 1823: 		 * Try to shrink the extent tree now.
 1824: 		 */
 1825: 		ext4_ext_replay_shrink_inode(inode, start + len);
```

## 4. candidate_0bee7caf6376

- buckets: top_ranked
- score: 70 E1_LLM_TRUE_CANDIDATE
- type/severity: error_swallowed / P1
- location: fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1764
- exception hints: False

- protocols: `[]`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'P1 severity +20', 'error_swallowed final return 0 +20']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_0bee7caf6376",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 1684: 	state = &EXT4_SB(sb)->s_fc_replay_state;
 1685: 	/*
 1686: 	 * during replay phase, the fc_regions_valid may not same as
 1687: 	 * fc_regions_used, update it when do new additions.
 1688: 	 */
 1689: 	if (replay && state->fc_regions_used != state->fc_regions_valid)
 1690: 		state->fc_regions_used = state->fc_regions_valid;
 1691: 	if (state->fc_regions_used == state->fc_regions_size) {
 1692: 		struct ext4_fc_alloc_region *fc_regions;
 1693: 
 1694: 		fc_regions = krealloc(state->fc_regions,
 1695: 				      sizeof(struct ext4_fc_alloc_region) *
 1696: 				      (state->fc_regions_size +
 1697: 				       EXT4_FC_REPLAY_REALLOC_INCREMENT),
 1698: 				      GFP_KERNEL);
 1699: 		if (!fc_regions)
 1700: 			return -ENOMEM;
 1701: 		state->fc_regions_size +=
 1702: 			EXT4_FC_REPLAY_REALLOC_INCREMENT;
 1703: 		state->fc_regions = fc_regions;
 1704: 	}
 1705: 	region = &state->fc_regions[state->fc_regions_used++];
 1706: 	region->ino = ino;
 1707: 	region->lblk = lblk;
 1708: 	region->pblk = pblk;
 1709: 	region->len = len;
 1710: 
 1711: 	if (replay)
 1712: 		state->fc_regions_valid++;
 1713: 
 1714: 	return 0;
 1715: }
 1716: 
 1717: /* Replay add range tag */
 1718: static int ext4_fc_replay_add_range(struct super_block *sb,
 1719: 				    struct ext4_fc_tl_mem *tl, u8 *val)
 1720: {
 1721: 	struct ext4_fc_add_range fc_add_ex;
 1722: 	struct ext4_extent newex, *ex;
 1723: 	struct inode *inode;
 1724: 	ext4_lblk_t start, cur;
 1725: 	int remaining, len;
 1726: 	ext4_fsblk_t start_pblk;
 1727: 	struct ext4_map_blocks map;
 1728: 	struct ext4_ext_path *path = NULL;
 1729: 	int ret;
 1730: 
 1731: 	memcpy(&fc_add_ex, val, sizeof(fc_add_ex));
 1732: 	ex = (struct ext4_extent *)&fc_add_ex.fc_ex;
 1733: 
 1734: 	trace_ext4_fc_replay(sb, EXT4_FC_TAG_ADD_RANGE,
 1735: 		le32_to_cpu(fc_add_ex.fc_ino), le32_to_cpu(ex->ee_block),
 1736: 		ext4_ext_get_actual_len(ex));
 1737: 
 1738: 	inode = ext4_iget(sb, le32_to_cpu(fc_add_ex.fc_ino), EXT4_IGET_NORMAL);
 1739: 	if (IS_ERR(inode)) {
 1740: 		ext4_debug("Inode not found.");
 1741: 		return 0;
 1742: 	}
 1743: 
 1744: 	ret = ext4_fc_record_modified_inode(sb, inode->i_ino);
 1745: 	if (ret)
 1746: 		goto out;
 1747: 
 1748: 	start = le32_to_cpu(ex->ee_block);
 1749: 	start_pblk = ext4_ext_pblock(ex);
 1750: 	len = ext4_ext_get_actual_len(ex);
 1751: 
 1752: 	cur = start;
 1753: 	remaining = len;
 1754: 	ext4_debug("ADD_RANGE, lblk %d, pblk %lld, len %d, unwritten %d, inode %ld\n",
 1755: 		  start, start_pblk, len, ext4_ext_is_unwritten(ex),
 1756: 		  inode->i_ino);
 1757: 
 1758: 	while (remaining > 0) {
 1759: 		map.m_lblk = cur;
 1760: 		map.m_len = remaining;
 1761: 		map.m_pblk = 0;
 1762: 		ret = ext4_map_blocks(NULL, inode, &map, 0);
 1763: 
>1764: 		if (ret < 0)
 1765: 			goto out;
 1766: 
 1767: 		if (ret == 0) {
 1768: 			/* Range is not mapped */
 1769: 			path = ext4_find_extent(inode, cur, NULL, 0);
 1770: 			if (IS_ERR(path))
 1771: 				goto out;
 1772: 			memset(&newex, 0, sizeof(newex));
 1773: 			newex.ee_block = cpu_to_le32(cur);
 1774: 			ext4_ext_store_pblock(
 1775: 				&newex, start_pblk + cur - start);
 1776: 			newex.ee_len = cpu_to_le16(map.m_len);
 1777: 			if (ext4_ext_is_unwritten(ex))
 1778: 				ext4_ext_mark_unwritten(&newex);
 1779: 			down_write(&EXT4_I(inode)->i_data_sem);
 1780: 			ret = ext4_ext_insert_extent(
 1781: 				NULL, inode, &path, &newex, 0);
 1782: 			up_write((&EXT4_I(inode)->i_data_sem));
 1783: 			ext4_free_ext_path(path);
 1784: 			if (ret)
 1785: 				goto out;
 1786: 			goto next;
 1787: 		}
 1788: 
 1789: 		if (start_pblk + cur - start != map.m_pblk) {
 1790: 			/*
 1791: 			 * Logical to physical mapping changed. This can happen
 1792: 			 * if this range was removed and then reallocated to
 1793: 			 * map to new physical blocks during a fast commit.
 1794: 			 */
 1795: 			ret = ext4_ext_replay_update_ex(inode, cur, map.m_len,
 1796: 					ext4_ext_is_unwritten(ex),
 1797: 					start_pblk + cur - start);
 1798: 			if (ret)
 1799: 				goto out;
 1800: 			/*
 1801: 			 * Mark the old blocks as free since they aren't used
 1802: 			 * anymore. We maintain an array of all the modified
 1803: 			 * inodes. In case these blocks are still used at either
 1804: 			 * a different logical range in the same inode or in
 1805: 			 * some different inode, we will mark them as allocated
 1806: 			 * at the end of the FC replay using our array of
 1807: 			 * modified inodes.
 1808: 			 */
 1809: 			ext4_mb_mark_bb(inode->i_sb, map.m_pblk, map.m_len, false);
 1810: 			goto next;
 1811: 		}
 1812: 
 1813: 		/* Range is mapped and needs a state change */
 1814: 		ext4_debug("Converting from %ld to %d %lld",
 1815: 				map.m_flags & EXT4_MAP_UNWRITTEN,
 1816: 			ext4_ext_is_unwritten(ex), map.m_pblk);
 1817: 		ret = ext4_ext_replay_update_ex(inode, cur, map.m_len,
 1818: 					ext4_ext_is_unwritten(ex), map.m_pblk);
 1819: 		if (ret)
 1820: 			goto out;
 1821: 		/*
 1822: 		 * We may have split the extent tree while toggling the state.
 1823: 		 * Try to shrink the extent tree now.
 1824: 		 */
 1825: 		ext4_ext_replay_shrink_inode(inode, start + len);
 1826: next:
 1827: 		cur += map.m_len;
 1828: 		remaining -= map.m_len;
 1829: 	}
 1830: 	ext4_ext_replay_shrink_inode(inode, i_size_read(inode) >>
 1831: 					sb->s_blocksize_bits);
 1832: out:
 1833: 	iput(inode);
 1834: 	return 0;
 1835: }
 1836: 
 1837: /* Replay DEL_RANGE tag */
 1838: static int
 1839: ext4_fc_replay_del_range(struct super_block *sb,
 1840: 			 struct ext4_fc_tl_mem *tl, u8 *val)
 1841: {
 1842: 	struct inode *inode;
 1843: 	struct ext4_fc_del_range lrange;
 1844: 	struct ext4_map_blocks map;
```

## 5. candidate_63c4fa28d90e

- buckets: top_ranked
- score: 70 E1_LLM_TRUE_CANDIDATE
- type/severity: error_swallowed / P1
- location: fs/ext4/fast_commit.c::ext4_fc_replay_add_range:1767
- exception hints: False

- protocols: `[]`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'P1 severity +20', 'error_swallowed final return 0 +20']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_63c4fa28d90e",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 1687: 	 * fc_regions_used, update it when do new additions.
 1688: 	 */
 1689: 	if (replay && state->fc_regions_used != state->fc_regions_valid)
 1690: 		state->fc_regions_used = state->fc_regions_valid;
 1691: 	if (state->fc_regions_used == state->fc_regions_size) {
 1692: 		struct ext4_fc_alloc_region *fc_regions;
 1693: 
 1694: 		fc_regions = krealloc(state->fc_regions,
 1695: 				      sizeof(struct ext4_fc_alloc_region) *
 1696: 				      (state->fc_regions_size +
 1697: 				       EXT4_FC_REPLAY_REALLOC_INCREMENT),
 1698: 				      GFP_KERNEL);
 1699: 		if (!fc_regions)
 1700: 			return -ENOMEM;
 1701: 		state->fc_regions_size +=
 1702: 			EXT4_FC_REPLAY_REALLOC_INCREMENT;
 1703: 		state->fc_regions = fc_regions;
 1704: 	}
 1705: 	region = &state->fc_regions[state->fc_regions_used++];
 1706: 	region->ino = ino;
 1707: 	region->lblk = lblk;
 1708: 	region->pblk = pblk;
 1709: 	region->len = len;
 1710: 
 1711: 	if (replay)
 1712: 		state->fc_regions_valid++;
 1713: 
 1714: 	return 0;
 1715: }
 1716: 
 1717: /* Replay add range tag */
 1718: static int ext4_fc_replay_add_range(struct super_block *sb,
 1719: 				    struct ext4_fc_tl_mem *tl, u8 *val)
 1720: {
 1721: 	struct ext4_fc_add_range fc_add_ex;
 1722: 	struct ext4_extent newex, *ex;
 1723: 	struct inode *inode;
 1724: 	ext4_lblk_t start, cur;
 1725: 	int remaining, len;
 1726: 	ext4_fsblk_t start_pblk;
 1727: 	struct ext4_map_blocks map;
 1728: 	struct ext4_ext_path *path = NULL;
 1729: 	int ret;
 1730: 
 1731: 	memcpy(&fc_add_ex, val, sizeof(fc_add_ex));
 1732: 	ex = (struct ext4_extent *)&fc_add_ex.fc_ex;
 1733: 
 1734: 	trace_ext4_fc_replay(sb, EXT4_FC_TAG_ADD_RANGE,
 1735: 		le32_to_cpu(fc_add_ex.fc_ino), le32_to_cpu(ex->ee_block),
 1736: 		ext4_ext_get_actual_len(ex));
 1737: 
 1738: 	inode = ext4_iget(sb, le32_to_cpu(fc_add_ex.fc_ino), EXT4_IGET_NORMAL);
 1739: 	if (IS_ERR(inode)) {
 1740: 		ext4_debug("Inode not found.");
 1741: 		return 0;
 1742: 	}
 1743: 
 1744: 	ret = ext4_fc_record_modified_inode(sb, inode->i_ino);
 1745: 	if (ret)
 1746: 		goto out;
 1747: 
 1748: 	start = le32_to_cpu(ex->ee_block);
 1749: 	start_pblk = ext4_ext_pblock(ex);
 1750: 	len = ext4_ext_get_actual_len(ex);
 1751: 
 1752: 	cur = start;
 1753: 	remaining = len;
 1754: 	ext4_debug("ADD_RANGE, lblk %d, pblk %lld, len %d, unwritten %d, inode %ld\n",
 1755: 		  start, start_pblk, len, ext4_ext_is_unwritten(ex),
 1756: 		  inode->i_ino);
 1757: 
 1758: 	while (remaining > 0) {
 1759: 		map.m_lblk = cur;
 1760: 		map.m_len = remaining;
 1761: 		map.m_pblk = 0;
 1762: 		ret = ext4_map_blocks(NULL, inode, &map, 0);
 1763: 
 1764: 		if (ret < 0)
 1765: 			goto out;
 1766: 
>1767: 		if (ret == 0) {
 1768: 			/* Range is not mapped */
 1769: 			path = ext4_find_extent(inode, cur, NULL, 0);
 1770: 			if (IS_ERR(path))
 1771: 				goto out;
 1772: 			memset(&newex, 0, sizeof(newex));
 1773: 			newex.ee_block = cpu_to_le32(cur);
 1774: 			ext4_ext_store_pblock(
 1775: 				&newex, start_pblk + cur - start);
 1776: 			newex.ee_len = cpu_to_le16(map.m_len);
 1777: 			if (ext4_ext_is_unwritten(ex))
 1778: 				ext4_ext_mark_unwritten(&newex);
 1779: 			down_write(&EXT4_I(inode)->i_data_sem);
 1780: 			ret = ext4_ext_insert_extent(
 1781: 				NULL, inode, &path, &newex, 0);
 1782: 			up_write((&EXT4_I(inode)->i_data_sem));
 1783: 			ext4_free_ext_path(path);
 1784: 			if (ret)
 1785: 				goto out;
 1786: 			goto next;
 1787: 		}
 1788: 
 1789: 		if (start_pblk + cur - start != map.m_pblk) {
 1790: 			/*
 1791: 			 * Logical to physical mapping changed. This can happen
 1792: 			 * if this range was removed and then reallocated to
 1793: 			 * map to new physical blocks during a fast commit.
 1794: 			 */
 1795: 			ret = ext4_ext_replay_update_ex(inode, cur, map.m_len,
 1796: 					ext4_ext_is_unwritten(ex),
 1797: 					start_pblk + cur - start);
 1798: 			if (ret)
 1799: 				goto out;
 1800: 			/*
 1801: 			 * Mark the old blocks as free since they aren't used
 1802: 			 * anymore. We maintain an array of all the modified
 1803: 			 * inodes. In case these blocks are still used at either
 1804: 			 * a different logical range in the same inode or in
 1805: 			 * some different inode, we will mark them as allocated
 1806: 			 * at the end of the FC replay using our array of
 1807: 			 * modified inodes.
 1808: 			 */
 1809: 			ext4_mb_mark_bb(inode->i_sb, map.m_pblk, map.m_len, false);
 1810: 			goto next;
 1811: 		}
 1812: 
 1813: 		/* Range is mapped and needs a state change */
 1814: 		ext4_debug("Converting from %ld to %d %lld",
 1815: 				map.m_flags & EXT4_MAP_UNWRITTEN,
 1816: 			ext4_ext_is_unwritten(ex), map.m_pblk);
 1817: 		ret = ext4_ext_replay_update_ex(inode, cur, map.m_len,
 1818: 					ext4_ext_is_unwritten(ex), map.m_pblk);
 1819: 		if (ret)
 1820: 			goto out;
 1821: 		/*
 1822: 		 * We may have split the extent tree while toggling the state.
 1823: 		 * Try to shrink the extent tree now.
 1824: 		 */
 1825: 		ext4_ext_replay_shrink_inode(inode, start + len);
 1826: next:
 1827: 		cur += map.m_len;
 1828: 		remaining -= map.m_len;
 1829: 	}
 1830: 	ext4_ext_replay_shrink_inode(inode, i_size_read(inode) >>
 1831: 					sb->s_blocksize_bits);
 1832: out:
 1833: 	iput(inode);
 1834: 	return 0;
 1835: }
 1836: 
 1837: /* Replay DEL_RANGE tag */
 1838: static int
 1839: ext4_fc_replay_del_range(struct super_block *sb,
 1840: 			 struct ext4_fc_tl_mem *tl, u8 *val)
 1841: {
 1842: 	struct inode *inode;
 1843: 	struct ext4_fc_del_range lrange;
 1844: 	struct ext4_map_blocks map;
 1845: 	ext4_lblk_t cur, remaining;
 1846: 	int ret;
 1847: 
```

## 6. candidate_7fb6f5389cec

- buckets: top_ranked
- score: 70 E1_LLM_TRUE_CANDIDATE
- type/severity: error_swallowed / P1
- location: fs/ext4/fast_commit.c::ext4_fc_replay_del_range:1862
- exception hints: False

- protocols: `[]`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'P1 severity +20', 'error_swallowed final return 0 +20']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_7fb6f5389cec",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 1782: 			up_write((&EXT4_I(inode)->i_data_sem));
 1783: 			ext4_free_ext_path(path);
 1784: 			if (ret)
 1785: 				goto out;
 1786: 			goto next;
 1787: 		}
 1788: 
 1789: 		if (start_pblk + cur - start != map.m_pblk) {
 1790: 			/*
 1791: 			 * Logical to physical mapping changed. This can happen
 1792: 			 * if this range was removed and then reallocated to
 1793: 			 * map to new physical blocks during a fast commit.
 1794: 			 */
 1795: 			ret = ext4_ext_replay_update_ex(inode, cur, map.m_len,
 1796: 					ext4_ext_is_unwritten(ex),
 1797: 					start_pblk + cur - start);
 1798: 			if (ret)
 1799: 				goto out;
 1800: 			/*
 1801: 			 * Mark the old blocks as free since they aren't used
 1802: 			 * anymore. We maintain an array of all the modified
 1803: 			 * inodes. In case these blocks are still used at either
 1804: 			 * a different logical range in the same inode or in
 1805: 			 * some different inode, we will mark them as allocated
 1806: 			 * at the end of the FC replay using our array of
 1807: 			 * modified inodes.
 1808: 			 */
 1809: 			ext4_mb_mark_bb(inode->i_sb, map.m_pblk, map.m_len, false);
 1810: 			goto next;
 1811: 		}
 1812: 
 1813: 		/* Range is mapped and needs a state change */
 1814: 		ext4_debug("Converting from %ld to %d %lld",
 1815: 				map.m_flags & EXT4_MAP_UNWRITTEN,
 1816: 			ext4_ext_is_unwritten(ex), map.m_pblk);
 1817: 		ret = ext4_ext_replay_update_ex(inode, cur, map.m_len,
 1818: 					ext4_ext_is_unwritten(ex), map.m_pblk);
 1819: 		if (ret)
 1820: 			goto out;
 1821: 		/*
 1822: 		 * We may have split the extent tree while toggling the state.
 1823: 		 * Try to shrink the extent tree now.
 1824: 		 */
 1825: 		ext4_ext_replay_shrink_inode(inode, start + len);
 1826: next:
 1827: 		cur += map.m_len;
 1828: 		remaining -= map.m_len;
 1829: 	}
 1830: 	ext4_ext_replay_shrink_inode(inode, i_size_read(inode) >>
 1831: 					sb->s_blocksize_bits);
 1832: out:
 1833: 	iput(inode);
 1834: 	return 0;
 1835: }
 1836: 
 1837: /* Replay DEL_RANGE tag */
 1838: static int
 1839: ext4_fc_replay_del_range(struct super_block *sb,
 1840: 			 struct ext4_fc_tl_mem *tl, u8 *val)
 1841: {
 1842: 	struct inode *inode;
 1843: 	struct ext4_fc_del_range lrange;
 1844: 	struct ext4_map_blocks map;
 1845: 	ext4_lblk_t cur, remaining;
 1846: 	int ret;
 1847: 
 1848: 	memcpy(&lrange, val, sizeof(lrange));
 1849: 	cur = le32_to_cpu(lrange.fc_lblk);
 1850: 	remaining = le32_to_cpu(lrange.fc_len);
 1851: 
 1852: 	trace_ext4_fc_replay(sb, EXT4_FC_TAG_DEL_RANGE,
 1853: 		le32_to_cpu(lrange.fc_ino), cur, remaining);
 1854: 
 1855: 	inode = ext4_iget(sb, le32_to_cpu(lrange.fc_ino), EXT4_IGET_NORMAL);
 1856: 	if (IS_ERR(inode)) {
 1857: 		ext4_debug("Inode %d not found", le32_to_cpu(lrange.fc_ino));
 1858: 		return 0;
 1859: 	}
 1860: 
 1861: 	ret = ext4_fc_record_modified_inode(sb, inode->i_ino);
>1862: 	if (ret)
 1863: 		goto out;
 1864: 
 1865: 	ext4_debug("DEL_RANGE, inode %ld, lblk %d, len %d\n",
 1866: 			inode->i_ino, le32_to_cpu(lrange.fc_lblk),
 1867: 			le32_to_cpu(lrange.fc_len));
 1868: 	while (remaining > 0) {
 1869: 		map.m_lblk = cur;
 1870: 		map.m_len = remaining;
 1871: 
 1872: 		ret = ext4_map_blocks(NULL, inode, &map, 0);
 1873: 		if (ret < 0)
 1874: 			goto out;
 1875: 		if (ret > 0) {
 1876: 			remaining -= ret;
 1877: 			cur += ret;
 1878: 			ext4_mb_mark_bb(inode->i_sb, map.m_pblk, map.m_len, false);
 1879: 		} else {
 1880: 			remaining -= map.m_len;
 1881: 			cur += map.m_len;
 1882: 		}
 1883: 	}
 1884: 
 1885: 	down_write(&EXT4_I(inode)->i_data_sem);
 1886: 	ret = ext4_ext_remove_space(inode, le32_to_cpu(lrange.fc_lblk),
 1887: 				le32_to_cpu(lrange.fc_lblk) +
 1888: 				le32_to_cpu(lrange.fc_len) - 1);
 1889: 	up_write(&EXT4_I(inode)->i_data_sem);
 1890: 	if (ret)
 1891: 		goto out;
 1892: 	ext4_ext_replay_shrink_inode(inode,
 1893: 		i_size_read(inode) >> sb->s_blocksize_bits);
 1894: 	ext4_mark_inode_dirty(NULL, inode);
 1895: out:
 1896: 	iput(inode);
 1897: 	return 0;
 1898: }
 1899: 
 1900: static void ext4_fc_set_bitmaps_and_counters(struct super_block *sb)
 1901: {
 1902: 	struct ext4_fc_replay_state *state;
 1903: 	struct inode *inode;
 1904: 	struct ext4_ext_path *path = NULL;
 1905: 	struct ext4_map_blocks map;
 1906: 	int i, ret, j;
 1907: 	ext4_lblk_t cur, end;
 1908: 
 1909: 	state = &EXT4_SB(sb)->s_fc_replay_state;
 1910: 	for (i = 0; i < state->fc_modified_inodes_used; i++) {
 1911: 		inode = ext4_iget(sb, state->fc_modified_inodes[i],
 1912: 			EXT4_IGET_NORMAL);
 1913: 		if (IS_ERR(inode)) {
 1914: 			ext4_debug("Inode %d not found.",
 1915: 				state->fc_modified_inodes[i]);
 1916: 			continue;
 1917: 		}
 1918: 		cur = 0;
 1919: 		end = EXT_MAX_BLOCKS;
 1920: 		if (ext4_test_inode_flag(inode, EXT4_INODE_INLINE_DATA)) {
 1921: 			iput(inode);
 1922: 			continue;
 1923: 		}
 1924: 		while (cur < end) {
 1925: 			map.m_lblk = cur;
 1926: 			map.m_len = end - cur;
 1927: 
 1928: 			ret = ext4_map_blocks(NULL, inode, &map, 0);
 1929: 			if (ret < 0)
 1930: 				break;
 1931: 
 1932: 			if (ret > 0) {
 1933: 				path = ext4_find_extent(inode, map.m_lblk, NULL, 0);
 1934: 				if (!IS_ERR(path)) {
 1935: 					for (j = 0; j < path->p_depth; j++)
 1936: 						ext4_mb_mark_bb(inode->i_sb,
 1937: 							path[j].p_block, 1, true);
 1938: 					ext4_free_ext_path(path);
 1939: 				}
 1940: 				cur += ret;
 1941: 				ext4_mb_mark_bb(inode->i_sb, map.m_pblk,
 1942: 							map.m_len, true);
```

## 7. candidate_ffec52cad42c

- buckets: top_ranked
- score: 70 E1_LLM_TRUE_CANDIDATE
- type/severity: error_swallowed / P1
- location: fs/ext4/fast_commit.c::ext4_fc_replay_del_range:1873
- exception hints: False

- protocols: `[]`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'P1 severity +20', 'error_swallowed final return 0 +20']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_ffec52cad42c",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 1793: 			 * map to new physical blocks during a fast commit.
 1794: 			 */
 1795: 			ret = ext4_ext_replay_update_ex(inode, cur, map.m_len,
 1796: 					ext4_ext_is_unwritten(ex),
 1797: 					start_pblk + cur - start);
 1798: 			if (ret)
 1799: 				goto out;
 1800: 			/*
 1801: 			 * Mark the old blocks as free since they aren't used
 1802: 			 * anymore. We maintain an array of all the modified
 1803: 			 * inodes. In case these blocks are still used at either
 1804: 			 * a different logical range in the same inode or in
 1805: 			 * some different inode, we will mark them as allocated
 1806: 			 * at the end of the FC replay using our array of
 1807: 			 * modified inodes.
 1808: 			 */
 1809: 			ext4_mb_mark_bb(inode->i_sb, map.m_pblk, map.m_len, false);
 1810: 			goto next;
 1811: 		}
 1812: 
 1813: 		/* Range is mapped and needs a state change */
 1814: 		ext4_debug("Converting from %ld to %d %lld",
 1815: 				map.m_flags & EXT4_MAP_UNWRITTEN,
 1816: 			ext4_ext_is_unwritten(ex), map.m_pblk);
 1817: 		ret = ext4_ext_replay_update_ex(inode, cur, map.m_len,
 1818: 					ext4_ext_is_unwritten(ex), map.m_pblk);
 1819: 		if (ret)
 1820: 			goto out;
 1821: 		/*
 1822: 		 * We may have split the extent tree while toggling the state.
 1823: 		 * Try to shrink the extent tree now.
 1824: 		 */
 1825: 		ext4_ext_replay_shrink_inode(inode, start + len);
 1826: next:
 1827: 		cur += map.m_len;
 1828: 		remaining -= map.m_len;
 1829: 	}
 1830: 	ext4_ext_replay_shrink_inode(inode, i_size_read(inode) >>
 1831: 					sb->s_blocksize_bits);
 1832: out:
 1833: 	iput(inode);
 1834: 	return 0;
 1835: }
 1836: 
 1837: /* Replay DEL_RANGE tag */
 1838: static int
 1839: ext4_fc_replay_del_range(struct super_block *sb,
 1840: 			 struct ext4_fc_tl_mem *tl, u8 *val)
 1841: {
 1842: 	struct inode *inode;
 1843: 	struct ext4_fc_del_range lrange;
 1844: 	struct ext4_map_blocks map;
 1845: 	ext4_lblk_t cur, remaining;
 1846: 	int ret;
 1847: 
 1848: 	memcpy(&lrange, val, sizeof(lrange));
 1849: 	cur = le32_to_cpu(lrange.fc_lblk);
 1850: 	remaining = le32_to_cpu(lrange.fc_len);
 1851: 
 1852: 	trace_ext4_fc_replay(sb, EXT4_FC_TAG_DEL_RANGE,
 1853: 		le32_to_cpu(lrange.fc_ino), cur, remaining);
 1854: 
 1855: 	inode = ext4_iget(sb, le32_to_cpu(lrange.fc_ino), EXT4_IGET_NORMAL);
 1856: 	if (IS_ERR(inode)) {
 1857: 		ext4_debug("Inode %d not found", le32_to_cpu(lrange.fc_ino));
 1858: 		return 0;
 1859: 	}
 1860: 
 1861: 	ret = ext4_fc_record_modified_inode(sb, inode->i_ino);
 1862: 	if (ret)
 1863: 		goto out;
 1864: 
 1865: 	ext4_debug("DEL_RANGE, inode %ld, lblk %d, len %d\n",
 1866: 			inode->i_ino, le32_to_cpu(lrange.fc_lblk),
 1867: 			le32_to_cpu(lrange.fc_len));
 1868: 	while (remaining > 0) {
 1869: 		map.m_lblk = cur;
 1870: 		map.m_len = remaining;
 1871: 
 1872: 		ret = ext4_map_blocks(NULL, inode, &map, 0);
>1873: 		if (ret < 0)
 1874: 			goto out;
 1875: 		if (ret > 0) {
 1876: 			remaining -= ret;
 1877: 			cur += ret;
 1878: 			ext4_mb_mark_bb(inode->i_sb, map.m_pblk, map.m_len, false);
 1879: 		} else {
 1880: 			remaining -= map.m_len;
 1881: 			cur += map.m_len;
 1882: 		}
 1883: 	}
 1884: 
 1885: 	down_write(&EXT4_I(inode)->i_data_sem);
 1886: 	ret = ext4_ext_remove_space(inode, le32_to_cpu(lrange.fc_lblk),
 1887: 				le32_to_cpu(lrange.fc_lblk) +
 1888: 				le32_to_cpu(lrange.fc_len) - 1);
 1889: 	up_write(&EXT4_I(inode)->i_data_sem);
 1890: 	if (ret)
 1891: 		goto out;
 1892: 	ext4_ext_replay_shrink_inode(inode,
 1893: 		i_size_read(inode) >> sb->s_blocksize_bits);
 1894: 	ext4_mark_inode_dirty(NULL, inode);
 1895: out:
 1896: 	iput(inode);
 1897: 	return 0;
 1898: }
 1899: 
 1900: static void ext4_fc_set_bitmaps_and_counters(struct super_block *sb)
 1901: {
 1902: 	struct ext4_fc_replay_state *state;
 1903: 	struct inode *inode;
 1904: 	struct ext4_ext_path *path = NULL;
 1905: 	struct ext4_map_blocks map;
 1906: 	int i, ret, j;
 1907: 	ext4_lblk_t cur, end;
 1908: 
 1909: 	state = &EXT4_SB(sb)->s_fc_replay_state;
 1910: 	for (i = 0; i < state->fc_modified_inodes_used; i++) {
 1911: 		inode = ext4_iget(sb, state->fc_modified_inodes[i],
 1912: 			EXT4_IGET_NORMAL);
 1913: 		if (IS_ERR(inode)) {
 1914: 			ext4_debug("Inode %d not found.",
 1915: 				state->fc_modified_inodes[i]);
 1916: 			continue;
 1917: 		}
 1918: 		cur = 0;
 1919: 		end = EXT_MAX_BLOCKS;
 1920: 		if (ext4_test_inode_flag(inode, EXT4_INODE_INLINE_DATA)) {
 1921: 			iput(inode);
 1922: 			continue;
 1923: 		}
 1924: 		while (cur < end) {
 1925: 			map.m_lblk = cur;
 1926: 			map.m_len = end - cur;
 1927: 
 1928: 			ret = ext4_map_blocks(NULL, inode, &map, 0);
 1929: 			if (ret < 0)
 1930: 				break;
 1931: 
 1932: 			if (ret > 0) {
 1933: 				path = ext4_find_extent(inode, map.m_lblk, NULL, 0);
 1934: 				if (!IS_ERR(path)) {
 1935: 					for (j = 0; j < path->p_depth; j++)
 1936: 						ext4_mb_mark_bb(inode->i_sb,
 1937: 							path[j].p_block, 1, true);
 1938: 					ext4_free_ext_path(path);
 1939: 				}
 1940: 				cur += ret;
 1941: 				ext4_mb_mark_bb(inode->i_sb, map.m_pblk,
 1942: 							map.m_len, true);
 1943: 			} else {
 1944: 				cur = cur + (map.m_len ? map.m_len : 1);
 1945: 			}
 1946: 		}
 1947: 		iput(inode);
 1948: 	}
 1949: }
 1950: 
 1951: /*
 1952:  * Check if block is in excluded regions for block allocation. The simple
 1953:  * allocator that runs during replay phase is calls this function to see
```

## 8. candidate_9c191269f23a

- buckets: top_ranked
- score: 70 E1_LLM_TRUE_CANDIDATE
- type/severity: error_swallowed / P1
- location: fs/ext4/fast_commit.c::ext4_fc_replay_del_range:1890
- exception hints: False

- protocols: `[]`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'P1 severity +20', 'error_swallowed final return 0 +20']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_9c191269f23a",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 1810: 			goto next;
 1811: 		}
 1812: 
 1813: 		/* Range is mapped and needs a state change */
 1814: 		ext4_debug("Converting from %ld to %d %lld",
 1815: 				map.m_flags & EXT4_MAP_UNWRITTEN,
 1816: 			ext4_ext_is_unwritten(ex), map.m_pblk);
 1817: 		ret = ext4_ext_replay_update_ex(inode, cur, map.m_len,
 1818: 					ext4_ext_is_unwritten(ex), map.m_pblk);
 1819: 		if (ret)
 1820: 			goto out;
 1821: 		/*
 1822: 		 * We may have split the extent tree while toggling the state.
 1823: 		 * Try to shrink the extent tree now.
 1824: 		 */
 1825: 		ext4_ext_replay_shrink_inode(inode, start + len);
 1826: next:
 1827: 		cur += map.m_len;
 1828: 		remaining -= map.m_len;
 1829: 	}
 1830: 	ext4_ext_replay_shrink_inode(inode, i_size_read(inode) >>
 1831: 					sb->s_blocksize_bits);
 1832: out:
 1833: 	iput(inode);
 1834: 	return 0;
 1835: }
 1836: 
 1837: /* Replay DEL_RANGE tag */
 1838: static int
 1839: ext4_fc_replay_del_range(struct super_block *sb,
 1840: 			 struct ext4_fc_tl_mem *tl, u8 *val)
 1841: {
 1842: 	struct inode *inode;
 1843: 	struct ext4_fc_del_range lrange;
 1844: 	struct ext4_map_blocks map;
 1845: 	ext4_lblk_t cur, remaining;
 1846: 	int ret;
 1847: 
 1848: 	memcpy(&lrange, val, sizeof(lrange));
 1849: 	cur = le32_to_cpu(lrange.fc_lblk);
 1850: 	remaining = le32_to_cpu(lrange.fc_len);
 1851: 
 1852: 	trace_ext4_fc_replay(sb, EXT4_FC_TAG_DEL_RANGE,
 1853: 		le32_to_cpu(lrange.fc_ino), cur, remaining);
 1854: 
 1855: 	inode = ext4_iget(sb, le32_to_cpu(lrange.fc_ino), EXT4_IGET_NORMAL);
 1856: 	if (IS_ERR(inode)) {
 1857: 		ext4_debug("Inode %d not found", le32_to_cpu(lrange.fc_ino));
 1858: 		return 0;
 1859: 	}
 1860: 
 1861: 	ret = ext4_fc_record_modified_inode(sb, inode->i_ino);
 1862: 	if (ret)
 1863: 		goto out;
 1864: 
 1865: 	ext4_debug("DEL_RANGE, inode %ld, lblk %d, len %d\n",
 1866: 			inode->i_ino, le32_to_cpu(lrange.fc_lblk),
 1867: 			le32_to_cpu(lrange.fc_len));
 1868: 	while (remaining > 0) {
 1869: 		map.m_lblk = cur;
 1870: 		map.m_len = remaining;
 1871: 
 1872: 		ret = ext4_map_blocks(NULL, inode, &map, 0);
 1873: 		if (ret < 0)
 1874: 			goto out;
 1875: 		if (ret > 0) {
 1876: 			remaining -= ret;
 1877: 			cur += ret;
 1878: 			ext4_mb_mark_bb(inode->i_sb, map.m_pblk, map.m_len, false);
 1879: 		} else {
 1880: 			remaining -= map.m_len;
 1881: 			cur += map.m_len;
 1882: 		}
 1883: 	}
 1884: 
 1885: 	down_write(&EXT4_I(inode)->i_data_sem);
 1886: 	ret = ext4_ext_remove_space(inode, le32_to_cpu(lrange.fc_lblk),
 1887: 				le32_to_cpu(lrange.fc_lblk) +
 1888: 				le32_to_cpu(lrange.fc_len) - 1);
 1889: 	up_write(&EXT4_I(inode)->i_data_sem);
>1890: 	if (ret)
 1891: 		goto out;
 1892: 	ext4_ext_replay_shrink_inode(inode,
 1893: 		i_size_read(inode) >> sb->s_blocksize_bits);
 1894: 	ext4_mark_inode_dirty(NULL, inode);
 1895: out:
 1896: 	iput(inode);
 1897: 	return 0;
 1898: }
 1899: 
 1900: static void ext4_fc_set_bitmaps_and_counters(struct super_block *sb)
 1901: {
 1902: 	struct ext4_fc_replay_state *state;
 1903: 	struct inode *inode;
 1904: 	struct ext4_ext_path *path = NULL;
 1905: 	struct ext4_map_blocks map;
 1906: 	int i, ret, j;
 1907: 	ext4_lblk_t cur, end;
 1908: 
 1909: 	state = &EXT4_SB(sb)->s_fc_replay_state;
 1910: 	for (i = 0; i < state->fc_modified_inodes_used; i++) {
 1911: 		inode = ext4_iget(sb, state->fc_modified_inodes[i],
 1912: 			EXT4_IGET_NORMAL);
 1913: 		if (IS_ERR(inode)) {
 1914: 			ext4_debug("Inode %d not found.",
 1915: 				state->fc_modified_inodes[i]);
 1916: 			continue;
 1917: 		}
 1918: 		cur = 0;
 1919: 		end = EXT_MAX_BLOCKS;
 1920: 		if (ext4_test_inode_flag(inode, EXT4_INODE_INLINE_DATA)) {
 1921: 			iput(inode);
 1922: 			continue;
 1923: 		}
 1924: 		while (cur < end) {
 1925: 			map.m_lblk = cur;
 1926: 			map.m_len = end - cur;
 1927: 
 1928: 			ret = ext4_map_blocks(NULL, inode, &map, 0);
 1929: 			if (ret < 0)
 1930: 				break;
 1931: 
 1932: 			if (ret > 0) {
 1933: 				path = ext4_find_extent(inode, map.m_lblk, NULL, 0);
 1934: 				if (!IS_ERR(path)) {
 1935: 					for (j = 0; j < path->p_depth; j++)
 1936: 						ext4_mb_mark_bb(inode->i_sb,
 1937: 							path[j].p_block, 1, true);
 1938: 					ext4_free_ext_path(path);
 1939: 				}
 1940: 				cur += ret;
 1941: 				ext4_mb_mark_bb(inode->i_sb, map.m_pblk,
 1942: 							map.m_len, true);
 1943: 			} else {
 1944: 				cur = cur + (map.m_len ? map.m_len : 1);
 1945: 			}
 1946: 		}
 1947: 		iput(inode);
 1948: 	}
 1949: }
 1950: 
 1951: /*
 1952:  * Check if block is in excluded regions for block allocation. The simple
 1953:  * allocator that runs during replay phase is calls this function to see
 1954:  * if it is okay to use a block.
 1955:  */
 1956: bool ext4_fc_replay_check_excluded(struct super_block *sb, ext4_fsblk_t blk)
 1957: {
 1958: 	int i;
 1959: 	struct ext4_fc_replay_state *state;
 1960: 
 1961: 	state = &EXT4_SB(sb)->s_fc_replay_state;
 1962: 	for (i = 0; i < state->fc_regions_valid; i++) {
 1963: 		if (state->fc_regions[i].ino == 0 ||
 1964: 			state->fc_regions[i].len == 0)
 1965: 			continue;
 1966: 		if (in_range(blk, state->fc_regions[i].pblk,
 1967: 					state->fc_regions[i].len))
 1968: 			return true;
 1969: 	}
 1970: 	return false;
```

## 9. candidate_e99672f2009b

- buckets: top_ranked
- score: 70 E1_LLM_TRUE_CANDIDATE
- type/severity: error_swallowed / P1
- location: fs/ext4/fast_commit.c::ext4_fc_replay_inode:1542
- exception hints: False

- protocols: `[]`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'P1 severity +20', 'error_swallowed final return 0 +20']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_e99672f2009b",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 1462: static int ext4_fc_replay_link(struct super_block *sb,
 1463: 			       struct ext4_fc_tl_mem *tl, u8 *val)
 1464: {
 1465: 	struct inode *inode;
 1466: 	struct dentry_info_args darg;
 1467: 	int ret = 0;
 1468: 
 1469: 	tl_to_darg(&darg, tl, val);
 1470: 	trace_ext4_fc_replay(sb, EXT4_FC_TAG_LINK, darg.ino,
 1471: 			darg.parent_ino, darg.dname_len);
 1472: 
 1473: 	inode = ext4_iget(sb, darg.ino, EXT4_IGET_NORMAL);
 1474: 	if (IS_ERR(inode)) {
 1475: 		ext4_debug("Inode not found.");
 1476: 		return 0;
 1477: 	}
 1478: 
 1479: 	ret = ext4_fc_replay_link_internal(sb, &darg, inode);
 1480: 	iput(inode);
 1481: 	return ret;
 1482: }
 1483: 
 1484: /*
 1485:  * Record all the modified inodes during replay. We use this later to setup
 1486:  * block bitmaps correctly.
 1487:  */
 1488: static int ext4_fc_record_modified_inode(struct super_block *sb, int ino)
 1489: {
 1490: 	struct ext4_fc_replay_state *state;
 1491: 	int i;
 1492: 
 1493: 	state = &EXT4_SB(sb)->s_fc_replay_state;
 1494: 	for (i = 0; i < state->fc_modified_inodes_used; i++)
 1495: 		if (state->fc_modified_inodes[i] == ino)
 1496: 			return 0;
 1497: 	if (state->fc_modified_inodes_used == state->fc_modified_inodes_size) {
 1498: 		int *fc_modified_inodes;
 1499: 
 1500: 		fc_modified_inodes = krealloc(state->fc_modified_inodes,
 1501: 				sizeof(int) * (state->fc_modified_inodes_size +
 1502: 				EXT4_FC_REPLAY_REALLOC_INCREMENT),
 1503: 				GFP_KERNEL);
 1504: 		if (!fc_modified_inodes)
 1505: 			return -ENOMEM;
 1506: 		state->fc_modified_inodes = fc_modified_inodes;
 1507: 		state->fc_modified_inodes_size +=
 1508: 			EXT4_FC_REPLAY_REALLOC_INCREMENT;
 1509: 	}
 1510: 	state->fc_modified_inodes[state->fc_modified_inodes_used++] = ino;
 1511: 	return 0;
 1512: }
 1513: 
 1514: /*
 1515:  * Inode replay function
 1516:  */
 1517: static int ext4_fc_replay_inode(struct super_block *sb,
 1518: 				struct ext4_fc_tl_mem *tl, u8 *val)
 1519: {
 1520: 	struct ext4_fc_inode fc_inode;
 1521: 	struct ext4_inode *raw_inode;
 1522: 	struct ext4_inode *raw_fc_inode;
 1523: 	struct inode *inode = NULL;
 1524: 	struct ext4_iloc iloc;
 1525: 	int inode_len, ino, ret, tag = tl->fc_tag;
 1526: 	struct ext4_extent_header *eh;
 1527: 	size_t off_gen = offsetof(struct ext4_inode, i_generation);
 1528: 
 1529: 	memcpy(&fc_inode, val, sizeof(fc_inode));
 1530: 
 1531: 	ino = le32_to_cpu(fc_inode.fc_ino);
 1532: 	trace_ext4_fc_replay(sb, tag, ino, 0, 0);
 1533: 
 1534: 	inode = ext4_iget(sb, ino, EXT4_IGET_NORMAL);
 1535: 	if (!IS_ERR(inode)) {
 1536: 		ext4_ext_clear_bb(inode);
 1537: 		iput(inode);
 1538: 	}
 1539: 	inode = NULL;
 1540: 
 1541: 	ret = ext4_fc_record_modified_inode(sb, ino);
>1542: 	if (ret)
 1543: 		goto out;
 1544: 
 1545: 	raw_fc_inode = (struct ext4_inode *)
 1546: 		(val + offsetof(struct ext4_fc_inode, fc_raw_inode));
 1547: 	ret = ext4_get_fc_inode_loc(sb, ino, &iloc);
 1548: 	if (ret)
 1549: 		goto out;
 1550: 
 1551: 	inode_len = tl->fc_len - sizeof(struct ext4_fc_inode);
 1552: 	raw_inode = ext4_raw_inode(&iloc);
 1553: 
 1554: 	memcpy(raw_inode, raw_fc_inode, offsetof(struct ext4_inode, i_block));
 1555: 	memcpy((u8 *)raw_inode + off_gen, (u8 *)raw_fc_inode + off_gen,
 1556: 	       inode_len - off_gen);
 1557: 	if (le32_to_cpu(raw_inode->i_flags) & EXT4_EXTENTS_FL) {
 1558: 		eh = (struct ext4_extent_header *)(&raw_inode->i_block[0]);
 1559: 		if (eh->eh_magic != EXT4_EXT_MAGIC) {
 1560: 			memset(eh, 0, sizeof(*eh));
 1561: 			eh->eh_magic = EXT4_EXT_MAGIC;
 1562: 			eh->eh_max = cpu_to_le16(
 1563: 				(sizeof(raw_inode->i_block) -
 1564: 				 sizeof(struct ext4_extent_header))
 1565: 				 / sizeof(struct ext4_extent));
 1566: 		}
 1567: 	} else if (le32_to_cpu(raw_inode->i_flags) & EXT4_INLINE_DATA_FL) {
 1568: 		memcpy(raw_inode->i_block, raw_fc_inode->i_block,
 1569: 			sizeof(raw_inode->i_block));
 1570: 	}
 1571: 
 1572: 	/* Immediately update the inode on disk. */
 1573: 	ret = ext4_handle_dirty_metadata(NULL, NULL, iloc.bh);
 1574: 	if (ret)
 1575: 		goto out;
 1576: 	ret = sync_dirty_buffer(iloc.bh);
 1577: 	if (ret)
 1578: 		goto out;
 1579: 	ret = ext4_mark_inode_used(sb, ino);
 1580: 	if (ret)
 1581: 		goto out;
 1582: 
 1583: 	/* Given that we just wrote the inode on disk, this SHOULD succeed. */
 1584: 	inode = ext4_iget(sb, ino, EXT4_IGET_NORMAL);
 1585: 	if (IS_ERR(inode)) {
 1586: 		ext4_debug("Inode not found.");
 1587: 		return -EFSCORRUPTED;
 1588: 	}
 1589: 
 1590: 	/*
 1591: 	 * Our allocator could have made different decisions than before
 1592: 	 * crashing. This should be fixed but until then, we calculate
 1593: 	 * the number of blocks the inode.
 1594: 	 */
 1595: 	if (!ext4_test_inode_flag(inode, EXT4_INODE_INLINE_DATA))
 1596: 		ext4_ext_replay_set_iblocks(inode);
 1597: 
 1598: 	inode->i_generation = le32_to_cpu(ext4_raw_inode(&iloc)->i_generation);
 1599: 	ext4_reset_inode_seed(inode);
 1600: 
 1601: 	ext4_inode_csum_set(inode, ext4_raw_inode(&iloc), EXT4_I(inode));
 1602: 	ret = ext4_handle_dirty_metadata(NULL, NULL, iloc.bh);
 1603: 	sync_dirty_buffer(iloc.bh);
 1604: 	brelse(iloc.bh);
 1605: out:
 1606: 	iput(inode);
 1607: 	if (!ret)
 1608: 		blkdev_issue_flush(sb->s_bdev);
 1609: 
 1610: 	return 0;
 1611: }
 1612: 
 1613: /*
 1614:  * Dentry create replay function.
 1615:  *
 1616:  * EXT4_FC_TAG_CREAT is preceded by EXT4_FC_TAG_INODE_FULL. Which means, the
 1617:  * inode for which we are trying to create a dentry here, should already have
 1618:  * been replayed before we start here.
 1619:  */
 1620: static int ext4_fc_replay_create(struct super_block *sb,
 1621: 				 struct ext4_fc_tl_mem *tl, u8 *val)
 1622: {
```

## 10. candidate_41b034187f74

- buckets: top_ranked
- score: 70 E1_LLM_TRUE_CANDIDATE
- type/severity: error_swallowed / P1
- location: fs/ext4/fast_commit.c::ext4_fc_replay_inode:1548
- exception hints: False

- protocols: `[]`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'P1 severity +20', 'error_swallowed final return 0 +20']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_41b034187f74",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 1468: 
 1469: 	tl_to_darg(&darg, tl, val);
 1470: 	trace_ext4_fc_replay(sb, EXT4_FC_TAG_LINK, darg.ino,
 1471: 			darg.parent_ino, darg.dname_len);
 1472: 
 1473: 	inode = ext4_iget(sb, darg.ino, EXT4_IGET_NORMAL);
 1474: 	if (IS_ERR(inode)) {
 1475: 		ext4_debug("Inode not found.");
 1476: 		return 0;
 1477: 	}
 1478: 
 1479: 	ret = ext4_fc_replay_link_internal(sb, &darg, inode);
 1480: 	iput(inode);
 1481: 	return ret;
 1482: }
 1483: 
 1484: /*
 1485:  * Record all the modified inodes during replay. We use this later to setup
 1486:  * block bitmaps correctly.
 1487:  */
 1488: static int ext4_fc_record_modified_inode(struct super_block *sb, int ino)
 1489: {
 1490: 	struct ext4_fc_replay_state *state;
 1491: 	int i;
 1492: 
 1493: 	state = &EXT4_SB(sb)->s_fc_replay_state;
 1494: 	for (i = 0; i < state->fc_modified_inodes_used; i++)
 1495: 		if (state->fc_modified_inodes[i] == ino)
 1496: 			return 0;
 1497: 	if (state->fc_modified_inodes_used == state->fc_modified_inodes_size) {
 1498: 		int *fc_modified_inodes;
 1499: 
 1500: 		fc_modified_inodes = krealloc(state->fc_modified_inodes,
 1501: 				sizeof(int) * (state->fc_modified_inodes_size +
 1502: 				EXT4_FC_REPLAY_REALLOC_INCREMENT),
 1503: 				GFP_KERNEL);
 1504: 		if (!fc_modified_inodes)
 1505: 			return -ENOMEM;
 1506: 		state->fc_modified_inodes = fc_modified_inodes;
 1507: 		state->fc_modified_inodes_size +=
 1508: 			EXT4_FC_REPLAY_REALLOC_INCREMENT;
 1509: 	}
 1510: 	state->fc_modified_inodes[state->fc_modified_inodes_used++] = ino;
 1511: 	return 0;
 1512: }
 1513: 
 1514: /*
 1515:  * Inode replay function
 1516:  */
 1517: static int ext4_fc_replay_inode(struct super_block *sb,
 1518: 				struct ext4_fc_tl_mem *tl, u8 *val)
 1519: {
 1520: 	struct ext4_fc_inode fc_inode;
 1521: 	struct ext4_inode *raw_inode;
 1522: 	struct ext4_inode *raw_fc_inode;
 1523: 	struct inode *inode = NULL;
 1524: 	struct ext4_iloc iloc;
 1525: 	int inode_len, ino, ret, tag = tl->fc_tag;
 1526: 	struct ext4_extent_header *eh;
 1527: 	size_t off_gen = offsetof(struct ext4_inode, i_generation);
 1528: 
 1529: 	memcpy(&fc_inode, val, sizeof(fc_inode));
 1530: 
 1531: 	ino = le32_to_cpu(fc_inode.fc_ino);
 1532: 	trace_ext4_fc_replay(sb, tag, ino, 0, 0);
 1533: 
 1534: 	inode = ext4_iget(sb, ino, EXT4_IGET_NORMAL);
 1535: 	if (!IS_ERR(inode)) {
 1536: 		ext4_ext_clear_bb(inode);
 1537: 		iput(inode);
 1538: 	}
 1539: 	inode = NULL;
 1540: 
 1541: 	ret = ext4_fc_record_modified_inode(sb, ino);
 1542: 	if (ret)
 1543: 		goto out;
 1544: 
 1545: 	raw_fc_inode = (struct ext4_inode *)
 1546: 		(val + offsetof(struct ext4_fc_inode, fc_raw_inode));
 1547: 	ret = ext4_get_fc_inode_loc(sb, ino, &iloc);
>1548: 	if (ret)
 1549: 		goto out;
 1550: 
 1551: 	inode_len = tl->fc_len - sizeof(struct ext4_fc_inode);
 1552: 	raw_inode = ext4_raw_inode(&iloc);
 1553: 
 1554: 	memcpy(raw_inode, raw_fc_inode, offsetof(struct ext4_inode, i_block));
 1555: 	memcpy((u8 *)raw_inode + off_gen, (u8 *)raw_fc_inode + off_gen,
 1556: 	       inode_len - off_gen);
 1557: 	if (le32_to_cpu(raw_inode->i_flags) & EXT4_EXTENTS_FL) {
 1558: 		eh = (struct ext4_extent_header *)(&raw_inode->i_block[0]);
 1559: 		if (eh->eh_magic != EXT4_EXT_MAGIC) {
 1560: 			memset(eh, 0, sizeof(*eh));
 1561: 			eh->eh_magic = EXT4_EXT_MAGIC;
 1562: 			eh->eh_max = cpu_to_le16(
 1563: 				(sizeof(raw_inode->i_block) -
 1564: 				 sizeof(struct ext4_extent_header))
 1565: 				 / sizeof(struct ext4_extent));
 1566: 		}
 1567: 	} else if (le32_to_cpu(raw_inode->i_flags) & EXT4_INLINE_DATA_FL) {
 1568: 		memcpy(raw_inode->i_block, raw_fc_inode->i_block,
 1569: 			sizeof(raw_inode->i_block));
 1570: 	}
 1571: 
 1572: 	/* Immediately update the inode on disk. */
 1573: 	ret = ext4_handle_dirty_metadata(NULL, NULL, iloc.bh);
 1574: 	if (ret)
 1575: 		goto out;
 1576: 	ret = sync_dirty_buffer(iloc.bh);
 1577: 	if (ret)
 1578: 		goto out;
 1579: 	ret = ext4_mark_inode_used(sb, ino);
 1580: 	if (ret)
 1581: 		goto out;
 1582: 
 1583: 	/* Given that we just wrote the inode on disk, this SHOULD succeed. */
 1584: 	inode = ext4_iget(sb, ino, EXT4_IGET_NORMAL);
 1585: 	if (IS_ERR(inode)) {
 1586: 		ext4_debug("Inode not found.");
 1587: 		return -EFSCORRUPTED;
 1588: 	}
 1589: 
 1590: 	/*
 1591: 	 * Our allocator could have made different decisions than before
 1592: 	 * crashing. This should be fixed but until then, we calculate
 1593: 	 * the number of blocks the inode.
 1594: 	 */
 1595: 	if (!ext4_test_inode_flag(inode, EXT4_INODE_INLINE_DATA))
 1596: 		ext4_ext_replay_set_iblocks(inode);
 1597: 
 1598: 	inode->i_generation = le32_to_cpu(ext4_raw_inode(&iloc)->i_generation);
 1599: 	ext4_reset_inode_seed(inode);
 1600: 
 1601: 	ext4_inode_csum_set(inode, ext4_raw_inode(&iloc), EXT4_I(inode));
 1602: 	ret = ext4_handle_dirty_metadata(NULL, NULL, iloc.bh);
 1603: 	sync_dirty_buffer(iloc.bh);
 1604: 	brelse(iloc.bh);
 1605: out:
 1606: 	iput(inode);
 1607: 	if (!ret)
 1608: 		blkdev_issue_flush(sb->s_bdev);
 1609: 
 1610: 	return 0;
 1611: }
 1612: 
 1613: /*
 1614:  * Dentry create replay function.
 1615:  *
 1616:  * EXT4_FC_TAG_CREAT is preceded by EXT4_FC_TAG_INODE_FULL. Which means, the
 1617:  * inode for which we are trying to create a dentry here, should already have
 1618:  * been replayed before we start here.
 1619:  */
 1620: static int ext4_fc_replay_create(struct super_block *sb,
 1621: 				 struct ext4_fc_tl_mem *tl, u8 *val)
 1622: {
 1623: 	int ret = 0;
 1624: 	struct inode *inode = NULL;
 1625: 	struct inode *dir = NULL;
 1626: 	struct dentry_info_args darg;
 1627: 
 1628: 	tl_to_darg(&darg, tl, val);
```

## 11. candidate_265190733128

- buckets: top_ranked
- score: 70 E1_LLM_TRUE_CANDIDATE
- type/severity: error_swallowed / P1
- location: fs/ext4/fast_commit.c::ext4_fc_replay_inode:1574
- exception hints: False

- protocols: `[]`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'P1 severity +20', 'error_swallowed final return 0 +20']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_265190733128",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 1494: 	for (i = 0; i < state->fc_modified_inodes_used; i++)
 1495: 		if (state->fc_modified_inodes[i] == ino)
 1496: 			return 0;
 1497: 	if (state->fc_modified_inodes_used == state->fc_modified_inodes_size) {
 1498: 		int *fc_modified_inodes;
 1499: 
 1500: 		fc_modified_inodes = krealloc(state->fc_modified_inodes,
 1501: 				sizeof(int) * (state->fc_modified_inodes_size +
 1502: 				EXT4_FC_REPLAY_REALLOC_INCREMENT),
 1503: 				GFP_KERNEL);
 1504: 		if (!fc_modified_inodes)
 1505: 			return -ENOMEM;
 1506: 		state->fc_modified_inodes = fc_modified_inodes;
 1507: 		state->fc_modified_inodes_size +=
 1508: 			EXT4_FC_REPLAY_REALLOC_INCREMENT;
 1509: 	}
 1510: 	state->fc_modified_inodes[state->fc_modified_inodes_used++] = ino;
 1511: 	return 0;
 1512: }
 1513: 
 1514: /*
 1515:  * Inode replay function
 1516:  */
 1517: static int ext4_fc_replay_inode(struct super_block *sb,
 1518: 				struct ext4_fc_tl_mem *tl, u8 *val)
 1519: {
 1520: 	struct ext4_fc_inode fc_inode;
 1521: 	struct ext4_inode *raw_inode;
 1522: 	struct ext4_inode *raw_fc_inode;
 1523: 	struct inode *inode = NULL;
 1524: 	struct ext4_iloc iloc;
 1525: 	int inode_len, ino, ret, tag = tl->fc_tag;
 1526: 	struct ext4_extent_header *eh;
 1527: 	size_t off_gen = offsetof(struct ext4_inode, i_generation);
 1528: 
 1529: 	memcpy(&fc_inode, val, sizeof(fc_inode));
 1530: 
 1531: 	ino = le32_to_cpu(fc_inode.fc_ino);
 1532: 	trace_ext4_fc_replay(sb, tag, ino, 0, 0);
 1533: 
 1534: 	inode = ext4_iget(sb, ino, EXT4_IGET_NORMAL);
 1535: 	if (!IS_ERR(inode)) {
 1536: 		ext4_ext_clear_bb(inode);
 1537: 		iput(inode);
 1538: 	}
 1539: 	inode = NULL;
 1540: 
 1541: 	ret = ext4_fc_record_modified_inode(sb, ino);
 1542: 	if (ret)
 1543: 		goto out;
 1544: 
 1545: 	raw_fc_inode = (struct ext4_inode *)
 1546: 		(val + offsetof(struct ext4_fc_inode, fc_raw_inode));
 1547: 	ret = ext4_get_fc_inode_loc(sb, ino, &iloc);
 1548: 	if (ret)
 1549: 		goto out;
 1550: 
 1551: 	inode_len = tl->fc_len - sizeof(struct ext4_fc_inode);
 1552: 	raw_inode = ext4_raw_inode(&iloc);
 1553: 
 1554: 	memcpy(raw_inode, raw_fc_inode, offsetof(struct ext4_inode, i_block));
 1555: 	memcpy((u8 *)raw_inode + off_gen, (u8 *)raw_fc_inode + off_gen,
 1556: 	       inode_len - off_gen);
 1557: 	if (le32_to_cpu(raw_inode->i_flags) & EXT4_EXTENTS_FL) {
 1558: 		eh = (struct ext4_extent_header *)(&raw_inode->i_block[0]);
 1559: 		if (eh->eh_magic != EXT4_EXT_MAGIC) {
 1560: 			memset(eh, 0, sizeof(*eh));
 1561: 			eh->eh_magic = EXT4_EXT_MAGIC;
 1562: 			eh->eh_max = cpu_to_le16(
 1563: 				(sizeof(raw_inode->i_block) -
 1564: 				 sizeof(struct ext4_extent_header))
 1565: 				 / sizeof(struct ext4_extent));
 1566: 		}
 1567: 	} else if (le32_to_cpu(raw_inode->i_flags) & EXT4_INLINE_DATA_FL) {
 1568: 		memcpy(raw_inode->i_block, raw_fc_inode->i_block,
 1569: 			sizeof(raw_inode->i_block));
 1570: 	}
 1571: 
 1572: 	/* Immediately update the inode on disk. */
 1573: 	ret = ext4_handle_dirty_metadata(NULL, NULL, iloc.bh);
>1574: 	if (ret)
 1575: 		goto out;
 1576: 	ret = sync_dirty_buffer(iloc.bh);
 1577: 	if (ret)
 1578: 		goto out;
 1579: 	ret = ext4_mark_inode_used(sb, ino);
 1580: 	if (ret)
 1581: 		goto out;
 1582: 
 1583: 	/* Given that we just wrote the inode on disk, this SHOULD succeed. */
 1584: 	inode = ext4_iget(sb, ino, EXT4_IGET_NORMAL);
 1585: 	if (IS_ERR(inode)) {
 1586: 		ext4_debug("Inode not found.");
 1587: 		return -EFSCORRUPTED;
 1588: 	}
 1589: 
 1590: 	/*
 1591: 	 * Our allocator could have made different decisions than before
 1592: 	 * crashing. This should be fixed but until then, we calculate
 1593: 	 * the number of blocks the inode.
 1594: 	 */
 1595: 	if (!ext4_test_inode_flag(inode, EXT4_INODE_INLINE_DATA))
 1596: 		ext4_ext_replay_set_iblocks(inode);
 1597: 
 1598: 	inode->i_generation = le32_to_cpu(ext4_raw_inode(&iloc)->i_generation);
 1599: 	ext4_reset_inode_seed(inode);
 1600: 
 1601: 	ext4_inode_csum_set(inode, ext4_raw_inode(&iloc), EXT4_I(inode));
 1602: 	ret = ext4_handle_dirty_metadata(NULL, NULL, iloc.bh);
 1603: 	sync_dirty_buffer(iloc.bh);
 1604: 	brelse(iloc.bh);
 1605: out:
 1606: 	iput(inode);
 1607: 	if (!ret)
 1608: 		blkdev_issue_flush(sb->s_bdev);
 1609: 
 1610: 	return 0;
 1611: }
 1612: 
 1613: /*
 1614:  * Dentry create replay function.
 1615:  *
 1616:  * EXT4_FC_TAG_CREAT is preceded by EXT4_FC_TAG_INODE_FULL. Which means, the
 1617:  * inode for which we are trying to create a dentry here, should already have
 1618:  * been replayed before we start here.
 1619:  */
 1620: static int ext4_fc_replay_create(struct super_block *sb,
 1621: 				 struct ext4_fc_tl_mem *tl, u8 *val)
 1622: {
 1623: 	int ret = 0;
 1624: 	struct inode *inode = NULL;
 1625: 	struct inode *dir = NULL;
 1626: 	struct dentry_info_args darg;
 1627: 
 1628: 	tl_to_darg(&darg, tl, val);
 1629: 
 1630: 	trace_ext4_fc_replay(sb, EXT4_FC_TAG_CREAT, darg.ino,
 1631: 			darg.parent_ino, darg.dname_len);
 1632: 
 1633: 	/* This takes care of update group descriptor and other metadata */
 1634: 	ret = ext4_mark_inode_used(sb, darg.ino);
 1635: 	if (ret)
 1636: 		goto out;
 1637: 
 1638: 	inode = ext4_iget(sb, darg.ino, EXT4_IGET_NORMAL);
 1639: 	if (IS_ERR(inode)) {
 1640: 		ext4_debug("inode %d not found.", darg.ino);
 1641: 		inode = NULL;
 1642: 		ret = -EINVAL;
 1643: 		goto out;
 1644: 	}
 1645: 
 1646: 	if (S_ISDIR(inode->i_mode)) {
 1647: 		/*
 1648: 		 * If we are creating a directory, we need to make sure that the
 1649: 		 * dot and dot dot dirents are setup properly.
 1650: 		 */
 1651: 		dir = ext4_iget(sb, darg.parent_ino, EXT4_IGET_NORMAL);
 1652: 		if (IS_ERR(dir)) {
 1653: 			ext4_debug("Dir %d not found.", darg.ino);
 1654: 			goto out;
```

## 12. candidate_d50479b0e5bd

- buckets: top_ranked
- score: 70 E1_LLM_TRUE_CANDIDATE
- type/severity: error_swallowed / P1
- location: fs/ext4/fast_commit.c::ext4_fc_replay_inode:1577
- exception hints: False

- protocols: `[]`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'P1 severity +20', 'error_swallowed final return 0 +20']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_d50479b0e5bd",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 1497: 	if (state->fc_modified_inodes_used == state->fc_modified_inodes_size) {
 1498: 		int *fc_modified_inodes;
 1499: 
 1500: 		fc_modified_inodes = krealloc(state->fc_modified_inodes,
 1501: 				sizeof(int) * (state->fc_modified_inodes_size +
 1502: 				EXT4_FC_REPLAY_REALLOC_INCREMENT),
 1503: 				GFP_KERNEL);
 1504: 		if (!fc_modified_inodes)
 1505: 			return -ENOMEM;
 1506: 		state->fc_modified_inodes = fc_modified_inodes;
 1507: 		state->fc_modified_inodes_size +=
 1508: 			EXT4_FC_REPLAY_REALLOC_INCREMENT;
 1509: 	}
 1510: 	state->fc_modified_inodes[state->fc_modified_inodes_used++] = ino;
 1511: 	return 0;
 1512: }
 1513: 
 1514: /*
 1515:  * Inode replay function
 1516:  */
 1517: static int ext4_fc_replay_inode(struct super_block *sb,
 1518: 				struct ext4_fc_tl_mem *tl, u8 *val)
 1519: {
 1520: 	struct ext4_fc_inode fc_inode;
 1521: 	struct ext4_inode *raw_inode;
 1522: 	struct ext4_inode *raw_fc_inode;
 1523: 	struct inode *inode = NULL;
 1524: 	struct ext4_iloc iloc;
 1525: 	int inode_len, ino, ret, tag = tl->fc_tag;
 1526: 	struct ext4_extent_header *eh;
 1527: 	size_t off_gen = offsetof(struct ext4_inode, i_generation);
 1528: 
 1529: 	memcpy(&fc_inode, val, sizeof(fc_inode));
 1530: 
 1531: 	ino = le32_to_cpu(fc_inode.fc_ino);
 1532: 	trace_ext4_fc_replay(sb, tag, ino, 0, 0);
 1533: 
 1534: 	inode = ext4_iget(sb, ino, EXT4_IGET_NORMAL);
 1535: 	if (!IS_ERR(inode)) {
 1536: 		ext4_ext_clear_bb(inode);
 1537: 		iput(inode);
 1538: 	}
 1539: 	inode = NULL;
 1540: 
 1541: 	ret = ext4_fc_record_modified_inode(sb, ino);
 1542: 	if (ret)
 1543: 		goto out;
 1544: 
 1545: 	raw_fc_inode = (struct ext4_inode *)
 1546: 		(val + offsetof(struct ext4_fc_inode, fc_raw_inode));
 1547: 	ret = ext4_get_fc_inode_loc(sb, ino, &iloc);
 1548: 	if (ret)
 1549: 		goto out;
 1550: 
 1551: 	inode_len = tl->fc_len - sizeof(struct ext4_fc_inode);
 1552: 	raw_inode = ext4_raw_inode(&iloc);
 1553: 
 1554: 	memcpy(raw_inode, raw_fc_inode, offsetof(struct ext4_inode, i_block));
 1555: 	memcpy((u8 *)raw_inode + off_gen, (u8 *)raw_fc_inode + off_gen,
 1556: 	       inode_len - off_gen);
 1557: 	if (le32_to_cpu(raw_inode->i_flags) & EXT4_EXTENTS_FL) {
 1558: 		eh = (struct ext4_extent_header *)(&raw_inode->i_block[0]);
 1559: 		if (eh->eh_magic != EXT4_EXT_MAGIC) {
 1560: 			memset(eh, 0, sizeof(*eh));
 1561: 			eh->eh_magic = EXT4_EXT_MAGIC;
 1562: 			eh->eh_max = cpu_to_le16(
 1563: 				(sizeof(raw_inode->i_block) -
 1564: 				 sizeof(struct ext4_extent_header))
 1565: 				 / sizeof(struct ext4_extent));
 1566: 		}
 1567: 	} else if (le32_to_cpu(raw_inode->i_flags) & EXT4_INLINE_DATA_FL) {
 1568: 		memcpy(raw_inode->i_block, raw_fc_inode->i_block,
 1569: 			sizeof(raw_inode->i_block));
 1570: 	}
 1571: 
 1572: 	/* Immediately update the inode on disk. */
 1573: 	ret = ext4_handle_dirty_metadata(NULL, NULL, iloc.bh);
 1574: 	if (ret)
 1575: 		goto out;
 1576: 	ret = sync_dirty_buffer(iloc.bh);
>1577: 	if (ret)
 1578: 		goto out;
 1579: 	ret = ext4_mark_inode_used(sb, ino);
 1580: 	if (ret)
 1581: 		goto out;
 1582: 
 1583: 	/* Given that we just wrote the inode on disk, this SHOULD succeed. */
 1584: 	inode = ext4_iget(sb, ino, EXT4_IGET_NORMAL);
 1585: 	if (IS_ERR(inode)) {
 1586: 		ext4_debug("Inode not found.");
 1587: 		return -EFSCORRUPTED;
 1588: 	}
 1589: 
 1590: 	/*
 1591: 	 * Our allocator could have made different decisions than before
 1592: 	 * crashing. This should be fixed but until then, we calculate
 1593: 	 * the number of blocks the inode.
 1594: 	 */
 1595: 	if (!ext4_test_inode_flag(inode, EXT4_INODE_INLINE_DATA))
 1596: 		ext4_ext_replay_set_iblocks(inode);
 1597: 
 1598: 	inode->i_generation = le32_to_cpu(ext4_raw_inode(&iloc)->i_generation);
 1599: 	ext4_reset_inode_seed(inode);
 1600: 
 1601: 	ext4_inode_csum_set(inode, ext4_raw_inode(&iloc), EXT4_I(inode));
 1602: 	ret = ext4_handle_dirty_metadata(NULL, NULL, iloc.bh);
 1603: 	sync_dirty_buffer(iloc.bh);
 1604: 	brelse(iloc.bh);
 1605: out:
 1606: 	iput(inode);
 1607: 	if (!ret)
 1608: 		blkdev_issue_flush(sb->s_bdev);
 1609: 
 1610: 	return 0;
 1611: }
 1612: 
 1613: /*
 1614:  * Dentry create replay function.
 1615:  *
 1616:  * EXT4_FC_TAG_CREAT is preceded by EXT4_FC_TAG_INODE_FULL. Which means, the
 1617:  * inode for which we are trying to create a dentry here, should already have
 1618:  * been replayed before we start here.
 1619:  */
 1620: static int ext4_fc_replay_create(struct super_block *sb,
 1621: 				 struct ext4_fc_tl_mem *tl, u8 *val)
 1622: {
 1623: 	int ret = 0;
 1624: 	struct inode *inode = NULL;
 1625: 	struct inode *dir = NULL;
 1626: 	struct dentry_info_args darg;
 1627: 
 1628: 	tl_to_darg(&darg, tl, val);
 1629: 
 1630: 	trace_ext4_fc_replay(sb, EXT4_FC_TAG_CREAT, darg.ino,
 1631: 			darg.parent_ino, darg.dname_len);
 1632: 
 1633: 	/* This takes care of update group descriptor and other metadata */
 1634: 	ret = ext4_mark_inode_used(sb, darg.ino);
 1635: 	if (ret)
 1636: 		goto out;
 1637: 
 1638: 	inode = ext4_iget(sb, darg.ino, EXT4_IGET_NORMAL);
 1639: 	if (IS_ERR(inode)) {
 1640: 		ext4_debug("inode %d not found.", darg.ino);
 1641: 		inode = NULL;
 1642: 		ret = -EINVAL;
 1643: 		goto out;
 1644: 	}
 1645: 
 1646: 	if (S_ISDIR(inode->i_mode)) {
 1647: 		/*
 1648: 		 * If we are creating a directory, we need to make sure that the
 1649: 		 * dot and dot dot dirents are setup properly.
 1650: 		 */
 1651: 		dir = ext4_iget(sb, darg.parent_ino, EXT4_IGET_NORMAL);
 1652: 		if (IS_ERR(dir)) {
 1653: 			ext4_debug("Dir %d not found.", darg.ino);
 1654: 			goto out;
 1655: 		}
 1656: 		ret = ext4_init_new_dir(NULL, dir, inode);
 1657: 		iput(dir);
```

## 13. candidate_60ab69805414

- buckets: top_ranked
- score: 70 E1_LLM_TRUE_CANDIDATE
- type/severity: error_swallowed / P1
- location: fs/ext4/fast_commit.c::ext4_fc_replay_inode:1580
- exception hints: False

- protocols: `[]`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'P1 severity +20', 'error_swallowed final return 0 +20']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_60ab69805414",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 1500: 		fc_modified_inodes = krealloc(state->fc_modified_inodes,
 1501: 				sizeof(int) * (state->fc_modified_inodes_size +
 1502: 				EXT4_FC_REPLAY_REALLOC_INCREMENT),
 1503: 				GFP_KERNEL);
 1504: 		if (!fc_modified_inodes)
 1505: 			return -ENOMEM;
 1506: 		state->fc_modified_inodes = fc_modified_inodes;
 1507: 		state->fc_modified_inodes_size +=
 1508: 			EXT4_FC_REPLAY_REALLOC_INCREMENT;
 1509: 	}
 1510: 	state->fc_modified_inodes[state->fc_modified_inodes_used++] = ino;
 1511: 	return 0;
 1512: }
 1513: 
 1514: /*
 1515:  * Inode replay function
 1516:  */
 1517: static int ext4_fc_replay_inode(struct super_block *sb,
 1518: 				struct ext4_fc_tl_mem *tl, u8 *val)
 1519: {
 1520: 	struct ext4_fc_inode fc_inode;
 1521: 	struct ext4_inode *raw_inode;
 1522: 	struct ext4_inode *raw_fc_inode;
 1523: 	struct inode *inode = NULL;
 1524: 	struct ext4_iloc iloc;
 1525: 	int inode_len, ino, ret, tag = tl->fc_tag;
 1526: 	struct ext4_extent_header *eh;
 1527: 	size_t off_gen = offsetof(struct ext4_inode, i_generation);
 1528: 
 1529: 	memcpy(&fc_inode, val, sizeof(fc_inode));
 1530: 
 1531: 	ino = le32_to_cpu(fc_inode.fc_ino);
 1532: 	trace_ext4_fc_replay(sb, tag, ino, 0, 0);
 1533: 
 1534: 	inode = ext4_iget(sb, ino, EXT4_IGET_NORMAL);
 1535: 	if (!IS_ERR(inode)) {
 1536: 		ext4_ext_clear_bb(inode);
 1537: 		iput(inode);
 1538: 	}
 1539: 	inode = NULL;
 1540: 
 1541: 	ret = ext4_fc_record_modified_inode(sb, ino);
 1542: 	if (ret)
 1543: 		goto out;
 1544: 
 1545: 	raw_fc_inode = (struct ext4_inode *)
 1546: 		(val + offsetof(struct ext4_fc_inode, fc_raw_inode));
 1547: 	ret = ext4_get_fc_inode_loc(sb, ino, &iloc);
 1548: 	if (ret)
 1549: 		goto out;
 1550: 
 1551: 	inode_len = tl->fc_len - sizeof(struct ext4_fc_inode);
 1552: 	raw_inode = ext4_raw_inode(&iloc);
 1553: 
 1554: 	memcpy(raw_inode, raw_fc_inode, offsetof(struct ext4_inode, i_block));
 1555: 	memcpy((u8 *)raw_inode + off_gen, (u8 *)raw_fc_inode + off_gen,
 1556: 	       inode_len - off_gen);
 1557: 	if (le32_to_cpu(raw_inode->i_flags) & EXT4_EXTENTS_FL) {
 1558: 		eh = (struct ext4_extent_header *)(&raw_inode->i_block[0]);
 1559: 		if (eh->eh_magic != EXT4_EXT_MAGIC) {
 1560: 			memset(eh, 0, sizeof(*eh));
 1561: 			eh->eh_magic = EXT4_EXT_MAGIC;
 1562: 			eh->eh_max = cpu_to_le16(
 1563: 				(sizeof(raw_inode->i_block) -
 1564: 				 sizeof(struct ext4_extent_header))
 1565: 				 / sizeof(struct ext4_extent));
 1566: 		}
 1567: 	} else if (le32_to_cpu(raw_inode->i_flags) & EXT4_INLINE_DATA_FL) {
 1568: 		memcpy(raw_inode->i_block, raw_fc_inode->i_block,
 1569: 			sizeof(raw_inode->i_block));
 1570: 	}
 1571: 
 1572: 	/* Immediately update the inode on disk. */
 1573: 	ret = ext4_handle_dirty_metadata(NULL, NULL, iloc.bh);
 1574: 	if (ret)
 1575: 		goto out;
 1576: 	ret = sync_dirty_buffer(iloc.bh);
 1577: 	if (ret)
 1578: 		goto out;
 1579: 	ret = ext4_mark_inode_used(sb, ino);
>1580: 	if (ret)
 1581: 		goto out;
 1582: 
 1583: 	/* Given that we just wrote the inode on disk, this SHOULD succeed. */
 1584: 	inode = ext4_iget(sb, ino, EXT4_IGET_NORMAL);
 1585: 	if (IS_ERR(inode)) {
 1586: 		ext4_debug("Inode not found.");
 1587: 		return -EFSCORRUPTED;
 1588: 	}
 1589: 
 1590: 	/*
 1591: 	 * Our allocator could have made different decisions than before
 1592: 	 * crashing. This should be fixed but until then, we calculate
 1593: 	 * the number of blocks the inode.
 1594: 	 */
 1595: 	if (!ext4_test_inode_flag(inode, EXT4_INODE_INLINE_DATA))
 1596: 		ext4_ext_replay_set_iblocks(inode);
 1597: 
 1598: 	inode->i_generation = le32_to_cpu(ext4_raw_inode(&iloc)->i_generation);
 1599: 	ext4_reset_inode_seed(inode);
 1600: 
 1601: 	ext4_inode_csum_set(inode, ext4_raw_inode(&iloc), EXT4_I(inode));
 1602: 	ret = ext4_handle_dirty_metadata(NULL, NULL, iloc.bh);
 1603: 	sync_dirty_buffer(iloc.bh);
 1604: 	brelse(iloc.bh);
 1605: out:
 1606: 	iput(inode);
 1607: 	if (!ret)
 1608: 		blkdev_issue_flush(sb->s_bdev);
 1609: 
 1610: 	return 0;
 1611: }
 1612: 
 1613: /*
 1614:  * Dentry create replay function.
 1615:  *
 1616:  * EXT4_FC_TAG_CREAT is preceded by EXT4_FC_TAG_INODE_FULL. Which means, the
 1617:  * inode for which we are trying to create a dentry here, should already have
 1618:  * been replayed before we start here.
 1619:  */
 1620: static int ext4_fc_replay_create(struct super_block *sb,
 1621: 				 struct ext4_fc_tl_mem *tl, u8 *val)
 1622: {
 1623: 	int ret = 0;
 1624: 	struct inode *inode = NULL;
 1625: 	struct inode *dir = NULL;
 1626: 	struct dentry_info_args darg;
 1627: 
 1628: 	tl_to_darg(&darg, tl, val);
 1629: 
 1630: 	trace_ext4_fc_replay(sb, EXT4_FC_TAG_CREAT, darg.ino,
 1631: 			darg.parent_ino, darg.dname_len);
 1632: 
 1633: 	/* This takes care of update group descriptor and other metadata */
 1634: 	ret = ext4_mark_inode_used(sb, darg.ino);
 1635: 	if (ret)
 1636: 		goto out;
 1637: 
 1638: 	inode = ext4_iget(sb, darg.ino, EXT4_IGET_NORMAL);
 1639: 	if (IS_ERR(inode)) {
 1640: 		ext4_debug("inode %d not found.", darg.ino);
 1641: 		inode = NULL;
 1642: 		ret = -EINVAL;
 1643: 		goto out;
 1644: 	}
 1645: 
 1646: 	if (S_ISDIR(inode->i_mode)) {
 1647: 		/*
 1648: 		 * If we are creating a directory, we need to make sure that the
 1649: 		 * dot and dot dot dirents are setup properly.
 1650: 		 */
 1651: 		dir = ext4_iget(sb, darg.parent_ino, EXT4_IGET_NORMAL);
 1652: 		if (IS_ERR(dir)) {
 1653: 			ext4_debug("Dir %d not found.", darg.ino);
 1654: 			goto out;
 1655: 		}
 1656: 		ret = ext4_init_new_dir(NULL, dir, inode);
 1657: 		iput(dir);
 1658: 		if (ret) {
 1659: 			ret = 0;
 1660: 			goto out;
```

## 14. candidate_a5de3c80d9d3

- buckets: top_ranked
- score: 70 E2_API_PROTOCOL_SUPPORTED
- type/severity: partial_cleanup / P2
- location: fs/ext4/inode.c::ext4_truncate:4151
- exception hints: False

- protocols: `['lock.down_write.up_write']`
- score explanation: `['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P2 severity +10', 'journal or lock protocol violation without exception hints +20']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_a5de3c80d9d3",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 4071:  * ext4_truncate() to have another go.  So there will be instantiated blocks
 4072:  * to the right of the truncation point in a crashed ext4 filesystem.  But
 4073:  * that's fine - as long as they are linked from the inode, the post-crash
 4074:  * ext4_truncate() run will find them and release them.
 4075:  */
 4076: int ext4_truncate(struct inode *inode)
 4077: {
 4078: 	struct ext4_inode_info *ei = EXT4_I(inode);
 4079: 	unsigned int credits;
 4080: 	int err = 0, err2;
 4081: 	handle_t *handle;
 4082: 	struct address_space *mapping = inode->i_mapping;
 4083: 
 4084: 	/*
 4085: 	 * There is a possibility that we're either freeing the inode
 4086: 	 * or it's a completely new inode. In those cases we might not
 4087: 	 * have i_rwsem locked because it's not necessary.
 4088: 	 */
 4089: 	if (!(inode->i_state & (I_NEW|I_FREEING)))
 4090: 		WARN_ON(!inode_is_locked(inode));
 4091: 	trace_ext4_truncate_enter(inode);
 4092: 
 4093: 	if (!ext4_can_truncate(inode))
 4094: 		goto out_trace;
 4095: 
 4096: 	if (inode->i_size == 0 && !test_opt(inode->i_sb, NO_AUTO_DA_ALLOC))
 4097: 		ext4_set_inode_state(inode, EXT4_STATE_DA_ALLOC_CLOSE);
 4098: 
 4099: 	if (ext4_has_inline_data(inode)) {
 4100: 		int has_inline = 1;
 4101: 
 4102: 		err = ext4_inline_data_truncate(inode, &has_inline);
 4103: 		if (err || has_inline)
 4104: 			goto out_trace;
 4105: 	}
 4106: 
 4107: 	/* If we zero-out tail of the page, we have to create jinode for jbd2 */
 4108: 	if (inode->i_size & (inode->i_sb->s_blocksize - 1)) {
 4109: 		err = ext4_inode_attach_jinode(inode);
 4110: 		if (err)
 4111: 			goto out_trace;
 4112: 	}
 4113: 
 4114: 	if (ext4_test_inode_flag(inode, EXT4_INODE_EXTENTS))
 4115: 		credits = ext4_writepage_trans_blocks(inode);
 4116: 	else
 4117: 		credits = ext4_blocks_for_truncate(inode);
 4118: 
 4119: 	handle = ext4_journal_start(inode, EXT4_HT_TRUNCATE, credits);
 4120: 	if (IS_ERR(handle)) {
 4121: 		err = PTR_ERR(handle);
 4122: 		goto out_trace;
 4123: 	}
 4124: 
 4125: 	if (inode->i_size & (inode->i_sb->s_blocksize - 1))
 4126: 		ext4_block_truncate_page(handle, mapping, inode->i_size);
 4127: 
 4128: 	/*
 4129: 	 * We add the inode to the orphan list, so that if this
 4130: 	 * truncate spans multiple transactions, and we crash, we will
 4131: 	 * resume the truncate when the filesystem recovers.  It also
 4132: 	 * marks the inode dirty, to catch the new size.
 4133: 	 *
 4134: 	 * Implication: the file must always be in a sane, consistent
 4135: 	 * truncatable state while each transaction commits.
 4136: 	 */
 4137: 	err = ext4_orphan_add(handle, inode);
 4138: 	if (err)
 4139: 		goto out_stop;
 4140: 
 4141: 	down_write(&EXT4_I(inode)->i_data_sem);
 4142: 
 4143: 	ext4_discard_preallocations(inode);
 4144: 
 4145: 	if (ext4_test_inode_flag(inode, EXT4_INODE_EXTENTS))
 4146: 		err = ext4_ext_truncate(handle, inode);
 4147: 	else
 4148: 		ext4_ind_truncate(handle, inode);
 4149: 
 4150: 	up_write(&ei->i_data_sem);
>4151: 	if (err)
 4152: 		goto out_stop;
 4153: 
 4154: 	if (IS_SYNC(inode))
 4155: 		ext4_handle_sync(handle);
 4156: 
 4157: out_stop:
 4158: 	/*
 4159: 	 * If this was a simple ftruncate() and the file will remain alive,
 4160: 	 * then we need to clear up the orphan record which we created above.
 4161: 	 * However, if this was a real unlink then we were called by
 4162: 	 * ext4_evict_inode(), and we allow that function to clean up the
 4163: 	 * orphan info for us.
 4164: 	 */
 4165: 	if (inode->i_nlink)
 4166: 		ext4_orphan_del(handle, inode);
 4167: 
 4168: 	inode_set_mtime_to_ts(inode, inode_set_ctime_current(inode));
 4169: 	err2 = ext4_mark_inode_dirty(handle, inode);
 4170: 	if (unlikely(err2 && !err))
 4171: 		err = err2;
 4172: 	ext4_journal_stop(handle);
 4173: 
 4174: out_trace:
 4175: 	trace_ext4_truncate_exit(inode);
 4176: 	return err;
 4177: }
 4178: 
 4179: static inline u64 ext4_inode_peek_iversion(const struct inode *inode)
 4180: {
 4181: 	if (unlikely(EXT4_I(inode)->i_flags & EXT4_EA_INODE_FL))
 4182: 		return inode_peek_iversion_raw(inode);
 4183: 	else
 4184: 		return inode_peek_iversion(inode);
 4185: }
 4186: 
 4187: static int ext4_inode_blocks_set(struct ext4_inode *raw_inode,
 4188: 				 struct ext4_inode_info *ei)
 4189: {
 4190: 	struct inode *inode = &(ei->vfs_inode);
 4191: 	u64 i_blocks = READ_ONCE(inode->i_blocks);
 4192: 	struct super_block *sb = inode->i_sb;
 4193: 
 4194: 	if (i_blocks <= ~0U) {
 4195: 		/*
 4196: 		 * i_blocks can be represented in a 32 bit variable
 4197: 		 * as multiple of 512 bytes
 4198: 		 */
 4199: 		raw_inode->i_blocks_lo   = cpu_to_le32(i_blocks);
 4200: 		raw_inode->i_blocks_high = 0;
 4201: 		ext4_clear_inode_flag(inode, EXT4_INODE_HUGE_FILE);
 4202: 		return 0;
 4203: 	}
 4204: 
 4205: 	/*
 4206: 	 * This should never happen since sb->s_maxbytes should not have
 4207: 	 * allowed this, sb->s_maxbytes was set according to the huge_file
 4208: 	 * feature in ext4_fill_super().
 4209: 	 */
 4210: 	if (!ext4_has_feature_huge_file(sb))
 4211: 		return -EFSCORRUPTED;
 4212: 
 4213: 	if (i_blocks <= 0xffffffffffffULL) {
 4214: 		/*
 4215: 		 * i_blocks can be represented in a 48 bit variable
 4216: 		 * as multiple of 512 bytes
 4217: 		 */
 4218: 		raw_inode->i_blocks_lo   = cpu_to_le32(i_blocks);
 4219: 		raw_inode->i_blocks_high = cpu_to_le16(i_blocks >> 32);
 4220: 		ext4_clear_inode_flag(inode, EXT4_INODE_HUGE_FILE);
 4221: 	} else {
 4222: 		ext4_set_inode_flag(inode, EXT4_INODE_HUGE_FILE);
 4223: 		/* i_block is stored in file system block size */
 4224: 		i_blocks = i_blocks >> (inode->i_blkbits - 9);
 4225: 		raw_inode->i_blocks_lo   = cpu_to_le32(i_blocks);
 4226: 		raw_inode->i_blocks_high = cpu_to_le16(i_blocks >> 32);
 4227: 	}
 4228: 	return 0;
 4229: }
 4230: 
 4231: static int ext4_fill_raw_inode(struct inode *inode, struct ext4_inode *raw_inode)
```

## 15. candidate_1b062282df8b

- buckets: top_ranked
- score: 70 E1_LLM_TRUE_CANDIDATE
- type/severity: error_swallowed / P1
- location: fs/ext4/super.c::ext4_fill_flex_info:3205
- exception hints: False

- protocols: `[]`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'P1 severity +20', 'error_swallowed final return 0 +20']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_1b062282df8b",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 3125: 		ext4_set_feature_journal_needs_recovery(sb);
 3126: 		if (ext4_has_feature_orphan_file(sb))
 3127: 			ext4_set_feature_orphan_present(sb);
 3128: 	}
 3129: 
 3130: 	err = ext4_commit_super(sb);
 3131: done:
 3132: 	if (test_opt(sb, DEBUG))
 3133: 		printk(KERN_INFO "[EXT4 FS bs=%lu, gc=%u, "
 3134: 				"bpg=%lu, ipg=%lu, mo=%04x, mo2=%04x]\n",
 3135: 			sb->s_blocksize,
 3136: 			sbi->s_groups_count,
 3137: 			EXT4_BLOCKS_PER_GROUP(sb),
 3138: 			EXT4_INODES_PER_GROUP(sb),
 3139: 			sbi->s_mount_opt, sbi->s_mount_opt2);
 3140: 	return err;
 3141: }
 3142: 
 3143: int ext4_alloc_flex_bg_array(struct super_block *sb, ext4_group_t ngroup)
 3144: {
 3145: 	struct ext4_sb_info *sbi = EXT4_SB(sb);
 3146: 	struct flex_groups **old_groups, **new_groups;
 3147: 	int size, i, j;
 3148: 
 3149: 	if (!sbi->s_log_groups_per_flex)
 3150: 		return 0;
 3151: 
 3152: 	size = ext4_flex_group(sbi, ngroup - 1) + 1;
 3153: 	if (size <= sbi->s_flex_groups_allocated)
 3154: 		return 0;
 3155: 
 3156: 	new_groups = kvzalloc(roundup_pow_of_two(size *
 3157: 			      sizeof(*sbi->s_flex_groups)), GFP_KERNEL);
 3158: 	if (!new_groups) {
 3159: 		ext4_msg(sb, KERN_ERR,
 3160: 			 "not enough memory for %d flex group pointers", size);
 3161: 		return -ENOMEM;
 3162: 	}
 3163: 	for (i = sbi->s_flex_groups_allocated; i < size; i++) {
 3164: 		new_groups[i] = kvzalloc(roundup_pow_of_two(
 3165: 					 sizeof(struct flex_groups)),
 3166: 					 GFP_KERNEL);
 3167: 		if (!new_groups[i]) {
 3168: 			for (j = sbi->s_flex_groups_allocated; j < i; j++)
 3169: 				kvfree(new_groups[j]);
 3170: 			kvfree(new_groups);
 3171: 			ext4_msg(sb, KERN_ERR,
 3172: 				 "not enough memory for %d flex groups", size);
 3173: 			return -ENOMEM;
 3174: 		}
 3175: 	}
 3176: 	rcu_read_lock();
 3177: 	old_groups = rcu_dereference(sbi->s_flex_groups);
 3178: 	if (old_groups)
 3179: 		memcpy(new_groups, old_groups,
 3180: 		       (sbi->s_flex_groups_allocated *
 3181: 			sizeof(struct flex_groups *)));
 3182: 	rcu_read_unlock();
 3183: 	rcu_assign_pointer(sbi->s_flex_groups, new_groups);
 3184: 	sbi->s_flex_groups_allocated = size;
 3185: 	if (old_groups)
 3186: 		ext4_kvfree_array_rcu(old_groups);
 3187: 	return 0;
 3188: }
 3189: 
 3190: static int ext4_fill_flex_info(struct super_block *sb)
 3191: {
 3192: 	struct ext4_sb_info *sbi = EXT4_SB(sb);
 3193: 	struct ext4_group_desc *gdp = NULL;
 3194: 	struct flex_groups *fg;
 3195: 	ext4_group_t flex_group;
 3196: 	int i, err;
 3197: 
 3198: 	sbi->s_log_groups_per_flex = sbi->s_es->s_log_groups_per_flex;
 3199: 	if (sbi->s_log_groups_per_flex < 1 || sbi->s_log_groups_per_flex > 31) {
 3200: 		sbi->s_log_groups_per_flex = 0;
 3201: 		return 1;
 3202: 	}
 3203: 
 3204: 	err = ext4_alloc_flex_bg_array(sb, sbi->s_groups_count);
>3205: 	if (err)
 3206: 		goto failed;
 3207: 
 3208: 	for (i = 0; i < sbi->s_groups_count; i++) {
 3209: 		gdp = ext4_get_group_desc(sb, i, NULL);
 3210: 
 3211: 		flex_group = ext4_flex_group(sbi, i);
 3212: 		fg = sbi_array_rcu_deref(sbi, s_flex_groups, flex_group);
 3213: 		atomic_add(ext4_free_inodes_count(sb, gdp), &fg->free_inodes);
 3214: 		atomic64_add(ext4_free_group_clusters(sb, gdp),
 3215: 			     &fg->free_clusters);
 3216: 		atomic_add(ext4_used_dirs_count(sb, gdp), &fg->used_dirs);
 3217: 	}
 3218: 
 3219: 	return 1;
 3220: failed:
 3221: 	return 0;
 3222: }
 3223: 
 3224: static __le16 ext4_group_desc_csum(struct super_block *sb, __u32 block_group,
 3225: 				   struct ext4_group_desc *gdp)
 3226: {
 3227: 	int offset = offsetof(struct ext4_group_desc, bg_checksum);
 3228: 	__u16 crc = 0;
 3229: 	__le32 le_group = cpu_to_le32(block_group);
 3230: 	struct ext4_sb_info *sbi = EXT4_SB(sb);
 3231: 
 3232: 	if (ext4_has_metadata_csum(sbi->s_sb)) {
 3233: 		/* Use new metadata_csum algorithm */
 3234: 		__u32 csum32;
 3235: 		__u16 dummy_csum = 0;
 3236: 
 3237: 		csum32 = ext4_chksum(sbi, sbi->s_csum_seed, (__u8 *)&le_group,
 3238: 				     sizeof(le_group));
 3239: 		csum32 = ext4_chksum(sbi, csum32, (__u8 *)gdp, offset);
 3240: 		csum32 = ext4_chksum(sbi, csum32, (__u8 *)&dummy_csum,
 3241: 				     sizeof(dummy_csum));
 3242: 		offset += sizeof(dummy_csum);
 3243: 		if (offset < sbi->s_desc_size)
 3244: 			csum32 = ext4_chksum(sbi, csum32, (__u8 *)gdp + offset,
 3245: 					     sbi->s_desc_size - offset);
 3246: 
 3247: 		crc = csum32 & 0xFFFF;
 3248: 		goto out;
 3249: 	}
 3250: 
 3251: 	/* old crc16 code */
 3252: 	if (!ext4_has_feature_gdt_csum(sb))
 3253: 		return 0;
 3254: 
 3255: 	crc = crc16(~0, sbi->s_es->s_uuid, sizeof(sbi->s_es->s_uuid));
 3256: 	crc = crc16(crc, (__u8 *)&le_group, sizeof(le_group));
 3257: 	crc = crc16(crc, (__u8 *)gdp, offset);
 3258: 	offset += sizeof(gdp->bg_checksum); /* skip checksum */
 3259: 	/* for checksum of struct ext4_group_desc do the rest...*/
 3260: 	if (ext4_has_feature_64bit(sb) && offset < sbi->s_desc_size)
 3261: 		crc = crc16(crc, (__u8 *)gdp + offset,
 3262: 			    sbi->s_desc_size - offset);
 3263: 
 3264: out:
 3265: 	return cpu_to_le16(crc);
 3266: }
 3267: 
 3268: int ext4_group_desc_csum_verify(struct super_block *sb, __u32 block_group,
 3269: 				struct ext4_group_desc *gdp)
 3270: {
 3271: 	if (ext4_has_group_desc_csum(sb) &&
 3272: 	    (gdp->bg_checksum != ext4_group_desc_csum(sb, block_group, gdp)))
 3273: 		return 0;
 3274: 
 3275: 	return 1;
 3276: }
 3277: 
 3278: void ext4_group_desc_csum_set(struct super_block *sb, __u32 block_group,
 3279: 			      struct ext4_group_desc *gdp)
 3280: {
 3281: 	if (!ext4_has_group_desc_csum(sb))
 3282: 		return;
 3283: 	gdp->bg_checksum = ext4_group_desc_csum(sb, block_group, gdp);
 3284: }
 3285: 
```

## 16. candidate_2719ed2f6b80

- buckets: top_ranked
- score: 60 E2_API_PROTOCOL_SUPPORTED
- type/severity: missing_cleanup / P2
- location: fs/ext4/mballoc.c::ext4_mb_add_groupinfo:3341
- exception hints: False

- protocols: `['memory.kmalloc.kzalloc.kcalloc.kmem_cache_alloc.kfree']`
- score explanation: `['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P2 severity +10', 'buffer_head or memory protocol violation without exception hints +10']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_2719ed2f6b80",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
 3261: 
 3262: static struct kmem_cache *get_groupinfo_cache(int blocksize_bits)
 3263: {
 3264: 	int cache_index = blocksize_bits - EXT4_MIN_BLOCK_LOG_SIZE;
 3265: 	struct kmem_cache *cachep = ext4_groupinfo_caches[cache_index];
 3266: 
 3267: 	BUG_ON(!cachep);
 3268: 	return cachep;
 3269: }
 3270: 
 3271: /*
 3272:  * Allocate the top-level s_group_info array for the specified number
 3273:  * of groups
 3274:  */
 3275: int ext4_mb_alloc_groupinfo(struct super_block *sb, ext4_group_t ngroups)
 3276: {
 3277: 	struct ext4_sb_info *sbi = EXT4_SB(sb);
 3278: 	unsigned size;
 3279: 	struct ext4_group_info ***old_groupinfo, ***new_groupinfo;
 3280: 
 3281: 	size = (ngroups + EXT4_DESC_PER_BLOCK(sb) - 1) >>
 3282: 		EXT4_DESC_PER_BLOCK_BITS(sb);
 3283: 	if (size <= sbi->s_group_info_size)
 3284: 		return 0;
 3285: 
 3286: 	size = roundup_pow_of_two(sizeof(*sbi->s_group_info) * size);
 3287: 	new_groupinfo = kvzalloc(size, GFP_KERNEL);
 3288: 	if (!new_groupinfo) {
 3289: 		ext4_msg(sb, KERN_ERR, "can't allocate buddy meta group");
 3290: 		return -ENOMEM;
 3291: 	}
 3292: 	rcu_read_lock();
 3293: 	old_groupinfo = rcu_dereference(sbi->s_group_info);
 3294: 	if (old_groupinfo)
 3295: 		memcpy(new_groupinfo, old_groupinfo,
 3296: 		       sbi->s_group_info_size * sizeof(*sbi->s_group_info));
 3297: 	rcu_read_unlock();
 3298: 	rcu_assign_pointer(sbi->s_group_info, new_groupinfo);
 3299: 	sbi->s_group_info_size = size / sizeof(*sbi->s_group_info);
 3300: 	if (old_groupinfo)
 3301: 		ext4_kvfree_array_rcu(old_groupinfo);
 3302: 	ext4_debug("allocated s_groupinfo array for %d meta_bg's\n",
 3303: 		   sbi->s_group_info_size);
 3304: 	return 0;
 3305: }
 3306: 
 3307: /* Create and initialize ext4_group_info data for the given group. */
 3308: int ext4_mb_add_groupinfo(struct super_block *sb, ext4_group_t group,
 3309: 			  struct ext4_group_desc *desc)
 3310: {
 3311: 	int i;
 3312: 	int metalen = 0;
 3313: 	int idx = group >> EXT4_DESC_PER_BLOCK_BITS(sb);
 3314: 	struct ext4_sb_info *sbi = EXT4_SB(sb);
 3315: 	struct ext4_group_info **meta_group_info;
 3316: 	struct kmem_cache *cachep = get_groupinfo_cache(sb->s_blocksize_bits);
 3317: 
 3318: 	/*
 3319: 	 * First check if this group is the first of a reserved block.
 3320: 	 * If it's true, we have to allocate a new table of pointers
 3321: 	 * to ext4_group_info structures
 3322: 	 */
 3323: 	if (group % EXT4_DESC_PER_BLOCK(sb) == 0) {
 3324: 		metalen = sizeof(*meta_group_info) <<
 3325: 			EXT4_DESC_PER_BLOCK_BITS(sb);
 3326: 		meta_group_info = kmalloc(metalen, GFP_NOFS);
 3327: 		if (meta_group_info == NULL) {
 3328: 			ext4_msg(sb, KERN_ERR, "can't allocate mem "
 3329: 				 "for a buddy group");
 3330: 			return -ENOMEM;
 3331: 		}
 3332: 		rcu_read_lock();
 3333: 		rcu_dereference(sbi->s_group_info)[idx] = meta_group_info;
 3334: 		rcu_read_unlock();
 3335: 	}
 3336: 
 3337: 	meta_group_info = sbi_array_rcu_deref(sbi, s_group_info, idx);
 3338: 	i = group & (EXT4_DESC_PER_BLOCK(sb) - 1);
 3339: 
 3340: 	meta_group_info[i] = kmem_cache_zalloc(cachep, GFP_NOFS);
>3341: 	if (meta_group_info[i] == NULL) {
 3342: 		ext4_msg(sb, KERN_ERR, "can't allocate buddy mem");
 3343: 		goto exit_group_info;
 3344: 	}
 3345: 	set_bit(EXT4_GROUP_INFO_NEED_INIT_BIT,
 3346: 		&(meta_group_info[i]->bb_state));
 3347: 
 3348: 	/*
 3349: 	 * initialize bb_free to be able to skip
 3350: 	 * empty groups without initialization
 3351: 	 */
 3352: 	if (ext4_has_group_desc_csum(sb) &&
 3353: 	    (desc->bg_flags & cpu_to_le16(EXT4_BG_BLOCK_UNINIT))) {
 3354: 		meta_group_info[i]->bb_free =
 3355: 			ext4_free_clusters_after_init(sb, group, desc);
 3356: 	} else {
 3357: 		meta_group_info[i]->bb_free =
 3358: 			ext4_free_group_clusters(sb, desc);
 3359: 	}
 3360: 
 3361: 	INIT_LIST_HEAD(&meta_group_info[i]->bb_prealloc_list);
 3362: 	init_rwsem(&meta_group_info[i]->alloc_sem);
 3363: 	meta_group_info[i]->bb_free_root = RB_ROOT;
 3364: 	INIT_LIST_HEAD(&meta_group_info[i]->bb_largest_free_order_node);
 3365: 	INIT_LIST_HEAD(&meta_group_info[i]->bb_avg_fragment_size_node);
 3366: 	meta_group_info[i]->bb_largest_free_order = -1;  /* uninit */
 3367: 	meta_group_info[i]->bb_avg_fragment_size_order = -1;  /* uninit */
 3368: 	meta_group_info[i]->bb_group = group;
 3369: 
 3370: 	mb_group_bb_bitmap_alloc(sb, meta_group_info[i], group);
 3371: 	return 0;
 3372: 
 3373: exit_group_info:
 3374: 	/* If a meta_group_info table has been allocated, release it now */
 3375: 	if (group % EXT4_DESC_PER_BLOCK(sb) == 0) {
 3376: 		struct ext4_group_info ***group_info;
 3377: 
 3378: 		rcu_read_lock();
 3379: 		group_info = rcu_dereference(sbi->s_group_info);
 3380: 		kfree(group_info[idx]);
 3381: 		group_info[idx] = NULL;
 3382: 		rcu_read_unlock();
 3383: 	}
 3384: 	return -ENOMEM;
 3385: } /* ext4_mb_add_groupinfo */
 3386: 
 3387: static int ext4_mb_init_backend(struct super_block *sb)
 3388: {
 3389: 	ext4_group_t ngroups = ext4_get_groups_count(sb);
 3390: 	ext4_group_t i;
 3391: 	struct ext4_sb_info *sbi = EXT4_SB(sb);
 3392: 	int err;
 3393: 	struct ext4_group_desc *desc;
 3394: 	struct ext4_group_info ***group_info;
 3395: 	struct kmem_cache *cachep;
 3396: 
 3397: 	err = ext4_mb_alloc_groupinfo(sb, ngroups);
 3398: 	if (err)
 3399: 		return err;
 3400: 
 3401: 	sbi->s_buddy_cache = new_inode(sb);
 3402: 	if (sbi->s_buddy_cache == NULL) {
 3403: 		ext4_msg(sb, KERN_ERR, "can't get new inode");
 3404: 		goto err_freesgi;
 3405: 	}
 3406: 	/* To avoid potentially colliding with an valid on-disk inode number,
 3407: 	 * use EXT4_BAD_INO for the buddy cache inode number.  This inode is
 3408: 	 * not in the inode hash, so it should never be found by iget(), but
 3409: 	 * this will avoid confusion if it ever shows up during debugging. */
 3410: 	sbi->s_buddy_cache->i_ino = EXT4_BAD_INO;
 3411: 	EXT4_I(sbi->s_buddy_cache)->i_disksize = 0;
 3412: 	for (i = 0; i < ngroups; i++) {
 3413: 		cond_resched();
 3414: 		desc = ext4_get_group_desc(sb, i, NULL);
 3415: 		if (desc == NULL) {
 3416: 			ext4_msg(sb, KERN_ERR, "can't read descriptor %u", i);
 3417: 			goto err_freebuddy;
 3418: 		}
 3419: 		if (ext4_mb_add_groupinfo(sb, i, desc) != 0)
 3420: 			goto err_freebuddy;
 3421: 	}
```

## 17. candidate_1ddf7a965135

- buckets: top_ranked
- score: 60 E2_API_PROTOCOL_SUPPORTED
- type/severity: missing_cleanup / P2
- location: fs/ext4/namei.c::__ext4_read_dirblock:154
- exception hints: False

- protocols: `['buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse']`
- score explanation: `['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P2 severity +10', 'buffer_head or memory protocol violation without exception hints +10']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_1ddf7a965135",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
   74: 	 */
   75: 	err = ext4_map_blocks(NULL, inode, &map, 0);
   76: 	if (err < 0)
   77: 		return ERR_PTR(err);
   78: 	if (err) {
   79: 		EXT4_ERROR_INODE(inode, "Logical block already allocated");
   80: 		return ERR_PTR(-EFSCORRUPTED);
   81: 	}
   82: 
   83: 	bh = ext4_bread(handle, inode, *block, EXT4_GET_BLOCKS_CREATE);
   84: 	if (IS_ERR(bh))
   85: 		return bh;
   86: 	inode->i_size += inode->i_sb->s_blocksize;
   87: 	EXT4_I(inode)->i_disksize = inode->i_size;
   88: 	err = ext4_mark_inode_dirty(handle, inode);
   89: 	if (err)
   90: 		goto out;
   91: 	BUFFER_TRACE(bh, "get_write_access");
   92: 	err = ext4_journal_get_write_access(handle, inode->i_sb, bh,
   93: 					    EXT4_JTR_NONE);
   94: 	if (err)
   95: 		goto out;
   96: 	return bh;
   97: 
   98: out:
   99: 	brelse(bh);
  100: 	ext4_std_error(inode->i_sb, err);
  101: 	return ERR_PTR(err);
  102: }
  103: 
  104: static int ext4_dx_csum_verify(struct inode *inode,
  105: 			       struct ext4_dir_entry *dirent);
  106: 
  107: /*
  108:  * Hints to ext4_read_dirblock regarding whether we expect a directory
  109:  * block being read to be an index block, or a block containing
  110:  * directory entries (and if the latter, whether it was found via a
  111:  * logical block in an htree index block).  This is used to control
  112:  * what sort of sanity checkinig ext4_read_dirblock() will do on the
  113:  * directory block read from the storage device.  EITHER will means
  114:  * the caller doesn't know what kind of directory block will be read,
  115:  * so no specific verification will be done.
  116:  */
  117: typedef enum {
  118: 	EITHER, INDEX, DIRENT, DIRENT_HTREE
  119: } dirblock_type_t;
  120: 
  121: #define ext4_read_dirblock(inode, block, type) \
  122: 	__ext4_read_dirblock((inode), (block), (type), __func__, __LINE__)
  123: 
  124: static struct buffer_head *__ext4_read_dirblock(struct inode *inode,
  125: 						ext4_lblk_t block,
  126: 						dirblock_type_t type,
  127: 						const char *func,
  128: 						unsigned int line)
  129: {
  130: 	struct buffer_head *bh;
  131: 	struct ext4_dir_entry *dirent;
  132: 	int is_dx_block = 0;
  133: 
  134: 	if (block >= inode->i_size >> inode->i_blkbits) {
  135: 		ext4_error_inode(inode, func, line, block,
  136: 		       "Attempting to read directory block (%u) that is past i_size (%llu)",
  137: 		       block, inode->i_size);
  138: 		return ERR_PTR(-EFSCORRUPTED);
  139: 	}
  140: 
  141: 	if (ext4_simulate_fail(inode->i_sb, EXT4_SIM_DIRBLOCK_EIO))
  142: 		bh = ERR_PTR(-EIO);
  143: 	else
  144: 		bh = ext4_bread(NULL, inode, block, 0);
  145: 	if (IS_ERR(bh)) {
  146: 		__ext4_warning(inode->i_sb, func, line,
  147: 			       "inode #%lu: lblock %lu: comm %s: "
  148: 			       "error %ld reading directory block",
  149: 			       inode->i_ino, (unsigned long)block,
  150: 			       current->comm, PTR_ERR(bh));
  151: 
  152: 		return bh;
  153: 	}
> 154: 	if (!bh && (type == INDEX || type == DIRENT_HTREE)) {
  155: 		ext4_error_inode(inode, func, line, block,
  156: 				 "Directory hole found for htree %s block",
  157: 				 (type == INDEX) ? "index" : "leaf");
  158: 		return ERR_PTR(-EFSCORRUPTED);
  159: 	}
  160: 	if (!bh)
  161: 		return NULL;
  162: 	dirent = (struct ext4_dir_entry *) bh->b_data;
  163: 	/* Determine whether or not we have an index block */
  164: 	if (is_dx(inode)) {
  165: 		if (block == 0)
  166: 			is_dx_block = 1;
  167: 		else if (ext4_rec_len_from_disk(dirent->rec_len,
  168: 						inode->i_sb->s_blocksize) ==
  169: 			 inode->i_sb->s_blocksize)
  170: 			is_dx_block = 1;
  171: 	}
  172: 	if (!is_dx_block && type == INDEX) {
  173: 		ext4_error_inode(inode, func, line, block,
  174: 		       "directory leaf block found instead of index block");
  175: 		brelse(bh);
  176: 		return ERR_PTR(-EFSCORRUPTED);
  177: 	}
  178: 	if (!ext4_has_metadata_csum(inode->i_sb) ||
  179: 	    buffer_verified(bh))
  180: 		return bh;
  181: 
  182: 	/*
  183: 	 * An empty leaf block can get mistaken for a index block; for
  184: 	 * this reason, we can only check the index checksum when the
  185: 	 * caller is sure it should be an index block.
  186: 	 */
  187: 	if (is_dx_block && type == INDEX) {
  188: 		if (ext4_dx_csum_verify(inode, dirent) &&
  189: 		    !ext4_simulate_fail(inode->i_sb, EXT4_SIM_DIRBLOCK_CRC))
  190: 			set_buffer_verified(bh);
  191: 		else {
  192: 			ext4_error_inode_err(inode, func, line, block,
  193: 					     EFSBADCRC,
  194: 					     "Directory index failed checksum");
  195: 			brelse(bh);
  196: 			return ERR_PTR(-EFSBADCRC);
  197: 		}
  198: 	}
  199: 	if (!is_dx_block) {
  200: 		if (ext4_dirblock_csum_verify(inode, bh) &&
  201: 		    !ext4_simulate_fail(inode->i_sb, EXT4_SIM_DIRBLOCK_CRC))
  202: 			set_buffer_verified(bh);
  203: 		else {
  204: 			ext4_error_inode_err(inode, func, line, block,
  205: 					     EFSBADCRC,
  206: 					     "Directory block failed checksum");
  207: 			brelse(bh);
  208: 			return ERR_PTR(-EFSBADCRC);
  209: 		}
  210: 	}
  211: 	return bh;
  212: }
  213: 
  214: #ifdef DX_DEBUG
  215: #define dxtrace(command) command
  216: #else
  217: #define dxtrace(command)
  218: #endif
  219: 
  220: struct fake_dirent
  221: {
  222: 	__le32 inode;
  223: 	__le16 rec_len;
  224: 	u8 name_len;
  225: 	u8 file_type;
  226: };
  227: 
  228: struct dx_countlimit
  229: {
  230: 	__le16 limit;
  231: 	__le16 count;
  232: };
  233: 
  234: struct dx_entry
```

## 18. candidate_22778481313c

- buckets: top_ranked
- score: 60 E2_API_PROTOCOL_SUPPORTED
- type/severity: missing_cleanup / P2
- location: fs/ext4/orphan.c::ext4_init_orphan_info:601
- exception hints: False

- protocols: `['buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse']`
- score explanation: `['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P2 severity +10', 'buffer_head or memory protocol violation without exception hints +10']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_22778481313c",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
  521: }
  522: 
  523: static struct ext4_orphan_block_tail *ext4_orphan_block_tail(
  524: 						struct super_block *sb,
  525: 						struct buffer_head *bh)
  526: {
  527: 	return (struct ext4_orphan_block_tail *)(bh->b_data + sb->s_blocksize -
  528: 				sizeof(struct ext4_orphan_block_tail));
  529: }
  530: 
  531: static int ext4_orphan_file_block_csum_verify(struct super_block *sb,
  532: 					      struct buffer_head *bh)
  533: {
  534: 	__u32 calculated;
  535: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  536: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  537: 	struct ext4_orphan_block_tail *ot;
  538: 	__le64 dsk_block_nr = cpu_to_le64(bh->b_blocknr);
  539: 
  540: 	if (!ext4_has_metadata_csum(sb))
  541: 		return 1;
  542: 
  543: 	ot = ext4_orphan_block_tail(sb, bh);
  544: 	calculated = ext4_chksum(EXT4_SB(sb), oi->of_csum_seed,
  545: 				 (__u8 *)&dsk_block_nr, sizeof(dsk_block_nr));
  546: 	calculated = ext4_chksum(EXT4_SB(sb), calculated, (__u8 *)bh->b_data,
  547: 				 inodes_per_ob * sizeof(__u32));
  548: 	return le32_to_cpu(ot->ob_checksum) == calculated;
  549: }
  550: 
  551: /* This gets called only when checksumming is enabled */
  552: void ext4_orphan_file_block_trigger(struct jbd2_buffer_trigger_type *triggers,
  553: 				    struct buffer_head *bh,
  554: 				    void *data, size_t size)
  555: {
  556: 	struct super_block *sb = EXT4_TRIGGER(triggers)->sb;
  557: 	__u32 csum;
  558: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  559: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  560: 	struct ext4_orphan_block_tail *ot;
  561: 	__le64 dsk_block_nr = cpu_to_le64(bh->b_blocknr);
  562: 
  563: 	csum = ext4_chksum(EXT4_SB(sb), oi->of_csum_seed,
  564: 			   (__u8 *)&dsk_block_nr, sizeof(dsk_block_nr));
  565: 	csum = ext4_chksum(EXT4_SB(sb), csum, (__u8 *)data,
  566: 			   inodes_per_ob * sizeof(__u32));
  567: 	ot = ext4_orphan_block_tail(sb, bh);
  568: 	ot->ob_checksum = cpu_to_le32(csum);
  569: }
  570: 
  571: int ext4_init_orphan_info(struct super_block *sb)
  572: {
  573: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  574: 	struct inode *inode;
  575: 	int i, j;
  576: 	int ret;
  577: 	int free;
  578: 	__le32 *bdata;
  579: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  580: 	struct ext4_orphan_block_tail *ot;
  581: 	ino_t orphan_ino = le32_to_cpu(EXT4_SB(sb)->s_es->s_orphan_file_inum);
  582: 
  583: 	if (!ext4_has_feature_orphan_file(sb))
  584: 		return 0;
  585: 
  586: 	inode = ext4_iget(sb, orphan_ino, EXT4_IGET_SPECIAL);
  587: 	if (IS_ERR(inode)) {
  588: 		ext4_msg(sb, KERN_ERR, "get orphan inode failed");
  589: 		return PTR_ERR(inode);
  590: 	}
  591: 	oi->of_blocks = inode->i_size >> sb->s_blocksize_bits;
  592: 	oi->of_csum_seed = EXT4_I(inode)->i_csum_seed;
  593: 	oi->of_binfo = kmalloc(oi->of_blocks*sizeof(struct ext4_orphan_block),
  594: 			       GFP_KERNEL);
  595: 	if (!oi->of_binfo) {
  596: 		ret = -ENOMEM;
  597: 		goto out_put;
  598: 	}
  599: 	for (i = 0; i < oi->of_blocks; i++) {
  600: 		oi->of_binfo[i].ob_bh = ext4_bread(NULL, inode, i, 0);
> 601: 		if (IS_ERR(oi->of_binfo[i].ob_bh)) {
  602: 			ret = PTR_ERR(oi->of_binfo[i].ob_bh);
  603: 			goto out_free;
  604: 		}
  605: 		if (!oi->of_binfo[i].ob_bh) {
  606: 			ret = -EIO;
  607: 			goto out_free;
  608: 		}
  609: 		ot = ext4_orphan_block_tail(sb, oi->of_binfo[i].ob_bh);
  610: 		if (le32_to_cpu(ot->ob_magic) != EXT4_ORPHAN_BLOCK_MAGIC) {
  611: 			ext4_error(sb, "orphan file block %d: bad magic", i);
  612: 			ret = -EIO;
  613: 			goto out_free;
  614: 		}
  615: 		if (!ext4_orphan_file_block_csum_verify(sb,
  616: 						oi->of_binfo[i].ob_bh)) {
  617: 			ext4_error(sb, "orphan file block %d: bad checksum", i);
  618: 			ret = -EIO;
  619: 			goto out_free;
  620: 		}
  621: 		bdata = (__le32 *)(oi->of_binfo[i].ob_bh->b_data);
  622: 		free = 0;
  623: 		for (j = 0; j < inodes_per_ob; j++)
  624: 			if (bdata[j] == 0)
  625: 				free++;
  626: 		atomic_set(&oi->of_binfo[i].ob_free_entries, free);
  627: 	}
  628: 	iput(inode);
  629: 	return 0;
  630: out_free:
  631: 	for (i--; i >= 0; i--)
  632: 		brelse(oi->of_binfo[i].ob_bh);
  633: 	kfree(oi->of_binfo);
  634: out_put:
  635: 	iput(inode);
  636: 	return ret;
  637: }
  638: 
  639: int ext4_orphan_file_empty(struct super_block *sb)
  640: {
  641: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  642: 	int i;
  643: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  644: 
  645: 	if (!ext4_has_feature_orphan_file(sb))
  646: 		return 1;
  647: 	for (i = 0; i < oi->of_blocks; i++)
  648: 		if (atomic_read(&oi->of_binfo[i].ob_free_entries) !=
  649: 		    inodes_per_ob)
  650: 			return 0;
  651: 	return 1;
  652: }
```

## 19. candidate_cbcf25d392dd

- buckets: top_ranked
- score: 60 E2_API_PROTOCOL_SUPPORTED
- type/severity: missing_cleanup / P2
- location: fs/ext4/symlink.c::ext4_get_link:95
- exception hints: False

- protocols: `['buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse']`
- score explanation: `['E0 static rule base +10', 'E2 API protocol support without exception hints +30', 'P2 severity +10', 'buffer_head or memory protocol violation without exception hints +10']`
- exception_hints: `[]`

Label template:

```json
{
  "candidate_id": "candidate_cbcf25d392dd",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
   15:  *
   16:  *  Copyright (C) 1991, 1992  Linus Torvalds
   17:  *
   18:  *  ext4 symlink handling code
   19:  */
   20: 
   21: #include <linux/fs.h>
   22: #include <linux/namei.h>
   23: #include "ext4.h"
   24: #include "xattr.h"
   25: 
   26: static const char *ext4_encrypted_get_link(struct dentry *dentry,
   27: 					   struct inode *inode,
   28: 					   struct delayed_call *done)
   29: {
   30: 	struct buffer_head *bh = NULL;
   31: 	const void *caddr;
   32: 	unsigned int max_size;
   33: 	const char *paddr;
   34: 
   35: 	if (!dentry)
   36: 		return ERR_PTR(-ECHILD);
   37: 
   38: 	if (ext4_inode_is_fast_symlink(inode)) {
   39: 		caddr = EXT4_I(inode)->i_data;
   40: 		max_size = sizeof(EXT4_I(inode)->i_data);
   41: 	} else {
   42: 		bh = ext4_bread(NULL, inode, 0, 0);
   43: 		if (IS_ERR(bh))
   44: 			return ERR_CAST(bh);
   45: 		if (!bh) {
   46: 			EXT4_ERROR_INODE(inode, "bad symlink.");
   47: 			return ERR_PTR(-EFSCORRUPTED);
   48: 		}
   49: 		caddr = bh->b_data;
   50: 		max_size = inode->i_sb->s_blocksize;
   51: 	}
   52: 
   53: 	paddr = fscrypt_get_symlink(inode, caddr, max_size, done);
   54: 	brelse(bh);
   55: 	return paddr;
   56: }
   57: 
   58: static int ext4_encrypted_symlink_getattr(struct mnt_idmap *idmap,
   59: 					  const struct path *path,
   60: 					  struct kstat *stat, u32 request_mask,
   61: 					  unsigned int query_flags)
   62: {
   63: 	ext4_getattr(idmap, path, stat, request_mask, query_flags);
   64: 
   65: 	return fscrypt_symlink_getattr(path, stat);
   66: }
   67: 
   68: static void ext4_free_link(void *bh)
   69: {
   70: 	brelse(bh);
   71: }
   72: 
   73: static const char *ext4_get_link(struct dentry *dentry, struct inode *inode,
   74: 				 struct delayed_call *callback)
   75: {
   76: 	struct buffer_head *bh;
   77: 	char *inline_link;
   78: 
   79: 	/*
   80: 	 * Create a new inlined symlink is not supported, just provide a
   81: 	 * method to read the leftovers.
   82: 	 */
   83: 	if (ext4_has_inline_data(inode)) {
   84: 		if (!dentry)
   85: 			return ERR_PTR(-ECHILD);
   86: 
   87: 		inline_link = ext4_read_inline_link(inode);
   88: 		if (!IS_ERR(inline_link))
   89: 			set_delayed_call(callback, kfree_link, inline_link);
   90: 		return inline_link;
   91: 	}
   92: 
   93: 	if (!dentry) {
   94: 		bh = ext4_getblk(NULL, inode, 0, EXT4_GET_BLOCKS_CACHED_NOWAIT);
>  95: 		if (IS_ERR(bh) || !bh)
   96: 			return ERR_PTR(-ECHILD);
   97: 		if (!ext4_buffer_uptodate(bh)) {
   98: 			brelse(bh);
   99: 			return ERR_PTR(-ECHILD);
  100: 		}
  101: 	} else {
  102: 		bh = ext4_bread(NULL, inode, 0, 0);
  103: 		if (IS_ERR(bh))
  104: 			return ERR_CAST(bh);
  105: 		if (!bh) {
  106: 			EXT4_ERROR_INODE(inode, "bad symlink.");
  107: 			return ERR_PTR(-EFSCORRUPTED);
  108: 		}
  109: 	}
  110: 
  111: 	set_delayed_call(callback, ext4_free_link, bh);
  112: 	nd_terminate_link(bh->b_data, inode->i_size,
  113: 			  inode->i_sb->s_blocksize - 1);
  114: 	return bh->b_data;
  115: }
  116: 
  117: const struct inode_operations ext4_encrypted_symlink_inode_operations = {
  118: 	.get_link	= ext4_encrypted_get_link,
  119: 	.setattr	= ext4_setattr,
  120: 	.getattr	= ext4_encrypted_symlink_getattr,
  121: 	.listxattr	= ext4_listxattr,
  122: };
  123: 
  124: const struct inode_operations ext4_symlink_inode_operations = {
  125: 	.get_link	= ext4_get_link,
  126: 	.setattr	= ext4_setattr,
  127: 	.getattr	= ext4_getattr,
  128: 	.listxattr	= ext4_listxattr,
  129: };
  130: 
  131: const struct inode_operations ext4_fast_symlink_inode_operations = {
  132: 	.get_link	= simple_get_link,
  133: 	.setattr	= ext4_setattr,
  134: 	.getattr	= ext4_getattr,
  135: 	.listxattr	= ext4_listxattr,
  136: };
```

## 20. candidate_65d848d5f1fd

- buckets: top_ranked, exception_hint
- score: 53 E2_API_PROTOCOL_SUPPORTED
- type/severity: missing_cleanup / P2
- location: fs/ext4/orphan.c::ext4_init_orphan_info:610
- exception hints: True

- protocols: `['buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse']`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']`
- exception_hints: `[{'type': 'ownership_transferred', 'resource_kind': 'buffer_head', 'resource_expr': 'ob_bh', 'line': 609, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ext4_orphan_block_tail(sb, oi->of_binfo[i].ob_bh)', 'protocol_id': 'buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse'}]`

Label template:

```json
{
  "candidate_id": "candidate_65d848d5f1fd",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
  530: 
  531: static int ext4_orphan_file_block_csum_verify(struct super_block *sb,
  532: 					      struct buffer_head *bh)
  533: {
  534: 	__u32 calculated;
  535: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  536: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  537: 	struct ext4_orphan_block_tail *ot;
  538: 	__le64 dsk_block_nr = cpu_to_le64(bh->b_blocknr);
  539: 
  540: 	if (!ext4_has_metadata_csum(sb))
  541: 		return 1;
  542: 
  543: 	ot = ext4_orphan_block_tail(sb, bh);
  544: 	calculated = ext4_chksum(EXT4_SB(sb), oi->of_csum_seed,
  545: 				 (__u8 *)&dsk_block_nr, sizeof(dsk_block_nr));
  546: 	calculated = ext4_chksum(EXT4_SB(sb), calculated, (__u8 *)bh->b_data,
  547: 				 inodes_per_ob * sizeof(__u32));
  548: 	return le32_to_cpu(ot->ob_checksum) == calculated;
  549: }
  550: 
  551: /* This gets called only when checksumming is enabled */
  552: void ext4_orphan_file_block_trigger(struct jbd2_buffer_trigger_type *triggers,
  553: 				    struct buffer_head *bh,
  554: 				    void *data, size_t size)
  555: {
  556: 	struct super_block *sb = EXT4_TRIGGER(triggers)->sb;
  557: 	__u32 csum;
  558: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  559: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  560: 	struct ext4_orphan_block_tail *ot;
  561: 	__le64 dsk_block_nr = cpu_to_le64(bh->b_blocknr);
  562: 
  563: 	csum = ext4_chksum(EXT4_SB(sb), oi->of_csum_seed,
  564: 			   (__u8 *)&dsk_block_nr, sizeof(dsk_block_nr));
  565: 	csum = ext4_chksum(EXT4_SB(sb), csum, (__u8 *)data,
  566: 			   inodes_per_ob * sizeof(__u32));
  567: 	ot = ext4_orphan_block_tail(sb, bh);
  568: 	ot->ob_checksum = cpu_to_le32(csum);
  569: }
  570: 
  571: int ext4_init_orphan_info(struct super_block *sb)
  572: {
  573: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  574: 	struct inode *inode;
  575: 	int i, j;
  576: 	int ret;
  577: 	int free;
  578: 	__le32 *bdata;
  579: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  580: 	struct ext4_orphan_block_tail *ot;
  581: 	ino_t orphan_ino = le32_to_cpu(EXT4_SB(sb)->s_es->s_orphan_file_inum);
  582: 
  583: 	if (!ext4_has_feature_orphan_file(sb))
  584: 		return 0;
  585: 
  586: 	inode = ext4_iget(sb, orphan_ino, EXT4_IGET_SPECIAL);
  587: 	if (IS_ERR(inode)) {
  588: 		ext4_msg(sb, KERN_ERR, "get orphan inode failed");
  589: 		return PTR_ERR(inode);
  590: 	}
  591: 	oi->of_blocks = inode->i_size >> sb->s_blocksize_bits;
  592: 	oi->of_csum_seed = EXT4_I(inode)->i_csum_seed;
  593: 	oi->of_binfo = kmalloc(oi->of_blocks*sizeof(struct ext4_orphan_block),
  594: 			       GFP_KERNEL);
  595: 	if (!oi->of_binfo) {
  596: 		ret = -ENOMEM;
  597: 		goto out_put;
  598: 	}
  599: 	for (i = 0; i < oi->of_blocks; i++) {
  600: 		oi->of_binfo[i].ob_bh = ext4_bread(NULL, inode, i, 0);
  601: 		if (IS_ERR(oi->of_binfo[i].ob_bh)) {
  602: 			ret = PTR_ERR(oi->of_binfo[i].ob_bh);
  603: 			goto out_free;
  604: 		}
  605: 		if (!oi->of_binfo[i].ob_bh) {
  606: 			ret = -EIO;
  607: 			goto out_free;
  608: 		}
  609: 		ot = ext4_orphan_block_tail(sb, oi->of_binfo[i].ob_bh);
> 610: 		if (le32_to_cpu(ot->ob_magic) != EXT4_ORPHAN_BLOCK_MAGIC) {
  611: 			ext4_error(sb, "orphan file block %d: bad magic", i);
  612: 			ret = -EIO;
  613: 			goto out_free;
  614: 		}
  615: 		if (!ext4_orphan_file_block_csum_verify(sb,
  616: 						oi->of_binfo[i].ob_bh)) {
  617: 			ext4_error(sb, "orphan file block %d: bad checksum", i);
  618: 			ret = -EIO;
  619: 			goto out_free;
  620: 		}
  621: 		bdata = (__le32 *)(oi->of_binfo[i].ob_bh->b_data);
  622: 		free = 0;
  623: 		for (j = 0; j < inodes_per_ob; j++)
  624: 			if (bdata[j] == 0)
  625: 				free++;
  626: 		atomic_set(&oi->of_binfo[i].ob_free_entries, free);
  627: 	}
  628: 	iput(inode);
  629: 	return 0;
  630: out_free:
  631: 	for (i--; i >= 0; i--)
  632: 		brelse(oi->of_binfo[i].ob_bh);
  633: 	kfree(oi->of_binfo);
  634: out_put:
  635: 	iput(inode);
  636: 	return ret;
  637: }
  638: 
  639: int ext4_orphan_file_empty(struct super_block *sb)
  640: {
  641: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  642: 	int i;
  643: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  644: 
  645: 	if (!ext4_has_feature_orphan_file(sb))
  646: 		return 1;
  647: 	for (i = 0; i < oi->of_blocks; i++)
  648: 		if (atomic_read(&oi->of_binfo[i].ob_free_entries) !=
  649: 		    inodes_per_ob)
  650: 			return 0;
  651: 	return 1;
  652: }
```

## 21. candidate_f3e8e44a00d3

- buckets: exception_hint
- score: 53 E2_API_PROTOCOL_SUPPORTED
- type/severity: missing_cleanup / P2
- location: fs/ext4/orphan.c::ext4_init_orphan_info:615
- exception hints: True

- protocols: `['buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse']`
- score explanation: `['E0 static rule base +10', 'E1 LLM true_candidate auxiliary signal +20', 'E2 API protocol support with exception hints +10', 'P2 severity +10', 'buffer_head or memory protocol violation with exception hints +3']`
- exception_hints: `[{'type': 'ownership_transferred', 'resource_kind': 'buffer_head', 'resource_expr': 'ob_bh', 'line': 609, 'reason': 'resource appears in a call before the error path', 'confidence': 'low', 'call': 'ext4_orphan_block_tail(sb, oi->of_binfo[i].ob_bh)', 'protocol_id': 'buffer_head.sb_bread.bread.ext4_bread.ext4_getblk.brelse'}]`

Label template:

```json
{
  "candidate_id": "candidate_f3e8e44a00d3",
  "verdict": "true_candidate | false_positive | uncertain",
  "confidence": "high | medium | low",
  "reason": "",
  "confirmed_exception": false,
  "confirmed_exception_type": null,
  "suggested_rule_update": null,
  "next_action": "add_wrapper_summary | add_ownership_rule | runtime_validation | upstream_history_check | no_action",
  "validation_hint": "ENOSPC | EIO | ENOMEM | quota | journal | none",
  "review_source": "codex_static_review | human_manual_review | upstream_confirmed",
  "reviewer": "manual",
  "notes": ""
}
```

Source context:

```c
  535: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  536: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  537: 	struct ext4_orphan_block_tail *ot;
  538: 	__le64 dsk_block_nr = cpu_to_le64(bh->b_blocknr);
  539: 
  540: 	if (!ext4_has_metadata_csum(sb))
  541: 		return 1;
  542: 
  543: 	ot = ext4_orphan_block_tail(sb, bh);
  544: 	calculated = ext4_chksum(EXT4_SB(sb), oi->of_csum_seed,
  545: 				 (__u8 *)&dsk_block_nr, sizeof(dsk_block_nr));
  546: 	calculated = ext4_chksum(EXT4_SB(sb), calculated, (__u8 *)bh->b_data,
  547: 				 inodes_per_ob * sizeof(__u32));
  548: 	return le32_to_cpu(ot->ob_checksum) == calculated;
  549: }
  550: 
  551: /* This gets called only when checksumming is enabled */
  552: void ext4_orphan_file_block_trigger(struct jbd2_buffer_trigger_type *triggers,
  553: 				    struct buffer_head *bh,
  554: 				    void *data, size_t size)
  555: {
  556: 	struct super_block *sb = EXT4_TRIGGER(triggers)->sb;
  557: 	__u32 csum;
  558: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  559: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  560: 	struct ext4_orphan_block_tail *ot;
  561: 	__le64 dsk_block_nr = cpu_to_le64(bh->b_blocknr);
  562: 
  563: 	csum = ext4_chksum(EXT4_SB(sb), oi->of_csum_seed,
  564: 			   (__u8 *)&dsk_block_nr, sizeof(dsk_block_nr));
  565: 	csum = ext4_chksum(EXT4_SB(sb), csum, (__u8 *)data,
  566: 			   inodes_per_ob * sizeof(__u32));
  567: 	ot = ext4_orphan_block_tail(sb, bh);
  568: 	ot->ob_checksum = cpu_to_le32(csum);
  569: }
  570: 
  571: int ext4_init_orphan_info(struct super_block *sb)
  572: {
  573: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  574: 	struct inode *inode;
  575: 	int i, j;
  576: 	int ret;
  577: 	int free;
  578: 	__le32 *bdata;
  579: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  580: 	struct ext4_orphan_block_tail *ot;
  581: 	ino_t orphan_ino = le32_to_cpu(EXT4_SB(sb)->s_es->s_orphan_file_inum);
  582: 
  583: 	if (!ext4_has_feature_orphan_file(sb))
  584: 		return 0;
  585: 
  586: 	inode = ext4_iget(sb, orphan_ino, EXT4_IGET_SPECIAL);
  587: 	if (IS_ERR(inode)) {
  588: 		ext4_msg(sb, KERN_ERR, "get orphan inode failed");
  589: 		return PTR_ERR(inode);
  590: 	}
  591: 	oi->of_blocks = inode->i_size >> sb->s_blocksize_bits;
  592: 	oi->of_csum_seed = EXT4_I(inode)->i_csum_seed;
  593: 	oi->of_binfo = kmalloc(oi->of_blocks*sizeof(struct ext4_orphan_block),
  594: 			       GFP_KERNEL);
  595: 	if (!oi->of_binfo) {
  596: 		ret = -ENOMEM;
  597: 		goto out_put;
  598: 	}
  599: 	for (i = 0; i < oi->of_blocks; i++) {
  600: 		oi->of_binfo[i].ob_bh = ext4_bread(NULL, inode, i, 0);
  601: 		if (IS_ERR(oi->of_binfo[i].ob_bh)) {
  602: 			ret = PTR_ERR(oi->of_binfo[i].ob_bh);
  603: 			goto out_free;
  604: 		}
  605: 		if (!oi->of_binfo[i].ob_bh) {
  606: 			ret = -EIO;
  607: 			goto out_free;
  608: 		}
  609: 		ot = ext4_orphan_block_tail(sb, oi->of_binfo[i].ob_bh);
  610: 		if (le32_to_cpu(ot->ob_magic) != EXT4_ORPHAN_BLOCK_MAGIC) {
  611: 			ext4_error(sb, "orphan file block %d: bad magic", i);
  612: 			ret = -EIO;
  613: 			goto out_free;
  614: 		}
> 615: 		if (!ext4_orphan_file_block_csum_verify(sb,
  616: 						oi->of_binfo[i].ob_bh)) {
  617: 			ext4_error(sb, "orphan file block %d: bad checksum", i);
  618: 			ret = -EIO;
  619: 			goto out_free;
  620: 		}
  621: 		bdata = (__le32 *)(oi->of_binfo[i].ob_bh->b_data);
  622: 		free = 0;
  623: 		for (j = 0; j < inodes_per_ob; j++)
  624: 			if (bdata[j] == 0)
  625: 				free++;
  626: 		atomic_set(&oi->of_binfo[i].ob_free_entries, free);
  627: 	}
  628: 	iput(inode);
  629: 	return 0;
  630: out_free:
  631: 	for (i--; i >= 0; i--)
  632: 		brelse(oi->of_binfo[i].ob_bh);
  633: 	kfree(oi->of_binfo);
  634: out_put:
  635: 	iput(inode);
  636: 	return ret;
  637: }
  638: 
  639: int ext4_orphan_file_empty(struct super_block *sb)
  640: {
  641: 	struct ext4_orphan_info *oi = &EXT4_SB(sb)->s_orphan_info;
  642: 	int i;
  643: 	int inodes_per_ob = ext4_inodes_per_orphan_block(sb);
  644: 
  645: 	if (!ext4_has_feature_orphan_file(sb))
  646: 		return 1;
  647: 	for (i = 0; i < oi->of_blocks; i++)
  648: 		if (atomic_read(&oi->of_binfo[i].ob_free_entries) !=
  649: 		    inodes_per_ob)
  650: 			return 0;
  651: 	return 1;
  652: }
```
