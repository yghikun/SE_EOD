# SE-EOD / MOCC-SE 项目架构说明

> 本文档以当前仓库代码为唯一事实来源，描述截至 2026-07-21 的实现。文档中的“已实现”表示有代码和回归测试支撑；“部分实现”和“未实现”不应在论文或实验报告中被表述为完整能力。
>
> 当前实现如何推进到工程、实验、论文和复现全部闭合，见 [`PROJECT_CLOSURE_PLAN.md`](PROJECT_CLOSURE_PLAN.md)；目标方法架构见 [`MOCC_SE_FULL_ARCHITECTURE.md`](MOCC_SE_FULL_ARCHITECTURE.md)。

SE-EOD 是 MOCC-SE 的现有错误路径分析基线，面向 Linux 文件系统 C 代码。它的输出是待复核候选，不是 confirmed bug。目标方法将现有资源义务扩展为带责任域和补偿关系的元数据 effect：

1. 从源码中提取错误路径、元数据事件和返回值契约。
2. 跟踪 phase facts、effect ledger、failure epochs 和 accounting obligations。
3. 检查 `failure_reported_as_success`、`incomplete_failure_completion` 和 `metadata_state_divergence`。
4. 使用协议、历史修复、人工标签和 LLM 信号排序，但不让排序信号反向篡改静态语义。

完整目标架构、协议责任域和评估边界集中记录在 [`MOCC_SE_FULL_ARCHITECTURE.md`](MOCC_SE_FULL_ARCHITECTURE.md)。本文件只描述当前仓库已经实现的 SE-EOD 基线，不把目标能力误写成已完成能力。

---

## 1. 系统定位与非目标

### 1.1 当前能力边界

SE-EOD 当前是“带 CFG 和资源状态传播的候选发现原型”，而不是编译器级静态分析器。它已经具备：

- tree-sitter C 函数与语句抽取；
- 版本化 frontend-neutral IR，tree-sitter 主流程通过 adapter 输出统一 translation-unit/function/symbol/call/access-path/CFG 模型；
- 函数内 CFG，包括 `if`、循环、`goto`、`return`、`break`、`continue`；
- 有界析取前向数据流；
- 简单路径谓词传播；
- acquire/release、scope cleanup、简单别名和函数指针目标传播；
- 跨函数 effect summary 不动点计算；
- 候选规则、证据排序、人工复核和 LLM triage 产物链路。

但它尚不具备：

- 基于实际 kernel build flags 的预处理和完整 Clang AST；
- 完整类型系统、SSA、points-to 或字段敏感别名分析；
- 一般 SMT 路径可行性求解；
- 对所有内核宏、条件编译和 GNU C 扩展的编译级语义恢复；
- 自动的动态复现、upstream 确认或缺陷修复证明。

### 1.2 输出含义

| 输出 | 可以声称 | 不可以声称 |
|---|---|---|
| `error_paths.csv` | 工具识别到的错误样退路径 | 路径在所有编译配置下都可行 |
| `suspicious_candidates.csv` | 静态规则认为值得复核 | 候选已是真实 bug |
| `quarantined_error_paths.csv` | 默认过滤掉的 low/uncertain 路径仍被保留供审计 | 它们和主输出具有同等置信度 |
| `quarantined_candidates.csv` | 从隔离路径派生的复核池候选 | 它们应直接混入主候选排序 |
| `api_drift_report.json/csv` | 当前源码与 lifecycle API 配置的一致性诊断 | 诊断项本身不能证明 bug 或 false positive |
| `ranked_candidates.jsonl` | 候选的排序和证据摘要 | 分数是概率或独立证据数量 |
| DeepSeek/LLM verdict | 辅助 triage 信号 | gold label、动态证明或 maintainer 确认 |

---

## 2. 端到端数据流

`src/main.py` 是统一命令行入口。完整数据流如下：

```text
Linux source tree
  -> iter_c_files(): 扫描 <linux>/<fs-subdir>/**/*.c
  -> TreeSitterFrontend.parse(): tree-sitter 解析、质量标记和 adapter
  -> TranslationUnitIR.functions: 版本化 FunctionIR
  -> optional infer_function_summaries(): 跨函数 effect 不动点
  -> ErrorPathExtractor.extract()
       -> 错误条件/返回识别
       -> CFG + 析取前向资源数据流
       -> 目标 label 后可达 return 状态检查
  -> high/medium error_paths.csv
  -> low/uncertain quarantined_error_paths.csv
  -> run_candidate_rules()
  -> suspicious_candidates.csv
  -> review-only quarantined_candidates.csv
  -> protocol/wrapper/ownership/history/manual/LLM evidence
  -> ranked_candidates.jsonl + candidates_with_evidence.csv
  -> optional llm_review_tasks.jsonl + DeepSeek outputs
```

这条流水线分成两个必须保持独立的区域：

```text
静态语义区域
  决定候选是否生成
  resource_map / CFG / path facts / summaries / reviewed semantic contracts

证据排序区域
  决定候选先看谁
  protocols / wrapper hints / ownership hints / history / manual / LLM
```

ranking hint 不能证明 release 或 transfer，因此不应在静态阶段直接删除候选。

---

## 3. 主要模块与责任

| 层级 | 模块 | 当前责任 |
|---|---|---|
| 调度 | `src/main.py` | CLI、阶段组合、主输出/quarantine 输出、统计和 warning |
| 文件发现 | `src/file_walker.py` | 递归扫描指定文件系统子目录下的 `.c` |
| 底层源码解析 | `src/parser.py`, `src/function_extractor.py` | tree-sitter C 解析、文本 fallback 和兼容抽取 API |
| 统一前端 IR | `src/frontend/model.py` | schema v1；translation unit、function、generic node、symbol、call、access path、diagnostic 和 CFG |
| tree-sitter adapter | `src/frontend/tree_sitter_frontend.py` | 将 parser 结果转换为统一 IR，区分直接/间接调用，记录 ERROR/text fallback |
| CFG | `src/cfg.py` | 函数内基本块、边、label、goto 和诊断 |
| 数据流 | `src/dataflow.py` | 普通前向求解和有界析取前向求解 |
| 错误语义 | `src/error_condition.py` | 错误条件、错误返回和置信度分类 |
| 错误源 | `src/backward_slicer.py` | 函数内轻量最近定义回溯 |
| label 展示 | `src/label_resolver.py` | 线性定位 label、收集展示调用、识别 retry/backedge |
| 资源状态 | `src/resource_state.py` | ownership state、action、join 和 violation |
| 元数据协议 | `src/metadata_protocol.py` | MOCC-SE schema v1、不可变协议模型、严格 JSON round-trip、跨引用和 handler scope 校验；尚未接入主流程 |
| 元数据事件 | `src/metadata_event.py` | 从统一 IR 规范化必要调用、字段赋值、list、flag/counter 与 protocol effect/handler；确定性 event ID、EXACT/NORMALIZED/UNKNOWN 和 must/may |
| 元数据状态 | `src/metadata_tracker.py` | `MetadataOperationInstance`、attempt-scoped failure token、effect ledger、accounting obligation、abort/transfer、join 和 widening |
| 协议验证 | `src/metadata_candidate_rules.py` | success/failure 合法出口，三类 MOCC-SE candidate 与独立 `ANALYSIS_UNKNOWN` |
| Protocol A 分析 | `src/metadata_protocol_analyzer.py` | 独立 CLI；按 operation entry/callee role/return contract 在 CFG 上生成 replay/recovery candidate、unknown 和 representative witness |
| 协议发现 | `src/metadata_protocol_discovery.py` | 独立 CLI；递归扫描源码树，按 filesystem applicability、精确入口和保守 semantic 锚点选择 operation；将 `PROTOCOL_CANDIDATE`、`DISCOVERY_REVIEW`、`DISCOVERY_REVIEW_UNKNOWN` 和 `DISCOVERY_UNKNOWN` 分开输出 |
| finding 复核队列 | `src/metadata_finding_review.py` | M8 开发入口；从 discovery JSON 生成源码复核 JSON/Markdown，保留 witness、源码上下文、open effect、unresolved failure、accounting state 和 summary-gap hints；支持 development source-review annotations |
| finding triage ledger | `src/metadata_finding_triage.py` | M8 开发入口；合并 review queue 和源码复核结论，输出候选是否通过初筛、后续开发主题和 protocol 分布，不作为 benchmark label |
| finding version matrix | `src/metadata_finding_matrix.py` | M8 开发入口；对齐多个 discovery report，按版本比较候选保留、消失和新增的函数级线索 |
| function repair diff | `src/metadata_function_diff.py` | M8 开发入口；对齐同一函数的多版本源码 diff，抽取 `return 0` -> error-symbol 等修复语义 hint |
| repair evidence ledger | `src/metadata_repair_evidence.py` | M8 开发入口；把 function diff 中的修复 hint 挂到 triage item，形成 development repair evidence，不作为 benchmark label |
| bug-hunt report | `src/metadata_bug_hunt_report.py` | M9 开发入口；汇总 reviewed queue、triage、version matrix 和 repair evidence，生成全量开发找 bug 报告 |
| confirmed bug linkage | `src/metadata_confirmed_bug_linkage.py` | M10 开发入口；将 M9 队列按函数链接到 `confirmed_bugs.md` Summary，区分 submitted、for-next、fixed duplicate 和未进入当前队列的已确认记录 |
| 资源传播 | `src/resource_tracker.py` | CFG transfer、path facts、alias、summary、scope cleanup、出口义务检查 |
| 资源表达式 | `src/resource_expr.py` | 规范化和保守表达式匹配 |
| release 匹配 | `src/resource_release.py` | release 名称、参数位置和地址参数匹配 |
| 跨函数 | `src/function_summary.py` | 调用图、effect seed、参数/返回效果和不动点 |
| 配置审计 | `src/resource_config_audit.py` | 统计兼容 acquire 合约和缺少 aggregate identity 的 `all` 合约 |
| API 漂移审计 | `src/api_drift_audit.py` | 对齐源码中观察到的 API 与 resource map/protocol/wrapper 配置 |
| 路径输出 | `src/csv_writer.py` | `error_paths.csv` schema 和 JSON 字段序列化 |
| 候选规则 | `src/candidate_rules.py` | missing、partial、swallowed、stale retry 候选；默认跳过 low/uncertain，隔离池可显式保留 |
| 候选 I/O | `src/candidate_checker.py` | 读错误路径、写主候选/quarantine 候选并统计 |
| 协议证据 | `src/protocol_db.py`, `src/protocol_matcher.py` | 加载 ranking protocol 并匹配候选 |
| wrapper hint | `src/wrapper_summary.py` | 人工 wrapper/alias 排序证据 |
| ownership hint | `src/ownership_transfer.py` | 基于名称和源码模式的低置信度提示 |
| ranking | `src/evidence_ranker.py` | ID、evidence level、score、exception hint 和排序输出 |
| 复核 | `src/manual_review.py`, `src/llm_task_builder.py` | 人工标签、LLM 任务和 DeepSeek 调用 |
| 历史证据 | `src/historical_fix.py` | 严格匹配已审查的跨版本修复 |
| 审查契约 | `src/false_positive_model.py` | 代码级特例和 reviewed suppression |

