# MOCC-SE 实施交接文档

> 更新时间：2026-07-21
>
> 当前主任务：M0-M7 已完成；Protocol A/B/C 均通过独立 CLI 输出版本化 JSON witness，M7 source-tree discovery 已能扫描源码树并区分 exact candidate、semantic review、analysis unknown 和 discovery quarantine。下一步继续项目开发，优先扩大可复核 finding 的质量和数量，不进入论文 benchmark 阶段。
>
> 工作目录：`E:\yanjiusheng\阅读论文\file_system\SE_EOD`

本文档是下一步编码的唯一执行入口。文档职责如下：

- [`docs/PROJECT_ARCHITECTURE.md`](docs/PROJECT_ARCHITECTURE.md)：当前已经实现的代码事实；
- [`docs/MOCC_SE_FULL_ARCHITECTURE.md`](docs/MOCC_SE_FULL_ARCHITECTURE.md)：MOCC-SE 目标方法和完整数据模型；
- [`docs/PROJECT_CLOSURE_PLAN.md`](docs/PROJECT_CLOSURE_PLAN.md)：工程、实验、论文和复现的完成门禁；
- 本文档：当前迭代具体做什么、按什么顺序做、如何验收。

发生冲突时，先以代码和测试确认当前事实，再依次更新上述文档，不能用计划文字宣布尚未实现的能力。

## 1. 当前目标

当前不继续以“增加资源泄漏候选”为主线，也不先实现完整 Clang/Kbuild 前端。当前目标是建立一个最小但完整的 MOCC-SE 分析链：

```text
协议定义
  -> 元数据事件
  -> failure/effect/accounting 状态传播
  -> 合法出口检查
  -> 协议违规候选
  -> representative witness
```

第一个纵向协议只处理 replay/recovery：

> 必要元数据恢复步骤失败后，必须传播错误、成功重试、事务中止或明确交给恢复机制；不能无处理地到达成功出口。

开发回归样例为 #1、#2、#5、#8、#13。它们是协议开发集，不是独立评估集。

## 2. 当前可复用基础

截至 2026-07-21，现有 SE-EOD 基线提供：

| 能力 | 现状 | MOCC-SE 用途 |
|---|---|---|
| 源码前端 | frontend IR schema v1、tree-sitter adapter、文本 fallback | 提供统一函数和语句输入 |
| CFG | `if`、循环、`goto`、`return`、`break`、`continue`、普通 switch | 提供错误路径和出口 |
| 数据流 | 有界析取、join、widening、路径事实 | 承载协议状态 |
| 错误条件 | errno、负值、NULL、ERR_PTR 等启发式分类 | 生成 failure event |
| 跨函数摘要 | must/may、exit class、return guard、固定点传播 | 承载协议 effect summary |
| 对象信息 | 局部 symbol、参数、简单 alias、有限字段信息 | 建立 principal object identity |
| witness | representative trace、anchors、CFG snapshot | 生成第一版协议 witness |
| 证据层 | history、manual、LLM、reviewed exception | 只用于排序和复核 |

全量测试基线为 `271 passed`（历史 SE-EOD 与 M0-M7 专项测试）。开始任何代码任务前重新运行测试，不能只依赖该历史数字。

## 3. 当前尚未实现的 MOCC-SE 能力

M0-M10 已分别实现于 `metadata_protocol.py`、`metadata_event.py`、
`metadata_tracker.py`、`metadata_candidate_rules.py` 和
`metadata_protocol_analyzer.py`。Protocol A 使用独立 CLI 输出专用 JSON，尚未接入旧
`src.main` 默认流水线，因此不得宣称旧 SE-EOD CSV/JSONL 已经自动包含 MOCC-SE 结果。
Protocol B/C MVP 已通过独立 CLI 生成版本化结果。M7-M10 已完成目录级扫描、源码
review、版本矩阵、repair evidence、bug-hunt report 和 confirmed-bug linkage。完整跨函数
handler/effect summary、通用未知 operation discovery 和冻结集评估仍未实现。

当前 A/B/C 的 `entry_functions`、callee 和 field anchors 仍来自 confirmed-bug 开发记录。
三版本 `fs/` 扫描虽然分别遍历了 8,544、12,280 和 10,302 个函数，但仅分析了 8、9 和
9 个 exact entry，`DISCOVERY_REVIEW` 均为 0。因此 M9/M10 是已知问题的回归、证据对齐
和规则开发链路，不是已经能发现新 bug 的全量语义检索。

现有 `ResourceFlowState` 不能直接改名后冒充上述模型。资源生命周期应作为 metadata effect 的兼容特化逐步接入。

## 4. 不得破坏的分析不变量

所有实现必须遵守：

