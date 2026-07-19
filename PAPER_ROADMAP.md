# 已完成进度（2026-07-14）

> 本文档保留历史进度和投稿路线。自 2026-07-18 起，跨工程、实验、论文和复现的统一完成门禁以 [`docs/PROJECT_CLOSURE_PLAN.md`](docs/PROJECT_CLOSURE_PLAN.md) 为准；当前代码事实以 [`docs/PROJECT_ARCHITECTURE.md`](docs/PROJECT_ARCHITECTURE.md) 为准。

以下任务已经完成并有仓库内产物；未列出的原路线图任务仍视为未完成。

- [x] 补全 Linux v6.8 与 v7.1 的 ext4、btrfs、XFS、F2FS 源码快照及来源 manifest（`linux-sources/`）。
- [x] 建立 benchmark schema、标注说明和稳定样本字段（`benchmark/schema.json`、`benchmark/README.md`）。
- [x] 建立并完成第一轮 30 条 ext4 v6.8 分层 pilot 标注；已明确它不是独立 gold test set（`benchmark/ext4-v6.8-pilot*.jsonl`）。
- [x] 实现 benchmark 评估、双 reviewer 比较和误报分类脚本（`scripts/evaluate_benchmark.py`、`scripts/compare_benchmark_reviews.py`、`scripts/analyze_benchmark_taxonomy.py`）。
- [x] 建立可选择 Linux 版本和文件系统的 Python 实验 runner（`scripts/run_experiment_v1_3.py`）。
- [x] 完成两个 Linux 版本、四个文件系统的 `experiment-v1.3` 静态分析矩阵（`outputs/experiment-v1.3/`）。
- [x] 每次矩阵运行记录命令、起止时间、源码版本、配置 SHA-256、Python/平台和 dirty worktree（各运行目录的 `run_manifest.json`）。
- [x] 生成跨版本、跨文件系统和候选变化报告（`outputs/experiment-v1.3/reports/`）。
- [x] 定位 v7.1 btrfs 543 条增长的主要原因，并完成 scope-cleanup 消融（`outputs/experiment-v1.3.1/reports/scope_cleanup_ablation.md`）。
- [x] 建模 `BTRFS_PATH_AUTO_FREE`、`BTRFS_PATH_AUTO_RELEASE`、`AUTO_KFREE`、`AUTO_KVFREE` 编译器自动清理。
- [x] 对 v7.1 btrfs 的 95 条候选进行逐条可复现源码审计（`outputs/experiment-v1.3.2/reports/btrfs_v7_1_candidate_audit.*`）。
- [x] 交叉核验并保留 `btrfs_recover_relocation()` 4 条已由 QEMU/fault injection 支持的真阳性，禁止误报规则压制已知真 bug。
- [x] 为自动清理、获取失败、错误返回消费、别名清理和审查契约增加回归测试（`tests/`）。
- [x] 完成 `experiment-v1.3.3` 两版本四文件系统重跑及模型改进差分，v6.8/v7.1 btrfs 已知真阳性保留率 100%（`outputs/experiment-v1.3.3/`）。
- [x] 完成 ext4 v6.8 的 CFG/path-sensitive 开发实验，接入基本块状态传播、状态 join、widening、截断统计和简单函数指针/间接调用处理（`src/cfg.py`、`src/resource_tracker.py`、`outputs/experiment-v1.5-cfg/`）。
- [x] 2026-07-14 修复 XFS 摘要收敛后全量回归测试通过：`110 passed`。

## 核心方法实现进度（2026-07-12）

