# 分步迁移计划

> 详细的实施路线图，从局部替换到全局主题生效的完整 Milestone。

## 核心原则

> **"Copy before writing, connect before creating, reuse before inventing."**

1. **优先复制** - 从 Demo 复制已验证的代码
2. **优先连接** - 使用适配器连接现有逻辑
3. **优先复用** - 复用现有控制器和工具类

---

## Phase 0: 准备工作 (1 天)

### 0.1 创建分支

```bash
git checkout -b feature/flutter-chat-ui-migration
```

### 0.2 确认依赖

```yaml
# pubspec.yaml - 已存在
flutter_chat_ui: ^2.0.0
flutter_chat_core: ^2.0.0
flyer_chat_text_message: ^2.0.0
flyer_chat_text_stream_message: ^2.0.0
```

### 0.3 创建迁移目录结构

```
lib/
├─ chat_ui/                          # 新增
│   ├─ builders/
│   │   ├─ text_message_builder.dart
│   │   ├─ stream_message_builder.dart
│   │   └─ message_actions_builder.dart
│   ├─ adapters/
│   │   ├─ message_adapter.dart      # Message <-> TextMessage
│   │   └─ controller_adapter.dart   # 控制器适配
│   ├─ widgets/
│   │   ├─ thinking_bubble.dart      # 从 conversation_view 提取
│   │   └─ streaming_markdown.dart   # 从 demo 复制
│   └─ chat_page_v2.dart             # 新版 ChatPage
```

### 0.4 完成标准

- [ ] 目录结构创建完成
- [ ] 所有测试通过
- [ ] 代码可编译

---

## Phase 1: 消息适配层 (2 天)

### 1.1 创建消息适配器

**文件**: `lib/chat_ui/adapters/message_adapter.dart`

```dart
import 'package:flutter_chat_core/flutter_chat_core.dart';
import '../../models/message.dart';

/// 消息模型适配器
/// 将生产 Message 转换为 flutter_chat_core 的 TextMessage
class MessageAdapter {
  static const String userAuthorId = 'user';
  static const String assistantAuthorId = 'assistant';

  /// 生产 Message -> TextMessage
  static TextMessage toTextMessage(Message msg) {
    return TextMessage(
      id: msg.id,
      authorId: msg.isUser ? userAuthorId : assistantAuthorId,
      createdAt: msg.timestamp,
      text: msg.content,
      metadata: _buildMetadata(msg),
    );
  }

  /// TextMessage -> 生产 Message
  static Message fromTextMessage(TextMessage msg, {bool isUser = false}) {
    return Message(
      id: msg.id,
      content: msg.text,
      isUser: isUser || msg.authorId == userAuthorId,
      timestamp: msg.createdAt,
      inputTokens: msg.metadata?['inputTokens'] as int?,
      outputTokens: msg.metadata?['outputTokens'] as int?,
      modelName: msg.metadata?['modelName'] as String?,
      providerName: msg.metadata?['providerName'] as String?,
      attachedFiles: _parseAttachedFiles(msg.metadata?['attachedFiles']),
    );
  }

  static Map<String, dynamic> _buildMetadata(Message msg) {
    return {
      if (msg.inputTokens != null) 'inputTokens': msg.inputTokens,
      if (msg.outputTokens != null) 'outputTokens': msg.outputTokens,
      if (msg.modelName != null) 'modelName': msg.modelName,
      if (msg.providerName != null) 'providerName': msg.providerName,
      if (msg.attachedFiles != null && msg.attachedFiles!.isNotEmpty)
        'attachedFiles': msg.attachedFiles!.map((f) => f.toJson()).toList(),
    };
  }

  static List<AttachedFileSnapshot>? _parseAttachedFiles(dynamic data) {
    if (data == null) return null;
    if (data is! List) return null;
    return data.map((e) => AttachedFileSnapshot.fromJson(e)).toList();
  }
}
```

### 1.2 创建控制器适配器

**文件**: `lib/chat_ui/adapters/controller_adapter.dart`