1. 静态语义决定候选是否生成；history、manual、LLM 和 ranking 不得修改协议状态。
2. 未证明 compensation、commit 或 handler ownership 时，开放 effect 不能被视为完成。
3. `ABORT` 只关闭明确属于 `TRANSACTION_SCOPED` 的 effect。
4. `RECOVERY_DELEGATED` 和 `DEFERRED` 必须有对象绑定、guard 和 handler 证据。
5. `ret > 0` 不能默认解释为失败；返回语义由 return contract 决定。
6. retry 开始新的 `attempt_id`；旧 failure 不能污染新 attempt 的最终结果。
7. `must` event 只有在对象、guard、CFG 和调用摘要均可证明时才能应用。
8. alias、间接调用、CFG 或 handler 不确定时保留 uncertainty，不能解释为安全。
9. `PARTIAL_UNRESOLVED` 与 `ANALYSIS_UNKNOWN` 必须分开。
10. 输出仍是待人工复核候选，不是 confirmed bug。
11. 现有 SE-EOD 输出 schema 和历史实验默认行为不能被静默改变。
12. M11 起每个 discovery 协议必须来自可复用语义；具体函数名只能是 regression seed，
    不能作为正式发现新 bug 的唯一适用条件。

## 5. 实施顺序

当前实现分为七个里程碑：

```text
M0  协议核心数据模型
 -> M1  元数据事件提取
 -> M2  协议状态传播
 -> M3  合法出口与候选生成
 -> M4  Protocol A replay/recovery 闭环
 -> M5  Protocol B device/topology rollback
 -> M6  Protocol C activation/reservation/accounting
 -> M7  Source-tree protocol discovery 与 review/unknown 隔离
```

每个里程碑必须先通过单元测试和现有回归，再进入下一项。不要同时重写 CFG、前端和协议引擎。

## 6. M0：协议核心数据模型

### 6.1 目标

建立与具体文件系统无关、可序列化、可验证的数据结构，不接入候选生成。

建议新增：

```text
src/metadata_protocol.py
tests/test_metadata_protocol.py
configs/metadata_protocols/
```

`metadata_protocol.py` 至少定义：

```text
EffectKind
EffectScope
EffectStatus
CompletionMode
ReturnOutcome
ViolationType
ObjectRef
ReturnContract
EffectSpec
CompensationSpec
HandlerSpec
AccountingConstraint
MetadataProtocol
```

枚举初始范围：

```text
EffectScope:
  LOCAL
  IN_MEMORY_GLOBAL
  TRANSACTION_SCOPED
  PERSISTENT
  RECOVERY_OWNED
  DEFERRED_OWNED

EffectStatus:
  OPEN
  COMPENSATED
  TRANSFERRED
  COMMITTED
  UNKNOWN

CompletionMode:
  COMMITTED
  ROLLED_BACK
  ABORTED
  RECOVERY_DELEGATED
  DEFERRED
  PARTIAL_UNRESOLVED
  ANALYSIS_UNKNOWN
```

### 6.2 Schema 要求

协议配置必须能够表达：

- operation entry；
- principal object roles；
- metadata events；
- return outcome guards；
- effect scope 和 owner；
- compensation relation；
- abort/recovery/deferred handler ownership；
- legal success/failure exits；
- accounting constraints；
- Linux 版本和文件系统适用范围；
- schema version 和 protocol version。

加载器必须拒绝：

- 未知枚举；
- 重复 event ID；
- 指向不存在 effect 的 compensation；
- 没有 scope 的 effect；
- 没有 owner 的 handler transfer；
- 互相重叠且没有优先级的 return contracts；
- 未定义的 legal phase/completion mode。

### 6.3 M0 完成门禁

- 数据模型可 JSON round-trip；
- 合法和非法协议 fixture 均有测试；
- 协议 ID 和 event ID 稳定；
- schema/version 错误明确报告；
- 不改变现有候选输出；
- 全量测试通过。

## 7. M1：元数据事件提取

### 7.1 目标

将 IR 中的调用、赋值、字段更新和容器操作规范化为事件：

```text
METADATA_UPDATE
POINTER_UPDATE
MEMBERSHIP_ADD
MEMBERSHIP_REMOVE
FLAG_SET
FLAG_CLEAR
COUNTER_UPDATE
RESERVATION_UPDATE
COMMIT
COMPENSATE
ABORT
RECOVERY_DELEGATE
DEFER_CLEANUP
```

建议新增：

```text
src/metadata_event.py
tests/test_metadata_event.py
```

每个事件必须包含：

```text
event_id
protocol_id
operation_id
kind
object_ref
container_ref
field_or_member
guard
strength: must | may
source_location
uncertainty_causes
```

### 7.2 对象身份

第一阶段只支持：

```text
EXACT       同一局部 symbol、argN、return 或明确字段
NORMALIZED  由 reviewed wrapper/summary 映射
UNKNOWN     无法证明同一对象
```

