# MOCC-SE Initial Source Triage

This is a development triage ledger, not a frozen benchmark or a confirmed-bug list.

- review queue: `outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.json`
- decisions: `<source_review>`
- triage items: 19
- reviewed items: 19
- unreviewed items: 0

Verdicts:

- `candidate_survives_initial_review`: 19

Surviving candidates by protocol:

- `mocc.protocol_a.replay_recovery`: 15
- `mocc.protocol_b.device_topology_rollback`: 2
- `mocc.protocol_c.activation_accounting`: 2

## 1. reserve_chunk_space / metadata_state_divergence

- review id: `mocc_review_mocc_occurrence_1fdcd64a328daf121598`
- protocol: `mocc.protocol_c.activation_accounting`
- location: `btrfs/block-group.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- The activation-changed path is modeled by ret > 0. The later reservation call is under if (!ret), so that path skips btrfs_block_rsv_add and reaches the void success exit with pending chunk metadata work.
- This is source-level development triage only; it is not counted as benchmark evidence.

Development follow-ups:

- Keep as a Protocol C finding candidate and compare against later/fixed versions before paper-stage adjudication.

Notes: derived from reviewed queue source_review

## 2. btrfs_recover_relocation / incomplete_failure_completion

- review id: `mocc_review_mocc_occurrence_1c504a8198f68f2b16af`
- protocol: `mocc.protocol_b.device_topology_rollback`
- location: `btrfs/relocation.c`
- verdict: `candidate_survives_initial_review`
- confidence: `medium`

Source evidence:

- fs_root->reloc_root is attached before the recovery commit. On commit failure, the visible failure path runs unset/free cleanup but no local compensation that clears the attached reloc_root pointer.
- Confidence is medium because the local source path is clear, but cross-function ownership outside this slice should still be checked before claiming a confirmed bug.

Development follow-ups:

- Keep as a Protocol B candidate and inspect fixed-version source or patch context to decide final adjudication.

Notes: derived from reviewed queue source_review

## 3. btrfs_init_new_device / incomplete_failure_completion

- review id: `mocc_review_mocc_occurrence_084190f9e1fa5b21424c`
- protocol: `mocc.protocol_b.device_topology_rollback`
- location: `btrfs/volumes.c`
- verdict: `candidate_survives_initial_review`
- confidence: `medium`

Source evidence:

- The finish_sprout failure path removes the new device list entries and counters, but the visible cleanup does not restore the sprout topology or active s_bdev/latest_dev effects introduced before the failure.
- The candidate remains source-supported rather than a final bug claim.

Development follow-ups:

- Keep as a Protocol B seed/sprout topology candidate and compare later source for rollback helpers or explicit restoration.

Notes: derived from reviewed queue source_review

## 4. ext4_fc_replay_add_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_494f361a7b84fadf6d2e`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `ext4/fast_commit.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- Multiple necessary replay steps can fail, yet the reviewed local paths reach return 0 without a proven retry, sentinel fallback, abort, recovery delegation, or propagated error.
- This annotation intentionally covers all add-range occurrences in the queue.

Development follow-ups:

- Keep these Protocol A add-range candidates as one reviewed development family; later count root causes separately from occurrence count.

Notes: derived from reviewed queue source_review

## 5. ext4_fc_replay_add_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_5b6b5526d4f1d1930526`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `ext4/fast_commit.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- Multiple necessary replay steps can fail, yet the reviewed local paths reach return 0 without a proven retry, sentinel fallback, abort, recovery delegation, or propagated error.
- This annotation intentionally covers all add-range occurrences in the queue.

Development follow-ups:

- Keep these Protocol A add-range candidates as one reviewed development family; later count root causes separately from occurrence count.

Notes: derived from reviewed queue source_review

## 6. ext4_fc_replay_add_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_67bc885339c21d674412`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `ext4/fast_commit.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- Multiple necessary replay steps can fail, yet the reviewed local paths reach return 0 without a proven retry, sentinel fallback, abort, recovery delegation, or propagated error.
- This annotation intentionally covers all add-range occurrences in the queue.

Development follow-ups:

- Keep these Protocol A add-range candidates as one reviewed development family; later count root causes separately from occurrence count.

Notes: derived from reviewed queue source_review

## 7. ext4_fc_replay_add_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_c85a2865849c465c67b8`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `ext4/fast_commit.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- Multiple necessary replay steps can fail, yet the reviewed local paths reach return 0 without a proven retry, sentinel fallback, abort, recovery delegation, or propagated error.
- This annotation intentionally covers all add-range occurrences in the queue.

Development follow-ups:

- Keep these Protocol A add-range candidates as one reviewed development family; later count root causes separately from occurrence count.

Notes: derived from reviewed queue source_review

## 8. ext4_fc_replay_add_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_e901bdddd2188d9c7135`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `ext4/fast_commit.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- Multiple necessary replay steps can fail, yet the reviewed local paths reach return 0 without a proven retry, sentinel fallback, abort, recovery delegation, or propagated error.
- This annotation intentionally covers all add-range occurrences in the queue.

Development follow-ups:

- Keep these Protocol A add-range candidates as one reviewed development family; later count root causes separately from occurrence count.

Notes: derived from reviewed queue source_review

## 9. ext4_fc_replay_del_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_451a8159d7ebc634d05b`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `ext4/fast_commit.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- Necessary delete-range replay steps can fail and still reach return 0; no source-visible allowed sentinel, retry success, abort, or recovery delegation closes the failure tokens.
- This annotation intentionally covers all delete-range occurrences in the queue.

Development follow-ups:

- Keep these Protocol A delete-range candidates as one reviewed development family.

Notes: derived from reviewed queue source_review

## 10. ext4_fc_replay_del_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_733ee0e26506eb6c017e`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `ext4/fast_commit.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- Necessary delete-range replay steps can fail and still reach return 0; no source-visible allowed sentinel, retry success, abort, or recovery delegation closes the failure tokens.
- This annotation intentionally covers all delete-range occurrences in the queue.

Development follow-ups:

- Keep these Protocol A delete-range candidates as one reviewed development family.

Notes: derived from reviewed queue source_review

## 11. ext4_fc_replay_del_range / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_769c3f15a6f7dfa5c159`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `ext4/fast_commit.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- Necessary delete-range replay steps can fail and still reach return 0; no source-visible allowed sentinel, retry success, abort, or recovery delegation closes the failure tokens.
- This annotation intentionally covers all delete-range occurrences in the queue.

Development follow-ups:

- Keep these Protocol A delete-range candidates as one reviewed development family.

Notes: derived from reviewed queue source_review

## 12. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_1b96d3faaab09e3c91d2`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `ext4/fast_commit.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- Necessary inode replay and metadata-dirtying steps can fail, but the reviewed paths reach return 0 without a proven legal failure completion.
- This annotation intentionally covers all inode replay occurrences in the queue.

Development follow-ups:

- Keep these Protocol A inode replay candidates as one reviewed development family.

Notes: derived from reviewed queue source_review

## 13. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_3e4f1c944e82245ff46d`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `ext4/fast_commit.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- Necessary inode replay and metadata-dirtying steps can fail, but the reviewed paths reach return 0 without a proven legal failure completion.
- This annotation intentionally covers all inode replay occurrences in the queue.

Development follow-ups:

- Keep these Protocol A inode replay candidates as one reviewed development family.

Notes: derived from reviewed queue source_review

## 14. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_5748c6c26760e1c2f625`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `ext4/fast_commit.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- Necessary inode replay and metadata-dirtying steps can fail, but the reviewed paths reach return 0 without a proven legal failure completion.
- This annotation intentionally covers all inode replay occurrences in the queue.

Development follow-ups:

- Keep these Protocol A inode replay candidates as one reviewed development family.

Notes: derived from reviewed queue source_review

## 15. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_d8ce5780d59918326ede`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `ext4/fast_commit.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- Necessary inode replay and metadata-dirtying steps can fail, but the reviewed paths reach return 0 without a proven legal failure completion.
- This annotation intentionally covers all inode replay occurrences in the queue.

Development follow-ups:

- Keep these Protocol A inode replay candidates as one reviewed development family.

Notes: derived from reviewed queue source_review

## 16. ext4_fc_replay_inode / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_e3968a5e986534d82167`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `ext4/fast_commit.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- Necessary inode replay and metadata-dirtying steps can fail, but the reviewed paths reach return 0 without a proven legal failure completion.
- This annotation intentionally covers all inode replay occurrences in the queue.

Development follow-ups:

- Keep these Protocol A inode replay candidates as one reviewed development family.

Notes: derived from reviewed queue source_review

## 17. ext4_expand_extra_isize_ea / metadata_state_divergence

- review id: `mocc_review_mocc_occurrence_894bc776d438d17f786e`
- protocol: `mocc.protocol_c.activation_accounting`
- location: `ext4/xattr.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- The failed inode-space attempt keeps its failure return provenance, but the later path updates i_extra_isize and returns that stale failure result.
- This records the M6/M8 source observation; no networking, security, or permission assumption is involved.

