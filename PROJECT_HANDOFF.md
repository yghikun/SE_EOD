# FMPCA Project Handoff

Updated: 2026-08-02

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
单元与集成测试：132/132 passed
Bug-specific condition count：0
Held-out checker modifications：0
Protocol/AcceptP modifications after E2 candidate reveal：0
Membership 真实案例资格审查：已完成，无案例通过
Membership 合成语义 fixture：已就绪，不属于论文证据
当前状态：v0.3 窄冻结已完成；独立 operation family 仍是泛化门槛，不再是窄冻结门槛；DSSA 的 Btrfs 设计/正常路径证据和跨文件系统筛选已记录
CMRC v0.5 窄冻结与 E6 post-freeze held-out：已完成；跨文件系统泛化不宣称
Protocol Scope Taxonomy v0.1：已落地为可执行规则；当前没有协议被登记为 COMMON
Phase 1 OIDS：已完成；Btrfs/ext4 具备 Phase 2 语义基础，XFS 已作为 pre-freeze screening 记录
Phase 2 OIDS：已完成；canonical candidate、Btrfs/ext4 binding、真实源码 witness 与 replay 已落地
Phase 3 OIDS：已完成；source composition 与 readiness 已落地，common freeze 被 all-path proof closure 单一 gate 阻断
Phase 4 OIDS：已完成；Btrfs all-path closure 成立，ext4 error contracts 转入细化
Phase 5 OIDS：已完成；ext4 registration/settlement failstop closure 成立，recovery flush contract 与 ERRORS_CONT 反例待关闭
Phase 6 OIDS：已完成；ext4 failstop profile 全部闭合，ERRORS_CONT 的 OIDS-O1/O2/O3 negative witnesses 全部闭合，universal/common freeze 被有效配置边界否定
Phase 7 OIDS：已完成；显式冻结 ext4 + non-continuing failstop 的 FS_SPECIFIC/NARROW_FREEZE scope，ERRORS_CONT 已登记为排除配置，未生成 COMMON 或 blind held-out 声明
当前主线：Phase 8，选择并锁定真正未揭示的独立 filesystem family，执行 post-scope source/replay/proof validation
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

## 21. 已完成：Protocol Scope Taxonomy v0.1

### 21.1 本轮完成内容

Phase 0 已经从方案变成可执行工程契约。范围判定现在拆成两个正交维度：

```text
semantic_scope = COMMON | FS_FAMILY | FS_SPECIFIC
freeze_boundary = STANDARD | NARROW_FREEZE
```

`NARROW_FREEZE` 不是比 `FS_SPECIFIC` 更宽或更窄的语义适用层级，而是冻结边界限定。它可以限定当前证据闭合到哪里，但不能产生跨文件系统声明。

机器判定顺序固定为：

```text
object
-> relation / authority
-> identity / epoch
-> source binding
-> replay / proof closure
-> protocol rule
```

### 21.2 已交付工件

```text
configs/catalog/protocol-scope-taxonomy-v0.1.json
docs/protocol-mining/protocol-scope-taxonomy-v0.1.md
src/fmpca/scope.py
tests/test_protocol_scope_taxonomy.py
```

`src/fmpca/scope.py` 已支持：

- taxonomy schema 与当前协议登记校验；
- `FS_SPECIFIC`、`FS_FAMILY`、`COMMON` 声明门槛；
- common candidate、common freeze、common held-out 三阶段 readiness；
- object / relation / lifecycle / authority / deadline 五维闭合；
- `APPLICABLE`、`NON_APPLICABLE`、`UNRESOLVED` 严格区分；
- CLI 列出当前范围登记或评估新的 scope declaration。

声明规则已经机器化：

```text
FS_SPECIFIC:
    至少一个 APPLICABLE 文件系统

FS_FAMILY:
    必须声明 family identity
    至少两个适用成员
    每个成员必须属于同一个已声明 family

COMMON:
    common freeze gates 全部闭合后才允许声明
```

`NON_APPLICABLE` 必须给出受控原因码和证据说明；“暂时没找到对应物”只能记为 `UNRESOLVED`，不能计入晋级证据，也不能伪装成已经证明不适用。

### 21.3 当前协议的保守登记

当前 registry 没有任何 `COMMON` 声明：

| 工件 | semantic scope | freeze boundary | 跨 FS 状态 |
|---|---|---|---|
| CMRC | `FS_SPECIFIC` | `NARROW_FREEZE` | `UNRESOLVED` |
| WDC | `FS_SPECIFIC` | `STANDARD` | `UNRESOLVED` |
| DTC composition | `FS_SPECIFIC` | `STANDARD` | `UNRESOLVED` |
| DTR | `FS_SPECIFIC` | `STANDARD` | `UNRESOLVED` |
| DSSA | `FS_SPECIFIC` | `NARROW_FREEZE` | `UNRESOLVED` |
| RRAS | `FS_SPECIFIC` | `NARROW_FREEZE` | `UNRESOLVED` |
| RAS | `FS_SPECIFIC` | `STANDARD` | `UNRESOLVED` |

这意味着已有 Btrfs 冻结资产继续保留，不因 taxonomy 引入而被重写；任何后续 common 晋级必须重新提供对象、关系、生命周期、权限和截止点证据。

### 21.4 验证结果

```text
taxonomy 定向测试 = 8/8 passed
full unit/integration tests = 90/90 passed
scope CLI current registry validation = PASS
python compileall = PASS
git diff --check = PASS
```

新增测试覆盖：

- 当前目录没有隐式 common 声明；
- 单一 development FS 只能达到 candidate，不能达到 common freeze；
- 两个独立 FS 且五维对应闭合时才能冻结 common；
- 任一 deadline 等对应缺口会阻断 common；
- `FS_FAMILY` 必须具有两个同 family 成员；
- `NON_APPLICABLE` 必须携带原因与证据；
- held-out 只有在第三个 FS 且冻结后零语义修改时才通过。

### 21.5 下一步计划：Phase 1 OIDS 跨文件系统证据包

下一步不写 canonical DSL，也不先创建 adapter。先完成以下四个证据工件：

```text
docs/crossfs/orphan-inode/btrfs.md
docs/crossfs/orphan-inode/ext4.md
docs/crossfs/orphan-inode/xfs.md
docs/crossfs/orphan-inode/correspondence-matrix.md
```

每个文件系统 dossier 必须用设计文档、源码注释、断言和正常/恢复路径回答：

1. 谁对应 canonical `inode`
2. 谁承担 `orphan_registry` 职责
3. 删除责任在何时、向谁转移
4. 何时允许对外观察为“终态已清理”

同时必须记录：

```text
source version / path / function
object and identity correspondence
relation and lifecycle timeline
transaction or journal context
deletion authority
BEFORE_COMMIT / BEFORE_RECOVERY_EXPOSURE / BEFORE_ORPHAN_REGISTRY_REMOVAL
evidence status = APPLICABLE | NON_APPLICABLE | UNRESOLVED
```

Phase 1 的验收条件是：先得到可审计的 correspondence matrix，并明确 Btrfs 与 ext4 是否真的能够闭合 OIDS 语义。只有两者对象、关系、生命周期、权限和截止点均闭合，才进入 Phase 2 canonical DSL + per-FS adapter；XFS 在这一阶段只做独立证据抽取，不提前作为 held-out 结果使用。

## 22. 已完成：OIDS Phase 1 跨文件系统证据包

### 22.1 已交付工件

```text
docs/crossfs/orphan-inode/btrfs.md
docs/crossfs/orphan-inode/ext4.md
docs/crossfs/orphan-inode/xfs.md
docs/crossfs/orphan-inode/correspondence-matrix.md
configs/evaluation/oids-phase1-evidence-v0.1.json
tests/test_oids_phase1_evidence.py
```

三份 dossier 使用同一个 checksum-verified Linux v6.14 源码快照：

```text
git_tag = v6.14
git_commit = 38fec10eb60d687e30c8c6b5420d86e8149f7557
archive_sha256 = a294b683e7b161bb0517bb32ec7ed1d2ea7603dfbabad135170ed12d00c47670
```

证据 manifest 对 11 个关键源码文件做 SHA-256 锁定，覆盖 orphan registry、namespace unlink、final eviction/free 和 recovery 调用链。

### 22.2 Phase 1 结论

```text
Btrfs applicability = APPLICABLE
ext4 applicability = APPLICABLE
XFS applicability = APPLICABLE (pre-freeze screening)

object correspondence = CLOSED
relation correspondence = CLOSED
lifecycle correspondence = CLOSED_WITH_TRANSACTIONAL_EQUIVALENCE
authority correspondence = CLOSED
deadline correspondence = CLOSED_WITH_TRANSACTIONAL_EQUIVALENCE

Btrfs/ext4 Phase 2 basis = ELIGIBLE
canonical DSL = NOT_STARTED
per-FS binding = NOT_STARTED
replay/proof closure = NOT_STARTED
COMMON claim = NOT_ALLOWED
```

三种文件系统都存在“最后链接删除后由持久 registry 承接清理责任”的语义骨架，但 registry 物理形态不同：

```text
Btrfs: per-root BTRFS_ORPHAN_ITEM_KEY
ext4: orphan-file slot 或 legacy s_last_orphan chain
XFS: AGI agi_unlinked[] bucket + inode forward link
```

不能把这些结构强行说成同一张表。Phase 1 只证明 canonical object/relation/lifecycle/authority/deadline 可以建立对应。

### 22.3 关键语义修正

ext4 的源码顺序是：

```text
ext4_orphan_del(handle)
-> ext4_mark_inode_dirty(handle)
-> ext4_free_inode(handle)
-> ext4_journal_stop(handle)
```

XFS 的 `xfs_inode_uninit()` 则在同一事务中执行 on-disk inode free 和 `xfs_iunlink_remove()`；Btrfs 在 truncate inode items 后再删除 orphan item。由此，OIDS 的共同 deadline 必须定义为：

```text
registry removal MUST NOT COMMIT unless terminal inode deletion is
already durably settled OR atomically co-settled in the same transaction
```

不能把它错误实现为所有文件系统都必须满足的 C 调用先后顺序，也不能要求
Btrfs 的删除与 orphan removal 必须属于同一事务：Btrfs 在
`btrfs_truncate_inode_items()` 后结束删除事务，再在后续事务中执行
`btrfs_orphan_del()`；ext4 和 XFS 则提供同事务原子结算证据。

### 22.4 XFS held-out 边界修正

由于 XFS 已在 Phase 1 被完整抽取并参与对应判断，后续不能把它称为严格意义上的 blind/unseen held-out。后续结果只能写成：

```text
POST_FREEZE_XFS_VALIDATED
```

或在 adapter 无法闭合时写成 `NON_APPLICABLE`。如果需要真正的 `COMMON_HELDOUT_VALIDATED`，必须使用没有参与 canonical 规则形成的额外文件系统，例如单独保留的 F2FS 评估。

### 22.5 验证结果

```text
OIDS evidence tests = 5/5 passed
full unit/integration tests = 95/95 passed
compileall = PASS
git diff --check = PASS
```

### 22.6 下一步计划：Phase 2 canonical DSL + Btrfs/ext4 adapters

下一轮实现范围固定为：

```text
configs/protocols/common/orphan-inode-deletion-settlement-v0.1-candidate.json
configs/bindings/common/orphan-inode-btrfs-v0.1.json
configs/bindings/common/orphan-inode-ext4-v0.1.json
src/fmpca/frontend_orphan_common.py
```

以及对应的 normal / fixed / negative / unknown 事件 fixture 和 replay 测试。

Phase 2 的硬约束：

1. canonical DSL 只写语义，不写 Btrfs/ext4 字段名。
2. Btrfs 与 ext4 adapter 分别映射 registry、identity、authority、transaction 和 recovery。
3. 只把 zero-link deletion 纳入 OIDS；linked truncate 记录必须排除。
4. `BEFORE_ORPHAN_REGISTRY_REMOVAL` 使用 transactional-equivalence 语义。
5. normal、fixed、negative、unknown 四类 replay 必须可区分。
6. Phase 2 完成前不把 OIDS 登记为 `COMMON`，也不冻结 XFS。

## 23. 已完成：OIDS Phase 2 canonical candidate 与 Btrfs/ext4 binding

### 23.1 已交付工件

```text
configs/protocols/common/orphan-inode-deletion-settlement-v0.1-candidate.json
configs/bindings/common/orphan-inode-btrfs-v0.1.json
configs/bindings/common/orphan-inode-ext4-v0.1.json
src/fmpca/frontend_orphan_common.py
src/fmpca/semantics_extensions.py
tests/test_oids_phase2_candidate.py
tests/fixtures/events/oids-*.json
```

DSL 新增可选且严格校验的 `deadline_events`，允许候选协议声明事件到
deadline 的映射。历史 v0.2 `semantics.py` 已保持字节级不变；新候选通过
`ProtocolDeadlineEngine` 使用协议局部 deadline，避免破坏 E1/E2 的 frozen
checker hash。

OIDS v0.1 candidate 当前定义三个义务：

```text
OIDS-O1: zero-link namespace transition commit 前 registry 必须已接受责任
OIDS-O2: registry removal 前删除必须已持久结算，或与 removal 同事务原子结算
OIDS-O3: recovery exposure 前注册的删除清理必须完成
```

`registration_transaction` 与 `settlement_transaction` 是不同角色。Btrfs
更早完成 inode-item 删除的事务不与后续 orphan-removal 事务合并身份；其
安全性由 `inode.terminal_deletion_durable` 表达。

### 23.2 真实源码 witness

Linux v6.14 源码分析结果：

| 文件系统 | registration | terminal settlement | 结论 |
|---|---|---|---|
| Btrfs | `btrfs_unlink_inode -> zero-link guard -> btrfs_orphan_add -> btrfs_end_transaction` | truncate 后的事务先结算，再执行 `btrfs_orphan_del` | `PRIOR_DURABLE_SETTLEMENT` |
| ext4 | `ext4_delete_entry -> drop_nlink -> zero-link guard -> ext4_orphan_add -> ext4_journal_stop` | `ext4_orphan_del` 与 `ext4_free_inode` 使用同一 `handle`，随后 stop | `SAME_TRANSACTION_EQUIVALENCE` |

前端严格拒绝嵌套的 Bug/case/function/line/patch 特判键。事务等价不仅检查
源码顺序，还要求 registry removal、terminal deletion 和 settlement 使用
同一个事务参数。`ext4_truncate()` 的 linked-truncate 路径不能形成
registration witness，因而不会被误选为 zero-link OIDS 实例。

### 23.3 replay 与结果