`UNKNOWN` 事件可以保留证据，但不能关闭一个精确 effect。

### 7.3 M1 完成门禁

- 直接调用、字段赋值、list add/del 和 counter update 均有 fixture；
- may/unknown 不会被升级为 must；
- 同一源码输入生成确定的 event ID；
- 事件提取与现有 resource tracker 并行运行时不改变旧结果；
- 全量测试通过。

## 8. M2：协议状态传播

### 8.1 建议新增

```text
src/metadata_tracker.py
tests/test_metadata_tracker.py
```

核心状态：

```text
MetadataOperationInstance
├── protocol_id
├── principal_objects
├── phase_facts
├── effect_ledger
├── failure_tokens
├── accounting_obligations
├── completion_mode
└── uncertainty_causes
```

### 8.2 Failure epoch

failure token 至少包含：

```text
failure_id
attempt_id
source_event
error_class
resolution
status_origin
```

以下操作可以关闭 failure：

- 明确传播为失败返回；
- protocol 允许的 sentinel handling；
- 新 attempt 的成功结果覆盖；
- 事务 abort；
- 恢复机制接管。

只有在协议明确允许时才关闭；简单的 `goto retry` 本身不能证明重试成功。

### 8.3 Effect ownership

状态转移必须区分：

```text
effect created
effect compensated
effect transferred to handler
effect committed
effect becomes unknown
```

`abort_transaction()` 不允许批量关闭 `IN_MEMORY_GLOBAL` effect。该反例必须有测试。

### 8.4 Join 和 widening

- 相同 effect 在所有输入状态都完成，才能得到 definite completed；
- 一条路径 OPEN、一条路径完成，join 后为 `UNKNOWN/MAY_OPEN`；
- 不同 attempt 的 failure token 不得按文本错误码直接合并；
- widening 必须记录丢失的 phase/effect/accounting 精度；
- 达到上限时 fail-open，不能静默删除 obligation。

### 8.5 M2 完成门禁

- branch、join、retry、abort、handler transfer 和 widening 均有测试；
- #4 的 stale failure epoch 能在最小 fixture 中表达；
- #17 类型的 global effect 不会被 abort 错误关闭；
- uncertainty provenance 可序列化；
- 全量测试通过。

## 9. M3：合法出口和候选生成

建议新增：

```text
src/metadata_candidate_rules.py
tests/test_metadata_candidate_rules.py
```

### 9.1 成功出口

必须满足：

```text
没有 unresolved necessary failure
phase 属于 legal success
required effects 已 committed/transferred
accounting constraints 成立
返回值来自当前 attempt 的成功 outcome
```

### 9.2 失败出口

每个 OPEN effect 必须满足至少一种合法完成方式：

```text
COMPENSATED
由匹配对象和 scope 的 ABORT handler 接管
RECOVERY_DELEGATED
DEFERRED
```

### 9.3 候选分类

只生成：

```text
failure_reported_as_success
incomplete_failure_completion
metadata_state_divergence
```

无法证明的状态进入 `ANALYSIS_UNKNOWN` 隔离输出，不与高置信违规混合。

### 9.4 M3 完成门禁

- 三类候选各有正例、反例和 unknown fixture；
- candidate 包含 protocol、operation、对象、开放 effect 和出口；
- ranking/LLM 不参与候选存在性判断；
- 现有 SE-EOD CSV/JSONL 默认不变；
- 全量测试通过。

## 10. M4：Protocol A replay/recovery

### 10.1 开发范围

第一版协议只覆盖已知的两类控制语义：

```text
普通必要步骤：ret < 0 或 ret != 0 表示失败
sentinel 步骤：只有 -ENOENT 等特定结果允许 fallback/create
```

开发函数：

```text
ext4_fc_replay_add_range
ext4_fc_replay_del_range
ext4_fc_replay_inode
xfs_rtcopy_summary
xfs_rtginode_ensure
```

函数名只用于选择开发 fixture；真正协议必须通过 operation entry、callee role 和 return contract 匹配，不能写成“遇到这五个函数就报告”。

### 10.2 协议义务

```text
necessary replay/load/copy step fails
AND failure is not resolved by retry/sentinel/abort/recovery
AND function reaches success exit
=> failure_reported_as_success
```

### 10.3 必须覆盖的反例

- `-ENOENT` 后合法创建；
- 第一次失败、第二次 retry 成功；
- 失败被上层事务 abort 接管；
- cleanup label 返回原错误；
- 非必要的 best-effort 调用失败后允许继续；
- unresolved indirect call 进入 unknown，而非直接报告。

### 10.4 M4 完成门禁

