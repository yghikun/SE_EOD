# Gate R Audit

Status: `PASS_WITH_RECORDED_LIMITATION`

Audit date: 2026-07-31

## Required Chain

Gate R requires at least one real-source vertical chain whose conclusion is
derived from allowed structural evidence:

```text
source operation root
-> generic binding
-> typed events and identities
-> protocol instance and obligations
-> deadline proof closure
-> source witness and coverage report
```

## Real-Source Chains

| Protocol | Source evidence | Differential or witness | Result |
|---|---|---|---|
| MetadataTransitionOutcome | ext4 v6.8/v7.1 and XFS v6.8/v6.14/v7.1 | Bug/fixed differential, validation, scope negative and held-out paths | PASS |
| FailureRollbackConformance | Btrfs v6.8 `fs/btrfs/relocation.c` | Active attachment at line 4382, checked commit failure at 4386, `out_unset` repair slice at 4404 with no matching release | PASS |

The source bindings use field/access paths, primitive calls, typed parameter
identity, return partitions and structural control flow. Neither binding
contains a Bug ID or target function name. Both are included in
`configs/freeze/semantic-freeze-v0.1.json`.

For the Btrfs witness, the exact `fs_root.reloc_root` delta remains open at
`AT_SETTLEMENT`; its repair slice is closed, so incomplete escape coverage
does not weaken this existential violation. The result is
`VIOLATION_UNDER_LOADED_SPEC`, not a whole-program safety claim.

## Recorded Limitation

The repository does not contain a local fixed-source snapshot for the Btrfs
relation case. Its repaired and safe paths are supported by the frozen manual
replay, accepted patch provenance, and QEMU fault-injection record, while the
executable paired safe/fixed checks use structured event fixtures. Therefore
Gate R establishes a real-source violation chain for this protocol, but does
not claim a Btrfs source-level Bug/fixed differential. The outcome protocol
does have real-source Bug/fixed differentials.
