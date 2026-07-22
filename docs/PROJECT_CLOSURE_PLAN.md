# MOCC-SE 项目闭合计划

> 状态基线：2026-07-22
>
> 本文档定义“做到什么程度才算完成”。当前实施顺序见 [`../PROJECT_HANDOFF.md`](../PROJECT_HANDOFF.md)，完整方法见 [`MOCC_SE_FULL_ARCHITECTURE.md`](MOCC_SE_FULL_ARCHITECTURE.md)，当前代码事实见 [`PROJECT_ARCHITECTURE.md`](PROJECT_ARCHITECTURE.md)。

## 1. 闭合定义

MOCC-SE 不能以“代码能运行”“找到了几个已知 bug”或“候选数量减少”作为完成标准。项目必须同时闭合七个循环：

| 闭环 | 输入 | 输出 | 完成条件 |
|---|---|---|---|
| 方法闭环 | 元数据操作和错误路径 | 协议、状态转移、合法后置条件 | 每个概念有可执行语义和反例 |
| 语义闭环 | Linux C/IR/CFG | operation、event、effect、failure、accounting | 每个候选能回链到路径和状态转移 |
| 配置闭环 | API 和文件系统约定 | 版本化 protocol/summary | 配置有 schema、来源、适用范围和 drift 检查 |
| 评估闭环 | 独立冻结数据 | Precision、Recall、F1、P@K、消融 | 无数据泄漏，指标可重算 |
| Finding 闭环 | 高置信候选 | 人工、动态、历史或 upstream 证据 | 每个 finding 有唯一状态，不夸大 accepted |
| 工程复现闭环 | 干净环境 | 相同核心输出和 manifest | 第三方可以重建输入、运行和核验 |
| 论文闭环 | 方法、实验、finding、局限 | 可审查论文和 artifact | 每个主张有算法、实验和证据对应 |

任一闭环未完成时，项目必须明确标为 prototype、development pilot 或 partial evaluation。

## 2. 冻结研究范围

### 2.1 核心问题

> 在 Linux 文件系统错误路径上，判断一个多阶段元数据操作是否通过提交、补偿、事务中止、恢复接管或延迟处理合法完成，并检查返回 outcome、元数据 effect 和记账状态是否一致。

### 2.2 核心候选

```text
failure_reported_as_success
incomplete_failure_completion
metadata_state_divergence
```

资源泄漏、`missing_cleanup`、`partial_cleanup` 和旧 `error_swallowed` 继续作为 SE-EOD 基线输出；只有映射到元数据 operation 和协议义务的记录才进入 MOCC-SE 核心结果。

### 2.3 合法完成模式

```text
COMMITTED
ROLLED_BACK
ABORTED
RECOVERY_DELEGATED
DEFERRED
```

`ABORTED` 不是万能安全状态，只能关闭 handler 明确拥有的 transaction-scoped effect。

### 2.4 分析结论

必须区分：

```text
PROVEN_VIOLATION
POSSIBLE_VIOLATION
LEGAL_COMPLETION
ANALYSIS_UNKNOWN
```

分析未知不能被解释为程序正确，也不能混入高置信违规统计。

### 2.5 非目标

首篇工作不要求：

- 完整 Clang/Kbuild 覆盖全部文件系统；
- 通用 SSA 或 points-to；
- 一般 SMT；
- 完整并发、内存模型或 crash-consistency 证明；
- 任意元数据算术推导；
- LLM 自动确认 bug；
- 自动生成可合并补丁。

闭合要求是 supported fragment 定义清楚、片段内行为可验证、片段外不确定性可量化。

## 3. 当前基线

### 3.1 已实现

当前 MOCC-SE 核心提供：

- frontend-neutral IR 和 tree-sitter adapter；
- 函数内 CFG；
- parameterized protocol schema 和 Protocol A/B/C；
- metadata event、effect ledger、failure attempt 和 accounting obligation；
- 合法成功/失败出口、三类违规和 unknown 隔离；
- source-tree exact analysis 与 broad semantic review 隔离；
- representative trace 和 CFG snapshot；
- source review、version matrix、repair evidence 和 confirmed linkage；
- 精简后 `138 passed` 测试基线。

