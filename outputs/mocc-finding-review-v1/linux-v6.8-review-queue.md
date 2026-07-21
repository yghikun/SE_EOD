# MOCC-SE Finding Review Queue

This is a development review queue, not a frozen benchmark.

- source report: `outputs/mocc-discovery-v1-linux-v6.8.json`
- source root: `E:/yanjiusheng/阅读论文/file_system/SE_EOD/linux-sources/linux-v6.8-fs/fs`
- source version: `linux-v6.8`
- review items: 19
- protocol candidates: 19
- discovery reviews: 0

## 1. reserve_chunk_space / metadata_state_divergence

- review id: `mocc_review_mocc_occurrence_1fdcd64a328daf121598`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_c.activation_accounting`
- operation: `btrfs_chunk_activation_reservation`
- location: `btrfs/block-group.c`
- exit: `success:btrfs.success`
- certainty: `high`
- family: `mocc_family_e3566f888ab190ed0731`

Review focus:

- Confirm whether return outcome, metadata effects, and accounting state agree.
- Check whether a missing reservation/accounting effect is hidden in a helper.

Likely development follow-ups:

- review reservation/accounting summaries for unsatisfied obligation

Witness:

- L4220 `necessary_step`: btrfs_zoned_activate_one_bg starts chunk_activation@1
- L4220 `branch`: contract btrfs.activation.changed: ret > 0
- L4220 `effect_created`: btrfs.chunk_metadata_pending
- L0 `accounting_check`: btrfs.pending_requires_reservation: pending_without_reservation
- L4245 `exit`: <implicit return>

Source context `btrfs/block-group.c:4216`:

```c
 4216: 			/*
 4217: 			 * We have a new chunk. We also need to activate it for
 4218: 			 * zoned filesystem.
 4219: 			 */
 4220: 			ret = btrfs_zoned_activate_one_bg(fs_info, info, true);
 4221: 			if (ret < 0)
 4222: 				return;
 4223: 
 4224: 			/*
```

Source context `btrfs/block-group.c:4241`:

```c
 4241: 					  bytes, BTRFS_RESERVE_NO_FLUSH);
 4242: 		if (!ret)
 4243: 			trans->chunk_bytes_reserved += bytes;
 4244: 	}
 4245: }
 4246: 
 4247: /*
 4248:  * Reserve space in the system space for allocating or removing a chunk.
 4249:  * The caller must be holding fs_info->chunk_mutex.
```

## 2. btrfs_recover_relocation / incomplete_failure_completion

- review id: `mocc_review_mocc_occurrence_1c504a8198f68f2b16af`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_b.device_topology_rollback`
- operation: `btrfs_relocation_recovery`
- location: `btrfs/relocation.c`
- exit: `failure:reloc.failure`
- certainty: `high`
- family: `mocc_family_b03a06d0c674eaf41b1b`

Review focus:

- Confirm whether each open effect is compensated or transferred on failure.
- Check callee summaries for cleanup hidden behind helper calls.

Likely development follow-ups:

- review compensation or handler summaries for open metadata effects

Witness:

- L4382 `effect_created`: reloc.root_pointer
- L4399 `necessary_step`: btrfs_commit_transaction starts recovery_commit@1
- L4399 `branch`: contract reloc.failure.nonzero: ret != 0
- L4399 `failure`: btrfs_commit_transaction -> ret != 0 (recovery_commit@1)
- L4421 `exit`: return err;
- L4421 `handler`: failure reaches function return

Source context `btrfs/relocation.c:4378`:

```c
 4378: 			btrfs_put_root(fs_root);
 4379: 			btrfs_end_transaction(trans);
 4380: 			goto out_unset;
 4381: 		}
 4382: 		fs_root->reloc_root = btrfs_grab_root(reloc_root);
 4383: 		btrfs_put_root(fs_root);
 4384: 	}
 4385: 
 4386: 	err = btrfs_commit_transaction(trans);
```

Source context `btrfs/relocation.c:4395`:

```c
 4395: 	if (IS_ERR(trans)) {
 4396: 		err = PTR_ERR(trans);
 4397: 		goto out_clean;
 4398: 	}
 4399: 	err = btrfs_commit_transaction(trans);
 4400: out_clean:
 4401: 	ret = clean_dirty_subvols(rc);
 4402: 	if (ret < 0 && !err)
 4403: 		err = ret;
```

Source context `btrfs/relocation.c:4417`:

```c
 4417: 		ASSERT(fs_root);
 4418: 		err = btrfs_orphan_cleanup(fs_root);
 4419: 		btrfs_put_root(fs_root);
 4420: 	}
 4421: 	return err;
 4422: }
 4423: 
 4424: /*
 4425:  * helper to add ordered checksum for data relocation.
```

## 3. btrfs_init_new_device / incomplete_failure_completion

- review id: `mocc_review_mocc_occurrence_084190f9e1fa5b21424c`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_b.device_topology_rollback`
- operation: `btrfs_sprout_device_add`
- location: `btrfs/volumes.c`
- exit: `failure:sprout.failure`
- certainty: `high`
- family: `mocc_family_fb79b2aa4177f853f100`

Review focus:

- Confirm whether each open effect is compensated or transferred on failure.
- Check callee summaries for cleanup hidden behind helper calls.

Likely development follow-ups:

- review compensation or handler summaries for open metadata effects

Witness:

- L2680 `effect_created`: sprout.fs_devices_topology
- L2681 `effect_created`: sprout.active_s_bdev
- L2681 `effect_created`: sprout.active_latest_dev
- L2688 `effect_created`: sprout.device_dev_membership
- L2689 `effect_created`: sprout.device_alloc_membership
- L2740 `necessary_step`: btrfs_finish_sprout starts finish_sprout@1
- L2740 `branch`: contract sprout.failure.nonzero: ret != 0
- L2740 `failure`: btrfs_finish_sprout -> ret != 0 (finish_sprout@1)
- L2796 `effect_compensated`: sprout.device_dev_membership
- L2797 `effect_compensated`: sprout.device_alloc_membership
- L2825 `exit`: return ret;
- L2825 `handler`: failure reaches function return

Source context `btrfs/volumes.c:2676`:

```c
 2676: 	}
 2677: 
 2678: 	mutex_lock(&fs_devices->device_list_mutex);
 2679: 	if (seeding_dev) {
 2680: 		btrfs_setup_sprout(fs_info, seed_devices);
 2681: 		btrfs_assign_next_active_device(fs_info->fs_devices->latest_dev,
 2682: 						device);
 2683: 	}
 2684: 
```

Source context `btrfs/volumes.c:2677`:

```c
 2677: 
 2678: 	mutex_lock(&fs_devices->device_list_mutex);
 2679: 	if (seeding_dev) {
 2680: 		btrfs_setup_sprout(fs_info, seed_devices);
 2681: 		btrfs_assign_next_active_device(fs_info->fs_devices->latest_dev,
 2682: 						device);
 2683: 	}
 2684: 
 2685: 	device->fs_devices = fs_devices;
```

Source context `btrfs/volumes.c:2684`:

```c
 2684: 
 2685: 	device->fs_devices = fs_devices;
 2686: 
 2687: 	mutex_lock(&fs_info->chunk_mutex);
 2688: 	list_add_rcu(&device->dev_list, &fs_devices->devices);
 2689: 	list_add(&device->dev_alloc_list, &fs_devices->alloc_list);
 2690: 	fs_devices->num_devices++;
 2691: 	fs_devices->open_devices++;
 2692: 	fs_devices->rw_devices++;
```

Source context `btrfs/volumes.c:2685`:

```c
 2685: 	device->fs_devices = fs_devices;
 2686: 
 2687: 	mutex_lock(&fs_info->chunk_mutex);
 2688: 	list_add_rcu(&device->dev_list, &fs_devices->devices);
 2689: 	list_add(&device->dev_alloc_list, &fs_devices->alloc_list);
 2690: 	fs_devices->num_devices++;
 2691: 	fs_devices->open_devices++;
 2692: 	fs_devices->rw_devices++;
 2693: 	fs_devices->total_devices++;
```

Source context `btrfs/volumes.c:2736`:

```c
 2736: 		goto error_sysfs;
 2737: 	}
 2738: 
 2739: 	if (seeding_dev) {
 2740: 		ret = btrfs_finish_sprout(trans);
 2741: 		if (ret) {
 2742: 			btrfs_abort_transaction(trans, ret);
 2743: 			goto error_sysfs;
 2744: 		}
```

Source context `btrfs/volumes.c:2792`:

```c
 2792: error_sysfs:
 2793: 	btrfs_sysfs_remove_device(device);
 2794: 	mutex_lock(&fs_info->fs_devices->device_list_mutex);
 2795: 	mutex_lock(&fs_info->chunk_mutex);
 2796: 	list_del_rcu(&device->dev_list);
 2797: 	list_del(&device->dev_alloc_list);
 2798: 	fs_info->fs_devices->num_devices--;
 2799: 	fs_info->fs_devices->open_devices--;
 2800: 	fs_info->fs_devices->rw_devices--;
```

Source context `btrfs/volumes.c:2793`:

```c
 2793: 	btrfs_sysfs_remove_device(device);
 2794: 	mutex_lock(&fs_info->fs_devices->device_list_mutex);
 2795: 	mutex_lock(&fs_info->chunk_mutex);
 2796: 	list_del_rcu(&device->dev_list);
 2797: 	list_del(&device->dev_alloc_list);
 2798: 	fs_info->fs_devices->num_devices--;
 2799: 	fs_info->fs_devices->open_devices--;
 2800: 	fs_info->fs_devices->rw_devices--;
 2801: 	fs_info->fs_devices->total_devices--;
```

Source context `btrfs/volumes.c:2821`:

```c
 2821: 	if (locked) {
 2822: 		mutex_unlock(&uuid_mutex);
 2823: 		up_write(&sb->s_umount);
 2824: 	}
 2825: 	return ret;
 2826: }
 2827: 
 2828: static noinline int btrfs_update_device(struct btrfs_trans_handle *trans,
 2829: 					struct btrfs_device *device)
```

## 4. ext4_fc_replay_add_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_494f361a7b84fadf6d2e`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `ext4_replay_add_range`
- location: `ext4/fast_commit.c`
- exit: `success:add.success`
- certainty: `high`
- family: `mocc_family_a61f1072e9812e00d46b`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L1780 `necessary_step`: ext4_ext_insert_extent starts insert_extent@1
- L1780 `branch`: contract add.failure.nonzero: ret != 0
- L1780 `failure`: ext4_ext_insert_extent -> ret != 0 (insert_extent@1)
- L1834 `exit`: return 0;

Source context `ext4/fast_commit.c:1776`:

```c
 1776: 			newex.ee_len = cpu_to_le16(map.m_len);
 1777: 			if (ext4_ext_is_unwritten(ex))
 1778: 				ext4_ext_mark_unwritten(&newex);
 1779: 			down_write(&EXT4_I(inode)->i_data_sem);
 1780: 			ret = ext4_ext_insert_extent(
 1781: 				NULL, inode, &path, &newex, 0);
 1782: 			up_write((&EXT4_I(inode)->i_data_sem));
 1783: 			ext4_free_ext_path(path);
 1784: 			if (ret)
```

Source context `ext4/fast_commit.c:1830`:

```c
 1830: 	ext4_ext_replay_shrink_inode(inode, i_size_read(inode) >>
 1831: 					sb->s_blocksize_bits);
 1832: out:
 1833: 	iput(inode);
 1834: 	return 0;
 1835: }
 1836: 
 1837: /* Replay DEL_RANGE tag */
 1838: static int
