# 停止按钮调试指南

## 问题描述
停止按钮被点击后，截断的消息应该保存为正常消息，但实际上消息消失了。

## 当前实现逻辑

### `_stopStreaming()` 方法（conversation_view.dart:479-524）

```dart
Future<void> _stopStreaming() async {
  // 1. 停止流控制器（_isStreaming 立即变为 false）
  await _streamController.stop();

  // 2. 如果有内容，保存消息
  if (_currentAssistantMessage.isNotEmpty) {
    // 创建消息对象
    final assistantMessage = Message(...);
    
    // 3. 在同一个 setState 中完成所有状态更新
    setState(() {
      widget.conversation.addMessage(assistantMessage);  // 先添加
      _currentAssistantMessage = '';  // 再清空
      _isLoading = false;
    });
    
    widget.onConversationUpdated();
  }
}
```

## 可能的问题

### 1. 渲染时序问题
`_currentAssistantMessage` 的临时显示依赖于：

```dart
// conversation_view.dart:992
itemCount: widget.conversation.messages.length + (_currentAssistantMessage.isEmpty ? 0 : 1)
```

**问题**：当 `setState` 执行时，`_currentAssistantMessage` 被清空，临时消息立即从列表中移除。虽然同时添加了正式消息，但可能存在渲染竞争。

### 2. StreamController 状态同步
按钮状态依赖 `_streamController.isStreaming`：

```dart
// conversation_view.dart:1251
isStreaming: _streamController.isStreaming
```

当 `stop()` 被调用时（line 101），`_isStreaming` **立即**设为 false，导致：
1. 按钮立即变为"发送"图标 ✅
2. UI 重新渲染
3. 此时 `_currentAssistantMessage` 还在，所以临时消息还显示
4. 但随后的 `setState` 清空了 `_currentAssistantMessage`

## 解决方案

### 方案 1：延迟清空（推荐）
不要立即清空 `_currentAssistantMessage`，而是在添加消息后的下一帧再清空：

```dart
Future<void> _stopStreaming() async {
  await _streamController.stop();

  if (_currentAssistantMessage.isNotEmpty) {
    final assistantMessage = Message(
      content: _currentAssistantMessage,
      ...
    );

    setState(() {
      widget.conversation.addMessage(assistantMessage);
      _isLoading = false;
      // 不要立即清空 _currentAssistantMessage
    });

    // 下一帧再清空
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) {
        setState(() {
          _currentAssistantMessage = '';
        });
      }
    });

    widget.onConversationUpdated();
  }
}
```

### 方案 2：使用局部变量
在 setState 之前保存内容，避免清空问题：

```dart
Future<void> _stopStreaming() async {
  await _streamController.stop();

  final content = _currentAssistantMessage;  // 保存副本
  if (content.isNotEmpty) {
    final assistantMessage = Message(
      content: content,  // 使用副本
      ...
    );

    setState(() {
      widget.conversation.addMessage(assistantMessage);
      _currentAssistantMessage = '';  // 现在可以安全清空
      _isLoading = false;
    });

    widget.onConversationUpdated();
  }
}
```

### 方案 3：添加调试日志
在关键位置添加日志，查看状态变化：

```dart
Future<void> _stopStreaming() async {
  debugPrint('🛑 [Stop] 开始停止，当前内容长度: ${_currentAssistantMessage.length}');
  
  await _streamController.stop();
  debugPrint('🛑 [Stop] 流已停止，isStreaming: ${_streamController.isStreaming}');

  if (_currentAssistantMessage.isNotEmpty) {
    debugPrint('🛑 [Stop] 准备保存消息，长度: ${_currentAssistantMessage.length}');
    
    final assistantMessage = Message(...);
    
    setState(() {
      widget.conversation.addMessage(assistantMessage);
      debugPrint('🛑 [Stop] 消息已添加到会话，总消息数: ${widget.conversation.messages.length}');
      _currentAssistantMessage = '';
      _isLoading = false;
    });
    
    debugPrint('🛑 [Stop] setState 完成，_currentAssistantMessage 已清空');
  }
}
```

## 测试步骤

1. 添加调试日志
2. 运行 `flutter run -v`
3. 发送消息
4. 在回复过程中点击停止
5. 查看控制台输出
6. 检查消息列表

## 预期结果

✅ 停止后，应该看到：
- 按钮立即变为发送图标
- 截断的消息保存为正常消息并显示在列表中
- 可以对该消息进行所有操作（复制、删除等）

❌ 如果失败，会看到：
- 临时消息闪烁后消失
- 消息列表中没有截断的内容
