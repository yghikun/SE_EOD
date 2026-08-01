# FMPCA Project Handoff

Updated: 2026-08-01

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
P0.1-P0.7 初始语料整理和通用语义挖掘：已完成
Protocol Catalog v0.1：已冻结为工程基线，不再作为最终领域协议目录
S0 五份可执行语义规范：已完成，语义内核可复用
I0-I3 语义内核、源码 binding、摘要与报告：已实现，可复用于 P1
P1.0-P1.6 领域协议重挖、追踪、replay、划分和 Catalog v0.2：已完成
I4：RecoveryAttachmentSettlement 与 DeviceTopologyRollback 已接入语义内核和真实源码 binding
Gate P1：PASS；领域对象、状态机、责任和 deadline 已冻结
Gate S：PASS；通用机制已降级为内核构件，领域规则不依赖案例特判
Gate R：RAS/DTR development Bug-source witness PASS；v0.2 fixed-source differential 仍开放
E0：23/23 cases passed，重新分类为语义内核资格/回归测试
E1：14/14 cases passed，解释为领域协议资格/回归评测，不是独立大规模 benchmark
E3：8/8 v0.3 Bug/fixed/normal/unknown replay cases passed；不是独立 family 或跨 FS benchmark
E2：候选资格门禁完成；0 个 v0.2 held-out family，v0.3 candidates=2，Git/source artifacts verified
v0.3：RelocationRootAttachmentSettlement 与 DeviceShrinkSpaceAccounting 已冻结为 Catalog v0.3 窄范围协议；两者各只有一个 operation family，因此不宣称 held-out 或跨文件系统泛化
runtime relocation merge 的 Bug 与 accepted fix 均已由 commit、blob、KASAN 报告和 repair slice 证实；它未纳入 v0.2 只因为 operation lifecycle 不在冻结 RAS 适用域，不是因为缺少 fix
单元与集成测试：58/58 passed
Bug-specific condition count：0
Held-out checker modifications：0
Protocol/AcceptP modifications after E2 candidate reveal：0
Membership 真实案例资格审查：已完成，无案例通过
Membership 合成语义 fixture：已就绪，不属于论文证据
当前状态：v0.3 窄冻结已完成；独立 operation family 仍是泛化门槛，不再是窄冻结门槛；DSSA 的 Btrfs 设计/正常路径证据和跨文件系统筛选已记录
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

## 10. 协议挖掘范围

第一轮协议挖掘使用 ext4、Btrfs 和 XFS 的已确认元数据 Bug，不再预先将某个文件系统或某个协议族指定为实现核心。

纳入条件：

```text
Bug 改变或控制文件系统元数据转换
或破坏元数据对象之间的关系
或破坏 transaction/recovery responsibility
或使 metadata transition 的 outcome 与实际完成阶段不一致
```

排除条件：

```text
普通 buffer_head、folio、path、filename 或 heap object 泄漏
只涉及通用资源生命周期
无法绑定元数据协议角色或关系
只有名称推断，没有源码、补丁或复现证据
```

`dquot`、transaction object、recovery root 等对象不能仅因名称属于文件系统就自动纳入。必须证明问题影响元数据语义，而不只是引用计数或内存释放。

当前确认语料的最终筛选结果为：

```text
纳入：
    #1, #2, #4, #5(error/outcome 部分), #7,
    #8, #13, #15, #16, #17, #18

排除：
    #3, #6, #9, #10, #11, #12, #14
```

逐项理由、证据状态和开发/验证/held-out 角色已记录在
`docs/corpus/confirmed-metadata-bugs.md` 与 `docs/protocol-mining/evaluation-split.md`。

MembershipConsistency 当前仅作为 DSL 和语义内核的合成 fixture。除非以后出现满足冻结公式的真实确认 Bug，否则不作为第一版论文协议或真实检测能力声明。

仍然暂不进入第一版范围：

```text
任意 crash point
persist ordering 和 crash image
通用 durability
持久 recovery authority
完整线程交错
通用 AtomicPoint
任意符号集合或完整 heap/shape analysis
```

## 11. 已完成工作与验收依据

`P0.1-P0.7`、`S0`、`I0-I4`、`E0` 和 `P1/E1` 已完成。下面的 11.1-11.12
保留原始执行契约，作为证据和实现审计依据；P0.7 形成的通用协议目录现在
降级为工程基线，不再直接作为论文的领域协议目录。

| 阶段 | 已完成内容 | 主要证据 |
|---|---|---|
| P0.1 | 恢复、筛选并版本化 confirmed metadata Bug corpus | `docs/corpus/` |
| P0.2 | 为 11 个纳入 Bug 建立 dossier 和统一语义记录 | `docs/cases/` |
| P0.3 | 按语义失败模式聚类并抽取候选协议 | `docs/protocol-mining/candidate-clusters.md` |
| P0.4 | 建立规则到文档、正常、Bug、fixed、safe 的追踪矩阵 | `docs/protocol-mining/traceability-matrix.md` |
| P0.5 | replay Bug、fixed、safe、delegated 和 unknown 路径 | `docs/protocol-mining/manual-replay-results-v0.1.md` |
| P0.6 | 冻结 development、validation、leave-one-out 和 held-out 划分 | `docs/protocol-mining/evaluation-split.md` |
| P0.7 | 形成 Catalog v0.1：MTO 与 FRC；现标记为通用工程基线；#15 延后 | `docs/protocol-mining/protocol-catalog-v0.1.md` |
| S0 | 完成五份可执行语义规范 | `docs/specs/` |
| I0-I1 | 实现 DSL、状态域、transfer、settlement、Proof Closure 和 fixtures | `src/fmpca/`、`tests/` |
| I2 | 实现 ext4/XFS outcome 与 Btrfs relation binding、identity、witness | `configs/bindings/`、`outputs/fmpca-e0-v0.1/` |
| I3 | 实现 guarded summary、隔离、责任传播和 Coverage Report | `src/fmpca/summary.py`、`src/fmpca/report.py` |
| E0 | 执行 baseline、负例、fixed、LOO 和 held-out 语义测试 | `23/23`；现解释为内核资格/回归测试，不是独立泛化证据 |
| P1.0-P1.6 | 建立领域资格标准，重挖 RAS/DTR，完成 traceability、replay、split 和 Catalog v0.2 | `docs/protocol-mining/domain-*-v0.2.md` |
| I4 | 实现两个领域协议、binding、多关系恢复/委托和 release/owner deadlines | `configs/protocols/*v0.2.json`、`configs/bindings/*v0.2.json` |
| E1 | 执行 Bug、fixed、safe-delegated、deadline-negative、unknown 和真实源码评测 | `14/14`；`outputs/fmpca-e1-v0.2/` |
| E2 | 对 post-freeze candidate 执行 semantic-footprint eligibility gate | `0` 个纳入 family，`1` 个 v0.3 candidate，Git artifacts `2`；`outputs/fmpca-e2-v0.2/` |
| V0.3-FREEZE | 冻结 `RelocationRootAttachmentSettlement` 窄范围协议、独立 adapter、replay 和 hash lock | `configs/freeze/domain-semantic-freeze-v0.3.json`、`docs/protocol-mining/domain-protocol-catalog-v0.3.md` |
| V0.3-FREEZE-2 | 冻结 `DeviceShrinkSpaceAccounting`，补齐 Btrfs 设计/正常源码证据、跨 FS 筛选和四类 replay | `docs/protocol-mining/dssa-evidence-v0.3.md`、`docs/protocol-mining/cross-filesystem-evidence-policy-v0.3.md` |

