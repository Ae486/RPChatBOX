# P0-3 代码块丝滑流式：设计对照文档（Flutter / OWUI）

> 目标：在“默认换行”的前提下，让代码块在流式阶段保持视觉稳定（不暴露 markdown backticks 等“半成品”），并解决行号与换行后的视觉行对齐问题；同时通过“屯一点 + 稳定节奏”减少掉帧与 auto-follow 丢失。
>
> 范围：本文件是 Phase 4 / P0-3 的实现对照文档，用于后续验收与回归定位。

## 1. 背景与问题

### 1.1 当前实现的问题（Flutter 生产）
- 行号 gutter 与代码内容在 `softWrap=true` 时无法对齐：窗口宽度变化导致折行数变化，但行号只按“原始行”渲染。
- 流式阶段若每次 chunk 都触发高亮（同步 `highlight.parse`）会导致卡顿；若完全不高亮则观感掉档。
- code/mermaid 等块级节点渲染与高度变化会干扰主列表 auto-follow，出现“丢跟随/跳动”。

### 1.2 参考实现（markstream-vue-main）的启发
`docs/research/markstream-vue-main/docs/guide/performance.md` 明确建议：
- 通过 typewriter + batching（budget/delay）保持稳定流。
- heavy nodes（Mermaid/Monaco/KaTeX）延迟渲染（defer nodes / viewport priority）。
- burst 时对 code blocks 做 fallback（禁用 codeBlockStream 或临时 renderCodeBlocksAsPre）。

## 2. 目标与非目标

### 2.1 目标
- **视觉稳定优先**：检测到 code block 信号后立即展示“代码块外壳”（header + 占位区域），避免 UI 暴露 markdown 原始形态。
- **默认换行**：保持 `softWrap=true` 的阅读体验。
- **行号对齐**：行号必须按“视觉行”对齐（折行后补空行占位），并在宽度变化时同步。
- **流式也能看见渲染结果**：采用“低频高亮 + 其余时间纯文本”的策略，避免卡顿且不掉档。
- **稳定节奏**：允许“屯一点”后再推进 display，减少频繁 re-layout；为后续全局 stable reveal（P0-1）做准备。

### 2.2 非目标（本阶段不做）
- 不在 P0-3 内引入 isolate/compute 高亮（P1 才做异步化）。
- 不在 P0-3 内实现 Mermaid/Latex 的完整策略（分别在 P0-4 / 后续项）。

## 3. 核心方案（P0-3）

### 3.1 UI 形态：占位高度“矮 -> 增高 -> 固定 maxHeight 后内部滚动”
- 初始 `minHeight` 较矮（让用户感知“在输出”）。
- 随着展示文本增长，容器自然增高；到达 `maxHeight` 后内部滚动展示更多行。

### 3.2 行号与视觉行对齐（TextPainter 方案）
- Flutter 无现成框架可直接复用“行号随换行”的对齐能力；采用 `TextPainter` 是可控且标准的做法。
- 做法：
  1) 在布局中通过 `LayoutBuilder` 获得代码区域可用宽度 `maxWidth`。
  2) 将代码按 `\n` 切分为“原始行”。
  3) 对每一原始行使用 `TextPainter(...).layout(maxWidth: ...)`，再用 `computeLineMetrics().length` 得到该行折成的“视觉行数”。
  4) 行号侧输出：每个原始行的第一视觉行显示数字，其余视觉行显示空字符串（占位），保证高度一致。
  5) 对结果做缓存（按 code hash + width + textStyleKey），并配合节流，避免在高频流式更新时反复计算。

### 3.3 流式语法高亮（B 策略：低频高亮，不暴露丑陋原始态）
- 流式阶段维持 code block 外壳不变。
- 高亮刷新频率限制为 300–500ms（可调）。
- 在高亮刷新间隔内：仍显示代码文本（与最终 UI 同一容器/样式），但不强制每次更新都触发 `highlight.parse`。
- 保护阈值：当代码长度过大时，流式阶段可暂不高亮，闭合后再一次性高亮（防卡顿）。

### 3.4 开关策略（必须不影响默认行为）
- master gate：`ConversationSettings.enableExperimentalStreamingMarkdown`（默认关闭）。
- sub flag：`MS_P0_CODE_PREVIEW`（默认 true，但需 master 才生效）。
- 默认不改变任何用户体验；仅在用户主动开启 master 后生效。

## 4. 验收与验证

### 4.1 体验验收（手工场景）
- 流式 code block 出现时：先看到 header + 占位框；随后代码以稳定节奏出现。
- 调整窗口宽度：代码折行变化时，行号 gutter 始终与视觉行对齐。
- 长代码：高度增长到 maxHeight 后内部滚动，主列表滚动与 auto-follow 不被强烈干扰。

### 4.2 性能验收（proxy）
- `highlight.parse` 调用频率显著降低（≤ 2–3 次/s）。
- frame jank 明显减少；主滚动与输入保持响应。

### 4.3 工程验证
- `flutter analyze`（改动文件）
- `flutter build windows`
- IDE diagnostics：改动文件 0 error

## 5. 实施文件与点位
- `lib/chat_ui/owui/code_block.dart`：实现 wrap 行号对齐 + 流式高亮节流 + 高度策略
- `lib/chat_ui/owui/markdown.dart`：将增强模式透传给 `OwuiCodeBlock`
- `lib/chat_ui/owui/assistant_message.dart`：透传增强开关到 `OwuiMarkdown`
- `lib/widgets/conversation_view_v2/build.dart`：从 `ConversationSettings` 计算 flag 并传入