Development follow-ups:

- Keep the stale-return Protocol C candidate and use version-diff review to confirm the repair pattern.

Notes: derived from reviewed queue source_review

## 18. xfs_rtcopy_summary / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_028bc7698b4b215c4e89`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `xfs/xfs_rtalloc.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- The realtime summary copy path can ignore failed get/modify summary steps and still return 0, with no source-visible retry or propagated error on the witnessed paths.
- This annotation intentionally covers both xfs_rtcopy_summary occurrences.

Development follow-ups:

- Keep as a Protocol A cross-filesystem validation candidate; use later-version source comparison for repair confirmation.

Notes: derived from reviewed queue source_review

## 19. xfs_rtcopy_summary / failure_reported_as_success

- review id: `mocc_review_mocc_occurrence_26ae1e03588221460d20`
- protocol: `mocc.protocol_a.replay_recovery`
- location: `xfs/xfs_rtalloc.c`
- verdict: `candidate_survives_initial_review`
- confidence: `high`

Source evidence:

- The realtime summary copy path can ignore failed get/modify summary steps and still return 0, with no source-visible retry or propagated error on the witnessed paths.
- This annotation intentionally covers both xfs_rtcopy_summary occurrences.

Development follow-ups:

- Keep as a Protocol A cross-filesystem validation candidate; use later-version source comparison for repair confirmation.

Notes: derived from reviewed queue source_review
