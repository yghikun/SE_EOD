# MOCC-SE 研究与论文路线图

> 更新时间：2026-07-21
>
> 本文档安排研究问题、实验和论文工作。具体编码顺序以 [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md) 为准，方法定义以 [`docs/MOCC_SE_FULL_ARCHITECTURE.md`](docs/MOCC_SE_FULL_ARCHITECTURE.md) 为准，完成门禁以 [`docs/PROJECT_CLOSURE_PLAN.md`](docs/PROJECT_CLOSURE_PLAN.md) 为准。

## 1. 论文主张

目标主张冻结为：

> MOCC-SE 是一种面向 Linux 文件系统元数据错误路径的协议感知静态分析方法。它将元数据修改表示为带责任域和补偿关系的 effect，统一建模提交、回滚、事务中止、恢复接管和延迟完成，并检查返回状态、元数据状态与记账状态是否满足合法完成后置条件。

SE-EOD 是实现和实验基线。资源泄漏、缺失 cleanup 和错误吞掉是具体表现或基线候选，不是最终研究问题。

论文不声称：

- 首次发现错误处理 bug；
- 对 Linux C 完全 sound 或 complete；
- 完整验证 crash consistency；
- 排名分数等于 bug 概率；
- LLM verdict 等于 ground truth。

## 2. 动机和开发 finding

当前 [outputs/confirmed_bugs.md](outputs/confirmed_bugs.md) 记录 19 条 confirmed/reviewed findings：

- 6 条已由上游修复；
- 13 条由已提交 patch 或 patch series 覆盖；
- submitted、Reviewed-by 和 upstream accepted 必须严格区分。

MOCC-SE 的开发样例为：

| 违规类别 | Finding | 作用 |
|---|---|---|
| `failure_reported_as_success` | #1、#2、#5、#8、#13 | 设计 replay/recovery 和 sentinel return contract |
| `incomplete_failure_completion` | #7、#17、#18、#19 | 设计 effect scope、compensation 和 handler ownership |
| `metadata_state_divergence` | #4、#16 | 设计 failure epoch、positive-success 和 accounting obligation |

这些 finding 是 motivating/development set，不进入无偏测试指标。

## 3. 研究问题

### RQ1：有效性

MOCC-SE 能否在冻结 benchmark 上准确发现元数据操作完成一致性违规？

报告：

```text
candidate precision
bug-cluster recall
F1
Precision@K
95% bootstrap confidence interval
```

### RQ2：三类违规覆盖

方法分别对以下类别表现如何？

```text
failure_reported_as_success
incomplete_failure_completion
metadata_state_divergence
```

不能只报告总体数字掩盖某一协议类别没有有效样本。

### RQ3：组件贡献

以下组件分别贡献多少？

```text
metadata events
return contracts
failure epochs
effect scope/owner
compensation and handlers
accounting obligations
interprocedural summaries
path sensitivity and witness
```

### RQ4：泛化

协议能否跨 Linux 版本、文件系统和未见函数复用？至少分别报告：

- 同文件系统跨版本；
- 同协议跨文件系统；
- 文件系统特定协议的适用边界；
- unsupported 和 analysis unknown 比例。

### RQ5：成本

报告：

- 分析运行时间和峰值内存；
- 每千函数候选数量；
- 单个 protocol 的配置行数和人工编写时间；
- 每个确认 finding 的人工复核时间；
- witness 对复核时间的影响。

### RQ6：真实发现

报告协议冻结后发现的：

- 新 bug；
- 历史已修复 bug；
- duplicate finding；
- uncertain finding；
- patch submitted、reviewed 和 upstream accepted 状态。

## 4. 方法实现路线

### Phase M0：协议核心模型

实现：

```text
MetadataProtocol
ReturnContract
EffectScope/Status
CompletionMode
ViolationType
schema validation/versioning
```

验收：模型可序列化，非法协议被拒绝，不改变 SE-EOD 默认输出。

### Phase M1：元数据事件

实现调用、赋值、字段、链表、flag、counter、reservation、commit、abort 和 handler 事件。

验收：对象 identity 分为 exact/normalized/unknown；may/unknown 不会关闭精确 effect。

### Phase M2：协议状态传播

实现：

```text
MetadataOperationInstance
effect ledger
failure token + attempt_id
accounting obligations
join/widening uncertainty
```

验收：retry stale error、global effect after abort 和 positive-success 均有最小正反例。

### Phase M3：合法出口

实现成功/失败出口后置条件和三类候选，分离 `PARTIAL_UNRESOLVED` 与 `ANALYSIS_UNKNOWN`。

### Phase M4：Protocol A

完成 replay/recovery 纵向闭环，开发回归覆盖 #1、#2、#5、#8、#13。

### Phase M5：Protocol B

完成 device/root/topology rollback，开发回归覆盖 #7、#17、#18、#19。

### Phase M6：Protocol C

完成 retry result provenance、positive-success 和 reservation/accounting，开发回归覆盖 #4、#16。

## 5. Benchmark 路线

### 5.1 数据划分

必须冻结：

```text
development set
validation set
test set
real-world discovery set
```

现有 confirmed bugs、ext4 pilot 和已审查候选属于 development set。

### 5.2 正例来源

优先从 Linux 历史补丁中采样：

