# MOCC-SE Development Bug-Hunt Report

This report summarizes development findings only. It is not a frozen benchmark, a precision/recall table, or a confirmed-bug list.

Inputs:

- reviewed queue: `outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.json`
- triage: `outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.json`
- matrix: `outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-discovery-matrix.json`
- repair evidence: `outputs/mocc-finding-review-v1/linux-v6.8-repair-evidence-ledger.json`

Summary:

- review items: 19
- candidates surviving initial source review: 19
- items with repair evidence: 7
- version candidate occurrences: `{'v6.8': 19, 'v6.14': 20, 'v7.1': 14}`

Priority 1: repair-evidence-backed candidates

- `ext4_fc_replay_inode` / `failure_reported_as_success` / `mocc_review_mocc_occurrence_1b96d3faaab09e3c91d2`
- `ext4_fc_replay_inode` / `failure_reported_as_success` / `mocc_review_mocc_occurrence_3e4f1c944e82245ff46d`
- `ext4_fc_replay_inode` / `failure_reported_as_success` / `mocc_review_mocc_occurrence_5748c6c26760e1c2f625`
- `ext4_fc_replay_inode` / `failure_reported_as_success` / `mocc_review_mocc_occurrence_d8ce5780d59918326ede`
- `ext4_fc_replay_inode` / `failure_reported_as_success` / `mocc_review_mocc_occurrence_e3968a5e986534d82167`
- `xfs_rtcopy_summary` / `failure_reported_as_success` / `mocc_review_mocc_occurrence_028bc7698b4b215c4e89`
- `xfs_rtcopy_summary` / `failure_reported_as_success` / `mocc_review_mocc_occurrence_26ae1e03588221460d20`

Priority 2: persistent candidates needing patch/source context

- `reserve_chunk_space` / `metadata_state_divergence`
- `btrfs_recover_relocation` / `incomplete_failure_completion`
- `btrfs_init_new_device` / `incomplete_failure_completion`
- `ext4_fc_replay_add_range` / `failure_reported_as_success`
- `ext4_fc_replay_add_range` / `failure_reported_as_success`
- `ext4_fc_replay_add_range` / `failure_reported_as_success`
- `ext4_fc_replay_add_range` / `failure_reported_as_success`
- `ext4_fc_replay_add_range` / `failure_reported_as_success`
- `ext4_fc_replay_del_range` / `failure_reported_as_success`
- `ext4_fc_replay_del_range` / `failure_reported_as_success`
- `ext4_fc_replay_del_range` / `failure_reported_as_success`
- `ext4_expand_extra_isize_ea` / `metadata_state_divergence`

Priority 3: removed/cleared functions to mine for repair patterns

- `ext4_fc_replay_inode` / `mocc.protocol_a.replay_recovery`
- `xfs_rtcopy_summary` / `mocc.protocol_a.replay_recovery`

Priority 4: added functions to inspect for expanded operation context

- `xfs_rtginode_ensure` / `mocc.protocol_a.replay_recovery`
