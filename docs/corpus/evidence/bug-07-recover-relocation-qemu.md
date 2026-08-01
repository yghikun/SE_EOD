# Btrfs recover_relocation QEMU fault-injection report

> MOCC-SE migration note (2026-07-21): this report is dynamic evidence for `incomplete_failure_completion` and the rule that transaction/global error handling cannot be assumed to own every in-memory metadata effect.

Date: 2026-07-11

Target:

- Linux 6.8 Btrfs
- `fs/btrfs/relocation.c::btrfs_recover_relocation`
- suspected path: `fs_root->reloc_root = btrfs_grab_root(reloc_root)` followed by first recovery `btrfs_commit_transaction(trans)` failure

## Setup

Kernel tree:

- `/root/repro/linux-v6.8-ext4`

Build output:

- `/root/repro/build-v6.8-btrfs-se-eod/arch/x86/boot/bzImage`

Repro artifacts:

- `/root/repro/btrfs-reloc-repro/initramfs.cpio.gz`
- `/root/repro/btrfs-reloc-repro/btrfs-test.img`
- `/root/repro/btrfs-reloc-repro/btrfs-pending-noabort.img`
- `/root/repro/btrfs-reloc-repro/btrfs-pending-abort.img`
- `/root/repro/btrfs-reloc-repro/btrfs-pending-normal.img`

Logs:

- `/root/repro/btrfs-reloc-repro/make_pending.log`
- `/root/repro/btrfs-reloc-repro/recover_noabort.log`
- `/root/repro/btrfs-reloc-repro/recover_abort.log`
- `/root/repro/btrfs-reloc-repro/recover_normal.log`

## Diagnostic patch

Temporary diagnostic hooks were added to:

- `/root/repro/linux-v6.8-ext4/fs/btrfs/relocation.c`
- `/root/repro/linux-v6.8-ext4/fs/btrfs/disk-io.c`

Boot parameter:

```text
se_eod_btrfs_reloc_fail=crash_after_prepare_merge
se_eod_btrfs_reloc_fail=recover_noabort
se_eod_btrfs_reloc_fail=recover_abort
```

The patch logs lines prefixed with:

```text
SE_EOD_BTRFS_RELOC
```

## Pending relocation image

The `make_pending` run creates a Btrfs subvolume, 24 snapshots, starts balance, and panics after `prepare_to_merge()` only when in-memory fs roots actually have `reloc_root`.

Observed:

```text
phase=crash_after_prepare_merge roots_with_reloc_root=25 fs_error=0
Kernel panic - not syncing: SE_EOD_BTRFS_RELOC crash_after_prepare_merge
```

`btrfs inspect-internal dump-tree -t root` confirmed 25 on-disk `TREE_RELOC ROOT_ITEM` records.

## Recovery experiments

### Normal recovery

Command used no recovery failure injection.

Observed:

```text
phase=before_recover_first_commit roots_with_reloc_root=25 fs_error=0
SE_EOD_INIT recovery mount rc=0
BTRFS info: balance: ended with status: 0
```

Conclusion: the generated pending image is valid, and normal recovery succeeds.

### Noabort recovery failure

Injection:

```text
se_eod_btrfs_reloc_fail=recover_noabort
```

This simulates a caller-visible failure after `fs_root->reloc_root` is assigned, without setting `BTRFS_FS_ERROR`.

Observed:

```text
phase=before_recover_first_commit roots_with_reloc_root=25 fs_error=0
injecting noabort recovery failure before first commit
phase=out_unset_error roots_with_reloc_root=25 fs_error=0
failed to recover relocation: -5
SE_EOD_INIT recovery mount rc=255
```

During mount-failure cleanup:

```text
drop_and_free_fs_root root=<256..280> reloc_offset=<same> fs_error=0 root_refs=1 reloc_refs=1
```

No `dropping reloc_root` line was emitted.

Conclusion: if this recovery commit failure reaches `out_unset` without `BTRFS_FS_ERROR`, `fs_root->reloc_root` remains attached through `btrfs_drop_and_free_fs_root()`. This confirms the cleanup gap modeled by the candidate.

### Abort recovery failure

Injection:

```text
se_eod_btrfs_reloc_fail=recover_abort
```

This aborts the transaction before the first recovery commit, setting `BTRFS_FS_ERROR`.

Observed:

```text
phase=before_recover_first_commit roots_with_reloc_root=25 fs_error=0
Transaction aborted (error -5)
phase=out_unset_error roots_with_reloc_root=25 fs_error=-5
```

During mount-failure cleanup, `btrfs_drop_and_free_fs_root()` emitted `dropping reloc_root` lines for roots it visited with `fs_error=-5`.

Conclusion: when the failure path sets `BTRFS_FS_ERROR`, the existing cleanup branch drops `root->reloc_root`. This is the intended safe path.

## Final classification

This is a real cleanup-defect candidate, with an important condition:

```text
Confirmed by QEMU/fault-injection for recovery failures that do not set BTRFS_FS_ERROR.
Not proven for all natural btrfs_commit_transaction() failures.
```

The source-level risk remains valid because `btrfs_recover_relocation()` itself does not clear `fs_root->reloc_root` on the `out_unset` error path. Cleanup currently relies on a later `BTRFS_FS_ERROR`-guarded branch in `btrfs_drop_and_free_fs_root()`.

Suggested fix direction:

```text
Track roots whose reloc_root is assigned during btrfs_recover_relocation(),
and on errors before clean_dirty_subvols(), explicitly clear root->reloc_root
and btrfs_put_root(reloc_root), independent of BTRFS_FS_ERROR.
```
