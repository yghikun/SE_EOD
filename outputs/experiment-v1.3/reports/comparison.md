# SE-EOD Experiment v1.3 Comparison

Generated: 2026-07-12T12:17:34.543651+00:00

The v1.3 runs use static analysis, protocol evidence, wrapper summaries, and ownership hints. Historical LLM verdicts and manual-review scores are excluded.

## Archived Outputs vs v1.3

| Version | FS | Old | v1.3 | Retained | Removed | Added | Reduction |
|---|---|---:|---:|---:|---:|---:|---:|
| linux-v6.8 | ext4 | 38 | 16 | 15 | 23 | 1 | 57.9% |
| linux-v6.8 | btrfs | 248 | 5 | 5 | 243 | 0 | 98.0% |
| linux-v6.8 | xfs | 87 | 6 | 3 | 84 | 3 | 93.1% |
| linux-v6.8 | f2fs | 74 | 0 | 0 | 74 | 0 | 100.0% |
| linux-v7.1 | ext4 | 15 | 13 | 13 | 2 | 0 | 13.3% |
| linux-v7.1 | btrfs | 543 | 543 | 543 | 0 | 0 | 0.0% |
| linux-v7.1 | xfs | 8 | 8 | 8 | 0 | 0 | 0.0% |
| linux-v7.1 | f2fs | 4 | 4 | 4 | 0 | 0 | 0.0% |

## v1.3 Cross-Version Comparison

| FS | v6.8 | v7.1 | Persisted | Only v6.8 | Only v7.1 | Delta |
|---|---:|---:|---:|---:|---:|---:|
| ext4 | 16 | 13 | 10 | 6 | 3 | -3 |
| btrfs | 5 | 543 | 0 | 5 | 543 | +538 |
| xfs | 6 | 8 | 0 | 6 | 8 | +2 |
| f2fs | 0 | 4 | 0 | 0 | 4 | +4 |

## ext4 v6.8 Pilot Retention

- True-bug retention: 100.0%
- False-positive retention: 0.0%
- Retained labels: `{'true_bug': 11}`

## btrfs v6.8 to v7.1

- Candidate delta: +538
- v7.1-only attribution: `{'candidate_changed_in_existing_function': 482, 'function_absent_from_other_error_corpus': 61}`
- `BTRFS_PATH_AUTO_FREE` occurrences in v7.1 C files: 154
- Candidates in auto-free functions: 475
- `btrfs_free_path` missing-cleanup candidates in auto-free functions: 472 (86.9% of all v7.1 btrfs candidates)
- Interpretation: the v7.1 btrfs spike is dominated by a scope-aware cleanup modeling gap, not evidence of 538 new bugs.
- Top v7.1-only functions:

  - `create_subvol`: 21
  - `btrfs_compare_trees`: 20
  - `btrfs_search_path_in_tree_user`: 16
  - `btrfs_get_subvol_name_from_objectid`: 15
  - `btrfs_mark_extent_written`: 15
  - `__btrfs_free_extent`: 14
  - `extent_fiemap`: 14
  - `__btrfs_balance`: 13
  - `btrfs_insert_data_csums`: 12
  - `populate_free_space_tree`: 11
  - `btrfs_clone`: 10
  - `replay_xattr_deletes`: 10
  - `copy_items`: 8
  - `scrub_enumerate_chunks`: 8
  - `btrfs_read_chunk_tree`: 8
