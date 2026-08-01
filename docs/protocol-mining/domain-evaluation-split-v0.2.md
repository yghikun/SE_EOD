# P1.5 Domain Evaluation Split v0.2

划分单位是 operation family，不是 Bug ID 或 relation projection。

| Family | Cases | v0.2 角色 | 理由 |
|---|---|---|---|
| relocation recovery | #7 | DEVELOPMENT | RAS 的唯一真实 operation family；可用于形成协议，但不能同时作为独立 held-out 泛化证据 |
| seed-to-sprout device add | #16/#17/#18 | DEVELOPMENT + relation validation | 三项来自同一 operation root/补丁系列；用于验证 membership、pointer、identity 投影，不计三个独立样本 |
| ext4 fast-commit / XFS realtime | #1/#2/#5/#8/#13 | OUTSIDE_DOMAIN_CATALOG_V0.2 | 当前只支持 `OutcomeAgreement` 内核机制，没有冻结为领域关系协议 |
| zoned companion reservation | #15 | DEFERRED | 单例且证据包不足 |

E1 包含 structured Bug、fixed、safe-delegated、deadline-negative、unknown 和两个真实 Bug-source witness。`held_out_operation_families=[]`：当前没有第三个不参与规则形成、又适配 RAS/DTR 的独立 operation family。继续把 #17 或 #18 标为 held-out 会违反独立性约束。

因此 E1 的解释是“Domain Protocol Catalog v0.2 的资格与回归评测”，不是大规模 benchmark，也不是跨文件系统泛化证明。后续只有新增独立 operation family，并在 v0.2 freeze 后不修改 AcceptP，才能建立真正 held-out E2。

