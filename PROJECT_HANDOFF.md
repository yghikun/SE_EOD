# 项目交接：层次化元数据 Typestate 分析器

更新时间：2026-08-04

## 1. 当前状态

项目已完成实现重置。当前仓库中不再保留旧分析器、协议 DSL、源码绑定、测试、生成图、旧案例文档或旧评测输出。

本次重置是主动决策。新工具将围绕**层次化关系 Typestate** 从零设计和实现，不以旧 `E/C/T/R`、OIDS 或此前 FMPCA 代码为实现基础。

当前真实能力为：

```text
总体架构：已由本文定义
可执行语义：0%
已冻结协议规格：0
源码前端：0%
测试：0
独立检测证据：0
```

保留的证据和基础设施：

```text
linux-sources/
outputs/confirmed_bugs.md
outputs/btrfs_tool_findings_pending_review_2026-07-23.md
docs/cases/patches/
3503222.3507770.pdf
3769109.pdf
Strom_Yemini_1986_Typestate.pdf
pyproject.toml
.git/
```

`README.md`、`PAPER_ROADMAP.md`、现有 PPT 及其检查文件不在本次删除范围内，其中可能仍有旧架构描述。它们后续需要单独重写；在此之前，本文是新实现唯一有效的交接文档。

## 2. 研究目标

工具分析一个进入错误路径的文件系统操作，并回答：

> 该错误路径产生的底层元数据转换轨迹，是否仍然实现了高层语义文件系统对象在对应 outcome 下允许到达的状态，并且满足轨迹已经触发的全部协议 deadline？

分析对象不是孤立的字段、API 对、inode、dentry、链表节点或计数器，而是**语义复合对象**：它应高到足以具有有意义的生命周期状态，又应低到可以从源码元数据中重建其状态。

首个开发候选为：

```text
语义对象：DeviceTopology
操作：为 seeded Btrfs 创建第一个可写设备，即 seed-to-sprout 转换
主要真实案例：outputs/confirmed_bugs.md 中确认的 Bug #18
同系列辅助证据：Bug #16 和 Bug #17
```

第一版只需要把一个真实操作做完整。在协议语义可执行且能够接受独立检验之前，不扩展为多文件系统或大规模 Bug 扫描。

## 3. 范围与非目标

### 3.1 第一版范围

- 分析一个元数据操作及其失败路径。
- 建模高层语义状态及 outcome-sensitive 合法转换。
- 建模多个子元数据对象、局部 typestate 和跨对象关系。
- 按顺序解释 path-sensitive 源码事件。
- 为所选操作支持必要的过程间事件投影。
- 显式检查 release、exposure、commit、operation return 等 deadline。
- 使用真实 Bug/fixed 源码差分做开发验证。
- 通过 Proof Closure 区分确定违规、符合和分析不完整。

### 3.2 第一版不做

- 不证明整个文件系统绝对正确。
- 不分析任意 crash point 或完整持久化 crash image。
- 不证明一般并发线程交错正确性。
- 不声称可以从任意源码中全自动挖掘完整协议。
- 不实现完整 heap/shape analysis。
- 不预设一套适用于全部文件系统的万能状态机。
- 不把 transaction abort 等同于全部状态自动回滚。
- 不把未配对 API 或剩余字段写入直接判为 Bug。
- 不恢复任何旧分析器模块或旧生成结果。

第一版能够成立的最强结论只能是：

```text
相对于已加载协议规格、已建模源码事件、对象身份、路径分区和显式假设，
证明某条路径符合或违反协议。
```

## 4. 核心思想

### 4.1 两个层次，而不是一个扁平状态机

模型由两个相连层次组成：

```text
高层语义对象
    DeviceTopology
    例如 SEEDED_STABLE、SPROUT_IN_PROGRESS、SPROUT_STABLE

内部因子化配置
    Membership typestate
    ActiveReference typestate
    TransactionAttachment typestate
    DeviceLifetime typestate
    跨对象关系和符号值
```

