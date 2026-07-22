# MOCC-SE Batch Scan Triage

This is an initial source triage ledger. It is not a confirmed-bug list and not a frozen benchmark result.

- batch report: `outputs/mocc-batch-scan-v1/linux-v7.1-fs.json`
- source version: `7.1`
- result semantics: `candidate_queue_not_bug_claims`
- bug claims allowed: `False`

Summary:

- `triage_items`: 15
- `by_verdict`: {'needs_external_semantics': 2, 'uncertain': 13}
- `by_priority`: {'P0': 2, 'P2': 13}
- `by_protocol`: {'mocc.protocol_a.replay_recovery': 2, 'mocc.protocol_d.transaction_lifecycle': 9, 'mocc.protocol_e.allocation_lifecycle': 4}
- `manual_bug_review_candidates`: 0
- `needs_protocol_instance`: 0
- `needs_external_semantics`: 2
- `likely_false_positive`: 0

## 1. __add_block_group_free_space

- review id: `mocc_occurrence_8867eaff966d3bef3ef0`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_e.allocation_lifecycle`
- source: `btrfs/free-space-tree.c`
- pattern: ``
- verdict: `uncertain`
- priority: `P2`
- confidence: `low`
- rationale: No specialized triage rule matched this review record.

Evidence:

- effect_created line 1428: btrfs.search_path.allocation
- exit line 1431: return -ENOMEM;

Follow-ups:

- add a triage rule or perform manual source review

## 2. btrfs_quota_enable

- review id: `mocc_occurrence_a558403a1ff9166e4b51`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_e.allocation_lifecycle`
- source: `btrfs/qgroup.c`
- pattern: ``
- verdict: `uncertain`
- priority: `P2`
- confidence: `low`
- rationale: No specialized triage rule matched this review record.

Evidence:

- effect_created line 1083: btrfs.search_path.allocation
- exit line 1304: return ret;

Follow-ups:

- add a triage rule or perform manual source review

## 3. btrfs_symlink

- review id: `mocc_occurrence_9e21bad18ca2c4a79a79`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_e.allocation_lifecycle`
- source: `btrfs/inode.c`
- pattern: ``
- verdict: `uncertain`
- priority: `P2`
- confidence: `low`
- rationale: No specialized triage rule matched this review record.

Evidence:

- effect_created line 9086: btrfs.search_path.allocation
- exit line 9131: return ret;

Follow-ups:

- add a triage rule or perform manual source review

## 4. ext4_convert_unwritten_extents

- review id: `mocc_occurrence_138878426d50f029fd22`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_d.transaction_lifecycle`
- source: `ext4/extents.c`
- pattern: ``
- verdict: `uncertain`
- priority: `P2`
- confidence: `low`
- rationale: No specialized triage rule matched this review record.

Evidence:

- effect_created line 5055: ext4.journal_handle.lifecycle
- exit line 5086: return ret > 0 ? ret2 : ret;

Follow-ups:

- add a triage rule or perform manual source review

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

## 7. ext4_generic_write_inline_data

- review id: `mocc_occurrence_3ba316f25ba5048ff781`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_d.transaction_lifecycle`
- source: `ext4/inline.c`
- pattern: ``
- verdict: `uncertain`
- priority: `P2`
- confidence: `low`
- rationale: No specialized triage rule matched this review record.

Evidence:

- effect_created line 713: ext4.journal_handle.lifecycle
- exit line 764: return 1;

Follow-ups:

- add a triage rule or perform manual source review

## 8. ext4_write_begin

- review id: `mocc_occurrence_f98cd489f05e397b0a88`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_d.transaction_lifecycle`
- source: `ext4/inode.c`
- pattern: ``
- verdict: `uncertain`
- priority: `P2`
- confidence: `low`
- rationale: No specialized triage rule matched this review record.

Evidence:

- effect_created line 1351: ext4.journal_handle.lifecycle
- exit line 1417: return ret;

Follow-ups:

- add a triage rule or perform manual source review

## 9. inode_logged

- review id: `mocc_occurrence_c2dbfa8a270586f6e002`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_e.allocation_lifecycle`
- source: `btrfs/tree-log.c`
- pattern: ``
- verdict: `uncertain`
- priority: `P2`
- confidence: `low`
- rationale: No specialized triage rule matched this review record.

Evidence:

- effect_created line 3810: btrfs.search_path.allocation
- exit line 3845: return 1;

Follow-ups:

- add a triage rule or perform manual source review

## 10. xfs_setfilesize

- review id: `mocc_occurrence_c08e090c7354a96ef01a`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_d.transaction_lifecycle`
- source: `xfs/xfs_aops.c`
- pattern: ``
- verdict: `uncertain`
- priority: `P2`
- confidence: `low`
- rationale: No specialized triage rule matched this review record.

Evidence:

- effect_created line 62: xfs.transaction.lifecycle
- effect_compensated line 70: xfs.transaction.lifecycle
- exit line 71: return 0;

Follow-ups:

- add a triage rule or perform manual source review

## 11. xfs_trans_alloc_dir

- review id: `mocc_occurrence_cfaec856ddae285829ce`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_d.transaction_lifecycle`
- source: `xfs/xfs_trans.c`
- pattern: ``
- verdict: `uncertain`
- priority: `P2`
- confidence: `low`
- rationale: No specialized triage rule matched this review record.

Evidence:

- effect_created line 1381: xfs.transaction.lifecycle
- exit line 1434: return 0;

Follow-ups:

- add a triage rule or perform manual source review

## 12. xfs_trans_alloc_ichange

- review id: `mocc_occurrence_634b54908c6d728b4cb8`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_d.transaction_lifecycle`
- source: `xfs/xfs_trans.c`
- pattern: ``
- verdict: `uncertain`
- priority: `P2`
- confidence: `low`
- rationale: No specialized triage rule matched this review record.

Evidence:

- effect_created line 1263: xfs.transaction.lifecycle
- exit line 1343: return 0;

Follow-ups:

- add a triage rule or perform manual source review

## 13. xfs_trans_alloc_icreate

- review id: `mocc_occurrence_fe7156b8eaaeaf7bbed7`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_d.transaction_lifecycle`
- source: `xfs/xfs_trans.c`
- pattern: ``
- verdict: `uncertain`
- priority: `P2`
- confidence: `low`
- rationale: No specialized triage rule matched this review record.

Evidence:

- effect_created line 1206: xfs.transaction.lifecycle
- exit line 1233: return 0;

Follow-ups:

- add a triage rule or perform manual source review

## 14. xfs_trans_alloc_inode

- review id: `mocc_occurrence_b28745824da1ba46d18f`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_d.transaction_lifecycle`
- source: `xfs/xfs_trans.c`
- pattern: ``
- verdict: `uncertain`
- priority: `P2`
- confidence: `low`
- rationale: No specialized triage rule matched this review record.

Evidence:

- effect_created line 1080: xfs.transaction.lifecycle
- exit line 1108: return 0;

Follow-ups:

- add a triage rule or perform manual source review

## 15. xrep_tempexch_trans_alloc

- review id: `mocc_occurrence_1fc1c33b4bd4c975a22d`
- classification: `DISCOVERY_REVIEW`
- protocol: `mocc.protocol_d.transaction_lifecycle`
- source: `xfs/scrub/tempfile.c`
- pattern: ``
- verdict: `uncertain`
- priority: `P2`
- confidence: `low`
- rationale: No specialized triage rule matched this review record.

Evidence:

- effect_created line 862: xfs.transaction.lifecycle
- exit line 871: return xrep_tempexch_reserve_quota(sc, tx);

Follow-ups:

- add a triage rule or perform manual source review
