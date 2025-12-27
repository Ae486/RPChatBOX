# OpenWebUI 风格主题调研（源码对照 + Tokens/规则抽取）

> 目标：借鉴 OpenWebUI 的“灰阶 + 简洁 + 细边框 + 大圆角 + prose + hover 克制”风格，形成可直接落地到 Flutter（本项目 `pages` 为主）的 tokens/交互规则口径。
>
> 重要约束：我们不是照搬 OpenWebUI Web 端组件；组件实现应以本项目 `lib/pages/*` 功能需求为准，仅借鉴其设计语言与一致性策略。

## 1. 调研范围与结论可信度

- 最终真相优先级：OpenWebUI 源码（本地快照） > 官方 repo/发布说明 > 官方 docs > 讨论/issue > 第三方文章。
- 本次 Phase 2 基于本地源码快照：`H:/chatboxapp/docs/research/open-webui-main`。
  - repo commit：`21a2b38148302fc597470e5fb3ba01dfe78d6838`

## 2. 权威来源清单（可复查）

### 2.1 官方仓库/文档

- GitHub Repo：`open-webui/open-webui`
  - https://github.com/open-webui/open-webui
- Releases（UI scale 入口与范围）
  - https://github.com/open-webui/open-webui/releases
- CHANGELOG（Interface Settings text scale 修复）
  - https://github.com/open-webui/open-webui/blob/main/CHANGELOG.md
- Features（Theme customization、背景）
  - https://docs.openwebui.com/features/

### 2.2 本地源码快照（本次 Phase 2 的主要证据）

- UI scale / prose / scrollbar：`H:/chatboxapp/docs/research/open-webui-main/src/app.css`
- gray palette：`H:/chatboxapp/docs/research/open-webui-main/tailwind.config.js`
- UI scale 设置页（slider + 持久化）：`H:/chatboxapp/docs/research/open-webui-main/src/lib/components/chat/Settings/Interface.svelte`
- 写入 CSS 变量：`H:/chatboxapp/docs/research/open-webui-main/src/lib/utils/text-scale.ts`
- 启动时应用 textScale：`H:/chatboxapp/docs/research/open-webui-main/src/routes/+layout.svelte`
- theme/OLED 与 custom.css 注入：`H:/chatboxapp/docs/research/open-webui-main/src/app.html`
- `/static/custom.css` 默认文件：`H:/chatboxapp/docs/research/open-webui-main/backend/open_webui/static/custom.css`

## 3. Phase 2A 关键发现（可直接落地的规则）

### 3.1 UI Scale（全局缩放）

- CSS 变量：`--app-text-scale`（默认 1）。
- 生效方式：`html { font-size: calc(1rem * var(--app-text-scale, 1)); }`。
- 写入方式：`document.documentElement.style.setProperty('--app-text-scale', `${scale}`)`。
- UI 控件：Interface Settings 的 range slider，`min=1` `max=1.5` `step=0.01`；并提供 ±0.1 的按钮。
- 持久化：存入用户 settings 的 `textScale`；`null` 表示默认（在保存前会将 `1` 折叠为 `null`）。

### 3.2 灰阶色板（gray50..950 含 gray850）

- Tailwind 颜色以 CSS variable + fallback 的方式定义：
  - `gray.850 = var(--color-gray-850, #262626)`
  - `gray.950 = var(--color-gray-950, #0d0d0d)`
- darkMode 使用 class：`darkMode: 'class'`，即 `.dark`。

### 3.3 主题模式（Light/Dark/OLED Dark）

- OLED Dark 不是独立一套 class，而是“仍使用 `.dark`” + 覆盖 `--color-gray-800/850/900/950`（更接近纯黑）。
- theme 的 class/变量初始化在 `src/app.html` 内联脚本中完成（避免 FOUC）。

### 3.4 prose（Markdown/Input 排版观感）

- `.markdown-prose`：核心原则是“段落与列表 margin 近乎为 0”，标题紧凑，blockquote 左侧细边框，`whitespace-pre-line`。
- `.input-prose`：输入区域（富文本/编辑器）也走 prose 规则，且段落 `my-1`（比消息略松一点）。

### 3.5 Scrollbar

- thumb：light `rgba(215, 215, 215, 0.6)`；dark `rgba(67, 67, 67, 0.6)`。
- 圆角：`9999px`；尺寸：`0.45rem`。

### 3.6 Custom CSS（custom.css）

- Web 端会固定注入 `<link rel="stylesheet" href="/static/custom.css" ... />`。
- 默认 `backend/open_webui/static/custom.css` 存在但为空。
- 结论：OpenWebUI 允许以“部署级覆盖”的方式做 CSS 定制（不依赖 UI 内置编辑器）。

