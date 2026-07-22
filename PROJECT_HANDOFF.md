# MOCC-SE 实施交接

> 更新时间：2026-07-22
>
> 当前任务：保持 M0-M11 可执行核心稳定，只对 fresh review queue 做源码复核、版本
> diff 和 repair/fault-model evidence；不扩展已明确为非目标的旧 SE-EOD、通用分析或
> 独立状态机运行时。

## 1. 文档职责

- [`docs/MOCC_SE_FULL_ARCHITECTURE.md`](docs/MOCC_SE_FULL_ARCHITECTURE.md)：方法和 EFSM 定义；
- [`docs/PROJECT_ARCHITECTURE.md`](docs/PROJECT_ARCHITECTURE.md)：当前代码事实；
- [`docs/PROJECT_CLOSURE_PLAN.md`](docs/PROJECT_CLOSURE_PLAN.md)：评估和论文门禁；
- [`PAPER_ROADMAP.md`](PAPER_ROADMAP.md)：研究问题和论文路线；
- 本文档：当前允许继续做什么，以及如何验收。

代码和测试是实现事实来源。目标架构不能用于宣布未实现能力。

## 2. 已冻结的方法抽象

MOCC-SE 使用由文件系统协议实例化的参数化、分层扩展状态机：

```text
operation control state
  + effect lifecycle and owner
  + failure token / attempt_id
  + accounting obligation
  + return provenance
  + protocol legal exit
```

它不是一个新增的 `state_machine.py`。现有 `MetadataProtocol`、
`MetadataOperationInstance`、tracker 和 legal-exit verifier 共同实现受支持片段。

当前 schema 只表达显式 phase、effect closure、return contract、boolean accounting 和
legal exit，不实现任意文件系统不变量语言。

## 3. 当前保留的执行链

```text
frontend/tree-sitter
  -> versioned FunctionIR
  -> function-local CFG
  -> metadata protocol and events
  -> effect/failure/accounting propagation
  -> legal-exit verification
  -> exact candidate / analysis unknown
  -> broad semantic discovery/review
  -> source review / version evidence / confirmed linkage
```

实现模块：

```text
src/parser.py
src/function_extractor.py
src/frontend/
src/cfg.py
src/metadata_protocol.py
src/metadata_event.py
src/metadata_tracker.py
src/metadata_candidate_rules.py
src/metadata_protocol_analyzer.py
src/metadata_protocol_discovery.py
src/metadata_finding_review.py
src/metadata_finding_triage.py
src/metadata_finding_matrix.py
src/metadata_function_diff.py
src/metadata_repair_evidence.py
src/metadata_bug_hunt_report.py
src/metadata_confirmed_bug_linkage.py
```

旧 `src.main`、resource lifecycle、legacy candidate、ranking/LLM 和 benchmark/
experiment 运行时代码已删除。旧 SE-EOD 输出是历史数据，不再有当前代码复现承诺。

## 4. 不得破坏的不变量

1. 静态协议语义决定 candidate 是否存在；人工、历史、patch 和 LLM 不得修改状态。
2. 未证明 compensation、commit 或 owner transfer 时，开放 effect 不能关闭。
3. `ABORT` 只能关闭协议明确归属于 transaction 的 effect。
4. success exit 不能带 unresolved necessary failure。
5. retry 必须建立新 `attempt_id`，最终返回值来源必须可追踪。
6. `ret > 0` 的含义由 return contract 决定，不能默认视为失败。
7. unknown alias、indirect call、handler coverage 或 CFG 必须保留 uncertainty。
8. `ANALYSIS_UNKNOWN` 不得混入协议已证明 candidate。
9. exact protocol candidate 与 broad `DISCOVERY_REVIEW` 必须分离。
10. 输出是待复核结果，不是自动 confirmed bug。

## 5. 当前协议

```text
Protocol A  replay/recovery return completion
Protocol B  Btrfs device/root/topology rollback
Protocol C  retry provenance and boolean activation/accounting
```

活动配置位于 `configs/metadata_protocols/`。`entry_functions` 是 regression seed；
函数名不能作为新 bug 的唯一发现条件。

## 6. 当前任务

只继续以下工作：

1. 复核 `outputs/mocc-discovery-v2/` 的 fresh queue；
2. 对高置信函数执行源码级路径检查和跨版本 diff；
3. 在证据允许时生成窄范围 fault model 或 patch proposal；
4. 将人工结论与静态 candidate 分层记录；
5. 保持文档、输出语义和测试基线一致。

当前 ext4 helper 验证入口：

```powershell
python scripts/validate_ext4_fc_replay_helpers.py
```

它只证明源码控制流模型中的错误传播差异，不等于完整内核 fault injection、真实磁盘
损坏或上游接受。

## 7. 明确不实施

除非研究范围重新评审，不实施：

- 恢复旧 `src.main`/SE-EOD resource/ranking/LLM 流水线；
- 独立状态机运行时；
- 完整 Clang/Kbuild frontend；
- 通用 SSA、points-to、SMT 或任意 C 路径证明；
- 完整跨函数 handler/effect summary；
- 任意元数据算术或不变量 DSL；
- 完整并发、持久化顺序或 crash-consistency 证明；
- 自动 bug 确认或自动合并补丁；
- 在没有跨文件系统冻结实验前声称适用于大多数文件系统。

## 8. 运行与验收

单函数协议分析：

```powershell
python -m src.metadata_protocol_analyzer `
  --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json `
  --source linux-sources/linux-v6.8-fs/fs/ext4/fast_commit.c `
  --source-version linux-v6.8
```

fresh discovery：

```powershell
python -m src.metadata_protocol_discovery `
  --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json `
  --protocol configs/metadata_protocols/protocol_b_device_topology_v1.json `
  --protocol configs/metadata_protocols/protocol_c_activation_accounting_v1.json `
  --source-root linux-sources/linux-v6.8-fs/fs `
  --source-version linux-v6.8 `
  --out outputs/mocc-discovery-v2/linux-v6.8-fresh-review.json
```

回归测试：

```powershell
python -m pytest -q
git diff --check
```

2026-07-22 精简后测试基线：

```text
138 passed
```

## 9. 输出边界

当前活动 MOCC 证据：

```text
outputs/mocc-protocol-a-v1/
outputs/mocc-protocol-b-v1/
outputs/mocc-protocol-c-v1/
outputs/mocc-discovery-v2/
outputs/mocc-finding-review-v1/
outputs/confirmed_bugs.md
```

`mocc-discovery-v1*` 和旧 SE-EOD 数据只保留历史/开发证据。所有 retained output 的
语义以 [`outputs/README.md`](outputs/README.md) 为准。

## 10. 交接检查

- [ ] `python -m pytest -q` 全部通过；
- [ ] `git diff --check` 通过；
- [ ] exact candidate、review 和 unknown 没有混合；
- [ ] 新 evidence 没有反向修改静态语义；
- [ ] 新 finding 状态区分 candidate/submitted/reviewed/accepted；
- [ ] 文档没有引用已删除模块或输出；
- [ ] 所有主张均限制在当前支持片段内。