- [x] 建立共享资源状态模型和错误路径违规契约（`src/resource_state.py`、`docs/method/resource_state_model.md`）。
- [x] 实现参数级函数摘要，覆盖直接释放、非首参数释放、out-parameter acquisition、返回值 acquisition、transfer/escape 和未知调用记录（`src/function_summary.py`）。
- [x] 实现目标函数集合内的调用图和固定点摘要传播，并保留调用链证据（`src/function_summary.py`）。
- [x] 将传播摘要以可选方式接入资源跟踪器和 CLI；历史实验默认行为不变（`src/resource_tracker.py`、`src/main.py`）。
- [x] 增加本地字段存储逃逸处理：`holder->field = ptr`、`holder.field = ptr` 会将当前局部 held resource 转为 escaped；普通 `alias = ptr` 不视为逃逸（`src/resource_tracker.py`、`tests/test_interprocedural.py`）。
- [x] 增加简单条件性 return acquisition：对 `arg ? *arg : NULL` 且 `if (!local) local = alloc()` 的可复用缓存路径，摘要记录 `argN == NULL`，调用点仅在实参确定为 `NULL/0` 时应用返回值 acquisition（`src/function_summary.py`、`src/resource_tracker.py`）。
- [x] 增加可审查的外部 API effect seed：`set_delayed_call(callback, cleanup, resource)` 将 `arg2` 标记为 transfer，并能经本地 wrapper 继续传播；该语义仅在跨过程模式生效（`src/function_summary.py`、`configs/ext4_resource_map.json`）。
- [x] 增加 retry 回边语义：标签解析在到达 return 前重访标签时标记为控制流环，不再将直接 `goto retry` 或 `error -> retry -> error` 当作函数错误退出（`src/label_resolver.py`、`src/error_path_extractor.py`）。
- [x] 增加可判定的 conditional effect：将函数体参数 guard 规范化为 `argN`，跨 wrapper 重映射条件，并在调用点安全求值布尔/整数常量、NULL 检查和已成功持有资源的非空 guard；未知复合条件仍保守不应用（`src/function_summary.py`、`src/resource_tracker.py`）。
- [x] 增加跨版本历史修复证据层：将 v6.8 `ext4_dx_add_entry` 的 3 条 `bh2` 泄漏候选与 v7.1 新增的 `brelse(bh2)` 修复行精确映射，候选保留并升级为 `E3_HISTORICAL_FIX_CONFIRMED`，不使用后续版本反向影响候选生成（`src/historical_fix.py`、`configs/ext4_historical_fixes.json`）。
- [x] 增加跨函数传播、状态转换、条件释放、条件返回获取、本地字段逃逸和摘要序列化回归测试（`tests/test_interprocedural.py`）。
- [x] 完成 ext4 v6.8 开发集同版本跨过程消融：baseline 和 interprocedural 均抽取 2198 条路径，候选分别为 16 和 19，retained 16、added 3、removed 0；3 条 added 均被 v7.1 源码修复确认为 E3；pilot eligible 11、true-positive retention 100%；摘要 1247 个函数、618 个 effect（其中 8 个 conditional effect）、4 轮收敛，Full 运行约 4.76 秒（`outputs/experiment-v1.4-baseline/linux-v6.8/ext4/`、`outputs/experiment-v1.4/reports/ext4_v6_8_interprocedural_ablation.md`）。
- [x] 建立 Linux v6.14 四文件系统检查脚本和测试（`scripts/check_linux_v6_14_filesystems.py`、`tests/test_linux_v6_14_checker.py`）。
- [x] 完成 Linux v6.14 `ext4`、`btrfs`、`f2fs`、`xfs` 四文件系统扫描，并上传 artifact（`outputs/linux-v6.14-bug-check/`）：合计 520 条 LLM review task，其中 ext4 30、btrfs 366、f2fs 55、xfs 69。
- [x] 完成 ext4 / XFS / F2FS 共 154 条候选的 DeepSeek 辅助 triage 和源码人工复核：人工复核真候选 43 条，归并为 11 个真 bug cluster。
- [x] 将已确认、已修复、已提交补丁和不应重复提交的项目记录到 `outputs/confirmed_bugs.md`，当前共 20 条 confirmed / reviewed bug records；其中 6 条已由上游修复，其余 14 条由已提交 patch 或 patch series 覆盖，但均不记为 upstream merged。
- [x] 已提交本轮关键 kernel patch：ext4、btrfs、XFS 和 F2FS 均已有提交记录；`reserve_chunk_space()` 已提交 v2 并获得 Reviewed-by。当前 submitted / under review 项不得写成 upstream accepted。
- [x] SE_EOD 仓库已同步到 GitHub `main`，临时 PR #1 已合并，临时分支已删除；交接文档同步提交为 `51b51c4`。
- [ ] 仍需在独立 benchmark 上完成更细粒度的 B0--Full 消融、复杂条件返回/alias 关系和间接调用边界验证；CFG 与简单函数指针处理已经落地，但目前仅完成 ext4 v6.8 开发集实验。当前实现是可验证的第一版方法闭环，不等同于最终论文版本，候选数变化不解释为最终 precision/recall。
- [x] 已定位并修复 Linux v6.14 XFS 摘要不收敛：条件传播的重复括号导致 effect identity 每轮变化；修复后 4 轮收敛，69 个候选保持完全一致（`outputs/linux-v6.14-xfs-convergence-check/xfs_convergence_report.md`）。
- [ ] XFS 仍有 1 个独立的 unresolved indirect call：`fs/xfs/xfs_fsmap.c::xfs_getfsmap` 中的 `fn`（约第 1097 行），需作为保守函数指针边界报告或后续建模。

# SE-EOD 论文与项目完整任务路线图

本文档把 SE-EOD 从当前研究原型推进到可投稿、可复现、可独立验证的研究制品。
所有任务均应以可检查的仓库产物结束，不能只以“做过分析”作为完成标准。

## 1. 总目标

目标论文主张建议冻结为：

> SE-EOD 是一种面向 Linux 文件系统错误路径的协议感知静态分析方法。它通过资源生命周期建模、跨函数所有权传播、异常证据校准和反馈驱动的误报抑制，发现资源泄漏、部分清理和错误吞噬缺陷。

建议投稿策略：

- 第一目标：按 CCF B 或同等水平正式论文的实验标准建设。
- 冲刺目标：在方法创新、独立 benchmark 和 upstream 结果足够强时投稿 ASE、ISSTA、FSE 或 ICSE 等主会。
- 保底目标：方法或实验未完全闭环时，拆分为 Tool Demo、Workshop 或应用型期刊论文。

## 2. 当前基线

截至 2026-07-14，仓库已经具备：

