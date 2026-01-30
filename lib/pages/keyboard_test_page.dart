/// 键盘动画测试页面 - 用于验证官方 flutter_chat_ui 的键盘滚动行为
///
/// 使用方法：
/// 1. 在 pubspec.yaml 中注释掉 dependency_overrides 块以使用官方 pub cache 版本
/// 2. 运行 flutter pub get
/// 3. 导航到此页面测试键盘弹起/收起时的滚动动画
library;

import 'package:flutter/material.dart';
import 'package:flutter_chat_ui/flutter_chat_ui.dart';
import 'package:flutter_chat_core/flutter_chat_core.dart' as chat;
import 'package:uuid/uuid.dart';

class KeyboardTestPage extends StatefulWidget {
  const KeyboardTestPage({super.key});

  @override
  State<KeyboardTestPage> createState() => _KeyboardTestPageState();
}

class _KeyboardTestPageState extends State<KeyboardTestPage> {
  final _chatController = chat.InMemoryChatController();
  static const _currentUserId = 'user-1';
  static const _aiUserId = 'ai-assistant';
  final _uuid = const Uuid();

  @override
  void initState() {
    super.initState();
    _addTemplateMessages();
  }

  void _addTemplateMessages() {
    final messages = <chat.Message>[];

    // 添加足够多的模板消息以测试滚动
    for (var i = 0; i < 20; i++) {
      final isUser = i % 2 == 0;
      messages.add(
        chat.TextMessage(
          id: _uuid.v4(),
          authorId: isUser ? _currentUserId : _aiUserId,
          text: isUser
              ? '这是用户消息 #${i ~/ 2 + 1}，用于测试键盘弹起时的滚动行为。'
              : '这是 AI 回复 #${i ~/ 2 + 1}，包含一些较长的文本内容来模拟真实对话场景。'
                '当键盘弹起时，观察此消息是否能平滑地跟随输入框上移。'
                '如果出现明显的阶梯跳跃或延迟，说明原始框架的 100ms 防抖正在生效。',
          createdAt: DateTime.now().subtract(Duration(minutes: 20 - i)),
        ),
      );
    }

    _chatController.setMessages(messages.reversed.toList());
  }

  void _handleSendPressed(String text) {
    final textMessage = chat.TextMessage(
      authorId: _currentUserId,
      createdAt: DateTime.now(),
      id: _uuid.v4(),
      text: text,
    );
    _chatController.insertMessage(textMessage);

    // 模拟 AI 回复
    Future.delayed(const Duration(milliseconds: 500), () {
      if (mounted) {
        final aiReply = chat.TextMessage(
          authorId: _aiUserId,
          createdAt: DateTime.now(),
          id: _uuid.v4(),
          text: '收到您的消息: "$text"',
        );
        _chatController.insertMessage(aiReply);
      }
    });
  }

  @override
  void dispose() {
    _chatController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('键盘动画测试'),
        actions: [
          IconButton(
            icon: const Icon(Icons.info_outline),
            onPressed: () => _showInfo(context),
          ),
        ],
      ),
      body: Chat(
        chatController: _chatController,
        currentUserId: _currentUserId,
        onMessageSend: _handleSendPressed,
        resolveUser: (userId) async {
          return chat.User(
            id: userId,
            name: userId == _currentUserId ? '用户' : 'AI',
          );
        },
      ),
    );
  }

  void _showInfo(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('测试说明'),
        content: const SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('验证步骤：', style: TextStyle(fontWeight: FontWeight.bold)),
              SizedBox(height: 8),
              Text('1. 滚动到消息列表底部'),
              Text('2. 点击输入框弹出键盘'),
              Text('3. 观察消息是否平滑跟随键盘上移'),
              SizedBox(height: 16),
              Text('预期行为：', style: TextStyle(fontWeight: FontWeight.bold)),
              SizedBox(height: 8),
              Text('• 官方版本（100ms防抖）：可见阶梯跳跃'),
              Text('• 本地修改版本（逐帧）：平滑跟随'),
              SizedBox(height: 16),
              Text('切换版本：', style: TextStyle(fontWeight: FontWeight.bold)),
              SizedBox(height: 8),
              Text('在 pubspec.yaml 中注释/取消注释 dependency_overrides 块'),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('确定'),
          ),
        ],
      ),
    );
  }
}