```

## 5. ext4_fc_replay_add_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_5b6b5526d4f1d1930526`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `ext4_replay_add_range`
- location: `ext4/fast_commit.c`
- exit: `success:add.success`
- certainty: `high`
- family: `mocc_family_0815218615100f6c6b6a`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L1769 `necessary_step`: ext4_find_extent starts find_extent@1
- L1769 `branch`: contract add.failure.errptr: IS_ERR(ret)
- L1769 `failure`: ext4_find_extent -> IS_ERR(ret) (find_extent@1)
- L1834 `exit`: return 0;

Source context `ext4/fast_commit.c:1765`:

```c
 1765: 			goto out;
 1766: 
 1767: 		if (ret == 0) {
 1768: 			/* Range is not mapped */
 1769: 			path = ext4_find_extent(inode, cur, NULL, 0);
 1770: 			if (IS_ERR(path))
 1771: 				goto out;
 1772: 			memset(&newex, 0, sizeof(newex));
 1773: 			newex.ee_block = cpu_to_le32(cur);
```

Source context `ext4/fast_commit.c:1830`:

```c
 1830: 	ext4_ext_replay_shrink_inode(inode, i_size_read(inode) >>
 1831: 					sb->s_blocksize_bits);
 1832: out:
 1833: 	iput(inode);
 1834: 	return 0;
 1835: }
 1836: 
 1837: /* Replay DEL_RANGE tag */
 1838: static int
```

