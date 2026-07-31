# FMPCA Project Handoff

Updated: 2026-07-31

## 1. 当前结论

项目已正式从旧的 failure-path residual analysis 转向：

```text
FMPCA
Failure-aware Metadata Protocol Conformance Analyzer
```

FMPCA 是一个新工具，不以旧 `E_f/C_f/T_f/R_f` 代码为实现基础。旧源码、测试、脚本、配置、评测输出、依赖和 CI 已从当前工作树清理；相关历史仍可通过 Git 恢复。

当前真实状态：

```text
研究对象：已冻结
总体架构：已冻结
第一版范围：已冻结
形式语义：尚未冻结
代码实现：尚未开始
实验结果：尚不存在
```

## 2. 冻结的研究对象

FMPCA 分析失败路径中的 `protocol instance`，而不是单个 effect 是否存在反向操作。

一个实例可以同时绑定：

```text
container
member
counter
active pointer
owner
transaction context
operation outcome
```

工具在协议特定 deadline 判断该实例是否符合已加载规格，不证明整个文件系统的绝对一致性。

## 3. 冻结的总体架构

```text
C frontend
-> failure paths, identity, alias and isolation
-> typed evidence and protocol events
-> spec-guided protocol instance reconstruction
-> relational symbolic protocol interpretation
<-> guarded interprocedural summaries
-> semantic obligations and responsibility transfer
-> checkpoint / terminal settlement
-> Violation / Conformance Proof Closure
-> AcceptP and Coverage and Assumption Report
```

不得重新将旧 residual normalization 作为核心判断，也不得把 FMPCA 描述成旧工具的一个后处理模块。

## 4. 冻结的协议状态

```text
ProtocolState = <
    SymbolicPreState,
    Phase,
    RoleBindings,
    RelationFacts,
    OperationLocalDeltas,
    Obligations,
    AuthorityClaims,
    TransactionContext,
    IsolationEvidence,
    Observability,
    Outcome,
    IrreversibleViolationEvidence,
    PrecisionProvenance
>
```

四个报告维度保持独立：

```text
Consistency
Responsibility
Observability
Outcome
```

`VALIDLY_DELEGATED` 不推出当前关系一致或不一致。

## 5. 冻结的语义规则

### 责任

```text
DELEGATED != DISCHARGED
ACCEPTED != COMPLETED
TransactionContext != IsolationProof
TransactionResponsibility != AutomaticRollback
FailstopContainment != ConsistencyRestored
```

每项义务必须声明：

```text
required_formula
activation_horizon
DeadlinePolicy: MUST_DISCHARGE | MAY_DELEGATE_TO(...)
delegation_deadline
completion_deadline
allowed_authorities
```

### 时间与隔离

```text
ALWAYS
BEFORE_EXPOSURE
BEFORE_COMMIT
AT_SETTLEMENT
BEFORE_OWNER_TERMINATION
```

`ALWAYS` 在每个完成的协议语义点后检查，不能被锁或事务豁免。其他不变量只有在隔离证明闭合时才能延迟到 deadline。

```text
RelevantEscapeClosure =
    CLOSED | ESCAPED | INCOMPLETE
```

不能把“没有观察到逃逸”直接当作“证明没有逃逸”。

### 结算

```text
Checkpoint:
    ReleaseIsolation
    LiveExposure
    AuthorityTransfer
    TransactionCommit
    TransactionAbort

TerminalSettlement:
    OperationReturn
    OwnerTermination
    FailstopBoundary
    ProtocolComplete
```

Authority transfer 只产生 `DELEGATED(authority)`，不自动结束协议实例。

### 接受条件

```text
AcceptP(state, deadline) =
    AlwaysInvariantsHold
    and DueNonDelegableConditionsHold
    and DueObligationsDischargedOrPermittedDelegated
    and DelegationSafetyHolds
    and ExposureSafe
    and PhaseOutcomeCompatible
    and NoApplicableIrreversibleViolation
```

## 6. 规格与 binding 边界

规格来自文件系统语义、文档、断言和重复实现模式。历史 Bug 可帮助归纳协议族，但不能进入协议判断。

允许 binding 使用：

```text
结构体类型、字段路径、primitive API、参数位置
返回值分区、锁/owner API、typed access path
```

禁止使用：

```text
Bug ID、补丁、行号、目标上层函数
特定完整调用链、直接 Violation、直接 AcceptP
单 Bug 专用 phase 或布尔变量
```

规格声明 semantic footprint；分析器根据字段访问、别名、possible-write 和 callee summary 计算 program influence/repair slice。

## 7. 实例身份规则

```text
SemanticInstanceKey = <
    protocol_id,
    anchor_role_identities,
    base_epoch
>

InstanceId = <SemanticInstanceKey, instance_generation>
```

