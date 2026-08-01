# Confirmed Metadata Bug Corpus (P0.1)

Status: working corpus for manual protocol mining; not a loaded analyzer input.

Generated: 2026-07-31

Corpus version: `p0.1-v0.1`

## Provenance

The source record was recovered from `outputs/confirmed_bugs.md` at Git commit
`023b7bcf4ddb227bdba3ad26d2782a5cc72ea067` (blob
`348111bcf9ac4ab1cc9b27ab5ca703fef042c33b`). The migrated source has SHA-256
`d90cddfed582bcc4bcd32b40a17932baa7433ae16144350332be439af01d0e96` and is
preserved verbatim in [`confirmed-bugs-source.md`](confirmed-bugs-source.md).

This table applies the FMPCA inclusion rule: a case must change a filesystem
metadata transition, a metadata-object relation, transaction/recovery
responsibility, or the agreement between transition outcome and actual
completion. A resource-lifetime defect alone is not sufficient. Missing source
version, patch, or reproduction details are recorded as `EVIDENCE_INCOMPLETE`
rather than filled from inference.

## Screening Table

| bug_id | filesystem | source version / commit | function and failure point | confirmation evidence | metadata relevance | include / exclude | decision rationale | candidate protocol family | development / validation / held-out role |
|---:|---|---|---|---|---|---|---|---|---|
| #1 | ext4 | Baseline version not recorded; fix branch `33b4ecd48982` | `ext4_fc_replay_add_range()` common `out:` returns success after range replay failure | Submitted error-propagation patch; source call chain recorded in source dossier | Fast-commit metadata replay outcome can report success after partial application | INCLUDE | The externally visible recovery outcome is inconsistent with the metadata transition; this is not merely cleanup | `MetadataTransitionOutcome` | VALIDATION |
| #2 | ext4 | Baseline version not recorded; same fix branch `33b4ecd48982` | `ext4_fc_replay_del_range()` swallows errors after delete-range state changes | Same submitted patch as #1; source-level confirmation | Delete replay can leave replay-side metadata partially changed while returning success | INCLUDE | Independent operation and failure path support the same outcome protocol; shared patch does not make it one bug | `MetadataTransitionOutcome` | VALIDATION |
| #3 | ext4 | Baseline version not recorded | `ext4_init_orphan_info()` skips `brelse()` for the current failed block | Patch v2; source-level confirmation | No metadata relation or transition rule is established; defect is a `buffer_head` reference leak | EXCLUDE | Generic resource lifetime only; no protocol role or relation evidence | `OUT_OF_SCOPE_RESOURCE_LIFETIME` | VALIDATION_NEGATIVE |
| #4 | ext4 | Baseline version not recorded; fix patch path in source record | `ext4_expand_extra_isize_ea()` returns stale `-ENOSPC` after successful fallback and inode update | Patch plus targeted ext4 image reproduction | Return outcome disagrees with completed inode metadata transition | INCLUDE | Direct metadata transition/outcome divergence with a normal retry path and a fixed path | `MetadataTransitionOutcome` | DEVELOPMENT |
| #5 | ext4 | Linux v6.8; upstream fix `ec0a7500d8eace5b4f305fa0c594dd148f0e8d29` | `ext4_fc_replay_inode()` swallows replay errors; `iloc.bh` leak treated separately | Upstream fix and v6.8 source comparison | Error/outcome part affects fast-commit metadata replay semantics | INCLUDE (error/outcome only) | The swallowed-error subcase is metadata outcome relevant; the `iloc.bh` leak is excluded from protocol evidence | `MetadataTransitionOutcome` | VALIDATION |
| #6 | btrfs | Linux v6.8 sparse tree | `__add_reloc_root()` leaks `mapping_node` on duplicate insertion | Source confirmation, ASan/LSan reproduction, patch review | No metadata relation transition is shown beyond allocation cleanup | EXCLUDE | Generic heap/resource lifetime; duplicate-key handling is not established as a filesystem metadata protocol | `OUT_OF_SCOPE_RESOURCE_LIFETIME` | VALIDATION_NEGATIVE |
| #7 | btrfs | Linux v6.8; fix commit `08f1ccb98abb` in follow-up branch | `btrfs_recover_relocation()` leaves `fs_root->reloc_root` attached on non-abort recovery failure | QEMU fault injection; maintainer acceptance into `for-next` | Recovery failure leaves an active metadata-root attachment and responsibility-dependent cleanup | INCLUDE | Cross-object relation and recovery responsibility are affected; `BTRFS_FS_ERROR` must not be used as implicit cleanup proof | `ActiveAttachmentSafety` | DEVELOPMENT |
| #8 | XFS | Linux v6.8; later mainline correction | `xfs_rtcopy_summary()` returns success after summary metadata copy failure | v6.8 source evidence, rediscovery candidates, later fixed source | Realtime summary metadata can be partially copied while caller observes success | INCLUDE | Independent XFS instance of transition/outcome mismatch with a caller error branch | `MetadataTransitionOutcome` | HELD_OUT |
| #9 | ext4 | Linux v6.8; corrected in Linux v7.1 snapshot | `ext4_dx_add_entry()` misses `brelse(bh2)` on journal error paths | v6.8/v7.1 source comparison | Only a `buffer_head` lifetime defect is evidenced | EXCLUDE | Generic resource lifetime; no metadata relation or outcome divergence evidence | `OUT_OF_SCOPE_RESOURCE_LIFETIME` | VALIDATION_NEGATIVE |
| #10 | ext4 | Linux v6.14; fixed in later mainline | `ext4_ext_shift_extents()` leaks `ext4_ext_path` on an unexpected extent path | Source audit and latest-tree comparison | Only path-object lifetime is evidenced | EXCLUDE | Generic resource lifetime; extent metadata semantics are not shown to diverge | `OUT_OF_SCOPE_RESOURCE_LIFETIME` | VALIDATION_NEGATIVE |
| #11 | F2FS | Linux v6.14; fixed in latest mainline | `f2fs_rename(RENAME_WHITEOUT)` leaks `f2fs_filename` buffer | Source audit and fixed latest-tree comparison | Only crypto/casefold buffer lifetime is evidenced | EXCLUDE | Generic resource lifetime; no whiteout metadata relation failure is established | `OUT_OF_SCOPE_RESOURCE_LIFETIME` | VALIDATION_NEGATIVE |
| #12 | XFS | Linux v6.14; fixed in latest mainline | `xfs_qm_quotacheck_dqadjust()` leaks a dquot reference after attach failure | Source audit and fixed latest-tree comparison | The record proves reference release, not quota metadata transition semantics | EXCLUDE | A dquot name alone does not establish metadata protocol relevance; evidence is reference lifetime only | `OUT_OF_SCOPE_RESOURCE_LIFETIME` | VALIDATION_NEGATIVE |
| #13 | XFS | Linux v6.14; latest recheck `a13c140cc289c0b7b3770bce5b3ad42ab35074aa` | `xfs_rtginode_ensure()` treats non-`ENOENT` load errors as success | Source-level confirmation and submitted patch evidence | Realtime metadata inode load failure is converted into an apparent successful ensure | INCLUDE | Caller-visible outcome and metadata object existence contract diverge | `MetadataTransitionOutcome` | HELD_OUT |
| #14 | F2FS | Latest sparse checkout based on `a13c140cc289c0b7b3770bce5b3ad42ab35074aa` | `find_in_level()` retains `dentry_folio` after `find_in_block()` error | v1/v2 patch messages and Reviewed-by | Only folio reference lifetime is evidenced | EXCLUDE | Generic resource lifetime; no directory metadata relation or outcome violation is demonstrated | `OUT_OF_SCOPE_RESOURCE_LIFETIME` | VALIDATION_NEGATIVE |
| #15 | btrfs | Linux v6.14 | `reserve_chunk_space()` lets positive zoned activation success skip chunk metadata reservation | Instrumented host-managed zoned `null_blk` reproduction; patch v2 and Reviewed-by | Metadata reservation obligation is skipped despite successful block-group activation | INCLUDE | Positive-success value changes a later metadata reservation decision; this is a transition-local outcome contract | `CompanionMetadataCompletion` | DEVELOPMENT (singleton family) |
| #16 | btrfs | Baseline commit not recorded; patch series evidence | `btrfs_init_new_device()` leaves failed sprout device on transaction update list | Targeted seed/sprout fault injection; patch 1/3 | Failed metadata/device transition leaves transaction responsibility attached to a released device | INCLUDE | Transaction update-list ownership is a metadata operation responsibility, not a generic allocation leak | `TransactionResponsibility` | DEVELOPMENT (singleton family) |
| #17 | btrfs | Baseline commit not recorded; patch series evidence | `btrfs_init_new_device()` leaves `latest_dev`/`s_bdev` pointing at failed sprout device | Targeted fault injection; reproduced stale/freed active pointer; patch 2/3 | Active metadata/device pointer relation is invalid after failure | INCLUDE | Cross-object identity and active attachment are directly affected | `ActiveAttachmentSafety` | VALIDATION (singleton family) |
| #18 | btrfs | Baseline commit not recorded; patch series evidence | `btrfs_init_new_device()` fails to roll back sprout `fs_devices` state after device-add failure | Targeted fault injection; assertion/kernel BUG before fix; patch 3/3 | Metadata container state and transaction/recovery outcome diverge after failed transition | INCLUDE | The filesystem remains in a partially initialized metadata state; this is stronger than local cleanup | `FailureRollbackConformance` | DEVELOPMENT |

## Role Policy

The roles above are the P0.6 split recorded in
`docs/protocol-mining/evaluation-split.md`. `DEVELOPMENT` cases may change a
candidate protocol. `VALIDATION` cases check a stabilized draft and scope
negatives. `HELD_OUT` cases (#8 and #13) must not alter a frozen `AcceptP`; any
unresolved binding must result in `INCOMPLETE`. The deferred singleton family
#15 has no manufactured held-out case and is not frozen in Catalog v0.1.

This table is not a Protocol Catalog and does not freeze any rule. Protocol
guards may only be derived later from independent documentation/design evidence
and normal or fixed source paths. Bug identifiers in this file are evidence
references, not permitted protocol predicates.

## Immediate Evidence Gaps

The source record does not consistently preserve the exact baseline commit for
#1, #2, #4, and #16-#18. Those cases remain included because their source,
patch, and reproduction evidence establishes the relevant semantic failure, but
the missing baseline identity must be resolved in the per-bug dossiers before
Gate P. No protocol obligation should be invented to compensate for that gap.