- 五个开发函数均生成可解释结果；
- 已修复版本不再生成同一违规，或者差异有明确版本解释；
- 每个候选保留“必要步骤 -> failure -> handler/无 handler -> exit” witness；
- Protocol A 在至少一个未参与设计的函数或版本上完成冻结验证；
- 不将这五个开发 bug 计入无偏 precision/recall；
- 全量测试通过。

## 11. M5：Protocol B device/topology rollback

M4 闭合后再实现：

```text
fs_root->reloc_root
device list membership
post_commit_list membership
s_bdev/latest_dev
fs_devices seed/sprout topology
```

重点不是一般内存释放，而是 effect scope、compensation 和 handler ownership。开发回归样例为 #7、#17、#18、#19。

完成要求：

- `ABORT` 不能误关全局拓扑 effect；
- 多个 principal object 能独立跟踪；
- pointer、membership、flag/counter compensation 可配；
- 未完整回滚时生成 `incomplete_failure_completion`；
- fault-injection evidence 只用于验证和排序。

当前状态：M5 MVP 已完成。Protocol B v1 配置覆盖 relocation root、device/list
membership、post-commit may summary、active pointer 和 seed/sprout topology；9 项
专项测试覆盖修复反例、多 principal object、ABORT scope、pointer/membership/
flag/counter compensation 和 unknown 隔离。v6.8/v6.14 输出与命令保存在
`outputs/mocc-protocol-b-v1/`。这些输入属于开发与版本一致性检查，不是无偏评估集。

## 12. M6：Protocol C activation/reservation/accounting

当前状态：M6 MVP 已完成。Protocol C v1 配置覆盖 ext4 extra-isize fallback
stale return provenance，以及 Btrfs zoned chunk activation 的 boolean
reservation accounting。v6.8/v6.14/v7.1 的 ext4/Btrfs 输出与命令保存在
`outputs/mocc-protocol-c-v1/`。这些输入属于开发与版本一致性检查，不是无偏评估集。

已实现：

- 多值 return outcome；
- fallback attempt 和 stale result provenance；
- reservation/counter obligation；
- phase 与 accounting 的关系约束。

开发回归样例为 #4、#15。

第一版只证明布尔关系：

```text
pending metadata work exists
=> matching reservation exists
```

不在第一版实现任意元数据算术求解。

## 12.5 M7：Source-tree protocol discovery

当前状态：M7 开发版已完成。新增 `src/metadata_protocol_discovery.py` 和
`tests/test_metadata_protocol_discovery.py`，通过独立 CLI 扫描源码树，不接入旧
`src.main` 默认输出。

M7 提供：

- 按 `fs/<filesystem>/...` 与 protocol filesystem applicability 过滤；
- exact operation entry 分析；
- 保守 semantic operation applicability；
- `operation.discovery` 可选上下文锚点，包括 `required_callees`、
  `required_fields`、`forbidden_callees` 和 `minimum_role_coverage`；
- exact result 输出为 `PROTOCOL_CANDIDATE`；
- semantic result 输出为 `DISCOVERY_REVIEW`，不能计入 protocol-proven candidate；
- semantic analyzer unknown 输出为 `DISCOVERY_REVIEW_UNKNOWN`；
- operation 匹配并列时进入 `DISCOVERY_UNKNOWN` quarantine；
- candidate family 和 occurrence fingerprint 去重。

当前 Linux v6.8 `fs/` 开发扫描输出：

```text
outputs/mocc-discovery-v1-linux-v6.8.json
scanned_files                  278
scanned_functions              8544
applicable_functions           8
protocol_candidate_occurrences 19
protocol_candidate_families    19
discovery_review_occurrences   0
analysis_unknown               2
discovery_unknown              0
```

Protocol C 的 Btrfs activation/reservation operation 已声明 discovery-only
上下文，要求同时出现 activation 和 reservation 调用，避免把只共享
`btrfs_zoned_activate_one_bg()` 的函数误列为 review lead。

## 13. 旧 G1-G5 工作的定位

旧交接文档中的基础设施任务调整为 supporting backlog：

| 旧任务 | 当前状态 | 新定位 |
|---|---|---|
| G1 switch CFG | 已完成 | 保持回归 |
| G2-A frontend IR | 已完成 | MOCC-SE 统一输入 |
| G2-B Kbuild compile DB | 未完成 | Protocol A MVP 后增强编译真实性 |
| G2-C Clang exporter | 未完成 | 编译感知扩展，不阻塞第一版协议 |
| G3 callee effect inference | 部分完成 | 在 M1/M2 中按协议 summary 需要扩展 |
| G4 bounded field/alias | 部分完成 | Protocol B 的前置增强 |
| G5 predecessor witness | 部分完成 | M3 先复用 representative trace，后续增强 |

这些任务仍重要，但不能继续让通用前端工程无限推迟元数据协议原型。

## 14. Benchmark 和数据泄漏规则

现有材料分为：

