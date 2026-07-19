# F2FS Maintainer Feedback

Date: 2026-07-19

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
- Current classification: retained as a source-level confirmed candidate based
  on the caller-owned folio analysis, but final maintainer resolution is
  pending.  Do not send a v2 until that reply arrives.

## Current Count Impact

- Confirmed bug records: 19, reduced from 20.
- Already fixed in upstream/mainline: 6.
- Submitted or under review and not recorded as merged: 13.
- `f2fs_get_new_data_folio()` is not included in any of those counts.