高层状态机描述语义复合对象的生命周期。子状态机描述实现该生命周期所需的内部元数据事实。

二者不是同步复制关系：

- 一个高层操作会展开为多个底层事件。
- 子状态可以变化，而高层状态暂时不变。
- 高层状态变化不要求每个子状态都变化。
- 多种内部配置可以共同实现同一个高层状态。
- 某些内部中间配置只在隔离条件成立时合法。
- 不能显式构造所有子状态的笛卡尔积。

### 4.2 源码事件驱动子状态，子状态共同实现高层状态

每条路径按以下顺序解释：

```text
源码语句或 callee summary
-> 类型化语义事件
-> 更新受影响的子 typestate、关系或符号值
-> 检查该事件触发的 deadline
-> 通过 Realize 推导当前可实现的高层状态
-> 继续执行直至协议结算点
```

高层状态不能仅由 `open()`、`btrfs_setup_sprout()` 等函数名推断。高层操作必须展开为类型化内部事件，再由事件形成的内部配置决定能够实现什么高层状态。

### 4.3 主状态机的主体

主状态机的主体是选定的语义复合对象，不是某一个 C 结构体。

首个案例中的对象边界为：

```text
DeviceTopology =
    topology 容器
    + 参与设备
    + active-device 引用
    + transaction-list attachment
    + 设备生命周期
    + 操作阶段与 outcome
```

这个层次避免两个极端：

- 太底层：只检查 inode、dentry、list 或 counter 的孤立变化，缺少语义上下文。
- 太高层：直接建模整个 file 或 filesystem，状态无法从源码中可靠重建。

## 5. 形式模型

### 5.1 高层状态机

对语义对象类型 `H`：

```text
HighMachine(H) = <Q, Op, Outcome, Entry, Allowed>
```

- `Q`：有限高层状态集合。
- `Op`：建模的高层操作。
- `Outcome`：相关成功与失败分区。
- `Entry`：合法操作入口状态。
- `Allowed(q0, op, outcome)`：结算时允许到达的高层状态集合。

`DeviceTopology` 的初始候选状态为：

```text
稳定状态：
    SEEDED_STABLE
    SPROUT_STABLE
    FAILSTOP_CONTAINED，仅在规格有证据时纳入

瞬态状态：
    SPROUT_IN_PROGRESS
    ROLLBACK_IN_PROGRESS
```

这些名称目前不是已冻结协议事实。必须先在规格获取 dossier 中获得语义证据，才能进入实现。

### 5.2 因子化内部配置

解释器状态为：

```text
kappa = <
    operation_phase,
    role_bindings,
    child_typestates,
    relation_facts,
    symbolic_values_and_deltas,
    authority_claims,
    isolation_evidence,
    observability,
    outcome,
    path_condition,
    precision_provenance
>
```

各子域分别存储，通过谓词组合。该表示是因子化配置，不是枚举后的乘积状态机。

首轮需要审查的 `DeviceTopology` 子域包括：

```text
Membership
    每个 device 属于哪个 topology
    device 是 linked、migrating 还是 detached

ActiveReference
    latest_dev 与 s_bdev 指向哪个 live device
    引用是 absent、valid 还是 dangling

TransactionAttachment
    device->post_commit_list 是 detached 还是 attached
    attachment 属于哪个 transaction

DeviceLifetime
    allocated/private、live/published、releasing 或 freed
```

dossier 可以合并或细化这些域，但不能只因为某个历史 Bug 需要某个标签就添加状态。

### 5.3 Realize 关系

`Realize(q, kappa)` 表示内部配置 `kappa` 是高层状态 `q` 的一个合法实现。

它是关系，不是一对一解码函数：

```text
Realize: HighState x InternalConfiguration -> Boolean
```

候选示例：

