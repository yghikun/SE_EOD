# MOCC-SE

MOCC-SE（Metadata Operation Completion Consistency for Static Error-path analysis）面向 Linux 文件系统 C 代码，静态检查多阶段元数据操作在失败路径上是否以合法方式完成。

SE-EOD 是仓库中已经实现的错误路径、资源状态和证据排序基线。MOCC-SE 在其 CFG、数据流和跨函数摘要之上，进一步跟踪元数据 effect、失败处理、补偿/接管和 accounting obligation。

系统输出待人工复核的候选，不直接声称候选一定是真实 bug。

## 研究问题

MOCC-SE 检查三个方面：

1. `failure_reported_as_success`：必要元数据步骤失败后，没有成功重试、中止或恢复，却到达成功出口。
2. `incomplete_failure_completion`：已经修改的指针、链表、root、设备状态或其他 effect 在失败退出前没有补偿，也没有交给合法 handler。
3. `metadata_state_divergence`：返回值、元数据阶段、reservation 或计数状态组成了协议不允许的组合。

统一后置条件是：

> 函数的每个可达出口都必须满足协议定义的合法完成模式，并保证返回状态、元数据状态和记账状态一致。

合法完成模式包括：

```text
COMMITTED
ROLLED_BACK
ABORTED
RECOVERY_DELEGATED
DEFERRED
```

无法证明合法完成时，系统区分真实的 `PARTIAL_UNRESOLVED` 与分析能力不足产生的 `ANALYSIS_UNKNOWN`。

## 文档入口

按以下顺序阅读：

1. [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md)：当前唯一实施顺序和下一项代码任务。
2. [docs/MOCC_SE_FULL_ARCHITECTURE.md](docs/MOCC_SE_FULL_ARCHITECTURE.md)：目标方法、状态模型和完整模块。
3. [docs/PROJECT_ARCHITECTURE.md](docs/PROJECT_ARCHITECTURE.md)：当前 SE-EOD 基线已经实现的代码事实。
4. [docs/PROJECT_CLOSURE_PLAN.md](docs/PROJECT_CLOSURE_PLAN.md)：工程、实验、finding、复现和论文完成门禁。
5. [PAPER_ROADMAP.md](PAPER_ROADMAP.md)：研究问题、实验路线和投稿阶段。

历史实验和证据说明见 [outputs/README.md](outputs/README.md)。配置职责见 [configs/README.md](configs/README.md)。

## 当前状态

截至 2026-07-21：

| 层次 | 状态 |
|---|---|
| SE-EOD 源码前端、CFG 和资源数据流 | 已实现并有回归测试 |
| frontend-neutral IR 和 tree-sitter adapter | 已实现 |
| 跨函数 effect summary 和固定点传播 | 已实现基线能力 |
| 证据排序、历史修复和人工/LLM triage | 已实现基线能力 |
| MOCC-SE 协议核心数据模型 | M0 已实现，schema v1 |
| 元数据事件提取 | M1 已实现，独立于旧 resource tracker |
| failure epoch、effect ledger 和 accounting state | M2 已实现 |
| 合法出口和三类候选规则 | M3 已实现，unknown 独立隔离 |
| Protocol A replay/recovery | M4 MVP 已实现，使用独立 CLI |
| Protocol B device/topology rollback | M5 MVP 已实现，使用独立 CLI |
| Protocol C activation/reservation/accounting | M6 MVP 已实现，使用独立 CLI |

当前测试基线：

```text
256 passed
```

该数字是当前 M0-M6 快照；每次交接必须重新运行测试确认。

## 当前实现架构

现有基线数据流：

```text
Linux source tree
  -> frontend IR / function extraction
  -> function CFG
  -> error condition and path extraction
  -> resource state propagation
  -> interprocedural summaries
  -> SE-EOD candidates
  -> history/manual/LLM evidence ranking
```

目标 MOCC-SE 数据流：

```text
existing frontend / CFG / summaries
  -> metadata protocol matching
  -> metadata event extraction
  -> operation instance creation
  -> failure/effect/accounting propagation
  -> legal completion verification
  -> MOCC-SE candidates and witness
  -> independent evidence ranking
```

静态语义与证据排序必须保持隔离。历史补丁、维护者反馈和 LLM 只能帮助排序或验证，不能把 effect 自动标为已补偿或已提交。

## 当前实施顺序

严格执行：

```text
M0  metadata protocol model and schema
M1  metadata event extraction
M2  protocol state propagation
M3  legal exit and candidate generation
M4  Protocol A replay/recovery
M5  Protocol B device/topology rollback
M6  Protocol C activation/reservation/accounting
```