```text
oids-btrfs-fixed-live-v0.1.json       = CONFORMANT
oids-ext4-fixed-live-v0.1.json        = CONFORMANT
oids-normal-recovery-v0.1.json        = CONFORMANT
oids-negative-registration-v0.1.json = VIOLATION (OIDS-O1)
oids-negative-removal-v0.1.json       = VIOLATION (OIDS-O2)
oids-unknown-settlement-v0.1.json     = INCOMPLETE
```

这完成了 candidate 级语义区分，但还不是 `COMMON` freeze。当前真实源码
witness 证明选定函数中的结构与事务关系，尚未把 unlink、eviction/recovery
的跨操作证据自动组合成一个 all-path canonical protocol instance。

### 23.4 验证结果

```text
OIDS Phase 2 定向测试 = 8/8 passed
full unit/integration tests = 104/104 passed
historical semantics.py freeze hash = 526ebf1c1a4342fc461d5d635baefeb06c8293e48c1648e93c7020248884999b
compileall = PASS
git diff --check = PASS
```

### 23.5 下一步计划：Phase 3 source composition 与 common-freeze gate

下一轮按以下顺序执行：

1. 将 Btrfs/ext4 registration 与 settlement witness 转换为 canonical events，按
   filesystem/inode/allocation epoch 组合跨操作实例。
2. 为 normal eviction 与 recovery 两类 authority 分别生成 proof/coverage report，
   明确 selected-path closure 与 all-path closure 的边界。
3. 新增 OIDS Phase 2/3 machine-readable evaluation/readiness manifest，锁定协议、
   binding、源码和 replay hash。
4. 用 Btrfs development 与 ext4 independent validation 运行 common-freeze gate；
   任一 identity、recovery 或 all-path 缺口都保持 candidate，不晋级 `COMMON`。
5. 只有 freeze 成功后才运行已揭示的 XFS，结果只能标记
   `POST_FREEZE_XFS_VALIDATED`；真正 held-out 仍需保留额外文件系统。

## 24. 已完成：OIDS Phase 3 source composition 与 readiness gate

### 24.1 已交付工件

```text
src/fmpca/orphan_composition.py
src/fmpca/orphan_candidate.py
configs/evaluation/oids-phase3-readiness-v0.1.json
tests/test_oids_phase3_composition.py
outputs/fmpca-oids-phase3-v0.1/summary.json
outputs/fmpca-oids-phase3-v0.1/report.md
```

`frontend_orphan_common.py` 与两个 binding 同时扩展了 recovery witness：

```text
Btrfs:
    btrfs_orphan_cleanup -> iput
    btrfs_start_pre_rw_mount -> set_bit(BTRFS_FS_OPEN)

ext4:
    ext4_orphan_cleanup -> ext4_process_orphan -> iput
    ext4_orphan_cleanup -> ext4_mark_recovery_complete
```

组合器将 registration、normal eviction 或 recovery、terminal deletion、registry
removal 和 exposure 转换为 canonical events。组合身份固定为：

```text
<filesystem, inode, filesystem_mount, inode_allocation_generation>
```

registration 与 settlement 的 inode generation 或 registry identity 不一致时，
组合器直接拒绝合并，不能把 inode number reuse 误当作同一协议实例。

### 24.2 source composition 结果

| 文件系统 | role | path | selected-path closure | acceptance | all-path closure | 报告 |
|---|---|---|---|---|---|---|
| Btrfs | `DEVELOPMENT` | normal eviction | `CLOSED` | `TRUE` | `OPEN` | `INCOMPLETE` |
| Btrfs | `DEVELOPMENT` | recovery | `CLOSED` | `TRUE` | `OPEN` | `INCOMPLETE` |
| ext4 | `VALIDATION` | normal eviction | `CLOSED` | `TRUE` | `OPEN` | `INCOMPLETE` |
| ext4 | `VALIDATION` | recovery | `CLOSED` | `TRUE` | `OPEN` | `INCOMPLETE` |

这里的 `INCOMPLETE` 是刻意保留的正确结果。当前 witness 能证明选定源码路径满足
candidate acceptance，但不能证明相关函数的所有成功、失败、事务中止和重试分支
都闭合；因此没有把静态调用顺序伪装成 universal conformance。

### 24.3 machine-readable readiness

Phase 3 manifest 已哈希锁定：

- OIDS protocol、Btrfs/ext4 binding；
- deadline extension、源码前端、composition 和 readiness runner；
- Phase 3 测试与 6 个 replay fixture；
- Linux v6.14 的 Btrfs/ext4 registration、settlement、recovery/exposure 源码。

实际 gate 结果：

```text
artifact_hashes_verified = true
bug_specific_condition_count = 0
result_partition_closed = true
replay = 6/6 passed
common_candidate_ready = true
common_freeze_ready = false
cross_filesystem_claim_allowed = false
failed_freeze_gates = [proof_closure_closed_per_filesystem]
```

OIDS 已在 scope catalog 保守登记为：

```text
semantic_scope = FS_SPECIFIC
freeze_boundary = NARROW_FREEZE
cross_filesystem_status = UNRESOLVED
```

虽然 Btrfs/ext4 五维 correspondence 和 selected source witness 已闭合，但在唯一
剩余 gate 关闭之前，仍不得登记为 `COMMON`。

### 24.4 验证结果

```text
OIDS Phase 3 定向测试 = 4/4 passed
full unit/integration tests = 108/108 passed
readiness runner = candidate_ready=True, freeze_ready=False
historical semantics.py freeze hash = 526ebf1c1a4342fc461d5d635baefeb06c8293e48c1648e93c7020248884999b
compileall = PASS
git diff --check = PASS
```

### 24.5 下一步计划：Phase 4 CFG/all-path proof closure

下一轮只处理当前唯一 freeze blocker：

1. 为 Btrfs/ext4 registration 构建分支级 CFG witness，证明所有成功的 zero-link
   namespace commit 都经过 persistent registry acceptance；失败/abort 不计作 commit。
2. 为 Btrfs eviction 证明所有实际提交 orphan removal 的路径都有更早已结算的
   terminal deletion；删除失败留下 registry record 的 retry 路径必须被判为安全。
3. 为 ext4 eviction 证明 persistent `ext4_orphan_del(handle, ...)`、inode free 和
   journal stop 的 handle identity 在所有相关成功路径闭合；
   `ext4_orphan_del(NULL, ...)` 只能算 in-memory cleanup，不能证明持久结算。
4. 为两个 recovery mount path 区分成功 exposure 与错误退出，证明只有 cleanup
   完成的成功路径可到达 exposure marker。
5. 将 all-path closure 结果写回 Phase 3 readiness；只有
   `proof_closure_closed_per_filesystem=true` 后才创建 OIDS common freeze manifest。

## 25. 已完成：OIDS Phase 4 CFG/all-path proof closure

### 25.1 已交付工件

```text
src/fmpca/c_cfg.py
src/fmpca/orphan_allpath.py
configs/evaluation/oids-phase4-allpath-v0.1.json
tests/test_oids_phase4_allpath.py
outputs/fmpca-oids-phase4-v0.1/summary.json
outputs/fmpca-oids-phase4-v0.1/report.md
```

`pyproject.toml` 新增真实 C AST/CFG 依赖：

```text
tree-sitter>=0.21
tree-sitter-c>=0.23
```

CFG frontend 当前支持 compound、if/else、while/for/do、goto/label、return、
break/continue、reachable、dominators 和 call/branch 查询。常真循环只能经 `break`
离开，label 节点不再重复归属其子树调用。`__cold`、`__maybe_unused` 使用等长空格
做行号保持的轻量 normalization；剩余 parse error 和 unresolved goto 都是 hard blocker，
不能产生 closed proof。

all-path 层新增：

```text
RegistrationCFGProof
SettlementCFGProof
RecoveryCFGProof
OIDSAllPathWitness
```

每个 clause 输出 status、源码文件、函数、行号、CFG node、assumptions 和 blockers。

### 25.2 clause-level 结果

| 文件系统 | stage | clause | 结果 | 结论 |
|---|---|---|---|---|
| Btrfs | registration | `OIDS-BTRFS-R1` | `CLOSED` | zero-link 分支的 orphan registration 先于 transaction settlement |
| Btrfs | registration | `OIDS-BTRFS-R2` | `CLOSED` | 非 `-EEXIST` registration failure 被 transaction abort containment 覆盖 |
| Btrfs | settlement | `OIDS-BTRFS-S1` | `CLOSED` | terminal deletion 事务先结算，再尝试 orphan removal；removal 自身受新事务约束 |
| Btrfs | recovery | `OIDS-BTRFS-C1` | `CLOSED` | 成功 RW exposure 被成功 orphan-cleanup gate 支配 |
| ext4 | registration | `OIDS-EXT4-R1` | `BLOCKED` | caller 丢弃 `ext4_orphan_add()` 返回值，尚未关闭所有同 handle abort 分支 |
| ext4 | settlement | `OIDS-EXT4-S1` | `CLOSED` | 成功 free 分支的 orphan removal、inode free、journal stop 使用同一 handle |
| ext4 | settlement | `OIDS-EXT4-S2` | `BLOCKED` | orphan-del/mark-dirty 错误尚未证明必然阻止 removal-only commit |
| ext4 | recovery | `OIDS-EXT4-C1` | `BLOCKED` | void cleanup 的 skip/error exits 不能由 syntactic dominance 代替 outcome proof |

Btrfs registration 证据覆盖 `btrfs_unlink()` 的 true branch 和
`btrfs_orphan_add()` 的 insert/abort 分区。Btrfs eviction 的 dominance 链为：

```text
btrfs_truncate_inode_items
-> btrfs_end_transaction
-> btrfs_orphan_del
-> btrfs_end_transaction
```

Btrfs recovery 证明 `btrfs_start_pre_rw_mount()` 同时 gate `fs_root` 和 `tree_root`
cleanup；`open_ctree()` 只有 gate 成功后才能到达 `BTRFS_FS_OPEN`。

### 25.3 ext4 helper audit 与保留 blocker

已审计 `__ext4_journal_get_write_access()`、`__ext4_handle_dirty_metadata()` 和
`ext4_journal_abort_handle()`，确认 journal write-access failure 和意外的
jbd2 dirty-metadata failure 会 abort supplied handle。但该局部事实还不能覆盖：

```text
EXT4_REGISTRATION_RETURN_IGNORED
EXT4_ORPHAN_ADD_ERROR_CONTAINMENT_NOT_CLOSED
EXT4_ORPHAN_DEL_RETURN_IGNORED
EXT4_MARK_DIRTY_FAILURE_ABORT_CONTRACT_NOT_CLOSED
CFG_PARSE_ERROR:__ext4_fill_super
EXT4_VOID_CLEANUP_HAS_NO_SUCCESS_OUTCOME
EXT4_RECOVERY_SKIP_AND_ERROR_PATHS_UNPARTITIONED
```

`ext4_orphan_del(NULL, inode)` 仍只算 in-memory cleanup。`__ext4_fill_super()` 的
Tree-sitter parse error 没有被忽略；即使静态上 cleanup call 支配
`ext4_mark_recovery_complete()`，void cleanup 内部的 read-only、feature、error-FS、
orphan-get failure 等路径也不能自动解释为每个 OIDS instance 已成功恢复。

### 25.4 machine-readable gate

Phase 4 manifest 哈希锁定 CFG/proof runner、测试、taxonomy、Phase 3 manifest、
依赖声明和实际读取的 Btrfs/ext4 Linux v6.14 源文件。实际结果：

```text
artifact_hashes_verified = true
bug_specific_condition_count = 0
btrfs.proof_closure_closed = true
ext4.proof_closure_closed = false
proof_closure_closed_per_filesystem = false
common_candidate_ready = true
common_freeze_ready = false
cross_filesystem_claim_allowed = false
failed_freeze_gates = [proof_closure_closed_per_filesystem]
freeze_manifest_generated = false
```

因此本阶段没有创建 COMMON freeze manifest，也没有修改 scope taxonomy 中的
`FS_SPECIFIC / NARROW_FREEZE / UNRESOLVED` 登记。

### 25.5 验证结果

```text
OIDS Phase 4 定向测试 = 5/5 passed
full unit/integration tests = 113/113 passed
all-path runner = candidate_ready=True, freeze_ready=False, all_filesystems_closed=False
historical semantics.py freeze hash = 526ebf1c1a4342fc461d5d635baefeb06c8293e48c1648e93c7020248884999b
compileall = PASS
git diff --check = PASS
```

### 25.6 下一步计划：Phase 5 ext4 interprocedural contract refinement

1. 对 registration 建立 `ext4_orphan_add()` 全部 early return 的 guarded summary，
   继续追踪 `ext4_orphan_file_add()`、write access、inode reserve、dirty metadata、
   iloc dirty、`ext4_std_error()` 和 `ext4_journal_stop()` 的 same-handle abort/commit 结果。
2. 对 settlement 建立 `ext4_orphan_del(handle, ...)`、post-removal
   `ext4_mark_inode_dirty()`、`ext4_free_inode()` 与 journal stop 的错误分区，证明或否定
   removal-only persistent commit；继续排除 `ext4_orphan_del(NULL, ...)`。
3. 对 recovery 将 `ext4_orphan_cleanup()` 的 void control flow 拆成 per-inode
   successful dispatch、safe non-applicable skip 和 error containment；改进预处理 CFG
   建模，但任何剩余 parse error 继续阻断 closure。
4. 只有 ext4 registration、settlement、recovery 三项全部 `CLOSED` 后，才重跑
   common-freeze gate 并考虑生成 manifest；否则继续保留 candidate 状态。

## 26. 已完成：OIDS Phase 5 ext4 interprocedural contracts

### 26.1 已交付工件

```text
src/fmpca/c_cfg_extensions.py
src/fmpca/orphan_ext4_contracts.py
configs/evaluation/oids-phase5-ext4-contracts-v0.1.json
tests/test_oids_phase5_ext4_contracts.py
docs/crossfs/orphan-inode/ext4-helper-contracts-v0.1.md
outputs/fmpca-oids-phase5-v0.1/summary.json
outputs/fmpca-oids-phase5-v0.1/report.md
linux-sources/linux-v6.14-fs/PHASE5_SUPPLEMENTARY_MANIFEST.json
linux-sources/linux-v6.14-fs/fs/jbd2/transaction.c
linux-sources/linux-v6.14-fs/include/linux/jbd2.h
```

JBD2 supplementary source 来自与现有快照相同的 Linux `v6.14` tag/commit，
分别哈希锁定。原 `SOURCE_MANIFEST.json` 保持字节级不变：

```text
SOURCE_MANIFEST.json SHA-256 = 302223b94530376b980c082621ec2a9c34b05dcfb27bfa45a3adf776e669918c
```

因此没有破坏旧 CMRC/source semantic freeze。

