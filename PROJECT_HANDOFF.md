# SE-EOD 代码完善阶段交接文档

> 更新时间：2026-07-18
>
> 工作目录：`E:\yanjiusheng\阅读论文\file_system\SE_EOD`
>
> 当前阶段：优先补齐分析器代码能力，不启动论文 benchmark、正式 baseline、排名校准和论文表格工作。

本文档是当前代码开发的第一入口。当前实现事实以 [`docs/PROJECT_ARCHITECTURE.md`](docs/PROJECT_ARCHITECTURE.md) 为准，完整项目闭合条件以 [`docs/PROJECT_CLOSURE_PLAN.md`](docs/PROJECT_CLOSURE_PLAN.md) 为准。本交接文档只回答一个问题：**下一步怎样按顺序把分析器本身完善。**

---

## 1. 当前阶段的一句话目标

先完成闭合计划第 3.2 节定义的代码缺口 G1--G5：

```text
G1  完整 switch/case/default CFG
  -> G2  统一前端 IR + Kbuild/Clang compiled mode
  -> G3  一般 callee CFG 的 success/error effect 自动推导
  -> G4  有限字段路径和 alias
  -> G5  可重建 predecessor witness
  -> 配置生命周期与全链路工程加固
```

在 G1--G5 完成以前，暂不把以下事项作为主任务：

- 独立 gold benchmark；
- 双 reviewer 标注和 Cohen's kappa；
- Precision、Recall、F1、P@K；
- Hector-like 或外部工具 baseline；
- B0--Full 论文消融；
- ranking 概率校准；
- 新增 LLM 能力；
- 论文表格、投稿文稿和 artifact release；
- 扩展更多候选类型或更多文件系统。

“暂不做 benchmark”不等于“不写测试”。每个代码阶段仍必须增加单元测试、端到端测试和真实 Linux 代码 golden fixture；这些属于工程正确性验证，不作为论文指标或 gold label。

---

## 2. 当前可核验快照

截至本次交接：

| 项目 | 当前值 |
|---|---|
| Git branch | `main` |
| Git HEAD | `c5f8122` (`API 配置漂移审计`) |
| 全量测试 | `186 passed` |
| 主前端 | frontend IR schema v1 + tree-sitter adapter，文本 fallback |
| CFG | 支持 if、loop、goto、return、break、continue 和普通 switch/case/default；GNU case range/prelude 精确降级 |
| 跨函数 | effect summary、不动点、SCC provenance、reviewed seed、部分自动 wrapper |
| 资源语义 | instance、validity、must/may、transfer/escape、multiplicity/cardinality、aggregate membership |
| witness | snapshot、representative trace、anchors；不是完整 predecessor graph |
| 配置防护 | resource config audit、API drift audit |

当前工作树可能包含闭合计划和相关文档的未提交修改。接手时必须先执行：

```powershell
git status --short
git diff --stat
git diff -- PROJECT_HANDOFF.md docs/PROJECT_CLOSURE_PLAN.md docs/PROJECT_ARCHITECTURE.md
```

不要覆盖、回退或清理不属于当前代码任务的用户修改。

---

## 3. 当前能力边界

### 3.1 已经完成的代码基础

当前代码已经具备：

- tree-sitter 函数和 statement 抽取；
- 函数内 CFG、label/goto 和 scope unwind；
- 有界析取数据流、join、widening 和截断诊断；
- acquire/release、acquire validity 和失败路径细化；
- obligation 级资源 ID、generation 和局部 symbol ID；
- `ACQUIRED/MAY_ACQUIRED/RELEASED/TRANSFERRED/ESCAPED` 生命周期；
- 简单 alias、函数指针目标和未知间接调用保守处理；
- summary effect 的 `must/may`、`success/error/any`、return guard 和 pending application；
- 循环 multiplicity、release cardinality、aggregate identity 和 membership fact；
- uncertainty cause、quarantine、CFG slice completeness 和 witness snapshot；
- 静态语义与 protocol/history/LLM ranking 隔离；
- API 配置漂移审计。

这些能力是 G1--G5 的基础，不应在后续重构中被削弱或重新实现成另一套平行逻辑。

### 3.2 仍需完成的代码缺口