M0-M6 已实现于：

```text
src/metadata_protocol.py
src/metadata_event.py
src/metadata_tracker.py
src/metadata_candidate_rules.py
src/metadata_protocol_analyzer.py
tests/test_metadata_protocol.py
tests/test_metadata_protocol_b.py
tests/test_metadata_protocol_c.py
configs/metadata_protocols/
```

Protocol A/B/C 使用 `python -m src.metadata_protocol_analyzer` 独立运行，不改变旧
`src.main` 的默认 CSV/JSONL。Protocol B 的版本化结果位于
`outputs/mocc-protocol-b-v1/`；Protocol C 的版本化结果位于
`outputs/mocc-protocol-c-v1/`。

## 开发样例与数据隔离

现有 [outputs/confirmed_bugs.md](outputs/confirmed_bugs.md) 中的元数据相关 finding 用作协议开发和回归：

| 协议 | 开发 finding |
|---|---|
| Protocol A | #1、#2、#5、#8、#13 |
| Protocol B | #7、#17、#18、#19 |
| Protocol C | #4、#15 |

这些 finding 已经参与协议设计，不能同时作为无偏测试集。正式评估必须在协议冻结后采集独立样本。

纯资源生命周期 finding 继续作为 SE-EOD 基线和回归材料，不作为 MOCC-SE 的主要贡献。

## 安装

Python 3 环境：

```bash
python -m pip install -r requirements.txt
```

检查环境：

```bash
python -m src.main --check-env
```

DeepSeek 是可选的复核工具，只从环境变量读取密钥：

```bash
export DEEPSEEK_API_KEY="..."
```

不要把密钥写入配置、输出或提交。

## 测试

```bash
python -m compileall -q src tests scripts
python -m pytest -q
```

文档或代码提交前：

```bash
git diff --check
git status --short
```

## 准备源码

```bash
python scripts/download_linux_fs.py
python scripts/download_linux_fs.py \
  --ref v7.1 \
  --target linux-sources/linux-v7.1-fs \
  --sparse-path fs
```

`linux-sources/` 是本地实验输入，不应提交到仓库。

## 重现 SE-EOD 基线

当前保留的 refined matrix 是 `experiment-v1.3.3`：

```bash
python scripts/run_experiment_v1_3.py \
  --output-root outputs/experiment-v1.3.3 \
  --experiment-name experiment-v1.3.3 \
  --force
python scripts/compare_experiment_v1_3_3.py
```

Btrfs cleanup 模型审计：

```bash
python scripts/compare_scope_cleanup_ablation.py
python scripts/audit_btrfs_v7_1_candidates.py
```

这些命令重现 SE-EOD 历史基线，不代表 MOCC-SE Protocol A 已经实现。

## 输出语义

| 输出 | 含义 | 不能声称 |
|---|---|---|
| `error_paths.csv` | 静态识别的错误样路径 | 所有编译配置下均可达 |
| `suspicious_candidates.csv` | SE-EOD 基线候选 | 已确认 bug |
| `quarantined_candidates.csv` | 分析不确定或低置信候选 | 与主候选置信度相同 |
| `ranked_candidates.jsonl` | 排序和证据摘要 | bug 概率 |
| `confirmed_bugs.md` | 人工、历史、动态或 patch 支持的记录 | 全部是新 bug 或 upstream accepted |
| 未来 MOCC-SE candidate | 协议后置条件可能违规 | 自动证明磁盘损坏 |

## 目录结构

```text
src/                    当前分析器代码
src/frontend/           frontend-neutral IR 和 adapter
configs/                资源配置、证据协议和未来 metadata protocols
tests/                  单元、回归和真实源码 fixture
benchmark/              现有开发 pilot 和未来冻结 benchmark
linux-sources/           本地 Linux 文件系统源码输入
outputs/                 历史实验、候选和验证证据
docs/                    架构、方法和闭合计划
scripts/                 实验、评估和复现脚本
```

## 支持边界

MOCC-SE 当前和首版实现均不声称：

- 完整 Clang/Kbuild 编译证明；
- 通用 SSA 或 points-to；
- 任意 C 程序的完整路径可行性；
- 完整并发可见性或 crash-consistency 证明；
- 任意元数据算术关系自动推导；
- LLM 自动确认 bug；
- 自动生成可直接合并的内核补丁。

第一版限制在显式 API、字段、链表、root/device 角色和可审查的函数摘要上。无法确认对象、handler 或返回语义时，必须输出不确定性，不能假装操作已经正确完成。
