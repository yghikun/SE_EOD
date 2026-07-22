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
验证器共同实现。`MetadataOperationInstance.control_state` 显式传播上述控制状态并记录
`control_history`；每个 `EffectRecord` 独立传播 effect lifecycle。合法出口要求控制层
到达 `EXITED`，非法转移或不同控制状态 join 会产生 `ANALYSIS_UNKNOWN`。当前仍没有
任意文件系统不变量 DSL。

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
independent evidence -> rule registry -> authority/split/coverage audit
protocol family -> filesystem binding -> operation instance
                                         |
                                         v
                               runtime MetadataProtocol
                                         |
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

规则 registry 是执行前的知识来源和覆盖审计层，不进入单条路径的状态传播。它强制
每个 active protocol operation 绑定至少一条有明确 authority、evidence usage 和 dataset
split 的规则，并把尚未实现的 coverage target 与 executable rule 分离。普通 Linux
实现源码属于 implementation evidence，不是 normative contract。

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
| `src/metadata_protocol.py` | 向后兼容 schema v1 的 schema v2、协议/operation、return contract、effect、有界 callee summary、handler、accounting 和 legal exit |
| `src/metadata_protocol_package.py` | 校验并组合 protocol family、filesystem binding 和 operation instance，生成原有 runtime schema v2 |
| `src/metadata_event.py` | 将调用、赋值、字段、容器更新和调用点对象替换规范化为确定性 metadata event |
| `src/metadata_tracker.py` | operation control state/trace、effect ledger、OPEN/COMMIT/COMPENSATE/TRANSFER、failure attempt、accounting、join/widening 和责任转移 |
| `src/metadata_candidate_rules.py` | `EXITED` 门禁、成功/失败合法出口、三类违规和独立 `ANALYSIS_UNKNOWN` |
| `src/metadata_protocol_analyzer.py` | 在单个函数 CFG 上执行精确协议分析并输出 witness |
| `src/metadata_protocol_discovery.py` | 扫描源码树，隔离 exact candidate、fresh semantic review 和 discovery unknown |
| `src/metadata_batch_scan.py` | 在 freeze/rule/manifest 边界内加载 active protocols，生成全量 candidate/review/unknown 队列 |
| `src/metadata_batch_triage.py` | 对 batch scan 队列生成初始源码 triage ledger，区分 likely false positive、needs external semantics、needs protocol instance 和 bug-review candidate |
| `src/metadata_ext4_replay_bookkeeping_audit.py` | 对 ext4 fast-commit replay bookkeeping helper 抽取源码事实，记录 ignored return、failure-to-success、bookkeeping/partial mutation，并保守输出 `needs_external_semantics` |

### 4.3 规则知识与覆盖审计

| 模块 | 责任 |
|---|---|
| `src/metadata_rule_registry.py` | schema v2、authority/evidence/usage/split、maturity、rule-to-operation binding、覆盖和污染校验 |
| `src/metadata_evidence_verifier.py` | 下载版本固定的外部 contract，校验 SHA-256 和逐字摘录 |
| `src/metadata_validation_manifest.py` | 冻结 active protocol/rule 配置，校验 blind validation manifest、源码 hash、函数存在性和 construction overlap |
| `src/metadata_validation_labels.py` | 生成并校验独立 reviewer label set 与 adjudication set，防止空模板被当作完成结果 |
| `src/metadata_validation_run.py` | 在不读取 blind labels 的前提下执行冻结样本，审计协议适用率；仅在完整裁决后计算 precision/recall/F1、abstention 和 prediction coverage |
| `src/metadata_validation_selection.py` | 为下一批 blind validation 生成 label-blind、protocol-applicable 候选池和 `draft_manifest`，冻结 selection seed 与适用性门禁 |
| `configs/metadata_rules/rule_registry_v2.json` | 当前证据规则、支持边界和未实现 coverage targets |
| `configs/validation/` | protocol/rule freeze v1、10 个 blind/unlabeled validation samples、reviewer/adjudication templates 和 JSON schema |

### 4.4 复核与证据

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

规则来源与协议绑定位于 `configs/metadata_rules/`。当前 registry v2.2 登记 1 条 normative、
7 条 confirmed 和 2 条 heuristic development 规则，覆盖以下 12 个 active operation。
14 份 external source 均固定 locator、SHA-256 与摘录；逐规则覆盖和缺口记录在
`configs/metadata_rules/EVIDENCE_AUDIT.md`。6 个 coverage target 仍是后续任务。

当前活动配置位于 `configs/metadata_protocols/`：

```text
protocol_a_replay_recovery_v1.json
protocol_b_device_topology_v1.json
protocol_c_activation_accounting_v1.json
protocol_d_transaction_lifecycle_v2.json
protocol_e_allocation_lifecycle_v2.json
```

Protocol A 覆盖 replay/recovery 返回一致性；Protocol B 覆盖 Btrfs device/root/topology
rollback；Protocol C 覆盖 retry provenance、positive-success 和 boolean
reservation/accounting；Protocol D 覆盖 XFS transaction allocation、commit/cancel，
以及 ext4 journal start/stop 的同一对象闭合；Protocol E 覆盖 Btrfs search path 的
非 NULL 分配和同对象释放。Protocol D/E 的 manifest 从 abstract family、filesystem
binding 和 operation instance 组合 runtime schema v2，并使用一层有界摘要从调用参数
或捕获的调用返回值绑定对象；A-C 仍是扁平兼容配置。Protocol E 已支持
`BTRFS_PATH_AUTO_FREE(path)` 这类 bounded 自动 cleanup 宏；allocation publication
或更宽的跨调用边界 ownership transfer 仍属于后续扩展。

