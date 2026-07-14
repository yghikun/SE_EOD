# SE-EOD 项目交接文档

更新时间：2026-07-14（当前状态以第 1、9、10、13 节为准；第 5、6、12 节保留历史执行记录）
工作目录：`E:\yanjiusheng\阅读论文\file_system\SE_EOD`

## 1. 当前一句话状态

SE-EOD 当前已经完成论文核心方法的主要工程落地：CFG 路径敏感资源传播、跨函数摘要、简单函数指针/间接调用处理、retry/backedge 语义、`PTR_ERR` 路径事实、CFG 诊断、候选证据排序和 LLM review task 生成都已经接入主流程。

现在的工作重点不是继续增加候选，而是补齐论文可信度闭环：独立 benchmark、XFS 固定点收敛、B0--Full 消融、外部 baseline、正式指标和可复现 artifact。

当前可核验快照：

- Linux v6.8、v7.1、v6.14，目标文件系统为 ext4、btrfs、F2FS、XFS。
- Linux v6.14 共生成 520 条 review task；ext4/XFS/F2FS 的 154 条已完成 DeepSeek 辅助 triage 和源码人工复核。
- `outputs/confirmed_bugs.md` 当前记录 20 条 confirmed/reviewed bug records：6 条已由上游修复，其余 14 条由已提交 patch 或 patch series 覆盖，但尚未记为 upstream merged。
- btrfs `reserve_chunk_space()` 修复已提交 v2，并获得 Reviewed-by；`btrfs_init_new_device()` sprout 回滚问题已提交 3-patch series。
- 2026-07-14 修复 XFS 摘要收敛后全量测试结果为 `110 passed`。
- Linux v6.14 XFS 原始 manifest 记录 50 轮未收敛；根因已定位为条件映射重复加括号，修复后 4 轮收敛且 69 条候选完全不变。诊断见 `outputs/linux-v6.14-xfs-convergence-check/xfs_convergence_report.md`。
- XFS 仍有 1 个独立的 unresolved indirect call：`xfs_getfsmap` 中的函数指针 `fn`；它不影响摘要收敛，但需要作为保守边界披露。
- 独立 benchmark 尚未建立。现有 30 条 ext4 v6.8 pilot 是开发集，不是 gold test set。

最重要的安全线：

1. 不要把 `linux-sources/` 推到 GitHub。
2. 不要把 DeepSeek/LLM verdict 当成 gold label，只能作为 triage evidence。
3. 不要压掉已知应该保留的 ext4 pilot 候选：`candidate_65d848d5f1fd`、`candidate_f3e8e44a00d3`。
4. 不要执行 `git reset --hard` 或清理未确认输出目录。

## 2. Linux 6.14 源码状态

已经拉取 Linux v6.14 的四个文件系统目录，位置：

`E:\yanjiusheng\阅读论文\file_system\SE_EOD\linux-sources\linux-v6.14-fs`

只包含：

- `fs/ext4`
- `fs/btrfs`
- `fs/f2fs`
- `fs/xfs`

来源 manifest：

`E:\yanjiusheng\阅读论文\file_system\SE_EOD\linux-sources\linux-v6.14-fs\SOURCE_MANIFEST.json`

基线信息：

| 字段 | 值 |
|---|---|
| Linux tag | `v6.14` |
| Commit | `38fec10eb60d687e30c8c6b5420d86e8149f7557` |
| Source | `https://codeload.github.com/torvalds/linux/tar.gz/refs/tags/v6.14` |
| Extracted at | `2026-07-13` |
| Archive retained | `false` |

`.gitignore` 已经包含 `/linux-sources/`，但提交前仍必须检查 `git status --short`，确认没有 Linux 源码被 staged。

## 3. Linux 6.14 检查脚本

新增脚本：

`E:\yanjiusheng\阅读论文\file_system\SE_EOD\scripts\check_linux_v6_14_filesystems.py`

对应测试：

`E:\yanjiusheng\阅读论文\file_system\SE_EOD\tests\test_linux_v6_14_checker.py`

脚本能力：