```text
Realize(SEEDED_STABLE, kappa) 要求：
    seed topology 仍是 active topology
    设备 membership 与相关计数一致
    active references 指向 live seed device
    失败的新设备未残留 transaction attachment

Realize(SPROUT_STABLE, kappa) 要求：
    新的 writable topology 已安装
    topology membership、计数、身份和 active references 一致
    publication/commit deadline 均已满足
```

每条 Realize 子句必须有独立设计证据，来源可以是文档、正常源码、fixed 源码、断言或重复实现模式。

### 5.4 轨迹安全与 deadline

只检查最终状态不够。有些错误在 operation return 前已经暴露或变成不可逆。

```text
Deadline 类型：
    ALWAYS
    BEFORE_EXPOSURE
    BEFORE_RELEASE
    BEFORE_COMMIT
    AT_OPERATION_RETURN
    BEFORE_OWNER_TERMINATION
```

`TraceSafe(path)` 表示每个已触发 deadline 的谓词都在到期事件处成立。

例如：

```text
ReleaseDevice(d) 要求：
    TransactionAttachment(d) == DETACHED
    不存在 active reference 指向 d
```

如果 device 在仍然 attached 时被释放，后续 cleanup 不能抹去已经形成的违规证据。

### 5.5 Outcome-sensitive 结算

失败后的合法状态不必等于成功状态，也不必逐字节恢复所有无关字段。

```text
Allowed(q0, operation, SUCCESS) 可以包含 SPROUT_STABLE。
Allowed(q0, operation, ERROR) 可以包含 SEEDED_STABLE。
Allowed(q0, operation, ERROR) 只有在有证据时才能包含 FAILSTOP_CONTAINED。
```

对 rollback 类操作，错误返回通常要求恢复入口语义状态，而不是机械恢复所有实现字段的原始比特模式。

### 5.6 接受条件

设路径 `pi` 从入口配置 `kappa0` 到结算配置 `kappaf`：

```text
Accept(pi) =
    EntryEvidence(kappa0)
    and Realize(q0, kappa0)
    and PathSemantics(kappa0, pi, kappaf)
    and ProofClosure(pi)
    and TraceSafe(pi)
    and exists q in Allowed(q0, operation, outcome):
        Realize(q, kappaf)
```

一条 proof-closed witness 满足以下任一条件时构成违规：

```text
1. 已触发的 trace/deadline 子句为 false。
2. 到达结算点时，不存在任何 outcome 允许的高层状态可被当前配置实现。
```

未解析 alias、未知相关调用、缺失路径分区或未建模 possible-write 只能产生分析不完整，不能证明违规，也不能证明符合。

## 6. 受限协议规格如何获得

### 6.1 规格来源

受限协议规格需要从文件系统语义中手工构建，使用多类证据交叉约束：

```text
规范性文档与源码注释
正常操作路径
错误路径契约
fixed 版本与已接受补丁
ASSERT、WARN、锁与生命周期条件
跨 helper 或跨实现反复出现的模式
历史 Bug 报告与动态复现
```

任何单一来源都不是绝对 oracle。Buggy source 可能正包含待检查错误；fixed source 可能混入非必要修复；文档也可能不完整。

之所以称为“受限”规格，是因为只建模有证据支持的状态、操作、角色、outcome 和 deadline。工具必须把未覆盖部分作为假设和能力边界报告，不能默认为完整。

### 6.2 历史 Bug 的合法用途

历史 Bug 可以用于：

- 定位值得建模的语义对象和操作；
- 暴露需要回答的语义问题；
- 检查模型能否区分 Bug 与 fixed 轨迹；
- 在存在独立依据时，帮助归纳子域或 deadline。

历史 Bug 不能用于：

- 将 Bug ID、源码行号或完整调用链写入接受规则；
- 因为某转换位于 Bug 版本中就直接宣布其非法；
- 在影响协议或 binding 后继续充当 held-out 证据；
- 看到评测结果后修改已冻结协议。

首个开发周期中，Bug #16-#18 及其补丁全部属于 development evidence，不属于独立评测证据。

### 6.3 通用语义与特定绑定

