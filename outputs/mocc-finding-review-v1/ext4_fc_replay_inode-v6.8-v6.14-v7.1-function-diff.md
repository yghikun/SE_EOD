# Function diff: ext4_fc_replay_inode

This is a MOCC-SE development source-diff artifact, not benchmark evidence.

Inputs:

- `v6.8`: found, L1517-L1611, `linux-sources/linux-v6.8-fs/fs/ext4/fast_commit.c`
- `v6.14`: found, L1525-L1619, `linux-sources/linux-v6.14-fs/fs/ext4/fast_commit.c`
- `v7.1`: found, L1519-L1616, `linux-sources/linux-v7.1-fs/fs/ext4/fast_commit.c`

## v6.8 -> v6.14

Semantic hints:

- none

Unified diff:

```diff
# no source changes
```

## v6.14 -> v7.1

Semantic hints:

- `return_success_changed_to_error_symbol`
- `local_return_propagation_repair`

Unified diff:

```diff
--- v6.14:linux-sources/linux-v6.14-fs/fs/ext4/fast_commit.c
+++ v7.1:linux-sources/linux-v7.1-fs/fs/ext4/fast_commit.c
@@ -56,19 +56,21 @@
 	/* Immediately update the inode on disk. */
 	ret = ext4_handle_dirty_metadata(NULL, NULL, iloc.bh);
 	if (ret)
-		goto out;
+		goto out_brelse;
 	ret = sync_dirty_buffer(iloc.bh);
 	if (ret)
-		goto out;
+		goto out_brelse;
 	ret = ext4_mark_inode_used(sb, ino);
 	if (ret)
-		goto out;
+		goto out_brelse;
 
 	/* Given that we just wrote the inode on disk, this SHOULD succeed. */
 	inode = ext4_iget(sb, ino, EXT4_IGET_NORMAL);
 	if (IS_ERR(inode)) {
 		ext4_debug("Inode not found.");
-		return -EFSCORRUPTED;
+		inode = NULL;
+		ret = -EFSCORRUPTED;
+		goto out_brelse;
 	}
 
 	/*
@@ -85,11 +87,12 @@
 	ext4_inode_csum_set(inode, ext4_raw_inode(&iloc), EXT4_I(inode));
 	ret = ext4_handle_dirty_metadata(NULL, NULL, iloc.bh);
 	sync_dirty_buffer(iloc.bh);
+out_brelse:
 	brelse(iloc.bh);
 out:
 	iput(inode);
 	if (!ret)
 		blkdev_issue_flush(sb->s_bdev);
 
-	return 0;
+	return ret;
 }
```
