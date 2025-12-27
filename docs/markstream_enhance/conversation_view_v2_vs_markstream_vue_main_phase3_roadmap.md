# ConversationViewV2 对齐 markstream-vue-main：Phase 3 优化路线图（生产优先 + Demo 验证策略）

> 范围：本文件仅记录 Phase 3 的优化路线图（Backlog + 迁移路径 + 验收/验证场景），不修改任何生产代码。

## 1. 背景与输入

**输入文档**
- Phase 2 评价表（差距与优先级依据）：`docs/markstream_enhance/conversation_view_v2_vs_markstream_vue_main_evaluation.md`
- 实施计划（Phase 1-4 总纲）：`.snow/plan/markstream_v2_smooth_streaming_gap_analysis.md`

**关键证据索引（生产/Demo）**
- 上游 chunk 聚合与 flush：`lib/utils/chunk_buffer.dart`，初始化点：`lib/widgets/conversation_view_v2.dart:129`
- flush 驱动 UI 更新：`lib/widgets/conversation_view_v2/streaming.dart:_handleStreamFlush`
- auto-follow：`lib/widgets/conversation_view_v2/scroll_and_highlight.dart:_requestAutoFollow`（800ms 节流）与 `_handleChatScrollNotification`（near-bottom=80px）
- Markdown stable/tail：`lib/chat_ui/owui/stable_body.dart:OwuiStableBody`
- 代码块同步高亮阻塞：`lib/chat_ui/owui/code_block.dart:_buildHighlightedSpan`（`highlight.parse` 同步）
- Mermaid 流式占位：`lib/chat_ui/owui/mermaid_block.dart:_buildContent`（`isStreaming` 时仅 “Rendering…”）
- Demo 可借鉴：
  - 渲染速度参数：`lib/pages/flyer_chat_demo/streaming_state.dart:_RenderSpeedConfig`
  - 流式代码块轻量预览：`lib/pages/flyer_chat_demo/streaming_code_block_preview.dart:_StreamingCodeBlockPreview`
  - Mermaid Demo 高度占位与交互：`lib/pages/flyer_chat_demo/mermaid_block.dart`

## 2. 总体目标与原则（对齐 markstream 思路）

**总体目标**：让 Flutter 生产端 `ConversationViewV2` 的流式体验在以下维度逼近 `markstream-vue-main`：
- 稳定流（抵抗 burst：避免“冻结 → dump”观感）
- 可控滚动（near-bottom 才跟随；用户操作优先；避免跳动）
- 重节点治理（代码高亮、Mermaid、WebView 等从主渲染路径剥离）
- 可观测与可回滚（feature flag + 小步合并）

**原则**
1. **可开关**：每个 P0 优化必须有 feature flag。
2. **可回滚**：回滚点尽量集中在 3 个入口：`_handleStreamFlush`、`_requestAutoFollow`、`OwuiMarkdown` 的 codeBuilder/streamingCodeBlock。
3. **先 Demo 后生产（但不教条）**：体验节奏类/参数类先 Demo；低风险治理类可直接生产灰度。

## 3. 路线图（P0 / P1 / P2）

> 每个 Backlog item 均包含：目标、涉及模块、实现要点、风险与回滚、验收指标、建议验证方式（Demo/生产）。

### P0（生产优先：立刻“变丝滑”，高收益/低风险）

#### P0-1 稳定流展示（typewriter / 小片 reveal），抵抗 burst “冻结→dump”
- **目标**：上游 chunk 突发时，UI 仍以稳定节奏小步增长（对齐 markstream 的 typewriter + batching 观感）。
- **涉及文件/模块**：
  - `lib/widgets/conversation_view_v2/streaming.dart:_handleStreamFlush`
  - `lib/widgets/stream_manager.dart`（聚合状态）
  - `lib/utils/chunk_buffer.dart`
- **实现要点（可落地）**：
  1) 引入“显示文本 displayText vs 真实文本 fullText”的 reveal 机制：flush 只追加 fullText；另有 revealer 在帧预算内推进 displayText。
  2) 推进策略优先按“帧预算（4–8ms）/tick 上限”而不是固定字速；chunk 越大推进越多，但受预算上限约束。
  3) UI 更新合并：同一帧内最多一次 `updateMessage`，避免 50ms flush 叠加导致 rebuild 风暴。
  4) 使用 Demo（`_RenderSpeedConfig`）调参后再带回生产默认值。
