/// INPUT: Conversation metadata + message snapshot + message index
/// OUTPUT: Conversation model for persistence and UI
/// POS: Models / Base Chat / Conversation
import 'package:hive/hive.dart';
import 'message.dart';

part 'conversation.g.dart';

/// 会话模型
@HiveType(typeId: 0)
class Conversation {
  @HiveField(0)
  final String id;
  @HiveField(1)
  String title;
  @HiveField(2)
  final List<Message> messages;
  @HiveField(3)
  final DateTime createdAt;
  @HiveField(4)
  DateTime updatedAt;
  @HiveField(5)
  String? systemPrompt; // 系统提示词（角色设定）
  @HiveField(6)
  int? scrollIndex; // 滚动位置（消息索引）
  @HiveField(7)
  String? roleId; // 角色ID（用于精确匹配角色）
  @HiveField(8)
  String? roleType; // 角色类型：'preset'（内置）或 'custom'（自定义）
  @HiveField(9)
  String? threadJson; // 树状消息链 JSON（V2 message branching）
  @HiveField(10)
  String? activeLeafId; // 活动叶子节点（可空，兼容旧数据）
  @HiveField(11)
  String? summary; // 会话摘要（可空，metadata）
  @HiveField(12)
  String? summaryRangeStartId; // 摘要覆盖范围起点
  @HiveField(13)
  String? summaryRangeEndId; // 摘要覆盖范围终点
  @HiveField(14)
  DateTime? summaryUpdatedAt; // 摘要更新时间
  @HiveField(15)
  List<String> messageIds; // message ID index (nullable, legacy-compatible)

  Conversation({
    required this.id,
    required this.title,
    List<Message>? messages,
    DateTime? createdAt,
    DateTime? updatedAt,
    this.systemPrompt,
    this.scrollIndex,
    this.roleId,
    this.roleType,
    this.threadJson,
    this.activeLeafId,
    this.summary,
    this.summaryRangeStartId,
    this.summaryRangeEndId,
    this.summaryUpdatedAt,
    List<String>? messageIds,
  })  : messages = messages ?? [],
        createdAt = createdAt ?? DateTime.now(),
        updatedAt = updatedAt ?? DateTime.now(),
        messageIds = List<String>.from(
          messageIds ?? (messages?.map((msg) => msg.id).toList() ?? const []),
        );

  /// 添加消息
  void addMessage(Message message) {
    messages.add(message);
    if (!messageIds.contains(message.id)) {
      messageIds.add(message.id);
    }
    updatedAt = DateTime.now();
  }

  /// 删除消息
  void removeMessage(String messageId) {
    messages.removeWhere((msg) => msg.id == messageId);
    messageIds.remove(messageId);
    updatedAt = DateTime.now();
  }

  /// 清空消息
  void clearMessages() {
    messages.clear();
    messageIds.clear();
    updatedAt = DateTime.now();
  }

  /// 获取最后一条消息预览
  String get lastMessagePreview {
    if (messages.isEmpty) {
      return '暂无消息';
    }
    final lastMsg = messages.last;
    final content = lastMsg.content.replaceAll('\n', ' ');
    return content.length > 50 ? '${content.substring(0, 50)}...' : content;
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'messages': messages.map((msg) => msg.toJson()).toList(),
      'createdAt': createdAt.toIso8601String(),
      'updatedAt': updatedAt.toIso8601String(),
      'systemPrompt': systemPrompt,
      'scrollIndex': scrollIndex,
      'roleId': roleId,
      'roleType': roleType,
      'threadJson': threadJson,
      'activeLeafId': activeLeafId,
      'summary': summary,
      'summaryRangeStartId': summaryRangeStartId,
      'summaryRangeEndId': summaryRangeEndId,
      'summaryUpdatedAt': summaryUpdatedAt?.toIso8601String(),
      'messageIds': messageIds,
    };
  }

  factory Conversation.fromJson(Map<String, dynamic> json) {
    final parsedMessages = (json['messages'] as List?)
            ?.whereType<Map<String, dynamic>>()
            .map((msg) => Message.fromJson(msg))
            .toList() ??
        <Message>[];
    final parsedMessageIds = (json['messageIds'] as List?)
        ?.whereType<String>()
        .toList();

    return Conversation(
      id: json['id'] as String,
      title: json['title'] as String,
      messages: parsedMessages,
      createdAt: DateTime.parse(json['createdAt'] as String),
      updatedAt: DateTime.parse(json['updatedAt'] as String),
      systemPrompt: json['systemPrompt'] as String?,
      scrollIndex: json['scrollIndex'] as int?,
      roleId: json['roleId'] as String?,
      roleType: json['roleType'] as String?,
      threadJson: json['threadJson'] as String?,
      activeLeafId: json['activeLeafId'] as String?,
      summary: json['summary'] as String?,
      summaryRangeStartId: json['summaryRangeStartId'] as String?,
      summaryRangeEndId: json['summaryRangeEndId'] as String?,
      summaryUpdatedAt: json['summaryUpdatedAt'] != null
          ? DateTime.tryParse(json['summaryUpdatedAt'] as String)
          : null,
      messageIds:
          parsedMessageIds ?? parsedMessages.map((msg) => msg.id).toList(),
    );
  }

  Conversation copyWith({
    String? id,
    String? title,
    List<Message>? messages,
    DateTime? createdAt,
    DateTime? updatedAt,
    String? systemPrompt,
    int? scrollIndex,
    String? roleId,
    String? roleType,
    String? threadJson,
    String? activeLeafId,
    String? summary,
    String? summaryRangeStartId,
    String? summaryRangeEndId,
    DateTime? summaryUpdatedAt,
    List<String>? messageIds,
  }) {
    return Conversation(
      id: id ?? this.id,
      title: title ?? this.title,
      messages: messages ?? this.messages,
      createdAt: createdAt ?? this.createdAt,
      updatedAt: updatedAt ?? this.updatedAt,
      systemPrompt: systemPrompt ?? this.systemPrompt,
      scrollIndex: scrollIndex ?? this.scrollIndex,
      roleId: roleId ?? this.roleId,
      roleType: roleType ?? this.roleType,
      threadJson: threadJson ?? this.threadJson,
      activeLeafId: activeLeafId ?? this.activeLeafId,
      summary: summary ?? this.summary,
      summaryRangeStartId: summaryRangeStartId ?? this.summaryRangeStartId,
      summaryRangeEndId: summaryRangeEndId ?? this.summaryRangeEndId,
      summaryUpdatedAt: summaryUpdatedAt ?? this.summaryUpdatedAt,
      messageIds: messageIds ?? this.messageIds,
    );
  }
}
