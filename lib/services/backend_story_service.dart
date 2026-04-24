import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';

import '../adapters/ai_provider.dart';
import '../models/story_runtime.dart';
import 'dio_service.dart';

class BackendStoryService {
  static const String defaultBaseUrl = 'http://localhost:8765';

  final Dio _controlDio;
  final Dio _dataDio;
  final String _baseUrl;

  BackendStoryService({Dio? dio, String? baseUrl})
    : _controlDio = dio ?? DioService().controlPlaneDio,
      _dataDio = dio ?? DioService().dataPlaneDio,
      _baseUrl = baseUrl ?? defaultBaseUrl;

  Future<RpStoryActivationResult> activateWorkspace(String workspaceId) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/setup/workspaces/$workspaceId/activate',
    );
    _ensureSuccess(response, action: 'activate story workspace');
    return RpStoryActivationResult.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<List<RpStorySession>> listSessions() async {
    final response = await _controlDio.get('$_baseUrl/api/rp/story-sessions');
    _ensureSuccess(response, action: 'list story sessions');
    final payload = Map<String, dynamic>.from(response.data as Map);
    final items = payload['data'] as List? ?? const [];
    return items
        .whereType<Map>()
        .map((item) => RpStorySession.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<RpChapterSnapshot> getSession(String sessionId) async {
    final response = await _controlDio.get(
      '$_baseUrl/api/rp/story-sessions/$sessionId',
    );
    _ensureSuccess(response, action: 'get story session');
    return RpChapterSnapshot.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpChapterSnapshot> getChapter(
    String sessionId,
    int chapterIndex,
  ) async {
    final response = await _controlDio.get(
      '$_baseUrl/api/rp/story-sessions/$sessionId/chapters/$chapterIndex',
    );
    _ensureSuccess(response, action: 'get story chapter');
    return RpChapterSnapshot.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpChapterSnapshot> updateRuntimeStoryConfig({
    required String sessionId,
    required Map<String, dynamic> patch,
  }) async {
    final response = await _controlDio.patch(
      '$_baseUrl/api/rp/story-sessions/$sessionId/runtime-config',
      data: {'runtime_story_config': Map<String, dynamic>.from(patch)},
    );
    _ensureSuccess(response, action: 'update story runtime config');
    return RpChapterSnapshot.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpStoryTurnResponse> runTurn({
    required String sessionId,
    required String commandKind,
    required String modelId,
    String? providerId,
    String? userPrompt,
    String? targetArtifactId,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/turn',
      data: {
        'session_id': sessionId,
        'command_kind': commandKind,
        'model_id': modelId,
        if (providerId != null) 'provider_id': providerId,
        if (userPrompt != null && userPrompt.isNotEmpty)
          'user_prompt': userPrompt,
        if (targetArtifactId != null) 'target_artifact_id': targetArtifactId,
      },
    );
    _ensureSuccess(response, action: 'run story turn');
    return RpStoryTurnResponse.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Stream<AIStreamEvent> streamTurn({
    required String sessionId,
    required String commandKind,
    required String modelId,
    String? providerId,
    String? userPrompt,
    String? targetArtifactId,
  }) async* {
    final response = await _dataDio.post<ResponseBody>(
      '$_baseUrl/api/rp/story-sessions/$sessionId/turn/stream',
      data: {
        'session_id': sessionId,
        'command_kind': commandKind,
        'model_id': modelId,
        if (providerId != null) 'provider_id': providerId,
        if (userPrompt != null && userPrompt.isNotEmpty)
          'user_prompt': userPrompt,
        if (targetArtifactId != null) 'target_artifact_id': targetArtifactId,
      },
      options: Options(responseType: ResponseType.stream),
    );
    _ensureSuccess(response, action: 'stream story turn');

    final responseStream = response.data!.stream;
    String? pendingErrorMessage;
    await for (final line
        in responseStream
            .cast<List<int>>()
            .transform(utf8.decoder)
            .transform(const LineSplitter())) {
      final payload = _parseStreamPayload(line);
      if (payload == null) continue;
      final type = payload['type'] as String?;
      if (type == 'error') {
        final error = payload['error'] as Map<String, dynamic>? ?? const {};
        pendingErrorMessage =
            error['message']?.toString() ?? 'Story stream failed';
        continue;
      }
      if (type == 'done') {
        break;
      }
      final event = _eventFromStreamPayload(payload);
      if (event != null) {
        yield event;
      }
    }
    if (pendingErrorMessage != null) {
      throw Exception(pendingErrorMessage);
    }
  }

  Map<String, dynamic>? _parseStreamPayload(String rawLine) {
    final line = rawLine.trim();
    if (line.isEmpty || !line.startsWith('data: ')) return null;
    final dataStr = line.substring(6);
    if (dataStr == '[DONE]') return null;
    return Map<String, dynamic>.from(jsonDecode(dataStr) as Map);
  }

  AIStreamEvent? _eventFromStreamPayload(Map<String, dynamic> parsed) {
    final type = parsed['type'] as String?;
    if (type == null) return null;
    switch (type) {
      case 'thinking_delta':
        final delta = parsed['delta']?.toString() ?? '';
        return delta.isEmpty ? null : AIStreamEvent.thinking(delta);
      case 'text_delta':
        final delta = parsed['delta']?.toString() ?? '';
        return delta.isEmpty
            ? null
            : AIStreamEvent.text(delta, isTypedSemantic: true);
      case 'tool_call':
        final rawToolCalls = parsed['tool_calls'] as List? ?? const [];
        final toolCalls = rawToolCalls
            .whereType<Map>()
            .map((item) => Map<String, dynamic>.from(item))
            .toList();
        return toolCalls.isEmpty ? null : AIStreamEvent.toolCall(toolCalls);
      case 'tool_started':
        final callId = parsed['call_id']?.toString() ?? '';
        return callId.isEmpty
            ? null
            : AIStreamEvent.toolStarted(
                callId: callId,
                toolName: parsed['tool_name']?.toString(),
              );
      case 'tool_result':
        final callId = parsed['call_id']?.toString() ?? '';
        return callId.isEmpty
            ? null
            : AIStreamEvent.toolResult(
                callId: callId,
                toolName: parsed['tool_name']?.toString(),
                result: parsed['result']?.toString() ?? '',
              );
      case 'tool_error':
        final callId = parsed['call_id']?.toString() ?? '';
        return callId.isEmpty
            ? null
            : AIStreamEvent.toolError(
                callId: callId,
                toolName: parsed['tool_name']?.toString(),
                errorMessage:
                    parsed['error']?.toString() ?? 'Unknown tool error',
              );
      case 'usage':
        return AIStreamEvent.usage(
          promptTokens: (parsed['prompt_tokens'] as num?)?.toInt() ?? 0,
          completionTokens: (parsed['completion_tokens'] as num?)?.toInt() ?? 0,
          totalTokens: (parsed['total_tokens'] as num?)?.toInt() ?? 0,
        );
      default:
        return null;
    }
  }

  void _ensureSuccess(Response response, {required String action}) {
    final statusCode = response.statusCode ?? 500;
    if (statusCode >= 200 && statusCode < 300) return;
    final data = response.data;
    if (data is Map<String, dynamic>) {
      final error = data['error'] as Map<String, dynamic>?;
      final detail = data['detail'] as Map<String, dynamic>?;
      final errorMap = error ?? (detail?['error'] as Map<String, dynamic>?);
      final message = errorMap?['message']?.toString();
      throw Exception(message ?? 'Backend $action failed: $statusCode');
    }
    throw Exception('Backend $action failed: $statusCode');
  }
}
