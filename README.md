# se_eod
sk-2ca00cef957c46edad2cc22ee6b7423c
`se_eod` 是一个面向 Linux ext4 的 Python 3 静态分析原型。当前项目已经完成了一条从
Linux v6.8 ext4 源码准备、函数内错误路径抽取、资源清理建模、可疑候选筛选，到
LLM/DeepSeek 辅助复核任务生成的端到端流水线。

项目的核心目标不是直接输出 confirmed bug，而是构建一个可复现的 ext4 错误路径语料库，
并从中筛出值得人工继续验证的资源泄漏、部分清理和错误吞掉候选。

## 当前已经完成的具体工作

### 1. Linux v6.8 ext4 源码准备

已经实现 `scripts/download_linux_fs.py`，用于稀疏下载 Linux 源码：

- 默认下载 `torvalds/linux.git` 的 `v6.8`，并只 checkout `fs/ext4`。
- 也支持通过 `--sparse-path fs` 下载整个 Linux `fs/` 树。
- 下载目录仍然是 Git checkout，因此分析结果可以记录真实的 Linux commit 和 tag。
- 默认仓库内已经准备了 `linux-v6.8-fs/`，当前输出中记录的版本为：
  - `linux_git_commit`: `e8f897f4afef0031fe618a8e94127a0934896aba`
  - `linux_git_tag`: `v6.8`

### 2. C 文件发现、解析和函数抽取

已经实现 ext4 C 文件扫描和函数级切分：

- `src/file_walker.py`：扫描 `<linux_path>/fs/ext4/*.c`。
- `src/parser.py`：读取 C 文件，优先初始化 `tree-sitter` + `tree-sitter-c`。
- `src/parser.py` 同时实现文本级 fallback；即使本地 tree-sitter API 版本不兼容，也能继续分析。
- `src/function_extractor.py`：
  - 提取函数名、签名、函数体、起止行号。
  - 提取函数参数名，用于判断错误变量是否来自函数参数。
  - 支持基于 tree-sitter AST 的函数抽取。
  - 同时支持保守文本扫描模式，能处理一部分内核宏和预处理语法带来的解析问题。

### 3. 函数内错误路径抽取

已经实现 `src/error_path_extractor.py`，在每个函数内部识别错误条件和退出路径：

- 识别 `if (...) return ...;` 形式的直接错误返回。
- 识别 `if (...) goto label;` 形式的错误分支。
- 识别分支块内先调用 cleanup helper、再 `return` 或 `goto` 的路径。
- 解析 `goto` 目标 label，并沿 label 向后收集 cleanup 调用直到最终 `return`。
- 为每条路径生成函数内唯一 `path_id`，如 `ext4_xxx#003`。
- 记录错误条件所在行、条件文本、退出类型、目标 label、最终返回表达式和抽取原因。
- 默认只输出 `high` 和 `medium` 置信度路径；可用 `--include-low-confidence` 包含低置信度路径。

### 4. 错误条件分类

已经实现 `src/error_condition.py`，将错误条件归类为可分析的类型：

- `ret`、`err`、`error`、`retval`、`status` 等非零错误变量检查。
- `ret < 0`、`count < 0` 等负数错误检查。
- `!ptr` 空指针检查。
- `IS_ERR(ptr)`、`IS_ERR_OR_NULL(ptr)` 错误指针检查。
- `ERR_PTR(...)`、`PTR_ERR(...)`、负 errno、`NULL` 等错误返回表达式。
- 版本不匹配、size/bounds 检查、复合条件等验证失败路径。
- 根据条件形式、目标 label 名称和最终返回值综合给出 `high`、`medium`、`low` 或 `uncertain`。

### 5. 错误来源回溯

已经实现 `src/backward_slicer.py`，对错误变量做轻量后向切片：

- 从错误条件行向前查找最近一次赋值。
- 如果右侧包含函数调用，记录调用表达式，例如 `ext4_map_blocks(...)`。
- 如果错误变量来自函数参数，则记录为 `function_parameter`。
- 未能定位时记录为 `unknown`。

该信息写入 `error_source_expr`，用于后续判断错误是否被吞掉、是否来自资源获取失败等。

### 6. 函数内资源持有和清理建模

已经实现 `src/resource_tracker.py` 和 `configs/ext4_resource_map.json`：

- 在错误路径之前扫描资源获取调用。
- 在错误路径之前遇到释放调用时，从 held resource 集合中移除对应资源。
- 对 `x = acquire(...)` 形式的资源获取建模。
- 对 `obj->field = acquire(...)`、`array[i] = acquire(...)` 等字段/数组左值做保守建模。
- 对 `mutex_lock(lock)`、`spin_lock(lock)`、`down_read(sem)` 这类直接以参数表示资源的调用建模。
- 判断某些路径是否只是资源获取失败本身，避免误报“刚获取失败还要求释放”。
- 通过 `src/resource_expr.py` 和 `src/resource_release.py` 统一资源表达式、释放 wrapper 和 alias 匹配。
- 通过 `src/false_positive_model.py` 记录已审查确认的 ext4 函数契约和 false-positive 建模规则。
- 对每条错误路径记录：
  - `held_resources`
  - `cleanup_calls`
  - `missing_cleanup_candidates`

当前默认资源模型覆盖：

- 内存：`kmalloc`、`kzalloc`、`kcalloc`、`vmalloc`、`kvzalloc`、`kmem_cache_alloc`
- POSIX ACL：`posix_acl_alloc`
- buffer head：`sb_bread`、`bread`、`ext4_bread`、`ext4_getblk`
- journal handle：`ext4_journal_start`、`ext4_journal_start_sb`、`__ext4_journal_start_sb`
- 锁和信号量：`mutex_lock`、`spin_lock`、`down_read`、`down_write`

### 7. 错误路径 CSV 语料库生成

已经实现 `src/csv_writer.py`，将抽取到的错误路径写入 CSV：

- 不依赖数据库。
- 不使用 SQLite。
- 不使用 pandas。
- 多值字段以 JSON 字符串写入 CSV 单元格，例如：
  - `cleanup_calls`
  - `held_resources`
  - `missing_cleanup_candidates`

当前仓库已生成的 v1.2.2 false-positive rule backpropagation 输出：

