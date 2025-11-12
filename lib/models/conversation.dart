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
  })  : messages = messages ?? [],
        createdAt = createdAt ?? DateTime.now(),
        updatedAt = updatedAt ?? DateTime.now();

  /// 添加消息
  void addMessage(Message message) {
    messages.add(message);
    updatedAt = DateTime.now();
  }

  /// 删除消息
  void removeMessage(String messageId) {
    messages.removeWhere((msg) => msg.id == messageId);
    updatedAt = DateTime.now();
  }

  /// 清空消息
  void clearMessages() {
    messages.clear();
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
    };
  }

  factory Conversation.fromJson(Map<String, dynamic> json) {
    return Conversation(
      id: json['id'] as String,
      title: json['title'] as String,
      messages: (json['messages'] as List?)
              ?.map((msg) => Message.fromJson(msg))
              .toList() ??
          [],
      createdAt: DateTime.parse(json['createdAt'] as String),
      updatedAt: DateTime.parse(json['updatedAt'] as String),
      systemPrompt: json['systemPrompt'] as String?,
      scrollIndex: json['scrollIndex'] as int?,
      roleId: json['roleId'] as String?,
      roleType: json['roleType'] as String?,
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
    );
  }
}

