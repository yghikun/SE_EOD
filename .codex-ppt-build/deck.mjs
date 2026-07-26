import fs from "node:fs/promises";
import { Presentation, PresentationFile, layers, shape, table, text } from "@oai/artifact-tool";
import { buildSlide01 } from "./vendor/slide-01.mjs";
import { buildSlide11 } from "./vendor/slide-11.mjs";
import { buildSlide13 } from "./vendor/slide-13.mjs";
import { buildSlide15 } from "./vendor/slide-15.mjs";
import { buildSlide16 } from "./vendor/slide-16.mjs";
import { buildSlide17 } from "./vendor/slide-17.mjs";
import { buildSlide18 } from "./vendor/slide-18.mjs";
import { buildSlide19 } from "./vendor/slide-19.mjs";
import { buildSlide26 } from "./vendor/slide-26.mjs";

const ROOT = "E:/yanjiusheng/阅读论文/file_system/SE_EOD";
const OUT = `${ROOT}/SE_EOD项目架构与Bug案例.pptx`;
const PREVIEW_DIR = `${ROOT}/.codex-ppt-build/previews`;
const FONT = "Microsoft YaHei";
const INK = "#000000";
const PANEL = "#F2F2F2";
const RULE = "#B8BCC4";
const BLUE = "#3D8DFF";
const BLUE_LIGHT = "#6DCBF4";
const RED = "#D94841";
const GREEN = "#18864B";

function rich(value, size = 21.33, { bold = false, color = INK, mono = false } = {}) {
  return {
    runs: [{
      run: value,
      textStyle: {
        fontSize: `${size}px`,
        typeface: mono ? "Consolas" : FONT,
        color,
        bold,
      },
    }],
    paragraphStyle: { lineSpacingPercent: 108000 },
  };
}

function topic(title, body, titleSize = 24, bodySize = 19) {
  return {
    titleHere: rich(title, titleSize, { bold: true }),
    titleGoesHere: rich(title, titleSize, { bold: true }),
    loremIpsumDolorSitAmetConsecteturAdipiscing: rich(body, bodySize),
    quamUtMassaLuctusCursusNullamPharetra: rich("", bodySize),
  };
}

function footer(n) {
  return rich(String(n).padStart(2, "0"), 13.33);
}

function setNotes(slide, presenter, sources) {
  slide.speakerNotes.textFrame.setText(
    `${presenter}\n\n[Sources]\n${sources.map((s) => `- ${ROOT}/${s}`).join("\n")}`,
  );
  slide.speakerNotes.setVisible(true);
}

function titleToken(value) {
  return rich(value, 38.67, { bold: true });
}