### 26.2 Phase 5 CFG extension

Phase 4 的 `c_cfg.py` 已被 Phase 4 manifest 锁定，本阶段没有修改它。新增 extension
只处理三类 Linux C syntax：

```text
label immediately followed by preprocessor directive
kernel macro type argument: list_entry(..., struct type, ...)
return type split onto the preceding line
```

normalization 保持源码行号并写入 `normalized_attributes`。经 extension 解析后：

```text
__ext4_fill_super      parse_has_error = false
ext4_orphan_del        parse_has_error = false
ext4_reserve_inode_write parse_has_error = false
```

### 26.3 JBD2 contract 结论

Linux v6.14 的真实实现证明：

```text
jbd2_journal_abort_handle(handle):
    handle->h_aborted = 1

jbd2_journal_stop(handle):
    observes is_handle_aborted(handle)
    returns -EIO for an aborted handle
    does not call jbd2_journal_abort()
```

因此必须保持：

```text
HANDLE_ABORTED != JOURNAL_TRANSACTION_ABORTED
HANDLE_STOP_ERROR != ROLLBACK_OF_ALREADY_JOURNALED_METADATA
```

`ext4_handle_error()` 的 policy 分支则是：非 `ERRORS_CONT` 的 writable 路径设置
shutdown 并调用 `jbd2_journal_abort()`；`ERRORS_CONT` 令 `continue_fs=true`，跳过
该 journal abort 分支。

### 26.4 guarded summary 结果

| stage | summary | profile | status | 结论 |
|---|---|---|---|---|
| registration | `EXT4-RC-1` | `ALL` | `CLOSED` | no-journal/bad/already-registered 分区不需要新 registration |
| registration | `EXT4-RC-2` | `ALL` | `CLOSED` | orphan-file `-ENOSPC` 明确 fallback 到 legacy list |
| registration | `EXT4-RC-3` | failstop | `CLOSED` | 非继续策略的 registration error 由 journal abort/non-RW failstop containment 覆盖 |
| registration | `EXT4-RC-4` | `ERRORS_CONT` | `UNSAFE` | handle abort 不足以排除先前 namespace metadata commit |
| settlement | `EXT4-SC-1` | `ALL` | `CLOSED` | 成功 orphan removal、inode free、journal stop 使用同一 handle |
| settlement | `EXT4-SC-2` | failstop | `CLOSED` | post-removal error 的非继续策略阻止 removal-only commit |
| settlement | `EXT4-SC-3` | `ERRORS_CONT` | `UNSAFE` | partial registry removal 可能已 journaled，而 inode free 被跳过 |
| recovery | `EXT4-CC-1` | `ALL` | `NOT_APPLICABLE` | empty registry 没有 OIDS recovery instance |
| recovery | `EXT4-CC-2` | `ALL` | `CLOSED` | valid orphan dispatch 到 `ext4_process_orphan`/`iput` |
| recovery | `EXT4-CC-3` | failstop | `BLOCKED` | 尚未锁定 journal flush error 到 mount failure 的传播 |
| recovery | `EXT4-CC-4` | `ERRORS_CONT` | `UNSAFE` | void cleanup error 后仍不能排除 recovery completion 和 mount return |

这里的 `UNSAFE` 表示源码合约无法排除 commit/exposure，不等同于已经取得动态
violation verdict。它足以阻断 universal conformance，但还需要 fault injection 或更强
transaction witness 才能升级为具体 violation。

### 26.5 machine-readable gate

```text
artifact_hashes_verified = true
bug_specific_condition_count = 0
registration.failstop_closed = true
settlement.failstop_closed = true
recovery.failstop_closed = false
universal_all_path_closed = false
failstop_profile_closed = false
common_freeze_manifest_generated = false
```

当前精确 blockers：

```text
EXT4_ERRORS_CONT_REGISTRATION_COMMIT_NOT_EXCLUDED
EXT4_ERRORS_CONT_REMOVAL_ONLY_COMMIT_NOT_EXCLUDED
EXT4_RECOVERY_FAILSTOP_FLUSH_CONTRACT_NOT_LOCKED
EXT4_ERRORS_CONT_RECOVERY_EXPOSURE_NOT_EXCLUDED
```

Phase 5 没有修改 OIDS protocol/AcceptP、scope taxonomy 或历史 `semantics.py`，
也没有生成 COMMON freeze manifest。

### 26.6 验证结果

```text
OIDS Phase 5 定向测试 = 7/7 passed
full unit/integration tests = 120/120 passed
Phase 5 runner = universal_closed=False, failstop_closed=False
historical semantics.py freeze hash = 526ebf1c1a4342fc461d5d635baefeb06c8293e48c1648e93c7020248884999b
base SOURCE_MANIFEST hash = 302223b94530376b980c082621ec2a9c34b05dcfb27bfa45a3adf776e669918c
compileall = PASS
git diff --check = PASS
```

### 26.7 下一步计划：Phase 6 configuration boundary / negative witness

1. 补充并锁定 `jbd2_journal_flush()` 及其 aborted-journal 返回传播，验证
   `ext4_mark_recovery_complete()` error 是否支配 `__ext4_fill_super()` mount failure，
   先关闭 `EXT4_RECOVERY_FAILSTOP_FLUSH_CONTRACT_NOT_LOCKED`。
2. 为 `ERRORS_CONT` registration 与 settlement 建立 transaction-level witness，区分
   “仅静态不能排除”与“存在可提交 removal/namespace-only state”；优先使用 fault injection
   或已有 JBD2 transaction state，而不是把 `UNSAFE` 直接宣称为 violation。
3. 明确 protocol applicability 是否允许配置边界 `errors != continue`。若允许，必须在
   scope taxonomy/declaration 中显式登记，不得作为隐藏 assumption；若不允许，则 ext4
   不能用于 OIDS COMMON freeze。
4. 若 ext4 universal closure 被有效配置反例否定，转入新的独立 filesystem family
   validation；XFS 已在 freeze 前读取，只能作 `POST_FREEZE_XFS_VALIDATED`，不能伪称 blind held-out。

## 27. 已完成：OIDS Phase 6 configuration boundary / negative witness

### 27.1 已交付工件

```text
src/fmpca/orphan_phase6.py
configs/evaluation/oids-phase6-configuration-boundary-v0.1.json
tests/test_oids_phase6_configuration_boundary.py
tests/fixtures/events/oids-ext4-errors-cont-registration-v0.1.json
tests/fixtures/events/oids-ext4-errors-cont-settlement-v0.1.json
tests/fixtures/events/oids-ext4-errors-cont-recovery-v0.1.json
docs/crossfs/orphan-inode/ext4-errors-continue-boundary-v0.1.md
outputs/fmpca-oids-phase6-v0.1/summary.json
outputs/fmpca-oids-phase6-v0.1/report.md
linux-sources/linux-v6.14-fs/PHASE6_SUPPLEMENTARY_MANIFEST.json
linux-sources/linux-v6.14-fs/fs/jbd2/journal.c
linux-sources/linux-v6.14-fs/fs/jbd2/commit.c
```

新增 JBD2 源码来自与既有快照相同的 Linux `v6.14` tag/commit，并由独立
supplementary manifest 锁定。没有修改旧 `SOURCE_MANIFEST.json` 或 Phase 5
supplementary manifest：

```text
SOURCE_MANIFEST.json SHA-256 = 302223b94530376b980c082621ec2a9c34b05dcfb27bfa45a3adf776e669918c
PHASE5_SUPPLEMENTARY_MANIFEST.json SHA-256 = ed9197eb71cae4c9775c1c544d3e02d0f6438c798b9bfc086bbea67f26fd1b6f
PHASE6_SUPPLEMENTARY_MANIFEST.json SHA-256 = f7d2ea6a0c2ad6c05d2a570919968762323d39f917fff89037040e8269cd7e66
```

### 27.2 failstop recovery closure

Phase 6 锁定了以下 Linux v6.14 源码传播链：

```text
ext4_handle_error(non-ERRORS_CONT, writable)
-> jbd2_journal_abort(journal, -EIO)
-> jbd2_journal_flush() observes is_journal_aborted(journal)
-> return -EIO
-> ext4_mark_recovery_complete() returns err
-> __ext4_fill_super() goto failed_mount9
-> return err
```

因此 Phase 5 的 blocker：

```text
EXT4_RECOVERY_FAILSTOP_FLUSH_CONTRACT_NOT_LOCKED
```

已关闭。结合 Phase 5 已关闭的 registration 与 settlement，明确限定为
`ERRORS_RO_OR_FAILSTOP` 的 ext4 profile 现在三阶段均闭合：

```text
registration.failstop_closed = true
settlement.failstop_closed = true
recovery.failstop_closed = true
failstop_profile_closed = true
```

### 27.3 JBD2 transaction-level witness

本阶段不再把“handle abort 后 stop 返回错误”误解释为 rollback。源码证明：

```text
jbd2_journal_dirty_metadata
-> __jbd2_journal_file_buffer(..., BJ_Metadata)
-> transaction->t_buffers

jbd2_journal_commit_transaction
-> while (commit_transaction->t_buffers)
-> discard/refile only if is_journal_aborted(journal)
-> otherwise submit metadata and commit record
```

同时保持 Phase 5 已锁定的区别：

```text
jbd2_journal_abort_handle: handle->h_aborted = 1
jbd2_journal_stop: observes handle abort, does not call jbd2_journal_abort
HANDLE_ABORTED != JOURNAL_ABORTED
```

因此已经进入 `t_buffers` 的 namespace/orphan metadata 不会仅因 handle-local abort
自动从 transaction 中回滚。Phase 6 machine-readable witness 结果：

```text
metadata_filed_on_transaction = true
commit_reads_metadata_list = true
discard_requires_journal_abort = true
handle_abort_is_not_journal_abort = true
handle_abort_does_not_prevent_commit = true
transaction_commit.closed = true
```

### 27.4 ERRORS_CONT negative witnesses

三个 fixture 使用 `ProtocolDeadlineEngine` 执行协议声明的自定义 deadline mapping，
而不是修改已冻结的 `semantics.py`。必须使用该 extension；直接使用历史
`ProtocolEngine` 不会消费 candidate protocol 的 `deadline_events`。

| stage | source-level reachable outcome | replay result | 规则 |
|---|---|---|---|
| registration | directory metadata 可进入 transaction，而 orphan registration 因 inode-location `-ENOMEM` 缺失 | `VIOLATION_UNDER_LOADED_SPEC` | `OIDS-O1` |
| settlement | orphan-file removal metadata 可进入 transaction，post-removal mark-dirty failure 跳过 inode free | `VIOLATION_UNDER_LOADED_SPEC` | `OIDS-O2` |
| recovery | orphan-get error 退出 void cleanup，recovery completion 与 mount exposure 仍可达 | `VIOLATION_UNDER_LOADED_SPEC` | `OIDS-O3` |

registration/recovery 的最终报告还会同时包含 `ACCEPTANCE@AT_SETTLEMENT`；对应的
协议义务规则 `OIDS-O1`/`OIDS-O3` 已在各自 deadline 固化，不能只引用 acceptance
作为反例结论。settlement 精确命中 `OIDS-O2`。

这些是闭合的 source-plus-semantic negative witnesses，不是 fault-injection 测量，
也不宣称每一次底层错误都必然到达该 outcome。它们证明的是对应可行路径足以否定
unqualified universal conformance。

### 27.5 configuration scope decision

本阶段的机器可读决定为：

```text
configuration_scope_decision = VALID_CONFIGURATION_BOUNDARY
failstop_profile_closed = true
errors_continue_negative_witness_closed = true
universal_all_path_closed = false
common_freeze_manifest_generated = false
```

`ERRORS_CONT` 是 ext4 的有效配置，不能在无条件的 OIDS COMMON/ext4 validation
声明里被静默排除。当前只允许声称限定的 non-continuing failstop profile 已闭合；
不允许据此声称 ext4 universal closure，也没有生成 COMMON freeze manifest。

若下一阶段选择排除 `ERRORS_CONT`，必须把 configuration predicate 写入 protocol
applicability、scope taxonomy/catalog 和 evaluation report。若 OIDS 本意覆盖所有有效
ext4 error policy，则 Phase 6 的反例意味着 ext4 universal validation 已被拒绝。

### 27.6 验证结果

```text
OIDS Phase 6 定向测试 = 8/8 passed
full unit/integration tests = 128/128 passed
Phase 6 runner = failstop_closed=True, errors_cont_witnesses=True, universal_closed=False
JSON validation = 119 files parsed
artifact_hashes_verified = true
bug_specific_condition_count = 0
historical semantics.py freeze hash = 526ebf1c1a4342fc461d5d635baefeb06c8293e48c1648e93c7020248884999b
base SOURCE_MANIFEST hash = 302223b94530376b980c082621ec2a9c34b05dcfb27bfa45a3adf776e669918c
compileall = PASS
git diff --check = PASS
```

### 27.7 下一步计划：Phase 7 applicability freeze / independent-family validation

1. 对 OIDS 作单一、显式的 scope 决定：若协议只要求 non-continuing failstop，
   将 `errors != continue` 写入 applicability 与 taxonomy/catalog，并把结论限定为该
   profile；不得继续使用无条件 ext4/common 表述。
2. 若 OIDS 必须覆盖 ext4 的全部有效 error policy，登记
   `ERRORS_CONT_VALID_COUNTEREXAMPLE`，正式拒绝 ext4 universal validation，不再尝试
   用额外 helper summary 消除已经闭合的 negative witness。
3. 根据上述决定重算 common-freeze gates。只有 applicability、每文件系统 closure、
   独立 family 与 post-freeze policy 全部满足时才允许生成 freeze；否则保持 candidate。
4. 转入新的独立文件系统 family/source validation。XFS 已在 freeze 前读取，只能标为
   `POST_FREEZE_XFS_VALIDATED`，不能称为 blind held-out；若需要真正 held-out，必须选择
   尚未在协议形成阶段揭示的新 family 并预先锁定 checker/protocol hashes。

## 28. 已完成：OIDS Phase 7 applicability freeze

### 28.1 已交付工件

```text
configs/evaluation/oids-phase7-ext4-failstop-scope-v0.1.json
configs/evaluation/oids-phase7-scope-freeze-v0.1.json
configs/catalog/oids-phase7-scope-qualification-v0.1.json
src/fmpca/orphan_phase7.py
tests/test_oids_phase7_scope.py
docs/crossfs/orphan-inode/oids-phase7-qualified-scope-v0.1.md
outputs/fmpca-oids-phase7-v0.1/summary.json
outputs/fmpca-oids-phase7-v0.1/report.md
```