- `outputs/ext4_error_paths.csv`
- 共 `2213` 条高/中置信度错误路径。
- 扫描 `39` 个 ext4 C 文件。
- 其中 `high` 置信度 `1288` 条，`medium` 置信度 `925` 条。

### 8. 可疑候选筛选

已经实现 `src/candidate_checker.py` 和 `src/candidate_rules.py`，从错误路径 CSV 中生成可疑候选：

- `missing_cleanup`：错误路径退出时，路径前已经获取的资源没有在 cleanup 路径中释放。
- `partial_cleanup`：cleanup label 释放了一部分资源，但仍有其他已持有资源未释放。
- `error_swallowed`：错误条件成立后最终返回成功值，例如 `0`，或在指针返回语义中返回 `NULL`。

候选严重程度规则已经实现：

- `P1`
  - journal handle 缺少 `ext4_journal_stop`
  - mutex/spinlock/rwsem 缺少解锁
  - 错误条件后返回 `0`
- `P2`
  - 缺少 `brelse`
  - 缺少 `kfree`、`kvfree`、`vfree`
  - 缺少 `posix_acl_release`
  - 部分清理候选
- `P3`
  - 其他较低优先级候选

当前仓库已生成：

- `outputs/suspicious_candidates.csv`
- 共 `38` 条静态可疑候选。
- 覆盖 `10` 个 ext4 C 文件。
- 类型分布：
  - `missing_cleanup`: `8`
  - `error_swallowed`: `29`
  - `partial_cleanup`: `1`
- 严重程度分布：
  - `P1`: `25`
  - `P2`: `13`

这些候选仍然只是静态可疑点，需要人工确认所有权转移、封装释放、路径可达性和上游补丁历史。

### 9. LLM 复核任务生成

已经实现 `src/llm_task_builder.py`，可以把可疑候选转换成 JSONL 格式的复核任务：

- 每条候选生成稳定 `task_id`。
- 解析 CSV 中的 JSON 字段，恢复为结构化数组。
- 自动截取候选行附近的源码上下文。
- 用 `>` 标记候选 `error_line`。
- 附带静态规则给出的原因。
- 附带固定复核问题，提醒检查：
  - 资源是否真的在错误路径前成功获取。
  - 错误路径是否真的退出函数。
  - cleanup label 是否已经释放资源。
  - 是否存在所有权转移。
  - 是否存在未建模的封装释放。
  - 候选应判为 `true_candidate`、`false_positive` 还是 `uncertain`。

当前仓库已生成：

- `outputs/llm_review_tasks.jsonl`
- 共 `38` 条 LLM 复核任务，与 `suspicious_candidates.csv` 一一对应。

### 10. DeepSeek 辅助复核和真候选提取

已经实现可选 DeepSeek 调用逻辑，默认不开启：

- API key 只从环境变量 `DEEPSEEK_API_KEY` 读取。
- 不把 secret 写入源码或输出文件。
- 默认模型参数：
  - `--deepseek-model deepseek-v4-pro`
  - `--deepseek-reasoning-effort max`
  - thinking mode enabled
- 支持 `--deepseek-limit` 限制发送数量。
- 支持 `--deepseek-start-index` 断点续跑。
- 支持 transient error retry。
- DeepSeek 输出写为 JSONL。
- 可以从已有 DeepSeek 结果中提取 verdict 为 `true_candidate` 的记录，而不重新调用模型。

仓库中保留了一轮早期 DeepSeek 辅助复核输出，基于 v1.2.1 的 `140` 条候选：

- `outputs/deepseek_reviews.jsonl`: `140` 条 DeepSeek 复核记录。
- `outputs/deepseek_true_candidates.jsonl`: `25` 条模型判为 `true_candidate` 的记录。
- `outputs/manual_bug_candidates_to_verify.md`: 对部分 DeepSeek true candidates 做了人工整理和后续验证计划。

注意：DeepSeek 结果只是辅助 triage，不是最终 bug 结论。

### 11. SE-EOD v1 协议证据排名

已经实现 SE-EOD v1：在现有静态候选之上增加 API resource protocol evidence layer。
该层不会替换原有 CSV 输出，也不会把候选升级为 confirmed bug，而是把“静态规则命中”、
“LLM/DeepSeek 辅助判断”和“API 生命周期协议支持”合并成可排序证据。

新增组件：

- `configs/resource_protocols/*.json`：显式描述 acquire/release 协议。
- `configs/wrapper_summaries.json`：记录已知 cleanup wrapper 和 release aliases。
- `src/protocol_db.py`：加载 `ResourceProtocolDB`，支持按资源类型、获取函数、释放函数和 required action 查询。
- `src/protocol_matcher.py`：把 `suspicious_candidates.csv` 中的 missing cleanup 与协议义务匹配。
- `src/evidence_ranker.py`：生成 ranked JSONL 和 CSV summary。
- `src/wrapper_summary.py`：加载 wrapper summary，判断某个 cleanup call 是否可能释放资源。
- `src/ownership_transfer.py`：生成轻量、保守的 ownership transfer hints。

当前协议覆盖：

- memory：`kmalloc`、`kzalloc`、`kcalloc`、`kmem_cache_alloc` -> `kfree`
- memory：`vmalloc`、`kvzalloc` -> `vfree` / `kvfree`
- buffer head：`sb_bread`、`bread`、`ext4_bread`、`ext4_getblk` -> `brelse`
- journal：`ext4_journal_start`、`ext4_journal_start_sb`、`__ext4_journal_start_sb` -> `ext4_journal_stop`
- locks/rwsem：`mutex_lock`、`spin_lock`、`down_read`、`down_write` -> 对应 unlock/up
- ACL：`posix_acl_alloc` -> `posix_acl_release`

证据等级保留为：

- `E0_STATIC_RULE_ONLY`
- `E1_LLM_TRUE_CANDIDATE`
- `E2_API_PROTOCOL_SUPPORTED`
- `E3_REPAIR_PATCH_SUPPORTED`
- `E4_DYNAMICALLY_REPRODUCED`
- `E5_UPSTREAM_CONFIRMED`

v1 只实现 `E0`、`E1`、`E2`。历史修复补丁证据、动态复现和 upstream confirmation
保留给 v2；DeepSeek verdict 仍然只是辅助排序信号，不是确认 bug 的证据。