第一轮 Gate 的实际状态：

```text
Gate P1 = DOMAIN_CATALOG_V0.2_PASS
Gate S = DOMAIN_KERNEL_AND_BINDING_PASS
Gate R = DEVELOPMENT_BUG_SOURCE_WITNESS_PASS; V0.2_FIXED_SOURCE_DIFFERENTIAL_OPEN
```

Gate R 的剩余限制不是语义内核或领域协议失败：RAS 已有 v6.8 真实 Bug 源码
violation witness，DTR 已有 v6.14 三 relation mutation/部分 cleanup violation witness；
但仓库尚无同一 frontend 下的本地 fixed-source 快照。repaired/safe 证据来自补丁来源、
动态记录和结构化 fixture，因此当前仍不能声称 source-level Bug/fixed differential。
这一限制不阻止 v0.3 的窄范围冻结：RRAS 明确把 selected fixed branch 的 all-path
closure 标为 `INCOMPLETE`，DSSA 则以独立 Btrfs 设计/正常路径补足规则来源；两者均不把
该限制隐藏成 conformance 或跨文件系统泛化结论。

### 11.1 建立可审计的元数据 Bug 语料

原 `outputs/confirmed_bugs.md` 是旧项目输出位置，不应直接作为新工具的输入。将其从 Git 历史恢复并迁移为只读研究语料：

```text
docs/corpus/confirmed-bugs-source.md
docs/corpus/confirmed-metadata-bugs.md
```

`confirmed-bugs-source.md` 保留原始记录和证据，不修改历史含义。`confirmed-metadata-bugs.md` 是新项目的筛选表，每个 Bug 必须记录：

```text
bug_id
filesystem
source version / commit
function and failure point
confirmation evidence
metadata relevance
include / exclude
decision rationale
candidate protocol family
development / validation / held-out role
```

### 11.2 为每个纳入 Bug 建立证据包

每个 Bug 建立独立 dossier，至少收集：

```text
设计文档、源码注释或 assertion 中的规范依据
Bug 版本的 operation root 和精确失败路径
正常路径和安全 error sibling path
修复补丁及修复后路径
参与对象及其生命周期
transaction / isolation / exposure 上下文
运行复现、fault injection 或维护者确认
```

缺失关键信息时标记 `EVIDENCE_INCOMPLETE`，不能为了覆盖率补写协议条件。

### 11.3 将源码操作归一化为协议事实

在定义协议前，先为每个 Bug 手工填写统一语义记录：

```text
OperationRoot
Roles and candidate anchor roles
Entry assumptions
Typed event sequence
Relation changes and operation-local deltas
Generated semantic obligations
Isolation and observability changes
Responsibility or authority transfer
Outcome and terminal state
Applicable deadlines
```

这一阶段只做归一化，不立即给 Bug 指定最终协议，也不编写 AcceptP。

### 11.4 按语义失败模式聚类

P0.3 根据归一化结果聚类，而不是根据文件系统、函数名或补丁系列聚类。当时使用的候选协议族为：

```text
MetadataTransitionOutcome
    #1, #2, #4, #5(error 部分), #8, #13

CompanionMetadataCompletion
    #15

ActiveAttachmentSafety
    #7, #17

TransactionResponsibility
    #16

FailureRollbackConformance
    #18
```

聚类结果允许拆分、合并或淘汰，但任何变化都必须由文档语义、正常源码模式和多个案例共同支持，不能只因为某个 Bug 难以归类。

最终 `MetadataTransitionOutcome` 与 `FailureRollbackConformance` 进入 Catalog
v0.1，`CompanionMetadataCompletion` 因只有 #15 单例而延后。

### 11.5 手工抽取候选协议规格

每个候选协议使用统一模板：

```text
ProtocolId
SemanticIntent
Roles
AnchorRoles
EntryPredicates
Phases
TypedEvents
Transitions
RelationUpdates
TemporalInvariants
SemanticObligations
AllowedAuthorities
Deadlines
CheckpointTriggers
TerminalSettlements
AcceptanceClauses
FrameConditions
SemanticFootprint
EvidenceReferences
```

每一条 invariant、obligation 和 deadline 必须至少标注：

```text
规范来源：文档、注释、assertion 或设计语义
正常实现来源：至少一条正常/回滚源码路径
反例来源：一个或多个 confirmed metadata bugs
```

Bug ID、目标函数名、源码行号和补丁版本只能出现在 evidence reference 中，不能出现在协议 guard 或 AcceptP 中。

### 11.6 建立 Traceability Matrix

创建：

```text
docs/protocol-mining/traceability-matrix.md
```

矩阵至少包含：

| Protocol | Rule | Document evidence | Normal source | Bug path | Fixed path | Safe negative | Status |
|---|---|---|---|---|---|---|---|

如果一条规则只有 Bug path，没有独立的规范或正常源码依据，则标记 `BUG_DERIVED_ONLY`，不能进入冻结协议。

### 11.7 手工 Replay 全部路径

为每个候选协议手工解释：

```text
Bug 路径
修复路径
正常成功路径
安全错误路径
合法责任转移路径
未知 helper 路径
```

每条 replay 记录：

```text
ProtocolInstanceKey
事件序列
逐步 ProtocolState
激活和解除的义务
触发的 deadline
AcceptP 子句结果
Violation / Conformant / Incomplete
```

手工 replay 的目标不是让所有纳入 Bug 都被某个协议覆盖。无法由有限通用规则解释的 Bug 可以标记 `OUTSIDE_PROTOCOL_CATALOG_V0`。

### 11.8 建立开发、验证和 Held-out 划分

不能用全部 confirmed bugs 编写协议后，再用同一批 Bug 声称泛化能力。

```text
DEVELOPMENT
    可用于发现和修改协议

VALIDATION
    规格稳定后用于调参和检查安全负例

HELD_OUT
    协议和 AcceptP 冻结后才能揭示
```

如果某一协议族案例过少，采用 leave-one-bug-out，而不是强行固定比例。任何 held-out 失败只能新增通用 binding 或报告 `INCOMPLETE`；修改通用 AcceptP 后，该案例不再属于 held-out。

### 11.9 评价并选择第一版协议

对每个候选协议评分：

```text
文件系统元数据特异性
已确认 Bug 数
独立函数和文件系统复用性
是否超越 API pairing / field restoration / local residual
安全路径和修复版本可用性
所需 alias / interprocedural / concurrency 能力
Bug-specific binding 数量
手工 replay 的确定性
```

第一版只选择 2-3 个协议。优先选择既有关系或责任语义、又有真实确认 Bug 和安全负例的协议。`MetadataTransitionOutcome` 可以作为工程入口和对照，但不能单独承担论文的文件系统特异性贡献。

### 11.10 冻结 Protocol Catalog v0.1

创建：

```text
docs/protocol-mining/protocol-catalog-v0.1.md
docs/protocol-mining/manual-replay-results-v0.1.md
docs/protocol-mining/freeze-manifest-v0.1.md
```

freeze manifest 记录：

```text
协议版本和内容哈希
纳入/排除 Bug 集合
development / validation / held-out 划分
使用的内核版本和配置
binding 版本
已知未建模语义
冻结日期
```

冻结后才能进入 DSL 和分析器实现。后续修改协议必须创建新版本，并说明由哪类通用证据触发。

### 11.11 协议冻结后编写五份可执行规范

根据选中的 2-3 个协议，在 `docs/specs/` 中建立：

