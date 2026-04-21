import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';

import '../models/attached_file.dart';
import '../models/conversation.dart';
import '../models/conversation_settings.dart';
import '../models/message.dart';
import '../models/model_config.dart';
import 'dio_service.dart';

class BackendConversationSummary {
  final String id;
  final String title;
  final String? systemPrompt;
  final String? roleId;
  final String? roleType;
  final String? latestCheckpointId;
  final String? selectedCheckpointId;
  final bool isPinned;
  final bool isArchived;
  final DateTime createdAt;
  final DateTime updatedAt;
  final DateTime lastActivityAt;

  const BackendConversationSummary({
    required this.id,
    required this.title,
    required this.systemPrompt,
    required this.roleId,
    required this.roleType,
    required this.latestCheckpointId,
    required this.selectedCheckpointId,
    required this.isPinned,
    required this.isArchived,
    required this.createdAt,
    required this.updatedAt,
    required this.lastActivityAt,
  });

  factory BackendConversationSummary.fromJson(Map<String, dynamic> json) {
    return BackendConversationSummary(
      id: json['id'] as String,
      title: json['title'] as String,
      systemPrompt: json['system_prompt'] as String?,
      roleId: json['role_id'] as String?,
      roleType: json['role_type'] as String?,
      latestCheckpointId: json['latest_checkpoint_id'] as String?,
      selectedCheckpointId: json['selected_checkpoint_id'] as String?,
      isPinned: json['is_pinned'] as bool? ?? false,
      isArchived: json['is_archived'] as bool? ?? false,
      createdAt: DateTime.parse(json['created_at'] as String),
      updatedAt: DateTime.parse(json['updated_at'] as String),
      lastActivityAt: DateTime.parse(json['last_activity_at'] as String),
    );
  }

  Conversation toConversation() {
    return Conversation(
      id: id,
      title: title,
      messages: <Message>[],
      createdAt: createdAt.toLocal(),
      updatedAt: updatedAt.toLocal(),
      systemPrompt: systemPrompt,
      roleId: roleId,
      roleType: roleType,
    );
  }
}

class BackendConversationSettingsSummary {
  final String conversationId;
  final String? selectedProviderId;
  final String? selectedModelId;
  final ModelParameters parameters;
  final bool enableVision;
  final bool enableTools;
  final bool enableNetwork;
  final bool enableExperimentalStreamingMarkdown;
  final int contextLength;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  const BackendConversationSettingsSummary({
    required this.conversationId,
    required this.selectedProviderId,
    required this.selectedModelId,
    required this.parameters,
    required this.enableVision,
    required this.enableTools,
    required this.enableNetwork,
    required this.enableExperimentalStreamingMarkdown,
    required this.contextLength,
    required this.createdAt,
    required this.updatedAt,
  });

  factory BackendConversationSettingsSummary.fromJson(
    Map<String, dynamic> json, {
    String? fallbackConversationId,
  }) {
    return BackendConversationSettingsSummary(
      conversationId:
          (json['conversation_id'] as String?) ?? fallbackConversationId ?? '',
      selectedProviderId: json['selected_provider_id'] as String?,
      selectedModelId: json['selected_model_id'] as String?,
      parameters: json['parameters'] != null
          ? ModelParameters.fromJson(
              Map<String, dynamic>.from(json['parameters'] as Map),
            )
          : const ModelParameters(),
      enableVision: json['enable_vision'] as bool? ?? false,
      enableTools: json['enable_tools'] as bool? ?? false,
      enableNetwork: json['enable_network'] as bool? ?? false,
      enableExperimentalStreamingMarkdown:
          json['enable_experimental_streaming_markdown'] as bool? ?? false,
      contextLength: json['context_length'] as int? ?? 10,
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'] as String)
          : null,
      updatedAt: json['updated_at'] != null
          ? DateTime.tryParse(json['updated_at'] as String)
          : null,
    );
  }

  ConversationSettings toConversationSettings() {
    return ConversationSettings(
      conversationId: conversationId,
      selectedProviderId: selectedProviderId,
      selectedModelId: selectedModelId,
      parameters: parameters,
      enableVision: enableVision,
      enableTools: enableTools,
      enableNetwork: enableNetwork,
      enableExperimentalStreamingMarkdown: enableExperimentalStreamingMarkdown,
      contextLength: contextLength,
      createdAt: createdAt?.toLocal(),
      updatedAt: updatedAt?.toLocal(),
    );
  }
}

class BackendConversationCompactSummary {
  final String conversationId;
  final String? summary;
  final String? rangeStartMessageId;
  final String? rangeEndMessageId;
  final DateTime? createdAt;
  final DateTime? updatedAt;

  const BackendConversationCompactSummary({
    required this.conversationId,
    required this.summary,
    required this.rangeStartMessageId,
    required this.rangeEndMessageId,
    required this.createdAt,
    required this.updatedAt,
  });

