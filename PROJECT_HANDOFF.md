# MOCC-SE 实施交接

> 更新时间：2026-07-22
>
> 当前项目状态：MOCC-SE 已从旧 SE-EOD 的 resource/ranking/LLM pipeline，收敛为
> “元数据操作完成一致性”的协议/规则/EFSM 静态分析原型。现在可以做 freeze-bound
> 全量候选扫描、初始 triage、源码事实审计和独立验证入口；但尚不能把扫描结果直接称为
> confirmed bug，也不能声称已经适用于大多数文件系统。

## 1. 这份文档怎么用

本文档是当前实现交接入口，回答三件事：

1. 现在项目实际实现了什么；
2. 哪些结论可以说，哪些不能说；
3. 下一步继续做什么，以及怎么验收。

更详细的文档分工如下：

- [`README.md`](README.md)：项目入口、运行命令和当前能力摘要；
- [`docs/MOCC_SE_FULL_ARCHITECTURE.md`](docs/MOCC_SE_FULL_ARCHITECTURE.md)：方法抽象和 EFSM 定义；
- [`docs/PROJECT_ARCHITECTURE.md`](docs/PROJECT_ARCHITECTURE.md)：当前代码模块和架构事实；
- [`docs/PROJECT_CLOSURE_PLAN.md`](docs/PROJECT_CLOSURE_PLAN.md)：闭合到论文/评估所需门禁；
- [`PAPER_ROADMAP.md`](PAPER_ROADMAP.md)：研究问题、论文路线和实验计划；
- [`outputs/README.md`](outputs/README.md)：输出目录的证据语义。

代码和测试是实现事实来源。目标架构、论文设想或人工判断不能反向宣布未实现能力。

## 2. 当前研究主张

MOCC-SE 的核心主张不是“找所有文件系统 bug”，也不是“从源码里自动学出真理”。当前更稳的表述是：

> MOCC-SE 将文件系统元数据操作建模为由协议实例化的参数化、分层扩展状态机，检查错误路径上
> return outcome、metadata effect lifecycle、owner/handler transfer、failure attempt 和
> accounting obligation 是否满足合法完成条件。

因此，工具输出分层如下：

```text
PROTOCOL_CANDIDATE
  精确协议实例命中；可以进入人工 bug review，但仍不是 confirmed bug。

DISCOVERY_REVIEW
  宽语义发现队列；只说明形状可疑，需要协议/语义复核。

ANALYSIS_UNKNOWN / DISCOVERY_UNKNOWN
  alias、handler、CFG、object identity 或语义证据不足；必须保留不确定性。

needs_external_semantics
  源码事实可疑，但还缺少独立语义契约，不能从待检查源码自证协议或 bug。

confirmed bug
  需要额外证据闭合：历史 upstream fix、maintainer/reviewer 确认、动态复现、
  accepted patch，或等价的独立验证证据。
```

这正是解决“自我验证悖论”的边界：协议可以受源码启发，但 active 协议义务必须由独立证据、
官方文档、历史修复、维护者语义或冻结验证支撑，不能完全来自被检查源码本身。

## 3. 已冻结的方法抽象

MOCC-SE 使用由文件系统协议实例化的参数化、分层扩展状态机：

```text
operation control state
  + effect lifecycle and owner
  + failure token / attempt_id
  + accounting obligation
  + return provenance
  + protocol legal exit
```

它不是一个新增的 `state_machine.py`。当前由以下组件共同实现受支持的 EFSM 片段：

```text
MetadataProtocol / MetadataOperationInstance
OperationControlState
metadata event extraction
effect ledger
failure attempt tracker
accounting tracker
legal-exit verifier
candidate / unknown classifier
```

操作层 `OperationControlState` 已显式实现：

```text
INIT
ACTIVE
COMMITTING
HANDLING_FAILURE
RETRYING
EXITED
UNKNOWN
```