## 6. ext4_fc_replay_add_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_67bc885339c21d674412`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `ext4_replay_add_range`
- location: `ext4/fast_commit.c`
- exit: `success:add.success`
- certainty: `high`
- family: `mocc_family_c7ddd5670afd52a332c7`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L1744 `necessary_step`: ext4_fc_record_modified_inode starts record_modified@1
- L1744 `branch`: contract add.failure.nonzero: ret != 0
- L1744 `failure`: ext4_fc_record_modified_inode -> ret != 0 (record_modified@1)
- L1834 `exit`: return 0;

Source context `ext4/fast_commit.c:1740`:

```c
 1740: 		ext4_debug("Inode not found.");
 1741: 		return 0;
 1742: 	}
 1743: 
 1744: 	ret = ext4_fc_record_modified_inode(sb, inode->i_ino);
 1745: 	if (ret)
 1746: 		goto out;
 1747: 
 1748: 	start = le32_to_cpu(ex->ee_block);
```

Source context `ext4/fast_commit.c:1830`:

```c
 1830: 	ext4_ext_replay_shrink_inode(inode, i_size_read(inode) >>
 1831: 					sb->s_blocksize_bits);
 1832: out:
 1833: 	iput(inode);
 1834: 	return 0;
 1835: }
 1836: 
 1837: /* Replay DEL_RANGE tag */
 1838: static int
```

