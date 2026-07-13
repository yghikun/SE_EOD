# SE-EOD 项目交接文档

更新时间：2026-07-13  
工作目录：`E:\yanjiusheng\阅读论文\file_system\SE_EOD`

## 1. 当前一句话状态

SE-EOD 当前已经完成论文核心方法的主要工程落地：CFG 路径敏感资源传播、跨函数摘要、函数指针/间接调用处理、retry/backedge 语义、`PTR_ERR` 路径事实、CFG 诊断、候选证据排序和 LLM review task 生成都已经接入主流程。

现在的工作重点已经从“核心方法还没落地”转为“用 Linux 6.14 的 ext4/xfs/f2fs/btrfs 做系统性检查，并让 LLM/DeepSeek 对候选做二次验证，再沉淀论文表格和人工审计结果”。

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

| FS | Error paths | Candidates/Tasks | CFG functions | Truncated | Unresolved indirect calls |
|---|---:|---:|---:|---:|---:|
| ext4 | 2214 | 30 | 818 | 0 | 0 |
| btrfs | 5026 | 366 | 1843 | 0 | 0 |
| f2fs | 1614 | 55 | 677 | 0 | 0 |
| xfs | 2023 | 69 | 869 | 0 | 1 |

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

## 5. 先验证 ext4、xfs、f2fs 的 DeepSeek 命令

用户当前想先排除 btrfs，只把 `ext4`、`xfs`、`f2fs` 交给 DeepSeek/LLM 验证。三者合计任务数是 154。

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

## 6. DeepSeek 完成后的下一步

完成 ext4/xfs/f2fs 验证后，接手者应该做：

1. 统计每个 `deepseek_reviews.jsonl` 的成功数、失败数、解析失败数。
2. 检查 review task id 是否和输入任务一一对应。
3. 统计 verdict 分布。
4. 读取 `deepseek_true_candidates.jsonl`，筛出 LLM 认为可能是真 bug 的候选。
5. 对每个 true candidate 回到 Linux 6.14 源码看上下文，不直接相信 LLM。
6. 生成 `ext4/xfs/f2fs` triage report，列出 candidate id、函数、资源、错误路径、LLM verdict、人工判断。

建议生成的报告文件：

`outputs/linux-v6.14-bug-check/reports/ext4_xfs_f2fs_deepseek_triage.md`

## 7. 测试状态

核心方法相关测试此前全量通过：

```text
102 passed
```

Linux 6.14 检查脚本新增测试通过：

```text
2 passed
```

接手后最小验证命令：

```powershell
cd "E:\yanjiusheng\阅读论文\file_system\SE_EOD"
python -m pytest -q
python -m pytest -q tests/test_linux_v6_14_checker.py
```

## 8. Git 和 GitHub 状态

当前本地 `main` 曾经领先远端一个提交：

```text
ab5b3f3 cfg测试
```

之前审计确认该提交没有包含 `linux-sources/`。

当前仍有未跟踪文件：

```text
?? outputs/linux-v6.14-bug-check-smoke/
?? outputs/linux-v6.14-bug-check/
?? scripts/check_linux_v6_14_filesystems.py
?? tests/test_linux_v6_14_checker.py
```

GitHub push 失败原因：

```text
remote: Permission to yghikun/SE_EOD.git denied to yghikun.
HTTP 403
```

原因是 `GITHUB_TOKEN` 环境变量覆盖了认证，但该 token 没有目标仓库写权限。GitHub CLI 已经可用，但要么清除 `GITHUB_TOKEN` 后重新登录，要么换有写权限的 token。

检查认证：

```powershell
gh auth status
```

当前用户之前看到：

```text
Logged in to github.com account yghikun (GITHUB_TOKEN)
Git operations protocol: https
```

如需重新登录，先在当前 PowerShell 会话清除 token：

```powershell
Remove-Item Env:GITHUB_TOKEN
gh auth login
```

注意：不要 force push，不要 stage `linux-sources/`，不要把大型输出目录一股脑推上去。建议只提交代码、测试、必要文档；大输出结果除非明确要做 artifact，否则保持本地。

提交前推荐检查：

```powershell
git status --short
git diff --stat
git diff --cached --stat
```

只 stage 当前实现相关文件的示例：

```powershell
git add scripts/check_linux_v6_14_filesystems.py tests/test_linux_v6_14_checker.py PROJECT_HANDOFF.md
```

## 9. 论文路线图当前判断

核心方法创新：已经工程实现到可跑 Linux 6.14 的程度。

论文还没完全闭环的部分：