```text
Protocol development set:
  outputs/confirmed_bugs.md
  ext4 v6.8 pilot
  已知修复和已提交补丁

Frozen evaluation set:
  协议冻结后采集
  不参与 schema、事件或规则设计
```

正式评估前必须记录：

- protocol version；
- 开发集函数和 commit；
- 冻结时间；
- test set 采样规则；
- reviewer 和 adjudication；
- unsupported/unknown 比例。

不得用已知 11 个元数据 bug 同时设计协议并报告无偏 recall。

## 15. 测试命令

每次编辑后：

```powershell
python -m compileall -q src tests
python -m pytest -q tests/test_metadata_protocol.py
git diff --check
```

每个里程碑退出前：

```powershell
python -m compileall -q src tests scripts
python -m pytest -q
git diff --check
git status --short
```

Protocol A 集成后还必须保存：

- 分析命令；
- Linux source version；
- protocol/schema version；
- candidate 和 unknown 数量；
- 每个开发函数的 witness；
- 修复前后差分。

## 16. 当前暂停项

完成 M0-M7 后仍暂不开展：

- Protocol C 之外的新协议实现；
- 大规模独立 benchmark 标注；
- 新增 LLM 调用或 prompt 调优；
- ranking 概率校准；
- GUI、自动补丁或完整 SMT；
- 全文件系统 Clang compiled-mode 覆盖；
- 正式论文表格。

历史 outputs、patch evidence 和 benchmark 文件不得删除或改写原始数字。

## 17. 下一次接手立即执行

M7 source-tree discovery 已完成。Protocol A/B/C 的开发 finding 和
`outputs/mocc-discovery-v1-linux-v6.8.json` 均不得用于报告无偏 precision/recall。

执行前：

```powershell
cd "E:\yanjiusheng\阅读论文\file_system\SE_EOD"
git status --short
python -m pytest -q
Get-Content -Encoding UTF8 docs\MOCC_SE_FULL_ARCHITECTURE.md -TotalCount 260
Get-Content -Encoding UTF8 src\metadata_protocol.py -TotalCount 320
Get-Content -Encoding UTF8 src\frontend\model.py -TotalCount 260
Get-Content -Encoding UTF8 src\function_summary.py -TotalCount 220
```

下一轮代码提交范围如继续推进，应严格限定为项目开发：

```text
M8 finding expansion loop：
  复核 M7 exact candidates 的源码语义
  找出 false-positive 原因和缺失 summary
  优先补跨函数 handler/effect/accounting summary
  在 A/B/C 内增加可复用 operation/role/context，而不是开 benchmark
```

旧 `src.main` 默认输出保持不变；Protocol A/B/C 继续通过独立入口运行。

## 18. 当前阶段 Definition of Done

Protocol A/B 阶段完成必须满足：

- [x] M0：协议模型、schema、版本和非法配置校验完成（24 项专项测试）；
- [x] M1：元数据事件及对象身份分级完成；
- [x] M2：failure epoch、effect ownership、join/widening 完成；
- [x] M3：合法出口和三类候选框架完成；
- [x] M4：replay/recovery 协议 MVP 端到端完成；
- [x] M5：device/topology rollback、scope ownership、对象级 compensation 和 may unknown 隔离完成；
- [x] M6：activation/reservation/accounting、stale return provenance 和 boolean reservation obligation 完成；
- [x] M7：source-tree discovery、semantic review 隔离、discovery quarantine、fingerprint 去重和 discovery context anchors 完成；
- [x] 五个开发函数均有稳定 witness；
- [x] 合法 retry、sentinel、abort 和 best-effort 反例不误报；
- [x] `ANALYSIS_UNKNOWN` 与真实 violation 分离；
- [x] Protocol A v1 冻结后在未参与设计的 Linux v6.14 `xfs_rtcopy_summary` 上完成版本验证；协议 SHA-256 和结果保存在 `outputs/mocc-protocol-a-v1/README.md`；
- [x] 现有 SE-EOD 默认输出和历史 186-test 基线不回退；当前全量 292 tests；
- [x] 新增能力有正例、反例、unknown 和版本差分测试；
- [x] 当前架构、完整架构、交接文档和 metadata protocol README 与代码状态一致。

M7 已满足上述门禁。下一步不是论文 benchmark，而是进入 M8 finding
expansion loop：围绕当前 exact candidates 做源码复核，补缺失 summary/operation
context，并在能复用的地方扩大 A/B/C 的项目开发覆盖。

## 19. M8 当前进度：finding expansion review queue

M8 已启动，第一件实物是从 M7 discovery report 派生的源码复核队列：