## 7. ext4_fc_replay_add_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_c85a2865849c465c67b8`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `ext4_replay_add_range`
- location: `ext4/fast_commit.c`
- exit: `success:add.success`
- certainty: `high`
- family: `mocc_family_0cefb3f2976d1d80ddb2`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L1762 `necessary_step`: ext4_map_blocks starts map_blocks@1
- L1762 `branch`: contract add.failure.negative: ret < 0
- L1762 `failure`: ext4_map_blocks -> ret < 0 (map_blocks@1)
- L1834 `exit`: return 0;

Source context `ext4/fast_commit.c:1758`:

```c
 1758: 	while (remaining > 0) {
 1759: 		map.m_lblk = cur;
 1760: 		map.m_len = remaining;
 1761: 		map.m_pblk = 0;
 1762: 		ret = ext4_map_blocks(NULL, inode, &map, 0);
 1763: 
 1764: 		if (ret < 0)
 1765: 			goto out;
 1766: 
```

Source context `ext4/fast_commit.c:1830`:

```c
 1830: 	ext4_ext_replay_shrink_inode(inode, i_size_read(inode) >>
 1831: 					sb->s_blocksize_bits);
 1832: out:
 1833: 	iput(inode);
 1834: 	return 0;
 1835: }
 1836: 
 1837: /* Replay DEL_RANGE tag */
 1838: static int
```

## 8. ext4_fc_replay_add_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_e901bdddd2188d9c7135`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `ext4_replay_add_range`
- location: `ext4/fast_commit.c`
- exit: `success:add.success`
- certainty: `high`
- family: `mocc_family_41d89170475c39254c72`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L1795 `necessary_step`: ext4_ext_replay_update_ex starts update_extent@1
- L1795 `branch`: contract add.failure.nonzero: ret != 0
- L1795 `failure`: ext4_ext_replay_update_ex -> ret != 0 (update_extent@1)
- L1834 `exit`: return 0;

Source context `ext4/fast_commit.c:1791`:

```c
 1791: 			 * Logical to physical mapping changed. This can happen
 1792: 			 * if this range was removed and then reallocated to
 1793: 			 * map to new physical blocks during a fast commit.
 1794: 			 */
 1795: 			ret = ext4_ext_replay_update_ex(inode, cur, map.m_len,
 1796: 					ext4_ext_is_unwritten(ex),
 1797: 					start_pblk + cur - start);
 1798: 			if (ret)
 1799: 				goto out;
```

Source context `ext4/fast_commit.c:1830`:

