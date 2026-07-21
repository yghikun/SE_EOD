# MOCC-SE 完整架构

> 版本：2026-07-21
>
> MOCC-SE（Metadata Operation Completion Consistency for Static Error-path analysis）是 SE-EOD 的元数据一致性研究主线。本文档描述目标方法架构；当前代码是否已经实现某项能力，以 `docs/PROJECT_ARCHITECTURE.md` 的实现状态为准。

## 1. 研究目标

MOCC-SE 面向 Linux 文件系统 C 代码，检查多阶段元数据操作在失败路径上的完成一致性。系统不直接断言候选是真实 bug，而是为人工复核生成带证据的候选。

核心问题是：

> 元数据操作的每个可达出口，是否满足协议定义的合法完成后置条件，并保持返回状态、元数据状态和记账状态一致？

重点覆盖三类违规：

1. `failure_reported_as_success`：必要步骤失败后没有成功重试、恢复或中止，却到达成功出口。
2. `incomplete_failure_completion`：已经产生的元数据 effect 没有补偿，也没有交给事务、恢复或延迟处理机制。
3. `metadata_state_divergence`：返回值、元数据阶段、reservation 或计数状态组成了协议不允许的组合。

资源泄漏、错误吞掉和 stale error 是具体表现；研究对象是元数据操作完成协议，而不是某一个函数名或某一种 API。

## 2. 总体架构

```text
Linux C 源码、版本和配置
          |
          v
+---------------------------+
| 1. 编译感知源码前端       |
| parser / IR / CFG / calls  |
+---------------------------+
          |
          v
+---------------------------+
| 2. 语义规范化层            |
| return contract / alias    |
| object identity / guards   |
+---------------------------+
          |
          v
+---------------------------+
| 3. 元数据协议库            |
| phases / effects / owners  |
| compensations / handlers   |
+---------------------------+
          |
          v
+---------------------------+
| 4. 事件和 effect 提取器    |
| update / pointer / list    |
| flag / counter / account   |
+---------------------------+
          |
          v
+---------------------------+
| 5. 协议状态传播器          |
| path facts / effect ledger |
| failure epochs / summaries |
+---------------------------+
          |
          v
+---------------------------+
| 6. 合法出口验证器          |
| success / rollback / abort |
| recovery / deferred        |
+---------------------------+
          |
          v
+---------------------------+
| 7. witness、候选和证据层   |
| trace / ranking / review   |
+---------------------------+
```

静态语义和证据排序必须分离：只有前者决定候选是否存在，历史补丁、维护者反馈和 LLM 只能用于排序和人工复核。

## 3. 统一状态模型

一次多阶段操作表示为：

```text
MetadataOperationInstance
├── operation_id
├── protocol_id
├── principal_objects
├── phase_facts
├── effect_ledger
├── failure_tokens
├── accounting_obligations
├── completion_mode
└── uncertainty_causes
```

### 3.1 Effect ledger

每个已发生但尚未闭合的修改记录为一个 effect：

```text
Effect
├── effect_id
├── kind
├── object_id
├── container_id
├── field_or_member
├── scope
├── owner
├── status
├── compensation
├── source_event
└── confidence
```

`scope` 不能省略。至少区分：

```text
LOCAL                 函数局部状态
IN_MEMORY_GLOBAL      全局指针、链表、root 拓扑
TRANSACTION_SCOPED    由事务 abort/commit 管理
PERSISTENT            已写入或准备写入磁盘的元数据
RECOVERY_OWNED        由恢复流程接管
DEFERRED_OWNED        由回调、worker 或延迟清理接管
```

`status` 使用：

```text
OPEN | COMPENSATED | TRANSFERRED | COMMITTED | UNKNOWN
```

事务中止只关闭明确标记为 `TRANSACTION_SCOPED` 的 effect，不能自动清除 active pointer、设备链表或 `fs_devices` 拓扑。

### 3.2 Failure token

错误不是一个永久的布尔标志，而是带尝试代际的 token：

```text
FailureToken
├── failure_id
├── attempt_id
├── source_expression
├── error_class
├── expected_sentinel
├── resolution
└── evidence
```

进入 `retry` 开始新 `attempt_id`。旧失败只有在 fallback、重试、映射或显式传播后才算 resolved。这样可以检测 #4 中“第二次已经成功，但返回值仍来自第一次”的 stale error。

### 3.3 记账义务

记账状态不能只保存一个整数，还要记录它对应的元数据义务：

```text
AccountingObligation
├── kind: reservation | counter | quota | bitmap
├── subject
├── required_condition
├── observed_state
├── unit_or_amount
└── status
```

第一阶段优先检查布尔关系，例如“pending chunk metadata 存在时必须有 reservation”；精确的任意算术关系作为后续扩展。

## 4. 协议定义

协议描述操作的合法状态转换，不描述某一个具体 bug。协议文件包含：

```yaml
protocol_id:
entry:
objects:
phases:
events:
return_contracts:
compensations:
handlers:
accounting_constraints:
legal_exits:
```

返回协议必须显式描述多值语义：

```yaml
return_contract:
  - guard: ret < 0
    outcome: failure
  - guard: ret == 0
    outcome: success_no_change
  - guard: ret > 0
    outcome: success_changed
```

这类契约用于处理 Btrfs zoned activation 的正数成功值，也用于区分 `-ENOENT` 与其他加载错误。

### 4.1 Protocol A：replay/recovery

不变量：

```text
必要恢复步骤失败
→ 必须传播错误、成功重试、取消事务或交给恢复处理
→ 不能无处理地到达成功出口
```

