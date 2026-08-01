# Domain Traceability Matrix v0.3

| Protocol/rule | Design semantics | Normal/safe source | Confirmed Bug | Fixed/repaired | Replay | Boundary |
|---|---|---|---|---|---|---|
| RRM-I1 | relocation attachment lifecycle and prestate | origin -> merge -> cleanup chain | `c0041b502e57` | `83201804efa4` repair sequence | Bug, fixed, normal, unknown | selected path; all-path closure incomplete |
| RRM-O1 | relation-specific settlement responsibility | teardown consumer and reference drop | `c0041b502e57` | `83201804efa4` | failure, delegated-safe, owner termination | no generic abort discharge |
| DSSA-I1 | free capacity equals writable capacity minus used | Btrfs add/remove and allocation consumer paths | `efba1454493d` | `e9fd2c05239a` | Bug, fixed success/failure, unknown | Btrfs device-shrink scope |
| DSSA-I2 | writable guard and same-delta rollback | writable-state normal update paths | `efba1454493d` | `e9fd2c05239a` | Bug, fixed success/failure, unknown | no cross-FS equivalence claim |
| DSSA-O1 | all changed relations settle to prestate | paired aggregate update discipline | `efba1454493d` | `e9fd2c05239a` | fixed failure and unknown | `UNKNOWN/WIDENED` cannot prove conformance |

No guard, binding branch or AcceptP clause contains a Bug ID, function name,
line number or patch ID. Same-family patches are not counted as independent
validation families.