| 缺口 | 现状 | 目标 | 当前优先级 |
|---|---|---|---|
| G1 switch CFG | 已完成；普通 case/default/fallthrough/break/continue/no-match 和 10 个 ext4 golden | 保留 GNU case range/prelude 精确 unsupported | 已完成 |
| G2-A 统一 IR | schema v1、tree-sitter adapter、稳定 ID、round-trip/golden/parity | 供 Clang adapter 复用 | 已完成 |
| G2-B 编译上下文 | IR 预留 `compile_command=null`，尚不执行 Kbuild | 可重建 compile database 及覆盖诊断 | 当前立即执行 |
| G3 callee effect | reviewed seed、简单 wrapper 和有限自动推导 | 从一般 callee return states 推导出口分类 effect | G2 后执行 |
| G4 field/alias | 简单局部 alias 和保守 field escape | 有界 access path 和明确 unknown 降级 | G3 后执行 |
| G5 witness | representative trace | 紧凑 predecessor state graph | G4 后执行 |

闭合计划中的 G6--G9 是 benchmark、baseline、artifact 和 related work 缺口，当前阶段明确延后。

注意：这里的“缺口 G1--G5”来自闭合计划第 3.2 节，不要与闭合计划“工作流 G：工程与复现”中的 `G-01` 等任务编号混淆。

---

## 4. 不得破坏的分析不变量

后续所有代码修改必须遵守以下规则：

1. `cleanup_calls` 只用于展示，资源是否解除由 CFG 状态传播决定。
2. protocol、wrapper hint、ownership hint、history、manual 和 LLM 不得修改静态资源状态。
3. 未证明 release/transfer 时必须保留义务；未知不能解释为安全。
4. CFG 不完整、summary may、未知 alias、widening 和未知 guard 必须保留 uncertainty provenance。
5. 自动 `must` effect 必须有可审计证明；不满足条件时降级为 `may`。
6. success/error effect 必须等待调用返回边事实证明，不能在 call block 提前应用。
7. pending effect 必须绑定 call site、result symbol、definition version 和 scope。
8. `multiplicity=many` 不能被普通 `cardinality=one/unknown` 全部解除。
9. aggregate `all` release 必须有 reviewed aggregate identity 或已证明 membership fact。
10. 一个错误路径上的多个 obligation 必须保持独立 ID，不能退回 path 级单候选。
11. 主输出与 quarantine 必须继续分离；降级不能变成静默丢弃。
12. 新前端必须复用同一资源状态和候选规则，不能产生 tree-sitter/Clang 两套语义实现。
13. 输出 schema 或 ID 算法变化必须显式版本化，并说明迁移影响。
14. 为减少候选而增加的 suppression 不能代替语义修复。

如果某项修改与这些不变量冲突，应先修改设计，而不是放宽测试。

---

## 5. 代码执行总顺序

严格按以下顺序推进：

1. 建立当前代码快照和针对 G1 的失败测试。
2. 完成 G1 switch CFG。
3. 建立 G2 统一前端 IR，先迁移 tree-sitter。
4. 接入 Kbuild compile commands。
5. 实现 Clang compiled mode 和前端 coverage 诊断。
6. 完成 G3 一般出口敏感 callee effect。
7. 完成 G4 有限字段路径和 alias。
8. 完成 G5 predecessor witness。
9. 加固配置 lifecycle、determinism、schema 和端到端回归。
10. 代码能力冻结后，再回到闭合计划处理 benchmark 和论文实验。

不能为了追求“并行完成”同时重写 CFG、IR 和 resource tracker。每一步先建立适配层和回归边界，再进入下一步。

---

## 6. G1：完整 switch/case/default CFG

**状态：已完成（2026-07-18）。** 实现位于 `src/cfg.py::_switch_statement()`，标准 case/default 不再仅因节点类型进入 unsupported。新增 edge kind 为 `switch_case/switch_default/switch_no_match/case_fallthrough`，资源边传播会保留标准 case/default 谓词。GNU case range 记录为 `case_range`，switch prelude/宏恢复残片记录为 `switch_prelude`。工程 golden 见 `tests/fixtures/switch_cfg_linux_ext4_v6_14.json` 和 `tests/test_switch_cfg_linux_golden.py`。

### 6.1 当前实现位置

主要文件：

- `src/cfg.py`；
- `tests/test_cfg.py`；
- `tests/test_cfg_resource_flow.py`；
- `src/resource_tracker.py`；
- `src/error_path_extractor.py`。

本节后续条目保留为 G1 的实现与验收记录，不再是待执行任务。

### 6.2 实现要求

G1 必须支持：

