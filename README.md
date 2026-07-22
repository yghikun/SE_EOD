# MOCC-SE

MOCC-SE（Metadata Operation Completion Consistency for Static Error-path
analysis）面向 Linux 文件系统 C 代码，静态检查多阶段元数据操作在失败路径上是否以
合法方式完成。

方法将操作形式化为由文件系统协议实例化的参数化、分层扩展状态机。通用分析传播
控制阶段、effect ledger、failure attempt、accounting obligation 和返回值来源；协议
定义对象角色、阶段、补偿/接管关系、返回契约和合法出口。

系统输出待人工复核的候选，不直接声称候选一定是真实 bug。

## 核心判定

```text
failure_reported_as_success
  必要元数据步骤失败且未解决，却到达成功出口

incomplete_failure_completion
  required effect 在退出时仍开放，或没有合法责任主体

metadata_state_divergence
  返回值、attempt、元数据阶段或记账状态不满足协议约束
```

合法完成模式包括：

```text
COMMITTED
ROLLED_BACK
ABORTED
RECOVERY_DELEGATED
DEFERRED
```

无法证明对象、handler 或路径语义时，系统输出 `ANALYSIS_UNKNOWN`，不把不确定性
解释为安全或真实违规。

## 当前架构

```text
Linux fs/ source
  -> frontend-neutral FunctionIR
  -> function-local CFG
  -> protocol applicability
  -> metadata event extraction
  -> effect/failure/accounting propagation
  -> legal-exit verification
  -> exact protocol candidate or unknown
  -> broad semantic discovery/review
  -> source review and repair evidence
```

当前没有独立 `state_machine.py`；协议模型、`MetadataOperationInstance`、tracker 和
legal-exit verifier 共同实现受支持的 EFSM 片段。旧 `src.main`、resource lifecycle、
ranking/LLM 和 benchmark/experiment 运行时代码已经删除。旧输出只作为历史数据保留。

详细模块和实现边界见
[`docs/PROJECT_ARCHITECTURE.md`](docs/PROJECT_ARCHITECTURE.md)。

## 当前状态

截至 2026-07-22：

| 能力 | 状态 |
|---|---|
| tree-sitter/frontend-neutral IR | 已实现 |
| 函数内 CFG | 已实现 |
| protocol schema/validation | 已实现，schema v1 |
| metadata event extraction | 已实现 |
| effect/failure/accounting tracker | 已实现 |
| legal exit 和三类候选 | 已实现 |
| Protocol A replay/recovery | MVP 已实现 |
| Protocol B device/topology rollback | MVP 已实现 |
| Protocol C activation/accounting | MVP 已实现 |
| fresh source-tree discovery | M11 开发链已实现 |
| 独立冻结 benchmark | 未实现 |
| 大多数文件系统泛化结论 | 尚无充分证据 |

测试基线：

```text
138 passed
```

## 文档入口

1. [`docs/MOCC_SE_FULL_ARCHITECTURE.md`](docs/MOCC_SE_FULL_ARCHITECTURE.md)：参数化扩展状态机和目标方法。
2. [`docs/PROJECT_ARCHITECTURE.md`](docs/PROJECT_ARCHITECTURE.md)：当前保留的代码和真实运行入口。
3. [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md)：当前实施边界和复核任务。
4. [`docs/PROJECT_CLOSURE_PLAN.md`](docs/PROJECT_CLOSURE_PLAN.md)：方法、评估和论文门禁。
5. [`PAPER_ROADMAP.md`](PAPER_ROADMAP.md)：研究问题和论文路线。
6. [`outputs/README.md`](outputs/README.md)：保留输出、历史数据和证据语义。

## 安装与测试

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```

准备本地 Linux `fs/` 源码：

```powershell
python scripts/download_linux_fs.py
python scripts/download_linux_fs.py `
  --ref v7.1 `
  --target linux-sources/linux-v7.1-fs `
  --sparse-path fs
```

`linux-sources/` 是本地输入，不应提交。

## 运行协议分析

单函数分析：

```powershell
python -m src.metadata_protocol_analyzer `
  --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json `
  --source linux-sources/linux-v6.8-fs/fs/ext4/fast_commit.c `
  --source-version linux-v6.8
```

fresh source-tree discovery：

```powershell
python -m src.metadata_protocol_discovery `
  --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json `
  --protocol configs/metadata_protocols/protocol_b_device_topology_v1.json `
  --protocol configs/metadata_protocols/protocol_c_activation_accounting_v1.json `
  --source-root linux-sources/linux-v6.8-fs/fs `
  --source-version linux-v6.8 `
  --out outputs/mocc-discovery-v2/linux-v6.8-fresh-review.json
```

该 discovery 默认排除 confirmed functions 和 regression seeds。宽松 semantic match
只进入 `DISCOVERY_REVIEW`，不会升级为协议已证明 candidate。

当前 ext4 helper fault model：

```powershell
python scripts/validate_ext4_fc_replay_helpers.py
```

它是窄范围源码控制流模型，不是完整内核 fault-injection。

## 目录结构

```text
src/frontend/              versioned frontend IR and tree-sitter adapter
src/metadata_*.py          protocol, EFSM state, discovery and review pipeline
src/cfg.py                 function-local CFG
src/parser.py              C source parsing and fallback
src/function_extractor.py  function extraction used by the frontend
configs/metadata_protocols active MOCC-SE protocol instances
tests/                     retained frontend/CFG/MOCC tests
scripts/                   source download and current validation only
outputs/                   retained development evidence and historical data
linux-sources/             local Linux source inputs
```

## 研究边界

当前不声称：

- 完整 Clang/Kbuild、SSA 或 points-to；
- 完整跨函数 handler/effect summary；
- 任意文件系统不变量或元数据算术自动推导；
- 完整并发或 crash-consistency 证明；
- LLM 自动确认 bug；
- 自动生成可合并内核补丁；
- 已适用于大多数文件系统。

历史补丁、人工判断和维护者反馈只能用于复核和验证，不能反向改变静态协议状态。