- **潜在风险与回滚**：
  - 风险：Timer/Ticker 回调晚于 dispose；必须统一用 `_isDisposed` 防护。
  - 风险：displayText 落后过多导致“看起来慢”；需设置最大滞后长度或在停止流式时快速追帧补齐。
  - 回滚：feature flag 关闭后恢复“flush 即全量更新 text”。
- **验收指标**：
  - 基础：`flutter build`/`flutter analyze` 通过；改动文件 `ide-get_diagnostics` 0 error；运行不崩溃。
  - 体验：burst（一次性 1k–5k chars）不出现长时间停住后突然跳大段；输出观感稳定。
  - 性能：Frame jank（>16ms/>32ms）下降；`updateMessage` 频率可控（建议 ≤ 15 次/s）。
- **建议验证**：先 Demo（节奏/参数），再生产灰度。

#### P0-2 auto-follow 改为“锚定式 stick-to-bottom + 帧内合并”，替代 800ms 纯节流
- **目标**：解决“接近底部仍丢跟随/跳动”，同时不抢用户手势。
- **涉及文件/模块**：
  - `lib/widgets/conversation_view_v2/scroll_and_highlight.dart:_requestAutoFollow`
  - `lib/widgets/conversation_view_v2/scroll_and_highlight.dart:_handleChatScrollNotification`
  - `lib/widgets/conversation_view_v2/streaming.dart:_handleStreamFlush`（flush 后跟随请求）
- **实现要点（可落地）**：
  1) 将 800ms throttle 改为“每帧最多一次”的合并请求（`_pendingAutoFollow` 标志）。
  2) 仅在 `isNearBottom == true` 且 `_autoFollowEnabled == true` 时滚动；否则不滚也不排队。
  3) smooth vs non-smooth：流式默认 `Duration.zero`；用户点击“回到底部”使用 smooth。
  4) 加入可观测计数：`scrollToIndex` 调用频率/成功率。
- **潜在风险与回滚**：
  - 风险：可能影响“定位消息/高亮”路径（同文件）。
  - 回滚：flag 关闭回到旧 `_requestAutoFollow`（800ms 版本）。
- **验收指标**：
  - 滚动：near-bottom（≤80px）流式时跟随成功率接近 100%；用户上滑后立即停跟随；回到底部恢复。
  - 性能：`scrollToIndex` 频率受控（建议 ≤ 10 次/s），无明显抖动。
- **建议验证**：可直接生产灰度，同时用 Demo 压测滚动打断。

#### P0-3 流式代码块降级：流式期间用轻量预览，闭合后再高亮
- **目标**：流式阶段避免同步 `highlight.parse` 阻塞 UI；闭合后再高亮。
- **涉及文件/模块**：
  - `lib/chat_ui/owui/markdown.dart`（`OwuiStableBody.streamingCodeBlock` builder）
  - `lib/chat_ui/owui/stable_body.dart:OwuiStableBody.extractLeadingFence`
  - `lib/chat_ui/owui/code_block.dart:_buildHighlightedSpan`
  - 可复用 Demo：`lib/pages/flyer_chat_demo/streaming_code_block_preview.dart:_StreamingCodeBlockPreview`
- **实现要点（可落地）**：
  1) 当 `isStreaming && !isClosed`：不渲染 `OwuiCodeBlock`，改为纯文本/行号/折叠的轻量预览。
  2) fence 闭合后切换到 `OwuiCodeBlock`（允许同步高亮，因为更新频率下降）。
  3) 长代码默认折叠以降低首屏布局成本。
- **潜在风险与回滚**：
  - 风险：流式阶段从高亮变为预览，预期变化；需清晰 UI 文案。
  - 回滚：flag 关闭恢复现状。
- **验收指标**：
  - 性能：流式阶段 `highlight.parse` 调用次数≈0；长帧显著减少。
  - 体验：行号/折叠/复制可用；闭合后高亮正确。