1. `protocol-dsl.md`：协议模板如何声明式表示。
2. `abstract-domain.md`：协议状态、lattice、join、widening 和 transfer。
3. `instance-reconstruction.md`：roles、anchor、alias、epoch 和 generation。
4. `interprocedural-summary.md`：guarded summary 和调用投影。
5. `proof-closure.md`：influence/repair slice、deadline 和结果证明。

Membership synthetic fixture 保留为 DSL 单元测试，但不能决定 DSL 的全部表达能力，也不能替代冻结协议目录中的真实案例。

### 11.12 三个实施 Gate

#### Gate P：协议目录冻结

```text
元数据 Bug 筛选逐项完成
每个冻结协议有规范、正常源码和 confirmed bug 三类证据
Bug、fixed 和 safe 路径已手工 replay
不存在 BUG_DERIVED_ONLY 的冻结规则
development / validation / held-out 已记录
Protocol Catalog v0.1 和 freeze manifest 已生成
```

#### Gate S：语义内核实现

```text
五份可执行规范完成
冻结协议和 Membership fixture 均可由 DSL 表示
transfer 和 settlement 有成对测试向量
AcceptP 不依赖 Bug ID、函数名或行号
Violation / Conformance Proof Closure 输入输出明确
```

Gate S 已按该顺序通过：先建立 `src/` 与 `tests/` 中的结构化事件语义内核，再进入真实源码 binding。

#### Gate R：真实源码分析

```text
至少一个冻结协议有通过资格审查的真实纵向案例
真实路径、身份和 deadline 已人工核对
binding 只使用允许的类型、字段和 primitive 证据
修复版本和安全路径已确定
```

Gate R 已按该顺序通过，并形成 C frontend、Btrfs/ext4/XFS binding 和 source witness。

## 12. 已完成：P1 Domain Protocol Re-mining

### 12.1 方向纠偏

当前真正的问题不是“通用协议缺少更多案例”，而是协议抽象层级错误：

```text
把失败形状抽象成 MTO/FRC
-> 不同元数据对象和生命周期被压进同一模板
-> 领域语义被转移到 binding
-> Catalog 失去文件系统元数据特异性
-> E0 只能证明通用机制可运行，不能支撑领域协议泛化
```

因此，MTO/FRC 不删除，但降级为语义内核可复用的机制：

```text
OutcomeAgreement      -> 通用 settlement clause
RestoreOrDelegate     -> 通用 obligation/authority schema
ProofClosure          -> 通用证明闭包机制
```

它们不再作为最终论文中的领域协议名称。

### 12.2 领域协议候选

领域协议必须绑定具体元数据对象、关系、合法状态、操作阶段、责任主体和结算边界。
当前优先重挖：

```text
RecoveryAttachmentSettlement
    #7
    fs_root <-> reloc_root attachment
    root reference ownership
    recovery failure
    teardown authority
    owner-termination settlement

DeviceTopologyRollback
    #16, #17, #18
    device membership and update-list ownership
    active device pointers
    sprout container and fsid identity
    transaction failure
    topology restoration before release/exposure
```

`#16/#17/#18` 来自同一 `btrfs_init_new_device` operation root 和同一补丁系列，
不能当作三个独立的泛化案例；它们是同一 `DeviceTopologyRollback` 协议的不同
关系投影。#7 虽然是单一 Bug，也不能因此否定协议资格；协议资格来自设计语义、
正常路径、合法失败路径和关系状态机，案例数量只影响评测强度。

ext4/XFS 案例暂不强行归入领域协议。需要重新检查它们是否分别形成
`FastCommitReplaySettlement`、`RealtimeMetadataGrowthSettlement` 或其他有独立
元数据对象和阶段语义的协议；如果只能得到“错误结果必须传播”，则保留为
`OutcomeAgreement` 的验证材料，不进入领域 Catalog。

### 12.3 执行顺序

```text
P1.0  DONE  领域协议资格标准和 kernel/domain 边界
P1.1  DONE  按对象、关系、生命周期和 operation family 重聚类
P1.2  DONE  RecoveryAttachmentSettlement 规格与事件词汇
P1.3  DONE  DeviceTopologyRollback 规格与关系投影
P1.4  DONE  ext4/XFS 降级为 OutcomeAgreement 材料，不强造领域协议
P1.5  DONE  domain traceability、manual replay 和独立性划分
P1.6  DONE  Domain Protocol Catalog v0.2 与 semantic freeze
I4    DONE  两个领域协议、binding、deadline 和 Proof Closure 接入
E1    DONE  14/14 Bug/fixed/safe/deadline/unknown/source qualification cases
```

### 12.4 已交付工件

```text
docs/protocol-mining/domain-protocol-criteria.md
docs/protocol-mining/domain-candidate-catalog-v0.2.md
docs/protocol-mining/domain-traceability-matrix-v0.2.md
docs/protocol-mining/domain-manual-replay-v0.2.md
docs/protocol-mining/domain-evaluation-split-v0.2.md
docs/protocol-mining/domain-protocol-catalog-v0.2.md
docs/protocol-mining/domain-freeze-manifest-v0.2.md
configs/freeze/domain-semantic-freeze-v0.2.json
configs/evaluation/e1-v0.2.json
outputs/fmpca-e1-v0.2/results.json
outputs/fmpca-e1-v0.2/report.md
```

v0.3 frozen artifacts additionally deliver:

```text
configs/protocols/relocation-root-attachment-settlement-v0.3-draft.json
configs/bindings/relocation-root-attachment-settlement-v0.3-draft.json
src/fmpca/frontend_v3.py
tests/fixtures/events/rras-normal.json
tests/test_v3_candidate.py
docs/protocol-mining/relocation-root-attachment-settlement-v0.3-draft.md
docs/protocol-mining/rras-traceability-v0.3-draft.md
docs/protocol-mining/rras-independence-screening-v0.3-draft.md
configs/evaluation/rras-v0.3-readiness.json
configs/freeze/domain-semantic-freeze-v0.3.json
docs/protocol-mining/domain-protocol-catalog-v0.3.md
docs/protocol-mining/domain-traceability-matrix-v0.3.md
docs/protocol-mining/domain-manual-replay-v0.3.md
docs/protocol-mining/domain-evaluation-split-v0.3.md
docs/protocol-mining/domain-freeze-manifest-v0.3.md
docs/protocol-mining/cross-filesystem-evidence-policy-v0.3.md
configs/evaluation/e3-v0.3.json
outputs/fmpca-e3-v0.3/results.json
outputs/fmpca-e3-v0.3/report.md
```

DeviceShrinkSpaceAccounting v0.3 frozen artifacts additionally deliver:

```text
configs/protocols/device-shrink-space-accounting-v0.3-draft.json
src/fmpca/frontend_device_shrink.py
tests/fixtures/patches/btrfs-shrink-free-chunk-space-e9fd2c.json
tests/fixtures/events/dssa-bug.json
tests/fixtures/events/dssa-fixed-success.json
tests/fixtures/events/dssa-fixed-failure.json
tests/fixtures/events/dssa-unknown.json
tests/test_device_shrink_candidate.py
docs/protocol-mining/device-shrink-space-accounting-v0.3-draft.md
configs/evaluation/dssa-v0.3-readiness.json
docs/protocol-mining/dssa-evidence-v0.3.md
```

Catalog v0.1、E0 manifest、E0 输出和 v0.1 freeze 未被覆盖。v0.2 freeze 额外锁定
E1 fixtures、真实源码快照和关键 semantics/frontend/proof 实现，避免只锁配置但允许
输入或抽取逻辑漂移。

### 12.5 Gate P1

