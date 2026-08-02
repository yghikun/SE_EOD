# OIDS Phase 8 UBIFS Independent-family Validation

Status: `APPLICABLE` for the preregistered successful RW recovery exposure
profile. This is an independent post-scope validation and does not modify the
Phase 7 ext4-specific narrow freeze.

## Evidence boundary

The candidate was registered as `UNREVEALED_FOR_OIDS` before the Linux v6.14
UBIFS target files were acquired. The immutable preregistration and its path-only
amendment are recorded in:

- `configs/evaluation/oids-phase8-ubifs-preregistration-v0.1.json`
- `configs/evaluation/oids-phase8-ubifs-preregistration-amendment-v0.1.json`
- `linux-sources/linux-v6.14-fs/PHASE8_UBIFS_SUPPLEMENTARY_MANIFEST.json`

The amendment preserves the original manifest and only replaces the nonexistent
`fs/ubifs/inode.c` target with the actual `file.c` settlement source and adds
`replay.c` for recovery reconstruction.

## Correspondence

| Dimension | UBIFS mapping | Decision |
|---|---|---|
| object | `struct ubifs_orphan`, inode number, and orphan-area state in `struct ubifs_info` | `CLOSED` |
| relation | a zero-link inode is recorded by inode number in the orphan tree/list and persistent orphan area | `CLOSED` |
| lifecycle | unlink registration, final eviction, journal replay, orphan-area recovery, and recovery commit | `CLOSED` |
| authority | `ubifs_evict_inode()` for live cleanup; `mount_ubifs()` for crash recovery | `CLOSED` |
| deadline | registration before commit, terminal TNC removal before orphan retirement, RW recovery before root exposure | `CLOSED` |

UBIFS uses two representations of the same responsibility. Before a commit, a
zero-link deletion inode in the journal is replayable. At commit, new in-memory
orphans are copied to the persistent orphan area. This is not interpreted as an
in-memory list alone satisfying persistent acceptance.

## Registration

`ubifs_unlink()` drops the link count and calls `ubifs_jnl_update()`. For the
last reference, `ubifs_jnl_update()` calls `ubifs_add_orphan()` before writing
the dent, deletion inode, and parent inode as one journal group.

The failure partition is explicit:

- failure before the journal write returns to `ubifs_unlink()`, which restores
  the saved link count;
- failure after the journal group write calls `ubifs_ro_mode()` and removes only
  the uncommitted in-memory orphan;
- a successful commit snapshots new orphans in `ubifs_orphan_start_commit()` and
  writes them through `ubifs_orphan_end_commit()` before commit publication.

## Settlement

`ubifs_evict_inode()` dispatches zero-link inodes to
`ubifs_jnl_delete_inode()`. The source has two commit-generation partitions:

- without an intervening commit, TNC removal occurs under `commit_sem`, then the
  in-memory orphan is retired;
- after an intervening commit, `ubifs_jnl_write_inode()` writes a fresh deletion
  inode, removes all inode keys from TNC, and only then retires the orphan.

Replay classifies a zero-link inode node as a deletion and applies
`ubifs_tnc_remove_ino()`. Therefore a post-write failure does not lose deletion
responsibility. TNC or commit failures enter read-only failstop. If an orphan is
owned by an active commit, `orphan_delete()` marks it for delayed deletion and
`ubifs_orphan_end_commit()` writes committed orphans before `erase_deleted()`.

## Recovery

For an unclean RW mount, `mount_ubifs()` orders:

```text
ubifs_replay_journal()
-> ubifs_mount_orphans(..., unclean=true, read_only=false)
-> ubifs_rcvry_gc_commit()
-> successful mount return
-> ubifs_fill_super() creates the root
```

Journal replay removes zero-link deletion entries. Orphan-area recovery removes
committed orphan inodes from TNC. `ubifs_rcvry_gc_commit()` then writes those TNC
updates to flash before root exposure.

Read-only recovery is deliberately not promoted to completed settlement. UBIFS
removes orphaned inodes from the current TNC view, keeps durable recovery
responsibility, and reports `recovery deferred`. The Phase 8 replay records this
as `INCOMPLETE_UNDER_LOADED_SPEC`; it is outside the validated successful RW
exposure profile and is not counted as a violation or as universal closure.

## Decision

```text
candidate_status_before_reveal = UNREVEALED_FOR_OIDS
applicability = APPLICABLE
validated_profile = SUCCESSFUL_RW_RECOVERY_EXPOSURE
read_only_recovery = RECOVERY_DEFERRED_OUTSIDE_VALIDATED_RW_EXPOSURE
phase7_scope_unchanged = true
common_freeze_manifest_generated = false
blind_held_out_claim_allowed = true
common_heldout_validated = false
```

The result supports independent-family generalization evidence under an explicit
profile. Because the source was not read until after preregistration, it is a
blind independent-family validation. It is not `COMMON_HELDOUT_VALIDATED`, does
not silently broaden `filesystem == ext4 AND error_policy != ERRORS_CONT`, and
does not create a COMMON freeze.