目标既不是一个万能状态机，也不是每个 Bug 一条规则，而是分成三层：

```text
可复用 schema：
    state、role、event、deadline、Realize、Allowed、evidence 类型

语义对象协议：
    DeviceTopology 在明确 operation family 下的状态和不变量

文件系统/源码 binding：
    Btrfs 类型、字段、API、参数位置和返回值分区
```

membership、reference validity、ownership、publication、rollback 等概念可以复用；`latest_dev`、`s_bdev`、`post_commit_list` 等字段只属于 Btrfs binding。

## 7. 协议表示

进入源码分析前，第一个协议必须能以受限声明式格式表达：

```text
ProtocolSpec = <
    protocol_id,
    semantic_object,
    applicability,
    evidence_manifest,
    roles,
    operation_scope,
    entry_predicates,
    high_states,
    outcomes,
    child_domains,
    relation_facts,
    typed_events,
    child_transitions,
    realize_clauses,
    invariants_and_deadlines,
    allowed_settlement_states,
    semantic_footprint,
    epoch_policy,
    assumptions
>
```

DSL 必须受限且可审计。它可以引用 typed role、relation、symbolic delta、事件顺序和有限状态，但不能执行任意代码，也不能直接读取源码行号。

源码 binding 必须独立保存：

```text
SourceBinding = <
    C types and fields,
    access-path patterns,
    API summaries,
    formal-to-actual role projection,
    return/error partitions,
    lock and lifetime evidence,
    provenance
>
```

## 8. 实例重建与源码解释

### 8.1 实例身份

事件依据语义角色和 operation epoch 聚合为协议实例：

```text
SemanticInstanceKey = <
    protocol_id,
    anchor_role_identities,
    base_epoch
>
```

`base_epoch` 至少包含 operation-root invocation 与 retry generation。transaction identity、object generation 或 allocation site 是否参与，由协议的 `EpochPolicy` 决定，不能默认全部拼入实例键。

Alias 规则：

```text
MUST_ALIAS     可以建立身份并解除条件
MAY_ALIAS      分裂候选实例或路径
NO_ALIAS       保持实例独立
UNKNOWN_ALIAS  使受影响证明不完整
```

### 8.2 过程间摘要

Callee summary 是带 guard 的有限关系，不是单一状态变换器：

```text
Summary_f(input) = {
    <guard, outcome, events, relation_delta, obligations, precision>, ...
}
```

Caller 将 actual role 投影给 callee，对每个可行分区应用摘要，再将事件和身份投影回 caller。只有 operation root 可以加载合法高层入口假设；普通 helper 必须继承 caller 的中间配置。

### 8.3 Proof Closure

违规证明与符合证明的闭合条件不同。

`ViolationProofClosure` 只需要一条独立 witness 路径满足：

- failure edge 有源码证据；
- 控制流可达且建模 guard 可满足；
- 关键事件为 must-execute；
- 关键对象身份已解析；
- 所有可能阻止或否定 witness 的调用均有完整 summary；
- deadline 之前不存在未知相关写入。

`ConformanceProofClosure` 还要求覆盖并接受全部相关可达分区。

结果汇总顺序固定为：

```text
VIOLATION_UNDER_LOADED_SPEC
    至少存在一条 proof-closed 违规 witness

POSSIBLE_VIOLATION_REVIEW
    只有 may-alias、may-execute 或抽象可行性支持违规

INCOMPLETE_UNDER_LOADED_SPEC
    无确定违规，但至少一个相关分区未闭合

CONFORMANT_UNDER_LOADED_SPEC
    所有相关可达分区均 proof-closed 且满足 Accept

NO_APPLICABLE_PROTOCOL
    操作没有实例化已加载协议
```

## 9. 首个真实案例：DeviceTopology

### 9.1 为什么选择该对象

Btrfs seed-to-sprout 操作通过多个结构体和 helper 协同改变 topology。它足够高层，能够表示真正的文件系统语义转换；同时又足够具体，可以从源码恢复内部配置。