---

## 4. CLI 与运行模式

### 4.1 主流水线

典型全流程命令：

```powershell
python -m src.main `
  --linux linux-sources/linux-v6.14-fs `
  --fs-subdir fs/ext4 `
  --resource-map configs/ext4_resource_map.json `
  --out outputs/linux-v6.14-bug-check/ext4/error_paths.csv `
  --enable-interprocedural `
  --function-summaries-out outputs/linux-v6.14-bug-check/ext4/function_summaries.json `
  --audit-api-drift `
  --api-drift-json-out outputs/linux-v6.14-bug-check/ext4/api_drift_report.json `
  --api-drift-csv-out outputs/linux-v6.14-bug-check/ext4/api_drift_report.csv `
  --check-candidates `
  --candidates-out outputs/linux-v6.14-bug-check/ext4/suspicious_candidates.csv `
  --quarantined-error-paths-out outputs/linux-v6.14-bug-check/ext4/quarantined_error_paths.csv `
  --quarantined-candidates-out outputs/linux-v6.14-bug-check/ext4/quarantined_candidates.csv `
  --rank-evidence `
  --protocols-dir configs/ext4_resource_protocols `
  --wrapper-summaries configs/wrapper_summaries.json `
  --enable-ownership-transfer-hints `
  --historical-fixes configs/ext4_historical_fixes.json `
  --ranked-candidates-out outputs/linux-v6.14-bug-check/ext4/ranked_candidates.jsonl `
  --candidates-with-evidence-out outputs/linux-v6.14-bug-check/ext4/candidates_with_evidence.csv `
  --build-llm-tasks `
  --llm-tasks-out outputs/linux-v6.14-bug-check/ext4/llm_review_tasks.jsonl
```

Linux/macOS shell 中将 PowerShell 换行符换成 `\`。

### 4.2 可独立执行的阶段

`src.main` 支持将候选之后的阶段独立重跑：

- `--rank-evidence`：对既有 `--candidates-in` 重新排序；
- `--build-llm-tasks`：从候选或 ranking 结果构建任务；若提供 ranked JSONL，则按 obligation 级 ranked item 生成任务；
- `--run-deepseek-review`：要求 `DEEPSEEK_API_KEY`；
- `--extract-deepseek-true-candidates`：不调用模型，仅从既有 review JSONL 提取子集。

MOCC-SE Protocol A/B/C 仍通过独立入口运行，不进入 `src.main` 默认 CSV/JSONL：

```powershell
python -m src.metadata_protocol_analyzer `
  --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json `
  --source linux-sources/linux-v6.8-fs/fs/ext4/fast_commit.c `
  --source-version linux-v6.8
```

M7 的目录级发现入口为：

```powershell
python -m src.metadata_protocol_discovery `
  --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json `
  --protocol configs/metadata_protocols/protocol_b_device_topology_v1.json `
  --protocol configs/metadata_protocols/protocol_c_activation_accounting_v1.json `
  --source-root linux-sources/linux-v6.8-fs/fs `
  --source-version linux-v6.8 `
  --out outputs/mocc-discovery-v1-linux-v6.8.json
```

发现器只把精确入口分析结果列为 `PROTOCOL_CANDIDATE`。通过 callee/effect/handler
或 `operation.discovery` 上下文锚点匹配到的非入口函数进入
`DISCOVERY_REVIEW`；其中 analyzer 本身无法证明的结果进入
`DISCOVERY_REVIEW_UNKNOWN`。多个 operation 得分并列时进入
`DISCOVERY_UNKNOWN` quarantine。

M8 的源码复核队列入口为：

```powershell
python -m src.metadata_finding_review `
  --discovery-report outputs/mocc-discovery-v1-linux-v6.8.json `
  --source-root linux-sources/linux-v6.8-fs/fs `
  --context-lines 4 `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-review-queue.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-review-queue.md
```

复核注释入口为：

```powershell
python -m src.metadata_finding_review `
  --discovery-report outputs/mocc-discovery-v1-linux-v6.8.json `
  --source-root linux-sources/linux-v6.8-fs/fs `
  --context-lines 4 `
  --annotations outputs/mocc-finding-review-v1/linux-v6.8-source-review-notes.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.md
```

该注释输出是项目开发 triage，不是 frozen benchmark label。它用于记录源码复核结论、
区分 likely true candidate 与 summary/frontend 缺口，并为下一轮跨版本确认或
operation/context 扩展排序。

M8 的 initial source triage 入口为：

```powershell
python -m src.metadata_finding_triage `
  --review-queue outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.md
```

如果 reviewed queue 已包含 `source_review`，该命令可直接派生 triage decisions；
也可以通过 `--decisions` 传入逐 `review_id` 的人工决策文件。

M8 的 discovery version matrix 入口为：

```powershell
python -m src.metadata_finding_matrix `
  --report v6.8=outputs/mocc-discovery-v1-linux-v6.8.json `
  --report v6.14=outputs/mocc-discovery-v1-linux-v6.14.json `
  --report v7.1=outputs/mocc-discovery-v1-linux-v7.1.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-discovery-matrix.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-discovery-matrix.md
```

该矩阵只用于项目开发定位：候选跨版本保留表示需要继续确认，候选消失表示优先查
fixed-version/source diff，新增候选表示可扩展 operation/context。

M8 的 function-level source diff 入口为：

```powershell
python -m src.metadata_function_diff `
  --function xfs_rtcopy_summary `
  --source v6.8=linux-sources/linux-v6.8-fs/fs/xfs/xfs_rtalloc.c `
  --source v6.14=linux-sources/linux-v6.14-fs/fs/xfs/xfs_rtalloc.c `
  --source v7.1=linux-sources/linux-v7.1-fs/fs/xfs/xfs_rtalloc.c `
  --out-json outputs/mocc-finding-review-v1/xfs_rtcopy_summary-v6.8-v6.14-v7.1-function-diff.json `
  --out-md outputs/mocc-finding-review-v1/xfs_rtcopy_summary-v6.8-v6.14-v7.1-function-diff.md
```

该工具用于把候选消失与源码修复形态连接起来。例如当前 `xfs_rtcopy_summary` 与
`ext4_fc_replay_inode` 的 v7.1 diff 都出现 `local_return_propagation_repair`
hint：旧版本错误路径最终 `return 0`，新版本返回 `error` 或 `ret`。

M8 的 repair evidence ledger 入口为：

```powershell
python -m src.metadata_repair_evidence `
  --triage outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.json `
  --function-diff outputs/mocc-finding-review-v1/xfs_rtcopy_summary-v6.8-v6.14-v7.1-function-diff.json `
  --function-diff outputs/mocc-finding-review-v1/ext4_fc_replay_inode-v6.8-v6.14-v7.1-function-diff.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-repair-evidence-ledger.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-repair-evidence-ledger.md
```

它把 7 条 Protocol A v6.8 候选连接到 v7.1 的本地错误传播修复 evidence，用于后续
项目开发排序；仍不能直接当作 confirmed bug 或 benchmark 标注。

M9 的 development bug-hunt report 入口为：

```powershell
python -m src.metadata_bug_hunt_report `
  --reviewed-queue outputs/mocc-finding-review-v1/linux-v6.8-reviewed-queue.json `
  --triage outputs/mocc-finding-review-v1/linux-v6.8-initial-source-triage.json `
  --matrix outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-discovery-matrix.json `
  --repair-evidence outputs/mocc-finding-review-v1/linux-v6.8-repair-evidence-ledger.json `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-development-bug-hunt-report.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-development-bug-hunt-report.md
```

该报告是当前项目开发找 bug 的主要入口：优先看 repair-evidence-backed candidates，
再看 persistent candidates、removed/cleared functions 和 newly-added functions。

M10 的 confirmed bug linkage 入口为：

```powershell
python -m src.metadata_confirmed_bug_linkage `
  --bug-hunt-report outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-development-bug-hunt-report.json `
  --confirmed-bugs outputs/confirmed_bugs.md `
  --out-json outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-confirmed-bug-linkage.json `
  --out-md outputs/mocc-finding-review-v1/linux-v6.8-v6.14-v7.1-confirmed-bug-linkage.md
```

linkage 只读取 `confirmed_bugs.md` 的 `## Summary` 表，避免把后文数字表格重复解析为 bug
记录。队列项按函数匹配，保留 priority queue 来源和 violation type；同一函数的多个
occurrence 可以链接到同一 confirmed record，同一函数也可以对应一组相关 confirmed
records（例如 `btrfs_init_new_device` 的 #16-#18）。因此 occurrence 数不能当作独立 bug
数，linkage 也不是 precision/recall benchmark。

### 4.3 默认置信度边界

`src.main` 默认仅把 `high` 和 `medium` 错误路径写入主 `error_paths.csv`。`low/uncertain` 不再被静默丢弃，而是写入 `--quarantined-error-paths-out`，默认路径为：

```text
outputs/linux-v6.8/ext4/quarantined_error_paths.csv
```

若启用 `--check-candidates`，主 `suspicious_candidates.csv` 仍使用默认候选规则，不混入 low/uncertain 的 missing/partial 候选；隔离路径会单独生成 `--quarantined-candidates-out`，默认路径为：

```text
outputs/linux-v6.8/ext4/quarantined_candidates.csv
```

隔离候选是 review-only 池：它们用于分析器改进、人工标注和配置迁移，不应直接与主候选同口径排序。`--include-low-confidence` 会把 low/uncertain 路径纳入主 `error_paths.csv`，此时 quarantine 路径输出为空，以避免重复计数。

---

## 5. 前端、函数 IR 与解析质量

### 5.1 文件范围

`iter_c_files(...)` 当前只扫描指定目录下的 `.c` 文件。它不会主动分析 `.h` 文件，也不执行 kernel Kbuild 或预处理。因此定义在头文件或宏中的 cleanup/helper 语义必须通过配置或 effect seed 补充。

### 5.2 parser quality

`parse_c_file(...)` 有三类质量结果：

| `parser_kind` / `analysis_quality` | 条件 | 后续处理 |
|---|---|---|
| `tree-sitter` | parser 可用且 root 不含 ERROR | 正常 CFG、数据流和 summary |
| `degraded-tree-sitter` | 生成 AST，但 root 含 ERROR | 路径强制 `low`，不用于跨函数 summary |
| `degraded-text` | parser 不可用、抛异常或 AST 无可用函数 | 文本抽取，路径强制 `low`，不用于 summary |

