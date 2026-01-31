# 流式渲染优化计划 v2.0

> 经 Claude + Codex 协同审核通过

## 背景

用户反馈的问题：
1. 参数调整后输出效果无变化
2. Think 块不显示
3. 输出完成后长时间延迟
4. 自动跟随丢失

## 设计原则

- **保持各层设计初衷不变**
- **不影响现有功能实现**
- **渐进式修复，低风险优先**

---

## P1: 完成后延迟修复 (第一优先级)

### 问题
`_pendingFinalize` 等待 reveal 消耗完所有 backlog，导致网络完成后 UI 仍需多次 tick 才能显示完成状态。

### 修复方案

```
onDone 触发
    ↓
检查 StablePrefixParser.split(fullText).tail
    ↓
┌─────────────────────────────────────────────────┐
│ tail 为空？                                      │
├─────────────────────────────────────────────────┤
│ 是 → displayedLen = fullLen → 立即 finalize     │
│ 否 → 进入两阶段快进                              │
└─────────────────────────────────────────────────┘

两阶段快进：
  Stage 1: maxCharsPerTick 临时提升至 500，持续 5 ticks
  Stage 2: 200ms 超时后，一次性 reveal 剩余内容
           (仍使用 _clampStableRevealEnd 保证安全)
```

### 文件
- `lib/widgets/conversation_view_v2/streaming.dart`

### 守护条件
- 始终使用 `_clampStableRevealEnd()` 避免断裂 token
- Stage 2 设置最大尝试次数 (10 次)，防止无限循环
- 如果 clamping 阻止完全 reveal，回退到正常 reveal 并在下一个安全边界 finalize

---

## P0: 自动跟随丢失修复 (第二优先级)

### 问题
`_requestAutoFollow()` 检查 `_isNearBottom`，该值在快速内容增长时可能过时。

### 修复方案

```dart
// 修改 _requestAutoFollow() 逻辑
void _requestAutoFollow({bool smooth = false}) {
  // 条件 1: 必须启用自动跟随
  if (!_autoFollowEnabled) return;

  // 条件 2: 检查是否有活跃的用户交互
  if (_hasActivePointerDown) return;  // 新增：指针按下时不滚动

  // 条件 3: 流式消息时跳过 _isNearBottom 检查
  final isStreaming = _activeAssistantPlaceholder?.metadata?['streaming'] == true;
  if (!isStreaming && !_isNearBottom) return;

  // 执行滚动...
}
```

### 文件
- `lib/widgets/conversation_view_v2/scroll_and_highlight.dart`

### 守护条件
- 仅在 `UserScrollNotification` 时禁用 `_autoFollowEnabled`，忽略 `ScrollUpdateNotification`
- 使用 pointer down/up 检测替代 SelectionArea 检测（更可靠）
- 在 post-frame callback 中重新计算 `_isNearBottom`

---

## P2: Think 块显示修复 (第三优先级)

### 问题
StreamManager 剥离 `<think>` 后，UI 重建仅在 body 内容变化时触发，纯 thinking 内容不触发重建。

### 修复方案 (Option A + 节流)

```dart
// StreamManager 中添加节流逻辑
class StreamManager {
  DateTime? _lastThinkingNotify;

  void append(String streamId, String chunk) {
    final data = _streams[streamId];
    if (data == null) return;

    final prevThinkingLen = data.thinkingContent.length;
    _parseThinkingContent(data, chunk);
    final thinkingGrew = data.thinkingContent.length > prevThinkingLen;

    // 节流：thinking 变化时最多 100ms 通知一次
    if (thinkingGrew) {
      final now = DateTime.now();
      if (_lastThinkingNotify == null ||
          now.difference(_lastThinkingNotify!) > Duration(milliseconds: 100)) {
        _lastThinkingNotify = now;
        // 标记需要强制 UI 更新
        data.thinkingNeedsUiRefresh = true;
      }
    }

    notifyListeners();
  }
}

// streaming.dart 中检查并触发更新
void _handleStreamFlush(String content) {
  _streamManager.append(streamId, content);

  final data = _streamManager.getData(streamId);
  if (data?.thinkingNeedsUiRefresh == true) {
    data.thinkingNeedsUiRefresh = false;
    // 强制触发 reveal tick（即使 body 未变）
    _scheduleNextRevealTick();
  }
}
```