以下条件均已满足，Gate P1 状态为 `PASS`：

```text
协议名称指向具体元数据对象/关系，而不是失败结果或通用回滚动作
协议有明确的合法状态机、operation root、anchor 和 settlement deadline
每条规则同时有规范语义、正常源码、Bug 路径和 fixed/safe 路径证据
binding 只负责把源码映射为领域事件，不承担未声明的协议语义
同一 operation family 的多个 Bug 不被错误计数为独立泛化案例
无法证明领域特异性的规则降级为 kernel clause 或 OUTSIDE_PROTOCOL_CATALOG
领域协议变化创建新 Catalog 版本，不回写 v0.1
```

独立性限制已显式记录：#7 只有一个 relocation-recovery family；#16/#17/#18
只算一个 seed-to-sprout family。runtime relocation merge 虽然 Bug/fix 已确认，
但其 preexisting attachment 生命周期超出冻结 RAS v0.2，已降级为
`RelocationRootAttachmentSettlement` v0.3 successor；该协议现已在新 Catalog 中窄冻结。因此 E2 的
`held_out_operation_families=[]`，不制造 held-out；真正 held-out 必须同时满足
operation-family 独立性和冻结协议适用域。

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

## 14. 当前风险、决策规则和验收

P1/E1 已证明领域协议本体和执行链可运行。当前风险按优先级为：

```text
1. RRAS v0.3 只有一个 runtime relocation merge family，不能宣称泛化
2. DSSA v0.3 只有一个 `btrfs_shrink_device` family，不能宣称泛化
3. RAS 与 DTR 都缺少同一 frontend 下的本地 fixed-source differential
4. 两个冻结协议各只有一个独立 operation family，尚无诚实 held-out 泛化证据
5. regex frontend 对宏、别名、路径和调用关系的结构恢复能力有限
6. conformance 所需的全路径、alias、escape closure 难于规模化闭合
7. capability-class baseline 不能替代外部工具的实证比较
8. provenance、环境和运行命令尚未形成独立复现实验包
```

TOC 决策规则：真正瓶颈是“领域适用域闭合”和“独立泛化证据”被混为一个门槛。
现已拆分：RRAS/DSSA 的具体对象关系、状态、责任、deadline、Bug/fix、正常路径和
replay 足以支持窄冻结；独立 operation family 只决定 generalization eligibility。
跨文件系统源码只能在对象角色、关系方向、单位/公式、阶段、authority 和 deadline
全部对应时支持同一规则；本轮 ext4/XFS/F2FS 未满足等价条件，未进入 AcceptP。
没有新的独立 family 时不宣称 held-out 泛化，也不把同 family 补丁重复计数。
没有新规范证据时不扩写 AcceptP、不把 #15 singleton 纳入 Catalog，也不以 E0/E1
指标宣称跨文件系统泛化。

已验证且后续不得丢失的内核回归门禁：

```text
58/58 tests passed；E3=8/8 cases passed
23/23 E0 cases passed
14/14 E1 cases passed
v0.1/v0.2 semantic freeze hash mismatches = 0
Bug-specific condition count = 0
held-out checker modifications = 0
UNKNOWN/WIDENED 不证明 conformance
transaction abort 不自动恢复任意 relation
delegation 不等于 obligation completion
owner termination 触发 termination boundary 和 AT_SETTLEMENT
device release 触发 BEFORE_RELEASE membership check
```

若新增 source/held-out 案例失败，先按以下顺序归因：

```text
binding gap -> identity/summary gap -> closure gap -> domain-protocol gap
```

只有独立规范证据证明领域协议本身不完整时，才创建 Catalog 新版本；
不能为保住指标向 v0.1 或 v0.2 AcceptP 加入案例特判。

## 15. 已完成：设备拓扑与容量贡献分解 v0.4

本节记录 2026-08-01 的最终实现状态，并取代第 14 节中“DSSA 只有一个 family”
作为设备容量方向的当前判断。v0.1-v0.3 冻结工件未被回写。

### 15.1 任务本质与最终决策

问题不是 DTR 与 DSSA 是否都调用设备函数，而是二者是否拥有同一个不可分割的
状态变量和结算边界。因果链如下：

```text
设备加入/删除会同时改变 topology 与 capacity
-> 两类状态经常在同一 operation root 中共同出现
-> 仅按函数或 Bug 聚类会误以为它们是一个协议
-> 但 resize 可以改变 capacity 而不改变 membership
-> topology 与 capacity 存在可独立变化的合法路径
-> 它们不能被压成一个带大量条件分支的协议
-> 应冻结两个 component，并用严格身份和跨关系公式进行 composition
```

最终分解为：

```text
DeviceTopologyRollback (DTR, frozen v0.2)
    membership / post-commit membership
    active device pointer / fsid identity
    topology rollback / exposure / release

WritableDeviceCapacityContribution (WDC, frozen v0.4)
    writable and allocation eligibility
    total_rw_bytes / free_chunk_space contribution
    add/remove and resize delta
    failed-delta restoration / capacity detachment before release

DeviceTopologyCapacityComposition (DTC, frozen v0.4)
    exact shared operation + device identity
    topology eligibility <-> capacity eligibility/contribution
    release-time joint detachment
```

`DeviceShrinkSpaceAccounting` v0.3 保持不可变；它现在被解释为 WDC 的 shrink
transition predecessor，而不是被删除、重写或与 DTR 直接拼接。

### 15.2 已冻结的语义约束

WDC：

```text
WDC-I1  capacity.eligible 必须与 component 内可见的 membership、writable、
        allocation-eligible 状态一致
WDC-I2  aggregate delta 必须表示真实贡献变化；失败恢复必须复用同一 delta
WDC-I3  device release 前 capacity contribution 必须已经 detached
WDC-O1  失败产生的 operation-local capacity delta 必须恢复到 prestate，
        或由合法 capacity_owner 在 settlement 前完成
```

DTC：

```text
DTC-ID  DTR/WDC 的 operation 或 device 身份不精确/不相等 -> INCOMPLETE
DTC-C1  Eligible = Member && Writable && AllocationEligible
DTC-C2  Eligible 与 terminal capacity contribution 的 PRESENT/ABSENT 一致
DTC-C3  BEFORE_RELEASE 时 membership 与 contribution 都必须为 ABSENT
```

组合判定保持 Proof Closure 边界：component violation 向 composition 传播；
任一 `UNKNOWN/WIDENED`、身份冲突或全路径未闭合都不能证明 conformance。
protocol guard、AcceptP 和 binding selection 均不使用 Bug ID、函数名、补丁 ID 或行号。

### 15.3 operation family 与证据强度

WDC 已由两个独立操作族共同验证：

```text
btrfs-device-membership-change
    btrfs_init_new_device 的 add/remove、容量加入及失败回滚语义

btrfs-device-capacity-resize
    btrfs_shrink_device 的 used-aware shrink、Bug/fix 与失败回滚语义
```

因此可以声称：

```text
freeze_eligible = true
cross_operation_family_validated = true
```

仍不能声称：

```text
held_out_generalization_eligible = false
cross_filesystem_generalization_eligible = false
```

原因是这两个 family 都参与了 v0.4 开发/验证，没有 post-freeze held-out family；
ext4/XFS/F2FS 也尚未同时满足对象角色、关系方向、单位/公式、阶段、authority 和
deadline 等价条件。真实 confirmed Bug 有 fix 并不消除这一限制：fix 能闭合负例与
修复语义，但不能自动制造独立 family 或跨文件系统等价性。

