# flutter_chat_ui 框架功能说明文档

> 详细介绍 flutter_chat_ui 框架的功能、API 和使用方式
> 最后更新: 2025-12-21

---

## 1. 框架概述

**flutter_chat_ui** 是一个功能丰富的 Flutter 聊天 UI 框架，由 Flyer Chat 团队开发维护。

### 1.1 核心特性

- 📱 **跨平台**: 支持 Android、iOS、Web、macOS、Windows、Linux
- 🎨 **高度可定制**: 完整的主题系统和自定义 Builder
- 📜 **消息类型丰富**: 文本、图片、文件、流式消息等
- ⚡ **性能优化**: 使用 `scrollable_positioned_list` 实现高效滚动
- 🔧 **状态管理**: 内置 `ChatController` 管理消息状态

### 1.2 包依赖关系

```
flutter_chat_ui
├── flutter_chat_core (核心模型)
│   ├── Message 类型定义
│   ├── User 模型
│   └── ChatController 接口
└── scrollable_positioned_list (高效滚动)
```

---

## 2. 核心组件

### 2.1 Chat Widget

**主入口组件**，负责渲染完整聊天界面。

```dart
Chat(
  chatController: _chatController,
  currentUserId: 'user_id',
  theme: chatTheme,
  backgroundColor: Colors.white,
  builders: Builders(...),
  onMessageSend: (text) async { ... },
  resolveUser: (userId) async { ... },
)
```

**主要参数**:

| 参数 | 类型 | 说明 |
|-----|------|------|
| `chatController` | `ChatController` | 消息状态管理器 |
| `currentUserId` | `String` | 当前用户 ID |
| `theme` | `ChatTheme` | 主题配置 |
| `builders` | `Builders` | 自定义 UI 构建器 |
| `onMessageSend` | `Future<void> Function(String)` | 发送消息回调 |
| `resolveUser` | `Future<User> Function(String)` | 用户信息解析 |

### 2.2 ChatController

**消息状态管理接口**，管理消息列表和滚动。

```dart
// 内置实现
final controller = InMemoryChatController();

// 常用方法
await controller.insertMessage(message);
await controller.updateMessage(oldMessage, newMessage);
await controller.removeMessage(messageId);
controller.setMessages(messages);

// 滚动控制
controller.scrollToIndex(index);
```

**InMemoryChatController 源码结构**:
```dart
class InMemoryChatController extends ChatController {
  final List<Message> _messages = [];
  final ItemScrollController _scrollController;
  
  @override
  List<Message> get messages => _messages;
  
  @override
  Future<void> insertMessage(Message message) async {
    _messages.add(message);
    notifyListeners();
  }
  
  @override
  void scrollToIndex(int index, {Duration? duration, Curve? curve}) {
    _scrollController.scrollTo(
      index: index,
      duration: duration ?? Duration.zero,
      curve: curve ?? Curves.easeOut,
    );
  }
}
```

### 2.3 Message 类型

**flutter_chat_core** 定义的消息类型:

```dart
// 基础文本消息
TextMessage(
  id: 'msg_1',
  authorId: 'user_id',
  text: 'Hello, World!',
  createdAt: DateTime.now(),
  metadata: {'key': 'value'},
)

// 流式文本消息
TextStreamMessage(
  id: 'stream_1',
  authorId: 'assistant_id',
  streamId: 'stream_id',
)

// 图片消息
ImageMessage(
  id: 'img_1',
  authorId: 'user_id',
  uri: 'https://example.com/image.jpg',
  width: 800,
  height: 600,
)

// 文件消息
FileMessage(
  id: 'file_1',
  authorId: 'user_id',
  name: 'document.pdf',
  size: 1024,
  uri: 'file://path/to/file',
)
```

---

## 3. Builders 系统

### 3.1 概述

`Builders` 类允许完全自定义消息渲染:

```dart
Builders(
  textMessageBuilder: ...,
  textStreamMessageBuilder: ...,
  imageMessageBuilder: ...,
  fileMessageBuilder: ...,
  composerBuilder: ...,
  scrollToBottomBuilder: ...,
)
```