## 4. Tokens 表（建议用于 Flutter ThemeExtension / Design Tokens）

> 下表是“可移植”的 tokens：不绑定 Web 技术细节，而是绑定视觉意图。

### 4.1 Gray Palette（基础色板）

来源：`H:/chatboxapp/docs/research/open-webui-main/tailwind.config.js`

| Token     | Fallback Hex | 说明                     |
| --------- | -----------: | ------------------------ |
| `gray50`  |    `#f9f9f9` | light surface 常用       |
| `gray100` |    `#ececec` | 边框/分隔线常用          |
| `gray200` |    `#e3e3e3` | hover 边框加强           |
| `gray300` |    `#cdcdcd` | 次级边框                 |
| `gray400` |    `#b4b4b4` | disabled/提示            |
| `gray500` |    `#9b9b9b` | muted 文本               |
| `gray600` |    `#676767` | 次级文本                 |
| `gray700` |    `#4e4e4e` | 深色文本/描边            |
| `gray800` |    `#333333` | dark 层级/高对比文本背景 |
| `gray850` |    `#262626` | dark surface card 常用   |
| `gray900` |    `#171717` | dark page 背景           |
| `gray950` |    `#0d0d0d` | 极深背景/阴影层          |

### 4.2 OLED Dark 覆盖（灰阶变量覆盖）

来源：`H:/chatboxapp/docs/research/open-webui-main/src/app.html`

| Token              | OLED 覆盖值 |
| ------------------ | ----------: |
| `--color-gray-800` |   `#101010` |
| `--color-gray-850` |   `#050505` |
| `--color-gray-900` |   `#000000` |
| `--color-gray-950` |   `#000000` |

Flutter 映射建议：提供一个 `themeVariant`（normal dark vs oled dark），对 `OwuiPalette` 的 `gray850/900/950` 做二次覆盖。

### 4.3 语义色（建议字段）

来源：多处 class 使用（如 `bg-white dark:bg-gray-850`，`text-gray-400` 等）

| Semantic Token | Light               | Dark                | 用途               |
| -------------- | ------------------- | ------------------- | ------------------ |
| `pageBg`       | `white`             | `gray900`           | Scaffold 背景      |
| `surface`      | `gray50`            | `gray850`           | Card/Input surface |
| `surface2`     | `white`             | `gray900`           | 更“贴近背景”的容器 |
| `borderSubtle` | `gray100/30`        | `gray850/30`        | 细边框（主流口径） |
| `borderStrong` | `gray200`           | `gray800`           | hover/focus 加强   |
| `textPrimary`  | `gray900`           | `white`             | 主文本             |
| `textMuted`    | `gray400`~`gray600` | `gray400`~`gray500` | 次级文本           |
| `hoverOverlay` | `black/5`           | `white/5`           | icon hover 背景    |

### 4.4 Border / Divider 透明度口径

来源：`H:/chatboxapp/docs/research/open-webui-main/src/app.css`（以及多处组件 class）

- 常用边框：`border-gray-100/30 dark:border-gray-850/30`
- hover/focus 边框增强：`hover:border-gray-200 focus-within:border-gray-100 hover:dark:border-gray-800 focus-within:dark:border-gray-800`

Flutter 映射建议：

- `borderSubtle = gray100.withOpacity(0.30)`（dark 用 gray850.withOpacity(0.30)）
- `borderHover`/`borderFocus`：直接用更强的灰阶（而不是彩色描边）

### 4.5 Radius（圆角）

来源：组件 class（大量 `rounded-3xl` / `rounded-full`）

| Token   |   px | 用途                         |
| ------- | ---: | ---------------------------- |
| `rLg`   |    8 | code block/局部控件          |
| `rXl`   |   12 | 小卡片/缩略图                |
| `r3xl`  |   24 | 主要容器（输入框/气泡/按钮） |
| `rFull` | 9999 | pill/icon button             |

### 4.6 Typography / Prose 规则（要点）

来源：`H:/chatboxapp/docs/research/open-webui-main/src/app.css`

- `.markdown-prose`：
  - `prose-p:my-0`（段间距极小）
  - `prose-headings:my-1`（标题紧凑）
  - `blockquote`：`border-s-2` + light/dark 不同灰
  - `whitespace-pre-line`
- `.input-prose`：
  - `prose-p:my-1`（输入区略松）

Flutter 映射建议：

- Markdown 的段落/标题间距必须收紧（避免默认过大）；引用块使用“细左边框 + 圆角/轻背景（可选）”。

### 4.7 Scrollbar

