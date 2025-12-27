# flutter_chat_ui 功能映射

> 生产项目功能与 flutter_chat_ui API 的详细对应关系，包含代码示例。

## 1. 核心 API 概览

### 1.1 Chat Widget

```dart
Chat(
  chatController: InMemoryChatController(),
  user: const User(id: 'user'),
  builders: Builders(...),
  theme: ChatTheme(...),
  composerBuilder: (context) => CustomInputWidget(),
  scrollController: ScrollController(),
  onEndReached: () async { /* 加载更多 */ },
  onMessageTap: (message) { /* 消息点击 */ },
  onMessageLongPress: (message) { /* 消息长按 */ },
)
```

### 1.2 ChatController API

| 方法 | 用途 | 对应生产功能 |
|------|------|-------------|
| `insertMessage(message)` | 插入消息 | `conversation.addMessage()` |
| `updateMessage(old, new)` | 更新消息 | 编辑消息内容 |
| `removeMessage(id)` | 删除消息 | 删除消息 |
| `scrollToMessage(id)` | 滚动到消息 | 搜索定位 |
| `messages` | 获取消息列表 | `conversation.messages` |

---

## 2. Builders 详细映射

### 2.1 textMessageBuilder

**签名**:
```dart
Widget Function(
  BuildContext context,
  TextMessage message,
  int index, {
  required bool isSentByMe,
  MessageGroupStatus? groupStatus,
})
```

**生产代码映射**:

| 生产功能 | 实现方式 |
|----------|----------|
| 消息气泡 | 返回自定义 Container |
| Markdown 渲染 | 使用 MarkdownWidget |
| 思考块解析 | 调用 `_splitByThinkingBlocks()` |
| 消息操作按钮 | 在返回的 Widget 中添加 |
| 编辑模式 | 条件渲染 TextField |
| 高亮效果 | 通过外部状态控制边框样式 |
| 附件预览 | 从 metadata 读取并渲染 |

**示例实现**:
```dart
textMessageBuilder: (context, message, index, {required isSentByMe, groupStatus}) {
  final metadata = message.metadata ?? {};
  final attachedFiles = metadata['attachedFiles'] as List?;
  final isEditing = _editingMessageId == message.id;
  final isHighlighted = _highlightedMessageId == message.id;
  
  return Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      // 消息头部
      _MessageHeader(
        authorId: message.authorId,
        createdAt: message.createdAt,
        modelName: metadata['modelName'],
        providerName: metadata['providerName'],
      ),
      
      // 附件预览 (用户消息)
      if (isSentByMe && attachedFiles != null)
        _AttachmentsPreview(files: attachedFiles),
      
      // 消息内容
      AnimatedContainer(
        duration: Duration(milliseconds: 200),
        decoration: BoxDecoration(
          color: isSentByMe 
              ? Theme.of(context).colorScheme.primaryContainer
              : Theme.of(context).colorScheme.surfaceContainerHigh,
          borderRadius: BorderRadius.circular(16),
          border: isHighlighted ? Border.all(
            color: Theme.of(context).colorScheme.primary,
            width: 3,
          ) : null,
        ),
        child: isEditing
            ? _EditTextField(controller: _editController)
            : _MessageContent(
                text: message.text,
                isSentByMe: isSentByMe,
              ),
      ),
      
      // 操作按钮
      if (!isEditing)
        MessageActions(
          isUser: isSentByMe,
          onCopy: () => _copyMessage(message.text),
          onRegenerate: () => _regenerateFromMessage(message),
          onEdit: () => _startEditMessage(message),
          onDelete: () => _deleteMessage(message),
          onExport: !isSentByMe ? () => _exportMessage(message) : null,
        ),
      
      // 编辑模式按钮
      if (isEditing)
        EditModeActions(
          onCancel: _cancelEdit,
          onSave: () => _saveEdit(message),
          onResend: isSentByMe ? () => _saveAndResend(message) : null,
        ),
    ],
  );
}
```

---

### 2.2 textStreamMessageBuilder

**签名**:
```dart
Widget Function(
  BuildContext context,
  TextStreamMessage message,
  int index, {
  required bool isSentByMe,
  MessageGroupStatus? groupStatus,
})
```

**生产代码映射**:

| 生产功能 | 实现方式 |
|----------|----------|
| 流式内容显示 | 使用 `message.text` 实时更新 |
| 思考气泡 | 解析 `<think>` 标签并分离渲染 |
| 打字机效果 | 使用 `_StreamingMarkdownBody` |
| 加载指示器 | 内容为空时显示 SpinKitThreeBounce |

