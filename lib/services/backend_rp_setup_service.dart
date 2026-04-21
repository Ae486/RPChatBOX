import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';

import '../adapters/ai_provider.dart';
import '../models/rp_setup.dart';
import 'dio_service.dart';

class BackendRpSetupService {
  static const String defaultBaseUrl = 'http://localhost:8765';

  final Dio _controlDio;
  final Dio _dataDio;
  final String _baseUrl;

  BackendRpSetupService({Dio? dio, String? baseUrl})
    : _controlDio = dio ?? DioService().controlPlaneDio,
      _dataDio = dio ?? DioService().dataPlaneDio,
      _baseUrl = baseUrl ?? defaultBaseUrl;

  Future<List<RpSetupWorkspace>> listWorkspaces() async {
    final response = await _controlDio.get('$_baseUrl/api/rp/setup/workspaces');
    _ensureSuccess(response, action: 'list setup workspaces');
    final payload = Map<String, dynamic>.from(response.data as Map);
    final items = payload['data'] as List? ?? const [];
    return items
        .whereType<Map>()
        .map((item) => RpSetupWorkspace.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<RpSetupWorkspace> createWorkspace({
    required String storyId,
    String mode = 'longform',
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/setup/workspaces',
      data: {'story_id': storyId, 'mode': mode},
    );
    _ensureSuccess(response, action: 'create setup workspace');
    return RpSetupWorkspace.fromJson(Map<String, dynamic>.from(response.data as Map));
  }

  Future<RpSetupWorkspace> getWorkspace(String workspaceId) async {
    final response = await _controlDio.get(
      '$_baseUrl/api/rp/setup/workspaces/$workspaceId',
    );
    _ensureSuccess(response, action: 'get setup workspace');
    return RpSetupWorkspace.fromJson(Map<String, dynamic>.from(response.data as Map));
  }

  Future<void> acceptCommitProposal({
    required String workspaceId,
    required String proposalId,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/setup/workspaces/$workspaceId/commit-proposals/$proposalId/accept',
    );
    _ensureSuccess(response, action: 'accept setup commit proposal');
  }

  Future<void> rejectCommitProposal({
    required String workspaceId,
    required String proposalId,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/setup/workspaces/$workspaceId/commit-proposals/$proposalId/reject',
    );
    _ensureSuccess(response, action: 'reject setup commit proposal');
  }

  Future<RpActivationCheckResult> runActivationCheck(String workspaceId) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/setup/workspaces/$workspaceId/activation-check',
    );
    _ensureSuccess(response, action: 'run setup activation check');
    return RpActivationCheckResult.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Stream<AIStreamEvent> streamTurn({
    required String workspaceId,
    required String modelId,
    String? providerId,
    String? targetStep,
    required List<SetupDialogueMessage> history,
    required String userPrompt,
  }) async* {
    final response = await _dataDio.post<ResponseBody>(
      '$_baseUrl/api/rp/setup/workspaces/$workspaceId/turn/stream',
      data: {
        'workspace_id': workspaceId,
        'model_id': modelId,
        if (providerId != null) 'provider_id': providerId,
        if (targetStep != null) 'target_step': targetStep,
        'history': history.map((item) => item.toJson()).toList(),
        'user_prompt': userPrompt,
      },
      options: Options(responseType: ResponseType.stream),
    );
    _ensureSuccess(response, action: 'stream setup turn');

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
            error['message']?.toString() ?? 'Setup stream failed';
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

  Future<String> runTurn({
    required String workspaceId,
    required String modelId,
    String? providerId,
    String? targetStep,
    required List<SetupDialogueMessage> history,
    required String userPrompt,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/setup/workspaces/$workspaceId/turn',
      data: {
        'workspace_id': workspaceId,
        'model_id': modelId,
        if (providerId != null) 'provider_id': providerId,
        if (targetStep != null) 'target_step': targetStep,
        'history': history.map((item) => item.toJson()).toList(),
        'user_prompt': userPrompt,
      },
    );
    _ensureSuccess(response, action: 'run setup turn');
    final payload = Map<String, dynamic>.from(response.data as Map);
    return payload['assistant_text'] as String? ?? '';
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
        return delta.isEmpty ? null : AIStreamEvent.text(delta, isTypedSemantic: true);
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
                errorMessage: parsed['error']?.toString() ?? 'Unknown tool error',
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
