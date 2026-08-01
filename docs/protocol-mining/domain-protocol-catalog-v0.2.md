# Domain Protocol Catalog v0.2

版本：`0.2.0`；状态：FROZEN CANDIDATE；日期：2026-07-31。

## RecoveryAttachmentSettlement

**Intent**：recovery operation 建立的每个 `fs_root <-> reloc_root` attachment，在失败结算前必须恢复入口关系，或由明确允许的 teardown authority 接管并实际完成。

- Anchors：`operation`、`fs_root`；epoch=`operation_root + retry_generation`。
- Roles：`relocation_root`、`recovery_owner`、`teardown_authority`。
- Phases：`DETACHED -> ATTACHED -> FAILURE_PENDING -> RESTORED/DELEGATED -> SETTLED`。
- Core relation：`fs_root.reloc_root`；伴随 root-reference ownership。
- Rule RAS-I1：settlement 时 attachment state 必须为 `DETACHED`。
- Rule RAS-O1：failure 激活每个 changed attachment 的 prestate obligation；只允许 `teardown_owner`，且 authority completion 才 discharge。
- Deadlines：operation return、protocol completion 或 owner termination 形成 settlement；owner termination 也保留独立 termination boundary。
- Frame：unrelated root lists、generic resource count。

证据强度：真实 v6.8 violation source witness + QEMU Bug/safe sibling + accepted fix direction + executable fixed/delegated replay。限制：只有一个真实 operation family，且本地 fixed source 未加载。

## DeviceTopologyRollback

**Intent**：seed-to-sprout device topology transition 在失败时，对 membership、active pointer 和 topology identity 的每个 operation-local delta 分别恢复或完成合法责任转移。

- Anchors：`operation`、`topology`；epoch=`operation_root + retry_generation`。
- Roles：seed/sprout container、device、active-device pointer slot、transaction owner、rollback authority。
- Phases：`STABLE -> MUTATING -> ROLLBACK_PENDING -> RESTORED/DELEGATED -> SETTLED`。
- Relations：`topology.device_membership`、`transaction.post_commit_membership`、`topology.active_device`、`topology.fsid_identity`。
- Rule DTR-I1/I2：active target 在持续使用及 exposure boundary 必须有效。
- Rule DTR-I3：device release 前必须有证据证明设备已脱离 topology 与 post-commit membership。
- Rule DTR-O1：failure 对每个 changed relation 激活独立 obligation；transaction/topology authority 必须逐 relation 完成，abort 或 delegation 本身不 discharge。
- Deadlines：release/exposure 是早期危险边界；其余未完成 relation 在 settlement 到期。
- Frame：generic resource count、unrelated transaction state。

证据强度：真实 v6.14 三 relation mutation/部分 cleanup violation witness + #16/#17/#18 动态与补丁系列 + executable fixed/delegated/negative replay。限制：三项只构成一个 operation family，本地 fixed source 未加载。

## 内核与协议边界

`OutcomeAgreement`、`RestoreOrDelegate`、`ProofClosure` 是这两个协议的执行机制。下列句子不能单独成为 Catalog 协议：failure must return error、failure must rollback、delegation must complete、operation must settle。Catalog v0.1、E0 和其 hash freeze 保持只读，只作为内核工程基线。