- switch 条件只求值一次；
- 每个 `case` 有独立入口；
- `default` 有独立入口；
- 多个 case 共享同一语句体；
- case 到下一个 case 的 fallthrough；
- 没有 default 时存在 no-match 出口；
- `break` 跳到最近 switch 出口；
- switch 中循环的 `continue` 仍指向循环 header；
- 循环中的 switch `break` 只退出 switch；
- 嵌套 switch 的 break target 正确；
- case 内 `goto cleanup`、`return` 和 scope unwind 正确；
- 暂时不能求值 case 值时保留所有可达分支；
- GNU case range 等未支持结构继续进入精确 unsupported range。

建议增加明确 edge kind：

```text
switch_case
switch_default
switch_no_match
case_fallthrough
```

edge condition 应保留 switch expression 与 case value，例如 `mode == 1`。这些条件后续可以进入 path facts，但 G1 不需要实现一般 case 表达式求值器。

### 6.3 推荐实现步骤

1. 用小型测试打印 tree-sitter 的 switch/case AST，确认当前 tree-sitter-c 版本的真实节点层次。
2. 在 `_CFGBuilder` 中增加独立 `_switch_statement()`，不要继续在通用 `_sequence()` 中靠字符串猜 case。
3. 创建 switch condition block 和 switch exit block。
4. 收集有序 case/default clauses，分别构建 clause body fragment。
5. 将 switch condition 连到每个 case/default 入口。
6. 将 clause 的 fallthrough exit 连到下一个 clause，而不是 switch exit。
7. 将 clause 内 break target 绑定到当前 switch exit；continue target 原样继承外层循环。
8. 没有 default 时增加 no-match edge。
9. 保留 return/goto 等非 fallthrough exits。
10. 删除已完整支持节点的 unsupported 标记，并保留仍未支持子结构的范围。

### 6.4 必须新增或修改的测试

至少覆盖：

- 单 case 命中和 no-match；
- 多 case + default；
- 两个 case 共享 body；
- 显式 fallthrough；
- 每个 case 单独 break；
- 嵌套 switch；
- loop 内 switch；
- switch 内 loop；
- case 内 goto cleanup；
- case 内 acquire，不同 case 分别 release/不 release；
- case fallthrough 后 release；
- switch 后统一 cleanup；
- unsupported GNU case range 的精确降级；
- 原有 `test_incomplete_cfg_on_candidate_slice_forces_low_confidence` 改为验证完整 switch 不再降级；
- unrelated unsupported slice 的现有行为继续成立。

### 6.5 G1 完成门禁

以下条件已全部满足：

- `switch_statement` 和普通 `case_statement` 不再出现在 unsupported nodes；
- switch golden tests 覆盖上述控制流；
- switch 中的资源状态候选符合人工预期；
- 原有 169 个测试与 9 个 G1 新增测试全部通过（当前共 178 个）；
- 对真实 Linux 文件系统至少 10 个 switch 函数建立工程 golden fixture；
- 候选或置信度发生变化时有差分说明，不使用候选减少作为正确性证明；
- `docs/PROJECT_ARCHITECTURE.md` 更新当前 switch 能力和残余边界。

### 6.6 G1 禁止的捷径

- 把整个 switch 当成一个顺序 compound block；
- 所有 case 都直接连接 switch exit，丢失 fallthrough；
- 把 switch 内所有 `break` 或 `continue` 都连到函数 exit；
- 实现后直接删除 unsupported 标记但不增加资源流测试；
- 通过扩大 quarantine 掩盖错误 CFG。

---

## 7. G2：统一前端 IR、Kbuild 和 Clang compiled mode

G2 是一个大任务，必须拆成四个可独立验收的子阶段，不能直接把 `parser.py` 替换成 Clang 调用。

### 7.1 G2-A：定义统一前端 IR

**状态：已完成（2026-07-19）。** 实现位于 `src/frontend/`，主流程已切换为 `TreeSitterFrontend -> TranslationUnitIR -> FunctionIR`。`Function/AstNode` 保留兼容别名，CFG 数据类已是 `ControlFlowGraphIR/BasicBlockIR/CFGEdgeIR`。专门测试覆盖 schema 拒绝、JSON round-trip、跨 root 稳定 ID、symbol/call/access-path、ERROR/text fallback diagnostics、CFG 序列化、semantic golden 和旧/新候选/summary 逐字段等价。

目标：资源分析不再直接依赖 tree-sitter 节点对象。