warning 会写到 stderr，包括：

```text
tree-sitter unavailable
tree-sitter initialization failed
tree-sitter parse failed
tree-sitter parse contains ERROR nodes
```

### 5.3 版本化统一前端 IR

`src/frontend/model.py` 定义 `FRONTEND_IR_SCHEMA_VERSION = 1`。主流程不再把 tree-sitter 原生 node 传给资源分析；`TreeSitterFrontend` 先转换为 `FrontendNode/FunctionIR/TranslationUnitIR`。`function_extractor.Function/AstNode` 仅保留为兼容别名。

`TranslationUnitIR` 记录：

```text
schema_version, translation_unit_id, identity_path
path, source_text, frontend_name, frontend_mode
compile_command (tree-sitter 模式为 null，由 G2-B/G2-C 填充)
diagnostics, functions
```

`FunctionIR` 记录：

```text
function_id, translation_unit_id, frontend_name/mode/schema_version
file, name, signature, return_type, source, body
source range, body_start_line
FrontendNode ast_node/body_node
source_start_byte, body_start_byte, file_bytes
parameters, symbols, calls, access_paths
analysis_quality, diagnostics, unsupported_features
```

`FrontendNode` 保留 syntax kind、source spelling/normalized text、source range、children 和 named fields，但不暴露 tree-sitter 原生 API。`CallIR` 区分 direct/indirect/field/table；参数或局部函数指针名不会伪装成 direct target。`AccessPathIR` 当前是语法级 exact/bounded/unknown 表示，并标记 lvalue/rvalue/address；它尚未用作 G4 的资源 alias 证明。

IR 和 `ControlFlowGraphIR` 均可 JSON round-trip；未知 schema 版本会显式拒绝。translation-unit ID 使用 source-root 相对路径和源码 digest，因此相同相对路径/内容在不同工作目录下产生相同 function/symbol/call ID。序列化只保留 AST 结构与 range，spelling 从 translation-unit source 重建，避免每个父节点重复完整子树文本。

当前仍不是 typed/compiled IR：`type_spelling` 只是源码摘要，`compile_command=null`，macro expansion 位置字段尚无 Clang 数据，也没有 SSA value、显式 memory object 或 points-to set。

---

## 6. CFG 与数据流求解

### 6.1 CFG 结构

`src/cfg.py` 生成 `ControlFlowGraph`：

```text
blocks: block_id -> BasicBlock（含 scope_depth）
edges: CFGEdge(source, target, kind, condition, scope_unwind)
entry / exit
labels: label_name -> block_id
unsupported_nodes
```

边类型包括：

```text
fallthrough, true, false, goto, backedge, return, break, continue,
switch_case, switch_default, switch_no_match, case_fallthrough, unknown
```

普通 `switch/case/default` 使用独立的 condition、dispatch、case/default 入口和 switch exit block。dispatch 边保留 `switch expression == case value` 或 default/no-match 条件；共享 case body 和显式 fallthrough 通过 `case_fallthrough` 保留。`break` 指向最近 switch exit，`continue` 继承外层 loop target，因此嵌套 switch/loop 不会混用控制目标。switch body 的词法 scope 仍通过 dispatch/scope-exit 进入和退出。

GNU case range（例如 `case 1 ... 3`）、case 前的 switch prelude/宏恢复残片及 tree-sitter 无法生成标准 `switch_statement` 的结构仍会以精确 byte/line range 进入 `unsupported_nodes`，不会伪造已支持语义。无法解析的 `goto` 会连到 exit 并记录 `unresolved_goto:<label>`。

### 6.2 析取前向求解

`solve_forward_disjunctive(...)` 在每个基本块保留多个状态，而不是立即把所有分支 join 成单值。默认边界：

```text
max_states_per_block = 16
max_iterations = 20000
```

当某个 block 的析取状态超过 16 时，solver 调用 `ResourceTracker._join_flow_states(...)` widening 为一个状态。结果记录：

```text
iterations
truncated
widened_blocks
in_states / out_states
```

因此当前实现的精确描述是：

```text
常规分支：析取保留 ACQUIRED 和 RELEASED 路径
状态爆炸：超限后执行 widening，保留 MAY_ACQUIRED
```

不应再将它描述为“所有分支在 join 时都变成 UNKNOWN”。

循环 backedge 会按循环内的 modified-variable 集合失效 `path_facts`，并额外失效依赖循环条件标识符的事实。循环外已证明且循环内未修改的事实会保留；已绑定到 `resource_id` 的稳定 validity fact 也不会因变量文本同名被清除。这是保守的局部失效，不是循环不变量推导。

### 6.3 CFG 诊断

`ResourceTracker.cfg_diagnostics()` 统计：

```text
functions
iterations
truncated_functions
widened_blocks
max_states_per_block
unresolved_indirect_calls
unresolved_indirect_call_names
inferred_validity_guards
unknown_validity_guards
loop_multiplicity_resources
function_details
```

这些统计在主流程 stdout 中输出。主流程还从已生成的静态候选统计 `candidates_with_unknown_guard`、`candidates_with_loop_multiplicity`、`candidates_with_incomplete_cfg` 和 `candidates_with_widening`，用于区分分析器不确定性的来源。其中 `candidates_with_incomplete_cfg` 来自候选 snapshot；真正影响置信度的是候选可达 slice 上的 `cfg_slice_complete=false`。

默认过滤阶段还输出 quarantine 统计：

```text
extracted_error_paths_before_filter
quarantined_error_paths
low_due_to_parser
low_due_to_cfg_slice
low_due_to_widening
low_due_to_unknown_guard
low_due_to_other
quarantined_candidates
quarantined_missing_cleanup_count
quarantined_partial_cleanup_count
quarantined_error_swallowed_count
```

这些字段用于解释 low/uncertain 路径为什么离开主输出：`parser` 表示文本或 parser-quality 降级，`cfg_slice` 表示候选可达 slice 经过 unsupported CFG 节点，`widening` 表示路径经过 widening/truncation，`unknown_guard` 表示 acquire validity guard 未能证明。一个路径可以同时计入多个原因。

---

## 7. 错误路径抽取

### 7.1 路径来源

`ErrorPathExtractor` 优先从 AST 中处理：

- `if (...) return ...`；
- `if (...) goto label`；
- 分支中 cleanup 后再 `return/goto`；
- 函数体顶层的直接错误 `return`。

对 `if` 的 consequence/alternative，`ErrorPath` 记录 `branch_taken = true/false`；alternative 使用否定后的条件参与 path-fact 和资源状态筛选。顶层直接 return 记录 `branch_taken = direct`。这修复了 else 中错误返回错误复用 true-edge 状态的问题。

AST 路径现在记录 `condition_start_byte/condition_end_byte`，并绑定 CFG 的 `edge_id/source_block/target_block/edge_kind`。同一函数内两个文本相同的 `if (ret)` 因 byte range 和 edge ID 不同而可区分。历史字段名仍为 `cfg_witness`，但 JSON 内明确记录 `kind=cfg_analysis_snapshot`，并包含 source state 数、可达 blocks/return blocks、scope-unwind edges、`cfg_complete/unsupported_nodes`、`cfg_slice_complete/unsupported_nodes_on_reachable_slice`、`unsupported_ranges_on_reachable_slice`、widening/truncated，以及每个可达 return 的析取状态快照。快照包含资源 ID/state/multiplicity/uncertainty、path facts、`symbol_ids`、尚未求值的 pending summary effects（包括 call site、result symbol/version 和 cardinality）以及一条压缩的 `representative_trace`。

`representative_trace` 记录最近若干个 block/edge/scope 事件，可帮助复核“状态从哪条 CFG 路径来”。快照还输出 `trace_total_events/trace_truncated/trace_start_reason/trace_anchors`；普通 trace 是滚动窗口，但 acquire、release/transfer/escape、cardinality 阻断和 aggregate 未解析等关键状态变化会作为 anchor 保留。它仍不是完整 predecessor graph：当前不记录每个中间 block 的 before/after 全量状态，也不能保证从任意 exit state 反向重建所有兄弟分支。

当 `missing_cleanup` 候选的错误出口可达 slice 包含 unsupported CFG 节点时，`ErrorPath.confidence` 强制降为 `low`，并在 reason 中记录 `incomplete CFG on candidate slice`。如果函数中存在无关的 unsupported 节点，但候选入口到出口的可达 slice 不经过它，只记录 `cfg_complete=false`，不把该候选整函数式降级。

当 AST 不可用时，工具使用线性 `Statement` 表示做降级抽取。所有此类路径会强制为 `low`。

### 7.2 条件分类

`ConditionInfo` 记录条件分类字段，分支方向则由 `ErrorPath` 单独记录：

```text
condition
condition_type
error_var
confidence
reason
```

```text
ErrorPath.branch_taken = true | false | direct
```

当前覆盖的常见形式包括：

```text
err / ret / status
ret < 0 / ret != 0 / specific errno
!ptr / ptr == NULL / ptr != NULL
IS_ERR(ptr) / IS_ERR_OR_NULL(ptr)
ERR_PTR(...) / PTR_ERR(...)
direct negative errno return / NULL return
```

这是模式分类器，不是类型化的错误代数据流。

### 7.3 错误源回溯

`find_error_source(...)` 在当前函数内回溯错误变量最近的赋值来源。例如：

```c
ret = ext4_journal_get_write_access(handle, sbh);
if (ret)
    goto out;
```

将生成：

```text
error_var = ret
error_source_expr = ext4_journal_get_write_access(handle, sbh)
```

它不跨越任意别名、phi 或函数边界追踪 error provenance。

### 7.4 label resolver 的正确架构位置

`label_resolver.py` 仍然会生成：

```text
cleanup_calls
final_return_expr
cycles
cycle_condition
reason
```

但 `cleanup_calls` 现在是展示和解释信息，不是“每条路径必然执行的 cleanup”。资源义务是否解除，由 `missing_cleanup_candidates_cfg(...)` 在目标 label 后的真实 CFG 可达 return 状态上判断。

例如：

```c
out:
    if (cleanup)
        kfree(ptr);
    return err;
```

当前结果是：

```text
cleanup_calls 可以包含 kfree(ptr)     # 展示
可达 return 仍有 ACQUIRED 路径   # 语义
missing_cleanup 保留                     # 候选
```

无条件 `kfree(ptr)` 会在 CFG transfer 中把资源变为 `RELEASED`，因而消除候选。

label resolver 另一个重要作用是识别向前 retry/backedge，避免把“重试”误认为函数错误退出。

---

