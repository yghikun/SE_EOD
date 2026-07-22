# MOCC-SE 当前项目架构

> 状态基线：2026-07-22
>
> 本文档只描述当前仓库中仍然存在并通过测试的实现。目标方法定义见
> [`MOCC_SE_FULL_ARCHITECTURE.md`](MOCC_SE_FULL_ARCHITECTURE.md)，研究和评估边界见
> [`PROJECT_CLOSURE_PLAN.md`](PROJECT_CLOSURE_PLAN.md)。

## 1. 当前定位

仓库已收敛为 MOCC-SE（Metadata Operation Completion Consistency for Static
Error-path analysis）原型。当前主线面向 Linux 文件系统 C 代码，将多阶段元数据操作
表示为由文件系统协议实例化的参数化扩展状态机，并检查每个可达出口是否为合法完成。

2026-07-22 已删除旧 SE-EOD 全流程运行时代码，包括：

```text
src.main
resource lifecycle tracker/dataflow
legacy candidate checker
ranking/history/manual/LLM pipeline
benchmark/experiment helper scripts
```

旧 SE-EOD 输出只作为历史数据保留，不再由当前 `src/` 提供可执行复现入口。当前
MOCC-SE 仍复用必要的 C 解析、frontend-neutral IR 和函数内 CFG，不复用旧资源状态机。

## 2. 参数化扩展状态机

方法模型为：

```text
M_P = <Q, X, Sigma, delta, Inv_P, Accept_P>
```

- `Q`：`INIT/ACTIVE/COMMITTING/HANDLING_FAILURE/RETRYING/EXITED` 等控制状态；
- `X`：phase、effect ledger、failure token、accounting、completion mode、return
  provenance 和 uncertainty；
- `Sigma`：从统一 IR 提取的 metadata event；
- `delta`：协议驱动的状态转移；
- `Inv_P`：当前协议可表达的 phase/effect/return/accounting 约束；
- `Accept_P`：成功或失败出口的合法完成谓词。

当前没有独立的 `state_machine.py`。扩展状态机由现有协议模型、tracker 和合法出口
验证器共同实现；也没有任意文件系统不变量 DSL。

三类违规是非法出口配置的诊断：

```text
unresolved necessary failure + success exit
    -> failure_reported_as_success

required effect remains open or has no valid owner at exit
    -> incomplete_failure_completion

return/phase/accounting/provenance constraint mismatch
    -> metadata_state_divergence
```

如果对象身份、handler 覆盖或路径语义不能证明，结果进入 `ANALYSIS_UNKNOWN`，不能
自动解释为安全或 bug。

## 3. 当前数据流

```text
Linux fs/ source
  -> TreeSitterFrontend
  -> versioned FunctionIR
  -> function-local CFG
  -> protocol applicability / operation selection
  -> metadata event extraction
  -> operation instance + effect/failure/accounting propagation
  -> legal-exit verification
  -> PROTOCOL_CANDIDATE | ANALYSIS_UNKNOWN
  -> broad semantic discovery
  -> DISCOVERY_REVIEW | DISCOVERY_REVIEW_UNKNOWN | DISCOVERY_UNKNOWN
  -> source review / version matrix / repair evidence / finding linkage
```

精确 protocol analysis 与宽松 discovery 必须分离。只有完整协议入口分析可以生成
`PROTOCOL_CANDIDATE`；broad semantic pattern 只生成待人工复核的
`DISCOVERY_REVIEW`。

## 4. 模块责任

### 4.1 前端与 CFG

| 模块 | 责任 |
|---|---|
| `src/parser.py` | 读取 C 源码、tree-sitter 初始化、文本 fallback 和基础语法辅助 |
| `src/function_extractor.py` | 从解析结果抽取函数和兼容节点 |
| `src/frontend/model.py` | 版本化 translation unit、function、symbol、call、access path 和 CFG IR |
| `src/frontend/tree_sitter_frontend.py` | 将 tree-sitter/文本结果转换为统一 IR，保留诊断和不确定性 |
| `src/cfg.py` | 构建函数内 CFG，支持分支、循环、goto、return 和普通 switch |

### 4.2 协议和 EFSM 核心

| 模块 | 责任 |
|---|---|
| `src/metadata_protocol.py` | schema v1、协议/operation、return contract、effect、handler、accounting 和 legal exit |
| `src/metadata_event.py` | 将调用、赋值、字段和容器更新规范化为确定性 metadata event |
| `src/metadata_tracker.py` | operation instance、effect ledger、failure attempt、accounting、join/widening 和责任转移 |
| `src/metadata_candidate_rules.py` | 成功/失败合法出口、三类违规和独立 `ANALYSIS_UNKNOWN` |
| `src/metadata_protocol_analyzer.py` | 在单个函数 CFG 上执行精确协议分析并输出 witness |
| `src/metadata_protocol_discovery.py` | 扫描源码树，隔离 exact candidate、fresh semantic review 和 discovery unknown |

