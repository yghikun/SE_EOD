# Device Capacity Source Evidence v0.4

| Family | Source witness | Relation evidence | Decision |
|---|---|---|---|
| membership change | Btrfs `btrfs_init_new_device`, v7.1 | membership add/remove, `total_rw_bytes +=/-= total_bytes`, `free_chunk_space add/sub total_bytes` | WDC operation family |
| capacity resize | Btrfs `btrfs_shrink_device`, v6.14/v7.1 | writable guard, `diff`, used-aware `free_diff`, same-delta rollback | WDC operation family |

The structural adapter discovers operation families from membership mutation
and capacity formula evidence. Function names are evaluation inputs and do not
appear in the binding or protocol guards.

The confirmed shrink Bug/fix supplies the exact negative/repair pair. The
membership family supplies independent normal and failure-rollback source
semantics and composes with the confirmed DTR topology family. This supports a
cross-operation-family protocol, not a post-freeze held-out claim.