旧 SE-EOD `src.main`、resource/dataflow、candidate、ranking/LLM 和实验辅助代码已删除；
保留的旧输出只是历史数据，不是当前可执行能力。

### 3.2 未实现

MOCC-SE 的 M0-M11 开发链已实现 schema v1、return contract、metadata event、
effect/failure/accounting 状态、合法出口、三类候选、unknown 隔离、Protocol A/B/C
witness 和 fresh discovery。仍缺少：

- 独立冻结 benchmark 的规模化采集与 adjudication；
- Protocol A/B/C 独立冻结 benchmark 与 protocol-versioned evaluation output。

### 3.3 明确非目标

完整 Kbuild/Clang、通用 points-to/SSA/SMT、完整跨函数 handler/effect summary、任意
metadata invariant DSL 和完整 crash-consistency 证明不属于当前实现 backlog。只有研究
范围重新评审后才能恢复为代码任务。

## 4. 方法闭合任务

### A1：协议核心模型 `P0`

必须定义并测试：

```text
MetadataProtocol
ObjectRef
ReturnContract
EffectKind/Scope/Status
CompensationSpec
HandlerSpec
AccountingConstraint
CompletionMode
ViolationType
```

完成证据：schema fixture、非法配置测试、round-trip、稳定 ID 和版本检查。

### A2：事件语义 `P0`

必须支持：

```text
metadata/pointer update
membership add/remove
flag set/clear
counter/reservation update
commit/compensate/abort
recovery/deferred transfer
```

每个 event 带对象、guard、must/may、源码位置和 uncertainty。

### A3：协议状态 `P0`

必须实现：

- operation instance；
- phase facts；
- effect ledger；
- failure epoch；
- accounting obligations；
- join/widening；
- handler ownership；
- completion mode。

必须包含反例：abort 不关闭 global pointer/list effect，未知 alias 不关闭精确 effect。

### A4：合法出口 `P0`

成功出口检查：

```text
no unresolved necessary failure
legal success phase
required effect completed/transferred
accounting constraints hold
return outcome belongs to current attempt
```

失败出口检查：每个开放 effect 已补偿或由匹配 scope/object 的 handler 接管。

## 5. 协议闭合任务

### B1：Protocol A replay/recovery `P0`

开发样例：#1、#2、#5、#8、#13。

必须识别：

- 必要步骤失败；
- cleanup 后返回原错误；
- 返回成功导致恢复继续；
- `-ENOENT` 等 sentinel；
- 合法 retry；
- best-effort 操作；
- transaction/recovery handler。

完成条件：修复前后差分正确，并在至少一个未参与协议设计的函数或版本上冻结验证。

### B2：Protocol B device/topology rollback `P0`

开发样例：#7、#17、#18、#19。

必须跟踪：

- root association；
- device/list membership；
- transaction update list；
- active pointer；
- seed/sprout topology；
- flag/counter/UUID 相关 effect。

完成条件：事务 effect 和 in-memory global effect 不混淆，多对象补偿可解释。

状态：M5 MVP 已完成。v6.8/v6.14 开发与版本一致性输出记录在
`outputs/mocc-protocol-b-v1/`；独立冻结评估仍属于后续 Gate 5。

### B3：Protocol C state/accounting `P0`

开发样例：#4、#15。

必须跟踪：

- retry attempt 和 result provenance；
- `ret < 0`、`ret == 0`、`ret > 0` outcome；
- phase transition；
- reservation/counter obligation。

第一版只要求布尔关系，不要求任意算术证明。

状态：M6 MVP 已完成。v6.8/v6.14/v7.1 开发与版本一致性输出记录在
`outputs/mocc-protocol-c-v1/`；独立冻结评估仍属于后续 Gate 5。

## 6. 配置闭合

每个 protocol 文件必须记录：

```text
schema_version
protocol_version
filesystem
linux_version_range
source/reviewer
operation entry
events and object roles
return contracts
effect scope/owner
compensations and handlers
legal exits
accounting constraints
```

必须提供：

- schema validation；
- protocol ID 稳定性；
- API/field drift 报告；
- wrapper summary 冲突诊断；
- reviewed resolution 状态；
- protocol 版本进入 run manifest。

