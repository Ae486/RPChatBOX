# V2（flutter_chat_ui）集成实施规格书（审查稿）
> 目标：以 `flutter_chat_ui` 为生产聊天 UI 主线，在不牺牲现有生产能力的前提下，重建一套 OpenWebUI 式“简洁、干净、美观”的样式组件与全局主题；并将 Demo（`lib/pages/flyer_chat_demo_page.dart`）中已验证的“流式渲染输出 + 自动滚动”方案作为**唯一同类方案**迁入生产，完全替代 V1 中对应实现。
>
> 本文面向：开发实施 / 代码审查 / 需求验收。
>
> 最后更新：2025-12-24

---

## Dev Log
- 2025-12-24：修复“最底部 AI 消息重新生成”崩溃（保留用户消息，仅删除其后消息并重新请求）；重构 `OwuiComposer` 为 OpenWebUI 式两段布局；修复 Markdown 表格圆角外边框闭合不全。

## Executive Summary（审查要点）

- **V2 是生产主线**：生产聊天页以 `lib/widgets/conversation_view_v2.dart`（`flutter_chat_ui.Chat`）为主；V1（`lib/widgets/conversation_view.dart`）仅保留为迁移期回退与对照。
- **Demo 是“同类能力唯一基准”**：Demo 已实现的能力（尤其“流式渲染输出/稳定前缀解析/自动滚动”）必须替代 V1 同类实现，禁止继续扩展 V1 旧滚动/渲染方案。
- **flutter_chat_ui 的角色边界清晰**：它提供消息列表/输入/主题注入与 builder 扩展点；业务功能（导出/搜索定位/重生成等）与“流式增量渲染策略”仍需我们实现。
- **OpenWebUI 风格落地为“Tokens + 组件规则”**：以灰阶、微边框、圆角、优秀 Markdown prose 排版为核心；同一套 tokens 同时驱动 `ThemeData`、`ChatTheme` 与自定义组件。
- **消息模型策略固定**：`authorId` 固定为 `'assistant'`（避免分裂导致 resolveUser/分组异常），`modelName/providerName` 等写入 `metadata`（已在 `lib/adapters/chat_message_adapter.dart` 体现）。
- **导出功能策略**：参考 V1 行为（交互/范围/格式），在 V2 + `flutter_chat_ui` builder 体系下实现“升级版导出”（可批量选择、可多格式、可跨平台保存/分享）。
- **第三方复用优先**：非聊天页面优先评估 `shadcn_ui` 作为组件库；样式解耦评估 `mix`；统一动效/骨架屏评估 `flutter_animate`/`animate_do` 与 `skeletonizer`，并给出“直接集成 vs 仅采纳理念”的决策矩阵。
- **验收以“可量化清单”推进**：按 P0/P1/P2 里程碑拆解，每个里程碑给出明确的 Demo 对齐点与生产必须通过项。

---

## 目录（章节结构）

1. 需求与约束（Demo baseline / V2 主线 / V1 回退）
2. 现状与关键入口（代码路径与职责）
3. `flutter_chat_ui` 角色边界与覆盖率清单（覆盖多少、还缺什么）
4. Demo Baseline：统一“流式渲染输出 + 自动滚动”方案（替换点与同源策略）
5. OpenWebUI 风格规范：设计 tokens 与组件样式规则（可落地映射到 Flutter 主题）
6. 第三方框架调研与决策矩阵（Shadcn UI / Mix / Animate-Do / Skeletonizer + 扩展推荐）
7. 迁移里程碑与验收标准（P0/P1/P2）
8. 风险、性能与回滚策略
9. 附录：参考链接与本仓库对照路径

---

## 1. 需求与约束

### 1.1 强约束（必须遵守）

1. **Demo 已实现能力必须替代 V1 同类实现**  
   重点：`lib/pages/flyer_chat_demo_page.dart` 的自动滚动策略、`StablePrefixParser` + `_StreamingMarkdownBody` 的流式渲染策略。
2. **V2（flutter_chat_ui）是生产主线**  
   新 UI、主题、消息渲染、滚动策略优先在 V2 落地；V1 仅用于迁移期回退/对照。
3. **“能抄不写，能连不造，能复用不原创”**  
   对于 Demo 未覆盖的能力，优先成熟第三方库/模式；其次参考并“升级改造”V1 逻辑以适配 V2 + `flutter_chat_ui`。

### 1.2 非目标（避免范围膨胀）

- 不在本阶段重写底层网络/模型层（保持现有 `EnhancedStreamController` 能跑通）。
- 不在本阶段长期维护两套渲染引擎（必须规划收敛边界与过渡期降级策略）。

