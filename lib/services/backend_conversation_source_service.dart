import 'package:dio/dio.dart';

import '../models/attached_file.dart';
import '../models/conversation_thread.dart';
import '../models/mcp/mcp_tool_call.dart';
import '../models/message.dart' as app;
import 'dio_service.dart';

class BackendConversationSourceDeleteUnsupportedException implements Exception {
  final int statusCode;

  const BackendConversationSourceDeleteUnsupportedException(this.statusCode);

  @override
  String toString() =>
      'Backend conversation source delete unsupported: HTTP $statusCode';
}

class BackendSourceBranchOption {
  final String childMessageId;
  final String checkpointId;

  const BackendSourceBranchOption({
    required this.childMessageId,
    required this.checkpointId,
  });
}

class BackendConversationSourceSnapshot {
  final String conversationId;
  final String? checkpointId;
  final String? latestCheckpointId;
  final String? selectedCheckpointId;
  final List<app.Message> messages;

  const BackendConversationSourceSnapshot({
    required this.conversationId,
    required this.checkpointId,
    required this.latestCheckpointId,
    required this.selectedCheckpointId,
    required this.messages,
  });

  factory BackendConversationSourceSnapshot.fromJson(
    Map<String, dynamic> json,
  ) {
    final rawMessages = json['messages'] as List? ?? const [];
    return BackendConversationSourceSnapshot(
      conversationId: json['conversation_id'] as String,
      checkpointId: json['checkpoint_id'] as String?,
      latestCheckpointId: json['latest_checkpoint_id'] as String?,
      selectedCheckpointId: json['selected_checkpoint_id'] as String?,
      messages: rawMessages
          .whereType<Map>()
          .map(
            (item) =>
                _backendMessageToAppMessage(Map<String, dynamic>.from(item)),
          )
          .toList(),
    );
  }
}

class BackendConversationSourceCheckpointDetail {
  final String checkpointId;
  final String? parentCheckpointId;
  final List<app.Message> messages;

  const BackendConversationSourceCheckpointDetail({
    required this.checkpointId,
    required this.parentCheckpointId,
    required this.messages,
  });

  factory BackendConversationSourceCheckpointDetail.fromJson(
    Map<String, dynamic> json,
  ) {
    final rawMessages = json['messages'] as List? ?? const [];
    return BackendConversationSourceCheckpointDetail(
      checkpointId: json['checkpoint_id'] as String,
      parentCheckpointId: json['parent_checkpoint_id'] as String?,
      messages: rawMessages
          .whereType<Map>()
          .map(
            (item) =>
                _backendMessageToAppMessage(Map<String, dynamic>.from(item)),
          )
          .toList(),
    );
  }
}

class BackendConversationSourceProjection {
  final BackendConversationSourceSnapshot current;
  final List<BackendConversationSourceCheckpointDetail> checkpoints;
  final ConversationThread thread;
  final Map<String, String> checkpointByMessageId;
  final Map<String, String> branchCheckpointByChildMessageId;
  final Map<String, int> messageIndexById;

  const BackendConversationSourceProjection({
    required this.current,
    required this.checkpoints,
    required this.thread,
    this.checkpointByMessageId = const {},
    @Deprecated('Use checkpointByMessageId instead')
    this.branchCheckpointByChildMessageId = const {},
    @Deprecated('No longer used') this.messageIndexById = const {},
  });

  String? checkpointIdForExactMessages(List<app.Message> messages) {
    if (messages.isEmpty) return '';

    final currentCheckpointId = current.checkpointId;
    if (currentCheckpointId != null &&
        _messageListsMatchExactly(current.messages, messages)) {
      return currentCheckpointId;
    }

    for (final checkpoint in checkpoints) {
      if (_messageListsMatchExactly(checkpoint.messages, messages)) {
        return checkpoint.checkpointId;
      }
    }
    return null;
  }
}

class BackendConversationSourceService {
  static const String defaultBaseUrl = 'http://localhost:8765';

  final Dio _dio;
  final String _baseUrl;

  BackendConversationSourceService({Dio? dio, String? baseUrl})
    : _dio = dio ?? DioService().controlPlaneDio,
      _baseUrl = baseUrl ?? defaultBaseUrl;