- 默认检查 `ext4`、`btrfs`、`f2fs`、`xfs`
- 开启 CFG 和 interprocedural analysis
- 输出 error paths、候选、ranked evidence、function summaries
- 为每个文件系统生成 `llm_review_tasks.jsonl`
- 合并生成根目录 `llm_review_tasks.jsonl`
- 可选 `--run-deepseek`
- 支持 `--filesystem`、`--min-evidence-score`、`--deepseek-limit`

基础运行命令：

```powershell
cd "E:\yanjiusheng\阅读论文\file_system\SE_EOD"

python scripts/check_linux_v6_14_filesystems.py `
  --source linux-sources/linux-v6.14-fs `
  --output-root outputs/linux-v6.14-bug-check
```

只跑某个文件系统：

```powershell
python scripts/check_linux_v6_14_filesystems.py `
  --source linux-sources/linux-v6.14-fs `
  --output-root outputs/linux-v6.14-bug-check `
  --filesystem ext4
```

## 4. 已完成的 Linux 6.14 检查结果

输出根目录：

`E:\yanjiusheng\阅读论文\file_system\SE_EOD\outputs\linux-v6.14-bug-check`

关键文件：

- `check_manifest.json`
- `llm_review_tasks.jsonl`
- `ext4/llm_review_tasks.jsonl`
- `btrfs/llm_review_tasks.jsonl`
- `f2fs/llm_review_tasks.jsonl`
- `xfs/llm_review_tasks.jsonl`

合并后的 LLM 任务：

```text
manifest=E:\yanjiusheng\阅读论文\file_system\SE_EOD\outputs\linux-v6.14-bug-check\check_manifest.json
llm_tasks=520
llm_input=E:\yanjiusheng\阅读论文\file_system\SE_EOD\outputs\linux-v6.14-bug-check\llm_review_tasks.jsonl
```

每个文件系统统计：

| FS | Error paths | Candidates/Tasks | CFG functions | Summary iterations/converged | Truncated | Unresolved indirect calls |
|---|---:|---:|---:|---|---:|---:|
| ext4 | 2214 | 30 | 818 | 4 / true | 0 | 0 |
| btrfs | 5026 | 366 | 1843 | 5 / true | 0 | 0 |
| f2fs | 1614 | 55 | 677 | 3 / true | 0 | 0 |
| xfs | 2023 | 69 | 869 | 50 / false（原始）；4 / true（修复后） | 0 | 1 |

XFS 不收敛已确认不是调用图深度或 SCC 发散，而是 `_map_condition_to_caller()` 每轮为参数增加括号，导致条件字符串和 effect identity 持续变化。修复后完整 XFS pipeline 在 4 轮收敛，69 个 ranked candidate 行完全一致，运行时间由 27.898 秒降至 15.640 秒。

优先级分布：

| Priority | Count |
|---|---:|
| P1 | 34 |
| P2 | 402 |
| P3 | 84 |

证据等级：

| Evidence | Count |
|---|---:|
| E2 protocol-supported | 498 |
| E0 static-only | 22 |

按文件系统的 severity：

| FS | P1 | P2 | P3 |
|---|---:|---:|---:|
| ext4 | 20 | 10 | 0 |
| btrfs | 9 | 324 | 33 |
| f2fs | 0 | 32 | 23 |
| xfs | 5 | 36 | 28 |

PowerShell 读取中文 review question 时要用 UTF-8：

```powershell
Get-Content -Encoding UTF8 outputs/linux-v6.14-bug-check\ext4\llm_review_tasks.jsonl -TotalCount 1
```

## 5. 历史记录：ext4、XFS、F2FS 的 DeepSeek 命令

本节任务已经完成，仅保留用于复现当时的执行方式。不要重复调用模型或把这些 verdict 当作 gold label。三者合计任务数是 154。

运行前设置 API key：

```powershell
cd "E:\yanjiusheng\阅读论文\file_system\SE_EOD"
$env:DEEPSEEK_API_KEY="你的 DeepSeek API Key"
```

执行：

```powershell
@'
from pathlib import Path
from src.llm_task_builder import (
    run_deepseek_review,
    extract_deepseek_true_candidates,
)

root = Path("outputs/linux-v6.14-bug-check")