历史 `protocol-scope-taxonomy-v0.1.json` 和 OIDS candidate protocol 保持字节级
不变。Phase 7 使用独立 qualification catalog 叠加显式配置 predicate，因此没有
回写或重解释 Phase 4-6 的历史证据。

### 28.2 显式 applicability 决定

Phase 7 选择并冻结以下限定范围：

```text
filesystem == ext4 AND error_policy != ERRORS_CONT
```

机器可读声明为：

```text
semantic_scope = FS_SPECIFIC
freeze_boundary = NARROW_FREEZE
included profile = ERRORS_RO_OR_FAILSTOP
excluded profile = ERRORS_CONT
excluded status = EXCLUDED_BY_EXPLICIT_PREDICATE
```

`ERRORS_CONT` 的排除依据不是方便性假设，而是 Phase 6 已闭合的
`OIDS-O1/O2/O3` source-plus-semantic negative witnesses。该排除同时写入 scope
declaration、qualification catalog、runner report 和测试。

### 28.3 executable scope gate

Phase 7 通过既有 `scope.py` 和历史 taxonomy 执行以下验证：

```text
scope.declaration_valid = true
scope.declared_semantic_scope = FS_SPECIFIC
scope.freeze_boundary = NARROW_FREEZE
scope.applicable_filesystems = [ext4]
phase6_failstop_closed = true
phase6_negative_witnesses_closed = true
applicability_predicate_closed = true
errors_cont_explicitly_excluded = true
qualified_scope_closed = true
```

只有 ext4 non-continuing failstop profile 被纳入该 narrow scope。Btrfs/ext4 不被
伪装成一个 implementation family；该声明也不把 candidate protocol 推广为 COMMON。

### 28.4 COMMON 与 held-out 边界

Phase 7 结果明确保持：

```text
common_freeze_manifest_generated = false
blind_held_out_claim_allowed = false
independent_family_status = NOT_A_BLIND_HELD_OUT
XFS policy = POST_FREEZE_XFS_VALIDATED
```

XFS 在 OIDS freeze 前已经被读取，因此只能作为 post-freeze validation/screening，
不能称为 blind held-out。真正的 held-out 需要选择此前未用于协议、binding、checker
形成的新 filesystem family，并在读取其目标源码前锁定当前 protocol/checker hashes。

### 28.5 验证结果

```text
OIDS Phase 7 定向测试 = 4/4 passed
full unit/integration tests = 132/132 passed
Phase 7 runner = qualified_scope_closed=True, common_freeze=False
JSON validation = 123 files parsed
artifact_hashes_verified = true
bug_specific_condition_count = 0
historical semantics.py freeze hash = 526ebf1c1a4342fc461d5d635baefeb06c8293e48c1648e93c7020248884999b
historical taxonomy hash = c4c1055e1c90b9c47ecf56a6f1d09331129f3d1a07c1555a14cf4b53c50119a4
base SOURCE_MANIFEST hash = 302223b94530376b980c082621ec2a9c34b05dcfb27bfa45a3adf776e669918c
compileall = PASS
git diff --check = PASS
```

### 28.6 下一步计划：Phase 8 independent-family pre-registration

1. 在读取新 filesystem 的 OIDS 目标源码前，生成 Phase 8 pre-registration manifest，
   锁定 Phase 7 scope catalog、protocol、binding-independent checker、测试和 AcceptP
   hashes，防止 candidate reveal 后修改语义。
2. 从此前未进入 OIDS protocol 形成阶段的 filesystem family 中选择一个候选；先做
   object/relation/lifecycle/authority/deadline 五维 correspondence screening，再决定
   `APPLICABLE / NON_APPLICABLE / UNRESOLVED`。
3. 只有 `APPLICABLE` 候选才继续建立 registration、settlement、recovery 的真实源码
   witness 与 replay；`NON_APPLICABLE` 必须给 controlled reason，`UNRESOLVED` 不计入
   broader-scope evidence。
4. 独立 family 通过 source、replay、proof closure 后，只能声明 post-scope validation；
   是否晋升 COMMON 仍需重新满足两文件系统独立 operation family 和全部 freeze gates，
   不因 Phase 7 narrow scope 自动晋升。

## 29. 已完成：OIDS Phase 8 UBIFS preregistered independent-family validation

### 29.1 预注册与源码边界

Phase 8 在读取 UBIFS 目标源码前选择了此前未进入 OIDS protocol、binding、
correspondence、replay、测试或 Linux 源码快照的 UBIFS，并锁定：

```text
candidate_filesystem = UBIFS
candidate_status_before_reveal = UNREVEALED_FOR_OIDS
source tag = Linux v6.14
source commit = 38fec10eb60d687e30c8c6b5420d86e8149f7557
preregistration SHA-256 = 9923997a1a885dccb7c2356d63c302d0c9512fd604084d59a8cad596d3d24e49
```

原预注册中的 `fs/ubifs/inode.c` 在 Linux v6.14 不存在。没有回写原文件，而是通过
独立 amendment 把 settlement 目标更正为 `file.c`，并为 recovery reconstruction
增加 `replay.c`：

```text
preregistration amendment SHA-256 = 981602b0bc1df6fd1fed5f5a120f76182191a73da110136efd2a08744ad1c17e
checker_or_protocol_lock_changes = 0
semantic_change = false
```

9 个 UBIFS 文件均来自同一 tag/commit，并由
`PHASE8_UBIFS_SUPPLEMENTARY_MANIFEST.json` 锁定：

```text
supplementary manifest SHA-256 = 89d5b6a1f65aa12e8949fc2b6fe9e3ec5c12cc51ab98b167c1ab0b4a1e65b1da
source_hashes_verified = true
pre_reveal_locks_verified = true
```

### 29.2 已交付工作件

```text
src/fmpca/orphan_phase8.py
configs/bindings/common/orphan-inode-ubifs-v0.1.json
configs/evaluation/oids-phase8-ubifs-validation-v0.1.json
tests/test_oids_phase8_ubifs.py
tests/fixtures/events/oids-ubifs-live-no-commit-v0.1.json
tests/fixtures/events/oids-ubifs-live-post-commit-v0.1.json
tests/fixtures/events/oids-ubifs-rw-recovery-v0.1.json
tests/fixtures/events/oids-ubifs-ro-recovery-deferred-v0.1.json
docs/crossfs/orphan-inode/ubifs-phase8-validation-v0.1.md
outputs/fmpca-oids-phase8-v0.1/summary.json
outputs/fmpca-oids-phase8-v0.1/report.md
linux-sources/linux-v6.14-fs/PHASE8_UBIFS_SUPPLEMENTARY_MANIFEST.json
```

最终交付 hash：

```text
Phase 8 validation manifest = bad098a91fc0af5a6a99bc5cc90f193fc73e1af92a14e824c6078486de258fa0
Phase 8 runner = 21de4ecd934e73f56cfb2ec08b2505ee140e07211ef48acae9ffe4088accf17c
Phase 8 tests = db906ada4e1eb5f0e22eaef28bfcdec4ad3e92645f7429ef5407aaf48e6722e7
Phase 8 dossier = 2d0800488a2df74d74a0163547f5d804893e3af9ba9d7497a24076a8aa4a61e3
Phase 8 summary = 7467148a4b9482db3454dcbfee0454c12dc2f3bb0ef95d8faa7e917f3a443baa
Phase 8 report = bd93054965875f9eaddeab1644c620904de86160c9b7f74b176c866a699ad446
```

### 29.3 五维 correspondence 与 registration

UBIFS 的五维 screening 全部闭合：

```text
object = CLOSED
relation = CLOSED
lifecycle = CLOSED
authority = CLOSED
deadline = CLOSED
applicability = APPLICABLE
```

`struct ubifs_orphan` 与 `struct ubifs_info` 的 orphan tree/list/commit state
提供 object 和 persistent registry role；inode number 提供 relation identity；
final eviction 与 mount recovery 是两个 deletion authorities。

registration 证明分区为：

```text
pre_write_failure_rollback
successful_journal_group
post_write_failure_read_only_failstop
commit_generation_persistence
```

`ubifs_unlink()` 先 `drop_nlink()`，再调用 `ubifs_jnl_update()`；last-reference
分支在 dent、zero-link inode 和 parent inode journal group 写入前调用
`ubifs_add_orphan()`。写入前失败由 unlink 恢复 saved nlink；写入后 bookkeeping
失败进入 `ubifs_ro_mode()`；成功 commit 通过 orphan start/end commit 把新 orphan
写入持久 orphan area。

### 29.4 settlement 与 recovery

settlement 闭合以下分区：

```text
no_intervening_commit
intervening_commit
orphan_owned_by_active_commit
settlement_error_failstop
```

无中间 commit 时，`ubifs_jnl_delete_inode()` 在 `commit_sem` 下先做 whole-inode
TNC removal，再 retire orphan。有中间 commit 时，`ubifs_jnl_write_inode()` 先写新的
replayable deletion inode，再移除 TNC keys 和 orphan。active commit 持有的 orphan
通过 `del/dnext` 延迟删除；`ubifs_orphan_end_commit()` 先 `commit_orphans()`，再
`erase_deleted()`。TNC/commit 失败均进入 read-only failstop。

successful RW recovery 的顺序闭合为：

```text
ubifs_replay_journal()
-> ubifs_mount_orphans(unclean=true, read_only=false)
-> ubifs_rcvry_gc_commit()
-> mount_ubifs() success
-> ubifs_fill_super() creates root
```

journal replay 把 zero-link inode node 分类为 deletion 并执行 whole-inode TNC
removal；持久 orphan area 处理已 commit 的 orphan；RW recovery commit 在 root
exposure 前把 TNC 更新写入 flash。

只读 recovery 没有被伪装为完成 settlement。源码明确报告 `recovery deferred`，
对应 replay 保持：

```text
read_only_recovery_profile = RECOVERY_DEFERRED_OUTSIDE_VALIDATED_RW_EXPOSURE
result = INCOMPLETE_UNDER_LOADED_SPEC
violation_rules = []
```

因此 Phase 8 的 validated profile 是 `SUCCESSFUL_RW_RECOVERY_EXPOSURE`，不声明
UBIFS 所有 mount profile 的 universal closure。

### 29.5 scope 与 held-out 结论

```text
candidate_validation_closed = true
blind_held_out_claim_allowed = true
validation_role = PREREGISTERED_BLIND_INDEPENDENT_FAMILY
phase7_scope_unchanged = true
common_freeze_manifest_generated = false
common_heldout_validated = false
```

UBIFS 在源码 reveal 前完成预注册，因此可以称为 blind independent-family validation。
但 Phase 7 没有 COMMON freeze，所以不能倒置时间顺序称为
`COMMON_HELDOUT_VALIDATED`。Phase 7 的 `filesystem == ext4 AND error_policy !=
ERRORS_CONT` narrow freeze 保持不变。

### 29.6 验证结果

```text
OIDS Phase 8 定向测试 = 8/8 passed
full unit/integration tests = 140/140 passed
Phase 8 runner = applicability=APPLICABLE, validation_closed=True, common_freeze=False
positive live/RW replays = 3/3 CONFORMANT_UNDER_LOADED_SPEC
read-only deferred replay = 1/1 INCOMPLETE_UNDER_LOADED_SPEC
JSON validation = 152 files parsed
artifact_hashes_verified = true
source_hashes_verified = true
pre_reveal_locks_verified = true
bug_specific_condition_count = 0
compileall = PASS
git diff --check = PASS
```

### 29.7 下一步计划：Phase 9 COMMON readiness requalification

1. 不修改 Phase 7 narrow freeze，新增 Phase 9 qualification/freeze artifacts，按历史
   taxonomy 重新计算 `COMMON` 的全部 candidate 与 freeze gates。
2. 分别锁定 Btrfs、ext4 non-continuing failstop 和 UBIFS successful-RW profile 的
   object/relation/lifecycle/authority/deadline、source、replay、proof closure，明确每个
   filesystem 的 applicability predicate，不把 UBIFS read-only deferred 路径算入 closure。
3. 只有 `minimum_two_applicable_filesystems`、independent operation family、per-FS
   source/replay/proof 和 protocol/binding/test hashes 全部满足时，才生成新的 COMMON
   freeze；否则输出精确 blocker 并保持 Phase 7 FS_SPECIFIC freeze。
4. 即使 Phase 9 生成 COMMON freeze，UBIFS 也只能作为该 freeze 的形成证据，不能成为
   post-COMMON held-out。之后必须另选一个尚未 reveal 的第三 filesystem，并在读取源码
   前锁定 Phase 9 COMMON artifacts，才能验证 `COMMON_HELDOUT_VALIDATED`。

## 30. 已完成：OIDS Phase 9 COMMON readiness requalification / narrow freeze

### 30.1 已交付工作件

```text
src/fmpca/orphan_phase9.py
configs/evaluation/oids-phase9-common-scope-v0.1.json
configs/catalog/oids-phase9-common-qualification-v0.1.json
configs/evaluation/oids-phase9-common-freeze-v0.1.json
tests/test_oids_phase9_common_freeze.py
docs/crossfs/orphan-inode/oids-phase9-common-freeze-v0.1.md
outputs/fmpca-oids-phase9-v0.1/summary.json
outputs/fmpca-oids-phase9-v0.1/report.md
```

最终交付 hash：

```text
Phase 9 freeze manifest = 2b044c5498e0c157a62d0f0d48a11e984a3412d0530fbd5a9fb2534a3bf46082
Phase 9 scope declaration = 5e1c1eabb052c535ab53d932bd7276b7dfe85e9f70d1c7a22eecb91513cab3a5
Phase 9 qualification catalog = 49026ce99a454743b2aad88323cc517f76d0b6564b6799cd580e19dc90570b92
Phase 9 runner = 052235e1281b729e845a91a4fd4fd90bd412ded4cbb9b448937771bbae3b9367
Phase 9 tests = 8ba1b2e5b24f5c368a33f5830a406bfa91d163ccdafca5e8f09b88e3b7d87013
Phase 9 dossier = b75166d9ff3ddd832982428be95cfc3bcd09b4ea2ba2fda6dbcdebc649cf8181
Phase 9 summary = dd9fe3062ba2df6705ea957a0e657a2acc301e7e81b7c0f3e20574a7e49de184
Phase 9 report = 03652517160e3495aba1f71cc23fe0957d2f7a0006c202c4c874f9356935fea4
```

### 30.2 COMMON gate 结果

Phase 9 没有修改历史 taxonomy，而是用既有 `scope.py` 对新的 scope declaration
重新执行所有 candidate/freeze gates：