- ext4、btrfs、XFS、F2FS 四类文件系统配置。
- Linux v6.8、v7.1 和 v6.14 三个版本的扫描结果；v6.14 已覆盖四个目标文件系统。
- 错误路径抽取、CFG/path-sensitive 传播、跨函数摘要、简单函数指针/间接调用处理、候选规则、协议证据排名、wrapper summary、ownership hint、review feedback 和 LLM 辅助复核链路。
- demo 端到端测试和模块级回归测试；2026-07-14 修复 XFS 摘要收敛后全量测试为 `110 passed`。
- 20 个源码级确认、历史验证、动态验证、已修复或 patch submitted 的问题记录（`outputs/confirmed_bugs.md`）；其中 6 个已由上游修复，其余 14 个由已提交 patch/series 覆盖，但尚未记为 upstream merged。
- btrfs recovery 的 QEMU/fault-injection 验证材料。
- Linux v6.14 四文件系统扫描 artifact 和 ext4/XFS/F2FS 154 条候选人工复核结果。
- 多封已发往内核邮件列表的 ext4、btrfs、XFS、F2FS patch submission 记录。
- GitHub `main` 已同步到远端，交接文档和路线图可作为当前接手入口。

当前主要缺口：

- 没有独立、冻结、可复核的 ground-truth benchmark。
- 没有完整的 Precision、Recall、F1、Precision@K 和人工成本指标。
- 缺少与外部工具及基础规则方法的正式 baseline 对比。
- 跨函数所有权传播已有可运行实现，但仍需整理成论文级算法、消融和威胁分析。
- v6.8/v7.1 已有部分跨版本差分，Linux v6.14 已有扫描与人工复核；仍需统一成论文实验表格。
- 运行 manifest 已在多轮实验中记录，但依赖锁定、artifact 一键复现和 CI 仍未完成。
- 一部分确认材料引用仓库外路径，外部读者无法复现。
- 缺少 LICENSE、CITATION、CI 和正式 artifact 说明。
- Linux v6.14 XFS 的摘要不收敛问题已修复并完成隔离重跑；仍有 `xfs_getfsmap` 的 1 个 unresolved indirect call，需要在威胁分析中披露。

## 3. 优先级定义

- `P0`：不完成就不应提交正式论文。
- `P1`：决定论文质量、可复现性和投稿层次。
- `P2`：增强影响力，但可以在首篇论文后继续。
- 每项任务完成后，将 `[ ]` 改为 `[x]`，并补充产物路径或结果链接。

### 2026-07-14 当前执行顺序

当前不再以“增加候选数量”为主线，按以下阻塞关系推进：

1. **独立 benchmark**：从 30 条 ext4 开发 pilot 扩展到四文件系统 300--500 条样本，至少 100 个独立正例；冻结 dev/validation/test，完成双 reviewer、Cohen's kappa 和分歧裁决。
2. **分析正确性**：已修复 XFS 摘要固定点问题；下一步验证修复后的 XFS 结果进入统一三版本实验，并记录 `xfs_getfsmap::fn` 的保守函数指针边界。
3. **论文级评估**：补齐 Recall、F1、分组指标、bootstrap 置信区间、人工成本和机器可读/LaTeX 输出。
4. **正式 baseline 与消融**：在相同 benchmark 上完成 B0--Full，并实现至少一个 pattern baseline 和一个外部工具 baseline。
5. **Artifact 与论文表格**：统一 runner/manifest，锁定依赖，补 CI、LICENSE、CITATION 和公开证据；由脚本生成论文表 1--7。
6. **并行维护 upstream**：继续跟踪已提交 patch；只有进入维护者 tree 或 mainline 后才标记 E5/upstream accepted。

## 4. 阶段 A：冻结研究问题和实验口径

### A1. 冻结研究问题 `P0`

- [ ] `RQ1 Effectiveness`：SE-EOD 能否准确发现 Linux 文件系统错误路径缺陷？
- [ ] `RQ2 Ranking`：协议和异常证据能否提高高排名候选的准确率？
- [ ] `RQ3 Components`：各模块分别贡献了多少效果？
- [ ] `RQ4 Generalization`：方法能否跨文件系统、跨内核版本工作？
- [ ] `RQ5 Cost`：方法的运行成本和人工审查成本是多少？
- [ ] `RQ6 Findings`：发现了多少新问题、历史问题和可动态复现问题？

验收标准：

- 在论文草稿中，每个 RQ 对应一个实验、至少一个表格或图、一个明确结论。
- 不使用候选数量下降代替准确率提高。
- 不使用 LLM verdict 作为独立 ground truth。

### A2. 冻结术语和 bug 状态 `P0`

- [ ] 定义 `candidate`、`true bug`、`historical bug`、`false positive`、`uncertain`。
- [ ] 定义 `source-confirmed`、`dynamically reproduced`、`patch submitted`、`upstream accepted`。
- [ ] 定义资源泄漏、部分清理、错误吞噬和 stale error 的边界。
- [x] 修改 `outputs/confirmed_bugs.md`，区分 source-confirmed、already fixed、patch submitted / under review、QEMU fault-injection confirmed；当前 20 条记录不能都表述为新 bug。
- [ ] 把 `outputs/confirmed_bugs.md` 进一步整理为论文表 7 可直接导出的 CSV/JSON。