for filesystem in ("ext4", "xfs", "f2fs"):
    output = root / filesystem
    print(f"\n=== Reviewing {filesystem} ===")

    stats = run_deepseek_review(
        output / "llm_review_tasks.jsonl",
        output / "deepseek_reviews.jsonl",
    )
    print(stats)

    result = extract_deepseek_true_candidates(
        output / "deepseek_reviews.jsonl",
        output / "deepseek_true_candidates.jsonl",
    )
    print(result)
'@ | python -
```

预期输出文件：

- `outputs/linux-v6.14-bug-check/ext4/deepseek_reviews.jsonl`
- `outputs/linux-v6.14-bug-check/ext4/deepseek_true_candidates.jsonl`
- `outputs/linux-v6.14-bug-check/xfs/deepseek_reviews.jsonl`
- `outputs/linux-v6.14-bug-check/xfs/deepseek_true_candidates.jsonl`
- `outputs/linux-v6.14-bug-check/f2fs/deepseek_reviews.jsonl`
- `outputs/linux-v6.14-bug-check/f2fs/deepseek_true_candidates.jsonl`

如果 DeepSeek 中断，不要覆盖已完成 reviews。应使用已有函数的 `start_index` 和 `limit` 分段续跑，或先备份旧 `deepseek_reviews.jsonl`。

## 6. 历史记录：DeepSeek 完成后的核验步骤

以下步骤已经完成，仅作为审计流程记录：

1. 统计每个 `deepseek_reviews.jsonl` 的成功数、失败数、解析失败数。
2. 检查 review task id 是否和输入任务一一对应。
3. 统计 verdict 分布。
4. 读取 `deepseek_true_candidates.jsonl`，筛出 LLM 认为可能是真 bug 的候选。
5. 对每个 true candidate 回到 Linux 6.14 源码看上下文，不直接相信 LLM。
6. 生成 `ext4/xfs/f2fs` triage report，列出 candidate id、函数、资源、错误路径、LLM verdict、人工判断。

建议生成的报告文件：

`outputs/linux-v6.14-bug-check/reports/ext4_xfs_f2fs_deepseek_triage.md`

## 7. 测试状态

2026-07-14 在当前工作树执行全量测试：

```text
110 passed in 0.45s
```

接手后最小验证命令：

```powershell
cd "E:\yanjiusheng\阅读论文\file_system\SE_EOD"
python -m pytest -q
python -m pytest -q tests/test_linux_v6_14_checker.py
```

## 8. Git 和 GitHub 状态

当前 SE_EOD 仓库已经完成本轮主分支同步：

```text
branch: main
remote: https://github.com/yghikun/SE_EOD.git
HEAD/origin-main: fb24038 验证bug
status: main 与 origin/main 对齐；工作树存在 `outputs/confirmed_bugs.md` 的未提交状态更新，禁止覆盖
```

本轮已进入 `main` 并推送到 GitHub 的关键提交：

- `156c461`：`Update handoff and confirmed bug status`
- `6bc316b`：`Add Linux 6.14 filesystem checker`
- `28c58df`：`Add Linux 6.14 bug-check outputs`
- `fb24038`：`验证bug`

对应的临时 PR：

```text
PR:    https://github.com/yghikun/SE_EOD/pull/1
title: [codex] Update handoff and confirmed bug status
state: MERGED
mergedAt: 2026-07-13T07:17:27Z
```

PR 页面不能从 GitHub 历史中真正删除；它已经是 `MERGED` 状态。为避免后续误用，已删除对应的远端分支和本地临时分支：

```text
deleted remote branch: origin/codex/update-handoff-confirmed-bugs
deleted local branch:  codex/update-handoff-confirmed-bugs
```

本轮重要文件已经纳入 GitHub：

- `PROJECT_HANDOFF.md`
- `outputs/confirmed_bugs.md`
- `scripts/check_linux_v6_14_filesystems.py`
- `tests/test_linux_v6_14_checker.py`
- `outputs/linux-v6.14-bug-check/`

注意：`outputs/linux-v6.14-bug-check/` 已作为本轮 artifact 上传，目录约 68 MB，单文件未超过 GitHub 100 MB 限制。`linux-sources/` 仍然没有上传，也不应上传。

后续提交前仍需检查：

```powershell
git status --short
git diff --stat
git diff --cached --stat
```

仍然不要提交：

- `linux-sources/`
- `E:\kernel-work\...` 外部 Linux patch 工作树
- 邮箱授权码、API key、SMTP 密码

## 9. 论文路线图当前判断

核心方法创新：已经工程实现到可跑 Linux 6.14 的程度。

论文还没完全闭环的部分：

1. 当前只有 30 条 ext4 v6.8 开发 pilot；尚无独立、冻结、双 reviewer 的 ground-truth benchmark，这是正式投稿的首要阻塞项。
2. ext4/XFS/F2FS 的 154 条候选已经完成 DeepSeek/人工复核并沉淀到 `outputs/confirmed_bugs.md`；btrfs 366 条尚未完成同等粒度审计，应先聚类并优先处理 P1/高分/新候选族。
3. Linux v6.14 XFS 摘要不收敛已修复并验证候选稳定；剩余 `xfs_getfsmap::fn` 间接调用是需要披露的保守边界。
4. 已提交到内核邮件列表的 patch 仍只能标为 `submitted / under review`，不能写成 upstream accepted；只有维护者 tree 或 mainline 出现对应 commit 后才能改状态。
5. 正式 Recall/F1、B0--Full 消融、外部 baseline、依赖锁定、CI 和论文表格生成仍需按 `PAPER_ROADMAP.md` 收尾。

## 10. 接手优先级

P0：扩展并冻结独立 benchmark：四文件系统 300--500 条样本、至少 100 个独立正例、dev/validation/test 隔离、双 reviewer、Cohen's kappa 和 adjudication。

已完成：XFS 函数摘要在 4 轮收敛，69 个候选 ID 和 ranked rows 与修复前完全一致；后续只需将该修复纳入统一三版本最终重跑。

P0：将 pilot 评估器升级为论文级评估入口，补 Recall、F1、分组指标、bootstrap 置信区间、CSV/JSON/Markdown/LaTeX 输出；随后运行 B0--Full 和至少一个外部工具 baseline。

P1：把 `outputs/confirmed_bugs.md` 整理为论文表 7 的 CSV/JSON，并将 `/root/bug_submit/...` 替换为 lore URL 或仓库内公开材料。

P1：对 btrfs 366 条候选先按函数、资源和路径族聚类，再优先人工复核 P1、高分和新候选族；LLM 仅可辅助排序。

并行维护：继续跟踪 btrfs、ext4、XFS、F2FS 已提交 patch 的 mailing list / patchwork 回复；维护者要求调整时只沿对应线程发 v2/v3。

## 11. 最小恢复命令

新的接手者只要从这里开始：

```powershell
cd "E:\yanjiusheng\阅读论文\file_system\SE_EOD"