1. DeepSeek/LLM triage 结果还没有回收整理。
2. ext4/xfs/f2fs/btrfs 的人工审计还没形成正式表格。
3. LLM verdict 需要人工确认后才能转成论文中的 confirmed finding。
4. 正式 benchmark、Precision/Recall/F1、消融和外部 baseline 仍需按 `PAPER_ROADMAP.md` 收尾。
5. GitHub 推送还没完成，且必须排除 `linux-sources/` 和不必要的大输出。

## 10. 接手优先级

P0：跑 DeepSeek 验证 ext4、xfs、f2fs，拿到 `deepseek_reviews.jsonl` 和 `deepseek_true_candidates.jsonl`。

P0：写 triage report，区分 `likely true bug`、`needs manual audit`、`false positive`。

P1：决定哪些输出应该进入论文 artifact，哪些只保留本地。

P1：整理提交范围，提交脚本、测试、交接文档，不提交 Linux 源码。

P2：恢复 GitHub 写权限后 push，但不要 force push。

## 11. 最小恢复命令

新的接手者只要从这里开始：

```powershell
cd "E:\yanjiusheng\阅读论文\file_system\SE_EOD"

Get-Content -Encoding UTF8 PROJECT_HANDOFF.md
Get-Content -Encoding UTF8 outputs/linux-v6.14-bug-check\check_manifest.json -TotalCount 40

python -m pytest -q tests/test_linux_v6_14_checker.py
```

然后继续跑第 5 节的 DeepSeek 命令。

---

## 12. 2026-07-13 最新补充：ext4 / XFS / F2FS 人工复核与 patch 提交状态

本节覆盖前面较早的“DeepSeek 完成后下一步”描述。ext4、XFS、F2FS 的 154 条候选已经完成完整性核验和源码人工复核：

| FS | 候选数 | DeepSeek 判 true | 人工复核真候选 | 真 bug cluster |
|---|---:|---:|---:|---:|
| ext4 | 30 | 26 | 20 | 4 |
| XFS | 69 | 7 | 5 | 3 |
| F2FS | 55 | 19 | 18 | 4 |
| 合计 | 154 | 52 | 43 | 11 |

已同步记录到：

- `outputs/confirmed_bugs.md`

注意：`outputs/confirmed_bugs.md` 已新增 confirmed bug #14--#16，并修正了 XFS `xfs_rtginode_ensure()` 和 ext4 `ext4_init_orphan_info()` 的提交/未合入状态。

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
- XFS `xfs_rtginode_ensure()`：已提交 patch。
- F2FS `f2fs_get_new_data_folio()`：已提交 v2。
- F2FS `find_in_level()`：已提交。
- F2FS `f2fs_move_inline_dirents()`：已提交。

### 12.5 下一步优先事项

P0：

1. 跟踪 F2FS 三封 patch 在 `linux-f2fs-devel` / patchwork 上的回复。
2. 跟踪 XFS `xfs_rtginode_ensure()` 回复，尤其是 Darrick/Christoph 是否要求调整 commit message 或 Fixes tag。
3. 跟踪 ext4 已提交 patch 的 review/合入状态。
4. 不要把 submitted patch 写成 upstream accepted；只有维护者 tree 或 mainline 出现对应 commit 后才能改状态。

P1：

1. 把 `outputs/confirmed_bugs.md` 中所有外部路径、Message-ID、状态整理成论文表格可用格式。
2. 如果需要继续挖 btrfs，先从 `outputs/linux-v6.14-bug-check/btrfs/` 的 366 条候选做 DeepSeek/人工 triage；不要把 btrfs 和这轮 F2FS patch 混在一起。
3. 运行最小测试：

```powershell
cd "E:\yanjiusheng\阅读论文\file_system\SE_EOD"
python -m pytest -q tests/test_linux_v6_14_checker.py
```

### 12.6 当前仓库状态提醒

当前 SE_EOD 工作树有这些本轮相关改动：

- `PROJECT_HANDOFF.md`：本交接补充。
- `outputs/confirmed_bugs.md`：新增/修正 confirmed bug #13--#16 和 patch 提交状态。
- `outputs/linux-v6.14-bug-check/`：本地分析输出，是否纳入 git 需要单独决定。
- `scripts/check_linux_v6_14_filesystems.py`
- `tests/test_linux_v6_14_checker.py`

提交 SE_EOD 仓库前必须检查：

```powershell
git status --short
git diff --stat
git diff --cached --stat
```

仍然不要 stage 或提交：

- `linux-sources/`
- `E:\kernel-work\...` 外部 Linux patch 工作树
- 邮箱授权码、API key、SMTP 密码