建议新增：

```text
src/frontend/__init__.py
src/frontend/model.py
src/frontend/base.py
src/frontend/tree_sitter_frontend.py
tests/test_frontend_ir.py
```

IR 至少表达：

- translation unit ID 和源码文件；
- function ID、名称、参数、返回类型和 source range；
- statement/expression kind；
- normalized text 和 source spelling；
- 直接调用、间接调用和可能目标；
- declaration/local symbol/type identity；
- lvalue/access path；
- CFG block/edge/condition；
- macro spelling/expansion location；
- frontend quality、unsupported feature 和 diagnostic。

实施约束：

- 先写 tree-sitter adapter，使现有主流程使用 IR；
- 保留兼容层，按模块逐步迁移；
- 不在迁移时重写资源语义；
- IR schema 必须有版本号；
- IR 必须可序列化，便于前端 golden 和差分。

G2-A 门禁：

- tree-sitter 主流程完全通过统一 IR；
- 现有候选和 summary 的差分为空或逐项解释；
- resource tracker 不再读取 tree-sitter 私有节点字段；
- IR round-trip 和 schema tests 通过。

### 7.2 G2-B：Kbuild compile commands

目标：获取真实内核构建参数，而不是自行拼 include/define。

第一阶段只固定一个可重建环境：

```text
Linux tag: 先选择仓库已有且源码完整的一个版本
Architecture: x86_64
Compiler: 固定 Clang 主版本
Config: 仓库保存 config 或生成步骤及 SHA-256
```

需要实现：

- 生成或导入 `compile_commands.json`；
- 规范化 command、directory 和 file；
- 将 translation unit 映射到 compile command；
- 记录没有进入当前 Kconfig build 的 `.c` 文件；
- 输出 compiler/config/compile database hash；
- 检查重复或缺失 command；
- 在 Linux/WSL/容器中可重建。

建议新增：

```text
src/compile_db.py
scripts/prepare_kernel_compile_db.py
tests/test_compile_db.py
```

Windows 可以继续开发 Python 主程序，但 Kbuild 与 Clang 集成验收必须在 Linux、WSL2 或固定容器中完成。

### 7.3 G2-C：Clang frontend exporter

最低闭合目标：

- 使用 compile command 完成预处理和类型检查；
- 导出 typed function、parameter、local declaration 和 call；
- 导出 field/member/access path；
- 导出函数内 CFG；
- 保留 spelling 与 macro expansion location；
- 区分直接调用和函数指针调用；
- 转换为 G2-A 的统一 IR。

推荐采用固定版本 Clang LibTooling 小型 exporter，不要求把整个项目迁移为 C++。Python 负责调度、读取 exporter JSON 和后续资源分析。

失败策略：

- exporter 失败不得静默回退；
- 可回退 tree-sitter，但必须记录 `frontend_mode`、失败原因和受影响函数；
- typed facts 缺失时不能伪造确定 alias 或 must effect；
- macro/inline 来源必须可以在 witness 中定位。

### 7.4 G2-D：前端覆盖和 parity

每次 compiled run 至少输出：

- 目标 `.c` 数；
- 进入 Kbuild 的 translation unit 数；
- compile command 成功/失败数；
- Clang AST/CFG 成功/失败数；
- tree-sitter fallback 函数数；
- unsupported/diagnostic 分类；
- tree-sitter 与 Clang 的函数、call、CFG 和候选差分。

G2 完成门禁：

- 统一 IR 稳定；
- compile database 可重建；
- Clang frontend 能分析选定文件系统的真实 translation units；
- 失败和 fallback 可量化；
- tree-sitter 保留为明确的 source-level/fallback mode；
- 主资源传播只有一套实现；
- 全量测试和 frontend golden 通过；
- 架构文档更新两种 frontend 的能力边界。

---

## 8. G3：一般 callee CFG 的出口敏感 effect

### 8.1 目标

从 callee 的真实 CFG return states 自动推导：

```text
resource: argN | return | *argN | bounded field path
action: acquire | release | transfer | escape
strength: must | may
exit_class: success | error | any | unknown
return_guard: normalized predicate
cardinality: one | all | unknown
```

### 8.2 主要修改位置

- `src/function_summary.py`；
- `src/resource_tracker.py`；
- `src/resource_state.py`；
- `src/dataflow.py`；
- `tests/test_interprocedural.py`；
- 新增独立 summary inference fixture/test 文件。

