# MOCC-SE Batch Scan Triage

This is an initial source triage ledger. It is not a confirmed-bug list and not a frozen benchmark result.

- batch report: `outputs\mocc-batch-scan-v1\linux-v7.1-fs.json`
- source version: `7.1`
- result semantics: `candidate_queue_not_bug_claims`
- bug claims allowed: `False`

Summary:

- `triage_items`: 8
- `by_verdict`: {'likely_false_positive': 6, 'needs_external_semantics': 2}
- `by_priority`: {'P0': 2, 'P2': 6}
- `by_protocol`: {'mocc.protocol_a.replay_recovery': 2, 'mocc.protocol_d.transaction_lifecycle': 1, 'mocc.protocol_e.allocation_lifecycle': 5}
- `manual_bug_review_candidates`: 0
- `needs_protocol_instance`: 0
- `needs_external_semantics`: 2
- `likely_false_positive`: 6

## 1. btrfs_del_inode_ref

- review id: `mocc_occurrence_7f06a68cd83c27414a68`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_e.allocation_lifecycle`
- source: `btrfs/inode-item.c`
- pattern: `mutation_failure_cleanup`
- verdict: `likely_false_positive`
- priority: `P2`
- confidence: `high`
- rationale: The matched mutation is local preparation or local argument state, not a proven durable metadata effect.

Evidence:

- compensation line 212: btrfs_del_item(trans, root, path)
- failure_control line 188: return -ENOMEM;
- failure_guard line 187: (!path)
- fallible_call line 186: btrfs_alloc_path() assigned to path
- state_mutation line 184: key.offset = ref_objectid

Follow-ups:

- teach broad discovery to distinguish local/search-key/reservation preparation from metadata effects
- do not promote without a protocol object binding

## 2. btrfs_drop_extents

- review id: `mocc_occurrence_cd6d01f9acaf54e0da10`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_e.allocation_lifecycle`
- source: `btrfs/file.c`
- pattern: `mutation_failure_cleanup`
- verdict: `likely_false_positive`
- priority: `P2`
- confidence: `high`
- rationale: The matched mutation is local preparation or local argument state, not a proven durable metadata effect.

Evidence:

- compensation line 179: btrfs_drop_extent_map_range(inode, args->start, args->end - 1, false)
- failure_control line 174: goto out;
- failure_guard line 172: (!path)
- fallible_call line 171: btrfs_alloc_path() assigned to path
- state_mutation line 165: args->extent_inserted = false

Follow-ups:

- teach broad discovery to distinguish local/search-key/reservation preparation from metadata effects
- do not promote without a protocol object binding

## 3. btrfs_insert_inode_ref

- review id: `mocc_occurrence_1784fbdf1cc5f3068ff3`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_e.allocation_lifecycle`
- source: `btrfs/inode-item.c`
- pattern: `mutation_failure_cleanup`
- verdict: `likely_false_positive`
- priority: `P2`
- confidence: `high`
- rationale: The matched mutation is local preparation or local argument state, not a proven durable metadata effect.

Evidence:

- compensation line 353: btrfs_free_path(path)
- failure_control line 313: return -ENOMEM;
- failure_guard line 312: (!path)
- fallible_call line 311: btrfs_alloc_path() assigned to path
- state_mutation line 309: key.offset = ref_objectid

Follow-ups:

- teach broad discovery to distinguish local/search-key/reservation preparation from metadata effects
- do not promote without a protocol object binding

## 4. btrfs_read_block_groups

- review id: `mocc_occurrence_512afd994a02a6e4daff`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_e.allocation_lifecycle`
- source: `btrfs/block-group.c`
- pattern: `mutation_failure_cleanup`
- verdict: `likely_false_positive`
- priority: `P2`
- confidence: `high`
- rationale: The matched mutation is local preparation or local argument state, not a proven durable metadata effect.

Evidence:

- compensation line 2694: btrfs_release_path(path)
- failure_control line 2658: return -ENOMEM;
- failure_guard line 2657: (!path)
- fallible_call line 2656: btrfs_alloc_path() assigned to path
- state_mutation line 2655: key.offset = 0

