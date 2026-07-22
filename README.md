# MOCC-SE

MOCC-SE（Metadata Operation Completion Consistency for Static Error-path
analysis）面向 Linux 文件系统 C 代码，静态检查多阶段元数据操作在失败路径上是否以
合法方式完成。

方法将操作形式化为参数化、分层扩展状态机。独立证据约束“应该满足什么”；抽象
protocol family 描述可复用角色和义务；filesystem binding 把角色和动作映射到具体 API；
operation instance 声明入口、适用范围和合法出口。三层组合成运行时 `MetadataProtocol`，
再由通用分析传播 `OperationControlState`、effect ledger、failure attempt、accounting
obligation 和返回值来源。

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
independent evidence -> rule registry -> authority/split/coverage audit
                              |
protocol family -> filesystem binding -> operation instance
                              |
                              v
                    runtime MetadataProtocol
                              |
Linux fs/ source -> frontend-neutral FunctionIR
  -> function-local CFG
  -> protocol applicability
  -> metadata event extraction
  -> effect/failure/accounting propagation
  -> legal-exit verification
  -> exact protocol candidate or unknown
  -> broad semantic discovery/review
  -> freeze-bound batch candidate scan
  -> source review and repair evidence
```

当前没有独立 `state_machine.py`；协议模型、`MetadataOperationInstance`、tracker 和
legal-exit verifier 共同实现受支持的 EFSM 片段。旧 `src.main`、resource lifecycle、
ranking/LLM 和 benchmark/experiment 运行时代码已经删除。旧输出只作为历史数据保留。

`configs/metadata_rules/rule_registry_v2.json` 是协议之上的知识来源和覆盖审计层。当前
1 条 normative、7 条 confirmed 与 2 条 heuristic development rule 覆盖全部 12 个
operation。14 份外部材料由版本化或不可变 locator、SHA-256 和逐字摘录固定，包括官方
文档、主线历史修复和独立维护者/审阅者邮件。逐规则覆盖和缺口见
[`configs/metadata_rules/EVIDENCE_AUDIT.md`](configs/metadata_rules/EVIDENCE_AUDIT.md)。registry
禁止 construction/evaluation 复用同一 locator；目前 validation/frozen rule 数量仍为 0。
`configs/validation/` 已冻结 active protocols/rules，并建立第一批 10 个 blind、unlabeled
validation 样本；reviewer/adjudication 模板与校验器也已建立。这只是独立验证入口，
不是验证结果。

详细模块和实现边界见
[`docs/PROJECT_ARCHITECTURE.md`](docs/PROJECT_ARCHITECTURE.md)。

## 当前状态

截至 2026-07-22：

| 能力 | 状态 |
|---|---|
| tree-sitter/frontend-neutral IR | 已实现 |
| 函数内 CFG | 已实现 |
| protocol schema/validation | 已实现；扁平 schema v1/v2 向后兼容，package schema v1 可组合 family/binding/operation |
| evidence-backed rule registry | v2.2 已实现，1 normative + 7 confirmed + 2 heuristic development rule / 12 个 operation |
| operation control state / effect submachine | 已实现，含 control trace 和非法转移 unknown |
| metadata event extraction | 已实现 |
| effect/failure/accounting tracker | 已实现 |
| legal exit 和三类候选 | 已实现 |
| Protocol A replay/recovery | MVP 已实现 |
| Protocol B device/topology rollback | MVP 已实现 |
| Protocol C activation/accounting | MVP 已实现 |
| Protocol D XFS/ext4 transaction lifecycle | MVP 已实现并物理分层，含参数与返回值两类调用点对象替换 |
| Protocol E Btrfs allocation lifecycle | 首个开发实例已实现并物理分层，覆盖 path 分配、同对象释放和 NULL 失败 |
| fresh source-tree discovery | M11 开发链已实现 |
| 独立冻结 benchmark | 已实现 freeze/manifest v1、reviewer/adjudication 模板和 freeze-bound batch scanner；10 个 blind、unlabeled 样本待双人真实标注 |
| 大多数文件系统泛化结论 | 尚无充分证据 |

测试基线：

```text
230 passed
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

先校验规则来源和 active protocol operation 覆盖：

```powershell
python -m src.metadata_rule_registry
python -m src.metadata_evidence_verifier
python -m src.metadata_validation_manifest
python -m src.metadata_validation_labels `
  --labels configs/validation/reviewer_a_labels_v1.json `
  --labels configs/validation/reviewer_b_labels_v1.json `
  --adjudication configs/validation/adjudication_v1.json
```

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
  --protocol configs/metadata_protocols/protocol_d_transaction_lifecycle_v2.json `
  --source-root linux-sources/linux-v6.8-fs/fs `
  --source-version linux-v6.8 `
  --out outputs/mocc-discovery-v2/linux-v6.8-fresh-review.json
```

该 discovery 默认排除 confirmed functions 和 regression seeds。宽松 semantic match
只进入 `DISCOVERY_REVIEW`，不会升级为协议已证明 candidate。

freeze-bound batch candidate scan：

```powershell
python -m src.metadata_batch_scan `
  --source-root linux-sources/linux-v7.1-fs/fs `
  --source-version 7.1 `
  --out outputs/mocc-batch-scan-v1/linux-v7.1-fs.json
```

该命令会先校验 protocol/rule freeze 和 validation manifest，再按当前规则适用版本加载
active protocols。输出语义是 `candidate_queue_not_bug_claims`：可以用于全量候选扫描，
但不能直接宣称 bug。

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
configs/protocol_families  reusable abstract roles, actions and obligations
configs/filesystem_bindings filesystem API/object mappings
configs/operations         entry-specific protocol instantiation
configs/metadata_protocols runtime protocol files and package manifests
configs/metadata_rules     evidence authority, usage, split and coverage targets
configs/validation         frozen protocol/rule inputs and blind validation manifest
tests/                     retained frontend/CFG/MOCC tests
scripts/                   source download and current validation only
outputs/                   retained development evidence and historical data
linux-sources/             local Linux source inputs
```

## 研究边界

当前不声称：

- 完整 Clang/Kbuild、SSA 或 points-to；
- 递归或通用跨函数 handler/effect summary；当前只支持配置化、`max_call_depth == 1` 的有界摘要；
- 任意文件系统不变量或元数据算术自动推导；
- 完整并发或 crash-consistency 证明；
- LLM 自动确认 bug；
- 自动生成可合并内核补丁；
- 已适用于大多数文件系统。

当前 ext4/JBD2 handle lifecycle 已由版本固定官方文档支持并升级为 normative；7 条规则由
implementation evidence 加独立 historical-fix 或 maintainer evidence 支持并升级为
confirmed。sprout multi-effect rollback 和 XFS 完整 transaction failure lifecycle 只有部分
外部覆盖，继续保持 heuristic。所有 10 条规则的 maturity 仍是 development；只有在隔离的
validation/frozen 数据上完成评估后，才能升级 maturity。

历史补丁、人工判断和维护者反馈只能用于复核和验证，不能反向改变静态协议状态。