保留补丁系列给出三种不同失败症状：

```text
Bug #16：
    失败设备仍留在 transaction dev_update_list

Bug #17：
    latest_dev 或 s_bdev 仍指向已释放的失败设备

Bug #18：
    error return 后 fs_devices 仍处于部分初始化的 sprout 状态
```

这说明单独检查 list 或 counter 不够。该操作需要联合 membership、active reference、transaction attachment、lifetime、topology identity 和 outcome。

### 9.2 候选高层流程

规格 dossier 必须验证或修订下面的候选状态机：

```text
SEEDED_STABLE
    -- BeginSprout -->
SPROUT_IN_PROGRESS
    -- PublishAndComplete / SUCCESS -->
SPROUT_STABLE

SPROUT_IN_PROGRESS
    -- FailureDetected -->
ROLLBACK_IN_PROGRESS
    -- RestoreSeedTopology / ERROR -->
SEEDED_STABLE
```

`INVALID` 不是合法高层状态，而是诊断结果：存在 proof-closed 证据表明内部配置违反 deadline，或无法实现任何 outcome 允许状态。

### 9.3 三个 Bug 的候选判定方式

以下规则仍需通过独立证据确认：

```text
#16：
    ReleaseDevice(new_device)
    且 TransactionAttachment(new_device) == ATTACHED
    -> BEFORE_RELEASE 违规

#17：
    ReleaseDevice(new_device)
    且 latest_dev 或 s_bdev 仍引用 new_device
    -> ActiveReference target-liveness 违规

#18：
    OperationReturn(ERROR)
    但内部配置仍是部分安装的 sprout topology
    且无法实现 Allowed(SEEDED_STABLE, sprout, ERROR) 中任何状态
    -> 最终状态符合性违规
```

Fixed 源码必须由完全相同的解释器和冻结规则处理，并在结算前观察到 detach、active-reference restoration 和 topology rollback。

### 9.4 证据入口

使用以下保留材料：

```text
outputs/confirmed_bugs.md
docs/cases/patches/sprout-rollback-v1/0000-cover-letter.patch
docs/cases/patches/sprout-rollback-v1/0001-*.patch
docs/cases/patches/sprout-rollback-v1/0002-*.patch
docs/cases/patches/sprout-rollback-v1/0003-*.patch
docs/cases/patches/sprout-rollback-v1/bug-source-a13c140c.zip
docs/cases/patches/sprout-rollback-v1/fixed-source-a4e996b8.zip
linux-sources/
```

Bug #18 默认作为主案例，因为它真正检查高层、outcome-sensitive 的 `Realize`。Bug #16 和 #17 属于同一操作中的 deadline 检查。最终 dossier 必须明确决定第一版同时覆盖三者，还是只实现 #18。

## 10. 从零实现步骤

每个阶段必须包含输入、产物、测试和通过门槛。前一阶段未通过时，不进入下一阶段。

### R0：重置并保留证据

输入：

- 重置前仓库；
- 用户确认的保留清单。

产物：

- 删除旧代码、测试、配置、图、案例派生文档和生成输出；
- 只保留获准证据。

测试：

- 枚举仓库、`outputs/` 和 `docs/cases/`；
- 检查 `git status`，不回退用户已有修改。

通过门槛：

- 不存在任何旧实现模块；
- 两份保留报告和补丁证据均可读取。

状态：**已于 2026-08-04 完成**。

### R1：证据分类与案例选择

输入：

- 已确认 Bug 描述；
- Bug/fixed 源码压缩包和补丁；
- 相关正常 Btrfs 源码与文档。

工作：

1. 重建 operation boundary 和 failure partitions。
2. 将证据逐项标记为 normative、implementation、fix、assertion、Bug observation 或 assumption。
3. 默认选择 #18 为主案例；如果证据不足，则缩小第一版范围。
4. 明确 #16/#17 是正式检查还是仅作为辅助证据。