**示例实现**:
```dart
textStreamMessageBuilder: (context, message, index, {required isSentByMe, groupStatus}) {
  final content = message.text;
  
  // 解析思考内容
  final thinkingVisible = _thinkingContent.isNotEmpty || _isThinkingOpen;
  
  return Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      // 消息头部
      _MessageHeader(
        authorId: message.authorId,
        createdAt: _currentUserSendTime ?? DateTime.now(),
        modelName: _currentModelName,
        providerName: _currentProviderName,
      ),
      
      // 思考气泡
      if (thinkingVisible)
        ThinkingBubble(
          content: _thinkingContent,
          isOpen: _isThinkingOpen,
          isExpanded: _thinkingExpanded,
          seconds: _thinkingSeconds,
          onToggle: () => setState(() => _thinkingExpanded = !_thinkingExpanded),
        ),
      
      // 正文气泡
      if (content.isNotEmpty)
        Container(
          padding: EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Theme.of(context).colorScheme.surfaceContainerHigh,
            borderRadius: BorderRadius.circular(16),
          ),
          child: StreamingMarkdownBody(
            text: content,
            splitStableMarkdown: _splitStableMarkdown,
          ),
        )
      else if (!thinkingVisible)
        // 加载指示器
        Row(
          children: [
            SpinKitThreeBounce(size: 14),
            SizedBox(width: 8),
            Text('正在输入...'),
          ],
        ),
    ],
  );
}
```

---

### 2.3 其他 Builders

| Builder | 用途 | 是否需要实现 |
|---------|------|-------------|
| `imageMessageBuilder` | 图片消息 | ⚠️ 可选 |
| `fileMessageBuilder` | 文件消息 | ⚠️ 可选 |
| `systemMessageBuilder` | 系统消息 | ⚠️ 可选 |
| `customMessageBuilder` | 自定义消息 | ⚠️ 可选 |
| `composerBuilder` | 输入区域 | ✅ 必需 (使用 OwuiComposer) |
| `scrollToBottomBuilder` | 回到底部按钮 | ✅ 推荐 |

---

## 3. 主题系统映射

### 3.1 ChatTheme 配置

```dart
ChatTheme(
  colors: ChatColors(
    primary: Theme.of(context).colorScheme.primary,
    onPrimary: Theme.of(context).colorScheme.onPrimary,
    surface: Theme.of(context).colorScheme.surface,
    onSurface: Theme.of(context).colorScheme.onSurface,
    surfaceContainerHigh: Theme.of(context).colorScheme.surfaceContainerHigh,
    onSurfaceVariant: Theme.of(context).colorScheme.onSurfaceVariant,
  ),
  typography: ChatTypography(
    bodyMedium: TextStyle(fontSize: 15),
    bodySmall: TextStyle(fontSize: 13),
  ),
  shape: RoundedRectangleBorder(
    borderRadius: BorderRadius.circular(16), // AppleTokens.corners.bubble
  ),
)
```

### 3.2 与 ChatBoxTokens 统一

```dart
// 创建统一的主题工厂
ChatTheme createChatTheme(BuildContext context) {
  final isDark = Theme.of(context).brightness == Brightness.dark;
  
  return ChatTheme(
    colors: ChatColors(
      primary: isDark ? Color(0xFF0A84FF) : Color(0xFF007AFF),
      onPrimary: Colors.white,
      surface: Theme.of(context).colorScheme.surface,
      onSurface: Theme.of(context).colorScheme.onSurface,
      surfaceContainerHigh: isDark 
          ? Color(0xFF1C1C1E) 
          : Color(0xFFF2F2F7),
      onSurfaceVariant: Color(0xFF8E8E93),
    ),
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(ChatBoxTokens.radius.large), // 16px
    ),
  );
}
```

---

## 4. 滚动控制映射

### 4.1 滚动到消息

**生产代码**:
```dart
void scrollToMessage(String messageId) {
  final index = widget.conversation.messages.indexWhere((m) => m.id == messageId);
  _itemScrollController.scrollTo(
    index: index,
    duration: Duration(milliseconds: 500),
    alignment: 0.2,
  );
}
```

**flutter_chat_ui**:
```dart
void scrollToMessage(String messageId) {
  chatController.scrollToMessage(messageId);
  // 或使用底层 ScrollController
}
```

### 4.2 智能滚动

**可复用组件**: `SmartScrollController`