```text
semantic_scope = COMMON
freeze_boundary = NARROW_FREEZE
common_candidate_ready = true
minimum_two_applicable_filesystems = true
all_correspondence_dimensions_closed = true
independent_operation_family_per_filesystem = true
source_witness_closed_per_filesystem = true
replay_closed_per_filesystem = true
proof_closure_closed_per_filesystem = true
protocol_binding_test_hashes_locked = true
common_freeze_ready = true
cross_filesystem_claim_allowed = true
failed_candidate_gates = []
failed_freeze_gates = []
```

因此机器可读决定为：

```text
decision = QUALIFIED_COMMON_NARROW_FREEZE
freeze_id = fmpca.oids.common.narrow-freeze.v0.1
common_freeze_manifest_generated = true
```

该 COMMON claim 仅覆盖共同 semantic footprint，不表示所有 filesystem、mount mode
和 error policy 都 universal conformant。

### 30.3 三个独立 freeze members

| filesystem | Phase 9 role | operation family | qualified profile |
|---|---|---|---|
| Btrfs | `DEVELOPMENT` | `btrfs-orphan-item-transaction` | zero-link deletion + successful RW recovery exposure |
| ext4 | `VALIDATION` | `ext4-orphan-file-or-list-jbd2-failstop` | `ERRORS_RO_OR_FAILSTOP` |
| UBIFS | `VALIDATION` | `ubifs-journal-and-orphan-area-commit` | live deletion + successful RW recovery exposure |

三个 operation family 名称互不相同。每个 member 的 object、relation、lifecycle、
authority、deadline、source witness、replay 和 proof closure 均为 true。

证据组合为：

```text
Btrfs: Phase 3 replay + Phase 4 CFG/all-path proof
ext4: Phase 3 replay + Phase 5 contracts + Phase 6 failstop/recovery + Phase 7 qualification
UBIFS: Phase 8 preregistered source/replay/proof validation
```

Phase 9 runner 会重新执行 Phase 3/4/6/7/8 manifests，而不是只信任 declaration 中的
布尔值。freeze manifest 还直接锁定 DSL、model、formulas、AcceptP/proof、semantics、
CFG frontend、binding frontend、各阶段 runner、scope、bindings、tests 和 protocol。

### 30.4 配置边界保持显式

ext4 `ERRORS_CONT` 仍由 Phase 6 的 OIDS-O1/O2/O3 negative witnesses 排除：

```text
filesystem == ext4 AND zero_link_deletion AND error_policy != ERRORS_CONT
```

UBIFS read-only recovery 仍保持：

```text
RECOVERY_DEFERRED_OUTSIDE_VALIDATED_RW_EXPOSURE
```

只读 deferred path 没有被计为 completed COMMON recovery exposure。Btrfs 与 UBIFS
的 freeze predicate 都显式限定 successful RW recovery exposure。

### 30.5 历史 freeze 与 held-out 时间边界

```text
phase7_scope_unchanged = true
historical_taxonomy_unchanged = true
candidate_protocol_unchanged = true
common_heldout_validated = false
ubifs_counts_as_post_common_heldout = false
```

Phase 7 scope declaration hash 仍为
`ee1f54519ef66077a3e99ed1306bbf01661de9ff7d6bbc6764b9a02a7a7bda85`；
Phase 7 freeze manifest hash 仍为
`9260fd03af2cd281a57e8966a91cd02716c08089243bfb37f0e73fada8596ac7`。

UBIFS 的 Phase 8 blind preregistration provenance 保持有效，但它参与形成 Phase 9
COMMON freeze，因此不能同时成为该 freeze 之后的 held-out validation。

### 30.6 验证结果

```text
OIDS Phase 9 定向测试 = 7/7 passed
full unit/integration tests = 147/147 passed
Phase 9 runner = common_candidate=True, common_freeze=True, common_heldout=False
JSON validation = 156 files parsed
artifact_hashes_verified = true
bug_specific_condition_count = 0
assessment.blockers = []
compileall = PASS
git diff --check = PASS
```

### 30.7 下一步计划：Phase 10 post-COMMON held-out pre-registration

1. 在读取任何新 candidate 源码前，生成 Phase 10 preregistration，至少锁定 Phase 9
   freeze manifest、COMMON scope、qualification catalog、protocol、三个 bindings、
   binding-independent checker、AcceptP、semantics、CFG frontend 和测试 hashes。
2. 从此前未进入 OIDS protocol formation、source snapshot、binding 或 screening 的
   filesystem 中选择一个新 candidate。XFS、F2FS、Btrfs、ext4 和 UBIFS 都不能冒充
   post-COMMON blind held-out。
3. 读取新 candidate 后先完成 object/relation/lifecycle/authority/deadline 五维 screening，
   再按预注册 partition 判定 `APPLICABLE / NON_APPLICABLE / UNRESOLVED`；不得为结果
   修改 Phase 9 freeze 或放宽 AcceptP。
4. 只有 correspondence、registration、settlement、recovery、source、replay 和 proof
   全部闭合且 `no_post_freeze_semantic_modifications = true` 时，才允许声明
   `COMMON_HELDOUT_VALIDATED`；否则保留 Phase 9 COMMON freeze 并报告精确 blocker。

## 31. 已完成：OIDS Phase 10 OCFS2 post-COMMON blind held-out screening

### 31.1 已交付工作件

```text
src/fmpca/orphan_phase10.py
configs/evaluation/oids-phase10-ocfs2-preregistration-v0.1.json
configs/evaluation/oids-phase10-ocfs2-preregistration-amendment-v0.1.json
configs/evaluation/oids-phase10-ocfs2-heldout-v0.1.json
configs/catalog/oids-phase10-ocfs2-screening-v0.1.json
configs/bindings/common/orphan-inode-ocfs2-v0.1.json
linux-sources/linux-v6.14-fs/PHASE10_OCFS2_SUPPLEMENTARY_MANIFEST.json
tests/fixtures/events/oids-ocfs2-live-v0.1.json
tests/fixtures/events/oids-ocfs2-async-recovery-v0.1.json
tests/test_oids_phase10_ocfs2_heldout.py
docs/crossfs/orphan-inode/ocfs2-phase10-heldout-screening-v0.1.md
outputs/fmpca-oids-phase10-v0.1/summary.json
outputs/fmpca-oids-phase10-v0.1/report.md
```

最终交付 hash：

```text
Phase 10 preregistration = 391b906fb50c00a54ec9c09f04db1c5492e9e2c4bff570ec31f3b79bc6be6b1a
Phase 10 preregistration amendment = 6af92d26f9feff76481c72c063ae1438b65edb6e553ad47147a53bd9b8b84de1
Phase 10 source manifest = e249fc4f49d407d76be051c7566b919ce16308b05b0e6c1971d8df04dda19f21
Phase 10 evaluation manifest = cdba00ca72f5518bd997e2e8e447a5538dc214e6fe229d9a5e3813111cd217d8
Phase 10 screening catalog = e49a7b92763b1c9f048fe67f3b279050d82b789fafa0e2699659984f981e6365
Phase 10 OCFS2 binding = c8f0ccd512b34dda760848a008df9093facb074d28efbc32338a767932069c41
Phase 10 runner = 175df9052ec294fae7df780eb9576a181952d7e57a1f709da243fd396cd2c20a
Phase 10 tests = d4aa37660aa8341c6bebaf995078250661bb743c5e9b5aa94e9d1ad58291b4cb
Phase 10 dossier = 34b527bdb4ea1512df0c00eb0acc8044435cda957c1471c7e7aa80a9a4a93892
Phase 10 summary = 78c35643b8f3210544eaf73a8fa19b4d5355c81994bc17df921f5c099ed66d7e
Phase 10 report = 5aca77db606503ff6524513cbe0ee96b61f5d68ef06772dd095f9f015ca9de9c
```

### 31.2 预注册与 blind provenance

在读取任何 `fs/ocfs2` 源码前，Phase 10 先生成 OCFS2 预注册，并锁定：

```text
Phase 9 COMMON freeze manifest + summary
COMMON scope + qualification catalog
candidate protocol
Btrfs/ext4/UBIFS 三个 freeze-member bindings
DSL + model + formulas + proof/AcceptP
semantics + deadline semantics
CFG frontend + binding frontend + scope + Phase 9 runner
既有 OIDS tests
```

预注册明确排除已经 reveal 的 XFS、F2FS、Btrfs、ext4 和 UBIFS。OCFS2 不在此前的
protocol formation、binding、screening、replay 或 source-evidence 中，因此：

```text
candidate_status_before_reveal = UNREVEALED_POST_COMMON_HELDOUT
validation_role = PREREGISTERED_POST_COMMON_BLIND_HELD_OUT
third_filesystem_post_freeze = true
```

源码 reveal 后发现 v6.14 没有独立的 `orphan_dir.c` 和 `recovery.c`；相应逻辑实际位于
`namei.c` 和 `journal.c`。amendment 只解析路径，并补入持久结构头 `ocfs2_fs.h`，没有修改
candidate、source revision、decision partition、closure gates 或任何冻结语义。

### 31.3 五维 correspondence 与 applicability

| dimension | status | 结论 |
|---|---|---|
| object | `CLOSED` | `OCFS2_ORPHANED_FL`、slot orphan system dir 与 `i_orphaned_slot` 构成持久 cleanup object |
| relation | `CLOSED` | inode block identity 被插入负责 slot 的 orphan directory |
| lifecycle | `CLOSED` | last-link registration、final eviction、journal replay 与 orphan scan 均有源码锚点 |
| authority | `CLOSED` | cluster-exclusive final eviction 与 recovery worker 是明确 deletion authorities |
| deadline | `BLOCKED` | orphan recovery 异步排队，mount exposure 前没有 join |

机器可读判定为：

```text
applicability = NON_APPLICABLE
controlled_reason_code = DEADLINE_NOT_ALIGNED
screening_dimensions_decided = true
controlled_non_applicable = true
```

这不是 `UNRESOLVED`：源码已经给出足够证据确定 deadline 不同构。

### 31.4 registration 与 settlement

`ocfs2_unlink()` 在启动 JBD2 handle 前准备 slot orphan directory；同一 handle 内依次 staged
namespace entry deletion、final `drop_nlink()`、`ocfs2_orphan_add()`，之后才
`ocfs2_commit_trans()`。成功 live deletion 的 registration 因此闭合。

final eviction 中，`ocfs2_wipe_inode()` 调用 `ocfs2_remove_inode()`；后者在一个
delete-inode handle 内调用 `ocfs2_orphan_del()`、清理 dinode 状态、
`ocfs2_free_dinode()`，最后统一 commit。orphan retirement 与 terminal dinode deletion
属于 atomic co-settlement，满足冻结的 OIDS-O2 alternative。

```text
registration.status = CLOSED
settlement.status = CLOSED
SUCCESSFUL_LIVE_DELETION replay = CONFORMANT_UNDER_LOADED_SPEC
```

### 31.5 recovery deadline blocker

OCFS2 journal replay 在 `ocfs2_check_volume()` 中同步执行，但 orphan cleanup 是第二阶段异步
工作：

```text
ocfs2_fill_super()
-> d_make_root()
-> sb->s_root = root
-> ocfs2_complete_mount_recovery()
   -> ocfs2_queue_recovery_completion()
-> VOLUME_MOUNTED / VOLUME_MOUNTED_QUOTAS
-> successful fill_super return

workqueue: ocfs2_complete_recovery()
-> ocfs2_wait_on_quotas()
-> ocfs2_recover_orphans()
-> iput() drives final deletion
```

queue 与 successful return 之间没有 `flush_work`、`flush_workqueue`、`drain_workqueue`
或等价 recovery join，因此无法在所有路径证明 OIDS-O3 的
`BEFORE_RECOVERY_EXPOSURE` deadline。

```text
recovery.status = BLOCKED
recovery.blocker = OCFS2_ORPHAN_RECOVERY_NOT_JOINED_BEFORE_MOUNT_EXPOSURE
RECOVERY_ASYNCHRONOUS_AFTER_MOUNT_EXPOSURE replay = INCOMPLETE_UNDER_LOADED_SPEC
```

没有为了获得正结果而改动 recovery exposure、AcceptP 或 protocol transitions。

### 31.6 COMMON held-out gate 结果

```text
common_freeze_ready = true
third_filesystem_post_freeze = true
heldout_correspondence_closed = false
heldout_source_witness_closed = false
heldout_replay_closed = false
heldout_proof_closure_closed = false
no_post_freeze_semantic_modifications = true
phase10_screening_closed = true
common_heldout_validated = false
```

Phase 10 完成的是一个有效、可复现的 negative blind screening。Phase 9 COMMON narrow freeze
保持有效且字节不变；OCFS2 不能作为下一次 blind held-out 重用。

### 31.7 验证结果

```text
OIDS Phase 10 定向测试 = 8/8 passed
full unit/integration tests = 155/155 passed
Phase 10 runner = applicability=NON_APPLICABLE, screening_closed=True, common_heldout=False
JSON validation = 165 files parsed
preregistration_hash_verified = true
pre_reveal_locks_verified = true
artifact_hashes_verified = true
source_hashes_verified = true
bug_specific_condition_count = 0
compileall = PASS
```

### 31.8 下一步计划：Phase 11 recovery-deadline-first held-out attempt

1. 保持 Phase 9 COMMON freeze、Phase 10 negative result 和所有历史 artifacts 不变；OCFS2
   从新的 blind candidate 集合中排除。
2. 在读取下一 filesystem 源码前生成新的 Phase 11 preregistration，继续锁定 Phase 9
   freeze、protocol、checker/AcceptP、semantics、CFG frontend、bindings 和 tests。
3. 对新候选先做 recovery-deadline-first 静态筛查：必须存在同步 orphan cleanup，或存在
   明确 wait/join 使 terminal settlement 支配正常 root exposure；否则尽早给出受控
   `DEADLINE_NOT_ALIGNED`，不做语义放宽。
4. 只有新候选五维 correspondence、registration、settlement、recovery、source、replay、
   proof 全部闭合，且 pre-reveal hashes 保持一致时，才生成
   `COMMON_HELDOUT_VALIDATED`；否则继续保留 Phase 9 COMMON narrow freeze。

## 32. 已完成：OIDS Phase 11 ReiserFS post-COMMON blind held-out evaluation

### 32.1 已交付工作件

```text
src/fmpca/orphan_phase11.py
configs/evaluation/oids-phase11-reiserfs-preregistration-v0.1.json
configs/evaluation/oids-phase11-reiserfs-heldout-v0.1.json
configs/catalog/oids-phase11-reiserfs-heldout-v0.1.json
configs/bindings/common/orphan-inode-reiserfs-v0.1.json
linux-sources/linux-v6.8-fs/PHASE11_REISERFS_SUPPLEMENTARY_MANIFEST.json
tests/fixtures/events/oids-reiserfs-live-success-v0.1.json
tests/fixtures/events/oids-reiserfs-rw-recovery-success-v0.1.json
tests/fixtures/events/oids-reiserfs-registration-enospc-v0.1.json
tests/fixtures/events/oids-reiserfs-settlement-removal-error-v0.1.json
tests/fixtures/events/oids-reiserfs-recovery-error-exposure-v0.1.json
tests/test_oids_phase11_reiserfs_heldout.py
docs/crossfs/orphan-inode/reiserfs-phase11-heldout-evaluation-v0.1.md
outputs/fmpca-oids-phase11-v0.1/summary.json
outputs/fmpca-oids-phase11-v0.1/report.md
```