每个 effect 仍有独立 lifecycle；control trace 与源码 witness 分离输出。非法状态倒退、
无法证明的状态 join、unknown alias、unknown handler coverage 等必须进入 `UNKNOWN`，
不能猜测为安全，也不能猜测为 bug。

当前 schema 只支持显式 phase、effect closure、return contract、boolean accounting 和
legal exit；不支持任意文件系统不变量语言、通用数学约束、完整 crash-consistency 证明或
无界跨函数摘要。

## 4. 当前保留的执行链

```text
independent evidence
  -> metadata rule registry
  -> authority / split / coverage audit
  -> protocol family / filesystem binding / operation instance
  -> runtime MetadataProtocol
  -> frontend-neutral FunctionIR
  -> function-local CFG
  -> metadata event extraction
  -> effect / failure / accounting propagation
  -> legal-exit verification
  -> exact candidate / analysis unknown
  -> broad semantic discovery / review
  -> freeze-bound batch scan
  -> batch triage
  -> source-fact audit / external semantic review
```

实现模块：

```text
src/parser.py
src/function_extractor.py
src/frontend/
src/cfg.py
src/metadata_protocol.py
src/metadata_protocol_package.py
src/metadata_rule_registry.py
src/metadata_evidence_verifier.py
src/metadata_event.py
src/metadata_tracker.py
src/metadata_candidate_rules.py
src/metadata_protocol_analyzer.py
src/metadata_protocol_discovery.py
src/metadata_batch_scan.py
src/metadata_batch_triage.py
src/metadata_ext4_replay_bookkeeping_audit.py
src/metadata_validation_manifest.py
src/metadata_validation_labels.py
src/metadata_finding_review.py
src/metadata_finding_triage.py
src/metadata_finding_matrix.py
src/metadata_function_diff.py
src/metadata_repair_evidence.py
src/metadata_bug_hunt_report.py
src/metadata_confirmed_bug_linkage.py
```

旧 `src.main`、resource lifecycle、legacy candidate、ranking/LLM、benchmark/experiment
运行时代码已删除。旧 SE-EOD 输出只作为历史数据保留，不再有当前代码复现承诺。

## 5. 当前协议和规则状态

当前 active protocol：

```text
Protocol A  replay/recovery return completion
Protocol B  Btrfs device/root/topology rollback
Protocol C  retry provenance and boolean activation/accounting
Protocol D  XFS/ext4 bounded transaction lifecycle
Protocol E  Btrfs bounded allocation/release lifecycle
```

活动 runtime 配置位于 `configs/metadata_protocols/`。其中：

- Protocol D/E 已拆成 `protocol_families/`、`filesystem_bindings/` 和 `operations/`，再由
  `metadata_protocols/` 中的 package manifest 组合；
- Protocol A/B/C 暂时保留扁平配置兼容，不能声称所有协议已经迁移；
- `entry_functions` 是 regression seed，不是新 bug 的唯一发现依据。

当前规则 registry：

```text
configs/metadata_rules/rule_registry_v2.json
registry version: 2.2.0
rules: 10
active protocols: 5
covered operations: 12
authority: 1 normative + 7 confirmed + 2 heuristic
maturity: all development; 0 validation/frozen rule
external evidence: 14 frozen sources
```

14 份 external evidence 包括版本固定官方 contract、主线 historical fix 和独立
maintainer/reviewer 邮件，均记录 locator、SHA-256 和逐字摘录。逐规则证据结论见
[`configs/metadata_rules/EVIDENCE_AUDIT.md`](configs/metadata_rules/EVIDENCE_AUDIT.md)。

新增 operation 或 rule 时必须满足：

- 有 rule binding；
- 有独立 evidence locator / 摘要 / 摘录；
- construction 与 evaluation 不复用同一 evidence locator；
- validation/frozen 数据不得污染 development rule construction；
- 如果缺少上述条件，校验必须失败。

## 6. 当前全量扫描状态

用户已运行 v7.1 fs 全量扫描：

```text
outputs/mocc-batch-scan-v1/linux-v7.1-fs.json
```

扫描摘要：

