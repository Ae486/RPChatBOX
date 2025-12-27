# OpenWebUI 主题风格说明（对照 + Flutter 落地）

> 目标：抽象出 OpenWebUI 的“灰阶 + 简洁 + 大留白 + 细边框 + 圆角”的可复用风格规范，作为本项目 UI 统一与组件开发的唯一口径。

## 1. 资料来源（本仓库内可追溯）

### 1.1 本项目内对照（用于快速迭代）

- OpenWebUI 本地对照仓库（历史对照）：`.tmp/open-webui/`
- 灰阶色板：`.tmp/open-webui/tailwind.config.js`
- 全局样式与 UI Scale：`.tmp/open-webui/src/app.css`
- 聊天：
  - 用户消息：`.tmp/open-webui/src/lib/components/chat/Messages/UserMessage.svelte`
  - 助手消息：`.tmp/open-webui/src/lib/components/chat/Messages/ResponseMessage.svelte`
  - 输入区：`.tmp/open-webui/src/lib/components/chat/MessageInput.svelte`

### 1.2 OpenWebUI 本地源码快照（本次调研的证据来源）

> 本项目在 `H:/chatboxapp/docs/research/open-webui-main` 保存了一份 OpenWebUI 源码快照；本风格规范的关键数值（UI scale、gray850、scrollbar、prose）以该快照为证据。

- 快照路径：`H:/chatboxapp/docs/research/open-webui-main`
- commit：`21a2b38148302fc597470e5fb3ba01dfe78d6838`
- 关键文件：
  - `H:/chatboxapp/docs/research/open-webui-main/src/app.css`
  - `H:/chatboxapp/docs/research/open-webui-main/tailwind.config.js`
  - `H:/chatboxapp/docs/research/open-webui-main/src/lib/components/chat/Settings/Interface.svelte`
  - `H:/chatboxapp/docs/research/open-webui-main/src/app.html`
  - `H:/chatboxapp/docs/research/open-webui-main/backend/open_webui/static/custom.css`（默认存在但为空）

### 1.3 本项目调研输出（本项目唯一口径）

- 调研总结（tokens/交互规则/Flutter 映射）：`docs/ui-rearchitecture/08-OPENWEBUI_STYLE_WEB_RESEARCH.md`

本项目当前 OpenWebUI 风格实现（Flutter）：

- OWUI 组件集合：`lib/chat_ui/owui/INDEX.md`
- 灰阶色板：`lib/chat_ui/owui/palette.dart`
- ChatTheme 映射：`lib/chat_ui/owui/chat_theme.dart`
- V2 聊天入口：`lib/widgets/conversation_view_v2.dart`

## 2. OpenWebUI 的视觉关键词（可落地）

- 灰阶主导：大部分 UI 基于 gray 50..950，彩色仅做强调（links、状态标识、少量 badge）。
- 轻量分层：页面背景与卡片/输入框通过“稍浅/稍深灰 + 细边框”区分，而不是大阴影。
- 大圆角（rounded-3xl/rounded-full）：聊天气泡与输入容器普遍偏“圆润”。
- prose 观感（Markdown 像文章）：段落间距压缩、标题紧凑、引用细左边框、表格与代码块视觉独立。
- 交互克制：hover 才出现辅助信息与操作按钮（时间戳、复制、编辑等）。
- 全局 UI Scale：通过一个统一尺度同时影响文本与布局密度（Web 端用 CSS 变量 `--app-text-scale`）。

## 3. 设计 Tokens（建议分层：基础色板 -> 语义色 -> 组件样式）

### 3.1 灰阶色板（基础色板）

来源：`.tmp/open-webui/tailwind.config.js`（默认 fallback）

- `gray50` `#f9f9f9`
- `gray100` `#ececec`
- `gray200` `#e3e3e3`
- `gray300` `#cdcdcd`
- `gray400` `#b4b4b4`
- `gray500` `#9b9b9b`
- `gray600` `#676767`
- `gray700` `#4e4e4e`
- `gray800` `#333333`
- `gray850` `#262626`
- `gray900` `#171717`
- `gray950` `#0d0d0d`

Flutter 当前实现：`lib/chat_ui/owui/palette.dart` 已对齐上述值。

### 3.2 语义色（必须统一的颜色口径）

建议语义（light/dark 均需覆盖）：

- `pageBackground`：light=white / dark=gray900
- `surfaceCard`：light=gray50 / dark=gray850
- `borderSubtle`：细边框（OpenWebUI 常见 `border-gray-100/30 dark:border-gray-850/30`）
- `textPrimary`：light=black / dark=white
- `textSecondary`：light=gray600 / dark=gray400
- `focus/hover`：建议以 `primary` 透明叠加或更亮/更暗灰（避免纯彩色大面积铺底）

### 3.3 圆角（OpenWebUI 常用映射）

- `rounded-3xl`：24px（用户气泡、输入容器、部分主按钮）
- `rounded-xl`：12px（缩略图/小卡片/内部容器）
- `rounded-lg`：8px（code block/局部控件）
- `rounded-full`：9999px（pill/圆按钮）

### 3.4 间距与密度

OpenWebUI 常见：输入区整体 padding 紧凑，但区域之间留白较大。

- 组件内 padding：8~12px 常见
- 区域分隔：16~24px 常见

### 3.5 排版（prose 观感）

来源：`.tmp/open-webui/src/app.css`