---

## 2. 现状与关键入口（代码路径）

### 2.1 生产入口与开关

- V1：`lib/widgets/conversation_view.dart`
- V2：`lib/widgets/conversation_view_v2.dart`
- 宿主切换：`lib/widgets/conversation_view_host.dart`（根据 `enableChatUiV2` 委派 `scrollToMessage()` / `enterExportMode()`）
- 设置开关：`lib/models/chat_settings.dart`（`enableChatUiV2`），UI：`lib/pages/settings_page.dart`

### 2.2 Demo（试验场，迁移基准）

- Demo 页：`lib/pages/flyer_chat_demo_page.dart`
- Demo 流式渲染核心：`lib/pages/flyer_chat_demo/streaming_markdown_body.dart`
- 稳定前缀解析器：`lib/rendering/markdown_stream/stable_prefix_parser.dart`
- Demo 相关分析/指导文档：
  - `docs/markstream-flutter/FLYER_CHAT_DEMO_ANALYSIS.md`
  - `docs/markstream-flutter/STREAMING_INTEGRATION_GUIDE.md`

### 2.3 生产流式管线与消息适配

- 网络流式控制：`lib/controllers/stream_output_controller.dart`（`EnhancedStreamController`）
- chunk 节流：`lib/utils/chunk_buffer.dart`
- V2 流式状态/think 解析：`lib/widgets/stream_manager.dart`
- flutter_chat_core 消息适配：`lib/adapters/chat_message_adapter.dart`

---

## 3. flutter_chat_ui 角色边界与覆盖率清单

### 3.1 框架负责什么（我们要“用好”而非“改它”）

- 消息列表与虚拟化：`Chat` 渲染、基础滚动与性能。
- 统一的消息模型：`flutter_chat_core` 的 `TextMessage/ImageMessage/FileMessage/CustomMessage/...`。
- 扩展点：`Builders`（`textMessageBuilder`/`customMessageBuilder`/`composerBuilder`/附件 builders 等）。
- 主题注入点：`ChatTheme`（以及基于 `ThemeData` 的默认映射）。

### 3.2 框架不负责什么（必须由我们实现/适配）

- **业务能力**：搜索定位、导出/批量选择、重生成、编辑/重发、附件快照与恢复、Token 统计等。
- **流式增量渲染策略**：稳定前缀解析、未闭合结构处理、增量渲染节流、流式代码块占位/闭合后升级渲染。
- **OpenWebUI 风格设计系统**：全局 tokens、组件库、交互一致性（hover/pressed/focus）、滚动条、动效等。

### 3.3 覆盖率清单（V1 → V2）

> 说明：这里的“覆盖”指“框架自带可用”；“可通过 builder 覆盖”指“框架提供容器/扩展点但实现仍在我们”；“需自研/复用”指“框架不提供，需要我们自己或引入第三方”。

| 功能域 | 具体能力 | flutter_chat_ui 自带 | 可通过 builders 承载 | 需自研/复用 | 参考来源/落地点 |
|---|---|---:|---:|---:|---|
| 消息列表 | 虚拟化渲染/基础滚动 | ✅ | - | - | `ConversationViewV2` 使用 `Chat` |
| 消息渲染 | 用户气泡/助手无气泡布局 | - | ✅ | - | `ConversationViewV2` builders |
| Markdown | prose 排版、代码块、表格 | - | ✅ | - | Demo：`markdown_widget` 配置 |
| 流式输出 | 增量更新 + 节流 | - | ✅ | ✅ | Demo：稳定前缀；生产：`ChunkBuffer` |
| 自动滚动 | 跟随/解锁/回到底部按钮 | - | ✅ | ✅ | Demo：`_autoFollowEnabled` 策略 |
| 思考块 | `<think>` 解析 + UI | - | ✅ | ✅ | 生产：`StreamManager` + `CustomMessage` |
| 搜索定位 | 按 messageId 跳转 + 高亮 | 部分（滚动能力） | ✅ | ✅（已实现） | 复用 `SearchPage` + 宿主委派；V2 用 pending-retry + 2s 高亮（`lib/pages/chat_page.dart`、`lib/widgets/conversation_view_v2.dart`） |
| 导出 | 批量选择 + 导出生成 | - | ✅ | ✅（已实现） | V2：批量导出模式（选择/全选/导出 md|txt）+ ChatPage 菜单入口（`lib/widgets/conversation_view_v2.dart`、`lib/pages/chat_page.dart`） |
| 上传附件 | 选文件/图片、插入消息 | - | ✅ | ✅ | 已有 `file_picker`、`ChatMessageAdapter` |
| 主题 | ChatTheme 覆盖 | ✅ | - | ✅（tokens） | `ChatDesignTokens -> ChatTheme` |

