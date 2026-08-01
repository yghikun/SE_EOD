# Domain Evaluation Split v0.5

| Operation family | Role | Independence decision |
|---|---|---|
| Btrfs chunk metadata reservation | development confirmed Bug/fixed/normal/unknown replay | used to derive and test CMRC from Bug #15 |
| Btrfs device item update | sibling normal source family | independent from Bug #15 publication path; used to qualify narrow freeze |
| Btrfs `do_chunk_alloc` | excluded sibling evidence | shares the same allocation/reservation mechanism too closely to count as independent family |
| `btrfs_trans_release_chunk_metadata` | settlement evidence | release helper only, not a separate publication/update family |
| non-Btrfs filesystems | outside v0.5 catalog | no object/role/deadline equivalence has been closed |

`cross_operation_family_validated=true`: CMRC v0.5 is executable across two
Btrfs operation families.

`held_out_generalization_eligible=false`: both admitted families participated
in the v0.5 freeze decision, so neither remains post-freeze held-out.

`cross_filesystem_generalization_eligible=false`: no other filesystem has yet
been shown to share the same chunk-tree metadata object, transaction-scoped
reservation accounting, release settlement and commit deadline.

