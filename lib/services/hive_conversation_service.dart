import 'package:hive_flutter/hive_flutter.dart';
import '../models/conversation.dart';
import '../models/message.dart';
import '../models/attached_file.dart';

/// Hive 实现的会话管理服务
/// 
/// 保持与 ConversationService 相同的接口，实现无缝迁移
class HiveConversationService {
  static const String _conversationsBoxName = 'conversations';
  static const String _currentConversationKey = 'current_conversation_id';
  
  Box<Conversation>? _conversationsBox;
  Box? _settingsBox;
  
  /// 初始化 Hive 数据库
  Future<void> initialize() async {
    // 初始化 Hive（只需调用一次）
    await Hive.initFlutter();
    
    // 注册适配器
    if (!Hive.isAdapterRegistered(0)) {
      Hive.registerAdapter(ConversationAdapter());
    }
    if (!Hive.isAdapterRegistered(1)) {
      Hive.registerAdapter(MessageAdapter());
    }
    if (!Hive.isAdapterRegistered(2)) {
      Hive.registerAdapter(FileTypeAdapter());
    }
    if (!Hive.isAdapterRegistered(3)) {
      Hive.registerAdapter(AttachedFileSnapshotAdapter());
    }
    
    // 打开数据库
    _conversationsBox = await Hive.openBox<Conversation>(_conversationsBoxName);
    _settingsBox = await Hive.openBox('settings');
  }
  
  /// 保存所有会话
  Future<void> saveConversations(List<Conversation> conversations) async {
    final box = _conversationsBox;
    if (box == null) throw Exception('Hive not initialized');
    
    // 清空并重新保存所有会话
    await box.clear();
    
    // 使用会话ID作为key存储
    for (final conversation in conversations) {
      await box.put(conversation.id, conversation);
    }
  }
  
  /// 加载所有会话
  Future<List<Conversation>> loadConversations() async {
    final box = _conversationsBox;
    if (box == null) throw Exception('Hive not initialized');
    
    if (box.isEmpty) {
      // 创建默认会话
      final defaultConversation = Conversation(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        title: '新对话',
      );
      return [defaultConversation];
    }
    
    // 返回所有会话，按更新时间排序
    final conversations = box.values.toList();
    conversations.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
    return conversations;
  }
  
  /// 保存当前会话 ID
  Future<void> saveCurrentConversationId(String id) async {
    final box = _settingsBox;
    if (box == null) throw Exception('Hive not initialized');
    
    await box.put(_currentConversationKey, id);
  }
  
  /// 加载当前会话 ID
  Future<String?> loadCurrentConversationId() async {
    final box = _settingsBox;
    if (box == null) throw Exception('Hive not initialized');
    
    return box.get(_currentConversationKey) as String?;
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
    final conversationsBox = _conversationsBox;
    final settingsBox = _settingsBox;
    
    if (conversationsBox == null || settingsBox == null) {
      throw Exception('Hive not initialized');
    }
    
    await conversationsBox.clear();
    await settingsBox.delete(_currentConversationKey);
  }
  
  /// 关闭数据库
  Future<void> close() async {
    await _conversationsBox?.close();
    await _settingsBox?.close();
  }
}