### 12. SE-EOD v1.1 异常感知协议排名

SE-EOD v1.1 在 v1 的 API lifecycle protocol ranking 上增加 exception-aware 证据：

- wrapper summary：如果 cleanup path 中出现已知 wrapper 或 alias，记录 `released_by_wrapper_possible`。
- ownership transfer hint：如果资源被写入结构字段、传入可能保留所有权的函数、或加入 list-like 结构，记录 `ownership_transfer_possible`。
- 这些提示不会删除候选，也不会自动判定 false positive。
- v1.1 只把候选降分，并把需要人工复核的 exception hints 写入 ranked JSONL、CSV summary 和 LLM task。

这有助于优先查看高置信度 `E2_API_PROTOCOL_SUPPORTED` 候选，同时保留 wrapper/ownership
不确定候选供人工继续判断。历史修复补丁证据仍保留给 v2；动态验证仍保留给 v2/v3。

启用 v1.1 的完整命令：

```bash
python -m src.main \
  --linux linux-v6.8-fs \
  --out outputs/ext4_error_paths.csv \
  --check-candidates \
  --candidates-out outputs/suspicious_candidates.csv \
  --rank-evidence \
  --wrapper-summaries configs/wrapper_summaries.json \
  --enable-ownership-transfer-hints \
  --ranked-candidates-out outputs/ranked_candidates.jsonl \
  --candidates-with-evidence-out outputs/candidates_with_evidence.csv
```

默认情况下，如果 `configs/wrapper_summaries.json` 存在，ranking 会加载 wrapper summaries；
ownership transfer hints 需要显式传入 `--enable-ownership-transfer-hints`。

## SE-EOD v1.1 验收与排序对比

v1.1 当前建议先冻结并验收，不急着进入 v2 历史补丁挖掘。验收目标是确认：

- 原始候选仍然保留，没有因为 exception hint 被删除。
- `E2_API_PROTOCOL_SUPPORTED` 候选仍然可识别。
- wrapper/ownership hint 只影响分数，不改变候选存在性。
- `score_explanation` 能解释每个候选为什么加分或降分。
- LLM task 中包含 `matched_protocols`、`exception_hints`、`wrapper_evidence` 和 `ownership_transfer_hints`。

生成 v1 baseline：

```bash
python -m src.main \
  --linux linux-v6.8-fs \
  --out outputs/ext4_error_paths.csv \
  --check-candidates \
  --candidates-out outputs/suspicious_candidates.csv \
  --rank-evidence \
  --ranked-candidates-out outputs/ranked_candidates_v1_no_exceptions.jsonl \
  --candidates-with-evidence-out outputs/candidates_with_evidence_v1_no_exceptions.csv
```

生成 v1.1 exception-aware ranking：

```bash
python -m src.main \
  --linux linux-v6.8-fs \
  --out outputs/ext4_error_paths.csv \
  --check-candidates \
  --candidates-out outputs/suspicious_candidates.csv \
  --rank-evidence \
  --enable-ownership-transfer-hints \
  --wrapper-summaries configs/wrapper_summaries.json \
  --ranked-candidates-out outputs/ranked_candidates_v1_1.jsonl \
  --candidates-with-evidence-out outputs/candidates_with_evidence_v1_1.csv
```

生成验收报告：

```bash
python scripts/validate_v1_1.py \
  --v1-ranked outputs/ranked_candidates_v1_no_exceptions.jsonl \
  --v1-1-ranked outputs/ranked_candidates_v1_1.jsonl \
  --report-out outputs/v1_1_validation_report.md \
  --limit 20
```

报告会输出总体统计、protocol 和 exception hint 分布、v1 到 v1.1 的排名升降变化、
top 20 高分候选，以及 top 20 exception hint 候选。

## SE-EOD v1.2: Review Feedback 闭环

SE-EOD v1.2 在 v1.1 的 exception-aware ranking 后增加 review feedback layer。目标不是删除
候选，也不是把外部审查结果当作 confirmed bug，而是把候选 triage 结果结构化沉淀到 ranking 中：

- `true_candidate` feedback：提高排序分数。
- `false_positive` feedback：降低排序分数。
- `uncertain` feedback：轻微降分或保持低影响。
- confirmed exception 只作为解释和规则更新线索，不再额外叠加强降分。
- 所有候选仍然保留，review label 只影响 `evidence_score` 和 `score_explanation`。

SE-EOD v1.2.1 进一步引入 source-aware review feedback scoring。`review_source` 不同，调分强度不同：

- `codex_static_review`：弱静态审查反馈，用于排序校准，不等价于人工确认或上游确认。
- `human_manual_review`：较强人工审查反馈。
- `upstream_confirmed`：最强上游确认或明确 intended behavior 反馈。

Review label 文件：

```text
outputs/manual_review_labels.jsonl
```

示例：

```json
{
  "candidate_id": "candidate_...",
  "verdict": "false_positive",
  "confidence": "high",
  "reason": "buffer_head is released by put_bh wrapper",
  "confirmed_exception": true,
  "confirmed_exception_type": "released_by_wrapper",
  "suggested_rule_update": "add put_bh as buffer_head release wrapper",
  "next_action": "add_wrapper_summary",
  "validation_hint": "none",
  "review_source": "human_manual_review",
  "reviewer": "manual",
  "notes": "wrapper summary should be updated"
}
```

启用 review feedback ranking：

```bash
python -m src.main \
  --linux linux-v6.8-fs \
  --out outputs/ext4_error_paths.csv \
  --check-candidates \
  --candidates-out outputs/suspicious_candidates.csv \
  --rank-evidence \
  --enable-ownership-transfer-hints \
  --wrapper-summaries configs/wrapper_summaries.json \
  --manual-review-labels outputs/manual_review_labels.jsonl \
  --ranked-candidates-out outputs/ranked_candidates.jsonl \
  --candidates-with-evidence-out outputs/candidates_with_evidence.csv
```

当前 source-aware 分数调整规则：