function buildChartSlide(presentation, page) {
  const slide = presentation.slides.add();
  slide.compose(
    layers({ name: "codex-grid-custom#evaluation-chart", width: "fill", height: "fill" }, [
      text([titleToken("四个文件系统已形成可量化的残差分析基线")], {
        name: "title",
        position: { left: 41.33, top: 36.12 }, width: 1197.33, height: 74,
        style: { fontSize: "38.67px", typeface: FONT, color: INK, autoFit: "none", insets: { top: 0, right: 0, bottom: 0, left: 0 } },
      }),
      ...[
        [41.33, "9,676", "函数被分析"],
        [452.67, "6,872", "失败切片"],
        [864.28, "1,425", "最终报告"],
      ].flatMap(([left, stat, label], index) => [
        shape({ name: `metric-${index}`, geometry: "roundRect", fill: PANEL, position: { left, top: 470 }, width: 374.67, height: 150 }),
        text([rich(stat, 44, { bold: true, color: index === 0 ? BLUE : INK }), rich(label, 20)], {
          name: `metric-text-${index}`, position: { left: left + 30, top: 500, width: 315, height: 92 },
          style: { fontSize: "24px", typeface: FONT, color: INK, autoFit: "shrinkText", insets: { top: 0, right: 0, bottom: 0, left: 0 } },
        }),
      ]),
      text([footer(page)], {
        name: "footer", position: { left: 1184.18, top: 659.24 }, width: 54.48, height: 25.33,
        style: { fontSize: "13.33px", typeface: FONT, color: INK, alignment: "right", verticalAlignment: "bottom", insets: { top: 0, right: 0, bottom: 0, left: 0 } },
      }),
    ]),
    { frame: { left: 0, top: 0, width: 1280, height: 720 }, baseUnit: 1 },
  );
  slide.charts.add("bar", {
    position: { left: 52, top: 132, width: 1170, height: 300 },
    categories: ["Btrfs", "Ext4", "F2FS", "XFS"],
    series: [
      { name: "边界残差", categories: ["Btrfs", "Ext4", "F2FS", "XFS"], values: [231, 75, 37, 187], fill: BLUE },
      { name: "UNKNOWN", categories: ["Btrfs", "Ext4", "F2FS", "XFS"], values: [174, 136, 53, 117], fill: BLUE_LIGHT },
    ],
    hasLegend: true,
    legend: { position: "bottom", overlay: false, textStyle: { typeface: FONT, fontSize: "14px", color: INK } },
    dataLabels: { showValue: true, textStyle: { typeface: FONT, fontSize: "13px", color: INK } },
    chartFill: "#FFFFFF",
    chartLine: { style: "solid", width: 0, fill: "#FFFFFF" },
    plotAreaFill: { type: "none" },
    plotAreaLine: { style: "solid", width: 0, fill: "#FFFFFF" },
    xAxis: { visible: true, line: { style: "solid", width: 1, fill: RULE }, textStyle: { typeface: FONT, fontSize: "14px", color: INK } },
    yAxis: { visible: true, max: 250, majorUnit: 50, majorGridlines: { style: "solid", width: 1, fill: "#EDEDED" }, line: { style: "solid", width: 0, fill: "#FFFFFF" }, textStyle: { typeface: FONT, fontSize: "12px", color: INK } },
    barOptions: { direction: "column", grouping: "clustered", gapWidth: 80 },
  });
  return slide;
}

function buildGateTableSlide(presentation, page) {
  const slide = presentation.slides.add();
  slide.compose(
    layers({ name: "codex-grid-custom#gate-table", width: "fill", height: "fill" }, [
      text([titleToken("单测全绿，但 M37 语义回归门仍有 4 项超预算")], {
        name: "title", position: { left: 41.33, top: 36.12 }, width: 1197.33, height: 74,
        style: { fontSize: "38.67px", typeface: FONT, color: INK, autoFit: "none", insets: { top: 0, right: 0, bottom: 0, left: 0 } },
      }),
      text([rich("失败点不是新增候选或丢失 witness，而是兼容匹配过多：比较器仍依赖语义例外，稳定身份尚未完全建立。", 21.33)], {
        name: "subtitle", position: { left: 42, top: 116 }, width: 1196, height: 72,
        style: { fontSize: "21.33px", typeface: FONT, color: INK, autoFit: "none", insets: { top: 0, right: 0, bottom: 0, left: 0 } },
      }),
      table({
        name: "gate-table", rows: 5, columns: 5,
        values: [
          ["文件系统", "实际兼容匹配", "预算", "超出", "门状态"],
          ["Btrfs", "250", "179", "+71 / 1.40x", "FAIL"],
          ["Ext4", "115", "95", "+20 / 1.21x", "FAIL"],
          ["F2FS", "48", "35", "+13 / 1.37x", "FAIL"],
          ["XFS", "692", "398", "+294 / 1.74x", "FAIL"],
        ],
        columnWidths: [245, 270, 185, 260, 237],
        position: { left: 41.33, top: 218 }, width: 1197.33, height: 338,
      }),
      shape({ name: "gate-callout", geometry: "roundRect", fill: "#FDEDEC", position: { left: 41.33, top: 580 }, width: 1197.33, height: 58 }),
      text([rich("结论：当前结果可讲、可复现，但不能把 M37 描述为已通过。", 22, { bold: true, color: RED })], {
        name: "gate-callout-text", position: { left: 67, top: 594 }, width: 1140, height: 34,
        style: { fontSize: "22px", typeface: FONT, color: RED, autoFit: "none", insets: { top: 0, right: 0, bottom: 0, left: 0 } },
      }),
      text([footer(page)], {
        name: "footer", position: { left: 1184.18, top: 659.24 }, width: 54.48, height: 25.33,
        style: { fontSize: "13.33px", typeface: FONT, color: INK, alignment: "right", verticalAlignment: "bottom", insets: { top: 0, right: 0, bottom: 0, left: 0 } },
      }),
    ]),
    { frame: { left: 0, top: 0, width: 1280, height: 720 }, baseUnit: 1 },
  );
  return slide;
}

