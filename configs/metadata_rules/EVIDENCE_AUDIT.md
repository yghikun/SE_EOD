# Independent Evidence Audit for the Nine Heuristic Rules

Audit date: 2026-07-22

This audit separates evidence that constructs an executable rule from evidence
that independently corroborates it. A project-authored patch or reproducer is
not counted as independent evidence. A maintainer or reviewer reply to such a
patch is independent evidence, but `for-next` is not described as a Linus
mainline merge.

| Rule | Independent evidence | Claim coverage | Decision | Remaining gap |
|---|---|---|---|---|
| `mocc.rule.replay.ext4.required_step_outcome` | Mainline commit `ec0a7500d8ea` changes `ext4_fc_replay_inode()` from unconditional success to returning the replay error; two independent Reviewed-by tags | Directly confirms the required-step outcome rule in one bound ext4 replay operation | `confirmed` | The exact `add_range` and `del_range` instances still rely on versioned implementation evidence |
| `mocc.rule.replay.xfs.summary_outcome` | Mainline commit `6b2d15536658` says `xfs_rtcopy_summary()` must return its error instead of `0` | Exact function and exact return obligation | `confirmed` | No validation/frozen sample |
| `mocc.rule.replay.xfs.ensure_sentinel` | Carlos Maiolino applied the exact fix to XFS `for-next` as `b7e53968cb88`; Christoph Hellwig separately reviewed it | Exact `-ENOENT` versus fatal-error distinction | `confirmed` | `for-next` is not recorded as a Linus mainline merge; no validation/frozen sample |
| `mocc.rule.topology.relocation_root_rollback` | David Sterba replied `Added to for-next, thanks.` to the exact cleanup patch | Exact relocation-root owner/rollback obligation | `confirmed` | `for-next` is not recorded as a Linus mainline merge; no validation/frozen sample |
| `mocc.rule.topology.sprout_multi_effect_rollback` | Mainline commit `70958a949d85` fixes an incorrect global readonly-state mutation in the same sprout device-add operation | Confirms that sprout add mutates persistent in-memory global state and needs state discipline, but does not cover the configured list, active-pointer, and `fs_devices` rollback effects | `heuristic` | Independent review or accepted fix for the three configured rollback effects |
| `mocc.rule.return.retry_current_attempt` | Jan Kara replied `Indeed` and supplied Reviewed-by for clearing the stale error before retry | Exact stale-attempt return provenance obligation | `confirmed` | No validation/frozen sample; no mainline commit recorded |
| `mocc.rule.accounting.pending_requires_reservation` | Johannes Thumshirn supplied Reviewed-by for the missing chunk reservation diagnosis while requesting cleanup and zoned fstests | Exact positive-success-to-reservation obligation | `confirmed` | Requested broader zoned testing is not a frozen evaluation set; no mainline commit recorded |
| `mocc.rule.transaction.xfs.lifecycle` | Versioned official XFS design documents define the one-shot `xfs_trans_alloc()` to `xfs_trans_commit()` pattern and state that commit releases joined resources | Covers normal allocation, commit, and release; does not define every failure cancellation or explicit transfer exit | `heuristic` | A complete official failure-path contract or an independent same-object leak/cancel fix for the registered operation |
| `mocc.rule.allocation.btrfs.search_path_release` | Mainline commit `d54a83901055` fixes a path free-after-free in the exact `btrfs_get_parent()` function and restructures its exits to free the allocated path once | Exact function, object type, release API, and post-allocation exits | `confirmed` | No validation/frozen sample |

All fourteen external artifacts in registry v2.2 are pinned by immutable or
versioned locators, SHA-256, and exact excerpts. Run:

```powershell
python -m src.metadata_evidence_verifier
```

The resulting authority distribution is one `normative`, seven `confirmed`,
and two `heuristic` rules. All ten rules remain `development`; authority does
not substitute for unseen validation or frozen evaluation evidence.
