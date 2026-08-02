# OIDS Phase 4 CFG / All-Path Proof Closure

Manifest: `configs/evaluation/oids-phase4-allpath-v0.1.json`

Common candidate ready: `True`
Common freeze ready: `False`
Per-filesystem proof closure: `False`

## Clause results

| Filesystem | Stage | Clause | Status | Conclusion |
|---|---|---|---|---|
| btrfs | registration | `OIDS-BTRFS-R1` | `CLOSED` | Every zero-link unlink path reaches orphan registration before transaction settlement. |
| btrfs | registration | `OIDS-BTRFS-R2` | `CLOSED` | A non-EEXIST registration failure cannot settle as a successful transaction. |
| btrfs | settlement | `OIDS-BTRFS-S1` | `CLOSED` | Every persistent orphan-removal attempt is preceded by settled terminal deletion and is transaction bounded. |
| btrfs | recovery | `OIDS-BTRFS-C1` | `CLOSED` | Successful RW exposure is dominated by a successful orphan-cleanup gate. |
| ext4 | registration | `OIDS-EXT4-R1` | `BLOCKED` | The zero-link call is present, but every ignored registration error is not yet proven to abort the same handle. |
| ext4 | settlement | `OIDS-EXT4-S1` | `CLOSED` | The successful free branch co-settles registry removal and inode free on one handle. |
| ext4 | settlement | `OIDS-EXT4-S2` | `BLOCKED` | Ignored orphan-del and mark-dirty errors are not yet proven to prevent a removal-only commit on every helper branch. |
| ext4 | recovery | `OIDS-EXT4-C1` | `BLOCKED` | Syntactic call dominance does not close per-inode recovery because cleanup is void and contains skip/error exits. |

## Remaining blockers

- btrfs: none
- ext4: `EXT4_REGISTRATION_RETURN_IGNORED`, `EXT4_ORPHAN_ADD_ERROR_CONTAINMENT_NOT_CLOSED`, `EXT4_ORPHAN_DEL_RETURN_IGNORED`, `EXT4_MARK_DIRTY_FAILURE_ABORT_CONTRACT_NOT_CLOSED`, `CFG_PARSE_ERROR:__ext4_fill_super`, `EXT4_VOID_CLEANUP_HAS_NO_SUCCESS_OUTCOME`, `EXT4_RECOVERY_SKIP_AND_ERROR_PATHS_UNPARTITIONED`

## Freeze decision

Failed gates: `proof_closure_closed_per_filesystem`

Btrfs registration, eviction settlement, and successful RW recovery exposure close under the CFG proof. ext4 retains explicit interprocedural error-contract and recovery-outcome blockers, so per-filesystem closure is false and no COMMON freeze manifest is generated.
