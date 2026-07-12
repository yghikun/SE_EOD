# SE-EOD 项目交接文档

更新时间：2026-07-12  
工作目录：`E:\yanjiusheng\阅读论文\file_system\SE_EOD`

## 1. 交接摘要

SE-EOD 是面向 Linux 文件系统错误路径的协议感知静态分析原型。目前已经可以对两个 Linux 版本中的 ext4、btrfs、XFS、F2FS 执行可复现的静态分析矩阵，生成候选、协议证据、排序结果、LLM review task 和运行 manifest。

当前最可信的实验版本是 `experiment-v1.3.3`。

必须先记住两件事：

1. `benchmark/ext4-v6.8-pilot-labels.jsonl` 的 30 条标注只是第一 reviewer pilot，不是独立 gold benchmark，不能直接用来宣称正式 Precision/Recall。
2. Linux v7.1 btrfs 最终保留的 4 条候选不是误报。它们对应 `btrfs_recover_relocation()` 的两个错误路径，并分别被输出为 `missing_cleanup` 和 `partial_cleanup`。同一缺陷已经在 v6.8 上获得 QEMU/fault-injection 证据，不能为了候选归零而添加压制规则。

## 2. 当前验证状态

- 全量测试：`48 passed`
- Python 源码与脚本：`compileall` 通过
- 配置 JSON：全部可解析
- `experiment-v1.3.3/experiment_manifest.json`：完整记录 8 个矩阵单元
- v6.8/v7.1 btrfs 已知真阳性保留率：`100%`
- v7.1 btrfs 95 条审计：`4 true_bug / 91 false_positive`

### experiment-v1.3.3 矩阵

| Linux | 文件系统 | 错误路径 | 最终候选 |
|---|---|---:|---:|
| v6.8 | ext4 | 2222 | 16 |
| v6.8 | btrfs | 4959 | 5 |
| v6.8 | XFS | 1833 | 6 |
| v6.8 | F2FS | 1645 | 0 |
| v7.1 | ext4 | 2364 | 13 |
| v7.1 | btrfs | 5442 | 4 |
| v7.1 | XFS | 2280 | 8 |
| v7.1 | F2FS | 1755 | 4 |

与 v1.3 相比，只有 v7.1 btrfs 发生候选数量变化：`543 -> 4`，删除 539 条误报且保留 4 条已知真阳性。不能把该下降直接表述为 Precision 提升，正式准确率必须在冻结 benchmark 上测量。

## 3. Linux 源码基线

源码位于 `linux-sources/`，只保留四个目标文件系统目录。

| 版本 | Commit | 官方归档 SHA-256 |
|---|---|---|
| v6.8 | `e8f897f4afef0031fe618a8e94127a0934896aba` | `87eebb4c5d35b5c71e2b1dbdd106be6e6ccc0ee3c3ba0602a3fc4d9d169a6b93` |
| v7.1 | `8cd9520d35a6c38db6567e97dd93b1f11f185dc6` | `ad7f8010a17ecd9959c79cba639dfbbc9dccbbfb7323c5f1d04421368939f18f` |

完整来源记录：

- `linux-sources/linux-v6.8-fs/SOURCE_MANIFEST.json`
- `linux-sources/linux-v7.1-fs/SOURCE_MANIFEST.json`

不要用其他源码目录覆盖这两个快照，除非同时更新 source manifest 和实验版本号。

## 4. 重要产物

### 主实验

- `outputs/experiment-v1.3/`：最初的 2×4 基线矩阵
- `outputs/experiment-v1.3.1/`：btrfs path scope-cleanup 消融
- `outputs/experiment-v1.3.2/`：95 条候选审计和通用内存自动清理消融
- `outputs/experiment-v1.3.3/`：当前模型改进后的完整矩阵
- `outputs/experiment-v1.3.3/reports/model_refinement_comparison.md`：v1.3 与 v1.3.3 对比
- `outputs/experiment-v1.3.2/reports/btrfs_v7_1_candidate_audit.jsonl`：95 条逐条标签与证据

`experiment-v1.3.1` 和 `experiment-v1.3.2` 是论文消融证据，不是临时垃圾，不能删除。

### 已确认问题

- `outputs/confirmed_bugs.md`：当前确认、历史修复和动态验证问题总表
- `outputs/linux-v6.8/btrfs/recover_relocation_qemu_report.md`：btrfs recovery 故障注入证据

部分证据仍引用 `/root/bug_submit/...` 等仓库外路径。正式 artifact 前必须迁入仓库或替换成公开 URL。

### Benchmark pilot

- `benchmark/schema.json`：样本 schema
- `benchmark/README.md`：标注流程
- `benchmark/ext4-v6.8-pilot.jsonl`：30 条分层 pilot
- `benchmark/ext4-v6.8-pilot-labels.jsonl`：第一 reviewer 标注
- `benchmark/ext4-v6.8-pilot-reviewer2-todo.jsonl`：第二 reviewer 待标注文件
- `benchmark/ext4-v6.8-pilot-evaluation.*`：pilot 评估
- `benchmark/ext4-v6.8-pilot-taxonomy.*`：误报分类

第二 reviewer、分歧裁决和冻结 test split 尚未完成。

## 5. 配置结构

配置职责说明见 `configs/README.md`。

- `*_resource_map.json`：错误路径抽取阶段的资源状态、释放、自动清理和 callee consumption
- `*_resource_protocols/*.json`：候选生成后的协议证据和排序解释
- `*_wrapper_summaries.json`：wrapper/alias 证据；ext4 保留历史文件名 `wrapper_summaries.json`
- `*_review_false_positives.json`：人工复核契约和 confirmed bug exceptions

