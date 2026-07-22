# XFS Tempfile Exchange Transaction Audit

This audit records source-visible facts for a high-ranked MOCC-SE
manual review item. It is not a confirmed-bug report.

- source root: `E:/yanjiusheng/阅读论文/file_system/SE_EOD/linux-sources/linux-v7.1-fs/fs`
- source version: `7.1`
- target helper: `xrep_tempexch_trans_alloc`
- helper definition: `xfs/scrub/tempfile.c:838`
- result semantics: `source_facts_not_bug_claims`
- bug claims allowed: `False`
- conclusion: `strong_manual_review_candidate_not_confirmed_bug`

## Summary

- `target_helper_allocates_sc_tp`: True
- `target_helper_returns_quota_result`: True
- `quota_helper_has_failure_return_without_cleanup`: True
- `callers`: 6
- `callers_returning_error_without_visible_cleanup`: 6
- `bug_claims_allowed`: 0

## Helper facts

- `allocates_sc_tp` at `xfs/scrub/tempfile.c:862`: error = xfs_trans_alloc(sc->mp, &M_RES(sc->mp)->tr_itruncate, tx->req.resblks, 0, flags, &sc->tp);
- `returns_quota_reserve_result` at `xfs/scrub/tempfile.c:871`: return xrep_tempexch_reserve_quota(sc, tx);
- `return_after_alloc_without_visible_cleanup` at `xfs/scrub/tempfile.c:871`: return xrep_tempexch_reserve_quota(sc, tx);
- `quota_failure_return_without_cleanup` at `xfs/scrub/tempfile.c:776`: return error;
- `quota_direct_failure_return_without_cleanup` at `xfs/scrub/tempfile.c:780`: return xfs_trans_reserve_quota_nblks(tp, req->ip2, ddelta + req->ip2_bcount, rdelta + req->ip2_rtbcount, true);

## Caller facts

### xrep_xattr_finalize_tempfile

- callsite: `xfs/scrub/attr_repair.c:1389`
- call statement: `return xrep_tempexch_trans_alloc(sc, XFS_ATTR_FORK, &rx->tx);`
- error return without visible cleanup: `True`

- `callsite` at `xfs/scrub/attr_repair.c:1389`: return xrep_tempexch_trans_alloc(sc, XFS_ATTR_FORK, &rx->tx);
- `caller_directly_returns_helper_result` at `xfs/scrub/attr_repair.c:1389`: return xrep_tempexch_trans_alloc(sc, XFS_ATTR_FORK, &rx->tx);

### xrep_xattr_finalize_tempfile

- callsite: `xfs/scrub/attr_repair.c:1402`
- call statement: `error = xrep_tempexch_trans_alloc(sc, XFS_ATTR_FORK, &rx->tx);`
- error return without visible cleanup: `True`

- `callsite` at `xfs/scrub/attr_repair.c:1402`: error = xrep_tempexch_trans_alloc(sc, XFS_ATTR_FORK, &rx->tx);
- `caller_error_return_without_visible_cleanup` at `xfs/scrub/attr_repair.c:1403`: if (error) return error;

### xrep_dir_finalize_tempdir

- callsite: `xfs/scrub/dir_repair.c:1609`
- call statement: `return xrep_tempexch_trans_alloc(sc, XFS_DATA_FORK, &rd->tx);`
- error return without visible cleanup: `True`

- `callsite` at `xfs/scrub/dir_repair.c:1609`: return xrep_tempexch_trans_alloc(sc, XFS_DATA_FORK, &rd->tx);
- `caller_directly_returns_helper_result` at `xfs/scrub/dir_repair.c:1609`: return xrep_tempexch_trans_alloc(sc, XFS_DATA_FORK, &rd->tx);

### xrep_dir_finalize_tempdir

- callsite: `xfs/scrub/dir_repair.c:1622`
- call statement: `error = xrep_tempexch_trans_alloc(sc, XFS_DATA_FORK, &rd->tx);`
- error return without visible cleanup: `True`

- `callsite` at `xfs/scrub/dir_repair.c:1622`: error = xrep_tempexch_trans_alloc(sc, XFS_DATA_FORK, &rd->tx);
- `caller_error_return_without_visible_cleanup` at `xfs/scrub/dir_repair.c:1623`: if (error) return error;

### xrep_parent_finalize_tempfile

- callsite: `xfs/scrub/parent_repair.c:1238`
- call statement: `error = xrep_tempexch_trans_alloc(sc, XFS_ATTR_FORK, &rp->tx);`
- error return without visible cleanup: `True`

- `callsite` at `xfs/scrub/parent_repair.c:1238`: error = xrep_tempexch_trans_alloc(sc, XFS_ATTR_FORK, &rp->tx);
- `caller_error_return_without_visible_cleanup` at `xfs/scrub/parent_repair.c:1239`: if (error) return error;

### xrep_symlink_rebuild

- callsite: `xfs/scrub/symlink_repair.c:463`
- call statement: `error = xrep_tempexch_trans_alloc(sc, XFS_DATA_FORK, tx);`
- error return without visible cleanup: `True`

- `callsite` at `xfs/scrub/symlink_repair.c:463`: error = xrep_tempexch_trans_alloc(sc, XFS_DATA_FORK, tx);
- `caller_error_return_without_visible_cleanup` at `xfs/scrub/symlink_repair.c:464`: if (error) return error;

## Interpretation

The audited source shape is stronger than a generic analyzer gap:
the helper can return quota-reservation errors after creating
`sc->tp`, and the immediate callers often propagate that error
without a visible local cleanup.  This remains a source-fact
audit, not a confirmed bug claim, because the final obligation
depends on XFS scrub transaction ownership semantics outside the
current protocol freeze.
