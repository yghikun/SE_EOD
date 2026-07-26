import fs from "node:fs/promises";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const ROOT = "E:/yanjiusheng/阅读论文/file_system/SE_EOD";
const OUT = `${ROOT}/SE_EOD项目架构与Bug案例_详细代码版.pptx`;
const RENDER_DIR = `${ROOT}/.codex-ppt-v2/final-render`;
const LAYOUT_DIR = `${ROOT}/.codex-ppt-v2/final-layout`;

const W = 1280;
const H = 720;
const FONT = "Microsoft YaHei";
const MONO = "Consolas";
const BLACK = "#000000";
const WHITE = "#FFFFFF";
const G1 = "#F3F3F3";
const G2 = "#DEDEDE";
const G3 = "#999999";

function box(slide, x, y, w, h, fill = G1, line = G2, name = "box") {
  return slide.shapes.add({
    geometry: "rect",
    name,
    position: { left: x, top: y, width: w, height: h },
    fill,
    line: { style: "solid", fill: line, width: 1 },
  });
}

function textBox(slide, value, x, y, w, h, opts = {}) {
  const s = slide.shapes.add({
    geometry: "textbox",
    name: opts.name || "text",
    position: { left: x, top: y, width: w, height: h },
    fill: opts.fill || "none",
    line: { style: "solid", fill: "none", width: 0 },
  });
  s.text = value;
  s.text.style = {
    fontSize: opts.size || 21,
    typeface: opts.mono ? MONO : FONT,
    color: opts.color || BLACK,
    bold: opts.bold || false,
    alignment: opts.align || "left",
    verticalAlignment: opts.valign || "top",
    autoFit: opts.autoFit || "shrinkText",
  };
  return s;
}

function title(slide, value, page, kicker = "SE_EOD · FAILURE-PATH METADATA RESIDUAL") {
  textBox(slide, kicker, 48, 24, 740, 25, { size: 13, bold: true, name: "kicker" });
  textBox(slide, value, 48, 54, 1184, 62, { size: 36, bold: true, name: "title" });
  box(slide, 48, 124, 1184, 2, BLACK, BLACK, "title-rule");
  textBox(slide, String(page).padStart(2, "0"), 1178, 678, 54, 20, { size: 12, align: "right", name: "page" });
}

function notes(slide, presenter, sources) {
  slide.speakerNotes.textFrame.setText(
    `${presenter}\n\n[Sources]\n${sources.map((s) => `- ${ROOT}/${s}`).join("\n")}`,
  );
  slide.speakerNotes.setVisible(true);
}

function metric(slide, x, y, w, value, label, detail = "") {
  box(slide, x, y, w, 150, G1, G2, `metric-${label}`);
  textBox(slide, value, x + 20, y + 20, w - 40, 52, { size: 38, bold: true });
  textBox(slide, label, x + 20, y + 76, w - 40, 30, { size: 19, bold: true });
  if (detail) textBox(slide, detail, x + 20, y + 112, w - 40, 24, { size: 14 });
}

function codeBlock(slide, code, x, y, w, h, label, size = 16.5) {
  box(slide, x, y, w, h, "#F7F7F7", "#BDBDBD", `code-${label}`);
  box(slide, x, y, 7, h, BLACK, BLACK, `code-bar-${label}`);
  textBox(slide, label, x + 20, y + 14, w - 40, 24, { size: 14, bold: true, mono: true });
  textBox(slide, code, x + 20, y + 46, w - 34, h - 58, { size, mono: true, autoFit: "shrinkText" });
}

function callout(slide, heading, body, x, y, w, h, invert = false) {
  box(slide, x, y, w, h, invert ? BLACK : G1, invert ? BLACK : G2, `callout-${heading}`);
  textBox(slide, heading, x + 18, y + 15, w - 36, 27, { size: 18, bold: true, color: invert ? WHITE : BLACK });
  textBox(slide, body, x + 18, y + 50, w - 36, h - 62, { size: 18, color: invert ? WHITE : BLACK });
}

function stage(slide, index, heading, body, x, y, w) {
  textBox(slide, String(index).padStart(2, "0"), x, y, 36, 26, { size: 14, bold: true });
  box(slide, x, y + 31, w, 2, BLACK, BLACK, `stage-rule-${index}`);
  textBox(slide, heading, x, y + 48, w, 34, { size: 21, bold: true });
  textBox(slide, body, x, y + 88, w, 90, { size: 17.5 });
}

function arrow(slide, x, y) {
  textBox(slide, "→", x, y, 34, 40, { size: 28, bold: true, align: "center", valign: "middle" });
}

const bug7Attach = [
  "4185  while (!list_empty(&reloc_roots)) {",
  "4186      reloc_root = list_entry(reloc_roots.next,",
  "4187                    struct btrfs_root, root_list);",
  "4188      list_del(&reloc_root->root_list);",
  "...",
  "4196      fs_root = btrfs_get_fs_root(fs_info,",
  "4197                    reloc_root->root_key.offset, false);",
  "4198      if (IS_ERR(fs_root)) {",
  "4199          ret = PTR_ERR(fs_root);",
  "4200          list_add_tail(&reloc_root->root_list, &reloc_roots);",
  "4201          btrfs_end_transaction(trans);",
  "4202          goto out_unset;",
  "4203      }",
  "4205      ret = __add_reloc_root(reloc_root);",
  "4207      if (ret) {",
  "4208          list_add_tail(&reloc_root->root_list, &reloc_roots);",
  "4209          btrfs_put_root(fs_root);",
  "4210          btrfs_end_transaction(trans);",
  "4211          goto out_unset;",
  "4212      }",
  "4213      fs_root->reloc_root = btrfs_grab_root(reloc_root);",
  "4214      btrfs_put_root(fs_root);",
  "4215  }",
  "4217  ret = btrfs_commit_transaction(trans);",
  "4218  if (ret)",
  "4219      goto out_unset;",
].join("\n");