```text
scanned_files: 334
scanned_functions: 10302
protocol_candidate_occurrences: 0
discovery_review_queue_entries: 8
analysis_unknown: 0
discovery_unknown: 0
result_semantics: candidate_queue_not_bug_claims
```

随后使用 `metadata_batch_triage` 生成初筛 ledger：

```text
outputs/mocc-batch-scan-v1/linux-v7.1-fs-triage.json
outputs/mocc-batch-scan-v1/linux-v7.1-fs-triage.md
```

当前 triage 结果：

```text
triage_items: 8
likely_false_positive: 6
needs_external_semantics: 2
needs_protocol_instance: 0
manual_bug_review_candidates: 0
```

解释：

- 6 条 Btrfs/XFS `mutation_failure_cleanup` 宽语义命中被判为 likely false positive，
  因为 matched mutation 是 local preparation / search key / reservation argument state，
  不是已证明的 durable metadata effect；
- 2 条 ext4 `failure_return_mismatch` 命中不是 bug，也不是立即应写入 active protocol 的实例；
  它们现在被归类为 `needs_external_semantics`。

这一步的意义是：当前工具已经可以跑全量候选队列，但 v7.1 这次扫描没有产生可以直接进入
manual bug review 的精确协议候选。

## 7. ext4 replay bookkeeping 审计状态

为两个 ext4 helper 新增了源码事实审计模块：

```text
src/metadata_ext4_replay_bookkeeping_audit.py
tests/test_metadata_ext4_replay_bookkeeping_audit.py
```

生成的审计产物：

```text
outputs/mocc-batch-scan-v1/ext4-replay-bookkeeping-audit.json
outputs/mocc-batch-scan-v1/ext4-replay-bookkeeping-audit.md
```

审计对象：

```text
ext4_ext_replay_set_iblocks
ext4_ext_clear_bb
```

v7.1 源码事实：

- 两个 helper 都是 public `int` return；
- fast-commit replay caller 都忽略 helper return；
- 两个 helper 都存在 `ext4_map_blocks()` 失败后经 `break` 到最终 `return 0` 的源码形状；
- `ext4_ext_replay_set_iblocks()` 在失败后仍会执行 `inode->i_blocks` bookkeeping 和
  `ext4_mark_inode_dirty(NULL, inode)`；
- `ext4_ext_clear_bb()` 有 bitmap / fast-commit region 相关 partial mutation 事实。

保守结论：

```text
conclusion: needs_external_semantics
bug_claim_allowed: false
```

也就是说，源码形状值得追，但缺少关键语义权威：ext4 fast-commit replay bookkeeping
失败到底必须 abort replay，还是允许 best-effort。只有找到独立文档、maintainer review、
accepted fix 或 fault-injection 证据后，才能决定是否升级为 active protocol instance 或
confirmed bug 候选。

旧脚本仍保留为窄范围 fault model：

```powershell
python scripts/validate_ext4_fc_replay_helpers.py
```

它只证明手写源码控制流模型中的错误传播差异，不等于完整内核 fault injection、真实磁盘损坏
或上游接受。

## 8. 当前不变量

不得破坏以下不变量：

1. 静态协议语义决定 candidate 是否存在；人工、历史、patch 或 LLM 不得修改状态机语义。
2. 未证明 compensation、commit 或 owner transfer 时，开放 effect 不能关闭。
3. `ABORT` 只能关闭协议明确归属于 transaction 的 effect。
4. success exit 不能带 unresolved necessary failure。
5. retry 必须建立新 `attempt_id`，最终返回值来源必须可追踪。
6. `ret > 0` 的含义由 return contract 决定，不能默认视为失败。
7. unknown alias、indirect call、handler coverage 或 CFG join 必须保留 uncertainty。
8. `ANALYSIS_UNKNOWN` 不得混入协议已证明 candidate。
9. exact `PROTOCOL_CANDIDATE` 与 broad `DISCOVERY_REVIEW` 必须分离。
10. `DISCOVERY_REVIEW`、`needs_protocol_instance`、`needs_external_semantics` 都不是 bug 结论。
11. legal exit 前操作控制状态必须到达 `EXITED`；非法转移或控制状态 join 不得猜测为安全。
12. 不能从待检查源码本身完全抽取协议后，再用同一协议声称发现该源码的 bug。