配置不能使用单个已知函数名直接编码“这是 bug”。

## 7. Benchmark 闭合

### D1：数据分离 `P0`

冻结：

```text
development
validation
test
discovery
```

现有 19 条 finding 和 ext4 pilot 属于 development。

### D2：样本单位 `P0`

至少同时保留：

- path instance；
- protocol obligation；
- bug cluster；
- fixing commit family。

Recall 以 bug cluster 为主，避免一个修复中的多条路径重复计数。

### D3：标注 schema `P0`

必须包含：

```text
protocol_id
operation/object roles
pre-failure effects
failure semantics
handler/completion
exit outcome
violation type
analysis uncertainty
reviewer/adjudication
evidence status
```

### D4：独立标注 `P0`

- 至少两名 reviewer；
- disagreement 单独裁决；
- 报告 Cohen's kappa 或适合的 agreement；
- LLM 不参与 ground truth；
- test 标签在规则冻结前不可见。

## 8. 评估闭合

### E1：Baseline `P0`

内部 B0-Full 和至少一个外部工具使用相同输入和 benchmark。

### E2：指标 `P0`

必须报告：

```text
Precision / Recall / F1
Precision@K
bug-cluster recall
bootstrap confidence interval
unknown/unsupported coverage
runtime / memory
manual review time
protocol authoring cost
```

### E3：消融 `P0`

分别关闭：

- metadata event semantics；
- return contracts；
- failure epoch；
- effect scope/owner；
- compensation/handlers；
- accounting obligations；
- interprocedural summaries；
- path sensitivity/witness。

不能用“候选减少”代替 precision 提升。

### E4：泛化 `P1`

至少报告：

- 同文件系统跨版本；
- replay 类协议跨 ext4/XFS；
- Btrfs 特定 topology 协议边界；
- protocol unchanged/revised 数量；
- API drift 和 unknown 原因。

## 9. Finding 闭合

统一 registry 字段：

```text
finding_id
candidate_id
protocol_id
filesystem/version/commit
source and witness
manual verdict
dynamic evidence
patch/message ID
review status
upstream commit
last verified date
```

允许状态：

```text
candidate
source_confirmed
dynamically_reproduced
patch_submitted
reviewed
upstream_accepted
duplicate
withdrawn
false_positive
uncertain
```

只有进入维护者 tree 或主线并记录 commit 才能写 `upstream_accepted`。

## 10. 工程和复现闭合

必须完成：

- 锁定 Python、tree-sitter 和可选 Clang 版本；
- protocol/schema version；
- deterministic IDs 和排序；
- run manifest；
- clean-room setup；
- unit、integration、golden 和 regression tests；
- CI；
- LICENSE、CITATION 和 artifact README；
- 一条命令重建核心实验；
- 所有公开证据路径可访问，不依赖 `/root/...` 私有路径。

资源上限、widening 和 truncation 必须进入 diagnostics，不能静默影响结论。

## 11. 论文闭合

### H1：Related Work `P0`

必须与原论文逐项比较：

- typestate/protocol checking；
- effect systems；
- error-path inconsistency；
- filesystem crash-consistency analysis；
- Coccinelle/Smatch/CodeQL/Clang checkers；
- protocol mining；
- LLM-assisted triage。

### H2：方法形式化 `P0`

论文必须把现有协议、tracker 和 legal-exit verifier 统一定义为一个参数化、分层的
扩展状态机；这一步是方法文档和可审查语义，不要求新增独立状态机运行时。必须定义：

- operation instance；
- control state 与 completion mode 的区分；
- event transfer；
- effect owner/scope；
- effect 子状态机及其 closed/transfer/unknown 条件；
- failure resolution；
- accounting obligation；
- legal success/failure exit；
- `Accept_P` 合法出口谓词及三类违规的派生关系；
- join/widening；
- termination；
- supported fragment。

不得把状态机模型写成已覆盖任意文件系统或任意 C 语义。完整 handler/effect summary、
任意元数据算术、通用 points-to、并发和 crash-consistency 证明仍属于未实现或非目标，
必须保留为限制。

### H3：主张追踪 `P0`

每个贡献必须对应：