  factory BackendConversationCompactSummary.fromJson(
    Map<String, dynamic> json, {
    String? fallbackConversationId,
  }) {
    return BackendConversationCompactSummary(
      conversationId:
          (json['conversation_id'] as String?) ?? fallbackConversationId ?? '',
      summary: json['summary'] as String?,
      rangeStartMessageId: json['range_start_message_id'] as String?,
      rangeEndMessageId: json['range_end_message_id'] as String?,
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'] as String)
          : null,
      updatedAt: json['updated_at'] != null
          ? DateTime.tryParse(json['updated_at'] as String)
          : null,
    );
  }

  void applyToConversation(Conversation conversation) {
    conversation.summary = summary;
    conversation.summaryRangeStartId = rangeStartMessageId;
    conversation.summaryRangeEndId = rangeEndMessageId;
    conversation.summaryUpdatedAt = updatedAt?.toLocal();
  }
}

class BackendConversationAttachmentSummary {
  final String id;
  final String conversationId;
  final String storageKey;
  final String localPath;
  final String originalName;
  final String mimeType;
  final int sizeBytes;
  final String kind;
  final Map<String, dynamic> metadata;
  final DateTime createdAt;

  const BackendConversationAttachmentSummary({
    required this.id,
    required this.conversationId,
    required this.storageKey,
    required this.localPath,
    required this.originalName,
    required this.mimeType,
    required this.sizeBytes,
    required this.kind,
    required this.metadata,
    required this.createdAt,
  });

  factory BackendConversationAttachmentSummary.fromJson(
    Map<String, dynamic> json,
  ) {
    return BackendConversationAttachmentSummary(
      id: json['id'] as String,
      conversationId: json['conversation_id'] as String,
      storageKey: json['storage_key'] as String,
      localPath: json['local_path'] as String,
      originalName: json['original_name'] as String,
      mimeType: json['mime_type'] as String,
      sizeBytes: json['size_bytes'] as int? ?? 0,
      kind: json['kind'] as String? ?? 'other',
      metadata: Map<String, dynamic>.from(json['metadata'] as Map? ?? const {}),
      createdAt: DateTime.parse(json['created_at'] as String),
    );
  }

  AttachedFile toAttachedFile() {
    return AttachedFile(
      id: id,
      name: originalName,
      path: localPath,
      mimeType: mimeType,
      sizeBytes: sizeBytes,
      type: _fileTypeFromKind(kind),
      uploadedAt: createdAt.toLocal(),
      metadata: {...metadata, 'storageKey': storageKey},
    );
  }

  AttachedFileSnapshot toAttachedFileSnapshot() {
    return AttachedFileSnapshot(
      id: id,
      name: originalName,
      path: localPath,
      mimeType: mimeType,
      type: _fileTypeFromKind(kind),
    );
  }
}

class BackendConversationService {
  static const String defaultBaseUrl = 'http://localhost:8765';

  final Dio _dio;
  final String _baseUrl;

  BackendConversationService({Dio? dio, String? baseUrl})
    : _dio = dio ?? DioService().controlPlaneDio,
      _baseUrl = baseUrl ?? defaultBaseUrl;

  Future<List<BackendConversationSummary>> listConversations({
    String? roleId,
  }) async {
    final response = await _dio.get(
      '$_baseUrl/api/conversations',
      queryParameters: {
        if (roleId != null && roleId.trim().isNotEmpty) 'role_id': roleId,
      },
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend conversation list failed: $statusCode');
    }

    final data = response.data as Map<String, dynamic>;
    final items = data['data'] as List? ?? const [];
    return items
        .whereType<Map>()
        .map(
          (item) => BackendConversationSummary.fromJson(
            Map<String, dynamic>.from(item),
          ),
        )
        .toList();
  }