## 9. 明确不实施

除非研究范围重新评审，不实施：

- 恢复旧 `src.main` / SE-EOD resource / ranking / LLM 流水线；
- 独立 `state_machine.py` 运行时；
- 完整 Clang/Kbuild frontend；
- 通用 SSA、points-to、SMT 或任意 C 路径证明；
- 完整跨函数 handler/effect summary；
- 任意元数据算术或不变量 DSL；
- 完整并发、持久化顺序或 crash-consistency 证明；
- 自动 bug 确认；
- 自动生成并合并内核补丁；
- 在没有跨文件系统冻结实验前声称适用于大多数文件系统。

## 10. 运行与验收

### 10.1 规则、证据和验证入口

```powershell
python -m src.metadata_rule_registry
python -m src.metadata_evidence_verifier
python -m src.metadata_validation_manifest
python -m src.metadata_validation_labels `
  --labels configs/validation/reviewer_a_labels_v1.json `
  --labels configs/validation/reviewer_b_labels_v1.json `
  --adjudication configs/validation/adjudication_v1.json
```

当前预期摘要：

```text
active_protocols: 5
covered_operations: 12
rules: 10
external sources verified: 14
frozen artifacts: 14
blind validation samples: 10
reviewer label templates: 2
adjudication template: 1
```

这些 validation 文件仍是入口和模板，不是 evaluation result。

### 10.2 单函数协议分析

```powershell
python -m src.metadata_protocol_analyzer `
  --protocol configs/metadata_protocols/protocol_a_replay_recovery_v1.json `
  --source linux-sources/linux-v6.8-fs/fs/ext4/fast_commit.c `
  --source-version linux-v6.8
```

### 10.3 fresh discovery

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

fresh discovery 默认排除 confirmed functions 和 regression seeds。输出是开发复核队列，
不是 frozen benchmark，也不能自动标为真实 bug。

### 10.4 freeze-bound batch scan

```powershell
python -m src.metadata_batch_scan `
  --source-root linux-sources/linux-v7.1-fs/fs `
  --source-version 7.1 `
  --out outputs/mocc-batch-scan-v1/linux-v7.1-fs.json
```

输出语义必须保持：

```text
candidate_queue_not_bug_claims
bug_claims_allowed: false
```

### 10.5 batch triage

```powershell
python -m src.metadata_batch_triage `
  --batch-report outputs/mocc-batch-scan-v1/linux-v7.1-fs.json `
  --out-json outputs/mocc-batch-scan-v1/linux-v7.1-fs-triage.json `
  --out-md outputs/mocc-batch-scan-v1/linux-v7.1-fs-triage.md
```

当前 v7.1 预期摘要：

```text
triage_items: 8
likely_false_positive: 6
needs_external_semantics: 2
needs_protocol_instance: 0
manual_bug_review_candidates: 0
```

### 10.6 ext4 replay bookkeeping source-fact audit

```powershell
python -m src.metadata_ext4_replay_bookkeeping_audit `
  --source-root linux-sources/linux-v7.1-fs/fs `
  --source-version 7.1 `
  --out-json outputs/mocc-batch-scan-v1/ext4-replay-bookkeeping-audit.json `
  --out-md outputs/mocc-batch-scan-v1/ext4-replay-bookkeeping-audit.md
```

当前预期摘要：

```text
audited_helpers: 2
helpers_with_public_int_return: 2
helpers_with_ignored_fast_commit_calls: 2
helpers_swallowing_ext4_map_blocks_errors: 2
helpers_with_metadata_bookkeeping_after_failure: 1
helpers_with_partial_metadata_mutation_before_failure: 1
bug_claims_allowed: 0
```