- **建议验证**：先 Demo 对照，再生产灰度（风险低）。

#### P0-4 Mermaid 流式占位“稳定高度 + Source 预览”，减少布局跳变
- **目标**：流式阶段不再只有 “Rendering…” 且高度不确定；闭合瞬间避免大跳变。
- **涉及文件/模块**：
  - `lib/chat_ui/owui/mermaid_block.dart:_buildContent`
  - `lib/widgets/mermaid_renderer.dart`（WebView 渲染成本）
  - 参考 Demo：`lib/pages/flyer_chat_demo/mermaid_block.dart`（preview 高度 360、source 代码预览）
- **实现要点（可落地）**：
  1) 流式期间：Preview tab 固定高度（建议 300–360）+ 提示；Source tab 显示 Mermaid 源码预览（可复用轻量 code preview）。
  2) 非流式（闭合后）：再挂载 `MermaidRenderer`，避免流式期频繁触发 WebView。
- **潜在风险与回滚**：
  - 风险：部分用户期望“边生成边渲染”；渐进渲染放到 P1。
  - 回滚：flag 关闭回到原 Rendering…。
- **验收指标**：
  - 滚动：闭合瞬间滚动不跳；高度突变（CLS proxy）下降。
  - 性能：流式阶段 WebView 初始化次数≈0；闭合后首次渲染耗时可观测。
- **建议验证**：先 Demo 验证高度与交互，再生产灰度。

---

### P1（对齐“渲染预算 + 重节点延迟 + 异步化”）

#### P1-1 高亮异步化 + 缓存：闭合后高亮也要“不卡顿”
- **目标**：闭合后一次性高亮大代码块也避免主线程长帧。
- **涉及文件/模块**：`lib/chat_ui/owui/code_block.dart:_buildHighlightedSpan`
- **实现要点**：
  1) 将高亮从 build 同步改为 compute/isolate 预处理 + 缓存；UI 线程只渲染 token 列表。
  2) 缓存 key：`(language, hash(code), isDarkTheme)`；首次纯文本显示，异步回来后替换。
- **风险与回滚**：实现复杂度上升；保留同步路径作为 fallback（flag）。
- **验收指标**：大代码块渲染长帧显著减少；高亮正确。
- **建议验证**：Demo 先行，生产灰度。

#### P1-2 渲染预算化（batchRendering/budget）的 Flutter 等价实现
- **目标**：让更新按预算分配，避免 flush 驱动的不可控 rebuild。
- **涉及文件/模块**：`lib/widgets/conversation_view_v2/streaming.dart`、`lib/widgets/stream_manager.dart`；对照 Demo 注释：`lib/pages/flyer_chat_demo/streaming_state.dart`。
- **实现要点**：统一“预算调度器”：文本 reveal（高）> auto-follow（中）> 重节点渲染（低）。
- **风险与回滚**：边界条件（停止流式/切换对话）要确保及时 flush 完成；flag 回滚。
- **验收指标**：长文档流式时 frame time 更稳定、抖动更小。
- **建议验证**：Demo 先行，再生产灰度。

#### P1-3 Mermaid 请求去重/节流 + 渐进尝试基础设施
- **目标**：在 WebView 体系下先压住重复渲染/频繁重载；渐进渲染作为可选增强。
- **涉及文件/模块**：`lib/widgets/mermaid_renderer.dart`、`lib/chat_ui/owui/mermaid_block.dart`
- **实现要点**：
  1) 渲染请求 debounce（300–800ms）+ 相同 code hash 去重。
  2) 渐进渲染优先“安全前缀尝试”；失败回退占位。
- **风险与回滚**：跨平台 WebView 差异；渐进失败率高；保留 P0 稳定占位。
- **验收指标**：渲染次数可控；相同输入不重复；闭合后渲染耗时可观测。
- **建议验证**：Demo 先行，生产谨慎灰度。