### 8.3 推导规则

1. 收集 callee 所有可达 return state。
2. 将 return 分类为 success、error 或 unknown。
3. 按出口类分别聚合参数、返回值和 out-parameter 的资源动作。
4. 同一出口类所有可达状态都存在同一动作，且 CFG 完整、无 widening、映射精确时，才允许生成 `must`。
5. 只有部分状态成立或存在不确定性时生成 `may`。
6. 不同出口类的动作不得合并成无条件 `any must`。
7. 调用点继续创建 pending effect，等待 caller edge fact 证明 return guard。
8. result 变量重赋值、symbol version 改变或离开 scope 时，旧 pending effect 失效。
9. reviewed seed 与自动推导冲突时输出 diagnostic，不能任意覆盖。
10. SCC 未收敛时自动派生 must 降为 may，原始 reviewed seed 保留来源。

### 8.4 必须覆盖的测试

- success 才 transfer；
- error 才 release；
- success 和 error 都 release；
- 两个 success return 只有一个 release；
- return local variable；
- 条件 return expression；
- out-parameter acquisition；
- non-first argument release；
- wrapper 到 wrapper 的 guard remap；
- alias 不精确时降为 may；
- unsupported switch/CFG 时禁止自动 must；
- recursive SCC 收敛和不收敛；
- caller result 重赋值使 pending effect 失效；
- reviewed/automatic effect 冲突诊断。

### 8.5 G3 完成门禁

- 自动 effect 有稳定 schema 和 provenance；
- 每个自动 must 可以通过 callee return witness 重建；
- 所有反例不会生成过强 must；
- 关闭自动推导后能够做工程差分，但暂不要求论文消融指标；
- 现有 reviewed seed 行为不回退；
- 全量测试通过，架构文档更新。

---

## 9. G4：有限字段路径和 alias

### 9.1 范围

不实现完整 points-to，先实现有界、可解释的 access path：

```text
arg0
arg0->field
arg0->field.subfield
local.field
*arg1
return
```

### 9.2 建议数据模型

新增结构化 `AccessPath`，不要继续用任意字符串做字段匹配：

```text
root_kind: local | parameter | return | unknown
root_id: symbol ID / arg index
dereference_depth
fields: ordered field names
index: constant | normalized symbol | unknown
casts: ignored-safe | type-changing | unknown
precision: exact | bounded | unknown
```

最大字段深度必须配置化并进入运行 manifest。

### 9.3 语义规则

- 简单 `a = b` 传播 root identity；
- `&obj->field` 与对应解引用规范化到相同 access path；
- 常量数组索引可以精确，未知索引不得假装相同或不同；
- 字段 store 默认保留 `MAY_ACQUIRED/field_store_without_contract`；
- reviewed 或自动 summary 证明后才 transfer/release；
- `container_of`、union、复杂 cast 和指针算术进入 explicit unknown；
- join 时不同精确路径不能错误合并成已释放；
- access path 必须映射到 obligation/resource ID，而不只映射 release 名称。

### 9.4 主要修改位置

- `src/resource_expr.py`；
- `src/resource_release.py`；
- `src/resource_tracker.py`；
- `src/function_summary.py`；
- G2 的 frontend IR；
- 新增 `src/access_path.py` 和对应测试。

### 9.5 G4 完成门禁

- access path 有结构化 schema、canonical form 和测试；
- struct member、nested field、out-parameter、取地址和简单 alias 正确；
- unknown index/cast/container 不产生过强 release/transfer；
- summary 可以表达 bounded field path；
- exact/bounded/unknown 数量进入 diagnostics；
- 全量测试通过，架构文档更新。

---

## 10. G5：可重建 predecessor witness

### 10.1 目标

给定一个 candidate/obligation ID，仅使用输出 artifact 就能回答：

- 资源在哪里获取；
- acquire validity 如何成立或为何未知；
- 经过哪些 CFG edge；
- 哪些调用产生 summary/pending effect；
- 哪些分支发生 join；
- 是否发生 widening/truncation；
- 为什么到错误 return 时仍为 `ACQUIRED/MAY_ACQUIRED`。

### 10.2 建议数据结构

每个保留状态增加稳定 witness node：

```text
state_id
block_id
edge_id
parent_state_ids
transfer_event
resource_state_digest
path_fact_digest
join_kind
widening_metadata
truncated
```

完整状态内容可以去重存储，witness node 只引用 digest，避免输出成倍膨胀。