```dart
import 'package:flutter_chat_core/flutter_chat_core.dart';
import '../../models/conversation.dart';
import 'message_adapter.dart';

/// 控制器适配器
/// 桥接 Conversation 和 InMemoryChatController
class ControllerAdapter {
  final Conversation conversation;
  late final InMemoryChatController chatController;

  ControllerAdapter(this.conversation) {
    chatController = InMemoryChatController();
    _syncMessages();
  }

  void _syncMessages() {
    for (final msg in conversation.messages) {
      chatController.insertMessage(MessageAdapter.toTextMessage(msg));
    }
  }

  /// 添加消息
  Future<void> addMessage(Message msg) async {
    conversation.addMessage(msg);
    await chatController.insertMessage(MessageAdapter.toTextMessage(msg));
  }

  /// 更新消息
  Future<void> updateMessage(Message oldMsg, Message newMsg) async {
    final oldIndex = conversation.messages.indexWhere((m) => m.id == oldMsg.id);
    if (oldIndex >= 0) {
      conversation.messages[oldIndex] = newMsg;
    }
    await chatController.updateMessage(
      MessageAdapter.toTextMessage(oldMsg),
      MessageAdapter.toTextMessage(newMsg),
    );
  }

  /// 删除消息
  Future<void> removeMessage(String messageId) async {
    conversation.removeMessage(messageId);
    await chatController.removeMessage(messageId);
  }

  void dispose() {
    chatController.dispose();
  }
}
```

### 1.3 完成标准

- [ ] MessageAdapter 单元测试通过
- [ ] ControllerAdapter 单元测试通过
- [ ] 双向转换无数据丢失

---

## Phase 2: 基础 Builder 实现 (3 天)

### 2.1 从 Demo 复制核心组件

**复制清单**:

| 源文件 | 目标文件 |
|--------|----------|
| `flyer_chat_demo_page.dart` 中的 `_splitByThinkingBlocks` | `lib/chat_ui/utils/thinking_parser.dart` |
| `flyer_chat_demo_page.dart` 中的 Markdown 配置 | `lib/chat_ui/widgets/markdown_config.dart` |
| `flyer_chat_demo/streaming_markdown_body.dart` | `lib/chat_ui/widgets/streaming_markdown.dart` |
| `flyer_chat_demo/enhanced_code_block.dart` | `lib/chat_ui/widgets/enhanced_code_block.dart` |

### 2.2 实现 TextMessageBuilder

**文件**: `lib/chat_ui/builders/text_message_builder.dart`

```dart
import 'package:flutter/material.dart';
import 'package:flutter_chat_core/flutter_chat_core.dart';
import '../widgets/message_actions_bar.dart';
import '../widgets/markdown_renderer.dart';
import '../utils/thinking_parser.dart';

typedef TextMessageBuilderCallback = Widget Function(
  BuildContext context,
  TextMessage message,
  int index, {
  required bool isSentByMe,
  MessageGroupStatus? groupStatus,
});

class TextMessageBuilderFactory {
  final void Function(String content) onCopy;
  final void Function(TextMessage message) onRegenerate;
  final void Function(TextMessage message) onEdit;
  final void Function(TextMessage message) onDelete;
  final void Function(TextMessage message)? onExport;
  final String? editingMessageId;
  final TextEditingController? editController;
  final VoidCallback? onCancelEdit;
  final void Function(TextMessage message)? onSaveEdit;
  final void Function(TextMessage message)? onSaveAndResend;
  final String? highlightedMessageId;

  TextMessageBuilderFactory({
    required this.onCopy,
    required this.onRegenerate,
    required this.onEdit,
    required this.onDelete,
    this.onExport,
    this.editingMessageId,
    this.editController,
    this.onCancelEdit,
    this.onSaveEdit,
    this.onSaveAndResend,
    this.highlightedMessageId,
  });

  TextMessageBuilderCallback get builder {
    return (context, message, index, {required isSentByMe, groupStatus}) {
      final isEditing = editingMessageId == message.id;
      final isHighlighted = highlightedMessageId == message.id;
      
      // 解析思考块
      final segments = ThinkingParser.splitByThinkingBlocks(message.text);
      
      return _MessageBubble(
        message: message,
        isSentByMe: isSentByMe,
        isEditing: isEditing,
        isHighlighted: isHighlighted,
        segments: segments,
        editController: editController,
        onCopy: () => onCopy(message.text),
        onRegenerate: () => onRegenerate(message),
        onEdit: () => onEdit(message),
        onDelete: () => onDelete(message),
        onExport: onExport != null ? () => onExport!(message) : null,
        onCancelEdit: onCancelEdit,
        onSaveEdit: onSaveEdit != null ? () => onSaveEdit!(message) : null,
        onSaveAndResend: onSaveAndResend != null ? () => onSaveAndResend!(message) : null,
      );
    };
  }
}

class _MessageBubble extends StatelessWidget {
  // ... 实现细节
}
```