## 8. 资源状态与义务语义

### 8.1 资源状态

`ResourceState` 当前包括：

| 状态 | 含义 | 错误出口行为 |
|---|---|---|
| `UNSEEN` | 未建立资源义务 | 不报告 |
| `ACQUIRED` | 当前路径确定持有 | 生成 missing cleanup |
| `MAY_ACQUIRED` | 至少一条可能路径仍持有 | 生成降置信度候选 |
| `BORROWED` | 借用资源 | 不直接产生当前函数释放义务 |
| `TRANSFERRED` | 有确定语义支持的所有权转移 | 不报告 |
| `RELEASED` | 义务已解除 | 不报告 |
| `ESCAPED` | 已有明确 escape effect | 不报告 |
| `UNKNOWN` | 无法解释的状态或非持有冲突 | 不单独当作确定泄漏 |

`MAY_ACQUIRED` 用来避免将分析器的不确定性直接转换为“没有候选”。它主要出现在：

- widening 合并了持有与非持有路径；
- 无法解析的间接调用可能消费资源；
- 资源被存入字段，但没有明确 transfer contract。

每个 `HeldResource` 同时记录 `uncertainty_causes`，将状态和产生原因分开。当前会输出的原因包括：

```text
widening
unknown_indirect_call
incomplete_function_pointer_targets
partial_function_pointer_consumers
field_store_without_contract
may_summary_effect
exit_sensitive_summary_unresolved
loop_multiple_instances
unresolved_acquire_validity
```

因此“分支/widening 后仍可能持有”和“未知 effect 可能消费”不再只表现为同一个无来源的枚举值。该 provenance 目前是候选级解释信息，尚未单独进入 evidence score。

确定 summary effect 现在保留生命周期语义：release 写为 `RELEASED`，transfer 写为 `TRANSFERRED`，escape 写为 `ESCAPED`。三者在当前 missing-cleanup 检查中都表示本函数义务已解除，但不会再丢失解除方式。历史 `resource_ownership_transfers` 不再过滤 held resource，也不改变 `ownership_state`：命中时仅记录 `unreviewed_ownership_transfer_hint` provenance，供 ranking/复核解释使用。要确定解除义务，必须迁移为带参数位置、action 和 must/may 的 summary/semantic effect。

`may` summary 和未签约字段存储只会把仍为 `ACQUIRED/MAY_ACQUIRED` 的义务降为 `MAY_ACQUIRED`；它们不会把已经 `RELEASED` 的实例重新建立为持有状态。确定 release 只有在调用实参通过当前 alias/environment 唯一解析到同一 `resource_id` 时才解除该实例；widening 后丢失的歧义 alias 不会释放任一可能实例。

### 8.2 join 规则

`join_states(...)` 对任一包含 `ACQUIRED` 或 `MAY_ACQUIRED` 的冲突 join 保留 `MAY_ACQUIRED`。例如：

```text
join(ACQUIRED, RELEASED) -> MAY_ACQUIRED
join(ACQUIRED, UNSEEN)   -> MAY_ACQUIRED
join(MAY_ACQUIRED, TRANSFERRED) -> MAY_ACQUIRED
```

普通析取分支在达到上限前不会立即调用这些 join；该规则主要用于 widening 和普通单状态 solver。

### 8.3 资源描述

`HeldResource` 记录：

```text
var
acquire_func
resource_type
release_functions
acquire_line
resource_id
generation
multiplicity: one | many
release_cardinality: one | all | unknown
validity_guard
validity_guard_source: explicit | failed_check | compatibility_default | none
out_resource_arg
release_arg_index
release_arg_requires_address
release_suggestion_template
scope_cleanup_function
scope_cleanup_decl_line
aggregate_id
container_owner
membership_relation
ownership_state
uncertainty_causes
```

候选输出中的 `ownership_state` 用于区分确定持有和可能持有。

同一 acquire site 经 backedge 再次执行、且上一实例仍为 `ACQUIRED/MAY_ACQUIRED` 时，实例提升为 `multiplicity=many`，记录 `loop_multiple_instances`。默认 `effect_cardinality=one` 的 release/transfer/escape 只能将其保持为 `MAY_ACQUIRED`。`cardinality=all` 只有在配置提供可匹配的 `aggregate_id` 时才可确定解除 `many` 义务；没有 aggregate identity 的旧式 `all` 合约会保守保留为 `MAY_ACQUIRED + aggregate_identity_unresolved`，并由配置审计统计。`unknown` 与 `one` 一样保守保留。

对新式 aggregate/member API，状态里还维护 `aggregate_memberships`，记录：

```text
resource_id -> aggregate_id, relation
```

`resource_membership_functions` 可以声明类似 `list_add(resource, aggregate)` 的 membership 建立调用。配置带有 `membership_relation` 的 `many + all` 资源，只有当当前状态中存在匹配的 membership fact 时，`release_all(aggregate)` 才会确定解除该资源；如果看到 all-release 但 membership fact 不存在或不匹配，资源保持 `MAY_ACQUIRED` 并记录 `aggregate_membership_unresolved`。join 只保留两侧共同存在的 membership fact，因此条件 membership 不会在汇合后被误当作必然成员关系。

这仍不是完整容器/points-to 建模：当前只识别配置声明的 membership API 和模板表达式，不自动从任意字段写入、链表宏或 `container_of` 推导 membership。

### 8.4 获取建模与失败精化

每个 CFG 资源实例携带 `validity_guard` 和来源。显式 `validity_guard/acquire_success_guard` 标为 `explicit`，`failed_check=IS_ERR/IS_ERR_OR_NULL` 标为 `failed_check`。为兼容历史 resource map，未声明合约的返回指针仍生成 `<resource_id> != NULL`，out-parameter 仍生成 `return == 0`，但标为 `compatibility_default`。这类默认 guard 可识别确定失败边，不能证明确定成功；表面上的成功边仍输出 `MAY_ACQUIRED + unresolved_acquire_validity`。guard 中的资源表达式在创建时改写为 `resource_id`，不会因后续重赋值或 shadowing 改绑。

出口检查将当前 state facts 与错误条件假设一起求值：guard 为 false 时该路径没有释放义务；guard 未知时保留 `MAY_ACQUIRED` 并记录 `unresolved_acquire_validity`。旧的 acquire-failure/error-source 过滤仍保留为兼容防线，而不再是唯一机制。当前支持的常见谓词包括：

```text
IS_ERR(x), IS_ERR_OR_NULL(x)
x == NULL, x != NULL, !x, x
x >= 0, x < 0
PTR_ERR(x), PTR_ERR_OR_ZERO(x) 错误来源关系
bad = IS_ERR(x); if (likely/unlikely(bad)) ... 的布尔来源关系
简单 && 真分支事实
```

它没有增加独立 `PENDING_ACQUIRE` 枚举，但 guard 已成为资源模型本身的一部分。下列情况仍是部分支持：

- helper 封装的失败判断；
- 未配置 helper 传播后的失败判断；
- 复合短路条件的 false edge；
- 非零成功、复杂返回协议或未配置的 output-parameter contract。

### 8.5 路径事实

`ResourceFlowState.path_facts` 是一组 `(atom, truth)`，当前主要表示：

```text
valid:<expr>
nonnegative:<expr>
error_source:<error-var>:<resource-expr>
is_err_source:<boolean-var>:<resource-expr>
expr:<normalized-condition>
```

边 transfer 遇到矛盾事实时会删除不可行的状态。当变量被重新赋值或自增/自减时，与它相关的旧事实会失效。

`ResourceFlowState.pending_summary_effects` 保存尚待调用返回值分支证明的出口敏感 effect，其身份包含 `call_site_id/resource_id/result_var/result_symbol_id/result_version/action/strength/exit_class/return_guard/effect_cardinality`。赋值、自增减或通过 output parameter 修改结果变量时会推进 definition version 并失效旧 pending effect；scope exit 也会丢弃绑定到离开作用域的 result symbol。分支 edge 添加新 facts 后才判断 `return_guard`。widening 只保留两侧完全相同的 pending effect，不会合并不同调用或版本。

这是轻量谓词传播，不是一般约束求解器。

### 8.6 别名、字段和函数指针

当前别名能力包括：

- `alias = ptr` 的简单绑定；
- `swap(a, b)` 的绑定交换；
- 别名上的 release；
- 函数指针声明/赋值的简单目标集；
- `function_target_complete` 显式记录每个函数指针绑定是否闭合；
- `ops->callback(...)`、`table[index](...)` 等复杂 callee 表达式保留其完整文本身份；
- 只有 `target_set_complete` 且所有目标均为 must consumer 时解除义务；
- 目标集含未知或只有部分消费时转为 `MAY_ACQUIRED`。

字段存储不再被无条件视为 transfer：

```c
holder->ptr = ptr;
```

若没有 reviewed semantic contract，`ptr` 变为 `MAY_ACQUIRED`，候选保留并降低置信度。

CFG 资源表现在以 `resource_id` 为主键，表达式只存在于 `aliases/environment` 绑定中。ID 形态为：

```text
<normalized-expression>@<acquire-line>:<acquire-function>#<generation>
```

同一变量在不同 acquire site 再次获取资源时会创建新 generation；旧 alias 继续指向旧实例，因此 `old = ptr; ptr = acquire(); release(old)` 不会错误释放新实例。

无法解析的 `fn = table[index]`、只在部分分支赋值、或把 `&fn` 传给未知注册函数时，目标集合会显式降为 incomplete。字段/表 callee 没有局部目标集时按未知间接调用保守处理。

嵌套 compound CFG 带 `scope_enter/scope_exit`。`ResourceFlowState.scope_frames` 记录进入作用域前的 alias、scope cleanup、函数指针目标、definition version、轻量 `symbol_ids` 和相关 path facts；仅对该作用域内声明的名字恢复绑定。作用域内声明会分配形如 `sid_<n>_<name>_<start_byte>` 的轻量 symbol id；当 path fact 触及 shadowed 名字时，事实绑定到 symbol/resource id，而不是继续污染外层同名文本变量。`goto/break/continue/return` 边携带 `scope_unwind`，edge transfer 会按跨越的作用域层数调用 `_leave_scope()`，因此非正常离开也会执行 scope cleanup 并恢复外层绑定。资源实例本身不会随名字离开作用域而删除。

这仍不是完整 SSA/context-sensitive symbol 模型：循环中同一 acquire site 使用一个带 `many` 标记的抽象实例；没有进入 shadow-sensitive scope 的普通变量仍以规范化文本为主；复杂聚合、数组下标相等性和跨函数 points-to 也未覆盖。`function_target_complete` 是局部赋值闭包状态，不是全程序 points-to 完备性证明。

### 8.7 scope cleanup

当前支持：

