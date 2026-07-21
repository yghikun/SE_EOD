# F2FS Maintainer Feedback

> MOCC-SE migration note (2026-07-21): this file records resource-lifetime review evidence. It remains useful for the SE-EOD baseline but is not itself evidence for metadata operation completion consistency.

Date: 2026-07-21

This file records upstream review outcomes for the three F2FS folio-lifetime
patches submitted in July 2026.  It separates maintainer-confirmed results from
submitted hypotheses so that patch-email counts are not mistaken for confirmed
bug counts.

## `find_in_level()`

- Finding: missing `f2fs_folio_put(dentry_folio, false)` when
  `find_in_block()` returns an error.
- Maintainer result: Chao Yu requested `Fixes` and `Cc: stable@vger.kernel.org`
  and provided `Reviewed-by: Chao Yu <chao@kernel.org>`.
- Review:
  `https://lore.kernel.org/linux-f2fs-devel/8f354c53-18d9-4cf2-8ca6-e7476210c171@kernel.org/`
- v2 Message-ID: `<20260719084514.586-1-3497809730@qq.com>`
- Current classification: confirmed bug; v2 submitted; not yet recorded as
  merged upstream.

## `f2fs_get_new_data_folio()`

- Proposed finding: caller-provided `ifolio` leak after
  `f2fs_reserve_block()` failure.
- Maintainer result: Chao Yu stated that the caller handles the folio.
- Review:
  `https://lore.kernel.org/linux-f2fs-devel/bfb4dffb-e02a-480c-bb91-29cf97b48e66@kernel.org/`
- Withdrawal reply Message-ID:
  `<20260719090143.972-1-3497809730@qq.com>`
- Current classification: false positive after maintainer review; patch
  withdrawn; excluded from confirmed-bug and submitted-fix totals.

## `f2fs_move_inline_dirents()`

- Proposed finding: caller-provided `ifolio` is not released when
  `f2fs_reserve_block()` fails.
- Maintainer result: Chao Yu asked whether `f2fs_reserve_block()` handles the
  error internally.
- Review:
  `https://lore.kernel.org/linux-f2fs-devel/c9081653-4295-4605-b543-ee84000b1ba4@kernel.org/`
- Technical clarification reply Message-ID:
  `<20260719090519.1473-1-3497809730@qq.com>`
- Follow-up review:
  `https://lore.kernel.org/linux-f2fs-devel/b3a3d74c-338d-422f-b2c7-84ad00a9187d@kernel.org/`
- Final maintainer result: Chao Yu pointed out that `err` being non-zero makes
  `if (err || need_put)` call `f2fs_put_dnode(dn)` regardless of `need_put`.
  This releases `dn.inode_folio` on the proposed error path.
- Current classification: false positive after maintainer review; patch
  withdrawn on 2026-07-21; excluded from confirmed-bug and submitted-fix
  totals.

## Current Count Impact

- Confirmed bug records: 18, reduced from 20 after two F2FS false positives.
- Already fixed in upstream/mainline: 6.
- Submitted or under review and not recorded as merged: 12.
- `f2fs_get_new_data_folio()` and `f2fs_move_inline_dirents()` are not included
  in any of those counts.