### 3.2 textMessageBuilder

**渲染普通文本消息**:

```dart
textMessageBuilder: (
  BuildContext context,
  TextMessage message,
  int index, {
  required bool isSentByMe,
  MessageGroupStatus? groupStatus,
}) {
  return Container(
    padding: EdgeInsets.all(12),
    decoration: BoxDecoration(
      color: isSentByMe ? Colors.blue : Colors.grey[200],
      borderRadius: BorderRadius.circular(12),
    ),
    child: Text(message.text),
  );
}
```

**参数说明**:

| 参数 | 说明 |
|-----|------|
| `context` | BuildContext |
| `message` | TextMessage 对象 |
| `index` | 消息在列表中的索引 |
| `isSentByMe` | 是否为当前用户发送 |
| `groupStatus` | 消息分组状态 (first/middle/last/single) |

### 3.3 textStreamMessageBuilder

**渲染流式消息**:

```dart
textStreamMessageBuilder: (
  BuildContext context,
  TextStreamMessage message,
  int index, {
  required bool isSentByMe,
  MessageGroupStatus? groupStatus,
}) {
  // 获取流式状态
  final streamState = _streamManager.getState(message.streamId);
  
  return FlyerChatTextStreamMessage(
    message: message,
    index: index,
    streamState: streamState,
    chunkAnimationDuration: Duration(milliseconds: 50),
  );
}
```

### 3.4 composerBuilder

**自定义输入框**:

```dart
composerBuilder: (BuildContext context) {
  return MyComposer(
    onSend: () => debugPrint('send'),
  );
}
```

---

## 4. 主题系统

### 4.1 ChatTheme

```dart
final chatTheme = ChatTheme(
  colors: ChatColors(
    primary: Colors.blue,
    onPrimary: Colors.white,
    surface: Colors.white,
    onSurface: Colors.black,
    surfaceContainerHigh: Colors.grey[100]!,
    onSurfaceVariant: Colors.grey,
  ),
  typography: ChatTypography(
    bodyMedium: TextStyle(fontSize: 16),
    bodySmall: TextStyle(fontSize: 14),
  ),
  shape: RoundedRectangleBorder(
    borderRadius: BorderRadius.circular(16),
  ),
);
```

### 4.2 颜色配置

| 属性 | 用途 |
|-----|------|
| `primary` | 主色调（用户气泡） |
| `onPrimary` | 主色调上的文字 |
| `surface` | 背景色 |
| `onSurface` | 背景上的文字 |
| `surfaceContainerHigh` | AI 消息气泡 |

---

## 5. 流式消息处理

### 5.1 创建流式消息

```dart
// 1. 创建 TextStreamMessage
final streamMessage = TextStreamMessage(
  id: _uuid.v4(),
  authorId: 'assistant',
  streamId: 'unique_stream_id',
);

// 2. 插入到控制器
await _chatController.insertMessage(streamMessage);

// 3. 开始流式更新
_streamManager.startStream(streamId, streamMessage);
```

### 5.2 更新流式内容

```dart
// 添加 chunk
_streamManager.addChunk(streamId, 'new text chunk');

// 完成流式
await _streamManager.completeStream(streamId);

// 转换为普通消息
final finalMessage = TextMessage(
  id: streamMessage.id,
  authorId: streamMessage.authorId,
  text: accumulatedText,
);
await _chatController.updateMessage(streamMessage, finalMessage);
```

### 5.3 StreamState

```dart
class StreamState {
  final String text;
  final bool isComplete;
  final DateTime? startTime;
  final DateTime? endTime;
  
  // 计算属性
  Duration? get duration => ...;
  double? get charactersPerSecond => ...;
}
```

---

## 6. 高级功能

### 6.1 精确滚动

```dart
// 滚动到指定索引
_chatController.scrollToIndex(
  index,
  duration: Duration(milliseconds: 300),
  curve: Curves.easeOut,
);

// 滚动到底部
final lastIndex = _chatController.messages.length - 1;
_chatController.scrollToIndex(lastIndex);
```

