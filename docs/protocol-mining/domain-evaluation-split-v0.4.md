# Domain Evaluation Split v0.4

| Operation family | Role | Independence decision |
|---|---|---|
| Btrfs device membership change | development plus cross-family validation | independent from resize; used to form v0.4 |
| Btrfs device capacity resize | development plus cross-family validation | independent from membership change; used to form v0.4 |
| ext4/XFS/F2FS capacity paths | outside catalog | objects/equations/lifecycle do not match WDC |

`cross_operation_family_validated=true`: one protocol is executable across two
independent operation families. `held_out_generalization_eligible=false`:
neither family remained unseen after freeze. The E4 result is qualification
and regression evidence, not a held-out benchmark.