```c
 1830: 	ext4_ext_replay_shrink_inode(inode, i_size_read(inode) >>
 1831: 					sb->s_blocksize_bits);
 1832: out:
 1833: 	iput(inode);
 1834: 	return 0;
 1835: }
 1836: 
 1837: /* Replay DEL_RANGE tag */
 1838: static int
```

## 9. ext4_fc_replay_del_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_451a8159d7ebc634d05b`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `ext4_replay_del_range`
- location: `ext4/fast_commit.c`
- exit: `success:del.success`
- certainty: `high`
- family: `mocc_family_dd4d926c9116795307f8`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L1872 `necessary_step`: ext4_map_blocks starts map_blocks@1
- L1872 `branch`: contract del.failure.negative: ret < 0
- L1872 `failure`: ext4_map_blocks -> ret < 0 (map_blocks@1)
- L1897 `exit`: return 0;

Source context `ext4/fast_commit.c:1868`:

```c
 1868: 	while (remaining > 0) {
 1869: 		map.m_lblk = cur;
 1870: 		map.m_len = remaining;
 1871: 
 1872: 		ret = ext4_map_blocks(NULL, inode, &map, 0);
 1873: 		if (ret < 0)
 1874: 			goto out;
 1875: 		if (ret > 0) {
 1876: 			remaining -= ret;
```

Source context `ext4/fast_commit.c:1893`:

```c
 1893: 		i_size_read(inode) >> sb->s_blocksize_bits);
 1894: 	ext4_mark_inode_dirty(NULL, inode);
 1895: out:
 1896: 	iput(inode);
 1897: 	return 0;
 1898: }
 1899: 
 1900: static void ext4_fc_set_bitmaps_and_counters(struct super_block *sb)
 1901: {
```

## 10. ext4_fc_replay_del_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_733ee0e26506eb6c017e`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `ext4_replay_del_range`
- location: `ext4/fast_commit.c`
- exit: `success:del.success`
- certainty: `high`
- family: `mocc_family_d50fda549bb49a3b7667`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L1886 `necessary_step`: ext4_ext_remove_space starts remove_space@1
- L1886 `branch`: contract del.failure.nonzero: ret != 0
- L1886 `failure`: ext4_ext_remove_space -> ret != 0 (remove_space@1)
- L1897 `exit`: return 0;

Source context `ext4/fast_commit.c:1882`:

```c
 1882: 		}
 1883: 	}
 1884: 
 1885: 	down_write(&EXT4_I(inode)->i_data_sem);
 1886: 	ret = ext4_ext_remove_space(inode, le32_to_cpu(lrange.fc_lblk),
 1887: 				le32_to_cpu(lrange.fc_lblk) +
 1888: 				le32_to_cpu(lrange.fc_len) - 1);
 1889: 	up_write(&EXT4_I(inode)->i_data_sem);
 1890: 	if (ret)
```

Source context `ext4/fast_commit.c:1893`:

```c
 1893: 		i_size_read(inode) >> sb->s_blocksize_bits);
 1894: 	ext4_mark_inode_dirty(NULL, inode);
 1895: out:
 1896: 	iput(inode);
 1897: 	return 0;
 1898: }
 1899: 
 1900: static void ext4_fc_set_bitmaps_and_counters(struct super_block *sb)
 1901: {
```

## 11. ext4_fc_replay_del_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_769c3f15a6f7dfa5c159`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `ext4_replay_del_range`
- location: `ext4/fast_commit.c`
- exit: `success:del.success`
- certainty: `high`
- family: `mocc_family_d4180a6b912dc753ba10`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L1861 `necessary_step`: ext4_fc_record_modified_inode starts record_modified@1
- L1861 `branch`: contract del.failure.nonzero: ret != 0
- L1861 `failure`: ext4_fc_record_modified_inode -> ret != 0 (record_modified@1)
- L1897 `exit`: return 0;

Source context `ext4/fast_commit.c:1857`:

```c
 1857: 		ext4_debug("Inode %d not found", le32_to_cpu(lrange.fc_ino));
 1858: 		return 0;
 1859: 	}
 1860: 
 1861: 	ret = ext4_fc_record_modified_inode(sb, inode->i_ino);
 1862: 	if (ret)
 1863: 		goto out;
 1864: 
 1865: 	ext4_debug("DEL_RANGE, inode %ld, lblk %d, len %d\n",
```

Source context `ext4/fast_commit.c:1893`:

