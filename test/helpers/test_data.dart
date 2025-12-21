

import 'package:chatboxapp/models/conversation.dart';
import 'package:chatboxapp/models/message.dart';

/// 测试数据工厂类
/// 提供创建会话和消息的便捷方法
class TestData {
  /// 创建测试会话
  static Conversation createTestConversation({
    String? id,
    String? title,
    List<Message>? messages,
    DateTime? createdAt,
    DateTime? updatedAt,
    String? systemPrompt,
    int? scrollIndex,
    String? roleId,
    String? roleType,
  }) {
    return Conversation(
      id: id ?? 'conv-test',
      title: title ?? '测试会话',
      messages: messages ?? [createTestMessage()],
      createdAt: createdAt ?? DateTime(2024, 1, 1, 12, 0),
      updatedAt: updatedAt ?? DateTime(2024, 1, 1, 12, 0),
      systemPrompt: systemPrompt,
      scrollIndex: scrollIndex,
      roleId: roleId,
      roleType: roleType,
    );
  }

  /// 创建用户消息
  static Message createUserMessage({
    String? id,
    String? content,
    DateTime? timestamp,
  }) {
    return Message(
      id: id ?? 'msg-user-test',
      content: content ?? '测试用户消息',
      isUser: true,
      timestamp: timestamp ?? DateTime(2024, 1, 1, 12, 0),
    );
  }

  /// 创建 AI 消息
  static Message createAiMessage({
    String? id,
    String? content,
    DateTime? timestamp,
    String? modelName,
    String? providerName,
    int? inputTokens,
    int? outputTokens,
  }) {
    return Message(
      id: id ?? 'msg-ai-test',
      content: content ?? 'AI回复内容',
      isUser: false,
      timestamp: timestamp ?? DateTime(2024, 1, 1, 12, 1),
      modelName: modelName ?? 'gpt-3.5-turbo',
      providerName: providerName ?? 'OpenAI',
      inputTokens: inputTokens ?? 100,
      outputTokens: outputTokens ?? 150,
    );
  }

  /// 创建测试消息，支持用户/AI
  static Message createTestMessage({
    String? id,
    String? content,
    bool isUser = true,
    DateTime? timestamp,
    String? modelName,
    String? providerName,
    int? inputTokens,
    int? outputTokens,
  }) {
    return isUser
        ? createUserMessage(
            id: id,
            content: content,
            timestamp: timestamp,
          )
        : createAiMessage(
            id: id,
            content: content,
            timestamp: timestamp,
            modelName: modelName,
            providerName: providerName,
            inputTokens: inputTokens,
            outputTokens: outputTokens,
          );
  }

  /// 创建多条消息的会话
  static Conversation createConversationWithMessages({
    int messageCount = 5,
    String? id,
    String? title,
  }) {
    final messages = List<Message>.generate(messageCount, (index) {
      final isUser = index.isEven;
      return createTestMessage(
        id: 'msg-test-$index',
        content: isUser ? '用户消息 $index' : 'AI回复 $index',
        isUser: isUser,
        timestamp: DateTime(2024, 1, 1, 12, index),
      );
    });

    return createTestConversation(
      id: id,
      title: title,
      messages: messages,
    );
  }
}
