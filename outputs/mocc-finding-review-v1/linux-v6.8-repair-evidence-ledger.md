# MOCC-SE Repair Evidence Ledger

This is development repair evidence, not a frozen benchmark or confirmed-bug list.

- triage source: `outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.json`
- repair sources: 2
- triage items: 19
- items with repair evidence: 7

Repair hints:

- `added_corruption_guard`: 2
- `callee_set_expanded`: 2
- `callee_set_reduced`: 2
- `local_return_propagation_repair`: 7
- `return_success_changed_to_error_symbol`: 7

## 12. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_1b96d3faaab09e3c91d2`
- protocol: `mocc.protocol_a.replay_recovery`
- triage verdict: `candidate_survives_initial_review`

Evidence `v6.14` -> `v7.1`:

- hint: `return_success_changed_to_error_symbol`
- hint: `local_return_propagation_repair`
- removed returns: `return -EFSCORRUPTED;`, `return 0;`
- added returns: `return ret;`
- source diff: `outputs/mocc-finding-review-v1/ext4_fc_replay_inode-v6.8-v6.14-v7.1-function-diff.json`

## 13. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_3e4f1c944e82245ff46d`
- protocol: `mocc.protocol_a.replay_recovery`
- triage verdict: `candidate_survives_initial_review`

Evidence `v6.14` -> `v7.1`:

- hint: `return_success_changed_to_error_symbol`
- hint: `local_return_propagation_repair`
- removed returns: `return -EFSCORRUPTED;`, `return 0;`
- added returns: `return ret;`
- source diff: `outputs/mocc-finding-review-v1/ext4_fc_replay_inode-v6.8-v6.14-v7.1-function-diff.json`

## 14. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_5748c6c26760e1c2f625`
- protocol: `mocc.protocol_a.replay_recovery`
- triage verdict: `candidate_survives_initial_review`

Evidence `v6.14` -> `v7.1`:

- hint: `return_success_changed_to_error_symbol`
- hint: `local_return_propagation_repair`
- removed returns: `return -EFSCORRUPTED;`, `return 0;`
- added returns: `return ret;`
- source diff: `outputs/mocc-finding-review-v1/ext4_fc_replay_inode-v6.8-v6.14-v7.1-function-diff.json`

## 15. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_d8ce5780d59918326ede`
- protocol: `mocc.protocol_a.replay_recovery`
- triage verdict: `candidate_survives_initial_review`

Evidence `v6.14` -> `v7.1`:

- hint: `return_success_changed_to_error_symbol`
- hint: `local_return_propagation_repair`
- removed returns: `return -EFSCORRUPTED;`, `return 0;`
- added returns: `return ret;`
- source diff: `outputs/mocc-finding-review-v1/ext4_fc_replay_inode-v6.8-v6.14-v7.1-function-diff.json`

## 16. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_e3968a5e986534d82167`
- protocol: `mocc.protocol_a.replay_recovery`
- triage verdict: `candidate_survives_initial_review`

Evidence `v6.14` -> `v7.1`:

- hint: `return_success_changed_to_error_symbol`
- hint: `local_return_propagation_repair`
- removed returns: `return -EFSCORRUPTED;`, `return 0;`
- added returns: `return ret;`
- source diff: `outputs/mocc-finding-review-v1/ext4_fc_replay_inode-v6.8-v6.14-v7.1-function-diff.json`

## 18. xfs_rtcopy_summary / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_028bc7698b4b215c4e89`
- protocol: `mocc.protocol_a.replay_recovery`
- triage verdict: `candidate_survives_initial_review`

Evidence `v6.14` -> `v7.1`:

- hint: `return_success_changed_to_error_symbol`
- hint: `local_return_propagation_repair`
- hint: `added_corruption_guard`
- hint: `callee_set_expanded`
- hint: `callee_set_reduced`
- removed returns: `return 0;`
- added returns: `return error;`
- source diff: `outputs/mocc-finding-review-v1/xfs_rtcopy_summary-v6.8-v6.14-v7.1-function-diff.json`

## 19. xfs_rtcopy_summary / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_26ae1e03588221460d20`
- protocol: `mocc.protocol_a.replay_recovery`
- triage verdict: `candidate_survives_initial_review`

Evidence `v6.14` -> `v7.1`:

- hint: `return_success_changed_to_error_symbol`
- hint: `local_return_propagation_repair`
- hint: `added_corruption_guard`
- hint: `callee_set_expanded`
- hint: `callee_set_reduced`
- removed returns: `return 0;`
- added returns: `return error;`
- source diff: `outputs/mocc-finding-review-v1/xfs_rtcopy_summary-v6.8-v6.14-v7.1-function-diff.json`