```c
 1893: 		i_size_read(inode) >> sb->s_blocksize_bits);
 1894: 	ext4_mark_inode_dirty(NULL, inode);
 1895: out:
 1896: 	iput(inode);
 1897: 	return 0;
 1898: }
 1899: 
 1900: static void ext4_fc_set_bitmaps_and_counters(struct super_block *sb)
 1901: {
```

## 12. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_1b96d3faaab09e3c91d2`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `ext4_replay_inode`
- location: `ext4/fast_commit.c`
- exit: `success:inode.success`
- certainty: `high`
- family: `mocc_family_0306deaee3bb1cfc6f64`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L1579 `necessary_step`: ext4_mark_inode_used starts mark_inode_used@1
- L1579 `branch`: contract inode.failure.nonzero: ret != 0
- L1579 `failure`: ext4_mark_inode_used -> ret != 0 (mark_inode_used@1)
- L1610 `exit`: return 0;

Source context `ext4/fast_commit.c:1575`:

```c
 1575: 		goto out;
 1576: 	ret = sync_dirty_buffer(iloc.bh);
 1577: 	if (ret)
 1578: 		goto out;
 1579: 	ret = ext4_mark_inode_used(sb, ino);
 1580: 	if (ret)
 1581: 		goto out;
 1582: 
 1583: 	/* Given that we just wrote the inode on disk, this SHOULD succeed. */
```

Source context `ext4/fast_commit.c:1606`:

```c
 1606: 	iput(inode);
 1607: 	if (!ret)
 1608: 		blkdev_issue_flush(sb->s_bdev);
 1609: 
 1610: 	return 0;
 1611: }
 1612: 
 1613: /*
 1614:  * Dentry create replay function.
```

## 13. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_3e4f1c944e82245ff46d`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `ext4_replay_inode`
- location: `ext4/fast_commit.c`
- exit: `success:inode.success`
- certainty: `high`
- family: `mocc_family_e419d74f5ab7000912d7`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L1576 `necessary_step`: sync_dirty_buffer starts sync_buffer@1
- L1576 `branch`: contract inode.failure.nonzero: ret != 0
- L1576 `failure`: sync_dirty_buffer -> ret != 0 (sync_buffer@1)
- L1610 `exit`: return 0;

Source context `ext4/fast_commit.c:1572`:

```c
 1572: 	/* Immediately update the inode on disk. */
 1573: 	ret = ext4_handle_dirty_metadata(NULL, NULL, iloc.bh);
 1574: 	if (ret)
 1575: 		goto out;
 1576: 	ret = sync_dirty_buffer(iloc.bh);
 1577: 	if (ret)
 1578: 		goto out;
 1579: 	ret = ext4_mark_inode_used(sb, ino);
 1580: 	if (ret)
```

Source context `ext4/fast_commit.c:1606`:

```c
 1606: 	iput(inode);
 1607: 	if (!ret)
 1608: 		blkdev_issue_flush(sb->s_bdev);
 1609: 
 1610: 	return 0;
 1611: }
 1612: 
 1613: /*
 1614:  * Dentry create replay function.
```

## 14. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_5748c6c26760e1c2f625`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `ext4_replay_inode`
- location: `ext4/fast_commit.c`
- exit: `success:inode.success`
- certainty: `high`
- family: `mocc_family_6060d023ecf268dc137d`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L1547 `necessary_step`: ext4_get_fc_inode_loc starts get_inode_loc@1
- L1547 `branch`: contract inode.failure.nonzero: ret != 0
- L1547 `failure`: ext4_get_fc_inode_loc -> ret != 0 (get_inode_loc@1)
- L1610 `exit`: return 0;

Source context `ext4/fast_commit.c:1543`:

```c
 1543: 		goto out;
 1544: 
 1545: 	raw_fc_inode = (struct ext4_inode *)
 1546: 		(val + offsetof(struct ext4_fc_inode, fc_raw_inode));
 1547: 	ret = ext4_get_fc_inode_loc(sb, ino, &iloc);
 1548: 	if (ret)
 1549: 		goto out;
 1550: 
 1551: 	inode_len = tl->fc_len - sizeof(struct ext4_fc_inode);
```

Source context `ext4/fast_commit.c:1606`:

```c
 1606: 	iput(inode);
 1607: 	if (!ret)
 1608: 		blkdev_issue_flush(sb->s_bdev);
 1609: 
 1610: 	return 0;
 1611: }
 1612: 
 1613: /*
 1614:  * Dentry create replay function.
```