```dart
// 初始化
_smartScrollController = SmartScrollController(
  scrollController: _scrollController,
  // flutter_chat_ui 的滚动监听方式可能不同
);

// 流式输出时自动滚动
_smartScrollController.autoScrollToBottom(
  messageCount: messages.length,
  smooth: false,
);
```

---

## 5. 消息操作映射

### 5.1 复制消息

```dart
void _copyMessage(String content) {
  Clipboard.setData(ClipboardData(text: content));
  AppleToast.success(context, message: '已复制到剪贴板');
}
```

### 5.2 删除消息

```dart
Future<void> _deleteMessage(TextMessage message) async {
  // 从 flutter_chat_ui 控制器删除
  await chatController.removeMessage(message.id);
  
  // 同步到 Conversation
  widget.conversation.removeMessage(message.id);
  widget.onConversationUpdated();
}
```

### 5.3 编辑消息

```dart
void _startEditMessage(TextMessage message) {
  setState(() {
    _editingMessageId = message.id;
    _editController.text = message.text;
  });
}

Future<void> _saveEdit(TextMessage message) async {
  final newContent = _editController.text.trim();
  if (newContent.isEmpty) return;

  final newMessage = TextMessage(
    id: message.id,
    authorId: message.authorId,
    createdAt: message.createdAt,
    text: newContent,
    metadata: message.metadata,
  );

  await chatController.updateMessage(message, newMessage);
  
  // 同步到 Conversation
  final originalMsg = MessageAdapter.fromTextMessage(message);
  originalMsg.content = newContent;
  widget.onConversationUpdated();

  setState(() {
    _editingMessageId = null;
    _editController.clear();
  });
}
```

### 5.4 重新生成

```dart
Future<void> _regenerateFromMessage(TextMessage message) async {
  final originalMsg = MessageAdapter.fromTextMessage(message);
  final messageIndex = widget.conversation.messages.indexWhere(
    (m) => m.id == message.id
  );
  
  if (messageIndex < 0) return;

  // 检查附件...
  
  if (originalMsg.isUser) {
    // 删除该消息及之后的所有消息
    final messagesToRemove = widget.conversation.messages
        .skip(messageIndex)
        .map((m) => m.id)
        .toList();
    
    for (final id in messagesToRemove) {
      await chatController.removeMessage(id);
      widget.conversation.removeMessage(id);
    }
    
    // 重新发送
    _messageController.text = originalMsg.content;
    await _sendMessage();
  } else {
    // AI 消息：找到上一条用户消息
    // ...
  }
}
```

---

## 6. 流式输出映射

### 6.1 开始流式输出

```dart
Future<void> _sendMessage() async {
  final text = _messageController.text.trim();
  if (text.isEmpty) return;

  // 添加用户消息
  final userMessage = TextMessage(
    id: DateTime.now().millisecondsSinceEpoch.toString(),
    authorId: 'user',
    createdAt: DateTime.now(),
    text: text,
    metadata: {
      'attachedFiles': _attachedFiles.map((f) => f.toJson()).toList(),
    },
  );
  await chatController.insertMessage(userMessage);

  // 创建流式消息
  final streamId = _uuid.v4();
  final streamMessage = TextStreamMessage(
    id: streamId,
    authorId: 'assistant',
    createdAt: DateTime.now(),
    text: '',
    metadata: {'streaming': true},
  );
  await chatController.insertMessage(streamMessage);

  setState(() {
    _isLoading = true;
    _currentAssistantMessage = '';
  });

  // 开始流式输出
  await _streamController.startStreaming(
    provider: provider,
    modelName: modelName,
    messages: chatMessages,
    parameters: parameters,
    onChunk: (chunk) {
      _chunkBuffer.add(chunk);
    },
    onDone: () async {
      // 替换为普通消息
      final finalMessage = TextMessage(
        id: streamId,
        authorId: 'assistant',
        createdAt: DateTime.now(),
        text: _currentAssistantMessage,
        metadata: {...},
      );
      await chatController.updateMessage(streamMessage, finalMessage);
      
      setState(() {
        _isLoading = false;
      });
    },
    onError: (error) {
      // 处理错误
    },
  );
}
```

### 6.2 停止流式输出

```dart
Future<void> _stopStreaming() async {
  await _streamController.stop();
  
  if (_currentAssistantMessage.isNotEmpty) {
    // 保存已生成的内容
    final partialMessage = TextMessage(
      id: _currentStreamId,
      authorId: 'assistant',
      createdAt: DateTime.now(),
      text: _currentAssistantMessage,
    );
    
    // 更新消息
    // ...
  }
}
```

---

## 7. 附件处理映射

### 7.1 附件存储