这些层次有部分 API 名称重叠，但用途不同，不应简单合并。

btrfs 新复核规则已经合入 canonical `configs/btrfs_review_false_positives.json` 的 `path_rules`。不要创建 `btrfs_v1_3_4_false_positives.json` 之类按实验版本命名的配置。新增规则必须：

1. 记录来源和 `reason_code`。
2. 优先使用严格 `path_ids` 和 `match_path_ids: true`。
3. 检查 `confirmed_bug_exceptions`，不得压制已知真阳性。
4. 增加正例和负例回归测试。

## 6. 核心实现变化

当前资源跟踪器已经支持：

- `__free(release_fn)`
- `BTRFS_PATH_AUTO_FREE`
- `BTRFS_PATH_AUTO_RELEASE`
- `AUTO_KFREE`
- `AUTO_KVFREE`
- cleanup-managed pointer alias
- `likely/unlikely/WARN_ON/WARN_ON_ONCE` 条件包装
- `PTR_ERR/PTR_ERR_OR_ZERO` 派生获取失败
- error-return callee consumption
- reviewed false-positive path contracts

关键文件：

- `src/resource_tracker.py`
- `src/error_condition.py`
- `src/candidate_rules.py`
- `configs/btrfs_resource_map.json`
- `configs/btrfs_review_false_positives.json`

当前仍以函数内分析为主，还没有完成论文路线图所要求的函数摘要、调用图和固定点跨函数所有权传播。

## 7. 常用命令

安装依赖并运行测试：

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```

重跑当前完整矩阵：

```powershell
python scripts/run_experiment_v1_3.py `
  --output-root outputs/experiment-v1.3.3 `
  --experiment-name experiment-v1.3.3 `
  --force
```

只重跑某个单元：

```powershell
python scripts/run_experiment_v1_3.py `
  --output-root outputs/experiment-v1.3.3 `
  --experiment-name experiment-v1.3.3 `
  --version linux-v7.1 `
  --filesystem btrfs `
  --force
```

runner 会从所有已有 `run_manifest.json` 重建根 manifest，局部重跑不会再丢失其他矩阵单元。

生成模型改进对比：

```powershell
python scripts/compare_experiment_v1_3_3.py
```

重建 95 条审计：

```powershell
python scripts/audit_btrfs_v7_1_candidates.py
```

重建 scope-cleanup 消融报告：

```powershell
python scripts/compare_scope_cleanup_ablation.py
```

## 8. 当前未完成事项

正式写论文结果前仍缺少：

1. 四文件系统独立 benchmark，建议总规模约 300 条，历史正例至少约 100 条。
2. 第二 reviewer、Cohen's kappa、分歧 adjudication 和冻结 test split。
3. 正式 Precision、Recall、F1、Precision@K 和分组指标。
4. B0-B4 内部消融以及至少一个外部 baseline。
5. 函数资源摘要、调用图和跨函数固定点传播。
6. ext4、XFS、F2FS 剩余候选的系统性人工审计。
7. 更多动态验证和 upstream 状态核验。
8. `pyproject.toml`、锁定依赖、CI、LICENSE、CITATION 和干净环境复跑。
9. 将仓库外 bug/patch 证据迁入 artifact。

详细路线见 `PAPER_ROADMAP.md`。该文件顶部已经列出目前有产物支持的完成项。

## 9. 建议接手顺序

### P0：冻结正式 benchmark 流程

1. 完成 ext4 pilot 第二 reviewer 标注和 adjudication。
2. 根据 pilot 修订标注指南，但不要把 Codex/LLM 标签当作 gold label。
3. 收集四文件系统历史修复正例。
4. 创建 development/validation/test split，并按 bug family 去重。

验收标准：至少能在冻结的小规模 benchmark 上无人工补答案地计算 Precision、Recall 和 F1。

### P0：实现核心方法创新

1. 定义资源状态机。
2. 生成参数级函数摘要。
3. 构建调用图并做固定点传播。
4. 为每个跨函数结论输出传播证据链。

验收标准：解决一组当前 wrapper/ownership 误报，同时保留现有 confirmed bug golden tests。

### P0：完成论文评估

1. 在冻结 benchmark 上跑 Full 和 B0-B4。
2. 接入至少一个外部 baseline。
3. 计算分组指标、置信区间、运行成本和人工成本。
4. 从脚本生成论文表格原始 CSV/JSON。

## 10. 交接风险清单

- 不要把候选数量下降写成 Precision 提升。
- 不要把 LLM/Codex verdict 当作 ground truth。
- 不要把 submitted patch 写成 upstream accepted。
- 不要把历史 bug 或重复发现写成全新 bug。
- 不要删除 `experiment-v1.3.1/.2` 消融目录。
- 不要给 `btrfs_recover_relocation()` 添加函数级 ownership-transfer 豁免。
- 不要使用冻结 test split 调规则或权重。
- 当前 worktree 含大量尚未提交的实验、benchmark、文档和实现变更；接手后应先审查并按逻辑拆分提交，不要执行 `git reset --hard`。

## 11. 下一位接手者的最小检查

```powershell
python -m pytest -q
python scripts/run_experiment_v1_3.py `
  --output-root outputs/experiment-v1.3.3 `
  --experiment-name experiment-v1.3.3
python scripts/compare_experiment_v1_3_3.py
```

预期结果：

- 测试至少 `48 passed`
- 根 manifest 的 `run_count` 为 `8`
- v6.8 btrfs 候选为 `5`
- v7.1 btrfs 候选为 `4`
- btrfs known-positive retention 为 `100%`