Follow-ups:

- teach broad discovery to distinguish local/search-key/reservation preparation from metadata effects
- do not promote without a protocol object binding

## 5. ext4_ext_clear_bb

- review id: `mocc_occurrence_685b9ccb333d70dc098b`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_a.replay_recovery`
- source: `ext4/extents.c`
- pattern: `failure_return_mismatch`
- verdict: `needs_external_semantics`
- priority: `P0`
- confidence: `high`
- rationale: The ext4 fast-commit replay helper shape is source-visible, but the missing question is whether replay bookkeeping failures are required to abort replay or may be best-effort.

Evidence:

- compensation line 6275: ext4_free_ext_path(path)
- failure_guard line 6253: (ret < 0)
- failure_to_success_exit line 6253: failure branch for ret reaches return 0;
- fallible_call line 6252: ext4_map_blocks(NULL, inode, &map, 0) assigned to ret
- success_exit line 6276: return 0;

Follow-ups:

- run metadata_ext4_replay_bookkeeping_audit on the exact Linux source tree
- seek independent ext4 fast-commit replay contract, maintainer review, accepted fix, or fault-injection evidence
- do not promote into an active protocol instance until that semantic obligation is frozen

## 6. ext4_ext_replay_set_iblocks

- review id: `mocc_occurrence_9f2246437df4f9b06eb0`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_a.replay_recovery`
- source: `ext4/extents.c`
- pattern: `failure_return_mismatch`
- verdict: `needs_external_semantics`
- priority: `P0`
- confidence: `high`
- rationale: The ext4 fast-commit replay helper shape is source-visible, but the missing question is whether replay bookkeeping failures are required to abort replay or may be best-effort.

Evidence:

- compensation line 6222: ext4_free_ext_path(path)
- failure_guard line 6165: (ret < 0)
- failure_to_success_exit line 6165: failure branch for ret reaches return 0;
- fallible_call line 6164: ext4_map_blocks(NULL, inode, &map, 0) assigned to ret
- success_exit line 6224: return 0;

Follow-ups:

- run metadata_ext4_replay_bookkeeping_audit on the exact Linux source tree
- seek independent ext4 fast-commit replay contract, maintainer review, accepted fix, or fault-injection evidence
- do not promote into an active protocol instance until that semantic obligation is frozen

## 7. inode_logged

- review id: `mocc_occurrence_1e170728375d6675b12c`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_e.allocation_lifecycle`
- source: `btrfs/tree-log.c`
- pattern: `mutation_failure_cleanup`
- verdict: `likely_false_positive`
- priority: `P2`
- confidence: `high`
- rationale: The matched mutation is local preparation or local argument state, not a proven durable metadata effect.

Evidence:

- compensation line 3818: btrfs_release_path(path)
- failure_control line 3812: return -ENOMEM;
- failure_guard line 3811: (!path)
- fallible_call line 3810: btrfs_alloc_path() assigned to path
- state_mutation line 3807: key.offset = 0

Follow-ups:

- teach broad discovery to distinguish local/search-key/reservation preparation from metadata effects
- do not promote without a protocol object binding

## 8. xlog_finish_defer_ops

- review id: `mocc_occurrence_ae1860e1f975ce853bcf`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_d.transaction_lifecycle`
- source: `xfs/xfs_log_recover.c`
- pattern: `mutation_failure_cleanup`
- verdict: `likely_false_positive`
- priority: `P2`
- confidence: `high`
- rationale: The matched mutation is local preparation or local argument state, not a proven durable metadata effect.

Evidence:

- compensation line 2545: list_del_init(&dfc->dfc_list)
- failure_control line 2538: return error;
- failure_guard line 2536: (error)
- fallible_call line 2534: xfs_trans_alloc(mp, &resv, dfc->dfc_blkres,
				dfc->dfc_rtxres, XFS_TRANS_RESERVE, &tp) assigned to error
- state_mutation line 2532: resv.tr_logflags = XFS_TRANS_PERM_LOG_RES

Follow-ups:

- teach broad discovery to distinguish local/search-key/reservation preparation from metadata effects
- do not promote without a protocol object binding