const bug7Cleanup = [
  "4231  out_clean:",
  "4232      ret2 = clean_dirty_subvols(rc);",
  "4233      if (ret2 < 0 && !ret)",
  "4234          ret = ret2;",
  "4235  out_unset:",
  "4236      unset_reloc_control(rc);",
  "4237  out_end:",
  "4238      reloc_chunk_end(fs_info);",
  "4239      free_reloc_control(rc);",
  "4240  out:",
  "4241      free_reloc_roots(&reloc_roots);",
  "4243      btrfs_free_path(path);",
  "4245      if (ret == 0) {",
  "4246          /* cleanup orphan inode ... */",
  "4247          fs_root = btrfs_grab_root(fs_info->data_reloc_root);",
  "4249          ret = btrfs_orphan_cleanup(fs_root);",
  "4250          btrfs_put_root(fs_root);",
  "4251      }",
  "4252      return ret;",
].join("\n");

const bug4Retry = [
  "2776  retry:",
  "2777      isize_diff = new_extra_isize -",
  "2778          EXT4_I(inode)->i_extra_isize;",
  "2779      if (EXT4_I(inode)->i_extra_isize >= new_extra_isize)",
  "2780          return 0;",
  "...",
  "2793      error = xattr_check_inode(inode, header, end);",
  "2794      if (error)",
  "2795          goto cleanup;",
  "2797      ifree = ext4_xattr_free_space(...);",
  "2798      if (ifree >= isize_diff)",
  "2799          goto shift;",
  "...",
  "2837      error = ext4_xattr_make_inode_space(handle, inode,",
  "2838                    raw_inode, isize_diff, ifree, bfree,",
  "2839                    &total_ino);",
  "2840      if (error) {",
  "2841          if (error == -ENOSPC &&",
  "2842              !tried_min_extra_isize && s_min_extra_isize) {",
  "2843              tried_min_extra_isize++;",
  "2844              new_extra_isize = s_min_extra_isize;",
  "2845              goto retry;",
  "2846          }",
  "2847          goto cleanup;",
  "2848      }",
].join("\n");

const bug4Return = [
  "2849  shift:",
  "2850      /* Adjust offsets and shift remaining entries */",
  "2851      ext4_xattr_shift_entries(IFIRST(header),",
  "2852          EXT4_I(inode)->i_extra_isize - new_extra_isize,",
  "2853          (void *)raw_inode + EXT4_GOOD_OLD_INODE_SIZE +",
  "2854          new_extra_isize, (void *)header, total_ino);",
  "2855      EXT4_I(inode)->i_extra_isize = new_extra_isize;",
  "",
  "2857      if (ext4_has_inline_data(inode))",
  "2858          error = ext4_find_inline_data_nolock(inode);",
  "",
  "2860  cleanup:",
  "2861      if (error && (mnt_count !=",
  "2862          le16_to_cpu(sbi->s_es->s_mnt_count))) {",
  "2863          ext4_warning(...);",
  "2865      }",
  "2866      return error;",
].join("\n");

const sproutPublish = [
  "2863  if (seeding_dev) {",
  "2865      seed_devices = btrfs_init_sprout(fs_info);",
  "2875      btrfs_setup_sprout(fs_info, seed_devices);",
  "2876      btrfs_assign_next_active_device(",
  "2877          fs_info->fs_devices->latest_dev, device);",
  "2878  }",
  "2880  device->fs_devices = fs_devices;",
  "2882  mutex_lock(&fs_info->chunk_mutex);",
  "2883  list_add_rcu(&device->dev_list, &fs_devices->devices);",
  "2884  list_add(&device->dev_alloc_list, &fs_devices->alloc_list);",
  "2885  fs_devices->num_devices++;",
  "2886  fs_devices->open_devices++;",
  "2887  fs_devices->rw_devices++;",
  "2888  fs_devices->total_devices++;",
  "2889  fs_devices->total_rw_bytes += device->total_bytes;",
  "2891  atomic64_add(device->total_bytes,",
  "2892               &fs_info->free_chunk_space);",
  "2897  btrfs_set_super_total_bytes(...);",
  "2901  orig_super_num_devices = ...;",
  "2902  btrfs_set_super_num_devices(... + 1);",
].join("\n");

const sproutFailCleanup = [
  "2918  if (seeding_dev) {",
  "2920      ret = init_first_rw_device(trans);",
  "2922      if (ret) {",
  "2923          btrfs_abort_transaction(trans, ret);",
  "2924          goto error_sysfs;",
  "2925      }",
  "2928  ret = btrfs_add_dev_item(trans, device);",
  "2929  if (ret) { ... goto error_sysfs; }",
  "2935  ret = btrfs_finish_sprout(trans);",
  "2936  if (ret) { ... goto error_sysfs; }",
  "...",
  "2987  error_sysfs:",
  "2988      btrfs_sysfs_remove_device(device);",
  "2991      list_del_rcu(&device->dev_list);",
  "2992      list_del(&device->dev_alloc_list);",
  "2993      fs_info->fs_devices->num_devices--;",
  "2994      fs_info->fs_devices->open_devices--;",
  "2995      fs_info->fs_devices->rw_devices--;",
  "2996      fs_info->fs_devices->total_devices--;",
  "2997      fs_info->fs_devices->total_rw_bytes -= device->total_bytes;",
  "2998      atomic64_sub(device->total_bytes, ...);",
  "2999      btrfs_set_super_total_bytes(...orig...);",
  "3001      btrfs_set_super_num_devices(...orig...);",
  "3011      btrfs_free_device(device);",
].join("\n");