建议证据等级：

| 等级 | 含义 |
|---|---|
| E0 | 静态规则命中 |
| E1 | 路径和资源状态证据 |
| E2 | API/协议证据支持 |
| E3 | 历史补丁或 upstream commit 支持 |
| E4 | 动态复现或 fault injection 支持 |
| E5 | 修复被 upstream 接受 |

验收标准：每个最终报告的问题都有唯一状态、证据等级、证据文件和最后核验日期。

## 5. 阶段 B：建立独立 Benchmark

### B1. 设计 benchmark 格式 `P0`

- [ ] 新建 `benchmark/schema.json`，约束标注字段。
- [ ] 新建 `benchmark/README.md`，说明采样、标注和争议处理流程。
- [ ] 为每条样本保存稳定 ID、Linux commit、文件、函数、错误行和候选类型。
- [ ] 保存最小源码上下文或可定位到源码的 commit/line 信息。
- [ ] 记录 reviewer、verdict、confidence、reason、evidence 和 adjudication。
- [ ] 将开发集、验证集和最终测试集分离。

建议字段：

```json
{
  "sample_id": "benchmark_...",
  "linux_commit": "...",
  "filesystem": "btrfs",
  "file": "fs/btrfs/relocation.c",
  "function": "__add_reloc_root",
  "candidate_type": "missing_cleanup",
  "verdict": "true_bug",
  "confidence": "high",
  "reviewers": ["reviewer_a", "reviewer_b"],
  "evidence_level": "E3",
  "evidence_refs": ["..."],
  "notes": "..."
}
```

### B2. 构建正例集 `P0`

- [ ] 收集 Linux 历史修复 commit 中的资源泄漏、错误吞噬和部分清理问题。
- [ ] 优先覆盖四类目标文件系统。
- [ ] 保证每种候选类型至少有 20 个正例；不足时明确披露。
- [ ] 将 SE-EOD 已发现且经过独立确认的问题加入正例集。
- [ ] 对每个历史正例保存修复前 commit 和修复 commit。
- [ ] 检查正例是否能在修复前版本被扫描，避免不可构建或源码缺失样本。

目标规模：首版至少 100 个独立正例，理想规模 150--200 个。

### B3. 构建负例与 uncertain 集 `P0`

- [ ] 从四个文件系统分层抽样候选，而不是只选 top-ranked。
- [ ] 覆盖 wrapper release、ownership transfer、acquire failure、不可达路径和 intended behavior。
- [ ] 至少由两名 reviewer 独立标注最终测试集。
- [ ] 计算 Cohen's kappa 或其他一致性指标。
- [ ] 对分歧样本进行第三方 adjudication。
- [ ] uncertain 样本单独报告，不强行计入正例或负例。

目标规模：首版总样本 300--500 条。

### B4. 防止数据泄漏 `P0`

- [ ] benchmark 测试集不得参与规则开发和分数调参。
- [ ] Codex/DeepSeek 产生的标签不得直接作为 gold label。
- [ ] 对从历史 patch 构造的正例，记录规则是否已经见过同一修复模式。
- [ ] 跨版本评估时按 commit、函数和补丁族去重。
- [ ] 在论文中披露人工规则和 benchmark 的潜在耦合。

## 6. 阶段 C：实现核心方法创新

主路线建议选择“跨函数资源所有权传播”。协议自动推断和统计校准作为增强项，不能取代主路线。

### C1. 定义资源状态模型 `P0`

- [x] 定义 `UNSEEN`、`ACQUIRED`、`BORROWED`、`TRANSFERRED`、`RELEASED`、`ESCAPED`、`UNKNOWN` 状态（`src/resource_state.py`）。
- [x] 定义 acquire、release、return、out-parameter、field store 和 callback 注册的状态转换。
- [x] 定义错误路径终点上的违规条件。
- [ ] 定义 alias 不确定、条件编译和未知调用的保守语义。
- [x] 将模型写入 `docs/method/resource_state_model.md`。

验收标准：模型能用状态转换解释当前所有主要候选类型，而不是依赖散落的特殊分支。

### C2. 构建函数摘要 `P0`

- [x] 为函数生成参数级资源摘要（`src/function_summary.py`）。
- [x] 摘要已表达 acquire、release、transfer、escape 和 conditional effect；显式 borrow effect 仍需补齐并单独评估。
- [x] 支持返回值携带资源和 out-parameter 获取资源。
- [x] 支持第二参数或非首参数释放资源。
- [x] 支持 wrapper 中的条件释放。
- [x] 对无法可靠解析的调用记录 unknown/未解析信息，不静默假设安全。
- [x] 将摘要序列化到 `function_summaries.json`，便于人工检查；跨运行增量缓存仍未实现。

建议摘要示例：

```json
{
  "function": "wrapper_put",
  "effects": [
    {"resource": "arg0", "action": "release", "condition": "arg0 != NULL"}
  ]
}
```

### C3. 调用图与固定点传播 `P0`

