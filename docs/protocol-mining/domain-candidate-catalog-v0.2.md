# P1.1-P1.4 Domain Candidate Catalog v0.2

状态：候选重挖完成。聚类键是元数据对象、关系、生命周期和 operation family，而不是共同的失败形状。

## 聚类结果

| 候选 | 对象与关系 | operation family | 证据案例 | 决策 |
|---|---|---|---|---|
| `RecoveryAttachmentSettlement` | `fs_root <-> reloc_root` attachment、root reference ownership、recovery/teardown responsibility | mount-time relocation recovery | #7 | 纳入；单例领域协议，不声称强泛化 |
| `DeviceTopologyRollback` | device membership/post-commit ownership、active pointer、sprout container、fsid identity | seed-to-sprout device add | #16/#17/#18 | 纳入；三项是同一 operation 的关系投影，只计一个 family |
| `FastCommitReplaySettlement` | ext4 fast-commit replay objects/outcome | 多个 replay helper | #1/#2/#5 | 延后；现有证据首先支持 kernel-level outcome agreement，尚未形成独立关系状态机 |
| `RealtimeMetadataGrowthSettlement` | XFS realtime summary/inode growth objects | realtime metadata helpers | #8/#13 | 延后；同上，不以“错误传播”冒充领域协议 |
| `CompanionMetadataCompletion` | zoned block-group activation/reservation | chunk reservation | #15 | 延后；单例且完整生命周期证据不足 |

## RecoveryAttachmentSettlement 统一语义记录

- OperationRoot：挂载期 relocation recovery epoch。
- Anchors：recovery operation 与 `fs_root` identity。
- Prestate：`fs_root.reloc_root` 未附着，或存在被入口语义确认的既有状态。
- Mutation：恢复过程抓取引用并建立 `fs_root.reloc_root` attachment。
- Failure：attachment 建立后 recovery transaction 失败。
- Obligation：失败结算前逐 attachment 恢复 prestate，或委托给允许的 teardown authority 并由其完成。
- Deadlines：`AT_SETTLEMENT`；owner termination 同时触发 termination check 和 settlement。
- Safe boundary：只有有证据的 teardown 分支可以承担责任；全局错误标志本身不是恢复证明。

## DeviceTopologyRollback 统一语义记录

- OperationRoot：seed filesystem 第一次加入 writable device 的 device-add epoch。
- Anchors：operation 与 topology container identity。
- Prestate：seed membership、active device identity 和 seed fsid identity。
- Mutations：建立 sprout、重绑 active pointer、改变 membership/post-commit ownership。
- Failure：拓扑变化后 transaction failure/abort。
- Obligations：每个已改变 relation 独立恢复 prestate，或逐 relation 合法委托并完成。
- Deadlines：membership 在 release 前必须恢复；active target 在 exposure 前必须有效；所有未结关系在 settlement 前完成。
- Safe boundary：transaction abort 不自动恢复任意内存 relation；恢复一个 relation 不代表整个 topology 已恢复。

## 纠偏结论

旧 `MetadataTransitionOutcome` 与 `FailureRollbackConformance` 保留为 v0.1 工程基线。v0.2 不删除它们，但只复用其 outcome、obligation/authority 和 proof-closure 机制，不再把它们列为论文的领域协议。

