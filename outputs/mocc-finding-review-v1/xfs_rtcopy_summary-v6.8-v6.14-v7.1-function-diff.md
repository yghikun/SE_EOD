# Function diff: xfs_rtcopy_summary

This is a MOCC-SE development source-diff artifact, not benchmark evidence.

Inputs:

- `v6.8`: found, L87-L119, `linux-sources/linux-v6.8-fs/fs/xfs/xfs_rtalloc.c`
- `v6.14`: found, L97-L129, `linux-sources/linux-v6.14-fs/fs/xfs/xfs_rtalloc.c`
- `v7.1`: found, L98-L133, `linux-sources/linux-v7.1-fs/fs/xfs/xfs_rtalloc.c`

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
- `added_corruption_guard`
- `callee_set_expanded`
- `callee_set_reduced`

Unified diff:

```diff
--- v6.14:linux-sources/linux-v6.14-fs/fs/xfs/xfs_rtalloc.c
+++ v7.1:linux-sources/linux-v7.1-fs/fs/xfs/xfs_rtalloc.c
@@ -15,6 +15,10 @@
 			error = xfs_rtget_summary(oargs, log, bbno, &sum);
 			if (error)
 				goto out;
+			if (XFS_IS_CORRUPT(oargs->mp, sum < 0)) {
+				error = -EFSCORRUPTED;
+				goto out;
+			}
 			if (sum == 0)
 				continue;
 			error = xfs_rtmodify_summary(oargs, log, bbno, -sum);
@@ -23,11 +27,10 @@
 			error = xfs_rtmodify_summary(nargs, log, bbno, sum);
 			if (error)
 				goto out;
-			ASSERT(sum > 0);
 		}
 	}
 	error = 0;
 out:
 	xfs_rtbuf_cache_relse(oargs);
-	return 0;
+	return error;
 }
```