  Future<BackendConversationSourceProjection> getProjection(
    String conversationId,
  ) async {
    final response = await _dio.get(
      '$_baseUrl/api/conversations/$conversationId/source/projection',
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception(
        'Backend conversation source projection failed: $statusCode',
      );
    }
    final payload = Map<String, dynamic>.from(response.data as Map);
    final current = BackendConversationSourceSnapshot.fromJson(
      Map<String, dynamic>.from(payload['current'] as Map),
    );
    final checkpoints = (payload['checkpoints'] as List? ?? const [])
        .whereType<Map>()
        .map(
          (item) => BackendConversationSourceCheckpointDetail.fromJson(
            Map<String, dynamic>.from(item),
          ),
        )
        .toList();

    return _buildProjection(
      current: current,
      checkpoints: checkpoints,
      payload: payload,
    );
  }

  Future<BackendConversationSourceSnapshot> appendMessages({
    required String conversationId,
    required List<app.Message> messages,
    String? baseCheckpointId,
    String? baseMessageId,
    bool selectAfterWrite = true,
    bool touchLastActivity = true,
  }) async {
    final response = await _dio.post(
      '$_baseUrl/api/conversations/$conversationId/source/messages',
      data: {
        'base_checkpoint_id': baseCheckpointId,
        'base_message_id': baseMessageId,
        'messages': messages.map(_appMessageToBackendJson).toList(),
        'select_after_write': selectAfterWrite,
        'touch_last_activity': touchLastActivity,
      },
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend conversation source append failed: $statusCode');
    }
    return BackendConversationSourceSnapshot.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<BackendConversationSourceSnapshot> patchMessage({
    required String conversationId,
    required String messageId,
    required String content,
    DateTime? editedAt,
    String? baseCheckpointId,
    bool selectAfterWrite = true,
    bool touchLastActivity = true,
  }) async {
    final response = await _dio.patch(
      '$_baseUrl/api/conversations/$conversationId/source/messages/$messageId',
      data: {
        'base_checkpoint_id': baseCheckpointId,
        'content': content,
        'edited_at': editedAt?.toUtc().toIso8601String(),
        'select_after_write': selectAfterWrite,
        'touch_last_activity': touchLastActivity,
      }..removeWhere((key, value) => value == null),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend conversation source patch failed: $statusCode');
    }
    return BackendConversationSourceSnapshot.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<BackendConversationSourceSnapshot> deleteMessage({
    required String conversationId,
    required String messageId,
  }) async {
    final response = await _dio.delete(
      '$_baseUrl/api/conversations/$conversationId/source/messages/$messageId',
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode == 405) {
      throw BackendConversationSourceDeleteUnsupportedException(statusCode);
    }
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend conversation source delete failed: $statusCode');
    }
    return BackendConversationSourceSnapshot.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<BackendConversationSourceSnapshot> selectCheckpoint({
    required String conversationId,
    String? checkpointId,
    String? messageId,
  }) async {
    final response = await _dio.put(
      '$_baseUrl/api/conversations/$conversationId/source/selection',
      data: {'checkpoint_id': checkpointId, 'message_id': messageId}
        ..removeWhere((key, value) => value == null),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend conversation source select failed: $statusCode');
    }
    return BackendConversationSourceSnapshot.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<BackendConversationSourceSnapshot> clearSource(
    String conversationId,
  ) async {
    final response = await _dio.delete(
      '$_baseUrl/api/conversations/$conversationId/source',
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend conversation source clear failed: $statusCode');
    }
    return BackendConversationSourceSnapshot.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  BackendConversationSourceProjection _buildProjection({
    required BackendConversationSourceSnapshot current,
    required List<BackendConversationSourceCheckpointDetail> checkpoints,
    Map<String, dynamic>? payload,
  }) {
    final projectionPayload = payload ?? const <String, dynamic>{};
    final checkpointByMessageId =
        (projectionPayload['checkpoint_by_message_id'] as Map? ?? const {}).map(
          (key, value) => MapEntry(key.toString(), value.toString()),
        );

    final threadJson = projectionPayload['thread'];
    final thread = threadJson is Map
        ? _threadFromBackendJson(
            conversationId: current.conversationId,
            json: Map<String, dynamic>.from(threadJson),
          )
        : _buildProjectionThreadFromCheckpoints(
            current: current,
            checkpoints: checkpoints,
          );

    return BackendConversationSourceProjection(
      current: current,
      checkpoints: checkpoints,
      thread: thread,
      checkpointByMessageId: checkpointByMessageId,
    );
  }
}

bool _messageListsMatchExactly(
  List<app.Message> left,
  List<app.Message> right,
) {
  if (left.length != right.length) return false;
  for (var i = 0; i < left.length; i++) {
    if (!_messagesMatchExactly(left[i], right[i])) return false;
  }
  return true;
}

bool _messagesMatchExactly(app.Message left, app.Message right) {
  return left.id == right.id &&
      left.isUser == right.isUser &&
      left.content == right.content &&
      _sameMoment(left.timestamp, right.timestamp) &&
      _sameMoment(left.editedAt, right.editedAt) &&
      left.inputTokens == right.inputTokens &&
      left.outputTokens == right.outputTokens &&
      left.modelName == right.modelName &&
      left.providerName == right.providerName &&
      left.thinkingDurationSeconds == right.thinkingDurationSeconds &&
      _attachmentsMatchExactly(left.attachedFiles, right.attachedFiles) &&
      _toolCallRecordsMatchExactly(left.toolCallRecords, right.toolCallRecords);
}

bool _sameMoment(DateTime? left, DateTime? right) {
  if (left == null || right == null) return left == right;
  return left.isAtSameMomentAs(right);
}

bool _attachmentsMatchExactly(
  List<AttachedFileSnapshot>? left,
  List<AttachedFileSnapshot>? right,
) {
  final leftFiles = left ?? const <AttachedFileSnapshot>[];
  final rightFiles = right ?? const <AttachedFileSnapshot>[];
  if (leftFiles.length != rightFiles.length) return false;
  for (var i = 0; i < leftFiles.length; i++) {
    final leftFile = leftFiles[i];
    final rightFile = rightFiles[i];
    if (leftFile.id != rightFile.id ||
        leftFile.name != rightFile.name ||
        leftFile.path != rightFile.path ||
        leftFile.mimeType != rightFile.mimeType ||
        leftFile.type != rightFile.type) {
      return false;
    }
  }
  return true;
}

Map<String, dynamic> _appMessageToBackendJson(app.Message message) {
  return {
    'id': message.id,
    'role': message.isUser ? 'user' : 'assistant',
    'content': message.content,
    'created_at': message.timestamp.toUtc().toIso8601String(),
    'edited_at': message.editedAt?.toUtc().toIso8601String(),
    'input_tokens': message.inputTokens,
    'output_tokens': message.outputTokens,
    'model_name': message.modelName,
    'provider_name': message.providerName,
    'attached_files':
        message.attachedFiles?.map((file) => file.toJson()).toList() ??
        const [],
    'thinking_duration_seconds': message.thinkingDurationSeconds,
    'tool_call_records':
        message.toolCallRecords?.map((record) => record.toJson()).toList() ??
        const [],
  }..removeWhere((key, value) => value == null);
}

app.Message _backendMessageToAppMessage(Map<String, dynamic> json) {
  return app.Message(
    id: json['id'] as String,
    content: json['content'] as String? ?? '',
    isUser: json['role'] == 'user',
    timestamp: json['created_at'] != null
        ? DateTime.parse(json['created_at'] as String).toLocal()
        : DateTime.now(),
    editedAt: json['edited_at'] != null
        ? DateTime.parse(json['edited_at'] as String).toLocal()
        : null,
    inputTokens: json['input_tokens'] as int?,
    outputTokens: json['output_tokens'] as int?,
    modelName: json['model_name'] as String?,
    providerName: json['provider_name'] as String?,
    attachedFiles: (json['attached_files'] as List? ?? const [])
        .whereType<Map>()
        .map(
          (item) =>
              AttachedFileSnapshot.fromJson(Map<String, dynamic>.from(item)),
        )
        .toList(),
    thinkingDurationSeconds: json['thinking_duration_seconds'] as int?,
    toolCallRecords: (json['tool_call_records'] as List? ?? const [])
        .whereType<Map>()
        .map(
          (item) => McpToolCallRecord.fromJson(Map<String, dynamic>.from(item)),
        )
        .toList(),
  );
}

bool _toolCallRecordsMatchExactly(
  List<McpToolCallRecord>? left,
  List<McpToolCallRecord>? right,
) {
  final leftRecords = left ?? const <McpToolCallRecord>[];
  final rightRecords = right ?? const <McpToolCallRecord>[];
  if (leftRecords.length != rightRecords.length) return false;
  for (var i = 0; i < leftRecords.length; i++) {
    final leftRecord = leftRecords[i];
    final rightRecord = rightRecords[i];
    if (leftRecord.callId != rightRecord.callId ||
        leftRecord.messageId != rightRecord.messageId ||
        leftRecord.toolName != rightRecord.toolName ||
        leftRecord.serverName != rightRecord.serverName ||
        leftRecord.status != rightRecord.status ||
        leftRecord.durationMs != rightRecord.durationMs ||
        leftRecord.argumentsJson != rightRecord.argumentsJson ||
        leftRecord.result != rightRecord.result ||
        leftRecord.errorMessage != rightRecord.errorMessage ||
        !_sameMoment(leftRecord.timestamp, rightRecord.timestamp)) {
      return false;
    }
  }
  return true;
}

ConversationThread _threadFromBackendJson({
  required String conversationId,
  required Map<String, dynamic> json,
}) {
  final rawNodes = json['nodes'] as Map? ?? const {};
  final nodes = <String, ThreadNode>{};
  rawNodes.forEach((key, value) {
    if (value is! Map) return;
    final nodeJson = Map<String, dynamic>.from(value);
    final messageJson = nodeJson['message'];
    if (messageJson is! Map) return;
    final message = _backendMessageToAppMessage(
      Map<String, dynamic>.from(messageJson),
    );
    nodes[key.toString()] = ThreadNode(
      id: nodeJson['id'] as String? ?? key.toString(),
      parentId: nodeJson['parent_id'] as String?,
      message: message,
      children: (nodeJson['children'] as List? ?? const [])
          .map((item) => item.toString())
          .toList(growable: false),
    );
  });

  final thread = ConversationThread(
    conversationId: json['conversation_id'] as String? ?? conversationId,
    nodes: nodes,
    rootId: json['root_id'] as String? ?? '',
    selectedChild: (json['selected_child'] as Map? ?? const {}).map(
      (key, value) => MapEntry(key.toString(), value.toString()),
    ),
    activeLeafId: json['active_leaf_id'] as String?,
  )..normalize();
  return thread;
}

ConversationThread _buildProjectionThreadFromCheckpoints({
  required BackendConversationSourceSnapshot current,
  required List<BackendConversationSourceCheckpointDetail> checkpoints,
}) {
  final nodes = <String, ThreadNode>{};
  final selectedChild = <String, String>{};
  final currentMessages = current.messages;

  for (final checkpoint in checkpoints) {
    for (final message in checkpoint.messages) {
      nodes.putIfAbsent(
        message.id,
        () => ThreadNode(
          id: message.id,
          parentId: null,
          message: message,
          children: const [],
        ),
      );
    }

    for (var i = 0; i < checkpoint.messages.length; i++) {
      final message = checkpoint.messages[i];
      final parentId = i == 0 ? null : checkpoint.messages[i - 1].id;
      final existing = nodes[message.id];
      if (existing == null) continue;
      if (existing.parentId == null && parentId != null) {
        nodes[message.id] = existing.copyWith(parentId: parentId);
      }
      if (parentId != null) {
        final parent = nodes[parentId];
        if (parent != null && !parent.children.contains(message.id)) {
          nodes[parentId] = parent.copyWith(
            children: [...parent.children, message.id],
          );
        }
      }
    }
  }

  for (var i = 0; i < currentMessages.length - 1; i++) {
    selectedChild[currentMessages[i].id] = currentMessages[i + 1].id;
  }

  final rootId = currentMessages.isNotEmpty
      ? currentMessages.first.id
      : (nodes.isNotEmpty ? nodes.keys.first : '');
  return ConversationThread(
    conversationId: current.conversationId,
    nodes: nodes,
    rootId: rootId,
    selectedChild: selectedChild,
    activeLeafId: currentMessages.isNotEmpty ? currentMessages.last.id : rootId,
  )..normalize();
}