```text
src/metadata_finding_review.py
src/metadata_finding_triage.py
src/metadata_finding_matrix.py
src/metadata_function_diff.py
src/metadata_repair_evidence.py
src/metadata_bug_hunt_report.py
src/metadata_confirmed_bug_linkage.py
tests/test_metadata_finding_review.py
tests/test_metadata_finding_triage.py
tests/test_metadata_finding_matrix.py
tests/test_metadata_function_diff.py
tests/test_metadata_repair_evidence.py
tests/test_metadata_bug_hunt_report.py
tests/test_metadata_confirmed_bug_linkage.py
outputs/mocc-finding-review-v1/linux-v6.8-review-queue.json
outputs/mocc-finding-review-v1/linux-v6.8-review-queue.md
outputs/mocc-finding-review-v1/linux-v6.8-source-review-notes.json
outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.json
outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.md
outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.json
outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.md
outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-discovery-matrix.json
outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-discovery-matrix.md
outputs/mocc-finding-review-v1/xfs_rtcopy_summary-v6.8-v6.14-v7.1-function-diff.json
outputs/mocc-finding-review-v1/xfs_rtcopy_summary-v6.8-v6.14-v7.1-function-diff.md
outputs/mocc-finding-review-v1/ext4_fc_replay_inode-v6.8-v6.14-v7.1-function-diff.json
outputs/mocc-finding-review-v1/ext4_fc_replay_inode-v6.8-v6.14-v7.1-function-diff.md
outputs/mocc-finding-review-v1/linux-v6.8-repair-evidence-ledger.json
outputs/mocc-finding-review-v1/linux-v6.8-repair-evidence-ledger.md
outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-development-bug-hunt-report.json
outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-development-bug-hunt-report.md
outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-confirmed-bug-linkage.json
outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-confirmed-bug-linkage.md
outputs/mocc-finding-review-v1/README.md
```

生成命令：

```powershell
python -m src.metadata_finding_review `
  --discovery-report outputs/mocc-discovery-v1-linux-v6.8.json `
  --source-root linux-sources/linux-v6.8-fs/fs `
  --context-lines 4 `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-review-queue.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-review-queue.md
```

队列摘要：

```text
review_items        19
protocol_candidates 19
discovery_reviews   0

Protocol A 15
Protocol B  2
Protocol C  2
```

每个 review item 包含 witness、源码上下文、unresolved failure、open effect、
accounting state、review focus 和 likely summary gap。该队列是项目开发材料，
不是 frozen benchmark。

M8 第二件实物是 development source-review annotation pass：

```powershell
python -m src.metadata_finding_review `
  --discovery-report outputs/mocc-discovery-v1-linux-v6.8.json `
  --source-root linux-sources/linux-v6.8-fs/fs `
  --context-lines 4 `
  --annotations outputs/mocc-finding-review-v1/linux-v6.8-source-review-notes.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.md
```

当前源码复核注释摘要：

```text
review_items             19
reviewed_items           19
unreviewed_items          0
likely_true_candidate    19
high confidence          17
medium confidence         2
unmatched_annotations     0
conflicting_annotations   0
```

解释约束：

- 这些是项目开发期 source-supported candidate notes，不是 confirmed bug label；
- Protocol A 重复 occurrence 按函数族注释，后续不能把 15 个 occurrence 直接当作
  15 个独立 root-cause bug；
- Protocol B 两条为 medium confidence，因为本地路径支持候选，但正式声称 bug 前
  仍需 fixed-version 或 patch context；
- 当前 19 条复核没有发现需要立即补 summary/front-end 的 false positive，下一步应
  转向跨版本确认、扩展到 v6.14/v7.1 或增加新的 A/B/C operation context。

M8 第三件实物是 initial source triage ledger：

```powershell
python -m src.metadata_finding_triage `
  --review-queue outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.md
```

当前 triage 摘要：

```text
triage_items                       19
reviewed_items                     19
unreviewed_items                    0
candidate_survives_initial_review  19

mocc.protocol_a.replay_recovery     15
mocc.protocol_b.device_topology_rollback 2
mocc.protocol_c.activation_accounting    2
```

`metadata_finding_triage` 可以从 reviewed queue 的 `source_review` 自动派生
decisions，也可以通过 `--decisions` 合并逐 `review_id` 的人工决策文件。

M8 第四件实物是 development cross-version discovery matrix：

```powershell
python -m src.metadata_finding_matrix `
  --report v6.8=outputs/mocc-discovery-v1-linux-v6.8.json `
  --report v6.14=outputs/mocc-discovery-v1-linux-v6.14.json `
  --report v7.1=outputs/mocc-discovery-v1-linux-v7.1.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-discovery-matrix.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-discovery-matrix.md
```

矩阵摘要：

```text
v6.8  candidates 19, unknown 2
v6.14 candidates 20, unknown 2
v7.1  candidates 14, unknown 3

persistent candidate functions:
  ext4_fc_replay_add_range
  ext4_fc_replay_del_range
  btrfs_recover_relocation
  btrfs_init_new_device
  reserve_chunk_space
  ext4_expand_extra_isize_ea

candidate removed/cleared by v7.1:
  ext4_fc_replay_inode
  xfs_rtcopy_summary

candidate added after v6.8:
  xfs_rtginode_ensure
```