### 10.3 行为要求

- 普通 transfer 保存单 parent；
- join 保存所有参与当前结论的 parent IDs；
- widening 保存被合并状态的摘要和阈值；
- 每个候选输出至少一条 acquire-to-exit 持有链；
- `MAY_ACQUIRED` 若来自 release/held 分歧，输出两条代表链；
- pending effect 记录创建、证明应用或失效事件；
- scope unwind 记录 binding 恢复；
- 图大小有上限；达到上限时明确 `witness_truncated=true`；
- representative trace 可保留作快速展示，但不能再冒充完整 witness。

### 10.4 主要修改位置

- `src/dataflow.py`；
- `src/resource_tracker.py`；
- `src/resource_state.py`；
- `src/error_path_extractor.py`；
- CSV/JSONL 输出 schema；
- `tests/test_cfg_resource_flow.py`；
- `tests/test_interprocedural.py`。

### 10.5 G5 完成门禁

- branch、join、loop、widening、pending effect、scope unwind 均有 witness 测试；
- candidate 可重建 acquire-to-exit 链；
- witness 截断不改变静态资源结论，只影响可解释性标记；
- 输出增长有统计和上限；
- ID 在相同输入和环境中确定；
- 全量测试通过，架构文档更新。

---

## 11. G1--G5 后的代码加固

G1--G5 完成后，先做一轮工程收口，再进入 benchmark。

### 11.1 配置 lifecycle

- resource map 增加 schema version；
- semantic contract 记录来源、reviewer 和适用 Linux 范围；
- API drift issue 支持 reviewed resolution 状态；
- rename、alias、wrapper、removed、unrelated、unknown 分类稳定；
- 配置变化输出机器可读 diff；
- high severity drift 必须处理或显式接受；
- hint 不能自动升级为 semantic effect。

### 11.2 Determinism

- 文件枚举顺序不影响 function/candidate/obligation ID；
- summary effect 顺序稳定；
- SCC 和 fixed-point 输出稳定；
- repeated run 输出除时间字段外可比较；
- schema 变化有迁移说明。

### 11.3 性能边界

- CFG state、summary effect、access path 和 witness node 均有独立上限；
- 每种 widening/truncation 有统计；
- 限制触发后采用 fail-open 状态，不静默解除资源；
- 小型 fixture 保持快速，全量 Linux 扫描才允许较长运行。

### 11.4 端到端 compiled-mode smoke

至少固定：

- 一个真实 Linux tag；
- 一个文件系统；
- 一组 Kbuild translation units；
- tree-sitter 与 Clang 两种前端；
- summary、candidate、quarantine、API drift 和 witness 输出。

这一步只验证代码链路稳定，不进行正式 Precision/Recall 评估。

---

## 12. 测试与验证命令

### 12.1 每次编辑后的最小检查

```powershell
python -m compileall -q src tests
python -m pytest -q tests/test_cfg.py tests/test_cfg_resource_flow.py
git diff --check
```

### 12.2 G2/G3/G4/G5 对应测试

```powershell
python -m pytest -q tests/test_interprocedural.py
python -m pytest -q tests/test_api_drift_audit.py tests/test_config_layout.py
python -m pytest -q tests/test_demo.py
```

### 12.3 每个阶段退出前

```powershell
python -m compileall -q src tests scripts
python -m pytest -q
git diff --check
git status --short
```

如果测试数或候选 schema 发生变化，在本文件“当前可核验快照”中更新，不继续引用旧的 `110 passed` 或其他历史数字。

Clang/Kbuild 测试需要 Linux/WSL/容器时，应同时保留：

- 执行命令；
- Clang 版本；
- kernel tag/config hash；
- compile database hash；
- 成功和失败 translation unit 清单。

---

## 13. 每个代码任务的完成格式

每个 G1--G5 子任务完成时记录：

```text
Task ID:
Problem:
Supported semantics:
Explicitly unsupported semantics:
Files changed:
Tests added/changed:
Diagnostics/schema changes:
Behavioral diff:
Known limitations:
Verification commands and result:
Architecture documentation updated:
```

不能只写“实现完成”。至少要说明支持范围、反例、降级策略和测试证据。

---

## 14. 当前暂停区

以下已有材料继续保留，但当前不主动扩展：