## 15. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_d8ce5780d59918326ede`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `ext4_replay_inode`
- location: `ext4/fast_commit.c`
- exit: `success:inode.success`
- certainty: `high`
- family: `mocc_family_54b0c0d8001d08984f41`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L1573 `necessary_step`: ext4_handle_dirty_metadata starts dirty_metadata@1
- L1573 `branch`: contract inode.failure.nonzero: ret != 0
- L1573 `failure`: ext4_handle_dirty_metadata -> ret != 0 (dirty_metadata@1)
- L1610 `exit`: return 0;

Source context `ext4/fast_commit.c:1569`:

```c
 1569: 			sizeof(raw_inode->i_block));
 1570: 	}
 1571: 
 1572: 	/* Immediately update the inode on disk. */
 1573: 	ret = ext4_handle_dirty_metadata(NULL, NULL, iloc.bh);
 1574: 	if (ret)
 1575: 		goto out;
 1576: 	ret = sync_dirty_buffer(iloc.bh);
 1577: 	if (ret)
```

Source context `ext4/fast_commit.c:1606`:

```c
 1606: 	iput(inode);
 1607: 	if (!ret)
 1608: 		blkdev_issue_flush(sb->s_bdev);
 1609: 
 1610: 	return 0;
 1611: }
 1612: 
 1613: /*
 1614:  * Dentry create replay function.
```

## 16. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_e3968a5e986534d82167`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `ext4_replay_inode`
- location: `ext4/fast_commit.c`
- exit: `success:inode.success`
- certainty: `high`
- family: `mocc_family_87c74beff5e8bb5765cd`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L1541 `necessary_step`: ext4_fc_record_modified_inode starts record_modified@1
- L1541 `branch`: contract inode.failure.nonzero: ret != 0
- L1541 `failure`: ext4_fc_record_modified_inode -> ret != 0 (record_modified@1)
- L1610 `exit`: return 0;

Source context `ext4/fast_commit.c:1537`:

```c
 1537: 		iput(inode);
 1538: 	}
 1539: 	inode = NULL;
 1540: 
 1541: 	ret = ext4_fc_record_modified_inode(sb, ino);
 1542: 	if (ret)
 1543: 		goto out;
 1544: 
 1545: 	raw_fc_inode = (struct ext4_inode *)
```

Source context `ext4/fast_commit.c:1606`:

```c
 1606: 	iput(inode);
 1607: 	if (!ret)
 1608: 		blkdev_issue_flush(sb->s_bdev);
 1609: 
 1610: 	return 0;
 1611: }
 1612: 
 1613: /*
 1614:  * Dentry create replay function.
```

## 17. ext4_expand_extra_isize_ea / metadata_state_divergence

- review id: `mocc_review_mocc_occurrence_894bc776d438d17f786e`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_c.activation_accounting`
- operation: `ext4_extra_isize_fallback`
- location: `ext4/xattr.c`
- exit: `failure:ext4.failure`
- certainty: `high`
- family: `mocc_family_22fb2e1d3a400fed5318`

Review focus:

- Confirm whether return outcome, metadata effects, and accounting state agree.
- Check whether a missing reservation/accounting effect is hidden in a helper.

Witness:

- L2834 `necessary_step`: ext4_xattr_make_inode_space starts inode_space_attempt@1
- L2834 `branch`: contract ext4.space.failure: ret != 0
- L2834 `failure`: ext4_xattr_make_inode_space -> ret != 0 (inode_space_attempt@1)
- L2852 `effect_created`: ext4.inode_extra_isize_changed
- L2863 `stale_result`: metadata changed after inode_space_attempt@1, but the returned symbol still carries its failure
- L2863 `exit`: return error;
- L2863 `handler`: failure reaches function return

Source context `ext4/xattr.c:2830`:

```c
 2830: 	} else {
 2831: 		bfree = inode->i_sb->s_blocksize;
 2832: 	}
 2833: 
 2834: 	error = ext4_xattr_make_inode_space(handle, inode, raw_inode,
 2835: 					    isize_diff, ifree, bfree,
 2836: 					    &total_ino);
 2837: 	if (error) {
 2838: 		if (error == -ENOSPC && !tried_min_extra_isize &&
```

Source context `ext4/xattr.c:2848`:

```c
 2848: 	ext4_xattr_shift_entries(IFIRST(header), EXT4_I(inode)->i_extra_isize
 2849: 			- new_extra_isize, (void *)raw_inode +
 2850: 			EXT4_GOOD_OLD_INODE_SIZE + new_extra_isize,
 2851: 			(void *)header, total_ino);
 2852: 	EXT4_I(inode)->i_extra_isize = new_extra_isize;
 2853: 
 2854: 	if (ext4_has_inline_data(inode))
 2855: 		error = ext4_find_inline_data_nolock(inode);
 2856: 
```

Source context `ext4/xattr.c:2859`:

```c
 2859: 		ext4_warning(inode->i_sb, "Unable to expand inode %lu. Delete some EAs or run e2fsck.",
 2860: 			     inode->i_ino);
 2861: 		mnt_count = le16_to_cpu(sbi->s_es->s_mnt_count);
 2862: 	}
 2863: 	return error;
 2864: }
 2865: 
 2866: #define EIA_INCR 16 /* must be 2^n */
 2867: #define EIA_MASK (EIA_INCR - 1)
