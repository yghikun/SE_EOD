import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const ROOT = "E:/yanjiusheng/阅读论文/file_system/SE_EOD";
const OUT = `${ROOT}/SE_EOD组会汇报_架构与本周高级候选.pptx`;
const TMP = `${ROOT}/.codex-ppt-v2/group-meeting`;
const RENDER = `${TMP}/render`;
const LAYOUT = `${TMP}/layout`;
const FONT = "Microsoft YaHei";
const MONO = "Consolas";
const BLACK = "#000000";
const WHITE = "#FFFFFF";
const G1 = "#F3F3F3";
const G2 = "#D8D8D8";
const G3 = "#8D8D8D";

function rect(slide, x, y, w, h, fill = G1, line = G2, name = "rect") {
  return slide.shapes.add({
    geometry: "rect",
    name,
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: line, width: 1 },
  });
}

function txt(slide, value, x, y, w, h, opts = {}) {
  const shape = slide.shapes.add({
    geometry: "textbox",
    name: opts.name || "text",
    position: { left: x, top: y, width: w, height: h },
    fill: opts.fill || "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  shape.text = value;
  shape.text.style = {
    fontSize: opts.size || 21,
    typeface: opts.mono ? MONO : FONT,
    color: opts.color || BLACK,
    bold: opts.bold || false,
    alignment: opts.align || "left",
    verticalAlignment: opts.valign || "top",
    autoFit: opts.autoFit || "shrinkText",
  };
  return shape;
}

function slideTitle(slide, value, page, kicker = "SE_EOD · GROUP MEETING") {
  txt(slide, kicker, 48, 23, 720, 24, { size: 13, bold: true, name: "kicker" });
  txt(slide, value, 48, 53, 1184, 64, { size: 37, bold: true, name: "title" });
  rect(slide, 48, 124, 1184, 2, BLACK, BLACK, "title-rule");
  txt(slide, String(page).padStart(2, "0"), 1178, 677, 54, 20, { size: 12, align: "right", name: "page" });
}

function setNotes(slide, body, sources) {
  slide.speakerNotes.textFrame.setText(
    `${body}\n\n[Sources]\n${sources.map((s) => `- ${ROOT}/${s}`).join("\n")}`,
  );
  slide.speakerNotes.setVisible(true);
}

function code(slide, value, x, y, w, h, label, size = 16.5, invert = false) {
  rect(slide, x, y, w, h, invert ? BLACK : "#F7F7F7", invert ? BLACK : "#BDBDBD", `code-${label}`);
  rect(slide, x, y, 7, h, invert ? WHITE : BLACK, invert ? WHITE : BLACK, `bar-${label}`);
  txt(slide, label, x + 20, y + 14, w - 38, 24, { size: 14, bold: true, mono: true, color: invert ? WHITE : BLACK });
  txt(slide, value, x + 20, y + 47, w - 36, h - 60, { size, mono: true, color: invert ? WHITE : BLACK });
}

function panel(slide, heading, body, x, y, w, h, invert = false) {
  rect(slide, x, y, w, h, invert ? BLACK : G1, invert ? BLACK : G2, `panel-${heading}`);
  txt(slide, heading, x + 20, y + 16, w - 40, 30, { size: 19, bold: true, color: invert ? WHITE : BLACK });
  txt(slide, body, x + 20, y + 55, w - 40, h - 68, { size: 18.5, color: invert ? WHITE : BLACK });
}

function ruleItem(slide, index, heading, body, x, y, w) {
  txt(slide, String(index).padStart(2, "0"), x, y, 38, 22, { size: 13, bold: true });
  rect(slide, x, y + 30, w, 2, BLACK, BLACK);
  txt(slide, heading, x, y + 48, w, 32, { size: 21, bold: true });
  txt(slide, body, x, y + 91, w, 74, { size: 18 });
}

function arrow(slide, x, y) {
  txt(slide, "→", x, y, 32, 36, { size: 27, bold: true, align: "center", valign: "middle" });
}

async function main() {
  await fs.mkdir(RENDER, { recursive: true });
  await fs.mkdir(LAYOUT, { recursive: true });
  const p = Presentation.create({ slideSize: { width: 1280, height: 720 } });
  let s;

  // 1. Cover
  s = p.slides.add();
  txt(s, "SE_EOD · 组会汇报", 52, 46, 600, 34, { size: 19, bold: true });
  rect(s, 52, 104, 150, 5, BLACK, BLACK);
  txt(s, "失败路径文件系统\n元数据残差分析", 52, 166, 890, 190, { size: 66, bold: true });
  txt(s, "为什么提出架构 · 两个确认案例 · 本周高级候选", 56, 400, 900, 46, { size: 26 });
  txt(s, "Linux 文件系统静态分析", 56, 594, 400, 34, { size: 18, bold: true });
  txt(s, "2026.07.26", 1030, 594, 200, 34, { size: 18, align: "right" });
  setNotes(s, "开场说明汇报主线：先解释问题为什么需要新的分析架构，再用两个确认 Bug 和本周候选检验架构是否真的抓住了复杂失败语义。", ["docs/METADATA_RESIDUAL_ARCHITECTURE.md", "outputs/confirmed_bugs.md", "outputs/btrfs_tool_findings_pending_review_2026-07-23.md"]);

  // 2. Core motivating shape
  s = p.slides.add(); slideTitle(s, "真正困难的不是发现失败，而是判断失败返回时还残留什么", 2);
  code(s, [
    "publish(owner, metadata_state);     // 状态先对外可见",
    "update(counter_or_topology);",
    "",
    "ret = later_operation();            // 后续步骤可能失败",
    "if (ret)",
    "    goto error;",
    "",
    "error:",
    "    local_cleanup();                // 只清了一部分对象",
    "    return ret;",
  ].join("\n"), 48, 154, 660, 430, "MOTIVATING FAILURE SHAPE", 19);
  panel(s, "分析问题", "错误路径上的 cleanup 是否真正覆盖了此前已经发布的元数据效果？", 754, 154, 478, 126, true);
  panel(s, "不能只看资源", "残留可能是 bit、计数、链表成员、owner 指针、设备拓扑或返回值语义，而不只是 kmalloc/free。", 754, 306, 478, 126);
  panel(s, "不能只看局部", "取消可能藏在 callee、transaction abort、owner teardown 或另一个错误出口；同名变量也不等于同一对象。", 754, 458, 478, 126);
  txt(s, "因此需要以失败点为中心，重建“写入 → 失败 → 清理 → 错误出口”的完整因果链。", 48, 622, 1184, 34, { size: 23, bold: true });
  setNotes(s, "提出架构的直接原因是这种代码形态：状态先发布，错误后发生，清理分散且常常只覆盖局部对象。传统局部模式难以回答最终残差。", ["docs/METADATA_RESIDUAL_ARCHITECTURE.md", "outputs/confirmed_bugs.md"]);

  // 3. Why existing abstractions are insufficient
  s = p.slides.add(); slideTitle(s, "三类语义断层使简单的“申请—释放”模型不够用", 3);
  panel(s, "状态效果不等于资源", "位状态、容器成员、计数增减、所属对象指针，以及成功状态/失败返回，都可能构成缺陷。", 48, 160, 350, 310);
  panel(s, "清理不等于取消", "free(local) 只能证明局部对象销毁；它不能自动取消已经挂到另一个 owner 字段、容器或事务链上的效果。", 465, 160, 350, 310, true);
  panel(s, "残差不等于 Bug", "函数边界上 R_f 非空，只说明错误退出时存在未闭合效果；owner 是否存活、影响是否可见仍需额外证据。", 882, 160, 350, 310);
  txt(s, "需要同时表达：对象身份、控制流可达性、错误出口分区、跨过程语义和证据强度。", 48, 525, 1184, 48, { size: 26, bold: true });
  txt(s, "这五个要求共同决定了架构，而不是先有模块再寻找问题。", 48, 590, 1184, 38, { size: 21 });
  setNotes(s, "这里把架构需求从问题中推导出来：效果类型丰富、取消依赖身份、结论需要分层。", ["docs/METADATA_RESIDUAL_ARCHITECTURE.md", "PAPER_ROADMAP.md"]);

  // 4. Design requirements
  s = p.slides.add(); slideTitle(s, "由问题反推架构：四个设计原则缺一不可", 4);
  ruleItem(s, 1, "Failure-centered", "以具体失败调用为锚，向前后两侧切片，而不是扫描孤立 API 名称。", 48, 166, 520);
  ruleItem(s, 2, "Identity-aware", "效果和取消必须匹配 Root、Key、Plane、Value，避免名称相似造成误抵消。", 712, 166, 520);
  ruleItem(s, 3, "Exit-sensitive", "不同 error return 保持独立分区，分支特有清理不能被提升为全函数保证。", 48, 390, 520);
  ruleItem(s, 4, "Evidence-preserving", "保留源码 site、路径、未知原因和 containment proof，让结果可回看、可质疑。", 712, 390, 520);
  panel(s, "架构目标", "不追求更多 candidate，而是输出可逐行复核、能限制结论边界的 residual witness。", 48, 565, 1184, 100, true);
  setNotes(s, "四个原则分别回应前一页的断层：路径、身份、分区、证据。后续模块都是这些原则的工程实现。", ["docs/METADATA_RESIDUAL_ARCHITECTURE.md", "docs/PROJECT_ARCHITECTURE.md"]);

  // 5. Pipeline
  s = p.slides.add(); slideTitle(s, "架构主链路：从 C 源码到可审计 residual witness", 5);
  const stages = [
    ["C source", "Linux 源码"], ["FunctionIR", "前端归一"], ["CFG", "控制流"], ["Scope", "元数据边界"],
    ["Failure", "失败点"], ["Slice", "双向切片"], ["Summary", "跨过程"], ["Report", "证据输出"],
  ];
  stages.forEach((item, i) => {
    const x = 48 + i * 148;
    rect(s, x, 176, 122, 148, i === 7 ? BLACK : G1, i === 7 ? BLACK : G2);
    txt(s, String(i + 1).padStart(2, "0"), x + 14, 193, 34, 21, { size: 13, bold: true, color: i === 7 ? WHITE : BLACK });
    txt(s, item[0], x + 14, 232, 96, 28, { size: 18, bold: true, color: i === 7 ? WHITE : BLACK });
    txt(s, item[1], x + 14, 274, 96, 30, { size: 15, color: i === 7 ? WHITE : BLACK });
    if (i < 7) arrow(s, x + 120, 229);
  });
  ruleItem(s, 1, "程序理解层", "frontend/ 与 cfg.py 保留表达式、调用点、分支、goto 和 return。", 48, 400, 340);
  ruleItem(s, 2, "残差计算层", "scope、failure point、effect extractor 与 slicer 计算 E_f / C_f / T_f / R_f。", 470, 400, 340);
  ruleItem(s, 3, "证据治理层", "function summary、oracle 与 report 约束跨过程传播和最终结论。", 892, 400, 340);
  setNotes(s, "按三层讲模块，而不是逐个文件报菜名：程序理解、残差计算、证据治理。", ["docs/PROJECT_ARCHITECTURE.md", "src/frontend/model.py", "src/cfg.py", "src/effect_extractor.py", "src/residual_slicer.py", "src/function_summary.py"]);

  // 6. Equation and model
  s = p.slides.add(); slideTitle(s, "核心抽象把状态变化表示为可匹配、可追踪的效果", 6);
  panel(s, "E_f · reaching effects", "失败前已经生效，并在 CFG 上能够到达失败调用的元数据效果。", 48, 154, 270, 132);
  panel(s, "C_f · cancellation", "错误路径上对同一对象、键和值执行的逆向效果。", 348, 154, 270, 132);
  panel(s, "T_f · protection", "事务 abort、fatal shutdown、owner teardown 等明确接管效果。", 648, 154, 270, 132);
  panel(s, "R_f · residual", "R_f = Normalize(E_f ⊕ C_f) − T_f", 948, 154, 284, 132, true);
  code(s, [
    "@dataclass(frozen=True)",
    "class MetadataEffect:",
    "    root: str",
    "    key: str",
    "    plane: MetadataPlane",
    "    delta: MetadataDelta",
    "    value: str",
    "    site: SourceSite",
    "    evidence: EffectEvidence",
    "",
    "identity = (root, key, plane)",
    "cancel_key = (root, key, plane, value)",
  ].join("\n"), 48, 332, 584, 292, "src/metadata_residual.py · MetadataEffect", 18);
  code(s, [
    "ADD(list, device)       ↔ REMOVE(list, device)",
    "INC(counter, n)         ↔ DEC(counter, n)",
    "SET(state_bit, value)   ↔ CLEAR(state_bit, value)",
    "ATTACH(owner.field, x)  ↔ DROP(owner.field, x)",
    "",
    "same spelling           ≠ same identity",
    "free(local_object)      ≠ rollback(owner.field)",
    "transaction abort       ≠ arbitrary state restore",
  ].join("\n"), 664, 332, 568, 292, "IDENTITY-AWARE CANCELLATION", 18);
  setNotes(s, "Effect schema 使结构、计数、恢复三类元数据共享统一表示；取消必须在身份和数值上兼容。", ["src/metadata_residual.py", "docs/METADATA_RESIDUAL_ARCHITECTURE.md"]);

  // 7. Interprocedural
  s = p.slides.add(); slideTitle(s, "跨过程摘要必须保留错误出口分区，否则容易过度证明清理", 7);
  code(s, [
    "@dataclass(frozen=True)",
    "class ErrorExitPartition:",
    "    exit_site: SourceSite",
    "    return_expression: str",
    "    return_constraint: str",
    "    opens: tuple[MetadataEffect, ...]",
    "    cancels: tuple[MetadataEffect, ...]",
    "    protects: tuple[MetadataEffect, ...]",
    "    residuals: tuple[MetadataEffect, ...]",
    "    terminal_actions: tuple[MetadataEffect, ...]",
    "    path: tuple[SourceSite, ...]",
    "    complete: bool",
    "    unknown_causes: tuple[str, ...]",
  ].join("\n"), 48, 150, 580, 454, "src/function_summary.py", 17.5);
  ruleItem(s, 1, "参数化身份", "callee 中 param->field 投影为 caller 的实参 owner，并保留 call-site witness。", 670, 164, 562);
  ruleItem(s, 2, "出口相关性", "return -ENOMEM 与 return ret 的路径效果分别保存，不做无条件合并。", 670, 326, 562);
  ruleItem(s, 3, "终止动作提升", "只有所有完整错误分区都包含 terminal action，才能投影为调用者级保证。", 670, 488, 562);
  setNotes(s, "这一页重点解释为何要做 ErrorExitPartition：同一函数不同错误出口的 cleanup 可能完全不同。", ["src/function_summary.py", "docs/METADATA_RESIDUAL_ARCHITECTURE.md"]);

  // 8. Evidence ladder
  s = p.slides.add(); slideTitle(s, "报告结论分层：残差证据与真实 Bug 之间不能直接画等号", 8);
  const ladder = [
    ["1", "SOURCE WITNESS", "效果、失败点、错误出口都有源码位置"],
    ["2", "BOUNDARY RESIDUAL", "R_f 非空并到达函数错误出口"],
    ["3", "OWNER / DOMAIN PROOF", "owner 存活或 failure domain 未吸收残差"],
    ["4", "DYNAMIC / REVIEW EVIDENCE", "复现、故障注入、历史修复或补丁审查"],
    ["5", "CONFIRMED BUG", "证据足以进入确认账本"],
  ];
  ladder.forEach((v, i) => {
    const y = 154 + i * 92;
    rect(s, 48, y, 1184, 70, i === 4 ? BLACK : (i % 2 === 0 ? G1 : WHITE), i === 4 ? BLACK : G2);
    txt(s, v[0], 68, y + 18, 44, 30, { size: 20, bold: true, color: i === 4 ? WHITE : BLACK });
    txt(s, v[1], 135, y + 18, 330, 30, { size: 19, bold: true, mono: true, color: i === 4 ? WHITE : BLACK });
    txt(s, v[2], 500, y + 18, 700, 32, { size: 18.5, color: i === 4 ? WHITE : BLACK });
  });
  txt(s, "本周候选停留在第 1–3 层：它们值得优先审查，但尚未进入 confirmed bug。", 48, 632, 1184, 34, { size: 22, bold: true });
  setNotes(s, "为后面的候选项建立口径：pending review 是分析器和源码审查得到的高价值线索，不等同于已复现 Bug。", ["README.md", "outputs/confirmed_bugs.md", "outputs/btrfs_tool_findings_pending_review_2026-07-23.md"]);

  // 9. Confirmed bug 1
  s = p.slides.add(); slideTitle(s, "确认案例 1：reloc_root 已挂到 fs_root，提交失败后引用未被撤销", 9, "CONFIRMED BUG · BTRFS #7");
  code(s, [
    "4196  fs_root = btrfs_get_fs_root(fs_info, ...);",
    "4205  ret = __add_reloc_root(reloc_root);",
    "4207  if (ret) { ... goto out_unset; }",
    "",
    "4213  fs_root->reloc_root = btrfs_grab_root(reloc_root);",
    "4214  btrfs_put_root(fs_root);",
    "",
    "4217  ret = btrfs_commit_transaction(trans);",
    "4218  if (ret)",
    "4219      goto out_unset;",
    "",
    "4235  out_unset:",
    "4236      unset_reloc_control(rc);",
    "4241      free_reloc_roots(&reloc_roots);",
    "4252      return ret;",
  ].join("\n"), 48, 148, 676, 486, "fs/btrfs/relocation.c · key path", 17.5);
  panel(s, "E_f", "ATTACH(fs_root->reloc_root, reloc_root)\nsite: line 4213", 760, 148, 472, 104);
  panel(s, "C_f / T_f", "局部 control 与 reloc_roots list 被释放，但没有动作指向已发布的 fs_root 字段。", 760, 274, 472, 126);
  panel(s, "R_f", "fs_root->reloc_root 引用跨越错误出口；故障注入观察到 25 个 root 保留 reloc_refs=1。", 760, 422, 472, 126, true);
  txt(s, "关键不是 cleanup 数量少，而是 cleanup 的 owner identity 与 4213 的写入不匹配。", 760, 575, 472, 58, { size: 19, bold: true });
  setNotes(s, "一页讲完确认案例：4213 发布引用，4217 提交失败，out_unset 未对同一 owner 字段执行 DROP。动态注入进一步确认引用残留。", ["linux-sources/linux-v6.14-fs/fs/btrfs/relocation.c", "outputs/confirmed_bugs.md", "outputs/linux-v6.8/btrfs/recover_relocation_qemu_report.md"]);

  // 10. Confirmed bug 2
  s = p.slides.add(); slideTitle(s, "确认案例 2：fallback 已更新 inode 状态，却可能返回上一轮 -ENOSPC", 10, "CONFIRMED BUG · EXT4 #4");
  code(s, [
    "2837  error = ext4_xattr_make_inode_space(...);",
    "2840  if (error) {",
    "2841      if (error == -ENOSPC && ... ) {",
    "2843          tried_min_extra_isize++;",
    "2844          new_extra_isize = s_min_extra_isize;",
    "2845          goto retry;",
    "2846      }",
    "2847      goto cleanup;",
    "2848  }",
    "2849  shift:",
    "2851      ext4_xattr_shift_entries(...);",
    "2855      EXT4_I(inode)->i_extra_isize = new_extra_isize;",
    "2860  cleanup:",
    "2866      return error;",
  ].join("\n"), 48, 148, 672, 458, "fs/ext4/xattr.c · key retry path", 18);
  panel(s, "第一次结果", "make_inode_space() 返回 -ENOSPC，error 保存失败值。", 758, 148, 474, 108);
  panel(s, "第二次状态", "降低 new_extra_isize 后，fallback 可以进入 shift 并更新 i_extra_isize。", 758, 278, 474, 126, true);
  panel(s, "最终分歧", "实际元数据状态 = 成功；函数 outcome = 旧失败。修复方向是在 retry 前清除 stale error。", 758, 426, 474, 180);
  txt(s, "复现记录：同一配置下 FS_IOC_FSSETXATTR 失败数从 802 降至 86。", 48, 628, 1184, 32, { size: 21, bold: true });
  setNotes(s, "第二个案例展示架构不能只分析资源残留，还要表达成功状态与失败返回之间的 outcome residual。", ["linux-sources/linux-v6.14-fs/fs/ext4/xattr.c", "outputs/confirmed_bugs.md"]);

  // 11. Weekly candidates overview
  s = p.slides.add(); slideTitle(s, "本周高级候选：三条路径分别落在状态、生命周期与设备拓扑", 11, "PENDING REVIEW · 2026-07-23");
  const rows = [
    ["P1", "btrfs_reconfigure()", "REMOUNTING bit 残留", "核心元数据状态", "直接 candidate"],
    ["P2", "btrfs_init_dev_replace_tgtdev()", "device allocation 泄漏", "资源生命周期", "直接 candidate"],
    ["P3", "btrfs_dev_replace_start()", "target 仍挂入 devices", "拓扑 + 计数", "UNKNOWN → direct candidate"],
  ];
  const xs = [48, 132, 462, 760, 1000];
  ["ID", "函数", "残差", "分类", "分析器来源"].forEach((h, i) => txt(s, h, xs[i], 164, i === 1 ? 300 : 210, 30, { size: 18, bold: true }));
  rect(s, 48, 204, 1184, 2, BLACK, BLACK);
  rows.forEach((row, ri) => {
    const y = 226 + ri * 100;
    rect(s, 48, y - 12, 1184, 78, ri === 0 ? BLACK : (ri === 2 ? G1 : WHITE), ri === 0 ? BLACK : G2);
    row.forEach((v, i) => txt(s, v, xs[i], y, i === 1 ? 310 : 220, 48, { size: i === 0 ? 20 : 17.5, bold: i === 0 || i === 1, color: ri === 0 ? WHITE : BLACK }));
  });
  panel(s, "共同证据", "三种代码形态在 Linux v6.14 与 v7.1 均存在；均需要重复查询 master / for-next / lore，并完成定向复现后才能升级为 confirmed bug。", 48, 550, 1184, 104, true);
  setNotes(s, "这一页只做候选总览。P1/P3属于论文核心元数据语义，P2是真实资源生命周期问题，但需要明确其与核心 claim 的边界。", ["outputs/btrfs_tool_findings_pending_review_2026-07-23.md"]);

  // 12. P1
  s = p.slides.add(); slideTitle(s, "候选 P1：两条验证失败直接 return，REMOUNTING bit 只在后续出口清除", 12, "PENDING REVIEW · P1");
  code(s, [
    "1505  sync_filesystem(sb);",
    "1506  set_bit(BTRFS_FS_STATE_REMOUNTING,",
    "1507          &fs_info->fs_state);",
    "",
    "1508  if (!btrfs_check_options(...))",
    "1509      return -EINVAL;",
    "",
    "1511  ret = btrfs_check_features(...);",
    "1512  if (ret < 0)",
    "1513      return ret;",
    "",
    "1556  clear_bit(BTRFS_FS_STATE_REMOUNTING, ...);",
    "1558  return 0;",
    "1559  restore:",
    "1562      clear_bit(BTRFS_FS_STATE_REMOUNTING, ...);",
  ].join("\n"), 48, 148, 650, 484, "fs/btrfs/super.c · btrfs_reconfigure", 18);
  panel(s, "E_f", "SET fs_info->fs_state.bit:BTRFS_FS_STATE_REMOUNTING", 738, 148, 494, 108, true);
  panel(s, "错误出口", "btrfs_check_options() 和 btrfs_check_features() 失败时直接 return，绕过 success / restore 清理。", 738, 278, 494, 142);
  panel(s, "潜在长期影响", "失败 remount 后原挂载仍存活；auto-defrag、qgroup rescan 与异步 space reclaim 会读取该状态位。", 738, 442, 494, 140);
  txt(s, "待确认关键点：自然失败场景下 bit 是否持续可见，并实际抑制至少一条后台路径。", 738, 606, 494, 40, { size: 18.5, bold: true });
  setNotes(s, "P1 是最贴近核心方法的候选：SET bit 到达验证失败，错误出口没有 CLEAR，且 owner 是长生命周期 fs_info。", ["outputs/btrfs_tool_findings_pending_review_2026-07-23.md", "linux-sources/linux-v6.14-fs/fs/btrfs/super.c"]);

  // 13. P2 / P3
  s = p.slides.add(); slideTitle(s, "候选 P2 / P3：同一 target device 在“挂入拓扑前后”需要不同清理", 13, "PENDING REVIEW · DEVICE REPLACE");
  code(s, [
    "293  device = btrfs_alloc_device(...);",
    "299  ret = lookup_bdev(...);",
    "300  if (ret)",
    "301      goto error;",
    "...",
    "322  ret = btrfs_get_dev_zone_info(device, false);",
    "323  if (ret)",
    "324      goto error;",
    "...",
    "335  error:",
    "336      fput(bdev_file);",
    "337      return ret;",
  ].join("\n"), 48, 150, 542, 380, "P2 · before list insertion", 17.5);
  code(s, [
    "631  ret = btrfs_init_dev_replace_tgtdev(...,",
    "632          &tgt_device);",
    "633  if (ret)",
    "634      return ret;",
    "",
    "636  ret = mark_block_group_to_copy(...);",
    "637  if (ret)",
    "638      return ret;      // bypass leave",
    "...",
    "719  leave:",
    "720      btrfs_destroy_dev_replace_tgtdev(tgt_device);",
    "721      return ret;",
  ].join("\n"), 642, 150, 590, 380, "P3 · after list insertion", 17.5, true);
  panel(s, "P2 · 生命周期", "device 尚未挂入 fs_devices；错误出口仅 fput(bdev_file)，没有释放已分配的 device。", 48, 538, 542, 118);
  panel(s, "P3 · 元数据拓扑", "target 已挂入 devices 并增加计数；mark_block_group_to_copy() 失败直接 return，绕过 leave。", 642, 538, 590, 118);
  setNotes(s, "P2 和 P3 放在一页是为了比较 phase-sensitive cleanup：同一个 device 在挂入拓扑前后需要不同清理函数，不能共用一个粗粒度 free 规则。", ["outputs/btrfs_tool_findings_pending_review_2026-07-23.md", "linux-sources/linux-v6.14-fs/fs/btrfs/dev-replace.c"]);

  // 14. Discussion
  s = p.slides.add(); slideTitle(s, "组会讨论：候选能否升级，取决于三个证据判断", 14);
  ruleItem(s, 1, "P1 的活性与影响", "失败 remount 后 fs_info 长期存活可以成立；还需证明 stale bit 对后台消费者的实际抑制。", 48, 164, 520);
  ruleItem(s, 2, "P2 的论文边界", "资源泄漏本身较清晰，但它更适合作为 SE-EOD baseline，还是纳入元数据 residual claim？", 712, 164, 520);
  ruleItem(s, 3, "P3 的完整回滚", "销毁 target device 是否足够？mark_block_group_to_copy() 已设置的部分 TO_COPY bits 是否也要恢复？", 48, 388, 520);
  ruleItem(s, 4, "候选口径", "在完成 duplicate search、定向 fault injection 与 owner-state 检查前，统一保持 pending review。", 712, 388, 520);
  panel(s, "汇报结论", "架构的价值不是找到可疑 return，而是区分写入阶段、owner 身份、清理范围和证据强度。", 48, 558, 1184, 108, true);
  setNotes(s, "结束时把讨论引向三个具体判断：P1影响、P2 scope、P3 partial rollback。", ["outputs/btrfs_tool_findings_pending_review_2026-07-23.md", "docs/METADATA_RESIDUAL_ARCHITECTURE.md"]);

  for (const [i, slide] of p.slides.items.entries()) {
    const stem = `slide-${String(i + 1).padStart(2, "0")}`;
    const png = await p.export({ slide, format: "png", scale: 1 });
    await fs.writeFile(`${RENDER}/${stem}.png`, new Uint8Array(await png.arrayBuffer()));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(`${LAYOUT}/${stem}.layout.json`, await layout.text(), "utf8");
  }
  const pptx = await PresentationFile.exportPptx(p);
  await pptx.save(OUT);
  console.log(`Wrote ${OUT}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
