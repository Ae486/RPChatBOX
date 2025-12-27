# OWUI Pages 风格统一（Pages + Overlays）实施计划

> 创建时间：2025-12-26  
> 状态：Draft（待你审查确认后开始编码）  
> 目标：在已完成的 Chat V2（OWUI 基础风格 + 树状消息链）之上，把 `lib/pages/*` 与常见 overlays（Dialog/SnackBar/Menu/Drawer）统一到 OpenWebUI 风格（灰阶 + 细边框 + 大圆角 + prose + hover 克制）。

---

## 0. 背景与当前基线

### 0.1 已有基础（本仓库现状）

- OWUI tokens 已落地：`lib/chat_ui/owui/owui_tokens.dart` + `lib/chat_ui/owui/owui_tokens_ext.dart`，并在 `lib/main.dart` 注入 `ThemeData.extensions`（`context.owuiColors/owuiRadius/owuiSpacing` 可用）。
- Chat V2 已部分 OWUI 风格化：`lib/widgets/conversation_view_v2.dart` + `lib/chat_ui/owui/*`（assistant 无气泡输出、用户气泡 24px 圆角、prose/稳定流式渲染）。
- OpenWebUI 证据来源已固化（本地快照）：`docs/research/open-webui-main`（UI scale、gray850、prose、scrollbar、OLED dark、hover reveal 等）。

### 0.2 当前问题（需要统一的主要入口）

- Pages 仍混用 Material/Apple 风格：大量 `AlertDialog`/默认 `SnackBar`/`PopupMenuButton`/`inversePrimary` AppBar、以及 `Colors.grey.shade*`/硬编码 padding/radius（示例：`lib/pages/settings_page.dart`、`lib/pages/search_page.dart`、`lib/pages/model_services_page.dart`、`lib/pages/chat_page.dart`）。
- 全局 overlays 仍是 Apple blur 路线：`lib/widgets/conversation_drawer.dart`、`lib/widgets/apple_dialog.dart`、`lib/widgets/apple_toast.dart` 等。
- OWUI 组件壳缺失：尚未形成可复用的 `OwuiScaffold/OwuiCard/OwuiDialog/OwuiSnackBar/OwuiMenu/...`，导致 pages 迁移会反复“页面内写样式”。

---

## 1. 目标与约束

### 1.1 目标（必须达成）

1) **统一入口**：pages 与 overlays 统一从 `OwuiTokens (ThemeExtension)` 取色/圆角/间距（禁止新增灰阶硬编码）。  
2) **先组件壳再迁移**：先沉淀 6~10 个高复用组件壳，再分批替换 pages。  
3) **Chat V2 不回退**：保持“assistant 无气泡输出”与现有流式稳定策略不受影响。  
4) **亮/暗一致可读**：至少保证 light/dark 下页面背景、卡片、边框、正文/次级文字对比清晰。  

### 1.2 约束（迁移规则）

- 新增/改动的 UI 代码禁止再出现：`Colors.grey.shade*` / `Color(0x...)`（tokens 定义处除外）。
- AppBar 迁移时避免 `inversePrimary` 这类“整条上色”背景，优先：同背景 + subtle bottom border。
- 成功/错误提示不使用整块绿/红背景；语义色仅作小面积强调（OpenWebUI 风格）。

---

## 2. 设计口径（来自 OpenWebUI 的可移植规则）

> 口径文档：`docs/ui-rearchitecture/08-OPENWEBUI_STYLE_GUIDE.md`、`docs/ui-rearchitecture/08-OPENWEBUI_STYLE_WEB_RESEARCH.md`

### 2.1 Tokens（最小集合）

- gray50..950（含 gray850）：已在 `OwuiPalette` 与 `OwuiTokens` 对齐。
- 语义色（light/dark）：`pageBg/surface/surface2/surfaceCard/borderSubtle/borderStrong/textPrimary/textSecondary/hoverOverlay`（已在 `OwuiTokens` 覆盖）。
- 圆角：`rLg=8/rXl=12/r3xl=24/rFull=9999`（已在 `OwuiTokens` 覆盖）。
- 间距：从 `OwuiTokens.spacing` 派生，并受 `uiScale` 影响（已实现）。

### 2.2 交互规则（桌面端关键）