下一轮 M8 的优先级应改为：

1. 对 `ext4_fc_replay_inode` 和 `xfs_rtcopy_summary` 做 v6.8/v6.14 -> v7.1
   source diff，提取真实修复语义；
2. 对 persistent candidates 做 patch/fixed-version context 查证，尤其是 Protocol B
   两条 medium-confidence 候选；
3. 复核 `xfs_rtginode_ensure` 为什么在 v6.14/v7.1 新增，判断是新增 finding 还是
   operation/context 扩展带来的开发线索。

M8 第五件实物是 function-level repair diff：

```powershell
python -m src.metadata_function_diff `
  --function xfs_rtcopy_summary `
  --source v6.8=linux-sources/linux-v6.8-fs/fs/xfs/xfs_rtalloc.c `
  --source v6.14=linux-sources/linux-v6.14-fs/fs/xfs/xfs_rtalloc.c `
  --source v7.1=linux-sources/linux-v7.1-fs/fs/xfs/xfs_rtalloc.c `
  --out-json outputs/mocc-finding-review-v1/xfs_rtcopy_summary-v6.8-v6.14-v7.1-function-diff.json `
  --out-md outputs/mocc-finding-review-v1/xfs_rtcopy_summary-v6.8-v6.14-v7.1-function-diff.md
```

```powershell
python -m src.metadata_function_diff `
  --function ext4_fc_replay_inode `
  --source v6.8=linux-sources/linux-v6.8-fs/fs/ext4/fast_commit.c `
  --source v6.14=linux-sources/linux-v6.14-fs/fs/ext4/fast_commit.c `
  --source v7.1=linux-sources/linux-v7.1-fs/fs/ext4/fast_commit.c `
  --out-json outputs/mocc-finding-review-v1/ext4_fc_replay_inode-v6.8-v6.14-v7.1-function-diff.json `
  --out-md outputs/mocc-finding-review-v1/ext4_fc_replay_inode-v6.8-v6.14-v7.1-function-diff.md
```

当前函数 diff 结论：

```text
xfs_rtcopy_summary:
  v6.8 -> v6.14: no source changes
  v6.14 -> v7.1: return 0 -> return error
  hints: local_return_propagation_repair, return_success_changed_to_error_symbol,
         added_corruption_guard

ext4_fc_replay_inode:
  v6.8 -> v6.14: no source changes
  v6.14 -> v7.1: return 0 -> return ret
  hints: local_return_propagation_repair, return_success_changed_to_error_symbol
```

这给下一步 Protocol A 开发一个清晰方向：把“错误路径最终成功返回 -> 后续版本改为传播
错误符号”的 repair pattern 纳入 development evidence/版本确认，而不是为单个函数写例外。

M8 第六件实物是 repair evidence ledger：

```powershell
python -m src.metadata_repair_evidence `
  --triage outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.json `
  --function-diff outputs/mocc-finding-review-v1/xfs_rtcopy_summary-v6.8-v6.14-v7.1-function-diff.json `
  --function-diff outputs/mocc-finding-review-v1/ext4_fc_replay_inode-v6.8-v6.14-v7.1-function-diff.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-repair-evidence-ledger.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-repair-evidence-ledger.md
```

当前 repair evidence 摘要：

```text
triage_items                 19
items_with_repair_evidence    7
items_without_repair_evidence 12
repair_evidence_functions:
  ext4_fc_replay_inode
  xfs_rtcopy_summary

by_repair_hint:
  local_return_propagation_repair       7
  return_success_changed_to_error_symbol 7
```

解释约束：repair evidence 是 development evidence，用于排序和指导下一步 patch/source
context 查证；不能直接当 confirmed bug，也不能计入 frozen benchmark label。

M9 第七件实物是 development bug-hunt report：

```powershell
python -m src.metadata_bug_hunt_report `
  --reviewed-queue outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.json `
  --triage outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.json `
  --matrix outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-discovery-matrix.json `
  --repair-evidence outputs/mocc-finding-review-v1/linux-v6.8-repair-evidence-ledger.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-development-bug-hunt-report.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-development-bug-hunt-report.md
```

当前 M9 bug-hunt report 摘要：

```text
review_items                       19
candidate_survives_initial_review  19
items_with_repair_evidence          7
persistent_candidate_occurrences   12
removed_or_cleared_functions        2
added_functions_to_inspect          1

Priority 1:
  ext4_fc_replay_inode              5 occurrences, repair evidence
  xfs_rtcopy_summary                2 occurrences, repair evidence

