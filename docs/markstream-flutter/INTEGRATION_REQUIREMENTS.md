# markstream-vue 集成需求指导书

> 基于代码审查的集成规划
> 最后更新: 2025-12-19

---

## 1. 当前架构分析

### 1.1 Demo 页面 (flyer_chat_demo_page.dart)

**集成方式**: 使用 `flutter_chat_ui` 的 `Chat` 组件

```dart
Chat(
  chatController: _chatController,
  currentUserId: _currentUserId,
  builders: Builders(
    textStreamMessageBuilder: ...,  // 流式消息
    textMessageBuilder: ...,        // 普通消息
  ),
  onMessageSend: _handleMessageSend,
)
```

**Markdown 渲染入口**:
- `textMessageBuilder`: 判断是否为 AI 消息，调用自定义 Markdown 渲染
- 使用 `MarkdownWidget` + 自定义 Generators 渲染

### 1.2 生产页面 (ConversationView)

**当前实现**:
- 使用 `ScrollablePositionedList` 手动构建消息列表
- 消息渲染通过 `_buildMessageBubble` → `EnhancedContentRenderer`
- 流式输出通过 `_streamController` 管理

**关键依赖**:
- `scrollable_positioned_list`: 精确跳转
- `enhanced_content_renderer.dart`: Markdown 渲染
- `stream_output_controller.dart`: 流式控制

---

## 2. 集成可行性分析

### 2.1 markstream-vue 组件 → flutter_chat_ui

| 方面 | 可行性 | 说明 |
|-----|--------|------|
| textMessageBuilder | ✅ 高 | 直接替换为 Markdown 渲染 |
| textStreamMessageBuilder | ✅ 高 | 配合 StreamState 使用 |
| 自定义气泡样式 | ✅ 高 | builders 完全支持 |
| 消息分组 | ⚠️ 中 | 需适配 groupStatus |
| 输入框定制 | ⚠️ 中 | 需要 composerBuilder |

### 2.2 flutter_chat_ui → 替换 ConversationView

| 方面 | 可行性 | 痛点 |
|-----|--------|------|
| 消息列表渲染 | ✅ 高 | Chat 组件自带 |
| 流式输出 | ✅ 高 | TextStreamMessage 类型 |
| 精确跳转 | ⚠️ 中 | 需要 scrollToIndex 适配 |
| 消息编辑 | ⚠️ 中 | 需要自定义实现 |
| 消息导出 | ⚠️ 中 | 需要扩展 |
| 思考气泡 | ⚠️ 中 | 需要 metadata 扩展 |
| 附件系统 | 🔴 难 | 需要完整适配 |
| Token 计数 | ✅ 高 | 可在外部处理 |

### 2.3 痛点总结

1. **消息类型扩展**: flutter_chat_ui 基于 `flutter_chat_core`，需要扩展消息类型
2. **精确跳转**: 需要适配 `scrollToIndex` 功能
3. **附件系统**: 当前使用 `AttachedFile`，需要适配
4. **思考气泡**: 需要通过 metadata 或自定义消息类型实现
5. **消息编辑**: 需要自定义 UI 和逻辑

---

## 3. 集成路线图

### Phase 1: Demo 页面完善 (已完成 90%)

- [x] 代码块增强 (_EnhancedCodeBlock)
- [x] Mermaid 增强 (_EnhancedMermaidBlock)
- [x] 语法高亮主题
- [x] 流式渲染统一
- [ ] 清理旧代码和无用文档

### Phase 2: 适配层设计

```dart
/// 消息内容适配器
abstract class MessageContentAdapter {
  Widget buildFromChatMessage(TextMessage message, bool isSentByMe);
  Widget buildStreamingContent(String text, bool isStreaming);
}

/// Markdown 适配器实现
class MarkdownMessageAdapter implements MessageContentAdapter {
  final bool isDark;
  final MarkdownConfig config;
  
  @override
  Widget buildFromChatMessage(TextMessage message, bool isSentByMe) {
    if (isSentByMe) {
      return Text(message.text); // 用户消息简单渲染
    }
    return _buildMarkdownContent(message);
  }
}
```

### Phase 3: ConversationView 渐进替换

1. **步骤 1**: 创建 `ChatUIConversationView` 包装器
2. **步骤 2**: 迁移消息渲染逻辑
3. **步骤 3**: 迁移流式输出逻辑
4. **步骤 4**: 迁移附件和编辑功能
5. **步骤 5**: 切换默认实现

### Phase 4: 清理和优化

- 删除旧 ConversationView
- 统一样式系统
- 性能优化

---

## 4. 技术方案

### 4.1 消息类型扩展

```dart
// 扩展 TextMessage 的 metadata
final message = TextMessage(
  id: id,
  authorId: authorId,
  text: text,
  metadata: {
    'streaming': true,
    'thinking': thinkingContent,
    'thinkingOpen': true,
    'attachments': [...],
  },
);
```

### 4.2 自定义 Builder 模式

```dart
builders: Builders(
  textMessageBuilder: (context, message, index, {required isSentByMe, groupStatus}) {
    // 判断消息类型
    final metadata = message.metadata ?? {};
    final isStreaming = metadata['streaming'] == true;
    final thinking = metadata['thinking'] as String?;
    
    if (isSentByMe) {
      return _buildUserMessage(message);
    }
    
    return _buildAssistantMessage(
      text: message.text,
      isStreaming: isStreaming,
      thinking: thinking,
    );
  },
),
```

### 4.3 流式输出适配

```dart
// 使用 TextStreamMessage
final streamMessage = TextStreamMessage(
  id: messageId,
  authorId: assistantId,
  streamId: streamId,
);

// StreamManager 管理状态
_streamManager.startStream(streamId, streamMessage);
_streamManager.addChunk(streamId, chunk);
await _streamManager.completeStream(streamId);
```

---

## 5. 风险评估

| 风险 | 等级 | 缓解措施 |
|-----|------|---------|
| API 兼容性 | 中 | 保持 flutter_chat_ui 版本锁定 |
| 性能回退 | 低 | 保留现有优化逻辑 |
| 功能缺失 | 中 | 渐进式迁移，双轨运行 |
| 用户体验变化 | 低 | 保持视觉一致性 |

---

## 6. 时间估算

| 阶段 | 工作量 | 备注 |
|-----|--------|------|
| Phase 1 清理 | 1天 | 删除旧代码和文档 |
| Phase 2 适配层 | 2天 | 设计和实现 |
| Phase 3 迁移 | 5天 | 功能迁移和测试 |
| Phase 4 优化 | 2天 | 清理和优化 |
| **总计** | **10天** | |

---

*本文档基于代码审查生成*