```text
codex_static_review:
  true_candidate high: +25
  true_candidate medium: +15
  false_positive high: -30
  false_positive medium: -15
  uncertain: -5

human_manual_review:
  true_candidate high: +50
  true_candidate medium: +30
  false_positive high: -60
  false_positive medium: -30
  uncertain: -5

upstream_confirmed:
  true_candidate / fixed: +100
  false_positive / intended_behavior: -100
  uncertain: -5
```

当前仓库已经完成第一批 `40` 条队列的源码静态审查标签，写入
`outputs/manual_review_labels.jsonl`。这些标签的 `reviewer` 和 `review_source` 都是
`codex_static_review`，表示它们是基于当前源码上下文的弱静态 triage 证据，不等价于
human manual review 或 upstream confirmed bug。

v1.2-static-review / v1.2.1 source-aware scoring 的冻结 checkpoint 结果：

- 候选总数仍保持 `140`。
- `E2_API_PROTOCOL_SUPPORTED` 仍保持 `111`。
- `exception_hints_count` 仍保持 `37`。
- `review_label_records = 40`。
- `review_feedback_applied = 40`。
- 首批标签分布：`35` 条 `false_positive`，`5` 条 `true_candidate`。
- 全部标签来源：`codex_static_review = 40`。
- source-aware weak feedback 后 top 20 中包含 `3` 条已标注 `true_candidate`。
- 被标注 `false_positive` 的候选平均排名下降约 `47.6` 位。
- 被标注 `true_candidate` 的候选平均排名上升约 `24.8` 位。

## SE-EOD v1.2.2: False-positive Rule Backpropagation

SE-EOD v1.2.2 把首批 `codex_static_review` 中已经确认的 false-positive 模式写回静态建模层。
这一步和 v1.2 review feedback 不同：review feedback 只调分、不删除候选；v1.2.2 会在资源模型
确认 cleanup 已覆盖时，直接避免生成对应的 missing-cleanup / partial-cleanup 候选。

新增建模能力：

- 统一资源表达式比较：支持 `s->base`/`base`、额外括号、cast、`bhs[i]`/`bhs` 等保守别名。
- 对带数组下标的字段尾名保持保守：不会把 `oi->of_binfo[i].ob_bh` 简化成 `ob_bh`，避免吞掉 orphan.c
  中需要继续验证的 loop-index cleanup 候选。
- cleanup wrapper/alias 进入确定性释放建模：`put_bh` -> `brelse`、`kobject_put` -> kobject release、
  `kmem_cache_free(cache, obj)` 释放第二参数、`ext4_fc_free(fc)` 释放 `fc->fs_private`/`s_ctx`。
- label resolver 会跟随 `cleanup_dquot -> cleanup` 这类二级 cleanup label。
- acquire-failure 过滤支持 `ptr == NULL`、`NULL == ptr`、`!obj->field` 等真实内核表达式。
- 已知 ext4 caller/callee contract 建模：`__track_dentry_update` 和
  `ext4_ind_truncate_ensure_credits` 的 caller-owned lock restore，`ext4_bread_batch(wait=false)`
  的 caller-owned buffer-head transfer，以及 `ext4_whiteout_for_rename` error cleanup contract。
- 嵌套 `if` 的内部 return/goto 不再被归因到外层条件，减少 path-infeasible false positive。

当前 v1.2.2 输出结果：

- `total_candidates = 38`
- `missing_cleanup = 8`
- `partial_cleanup = 1`
- `error_swallowed = 29`
- `E2_API_PROTOCOL_SUPPORTED = 9`
- `exception_hints_count = 2`
- `manual_review_labels_count = 40`
- `manual_review_applied_count = 5`
- 首批 `35` 条 `codex_static_review` false-positive 标签对应候选已不再出现。
- `ext4_xattr_block_set`、`ext4_map_blocks`、`__track_dentry_update`、
  `parse_apply_sb_mount_options` 中已审查的 false-positive missing-cleanup 模式当前为 `0` 条。
- `ext4_init_orphan_info` 中 `candidate_65d848d5f1fd` 和 `candidate_f3e8e44a00d3`
  仍保留为 true-candidate 静态审查候选，没有被数组别名规则吞掉。

生成不带 review feedback 的 v1.2.2 baseline：

```bash
python -m src.main \
  --linux linux-v6.8-fs \
  --out outputs/ext4_error_paths.csv \
  --check-candidates \
  --candidates-out outputs/suspicious_candidates.csv \
  --rank-evidence \
  --enable-ownership-transfer-hints \
  --wrapper-summaries configs/wrapper_summaries.json \
  --ranked-candidates-out outputs/ranked_candidates_v1_2_fp_model_no_manual.jsonl \
  --candidates-with-evidence-out outputs/candidates_with_evidence_v1_2_fp_model_no_manual.csv
```

生成第一批 review 队列：

```bash
python scripts/prepare_manual_review_queue.py \
  --ranked outputs/ranked_candidates_v1_2_fp_model_no_manual.jsonl \
  --llm-tasks outputs/llm_review_tasks.jsonl \
  --queue-jsonl-out outputs/manual_review_queue.jsonl \
  --queue-md-out outputs/manual_review_queue.md \
  --label-template-out outputs/manual_review_labels_todo.jsonl \
  --limit 20
```

该脚本会选取 ranked top 20 和 `has_exception_hints=true` 的 top 20，并按 `candidate_id`
去重。当前仓库已生成 `21` 条待审查队列，label template 中显式包含 `review_source`：

- `outputs/manual_review_queue.jsonl`：结构化审查队列，便于脚本处理。
- `outputs/manual_review_queue.md`：带源码上下文的浏览版。
- `outputs/manual_review_labels_todo.jsonl`：待填写标签模板。

注意：`manual_review_labels_todo.jsonl` 不是 ranking 输入文件。审查完成后，只把已填好
且 verdict 为 `true_candidate`、`false_positive` 或 `uncertain` 的 JSON object 复制到
`outputs/manual_review_labels.jsonl`，再重新运行 ranking。ranker 会忽略说明行和未填写的
TODO verdict。

加入真实 human manual review 或 upstream confirmed 标签后的验收目标：