最终交付 hash：

```text
Phase 11 preregistration = 92702a5d9a770a67a8a7c732f0c72532be420eb677232c62e038b510cfe0a826
Phase 11 source manifest = b17965790c8de2883524053310391f5442cbc57548e3232d86d96a8e5eaf4cb2
Phase 11 evaluation manifest = cd7e6d7e5a79e8872801a3932899d1c141505366a032f1a72023b8dc69b358c9
Phase 11 held-out catalog = a8d91adb5a1cf8716141547209a58bd0e34182745b1d1f77a029a58b232776fe
Phase 11 ReiserFS binding = b432eb316fea46472bb4765e2f5e6264be851e3cc7fefefdec2cab1b8b1dd829
Phase 11 runner = 9a981e186cd59a602176e4b797e02b17e5708bca6efa4c9840ba85b6fe7b2bbd
Phase 11 tests = dbdf8d077a263284dd82a9463e657978b44b52fee78804a037bd499870bb2368
Phase 11 dossier = 42d2ef064b14538f6c90f07670033d97e6f4f9ad5fb97264f075df062c792540
Phase 11 summary = 49ac98ac2985973ed9c770a13bfc33dc0eb7e2630ea740c1a8309d619a22f2e8
Phase 11 report = fe682c7df8ca33d20812575f132429a04443d9c4a34d129b62e16b64443007fe
```

### 32.2 预注册与 blind provenance

ReiserFS 在读取任何 `fs/reiserfs` 源码前完成预注册。预注册锁定 26 个 Phase 9/10、
protocol、checker/AcceptP、semantics、CFG frontend、bindings 和 tests 文件，全部 hash
验证通过。此前已 reveal 的 XFS、F2FS、Btrfs、ext4、UBIFS 和 OCFS2 均被排除。

源码固定为 Linux v6.8：

```text
tag = v6.8
commit = e8f897f4afef0031fe618a8e94127a0934896aba
registered source paths = 6
path amendment required = false
```

六个注册路径全部存在并逐文件锁定。ReiserFS 在预注册前未进入 OIDS protocol formation、
binding、screening、replay 或 source-evidence artifacts，因此 provenance 为：

```text
validation_role = PREREGISTERED_POST_COMMON_BLIND_HELD_OUT
third_filesystem_post_freeze = true
```

### 32.3 五维 correspondence 与 applicability

| dimension | status | 源码结论 |
|---|---|---|
| object | `CLOSED` | `MAX_KEY_OBJECTID` save-link keyspace 与 `i_link_saved_unlink_mask` 构成持久 cleanup object |
| relation | `CLOSED` | save-link key/body 绑定 inode object id 与原 directory id |
| lifecycle | `CLOSED` | last-link unlink、final eviction、journal replay、mount scan 全部有源码锚点 |
| authority | `CLOSED` | `reiserfs_evict_inode()` 与 `finish_unfinished()`/`iput()` 是明确删除 authority |
| deadline | `CLOSED` | 同步 `finish_unfinished()` 位于 successful RW mount return 前 |

因此机器可读 applicability 结论为：

```text
applicability = APPLICABLE
screening_dimensions_decided = true
correspondence_closed = true
```

不得把 `add_save_link()`、`remove_save_link()` 或 `finish_unfinished()` 的内部成功结果新增为
post-reveal applicability predicate；这些是执行 outcome，不是预先存在的 filesystem/profile
边界。

### 32.4 正常 registration、settlement 与 recovery

成功 registration 顺序闭合：

```text
reiserfs_unlink()
drop_nlink                  namei.c:1052
reiserfs_cut_from_item      namei.c:1060
add_save_link               namei.c:1076
journal_end                 namei.c:1078
```

成功 settlement 使用两个有序事务，而不是虚构 atomic co-settlement：

```text
reiserfs_evict_inode()
reiserfs_delete_object      inode.c:63
journal_end                 inode.c:76
remove_save_link            inode.c:91

remove_save_link()
reiserfs_delete_solid_item  super.c:540
journal_end                 super.c:547
```

成功 RW recovery 同步闭合：

```text
journal_init / journal_read super.c:2022, journal.c:2898
d_make_root                 super.c:2083
finish_unfinished           super.c:2185
successful return           super.c:2214
```

三条正常 stage 均为 `CLOSED`；live-success replay 中 terminal deletion 与 later save-link
retirement 的独立事务身份已被正确保留。

### 32.5 failure partitions 与 held-out 非符合结论

registration 的 `SAVE_LINK_ENOSPC_UNPROPAGATED` 分区：

```text
add_save_link() is void
reiserfs_insert_item()      super.c:494
retval error branch         super.c:496
caller journal_end          namei.c:1078
replay result               VIOLATION_UNDER_LOADED_SPEC / OIDS-O1
```

settlement 的 `SAVE_LINK_REMOVAL_ERROR_IGNORED` 分区：`remove_save_link()` 返回
`journal_end()` 结果，但 `reiserfs_evict_inode()` 丢弃它；没有额外 exposure event 时，结果严格
保留为 `INCOMPLETE_UNDER_LOADED_SPEC`。

recovery 的 `RECOVERY_ERROR_EXPOSURE_REACHABLE` 分区：

```text
finish_unfinished returns retval   super.c:420
reiserfs_fill_super ignores result super.c:2185
successful return remains reachable super.c:2214
replay result                      VIOLATION_UNDER_LOADED_SPEC / OIDS-O3
```

最终判定为：

```text
applicability = APPLICABLE
conformance_decision = NON_CONFORMANT_HELDOUT
phase11_screening_closed = true
candidate_conformant = false
common_heldout_validated = false
failed_heldout_gates = [heldout_replay_closed, heldout_proof_closure_closed]
```

这不是 `NON_APPLICABLE` 或 `UNRESOLVED`：ReiserFS 的 OIDS correspondence 已闭合，正是
因为失败路径仍在适用域内，held-out conformance 才被有效反例否定。Phase 9 COMMON narrow
freeze 保持字节不变；`COMMON` 语义适用性不能被误写成所有适用 filesystem 都符合。

### 32.6 验证结果

```text
OIDS Phase 11 定向测试 = 8/8 passed
full unit/integration tests = 163/163 passed
Phase 11 runner = applicability=APPLICABLE, decision=NON_CONFORMANT_HELDOUT
positive live/RW recovery replays = 2/2 CONFORMANT_UNDER_LOADED_SPEC
registration/recovery negative replays = OIDS-O1/OIDS-O3 closed
settlement removal-error replay = INCOMPLETE_UNDER_LOADED_SPEC
JSON validation = 177 files parsed
preregistration_hash_verified = true
pre_reveal_locks_verified = true
artifact_hashes_verified = true
source_hashes_verified = true
registered_sources_exact = true
bug_specific_condition_count = 0
compileall = PASS
git diff --check = PASS
```

### 32.7 下一步计划：Phase 12 COMMON claim disposition / counterexample audit

1. 冻结 Phase 11 的 `APPLICABLE / NON_CONFORMANT_HELDOUT` 结果，不修改 Phase 9 COMMON
   freeze、v0.1 protocol、checker/AcceptP、semantics 或历史 replay。
2. 生成 cross-filesystem claim-disposition matrix，明确区分 `COMMON semantic applicability`、
   正常路径 conformance、failure-path conformance 与 `COMMON_HELDOUT_VALIDATED`，防止把
   taxonomy scope 和经验符合性混为一谈。
3. 独立复核 ReiserFS OIDS-O1/OIDS-O3 的 source-to-CFG-to-replay 最小反例切片，并审计
   outcome-dependent narrowing 不可能合法排除这些路径。
4. 如果研究目标需要修复协议或改变 applicability，必须创建新的 protocol version 和新的
   development/validation/held-out split；不得 post hoc 修改 v0.1 后继续沿用 Phase 11 blind
   provenance。

## 33. 已完成：OIDS Phase 12 COMMON claim disposition / counterexample audit

### 33.1 已交付工作件

```text
src/fmpca/orphan_phase12.py
configs/evaluation/oids-phase12-claim-disposition-v0.1.json
configs/catalog/oids-phase12-common-claim-disposition-v0.1.json
tests/fixtures/events/oids-phase12-reiserfs-o1-minimal-v0.1.json
tests/fixtures/events/oids-phase12-reiserfs-o3-minimal-v0.1.json
tests/test_oids_phase12_claim_disposition.py
docs/crossfs/orphan-inode/oids-phase12-claim-disposition-v0.1.md
outputs/fmpca-oids-phase12-v0.1/summary.json
outputs/fmpca-oids-phase12-v0.1/report.md
```

最终交付 hash：

```text
Phase 12 evaluation manifest = 150235f8f767a47b7ba152e55f94b9bf3668aaa8657b8fabfaed4acb481acf05
Phase 12 claim catalog = 81655f303a621a6caab0ec62eb0a5e51c5c0ea002a29c846ef236b6059dfa82a
Phase 12 runner = f5ee8550de77e34ab8ed8bcddbbb6f5e270ff3401f2b188895a5e235cabb4348
Phase 12 OIDS-O1 minimal fixture = ac9c8135ebd3734a7f230b1737852bbde469a2459364fa1e4979cdefc297c2f5
Phase 12 OIDS-O3 minimal fixture = 139e1ccb036b743206440c2c5fb13cde2c3f472153e859c17fe4c319c53cd54e
Phase 12 tests = 4b4f85abc19b392a255be6401137fa1004f8852b41a896a5e988fbb2c1b6cf6f
Phase 12 dossier = 892c8393cfbd67b8885beec9b5293a4a794ec22e1c866ffe946638aa5ac4d86f
Phase 12 summary = 9a37e9941a6f36946849d85ed15d776337eaca8f5ebd3a23cbb9155899c2191b
Phase 12 report = 545ce00eea7297e9213450a3ef5d7920864b88749d08ac997dbc272d0b550a06
```

### 33.2 Phase 12 的职责边界

Phase 12 没有选择新 filesystem，也没有修改 OIDS v0.1 protocol、Phase 9 COMMON freeze、
checker/AcceptP、semantics、bindings 或历史 replay。runner 会重新执行 Phase 9、10、11，
再对它们做 claim disposition，而不是只信任已有 summary 中的布尔值。

```text
COMMON semantic applicability != universal filesystem conformance
qualified normal-path evidence != failure-path conformance
freeze formation evidence != post-freeze held-out evidence
```

历史结果全部保持：

```text
Phase 9 = QUALIFIED_COMMON_NARROW_FREEZE
Phase 10 OCFS2 = NON_APPLICABLE / DEADLINE_NOT_ALIGNED
Phase 11 ReiserFS = APPLICABLE / NON_CONFORMANT_HELDOUT
protocol_v0_1_mutated = false
historical_results_preserved = true
```

### 33.3 cross-filesystem claim-disposition matrix

| filesystem | evaluation role | applicability | normal profile | failure/held-out disposition |
|---|---|---|---|---|
| Btrfs | `FREEZE_FORMATION_DEVELOPMENT` | applicable | `CLOSED` | 未执行 post-COMMON held-out |
| ext4 | `FREEZE_FORMATION_VALIDATION` | `ERRORS_RO_OR_FAILSTOP` 边界内 applicable | `CLOSED` | `ERRORS_CONT` 继续由 negative witnesses 排除 |
| UBIFS | `FREEZE_FORMATION_VALIDATION` | live/successful-RW profile 内 applicable | `CLOSED` | read-only recovery deferred；不是 post-COMMON held-out |
| OCFS2 | `POST_COMMON_BLIND_SCREENING` | `NON_APPLICABLE` | live-only closed | `DEADLINE_NOT_ALIGNED`，不能评价 COMMON recovery conformance |
| ReiserFS | `POST_COMMON_BLIND_HELD_OUT` | `APPLICABLE` | successful live/RW `CLOSED` | `NON_CONFORMANT_HELDOUT`，OIDS-O1/O3 反例闭合 |

矩阵由 Phase 9–11 runner 的实际结果重建，并与 catalog 精确比对：

```text
matrix_matches_catalog = true
semantic_applicability_supported = true
normal_profiles_supported = true
failure_path_conformance_refuted = true
```

OCFS2 的受控不适用结果不会修复或反驳 ReiserFS 的 applicable counterexample；两者处于不同
claim partition。

### 33.4 OIDS-O1 独立最小反例审计

Phase 12 没有调用 Phase 11 的 registration analysis helper，而是独立重建 CFG 并定位：

```text
void add_save_link(...)                  super.c:429
reiserfs_insert_item(...)                super.c:494
retval error branch                      super.c:496
reiserfs_unlink -> add_save_link         namei.c:1076
reiserfs_unlink -> journal_end           namei.c:1078
```

最小 replay：

```text
InitializeOrphanDeletion
LastLinkRemoved
RegistrationTransactionCommit
=> VIOLATION_UNDER_LOADED_SPEC / OIDS-O1
```

分别删除上述任意一个事件后，`OIDS-O1` 均消失：

```text
source_control_flow_closed = true
source_replay_bridge_closed = true
rule_specific_irreducible = true
```

### 33.5 OIDS-O3 独立最小反例审计

独立 CFG slice：

```text
finish_unfinished returns retval         super.c:420
reiserfs_fill_super ignores result       super.c:2185
successful mount return reachable        super.c:2214
```

最小且不同时引入 OIDS-O1 的 replay：

```text
InitializeOrphanDeletion
LastLinkRemoved
OrphanRegistryAccepted
RecoveryAuthorityAccepted
RecoveryExposure
=> VIOLATION_UNDER_LOADED_SPEC / OIDS-O3
```

分别删除任意一个事件后，`OIDS-O3` 均消失：

```text
source_control_flow_closed = true
source_replay_bridge_closed = true
rule_specific_irreducible = true
```

因此两个 held-out violation 都有独立的 source-to-CFG-to-replay 最小证明，不依赖 Phase 11
summary 的既有判定。

### 33.6 outcome-dependent narrowing audit

Phase 9 冻结 predicate 只使用：

```text
filesystem identity
zero-link deletion
error policy
live-cleanup profile
successful-RW recovery-exposure profile
```