async function main() {
  await fs.mkdir(RENDER_DIR, { recursive: true });
  await fs.mkdir(LAYOUT_DIR, { recursive: true });
  const p = Presentation.create({ slideSize: { width: W, height: H } });
  let s;

  // 1
  s = p.slides.add();
  textBox(s, "SE_EOD · 项目架构详解", 52, 46, 700, 34, { size: 18, bold: true });
  box(s, 52, 104, 150, 5, BLACK, BLACK);
  textBox(s, "从失败路径到\n元数据残差证据", 52, 170, 850, 190, { size: 67, bold: true });
  textBox(s, "Linux 文件系统静态分析 · 架构、源码链路与真实 Bug", 56, 395, 850, 48, { size: 25 });
  textBox(s, "详细代码版", 56, 596, 250, 34, { size: 18, bold: true });
  textBox(s, "2026.07", 1080, 596, 150, 34, { size: 18, align: "right" });
  notes(s, "开场先说明：本报告不是罗列规则，而是解释项目如何把失败路径上的状态变更组织成可追溯、可复核的证据。", ["README.md", "docs/PROJECT_ARCHITECTURE.md"]);

  // 2
  s = p.slides.add(); title(s, "系统的输出不是告警数量，而是一条可审计的失败因果链", 2);
  stage(s, 1, "源码事实", "记录具体赋值、容器更新、计数变化、调用返回和 goto / return 位置。", 48, 164, 250);
  arrow(s, 318, 238);
  stage(s, 2, "路径事实", "证明状态写入能够到达失败点，并沿哪一条错误边到达函数出口。", 350, 164, 250);
  arrow(s, 620, 238);
  stage(s, 3, "语义事实", "把写入表示为 Root / Key / Plane / Delta / Value，并匹配取消或保护。", 652, 164, 250);
  arrow(s, 922, 238);
  stage(s, 4, "结论事实", "输出残差、源码 witness、未解决身份和结论边界，供人工或动态验证。", 954, 164, 278);
  callout(s, "输入", "Linux C 源码 + 文件系统元数据作用域合同", 48, 414, 340, 132);
  callout(s, "分析核心", "FunctionIR + CFG + failure point + bidirectional slice + function summary", 438, 414, 442, 132, true);
  callout(s, "输出", "ResidualSlice：E_f、C_f、T_f、R_f、error exit、rationale 与 evidence", 930, 414, 302, 132);
  textBox(s, "同一条证据链既服务于自动报告，也允许审查者回到原始源码逐行复核。", 48, 590, 1184, 48, { size: 25, bold: true });
  notes(s, "这一页定义系统的沟通目标：输出不是一个分数，而是从源码事实到结论事实的可回溯链条。", ["docs/PROJECT_ARCHITECTURE.md", "docs/METADATA_RESIDUAL_ARCHITECTURE.md", "src/metadata_residual.py"]);

  // 3
  s = p.slides.add(); title(s, "残差模型把“发生了什么”与“错误退出时还剩什么”分开", 3);
  callout(s, "E_f · 到达失败点", "失败发生前已经生效的结构、计数、恢复或事务元数据效果。", 48, 166, 270, 145);
  callout(s, "C_f · 取消 / 补偿", "错误路径上与同一对象、键和值匹配的逆向效果。", 348, 166, 270, 145);
  callout(s, "T_f · 保护 / 转移", "事务 abort、owner teardown、forced shutdown 等明确接管效果。", 648, 166, 270, 145);
  callout(s, "R_f · 最终残差", "R_f = Normalize(E_f ⊕ C_f) − T_f。非空且到达错误出口才进入报告。", 948, 166, 284, 145, true);
  codeBlock(s, [
    "Effect = <Root, Key, Plane, Delta, Value, Site, Evidence>",
    "",
    "identity(effect)        = (Root, Key, Plane)",
    "cancellation_key(effect)= (Root, Key, Plane, Value)",
    "",
    "ADD(list, device)       ↔ REMOVE(list, device)",
    "INC(counter, n)         ↔ DEC(counter, n)",
    "ATTACH(root.reloc_root) ↔ DROP(root.reloc_root)",
  ].join("\n"), 48, 355, 760, 252, "IDENTITY-AWARE CANCELLATION", 18);
  callout(s, "关键约束", "名字相似不等于同一对象。Root、Key、Plane、Value 的身份必须兼容，才能把补偿认作取消。", 838, 355, 394, 252);
  notes(s, "这一页是全套架构的核心。状态标签只是结果，真正的方法贡献是围绕失败点计算 R_f，并保留身份与源码位置。", ["docs/METADATA_RESIDUAL_ARCHITECTURE.md", "src/metadata_residual.py"]);

  // 4
  s = p.slides.add(); title(s, "主链路从 C 源码走到可审计 witness，共经过八个阶段", 4);
  const flow = [
    ["Linux C", "源文件与版本"], ["FunctionIR", "Tree-sitter 前端"], ["CFG", "分支与错误出口"], ["Scope", "元数据边界"],
    ["Failure", "失败点发现"], ["Slice", "E_f / C_f / T_f"], ["Summary", "跨过程投影"], ["Report", "证据与回归门"],
  ];
  flow.forEach((v, i) => {
    const x = 48 + i * 148;
    box(s, x, 188, 122, 150, i === 7 ? BLACK : G1, i === 7 ? BLACK : G2);
    textBox(s, String(i + 1).padStart(2, "0"), x + 14, 205, 40, 22, { size: 13, bold: true, color: i === 7 ? WHITE : BLACK });
    textBox(s, v[0], x + 14, 245, 94, 30, { size: 20, bold: true, color: i === 7 ? WHITE : BLACK });
    textBox(s, v[1], x + 14, 286, 94, 38, { size: 15, color: i === 7 ? WHITE : BLACK });
    if (i < 7) arrow(s, x + 120, 240);
  });
  stage(s, 1, "理解源程序", "前端把不同 C 写法归一为 FunctionIR；CFG 保留条件、goto、return 与调用点。", 48, 404, 340);
  stage(s, 2, "计算失败残差", "以失败点为锚，向后找已发生效果，沿错误路径向前找取消、保护和退出。", 470, 404, 340);
  stage(s, 3, "约束结论边界", "跨过程摘要、oracle 与回归门共同防止“候选残差”被过度表述为已确认 Bug。", 892, 404, 340);
  notes(s, "讲解时强调三层：程序理解、残差计算、证据治理。任何一层缺失都会导致结果不可审计。", ["docs/PROJECT_ARCHITECTURE.md", "docs/METADATA_RESIDUAL_ARCHITECTURE.md"]);

  // 5
  s = p.slides.add(); title(s, "模块按证据责任划分，而不是按文件系统堆叠规则", 5);
  const mods = [
    ["frontend/", "C AST → FunctionIR", "保留源码位置、表达式与调用点"],
    ["cfg.py", "函数内控制流", "构建块、边与错误出口可达性"],
    ["metadata_scope.py", "作用域合同", "过滤非结构/计数/恢复元数据"],
    ["failure_points.py", "失败点发现", "识别错误检查、goto 与 error return"],
    ["effect_extractor.py", "效果抽取", "生成 Root / Key / Plane / Delta"],
    ["residual_slicer.py", "双向切片", "计算 E_f、C_f、T_f 与 R_f"],
    ["function_summary.py", "跨过程语义", "参数化效果并保留错误出口分区"],
    ["harness + oracle", "证据治理", "批量评估、人工 verdict 与回归门"],
  ];
  mods.forEach((m, i) => {
    const col = i % 2; const row = Math.floor(i / 2);
    const x = 48 + col * 600; const y = 154 + row * 122;
    textBox(s, m[0], x, y, 190, 28, { size: 19, bold: true, mono: true });
    textBox(s, m[1], x + 205, y, 340, 28, { size: 19, bold: true });
    box(s, x, y + 36, 550, 1, G3, G3);
    textBox(s, m[2], x, y + 50, 550, 40, { size: 17 });
  });
  notes(s, "复杂度主要集中在效果抽取、切片和函数摘要。文件系统差异通过作用域配置与源码证据进入，而不是复制四套分析器。", ["src/frontend/model.py", "src/cfg.py", "src/metadata_scope.py", "src/failure_points.py", "src/effect_extractor.py", "src/residual_slicer.py", "src/function_summary.py"]);

  // 6
  s = p.slides.add(); title(s, "核心数据结构直接保留身份、路径和证据来源", 6);
  codeBlock(s, [
    "231  @dataclass(frozen=True)",
    "232  class MetadataEffect:",
    "233      root: str",
    "234      key: str",
    "235      plane: MetadataPlane",
    "236      delta: MetadataDelta",
    "237      value: str",
    "238      site: SourceSite",
    "239      evidence: EffectEvidence = DIRECT_SOURCE",
    "...",
    "247      def identity(self):",
    "248          return (self.root, self.key, self.plane)",
    "250      def cancellation_key(self):",
    "251          return (self.root, self.key, self.plane, self.value)",
  ].join("\n"), 48, 152, 570, 454, "src/metadata_residual.py · MetadataEffect", 17.5);
  codeBlock(s, [
    "312  @dataclass(frozen=True)",
    "313  class ResidualSlice:",
    "314      failure_site: SourceSite",
    "315      reaching_effects: tuple[MetadataEffect, ...]",
    "316      cancellations: tuple[MetadataEffect, ...]",
    "317      protections: tuple[MetadataEffect, ...]",
    "318      residuals: tuple[MetadataEffect, ...]",
    "319      state: ResidualState",
    "320      exit_site: SourceSite | None = None",
    "321      rationale: str = \"\"",
    "322      out_of_scope_effects: tuple[...] = ()",
    "323      containment_proofs: tuple[...] = ()",
    "324      owner_teardown_proofs: tuple[...] = ()",
  ].join("\n"), 650, 152, 582, 454, "src/metadata_residual.py · ResidualSlice", 17.5);
  notes(s, "MetadataEffect 是最小证据单元；ResidualSlice 是一次失败路径分析的完整账本。保留 out-of-scope 与 containment proof 是为了审计，不是只保留最终标签。", ["src/metadata_residual.py"]);

  // 7
  s = p.slides.add(); title(s, "跨过程摘要按错误出口分区，避免把分支特有清理投影到所有失败", 7);
  codeBlock(s, [
    "196  @dataclass(frozen=True)",
    "197  class ErrorExitPartition:",
    "200      exit_site: SourceSite",
    "201      return_expression: str",
    "202      return_constraint: str = \"\"",
    "203      opens: tuple[MetadataEffect, ...] = ()",
    "204      cancels: tuple[MetadataEffect, ...] = ()",
    "205      protects: tuple[MetadataEffect, ...] = ()",
    "206      residuals: tuple[MetadataEffect, ...] = ()",
    "207      terminal_actions: tuple[MetadataEffect, ...] = ()",
    "209      path: tuple[SourceSite, ...] = ()",
    "210      complete: bool = False",
    "211      unknown_causes: tuple[str, ...] = ()",
  ].join("\n"), 48, 152, 560, 444, "function_summary.py · ErrorExitPartition", 17.5);
  codeBlock(s, [
    "283  @dataclass(frozen=True)",
    "284  class FunctionSummary:",
    "285      function_name: str",
    "286      parameters: tuple[str, ...]",
    "292      opens: tuple[MetadataEffect, ...]",
    "293      cancels: tuple[MetadataEffect, ...]",
    "294      protects: tuple[MetadataEffect, ...]",
    "296      error_opens: tuple[...] = ()",
    "297      error_cancels: tuple[...] = ()",
    "298      error_protects: tuple[...] = ()",
    "307      error_exit_partitions: tuple[...] = ()",
    "308      error_partitions_exhaustive: bool = False",
    "309      unresolved_calls: tuple[str, ...] = ()",
  ].join("\n"), 640, 152, 592, 444, "function_summary.py · FunctionSummary", 17.5);
  textBox(s, "投影规则：只有所有完整 error partition 都包含 terminal action，才把它提升为聚合调用者失败语义。", 48, 620, 1184, 34, { size: 20, bold: true });
  notes(s, "这页解释为什么项目不把某个分支中的 abort 或 cleanup 粗暴视为函数级保证。分区保持 return constraint 与源码路径相关。", ["src/function_summary.py", "docs/METADATA_RESIDUAL_ARCHITECTURE.md"]);

  // 8
  s = p.slides.add(); title(s, "分析器只证明函数边界残差；确认 Bug 需要额外活性与影响证据", 8);
  callout(s, "可以自动声称", "• R_f 非空并到达错误出口\n• 效果属于文件系统元数据作用域\n• witness 可定位到源码站点与路径\n• 取消或保护关系有显式身份依据", 48, 166, 540, 316);
  callout(s, "不能自动越界声称", "• owner 在退出后一定继续存活\n• 残差一定造成用户可见损坏\n• 候选一定自然可触发\n• 未复现即可视为 upstream Bug", 644, 166, 588, 316, true);
  textBox(s, "FUNCTION_BOUNDARY_RESIDUAL", 48, 526, 350, 36, { size: 24, bold: true, mono: true });
  arrow(s, 420, 520);
  textBox(s, "owner-liveness / failure-domain proof", 470, 526, 430, 36, { size: 20, bold: true });
  arrow(s, 920, 520);
  textBox(s, "confirmed bug", 972, 526, 260, 36, { size: 24, bold: true, mono: true, align: "right" });
  notes(s, "这一页用于限制结论边界。报告中的 Candidate 不是 confirmed bug；动态注入、补丁审查或历史修复用于把候选推进为确认记录。", ["README.md", "PAPER_ROADMAP.md", "outputs/confirmed_bugs.md"]);

  // 9
  s = p.slides.add(); title(s, "Bug #7：reloc_root 引用先挂接，第一次提交失败后直接进入清理出口", 9, "CASE 01 · BTRFS RELOCATION RECOVERY");
  stage(s, 1, "读取恢复根", "4128–4135：读取 reloc_root，并加入本地 reloc_roots 列表。", 48, 162, 330);
  stage(s, 2, "建立持久挂接", "4196–4214：取得 fs_root，__add_reloc_root() 后 grab 引用写入 fs_root->reloc_root。", 475, 162, 330);
  stage(s, 3, "提交失败跳转", "4217–4219：btrfs_commit_transaction() 返回错误，goto out_unset。", 902, 162, 330);
  callout(s, "关键状态写入", "fs_root->reloc_root = btrfs_grab_root(reloc_root);", 48, 414, 560, 150, true);
  callout(s, "关键失败边", "ret = btrfs_commit_transaction(trans);\nif (ret) goto out_unset;", 672, 414, 560, 150);
  textBox(s, "问题不在“有没有 goto”，而在 goto 之后的清理集合是否覆盖刚刚发布到 fs_root 的引用。", 48, 606, 1184, 38, { size: 22, bold: true });
  notes(s, "先讲因果链，不急着讲动态结果：attach 发生在提交之前，提交失败让控制直接进入 out_unset。", ["linux-sources/linux-v6.14-fs/fs/btrfs/relocation.c", "outputs/confirmed_bugs.md"]);

  // 10
  s = p.slides.add(); title(s, "Bug #7 源码：写入发生在循环内，失败边发生在循环之后", 10, "CASE 01 · SOURCE WALKTHROUGH");
  codeBlock(s, bug7Attach, 48, 145, 805, 512, "fs/btrfs/relocation.c · 4185–4219", 15.4);
  callout(s, "① 获取 owner", "4196–4203：fs_root 获取失败时，reloc_root 会重新放回本地列表；这条路径有显式回收线索。", 885, 145, 347, 142);
  callout(s, "② 发布引用", "4213：grab_root() 增加引用，并把指针存入 fs_root->reloc_root。之后本地 list 已经为空。", 885, 309, 347, 142, true);
  callout(s, "③ 提交失败", "4217–4219：commit 失败时只知道跳到 out_unset；必须检查该出口是否反向清除已挂接引用。", 885, 473, 347, 184);
  notes(s, "逐行讲 4200 与 4213 的差异：前者仍把对象放回本地列表，后者已经转移到 fs_root 字段；因此后续 free_reloc_roots() 无法覆盖它。", ["linux-sources/linux-v6.14-fs/fs/btrfs/relocation.c"]);

  // 11
  s = p.slides.add(); title(s, "Bug #7 清理出口释放局部控制对象，却没有显式清空已挂接字段", 11, "CASE 01 · RESIDUAL CALCULATION");
  codeBlock(s, bug7Cleanup, 48, 145, 620, 500, "fs/btrfs/relocation.c · 4231–4252", 16.2);
  callout(s, "E_f", "ATTACH(fs_root->reloc_root, reloc_root)\nsite = relocation.c:4213", 704, 145, 528, 105);
  callout(s, "C_f", "unset_reloc_control / free_reloc_control / free_reloc_roots\n均未指向 fs_root->reloc_root", 704, 266, 528, 124);
  callout(s, "T_f", "提交失败不等同于字段引用被事务接管；当前路径也没有 owner teardown 证明。", 704, 406, 528, 105);
  callout(s, "R_f", "ATTACH(fs_root->reloc_root, reloc_root) 仍然存活\n⇒ FUNCTION_BOUNDARY_RESIDUAL", 704, 527, 528, 118, true);
  notes(s, "free_reloc_roots 只能释放仍在局部 reloc_roots 列表中的根。4213 之后对象已经不在该列表，而是挂到 fs_root 字段。", ["linux-sources/linux-v6.14-fs/fs/btrfs/relocation.c", "docs/METADATA_RESIDUAL_ARCHITECTURE.md"]);

  // 12
  s = p.slides.add(); title(s, "Bug #7 的动态证据把静态残差推进为已确认缺陷", 12, "CASE 01 · FAULT INJECTION");
  metric(s, 48, 158, 350, "25", "残留 roots", "recover_noabort 注入结果");
  metric(s, 430, 158, 350, "reloc_refs = 1", "引用仍在", "失败返回后未归零");
  metric(s, 812, 158, 420, "fs_error = 0", "非全局错误清理", "排除依赖 FS_ERROR 的解释");
  codeBlock(s, [
    "// 修复方向：在 recovery failure path 上对已挂接 root 做对称释放",
    "for_each_attached_reloc_root(fs_root) {",
    "    reloc_root = fs_root->reloc_root;",
    "    fs_root->reloc_root = NULL;",
    "    btrfs_put_root(reloc_root);",
    "}",
    "",
    "// 要验证的后置条件",
    "assert(fs_root->reloc_root == NULL);",
    "assert(reloc_refs == 0);",
  ].join("\n"), 48, 352, 690, 250, "PATCH INTENT · 对称撤销（示意）", 18);
  callout(s, "证据结论", "故障注入未出现 dropping reloc_root 日志；补丁已进入 Btrfs for-next。材料不把它表述为已合入 Linus mainline。", 778, 352, 454, 250, true);
  notes(s, "这里区分静态分析与动态确认：静态分析定位缺口，QEMU 注入证明引用确实跨越失败出口，维护者 for-next 接受提供外部审查证据。示意代码表达修复意图，不等同于原始补丁逐字内容。", ["outputs/confirmed_bugs.md", "outputs/linux-v6.8/btrfs/recover_relocation_qemu_report.md", "linux-sources/linux-v6.14-fs/fs/btrfs/relocation.c"]);

  // 13
  s = p.slides.add(); title(s, "Bug #4 源码：第一次 -ENOSPC 降低目标后，控制回到 retry", 13, "CASE 02 · EXT4 XATTR RETRY");
  codeBlock(s, bug4Retry, 48, 145, 792, 512, "fs/ext4/xattr.c · 2776–2848", 15.4);
  callout(s, "首次尝试", "2837–2840：make_inode_space() 返回 -ENOSPC，error 保存这次失败。", 872, 145, 360, 140);
  callout(s, "降级策略", "2841–2845：把 new_extra_isize 降为 s_min_extra_isize，然后 goto retry。", 872, 308, 360, 140, true);
  callout(s, "第二次成功入口", "2797–2799：较小目标可能直接满足 ifree >= isize_diff，从而 goto shift。", 872, 471, 360, 186);
  notes(s, "这类 Bug 的难点是 loop/retry 语义：同一变量 error 跨迭代携带值，而元数据状态可能在后续迭代成功。", ["linux-sources/linux-v6.14-fs/fs/ext4/xattr.c", "outputs/confirmed_bugs.md"]);

  // 14
  s = p.slides.add(); title(s, "Bug #4 源码：i_extra_isize 已更新，但函数仍可能沿 cleanup 返回旧错误", 14, "CASE 02 · STATE / OUTCOME DIVERGENCE");
  codeBlock(s, bug4Return, 48, 145, 720, 490, "fs/ext4/xattr.c · 2849–2866", 17);
  callout(s, "状态语义", "2851–2855 执行条目移动并写入：\nEXT4_I(inode)->i_extra_isize = new_extra_isize", 804, 145, 428, 160, true);
  callout(s, "返回语义", "2866 直接 return error。若 fallback 成功前没有清掉第一次 -ENOSPC，调用者收到失败。", 804, 329, 428, 160);
  callout(s, "残差类型", "这不是传统资源泄漏，而是 metadata_state_divergence：实际状态 = 成功，API outcome = 失败。", 804, 513, 428, 122);
  notes(s, "强调这是 outcome residual：状态已经改变，返回值却否认改变。上层可能重试、回滚或向用户报告错误，从而产生二次影响。", ["linux-sources/linux-v6.14-fs/fs/ext4/xattr.c", "outputs/confirmed_bugs.md"]);

  // 15
  s = p.slides.add(); title(s, "Bug #4 修复只需清理一次旧值，但验证必须覆盖状态与返回值", 15, "CASE 02 · FIX AND REPRODUCTION");
  codeBlock(s, [
    "if (error == -ENOSPC && !tried_min_extra_isize &&",
    "    s_min_extra_isize) {",
    "    tried_min_extra_isize++;",
    "    new_extra_isize = s_min_extra_isize;",
    "",
    "    error = 0;          // 清除上一轮失败结果",
    "    goto retry;",
    "}",
    "",
    "// 验证不变量",
    "fallback_succeeded  => i_extra_isize == s_min_extra_isize",
    "fallback_succeeded  => return_value == 0",
  ].join("\n"), 48, 154, 642, 390, "PATCH CORE · clear stale error before retry", 18.5);
  metric(s, 730, 154, 230, "802", "修复前失败数", "FS_IOC_FSSETXATTR");
  metric(s, 990, 154, 242, "86", "修复后失败数", "同一复现配置");
  callout(s, "复现条件", "ext4 / 1 KiB block / 256-byte inode / project quota / min_extra_isize 与 want_extra_isize = 32", 730, 344, 502, 200);
  textBox(s, "下降 716 次失败不是“全部问题消失”，而是 stale error 这一条路径被显著消除。", 48, 586, 1184, 42, { size: 22, bold: true });
  notes(s, "修复补丁在 fallback retry 前清零 error。802→86 是补丁复现记录，不应解读为剩余 86 次都属于同一 Bug。", ["outputs/confirmed_bugs.md", "linux-sources/linux-v6.14-fs/fs/ext4/xattr.c"]);

  // 16
  s = p.slides.add(); title(s, "Btrfs sprout 先发布拓扑、指针和计数，再执行可能失败的持久化步骤", 16, "CASE 03 · MULTI-DOMAIN ROLLBACK");
  codeBlock(s, sproutPublish, 48, 145, 752, 512, "fs/btrfs/volumes.c · 2863–2903", 15.8);
  callout(s, "拓扑", "btrfs_setup_sprout() 改变 fs_devices 组织与 fsid 语义。", 836, 145, 396, 120);
  callout(s, "活跃指针", "latest_dev / s_bdev 等 active device 关系被切到新设备。", 836, 286, 396, 120, true);
  callout(s, "计数与 super", "device lists、num/open/rw/total、free_chunk_space 和 superblock 计数一起更新。", 836, 427, 396, 150);
  textBox(s, "发布面越多，错误出口需要恢复的不变量就越多；只按行号附近做局部删除必然不完整。", 836, 598, 396, 52, { size: 18, bold: true });
  notes(s, "2863–2903 是发布阶段：多个 owner 和容器同时改变。这个案例直接检验分析器的 identity-aware cancellation 与 owner 关系建模。", ["linux-sources/linux-v6.14-fs/fs/btrfs/volumes.c", "outputs/confirmed_bugs.md"]);

  // 17
  s = p.slides.add(); title(s, "Sprout 后续三处都可能失败，而 error_sysfs 只回滚设备列表与部分计数", 17, "CASE 03 · FAILURE AND PARTIAL CLEANUP");
  codeBlock(s, sproutFailCleanup, 48, 145, 780, 512, "fs/btrfs/volumes.c · 2918–3011", 15.2);
  callout(s, "失败点", "init_first_rw_device()\nbtrfs_add_dev_item()\nbtrfs_finish_sprout()", 862, 145, 370, 170, true);
  callout(s, "明确回滚", "dev_list / alloc_list、设备计数、free_chunk_space、super total/num devices。", 862, 338, 370, 150);
  callout(s, "未覆盖域", "transaction update list、active device pointers、sprout fs_devices topology。", 862, 511, 370, 146);
  notes(s, "对照发布与清理两段代码：error_sysfs 有很多减法，但这些减法只覆盖同一 owner 的局部字段，不能自动证明 topology 与 active pointer 已恢复。", ["linux-sources/linux-v6.14-fs/fs/btrfs/volumes.c", "outputs/confirmed_bugs.md"]);

  // 18
  s = p.slides.add(); title(s, "同一条失败链形成三个独立残差域，对应 #16–#18 三个 Bug", 18, "CASE 03 · THREE RESIDUAL DOMAINS");
  callout(s, "#16 · 事务更新链", "残差：device->post_commit_list 仍挂在 transaction update list。\n后果：设备释放后链表仍引用它，触发 WARN / UAF 风险。", 48, 164, 360, 330);
  callout(s, "#17 · 活跃设备指针", "残差：latest_dev / s_bdev 指向失败并将被释放的 device。\n后果：后续访问可能出现 NULL 解引用或已释放对象访问。", 460, 164, 360, 330, true);
  callout(s, "#18 · Sprout 容器状态", "残差：fs_devices 已完成 sprout 切换，但错误出口没有恢复 seed/sprout 关系。\n后果：拓扑与持久化状态不一致，可能触发 kernel BUG。", 872, 164, 360, 330);
  textBox(s, "完整回滚条件", 48, 535, 190, 34, { size: 21, bold: true });
  textBox(s, "detach transaction list  ∧  restore active pointers  ∧  rollback sprout topology  ∧  restore counters", 256, 535, 976, 34, { size: 20, bold: true, mono: true });
  textBox(s, "三个补丁不是重复修复，而是在不同 owner / container identity 上补齐互不替代的不变量。", 48, 600, 1184, 40, { size: 22, bold: true });
  notes(s, "#16–#18 共用一条失败链，但 residual root 不同，因此形成三个独立 Bug 记录和三补丁系列。", ["outputs/confirmed_bugs.md", "linux-sources/linux-v6.14-fs/fs/btrfs/volumes.c"]);

  // 19
  s = p.slides.add(); title(s, "三组案例对应三种残差模式，检验架构的不同能力", 19);
  const compareRows = [
    ["Bug #7 · Btrfs relocation", "悬挂引用", "fs_root->reloc_root", "commit failure", "字段引用未对称释放"],
    ["Bug #4 · Ext4 xattr", "状态 / 返回分歧", "i_extra_isize + error", "fallback retry", "状态成功但返回旧错误"],
    ["Bug #16–#18 · Btrfs sprout", "跨域部分回滚", "list / pointer / topology", "late device-add failure", "多个 owner 不变量未恢复"],
  ];
  const compareCols = [48, 332, 520, 770, 998];
  ["案例", "残差类型", "关键身份", "失败边", "清理缺口"].forEach((h, i) =>
    textBox(s, h, compareCols[i], 166, i === 0 ? 260 : 210, 30, { size: 18, bold: true }),
  );
  box(s, 48, 204, 1184, 2, BLACK, BLACK);
  compareRows.forEach((r, ri) => {
    const y = 226 + ri * 106;
    if (ri === 1) box(s, 48, y - 14, 1184, 82, BLACK, BLACK);
    r.forEach((v, i) => textBox(s, v, compareCols[i], y, i === 0 ? 268 : 215, 54, {
      size: i === 0 ? 19 : 17.5,
      bold: i === 0,
      color: ri === 1 ? WHITE : BLACK,
    }));
  });
  callout(s, "架构要求", "引用残差需要 owner identity；重试残差需要跨迭代 outcome 语义；多域回滚需要同时建模容器、活跃指针和拓扑 owner。", 48, 558, 1184, 92, true);
  notes(s, "横向比较三个案例：它们不是同一种规则的重复命中，而是分别检验引用身份、控制流重试和多 owner 回滚能力。", ["outputs/confirmed_bugs.md", "linux-sources/linux-v6.14-fs/fs/btrfs/relocation.c", "linux-sources/linux-v6.14-fs/fs/ext4/xattr.c", "linux-sources/linux-v6.14-fs/fs/btrfs/volumes.c"]);

  // 20
  s = p.slides.add(); title(s, "架构的关键不是命中更多规则，而是保存完整因果关系", 20);
  stage(s, 1, "以失败点为锚", "先确定具体失败调用和错误出口，再讨论哪些状态写入能够到达这里。", 48, 164, 520);
  stage(s, 2, "以对象身份匹配回滚", "取消必须与原效果共享 Root、Key、Plane 和 Value；名称相似不足以证明回滚。", 712, 164, 520);
  stage(s, 3, "以出口分区约束摘要", "分支特有的 cleanup、abort 或 shutdown 不得被提升为所有错误出口的共同保证。", 48, 382, 520);
  stage(s, 4, "以证据边界约束结论", "函数边界残差、owner 活性、动态影响和 confirmed bug 是逐层增强的不同结论。", 712, 382, 520);
  callout(s, "最终结论", "SE_EOD 将“看起来没清理”转化为可复核结论：对象发生了什么效果、经过哪条失败路径、哪些逆操作没有覆盖、错误退出时还剩什么。", 48, 548, 1184, 118, true);
  notes(s, "结尾回到方法本身：路径、身份、分区和证据边界共同构成可审计的 Bug 解释。", ["docs/METADATA_RESIDUAL_ARCHITECTURE.md", "src/metadata_residual.py", "src/function_summary.py", "outputs/confirmed_bugs.md"]);

  for (const [i, slide] of p.slides.items.entries()) {
    const stem = `slide-${String(i + 1).padStart(2, "0")}`;
    const png = await p.export({ slide, format: "png", scale: 1 });
    await fs.writeFile(`${RENDER_DIR}/${stem}.png`, new Uint8Array(await png.arrayBuffer()));
    const layout = await slide.export({ format: "layout" });
    await fs.writeFile(`${LAYOUT_DIR}/${stem}.layout.json`, await layout.text(), "utf8");
  }
  const montage = await p.export({ format: "webp", montage: true, scale: 1 });
  await fs.writeFile(`${ROOT}/.codex-ppt-v2/final-montage.webp`, new Uint8Array(await montage.arrayBuffer()));
  const pptx = await PresentationFile.exportPptx(p);
  await pptx.save(OUT);
  console.log(`Wrote ${OUT}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