```dart
// 通过 metadata 存储附件信息
final userMessage = TextMessage(
  id: messageId,
  authorId: 'user',
  createdAt: DateTime.now(),
  text: text,
  metadata: {
    'attachedFiles': attachedFiles.map((f) => {
      'id': f.id,
      'name': f.name,
      'path': f.path,
      'mimeType': f.mimeType,
      'size': f.size,
    }).toList(),
  },
);
```

### 7.2 附件读取

```dart
Widget _buildAttachmentsPreview(Map<String, dynamic>? metadata) {
  final filesData = metadata?['attachedFiles'] as List?;
  if (filesData == null || filesData.isEmpty) return SizedBox.shrink();
  
  return Wrap(
    spacing: 8,
    children: filesData.map((data) {
      return Chip(
        avatar: Icon(_getFileIcon(data['mimeType'])),
        label: Text(data['name']),
      );
    }).toList(),
  );
}
```

---

## 8. 导出模式映射

### 8.1 导出模式 UI

由于 flutter_chat_ui 不支持导出模式，需要在外层包装:

```dart
Widget build(BuildContext context) {
  return Stack(
    children: [
      // Chat widget
      Chat(
        chatController: _chatController,
        // ...
      ),
      
      // 导出模式工具栏
      if (_isExportMode)
        Positioned(
          top: 0,
          left: 0,
          right: 0,
          child: ExportModeToolbar(
            selectedCount: _selectedMessageIds.length,
            totalCount: _chatController.messages.length,
            onExit: _exitExportMode,
            onSelectAll: _selectAllMessages,
            onExport: _exportSelectedMessages,
          ),
        ),
    ],
  );
}
```

### 8.2 消息选择

在 Builder 中添加复选框:

```dart
textMessageBuilder: (context, message, index, {...}) {
  return Row(
    children: [
      if (_isExportMode)
        Checkbox(
          value: _selectedMessageIds.contains(message.id),
          onChanged: (_) => _toggleMessageSelection(message.id),
        ),
      Expanded(
        child: _MessageBubble(message: message, ...),
      ),
    ],
  );
}
```

---

## 9. 完整集成示例

```dart
class ConversationViewV2 extends StatefulWidget {
  final Conversation conversation;
  final ChatSettings settings;
  final VoidCallback onConversationUpdated;
  final Function(Conversation) onTokenUsageUpdated;

  const ConversationViewV2({...});

  @override
  State<ConversationViewV2> createState() => _ConversationViewV2State();
}

class _ConversationViewV2State extends State<ConversationViewV2> {
  late InMemoryChatController _chatController;
  late EnhancedStreamController _streamController;
  late ChunkBuffer _chunkBuffer;
  
  final _messageController = TextEditingController();
  final _editController = TextEditingController();
  
  String? _editingMessageId;
  String? _highlightedMessageId;
  bool _isLoading = false;
  String _currentAssistantMessage = '';
  
  // 思考状态
  bool _thinkingVisible = false;
  String _thinkingContent = '';
  // ...

  @override
  void initState() {
    super.initState();
    _chatController = InMemoryChatController();
    _streamController = EnhancedStreamController();
    _chunkBuffer = ChunkBuffer(onFlush: _handleChunk);
    
    // 同步现有消息
    for (final msg in widget.conversation.messages) {
      _chatController.insertMessage(MessageAdapter.toTextMessage(msg));
    }
  }

  @override
  Widget build(BuildContext context) {
    final chatTheme = createChatTheme(context);
    
    return Chat(
      chatController: _chatController,
      user: const User(id: 'user'),
      theme: chatTheme,
      builders: Builders(
        textMessageBuilder: _buildTextMessage,
        textStreamMessageBuilder: _buildStreamMessage,
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
        scrollToBottomBuilder: (context, animation, scrollController) {
          return FloatingActionButton.small(
            onPressed: () => scrollController.jumpTo(0),
            child: Icon(Icons.arrow_downward),
          );
        },
      ),
    );
  }

  Widget _buildTextMessage(
    BuildContext context,
    TextMessage message,
    int index, {
    required bool isSentByMe,
    MessageGroupStatus? groupStatus,
  }) {
    // 完整的消息构建逻辑
  }

  Widget _buildStreamMessage(
    BuildContext context,
    TextStreamMessage message,
    int index, {
    required bool isSentByMe,
    MessageGroupStatus? groupStatus,
  }) {
    // 流式消息构建逻辑
  }

  // 消息操作方法...
  // 流式输出方法...
}
```

---

*文档版本: 1.0*
*创建时间: 2024-12-21*
