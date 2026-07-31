# FMPCA

**Failure-aware Metadata Protocol Conformance Analyzer**

失败感知的元数据协议符合性分析器

FMPCA 是一个面向 Linux 文件系统 C 源码的新静态分析工具。它在受限元数据协议规格的引导下，重建跨函数、跨对象的协议实例，分析调用失败后的执行路径，并在协议规定的 deadline 检查元数据关系、语义义务、责任转移、可观察性和返回结果是否共同符合规格。

本项目不再以旧的 `E_f/C_f/T_f/R_f` residual analysis 为方法基础。旧实现、测试、配置和评测脚本已从当前工作树移除；需要追溯时使用 Git 历史。

## 当前状态

```text
总体架构：已冻结为 FMPCA 1.0
形式语义：待编写五份可执行规范
工具实现：尚未开始
首个目标：打通一个 Btrfs MembershipConsistency 真实案例
```

当前仓库是设计与研究阶段的干净起点。现阶段没有可运行的分析器，也没有应当宣称通过的测试或实验结果。

## 研究问题

一个文件系统元数据操作通常分散在多个对象、字段和 helper 中。例如，将设备加入集合可能同时涉及：

```text
成员关系
成员计数
active pointer
对象生命周期
caller 或 transaction 责任
对外返回结果
```

局部 cleanup、字段恢复或 API 配对全部完成，并不保证这些关系在失败路径的正确时刻已经达到允许状态。FMPCA 的分析对象因此不是单个 effect，而是：

```text
protocol instance
```

## 核心模型

FMPCA 使用关系型符号协议状态机，而不是简单的单对象 FSM：

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

`Phase` 表示有限协议阶段；跨对象语义由关系事实、局部增量和义务表示，避免把所有关系组合展开成状态。

总体分析链为：

```text
C 源码
-> 失败路径、对象身份与隔离分析
-> 类型化元数据事件
-> 规格引导的协议实例重建
-> 关系型符号协议执行
-> 过程间摘要
-> 义务与责任转移
-> checkpoint / terminal settlement
-> Violation / Conformance Proof Closure
-> AcceptP 与覆盖假设报告
```

## 受限协议规格

协议规格来自文件系统设计不变量、内核文档和断言、重复源码模式，以及从历史 Bug 中归纳出的通用协议族。历史 Bug 只能用于归纳和验证，不能成为报警条件。

通用协议和源码绑定分离：

```text
通用规格：AddMember 产生关系同步义务
Btrfs binding：具体字段/API 被提升为 AddMember
```

DSL 和 binding 禁止依赖 Bug ID、补丁、行号、目标上层函数、特定调用链或任意 Python checker。工具提供的是 `spec-guided protocol instance reconstruction`，不是自动发现任意协议。

## 关键语义

- `TransactionContext` 不等于隔离、回滚或责任完成。
- `DELEGATED` 不等于 `DISCHARGED`，合法转交只改变责任主体。
- `ALWAYS` 不变量在每个协议语义点都必须成立。
- 其他不变量可以在已证明的隔离域内暂时不成立，但必须在 exposure、锁释放、return 等 deadline 前处理。
- `AuthorityTransfer` 是 checkpoint，不自动结束协议实例。
- `TransactionCommit` 和 `TransactionAbort` 使用不同的类型化语义。
- 证明一个违规 witness 与证明所有路径符合使用不同的 Proof Closure 条件。

简化接受条件为：

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

## 第一版范围

FMPCA 1.0 首先针对 Btrfs：

```text
协议：
  MembershipConsistency
  ActiveMemberSafety
  OutcomeContract

责任：
  CallerContinuation
  一个明确建模的 TransactionResponsibility
  FailstopContainment

局部增量：
  MembershipDelta
  CounterDelta
  ReferenceDelta
  PointerRebind
```

第一版不包括任意掉电点、持久化排序、crash image、通用 durability、完整线程交错、通用 atomic point 或任意符号集合分析。持久 recovery authority 在真实实现和评测完成前不作为能力声明。

## 输出

```text
VIOLATION_UNDER_LOADED_SPEC
POSSIBLE_VIOLATION_REVIEW
INCOMPLETE_UNDER_LOADED_SPEC
CONFORMANT_UNDER_LOADED_SPEC
NO_APPLICABLE_PROTOCOL
```

FMPCA 不输出绝对 `SAFE`。每个结论都相对于内核配置、路径模型、对象身份、摘要以及已加载协议规格成立，并附带 `Coverage and Assumption Report`。

## 项目文档

- [PAPER_ROADMAP.md](PAPER_ROADMAP.md)：研究主张、研究问题、里程碑与评测计划。
- [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md)：冻结决策、当前状态和下一步实施要求。

在五份可执行语义规范完成前，不应重新创建大规模实现目录或移植旧 residual 代码。