### 15.4 已交付实现

```text
configs/protocols/writable-device-capacity-contribution-v0.4.json
configs/compositions/device-topology-capacity-v0.4.json
configs/bindings/writable-device-capacity-contribution-v0.4.json
configs/evaluation/wdc-v0.4-readiness.json
configs/evaluation/e4-v0.4.json
configs/freeze/domain-semantic-freeze-v0.4.json

src/fmpca/frontend_capacity.py
src/fmpca/composition.py
src/fmpca/readiness_v4.py
tests/test_device_composition_v4.py
tests/fixtures/events/*v0.4.json

docs/protocol-mining/device-protocol-decomposition-v0.4.md
docs/protocol-mining/device-source-evidence-v0.4.md
docs/protocol-mining/domain-protocol-catalog-v0.4.md
docs/protocol-mining/domain-traceability-matrix-v0.4.md
docs/protocol-mining/domain-manual-replay-v0.4.md
docs/protocol-mining/domain-evaluation-split-v0.4.md
docs/protocol-mining/domain-freeze-manifest-v0.4.md

outputs/fmpca-e4-v0.4/results.json
outputs/fmpca-e4-v0.4/report.md
```

v0.4 freeze 还锁定了 v7.1 `SOURCE_MANIFEST.json`、Btrfs `volumes.c`、confirmed
shrink patch fixture、全部 replay fixture、执行器与测试，避免只锁协议 JSON 而允许
证据或分析逻辑漂移。

### 15.5 最终验收

```text
69/69 full unit tests passed
11/11 v0.4 targeted tests passed
E4 = 10/10 cases passed
WDC protocol SHA-256 = 2777f35892c2172b9d7a56103abc1acfd78f3e9d0491d7d03727828b6adbd9b8
v0.1/v0.2/v0.3/v0.4 freeze mismatches = 0
python compileall = PASS
git diff --check = PASS (line-ending warnings only)
bug-specific condition count = 0
```

### 15.6 下一步与 TOC 约束

当前系统的主要约束已不再是设备协议表达能力，而是独立泛化证据。下一步顺序：

```text
1. 在 v0.4 冻结之后筛选新的 device-capacity operation family
2. 先做 applicability screening，不修改 WDC/DTC
3. 用现有 binding 运行 source witness 和 identity/closure 检查
4. 只有完整 replay 后才把该 family 纳入 held-out E5
5. 若失败，按 binding -> identity/summary -> closure -> protocol 顺序归因
6. 仅当独立设计证据证明协议缺规则时创建 Catalog v0.5
```

最有价值的候选不是另一个 `btrfs_shrink_device` 补丁，而是没有参与 v0.4 开发的
独立 add/remove/grow/replace family。跨文件系统候选只有满足完整语义同构时才可用于
WDC held-out；否则应形成新的领域协议或留作 kernel clause 证据。

## 16. 已完成：E5 v0.4 独立 held-out 筛选与验证

本轮任务理解：继续寻找一个没有参与 v0.4 规则形成的独立 operation
family，用冻结后的 WDC/DTC 语义和 binding 做 applicability screening；
只有通过对象、身份、source witness 和 replay closure 后才允许纳入
held-out。不能为了制造 held-out 指标而修改 WDC/DTC。

### 16.1 第一性原理判断

WDC/DTC 的真实对象不是“任何容量相关函数”，而是：

```text
device membership / writable / allocation eligibility
-> device capacity contribution
-> total_rw_bytes / free_chunk_space aggregate delta
-> failure rollback or release settlement
-> DTR/WDC exact operation + device identity composition
```

因此 held-out candidate 必须至少能绑定 `operation + device`，并产生
WDC 可理解的 contribution/aggregate-delta witness。确认 bug 是否真实、有
fix 或修补方向，只能证明它是好语料；不能自动证明它是 WDC/DTC 的 held-out。

### 16.2 已筛选候选

```text
Candidate: btrfs_grow_device()
Family: btrfs-device-grow
Source: linux-sources/linux-v7.1-fs/fs/btrfs/volumes.c
Decision: REJECT_BINDING_GAP

Candidate: btrfs_rm_device()
Family: btrfs-device-remove
Source: linux-sources/linux-v7.1-fs/fs/btrfs/volumes.c
Decision: REJECT_BINDING_GAP

Candidate: btrfs_dev_replace_finishing()
Family: btrfs-device-replace-finish
Source: linux-sources/linux-v7.1-fs/fs/btrfs/dev-replace.c
Decision: REJECT_OUTSIDE_WDC_DTC_FOOTPRINT

Candidate: Bug #15, btrfs reserve_chunk_space()
Family: btrfs-chunk-metadata-reservation
Source: linux-sources/linux-v6.14-fs/fs/btrfs/block-group.c
Decision: REJECT_OUTSIDE_WDC_DTC_FOOTPRINT
```

因果链：

```text
btrfs_grow_device 绑定 operation + device，并直接增加 total_rw_bytes/free_chunk_space
-> 但当前冻结 WDC binding 不能闭合失败路径的 same-delta rollback / paired replay
-> 拒绝原因为 binding/closure gap，不是 WDC 规则缺失

btrfs_rm_device 本地闭合 topology membership undo
-> capacity detachment 委托给 btrfs_shrink_device(device, 0)
-> 当前 E5 选择的 operation root 内没有直接 aggregate contribution witness
-> 需要 interprocedural WDC summary 后再评估，当前不能纳入 held-out

btrfs_dev_replace_finishing 替换 source/target device identity
-> target 继承 devid/uuid/total_bytes/bytes_used，source 被移除
-> 净 capacity contribution 预期不变
-> 语义对象是 topology/identity substitution，不是 WDC aggregate delta
-> 不能作为 WDC/DTC held-out

reserve_chunk_space 发布/排队新的 chunk/block group
-> zoned activation 返回正数 success
-> 正数 success 被复用为后续 reservation 条件
-> chunk_block_rsv_add 被跳过
-> 失败对象是 chunk publication / metadata reservation completion
-> anchor 是 block_group + transaction，不是 device
-> WDC binding 无法闭合 device eligibility / contribution / aggregate delta
-> DTC 无法闭合 shared operation + device identity
-> #15 是真实 confirmed bug，但不是 WDC/DTC held-out family
```

### 16.3 已交付工件

```text
configs/evaluation/e5-v0.4-heldout-screening.json
configs/freeze/heldout-semantic-freeze-e5-v0.4.json
docs/protocol-mining/e5-heldout-screening-v0.4.md
src/fmpca/heldout_v4.py
tests/test_v4_heldout_screening.py
outputs/fmpca-e5-v0.4-heldout-screening/results.json
outputs/fmpca-e5-v0.4-heldout-screening/report.md
```

README 已补充 E5 运行命令。E5 runner 会验证 v0.4 freeze、使用现有
WDC binding 做 source witness，并按以下约束筛选：

```text
independent_from_development
target_semantic_footprint_closed
target_identity_closed
source_witness_closed_under_existing_binding
closure_closed_for_replay
```

### 16.4 验证结果

```text
E5 total_candidates = 4
E5 eligible_candidate_count = 0
E5 rejected_candidate_count = 4
held_out_operation_families = []
protocol_acceptance_modifications = 0
checker_modifications_after_freeze = 0
bug_specific_condition_count = 0
targeted E5 tests = 5/5 passed
full unit tests after E5+CMRC = 79/79 passed
```

### 16.5 当前 TOC 约束与推荐下一步

当前主约束不是 WDC/DTC 表达能力，而是缺少真正同构的、post-freeze 的
device-capacity held-out family。#15 暴露的是另一个潜在协议：