产物：

```text
docs/evidence/device-topology/evidence-manifest.md
docs/evidence/device-topology/source-map.md
docs/evidence/device-topology/case-selection.md
```

测试：

- 每个候选状态、关系和 deadline 至少有一个可追溯来源；
- 冲突证据被记录而不是被静默合并；
- Bug-only observation 被显式标记。

通过门槛：

- semantic object、operation root、entry condition、outcome partition 和 settlement point 均无歧义。

### R2：规格获取 dossier

输入：

- R1 evidence manifest。

工作：

1. 定义高层对象边界。
2. 定义合法入口、瞬态、成功和失败状态。
3. 定义 child role 和因子化状态域。
4. 定义关系、符号 delta、不变量和 deadline。
5. 定义 `Realize`、`Allowed`、`TraceSafe` 与假设。
6. 记录反面证据和明确不建模的行为。

产物：

```text
docs/specification/device-topology-dossier.md
specs/device-topology/protocol.yaml
specs/device-topology/evidence.lock
```

测试：

- 规则中不含 Bug ID、patch ID、源码行号或完整目标调用链；
- 去掉 Bug-specific 证据后，每条语义规则仍有独立依据；
- 至少一个正常成功轨迹和一个合法错误轨迹能通过手工 replay；
- 有歧义的子句被标为 unresolved，不做猜测。

通过门槛：

- 专家无需查看 Bug/fixed 标签，仅依据协议即可判断预期结果。

### R3：最小结构化事件解释器

输入：

- R2 的冻结草案；
- 手工编写的 typed event trace。

工作：

1. 实现 typed identity、role、event、child domain 和 `kappa`。
2. 实现事件 replay 与因子化状态更新。
3. 实现 `Realize`、deadline、`Allowed` 和结果汇总。
4. 输出逐事件证据轨迹。

此阶段不实现 C 源码解析。

必须测试：

```text
normal success
legal rollback
#16 形态的 release deadline violation
#17 形态的 active-reference violation
#18 形态的 final realization violation
unknown relevant repair
may-alias ambiguity
```

通过门槛：

- 不使用目标函数或 Bug-specific 分支即可得到预期结果；
- unknown 不能证明违规或符合；
- 子状态变化不必强迫高层状态变化；
- 多个内部配置可以实现同一高层状态。

### R4：单操作源码到事件 binding

输入：

- Bug-source tree；
- R2 协议和 source map；
- R3 解释器。

工作：

1. 只实现目标操作所需的最小 C frontend。
2. 恢复控制流 failure partitions。
3. 解析所选对象身份和 formal-to-actual projection。
4. 将源码语句与 callee summary 映射为 typed event。
5. 计算协议 influence/repair slice。

产物：

```text
Btrfs DeviceTopology source binding
必要 helper 的 guarded summaries
带 provenance 的 source-derived event traces
Coverage and Assumption Report
```

测试：

- 每个抽取事件都可追溯到源码和 binding 证据；
- direct 与 interprocedural 事件映射到相同语义类型；
- may/unknown alias 不会升级为 must identity；
- 未建模相关调用会导致 incomplete。

通过门槛：

- 所选真实错误分区能从源码端到端 replay，无需手工改写事件轨迹。

### R5：开发用 Bug/fixed differential

输入：

- 相同的协议、解释器和 binding；
- `bug-source-a13c140c.zip`；
- `fixed-source-a4e996b8.zip` 或三份补丁。

工作：

1. 分析选定 Bug failure partition。
2. 分析对应 fixed failure partition。
3. 对比事件、子状态、高层 Realize、deadline 和 Proof Closure。

预期：

```text
Bug source：
    对所选 witness 输出 VIOLATION_UNDER_LOADED_SPEC

Fixed source：
    对相同建模分区满足 Accept
```

测试：

- 两个版本使用完全相同的协议和语义代码；
- 只有源码派生事件不同；
- 报告能指出第一个决定性 deadline 或结算不匹配；
- 看到差分结果后不修改规则。

