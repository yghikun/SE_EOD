# CFG-added Candidate Triage

Generated: 2026-07-12T17:02:59.280550+00:00

Inputs:

- Before: `outputs\experiment-v1.4\linux-v6.8\ext4\ranked_candidates.jsonl`
- After: `outputs\experiment-v1.5-cfg\linux-v6.8\ext4\ranked_candidates.jsonl`

## Summary

| Before | After | Retained | Added | Removed |
|---:|---:|---:|---:|---:|
| 19 | 29 | 18 | 11 | 1 |

Added candidate families:

- `__ext4_new_inode.journal_handle_stop`: 7
- `ext4_expand_extra_isize_ea.stale_retry_contract`: 1
- `ext4_ext_shift_extents.path_kfree_direct_return`: 1
- `ext4_init_orphan_info.partial_cleanup_duplicate`: 2

Interpretation: CFG/path-sensitive analysis is surfacing review evidence; candidate-count increase is not treated as a precision loss, and duplicate/path-id drift rows are not suppressed from raw analyzer output.

## Added Candidate Triage

| Candidate | Location | Type | Evidence | Family | Disposition | Note |
|---|---|---|---|---|---|---|
| `candidate_cbf05c8486ab` | fs/ext4/extents.c:5241 `ext4_ext_shift_extents` | `missing_cleanup` | E2_API_PROTOCOL_SUPPORTED / 60 | `ext4_ext_shift_extents.path_kfree_direct_return` | `retain_plausible_true_positive` | Direct error return bypasses the out: cleanup after ext4_find_extent() produced path; keep as a plausible resource-leak finding pending patch/dynamic validation. |
| `candidate_b56aa8cdb611` | fs/ext4/ialloc.c:1090 `__ext4_new_inode` | `missing_cleanup` | E2_API_PROTOCOL_SUPPORTED / 80 | `__ext4_new_inode.journal_handle_stop` | `retain_high_value_needs_validation` | CFG exposes a family of journal-handle paths acquired by __ext4_journal_start_sb() and returning through out: without a visible ext4_journal_stop(handle). Do not auto-suppress; validate ext4 current-handle semantics or reproduce dynamically. |
| `candidate_3e38c6b50850` | fs/ext4/ialloc.c:1110 `__ext4_new_inode` | `missing_cleanup` | E2_API_PROTOCOL_SUPPORTED / 80 | `__ext4_new_inode.journal_handle_stop` | `retain_high_value_needs_validation` | CFG exposes a family of journal-handle paths acquired by __ext4_journal_start_sb() and returning through out: without a visible ext4_journal_stop(handle). Do not auto-suppress; validate ext4 current-handle semantics or reproduce dynamically. |
| `candidate_3217f0ff3ae4` | fs/ext4/ialloc.c:1125 `__ext4_new_inode` | `missing_cleanup` | E2_API_PROTOCOL_SUPPORTED / 45 | `__ext4_new_inode.journal_handle_stop` | `retain_high_value_needs_validation` | CFG exposes a family of journal-handle paths acquired by __ext4_journal_start_sb() and returning through out: without a visible ext4_journal_stop(handle). Do not auto-suppress; validate ext4 current-handle semantics or reproduce dynamically. |
| `candidate_670436be1ab8` | fs/ext4/ialloc.c:1133 `__ext4_new_inode` | `missing_cleanup` | E2_API_PROTOCOL_SUPPORTED / 45 | `__ext4_new_inode.journal_handle_stop` | `retain_high_value_needs_validation` | CFG exposes a family of journal-handle paths acquired by __ext4_journal_start_sb() and returning through out: without a visible ext4_journal_stop(handle). Do not auto-suppress; validate ext4 current-handle semantics or reproduce dynamically. |
| `candidate_101776b5ca31` | fs/ext4/ialloc.c:1144 `__ext4_new_inode` | `missing_cleanup` | E2_API_PROTOCOL_SUPPORTED / 45 | `__ext4_new_inode.journal_handle_stop` | `retain_high_value_needs_validation` | CFG exposes a family of journal-handle paths acquired by __ext4_journal_start_sb() and returning through out: without a visible ext4_journal_stop(handle). Do not auto-suppress; validate ext4 current-handle semantics or reproduce dynamically. |
| `candidate_0cc5f9380e13` | fs/ext4/ialloc.c:1151 `__ext4_new_inode` | `missing_cleanup` | E2_API_PROTOCOL_SUPPORTED / 45 | `__ext4_new_inode.journal_handle_stop` | `retain_high_value_needs_validation` | CFG exposes a family of journal-handle paths acquired by __ext4_journal_start_sb() and returning through out: without a visible ext4_journal_stop(handle). Do not auto-suppress; validate ext4 current-handle semantics or reproduce dynamically. |
| `candidate_d24b7abbeedc` | fs/ext4/ialloc.c:1173 `__ext4_new_inode` | `missing_cleanup` | E2_API_PROTOCOL_SUPPORTED / 45 | `__ext4_new_inode.journal_handle_stop` | `retain_high_value_needs_validation` | CFG exposes a family of journal-handle paths acquired by __ext4_journal_start_sb() and returning through out: without a visible ext4_journal_stop(handle). Do not auto-suppress; validate ext4 current-handle semantics or reproduce dynamically. |
| `candidate_02ee93edfc17` | fs/ext4/orphan.c:610 `ext4_init_orphan_info` | `partial_cleanup` | E2_API_PROTOCOL_SUPPORTED / 33 | `ext4_init_orphan_info.partial_cleanup_duplicate` | `duplicate_evidence_retain_missing_cleanup_primary` | Partial-cleanup view duplicates the same confirmed orphan-file buffer_head leak already emitted as missing_cleanup; keep the missing_cleanup row as the primary benchmark-positive ID. Duplicate of candidate_65d848d5f1fd. |
| `candidate_def03dceca5d` | fs/ext4/orphan.c:615 `ext4_init_orphan_info` | `partial_cleanup` | E2_API_PROTOCOL_SUPPORTED / 33 | `ext4_init_orphan_info.partial_cleanup_duplicate` | `duplicate_evidence_retain_missing_cleanup_primary` | Partial-cleanup view duplicates the same confirmed orphan-file buffer_head leak already emitted as missing_cleanup; keep the missing_cleanup row as the primary benchmark-positive ID. Duplicate of candidate_f3e8e44a00d3. |
| `candidate_4c72269f064d` | fs/ext4/xattr.c:2837 `ext4_expand_extra_isize_ea` | `stale_error_after_retry` | E0_STATIC_RULE_ONLY / 30 | `ext4_expand_extra_isize_ea.stale_retry_contract` | `known_finding_path_id_renumbered` | Known stale-error-after-retry contract finding; the CFG pass renumbered the path_id, so treat as stable-finding drift rather than a new semantic regression. |

## Removed Stable Keys

| Candidate | Location | Type | Evidence |
|---|---|---|---|
| `candidate_ad40dbc309ac` | fs/ext4/xattr.c:2837 `ext4_expand_extra_isize_ea` | `stale_error_after_retry` | E0_STATIC_RULE_ONLY / 30 |