```text
ChunkMetadataReservationCompletion / CompanionMetadataCompletion
```

本轮已经同时执行两条线：

```text
1. WDC/DTC 线：grow/remove/replace-finish 已筛选并版本化；仍无 held-out family。
2. 协议目录线：#15 已启动为 ChunkMetadataReservationCompletion v0.5 candidate；
   candidate_ready=true，但 freeze_eligible=false。
3. 后续仍按 binding -> identity/summary -> closure -> protocol 顺序归因；
   只有前三层都闭合且协议仍失败，才创建 Catalog v0.5。
```

## 17. 已完成：ChunkMetadataReservationCompletion v0.5 candidate

### 17.1 任务本质

这次不要把 #15 塞进 WDC/DTC。第一性原理判断如下：

```text
WDC/DTC 的对象 = device capacity contribution
#15 的对象 = chunk item publication + transaction chunk metadata reservation
```

真正约束不是 “Bug 是否真实、有无 fix”。#15 已经是真实 confirmed bug，且有
patch/review 证据。真正约束是：

```text
是否有第二个独立 normal/fixed/sibling family
-> 如果没有，协议可以成为 executable candidate
-> 但不能冻结进 Protocol Catalog
```

### 17.2 已实现语义候选

```text
ProtocolId: fmpca.chunk_metadata_reservation_completion
Version: 0.5.0-candidate
核心对象:
    chunk_item_publication
    chunk_block_reservation
    trans->chunk_bytes_reserved
    btrfs_zoned_activate_one_bg success domain
    btrfs_trans_release_chunk_metadata settlement

核心规则:
    CMRC-I1  reservation success-domain predicate 必须兼容 helper success domain
    CMRC-I2  source footprint 必须含 chunk publication + reservation accounting
    CMRC-I3  TransactionCommit 前 reservation.completed 必须为 true
    CMRC-O1  ChunkItemPublication 激活 BEFORE_COMMIT 的 MUST_DISCHARGE obligation
```

### 17.3 已交付工件

```text
configs/protocols/chunk-metadata-reservation-completion-v0.5-candidate.json
configs/bindings/chunk-metadata-reservation-completion-v0.5-candidate.json
configs/evaluation/cmrc-v0.5-readiness.json

src/fmpca/frontend_chunk.py
src/fmpca/chunk_candidate.py

tests/fixtures/events/cmrc-bug-v0.5.json
tests/fixtures/events/cmrc-fixed-v0.5.json
tests/fixtures/events/cmrc-normal-v0.5.json
tests/fixtures/events/cmrc-unknown-v0.5.json
tests/test_chunk_metadata_reservation_candidate.py

docs/protocol-mining/chunk-metadata-reservation-completion-v0.5-candidate.md
docs/protocol-mining/chunk-reservation-source-evidence-v0.5.md

outputs/fmpca-cmrc-v0.5-candidate-readiness/results.json
outputs/fmpca-cmrc-v0.5-candidate-readiness/report.md
```

### 17.4 Source witness 结论

```text
reserve_chunk_space()
-> btrfs_chunk_alloc_add_chunk_item() 可发布/排队 chunk item
-> btrfs_zoned_activate_one_bg() 可返回 1 表示成功激活
-> caller 只把 ret < 0 当失败
-> 后续 btrfs_block_rsv_add() 却被 if (!ret) 控制
-> ret == 1 时 reservation 被跳过
-> trans->chunk_bytes_reserved 不增加
-> BEFORE_COMMIT reservation.completed 不能闭合
```

正常 settlement 证据：

```text
btrfs_trans_release_chunk_metadata()
-> if (!trans->chunk_bytes_reserved) return
-> btrfs_block_rsv_release(... trans->chunk_bytes_reserved ...)
-> trans->chunk_bytes_reserved = 0
```

### 17.5 验证结果

```text
CMRC protocol DSL validation = PASS
CMRC targeted tests = 5/5 passed
CMRC replay = 4/4 passed
candidate_ready = true
freeze_eligible = false
failed_candidate_gates = []
failed_freeze_gates =
    second_family_source_witness_closed
    second_independent_family_available
bug_specific_condition_count = 0
full unit tests after E5+CMRC = 79/79 passed
git diff --check = PASS (line-ending warnings only)
```

### 17.6 推荐下一步

当前主约束已经非常窄：

```text
WDC/DTC: 需要 interprocedural summary 才能重新评估 btrfs_rm_device/remove；
         grow 需要 fixed/negative/paired replay 才可能成为 held-out；
         replace-finish 更像 DeviceIdentitySubstitution，不建议强塞 WDC。

CMRC:    优先找第二个独立 chunk-tree metadata publication/reservation family。
         候选方向是 remove chunk、device item update、system chunk relocation，
         但必须满足 “发布/更新 chunk-tree metadata + transaction reservation
         + release settlement + fixed/normal sibling” 同时闭合。
```

## 18. 已完成：ChunkMetadataReservationCompletion v0.5 窄冻结

### 18.1 当前事实

CMRC 不再是“只到 candidate”的中间态，而是已经收口为 v0.5
窄冻结工件：

```text
protocol_version = 0.5.0
freeze_id = fmpca-domain-semantic-freeze-v0.5
evaluation_id = fmpca-cmrc-v0.5-freeze-readiness
candidate_ready = true
freeze_eligible = true
operation_family_count = 2
replay = 5/5
second_family_screening = 1/1
```

冻结的第二个独立 family 是：

```text
btrfs_grow_device()
-> btrfs_reserve_chunk_metadata()
-> btrfs_update_device()
-> btrfs_trans_release_chunk_metadata()
```

它和 `reserve_chunk_space()` 的关系不是“同一 bug 的重复复述”，而是
同一类 chunk-tree metadata publication / reservation / release lifecycle
在另一个独立 operation family 中再次闭合。

### 18.2 已交付工件

```text
configs/protocols/chunk-metadata-reservation-completion-v0.5.json
configs/bindings/chunk-metadata-reservation-completion-v0.5.json
configs/evaluation/cmrc-v0.5-readiness.json
configs/freeze/domain-semantic-freeze-v0.5.json

docs/protocol-mining/chunk-metadata-reservation-completion-v0.5.md
docs/protocol-mining/chunk-reservation-source-evidence-v0.5.md
docs/protocol-mining/domain-protocol-catalog-v0.5.md
docs/protocol-mining/domain-traceability-matrix-v0.5.md
docs/protocol-mining/domain-manual-replay-v0.5.md
docs/protocol-mining/domain-evaluation-split-v0.5.md
docs/protocol-mining/domain-freeze-manifest-v0.5.md

src/fmpca/chunk_candidate.py
src/fmpca/frontend_chunk.py
tests/test_chunk_metadata_reservation_candidate.py
tests/fixtures/events/cmrc-*.json
docs/cases/bug-15-btrfs-chunk-reservation.md
docs/corpus/confirmed-bugs-source.md
docs/corpus/confirmed-metadata-bugs.md
linux-sources/linux-v6.14-fs/SOURCE_MANIFEST.json
linux-sources/linux-v6.14-fs/fs/btrfs/block-group.c
linux-sources/linux-v6.14-fs/fs/btrfs/zoned.c
linux-sources/linux-v6.14-fs/fs/btrfs/transaction.c
linux-sources/linux-v7.1-fs/SOURCE_MANIFEST.json
linux-sources/linux-v7.1-fs/fs/btrfs/volumes.c
```

### 18.3 验证结果