  Future<BackendConversationSummary> createConversation({
    String? title,
    String? systemPrompt,
    String? roleId,
    String? roleType,
  }) async {
    final response = await _dio.post(
      '$_baseUrl/api/conversations',
      data: {
        'title': title,
        'system_prompt': systemPrompt,
        'role_id': roleId,
        'role_type': roleType,
      },
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend conversation create failed: $statusCode');
    }
    return BackendConversationSummary.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<BackendConversationSummary> updateConversation({
    required String conversationId,
    String? title,
    String? systemPrompt,
    String? roleId,
    String? roleType,
    String? latestCheckpointId,
    String? selectedCheckpointId,
    bool? isPinned,
    bool? isArchived,
    bool touchLastActivity = false,
  }) async {
    final response = await _dio.patch(
      '$_baseUrl/api/conversations/$conversationId',
      data: {
        'title': title,
        'system_prompt': systemPrompt,
        'role_id': roleId,
        'role_type': roleType,
        'latest_checkpoint_id': latestCheckpointId,
        'selected_checkpoint_id': selectedCheckpointId,
        'is_pinned': isPinned,
        'is_archived': isArchived,
        'touch_last_activity': touchLastActivity,
      }..removeWhere((key, value) => value == null),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend conversation update failed: $statusCode');
    }
    return BackendConversationSummary.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<void> deleteConversation(String conversationId) async {
    final response = await _dio.delete(
      '$_baseUrl/api/conversations/$conversationId',
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode == 404) {
      return;
    }
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend conversation delete failed: $statusCode');
    }
  }

  Future<BackendConversationSettingsSummary> getConversationSettings(
    String conversationId,
  ) async {
    final response = await _dio.get(
      '$_baseUrl/api/conversations/$conversationId/settings',
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend conversation settings get failed: $statusCode');
    }
    return BackendConversationSettingsSummary.fromJson(
      Map<String, dynamic>.from(response.data as Map),
      fallbackConversationId: conversationId,
    );
  }

  Future<BackendConversationSettingsSummary> updateConversationSettings(
    ConversationSettings settings,
  ) async {
    final response = await _dio.put(
      '$_baseUrl/api/conversations/${settings.conversationId}/settings',
      data: {
        'selected_provider_id': settings.selectedProviderId,
        'selected_model_id': settings.selectedModelId,
        'parameters': settings.parameters.toJson(),
        'enable_vision': settings.enableVision,
        'enable_tools': settings.enableTools,
        'enable_network': settings.enableNetwork,
        'enable_experimental_streaming_markdown':
            settings.enableExperimentalStreamingMarkdown,
        'context_length': settings.contextLength,
      },
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception(
        'Backend conversation settings update failed: $statusCode',
      );
    }
    return BackendConversationSettingsSummary.fromJson(
      Map<String, dynamic>.from(response.data as Map),
      fallbackConversationId: settings.conversationId,
    );
  }

  Future<BackendConversationCompactSummary> getCompactSummary(
    String conversationId,
  ) async {
    final response = await _dio.get(
      '$_baseUrl/api/conversations/$conversationId/compact-summary',
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception(
        'Backend conversation compact summary get failed: $statusCode',
      );
    }
    return BackendConversationCompactSummary.fromJson(
      Map<String, dynamic>.from(response.data as Map),
      fallbackConversationId: conversationId,
    );
  }

  Future<BackendConversationCompactSummary> updateCompactSummary({
    required String conversationId,
    required String? summary,
    required String? rangeStartMessageId,
    required String? rangeEndMessageId,
    bool touchLastActivity = false,
  }) async {
    final response = await _dio.put(
      '$_baseUrl/api/conversations/$conversationId/compact-summary',
      data: {
        'summary': summary,
        'range_start_message_id': rangeStartMessageId,
        'range_end_message_id': rangeEndMessageId,
        'touch_last_activity': touchLastActivity,
      },
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception(
        'Backend conversation compact summary update failed: $statusCode',
      );
    }
    return BackendConversationCompactSummary.fromJson(
      Map<String, dynamic>.from(response.data as Map),
      fallbackConversationId: conversationId,
    );
  }

  Future<BackendConversationCompactSummary> clearCompactSummary(
    String conversationId,
  ) async {
    final response = await _dio.delete(
      '$_baseUrl/api/conversations/$conversationId/compact-summary',
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception(
        'Backend conversation compact summary clear failed: $statusCode',
      );
    }
    return BackendConversationCompactSummary.fromJson(
      Map<String, dynamic>.from(response.data as Map),
      fallbackConversationId: conversationId,
    );
  }

  Future<List<BackendConversationAttachmentSummary>> listAttachments(
    String conversationId,
  ) async {
    final response = await _dio.get(
      '$_baseUrl/api/conversations/$conversationId/attachments',
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception(
        'Backend conversation attachments list failed: $statusCode',
      );
    }
    final payload = Map<String, dynamic>.from(response.data as Map);
    final items = payload['data'] as List? ?? const [];
    return items
        .whereType<Map>()
        .map(
          (item) => BackendConversationAttachmentSummary.fromJson(
            Map<String, dynamic>.from(item),
          ),
        )
        .toList();
  }

  Future<List<BackendConversationAttachmentSummary>> uploadAttachments({
    required String conversationId,
    required List<AttachedFile> files,
  }) async {
    final response = await _dio.post(
      '$_baseUrl/api/conversations/$conversationId/attachments',
      data: {
        'files': await Future.wait(
          files.map((file) async {
            String? data;
            final path = file.path;
            if (path.isNotEmpty) {
              final localFile = File(path);
              if (await localFile.exists()) {
                data = base64Encode(await localFile.readAsBytes());
              }
            }
            return {
              'client_id': file.id,
              'name': file.name,
              'mime_type': file.mimeType,
              'kind': file.type.name,
              if (path.isNotEmpty) 'path': path,
              if (data != null) 'data': data,
              'metadata': file.metadata,
            };
          }),
        ),
      },
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception(
        'Backend conversation attachments upload failed: $statusCode',
      );
    }
    final payload = Map<String, dynamic>.from(response.data as Map);
    final items = payload['data'] as List? ?? const [];
    return items
        .whereType<Map>()
        .map(
          (item) => BackendConversationAttachmentSummary.fromJson(
            Map<String, dynamic>.from(item),
          ),
        )
        .toList();
  }
}

FileType _fileTypeFromKind(String kind) {
  switch (kind) {
    case 'image':
      return FileType.image;
    case 'video':
      return FileType.video;
    case 'audio':
      return FileType.audio;
    case 'document':
      return FileType.document;
    case 'code':
      return FileType.code;
    default:
      return FileType.other;
  }
}