### 10.7 测试

```powershell
python -m compileall -q src tests scripts
python -m pytest -q
git diff --check
```

当前测试基线：

```text
238 passed
```

`git diff --check` 在 Windows 工作区可能只提示 LF/CRLF 转换 warning；没有 trailing
whitespace 或 patch whitespace error 即可。

## 11. 输出边界

当前活动 MOCC-SE 输出：

```text
outputs/confirmed_bugs.md
outputs/mocc-protocol-a-v1/
outputs/mocc-protocol-b-v1/
outputs/mocc-protocol-c-v1/
outputs/mocc-discovery-v2/
outputs/mocc-batch-scan-v1/
outputs/mocc-finding-review-v1/
```

其中：

- `mocc-protocol-*-v1/`：Protocol A/B/C 开发 witness；
- `mocc-discovery-v2/`：fresh discovery、source triage 和历史 ext4 fault-model 开发证据；
- `mocc-batch-scan-v1/`：freeze-bound 全量候选队列、batch triage、ext4 replay bookkeeping
  source-fact audit；
- `mocc-finding-review-v1/`：development review、version matrix、repair evidence、
  bug-hunt report 和 confirmed-bug linkage；
- `confirmed_bugs.md`：人工/历史/动态支持的 finding 状态记录。

`mocc-discovery-v1*` 和旧 SE-EOD 数据只保留历史/开发证据。所有 retained output 的语义以
[`outputs/README.md`](outputs/README.md) 为准。

## 12. 下一步优先级

当前最值得继续的是三条线，优先级如下。

### P0：闭合 ext4 replay bookkeeping 的外部语义

目标：回答 `ext4_ext_replay_set_iblocks()` 和 `ext4_ext_clear_bb()` 的失败是否必须导致
fast-commit replay abort。

需要做：

1. 查 ext4 fast-commit replay 官方文档、commit history、lore 讨论和 maintainer 反馈；
2. 如果找到语义契约，把 evidence 固定到 registry 或新 evidence artifact；
3. 如果语义支持“必须 abort”，再设计新的 operation instance 或扩展 Protocol A；
4. 如果语义支持 best-effort，则把这两个 review 降级为 false positive / out of scope；
5. 不论哪种结论，都不能直接修改 frozen active protocol，除非同步更新 freeze 和文档。

### P1：完成 blind validation 标注链

目标：让规则 maturity 有机会从 development 进入 validation/frozen。

需要做：

1. 填写 `reviewer_a_labels_v1.json` 和 `reviewer_b_labels_v1.json`；
2. 填写 `adjudication_v1.json`；
3. 记录分歧和 adjudication rationale；
4. 生成单独 evaluation artifact；
5. 不把 validation label 回流到 construction evidence。

### P2：减少 broad discovery 假阳性

目标：把当前 6 条 local-preparation 类 false positive 从源头降低。

需要做：

1. 把 triage 中识别到的 local/search-key/reservation preparation 模式迁入 discovery filter；
2. 保留 conservative unknown，不要过度过滤真实 metadata effect；
3. 更新 discovery/triage 测试；
4. 重新跑 v7.1 batch scan，确认 review_queue 从 8 更接近 2。

## 13. 交接检查

接手或提交前检查：

- [ ] `python -m pytest -q` 全部通过；
- [ ] `python -m src.metadata_rule_registry` 通过；
- [ ] `python -m src.metadata_evidence_verifier` 通过；
- [ ] `python -m src.metadata_validation_manifest` 通过；
- [ ] `metadata_validation_labels` 对两个 reviewer template 和 adjudication template 校验通过；
- [ ] exact candidate、review、unknown、needs external semantics 没有混合；
- [ ] 新 evidence 没有反向修改静态语义；
- [ ] 新 finding 状态区分 candidate、source_confirmed、patch_submitted、reviewed、upstream_accepted；
- [ ] 文档没有引用已删除模块或已删除输出；
- [ ] 所有研究主张均限制在当前支持片段内。