async function main() {
  await fs.mkdir(PREVIEW_DIR, { recursive: true });
  const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });

  let s = buildSlide01(presentation, {
    title: rich("SE_EOD · 项目架构复盘", 24, { bold: true, color: BLUE }),
    title2: rich("从失败路径到\n元数据残差证据", 80, { bold: true }),
    title3: rich("Linux 文件系统静态分析 · 当前实现、真实 bug 与下一步", 26),
  });
  setNotes(s, "开场强调：项目的目标不是宣称自动确认 bug，而是把失败路径上的文件系统元数据残差变成可审计证据。", ["README.md", "docs/PROJECT_ARCHITECTURE.md"]);

  s = buildSlide19(presentation, {
    title: titleToken("实现稳定，但语义回归门还没有过线"),
    body1: {
      topic: rich("当前快照", 22, { bold: true, color: BLUE }),
      loremIpsumDolorSitAmetConsecteturAdipiscing: rich("单元测试、确认缺陷账本与 M37 批量评估同时存在；三者回答的是不同问题。", 21),
    },
    stat1: rich("297 / 297", 42, { bold: true, color: GREEN }),
    stat2: rich("18", 42, { bold: true }),
    stat3: rich("4", 42, { bold: true, color: RED }),
    body2: rich("单元测试通过", 22, { bold: true }),
    body3: rich("已确认 bug 记录", 22, { bold: true }),
    body4: rich("M37 门失败项", 22, { bold: true }),
    footer1: footer(2),
  });
  setNotes(s, "测试全绿说明代码路径稳定；18 条记录是研究证据账本；M37 的 4 个失败表示语义比较仍超出兼容预算，不能混为一个健康指标。", ["outputs/confirmed_bugs.md", "outputs/residual-evaluation-batch/m37-regression-gate.json", ".github/workflows/ci.yml"]);

  s = buildSlide13(presentation, {
    title: titleToken("残差公式把“发生了什么”与“错误退出时还剩什么”分开"),
    body1: { titleGoesHere: rich("E_f · 到达失败点", 26, { bold: true, color: BLUE }), loremIpsumDolorSitAmetConsecteturAdipiscing: rich("失败发生前已经生效的结构、计数或恢复元数据效果。", 21) },
    body2: { titleGoesHere: rich("C_f · 取消与补偿", 26, { bold: true }), loremIpsumDolorSitAmetConsecteturAdipiscing: rich("错误路径上与同一对象、键和值匹配的逆向效果。", 21) },
    body3: { titleGoesHere: rich("T_f · 保护与转移", 26, { bold: true }), loremIpsumDolorSitAmetConsecteturAdipiscing: rich("事务、日志、孤儿、恢复或延期机制明确接管的效果。", 21) },
    body4: { titleGoesHere: rich("R_f · 最终残差", 26, { bold: true, color: RED }), loremIpsumDolorSitAmetConsecteturAdipiscing: rich("R_f = Normalize(E_f ⊕ C_f) − T_f；非空才进入报告。", 21) },
    footer1: footer(3),
  });
  setNotes(s, "这是整套架构的中心。状态标签只是实现格，不是论文贡献；贡献是围绕失败点计算 R_f。", ["README.md", "docs/METADATA_RESIDUAL_ARCHITECTURE.md", "PAPER_ROADMAP.md"]);

  s = buildSlide17(presentation, {
    title: titleToken("主链路分成三段：理解源码、计算残差、约束结论"),
    label1: rich("01 · 前端与控制流", 20, { bold: true, color: BLUE }),
    label2: rich("02 · 残差计算", 20, { bold: true }),
    label3: rich("03 · 证据治理", 20, { bold: true }),
    body1: topic("FunctionIR + CFG", "Tree-sitter 解析 C；函数级 CFG 保留分支、返回与调用点。", 25, 20),
    body2: topic("双向切片", "向后收集 E_f，向前收集 C_f / T_f，再做身份感知归一化。", 25, 20),
    body3: topic("报告 + Oracle + Gate", "输出 witness；人工 verdict 与跨版本比较防止语义漂移。", 25, 20),
    footer1: footer(4),
  });
  setNotes(s, "架构不是单个 detector：前端、分析核、证据治理三层缺一不可。最后一层解释了为什么项目同时保留 539 行人工 oracle 与回归门。", ["docs/PROJECT_ARCHITECTURE.md", "docs/METADATA_RESIDUAL_ARCHITECTURE.md", "outputs/candidate_review_oracle.jsonl"]);

  const moduleTokens = {
    title: titleToken("模块边界围绕“证据可追溯”组织，而不是按文件系统堆规则"),
    body1: topic("frontend/", "C AST → 中立 FunctionIR", 23, 18),
    body2: topic("cfg.py", "函数内控制流与可达性", 23, 18),
    body3: topic("metadata_scope.py", "只保留结构 / 计数 / 恢复元数据", 23, 18),
    body4: topic("failure_points.py", "定位失败调用、检查与错误出口", 23, 18),
    body5: topic("effect_extractor.py", "抽取 Root / Key / Plane / Delta", 23, 18),
    body6: topic("residual_slicer.py", "E_f / C_f / T_f 与路径约束", 23, 18),
    body7: topic("function_summary.py", "跨函数参数化与退出分区", 23, 18),
    body8: topic("harness + oracle", "批量评估、比较、审计与回归门", 23, 18),
    footer1: footer(5),
  };
  s = buildSlide16(presentation, moduleTokens);
  setNotes(s, "复杂度集中在跨函数摘要、切片和效果抽取：function_summary.py 约 4,869 行，是当前最大的维护热点。", ["src/frontend/model.py", "src/cfg.py", "src/metadata_scope.py", "src/failure_points.py", "src/effect_extractor.py", "src/residual_slicer.py", "src/function_summary.py", "src/evaluation_harness.py"]);

  s = buildSlide11(presentation, {
    title: titleToken("报告严格区分“函数边界残差”与“已确认活体 bug”"),
    body1: {
      topic: rich("结论边界", 21, { bold: true, color: BLUE }),
      loremIpsumDolorSitAmetConsecteturAdipiscing: rich("源码能证明 R_f 非空，并不自动证明 owner 仍存活、系统继续正常运行或缺陷可自然触发。", 21),
      loremIpsumDolorSitAmetConsecteturAdipiscing2: rich("因此当前主分类是 FUNCTION_BOUNDARY_RESIDUAL；LIVE_METADATA_RESIDUAL 仍保留给未来 owner-liveness 层。", 21),
    },
    body2: rich("分析器可以声称", 26, { bold: true, color: GREEN }),
    body3: rich("分析器不能越界声称", 26, { bold: true, color: RED }),
    body4: {
      detailGoesHere: rich("R_f 非空且到达错误出口", 19),
      detailGoesHere2: rich("效果属于元数据作用域", 19),
      detailGoesHere3: rich("证据来自源码或显式原语", 19),
    },
    body5: {
      detailGoesHere: rich("owner 一定继续存活", 19),
      detailGoesHere2: rich("一定造成用户可见损坏", 19),
      detailGoesHere3: rich("无需复现即可确认为 bug", 19),
    },
    footer1: footer(6),
  });
  setNotes(s, "这一页用于防止过度解读。项目文档明确指出 Candidate 只是兼容别名，不应当等同于 confirmed bug。", ["README.md", "docs/METADATA_RESIDUAL_ARCHITECTURE.md", "PAPER_ROADMAP.md"]);

  s = buildSlide11(presentation, {
    title: titleToken("Bug #7：一次失败提交让 reloc_root 引用越过错误出口"),
    body1: {
      topic: rich("btrfs_recover_relocation() · Linux 6.14", 21, { bold: true, color: BLUE }),
      loremIpsumDolorSitAmetConsecteturAdipiscing: rich("恢复循环把 reloc_root 挂到 fs_root；随后第一次事务提交失败会跳到 out_unset。", 21),
      loremIpsumDolorSitAmetConsecteturAdipiscing2: rich("局部错误清理只释放 reloc_roots 列表与 path，没有明确清空 fs_root->reloc_root。", 21),
    },
    body2: rich("fs_root->reloc_root =\nbtrfs_grab_root(reloc_root);", 21, { bold: true, mono: true, color: BLUE }),
    body3: rich("ret = btrfs_commit_transaction(trans);\nif (ret) goto out_unset;", 21, { bold: true, mono: true, color: RED }),
    body4: {
      detailGoesHere: rich("写入：relocation-root 引用", 18),
      detailGoesHere2: rich("位置：relocation.c:4213", 18, { mono: true }),
      detailGoesHere3: rich("发生在失败提交之前", 18),
    },
    body5: {
      detailGoesHere: rich("出口：out_unset → out", 18),
      detailGoesHere2: rich("位置：relocation.c:4217–4241", 18, { mono: true }),
      detailGoesHere3: rich("缺少对挂接引用的局部逆操作", 18),
    },
    footer1: footer(7),
  });
  setNotes(s, "先只讲源码路径：赋值发生在 4213，提交在 4217，失败后到 4235/4240。这里形成结构清晰的 mutation → failure → error exit。", ["linux-sources/linux-v6.14-fs/fs/btrfs/relocation.c", "outputs/confirmed_bugs.md"]);

  s = buildSlide18(presentation, {
    title: titleToken("Bug #7 的证据链从静态残差走到了故障注入确认"),
    body1: topic("E_f：建立挂接", "fs_root->reloc_root 获得一个 btrfs_grab_root() 引用；这是恢复域中的结构效果。", 24, 19),
    body2: topic("C_f / T_f：均未闭合", "out_unset 取消控制对象，但没有覆盖已挂接的 fs_root 引用；是否依赖 FS_ERROR 清理仍是关键条件。", 24, 19),
    body3: topic("R_f：引用仍在", "recover_noabort 注入中 25 个 root 保留 reloc_refs=1，且 fs_error=0；缺少 dropping reloc_root 日志。", 24, 19),
    label1: rich("源码残差", 20, { bold: true, color: BLUE }),
    label2: rich("路径条件", 20, { bold: true }),
    label3: rich("QEMU 证据", 20, { bold: true, color: GREEN }),
    footer1: footer(8),
  });
  setNotes(s, "这是最完整的案例：分析器用于定位残差，故障注入用于证明在 fs_error=0 的恢复失败中引用确实未清理。补丁已进入 btrfs for-next，但材料未声称已进 Linus mainline。", ["outputs/confirmed_bugs.md", "outputs/linux-v6.8/btrfs/recover_relocation_qemu_report.md", "linux-sources/linux-v6.14-fs/fs/btrfs/relocation.c"]);

  s = buildSlide11(presentation, {
    title: titleToken("Bug #4：重试成功，却把旧的 -ENOSPC 带到了返回值"),
    body1: {
      topic: rich("ext4_expand_extra_isize_ea()", 21, { bold: true, color: BLUE }),
      loremIpsumDolorSitAmetConsecteturAdipiscing: rich("第一次 ext4_xattr_make_inode_space() 返回 -ENOSPC，代码降低目标 extra_isize 并 goto retry。", 21),
      loremIpsumDolorSitAmetConsecteturAdipiscing2: rich("如果第二次在 inode 内找到空间，直接 goto shift 并更新 i_extra_isize；但 error 仍可能保存第一次失败值。", 21),
    },
    body2: rich("实际状态\ni_extra_isize 已更新", 25, { bold: true, color: GREEN }),
    body3: rich("返回结果\n仍返回 -ENOSPC", 25, { bold: true, color: RED }),
    body4: {
      detailGoesHere: rich("retry：目标降为 s_min_extra_isize", 18),
      detailGoesHere2: rich("shift：执行元数据移动", 18),
      detailGoesHere3: rich("line 2855：提交新 extra_isize", 18, { mono: true }),
    },
    body5: {
      detailGoesHere: rich("error 未在 retry 前清零", 18),
      detailGoesHere2: rich("cleanup：return error", 18, { mono: true }),
      detailGoesHere3: rich("结果与元数据状态发生分歧", 18),
    },
    footer1: footer(9),
  });
  setNotes(s, "这个案例不只是资源未释放，而是 outcome residual：操作状态成功、函数结果失败。账本中的复现实验显示清理 stale error 后 FS_IOC_FSSETXATTR 失败数从 802 降到 86。", ["linux-sources/linux-v6.14-fs/fs/ext4/xattr.c", "outputs/confirmed_bugs.md"]);

  s = buildSlide15(presentation, {
    title: titleToken("Btrfs sprout 失败不是一个点，而是三组状态同时需要回滚"),
    body1: {
      titleHere: rich("btrfs_init_new_device()", 27, { bold: true, color: BLUE }),
      loremIpsumDolorSitAmetConsecteturAdipiscing: rich("代码先发布拓扑、计数与活动指针，随后创建首批可写 chunk。", 20),
      quamUtMassaLuctusCursusNullamPharetra: rich("后续失败只删除新设备与部分计数，无法自动恢复所有早先状态。", 20),
    },
    label1: rich("#16", 28, { bold: true, color: RED }), body2: rich("post_commit_list 仍挂在事务更新链", 22, { bold: true }),
    label2: rich("#17", 28, { bold: true, color: RED }), body3: rich("latest_dev / s_bdev 指向失败设备", 22, { bold: true }),
    label3: rich("#18", 28, { bold: true, color: RED }), body4: rich("fs_devices 已完成 sprout 切换但未恢复", 22, { bold: true }),
    label4: rich("影响", 24, { bold: true }), body5: rich("WARN、NULL 解引用与 kernel BUG", 22, { bold: true }),
    footer1: footer(10),
  });
  setNotes(s, "三个 bug 共用一条失败链，但残差根不同：事务列表、活动设备指针、fs_devices 拓扑。它说明身份感知不能只看变量名，必须覆盖多个 owner 与容器关系。", ["linux-sources/linux-v6.14-fs/fs/btrfs/volumes.c", "outputs/confirmed_bugs.md"]);

  s = buildSlide18(presentation, {
    title: titleToken("Sprout 案例暴露了跨域回滚的核心难点"),
    body1: topic("先发布", "btrfs_setup_sprout()、active device 切换、设备链表和计数先发布。", 24, 19),
    body2: topic("后失败", "init_first_rw_device() / btrfs_add_dev_item() / btrfs_finish_sprout() 任一失败都进入 error_sysfs。", 24, 19),
    body3: topic("只回滚局部", "error_sysfs 删除设备和计数，却没有完整逆转事务链、活动指针和 sprout 容器状态。", 24, 19),
    label1: rich("TOPOLOGY", 18, { bold: true, color: BLUE }),
    label2: rich("FAILURE", 18, { bold: true, color: RED }),
    label3: rich("PARTIAL ROLLBACK", 18, { bold: true }),
    footer1: footer(11),
  });
  setNotes(s, "讲解时把 2875–2903 看成发布阶段，把 2920–2938 看成失败点，把 2987–3017 看成局部回滚。三段正好对应双向切片的边界。", ["linux-sources/linux-v6.14-fs/fs/btrfs/volumes.c", "outputs/confirmed_bugs.md"]);

  s = buildChartSlide(presentation, 12);
  setNotes(s, "M37 当前覆盖 314 个源文件、9,676 个函数和 6,872 个失败切片。柱图只比较边界残差与 UNKNOWN，不把 review/contained 混入，以免分类含义不一致。", ["outputs/residual-evaluation-batch/linux-v6.14-fs-btrfs-m37-semantic-audit/summary.json", "outputs/residual-evaluation-batch/linux-v6.14-fs-ext4-m37-semantic-audit/summary.json", "outputs/residual-evaluation-batch/linux-v6.14-fs-f2fs-m37-semantic-audit/summary.json", "outputs/residual-evaluation-batch/linux-v6.14-fs-xfs-m37-semantic-audit/summary.json"]);

  s = buildGateTableSlide(presentation, 13);
  setNotes(s, "38 个检查中 34 个通过。新增候选、丢失基线 witness、oracle 安全回归都为 0；失败集中在 compatibility match budget，说明比较键与语义身份还不够精确。", ["outputs/residual-evaluation-batch/m37-regression-gate.json", "scripts/check_m35_regression_gate.py", "scripts/compare_residual_runs.py"]);

  s = buildSlide15(presentation, {
    title: titleToken("下一阶段应先降低语义不确定性，再扩大扫描规模"),
    body1: {
      titleHere: rich("优先级原则", 27, { bold: true, color: BLUE }),
      loremIpsumDolorSitAmetConsecteturAdipiscing: rich("先让同一 witness 在版本与里程碑之间可稳定匹配。", 20),
      quamUtMassaLuctusCursusNullamPharetra: rich("再补 owner-liveness，最后扩展到 outcome residual。", 20),
    },
    label1: rich("P0", 28, { bold: true, color: RED }), body2: rich("修正兼容匹配超预算，提升 exact identity", 22, { bold: true }),
    label2: rich("P1", 28, { bold: true }), body3: rich("优先补 172 个 sole-gap summary blocker", 22, { bold: true }),
    label3: rich("P2", 28, { bold: true }), body4: rich("实现 owner-liveness / failure-domain 证明", 22, { bold: true }),
    label4: rich("P3", 28, { bold: true }), body5: rich("把 stale return 与 success-outcome 纳入统一模型", 22, { bold: true }),
    footer1: footer(14),
  });
  setNotes(s, "M37c 显示 SUMMARY_BODY_UNAVAILABLE 是最大 UNKNOWN 缺口：251 份报告、172 份 sole blocker，其中 149 份源码可用。先做这些比盲目扩展规则更有直接收益。", ["outputs/residual-evaluation-batch/m37c-semantic-blocker-impact/semantic_blocker_impact.md", "PAPER_ROADMAP.md", "PROJECT_HANDOFF.md"]);

  s = buildSlide26(presentation, {
    title: rich("SE_EOD", 24, { bold: true, color: BLUE }),
    title2: rich("架构已经能解释 bug；\n下一步要证明影响边界。", 72, { bold: true }),
    title3: {
      loremIpsumDetails: rich("残差计算是核心", 24, { bold: true }),
      loremIpsumDetails2: rich("真实案例验证价值", 24, { bold: true }),
      loremIpsumDetails3: rich("语义稳定性决定可信度", 24, { bold: true }),
    },
  });
  setNotes(s, "收束：项目已经从规则堆叠转向证据驱动残差分析；案例证明方法有价值，而当前门失败清楚指出了下一步工程重点。", ["README.md", "PAPER_ROADMAP.md", "outputs/residual-evaluation-batch/m37-regression-gate.json"]);

  for (const [index, slide] of presentation.slides.items.entries()) {
    const stem = `slide-${String(index + 1).padStart(2, "0")}`;
    const png = await presentation.export({ slide, format: "png", scale: 1 });
    await fs.writeFile(`${PREVIEW_DIR}/${stem}.png`, new Uint8Array(await png.arrayBuffer()));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(`${PREVIEW_DIR}/${stem}.layout.json`, await layout.text(), "utf8");
  }

  const montage = await presentation.export({ format: "webp", montage: true, scale: 1 });
  await fs.writeFile(`${ROOT}/.codex-ppt-build/deck-montage.webp`, new Uint8Array(await montage.arrayBuffer()));

  const pptx = await PresentationFile.exportPptx(presentation);
  await pptx.save(OUT);
  console.log(`Wrote ${OUT}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