覆盖 ext4 fast commit、XFS realtime summary 和 rtgroup inode ensure。

### 4.2 Protocol B：设备和元数据拓扑初始化

跟踪：

```text
device list membership
active device pointer
transaction update list
root/reloc_root association
fs_devices seed/sprout topology
```

每个 effect 必须有明确的补偿或责任转移。覆盖 Btrfs relocation recovery 和 sprout device-add。

### 4.3 Protocol C：激活、reservation 和空间记账

检查：

```text
元数据阶段已进入下一步
→ 返回结果必须允许该阶段继续
→ 所需 reservation/counter 必须同步更新
```

覆盖 stale error、positive-success return 和 chunk metadata reservation。

## 5. 事件提取

事件分为：

```text
METADATA_UPDATE      字段或磁盘元数据修改
POINTER_UPDATE       指针改向
MEMBERSHIP_ADD       加入链表、树或容器
MEMBERSHIP_REMOVE    从容器删除
FLAG_SET/CLEAR       标志改变
COUNTER_UPDATE       计数器改变
RESERVATION_UPDATE   空间或配额记账改变
COMMIT               提交
COMPENSATE           逆向恢复
ABORT                事务中止
RECOVERY_DELEGATE    交给恢复流程
DEFER_CLEANUP        登记延迟清理
```

事件记录源码位置、guard、对象绑定和 `must/may` 强度。无法唯一解析对象时保留不确定性，不把 effect 直接标记为已完成。

## 6. 分析算法

### 6.1 路径状态传播

分析器在 CFG 上传播：

```text
ProtocolFlowState
├── phase_facts
├── symbol_bindings
├── effect_ledger
├── failure_tokens
├── accounting_obligations
└── uncertainty_causes
```

每个语句应用事件转移；每个条件边附加路径事实；每个函数出口交给合法出口验证器。

### 6.2 跨函数摘要

摘要至少包含：

```text
requires
provides
phase_transition
effect_create
effect_compensate
effect_transfer
return_contract
accounting_effect
guard
strength: must | may
```

调用点只有在参数映射、返回 guard 和对象身份可证明时才应用 `must` effect。未知间接调用、不可解析 alias 和不完整 CFG 进入 `may/unknown`，不能据此删除开放 effect。

### 6.3 对象身份

第一阶段采用分级身份：

```text
EXACT       同一局部变量、参数、字段或明确容器成员
NORMALIZED  通过已审查 wrapper 映射得到
UNKNOWN     只能证明类型或大致角色，不能证明同一对象
```

系统不实现通用 points-to，而是限制在文件系统协议所需的字段、链表、root 和 device 角色上。

## 7. 合法出口验证

### 成功出口

必须满足：

```text
没有未解析的必要 failure token
当前 phase 属于合法成功阶段
必要 effect 已 COMMITTED 或合法 TRANSFERRED
accounting constraints 成立
返回值符合当前 attempt 的成功契约
```

### 失败出口

每个开放 effect 必须满足以下之一：

```text
COMPENSATED
由明确 handler 接管
已登记 RECOVERY_OWNED/DEFERRED_OWNED
事务范围内并且已 ABORT
```

`ANALYSIS_UNKNOWN` 与真实 `PARTIAL_UNRESOLVED` 分离。前者不声称程序错误，后者才生成高置信候选。

## 8. 输出和证据

每个候选保留：

```text
candidate_id
protocol_id
operation_id
violation_type
error_event
exit_event
principal_objects
open_effects
unresolved_failures
accounting_state
representative_trace
uncertainty_causes
static_certainty
```

证据分为独立维度：

```text
static_certainty
protocol_support
historical_confirmation
dynamic_validation
review_priority
```

总分只安排人工复核，不解释为 bug 概率。LLM、历史补丁和维护者反馈不能反向修改静态状态。

## 9. 工程模块

在现有 SE-EOD 基础上，完整实现建议拆成：

```text
src/frontend/                 parser、IR、CFG、调用图
src/semantics/                return contract、guard、对象身份
src/protocol/                 protocol DB、schema、版本和校验
src/metadata/                 event extractor、effect ledger、accounting
src/analysis/                 path propagation、summary、join、widening
src/verification/             legal exit、witness、candidate rules
src/evidence/                 history、dynamic、manual、ranking
```

现有 `cfg.py`、`dataflow.py`、`function_summary.py` 和 `resource_tracker.py` 作为前端和传播基础；资源生命周期可以作为 metadata effect 的一个特化，而不是再维护一套互不相容的状态引擎。

## 10. 评估设计

协议开发集和测试集必须隔离：

```text
开发集：设计协议和调试规则
冻结测试集：协议冻结后再标注
新版本集：检查跨版本泛化
真实发现集：只统计新的人工/动态确认
```

必须报告：

```text
precision / recall / F1 / P@K
bug-cluster recall
人工复核时间
unknown/unsupported 比例
协议编写成本和跨版本复用率
组件消融和误报分类
```

现有 `confirmed_bugs.md` 用于动机和回归验证，不可同时作为无偏测试集。

## 11. 研究边界

完整架构仍不声称：

```text
完整 Clang/Kbuild 编译证明
通用 points-to 或 SSA
任意 C 程序的完备路径可行性
完整并发可见性证明
完整 crash-consistency 证明
任意 metadata 算术关系自动推导
```

“完整”指协议、状态、证据和评估闭环完整，不指覆盖任意 Linux 语义。无法识别对象、责任域或 handler 时，系统必须保守保留不确定性。