---

## 4. Demo Baseline：统一“流式渲染输出 + 自动滚动”方案

### 4.1 Demo 的关键点（必须同源迁入）

- **稳定前缀解析**：`StablePrefixParser`（`lib/rendering/markdown_stream/stable_prefix_parser.dart`）将输入分为 `stable` 与 `tail`，避免未闭合结构导致的闪烁/反复重建。
- **流式 Markdown Body**：`lib/pages/flyer_chat_demo/streaming_markdown_body.dart`  
  - stable 部分渲染为 Markdown（可缓存、可复用）；tail 以纯文本或“流式代码块占位”渲染。
  - fence/表格/HTML/LaTeX/think 等结构闭合后“升级”为增强组件（代码块、Mermaid、公式等）。
- **自动滚动**：`lib/pages/flyer_chat_demo_page.dart`  
  - 通过 `_autoFollowEnabled` + near-bottom 判断（阈值）+ ScrollNotification 监听实现“用户上滑解锁/显示回到底部按钮/回到底部后重新锁定”。

### 4.2 生产 V2 的替换点（建议）

1. **消息渲染替换点**：`lib/widgets/conversation_view_v2.dart` 的 `textMessageBuilder`（助手消息）  
   - 将 `_buildAssistantFullWidth(content: message.text)` 替换为 Demo 同源的“流式 stable-prefix 渲染组件”。
2. **自动滚动替换点**：V2 页面层（而非 V1 的滚动控制器）  
   - 复用 Demo 的策略：基于 scroll notification 与“near-bottom”判定，驱动 `ChatController.scrollToIndex(...)` 或等价能力。
3. **渲染引擎收敛策略**：生产当前存在 `flutter_markdown` 链路，Demo 使用 `markdown_widget`  
   - 推荐：以 `markdown_widget` 为主线（与 Demo 同源），保留 `flutter_markdown` 仅作迁移期降级（明确触发条件与期限）。

---

## 5. OpenWebUI 风格规范（Tokens + 组件规则）

### 5.1 资料来源（必须可追溯）

- OpenWebUI 仓库：`https://github.com/open-webui/open-webui`
- 本仓库已拉取用于对照：`.tmp/open-webui/`
  - 全局样式：`.tmp/open-webui/src/app.css`
  - 灰阶色板：`.tmp/open-webui/tailwind.config.js`
  - 消息组件：`.tmp/open-webui/src/lib/components/chat/Messages/UserMessage.svelte`、`.tmp/open-webui/src/lib/components/chat/Messages/ResponseMessage.svelte`
  - 浮动按钮/自动滚动 gating：`.tmp/open-webui/src/lib/components/chat/ContentRenderer/FloatingButtons.svelte`

### 5.2 设计 Tokens（OpenWebUI Draft v0.1）

#### 5.2.1 灰阶色板（来自 OpenWebUI Tailwind 配置）

> 源：`.tmp/open-webui/tailwind.config.js`

| Token | Hex（默认值） | 用途建议 |
|---|---|---|
| `gray50` | `#f9f9f9` | 浅底气泡/卡片背景 |
| `gray100` | `#ececec` | 浅边框/分隔线 |
| `gray200` | `#e3e3e3` | hover 背景/次级边框 |
| `gray300` | `#cdcdcd` | disabled 边框 |
| `gray400` | `#b4b4b4` | 次级文本 |
| `gray500` | `#9b9b9b` | 次次级文本 |
| `gray600` | `#676767` | 深色图标/文本 |
| `gray700` | `#4e4e4e` | 深色边框 |
| `gray800` | `#333333` | 暗色卡片背景 |
| `gray850` | `#262626` | 暗色气泡背景（OpenWebUI 常用） |
| `gray900` | `#171717` | 暗色页面背景 |
| `gray950` | `#0d0d0d` | 暗色极深背景/分隔 |

#### 5.2.2 圆角与间距（对齐 OpenWebUI 的 tailwind 语义）

| 语义 | Tailwind | 参考像素 | Flutter tokens 建议 |
|---|---|---:|---|
| Chat bubble | `rounded-3xl` | 24px | `radius.chatBubble = 24` |
| Thumbnail | `rounded-xl` | 12px | `radius.thumbnail = 12` |
| Code block | `rounded-lg` | 8px | `radius.codeBlock = 8` |
| Pill button | `rounded-full` | 999px | `radius.pill = 999` |

#### 5.2.3 排版与 Prose（核心：Markdown“像文章一样好读”）