- `manual_review_labels_count > 0`
- `manual_review_applied_count > 0`
- `labels_by_review_source` 能区分 `codex_static_review`、`human_manual_review` 和 `upstream_confirmed`。
- false positive 候选排名下降，true candidate 候选排名上升。
- v1.2.2 当前候选总数保持 `38`。
- v1.2.2 当前 `E2_API_PROTOCOL_SUPPORTED` 数量保持 `9`。

生成 v1.2.1 source-aware review-feedback 验收报告：

```bash
python scripts/validate_v1_2_review_feedback.py \
  --baseline-ranked outputs/ranked_candidates_v1_2_fp_model_no_manual.jsonl \
  --feedback-ranked outputs/ranked_candidates.jsonl \
  --review-labels outputs/manual_review_labels.jsonl \
  --report-out outputs/v1_2_review_feedback_report.md \
  --limit 20
```

报告会输出 review verdict、reviewer/source 分布、score adjustment by source、top 20
质量变化、true/false candidate 平均排名变化、最大升降排名候选，以及后续建议动作分布。
旧入口 `scripts/validate_v1_2_manual.py` 和旧参数名仍保留兼容，但新报告名优先使用
`outputs/v1_2_review_feedback_report.md`。

### 13. Demo 测试覆盖

已经实现 `tests/test_demo.py` 和 `tests/demo_ext4_like.c`：

- 构造临时 Linux-like 目录 `fs/ext4/demo_ext4_like.c`。
- 跑完整分析流程：
  - 错误路径抽取
  - 可疑候选筛选
  - LLM task 生成
- 覆盖直接错误返回。
- 覆盖 `goto` cleanup label。
- 覆盖 buffer head 的 `brelse` 正确清理和缺失清理。
- 覆盖 journal handle 的 `ext4_journal_stop` 正确清理和缺失清理。
- 覆盖 ACL 类似函数里的 size、version、bounds、allocation 失败路径。
- 覆盖 `error_swallowed` 候选。
- 覆盖 `partial_cleanup` 候选。
- 覆盖 DeepSeek true candidate 提取逻辑。
- 覆盖 `ResourceProtocolDB` 加载、buffer head/journal/mutex 协议匹配、ranked JSONL/CSV 输出。
- 覆盖带协议证据的 LLM task 字段。
- 覆盖 `WrapperSummaryDB`、wrapper exception hint、ownership transfer hint 和异常感知降分。
- 覆盖 review feedback label 调分且不删除候选。
- 覆盖 v1.2.2 false-positive rule backpropagation：字段别名、数组元素、`kmem_cache_free`
  第二参数、`put_bh`、`kobject_put`、`ext4_fc_free`、NULL acquire-failure 和嵌套 if 归因。

## 项目目录说明

```text
.
├── configs/
│   ├── ext4_resource_map.json        # 资源获取/释放映射
│   ├── btrfs_resource_map.json       # btrfs 资源获取/释放映射
│   ├── wrapper_summaries.json        # cleanup wrapper / alias 摘要
│   ├── btrfs_wrapper_summaries.json  # btrfs cleanup wrapper / alias 摘要
│   ├── resource_protocols/           # ext4 API lifecycle 协议
│   └── btrfs_resource_protocols/     # btrfs API lifecycle 协议
├── linux-v6.8-fs/                    # 稀疏 checkout 的 Linux v6.8 源码
├── outputs/
│   ├── ext4_error_paths.csv          # 错误路径语料库
│   ├── suspicious_candidates.csv     # 静态可疑候选
│   ├── ranked_candidates.jsonl       # v1/v1.2 证据排名结果
│   ├── candidates_with_evidence.csv  # v1/v1.2 证据 summary
│   ├── ranked_candidates_v1_no_exceptions.jsonl
│   ├── ranked_candidates_v1_1.jsonl
│   ├── ranked_candidates_v1_2_no_manual.jsonl
│   ├── ranked_candidates_v1_2_fp_model_no_manual.jsonl
│   ├── candidates_with_evidence_v1_no_exceptions.csv
│   ├── candidates_with_evidence_v1_1.csv
│   ├── candidates_with_evidence_v1_2_no_manual.csv
│   ├── candidates_with_evidence_v1_2_fp_model_no_manual.csv
│   ├── v1_1_validation_report.md     # v1.1 排名验收报告
│   ├── v1_2_review_feedback_report.md
│   ├── v1_2_manual_feedback_report.md  # 兼容旧报告名
│   ├── manual_review_labels.jsonl    # v1.2 review feedback 标签
│   ├── manual_review_queue.jsonl     # v1.2 首批 review queue
│   ├── manual_review_queue.md        # v1.2 review 浏览版
│   ├── manual_review_labels_todo.jsonl
│   ├── llm_review_tasks.jsonl        # LLM 复核任务
│   ├── deepseek_reviews.jsonl        # DeepSeek 原始复核结果
│   ├── deepseek_true_candidates.jsonl
│   └── manual_bug_candidates_to_verify.md
├── scripts/
│   ├── download_linux_fs.py          # Linux 源码稀疏下载脚本
│   ├── prepare_manual_review_queue.py
│   ├── validate_v1_1.py              # v1/v1.1 排名对比和验收报告
│   ├── validate_v1_2_review_feedback.py
│   └── validate_v1_2_manual.py       # 兼容旧入口
├── src/
│   ├── main.py                       # CLI 入口和流水线编排
│   ├── parser.py                     # C 文件读取和 tree-sitter/text fallback
│   ├── function_extractor.py         # 函数抽取
│   ├── error_condition.py            # 错误条件分类
│   ├── backward_slicer.py            # 错误来源回溯
│   ├── label_resolver.py             # goto label cleanup 解析
│   ├── resource_tracker.py           # 函数内资源持有/释放建模
│   ├── error_path_extractor.py       # 错误路径抽取
│   ├── candidate_rules.py            # 可疑候选规则
│   ├── candidate_checker.py          # 候选 CSV 生成
│   ├── protocol_db.py                # ResourceProtocolDB
│   ├── protocol_matcher.py           # API 协议证据匹配
│   ├── wrapper_summary.py            # cleanup wrapper summary DB
│   ├── ownership_transfer.py         # ownership transfer hints
│   ├── manual_review.py              # review feedback labels 和调分
│   ├── evidence_ranker.py            # v1 证据等级和排序
│   ├── llm_task_builder.py           # LLM/DeepSeek 复核任务
│   └── csv_writer.py                 # 错误路径 CSV 写出
└── tests/
    ├── demo_ext4_like.c              # demo C fixture
    └── test_demo.py                  # 端到端测试
```