#### P1-4 重节点延迟挂载（viewportPriority 的最小等价）
- **目标**：避免 offscreen 的 Mermaid/WebView 或大代码块高亮抢资源。
- **涉及文件/模块**：`lib/chat_ui/owui/markdown.dart`、`lib/chat_ui/owui/mermaid_block.dart`、`lib/chat_ui/owui/code_block.dart`
- **实现要点**：先做“基于滚动状态”的延迟：用户不在底部时重节点默认占位；滚到附近/展开时再 mount。
- **风险与回滚**：可能出现“滚到节点时延迟加载”；需要 loading UI；flag 回滚。
- **验收指标**：长对话滚动掉帧减少；重节点不再 offscreen 初始化。
- **建议验证**：生产灰度 + Demo 压测。

---

### P2（中长期：超长会话/大规模内容治理）

#### P2-1 超长会话虚拟化与消息级增量更新治理
- **目标**：超长对话下滚动与内存可控。
- **涉及文件/模块**：`lib/widgets/conversation_view_v2/build.dart`、`lib/widgets/conversation_view_v2/streaming.dart`
- **实现要点**：明确只更新末尾消息边界；评估列表承载能力（规划项）。
- **风险与回滚**：回归成本高；逐步替换。
- **验收指标**：1k+ 消息仍流畅；内存峰值可控。

#### P2-2 可观测性体系：把“丝滑”变成可量化回归门槛
- **目标**：形成可对比的回归检测闭环。
- **涉及文件/模块**：建议埋点点位：`_handleStreamFlush`、`_requestAutoFollow`、`_buildHighlightedSpan`、`MermaidRenderer`。
- **实现要点**：采集 frame timings、updateMessage/scrollToIndex 次数、highlight 耗时、mermaid 渲染耗时；debug overlay/日志；release 关闭或采样。
- **验收指标**：同一套场景可对比 P0/P1 前后指标变化。

## 4. Demo 先行验证 → 生产落地：迁移路径（feature flag + 小步合并）

1) **先落地“可开关”**：每个 P0/P1 项都有独立 flag，默认关闭，支持灰度。
2) **小步合并顺序建议**（依赖最小 → 收益最大）：
   - PR1：P0-3（流式代码块降级）
   - PR2：P0-4（Mermaid 固定高度占位 + Source 预览）
   - PR3：P0-2（auto-follow 合并请求 + 锚定语义）
   - PR4：P0-1（稳定流 revealer）
3) **回滚策略**：出现问题一键关 flag 回到当前逻辑；回滚点集中在三处入口（见“原则”）。

## 5. 推荐验证场景清单 + 可观测 proxy

1) **burst chunk**：一次 flush 追加 1k/5k/20k chars。
- proxy：`updateMessage` 次数/s；frame jank（>16ms/>32ms）；displayText 落后长度（fullText - displayText）。

2) **长文档**：多段 markdown（列表/表格/引用/latex） + 3–5 个代码块 + 1–2 个 mermaid。
- proxy：`OwuiStableBody` stable 前缀缓存命中率；frame timings；内存峰值。

3) **代码块未闭合**：``` 后持续增长 200+ 行，最后才闭合。
- proxy：流式阶段 `highlight.parse` 调用次数≈0；代码块内部滚动不抢主滚动。

4) **mermaid 未闭合/闭合瞬间渲染**：```mermaid 长时间不闭合；闭合后首次渲染。
- proxy：流式阶段 WebView 初始化次数≈0；闭合瞬间 scroll offset 跳变幅度；首次可见耗时。

5) **用户滚动打断**：流式中上滑阅读旧消息，停留 5s，再点“回到底部”。
- proxy：auto-follow 状态切换次数；`scrollToIndex` 频率；恢复跟随成功率。

6) **高频 flush**：保持 ChunkBuffer 50ms，连续输出 10–20 秒。
- proxy：frame time 分布是否稳定；CPU 占用趋势；滚动/输入响应延迟。

---

## 6. Phase 4 进入条件（本路线图的下一步）

当你确认进入 Phase 4（开始改生产代码）时，建议每个 PR 的最小验收都包含：
- `flutter analyze`
- `flutter build`（或团队约定的最小 build）
- `ide-get_diagnostics`（改动文件 0 error）
- 按上述验证场景至少跑 2-3 个，确保体验指标不回退
