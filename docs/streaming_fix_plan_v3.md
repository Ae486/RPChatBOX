# 流式渲染修复计划 v3.0

> 经 Claude + Codex 协同审核通过
> 实施完成：2026-01-30

## 根因确认

```
_handleStreamFlush() 直接调用 _stableFlowRevealTick()
    ↓
消费者节奏被生产者节奏绑架
    ↓
revealTickMs 参数失效
    ↓
输出由 ChunkBuffer 50ms flush 控制，而非 timer
    ↓
高度剧变 → 自动跟随丢失 → backlog 累积 → 完成延迟
```

---

## 修复项

### FIX-1: 解耦生产者与消费者（核心修复）

**文件**: `lib/widgets/conversation_view_v2/streaming.dart`

**位置**: `_handleStreamFlush()` 方法（约第 307-344 行）

**修改**:
```dart
@override
void _handleStreamFlush(String content) {
  if (_isDisposed) return;

  final streamId = _activeStreamId;
  final oldPlaceholder = _activeAssistantPlaceholder;
  if (streamId == null || oldPlaceholder == null) return;

  _streamManager.append(streamId, content);

  _scheduleStreamingImagePrefetch(streamId);

  final useStableFlow = MarkstreamV2StreamingFlags.stableFlowReveal(_conversationSettings);
  if (!useStableFlow) {
    debugPrint('[streaming] stableFlowReveal=false, 走旧逻辑');
    final state = _streamManager.getState(streamId);

    final newMsg = chat.TextMessage(
      id: oldPlaceholder.id,
      authorId: oldPlaceholder.authorId,
      createdAt: oldPlaceholder.createdAt,
      text: state.text,
      metadata: {
        ...(oldPlaceholder.metadata ?? const <String, dynamic>{}),
        'streaming': !state.isComplete,
      },
    );

    MarkstreamV2StreamingMetrics.onUpdateMessage();
    _chatController.updateMessage(oldPlaceholder, newMsg);
    _activeAssistantPlaceholder = newMsg;
    _requestAutoFollow(smooth: true);
    return;
  }

  _ensureStableFlowRevealTimer();
  // FIX-1: 删除直接调用，让 timer 控制节奏
  // _stableFlowRevealTick();  // ← 删除这行
}
```

---

### FIX-2: 首次 flush 立即显示（用户体验优化）

**问题**: FIX-1 后，首次 flush 需要等待一个 tick 周期才显示。

**文件**: `lib/widgets/conversation_view_v2/streaming.dart`

**位置**: `_handleStreamFlush()` 方法末尾

**修改**:
```dart
  _ensureStableFlowRevealTimer();

  // FIX-2: 仅在首次 flush 时立即触发一次 tick，后续由 timer 控制
  if (_stableRevealDisplayedLen == 0) {
    _stableFlowRevealTick();
  }
}
```

---

### FIX-3: 完成时快进（消除完成延迟）

**问题**: 流结束时可能还有 backlog，需要等多个 tick 才能完成。

**文件**: `lib/widgets/conversation_view_v2/streaming.dart`

**位置**: `_stableFlowRevealTick()` 方法中，计算 `proposed` 之后

**修改**:
```dart
void _stableFlowRevealTick() {
  // ... 现有代码 ...

  final backlog = fullLen - displayedLen;
  if (backlog <= 0) {
    // ... 现有逻辑 ...
  }

  final maxCharsPerTick =
      MarkstreamV2StreamingFlags.revealMaxCharsPerTick(_conversationSettings);
  // ... 现有代码 ...

  // FIX-3: 流结束时快进
  // 如果流已结束且 backlog 较小（≤ 3 倍 maxCharsPerTick），一次性显示完
  var proposed = displayedLen + maxCharsPerTick;
  if (_pendingFinalize != null && backlog > 0 && backlog <= maxCharsPerTick * 3) {
    proposed = fullLen;  // 快进到末尾
  }

  // ... 后续 clamp 和更新逻辑保持不变 ...
}
```

---

## 完整修改后的 _handleStreamFlush

```dart
@override
void _handleStreamFlush(String content) {
  if (_isDisposed) return;

  final streamId = _activeStreamId;
  final oldPlaceholder = _activeAssistantPlaceholder;
  if (streamId == null || oldPlaceholder == null) return;

  _streamManager.append(streamId, content);

  _scheduleStreamingImagePrefetch(streamId);

  final useStableFlow = MarkstreamV2StreamingFlags.stableFlowReveal(_conversationSettings);
  if (!useStableFlow) {
    debugPrint('[streaming] stableFlowReveal=false, 走旧逻辑');
    final state = _streamManager.getState(streamId);

    final newMsg = chat.TextMessage(
      id: oldPlaceholder.id,
      authorId: oldPlaceholder.authorId,
      createdAt: oldPlaceholder.createdAt,
      text: state.text,
      metadata: {
        ...(oldPlaceholder.metadata ?? const <String, dynamic>{}),
        'streaming': !state.isComplete,
      },
    );

    MarkstreamV2StreamingMetrics.onUpdateMessage();
    _chatController.updateMessage(oldPlaceholder, newMsg);
    _activeAssistantPlaceholder = newMsg;
    _requestAutoFollow(smooth: true);
    return;
  }

  _ensureStableFlowRevealTimer();

  // FIX-2: 仅在首次 flush 时立即触发，后续由 timer 控制
  if (_stableRevealDisplayedLen == 0) {
    _stableFlowRevealTick();
  }
}
```

---

## 不修改项

| 组件 | 原因 |
|------|------|
| ChunkBuffer | 仍然有效减少 UI 更新频率，只是不再绑架消费者 |
| StreamManager | 状态管理 + Think 解析职责清晰 |
| StablePrefixParser | 块级完整性保护正常工作 |
| OwuiStableBody | 块级容器渲染逻辑正确 |
| _clampStableRevealEnd | 字符级安全边界保护正常工作 |
| 所有渲染参数 | 参数本身设计正确，修复后将生效 |

---

## 预期效果

| 问题 | 修复后 |
|------|--------|
| 参数无效 | `revealTickMs`、`maxCharsPerTick` 等参数生效 |
| 输出卡顿 | 平滑输出，无高度剧变 |
| 自动跟随丢失 | 高度变化平缓，不再触发误判 |
| 完成延迟 | 小 backlog 时快进完成 |

---

## 测试场景

### 1. 参数生效测试
```
设置: revealTickMs=32, maxCharsPerTick=50
操作: 发送消息获取长回复
预期: 每 32ms 输出约 50 字符，输出平滑
```

### 2. 自动跟随测试
```
操作: 发送消息，观察长回复（>2000 字符）
预期: 始终保持在底部，无跳动
```

### 3. 首次响应测试
```
操作: 发送消息
预期: 立即看到响应开始（无等待感）
```

### 4. 完成延迟测试
```
操作: 等待回复完成
预期: 流结束后 <200ms 显示完成状态
```

### 5. 块级结构测试
```
输入: 包含代码块、LaTeX、表格的回复
预期: 块级容器正确渲染，无原始标记泄露
```

---

## 实施步骤

1. **修改 `_handleStreamFlush()`**
   - 删除 `_stableFlowRevealTick()` 直接调用
   - 添加首次 flush 判断

2. **修改 `_stableFlowRevealTick()`**
   - 添加完成时快进逻辑

3. **测试验证**

4. **提交**

---

## 审核记录

- **v1.0**: 初始计划（多项修复）
- **v2.0**: Codex 审核后修订
- **v3.0**: 聚焦根因，单点修复
- **v3.0 审核**: Codex 批准，建议 FIX-1+2+3 一起发布
