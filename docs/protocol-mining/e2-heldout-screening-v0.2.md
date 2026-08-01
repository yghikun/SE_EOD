# E2 Held-out Screening v0.2

Screening date: 2026-07-31. Protocol and AcceptP freeze predates candidate inspection in this evaluation workflow.

## Eligibility decision

The runtime relocation merge Bug/fix is confirmed and its Git provenance is
complete. It is nevertheless **not a v0.2 held-out case**. The frozen
`RecoveryAttachmentSettlement` protocol scopes its operation root to a
mount-time recovery operation that establishes the attachment. The candidate
starts in `merge_reloc_roots()` after an attachment was established elsewhere.
Its binding therefore requires a `preexisting_relation_failure_cleanup`
semantic and the footprint `relocation_failure`, neither of which is in the
frozen v0.2 protocol footprint. The candidate is retained as evidence for a
future `RelocationRootAttachmentSettlement` v0.3 protocol.

| Candidate | Operation family | Relation/object | Decision | Reason |
|---|---|---|---|---|
| `83201804efa4` | runtime relocation merge | `fs_root <-> reloc_root` attachment and owned ref | V0.3 PROTOCOL CANDIDATE | Confirmed stale attachment and exact Bug/fixed repair sequence, but the operation lifecycle is outside frozen RAS v0.2 |
| `b78fe9563e2d` | runtime relocation merge | attachment clear ordering | VALIDATION ONLY | Same held-out operation family as `832018...`; not a second independent sample |
| `51415b6c1b11` | runtime relocation merge/cancel | reloc-root attachment refs | HISTORICAL SUPPORT | Same family and predates v0.2; supports design semantics, not E2 count |
| `c78a10aebb27` | mount-time recovery | reloc-root list/ref cleanup | EXCLUDE FROM HELD_OUT | Same operation family as RAS development case |
| `ce6050bafb4e` | runtime relocation merge | temporary `root` reference | OUT_OF_SCOPE | Generic root reference leak; does not leave the protocol attachment relation unsettled |
| `ae2eb64bfd97` | concurrent relocation/COW | `reloc_control` lifetime | OUT_OF_SCOPE | Different concurrent control-object protocol, not RAS attachment settlement |
| `70958a949d85` | seed-to-sprout add | superblock readonly state | EXCLUDE FROM HELD_OUT | Same DTR development operation family and different state contract |
| `611ccc58e1f2` | device replace | allocation-state tree lifetime | OUT_OF_SCOPE | Resource/state-tree lifetime, not topology rollback |
| `e9fd2c05239a` | device shrink | free-space counters | OUTSIDE_CATALOG | Independent operation but requires a counter-consistency protocol absent from v0.2 |

No new v0.2 operation family is counted. Candidate count is not inflated by
multiple commits touching the same runtime relocation merge path.