- hover 才显示辅助操作（时间戳/按钮等）：优先用于 pages 的 icon button / menu 项；聊天区后续再补齐（不在本计划首批强制）。
- icon button hover overlay：light `black 5%`，dark `white 5%`（对应 `OwuiTokens.colors.hoverOverlay`）。
- 输入框 focus/hover：优先“边框加深/对比增强”，避免彩色描边大面积出现。

---

## 3. 总体实施策略（分阶段）

### Phase 0：基线确认（仅校验，不做大范围改动）

**目标**：确保 OWUI tokens 已可在任意页面取用，并明确迁移“唯一入口”。

**动作**：
- [ ] 确认 `context.owui*` 在 pages 内可用（亮/暗均可）。
- [ ] 明确 `OwuiPalette` 仅作为 gray primitives，pages 不再直接依赖 `OwuiPalette.*(context)`（除非极少数 legacy）。

**验收**：
- [ ] `dart analyze` 无 error；Chat V2 可正常运行。

### Phase 1：OWUI 组件壳（优先覆盖 pages + overlays）

**目标**：把“页面骨架 + 弹层 + 菜单 + 提示”的样式固定为可复用组件，避免每个 page 重复写样式。

**新增目录**：`lib/chat_ui/owui/components/*`

**组件清单（最小集合）**：

1) `OwuiScaffold`
- 统一 `scaffoldBackgroundColor`、默认页面 padding（可选）、divider/border 口径。
- 提供 `OwuiAppBar` 的默认组合（可选）。

2) `OwuiAppBar`
- 默认同背景/透明；底部 subtle border；统一 title/leading/actions density。

3) `OwuiCard` / `OwuiSection`
- `surfaceCard + borderSubtle`；圆角按层级（常用 12/16，主容器可选 24）。
- 支持“无阴影 / 极弱阴影”策略（默认无阴影）。

4) `OwuiDialog`
- 统一 `AlertDialog`：背景=surface、边框=subtle、圆角=12/16；按钮样式克制；不引入 Apple blur。

5) `OwuiSnackBar`
- 统一提示：灰阶 surface + subtle border；success/error 使用左侧小标记或小面积 icon/点缀（避免整块红绿底）。

6) `OwuiMenu`（PopupMenu）
- 统一 shape/colors/density；支持常用 `PopupMenuButton` 替换。

7) （可选）`OwuiTextField` / `OwuiSearchField`
- 统一输入框高度/padding/radius/border/focus-within；供 Search/AppBar 使用。

**验收**：
- [ ] `dart analyze` 无 error；至少在 `SettingsPage` 或 `SearchPage` 里落地 1 个组件。
- [ ] 新增组件代码不出现 `Colors.grey.shade*` / `Color(0x...)`（tokens 定义处除外）。

### Phase 2：Pages 分批迁移（每页最多 3-5 个改动点）

> 目标：用 Phase 1 的组件壳逐页替换“最显眼、最不一致”的 UI。

**优先顺序**：

1) `lib/pages/settings_page.dart`（试点）
- [ ] “清除图片缓存”确认弹窗：`AlertDialog -> OwuiDialog`
- [ ] 清除成功/失败提示：默认 `SnackBar(红/绿底) -> OwuiSnackBar`
- [ ] 页面卡片/间距：`Card/SizedBox` 迁移为 `OwuiCard`/tokens（避免硬编码 `TextStyle(color: Colors.grey)`）

2) `lib/pages/search_page.dart`
- [ ] AppBar 搜索框：迁移为 `OwuiSearchField`（或 Owui 口径输入框）
- [ ] Empty/NoResults：灰阶从 tokens 获取（移除 `Colors.grey.shade*`）
- [ ] 预览弹窗：`AlertDialog -> OwuiDialog`

3) `lib/pages/chat_page.dart`
- [ ] `PopupMenuButton`：统一为 `OwuiMenu`（shape/colors/density）
- [ ] 重命名/清空/统计/主题 Dialog：逐步迁移为 `OwuiDialog`
- [ ] AppleToast：规划替换口径（短期可保留，新增入口改走 Owui）

4) `lib/pages/model_services_page.dart`
- [ ] AppBar：移除 `inversePrimary` 强色背景，改 `OwuiAppBar`
- [ ] Empty state：灰阶用 tokens（移除 `Colors.grey.shade*`）
- [ ] BottomBar：shadow/背景/分隔线统一（OWUI 轻阴影或无阴影）