- `__free(name)` 形式；
- `scope_cleanup_macros` 配置的 cleanup macro；
- cleanup-managed alias 将释放函数绑定到原资源。

仅当 scope cleanup 函数属于资源的 `release_functions` 时，它才证明义务解除。

### 8.8 出口检查

对 AST/CFG 函数，候选判定流程是：

```text
错误条件 block
  -> goto target label 或条件后续 CFG
  -> 枚举可达 return_statement blocks
  -> 只保留与错误条件 path facts 兼容的状态
  -> 查看相同 acquire identity 是否仍为 ACQUIRED/MAY_ACQUIRED
  -> 生成 missing cleanup
```

只在没有 AST/CFG 可用时，才回退到基于 `cleanup_calls` 的线性判断；此时整条路径已经被标记为 `low`。

`ErrorPath.resource_analysis` 明确记录结论来源：

```text
cfg              # CFG 可达出口资源状态是事实来源
linear-fallback  # CFG 无法形成可达出口结论，回退线性 cleanup 判断并强制 low
linear-degraded  # 文本兼容路径，默认 low
```

候选层对 `resource_analysis=cfg` 的 `missing_cleanup_candidates` 直接信任，不再用展示级 `cleanup_calls` 二次删除。旧 CSV、`linear-fallback` 或 `linear-degraded` 输入才使用历史兼容过滤。

---

## 9. 跨函数 effect summary

### 9.1 summary schema

`SummaryEffect` 包含：

```text
resource: argN | return
action: acquire | borrow | transfer | release | escape | unknown
strength: must | may
exit_class: any | success | error
return_guard
effect_cardinality: one | all | unknown
must_reason
condition
resource_type
release_functions
evidence chain
```

`FunctionSummary` 记录：

```text
function
parameters
effects
callees
unresolved_calls
iterations
```

`function_summaries.json` 额外记录 `call_graph`、`converged` 和总 `iterations`。

### 9.2 直接 effect 推导

工具从函数体中识别：

- 已知 release API 作用于哪个形参；
- output-parameter acquire；
- 返回值 acquire 及直接 wrapper return；
- 形参存入字段的 `may escape` effect；
- 直接返回参数的 transfer effect；
- 简单 `if (condition) release(arg)` 的条件 effect。

自动 field-store summary 不再把存入字段解释为确定 ownership transfer。它生成 `action=escape, strength=may`；调用点将资源保持为 `MAY_ACQUIRED`，记录 `may_summary_effect`，而不是解除义务。

自动 release/out-parameter effect 只有在 `analysis_quality=tree-sitter`、`unsupported_nodes` 为空、callee 和实参映射可精确解析，且 call event 位于可隔离的 call-only/assignment/direct-return block 中，并 postdominate CFG exit 时，才推导为 `must`。如果 release 调用与其他控制语义混在同一 block 中，当前保守降为 `may`，避免把“删除整个 block 后不可达”误当作“删除 call 后不可达”。GNU case range/switch prelude 等仍 unsupported 的 switch 子结构、`unresolved_goto`、degraded parser、绕过调用的出口或不精确调用均强制降为 `may`。无 AST 输入不能生成自动 `must`。确定 effect 的 `must_reason` 输出 `complete_cfg/cfg_postdominating_effect/exact_callee/exact_argument_mapping`等独立证据；reviewed seed 则记录 `reviewed_seed`。

schema v4 支持 reviewed effect 的 `exit_class/return_guard`、`effect_cardinality` 和 `must_reason`。调用形如 `ret = submit(ptr)` 时，effect 不会在 call block 立即解除义务，而是以 call-site/result-definition version 身份进入 pending 集合；只有后续 edge facts 证明 `return == 0` 等 guard，且结果变量版本未失效时才应用。

当前不会自动从一般 callee CFG 推导 success/error-specific effect。出口敏感 effect 主要来自 reviewed seed；直接 `return callee(...)`，以及规范的 `ret = callee(...); if (ret) return ret; return 0;` 状态转发 wrapper，可以原样传播其出口类别。后者要求结果变量未重赋值、返回表达式仅为该变量或 `0`，且分支 guard 与 callee `return_guard` 对应。其他无法证明返回类别保持关系的传播会降为 `strength=may, exit_class=any`。

### 9.3 不动点传播

`infer_function_summaries(...)` 对所有本地函数迭代传播 callee effect，默认最多 50 轮：

```text
a(arg0) -> b(arg0)
b(arg0) -> c(arg0)
c(arg0) -> release(arg0)

不动点后：a/b/c 都可带 release effect
```

它构建调用图并做全局不动点迭代，能处理有限的递归/互递归传播。当前会用 Tarjan SCC 给 effect 标注 `origin_scc`，例如互递归 `cycle_a/cycle_b` 会输出 `cycle_a+cycle_b`；但求解器本身仍是全局迭代，不是按 SCC 分层调度，也没有 context-sensitive call string。

条件会从 callee 的 `argN` 重映射到 caller 实参，并避免因重复加括号导致不收敛。

若达到迭代上限仍未收敛，summary DB 输出 `converged=false`。此时所有自动推导的 `must` effect 都会降为 `may`，清空 `must_reason`，并记录 `convergence_status=not_converged`；只有 `origin_kind=reviewed_seed` 的原始 reviewed seed 保留 `must`。从 reviewed seed 经过 wrapper 或递归传播得到的 effect 标为 `origin_kind=derived_from_reviewed_seed`，在全局非收敛时仍会降级。每个 effect 还输出轻量 provenance：`origin_scc`、`origin_kind`、`convergence_status` 和 `propagation_depth`。

### 9.4 reviewed effect seed

`resource_map.interprocedural_effect_seeds` 是可直接进入数据流的审查合约。例如：

```json
{
  "set_delayed_call": {
    "resource": "arg2",
    "action": "transfer",
    "strength": "must",
    "exit_class": "success",
    "return_guard": "return == 0",
    "condition": "always",
    "evidence": "set_delayed_call registers arg2 for callback-owned cleanup"
  }
}
```

这类 seed 有明确的参数位置、action、strength 和可选出口 guard，因而是静态语义，不是 ranking hint。`strength` 省略时为 `must`，`exit_class` 省略时为 `any`，`effect_cardinality` 省略时为 `one`，只有 reviewed 合约应声明 `all`。

### 9.5 跨函数边界

- 主流程只用 `analysis_quality == tree-sitter` 的函数推导 summary；
- 未知的参数调用记入 `unresolved_calls`，不自动当作 release；
- 无法解析的间接调用在函数内数据流中保留 `MAY_ACQUIRED`；
- 函数指针、宏 wrapper、返回别名和引用计数语义仅部分建模。
- summary 不动点仍是 context-insensitive 全局迭代；直接 must effect 会查询函数 CFG 的出口必经性，但不读取资源 dataflow 的 widened/truncated 状态。
- 一般 success/error-specific effect 仍不会从 callee CFG 自动推导，返回值关系只支持 reviewed guard、直接 return 和规范状态转发 wrapper。

---

## 10. 配置层与事实所有权

`configs/README.md` 定义了五层配置。这些层可以包含重叠 API 名，但它们服务于不同阶段。

| 层 | 文件 | 是否影响候选生成 | 用途 |
|---|---|---:|---|
| 静态资源状态 | `*_resource_map.json` | 是 | acquire/release、scope cleanup、callee consumer、semantic transfer、effect seed |
| ranking protocol | `*_resource_protocols/*.json` | 否 | 候选后的 E2 协议证据和 required action |
| wrapper summary | `*_wrapper_summaries.json` | 否 | 保守 wrapper/alias exception hint |
| reviewed exception | `*_review_false_positives.json` | 是/排序 | 精确的已审查 suppression 和 confirmed-bug exception |
| historical fix | `*_historical_fixes.json` | 否 | 将已生成候选升级为历史修复证据 |

### 10.1 resource map 主要 schema

`acquire_functions` 中单个 API 可配置：

```text
resource_type
release: string | list[string]
failed_check
validity_guard
acquire_success_guard
direct_resource_arg
out_resource_arg
out_arg_requires_address
release_arg_index
release_arg_requires_address
release_cardinality
aggregate_id
container_owner
membership_relation
release_suggestion
```

resource map 顶层还可包含：

```text
callee_resource_consumers
resource_ownership_transfers
scope_cleanup_macros
interprocedural_effect_seeds
review_false_positive_contracts_file
stale_error_retry_contracts
error_output_contracts
```

不同文件系统只使用其中的一部分。

`interprocedural_effect_seeds` 的 effect 字段为：

```text
resource, action, strength
exit_class, return_guard
effect_cardinality
aggregate_id, container_owner, membership_relation
condition, resource_type, release_functions, evidence
```

`exit_class` 默认为 `any`；`success/error` effect 应同时给出能映射到调用返回变量的 `return_guard`。当前 guard 求值只覆盖资源数据流已经支持的零值、非零值和正负谓词。

`ResourceTracker.config_audit` 会在主流程 stdout 中输出：

```text
config_explicit_acquire_contracts
config_compatibility_default_acquires
config_release_all_without_aggregate_identity
config_reviewed_all_effects_without_aggregate_identity
config_membership_relation_without_membership_api
```

这些统计用于迁移审计，不直接改变候选排序；真正影响数据流的是 acquire/release/effect 合约本身。

### 10.2 API 配置漂移审计

`--audit-api-drift` 会调用 `src/api_drift_audit.py`，把当前扫描到的函数定义/调用名，与 `resource_map`、`resource_protocols` 和 `wrapper_summaries` 中的 lifecycle API 配置做一致性检查。默认输出位于 `--out` 同目录：

```text
api_drift_report.json
api_drift_report.csv
```

该审计只生成诊断，不参与资源状态传播，也不会 suppress 候选。它覆盖以下风险：

```text
configured_function_unobserved
protocol_acquire_missing_from_resource_map
protocol_release_missing_from_resource_map
protocol_release_resource_type_mismatch
wrapper_release_action_unknown
unconfigured_similar_lifecycle_api
frequent_missing_cleanup_action
```

其中 `unconfigured_similar_lifecycle_api` 是名称启发式：如果当前源码中出现 `ext4_journal_stop_handle(...)` 这类未配置函数，而它和已配置的 `ext4_journal_stop(...)` 在 token/prefix 上高度相似，会被列为“疑似 release alias / API rename / wrapper”。这不是语义证明，只是提醒人工检查配置是否漂移。

若同一 missing cleanup action 在候选中高频出现，`frequent_missing_cleanup_action` 会提示可能存在未建模 wrapper、release alias、ownership transfer 或 API 改名。它同样不改变主候选，只帮助解释“为什么某类候选突然暴增”。

主流程 stdout 会输出：

