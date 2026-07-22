# MOCC-SE Finding Review Queue

This is a development review queue, not a frozen benchmark.

- source report: `outputs/mocc-discovery-v2/linux-v6.8-fresh-review.json`
- source root: `E:/yanjiusheng/阅读论文/file_system/SE_EOD/linux-sources/linux-v6.8-fs/fs`
- source version: `linux-v6.8`
- review items: 4
- protocol candidates: 0
- discovery reviews: 4

## 1. btrfs_reloc_post_snapshot / mutation_failure_cleanup

- review id: `mocc_review_mocc_occurrence_1849bc3484239bd706ab`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_b.device_topology_rollback`
- operation: ``
- location: `btrfs/relocation.c`
- exit: `:`
- certainty: `review`
- family: `mocc_family_15e59460e3e78dfc747a`

Review focus:

- Review protocol witness and source context for semantic mismatch.
- First decide whether this non-entry function is truly the same operation.

Likely development follow-ups:

- review may/unknown event provenance before promoting finding

Witness:

- L4596 `compensation`: btrfs_put_root(reloc_root)
- L4583 `failure_control`: return ret;
- L4582 `failure_guard`: (ret)
- L4579 `fallible_call`: btrfs_block_rsv_migrate(&pending->block_rsv,
					      rc->block_rsv,
					      rc->nodes_relocated, true) assigned to ret
- L4576 `state_mutation`: rc->merging_rsv_size += rc->nodes_relocated

Source context `btrfs/relocation.c:4572`:

```c
 4572: 	if (!rc || !have_reloc_root(root))
 4573: 		return 0;
 4574: 
 4575: 	rc = root->fs_info->reloc_ctl;
 4576: 	rc->merging_rsv_size += rc->nodes_relocated;
 4577: 
 4578: 	if (rc->merge_reloc_tree) {
 4579: 		ret = btrfs_block_rsv_migrate(&pending->block_rsv,
 4580: 					      rc->block_rsv,
```

Source context `btrfs/relocation.c:4575`:

```c
 4575: 	rc = root->fs_info->reloc_ctl;
 4576: 	rc->merging_rsv_size += rc->nodes_relocated;
 4577: 
 4578: 	if (rc->merge_reloc_tree) {
 4579: 		ret = btrfs_block_rsv_migrate(&pending->block_rsv,
 4580: 					      rc->block_rsv,
 4581: 					      rc->nodes_relocated, true);
 4582: 		if (ret)
 4583: 			return ret;
```

Source context `btrfs/relocation.c:4578`:

```c
 4578: 	if (rc->merge_reloc_tree) {
 4579: 		ret = btrfs_block_rsv_migrate(&pending->block_rsv,
 4580: 					      rc->block_rsv,
 4581: 					      rc->nodes_relocated, true);
 4582: 		if (ret)
 4583: 			return ret;
 4584: 	}
 4585: 
 4586: 	new_root = pending->snap;
```

Source context `btrfs/relocation.c:4579`:

```c
 4579: 		ret = btrfs_block_rsv_migrate(&pending->block_rsv,
 4580: 					      rc->block_rsv,
 4581: 					      rc->nodes_relocated, true);
 4582: 		if (ret)
 4583: 			return ret;
 4584: 	}
 4585: 
 4586: 	new_root = pending->snap;
 4587: 	reloc_root = create_reloc_root(trans, root->reloc_root,
```

Source context `btrfs/relocation.c:4592`:

```c
 4592: 	ret = __add_reloc_root(reloc_root);
 4593: 	ASSERT(ret != -EEXIST);
 4594: 	if (ret) {
 4595: 		/* Pairs with create_reloc_root */
 4596: 		btrfs_put_root(reloc_root);
 4597: 		return ret;
 4598: 	}
 4599: 	new_root->reloc_root = btrfs_grab_root(reloc_root);
 4600: 
```

## 2. clean_dirty_subvols / mutation_failure_cleanup

- review id: `mocc_review_mocc_occurrence_d5bf2221444cb451f4e7`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_b.device_topology_rollback`
- operation: ``
- location: `btrfs/relocation.c`
- exit: `:`
- certainty: `review`
- family: `mocc_family_ec883cd5b4bf1a43c46b`

Review focus:

- Review protocol witness and source context for semantic mismatch.
- First decide whether this non-entry function is truly the same operation.

Likely development follow-ups:

- review may/unknown event provenance before promoting finding

Witness:

- L1652 `compensation`: list_del_init(&root->reloc_dirty_list)
- L1684 `failure_control`: return ret;
- L1667 `failure_guard`: (ret2 < 0)
- L1666 `fallible_call`: btrfs_drop_snapshot(reloc_root, 0, 1) assigned to ret2
- L1653 `state_mutation`: root->reloc_root = NULL

Source context `btrfs/relocation.c:1648`:

```c
 1648: 		if (root->root_key.objectid != BTRFS_TREE_RELOC_OBJECTID) {
 1649: 			/* Merged subvolume, cleanup its reloc root */
 1650: 			struct btrfs_root *reloc_root = root->reloc_root;
 1651: 
 1652: 			list_del_init(&root->reloc_dirty_list);
 1653: 			root->reloc_root = NULL;
 1654: 			/*
 1655: 			 * Need barrier to ensure clear_bit() only happens after
 1656: 			 * root->reloc_root = NULL. Pairs with have_reloc_root.
```

Source context `btrfs/relocation.c:1649`:

```c
 1649: 			/* Merged subvolume, cleanup its reloc root */
 1650: 			struct btrfs_root *reloc_root = root->reloc_root;
 1651: 
 1652: 			list_del_init(&root->reloc_dirty_list);
 1653: 			root->reloc_root = NULL;
 1654: 			/*
 1655: 			 * Need barrier to ensure clear_bit() only happens after
 1656: 			 * root->reloc_root = NULL. Pairs with have_reloc_root.
 1657: 			 */
```

Source context `btrfs/relocation.c:1662`:

```c
 1662: 				 * btrfs_drop_snapshot drops our ref we hold for
 1663: 				 * ->reloc_root.  If it fails however we must
 1664: 				 * drop the ref ourselves.
 1665: 				 */
 1666: 				ret2 = btrfs_drop_snapshot(reloc_root, 0, 1);
 1667: 				if (ret2 < 0) {
 1668: 					btrfs_put_root(reloc_root);
 1669: 					if (!ret)
 1670: 						ret = ret2;
```

Source context `btrfs/relocation.c:1663`:

```c
 1663: 				 * ->reloc_root.  If it fails however we must
 1664: 				 * drop the ref ourselves.
 1665: 				 */
 1666: 				ret2 = btrfs_drop_snapshot(reloc_root, 0, 1);
 1667: 				if (ret2 < 0) {
 1668: 					btrfs_put_root(reloc_root);
 1669: 					if (!ret)
 1670: 						ret = ret2;
 1671: 				}
```

Source context `btrfs/relocation.c:1680`:

```c
 1680: 					ret = ret2;
 1681: 			}
 1682: 		}
 1683: 	}
 1684: 	return ret;
 1685: }
 1686: 
 1687: /*
 1688:  * merge the relocated tree blocks in reloc tree with corresponding
```

## 3. ext4_ext_clear_bb / failure_return_mismatch

- review id: `mocc_review_mocc_occurrence_685b9ccb333d70dc098b`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: ``
- location: `ext4/extents.c`
- exit: `:`
- certainty: `review`
- family: `mocc_family_878c8140d286e962e139`

Review focus:

- Review protocol witness and source context for semantic mismatch.
- First decide whether this non-entry function is truly the same operation.

Likely development follow-ups:

- review may/unknown event provenance before promoting finding

Witness:

- L6099 `compensation`: ext4_free_ext_path(path)
- L6110 `failure_guard`: (ret < 0)
- L6110 `failure_to_success_exit`: failure branch for ret reaches return 0;
- L6109 `fallible_call`: ext4_map_blocks(NULL, inode, &map, 0) assigned to ret
- L6131 `success_exit`: return 0;

Source context `ext4/extents.c:6095`:

```c
 6095: 	if (IS_ERR(path))
 6096: 		return PTR_ERR(path);
 6097: 	ex = path[path->p_depth].p_ext;
 6098: 	if (!ex) {
 6099: 		ext4_free_ext_path(path);
 6100: 		return 0;
 6101: 	}
 6102: 	end = le32_to_cpu(ex->ee_block) + ext4_ext_get_actual_len(ex);
 6103: 	ext4_free_ext_path(path);
```

Source context `ext4/extents.c:6105`:

```c
 6105: 	cur = 0;
 6106: 	while (cur < end) {
 6107: 		map.m_lblk = cur;
 6108: 		map.m_len = end - cur;
 6109: 		ret = ext4_map_blocks(NULL, inode, &map, 0);
 6110: 		if (ret < 0)
 6111: 			break;
 6112: 		if (ret > 0) {
 6113: 			path = ext4_find_extent(inode, map.m_lblk, NULL, 0);
```

Source context `ext4/extents.c:6106`:

```c
 6106: 	while (cur < end) {
 6107: 		map.m_lblk = cur;
 6108: 		map.m_len = end - cur;
 6109: 		ret = ext4_map_blocks(NULL, inode, &map, 0);
 6110: 		if (ret < 0)
 6111: 			break;
 6112: 		if (ret > 0) {
 6113: 			path = ext4_find_extent(inode, map.m_lblk, NULL, 0);
 6114: 			if (!IS_ERR_OR_NULL(path)) {
```

Source context `ext4/extents.c:6127`:

```c
 6127: 		}
 6128: 		cur = cur + map.m_len;
 6129: 	}
 6130: 
 6131: 	return 0;
 6132: }
```

## 4. ext4_ext_replay_set_iblocks / failure_return_mismatch

- review id: `mocc_review_mocc_occurrence_9f2246437df4f9b06eb0`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_a.replay_recovery`
- operation: ``
- location: `ext4/extents.c`
- exit: `:`
- certainty: `review`
- family: `mocc_family_2cd198a6dcf5df9ec459`

Review focus:

- Review protocol witness and source context for semantic mismatch.
- First decide whether this non-entry function is truly the same operation.

Likely development follow-ups:

- review may/unknown event provenance before promoting finding

Witness:

- L6004 `compensation`: ext4_free_ext_path(path)
- L6016 `failure_guard`: (ret < 0)
- L6016 `failure_to_success_exit`: failure branch for ret reaches return 0;
- L6015 `fallible_call`: ext4_map_blocks(NULL, inode, &map, 0) assigned to ret
- L6078 `success_exit`: return 0;

Source context `ext4/extents.c:6000`:

```c
 6000: 	if (IS_ERR(path))
 6001: 		return PTR_ERR(path);
 6002: 	ex = path[path->p_depth].p_ext;
 6003: 	if (!ex) {
 6004: 		ext4_free_ext_path(path);
 6005: 		goto out;
 6006: 	}
 6007: 	end = le32_to_cpu(ex->ee_block) + ext4_ext_get_actual_len(ex);
 6008: 	ext4_free_ext_path(path);
```

Source context `ext4/extents.c:6011`:

```c
 6011: 	cur = 0;
 6012: 	while (cur < end) {
 6013: 		map.m_lblk = cur;
 6014: 		map.m_len = end - cur;
 6015: 		ret = ext4_map_blocks(NULL, inode, &map, 0);
 6016: 		if (ret < 0)
 6017: 			break;
 6018: 		if (ret > 0)
 6019: 			numblks += ret;
```

Source context `ext4/extents.c:6012`:

```c
 6012: 	while (cur < end) {
 6013: 		map.m_lblk = cur;
 6014: 		map.m_len = end - cur;
 6015: 		ret = ext4_map_blocks(NULL, inode, &map, 0);
 6016: 		if (ret < 0)
 6017: 			break;
 6018: 		if (ret > 0)
 6019: 			numblks += ret;
 6020: 		cur = cur + map.m_len;
```

Source context `ext4/extents.c:6074`:

```c
 6074: 
 6075: out:
 6076: 	inode->i_blocks = numblks << (inode->i_sb->s_blocksize_bits - 9);
 6077: 	ext4_mark_inode_dirty(NULL, inode);
 6078: 	return 0;
 6079: }
 6080: 
 6081: int ext4_ext_clear_bb(struct inode *inode)
 6082: {
```