### 2.3 实现 StreamMessageBuilder

**文件**: `lib/chat_ui/builders/stream_message_builder.dart`

```dart
// 复用 Demo 的 textStreamMessageBuilder 逻辑
// 集成思考气泡渲染
```

### 2.4 完成标准

- [ ] 消息可正常渲染
- [ ] Markdown 渲染正确
- [ ] 代码块、Mermaid 正常显示
- [ ] 思考气泡正常显示

---

## Phase 3: 消息操作功能 (2 天)

### 3.1 实现消息操作栏

**文件**: `lib/chat_ui/widgets/message_actions_bar.dart`

```dart
// 从 lib/widgets/message_actions.dart 复制并适配
// 使用 flutter_chat_core 的 Message 类型
```

### 3.2 实现编辑模式

- 条件渲染 TextField
- 保存/取消按钮
- 重新发送按钮 (仅用户消息)

### 3.3 实现重新生成

**关键逻辑** (从 `conversation_view.dart` 复制):

```dart
Future<void> _regenerateFromMessage(TextMessage message) async {
  // 1. 获取原始 Message
  final originalMsg = MessageAdapter.fromTextMessage(message);
  
  // 2. 检查附件
  // 3. 删除后续消息
  // 4. 重新发送
}
```

### 3.4 完成标准

- [ ] 复制功能正常
- [ ] 删除功能正常
- [x] 编辑功能正常
- [ ] 重新生成功能正常
- [x] 编辑并重发功能正常

---

## Phase 4: 流式输出集成 (2 天)

### 4.1 复用现有控制器

**直接复用**:
- `EnhancedStreamController`
- `ChunkBuffer`
- `SmartScrollController`

### 4.2 集成思考气泡

**文件**: `lib/chat_ui/widgets/thinking_bubble.dart`

```dart
// 从 conversation_view.dart 提取思考气泡相关代码
// - _buildInlineThinkingSection()
// - _buildSavedThinkingSection()
// - 呼吸灯动画
// - 计时器
```

### 4.3 实现流式渲染

**文件**: `lib/chat_ui/widgets/streaming_markdown.dart`

```dart
// 从 Demo 复制 _StreamingMarkdownBody
// 集成 StablePrefixParser
```

### 4.4 完成标准

- [ ] 流式输出正常显示
- [ ] 思考气泡正常显示
- [ ] 呼吸灯动画正常
- [ ] 计时器正常
- [ ] 停止生成功能正常

---

## Phase 5: 输入区域集成 (1 天)

### 5.1 替换为 OwuiComposer

V2 输入区使用 `OwuiComposer`（基于 `flutter_chat_ui` 的 `Composer` 结构改造），并复用既有的文件上传/模型选择/对话配置逻辑（来源于 `EnhancedInputArea`），以便后续扩展更多动作按钮（语音、链接附件、工具开关等）时避免反复返工。

### 5.2 集成方式

```dart
Chat(
  chatController: _controller,
  builders: Builders(...),
  composerBuilder: (context) => OwuiComposer(
    textController: _messageController,
    isStreaming: _isLoading || _streamController.isStreaming,
    onSend: _sendMessage,
    onStop: _stopStreaming,
    serviceManager: globalModelServiceManager,
    conversationSettings: _conversationSettings,
    onSettingsChanged: _onSettingsChanged,
    attachmentBarVisible: _attachmentBarVisible,
  ),
)
```

### 5.3 完成标准

- [ ] 输入框正常工作
- [ ] 文件上传正常
- [ ] 模型选择正常
- [ ] 发送/停止按钮正常

---

## Phase 6: 高级功能迁移 (2 天)

### 6.1 导出功能

**迁移策略**: 保持现有逻辑，通过 metadata 获取原始 Message

```dart
void _exportMessage(TextMessage flutterMessage) {
  final originalMsg = MessageAdapter.fromTextMessage(flutterMessage);
  // 使用现有导出逻辑
}
```

### 6.2 搜索定位

**迁移策略**: 复用现有 `SearchPage`（跨会话 contains 搜索 + 预览），跳转后通过宿主
`ConversationViewHostState.scrollToMessage(messageId)` 委派到 V1/V2。