```text
api_drift_observed_api_names
api_drift_configured_api_names
api_drift_issues
api_drift_high
api_drift_medium
api_drift_low
api_drift_csv_rows
api_drift_json
api_drift_csv
```

### 10.3 semantic contract 与 hint

必须遵守以下区分：

```text
有明确 argN/resource expression + action + condition
  -> 可以进入数据流

只有 function name/resource kind/name pattern
  -> 只能是 ranking hint
```

`wrapper_summaries.json` 当前没有统一的 must/may effect 和参数位置 schema，所以只用于 ranking。若需要让确定 wrapper 直接改变资源状态，应将它放入 `interprocedural_effect_seeds` 或让自动 summary 从函数体推导，不能仅依赖 ranking wrapper 文件。

历史 `resource_ownership_transfers` 同样只是静态阶段的兼容 hint：它记录 `unreviewed_ownership_transfer_hint` provenance，但不得删除 held resource，也不得把 `ACQUIRED` 改写为 `MAY_ACQUIRED`。只有 reviewed semantic effect 或自动 summary effect 才能改变资源状态；ranking hint 只能影响后续排序和复核解释。

### 10.4 reviewed suppression

reviewed exception 分为：

- `rules`：稳定的函数级合约；
- `path_rules`：要求精确 `path_id` 的路径规则。

confirmed-bug exception 的优先级高于 false-positive suppression。新 suppression 应记录 `rule_id`、审查来源和适用范围，不应以实验版本名复制新配置文件。

---

## 11. 候选生成

### 11.1 输入边界

`candidate_checker.py` 读取 `error_paths.csv`，对每行调用 `run_candidate_rules(...)`。默认主流程不会把 `low` 路径交给它；规则自身也会对某些 low 路径做额外过滤。

### 11.2 候选类型

| 类型 | 当前规则 | 主要边界 |
|---|---|---|
| `missing_cleanup` | 有 held resource 且有 missing release | 依赖 resource map、alias 和 CFG 出口准确性 |
| `partial_cleanup` | CFG 同一可达错误出口上，同时存在已解除和仍持有的入口资源实例 | CFG 模式不读取展示调用；旧/降级 CSV 才使用兼容规则 |
| `error_swallowed` | 条件包含常见 error variable，最终返回 `0` 或部分 NULL 语义 | 是启发式规则，不跟踪完整 error provenance |
| `stale_error_after_retry` | 基于 reviewed `stale_error_retry_contracts` 精确匹配 | 不是通用 stale-error 数据流 |

### 11.3 severity

`P1/P2/P3` 是 triage 严重度，不是置信度。当前规则大致为：

```text
P1: journal_handle, mutex/rwsem/spinlock, return-0 error swallowing
P2: buffer_head, memory, posix_acl, partial cleanup
P3: 其他未分类资源
```

### 11.4 候选 ID

ranking 阶段区分路径聚合 ID 和资源义务 ID。当前 ID 使用 SHA-256 的前 20 个十六进制字符：

```text
path_candidate_id = candidate_<sha256-20>
llm_task_id = llm_review_<sha256-20>
obligation_candidate_id = obligation_<sha256-20>
```

AST 路径 fingerprint 依赖 `file/function/condition_start_byte/condition_end_byte/branch_taken/cfg_edge_kind/candidate_type/error_line`；没有 byte range 的降级路径才回退到 `path_id`。obligation ID 在此基础上再绑定 `resource_id + missing action`，因而同一路径上的 `kfree(ptr)` 和 `brelse(bh)` 可分别审查。

ranking 输出现在按 obligation 展开：一个资源释放义务对应一条 ranking 记录，`candidate_id` 使用该 obligation ID，`path_candidate_id` 保留共享路径身份用于 UI 分组和旧数据关联。单 obligation 记录仍允许读取旧的 path/task/manual label 以兼容历史产物；同一路径存在多个 obligation 时，manual/LLM lookup 优先使用各自 obligation/task ID，避免一个义务的标签污染另一个义务。为读取已有人工/LLM 标签，同时输出并索引原 SHA-1/12 的 `legacy_candidate_id/legacy_llm_task_id`；新产物不应继续生成 legacy ID。

---

## 12. 证据排序

### 12.1 证据来源

ranking 聚合：

```text
static_evidence
protocol_evidence
wrapper_evidence
ownership_transfer_hints
historical_fix_evidence
manual_review
llm_evidence
```

其中 protocol/wrapper/ownership/LLM 不改变已生成的静态候选；manual review 改分，historical fix 增加证据层级。

### 12.2 evidence level

代码定义的标签包括：

```text
E0_STATIC_RULE_ONLY
E1_LLM_TRUE_CANDIDATE
E2_API_PROTOCOL_SUPPORTED
E3_REPAIR_PATCH_SUPPORTED
E3_HISTORICAL_FIX_CONFIRMED
E4_DYNAMICALLY_REPRODUCED
E5_UPSTREAM_CONFIRMED
```

当前 `_evidence_level(...)` 实际自动选择的只有：

```text
historical fix -> E3_HISTORICAL_FIX_CONFIRMED
else protocol  -> E2_API_PROTOCOL_SUPPORTED
else LLM       -> E1_LLM_TRUE_CANDIDATE
else           -> E0_STATIC_RULE_ONLY
```

E3 repair patch、E4 dynamic、E5 upstream 常量为扩展保留，当前不由这个静态 ranking 函数自动产生。

evidence level 是一个优先标签，不是严格单调的证明强度格。例如 LLM 信号不自动强于精确静态 witness。

### 12.3 当前 scoring

`_score(...)` 当前使用累加式启发分数：

```text
E0 static base                                      +10
LLM true_candidate auxiliary signal                +20
protocol without exception hints                   +30
protocol with exception hints                      +10
historical source fix                              +40
P1 / P2 severity                                   +20 / +10
error_swallowed final return 0                     +20
journal/lock protocol, clean / hinted              +20 / +5
buffer_head/memory protocol, clean / hinted        +10 / +3
manual review adjustment                           variable
```

该分数只适合排序，不是经过校准的真实概率。静态规则、protocol、severity 和 resource-kind bonus 可能源自同一条资源事实，因此存在相关证据重复计分风险。对分数做结论时必须同时展示 `score_explanation`。

为避免把同源加分误读成独立证据数量，ranking 额外输出 `score_dimensions`：

```text
static_certainty       # CFG、widening/truncated、资源不确定性
model_certainty        # LLM 信号，缺失时为 0
protocol_support       # 协议支持，不等于历史确认
historical_confirmation # 严格匹配的历史修复
external_confirmation  # 上述两者的兼容聚合值
impact                 # P1/P2/P3 影响维度
review_priority        # 保留兼容的现有总排序分
```

这些维度不相加宣称为概率；`review_priority` 仍保留旧启发式总分以维持实验兼容，论文或人工界面应优先并列展示各维度。

### 12.4 exception hints

wrapper 或 ownership hint 会生成：

```text
has_exception_hints
exception_hints
released_by_wrapper_possible
ownership_transfer_possible
```

这些字段表示“需要人工检查的可能例外”，不表示静态分析已证明资源释放或转移。

### 12.5 历史修复和人工标签

Historical fix 要求精确匹配文件、函数、候选类型和影响行；在 obligation 级 ranking 中还可通过 `obligation_id/resource_id/resource_id_pattern/resource_type/acquire_func/missing_cleanup/missing_action/missing_arg` 等 selector 进一步限定。它只附加到已有 obligation，不反向生成或删除候选。若历史修复只描述路径行号而没有 obligation selector，则同一路径多义务场景仍应优先补充 selector 后再用于强证据。

Manual review 查找顺序优先 obligation ID 和 obligation task ID，并带来 source-aware score adjustment。旧 path/task/legacy ID 只在该路径只有一个 obligation 时作为兼容 fallback；同一路径存在多个义务时，不会把旧 path-level 标签自动复制为每个 obligation 的 gold label。LLM task builder 在提供 ranked JSONL 时同样按 obligation 任务粒度输出。

---

## 13. 输出契约

### 13.1 `error_paths.csv`

固定列：

```text
linux_git_commit, linux_git_tag
file, function, function_start_line, function_end_line
path_id, error_line
condition, condition_type, branch_taken
condition_start_byte, condition_end_byte
cfg_edge_id, cfg_source_block, cfg_target_block, cfg_edge_kind
cfg_witness
error_var, error_source_expr
exit_type, target_label
cleanup_calls, final_return_expr
held_resources, missing_cleanup_candidates
released_cleanup_candidates, partial_cleanup
resource_analysis
confidence, reason
```

JSON 字段：

```text
cleanup_calls
held_resources
missing_cleanup_candidates
released_cleanup_candidates
cfg_witness
```

`held_resources` 中包含 `resource_id/generation/multiplicity/release_cardinality/validity_guard/validity_guard_source`、acquire 位置、预期 release、scope cleanup、`aggregate_id/container_owner/membership_relation`、`ownership_state` 和 `uncertainty_causes`。`cfg_witness` 是历史字段名，对象的 `kind=cfg_analysis_snapshot`，包含入口 edge identity、byte range、scope unwind、CFG completeness、source state 数、可达 block、unsupported range、return 出口状态快照、symbol IDs、trace metadata/anchors 及 widening/truncated 标志。`released_cleanup_candidates` 和 `partial_cleanup` 是逐个 return block 的逐个 `ResourceFlowState` 计算；不会将不同析取状态的 released/missing 集合后伪造 partial cleanup。

### 13.2 `suspicious_candidates.csv`

```text
linux_git_commit, linux_git_tag
file, function, path_id, error_line
candidate_type, severity
condition, branch_taken, condition_start_byte, condition_end_byte
cfg_edge_id, cfg_source_block, cfg_target_block, cfg_edge_kind, cfg_witness
exit_type, target_label, error_source_expr
held_resources, cleanup_calls, missing_cleanup_candidates
released_cleanup_candidates, partial_cleanup
resource_analysis
final_return_expr, evidence, reason
```

### 13.3 `function_summaries.json`

```text
schema_version = 4
converged
iterations
call_graph
summaries[]
  function, parameters, effects, callees, unresolved_calls, iterations
  effects[]: resource, action, strength, exit_class, return_guard,
             effect_cardinality, must_reason,
             origin_scc, origin_kind, convergence_status, propagation_depth,
             condition, resource_type,
             release_functions, evidence
```

### 13.4 `ranked_candidates.jsonl`

每行的主要结构：

