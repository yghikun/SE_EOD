# Linux v7.1 btrfs 95-Candidate Audit

> MOCC-SE migration note (2026-07-21): this source audit is historical evidence. The `btrfs_recover_relocation()` records motivate effect ownership and incomplete failure completion, but remain part of the protocol development set.

## Verdict

- Confirmed bugs: **4**
- False positives: **91**
- Uncertain: **0**
- Static candidates after the second cleanup-model ablation: **35**

Four candidate records (two paths, each emitted as missing and partial cleanup) represent the confirmed `btrfs_recover_relocation()` cleanup defect. The other 91 do not demonstrate their claimed missing-cleanup or swallowed-error defect.

## False-Positive Causes

| Cause | Candidates |
|---|---:|
| `compiler_managed_scope_cleanup` | 60 |
| `failed_acquisition_not_held` | 18 |
| `handled_page_sentinel` | 2 |
| `not_found_sentinel` | 2 |
| `pointer_error_sentinel` | 2 |
| `documented_recovery_policy` | 1 |
| `boolean_helper_result` | 1 |
| `fail_safe_fallback` | 1 |
| `best_effort_duplicate_or_insert_failure` | 1 |
| `short_add_sentinel` | 1 |
| `alias_has_scope_cleanup` | 1 |
| `callee_releases_on_error` | 1 |

## Highest-Frequency Functions

| Function | Candidates |
|---|---:|
| `create_subvol` | 21 |
| `btrfs_clone` | 10 |
| `copy_items` | 8 |
| `send_subvol_begin` | 5 |
| `create_reloc_root` | 5 |
| `btrfs_recover_relocation` | 4 |
| `btrfs_recover_log_trees` | 4 |
| `btrfs_find_orphan_roots` | 3 |
| `is_same_device` | 3 |
| `extent_writepage` | 2 |
| `btrfs_symlink` | 2 |
| `btrfs_quota_enable` | 2 |

## Reproducibility

- Original set: `experiment-v1.3.1/linux-v7.1/btrfs` (95).
- Added `AUTO_KFREE -> kfree` and `AUTO_KVFREE -> kvfree` from `fs/btrfs/misc.h`.
- Rerun set: `experiment-v1.3.2/linux-v7.1/btrfs` (35).
- Every retained candidate was classified by an explicit source-contract rule; the script fails if a retained candidate has no rule.