```text
CMRC freeze readiness = PASS
CMRC replay = 5/5
CMRC second-family screening = 1/1
candidate_ready = true
freeze_eligible = true
bug_specific_condition_count = 0
full unit tests = 80/80 passed
git diff --check = PASS (line-ending warnings only)
```

### 18.4 现在的约束与推荐下一步

当前主要约束已经后移：不是 CMRC 能否冻结，而是冻结之后有没有真正
post-freeze 的 held-out operation family。TOC 决策如下：

```text
WDC/DTC 线：已冻结，不该再把 #15 塞回 device-capacity 目录。
CMRC 线：已冻结，不应再把它当 candidate 或用旧冻结口径描述。
下一步主线：建立 E6 post-v0.5 CMRC held-out screening。
```

E6 的准入条件应固定为：

```text
1. 不修改 CMRC v0.5 protocol / binding / acceptance formula
2. 候选 family 必须独立于 reserve_chunk_space 和 btrfs_grow_device
3. 必须闭合 chunk-tree metadata update + transaction reservation + release settlement
4. 必须有 normal/fixed/safe/unknown replay，不能只靠单例 bug
5. 若失败，按 binding -> identity/summary -> closure -> protocol 顺序归因
```

候选方向可以先筛：

```text
remove_chunk_item / chunk deletion
system chunk relocation
其他 chunk-tree item update family
```

如果 E6 暂时找不到合格 family，再切回 WDC/DTC 线实现 interprocedural
summary，用来重新评估 `btrfs_rm_device()` 的 capacity detachment 与
release settlement。

## 19. 已完成：E6 post-v0.5 CMRC held-out screening

### 19.1 本轮任务理解

用户问“继续按你的想法看看什么时候能完整地实现”。这里的“完整”不能理解为
无限扩大协议目录，而应按第一性原理拆成三个层级：

```text
语义闭合：协议、binding、source witness、replay、proof closure 全闭合
冻结闭合：机器 hash 锁住协议/证据/runner/test
泛化闭合：冻结后 held-out family 不改协议也能通过
```

CMRC 在 v0.5 已经完成前两层。本轮 E6 继续验证第三层。

### 19.2 TOC 判断

瓶颈不是“再找一个和 #15 相似的地方”，而是：

```text
post-freeze family 必须独立于：
    btrfs-chunk-metadata-reservation
    btrfs-device-item-update

同时还必须闭合：
    chunk-tree metadata update
    transaction chunk metadata reservation
    btrfs_trans_release_chunk_metadata settlement
    normal/fixed/negative/unknown replay
```

因此选择 `btrfs_remove_chunk()`，不选择 `btrfs_add_dev_item()`：

```text
btrfs_remove_chunk()
-> check_system_chunk(trans, map->type)
-> remove_chunk_item(trans, map, chunk_offset)
-> btrfs_update_device(...) / btrfs_free_chunk(...)
-> btrfs_trans_release_chunk_metadata(trans)
-> TransactionCommit
```

`btrfs_add_dev_item()` 虽然也有 reservation / insert / release 形状，但属于
已用于 v0.5 freeze 的 `btrfs-device-item-update` 邻近 family，因此在 E6 中
按 `REJECT_NOT_INDEPENDENT` 处理。

### 19.3 已交付工件

```text
configs/evaluation/e6-v0.5-heldout-screening.json
configs/freeze/heldout-semantic-freeze-e6-v0.5.json
docs/protocol-mining/e6-cmrc-heldout-screening-v0.5.md
src/fmpca/heldout_cmrc_v5.py
tests/test_heldout_cmrc_v5.py

tests/fixtures/events/cmrc-remove-chunk-heldout-normal-v0.5.json
tests/fixtures/events/cmrc-remove-chunk-heldout-fixed-v0.5.json
tests/fixtures/events/cmrc-remove-chunk-heldout-negative-v0.5.json
tests/fixtures/events/cmrc-remove-chunk-heldout-unknown-v0.5.json

outputs/fmpca-e6-v0.5-heldout-screening/results.json
outputs/fmpca-e6-v0.5-heldout-screening/report.md
```

### 19.4 当前结果

```text
E6 screened candidates = 2
E6 eligible held-out families = 1
E6 held_out_operation_families = [btrfs-chunk-item-removal]
E6 rejected family = btrfs-device-item-update / REJECT_NOT_INDEPENDENT
E6 replay = 4/4
protocol_acceptance_modifications = 0
checker_modifications_after_freeze = 0
bug_specific_condition_count = 0
full unit tests after E6 = 82/82 passed
git diff --check = PASS (line-ending warnings only)
```

这意味着 CMRC 目前已经达到：

```text
v0.5 narrow freeze = complete
post-freeze held-out validation = complete for one independent Btrfs family
cross-filesystem generalization = not complete / not claimed
```

### 19.5 什么时候算“完整实现”

如果论文/项目目标是“一个可执行、可冻结、带 held-out 的 Btrfs metadata
protocol analyzer”，那么 CMRC 这条线现在可以算完整：协议、binding、证据、
replay、freeze、held-out 都已经闭合。

如果目标是“跨文件系统的一般 metadata protocol analyzer”，还不能说完整。下一步
必须做跨 FS applicability，而不是继续在 Btrfs 内部复制相似 family：

```text
1. 建立 E7 cross-filesystem CMRC applicability screen
2. 先找是否存在同构对象：
   chunk-tree-like metadata update
   transaction-scoped reservation accounting
   release settlement
   commit deadline
3. 若 ext4/XFS/F2FS 没有同构对象，明确记录为 non-applicable，
   不要为了跨 FS 指标硬映射
4. 若找到同构对象，再创建 source binding adapter；
   若 binding 无法闭合，归因为 binding/identity/summary gap，
   不直接改 CMRC
```

替代路线：回到 WDC/DTC，实现 interprocedural summary，重评
`btrfs_rm_device()` 的 delegated capacity detachment。优先级低于 E7，除非
目标从 CMRC 泛化改回 device-capacity 泛化。

> 注意：以上“跨 FS 再找一个类似 CMRC 的 Btrfs 路线”已经被第 20 节替代。
> 现在主线改为“分层协议目录 + 先做真实语义对应，再决定 common / family / specific”。

## 20. 下一阶段方案：分层协议目录（Common + FS-specific）

### 20.1 先把问题说透

我们现在真正要解决的，不是“能不能把更多 bug 名字抽成一个更大的通用规格”，而是：

1. 这个语义对象是否真的存在跨文件系统对应物
2. 这个对象之间的关系是否同构
3. 删除、恢复、提交、暴露这几个生命周期节点是否一致
4. 责任主体和截止点是否能闭合 replay / proof / source binding

如果这四件事不成立，继续抽象只会制造一个更大的壳，不会制造一个可验证的协议。

### 20.2 分层 taxonomy

后续所有协议先分四层：

```text
COMMON
FS_FAMILY
FS_SPECIFIC
NARROW_FREEZE
```

- `COMMON`：跨文件系统可复用，且对象、关系、生命周期、权限、截止点都能一一对应。
- `FS_FAMILY`：只在少数实现族中成立，但内部语义稳定，允许 family-level freeze。
- `FS_SPECIFIC`：单文件系统闭包，优先保真，不强行泛化。
- `NARROW_FREEZE`：只冻结当前语义与回放闭环，不宣称跨 FS 适用。

### 20.3 common 协议的最低门槛

一个协议只有在下面五项都能对应时，才允许进入 common 候选：

```text
Object
Relation
Lifecycle
Authority
Deadline
```