### 文件
- `lib/widgets/stream_manager.dart`
- `lib/widgets/conversation_view_v2/streaming.dart`

### 守护条件
- 节流至最多 10 次/秒 thinking 更新
- 不改变 StreamManager 作为 thinking 解析源的设计
- 确保 body 为空时 thinking 仍能显示

---

## P3: 参数生效修复 (第四优先级)

### 问题
ChunkBuffer 50ms 刷新间隔主导节奏，`revealTickMs` 被架空。

### 修复方案

```dart
// StreamingTuningParams 新增参数
class StreamingTuningParams {
  int _chunkBufferFlushMs = 50;
  int get chunkBufferFlushMs => _chunkBufferFlushMs;
  set chunkBufferFlushMs(int v) {
    final clamped = v.clamp(16, 200);  // 最小 16ms (60fps)
    if (_chunkBufferFlushMs == clamped) return;
    _chunkBufferFlushMs = clamped;
    notifyListeners();
    _markDirtyAndScheduleSave();
  }
}

// conversation_view_v2.dart initState() 中使用
_chunkBuffer = ChunkBuffer(
  onFlush: _handleStreamFlush,
  flushInterval: Duration(
    milliseconds: StreamingTuningParams.instance.chunkBufferFlushMs,
  ),
  flushThreshold: 30,
);
```

### 文件
- `lib/widgets/conversation_view_v2/streaming_feature_flags.dart`
- `lib/widgets/conversation_view_v2.dart`

### 守护条件
- 最小值 16ms，防止 UI 洪泛
- 文档说明：参数变更在下次打开对话时生效
- 调试面板添加该参数的 Slider

---

## P4: 主开关语义修复 (第五优先级)

### 问题
`enableExperimentalStreamingMarkdown` 名称暗示控制所有流式行为，但实际只控制视觉效果。

### 修复方案

1. **保持当前行为**（stableFlowReveal 始终启用）
2. **更新 UI 文案**：
   - 标题: "实验性 Markdown 视觉效果"
   - 描述: "启用代码块流式预览、Mermaid 占位符、淡入动画等视觉增强。核心流式渲染始终启用。"
3. **向后兼容**：读取时同时检查新旧 key

### 文件
- `lib/widgets/conversation_config_dialog.dart`
- `lib/models/conversation_settings.dart`（可选：添加迁移逻辑）

### 守护条件
- 保持 JSON key 不变，仅更新 UI 文案
- 或：读取时兼容旧 key，写入时使用新 key

---

## 实施检查清单

| 优先级 | 任务 | 文件 | 风险 | 状态 |
|--------|------|------|------|------|
| P1 | 添加快进逻辑 | streaming.dart | 低 | [ ] |
| P0 | 添加流式检查 + 指针守护 | scroll_and_highlight.dart | 低 | [ ] |
| P2 | 添加节流 thinking 更新 | stream_manager.dart, streaming.dart | 中 | [ ] |
| P3 | 添加 chunkBufferFlushMs | streaming_feature_flags.dart, conversation_view_v2.dart | 中 | [ ] |
| P4 | 更新 UI 文案 | conversation_config_dialog.dart | 低 | [ ] |

---

## 测试场景

### P1 测试
- [ ] 短回复（<500 字符）：应立即完成
- [ ] 长回复（>5000 字符）：应在 200ms 内完成
- [ ] 包含代码块的回复：不应显示断裂的 ``` 标记

### P0 测试
- [ ] 流式输出时保持在底部
- [ ] 用户上滑后停止跟随
- [ ] 用户选择文本时不强制滚动

### P2 测试
- [ ] 模型先输出 `<think>` 再输出正文：thinking 块应立即显示
- [ ] 纯 thinking 输出：应显示 thinking 块
- [ ] thinking 更新频率：不应超过 10 次/秒

### P3 测试
- [ ] 设置 chunkBufferFlushMs=16：输出应更流畅
- [ ] 设置 chunkBufferFlushMs=200：输出应更卡顿（符合预期）

### P4 测试
- [ ] UI 文案正确显示
- [ ] 旧配置能正确加载

---

## 审核记录

- **v1.0**: Claude 初稿
- **v1.0 审核**: Codex 提出 5 项调整建议
- **v2.0**: Claude 根据反馈修订
- **v2.0 审核**: Codex 批准，附加 3 项微调建议
- **v2.0 最终**: 整合所有建议，生成可执行计划