### 6.2 消息元数据

```dart
// 使用 metadata 存储额外信息
final message = TextMessage(
  id: id,
  authorId: authorId,
  text: text,
  metadata: {
    'streaming': true,
    'thinking': thinkingContent,
    'attachments': [...],
    'tokenCount': 150,
  },
);

// 在 builder 中读取
final isStreaming = message.metadata?['streaming'] == true;
```

### 6.3 消息分组

```dart
// groupStatus 表示消息在连续同用户消息中的位置
switch (groupStatus) {
  case MessageGroupStatus.first:
    // 第一条消息，显示头像
    break;
  case MessageGroupStatus.middle:
    // 中间消息，不显示头像
    break;
  case MessageGroupStatus.last:
    // 最后一条消息
    break;
  case MessageGroupStatus.single:
    // 独立消息
    break;
}
```

---

## 7. 与现有项目集成

### 7.1 Demo 页面集成示例

```dart
// lib/pages/flyer_chat_demo_page.dart
class _FlyerChatDemoPageState extends State<FlyerChatDemoPage> {
  late final InMemoryChatController _chatController;
  late final _DemoStreamManager _streamManager;
  
  @override
  void initState() {
    super.initState();
    _chatController = InMemoryChatController();
    _streamManager = _DemoStreamManager(chatController: _chatController);
  }
  
  @override
  Widget build(BuildContext context) {
    return Chat(
      chatController: _chatController,
      currentUserId: 'user',
      builders: Builders(
        textMessageBuilder: _buildTextMessage,
        textStreamMessageBuilder: _buildStreamMessage,
      ),
      onMessageSend: _handleMessageSend,
    );
  }
}
```

### 7.2 自定义 Markdown 渲染

```dart
Widget _buildTextMessage(context, message, index, {required isSentByMe, groupStatus}) {
  if (!isSentByMe) {
    // AI 消息使用 Markdown 渲染
    return MarkdownWidget(
      data: message.text,
      config: MarkdownConfig.darkConfig,
      // ... 配置
    );
  }
  
  // 用户消息简单文本
  return Text(message.text);
}
```

---

## 8. 性能优化

### 8.1 消息缓存

```dart
// 使用 key 缓存复杂组件
textMessageBuilder: (context, message, index, {...}) {
  return KeyedSubtree(
    key: ValueKey(message.id),
    child: _buildComplexContent(message),
  );
}
```

### 8.2 流式更新节流

```dart
// 使用 ChunkBuffer 批量更新
_chunkBuffer = ChunkBuffer(
  onFlush: (content) {
    setState(() {
      _accumulatedText += content;
    });
  },
  flushInterval: Duration(milliseconds: 100),
  flushThreshold: 50,
);
```

---

## 9. 常见问题

### Q1: 如何实现消息编辑？

```dart
// 在 metadata 中存储编辑状态
// 在 builder 中根据状态渲染编辑 UI
final isEditing = message.metadata?['editing'] == true;
if (isEditing) {
  return TextField(controller: _editController);
}
```

### Q2: 如何实现消息删除？

```dart
// 使用 ChatController
await _chatController.removeMessage(messageId);
```

### Q3: 如何获取消息位置？

```dart
// 使用 ItemPositionsListener
_chatController.itemPositionsListener.itemPositions.addListener(() {
  final positions = _chatController.itemPositionsListener.itemPositions.value;
  // 处理可见消息位置
});
```

---

## 10. 参考链接

- [flutter_chat_ui pub.dev](https://pub.dev/packages/flutter_chat_ui)
- [flutter_chat_core 源码](https://github.com/flyerhq/flutter_chat_core)
- [官方示例](https://github.com/flyerhq/flutter_chat_ui/tree/main/example)
- [flyer_chat_text_message](https://pub.dev/packages/flyer_chat_text_message)
- [flyer_chat_text_stream_message](https://pub.dev/packages/flyer_chat_text_stream_message)

---

*本文档基于 flutter_chat_ui 源码和使用经验编写*
