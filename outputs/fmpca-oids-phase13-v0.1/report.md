# OIDS Phase 13 v0.2 Revision Preregistration and Split Reset

Manifest: `configs/evaluation/oids-phase13-v0.2-preregistration-v0.1.json`

Preregistration closed: `True`
v0.1 frozen: `True`
v0.2 implemented: `False`
Held-out validation allowed: `False`

## ReiserFS development bugs

| Case | Rule | Evidence | Bug claim | Runtime | Upstream | Security |
|---|---|---|---|---|---|---|
| REISERFS_SAVE_LINK_ENOSPC_UNPROPAGATED | OIDS-O1 | SOURCE_CONFIRMED_CORRECTNESS_BUG | `True` | `False` | `False` | `False` |
| REISERFS_RECOVERY_ERROR_EXPOSURE_REACHABLE | OIDS-O3 | SOURCE_CONFIRMED_CORRECTNESS_BUG | `True` | `False` | `False` | `False` |

## Split reset

Development cases: `2`
Regression validation filesystems: `btrfs, ext4, ocfs2, ubifs`
Held-out cases: `0`
Held-out contamination: `0`
Split closed: `True`

## Interpretation

Both ReiserFS findings qualify as source-confirmed correctness bugs under the frozen OIDS contract: source anchors, control flow, minimal replay, unsafe checkpoints, and repair contracts are closed. Neither finding is claimed as runtime-reproduced, upstream-acknowledged, security-relevant, or assigned a CVE. Phase 13 preregisters a v0.2 diagnostic and failure-handling contract extension before semantic edits, preserves OIDS-O1 and OIDS-O3 as violations, moves ReiserFS into development, resets regression validation, and leaves the future held-out partition empty.

Next phase: Phase 14 will implement the preregistered v0.2 diagnostic and failure-handling contract schema without changing v0.1 or weakening OIDS-O1/OIDS-O3. It will map both ReiserFS development bugs to safe repair alternatives, rerun Btrfs/ext4/UBIFS/OCFS2 regression boundaries, and keep held-out validation disabled until a separate candidate preregistration.