- filesystem metadata replay/recovery；
- device/root/topology rollback；
- transaction abort 未覆盖的内存状态；
- reservation、quota、bitmap 和 counter consistency；
- stale/positive-success return semantics。

同一修复 commit 的多个路径记录聚合为一个 bug cluster，避免 recall 重复计数。

### 5.3 负例来源

包括：

- 合法 retry；
- 合法 sentinel，如 `-ENOENT` 后 create；
- best-effort 操作；
- transaction 确实拥有并回滚 effect；
- recovery/deferred handler 已登记；
- 正数成功返回；
- 仅分析不确定、不能证明违规的路径。

### 5.4 标注

每个样本至少记录：

```text
protocol_id
operation_id
principal_objects
error event
effects before failure
completion handler
legal/illegal exit
violation type
uncertainty
reviewers and adjudication
```

LLM 不能作为 reviewer 或 gold label。

## 6. Baseline 和消融

内部 baseline：

| ID | 能力 |
|---|---|
| B0 | 名称级错误/cleanup pattern |
| B1 | SE-EOD 线性错误路径 |
| B2 | CFG resource obligation |
| B3 | metadata events，不检查 completion |
| B4 | 加 return contract 和 failure epoch |
| B5 | 加 effect scope、compensation 和 handlers |
| B6 | 加 accounting obligations |
| Full | 加跨函数 summary、有限对象身份和 witness |

外部 baseline 至少尝试：

- Coccinelle semantic patch；
- Smatch、CodeQL 或 Clang Static Analyzer 中可运行的相关检查；
- 一个错误处理路径差异或 typestate/protocol baseline。

若外部工具无法在相同内核输入上运行，必须保存环境和失败原因，不能只比较报告数量。

## 7. 证据和 finding 状态

候选存在性由静态语义决定。证据单独展示：

```text
static_certainty
protocol_support
historical_confirmation
dynamic_validation
maintainer_feedback
review_priority
```

Finding 状态固定为：

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

邮件发送成功不等于 accepted，Reviewed-by 也不等于 merged。

## 8. 论文结构

建议正文：

1. Introduction：元数据多阶段操作和失败完成问题；
2. Background：Linux 文件系统错误路径、事务和恢复；
3. Motivation：三类开发 finding；
4. Metadata Operation Completion Model；
5. Static Analysis：事件、ledger、failure epoch、handler 和 accounting；
6. Implementation：现有 SE-EOD 基础和 MOCC-SE 模块；
7. Evaluation；
8. Findings；
9. Related Work；
10. Threats and Limitations；
11. Conclusion。

## 9. 论文贡献

目标贡献表述：

1. 定义文件系统元数据操作完成一致性及合法完成模式；
2. 提出带 scope、owner 和 compensation 的 metadata effect ledger；
3. 统一建模错误传播、回滚、事务中止、恢复接管和延迟完成；
4. 检查返回 outcome、元数据 phase 和 accounting obligation 的关系后置条件；
5. 在独立、冻结、跨版本/跨文件系统 benchmark 上评估，并报告真实 upstream findings。

是否使用“首次”或强于现有 typestate/effect analysis 的表述，必须由 Related Work 原文比较支持。

## 10. 执行时间线

时间以里程碑闭合为准，不为赶日期跳过门禁。

### 第 1 阶段：M0-M3

- 协议模型；
- 事件；
- 状态传播；
- 合法出口；
- 合成 fixture 和现有回归。

### 第 2 阶段：M4

- Protocol A；
- 开发函数修复前后差分；
- 第一个未见样本验证；
- 冻结 protocol v1。

### 第 3 阶段：M5-M6

- Protocol B/C；
- effect ownership 和 accounting；
- 三类候选端到端闭合。

### 第 4 阶段：Benchmark 和 baseline

- 冻结数据；
- 双 reviewer；
- baseline 和消融；
- 误差分类。

### 第 5 阶段：真实扫描和论文

- 跨版本/文件系统运行；
- 动态验证和 upstream；
- artifact；
- 论文写作和独立复现。

## 11. 投稿门槛

### Tool/Workshop

- 至少一个协议完整；
- 有可运行 artifact；
- 有开发集和小型独立评估；
- 不夸大泛化。

### CCF B 或同等级完整论文

- 三类违规至少两类有充分独立样本；
- 冻结 benchmark、双人标注和统计完整；
- 至少一个外部 baseline；
- 完整消融；
- 有新的 source-confirmed 或动态 finding；
- artifact 可复现核心表格。

### 更高目标

除上述条件外，还需要：

- 协议跨文件系统泛化证据；
- 更完整 compiled frontend；
- 更大独立 benchmark；
- 多个 upstream accepted finding；
- 清晰证明相对 typestate、effect system 和 error-path checker 的方法差异。

## 12. 路线图 Definition of Done

- [ ] M0-M6 全部通过各自门禁；
- [ ] 协议开发集与冻结测试集完全分离；
- [ ] 三类候选均有正例、反例和 unknown；
- [ ] Precision、Recall、F1、P@K 和置信区间可重算；
- [ ] baseline、消融和误差分类完整；
- [ ] 协议编写成本和 unknown coverage 被报告；
- [ ] 每个 finding 有唯一状态和证据来源；
- [ ] 所有论文主张可以回链到算法、实验和 artifact；
- [ ] README、架构、交接、闭合计划和代码状态一致；
- [ ] 第三方能够从干净环境复现核心结果。
