# E6 CMRC Held-out Screening v0.5

Date: 2026-08-01. Status: post-freeze held-out screen.

## Task understanding

CMRC v0.5 is already frozen. E6 therefore must not change the CMRC protocol,
binding or acceptance formula. The task is to ask whether a third operation
family, unseen during the v0.5 freeze decision, satisfies the same
reservation/update/release lifecycle.

## First-principles constraint

The object is still:

```text
chunk-tree metadata update
-> transaction-scoped chunk metadata reservation
-> release of trans->chunk_bytes_reserved
-> commit-time settlement
```

A candidate is not eligible merely because it mentions chunks or devices. It
must close the same semantic relation with the frozen CMRC binding.

## Screened candidates

| Candidate | Family | Decision |
|---|---|---|
| `btrfs_remove_chunk()` | `btrfs-chunk-item-removal` | `ELIGIBLE_HELD_OUT_REPLAY` |
| `btrfs_add_dev_item()` | `btrfs-device-item-update` | `REJECT_NOT_INDEPENDENT` |

## Causal chain for the accepted family

```text
btrfs_remove_chunk()
-> check_system_chunk(trans, map->type)
-> remove_chunk_item(trans, map, chunk_offset)
-> btrfs_update_device(...) and btrfs_free_chunk(...)
-> btrfs_trans_release_chunk_metadata(trans)
-> later transaction commit
```

This family is independent from the v0.5 development families because it is a
chunk item removal path, not the Bug #15 positive-success publication path and
not the `btrfs_grow_device()` device-item update family.

## Replay

| Fixture | Role | Result |
|---|---|---|
| `cmrc-remove-chunk-heldout-normal-v0.5.json` | normal | `CONFORMANT` |
| `cmrc-remove-chunk-heldout-fixed-v0.5.json` | retry/repair-like | `CONFORMANT` |
| `cmrc-remove-chunk-heldout-negative-v0.5.json` | negative | `VIOLATION` |
| `cmrc-remove-chunk-heldout-unknown-v0.5.json` | unknown | `INCOMPLETE` |

E6 admits one post-freeze held-out family and makes no cross-filesystem
generalization claim.