```

## 18. xfs_rtcopy_summary / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_028bc7698b4b215c4e89`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `xfs_copy_summary`
- location: `xfs/xfs_rtalloc.c`
- exit: `success:copy.success`
- certainty: `high`
- family: `mocc_family_8f70f320171e9690ad2d`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L101 `necessary_step`: xfs_rtget_summary starts get_summary@1
- L101 `branch`: contract copy.failure.nonzero: ret != 0
- L101 `failure`: xfs_rtget_summary -> ret != 0 (get_summary@1)
- L118 `exit`: return 0;

Source context `xfs/xfs_rtalloc.c:97`:

```c
   97: 	for (log = oargs->mp->m_rsumlevels - 1; log >= 0; log--) {
   98: 		for (bbno = oargs->mp->m_sb.sb_rbmblocks - 1;
   99: 		     (xfs_srtblock_t)bbno >= 0;
  100: 		     bbno--) {
  101: 			error = xfs_rtget_summary(oargs, log, bbno, &sum);
  102: 			if (error)
  103: 				goto out;
  104: 			if (sum == 0)
  105: 				continue;
```

Source context `xfs/xfs_rtalloc.c:114`:

```c
  114: 	}
  115: 	error = 0;
  116: out:
  117: 	xfs_rtbuf_cache_relse(oargs);
  118: 	return 0;
  119: }
  120: /*
  121:  * Mark an extent specified by start and len allocated.
  122:  * Updates all the summary information as well as the bitmap.
```

## 19. xfs_rtcopy_summary / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_26ae1e03588221460d20`
- classification: `PROTOCOL_CANDIDATE`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: `xfs_copy_summary`
- location: `xfs/xfs_rtalloc.c`
- exit: `success:copy.success`
- certainty: `high`
- family: `mocc_family_79510ac618cc9224ce98`

Review focus:

- Confirm whether the failed necessary step can reach a success exit.
- Check for retry, sentinel handling, abort, recovery, or propagated error.

Likely development follow-ups:

- review retry/handler/return-propagation summaries for unresolved failure

Witness:

- L106 `necessary_step`: xfs_rtmodify_summary starts modify_summary@1
- L106 `branch`: contract copy.failure.nonzero: ret != 0
- L106 `failure`: xfs_rtmodify_summary -> ret != 0 (modify_summary@1)
- L118 `exit`: return 0;

Source context `xfs/xfs_rtalloc.c:102`:

```c
  102: 			if (error)
  103: 				goto out;
  104: 			if (sum == 0)
  105: 				continue;
  106: 			error = xfs_rtmodify_summary(oargs, log, bbno, -sum);
  107: 			if (error)
  108: 				goto out;
  109: 			error = xfs_rtmodify_summary(nargs, log, bbno, sum);
  110: 			if (error)
```

Source context `xfs/xfs_rtalloc.c:114`:

```c
  114: 	}
  115: 	error = 0;
  116: out:
  117: 	xfs_rtbuf_cache_relse(oargs);
  118: 	return 0;
  119: }
  120: /*
  121:  * Mark an extent specified by start and len allocated.
  122:  * Updates all the summary information as well as the bitmap.
```