## 安装

```bash
cd se_eod
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

依赖：

- `tree-sitter>=0.20`
- `tree-sitter-c>=0.20`
- `pytest>=7`

实现会优先使用 `tree-sitter-c`。如果本地 tree-sitter API 组合不兼容，程序会输出 warning 并回退到文本级解析。

## 准备 Linux 源码

默认只下载 ext4：

```bash
cd se_eod
python scripts/download_linux_fs.py
```

下载整个 Linux `fs/` 目录：

```bash
python scripts/download_linux_fs.py --sparse-path fs
```

也可以手动准备完整内核源码：

```bash
git clone https://github.com/torvalds/linux.git
cd linux
git checkout v6.8
```

运行分析时传入源码根目录即可：

```bash
python -m src.main --linux /path/to/linux --out outputs/ext4_error_paths.csv
```

## 运行测试

```bash
cd se_eod
python -m pytest -q
```

## 生成错误路径语料库

扫描仓库内的 `linux-v6.8-fs`：

```bash
cd se_eod
python -m src.main \
  --linux linux-v6.8-fs \
  --out outputs/ext4_error_paths.csv
```

默认只写出 `high` 和 `medium` 置信度路径。包含低置信度路径：

```bash
python -m src.main \
  --linux linux-v6.8-fs \
  --out outputs/ext4_error_paths.csv \
  --include-low-confidence
```

运行后会打印统计信息，例如扫描文件数、函数数、错误路径数和可疑 missing cleanup 数。

## 扫描 Linux v6.8 btrfs

工具默认仍然扫描 `fs/ext4`，可以通过 `--fs-subdir` 和 `--resource-map` 切换到 btrfs。
当前 btrfs 配置覆盖内存分配、`btrfs_path`、transaction handle、root/block-group 引用、
`fs_path`、`extent_changeset`、`ulist` 和常见锁协议。

完整 btrfs 检查命令：

```bash
python -m src.main \
  --linux linux-v6.8-fs \
  --fs-subdir fs/btrfs \
  --resource-map configs/btrfs_resource_map.json \
  --out outputs/btrfs_error_paths.csv \
  --check-candidates \
  --candidates-out outputs/btrfs_suspicious_candidates.csv \
  --rank-evidence \
  --protocols-dir configs/btrfs_resource_protocols \
  --enable-ownership-transfer-hints \
  --wrapper-summaries configs/btrfs_wrapper_summaries.json \
  --ranked-candidates-out outputs/btrfs_ranked_candidates.jsonl \
  --candidates-with-evidence-out outputs/btrfs_candidates_with_evidence.csv \
  --build-llm-tasks \
  --llm-tasks-out outputs/btrfs_llm_review_tasks.jsonl
```

已在 Linux `v6.8` btrfs 上验证：

```text
scanned_files=63
scanned_functions=2876
extracted_error_paths=4954
total_candidates=248
E2_API_PROTOCOL_SUPPORTED_count=211
llm_review_tasks=248
pytest=9 passed
```

## 生成可疑候选

```bash
cd se_eod
python -m src.main \
  --linux linux-v6.8-fs \
  --out outputs/ext4_error_paths.csv \
  --check-candidates \
  --candidates-out outputs/suspicious_candidates.csv
```

该命令先生成错误路径 CSV，再根据规则生成 `suspicious_candidates.csv`。

## SE-EOD v1: Protocol Evidence Ranking

静态候选不是 confirmed bugs。SE-EOD v1 使用 `ResourceProtocolDB` 把原有 acquire/release
资源映射提升为显式 API 生命周期证据：如果候选缺少的 cleanup action 与协议义务匹配，
则候选获得 `E2_API_PROTOCOL_SUPPORTED`。如果只有静态规则命中，则保持
`E0_STATIC_RULE_ONLY`。如果可选 DeepSeek true-candidate 输入中存在同一 task，则可获得
`E1_LLM_TRUE_CANDIDATE`，但这仍只是辅助 triage。

生成候选并排名证据：

```bash
python -m src.main \
  --linux linux-v6.8-fs \
  --out outputs/ext4_error_paths.csv \
  --check-candidates \
  --candidates-out outputs/suspicious_candidates.csv \
  --rank-evidence \
  --wrapper-summaries configs/wrapper_summaries.json \
  --ranked-candidates-out outputs/ranked_candidates.jsonl \
  --candidates-with-evidence-out outputs/candidates_with_evidence.csv
```

基于已有候选单独排名：

```bash
python -m src.main \
  --rank-evidence \
  --candidates-in outputs/suspicious_candidates.csv \
  --ranked-candidates-out outputs/ranked_candidates.jsonl \
  --candidates-with-evidence-out outputs/candidates_with_evidence.csv
```

构造带协议证据的 LLM 复核任务：

```bash
python -m src.main \
  --linux linux-v6.8-fs \
  --build-llm-tasks \
  --candidates-in outputs/suspicious_candidates.csv \
  --rank-evidence \
  --wrapper-summaries configs/wrapper_summaries.json \
  --ranked-candidates-out outputs/ranked_candidates.jsonl \
  --llm-tasks-out outputs/llm_review_tasks.jsonl
```

## 生成 LLM 复核任务

基于已有候选生成 JSONL：

```bash
cd se_eod
python -m src.main \
  --linux linux-v6.8-fs \
  --build-llm-tasks \
  --candidates-in outputs/suspicious_candidates.csv \
  --llm-tasks-out outputs/llm_review_tasks.jsonl \
  --context-lines 80
```

一次性运行静态分析、候选筛选和 LLM task 生成：

```bash
python -m src.main \
  --linux linux-v6.8-fs \
  --out outputs/ext4_error_paths.csv \
  --check-candidates \
  --candidates-out outputs/suspicious_candidates.csv \
  --build-llm-tasks \
  --llm-tasks-out outputs/llm_review_tasks.jsonl