> 源：`.tmp/open-webui/src/app.css` 中 `.markdown-prose*`、`.input-prose*`。

- 目标：助手消息采用“无气泡 + 全宽 prose”，用户消息保持简洁气泡。
- 规则：压缩段落间距（`prose-p:my-0`）、标题紧凑、引用用细左边框、代码块不强行注入默认样式（由我们的增强代码块组件负责）。

#### 5.2.4 滚动条与 Shimmer（增强“干净但不死板”）

> 源：`.tmp/open-webui/src/app.css` 中 `::-webkit-scrollbar*` 与 `.shimmer`。

- 滚动条：细、圆（thumb radius 999）、浅色/暗色分别有不同透明度的 thumb。
- Shimmer：用于状态提示/加载占位；建议与骨架屏策略统一（见第 6 章）。

### 5.3 组件样式规则（聊天页）

| 区域 | OpenWebUI 规则 | Flutter 落地方式（建议） |
|---|---|---|
| 用户消息 | 右侧气泡、最大宽 90%、浅灰底（暗色用 `gray850`） | `textMessageBuilder` -> UserBubble 组件 |
| 助手消息 | 无气泡、全宽 markdown-prose、可显示头像/模型名/时间 | `textMessageBuilder` -> AssistantProse 组件 |
| 消息头 | 模型名 + 时间戳（hover 才显示次要信息） | 桌面端 `MouseRegion` + `AnimatedOpacity` |
| 消息操作 | hover 出现 actions（复制/重生成/删除/导出等） | builder 内部统一 ActionRow（可按平台裁剪） |
| 浮动按钮 | 不在底部时显示“回到底部” | 复用 Demo near-bottom 判定 + FAB |

### 5.4 Tokens 映射到 Flutter（全局主题统一）

参考蓝图：`docs/ui-rearchitecture/05-DESIGN_TOKENS_ARCHITECTURE.md`

- 统一以 `ThemeExtension` 承载：`ChatDesignTokens`（颜色/间距/圆角/排版/动效/滚动条等）。
- 显式映射到：
  - `ThemeData`（Material 全局）
  - `flutter_chat_ui.ChatTheme`（聊天组件）
  - 自定义组件（从 tokens 取值，禁止散落硬编码）
- 工具化可选：`theme_extensions_builder`（减少 ThemeExtension 样板代码，见第 6 章）。

---

## 6. 第三方框架调研与决策矩阵

### 6.1 评估维度（统一口径）

- 复用价值（能省多少自研组件/逻辑）
- 与“OpenWebUI 扁平灰阶”兼容性
- 与 `flutter_chat_ui` 的交互模式兼容性（滚动、手势、builder 体系）
- 集成复杂度与侵入性（是否需要改 `main.dart` / App 架构）
- 维护成本（活跃度、版本节奏、breaking 风险）
- 性能/包体/平台风险（尤其桌面端、Web、NDK/Rust 等）

### 6.2 决策矩阵（Direct vs Concepts）

| 组件/框架 | 适用范围 | 价值 | 集成复杂度 | 维护成本 | 风格兼容 | 性能/平台风险 | 结论（Direct/Concepts） | 备注 |
|---|---|---:|---:|---:|---:|---:|---|---|
| `shadcn_ui`（MIT） | 非聊天页（设置/资料/表单/弹窗） | 高 | 中-高 | 中 | 高 | 中 | **Direct（建议试点）** | 支持 “Shadcn + Material” 组合；需评估对现有 ThemeData/路由的侵入点。文档：`https://flutter-shadcn-ui.mariuti.com/` |
| `mix`（BSD-3） | 设计系统/样式解耦（非聊天页优先） | 中 | 高 | 中 | 高 | 低 | **Concepts（暂不 Direct）** | 能做“样式语义与 widget 解耦”，但引入成本高；对 `flutter_chat_ui` 现有 builder 体系收益有限。包：`https://pub.dev/packages/mix` |
| `flutter_animate`（MIT） | 全局动效（入场/状态/渐变/微交互） | 高 | 低 | 低 | 高 | 低 | **Direct（推荐）** | `shadcn_ui` 已依赖它；作为统一动效底座更合理。包：`https://pub.dev/packages/flutter_animate` |
| `animate_do`（MIT） | 快速入场动画（少量场景） | 中 | 低 | 低 | 中 | 低 | **Concepts（不优先）** | 与 `flutter_animate` 重叠，若选 `flutter_animate` 则避免双栈。包：`https://pub.dev/packages/animate_do` |
| `skeletonizer`（MIT） | 骨架屏（列表/卡片/详情页加载） | 高 | 低 | 低 | 高 | 低-中 | **Direct（推荐）** | 对非聊天页极省工；聊天流式占位可择优使用（Demo 已有专门占位逻辑）。包：`https://pub.dev/packages/skeletonizer` |