Get-Content -Encoding UTF8 PROJECT_HANDOFF.md
Get-Content -Encoding UTF8 outputs/linux-v6.14-bug-check\check_manifest.json -TotalCount 40

git status --short
python -m pytest -q
```

然后优先查看第 13 节当前状态与 `PAPER_ROADMAP.md` 的“2026-07-14 当前执行顺序”；第 5、6、12 节是历史执行记录，不要重复跑已完成的 ext4/XFS/F2FS 模型任务。

---

## 12. 2026-07-13 历史记录：人工复核与 patch 提交状态

本节保留 2026-07-13 的执行现场。凡与第 1、9、10、13 节冲突的状态，以 2026-07-14 当前状态为准。ext4、XFS、F2FS 的 154 条候选已经完成完整性核验和源码人工复核：

| FS | 候选数 | DeepSeek 判 true | 人工复核真候选 | 真 bug cluster |
|---|---:|---:|---:|---:|
| ext4 | 30 | 26 | 20 | 4 |
| XFS | 69 | 7 | 5 | 3 |
| F2FS | 55 | 19 | 18 | 4 |
| 合计 | 154 | 52 | 43 | 11 |

已同步记录到：

- `outputs/confirmed_bugs.md`

注意：本节当时只更新到 confirmed bug #16；当前 `outputs/confirmed_bugs.md` 已扩展到 #20。

### 12.1 最新 mainline 对照基线

最新版对照使用的是 Torvalds mainline HEAD：

```text
a13c140cc289c0b7b3770bce5b3ad42ab35074aa
```

Windows 上完整 Linux checkout 会因为大小写冲突导致 netfilter 等文件显示 modified；后续做内核 patch 时要用 sparse checkout，避开大小写冲突。

已经使用的干净 sparse 工作树：

```text
E:\kernel-work\linux-f2fs-ifolio-sparse
```

该工作树通过以下方式建立：

```powershell
cd E:\kernel-work
git clone --no-checkout --shared .\linux-f2fs-ifolio-clean linux-f2fs-ifolio-sparse
cd linux-f2fs-ifolio-sparse
git sparse-checkout init --cone
git sparse-checkout set fs/f2fs scripts MAINTAINERS
git checkout master
```

### 12.2 已提交 patch，禁止重复提交

这些已经发到对应 mailing list。不要重复投同一个 patch；后续只能基于维护者回复发 v2/v3 或 reply。

#### btrfs：已提交

- `__add_reloc_root()`
  - Subject: `[PATCH v2] btrfs: free mapping node on duplicate reloc root insert`
  - 状态：v2 submitted，Qu Wenruo 已回复；后续只在该线程继续修改或回复。
- `btrfs_recover_relocation()`
  - Subject: `[PATCH] btrfs: drop recovered reloc root refs on recovery failure`
  - From: Guanghui Yang
  - 状态：patch submitted；本地 QEMU/fault-injection 已验证，但尚未记录为 upstream merged。

#### btrfs：当时已确认、随后已提交

- `reserve_chunk_space()`
  - Bug：zoned `btrfs_zoned_activate_one_bg()` 成功返回 `1` 后，`ret` 未归零，导致后续 `if (!ret)` 跳过 `btrfs_block_rsv_add()` 和 `trans->chunk_bytes_reserved` 更新。
  - 不是 `bg` 生命周期 bug，也不是缺 `btrfs_put_block_group()`；`btrfs_create_chunk()` 成功后 block group 已进入 btrfs / transaction 管理。
  - 复现：host-managed zoned `null_blk`，`zone_size=256MiB`，`zone_max_active=8`；修复前日志显示 `zoned_activate ret=1` 且 `skip chunk_block_rsv_add`，归零后 `chunk_reserved=393216`。
  - 修复方向：`ret = btrfs_zoned_activate_one_bg(...); if (ret < 0) return; ret = 0;`，或使用单独局部变量保存 zoned activation 返回值。
  - 当前状态：Linux 6.14 本地复现确认；修复已提交 v2，lore Message-ID `tencent_7498732A1B9E13C552CFF1101E377288C407@qq.com`，并获得 Johannes Thumshirn 的 Reviewed-by；尚未记录为 upstream merged。

#### ext4：已提交

- `ext4_fc_replay_add_range()` / `ext4_fc_replay_del_range()`
  - Subject: `ext4: propagate errors from fast commit range replay`
  - 状态：patch submitted，latest mainline 在 2026-07-13 检查时仍未合入。
- `ext4_init_orphan_info()`
  - Subject: `ext4: fix buffer_head leak in ext4_init_orphan_info`
  - 状态：patch submitted，latest mainline `a13c140cc289...` 仍是旧的 `for (i--; i >= 0; i--)` cleanup 形态。
- `ext4_expand_extra_isize_ea()`
  - Subject: `ext4: clear error before retrying inode xattr space fallback`
  - 状态：patch submitted / under review。

#### XFS：已提交

- `xfs_rtginode_ensure()`
  - Subject: `[PATCH] xfs: propagate errors from xfs_rtginode_load`
  - To: `linux-xfs@vger.kernel.org`
  - 维护者/Reviewer：Carlos Maiolino、Darrick J. Wong、Christoph Hellwig
  - Fixes: `aa897e0bed0f ("xfs: support creating per-RTG files in growfs")`
  - 状态：patch submitted，latest mainline `a13c140cc289...` 检查时仍未合入。

#### F2FS：已提交

1. `f2fs_get_new_data_folio()`

   - v1 Message-ID: `<20260713055959.1865-1-3497809730@qq.com>`
   - v2 Message-ID: `<20260713061601.712-1-3497809730@qq.com>`
   - v2 Subject: `[PATCH v2] f2fs: fix ifolio leak in f2fs_get_new_data_folio`
   - 状态：v2 submitted。v1 已被 v2 supersede；后续回复应基于 v2 线程。

2. `find_in_level()`

   - Message-ID: `<20260713063633.555-1-3497809730@qq.com>`
   - Subject: `[PATCH] f2fs: fix dentry folio leak in find_in_level`
   - 状态：patch submitted。

3. `f2fs_move_inline_dirents()`

   - Message-ID: `<20260713064043.1837-1-3497809730@qq.com>`
   - Subject: `[PATCH] f2fs: fix ifolio leak in f2fs_move_inline_dirents`
   - 状态：patch submitted。

F2FS 收件人使用：

```text
To: Jaegeuk Kim <jaegeuk@kernel.org>
Cc: Chao Yu <chao@kernel.org>
Cc: linux-f2fs-devel@lists.sourceforge.net
Cc: linux-kernel@vger.kernel.org
```

不要把 F2FS patch 发到 `linux-xfs@vger.kernel.org` 或 `linux-btrfs@vger.kernel.org`。

### 12.3 F2FS patch 工作树分支

外部 Linux sparse 工作树中用过的分支：

```text
E:\kernel-work\linux-f2fs-ifolio-sparse
```

- `f2fs-ifolio-leak-fix`
  - commit: `a0c8c0e255c92ff3ebb9d188d6dd5266330ac7cc`
  - patch dir: `patches-v2/`
  - 已发 v2。
- `f2fs-find-in-level-folio-leak`
  - commit: `dd9b477726b2f52bf495f436e49baecfa0bcdaf3`
  - patch dir: `patches-find/`
  - 已发送。
- `f2fs-move-inline-dirents-ifolio-leak`
  - commit: `38c593752c0f45eea652d8adaa6a5f46ccdf799a`
  - patch dir: `patches-inline/`
  - 已发送。

后续如果要发 v2/v3，先切到对应分支，`git commit --amend`，再用 `git format-patch -1 -v2` 或 `-v3`。需要回复旧线程时必须加 `--in-reply-to <Message-ID>`。

### 12.4 当前不应再当作未提交项的 bug

下面这些已经提交或已由上游修复，不要再作为“待提交新 bug”处理：

- ext4 `ext4_ext_shift_extents()`：latest mainline 已修。
- ext4 `ext4_fc_replay_inode()`：latest mainline 已修；已有 upstream commit `ec0a7500d8ea`。
- ext4 `ext4_dx_add_entry()`：latest mainline 已修。
- XFS `xfs_qm_quotacheck_dqadjust()`：latest mainline 已修。
- XFS `xfs_rtcopy_summary()`：latest mainline 已修。
- F2FS `f2fs_rename()` with `RENAME_WHITEOUT`：latest mainline 已修。
- btrfs `__add_reloc_root()`：已提交 v2，且已有 Qu Wenruo 回复。
- btrfs `btrfs_recover_relocation()`：已提交 patch。
- XFS `xfs_rtginode_ensure()`：已提交 patch。
- F2FS `f2fs_get_new_data_folio()`：已提交 v2。
- F2FS `find_in_level()`：已提交。
- F2FS `f2fs_move_inline_dirents()`：已提交。

### 12.5 下一步优先事项

以下是 2026-07-13 当时的优先事项，已由第 10、13 节取代。状态修正如下：

1. btrfs `reserve_chunk_space()` 修复已经提交 v2 并获得 Reviewed-by，不再是“待提交”事项。
2. 跟踪 btrfs 两个已提交 patch 的回复；`__add_reloc_root()` 后续修改必须基于已有 v2 线程。
3. 跟踪 F2FS 三封 patch 在 `linux-f2fs-devel` / patchwork 上的回复。
4. 跟踪 XFS `xfs_rtginode_ensure()` 回复，尤其是 Darrick/Christoph 是否要求调整 commit message 或 Fixes tag。
5. 跟踪 ext4 已提交 patch 的 review/合入状态。
6. 不要把 submitted patch 写成 upstream accepted；只有维护者 tree 或 mainline 出现对应 commit 后才能改状态。

1. 把 `outputs/confirmed_bugs.md` 中所有外部路径、Message-ID、状态整理成论文表格可用格式。
2. 如果需要继续挖 btrfs，先对 366 条候选聚类，再做优先级人工 triage；不要把 DeepSeek verdict 当作标签。
3. 运行全量测试：

```powershell
cd "E:\yanjiusheng\阅读论文\file_system\SE_EOD"
python -m pytest -q
```

### 12.6 当前仓库状态提醒

本轮 SE_EOD 仓库更新已经合并到 `main` 并推送到 GitHub。最终主分支包含：

- `PROJECT_HANDOFF.md`：交接补充。
- `outputs/confirmed_bugs.md`：当前 confirmed/reviewed bug #1--#20、已修复项、已提交 patch 状态。
- `outputs/linux-v6.14-bug-check/`：Linux 6.14 分析输出 artifact。
- `scripts/check_linux_v6_14_filesystems.py`
- `tests/test_linux_v6_14_checker.py`

2026-07-14 最终核验过的全量测试：

```text
python -m pytest -q
110 passed in 0.45s
```

最终 GitHub 状态：

```text
artifact push range: ab5b3f3..28c58df
PR #1: MERGED
remote branch codex/update-handoff-confirmed-bugs: deleted
local branch codex/update-handoff-confirmed-bugs: deleted
```

后续提交 SE_EOD 仓库前仍必须检查：

```powershell
git status --short
git diff --stat
git diff --cached --stat
```

仍然不要 stage 或提交：

- `linux-sources/`
- `E:\kernel-work\...` 外部 Linux patch 工作树
- 邮箱授权码、API key、SMTP 密码

---

## 13. 2026-07-14 当前权威状态

### 13.1 投稿阻塞项

| 顺序 | 阻塞项 | 当前证据 | 完成标准 |
|---:|---|---|---|
| 1 | 独立 benchmark | 仅有 30 条 ext4 v6.8 开发 pilot | 四文件系统 300--500 条、至少 100 正例、冻结 test split、双 reviewer、kappa、adjudication |
| 2 | 论文级指标 | 当前 evaluator 主要输出 precision 与 Precision@K | Recall、F1、分组指标、置信区间、人工成本和论文表格格式 |
| 3 | Baseline/消融 | 已有 ext4 开发集局部消融 | 相同 benchmark 上 B0--Full、pattern baseline、至少一个外部工具 baseline |
| 4 | Artifact | 有 runner/manifest，无打包、CI 和开源元数据 | 统一命令、稳定 manifest schema、依赖锁、CI、LICENSE、CITATION、干净环境复现 |

已解除的阻塞项：XFS 摘要条件规范化已修复，4 轮收敛，候选稳定；`xfs_getfsmap::fn` 作为单独的保守间接调用边界保留。

### 13.2 Bug 与 upstream 状态

- `outputs/confirmed_bugs.md` 共 20 条记录。
- 6 条已在上游修复；其余 14 条由已提交 patch 或 patch series 覆盖。
- `reserve_chunk_space()`：v2 submitted，Reviewed-by received，未记录为 upstream merged。
- `btrfs_init_new_device()`：3-patch sprout rollback series submitted，未记录为 upstream merged。
- 所有状态更新必须带最后核验日期、公开 lore/commit 链接和 E0--E5 证据等级。
- 继续跟踪邮件列表是并行维护任务，不能替代 benchmark 和正式评估主线。

### 13.3 工作树与测试

```text
branch: main
HEAD: fb24038
origin/main: fb24038
tests: 110 passed in 0.45s
dirty: 包含用户的 outputs/confirmed_bugs.md 状态更新，以及本轮 XFS 收敛修复和文档；禁止覆盖用户修改
```

接手后的第一组命令：

```powershell
cd "E:\yanjiusheng\阅读论文\file_system\SE_EOD"
git status --short
python -m pytest -q
Get-Content -Encoding UTF8 PAPER_ROADMAP.md -TotalCount 130
```