分层职责固定为：family 只定义抽象角色、动作、义务和适用条件；binding 只定义具体
API、对象角色、guard 和 owner 映射；operation 只定义入口、返回契约、effect 实例和合法
出口。`MetadataProtocol.read_json()` 对 analyzer 保持统一接口，因此运行时不依赖配置的
物理布局。

`operation.entry_functions` 仅作为 regression seed。函数名不能直接编码“这是 bug”；
candidate 语义必须来自 operation role、event、return contract、effect/handler 和 legal
exit。当前 schema 只支持显式配置的布尔/关系约束，不推导任意元数据算术。

全量扫描入口是 `metadata_batch_scan`。它复用 discovery 引擎，但先校验 freeze 和
validation manifest，并按 rule applicability 过滤协议版本。输出
`candidate_queue_not_bug_claims`，因此只产生待复核队列，不产生 confirmed bug。
`metadata_batch_triage` 对该队列做初始源码复核归类；该 triage ledger 仍不是 benchmark
label，也不是 confirmed bug list。

## 6. 运行入口

### 6.0 规则和协议覆盖校验

```powershell
python -m src.metadata_rule_registry
python -m src.metadata_evidence_verifier
python -m src.metadata_validation_manifest
python -m src.metadata_validation_labels `
  --labels configs/validation/reviewer_a_labels_v1.json `
  --labels configs/validation/reviewer_b_labels_v1.json `
  --adjudication configs/validation/adjudication_v1.json
python -m src.metadata_validation_run `
  --out outputs/mocc-validation-v1/unseen-batch-1-predictions.json
python -m src.metadata_validation_selection `
  --source 7.1=linux-sources/linux-v7.1-fs/fs/ext4/fast_commit.c `
  --samples-per-protocol 0 `
  --out outputs/mocc-validation-v1/batch-2-selection-smoke.json
python -m src.metadata_batch_scan `
  --source-root linux-sources/linux-v7.1-fs/fs `
  --source-version 7.1 `
  --max-files 1
python -m src.metadata_batch_triage `
  --batch-report outputs/mocc-batch-scan-v1/linux-v7.1-fs.json `
  --out-json outputs/mocc-batch-scan-v1/linux-v7.1-fs-triage.json `
  --out-md outputs/mocc-batch-scan-v1/linux-v7.1-fs-triage.md
python -m src.metadata_ext4_replay_bookkeeping_audit `
  --source-root linux-sources/linux-v7.1-fs/fs `
  --source-version 7.1 `
  --out-json outputs/mocc-batch-scan-v1/ext4-replay-bookkeeping-audit.json `
  --out-md outputs/mocc-batch-scan-v1/ext4-replay-bookkeeping-audit.md
```

当前预期摘要：5 个 active protocol、12 个 covered operation、1 条 normative、7 条
confirmed 和 2 条 heuristic development rule、0 条 validation/frozen rule；external
evidence verifier 应验证 14 个文档、主线提交和维护者邮件源。
`metadata_validation_manifest` 应验证 14 个 frozen artifact、10 个 blind/unlabeled sample、
5 个 active protocol 和 0 个 construction overlap。该 manifest 不是 validation 结果；
`metadata_validation_labels` 应验证 2 个 reviewer template 与 1 个 adjudication template。
这些文件仍不是 validation 结果；所有 10 条 rule maturity 仍保持 development。当前
validation runner 审计显示 batch 1 在 lifecycle discovery 扩展后有 2/10 个样本进入
exact/semantic 协议分析，其余 8 个仍为 out of scope，所以该批次只能作为 manifest
覆盖不足的诊断，不能生成性能指标。batch 2 应通过
`metadata_validation_selection` 先生成 selection audit 和 draft manifest，再冻结人工标注。
当前 selection smoke artifact 显示 32/32 个 registered exact-entry identities 均为
construction overlap，说明 batch 2 必须依赖 semantic/fresh discovery 或先扩展协议适用性。
生命周期协议的 semantic applicability 已扩展为 acquire/open-first：D/E 协议可以因
`xfs_trans_alloc()`、`ext4_journal_start()` 或 `btrfs_alloc_path()` 进入 operation analysis，
而 terminal action 缺失由 analyzer 判定为 candidate 或 unknown。这使 batch 2 selection
能在 protocol-relevant roots 中产生 D/E 可审计样本，同时仍保持 semantic review 与
`PROTOCOL_CANDIDATE` 分离。

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

当前只保留两个脚本：

```text
scripts/download_linux_fs.py
scripts/validate_ext4_fc_replay_helpers.py
```

前者准备本地 Linux `fs/` 源码；后者对当前 ext4 fast-commit helper 候选执行窄范围
源码控制流 fault model。后者不是完整内核 fault-injection 或上游确认。新的
`src.metadata_ext4_replay_bookkeeping_audit` 是源码事实审计模块，不是脚本目录里的
legacy validator。

## 7. 测试结构

当前测试只覆盖保留的执行链：

```text
frontend IR and parser fallback
function-local CFG and Linux switch golden
protocol schema and validation
metadata event extraction
effect/failure/accounting propagation
legal exits and candidate classification
Protocol A/B/C/D/E analysis
source-tree discovery and fresh queue
review/triage/matrix/diff/repair/linkage
```

2026-07-22 实测：

```text
248 passed
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
- 递归或通用跨函数 handler/effect summary；当前只执行配置化的一层摘要；
- 任意 metadata invariant 或算术约束自动推导；
- 完整并发、持久化顺序或 crash-consistency 证明；
- 自动动态复现、自动确认 bug 或自动生成可合并补丁；
- 已经对大多数文件系统完成泛化验证。

支持片段外必须输出 unknown/unsupported，不能通过文档主张扩大实现能力。