`BaseEpoch` 至少包含 operation root 和 retry generation。transaction context、object generation 或 allocation site 是否参与区分，由协议 `EpochPolicy` 决定。

```text
MUST_ALIAS     可绑定同一实例和解除义务
MAY_ALIAS      分裂候选状态
NO_ALIAS       不匹配
UNKNOWN_ALIAS  产生 INCOMPLETE
```

多个候选超过预算时形成 `CandidateInstanceSet`，不能据此证明 discharge 或 claim coverage。

## 8. 过程间摘要要求

摘要是带 guard 的有限关系：

```text
Summary_f(input_state) = {
    <guard, outcome, delta, obligations, claims, isolation>, ...
}
```

caller 将状态投影到 callee，应用匹配的摘要分区，再把结果投影回 caller。只有 operation root 可以加载合法入口假设；普通 helper 继承 caller 的中间状态。

`TransactionCommit` 与 `TransactionAbort` 必须分开建模，禁止通用的 `abort => rollback all` 或 `commit => complete all`。

## 9. Proof Closure 要求

必须分别实现：

```text
ViolationProofClosure(instance, witness_path)
ConformanceProofClosure(instance, operation_root)
```

违规 repair slice 只分析对应 deadline 之前可能完成修复或合法转交的代码。deadline 之后的 cleanup 不能消除已经产生的 exposure 或 irreversible witness。

证明符合要求全部相关路径闭合；一个独立违规 witness 不要求所有其他路径均完成分析。

事实精度为：

```text
EXACT | JOIN_PRESERVED | WIDENED | UNKNOWN
```

精确保留的 must fact 可以证明违规；依赖 widened/unknown 信息时不能证明符合。

## 10. 第一版实现范围

```text
Filesystem:
    Btrfs

Protocols:
    MembershipConsistency
    ActiveMemberSafety
    OutcomeContract

Responsibility:
    CallerContinuation
    TypedTransactionResponsibilityV1
    FailstopContainment

Deltas:
    MembershipDelta
    CounterDelta
    ReferenceDelta
    PointerRebind
```

暂不实现：

```text
任意 crash point
persist ordering 和 crash image
通用 durability
持久 recovery authority
完整线程交错
通用 AtomicPoint
任意符号集合或完整 heap/shape analysis
```

## 11. 下一步：五份可执行语义规范

在创建正式实现前，依次完成：

1. `protocol-dsl.md`：DSL 语法、类型、footprint、义务、deadline 和反硬编码约束。
2. `abstract-domain.md`：状态 lattice、join、widening、transfer 和精度 provenance。
3. `instance-reconstruction.md`：anchor、identity、EpochPolicy、generation 和候选冲突处理。
4. `interprocedural-summary.md`：guarded relation、参数投影、递归和错误分区。
5. `proof-closure.md`：influence/repair slice、deadline 截断、结果汇总和覆盖报告。

完成标准不是文档篇幅，而是每份规范都能直接导出数据结构、transfer rule 和单元测试。

## 12. 推荐实施顺序

```text
1. MembershipConsistency 纵向链
2. ActiveMemberSafety
3. OutcomeContract
4. CallerContinuation
5. TypedTransactionResponsibilityV1
6. FailstopContainment
7. Proof Closure 与完整评测
```

第一个端到端验收必须是：

```text
真实 Btrfs 源码
-> TypedEvent
-> ProtocolInstance
-> SymbolicDelta
-> SemanticObligation
-> ReleaseIsolation/OperationReturn deadline
-> AcceptP violation
-> source witness
```

## 13. 不得回退的路线

不要重新引入：

```text
E/C/T/R 作为论文核心
简单 SET/CLEAR 或 API pairing 作为一致性结论
函数出口即统一 settlement boundary
看到 transaction abort 就清除全部状态
以目标函数、行号或 Bug ID 驱动协议
用 MAY_ALIAS 关闭义务
用未知路径证明安全
把 fail-stop 描述为状态已经恢复
```

## 14. 风险和验收

最大技术风险依次为：

```text
协议实例重建错误合并或错误拆分
跨函数身份投影不稳定
binding 隐含 Bug 特判
隔离和逃逸证据不足
Proof Closure 对未知 repair/influence 处理不严谨
```

论文价值最终依赖以下证据：

```text
旧局部分析认为已处理，但 FMPCA 检出真实关系违规
至少一个真实 outcome 违规
一个冻结协议模板覆盖多个独立案例
修复版本和合法失败路径不报警
held-out 案例不修改通用 checker
Bug-specific condition count = 0
```

如果第一条真实纵向链失败，应修改具体事件绑定、实例算法或语义规则，不应重新设计顶层架构。
