# FMPCA Paper Roadmap

Updated: 2026-07-31

## 1. 论文主张

Linux 文件系统的一个逻辑元数据操作可能由多个对象、关系、计数器、owner 和返回结果共同表示，并跨越多个 helper 分阶段完成。调用失败后，局部操作已经配对或 cleanup 已经执行，不代表该逻辑操作在 exposure、operation return 或 owner termination 等 deadline 上符合元数据协议。

FMPCA 的目标是：

> 依据受限规格重建失败路径中的文件系统元数据协议实例，并在协议特定 deadline 联合验证跨对象关系增量、语义义务、责任转移、隔离可见性和 outcome。

## 2. 核心贡献

### C1：规格引导的协议实例重建

根据类型化元数据事件、anchor identity 和 operation epoch，将跨函数、跨对象的源码更新聚合为有限协议实例。

### C2：失败路径协议结算分析

在 release-isolation、live exposure、operation return、owner termination 和责任转移等 checkpoint/deadline 上，判断关系、义务、责任和 outcome 是否共同满足协议接受条件。

路径敏感分析、别名分析、CFG、SMT 和函数摘要属于支撑技术，不单独包装成核心贡献。

## 3. 与现有工作的边界

FMPCA 借鉴 typestate 的阶段和转换、路径敏感别名分析的状态传播，以及 SquirrelFS 对持久状态和恢复义务的区分思想，但不声称：

```text
把 typestate 首次扩展为多对象协议
验证完整 C 语义下的绝对安全
覆盖任意 crash point 或持久化顺序
自动发现任意文件系统协议
自动确认所有报告都是真实 Bug
```

更准确的定位是：

```text
failure-aware
+ filesystem metadata protocol
+ spec-guided instance reconstruction
+ relational symbolic state
+ deadline-aware obligation settlement
```

## 4. 研究问题

```text
RQ1  Detection
     FMPCA 能否发现 API pairing、字段恢复和局部 residual 分析遗漏的
     真实失败路径协议违规？

RQ2  Reconstruction
     FMPCA 能否正确聚合跨 helper 的同一协议事件，同时避免合并不同对象、
     retry 或 operation generation？

RQ3  Reuse
     冻结后的通用协议模板能否仅通过少量源码 binding 覆盖多个独立 Bug？

RQ4  Precision
     Proof Closure、隔离/逃逸分析和责任转移对误报、INCOMPLETE 与分析成本
     分别有什么影响？

RQ5  Generalization
     协议冻结后，工具能否检测 held-out Bug 或独立构造的 mutant，并在修复版本
     和合法失败路径上不报警？
```

## 5. 方法核心

```text
EntryPredicate(S0)
+ PathSemantics(S0, path, Sf)
+ protocol-specific deadline
+ ProofClosure
-> AcceptP(Sf, deadline)
```

确定违规采用存在性条件：

```text
exists path:
    FeasibleModelPath(path)
    and ViolationProofClosure(instance, path)
    and not AcceptP(FinalState(path), deadline)
```

规格内符合采用全称条件：

```text
for every relevant reachable path:
    ConformanceProofClosure(instance, path)
    and AcceptP(FinalState(path), deadline)
```

## 6. 第一版实验范围

目标文件系统：`Btrfs`。

协议模板：

```text
MembershipConsistency
ActiveMemberSafety
OutcomeContract
```

责任机制：

```text
CallerContinuation
TypedTransactionResponsibilityV1
FailstopContainment
```

第一版不评测任意掉电、flush/barrier、crash image、通用持久恢复或完整并发交错。

## 7. 对照基线

至少实现或复现实验上可比较的三类基线：

```text
B1  API pairing / companion-operation checking
B2  field restoration or local effect residual checking
B3  path-sensitive single-object typestate checking
```

比较重点不是单纯报告数量，而是 FMPCA 是否检测到基线判断为已处理、但协议终态仍非法的强案例。

## 8. 评测设计

### 真实强案例

至少包含：

```text
Case A  Membership 或 ActiveMember 关系违规
        局部 cleanup 看似完成，但 active pointer 指向非成员或 dead object。

Case B  Outcome 违规
        COMPLETE + ERROR，或 PARTIAL + SUCCESS。
```

### 泛化与负例

```text
fixed-version differential
安全 cleanup 路径
合法 caller continuation
合法 transaction responsibility
fail-stop containment
leave-one-bug-out
held-out Bug
与协议开发过程独立的 mutation set
```

### 反硬编码指标

```text
每个协议模板覆盖的函数和 Bug 数
每条 binding 的复用次数
新增案例需要增加的 binding 行数
通用 checker 修改次数
Bug-specific condition count = 0
```

## 9. 实施里程碑

### F0：可执行语义

完成五份规范：

```text
protocol DSL and type system
abstract domain and transfer semantics
protocol instance reconstruction and EpochPolicy
interprocedural protocol summary algebra
Violation/Conformance Proof Closure
```

### F1：最小前端和 Membership 纵向链

实现 C 前端、错误路径、类型化事件、anchor identity、局部 delta 和 `MembershipConsistency`，在一个真实 Btrfs 函数上输出源码 witness。

### F2：ActiveMemberSafety

加入 pointer rebind、member liveness、isolation release、escape/exposure 和 irreversible evidence。

### F3：OutcomeContract

关联协议阶段与 `SUCCESS/ERROR/RETRY/DEFERRED`，验证完成程度与返回结果一致。

### F4：过程间与责任传播

实现 guarded relational summaries、caller continuation、一个受限 transaction responsibility 和 fail-stop containment。

### F5：Proof Closure 与报告

实现 influence/repair slice、deadline 截断、精度 provenance、两类 witness 等级和 `Coverage and Assumption Report`。

### F6：实验与论文

冻结协议和 checker 后执行基线、消融、修复版本、负例、leave-one-out 和 held-out 实验。

## 10. 每阶段验收原则

任何里程碑都不能只通过报告数量变化验收。必须同时满足：

```text
目标 witness 有源码和状态转换证据
may-alias 不用于解除义务
未知 repair 不产生确定违规
未知 influence 不产生 CONFORMANT
修复版本和对应安全路径不报警
新增 binding 不包含目标函数或 Bug 特判
```

## 11. 论文成立的最低证据

论文主张只有在以下条件全部满足后才成立：

```text
至少一个旧局部分析认为已处理、FMPCA 检出的真实关系 Bug
至少一个 metadata transition 与 outcome 不一致的真实 Bug
同一冻结协议模板覆盖多个独立案例
修复版本及合法责任转移路径不报警
held-out 案例不修改通用 AcceptP 或 checker
```

在这些证据完成前，只能声称架构和方法假设成立，不能声称工具已经具备一般化检测能力。