判定顺序固定为：

```text
object correspondence
-> relation/authority correspondence
-> identity/epoch correspondence
-> source binding correspondence
-> replay/proof closure
-> protocol rule
```

意思很直接：先证明“是不是同一个语义对象”，再看“对象之间的边是否一致”，最后才谈 identity、binding、proof。顺序一旦倒过来，就很容易把格式统一误判成语义统一。

### 20.4 当前 Btrfs 协议的保守分类

当前已冻结或在用的协议，先保守归类如下：

- `CMRC`：Btrfs `FS_SPECIFIC`
- `WDC`：Btrfs `FS_SPECIFIC`
- `DTC`：Btrfs `FS_SPECIFIC`
- `DSSA`：Btrfs `FS_SPECIFIC`，但边界保留 narrow freeze 属性
- `RRAS`：Btrfs `FS_SPECIFIC`，同样保留 narrow freeze 属性
- `DTR`：不能因为名字像 device transfer / transition 就自动归 common，必须重新做跨 FS 对应
- `RAS`：同上，不能直接按命名迁移

结论：名字相似不等于对象相同，字段相似不等于关系相同，回放相似也不等于责任相同。

### 20.5 第一条 common 主线：OrphanInodeDeletionSettlement

推荐把 `OrphanInodeDeletionSettlement`（OIDS）作为第一条 common 主线，而不是继续追 CMRC。原因是 OIDS 更像“跨 FS 都存在的语义骨架”：孤儿 inode、引用清零、删除责任、恢复可见性、事务/日志截止点，这些概念更容易找到真实对应物。

OIDS 的 canonical roles：

```text
operation
inode
namespace_entry
orphan_registry
transaction_or_journal
deletion_authority
```

关键关系：

```text
inode.namespace_attached
inode.last_link_removed
inode.cleanup_required
orphan_registry.records_inode
deletion_authority.accepted
inode.terminally_deleted
```

截止点：

```text
BEFORE_COMMIT
BEFORE_RECOVERY_EXPOSURE
BEFORE_ORPHAN_REGISTRY_REMOVAL
```

这里要特别保留一条规则：canonical `orphan_registry` 允许映射到 ext4 orphan 机制、XFS unlinked 机制、Btrfs orphan item，也允许 `NON_APPLICABLE`。不要强行把字段对齐成“同一张表”，那会把真正的语义差异抹平。

### 20.6 实现步骤

#### Phase 0：先做 taxonomy

先把“协议属于哪一层”变成可执行规则，而不是口头判断。

交付物：

```text
configs/catalog/protocol-scope-taxonomy-v0.1.json
docs/protocol-mining/protocol-scope-taxonomy-v0.1.md
src/fmpca/scope.py
tests/test_protocol_scope_taxonomy.py
```

这里要定义清楚：

- common / family / specific / narrow 的区别
- 协议升级到 common 的准入条件
- non-applicable 的记录方式
- 不能把“暂时没找到对应物”误写成“已经是 common”

#### Phase 1：为 OIDS 建证据包和对应矩阵

先对 Btrfs、ext4、XFS 各自抽取语义 dossier，再做 correspondence matrix。

交付物：

```text
docs/crossfs/orphan-inode/btrfs.md
docs/crossfs/orphan-inode/ext4.md
docs/crossfs/orphan-inode/xfs.md
docs/crossfs/orphan-inode/correspondence-matrix.md
```

每个 dossier 至少要回答四个问题：

1. 这个 FS 中谁是 `inode`
2. 谁承担 `orphan_registry` 的职责
3. 删除责任在什么时候转移
4. 何时允许对外可见为“终态已清理”

#### Phase 2：定义 canonical DSL + per-FS adapter

先写 canonical protocol，再写 FS 绑定，最后才谈冻结。

交付物：

```text
configs/protocols/common/orphan-inode-deletion-settlement-v0.1-candidate.json
configs/bindings/common/orphan-inode-btrfs-v0.1.json
configs/bindings/common/orphan-inode-ext4-v0.1.json
configs/bindings/common/orphan-inode-xfs-v0.1.json
src/fmpca/frontend_orphan_common.py
```

规则：

- canonical DSL 只描述语义，不绑定某个 FS 的字段名
- adapter 只做映射，不重写语义
- 如果某个 adapter 无法闭合，就返回 `NON_APPLICABLE`
- 不允许用“补一个字段”掩盖“对应对象缺失”

#### Phase 3：先做 Btrfs + ext4 的 development / validation

先不要一口气拉满三家，先让两家真正闭环。

验证要求：

- normal / fixed / safe / unknown replay 都要有
- 必须有独立 source witness
- 必须有 identity / authority / deadline 的可追踪映射
- 必须能区分 negative / fixed / unknown

如果 Btrfs 和 ext4 都成立，才允许把协议推进到 `COMMON` 候选冻结。

#### Phase 4：冻结 common v0.1

冻结时要把下面三件事锁死：

```text
protocol definition
per-FS binding
test corpus / replay fixture
```

冻结标准：

- 至少 2 个文件系统成立
- 每个 FS 都有独立 operation family
- source witness 能闭合
- replay 能闭合
- proof closure 能闭合

#### Phase 5：再做 XFS held-out applicability

XFS 不是“顺手再试一下”，而是 common 是否真的成立的第三道门。

两种结果都可以接受：

- `COMMON_HELDOUT_VALIDATED`：XFS 通过，不改协议
- `NON_APPLICABLE`：XFS 不同构，明确记录原因，不硬凑 common

如果 XFS 不能与 canonical roles 做稳定对应，就不要继续把它纳入 common；把结果如实写成 family / specific 边界，比虚假的统一更有价值。

#### Phase 6：再扩展下一个候选

OIDS 冻结后，再考虑下面两类：

- `DirectoryEntryRenameAtomicity`
- `LinkCountReferenceSettlement`

最后才考虑 extent / block ownership 一类更复杂的候选，因为它们更容易在关系层上分叉。

### 20.7 验收门槛

#### common candidate ready

- DSL 已定义
- bindings 已定义
- source witness 已定义
- 至少一个 development FS replay 闭合
- negative / fixed / unknown 可区分

#### common freeze ready

- 至少两个 FS 成立
- object / relation / lifecycle / authority / deadline 全部对应
- protocol hash、binding hash、test hash 全部锁定

#### common held-out validated

- 第三个 FS 通过 post-freeze 验证
- 不需要改协议
- 不需要改 binding
- 不需要放宽判定条件

#### non-applicable

- 对应对象不存在
- 对应关系不闭合
- 生命周期不一致
- 权限 / 截止点不可对齐

### 20.8 里程碑

```text
M1: Btrfs CMRC freeze + held-out 已完成
M2: taxonomy + OIDS 在 Btrfs/ext4 上完成语义闭合
M3: 至少一个 common / family 冻结
M4: XFS held-out 通过，或被严格判定 non-applicable
M5: 至少 1 个 COMMON_HELDOUT_VALIDATED 协议 + 若干 FS-specific 协议
```

### 20.9 当前最推荐的下一步

现在不建议继续追 E7 “跨 FS 的 CMRC applicability”。更稳的主线是：

1. 先把协议分层 taxonomy 落地
2. 先拿 OIDS 做第一条 common 语义线
3. 同时保留 Btrfs-specific 协议作为高保真冻结资产
4. 若某个 FS 不能对应，就诚实写 `NON_APPLICABLE`

这条路的本质是：先把“对象真的一致”证明出来，再把协议推广出去。反过来做，得到的只是更大的噪声容器。