下列 post-reveal outcome predicates 均不存在于冻结 scope，且被明确拒绝：

```text
add_save_link_succeeded
remove_save_link_succeeded
finish_unfinished_succeeded
```

```text
no_outcome_predicates_in_frozen_scope = true
narrowing_audit_closed = true
decision = POST_REVEAL_OUTCOME_NARROWING_REJECTED
```

### 33.7 最终 claim disposition

```text
common_semantic_applicability = SUPPORTED_UNDER_FROZEN_NARROW_SCOPE
common_normal_profile_conformance = SUPPORTED_FOR_EVALUATED_QUALIFIED_PROFILES
common_failure_path_conformance = REFUTED_BY_POST_COMMON_HELDOUT_COUNTEREXAMPLE
common_heldout_validated = false
universal_filesystem_conformance = NOT_CLAIMED
protocol_v0_1_disposition = FROZEN_WITH_RETAINED_COUNTEREXAMPLE
revised_protocol_requirement = NEW_VERSION_AND_NEW_EVALUATION_SPLIT
phase12_claim_disposition_closed = true
```

Phase 9 COMMON narrow freeze 仍是有效的语义适用域工作件；被否定的是 v0.1 对 applicable
held-out implementation 的 failure-path conformance，而不是协议 footprint 的存在性。不能把
formation members 的正常/qualified profile 结果提升为 universal conformance。

### 33.8 验证结果

```text
OIDS Phase 12 定向测试 = 8/8 passed
full unit/integration tests = 171/171 passed
Phase 12 runner = disposition_closed=True, common_heldout=False
cross-filesystem matrix rows = 5/5 matched
minimal counterexample audits = 2/2 closed
OIDS-O1 deletion trials = 3/3 target rule absent
OIDS-O3 deletion trials = 5/5 target rule absent
JSON validation = 182 files parsed
artifact_hashes_verified = true
historical_results_preserved = true
bug_specific_condition_count = 0
compileall = PASS
git diff --check = PASS
```

### 33.9 下一步计划：Phase 13 OIDS v0.2 revision preregistration / split reset

1. 冻结 Phase 12 claim disposition；OIDS v0.1、Phase 9 freeze 和 ReiserFS counterexamples
   保持不变，作为 v0.2 的历史基线与 development evidence。
2. 在任何 semantics、AcceptP、protocol transition 或 applicability 修改前，预注册 v0.2 的
   repair objective：至少说明如何处理 registration acceptance failure 和 recovery cleanup
   error exposure，不得先看结果再选规则。
3. 创建新的 development/validation/held-out split。ReiserFS OIDS-O1/O3 已 reveal，只能转为
   v0.2 development counterexamples，不能继续充当 v0.2 held-out evidence。
4. 只有 v0.2 源码/replay/proof 在新 development 与 validation 集闭合后，才选择一个真正未
   reveal 的 filesystem 做新的 post-freeze held-out；在此之前不生成新的 COMMON validated
   claim。

## 34. 已完成：OIDS Phase 13 v0.2 revision preregistration / split reset

### 34.1 已交付工作件

```text
configs/evaluation/oids-phase13-v0.2-revision-preregistration-v0.1.json
configs/evaluation/oids-phase13-v0.2-evaluation-split-v0.1.json
configs/evaluation/oids-phase13-v0.2-preregistration-v0.1.json
configs/catalog/oids-phase13-reiserfs-development-bugs-v0.1.json
src/fmpca/orphan_phase13.py
tests/test_oids_phase13_v02_preregistration.py
docs/cases/reiserfs-oids-source-confirmed-bugs-v0.1.md
docs/crossfs/orphan-inode/oids-phase13-v0.2-preregistration-v0.1.md
outputs/fmpca-oids-phase13-v0.1/summary.json
outputs/fmpca-oids-phase13-v0.1/report.md
```

最终交付 hash：

```text
Phase 13 revision preregistration = 5262d9db9c2f20b1434ad955de923deaf2df5c5a66267112db2c7c71e573f404
Phase 13 evaluation split = 93ee6fedb2519084bfd705e49a314d033ba637a7524be274ee593b6218ab60cc
Phase 13 evaluation manifest = 2ab0f9acc550999af7b56185f4d37cc533a593a2eb2e569cc456e3d95e3f4698
Phase 13 bug catalog = 403149f2a22d0eac007c4feebef5ede7d290ee58b7e44986bf8e45e77875f799
Phase 13 runner = 110ee9eb89cb931ef42d645e52efe9ffb40ebc10fe3c73bf3937e36e76af9a71
Phase 13 tests = 4c13a61c1df33e579773b30e8ad513b08142b489df2b78904ed747d34747d04b
Phase 13 bug dossier = e02e7c3c1e2f259250efe4cfd9c2f8892217f1386b034f10b8548781962b4124
Phase 13 cross-FS dossier = 0c0aec1b3a88ade00168791966162e11e1146cf11850bd3f13e00bf9c71ff466
Phase 13 summary = 7428fae81ee501e230cd30402b758c54baaa7a6a4823d56363b06f1270a32702
Phase 13 report = d0433341b7b3ab55ae8fd1f0611a71e6187bdd70bef522e07d4522b3702bc091
```

### 34.2 ReiserFS 两个发现是不是 bug

结论：是。当前允许的准确表述为：

```text
SOURCE_CONFIRMED_CORRECTNESS_BUG under the frozen OIDS contract
```

判定不是仅凭 replay 标签，而是同时满足：

```text
真实 Linux v6.8 源码锚点闭合
CFG 中错误到不安全 checkpoint 的路径可达
rule-specific minimal replay 闭合且不可再约简
存在明确 metadata correctness impact mechanism
存在不改变 applicability 的 safe repair contract
```

两个 case 为：

| case | rule | bug class | source-confirmed |
|---|---|---|---|
| `REISERFS_SAVE_LINK_ENOSPC_UNPROPAGATED` | `OIDS-O1` | registration acceptance error suppression | true |
| `REISERFS_RECOVERY_ERROR_EXPOSURE_REACHABLE` | `OIDS-O3` | recovery cleanup error suppression | true |

registration bug 的 correctness mechanism：last-link namespace removal 可以在持久 save link
不存在时提交；若在 live eviction 前崩溃，零链接 inode 可能不在 mount save-link recovery 的
枚举范围内。

recovery bug 的 correctness mechanism：同步 `finish_unfinished()` 已报告 cleanup failure，
但 `reiserfs_fill_super()` 丢弃结果并仍可成功暴露 mount。

证据边界保持为：

```text
source_confirmed_bug_count = 2
runtime_reproduced_bug_count = 0
upstream_acknowledged_bug_count = 0
security_bug_count = 0
cve_claimed = false
```

因此可以称为源码确认的正确性 bug，但当前不能称为 upstream-confirmed bug、已运行复现的 bug、
安全漏洞、可利用漏洞或 CVE。

### 34.3 v0.2 预注册时间边界

Phase 13 在任何 protocol/semantics 修改前生成 revision preregistration，并锁定 Phase 12、
v0.1 protocol、DSL、proof/AcceptP、semantics、CFG frontend、ReiserFS source manifest 和两个
最小反例 fixture。

```text
planned_protocol_version = 0.2.0
revision_kind = DIAGNOSTIC_AND_FAILURE_HANDLING_CONTRACT_EXTENSION
semantic_edits_before_preregistration = 0
v0_1_protocol_mutated = false
v0_2_protocol_implemented = false
normative_safety_outcomes_preserved = true
pre_edit_locks_verified = true
```

Phase 13 只完成预注册与 split reset，尚未实现 v0.2。v0.1 的 OIDS-O1/O3 violation 结果不会
在 v0.2 中被放宽或改写。

### 34.4 预注册 repair objectives

registration acceptance failure 的允许修复选择：

```text
propagate error and prevent namespace commit
or prove abort/rollback of final-link transition
or enter failstop before unsafe success exposure
```

以下结果继续是 OIDS-O1：

```text
commit namespace removal while persistent cleanup responsibility is absent
```

recovery cleanup failure 的允许修复选择：

```text
propagate mount failure before root exposure
or explicit failstop/read-only containment with retained responsibility
or deadline-safe delegation proven before exposure
```

以下结果继续是 OIDS-O3：

```text
successful mount exposure with required cleanup incomplete
```

v0.2 的计划扩展面是 machine-readable failure cause、repair obligation、safe alternatives 和
证据等级；不是增加 `add_save_link_succeeded` 或 `finish_unfinished_succeeded` outcome predicate。

### 34.5 evaluation split reset

```text
development:
    ReiserFS OIDS-O1 source/CFG/minimal replay
    ReiserFS OIDS-O3 source/CFG/minimal replay

regression validation:
    Btrfs qualified successful profile
    ext4 ERRORS_RO_OR_FAILSTOP + ERRORS_CONT boundary
    UBIFS live/RW + read-only deferred boundary
    OCFS2 DEADLINE_NOT_ALIGNED boundary

held-out:
    empty
```

```text
development_case_count = 2
heldout_case_count = 0
heldout_contamination_count = 0
heldout_validation_allowed = false
common_v0_2_validated = false
split_reset_closed = true
```

ReiserFS 保留其 v0.1 blind held-out 历史 provenance，但由于源码与结果已经 reveal，它在 v0.2
中只能作为 development evidence。XFS、F2FS、Btrfs、ext4、UBIFS、OCFS2 和 ReiserFS 均
不能成为 v0.2 新 held-out。

### 34.6 验证结果

```text
OIDS Phase 13 定向测试 = 8/8 passed
full unit/integration tests = 179/179 passed
Phase 13 runner = preregistration_closed=True, source_confirmed_bugs=2
pre_edit_locks_verified = true
artifact_hashes_verified = true
v0_1_frozen = true
bug_cases_closed = true
terminology_policy_closed = true
repair_objectives_closed = true
heldout_validation_allowed = false
JSON validation = 187 files parsed
compileall = PASS
git diff --check = PASS
```

### 34.7 下一步计划：Phase 14 v0.2 diagnostic / failure-contract implementation

1. 保持 v0.1 protocol、Phase 9 freeze、Phase 12 disposition 和 Phase 13 preregistration 不变；
   新增独立 v0.2 artifact，不覆盖历史文件。
2. 实现 machine-readable failure-cause taxonomy、repair obligation 与 safe-outcome alternatives，
   把 ReiserFS OIDS-O1/O3 proof closure 映射到预注册 repair objectives。
3. 重新执行 Btrfs、ext4、UBIFS 和 OCFS2 regression boundaries，证明 v0.2 诊断扩展不改变
   v0.1 的 positive、negative、deferred 和 non-applicable 结果。
4. Phase 14 继续保持 held-out 为空、`common_v0_2_validated=false`；只有之后单独完成新候选的
   pre-reveal preregistration，才能读取新 filesystem 源码或生成 v0.2 held-out claim。

## 35. 已完成：OIDS Phase 14 v0.2 diagnostic / failure-contract implementation

### 35.1 已交付工作件

```text
configs/protocols/common/orphan-inode-deletion-settlement-v0.2-diagnostic.json
src/fmpca/diagnostics.py
configs/catalog/oids-phase14-reiserfs-diagnostic-mapping-v0.1.json
configs/evaluation/oids-phase14-v0.2-diagnostic-v0.1.json
src/fmpca/orphan_phase14.py
tests/test_oids_phase14_v02_diagnostics.py
docs/crossfs/orphan-inode/oids-phase14-v0.2-diagnostic-v0.1.md
outputs/fmpca-oids-phase14-v0.1/summary.json
outputs/fmpca-oids-phase14-v0.1/report.md
```

最终交付 hash：

```text
v0.2 diagnostic extension = 613b00438c5ebb6bf3ed6abc48ceb7bf6d73991dd074219f7ed2f84bc4d25fb1
diagnostic loader/engine = 27a6631a4d7c0ef75dd6604c58dbd6b886ae71bf5a06d9dbac3bfc946cb02cb1
ReiserFS diagnostic mapping = 2918075f088c453d98309212a9aa4900b352fef47bfa009f5e76cfd6dd1dc278
Phase 14 evaluation manifest = af7fcf7969e1f2d4ee5941a937af7cfdd1aeae69d85e787a0728a2669dc214ff
Phase 14 runner = be0add986c0d6d81b5b86048dcb1bf7660e281359289a6fd9d1747c91ad63ab1
Phase 14 tests = 4a9a42188ac714dcaae97aad03783b26bde3118334ebccecd725d4ea8d56beda
Phase 14 dossier = a9bdebfea2366c66f8f9e406bc06a571594052755ea013cb260a135b9c7cd330
Phase 14 summary = cbb90e330aa384be04391c26cb50ac55b9e0a45884c12a15e21cc0d9d27ebdc1
Phase 14 report = e981e1c10f8ff46bf5904ea12f9a6f7b801db2bbeb09fa20501b2e1cf74202e0
```

### 35.2 v0.2 架构边界

v0.1 executable protocol 的 DSL 根对象是严格 schema，Phase 14 没有向其中塞入额外字段，
也没有修改 DSL、transitions、obligations、deadlines、AcceptP 或 proof semantics。

v0.2 被实现为独立、可验证的 diagnostic extension：

```text
v0.1 executable protocol
    unchanged protocol behavior and results

v0.2 diagnostic extension
    evidence-level schema
    failure-cause taxonomy
    repair obligations
    safe-outcome alternatives
    diagnostic mappings
```

extension 直接锁定 v0.1 protocol hash，并对 canonical OIDS-O1/OIDS-O3 obligation 对象分别
锁定 hash：

```text
v0.1 protocol = c95135df0a9c916cd863d557aedebf64f06ae7bfee5bcf81692ce56f3c263122
OIDS-O1 canonical hash = f569cd534b40277b0e0a2f97e9ba9c9b3239d17917b5c203edde559c81c8457d
OIDS-O3 canonical hash = 58ef0997a1e62f0b4dc014b198229369af79b97cee458ede7f0cbb392769c5f8
```

```text
v0_1_protocol_mutated = false
v0_2_diagnostic_implemented = true
v0_2_normative_protocol_replaced = false
```

### 35.3 diagnostic engine

新增 `src/fmpca/diagnostics.py` 提供：

```text
load_diagnostic_extension()
validate_diagnostic_extension()
diagnose_failure()
DiagnosticFinding
```

validator 检查：

```text
base protocol and obligation hashes
unique evidence/cause/repair IDs
cause -> rule -> repair references
one diagnostic mapping per cause
safe alternative kinds and required facts
base applicability scope preserved
no new applicability predicates
held-out claims disabled
```

诊断输入是通用的 `rule + cause + trigger facts + evidence level/facts`，没有按 ReiserFS 函数名
硬编码结果。若少任一 evidence-level 必需事实，`diagnostic_closed=false`。