```text
candidate_id, path_candidate_id, obligation_id, obligation_candidate_ids
resource_id, missing_cleanup
legacy_candidate_id, llm_task_id, legacy_llm_task_id
candidate_type, severity
evidence_level, evidence_score, score_dimensions
static_evidence
protocol_evidence
historical_fix_evidence
wrapper_evidence
ownership_transfer_hints
has_exception_hints, exception_hints
manual_review, manual_score_adjustment
score_explanation
llm_evidence
missing_evidence
file, function, path_id, error_line, condition, branch_taken,
cfg_edge_id, cfg_edge_kind, cfg_source_block, cfg_target_block, cfg_witness,
resource_analysis, final_return_expr
```

### 13.5 `candidates_with_evidence.csv`

该文件是 ranking JSONL 的扁平摘要，包含：

```text
candidate_id, path_candidate_id, obligation_id, obligation_candidate_ids
resource_id, missing_cleanup, legacy_candidate_id
branch_taken, resource_analysis
evidence_level, evidence_score
historical_fix_ids, fixed_versions
matched_protocol_ids, required_actions
exception hint 字段
manual review 字段
score_explanation, missing_evidence
final_return_expr
```

### 13.6 LLM 输出

| 文件 | 作用 |
|---|---|
| `llm_review_tasks.jsonl` | 候选/obligation、源码上下文、协议摘要和复核问题 |
| `deepseek_reviews.jsonl` | 模型原始结构化输出和错误状态 |
| `deepseek_true_candidates.jsonl` | `verdict == true_candidate` 的子集 |

LLM 输出必须保留 model、调用参数和任务 ID 才可复现。提供 `ranked_candidates.jsonl` 时，task builder 使用 ranked item 的 `llm_task_id/obligation_id/resource_id/missing_cleanup`，使模型复核粒度与 ranking 记录一致；没有 ranking 输入时才兼容旧的候选 CSV 行粒度。

---

## 14. 一条 missing-cleanup 路径如何形成

以简化的 journal handle 为例：

```c
handle = ext4_journal_start(inode, credits);
if (IS_ERR(handle))
    return PTR_ERR(handle);

ret = do_work(handle);
if (ret)
    goto out;

ext4_journal_stop(handle);
return 0;

out:
    if (already_stopped)
        ext4_journal_stop(handle);
    return ret;
```

### 14.1 acquire

resource map 指定：

```json
{
  "ext4_journal_start": {
    "resource_type": "journal_handle",
    "release": ["ext4_journal_stop"],
    "failed_check": "IS_ERR"
  }
}
```

数据流在 acquire site 建立 `handle: ACQUIRED`。

### 14.2 acquire failure edge

`IS_ERR(handle)` true edge 建立 `valid:handle = false`，`PTR_ERR(handle)` 建立 error-source 关系。在该错误 return 上，resource tracker 识别这是 acquire failure，不产生 `ext4_journal_stop(handle)` 候选。

### 14.3 work failure edge

`ret` true edge 通过 `goto` 进入 `out` label。CFG 继续执行 label 后结构。

### 14.4 conditional cleanup

`already_stopped` true 路径把 handle 变为 `RELEASED`；false 路径仍为 `ACQUIRED`。析取 solver 保留两条路径。

### 14.5 exit obligation

`missing_cleanup_candidates_cfg(...)` 在可达 `return ret` 的状态中看到至少一个 `ACQUIRED`，因此保留：

```text
ext4_journal_stop(handle)
```

`cleanup_calls` 虽然包含 `ext4_journal_stop(handle)`，但它只用于展示，不会把条件释放误认为 must release。

### 14.6 ranking

候选生成后，protocol matcher 可以匹配 journal protocol，然后添加 E2 证据和分数。该协议证据不是候选存在的原因；候选已经由 CFG 资源义务成立。

---

## 15. 当前能力矩阵

### 15.1 已实现

| 能力 | 证据 |
|---|---|
| frontend-neutral IR schema v1 | `src/frontend/`；translation unit/function/node/symbol/call/access-path/diagnostic/CFG 可序列化 |
| tree-sitter IR adapter | 主流程使用 `TreeSitterFrontend`；候选/summary parity、schema/round-trip/determinism/golden tests |
| 解析质量降级隔离 | `analysis_quality`, low-confidence filter, `quarantined_error_paths.csv`, `quarantined_candidates.csv` |
| `if`/循环/`goto`/`return` CFG | `cfg.py` |
| 普通 `switch/case/default` CFG | case/default/no-match dispatch、fallthrough、嵌套 switch/loop break/continue、10 个 ext4 v6.14 golden |
| 有界析取数据流 | `dataflow.py` |
| `MAY_ACQUIRED` fail-open 防护 | `resource_state.py` |
| `MAY_ACQUIRED` uncertainty provenance | `HeldResource.uncertainty_causes` |
| acquire-site/generation resource ID | `HeldResource.resource_id`, expression-to-ID aliases |
| scope-local lightweight symbol ID | `ResourceFlowState.symbol_ids`, `PendingSummaryEffect.result_symbol_id` |
| 循环同 site multiplicity | `HeldResource.multiplicity`, `loop_multiple_instances` |
| aggregate-aware action cardinality | `release_cardinality/effect_cardinality` + `aggregate_id`，缺失 aggregate 时保守降级 |
| label 后 CFG 终点义务检查 | `cleanup_outcome_cfg` / `missing_cleanup_candidates_cfg` |
| if true/false branch binding | `ErrorPath.branch_taken` |
| CFG analysis snapshot | byte range、edge ID、scope unwind、CFG completeness、unsupported ranges、return states、symbol IDs、representative trace/anchors、widening/truncated |
| 基础 NULL/ERR_PTR/整数谓词 | `resource_tracker.py` path facts |
| acquire validity guard | NULL/ERR_PTR、布尔 IS_ERR alias、out-parameter return guard |
| 简单 alias/swap/function pointer | `resource_tracker.py` |
| 普通 compound shadowing | `scope_enter/scope_exit`, `ResourceFlowState.scope_frames` |
| 非正常 scope unwind | `CFGEdge.scope_unwind`, goto/break/continue/return edge transfer |
| 函数指针目标完整性状态 | `function_target_complete` |
| scope cleanup | `__free`, configured macros |
| 自动跨函数 summary | `function_summary.py` |
| reviewed external effect seed | `interprocedural_effect_seeds` |
| reviewed 出口敏感 effect | `exit_class`, `return_guard`, pending edge application |
| pending effect identity | `call_site_id`, result symbol/definition version, scope/reassignment invalidation |
| summary SCC provenance | `origin_scc`, `origin_kind`, `convergence_status`, `propagation_depth` |
| resource-map migration audit | `src/resource_config_audit.py`, main stdout config audit counters |
| obligation-level ID | path ID + resource ID + missing action; SHA-256/20 + legacy lookup |
| obligation-level historical evidence | historical fix selector 可绑定 obligation/resource/action |
| retry/backedge 过滤 | `label_resolver.py`, `error_path_extractor.py` |
| 候选、协议、历史、人工和 LLM 链路 | 对应 `src/` 模块和输出 |

### 15.2 部分实现

| 能力 | 当前范围 | 主要缺口 |
|---|---|---|
| acquire failure refinement | 实例 guard；NULL/ERR_PTR/PTR_ERR；布尔 IS_ERR alias；out return guard | 无一般 helper contract、复合 false-edge 求解和独立 pending state |
| resource instances | acquire site + expression generation；循环同 site 提升为 `multiplicity=many` | 不展开循环迭代实例和调用上下文 |
| alias/scope | 简单变量、swap、compound 遮蔽、非正常 scope unwind、scope-local symbol ID、部分字段/数组表达式 | 完整 SSA、跨函数 symbol identity、聚合对象和 points-to 不完整 |
| 函数指针 | 局部目标集及 completeness；字段/表调用保守识别 | completeness 不是全程序证明；间接调用图、宏表和跨编译单元不完整 |
| 路径可行性 | 简单相等/空值/正负谓词 | 无一般布尔化简和 SMT |
| 跨函数 | 参数/返回 effect 全局不动点；must/may；reviewed success/error guard；规范状态 wrapper 传播；SCC provenance；非收敛时自动 must 降级 | 不自动推导一般出口类别，无 SCC 分层调度、context sensitivity 和完整 alias summary |
| witness | analysis snapshot：acquire/guard、edge identity、scope unwind、CFG completeness、unsupported ranges、return states、symbol IDs、压缩 representative trace 和 anchors | 无完整 state predecessor graph 和逐 block before/after transition log |
| 证据排序 | obligation 级记录、多源启发式分数 | 未校准，相关证据可能重复计分 |
| 分维度 ranking | static/model/protocol/history/external/impact/review_priority | review_priority 仍兼容旧总分，未做概率校准 |

### 15.3 未实现

```text
compile_commands/Kbuild-aware preprocessing
Clang typed AST/CFG
full SSA, loop-instance expansion and context-sensitive resource identity
field-sensitive and context-sensitive points-to
general SMT feasibility
complete macro/header semantic extraction
automatic dynamic reproduction
automatic upstream acknowledgement
probabilistically calibrated confidence score
```

---

## 16. 主要风险与误报/漏报方向

| 风险 | 可能误报 | 可能漏报 | 当前缓解 |
|---|---|---|---|
| resource map 滞后 | 新 release wrapper 未识别 | 新 acquire API 未跟踪 | 版本化配置、审查、未来 API drift checker |
| 宏/头文件语义 | cleanup 被遗漏 | acquire/transfer 被遗漏 | degraded quality、effect seed、人工复核 |
| 复杂 alias | 别名 release 未匹配 | 文本 symbol/聚合 alias 混淆 | resource ID + alias/swap + scope frame/unwind + scope-local symbol ID；仍需完整 SSA/points-to |
| 字段存储 | 实际 transfer 却保留候选 | 若配置过宽可错误解除 | 默认 `MAY_ACQUIRED`，只信 reviewed contract |
| 未知间接调用 | 实际 consume 但保留候选 | 旧 UNKNOWN 策略会漏报 | 现使用 `MAY_ACQUIRED`、记录原因并降置信度 |
| acquire guard 未解 | 可能保留失败 acquire 候选 | 过宽 contract 可错误删除义务 | 兼容 guard 不证明成功；未知转 `MAY_ACQUIRED`并统计 |
| 函数指针闭包 | 不完整目标集保留候选 | 错误标为 complete 会漏报 | 未解析赋值、缺失分支及 `&fn` escape 自动降为 incomplete |
| 出口敏感 summary | guard 无法证明时保留候选 | reviewed guard 配错可能错误解除 | pending effect 只在 edge facts 证明后应用；一般自动推导尚未开放 |
| 循环多实例 | 抽象 `many` 可能保留已全部释放的候选 | 错误 `all` + aggregate 合约可过度解除 | 按 modified variables 失效 facts；默认 one；`all` 必须有 aggregate identity，否则保守降级并审计 |
| 条件 cleanup | 若谓词不可判定则保守报告 | 静态列表曾会误抑制 | CFG 可达 return 状态是语义来源 |
| 文本降级 | 语法误识别 | 函数/路径遗漏 | 强制 low，默认不输出，不进 summary |
| ranking 相关证据 | 兼容总分仍可能过高 | 例外 hint 可过度降分 | obligation 级展开，protocol/history 分维度展示，不用总分做 bug 概率 |