```

## 可选 DeepSeek 复核

先在 shell 中设置 API key：

```bash
export DEEPSEEK_API_KEY="..."
```

调用 DeepSeek 复核前 5 条任务：

```bash
python -m src.main \
  --linux linux-v6.8-fs \
  --build-llm-tasks \
  --candidates-in outputs/suspicious_candidates.csv \
  --llm-tasks-out outputs/llm_review_tasks.jsonl \
  --run-deepseek-review \
  --deepseek-reviews-out outputs/deepseek_reviews.jsonl \
  --deepseek-true-candidates-out outputs/deepseek_true_candidates.jsonl \
  --deepseek-model deepseek-v4-pro \
  --deepseek-reasoning-effort max \
  --deepseek-limit 5
```

从已有 DeepSeek 结果中提取 `true_candidate`，不重新调用 API：

```bash
python -m src.main \
  --extract-deepseek-true-candidates \
  --deepseek-reviews-out outputs/deepseek_reviews.jsonl \
  --deepseek-true-candidates-out outputs/deepseek_true_candidates.jsonl
```

## 输出文件说明

### `outputs/ext4_error_paths.csv`

错误路径语料库。主要字段：

- `linux_git_commit`：Linux checkout commit hash，失败时为 `unknown`。
- `linux_git_tag`：Linux tag/describe，失败时为 `unknown`。
- `file`：相对 Linux 源码根目录的 C 文件路径。
- `function`：函数名。
- `function_start_line` / `function_end_line`：函数范围。
- `path_id`：函数内路径编号。
- `error_line`：错误条件或直接错误返回所在行。
- `condition`：`if` 条件；直接返回时为空。
- `condition_type`：错误条件分类。
- `error_var`：条件中的主要错误变量。
- `error_source_expr`：错误变量最近来源表达式。
- `exit_type`：`return` 或 `goto`。
- `target_label`：`goto` 的目标 label。
- `cleanup_calls`：分支和 label cleanup 中收集到的调用，JSON list。
- `final_return_expr`：最终返回表达式。
- `held_resources`：错误路径前仍被认为持有的资源，JSON list。
- `missing_cleanup_candidates`：静态建议的缺失释放调用，JSON list。
- `confidence`：`high`、`medium`、`low` 或 `uncertain`。
- `reason`：抽取和分类原因。

### `outputs/suspicious_candidates.csv`

静态可疑候选。主要字段：

- `candidate_type`：`missing_cleanup`、`partial_cleanup` 或 `error_swallowed`。
- `severity`：`P1`、`P2` 或 `P3`。
- `evidence`：包含 held resources、missing releases、cleanup calls 和 final return 的 JSON。
- 其余字段继承自错误路径 CSV，便于定位源码。

### `outputs/ranked_candidates.jsonl`

SE-EOD 证据排名结果，每行一个候选。v1.2 输出会同时包含协议证据、exception hints
和可选 review feedback 字段。主要字段：

- `candidate_id`：稳定候选 ID。
- `candidate_type` / `severity`：继承静态候选类型和优先级。
- `evidence_level`：`E0_STATIC_RULE_ONLY`、`E1_LLM_TRUE_CANDIDATE` 或 `E2_API_PROTOCOL_SUPPORTED`。
- `evidence_score`：用于排序的整数分数。
- `static_evidence`：静态规则证据。
- `protocol_evidence`：匹配到的 API lifecycle 协议证据。
- `wrapper_evidence`：cleanup wrapper 或 alias 可能释放资源的证据。
- `ownership_transfer_hints`：资源可能被转移所有权的保守提示。
- `has_exception_hints` / `exception_hints`：是否存在 wrapper/ownership exception hints。
- `score_explanation`：本候选得分构成。
- `manual_review`：可选 review feedback 标签，字段名为兼容旧输出保留。
- `manual_score_adjustment`：review feedback 带来的分数调整。
- `llm_evidence`：可选 DeepSeek true-candidate 记录。
- `missing_evidence`：v1 尚未实现的 `repair_patch`、`dynamic_validation`、`upstream_confirmation`。

### `outputs/candidates_with_evidence.csv`

面向人工浏览的 ranked summary。主要字段：

- `candidate_id`
- `file`
- `function`
- `error_line`
- `candidate_type`
- `severity`
- `evidence_level`
- `evidence_score`
- `matched_protocol_ids`
- `required_actions`
- `has_exception_hints`
- `exception_hints`
- `released_by_wrapper_possible`
- `ownership_transfer_possible`
- `manual_verdict`
- `manual_confidence`
- `manual_review_source`
- `manual_confirmed_exception`
- `manual_exception_type`
- `manual_score_adjustment`
- `manual_reason`
- `manual_next_action`
- `manual_validation_hint`
- `score_explanation`
- `missing_evidence`
- `final_return_expr`

### `outputs/manual_review_labels.jsonl`

v1.2 review feedback 标签输入文件。每行一个 JSON object；没有 `candidate_id` 的说明行会被 ranker 忽略。
推荐使用 `ranked_candidates.jsonl` 中的稳定 `candidate_id`。

支持字段：

- `candidate_id`
- `verdict`: `true_candidate`、`false_positive` 或 `uncertain`
- `confidence`: `high`、`medium` 或 `low`
- `reason`
- `confirmed_exception`
- `confirmed_exception_type`
- `suggested_rule_update`
- `next_action`: `add_wrapper_summary`、`add_ownership_rule`、`runtime_validation`、
  `upstream_history_check` 或 `no_action`
- `validation_hint`: `ENOSPC`、`EIO`、`ENOMEM`、`quota`、`journal` 或 `none`
- `review_source`: `codex_static_review`、`human_manual_review` 或 `upstream_confirmed`
- `reviewer`
- `notes`

当前仓库的第一批标签使用 `reviewer=codex_static_review` 和
`review_source=codex_static_review`，包含 `40` 条静态审查结论。这些标签用于弱排序反馈和规则沉淀，
不代表 human manual review 或 upstream confirmed bug。

### `outputs/manual_review_queue.jsonl`

由 `scripts/prepare_manual_review_queue.py` 生成的首批 review queue。默认包含 ranked top 20
和 exception-hint top 20 的去重集合。每行包含候选定位、分数、协议、exception hints、
score explanation、label template 和源码上下文。

### `outputs/manual_review_queue.md`

同一队列的浏览版，适合直接阅读源码上下文并填写审查结论。

### `outputs/manual_review_labels_todo.jsonl`

review feedback TODO 模板，不应直接作为 `--manual-review-labels` 输入。填完后，把有效 JSON object
复制到 `outputs/manual_review_labels.jsonl`。未填写的占位 verdict 会被 loader 忽略。

### `outputs/ranked_candidates_v1_no_exceptions.jsonl`

用于 v1.1 验收的 v1 baseline ranked 输出。它保留协议 ranking 和 wrapper summary 默认行为，
但不启用 `--enable-ownership-transfer-hints`。

### `outputs/ranked_candidates_v1_1.jsonl`

用于 v1.1 验收的 exception-aware ranked 输出，启用了 wrapper summaries 和 ownership transfer hints。

### `outputs/ranked_candidates_v1_2_no_manual.jsonl`

v1.2.1 review-feedback 对比用历史 baseline。它启用 wrapper summaries 和 ownership transfer hints，
但不应用 `manual_review_labels.jsonl`。该文件保留 `140` 个候选、`111` 个 E2 候选、
`37` 个 exception-hint 候选的冻结 checkpoint。

### `outputs/ranked_candidates_v1_2_fp_model_no_manual.jsonl`

v1.2.2 false-positive rule backpropagation 后的不带 review feedback baseline。当前统计为
`38` 个候选、`9` 个 E2 候选、`2` 个 exception-hint 候选、`0` 个 manual-applied 候选。

### `outputs/v1_1_validation_report.md`

由 `scripts/validate_v1_1.py` 生成的验收报告，包含：

- evidence level、candidate type、severity 和 exception hint 统计。
- protocol 命中分布。
- exception hint 类型分布。
- v1/v1.1 排名升降对比。
- top ranked candidates 和 top exception-hint candidates。

### `outputs/v1_2_review_feedback_report.md`

由 `scripts/validate_v1_2_review_feedback.py` 生成的 v1.2.1 source-aware review-feedback
验收报告，包含：

- review label 数量和应用数量。
- review verdict、confidence、reviewer/source、exception type、next action 和 validation hint 分布。
- source-aware score adjustment by source。
- baseline top 20 与 review-feedback top 20 的标签分布。
- true candidate / false positive 的平均排名变化。
- 最大上升和下降候选列表。

`outputs/v1_2_manual_feedback_report.md` 是兼容旧文件名的同内容报告。

### `outputs/llm_review_tasks.jsonl`

每行一个 LLM 复核任务，包含：

- 候选元数据。
- 结构化资源和 cleanup 信息。
- 带行号的源码上下文。
- 静态规则原因。
- 复核问题列表。
- 如果启用 `--rank-evidence`，还会包含 `matched_protocols`、
  `protocol_exceptions_to_check`、`wrapper_evidence`、`ownership_transfer_hints`、
  `has_exception_hints`、`exception_hints`、`manual_review`、`manual_score_adjustment`、
  `evidence_level`、`evidence_score` 和 `score_explanation`。

### `outputs/deepseek_reviews.jsonl`

每行一个 DeepSeek 调用结果，包含：

- task metadata。
- model。
- task index。
- 调用是否成功。
- 原始 response 或 error。

### `outputs/deepseek_true_candidates.jsonl`

从 DeepSeek 结果中提取出的 `verdict == "true_candidate"` 记录，方便后续人工验证。

### `outputs/manual_bug_candidates_to_verify.md`

对部分模型认为更值得跟进的候选做了人工整理，包括：

- 候选组。
- 函数名。
- JSONL 行号。
- 当前验证状态。
- 后续验证 checklist。

## 当前结果解读

当前标准输出显示，工具已经在 Linux v6.8 ext4 上抽取出 `2213` 条高/中置信度错误路径，
并在 v1.2.2 建模后筛出 `38` 条静态可疑候选。仓库中也保留了 v1.2.1 时期
`140` 条候选的一轮 DeepSeek 复核结果，作为历史 triage 资料。

其中 `manual_bug_candidates_to_verify.md` 已经把部分 DeepSeek true candidates 聚合为人工跟进组，例如：

- `ext4_fc_replay_inode`
- `ext4_fc_replay_add_range`
- `ext4_fc_replay_del_range`
- `ext4_init_orphan_info`
- `ext4_expand_extra_isize_ea`

这些记录的状态包括 `submitted`、`duplicate/fixed`、`pending` 和疑似 false positive。最终是否为 bug 仍需要结合最新 upstream、stable patch history、调用约定和 fault injection 继续确认。

## 已知局限

- 目前主要是函数内分析，不做完整跨函数所有权传播。
- cleanup wrapper 如果没有出现在资源映射里，可能导致 false positive。
- 资源所有权转移给子函数时，当前模型可能仍认为本函数持有资源。
- 复杂宏、条件编译和内核控制流可能影响路径可达性判断。
- label 解析是保守的线性解析，不等价于完整 CFG。
- `NULL` 返回是否表示错误取决于函数语义，仍需人工判断。
- LLM/DeepSeek 只用于辅助筛选，不替代代码证据、human review 或 upstream confirmation。
- SE-EOD v1 的协议证据仍是函数内证据，不等价于跨函数所有权证明。
- v1.1 的 wrapper/ownership exception hints 是降分信号，不是 false positive 判定。
- v1.2 的 review feedback labels 是排序反馈信号，不会删除候选；`codex_static_review`
  只作为弱静态审查反馈。
- v1.2.2 的 false-positive rule backpropagation 会改变静态建模并减少候选数量；这和
  review feedback 的“只调分不删除”语义不同。
- E3/E4/E5 仅作为保留等级，v1/v1.1/v1.2 尚未实现历史补丁挖掘、动态验证或 upstream confirmation。

## 后续工作

- 为 ext4 常见 cleanup wrapper 增加更多跨函数摘要。
- 对高价值候选做 upstream/stable patch history 对齐。
- 对 P1/P2 候选设计 fault injection 或镜像级复现。
- 将 human review / upstream confirmation 结果反向沉淀到规则中，降低 false positive。
- 对候选输出增加更细粒度的 ownership transfer 标注。
- 在 v2 中实现 repair patch evidence、dynamic validation 和 upstream confirmation。