### 4.3 复核与证据

| 模块 | 责任 |
|---|---|
| `src/metadata_finding_review.py` | 从 discovery report 生成带源码上下文的复核队列 |
| `src/metadata_finding_triage.py` | 合并人工源码复核结论，生成 development triage |
| `src/metadata_finding_matrix.py` | 对齐多个 Linux 版本的函数级候选状态 |
| `src/metadata_function_diff.py` | 提取函数级版本 diff 和修复语义 hint |
| `src/metadata_repair_evidence.py` | 将版本修复 hint 连接到 triage item |
| `src/metadata_bug_hunt_report.py` | 汇总 development review、matrix 和 repair evidence |
| `src/metadata_confirmed_bug_linkage.py` | 将开发队列连接到 `outputs/confirmed_bugs.md` |

这些证据模块不改变静态协议状态。人工结论、历史修复和 patch 只能用于复核与验证，
不能反向关闭 effect 或 failure token。

## 5. 协议配置

当前活动配置位于 `configs/metadata_protocols/`：

```text
protocol_a_replay_recovery_v1.json
protocol_b_device_topology_v1.json
protocol_c_activation_accounting_v1.json
```

Protocol A 覆盖 replay/recovery 返回一致性；Protocol B 覆盖 Btrfs device/root/topology
rollback；Protocol C 覆盖 retry provenance、positive-success 和 boolean
reservation/accounting。

`operation.entry_functions` 仅作为 regression seed。函数名不能直接编码“这是 bug”；
candidate 语义必须来自 operation role、event、return contract、effect/handler 和 legal
exit。当前 schema 只支持显式配置的布尔/关系约束，不推导任意元数据算术。

## 6. 运行入口

### 6.1 单函数协议分析

```powershell
python -m src.metadata_protocol_analyzer `
  --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json `
  --source linux-sources/linux-v6.8-fs/fs/ext4/fast_commit.c `
  --source-version linux-v6.8
```

### 6.2 源码树 fresh discovery

```powershell
python -m src.metadata_protocol_discovery `
  --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json `
  --protocol configs/metadata_protocols/protocol_b_device_topology_v1.json `
  --protocol configs/metadata_protocols/protocol_c_activation_accounting_v1.json `
  --source-root linux-sources/linux-v6.8-fs/fs `
  --source-version linux-v6.8 `
  --out outputs/mocc-discovery-v2/linux-v6.8-fresh-review.json
```

该命令默认排除 confirmed functions 和 regression seeds。当前 v6.8 产物是开发复核
队列，不是 frozen benchmark，也不能自动标为真实 bug。

### 6.3 辅助脚本

当前只保留：

```text
scripts/download_linux_fs.py
scripts/validate_ext4_fc_replay_helpers.py
```

前者准备本地 Linux `fs/` 源码；后者对当前 ext4 fast-commit helper 候选执行窄范围
源码控制流 fault model。后者不是完整内核 fault-injection 或上游确认。

## 7. 测试结构

当前测试只覆盖保留的执行链：

```text
frontend IR and parser fallback
function-local CFG and Linux switch golden
protocol schema and validation
metadata event extraction
effect/failure/accounting propagation
legal exits and candidate classification
Protocol A/B/C analysis
source-tree discovery and fresh queue
review/triage/matrix/diff/repair/linkage
```

2026-07-22 实测：

```text
138 passed
```

运行：

```powershell
python -m pytest -q
```

## 8. 输出保留策略

当前保留：

```text
outputs/confirmed_bugs.md
outputs/mocc-protocol-a-v1/
outputs/mocc-protocol-b-v1/
outputs/mocc-protocol-c-v1/
outputs/mocc-discovery-v1*
outputs/mocc-discovery-v2/
outputs/mocc-finding-review-v1/
outputs/experiment-v1.3.3/   # 历史数据基线，不再由当前代码复现
outputs/linux-v6.8/          # 历史数据/证据输入
outputs/linux-v7.1/          # 历史数据/证据输入
```

输出语义和清理记录见 [`../outputs/README.md`](../outputs/README.md)。历史输出不能被
解释为当前 MOCC-SE 的无偏评估结果。

## 9. 明确不支持

当前实现不声称：

- 完整 Kbuild/Clang 编译语义；
- 通用 SSA、points-to 或字段敏感别名分析；
- 完整跨函数 handler/effect summary；
- 任意 metadata invariant 或算术约束自动推导；
- 完整并发、持久化顺序或 crash-consistency 证明；
- 自动动态复现、自动确认 bug 或自动生成可合并补丁；
- 已经对大多数文件系统完成泛化验证。

支持片段外必须输出 unknown/unsupported，不能通过文档主张扩大实现能力。