```text
formal definition
implementation component
ablation
evaluation table/figure
artifact command
threat
```

### H4：Threats `P0`

至少覆盖：前端、对象身份、协议人工配置、路径可行性、版本偏差、数据泄漏、reviewer、动态验证和 upstream selection bias。

## 12. Gate

### Gate 0：文档和范围

- 主张、术语、开发集和非目标冻结；
- README、完整架构、交接和闭合计划一致。

### Gate 1：M0

- 协议模型、schema 和测试完成；
- 不改变旧输出。

### Gate 2：M1-M3

- 事件、状态、合法出口和候选框架完成；
- 正例、反例和 unknown 完整。

### Gate 3：Protocol A

- 五个开发 finding 回归；
- 合法 sentinel/retry/best-effort 不误报；
- 至少一个未见验证样本。

### Gate 4：Protocol B/C

- 三类违规完整；
- effect ownership 和 accounting 通过反例。

### Gate 5：冻结评估

- benchmark、baseline、指标、消融和统计完成；
- 不再修改 test label 或核心 protocol。

### Gate 6：Finding 和 artifact

- finding registry、动态证据、公开路径和一键复现完成。

### Gate 7：论文

- 每项主张可回链；
- 独立复现通过；
- threats 和局限完整。

## 13. 统一任务完成模板

```text
Task ID:
Problem and protocol obligation:
Supported semantics:
Explicitly unsupported semantics:
Files changed:
Schema/output changes:
Positive tests:
Negative tests:
Unknown tests:
Behavioral diff:
Known limitations:
Verification commands/results:
Documentation updated:
```

不能只写“实现完成”。

## 14. 风险和止损

| 风险 | 触发条件 | 处理 |
|---|---|---|
| 协议过拟合 | 只能找回已知函数 | 冻结协议，在未见函数/版本验证 |
| 状态爆炸 | operation/effect 超限 | 有界 join/widening，报告 unknown |
| handler 过强 | abort 自动消除所有 effect | scope/owner 检查和反例测试 |
| alias 假精确 | unknown 被当成同一对象 | exact/normalized/unknown 分级 |
| accounting 过度承诺 | 需要任意算术 | 第一版降为布尔 obligation |
| 前端工程拖延 | 长期没有协议闭环 | tree-sitter/IR 先完成 M0-M5 |
| benchmark 泄漏 | 已知 finding 进入 test | development/test 完全隔离 |
| 证据污染语义 | history/LLM 删除候选 | 静态与 ranking 分层 |

## 15. 最终 Definition of Done

### 方法和代码

- [x] M0-M11 开发链通过；
- [x] 三类违规均有端到端 fixture；
- [x] `PARTIAL_UNRESOLVED` 和 `ANALYSIS_UNKNOWN` 分离；
- [x] protocol/schema/output versioned；
- [ ] 所有 must effect 和 handler transfer 可审计；
- [x] 精简后全量测试和 Linux CFG golden 通过。

### 实验

- [ ] 开发、验证、测试和 discovery 分离；
- [ ] 双 reviewer 和裁决完成；
- [ ] baseline、消融、指标和统计可重算；
- [ ] unknown coverage、人工成本和协议成本被报告；
- [ ] 至少跨两个文件系统和两个 Linux 版本。

### Finding

- [ ] finding registry 状态唯一；
- [ ] 新旧、duplicate、withdrawn 和 uncertain 分开；
- [ ] submitted/reviewed/accepted 不混淆；
- [ ] 关键 finding 有 source、history 或 dynamic evidence。

### 复现和论文

- [ ] 干净环境可一键运行；
- [ ] manifest、依赖、LICENSE、CITATION 和 CI 完整；
- [ ] 核心表格由脚本生成；
- [ ] Related Work 基于原文；
- [ ] 每个贡献有实验和 threat；
- [ ] 标题、摘要和结论不超出证据。

## 16. 立即执行

当前任务以 [`../PROJECT_HANDOFF.md`](../PROJECT_HANDOFF.md) 为准：M6 Protocol C activation/reservation/accounting 已完成。

Protocol C 的 M6 MVP 已闭合；在冻结评估门禁完成前不启动大规模 benchmark、LLM 调优、ranking 校准或正式论文表格。
