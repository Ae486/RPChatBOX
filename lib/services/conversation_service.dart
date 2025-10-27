import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/conversation.dart';

/// 会话管理服务
class ConversationService {
  static const String _conversationsKey = 'conversations';
  static const String _currentConversationKey = 'current_conversation_id';

  /// 保存所有会话
  Future<void> saveConversations(List<Conversation> conversations) async {
    final prefs = await SharedPreferences.getInstance();
    final jsonList = conversations.map((conv) => conv.toJson()).toList();
    await prefs.setString(_conversationsKey, json.encode(jsonList));
  }

  /// 加载所有会话
  Future<List<Conversation>> loadConversations() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = prefs.getString(_conversationsKey);

    if (jsonStr == null || jsonStr.isEmpty) {
      // 创建默认会话
      final defaultConversation = Conversation(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        title: '新对话',
      );
      return [defaultConversation];
    }

    try {
      final jsonList = json.decode(jsonStr) as List;
      return jsonList.map((json) => Conversation.fromJson(json)).toList();
    } catch (e) {
      // 数据损坏，返回默认会话
      final defaultConversation = Conversation(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        title: '新对话',
      );
      return [defaultConversation];
    }
  }

  /// 保存当前会话 ID
  Future<void> saveCurrentConversationId(String id) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_currentConversationKey, id);
  }

  /// 加载当前会话 ID
  Future<String?> loadCurrentConversationId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString(_currentConversationKey);
  }

  /// 创建新会话
  Conversation createConversation({
    String? title,
    String? systemPrompt,
    String? roleId,
    String? roleType,
  }) {
    return Conversation(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      title: title ?? '新对话 ${DateTime.now().month}/${DateTime.now().day}',
      systemPrompt: systemPrompt,
      roleId: roleId,
      roleType: roleType,
    );
  }

  /// 删除会话
  Future<void> deleteConversation(
    List<Conversation> conversations,
    String conversationId,
  ) async {
    conversations.removeWhere((conv) => conv.id == conversationId);
    await saveConversations(conversations);
  }

  /// 更新会话标题
  Future<void> updateConversationTitle(
    List<Conversation> conversations,
    String conversationId,
    String newTitle,
  ) async {
    final conv = conversations.firstWhere((c) => c.id == conversationId);
    conv.title = newTitle;
    await saveConversations(conversations);
  }

  /// 清空所有会话
  Future<void> clearAllConversations() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_conversationsKey);
    await prefs.remove(_currentConversationKey);
  }
}