Priority 2:
  reserve_chunk_space
  btrfs_recover_relocation
  btrfs_init_new_device
  ext4_fc_replay_add_range
  ext4_fc_replay_del_range
  ext4_expand_extra_isize_ea

Priority 3:
  xfs_rtginode_ensure               added after v6.8, inspect operation context
```

这是当前“已知协议实例的项目开发回归与证据汇总”主入口；仍不是论文 benchmark，也不是
未知函数的全量元数据 bug discovery。

如果回到单版本 v6.8 review queue，按以下顺序做源码复核：

1. `metadata_state_divergence`：先看 `reserve_chunk_space` 和
   `ext4_expand_extra_isize_ea`，判断是潜在 finding 还是缺失 accounting/return
   summary。
2. `incomplete_failure_completion`：复核 Btrfs relocation/sprout 两条，判断是否缺
   compensation/handler summary。
3. `failure_reported_as_success`：批量复核 ext4/xfs replay 族，提取可复用的
   retry/sentinel/return-propagation summary，而不是逐函数硬编码例外。

## 20. M10 当前进度：confirmed bug linkage

M10 已完成开发期 confirmed bug linkage：

```powershell
python -m src.metadata_confirmed_bug_linkage `
  --bug-hunt-report outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-development-bug-hunt-report.json `
  --confirmed-bugs outputs/confirmed_bugs.md `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-confirmed-bug-linkage.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-confirmed-bug-linkage.md
```

当前结果：

```text
candidate queue entries                 22
queue entries linked to confirmed bugs  22
unique confirmed bug records             18
unique confirmed records linked          11
confirmed records outside M9 queue         7

linked status:
  submitted                               7
  submitted + Reviewed-by                 1
  accepted into for-next                  1
  fixed duplicate                         2
```

这里的 22 是 occurrence/priority-queue 条目，不是 22 个独立 root-cause bugs。链接覆盖的
11 条唯一 confirmed records 是 #1、#2、#4、#5、#7、#8、#13、#15、#16、#17、#18。
未进入本轮 M9 队列的 #3、#6、#9、#10、#11、#12、#14 仍然是 confirmed records；它们
只是不在当前 A/B/C 队列中，不能改写成待确认项，也不能据此计算 benchmark recall。

## 21. M11：protocol generalization and fresh discovery

M11 的目标不是继续把 `confirmed_bugs.md` 中的新函数加入 A/B/C，而是将现有规则从
function-instance specification 改为可迁移的 operation pattern，并首次生成排除开发集后的
fresh candidate queue。

当前事实：

```text
v6.8  scanned functions  8544  applicable functions 8  DISCOVERY_REVIEW 0
v6.14 scanned functions 12280  applicable functions 9  DISCOVERY_REVIEW 0
v7.1  scanned functions 10302  applicable functions 9  DISCOVERY_REVIEW 0
```

这说明当前瓶颈在 discovery gate，而不是 confirmed-bug review：绝大多数函数没有进入
`analyze_function(...)`。M11 必须按以下顺序推进：

1. 将 `entry_functions` 改为 optional regression seed；新增不依赖函数名的 broad operation
   discovery，基于 return provenance、state mutation、failure exit、compensation 和
   accounting relation 生成 `DISCOVERY_REVIEW`。
2. 保持两阶段输出：宽松语义匹配只进入 review queue，只有完整协议状态检查支持的结果才
   能升级为 `PROTOCOL_CANDIDATE`。
3. 增加 `--exclude-confirmed-functions` 或同等机制，默认排除 `confirmed_bugs.md` 中的
   函数及开发 seed；按 function/root-cause 聚合生成 fresh queue。
4. 在工程测试中执行 leave-one-function-out：删除一个 seed 函数名和其专属 anchor 后，规则
   必须仍能以语义方式把该函数送入 review queue。这个检查用于开发泛化，不是论文 benchmark。
5. 只对 fresh queue 做源码复核、版本 diff 和 patch/reproduction；确认后才新增
   `confirmed_bugs.md` 记录，绝不把 static candidate 自动标为 bug。

M11 Definition of Done：至少一个被排除的已知函数能通过非 exact-entry 语义路径进入
`DISCOVERY_REVIEW`，并且在排除全部 confirmed functions 后，full `fs/` 扫描能输出一个
去重后的 fresh review queue。未满足前，不能声称工具已能发现真正新 bug。

清理记录（2026-07-21）：删除无引用的
`outputs/mocc-finding-review-v1/linux-v6.8-initial-triage-decisions.json`，因为当前 triage
从 reviewed queue 内嵌的 `source_review` 直接派生 decisions，最终 triage report 已保存结论。
Python/pytest cache 已在 `.gitignore` 中排除、可随时再生，不是项目产物；历史 baseline、
benchmark、A/B/C 回归证据和 M8-M10 产物均保留。
