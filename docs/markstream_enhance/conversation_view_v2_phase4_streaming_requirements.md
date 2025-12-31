# ConversationViewV2 丝滑流式渲染（Phase 4）需求与验收规格

> 目标：把“屯一点 + 稳定 reveal/budget”的观感落到 Flutter 生产端（ConversationViewV2 + OWUI），并系统性解决：冻结→dump、auto-follow 丢失、code/mermaid/latex 块级卡顿与布局跳变。

## 0. 范围

### 0.1 In Scope
- ConversationViewV2 的流式输出观感（稳定节奏、抗 burst）
- auto-follow（跟随到底部）可靠性治理
- 块级节点（code / mermaid / latex）在流式阶段的“稳定外壳 + 重活 defer + 低频补全”策略
- 可调参数与灰度开关（便于开发阶段 A/B 调参，后续可转为用户自定义项）

### 0.2 Out of Scope（Phase 4 不做）
- isolate/compute 异步高亮（可作为 P1）
- 超长会话虚拟化（P2）
- Mermaid 真正“渐进渲染”（P1，先解决占位/跳变与 WebView 初始化成本）

## 1. 用户体验目标（必须满足）

### 1.1 全局观感
- **持续生长**：输出是连续的、稳定节奏的小步增长，不出现明显“停住→突然跳一大段（dump）”。
- **不露馅**：不会短暂闪现 markdown 的“半成品符号”（例如代码 fence 的反引号/波浪号、LaTeX 分隔符 `$`/`$$` 的半截）。
- **不抖不跳**：块级节点出现/闭合不会导致明显布局跳变（CLS proxy）、列表滚动跳动。

### 1.2 块级节点共识（来自讨论结论）
- code / mermaid / latex：检测到块级信号后，先展示组件外壳（header + body 占位容器），避免布局抖动。
- 真正渲染（语法高亮 / WebView / Math layout）只在：
  - 满足可展示条件（闭合或稳定一段时间）
  - 且以稳定节奏推进（不是每次 flush 都重排）

## 2. 核心策略：屯一点 + 稳定 reveal（两层）

### 2.1 全局（ConversationViewV2）稳定流
- flush 只累积 fullText（真实内容）
- 独立 revealer 按 tick 推进 displayText（展示内容）
- UI 只用 displayText 触发 `_chatController.updateMessage(...)`

**关键点：safeBoundary（不露馅）**
- displayText 的边界不能落在“危险半截”上：
  - 反引号/波浪号 fence 的半截（`、``、~~）
  - LaTeX 分隔符的半截（$ 或 $$ 未闭合）
  - （如涉及）think 标签边界（<think>…）

### 2.2 节点级（OWUI）defer heavy nodes
- code：外壳稳定 + wrap 行号对齐 + 高亮节流
- mermaid：流式期固定高度占位 + source；闭合后再挂载 MermaidRenderer（WebView）
- latex：P0 依赖全局 reveal 限频 + stable prefix 缓存减少 Math.tex 频繁重建；P1 再考虑流式期 lazy-render

## 3. 代码块（Code Block）详细需求（P0-3）

### 3.1 形态（绝不丑）
- 检测到 code fence 后立即呈现 code block 外壳（header + gutter + body），不显示 raw fence。
- 流式阶段允许纯文本，但必须保持最终外观一致（背景/边框/字体/布局一致）。

### 3.2 默认换行
- 代码内容默认 `softWrap=true`。

### 3.3 行号与视觉行对齐（必须）
- 行号必须按“视觉行”对齐（折行后的行也要占位对齐）。
- 窗口宽度变化导致折行数变化时，行号侧同步更新。

**实现建议（优先复用，不重复造轮子）**
- 经调研，Flutter 侧没有现成可复用的“软换行 + 行号跟随视觉行”标准组件；建议采用 `TextPainter.layout(maxWidth)` + `computeLineMetrics()` 计算每原始行的视觉行数。
- 必须做缓存 + 节流，避免高频流式更新时重复计算导致卡顿。

### 3.4 高亮策略：B（低频高亮 + 其余时间纯文本）
- 流式阶段：`highlight.parse` 必须节流（建议 300–500ms）；代码过长时可暂停高亮。
- 闭合后：立即做一次最终高亮补齐。

### 3.5 高度策略（矮→增高→maxHeight 后内部滚动）
- 初始 `minHeight`（用户立刻感知在输出）
- 随输出增长自然增高
- 达到 `maxHeight` 后内部滚动承载更多内容；流式时内部滚动 stick-to-bottom

## 4. Mermaid（P0-4）详细需求
- 流式阶段：不挂载 WebView MermaidRenderer；使用固定高度占位 + 提示；Source tab 可查看/复制源码。
- 闭合后：再挂载 MermaidRenderer；优先传入固定高度以减少高度测量带来的跳变。

## 5. LaTeX 详细需求
- 不允许在全局 reveal 过程中把 `$`/`$$` 的半截暴露给用户（safeBoundary 保障）。
- 现有 `OwuiLatexSyntax` 仅在闭合时匹配渲染，P0 依赖全局限频与 stable 前缀缓存降低 Math.tex 重建频率。

## 6. auto-follow（防丢失）详细需求（P0-2）

### 6.1 当前问题特征
- 丢跟随与“更新过频 + 块级节点高度变化 + 粗时间节流（800ms）”强相关。

### 6.2 目标策略：锚定式 + 合帧
- 仅 near-bottom 才执行滚动（threshold 可调）
- 每帧最多一次滚动请求（合并 `_pendingAutoFollow`），替代 800ms 时间节流
- 用户上滑立即停止跟随；点击“回到底部”恢复

## 7. 可调参数（开发阶段必须可调）

### 7.1 开关（master + 子项）
- master（对话级）：`ConversationSettings.enableExperimentalStreamingMarkdown`
- build-time（建议用 `--dart-define`）：
  - `MS_P0_STABLE_FLOW_REVEAL`（全局 reveal）
  - `MS_P0_ANCHOR_AUTO_FOLLOW`（锚定式 auto-follow）
  - `MS_P0_CODE_PREVIEW`（此处语义更新为：启用代码块流式增强/外壳稳定/行号对齐/高亮节流）
  - `MS_P0_MERMAID_PLACEHOLDER`（mermaid 流式占位稳定）

### 7.2 数值参数（建议同样 `--dart-define`）
- 全局 reveal：`tickMs` / `minBufferChars` / `maxCharsPerTick` / `maxLagChars`
- auto-follow：`nearBottomPx`
- code block：`minHeight` / `maxHeight` / `highlightThrottleMs` / `wrapMetricsThrottleMs`
- mermaid：`placeholderHeight`

## 8. 验收场景（必须手工回归）
- burst：一次性追加 1k/5k chars，观感稳定无 dump
- 未闭合 code block：持续增长 200+ 行，外壳稳定、行号对齐、不卡顿
- 调整窗口宽度：softWrap 折行变化时行号始终对齐
- 未闭合 mermaid：流式期不触发 WebView；闭合瞬间跳变显著降低
- 用户滚动打断：上滑阅读 5s 后不被抢回；点回到底部恢复

## 9. 验证与回滚
- 每阶段必须通过：`flutter analyze` + `flutter build windows`
- 回滚：关闭 master（对话配置 UI 已有开关）即可回到当前行为；也可单项关闭 `MS_P0_*` 二分定位