### 35.4 failure-cause taxonomy

| cause | rule | stage | unsafe checkpoint |
|---|---|---|---|
| `REGISTRATION_ACCEPTANCE_ERROR_SUPPRESSION` | OIDS-O1 | registration | `RegistrationTransactionCommit` |
| `RECOVERY_CLEANUP_ERROR_SUPPRESSION` | OIDS-O3 | recovery | `RecoveryExposure` |

当前证据等级 schema 包含：

```text
SOURCE_CONFIRMED_CORRECTNESS_BUG
RUNTIME_REPRODUCED_CORRECTNESS_BUG
UPSTREAM_ACKNOWLEDGED_CORRECTNESS_BUG
```

每一级有独立 required facts；Phase 14 的 ReiserFS mapping 只满足 source-confirmed level，
没有被提升为 runtime 或 upstream level。

### 35.5 machine-readable repair obligations

`REGISTRATION_ACCEPTANCE_FAILURE_CONTRACT`：

```text
REGISTRATION_PROPAGATE_AND_PREVENT_COMMIT
REGISTRATION_ABORT_OR_ROLLBACK
REGISTRATION_FAILSTOP
```

`RECOVERY_CLEANUP_FAILURE_EXPOSURE_CONTRACT`：

```text
RECOVERY_PROPAGATE_MOUNT_FAILURE
RECOVERY_CONTAIN_AND_RETAIN_RESPONSIBILITY
RECOVERY_DEADLINE_SAFE_DELEGATION
```

每个 alternative 都声明独立 `required_facts`，选择策略为：

```text
AT_LEAST_ONE_SAFE_ALTERNATIVE_MUST_BE_PROVEN
```

diagnostic 不自动 discharge obligation；给出 repair suggestion 也不等于证明 repair 已实现。

### 35.6 ReiserFS development mapping

| case | cause | repair obligation | diagnostic | proven safe alternative |
|---|---|---|---|---|
| OIDS-O1 ENOSPC suppression | registration error suppression | registration failure contract | closed | none |
| OIDS-O3 cleanup error suppression | recovery error suppression | recovery failure contract | closed | none |

```text
diagnostic_mappings_closed = true
evidence_gate_closed = true
mapping_policy_closed = true
OIDS-O1 repair_status = REQUIRED_NOT_IMPLEMENTED
OIDS-O3 repair_status = REQUIRED_NOT_IMPLEMENTED
```

两个 mapping 的 `observed_repair_facts=[]`；所有 safe alternative 仍缺少证明事实。因此 v0.2
提供了可执行诊断和修复条件，但没有虚构 ReiserFS 已经修复。

### 35.7 v0.1 violation 与 regression preservation

Phase 14 使用 v0.1 base protocol 重新执行两个最小 development replay：

```text
ReiserFS OIDS-O1 = VIOLATION_UNDER_LOADED_SPEC
ReiserFS OIDS-O3 = VIOLATION_UNDER_LOADED_SPEC
violation_results_preserved = true
```

并重新执行 Phase 6、8、9、10 runner：

| filesystem | regression boundary | result |
|---|---|---|
| Btrfs | qualified successful profile | `CLOSED` |
| ext4 | failstop positive + `ERRORS_CONT` negative | `PRESERVED` |
| UBIFS | live/RW positive + read-only deferred | `PRESERVED` |
| OCFS2 | `NON_APPLICABLE / DEADLINE_NOT_ALIGNED` | `PRESERVED` |

```text
regression_boundaries_preserved = true
applicability_unchanged = true
```

v0.2 没有新增 applicability predicate；`add_save_link_succeeded`、
`remove_save_link_succeeded`、`finish_unfinished_succeeded` 继续被拒绝。

### 35.8 held-out 状态

```text
heldout_partition_empty = true
heldout_validation_allowed = false
common_v0_2_validated = false
future_candidate_requires_separate_preregistration = true
```

Phase 14 只实现 development diagnostics 和 regression validation。没有选择候选、没有读取新
filesystem 源码，也没有生成 v0.2 held-out 或 COMMON validated claim。

### 35.9 验证结果

```text
OIDS Phase 14 定向测试 = 10/10 passed
full unit/integration tests = 189/189 passed
Phase 14 runner = diagnostic_closed=True, regressions=True, heldout_allowed=False
diagnostic mappings = 2/2 closed
safe alternatives falsely proven = 0
development violation replays = 2/2 preserved
regression boundaries = 4/4 preserved
artifact_hashes_verified = true
phase13_preregistration_preserved = true
evidence_gate_closed = true
JSON validation = 191 files parsed
compileall = PASS
git diff --check = PASS
```

### 35.10 下一步计划：Phase 15 v0.2 regression freeze / held-out preregistration

1. 生成 Phase 15 v0.2 regression freeze，锁定 v0.1 base、v0.2 diagnostic extension、Phase 13
   preregistration、Phase 14 summary、diagnostic mappings、tests 和四个 regression boundaries。
2. 仅使用现有 artifact/provenance 做未揭示候选池资格审计；不读取任何候选 filesystem 源码。
3. 从不在 XFS、F2FS、Btrfs、ext4、UBIFS、OCFS2、ReiserFS 集合中的 filesystem 选择一个
   candidate，并在源码 reveal 前单独预注册 source revision、target paths、applicability
   dimensions、decision partitions 和所有 pre-reveal hashes。
4. 只有 preregistration 写入并验证后，下一阶段才能获取候选源码；Phase 15 本身继续保持
   `common_v0_2_validated=false`。

## 36. 已完成：OIDS Phase 15 v0.2 regression freeze / JFS held-out preregistration

### 36.1 冻结结果

在读取或获取 JFS 源码前，完成了候选池审计、回归边界冻结和独立预注册：

```text
candidate = JFS
source tag = Linux v6.14
source commit = 38fec10eb60d687e30c8c6b5420d86e8149f7557
validation role = PREREGISTERED_V0_2_BLIND_HELD_OUT
registered target sources = 10
stop policy = ACCEPT_FIRST_COMPLETE_RESULT_WITHOUT_CANDIDATE_REPLACEMENT
source_unrevealed_at_freeze = true
phase15_preregistration_closed = true
common_v0_2_validated = false
```

JFS 是唯一选中候选；GFS2 和 NILFS2 未选中。JFS 的选择依据是独立 journaling/inode-map
operation family 和此前 OIDS artifact 中零出现，不包含对源码语义或预期结果的判断。

### 36.2 关键 hash

```text
regression freeze = 28b2259dcb9d8633c23389a68095f382091a2591282272fff110e44b93f81c62
candidate pool = 397677c849129a9f85b3453fbf47bc24dd5b666ef78f24a7319146f25f2808a3
JFS preregistration = 938f31a9381c8998d3f0aabdc314c38ca775626df559580aff61b1fce4076595
Phase 15 manifest = 89bf95786174f9bcaf7da85859a196ecca07f63f16e0f689f47b3e600a2e084a
Phase 15 summary = f59395580b5c1dc520458b7e8d67455bf1d448e15f6fd534b79c0923888f5334
Phase 15 report = 4fdbdb32fd0be4adeea1fbf5da07c0d1ca01af530f1eaf6253869f2ce13887b7
```

## 37. 已完成：OIDS Phase 16 JFS blind held-out evaluation

### 37.1 首个完整结果

按照预注册顺序完成 object、relation、lifecycle、authority、deadline 筛选，并接受首个完整结果：

```text
applicability = NON_APPLICABLE
controlled_reason_code = PERSISTENT_CLEANUP_OBJECT_NOT_FOUND
conformance = NOT_EVALUABLE
diagnostic_disposition = NOT_APPLICABLE
replay_required = false
candidate_replaced = false
stop_policy_honored = true
phase16_heldout_evaluation_closed = true
```

JFS 在最后链接删除事务中调用 `commitZeroLink()`，释放 persistent block-map resources，随后
transaction manager 通过 `diUpdatePMap(..., true, ...)` 释放 persistent inode allocation map。
若被删除文件仍打开，只剩 working-map 的易失清理，由 close/evict 处理；固定内核实现中不存在
可供 mount recovery 枚举的 durable orphan registry 或等价 persistent pending-cleanup relation。

注册的 `jfs_logmgr.c` 注释引用 `jfs_logredo.c`，但该路径在固定 commit 中不存在，也不在固定
`fs/jfs/Makefile` 的 kernel build 内。结构性 amendment 只增加 Makefile 来关闭编译边界，没有改变
候选、版本、适用性维度、结果分区或停止规则。内核 read-write mount 对 dirty filesystem 返回
`-EINVAL`，未把外部 fsck 行为冒充为 kernel OIDS recovery。

### 37.2 关键 hash

```text
source manifest = 95f2917df5e3747500a059562c035b2ceca51fccf10d5e2115f9d793ab024889
structural amendment = b57c046da23118eee695f3a672582ea97100e3069647cd71681de1638ff95bce
Phase 16 manifest = c602717a18c10fa1fde887472955dca5efa48ffcd7e2103a3a2a249151e9a8b9
Phase 16 summary = 2ed72ce51422940581d35600eb57cd4cdd53b5b0eb41e6ea3b854acd16bacb52
Phase 16 report = 66f389bccb32ca2a33ae91f0bc47025f0caa656c23a753d3806569f5fabeae19
```

## 38. 已完成：OIDS Phase 17 held-out result freeze

Phase 17 byte-for-byte 冻结 Phase 16 的首个结果，不重新选择候选：

```text
candidate = JFS
heldout_attempt_final = true
candidate_replaced = false
stop_policy_honored = true
v0_2_claim_disposition = HELDOUT_NON_APPLICABLE_NO_COMMON_VALIDATION
common_validation_gate_satisfied = false
common_v0_2_validated = false
phase17_result_freeze_closed = true
```

该结果是有效的 blind held-out attempt，但不是 conformance positive，也不是协议 counterexample。
由于候选不在 OIDS applicability domain 内，它不能支持 `COMMON_V0_2_VALIDATED`。

```text
Phase 17 manifest = fbef12d8c96c14b183f972bc3cbffce2b1a68fab35815fd5e033fbf344e23637
Phase 17 summary = 216517914eeab5b97c97532fa135b7f4481525990e51fe725713268a6d6c1605
Phase 17 report = 24ebb4bce8a94967abf1667b0ba951a7a9ede1a345541b0121455c4f6cfbd08b
```

## 39. 已完成：OIDS Phase 18 final release / hard endpoint

### 39.1 最终状态

```text
release_version = 0.2.0-final
Phase 1-17 chain = 17/17 hash-verified and assertion-closed
project_status = COMPLETE
hard_endpoint = PHASE_18
further_phase_expansion = false
maintenance_mode = true
project_complete = true
```

最终 claim matrix：

| claim | disposition |
|---|---|
| OIDS v0.1 executable protocol | frozen and regression-preserved |
| qualified COMMON candidate scope | Btrfs + ext4 fail-stop + UBIFS |
| OIDS v0.2 diagnostic extension | implemented and development-validated |
| ReiserFS OIDS-O1/O3 | two source-confirmed correctness bugs under frozen OIDS contract |
| JFS blind held-out | `NON_APPLICABLE / PERSISTENT_CLEANUP_OBJECT_NOT_FOUND` |
| `COMMON_V0_2_VALIDATED` | `NOT_VALIDATED` |

### 39.2 最终交付件与 hash

```text
configs/evaluation/oids-final-release-v0.2.json
src/fmpca/orphan_phase18.py
tests/test_oids_phase18_final_release.py
docs/crossfs/orphan-inode/oids-final-report-v0.2.md
docs/crossfs/orphan-inode/REPRODUCIBILITY-v0.2.md
outputs/fmpca-oids-final-v0.2/summary.json
outputs/fmpca-oids-final-v0.2/report.md

final manifest = 6470495535c18a29c46d0c3a452863f7ddbbba7857fc75e4106258bb2b1785a3
final summary = 40e2010457c1666e6d2cef241d559c3a54faef2460912baccbc3b41e33696e36
final report = 3f4a55dc386aa4580e2baf6f1c6aff43a1442a9c288fb78278ab77ee402486ce
```

### 39.3 最终验证

```text
Phase 15-18 targeted tests = 24/24 passed
full unit/integration tests = 213/213 passed
JSON validation = 194 files parsed
compileall = PASS
git diff --check = PASS (line-ending warnings only)
```

### 39.4 下一步计划：maintenance only

项目已在 Phase 18 完整结束，不再新增 Phase 19 或继续扩大经验性 claim。后续只允许：

1. bug fixes；
2. dependency maintenance；
3. reproducibility maintenance。

Phase 15 是历史 pre-reveal freeze；当前源码已经存在，不能通过重新运行 Phase 15 runner 来伪造历史
时点。复现时验证其 frozen summary/hash，然后可直接重跑 Phase 16、17、18 和全量测试。任何新候选、
新 held-out claim 或协议语义修改都必须另起独立版本化项目，而不是继续本项目的 phase 编号。

## Maintenance M1：只读发布完整性检查器

Phase 18 封版后新增独立 maintenance verifier，不修改任何 Phase 15-18 哈希锁定 artifact，也不引入
Phase 19：

```text
src/fmpca/orphan_maintenance.py
tests/test_oids_release_maintenance.py
```

执行命令：

```powershell
python -m src.fmpca.orphan_maintenance
```

检查器只读完成以下工作：

1. 验证 Phase 15 preregistration 和 frozen summary 的历史哈希，不重新运行 pre-reveal runner；
2. 在内存中重新计算 Phase 16、17、18，不覆盖 outputs；
3. 要求三个重算结果与 frozen summary 逐项完全一致；
4. 验证 final manifest、summary、report 哈希；
5. 保持 `project_status=COMPLETE`、`hard_endpoint=PHASE_18`、
   `further_phase_expansion=false`、`maintenance_mode=true` 和
   `common_v0_2_validated=false`。

本次结果：

```text
maintenance_closed = true
historical Phase 15 freeze = true
Phase 16-18 recomputation = 3/3 exact
final endpoint preserved = true
maintenance targeted tests = 4/4 passed
full unit/integration tests = 217/217 passed
compileall = PASS
git diff --check = PASS (line-ending warnings only)

maintenance verifier = 04560b3c716d360ab92299987b73c34918c6acbda65b9211a2923d699adf85a3
maintenance tests = 0e310eb7411545d1cd614ad42ff2896b2d8e30d92f7cc058a85c507d20b2a895
```

### 下一步计划

没有主动的研究开发步骤，也不新增 phase。以后每次 bug fix、依赖升级或复现环境调整后，先运行
`python -m src.fmpca.orphan_maintenance`，再运行全量测试；只有检查器发现漂移时才进入对应的
maintenance 修复。
