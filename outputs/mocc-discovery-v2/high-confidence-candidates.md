# High-Confidence Candidate Bugs

This note collects the strongest unconfirmed leads from M11 fresh discovery.
They are not confirmed bugs and must not be moved into `outputs/confirmed_bugs.md`
until dynamic validation closes the loop.

## 1. ext4 fast-commit replay helper swallows helper failures

Status: `UNCONFIRMED / PENDING DYNAMIC VALIDATION`

Source anchors:

- `linux-sources/linux-v6.8-fs/fs/ext4/extents.c:5988`
- `linux-sources/linux-v6.8-fs/fs/ext4/extents.c:6081`
- `linux-sources/linux-v6.8-fs/fs/ext4/fast_commit.c:1517`

What looks wrong:

- `ext4_ext_replay_set_iblocks()` and `ext4_ext_clear_bb()` both hit fallible
  helpers such as `ext4_map_blocks()`, `skip_hole()`, and `ext4_find_extent()`.
- Their error paths converge to a common `out:` path that still rewrites inode
  accounting, marks the inode dirty, and returns `0`.
- `ext4_fc_replay_inode()` calls both helpers and does not check their return
  values.

Why this is high confidence:

- Local modeling shows the original caller swallows helper failures in all
  injected scenarios, while a minimal fixed model propagates them.
- Current validation artifact:
  `outputs/mocc-discovery-v2/ext4-fc-helper-fault-validation.md`
  and `outputs/mocc-discovery-v2/ext4-fc-helper-fault-validation.json`

Suggested next validation:

- run a real kernel fault-injection pass around the replay helper path;
- confirm whether inode metadata is dirtied even when helper work fails;
- compare against the RFC sketch in
  `outputs/mocc-discovery-v2/ext4-fc-helper-error-propagation-rfc.patch`.

Likely fix direction:

- keep replay helpers from converting helper failures into silent success;
- let the outer caller own the final success/failure decision.

## 2. btrfs RAID stripe tree transaction double-end / possible UAF

Status: `UNCONFIRMED / PENDING DYNAMIC VALIDATION`

Source anchors:

- `linux-sources/linux-v6.8-fs/fs/btrfs/raid-stripe-tree.c:77`
- `linux-sources/linux-v6.8-fs/fs/btrfs/inode.c:3106`
- `linux-sources/linux-v6.8-fs/fs/btrfs/inode.c:3165`

What looks wrong:

- `btrfs_insert_one_raid_extent()` allocates a stripe extent with
  `kzalloc(GFP_NOFS)`.
- On allocation failure it aborts the transaction, ends the transaction, and
  returns `-ENOMEM`.
- The ordered-I/O completion path later reaches the shared `out:` cleanup and
  calls `btrfs_end_transaction(trans)` again when `trans` is still non-NULL.

Why this is high confidence:

- The helper appears to hand ownership of the transaction back to the caller
  after already ending it.
- That shape is consistent with a double-end / use-after-free risk on the
  transaction handle if the failure path is reachable under slab pressure.

Suggested next validation:

- force `kzalloc()` failure with `failslab` under `RAID_STRIPE_TREE`;
- run with KASAN or KFENCE to catch a double-end or handle reuse;
- confirm that the caller still owns `trans` after the helper fails.

Likely fix direction:

- remove helper-owned `btrfs_end_transaction(trans)` and keep the caller as the
  single owner of transaction teardown.
