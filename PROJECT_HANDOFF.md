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
E2：候选资格门禁完成；0 个 v0.2 held-out family，1 个 confirmed v0.3 candidate，Git artifacts verified=2
v0.3 drafts：RelocationRootAttachmentSettlement 与 DeviceShrinkSpaceAccounting 已实现为未冻结协议和独立 replay；前者 origin/normal source chain 已闭合，后者 patch provenance 与四类语义路径已闭合
runtime relocation merge 的 Bug 与 accepted fix 均已由 commit、blob、KASAN 报告和 repair slice 证实；它未纳入 v0.2 只因为 operation lifecycle 不在冻结 RAS 适用域，不是因为缺少 fix
单元与集成测试：58/58 passed
Bug-specific condition count：0
Held-out checker modifications：0
Protocol/AcceptP modifications after E2 candidate reveal：0
Membership 真实案例资格审查：已完成，无案例通过
Membership 合成语义 fixture：已就绪，不属于论文证据
当前主任务：为两个 v0.3 singleton candidate 补充独立设计/正常源码证据；不把同一 operation family 的补丁计为泛化样本
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
| V0.3-DRAFT | 实现 `RelocationRootAttachmentSettlement` 草案、独立 adapter 和 replay | `configs/protocols/relocation-root-attachment-settlement-v0.3-draft.json`、`docs/protocol-mining/relocation-root-attachment-settlement-v0.3-draft.md` |
| V0.3-DRAFT-2 | 实现 `DeviceShrinkSpaceAccounting` 草案、patch provenance 和四类语义 replay | `configs/protocols/device-shrink-space-accounting-v0.3-draft.json`、`docs/protocol-mining/device-shrink-space-accounting-v0.3-draft.md` |

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

v0.3 draft additionally delivers:

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
```

DeviceShrinkSpaceAccounting v0.3 draft additionally delivers:

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
`RelocationRootAttachmentSettlement` v0.3 candidate。因此 E2 的
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
1. RRAS v0.3 只有一个 runtime relocation merge family，无法冻结为泛化协议
2. DSSA v0.3 只有一个 `btrfs_shrink_device` family，独立设计/正常源码验证仍缺失
3. RAS 与 DTR 都缺少同一 frontend 下的本地 fixed-source differential
4. 两个冻结协议各只有一个独立 operation family，尚无诚实 held-out 泛化证据
5. regex frontend 对宏、别名、路径和调用关系的结构恢复能力有限
6. conformance 所需的全路径、alias、escape closure 难于规模化闭合
7. capability-class baseline 不能替代外部工具的实证比较
8. provenance、环境和运行命令尚未形成独立复现实验包
```

TOC 决策规则：当前瓶颈是领域适用域与独立证据的同时闭合。runtime relocation
merge 的真实 Bug/fix 不因“有 fix”自动成为 RAS v0.2 held-out；当前已形成
未冻结 v0.3 draft。RRAS 的 selected origin/normal chain 已闭合，但 readiness gate
因缺少 independent validation family 明确失败；DSSA 已完成 confirmed patch
差分和语义 replay，但仍缺独立设计/正常源码验证。后续优先补充独立 operation
family；同 family 的额外补丁只作 validation，不改变 family count。
没有新规范证据时不扩写 AcceptP、不把 #15 singleton 纳入 Catalog，也不以 E0/E1
指标宣称跨文件系统泛化。

已验证且后续不得丢失的内核回归门禁：

```text
58/58 tests passed
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
