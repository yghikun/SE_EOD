# RRAS Independence Screening v0.3

Screening date: 2026-07-31. Result: `ONE_OPERATION_FAMILY_ONLY`.

| Candidate | Semantic object | Operation family | Decision |
|---|---|---|---|
| `83201804efa4` | stale `fs_root.reloc_root` plus owned reference after merge failure | runtime relocation merge | DEVELOPMENT family |
| `b78fe9563e2d` | clear ordering and dead-reloc-tree state in `merge_reloc_roots()` | runtime relocation merge | SAME_FAMILY_VALIDATION; count remains one |
| `51415b6c1b11` | orphan/cancel relocation-root references settled in `merge_reloc_roots()` | runtime relocation merge/cancel | SAME_FAMILY_HISTORICAL_SUPPORT |
| `c78a10aebb27` | zero-ref relocation-root cleanup during mount recovery | mount-time recovery | Different operation mode; evidence for RAS, not validation of the imported-attachment RRAS draft |
| `6a8269b6459e` | unlinked mapping-node allocation after duplicate RB-tree insert | local allocation cleanup | OUT_OF_SCOPE_RESOURCE_LIFETIME |
| `ce6050bafb4e` | temporary fs-root reference | runtime relocation merge | OUT_OF_SCOPE_GENERIC_REFERENCE |
| `ae2eb64bfd97` | concurrent `reloc_control` lifetime | relocation/COW concurrency | OUTSIDE_RRAS_CONTROL_OBJECT_PROTOCOL |

## Decision

Multiple patches in `merge_reloc_roots()` do not create multiple independent
operation families. The executable readiness manifest therefore records one
family and sets `independent_validation_family=false`. RRAS v0.3 is frozen
only for this declared family; `generalization_eligible=false` remains
enforced.