- `benchmark/`：保留现有 30 条 ext4 pilot 和脚本，不把它升级为最终 benchmark；
- `outputs/confirmed_bugs.md`：保留状态，不把 finding 跟踪作为代码主线；
- `scripts/evaluate_benchmark.py` 等评估脚本：不做论文级扩展；
- historical fixes：继续作为 ranking evidence，不用于修改静态语义；
- DeepSeek/LLM：不新增调用、不调 prompt、不做概率校准；
- submitted kernel patches：可在维护者明确回复时单独处理，但不改变 G1--G5 顺序；
- `PAPER_ROADMAP.md`：保留历史和后续论文任务，暂不按其 benchmark 优先级执行。

暂停不代表删除。不得清理这些目录或重写已有标签。

---

## 15. 安全与仓库规则

1. 不提交 `linux-sources/`。
2. 不提交 API key、邮箱凭据或个人密钥。
3. 不执行 `git reset --hard`、`git checkout --` 或清理未确认输出。
4. 不覆盖现有 dirty worktree 中不属于当前任务的修改。
5. 不把 LLM verdict 当作静态语义或 gold label。
6. 不把 patch submitted/Reviewed-by 写成 upstream accepted。
7. 不为通过测试而放宽 fail-open 语义。
8. 不在 G2 中删除 tree-sitter fallback；先完成 parity 再决定长期维护方式。
9. 不在没有 schema version 的情况下改变候选或 witness 字段含义。
10. 每次提交前检查：

```powershell
git status --short
git diff --stat
git diff --check
git diff --cached --stat
```

---

## 16. 下一次接手应立即做什么

下一项唯一主任务是 **G2-B：接入并验证 Kbuild compile database**。

恢复命令：

```powershell
cd "E:\yanjiusheng\阅读论文\file_system\SE_EOD"

Get-Content -Encoding UTF8 PROJECT_HANDOFF.md -TotalCount 260
Get-Content -Encoding UTF8 docs\PROJECT_CLOSURE_PLAN.md -TotalCount 360

git status --short
python -m pytest -q

Get-Content -Encoding UTF8 src\frontend\model.py -TotalCount 220
Get-Content -Encoding UTF8 src\frontend\tree_sitter_frontend.py -TotalCount 220
Get-Content -Encoding UTF8 docs\PROJECT_CLOSURE_PLAN.md | Select-Object -Skip 220 -First 90
```

第一轮 G2-B 步骤：

1. 确认 Linux/WSL/容器中的内核 tag、architecture、Clang 版本和 `.config` 来源；
2. 实现 compile database loader/normalizer，严格区分 `arguments` 与 `command`；
3. 建立 translation unit 到唯一 compile command 的映射，重复/缺失显式报错；
4. 将 `CompileCommandIR` 填入 `TranslationUnitIR`；
5. 输出 config/compiler/compile-database hash 和 covered/uncovered 清单；
6. 在干净 Linux/WSL/容器中验证可重建性。

在 G2-B 完成前，不先写 Clang exporter，不伪造 compile flags，不开始 benchmark、LLM 或 ranking 工作。

---

## 17. 代码完善阶段 Definition of Done

本阶段完成必须同时满足：

- [x] G1：switch/case/default CFG 完整并有 10 个 ext4 v6.14 真实函数 golden；
- [x] G2-A：frontend IR schema v1、tree-sitter adapter、round-trip/golden/parity 已完成；
- [ ] G2：tree-sitter/Clang 使用同一 IR，Kbuild compile database 可重建；
- [ ] G2：compiled mode 的成功、失败和 fallback 可量化；
- [ ] G3：一般 callee CFG 可推导出口敏感 must/may effect；
- [ ] G3：每个自动 must 有可重建证明；
- [ ] G4：有限字段路径和 alias 有结构化模型与保守降级；
- [ ] G5：candidate 有 acquire-to-exit predecessor witness；
- [ ] 配置 lifecycle、determinism、schema version 和资源上限完成；
- [ ] 所有新增能力有正例、反例、unknown 和 regression tests；
- [ ] tree-sitter fallback、quarantine 和 uncertainty provenance 未被破坏；
- [ ] 全量测试、compileall 和 diff check 通过；
- [ ] `PROJECT_ARCHITECTURE.md` 与代码一致；
- [ ] 本文件更新为新的代码快照。

达到这些条件后，分析器代码主线才算完善。届时再按照 `PROJECT_CLOSURE_PLAN.md` 从 G6 开始处理独立 benchmark、baseline、正式评估、artifact 和论文闭合。
