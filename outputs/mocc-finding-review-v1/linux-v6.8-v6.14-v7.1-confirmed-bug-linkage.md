# MOCC-SE Confirmed Bug Linkage

This is a development linkage report, not a frozen benchmark or a new-submission list.

- bug-hunt report: `outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-development-bug-hunt-report.json`
- confirmed bugs: `outputs/confirmed_bugs.md`
- candidate links: 22
- candidates with confirmed bug: 22
- candidates without confirmed bug: 0
- confirmed bug records: 18
- confirmed bug records linked: 11
- confirmed bug records outside this queue: 7

Status classes:

- `confirmed_fixed_duplicate`: 6
- `confirmed_for_next`: 1
- `confirmed_submitted`: 9
- `confirmed_submitted_reviewed`: 2

Candidate links:

- `ext4_fc_replay_inode` / `failure_reported_as_success` / `repair_evidence_first` -> #5 `confirmed_fixed_duplicate`
- `ext4_fc_replay_inode` / `failure_reported_as_success` / `repair_evidence_first` -> #5 `confirmed_fixed_duplicate`
- `ext4_fc_replay_inode` / `failure_reported_as_success` / `repair_evidence_first` -> #5 `confirmed_fixed_duplicate`
- `ext4_fc_replay_inode` / `failure_reported_as_success` / `repair_evidence_first` -> #5 `confirmed_fixed_duplicate`
- `ext4_fc_replay_inode` / `failure_reported_as_success` / `repair_evidence_first` -> #5 `confirmed_fixed_duplicate`
- `xfs_rtcopy_summary` / `failure_reported_as_success` / `repair_evidence_first` -> #8 `confirmed_fixed_duplicate`
- `xfs_rtcopy_summary` / `failure_reported_as_success` / `repair_evidence_first` -> #8 `confirmed_fixed_duplicate`
- `reserve_chunk_space` / `metadata_state_divergence` / `persistent_candidates_next` -> #15 `confirmed_submitted_reviewed`
- `btrfs_recover_relocation` / `incomplete_failure_completion` / `persistent_candidates_next` -> #7 `confirmed_for_next`
- `btrfs_init_new_device` / `incomplete_failure_completion` / `persistent_candidates_next` -> #16 `confirmed_submitted`, #17 `confirmed_submitted`, #18 `confirmed_submitted`
- `ext4_fc_replay_add_range` / `failure_reported_as_success` / `persistent_candidates_next` -> #1 `confirmed_submitted`
- `ext4_fc_replay_add_range` / `failure_reported_as_success` / `persistent_candidates_next` -> #1 `confirmed_submitted`
- `ext4_fc_replay_add_range` / `failure_reported_as_success` / `persistent_candidates_next` -> #1 `confirmed_submitted`
- `ext4_fc_replay_add_range` / `failure_reported_as_success` / `persistent_candidates_next` -> #1 `confirmed_submitted`
- `ext4_fc_replay_add_range` / `failure_reported_as_success` / `persistent_candidates_next` -> #1 `confirmed_submitted`
- `ext4_fc_replay_del_range` / `failure_reported_as_success` / `persistent_candidates_next` -> #2 `confirmed_submitted`
- `ext4_fc_replay_del_range` / `failure_reported_as_success` / `persistent_candidates_next` -> #2 `confirmed_submitted`
- `ext4_fc_replay_del_range` / `failure_reported_as_success` / `persistent_candidates_next` -> #2 `confirmed_submitted`
- `ext4_expand_extra_isize_ea` / `metadata_state_divergence` / `persistent_candidates_next` -> #4 `confirmed_submitted`
- `ext4_fc_replay_inode` / `` / `removed_or_cleared_functions` -> #5 `confirmed_fixed_duplicate`
- `xfs_rtcopy_summary` / `` / `removed_or_cleared_functions` -> #8 `confirmed_fixed_duplicate`
- `xfs_rtginode_ensure` / `` / `added_functions_to_inspect` -> #13 `confirmed_submitted`

Confirmed records outside this bug-hunt queue:

These records remain confirmed; absence here only means that the current M9 queue did not select them.

- #3 `ext4_init_orphan_info` / `confirmed_submitted`
- #6 `__add_reloc_root` / `confirmed_submitted`
- #9 `ext4_dx_add_entry` / `confirmed_fixed_duplicate`
- #10 `ext4_ext_shift_extents` / `confirmed_fixed_duplicate`
- #11 `f2fs_rename() with RENAME_WHITEOUT` / `confirmed_fixed_duplicate`
- #12 `xfs_qm_quotacheck_dqadjust` / `confirmed_fixed_duplicate`
- #14 `find_in_level` / `confirmed_submitted_reviewed`