通过门槛：

- 差分由语义转换解释，而不是由补丁文本匹配解释。

本阶段仅是**开发验证**，不是独立评测证据。

### R6：冻结 v0.1

输入：

- 已通过 R1-R5 的全部产物。

产物：

```text
protocol hash
binding hash
semantic-engine hash
evidence-manifest hash
明确的 applicability 与 exclusion
```

通过门槛：

- clean checkout 能复现全部 R3 与 R5 报告；
- Bug-specific condition count 为 0。

### R7：冻结后未见分区

输入：

- 已冻结 v0.1；
- 一条没有参与协议或 binding 开发的 failure partition。

工作：

- 查看结果前登记预期范围和分析流程；
- 不修改语义或 binding 直接运行；
- 如实分类 violation、conformance 和 incomplete。

通过门槛：

- 只有本阶段结果可以成为初始独立检测证据；
- 任何冻结后修改都会取消 held-out 身份并产生新版本。

### R8：扩展决策

只有 R7 完成后才能决定：

- 增加另一个 `DeviceTopology` 操作；
- 检查第二种 Btrfs topology transition；
- 将语义对象 schema 迁移到另一文件系统；
- 增加 persistent recovery responsibility；
- 泛化部分 child domain。

扩展必须体现冻结语义规则的复用，仅新增少量 binding。不能只用“能够重新描述多少历史 Bug”衡量泛化能力。

## 11. 下一步只做什么

下一项任务仅执行 **R1**，暂时不写分析器代码。

具体顺序：

```text
1. 提取 Bug 与 fixed 版本的 btrfs_init_new_device() 及必要 helpers。
2. 追踪 seed-to-sprout 正常路径和选定错误分区。
3. 识别 operation entry、commit/exposure/release 点和 return outcome。
4. 建立 candidate role 与源码 identity 表。
5. 严格分开正常语义证据和 Bug-derived observation。
6. 决定 v0.1 只建模 Bug #18，还是覆盖完整 #16-#18 patch series。
7. 生成三份 R1 文档，评审通过后才能定义状态。
```

必须坚持的顺序是：

> 先依据独立文件系统语义确定合法 DeviceTopology 转换，再检查 Bug 源码是否符合该转换；不能从错误源码反向定制状态机。

## 12. 首个案例完成验收表

以下问题全部回答“是”后，才能宣称首个案例完成：

```text
[ ] 分析对象是否高于原始字段，同时仍能从源码重建？
[ ] 高层对象是否至少有两个有意义的稳定状态？
[ ] 中间状态是否由操作语义支持？
[ ] 子域是否因子化，而非展开为乘积状态机？
[ ] 每条 Realize 子句是否有独立证据？
[ ] 高层与子状态是否允许以不同速率变化？
[ ] 瞬态 deadline 是否在最终结算前被检查？
[ ] failure acceptance 是否 outcome-sensitive？
[ ] unknown call、alias 和 write 是否进入 Proof Closure？
[ ] Bug/fixed 源码是否由完全相同的冻结规则处理？
[ ] 首个 differential 是否只标记为 development validation？
[ ] 独立结果是否只来自冻结后未见分区？
```

## 13. 理论定位

本架构可以吸收但不直接照搬三类工作：

- 经典 Typestate：操作是否合法取决于对象当前抽象状态。
- Path-sensitive、alias-aware OS Typestate：路径分区、对象身份和过程间状态传播。
- SquirrelFS：把文件系统特定的顺序和状态转换义务编码为可系统检查的约束。

本项目拟验证的不同贡献是：

> 从多个子元数据对象的因子化 typestate 与关系配置中重建高层语义文件系统对象状态，再使用事件 deadline 和 outcome-sensitive 允许状态检查失败路径。

在 R1-R5 真实 `DeviceTopology` 案例跑通前，这一贡献仍是待验证的方法假设，而不是已实现能力。