- [x] 构建目标文件系统范围内的调用图。
- [x] 已实现固定点迭代和轮次上限；XFS 未收敛根因是条件表达式重复括号导致 effect identity 抖动，已修复并在 4 轮内收敛。
- [x] 在调用点应用 callee summary。
- [x] 对简单函数指针进行目标传播，对无法解析的间接调用采用 `UNKNOWN` 保守策略并输出诊断；宏和预处理边界仍需系统报告。
- [ ] 缓存稳定摘要，避免全量重复计算。
- [x] 输出跨函数结论的传播链，保证可解释性。

验收标准：至少解决一组当前已知的 wrapper/ownership false positives，并保留已知真阳性。

### C4. 路径敏感与别名处理 `P1`

- [x] 已用基本块 CFG 补充函数内线性 label 解析，并接入主流程（`src/cfg.py`、`outputs/experiment-v1.5-cfg/`）。
- [x] 区分 acquire 成功路径和 acquire failure 路径。
- [ ] 支持简单字段别名、数组元素和指针赋值传播。
- [x] 为路径合并定义状态 join 规则（`src/resource_state.py::join_states`）。
- [x] 通过状态上限与 widening 限制路径爆炸，并在 manifest 中记录 truncated/widened blocks。
- [ ] 报告宏和预处理不可见性造成的分析盲区。

当前边界：本地字段存储逃逸和简单指针赋值已覆盖，但数组元素、复杂 alias 与跨过程指针关系仍未达到论文级完整度；CFG 消融目前仅覆盖 ext4 v6.8 开发集。

### C5. 协议自动推断 `P2`

- [ ] 从已知 acquire/release 调用对扩展 wrapper 摘要。
- [ ] 从错误清理路径中挖掘高频资源释放模式。
- [ ] 对推断协议输出置信度和证据调用点。
- [ ] 人工确认后才能写入正式 protocol DB。
- [ ] 比较人工协议、自动协议和混合协议的精度与覆盖率。

### C6. 证据分数校准 `P1`

- [ ] 将当前启发式加减分与 benchmark verdict 对齐。
- [ ] 只在开发集上选择阈值和权重。
- [ ] 输出 reliability diagram 或分箱准确率。
- [ ] 比较原始启发式分数、校准后分数和无排名 baseline。
- [ ] 保留 score explanation 和 counter-evidence。

## 7. 阶段 D：Baseline、消融和指标

### D1. 内部 baseline `P0`

- [ ] `B0`：仅错误路径和基础候选规则。
- [ ] `B1`：B0 + 资源协议。
- [ ] `B2`：B1 + wrapper summary。
- [ ] `B3`：B2 + ownership hints。
- [ ] `B4`：B3 + false-positive rule backpropagation。
- [ ] `Full`：B4 + 跨函数传播和证据校准。
- [ ] 固定每个版本的配置和 commit，确保比较只改变目标模块。

### D2. 外部 baseline `P0`

- [ ] 调研 Coccinelle 是否能实现对应 semantic patch。
- [ ] 调研 CodeQL C/C++ 是否有资源泄漏和错误返回相关 query。
- [ ] 调研 Clang Static Analyzer 或 Infer 对 Linux 内核子集的可运行性。
- [ ] 对不能运行或不能表达的 baseline 记录客观原因。
- [ ] 至少实现一个简单 pattern baseline 和一个外部工具 baseline。
- [ ] 对所有工具使用相同源码版本和 ground truth。

注意：不能只比较报告数量，必须比较相同 benchmark 上的命中结果。

### D3. 指标实现 `P0`

- [x] 已建立 pilot 评估脚本 `scripts/evaluate_benchmark.py`；仍需升级为冻结 benchmark 的统一评估入口。
- [ ] 计算 Precision、Recall、F1。
- [x] 已计算当前样本规模允许的 Precision@10、@20、@50、@100。
- [ ] 计算不同文件系统和候选类型的分组指标。
- [ ] 计算误报减少率和真阳性保留率。
- [ ] 报告 bootstrap 置信区间或适当显著性检验。
- [ ] 输出机器可读 JSON/CSV 和论文可用 Markdown/LaTeX 表格。

### D4. 效率指标 `P1`

- [ ] 记录扫描文件数、函数数、错误路径数。
- [ ] 记录 wall-clock time、CPU time 和峰值内存。
- [ ] 区分解析、函数内分析、跨函数传播、排名和 LLM 阶段耗时。
- [ ] 报告启用跨函数分析前后的额外成本。
- [ ] 记录人工审查每条候选的中位时间。
- [ ] 报告 LLM 是否降低人工排序成本，但不把 LLM 判断当作正确答案。

## 8. 阶段 E：跨版本与泛化验证

### E1. 自动生成跨版本差分 `P0`

- [ ] 新建 `scripts/compare_versions.py`。
- [ ] 按稳定候选 ID、文件、函数、候选类型匹配 v6.8 和 v7.1。
- [ ] 分类为 persisted、fixed、new-code、removed-code、rule/config drift、unmatched。
- [ ] 对函数重命名和代码移动提供人工映射入口。
- [ ] 输出四个文件系统的差分表和 top changes。

