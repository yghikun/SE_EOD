# P1.5 Domain Manual Replay v0.2

## RecoveryAttachmentSettlement

| 路径 | 关键事件与状态 | deadline/义务 | 结果 |
|---|---|---|---|
| Bug #7 / `ras-bug` | prestate detached -> attach -> recovery failure -> return | RAS-O1 open；RAS-I1 false at settlement | VIOLATION |
| repaired / `ras-fixed` | attach -> failure -> detach/drop -> return | relation matches prestate；O1 discharged | CONFORMANT |
| guarded teardown / `ras-safe-delegated` | failure -> delegate to `teardown_owner` -> authority complete -> return | delegation 本身不 discharge；completion 后 discharge | CONFORMANT |
| owner exits / `ras-owner-termination-violation` | attach -> failure -> owner termination | 同时到达 `BEFORE_OWNER_TERMINATION` 与 `AT_SETTLEMENT`；O1 open | VIOLATION |
| unknown helper / `ras-unknown` | helper 可能 detach，但 precision=UNKNOWN | 无精确 violation，亦无 universal conformance | INCOMPLETE |
| real v6.8 source | attachment line -> checked commit failure -> `out_unset` 无 release -> return | repair slice closed；RAS-I1/O1 false | VIOLATION |

## DeviceTopologyRollback

| 路径 | 关键事件与状态 | deadline/义务 | 结果 |
|---|---|---|---|
| Bug projection / `dtr-bug` | snapshot+mutate fsid/active -> failure -> return | 两个 DTR-O1 open at settlement | VIOLATION |
| full repair / `dtr-fixed` | failure -> restore fsid -> restore active -> return | 多 relation restore 可重入；逐项 discharge | CONFORMANT |
| legal transfer / `dtr-delegated-safe` | 两项 delegate -> 两项 authority complete -> return | 每个 authority claim 单独完成 | CONFORMANT |
| stale exposure / `dtr-exposure` | active rebind -> failure -> invalid live exposure | DTR-I1/I2 与 irreversible witness | VIOLATION |
| release while attached / `dtr-release-violation` | device membership + post-commit membership mutation -> failure -> release while either relation remains attached | DTR-I3 false at `BEFORE_RELEASE` | VIOLATION |
| release repair / `dtr-release-fixed` | 两项 membership restore -> detached proof -> release -> return | DTR-I3 true；两个 DTR-O1 discharged | CONFORMANT |
| unknown restore / `dtr-unknown` | restore event precision=UNKNOWN -> return | obligation 表面完成但 proof depends on unknown fact | INCOMPLETE |
| real v6.14 source | sprout/fsid、active pointer、device membership mutation -> abort boundary -> only device membership restore -> return | fsid/active obligations remain open；post-commit helper effect 未做 interprocedural claim | VIOLATION |

所有 conformant 行都要求 `all_paths_closed=true`。所有 unknown 行明确拒绝用 widening/未知 helper 证明 conformance；所有 violation 行的 false clause 都在对应 deadline 前有精确 witness 和 closed repair slice。