---

## 17. 开发和回归不变量

修改核心分析时应保持：

1. `cleanup_calls` 可展示，但不能在 CFG 可用时独立证明 must release。
2. 只有明确 semantic effect 才能转为 `RELEASED/TRANSFERRED/ESCAPED`。
3. 未知间接调用和未证明字段 transfer 必须保留 `MAY_ACQUIRED`。
4. `MAY_ACQUIRED` 必须保留 `uncertainty_causes`，不得只输出无来源状态。
5. acquire failure 路径不得生成释放义务。
6. degraded parser 产物不得成为默认 high/medium 候选或 summary 事实。
7. ranking protocol/wrapper/ownership/LLM 不得反向删除静态候选。
8. 新的 reviewed suppression 必须同时增加真阳性和假阳性边界测试。
9. 所有实验应记录 Linux commit/tag、配置文件、启用的分析开关和 CFG/summary 诊断。
10. `may` effect 或字段存储不得把 `RELEASED/TRANSFERRED/ESCAPED` 重新提升为持有义务。
11. `success/error` effect 只有在调用返回 guard 被当前 CFG edge facts 证明时才能解除义务。
12. backedge 不得永久携带上一轮循环条件事实；循环中仍活跃的同 site acquire 必须保留 multiplicity 不确定性。
13. acquire guard 必须绑定 `resource_id`；无法证明 guard 时不得把失败路径当作确定持有或确定未持有。
14. 函数指针只有在目标集 complete 且所有目标均 must consume 时才能解除义务。
15. 同一条件文本的不同 AST 节点必须具有不同 byte range/CFG edge identity。
16. 普通 compound 退出后必须恢复该作用域内声明名字的外层绑定，不能删除仍活跃的资源实例。
17. 只有 tree-sitter 且 CFG 完整的自动 summary 才能产生 `must`，并必须输出 `must_reason`。
18. `resource_ownership_transfers` 兼容 hint 不得过滤 held resource，也不得改变 `ownership_state`。
19. pending effect 必须绑定 call site、result symbol 和 result definition version；重赋值、out-parameter 修改或离开 shadowing scope 后不得由旧 guard 触发。
20. `partial_cleanup` 必须在同一 return block 的同一析取 state 内判定。
21. `multiplicity=many` 只能被带 aggregate identity 的 reviewed `cardinality=all` 确定解除；缺少 aggregate identity 时必须保守保留并记录 `aggregate_identity_unresolved`。
22. 同一路径上的多个 missing cleanup obligation 必须拆成多条 ranking 记录，manual/LLM label 不得默认跨 obligation 传播。
23. 候选错误出口 slice 上存在 unsupported CFG 节点时，不得输出 high/medium 静态置信度；无关 unsupported 节点只作为函数级诊断。
24. historical fix 在多 obligation 路径上必须使用 obligation/resource/action selector，不能只凭路径行号复制到所有义务。
25. summary fixed point 未收敛时，自动推导和 derived-from-reviewed 的 `must` effect 必须降级为 `may`；只有原始 `origin_kind=reviewed_seed` seed 可保留 `must`。
26. `cfg_witness` 必须保留可复核的 edge/byte/scope/symbol/trace 信息；新增 witness 字段不得替代真实数据流语义。
27. `origin_scc` 是 summary provenance；它可以解释 effect 来源，但不能被当作 context-sensitive 证明。
28. 自动 summary 的 postdominating proof 必须针对可隔离 call event；复杂 block 不能通过删除整个 block 证明 `must`。

当前核心回归命令：

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m pytest -q
python -m compileall -q src tests
git diff --check
```

核心测试集包括：

```text
tests/test_cfg.py
tests/test_cfg_resource_flow.py
tests/test_interprocedural.py
tests/test_retry_paths.py
tests/test_scope_cleanup.py
tests/test_demo.py
tests/test_candidate_contracts.py
tests/test_historical_fix.py
```

---

## 18. 实验与产物组织

常见输出布局：

```text
outputs/<experiment>/<linux-version>/<filesystem>/
  error_paths.csv
  suspicious_candidates.csv
  function_summaries.json
  ranked_candidates.jsonl
  candidates_with_evidence.csv
  llm_review_tasks.jsonl
  deepseek_reviews.jsonl
  deepseek_true_candidates.jsonl
  run_manifest.json
```

常用脚本：

| 脚本 | 用途 |
|---|---|
| `scripts/download_linux_fs.py` | 准备 sparse Linux 源码 |
| `scripts/check_linux_v6_14_filesystems.py` | Linux v6.14 多文件系统扫描 |
| `scripts/check_linux_v7_1_filesystems.sh` | Linux v7.1 批处理 |
| `scripts/run_experiment_v1_3.py` | 运行冻结实验矩阵 |
| `scripts/compare_interprocedural_ablation.py` | 跨函数消融 |
| `scripts/prepare_manual_review_queue.py` | 准备人工队列 |
| `scripts/evaluate_benchmark.py` | benchmark 指标计算 |
| `scripts/triage_cfg_added_candidates.py` | CFG 新增候选审计 |

具体脚本是否存在和参数应以当前 `scripts/` 目录为准；历史报告中的旧命令可能已过期。

---

## 19. 推荐阅读顺序

### 19.1 理解当前任务和目标方法

```text
1. PROJECT_HANDOFF.md
2. docs/MOCC_SE_FULL_ARCHITECTURE.md
3. docs/PROJECT_ARCHITECTURE.md
4. docs/PROJECT_CLOSURE_PLAN.md
```

### 19.2 理解 SE-EOD 静态核心

```text
1. docs/PROJECT_ARCHITECTURE.md
2. src/resource_state.py
3. src/cfg.py
4. src/dataflow.py
5. src/resource_tracker.py
6. src/error_path_extractor.py
7. tests/test_cfg_resource_flow.py
```

### 19.3 理解跨函数语义

```text
1. src/function_summary.py
2. configs/ext4_resource_map.json::interprocedural_effect_seeds
3. tests/test_interprocedural.py
4. outputs/.../function_summaries.json
```

### 19.4 理解候选和 ranking

```text
1. src/candidate_rules.py
2. configs/README.md
3. src/protocol_matcher.py
4. src/evidence_ranker.py
5. src/manual_review.py
6. src/llm_task_builder.py
```

### 19.5 理解实验可信度

```text
1. PAPER_ROADMAP.md
2. docs/PROJECT_CLOSURE_PLAN.md
3. benchmark/
4. scripts/evaluate_benchmark.py
5. outputs/*/run_manifest.json
```

---

## 20. SE-EOD 基线架构总结

SE-EOD 的当前核心不是“在 label 后找到几个 cleanup 名字”，而是：

```text
可用时使用 tree-sitter 函数 AST
  -> 构建函数内 CFG
  -> 在边上传播简单路径事实
  -> 为 acquire site/generation 创建资源实例 ID
  -> 将 acquire validity guard 绑定到资源 ID
  -> 以表达式到 ID 的绑定和析取状态跟踪资源义务
  -> 用 scope frame 和 edge scope_unwind 恢复 shadowed binding
  -> widening 时保留 MAY_ACQUIRED
  -> 保留 uncertainty causes
  -> 按 must/may strength 应用自动 summary 和 reviewed semantic effect
  -> 将 success/error effect 延迟到 return guard 被 CFG edge 证明
  -> 将错误路径绑定到 if true/false 方向
  -> 输出 AST byte range、CFG edge identity 和 analysis snapshot
  -> 在目标 label 后的可达 return 上检查义务
  -> 生成待人工复核的候选
```

`cleanup_calls`、wrapper hint、ownership hint、protocol 和 LLM 都不能替代这条静态语义主线。

这套架构的实用价值是可以在多个 Linux 版本和文件系统上稳定生成可复现的错误路径与候选语料。它的主要研究风险仍是前端缺少编译上下文、循环只做粗粒度 multiplicity/cardinality 抽象、scope-local symbol/aggregate identity 仍不是完整 SSA 与 points-to、一般 success/error effect 尚不能从 callee CFG 自动推导、未迁移配置仍使用 compatibility acquire guard、representative trace 还不是完整 predecessor graph，以及 ranking 未校准。

---

## 21. MOCC-SE 迁移状态

本文件描述的是已经存在的 SE-EOD 基线，不应被误读为 MOCC-SE 已经实现。目标方法和下一步顺序见 [`MOCC_SE_FULL_ARCHITECTURE.md`](MOCC_SE_FULL_ARCHITECTURE.md) 与 [`../PROJECT_HANDOFF.md`](../PROJECT_HANDOFF.md)。

| MOCC-SE 层 | 当前状态 | 实现要求 |
|---|---|---|
| Protocol schema | M0 已实现 | schema v1；operation/principal object/callee role、return contract、effect scope/owner、compensation、handler、accounting、legal exit；严格 JSON 校验和 round-trip，尚未接入 `src.main` |
| Metadata events | M1 已实现 | 直接调用、字段赋值、list add/del、flag/counter、协议 effect/handler；确定性 ID 和对象身份分级 |
| Effect ledger | M2 已实现 | OPEN/COMPENSATED/TRANSFERRED/COMMITTED/UNKNOWN、对象匹配、scope ownership、join/widening |
| Failure epoch | M2 已实现 | 每个 callee role 的 attempt ID 独立，retry 只有在后续 attempt 成功时关闭旧 failure |
| Legal exit verifier | M3 已实现 | success/failure 后置条件、三类候选、`ANALYSIS_UNKNOWN` 隔离和 JSON witness |
| Protocol A | M4 MVP 已实现 | 五个开发函数均有协议驱动结果；sentinel/retry/abort/best-effort/indirect unknown 反例；独立 CLI，尚未接入旧 `src.main` 默认输出 |
| Protocol B | M5 MVP 已实现 | root association、device/list membership、post-commit may summary、active pointer 和 seed/sprout topology；pointer/membership/flag/counter compensation；ABORT scope 与多对象反例 |
| Protocol C | M6 MVP 已实现 | activation/reservation/accounting，开发样例 #4、#15；v1 输出在 `outputs/mocc-protocol-c-v1/` |

现有资源状态可以作为 effect ledger 的特化输入，但不能通过改名直接宣称已经完成元数据协议分析。历史 `missing_cleanup`、`partial_cleanup` 和 `error_swallowed` 输出继续用于 baseline、回归和动机说明。