### E2. 解释 btrfs 候选增长 `P0`

- [x] 核对两个版本使用的 resource map、protocol 和 wrapper summary，并通过冻结矩阵控制配置差异。
- [x] 区分新增源码和旧函数中新出现的候选。
- [x] 对清理模型修正后的 v7.1 btrfs 95 条候选完成逐条源码审计，而不是继续使用原始 543 条作为最终口径。
- [x] 统计各 candidate type、resource kind 和 evidence level 的变化。
- [x] 确认原始增长主要受 scope-cleanup/自动清理建模缺失影响，并验证已知真阳性保留率。
- [x] 将结论写入 `outputs/experiment-v1.3.1/reports/scope_cleanup_ablation.md` 和 `outputs/experiment-v1.3.2/reports/btrfs_v7_1_candidate_audit.md`。

### E3. 跨文件系统迁移 `P1`

- [ ] 区分通用协议和文件系统专用协议。
- [ ] 做 leave-one-filesystem-out 实验或等价迁移实验。
- [ ] 统计新增文件系统需要多少人工协议配置。
- [ ] 报告哪些规则能够复用，哪些必须人工定制。

### E4. 增加第三个 Linux 版本 `P1`

- [x] 选择 Linux v6.14 作为第三个版本，并保存 tag、commit 和来源 manifest。
- [x] 使用 CFG + interprocedural pipeline 扫描 ext4、btrfs、F2FS、XFS（`outputs/linux-v6.14-bug-check/`）。
- [ ] 验证主要结论不是 v6.8/v7.1 的偶然现象。
- [ ] 控制实验规模，不能因增加版本而牺牲人工标注质量。

## 9. 阶段 F：真实缺陷验证与 Upstream 闭环

### F1. 统一候选核验队列 `P0`

- [x] 已合并 Linux v6.14 四文件系统 LLM review task 队列：总计 520 条，ext4/XFS/F2FS 子集共 154 条已优先处理。
- [x] 已优先处理 ext4、XFS、F2FS 中 P1/P2、E2 以上和高价值候选，并完成源码人工复核。
- [x] ext4/XFS/F2FS 已核验项已记录函数、资源、错误路径、upstream/mainline 状态和 patch 状态（`outputs/confirmed_bugs.md`、`PROJECT_HANDOFF.md`）。
- [x] 已查询 latest mainline，区分已经由上游修复、重复发现、已提交但未合入的项目，避免重复报告。
- [ ] btrfs Linux v6.14 的 366 条候选还没有做同等粒度人工复核，应单独开一轮。
- [ ] 为 false positive 记录可复用的规则更新建议。

### F2. 动态验证 `P1`

- [ ] 为可触发候选设计 fault injection 点。
- [ ] 建立 QEMU 内核、镜像、挂载和日志采集脚本。
- [ ] 保存内核配置、镜像哈希和执行命令。
- [ ] 比较修复前后日志、返回值、引用计数或泄漏检测结果。
- [ ] 对无法自然触发的问题明确标注“条件注入验证”，避免过度表述。
- [ ] 目标：至少 5 个具有 E4 动态证据的问题。

### F3. 补丁和上游状态 `P1`

- [x] `__add_reloc_root()` 修复已提交 v2，并收到 reviewer 回复；后续只沿已有线程推进。
- [x] `reserve_chunk_space()` zoned 正返回值修复已提交 v2，并获得 Reviewed-by；尚未记为 upstream merged。
- [x] `btrfs_init_new_device()` sprout 回滚问题已形成并提交 3-patch series。
- [x] 已补充 XFS `xfs_rtginode_ensure()` 源码复核、latest mainline 对照和 patch submission 状态。
- [x] 已记录 F2FS 三个 patch 的 Message-ID、subject、收件人和 v1/v2 关系。
- [x] 已记录 submitted、already fixed upstream / duplicate finding、source-level confirmed、QEMU fault-injection confirmed 等状态（`outputs/confirmed_bugs.md`）。
- [ ] 继续跟踪 ext4、btrfs、XFS、F2FS 已提交 patch 的邮件列表 / patchwork 状态；维护者要求修改时只发 v2/v3，不重复开新线程。
- [ ] 补齐 XFS 历史问题的准确 fixing commit。
- [ ] 将可公开 patch 和复现材料放入仓库或稳定归档地址，替换 `/root/bug_submit/...` 等外部路径。
- [ ] 目标：至少 2 个 upstream accepted；未达到时如实报告。

### F4. 规则反馈闭环 `P1`

- [ ] 从确认 false positives 中提取 wrapper、transfer 和 acquire-failure 规则。
- [ ] 每次规则更新必须增加正例和负例回归测试。
- [ ] 在冻结测试集上验证真阳性保留率。
- [ ] 记录规则版本、来源证据和影响候选数量。
- [ ] 禁止直接根据测试集逐条硬编码函数名和行号。

## 10. 阶段 G：工程化与可复现 Artifact

### G1. 一键运行 `P0`