```dart
void scrollToMessage(String messageId) {
  // V2: messageId -> index -> scrollToIndex，并实现“未就绪重试 + 2s 高亮”
}
```

### 6.3 Token 统计

**迁移策略**: 通过 metadata 获取 Token 信息

### 6.4 完成标准

- [x] 导出功能正常
- [x] 搜索定位正常
- [ ] Token 统计正常

---

## Phase 7: 新版 ChatPage 集成 (2 天)

### 7.1 创建 ChatPageV2

**文件**: `lib/chat_ui/chat_page_v2.dart`

```dart
class ChatPageV2 extends StatefulWidget {
  // 复制 ChatPage 的会话管理逻辑
  // 使用新的 ConversationViewV2
}
```

### 7.2 创建 ConversationViewV2

**文件**: `lib/chat_ui/conversation_view_v2.dart`

```dart
class ConversationViewV2 extends StatefulWidget {
  // 使用 flutter_chat_ui 的 Chat widget
  // 集成所有自定义 Builder
}
```

### 7.3 并行运行测试

在 `main.dart` 中添加切换开关:

```dart
// 开发期间可切换
const bool useNewChatUI = true;

home: useNewChatUI ? ChatPageV2() : ChatPage(),
```

### 7.4 完成标准

- [ ] 新版 ChatPage 可正常使用
- [ ] 所有功能与旧版一致
- [ ] 无明显性能回归

---

## Phase 8: 清理与优化 (2 天)

### 8.1 移除旧代码

**删除文件**:
- `lib/widgets/conversation_view.dart` (2371 行)
- `lib/pages/chat_page.dart` (651 行)

**保留文件**:
- `lib/widgets/message_actions.dart` - 可能需要保留作为参考
- `lib/widgets/enhanced_input_area.dart` - 继续使用

### 8.2 重命名

```
lib/chat_ui/chat_page_v2.dart -> lib/pages/chat_page.dart
lib/chat_ui/conversation_view_v2.dart -> lib/widgets/conversation_view.dart
```

### 8.3 代码审查

- 移除未使用的 import
- 统一代码风格
- 添加必要的注释

### 8.4 性能优化

- 检查不必要的 rebuild
- 优化大消息列表滚动
- 检查内存泄漏

### 8.5 完成标准

- [ ] 所有旧代码已移除
- [ ] 代码编译通过
- [ ] 所有测试通过
- [ ] 性能无明显回归

---

## 时间线总结

| Phase | 名称 | 预计时间 | 累计 |
|-------|------|----------|------|
| 0 | 准备工作 | 1 天 | 1 天 |
| 1 | 消息适配层 | 2 天 | 3 天 |
| 2 | 基础 Builder | 3 天 | 6 天 |
| 3 | 消息操作 | 2 天 | 8 天 |
| 4 | 流式输出 | 2 天 | 10 天 |
| 5 | 输入区域 | 1 天 | 11 天 |
| 6 | 高级功能 | 2 天 | 13 天 |
| 7 | 新版集成 | 2 天 | 15 天 |
| 8 | 清理优化 | 2 天 | **17 天** |

**总计: 约 3 周 (17 个工作日)**

---

## 回滚计划

### 触发条件

- 关键功能无法实现
- 性能严重回归 (>50%)
- 用户体验明显下降

### 回滚步骤

1. 切换 `useNewChatUI = false`
2. 保留新代码在 `lib/chat_ui/` 目录
3. 分析失败原因
4. 制定修复计划

### 数据兼容性

由于使用适配器模式，数据层完全兼容，回滚不会丢失任何用户数据。

---

## 验收标准

### 功能验收

- [ ] 所有消息操作功能正常 (复制、编辑、删除、重新生成、编辑重发)
- [ ] 流式输出正常，思考气泡正常
- [ ] 文件上传和附件功能正常
- [x] 搜索定位功能正常
- [x] 导出功能正常
- [ ] Token 统计正常
- [ ] 会话管理功能正常

### 性能验收

- [ ] 首屏加载时间 < 500ms
- [ ] 流式输出无明显卡顿
- [ ] 大消息列表 (1000+) 滚动流畅
- [ ] 内存占用无明显增加

### 代码质量验收

- [ ] 单元测试覆盖率 > 60%
- [ ] 无编译警告
- [ ] 代码审查通过

---

*文档版本: 1.0*
*创建时间: 2024-12-21*