- `.markdown-prose`：段落 `prose-p:my-0`（几乎不留额外段间距）、标题 `my-1`、引用 `border-s-2`、`whitespace-pre-line`
- `.input-prose*`：输入区也使用 prose 规则以保证预览/富文本一致

Flutter 落地建议：

- Markdown renderer（本项目用 `markdown_widget`）：
  - 段落/标题 margin 需要被“压缩”，避免 Flutter 默认段间距过大
  - 引用块：细左边框 + 浅色背景（可选）
  - 代码块：不要依赖 prose 默认样式；统一交给增强 code block 组件

### 3.6 UI Scale（全局缩放）

来源：`.tmp/open-webui/src/app.css`

- `--app-text-scale` 控制 `html font-size`，从而影响整个 UI（包括 sidebar item sizing 等）。

Flutter 落地建议（必须同时处理字体与布局密度）：

- 文本：`ThemeData.textTheme.apply(fontSizeFactor: uiScale)`
- 布局：spacing/radius 等从 tokens 计算时乘以同一个 `uiScale`
- 交互：命中区域（tap target）不应随 scale 缩小到低于可用阈值

### 3.7 滚动条

来源：`.tmp/open-webui/src/app.css`

- thumb 圆角 9999px
- light：rgba(215,215,215,0.6)
- dark：rgba(67,67,67,0.6)
- 尺寸约 0.45rem（约 7px）

Flutter 当前实现：`lib/main.dart` 的 `ScrollbarThemeData` 已基本对齐（厚度 8px、圆角 999、light/dark thumbColor）。

## 4. 组件级样式规则（落地口径）

### 4.1 页面基础（Scaffold/AppBar）

- 背景：pageBackground（light 白、dark gray900）
- 分隔：用 divider/border（subtle）而非强色背景
- AppBar：尽量避免 `inversePrimary` 这类“整条上色”的背景；更多使用透明/同背景 + 下分隔线

### 4.2 Card/Section

- Card：surfaceCard + borderSubtle + 圆角（12~16）
- Section：标题使用统一 textStyle（标题/说明/辅助信息层级清晰）

### 4.3 输入框与按钮

来自 `MessageInput.svelte`：

- 输入容器：rounded-3xl + border-gray-100/30 + hover/focus 边框更明显
- Icon Button：rounded-full，hover 才出现背景（灰 50/800 透明）
- 主发送按钮：enabled=黑/白反转；disabled=灰

### 4.4 Chat：用户消息 vs 助手消息

来自 `UserMessage.svelte` / `ResponseMessage.svelte`：

- 用户：右侧气泡，最大宽度约 90%，背景 gray50/dark gray850，圆角 24
- 助手：无气泡，全宽 prose；头像/模型名在较大屏幕出现（`@lg:flex`），时间戳 hover 才显示（除高对比模式）

### 4.5 Hover 行为（桌面端关键体验）

- 时间戳、操作按钮默认不可见（或低透明），hover 后显示并带过渡。
- Flutter 对应：`MouseRegion` + `AnimatedOpacity` / `AnimatedSwitcher`。

## 5. 当前 Flutter OWUI 实现对齐检查（结论 + TODO）

### 5.1 已对齐/基本一致

- 灰阶色板：`lib/chat_ui/owui/palette.dart` 与 OpenWebUI tailwind gray 对齐。
- 聊天用户气泡大圆角：`lib/chat_ui/owui/chat_theme.dart` 使用 24px；`lib/widgets/conversation_view_v2/user_bubble.dart` 使用 `OwuiChatTheme.userBubbleDecoration()`。
- 文本渲染主线：`lib/chat_ui/owui/markdown.dart`（`markdown_widget` + stable prefix）符合“prose + 流式稳定”的方向。
- 输入区“两段布局 + 动作栏”：`lib/chat_ui/owui/composer/owui_composer.dart`结构与 OpenWebUI 接近（附件/联网/配置/模型/发送-停止）。

### 5.2 存在差异/需要统一的点（后续开发必须处理）

- 仍存在硬编码颜色（尤其 `const Color(0x...)`、`Colors.grey.shade*`）：
  - `lib/chat_ui/owui/code_block.dart`
  - `lib/chat_ui/owui/mermaid_block.dart`
  - `lib/chat_ui/owui/assistant_message.dart`（Thinking 标题色等）
  - `lib/widgets/conversation_view_v2/build.dart`（scroll-to-bottom 按钮）
- 圆角策略不完全一致：输入容器当前多处使用 16/12，OpenWebUI 更偏 24（rounded-3xl）。
- hover 显示细节与按钮：OpenWebUI 更强调 hover 才出现；Flutter 目前以长按/右键为主，缺少桌面 hover actions（需要补齐）。
- 全局 UI Scale：OpenWebUI 有统一缩放机制；Flutter 目前仅有 ThemeMode，缺少可配置 scale/font/color。

## 6. 迁移落地建议（约束）

- 所有页面与组件：禁止直接使用 `Colors.grey.shade*`、`const Color(0x...)`（除非是“语义 token 的默认值”集中定义处）。
- 新组件/新页面：必须从 tokens（ThemeExtension）取色/间距/圆角。
- OWUI 范围内优先：保持 “OwuiPalette / OwuiTokens -> ThemeData/ChatTheme -> 组件” 单向依赖，避免反向依赖具体页面。

---

维护说明：

- 若新增/调整 OWUI 组件或 tokens，请同步更新：`lib/chat_ui/owui/INDEX.md` 与本文件。