- [x] 新增 Linux v6.14 四文件系统 Python 检查脚本（`scripts/check_linux_v6_14_filesystems.py`）。
- [x] 支持选择 Linux 源码路径、输出目录、文件系统和是否运行 DeepSeek。
- [ ] 运行前检查依赖、源码 commit、配置和 API key。
- [ ] 支持 dry-run，打印将执行的步骤和输出路径。
- [ ] 失败时保留阶段状态，允许从中断点继续。
- [ ] 保留现有 Bash 脚本作为 Linux 快捷入口。
- [ ] 后续需要把 v6.8/v7.1/v6.14 的实验入口统一为一个论文级 runner，而不是只服务本轮 v6.14 检查。

### G2. 实验 manifest `P0`

- [x] Linux v6.14 检查已写出 `check_manifest.json`。
- [x] Linux v6.14 检查已记录 Linux tag/commit、源码来源和输出统计。
- [ ] 统一所有论文实验为 `run_manifest.json` / `check_manifest.json` 的稳定 schema。
- [ ] 记录 SE-EOD git commit 和 worktree dirty 状态。
- [ ] 记录 Python 和依赖版本。
- [ ] 记录所有配置文件 SHA-256。
- [ ] 记录完整 CLI 参数和开始/结束时间。
- [ ] 记录 DeepSeek model、endpoint、prompt schema version 和失败重试统计。
- [ ] 不记录 API key 或其他秘密。

### G3. 依赖与打包 `P1`

- [ ] 新增 `pyproject.toml`，声明 Python 版本和 CLI entry point。
- [ ] 为论文 artifact 固定精确依赖版本或生成 lock 文件。
- [ ] 将运行依赖和开发/测试依赖分组。
- [ ] 验证全新虚拟环境能安装并运行 demo。
- [ ] 可选：提供 Dockerfile，但不能把 Docker 当作唯一复现方式。

### G4. 测试重构 `P1`

- [ ] 将 `tests/test_demo.py` 拆分为 parser、tracker、ranking、review、CLI 等测试文件。
- [ ] 保留端到端 demo 测试。
- [ ] 为每个 confirmed bug 增加最小正例或 golden regression。
- [ ] 为每类主要 false positive 增加负例。
- [ ] 增加配置 schema 和 JSON 校验测试。
- [ ] 增加输出稳定性测试，避免字段或候选 ID 意外漂移。

### G5. CI 与质量门禁 `P1`

- [ ] 添加 GitHub Actions 或等价 CI。
- [ ] 在支持的 Python 版本上运行测试。
- [ ] 校验所有 JSON/JSONL/CSV schema。
- [ ] 运行 demo 端到端扫描。
- [ ] 检查 README 中引用的仓库内文件是否存在。
- [ ] 可选增加 formatter、linter 和类型检查；首次引入时避免无关大规模格式化。

### G6. 开源元数据 `P0`

- [ ] 添加明确的 `LICENSE`。
- [ ] 添加 `CITATION.cff`。
- [ ] 添加 `CONTRIBUTING.md` 和安全报告方式。
- [ ] 将 `/root/bug_submit/...` 等外部不可访问路径替换为仓库内材料或公开 URL。
- [ ] 检查输出中是否包含 API response 的隐私或不可再分发内容。
- [ ] 为 Linux 源码、模型输出和 benchmark 分别说明许可边界。

## 11. 阶段 H：论文实验与写作

### H1. 实验冻结 `P0`

- [ ] 创建论文实验 tag 或 release candidate。
- [ ] 冻结 benchmark test split。
- [ ] 冻结配置、依赖和 Linux commits。
- [ ] 从干净环境完整重跑全部实验。
- [ ] 自动生成所有论文表格的原始 CSV/JSON。
- [ ] 对异常结果进行解释，禁止只删除不利数据。

### H2. 必备表格 `P0`

- [ ] 表 1：数据集和扫描规模。Linux v6.14 原始统计来源已具备（`outputs/linux-v6.14-bug-check/check_manifest.json`），仍需整理成论文表格。
- [ ] 表 2：总体 Precision、Recall、F1。
- [ ] 表 3：按文件系统和候选类型分组结果。
- [ ] 表 4：内部消融实验。
- [ ] 表 5：外部 baseline 对比。
- [ ] 表 6：运行时间、内存和人工审查成本。
- [ ] 表 7：真实 bug、证据等级、补丁和 upstream 状态。原始记录已具备（`outputs/confirmed_bugs.md`），仍需导出成论文表格。

### H3. 必备图形 `P1`

- [ ] 方法架构图：源码到候选证据的完整数据流。
- [ ] 资源状态机或跨函数传播示意图。
- [ ] Precision@K 或累积真阳性曲线。
- [ ] 跨版本候选变化归因图。
- [ ] 可选：分数校准 reliability diagram。

### H4. 论文结构 `P0`

