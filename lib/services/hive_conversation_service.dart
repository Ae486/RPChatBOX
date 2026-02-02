/// INPUT: Conversation metadata + threadJson/message snapshots
/// OUTPUT: Hive persistence for conversations + messages
/// POS: Services / Storage / Hive
import 'dart:convert';

import 'package:hive_flutter/hive_flutter.dart';
import '../models/conversation.dart';
import '../models/conversation_thread.dart';
import '../models/message.dart';
import '../models/attached_file.dart';

/// Hive 实现的会话管理服务
/// 
/// 保持与 ConversationService 相同的接口，实现无缝迁移
class HiveConversationService {
  static const String _conversationsBoxName = 'conversations';
  static const String _messagesBoxName = 'messages';
  static const String _currentConversationKey = 'current_conversation_id';
  
  Box<Conversation>? _conversationsBox;
  Box<Message>? _messagesBox;
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
    _messagesBox = await Hive.openBox<Message>(_messagesBoxName);
    _settingsBox = await Hive.openBox('settings');
  }
  
  /// 保存所有会话
  Future<void> saveConversations(List<Conversation> conversations) async {
    final box = _conversationsBox;
    final messageBox = _messagesBox;
    if (box == null || messageBox == null) {
      throw Exception('Hive not initialized');
    }

    final messageMap = <String, Message>{};
    final keepIds = <String>{};

    for (final conversation in conversations) {
      final extracted = _extractMessagesForConversation(conversation, messageBox);
      if (extracted.isNotEmpty) {
        final ordered = _sortMessages(extracted);
        final ids = ordered.map((msg) => msg.id).toList();
        conversation.messageIds = ids;
        keepIds.addAll(ids);
        for (final msg in ordered) {
          messageMap[msg.id] = msg;
        }
        continue;
      }

      if (conversation.messageIds.isNotEmpty) {
        keepIds.addAll(conversation.messageIds);
        continue;
      }

      if (conversation.messages.isNotEmpty) {
        final ordered = _sortMessages(conversation.messages);
        final ids = ordered.map((msg) => msg.id).toList();
        conversation.messageIds = ids;
        keepIds.addAll(ids);
        for (final msg in ordered) {
          messageMap[msg.id] = msg;
        }
      } else {
        conversation.messageIds = <String>[];
      }
    }

    if (messageMap.isNotEmpty) {
      await messageBox.putAll(messageMap);
    }
    await _cleanupOrphanMessages(messageBox, keepIds);

    // 清空并重新保存所有会话
    await box.clear();

    // 使用会话ID作为key存储 (messages stored separately)
    for (final conversation in conversations) {
      final persisted = conversation.copyWith(messages: <Message>[]);
      await box.put(conversation.id, persisted);
    }
  }
  
  /// 加载所有会话
  Future<List<Conversation>> loadConversations() async {
    final box = _conversationsBox;
    final messageBox = _messagesBox;
    if (box == null || messageBox == null) {
      throw Exception('Hive not initialized');
    }
    
    if (box.isEmpty) {
      // 创建默认会话
      final defaultConversation = Conversation(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        title: '新对话',
      );
      return [defaultConversation];
    }
    
    // 返回所有会话，按更新时间排序（只读，不写）
    final conversations = box.values.toList();
    for (final conversation in conversations) {
      final thread = _loadThread(
        conversation.threadJson,
        messageBox: messageBox,
      );
      if (thread != null && thread.nodes.isNotEmpty) {
        final allMessages = _collectThreadMessages(thread);
        final ordered = _sortMessages(allMessages);
        conversation.messageIds = ordered.map((msg) => msg.id).toList();
        conversation.activeLeafId = thread.activeLeafId;
        conversation.messages
          ..clear()
          ..addAll(thread.buildActiveChain());
        continue;
      }

      if (conversation.messageIds.isNotEmpty) {
        final loaded = _loadMessagesByIds(messageBox, conversation.messageIds);
        if (loaded.isNotEmpty) {
          conversation.messages
            ..clear()
            ..addAll(loaded);
          continue;
        }
      }

      // 兼容旧数据：如果有内嵌 messages 但无 messageIds，同步 messageIds
      if (conversation.messages.isNotEmpty) {
        conversation.messageIds =
            conversation.messages.map((msg) => msg.id).toList();
      }
    }

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
    final messageBox = _messagesBox;
    
    if (conversationsBox == null || settingsBox == null || messageBox == null) {
      throw Exception('Hive not initialized');
    }
    
    await conversationsBox.clear();
    await messageBox.clear();
    await settingsBox.delete(_currentConversationKey);
  }
  
  /// 关闭数据库
  Future<void> close() async {
    await _conversationsBox?.close();
    await _messagesBox?.close();
    await _settingsBox?.close();
  }

  ConversationThread? _loadThread(String? raw, {Box<Message>? messageBox}) {
    final text = (raw ?? '').trim();
    if (text.isEmpty) return null;
    try {
      final decoded = jsonDecode(text);
      Message? Function(String)? lookup;
      if (messageBox != null) {
        lookup = (id) => messageBox.get(id);
      }
      if (decoded is Map<String, dynamic>) {
        return ConversationThread.fromJson(decoded, messageLookup: lookup);
      }
      if (decoded is Map) {
        return ConversationThread.fromJson(
          decoded.cast<String, dynamic>(),
          messageLookup: lookup,
        );
      }
    } catch (_) {
      // Ignore parsing errors; fall back to linear messages.
    }
    return null;
  }

  List<Message> _collectThreadMessages(ConversationThread thread) {
    if (thread.nodes.isEmpty) return const <Message>[];
    return thread.nodes.values.map((node) => node.message).toList(growable: false);
  }

  List<Message> _loadMessagesByIds(Box<Message> box, List<String> ids) {
    if (ids.isEmpty) return const <Message>[];
    final result = <Message>[];
    for (final id in ids) {
      final message = box.get(id);
      if (message != null) {
        result.add(message);
      }
    }
    return result;
  }

  List<Message> _sortMessages(Iterable<Message> messages) {
    final list = messages.toList(growable: false);
    if (list.length <= 1) return list;
    final sorted = List<Message>.from(list);
    sorted.sort((a, b) {
      final cmp = a.timestamp.compareTo(b.timestamp);
      if (cmp != 0) return cmp;
      return a.id.compareTo(b.id);
    });
    return sorted;
  }

  List<Message> _extractMessagesForConversation(
    Conversation conversation,
    Box<Message> messageBox,
  ) {
    // 优先使用内存中的 conversation.messages 构建 lookup
    // 解决：新消息还未保存到 messageBox 时，messageLookup 返回 null 导致 fallback
    final memoryLookup = <String, Message>{};
    for (final msg in conversation.messages) {
      memoryLookup[msg.id] = msg;
    }

    Message? combinedLookup(String id) {
      return memoryLookup[id] ?? messageBox.get(id);
    }

    final thread = _loadThreadWithLookup(
      conversation.threadJson,
      messageLookup: combinedLookup,
    );
    if (thread != null && thread.nodes.isNotEmpty) {
      return _collectThreadMessages(thread);
    }
    if (conversation.messageIds.isNotEmpty) {
      final loaded = _loadMessagesByIds(messageBox, conversation.messageIds);
      if (loaded.isNotEmpty) {
        return loaded;
      }
    }
    if (conversation.messages.isNotEmpty) {
      return conversation.messages;
    }
    return const <Message>[];
  }

  ConversationThread? _loadThreadWithLookup(
    String? raw, {
    required Message? Function(String) messageLookup,
  }) {
    final text = (raw ?? '').trim();
    if (text.isEmpty) return null;
    try {
      final decoded = jsonDecode(text);
      if (decoded is Map<String, dynamic>) {
        return ConversationThread.fromJson(decoded, messageLookup: messageLookup);
      }
      if (decoded is Map) {
        return ConversationThread.fromJson(
          decoded.cast<String, dynamic>(),
          messageLookup: messageLookup,
        );
      }
    } catch (_) {
      // Ignore parsing errors; fall back to linear messages.
    }
    return null;
  }

  Future<void> _cleanupOrphanMessages(
    Box<Message> box,
    Set<String> keepIds,
  ) async {
    if (box.isEmpty) return;
    if (keepIds.isEmpty) {
      await box.clear();
      return;
    }
    final staleKeys = box.keys
        .whereType<String>()
        .where((id) => !keepIds.contains(id))
        .toList(growable: false);
    if (staleKeys.isNotEmpty) {
      await box.deleteAll(staleKeys);
    }
  }
}