### 6.3 额外“能抄不写”推荐（按场景）

| 目标 | 推荐 | 价值点 | 风险/备注 |
|---|---|---|---|
| 主题/Token 生成 | `theme_extensions_builder` | 自动生成 `ThemeExtension` 样板 + `BuildContext` 扩展 | 需引入 build_runner 流程（项目已使用） |
| 主题快速成型 | `flex_color_scheme` | 更快搭建 light/dark + surface blend | 与 OpenWebUI “灰阶”需适配（可只采纳理念） |
| 组件目录/审查 | `widgetbook` | 组件/页面隔离开发 + 可视化审查 + golden 测试体系 | 偏工程化投入；适合 UI 重构期 |
| 导出/分享 | `share_plus`、`file_saver` | 跨平台分享/保存导出内容（markdown/json/txt） | Linux 文件分享限制；保存路径差异需 UX 统一 |
| 复制能力增强 | `super_clipboard` | 富文本/图片/多格式剪贴板（桌面端强） | Rust/NDK/预编译二进制带来维护与 CI 风险 |

---

## 7. 迁移里程碑与验收标准（可量化）

### 7.1 里程碑表

| 里程碑 | 范围 | 交付物 | 验收标准（必须满足） |
|---|---|---|---|
| P0：渲染与滚动同源化 | Demo baseline 迁入生产 V2 | V2 使用 Demo 稳定前缀渲染 + Demo 自动滚动策略 | 1）流式观感对齐 Demo；2）上滑解锁/回到底部按钮/重新锁定行为一致；3）不再扩展 V1 滚动/渲染实现 |
| P0：主题与组件骨架 | OpenWebUI 风格 tokens 初版 | `ChatDesignTokens`（ThemeExtension）+ `ChatTheme` 显式映射 | 1）亮/暗主题可读；2）聊天页（V2）与非聊天页（至少设置页）视觉一致；3）禁止硬编码样式值 |
| P1：生产必备功能补齐 | 搜索定位/高亮、导出模式、编辑/重发、重生成 | V2 完整支持宿主调用 `scrollToMessage`/`enterExportMode` | 1）功能不低于 V1 核心清单；2）导出支持至少 2 种格式（建议 Markdown + JSON） |
| P2：体验增强与工程化 | Mermaid/代码块交互、骨架屏/动效统一、组件目录 | 增强组件对齐 Demo；可选引入 `widgetbook` | 1）Mermaid/代码块交互对齐 Demo；2）加载体验统一；3）关键 UI 变更可审查 |

### 7.2 V1 回退策略（迁移期保障）

- 保持 `enableChatUiV2=false` 可回退到 V1。
- 所有新业务能力优先在 V2 实现，V1 仅做“生存维护”，不继续叠功能。

---

## 8. 风险、性能与回滚策略

- **双渲染引擎长期并存**：生产存在 `flutter_markdown` 链路，Demo 使用 `markdown_widget`；必须定义“主线/降级/期限”，避免同一消息两套渲染器导致差异与维护成本爆炸。
- **滚动能力差异**：`flutter_chat_ui` 的滚动控制与 V1 的 `ScrollablePositionedList` 不同；需要通过“页面层策略 + ChatController 能力”实现 Demo 体验，不可回退 V1 旧逻辑。
- **metadata schema 复杂化**：thinking/attachments/export-mode/highlight/model/provider 等都进入 metadata；需统一 schema（键名、类型、版本），避免互相覆盖。
- **第三方依赖平台风险**：如 `super_clipboard`（Rust/NDK）需要评估 CI 与桌面端发布链路；建议仅在确有需求时引入。

---

## 9. 附录：参考链接与对照路径

- OpenWebUI：`https://github.com/open-webui/open-webui`
- OpenWebUI 本地对照：`.tmp/open-webui/`
- Shadcn UI（Flutter）：`https://pub.dev/packages/shadcn_ui`，文档：`https://flutter-shadcn-ui.mariuti.com/`
- Mix：`https://pub.dev/packages/mix`
- Skeletonizer：`https://pub.dev/packages/skeletonizer`
- Flutter Animate：`https://pub.dev/packages/flutter_animate`
- Animate Do：`https://pub.dev/packages/animate_do`
- ThemeExtension 生成器：`https://pub.dev/packages/theme_extensions_builder`
- 导出/分享：`https://pub.dev/packages/share_plus`，保存：`https://pub.dev/packages/file_saver`