5) `lib/pages/provider_detail_page.dart` / `lib/pages/custom_roles_page.dart`
- 作为后续批次：AppleTokens 依赖多，需拆分提交逐步迁移。

**每批验收（强制）**：
- [ ] App 可编译运行（至少本地 `flutter run` 级别通过）。
- [ ] `dart analyze` 无 error。
- [ ] 迁移页新增代码不出现灰阶硬编码（tokens 定义处除外）。

### Phase 3：全局 overlays 收敛（Drawer/Dialog/Toast）

**目标**：把用户高频入口的 overlay 统一视觉口径，减少 Apple 风格残留。

1) Drawer：`lib/widgets/conversation_drawer.dart`
- [ ] 背景：OWUI pageBg/surface；去 blur 或降级为轻微透明（待你确认取舍）
- [ ] 分组卡片：`OwuiCard` 风格（borderSubtle + 圆角）

2) Dialog：`lib/widgets/apple_dialog.dart`
- [ ] 明确定位：标记 legacy，仅保留 ActionSheet 能力；或提供 Owui 对应替代入口。

3) Toast：`lib/widgets/apple_toast.dart` / `lib/utils/global_toast.dart`
- [ ] 统一提示视觉与调用入口（与 `OwuiSnackBar` 分工：页内 vs 全局）。

**验收**：
- [ ] ChatPage 的 drawer/menu/dialog 在 light/dark 下观感一致。

### Phase 4（可选）：UI Scale / Theme 可配置化

> 说明：本仓库 tokens 已包含 `uiScale`，但当前未提供设置入口与持久化。

- [ ] Settings 新增「界面设置」区：UI Scale（建议 0.85~1.25 step 0.05 或对齐 OpenWebUI 1.0~1.5）
- [ ] `ThemeData.textTheme.apply(fontSizeFactor: scale)` + `OwuiTokens.(light/dark)(uiScale: scale)` 注入
- [ ] 确保 spacing/radius 也随 scale 派生（避免“字大但布局紧”）

---

## 4. 研发执行方式（提交策略）

- 每个 phase 拆分为多个小 patch：优先“可编译 + 可回滚”。
- pages 迁移每个页面最多 3~5 个改动点，避免一次性大改引入回归。
- 任何新增组件/公共能力：先在 `specs/ui-rearchitecture/*` 更新对应说明（本文件作为总入口）。

---

## 5. 验证策略

- 静态检查：`dart analyze`（必须无 error）。
- 最小回归：`flutter test test\\unit`（若环境可运行）。
- 手测清单：
  - Settings：清缓存确认弹窗 + 成功/失败提示
  - Search：搜索框 + 空态 + 预览弹窗 + 跳转
  - Chat：菜单 + 对话框 + Drawer
  - Model Services：空态 + 列表 + bottom bar
  - light/dark 各验一次

---

## 6. 已确认（本轮执行口径）

1) Drawer：采用方案 A（完全 OWUI）
- 去除 blur / BackdropFilter / 透明玻璃感
- 使用 `OwuiTokens` 的 `pageBg/surface/surfaceCard + borderSubtle` 作为背景与边框

2) Apple*：一次性替换为 OWUI
- `AppleDialog` / `AppleToast` / `AppleIcons` / `AppleTokens` 等：页面与核心组件中不再使用
- Dialog / Sheet：统一用 `OwuiDialog`（必要时补 `OwuiSheet`）
- Toast / 提示：统一用 `OwuiSnackBars`（必要时补 `OwuiToast` 全局 overlay）

3) Icons：使用 Lucide
- 引入 `lucide_icons`，并统一通过 `OwuiIcons` 间接引用（便于后续替换/主题化）

4) UI Scale：全局缩放（字体 + 控件 + 间距）
- `uiScale` 同时影响：字体（包括代码字体）、按钮/输入框 paddings、圆角、间距等（不使用 `Transform.scale`，避免点击区域错位）
- 默认 `1.0`，范围建议先用 `0.85~1.25`（可再调）

---

## 7. 本轮“开始开发”门槛（已满足）

- [x] 组件壳命名统一为 `Owui*`
- [x] Drawer 方向确认：方案 A（无 blur）
- [x] Apple* 策略确认：一次性替换为 OWUI
- [x] 新增“显示设置”入口：Settings -> Display Settings（UI scale / 字体）