来源：`H:/chatboxapp/docs/research/open-webui-main/src/app.css`

| Token             | Light                   | Dark                 |
| ----------------- | ----------------------- | -------------------- |
| `scrollbarThumb`  | `rgba(215,215,215,0.6)` | `rgba(67,67,67,0.6)` |
| `scrollbarSize`   | `0.45rem`               | `0.45rem`            |
| `scrollbarRadius` | `9999px`                | `9999px`             |

### 4.8 Background Image（可选能力）

来源：`H:/chatboxapp/docs/research/open-webui-main/src/lib/components/chat/Settings/Interface.svelte` + `Chat.svelte`

- 允许用户上传 `backgroundImageUrl`（DataURL）并在 Chat 背景使用。
- 叠加层：`bg-linear-to-t from-white to-white/85 dark:from-gray-900 dark:to-gray-900/90`（确保文字可读）。

Flutter 映射建议：

- 如果支持自定义背景：必须强制加一层渐变/遮罩，确保对比度与可读性。

## 5. 交互规则表（hover/focus/active）

### 5.1 Hover 才显示操作（桌面端关键）

来源：如 `Messages/ResponseMessage.svelte` 的 `invisible group-hover:visible transition`。

- 时间戳/复制/编辑/再生成：默认不可见，hover 后显示。
- 高对比模式：会提升可见性（避免 hover 才能看到关键信息）。

Flutter 映射建议：

- 桌面端用 `MouseRegion` + `AnimatedOpacity`/`AnimatedSwitcher` 实现 hover reveal。

### 5.2 Icon Button 的 hover 背景

来源：多处使用 `hover:bg-black/5 dark:hover:bg-white/5`。

Flutter 映射建议：

- 给 `OwuiIconButton` 一个 `hoverOverlay` token（light black 5%，dark white 5%）。

### 5.3 输入框 focus-within 边框

来源：`MessageInput.svelte`：`hover:border-*` / `focus-within:border-*`。

Flutter 映射建议：

- 输入容器在 focus 时优先“加深边框/提高对比”，而不是使用彩色描边。

## 6. Flutter 落地映射建议（按 pages 功能需要写组件）

### 6.1 ThemeExtension 字段建议（最小集合）

- `uiScale`：double
- `palette.gray50..950`（含 gray850），并支持 `oledDarkOverrides`
- `colors`（语义色）：`pageBg/surface/borderSubtle/borderStrong/textPrimary/textMuted/hoverOverlay`
- `radius`：`rLg/rXl/r3xl/rFull`
- `scrollbar`：thumbColor/thickness/radius
- `prose`：用于 Markdown renderer 的 spacing/quote/code 默认规则

### 6.2 基础组件建议（优先覆盖 pages 常见需求）

- `OwuiScaffold`：统一背景与分隔线策略
- `OwuiCard`：surface + borderSubtle + 圆角（默认 12/24 取决于页面层级）
- `OwuiTextField`/`OwuiSearchField`：focus/hover 边框策略统一
- `OwuiButton`/`OwuiIconButton`：hoverOverlay + 圆角策略统一
- `OwuiProse`（或 Markdown wrapper）：统一段落/标题/引用规则

### 6.3 禁止事项（保证长期一致）

- 页面/组件禁止直接使用 `Colors.grey.*`、`Color(0x...)`（除非集中在 tokens 定义处）。
- spacing/radius/fontSize 不允许页面任意写死；统一从 tokens 派生（并响应 `uiScale`）。

## 7. 证据定位（快速索引）

- UI Scale：`H:/chatboxapp/docs/research/open-webui-main/src/app.css`、`H:/chatboxapp/docs/research/open-webui-main/src/lib/utils/text-scale.ts`、`H:/chatboxapp/docs/research/open-webui-main/src/lib/components/chat/Settings/Interface.svelte`、`H:/chatboxapp/docs/research/open-webui-main/src/routes/+layout.svelte`
- Gray palette：`H:/chatboxapp/docs/research/open-webui-main/tailwind.config.js`
- OLED：`H:/chatboxapp/docs/research/open-webui-main/src/app.html`、`H:/chatboxapp/docs/research/open-webui-main/src/lib/components/chat/Settings/General.svelte`
- Prose：`H:/chatboxapp/docs/research/open-webui-main/src/app.css`；使用点：`Messages/ResponseMessage.svelte` / `Messages/UserMessage.svelte`
- Scrollbar：`H:/chatboxapp/docs/research/open-webui-main/src/app.css`
- Custom CSS：`H:/chatboxapp/docs/research/open-webui-main/src/app.html` + `H:/chatboxapp/docs/research/open-webui-main/backend/open_webui/static/custom.css`