- [ ] Introduction：问题、缺口、方法、结果和贡献。
- [ ] Background/Motivation：用 1--2 个真实 bug 说明错误路径难点。
- [ ] Method：状态模型、摘要、传播、候选和证据校准。
- [ ] Implementation：解析器、配置、规模控制和 LLM 边界。
- [ ] Evaluation：围绕 RQ 组织，不按代码模块流水账描述。
- [ ] Findings：新 bug、历史 bug、动态复现和 upstream 状态。
- [ ] Threats to Validity：标注偏差、规则耦合、宏、版本和外部工具限制。
- [ ] Related Work：错误处理、资源泄漏、协议挖掘、Linux 静态分析和 LLM triage。
- [ ] Artifact：环境、命令、数据、预期输出和复现时间。

### H5. 论文贡献表述门禁 `P0`

- [ ] 不把 LLM 判断描述为确认 bug。
- [ ] 不把 submitted patch 描述为 upstream accepted。
- [ ] 不把历史 bug 描述为新发现。
- [ ] 不把候选数量下降描述为准确率提升。
- [ ] 不把四个文件系统描述为整个 Linux 内核的泛化证明。
- [ ] 所有百分比和数量都能追溯到脚本生成的结果文件。

## 12. 建议执行顺序

### 第 1--2 周：实验地基

- [ ] 完成 A1、A2。
- [x] 完成 benchmark schema 和 pilot 标注指南；独立 benchmark 的 sampling/adjudication 细则仍待冻结。
- [x] 增加运行 manifest 初版；稳定统一 schema 仍待完成。
- [ ] 固定依赖并恢复本地测试环境。

### 第 3--6 周：Benchmark 和 baseline

- [ ] 收集历史正例。
- [ ] 完成人工负例抽样和双人标注。
- [ ] 实现统一评估脚本。
- [ ] 跑 B0--B4 内部消融。
- [ ] 完成至少一个外部 baseline。

### 第 7--11 周：核心方法

- [x] 实现资源状态模型。
- [x] 实现函数摘要和调用图传播。
- [x] 增加路径合并、未知调用诊断和可解释传播链；XFS 摘要不收敛已修复，复杂 alias 边界仍待完善。
- [ ] 用开发集修复错误，不接触冻结测试集。

### 第 12--14 周：强验证

- [x] 已完成 Linux v6.14 四文件系统扫描与 ext4/XFS/F2FS 人工复核。
- [ ] 重跑并冻结四文件系统、多版本的最终论文实验。
- [ ] 完成统一的跨版本差分归因。
- [ ] 动态验证高价值候选。
- [x] 已推进 ext4、btrfs、XFS、F2FS 多个 patch submission。
- [ ] 继续跟踪 patch review、accepted/rejected/duplicate 状态。

### 第 15--16 周：Artifact 和论文

- [ ] 从干净环境一键复现实验。
- [ ] 冻结表格、图和 bug 状态。
- [ ] 完成论文初稿和内部审阅。
- [ ] 根据目标 venue 的页数和 artifact 要求裁剪。

## 13. 投稿门槛

### Workshop / Tool Demo

- [ ] 工具可运行，demo 可复现。
- [ ] 有清楚的架构和至少若干真实案例。
- [ ] 明确说明局限，不夸大 LLM 作用。

### CCF B 或同等正式论文

- [ ] 独立 benchmark 达到 300 条左右或有充分规模解释。
- [ ] 完整报告 Precision、Recall、F1 和 Precision@K。
- [ ] 有内部消融和至少一个外部 baseline。
- [ ] 四文件系统结果可解释。
- [ ] 至少若干源码级确认问题，并有动态或 upstream 强证据。
- [ ] Artifact 可从干净环境复现主要表格。

### CCF A 主会冲刺

- [ ] 跨函数所有权传播形成明确算法贡献。
- [ ] 相比 baseline 有显著且稳定的效果提升。
- [ ] benchmark 规模、标注独立性和统计方法经得起质疑。
- [ ] 有多个此前未知的真实问题，最好包含 upstream accepted patch。
- [ ] 方法在不同文件系统和版本上表现稳定。
- [ ] Artifact、威胁分析和复现材料完整。

## 14. 暂不优先事项

在 P0/P1 任务完成前，以下事项暂缓：

- [ ] GUI 或可视化 dashboard。
- [ ] 无明确实验目的地增加更多文件系统。
- [ ] 自动生成修复补丁作为主线。
- [ ] 继续堆叠大量人工函数名规则。
- [ ] 更换或并行接入多个 LLM 只为增加模型数量。
- [ ] 在 benchmark 冻结前反复调排序权重。

## 15. 最终 Definition of Done

项目达到正式论文投稿状态，必须同时满足：

- [ ] 方法贡献可以用一张状态模型图和一段算法描述讲清楚。
- [ ] 所有核心结论都有独立 benchmark 支持。
- [ ] 所有实验都能由统一命令和 manifest 复现。
- [ ] 所有表格都由脚本从原始结果生成。
- [ ] 所有确认 bug 都有可访问证据和准确状态。
- [ ] LLM 仅作为辅助 triage，不参与 ground truth 定义。
- [ ] 代码测试、配置校验和 demo 在 CI 中通过。
- [ ] README、LICENSE、CITATION 和 artifact 指南完整。
- [ ] 至少一名未参与实现的人按文档成功复现实验。

完成上述条件后，再根据跨函数方法的创新强度、实验提升幅度和 upstream 成果决定最终投稿层次。
