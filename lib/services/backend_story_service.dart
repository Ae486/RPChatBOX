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

  Future<RpRuntimeInspection> getRuntimeInspection({
    required String sessionId,
    String? branchHeadId,
    String? turnId,
    int? targetChapterIndex,
    int? limit,
  }) async {
    final response = await _controlDio.get(
      '$_baseUrl/api/rp/story-sessions/$sessionId/runtime/inspect',
      queryParameters: {
        if (branchHeadId != null && branchHeadId.isNotEmpty)
          'branch_head_id': branchHeadId,
        if (turnId != null && turnId.isNotEmpty) 'turn_id': turnId,
        if (targetChapterIndex != null)
          'target_chapter_index': targetChapterIndex,
        if (limit != null) 'limit': limit,
      },
    );
    _ensureSuccess(response, action: 'get story runtime inspection');
    return RpRuntimeInspection.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpMemoryInspection> getMemoryInspection({
    required String sessionId,
    required String branchHeadId,
    required String turnId,
    required String runtimeProfileSnapshotId,
    List<String>? layers,
    List<String>? domains,
    bool includeHiddenAudit = false,
  }) async {
    final response = await _controlDio.get(
      '$_baseUrl/api/rp/story-sessions/$sessionId/memory/inspection',
      queryParameters: {
        'branch_head_id': branchHeadId,
        'turn_id': turnId,
        'runtime_profile_snapshot_id': runtimeProfileSnapshotId,
        if (layers != null && layers.isNotEmpty) 'layers': layers,
        if (domains != null && domains.isNotEmpty) 'domains': domains,
        if (includeHiddenAudit) 'include_hidden_audit': includeHiddenAudit,
      },
    );
    _ensureSuccess(response, action: 'get story memory inspection');
    return RpMemoryInspection.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpMemoryActionResponse> directEditCoreMemory({
    required String sessionId,
    required Map<String, dynamic> identity,
    required String actor,
    required String domain,
    String? domainPath,
    required List<Map<String, dynamic>> operations,
    required List<Map<String, dynamic>> baseRefs,
    List<Map<String, dynamic>> sourceRefs = const [],
    String? reason,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/memory/core/direct-edit',
      data: {
        'identity': identity,
        'actor': actor,
        'domain': domain,
        if (domainPath != null && domainPath.isNotEmpty)
          'domain_path': domainPath,
        'operations': operations,
        'base_refs': baseRefs,
        if (sourceRefs.isNotEmpty) 'source_refs': sourceRefs,
        if (reason != null && reason.isNotEmpty) 'reason': reason,
      },
    );
    _ensureSuccess(response, action: 'direct edit core memory');
    return RpMemoryActionResponse.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpBrainstormSession> startBrainstormSession({
    required String sessionId,
    required Map<String, dynamic> identity,
    required String actor,
    Map<String, dynamic> metadata = const {},
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/brainstorm/sessions',
      data: {
        'identity': identity,
        'actor': actor,
        if (metadata.isNotEmpty) 'metadata': metadata,
      },
    );
    _ensureSuccess(response, action: 'start story brainstorm session');
    return RpBrainstormSession.fromJson(
      _mapOrEmpty((response.data as Map)['item']),
    );
  }

  Future<RpBrainstormSession> readBrainstormSession({
    required String sessionId,
    required String brainstormId,
    required Map<String, dynamic> identity,
  }) async {
    final response = await _controlDio.get(
      '$_baseUrl/api/rp/story-sessions/$sessionId/brainstorm/sessions/$brainstormId',
      queryParameters: {
        'story_id': identity['story_id'],
        'branch_head_id': identity['branch_head_id'],
        'turn_id': identity['turn_id'],
        'runtime_profile_snapshot_id': identity['runtime_profile_snapshot_id'],
      },
    );
    _ensureSuccess(response, action: 'read story brainstorm session');
    return RpBrainstormSession.fromJson(
      _mapOrEmpty((response.data as Map)['item']),
    );
  }

  Future<RpBrainstormSession> sendBrainstormMessage({
    required String sessionId,
    required String brainstormId,
    required Map<String, dynamic> identity,
    required String actor,
    required String prompt,
    required String modelId,
    String? providerId,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/brainstorm/sessions/$brainstormId/messages',
      data: {
        'identity': identity,
        'actor': actor,
        'prompt': prompt,
        'model_id': modelId,
        if (providerId != null && providerId.isNotEmpty)
          'provider_id': providerId,
      },
    );
    _ensureSuccess(response, action: 'send story brainstorm message');
    return RpBrainstormSession.fromJson(
      _mapOrEmpty((response.data as Map)['item']),
    );
  }

  Future<RpBrainstormSession> summarizeBrainstormSession({
    required String sessionId,
    required String brainstormId,
    required Map<String, dynamic> identity,
    required String actor,
    required String modelId,
    String? providerId,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/brainstorm/sessions/$brainstormId/summarize',
      data: {
        'identity': identity,
        'actor': actor,
        'model_id': modelId,
        if (providerId != null && providerId.isNotEmpty)
          'provider_id': providerId,
      },
    );
    _ensureSuccess(response, action: 'summarize story brainstorm session');
    return RpBrainstormSession.fromJson(
      _mapOrEmpty((response.data as Map)['item']),
    );
  }

  Future<RpBrainstormSession> continueBrainstormWriting({
    required String sessionId,
    required String brainstormId,
    required Map<String, dynamic> identity,
    required String actor,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/brainstorm/sessions/$brainstormId/continue-writing',
      data: {'identity': identity, 'actor': actor},
    );
    _ensureSuccess(response, action: 'continue story brainstorm writing');
    return RpBrainstormSession.fromJson(
      _mapOrEmpty((response.data as Map)['item']),
    );
  }

  Future<RpBrainstormSession> addBrainstormBatchItem({
    required String sessionId,
    required String brainstormId,
    required String batchId,
    required Map<String, dynamic> identity,
    required String actor,
    required String text,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/brainstorm/sessions/$brainstormId/batches/$batchId/items',
      data: {'identity': identity, 'actor': actor, 'text': text},
    );
    _ensureSuccess(response, action: 'add story brainstorm item');
    return RpBrainstormSession.fromJson(
      _mapOrEmpty((response.data as Map)['item']),
    );
  }

  Future<RpBrainstormSession> updateBrainstormItem({
    required String sessionId,
    required String brainstormId,
    required String batchId,
    required String itemId,
    required Map<String, dynamic> identity,
    required String actor,
    String? text,
    String? status,
  }) async {
    final response = await _controlDio.patch(
      '$_baseUrl/api/rp/story-sessions/$sessionId/brainstorm/sessions/$brainstormId/batches/$batchId/items/$itemId',
      data: {
        'identity': identity,
        'actor': actor,
        if (text != null && text.isNotEmpty) 'text': text,
        if (status != null && status.isNotEmpty) 'status': status,
      },
    );
    _ensureSuccess(response, action: 'update story brainstorm item');
    return RpBrainstormSession.fromJson(
      _mapOrEmpty((response.data as Map)['item']),
    );
  }

  Future<RpBrainstormBatchSubmitResponse> submitBrainstormBatch({
    required String sessionId,
    required String brainstormId,
    required String batchId,
    required Map<String, dynamic> identity,
    required String actor,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/brainstorm/sessions/$brainstormId/batches/$batchId/submit',
      data: {'identity': identity, 'actor': actor},
    );
    _ensureSuccess(response, action: 'submit story brainstorm batch');
    return RpBrainstormBatchSubmitResponse.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpMemoryActionResponse> reviewRecallMemory({
    required String sessionId,
    required Map<String, dynamic> identity,
    required String actor,
    required String action,
    required List<String> materialRefs,
    String? reason,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/memory/recall/actions',
      data: {
        'identity': identity,
        'actor': actor,
        'action': action,
        'material_refs': materialRefs,
        if (reason != null && reason.isNotEmpty) 'reason': reason,
      },
    );
    _ensureSuccess(response, action: 'review recall memory');
    return RpMemoryActionResponse.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpMemoryActionResponse> evolveArchivalMemory({
    required String sessionId,
    required Map<String, dynamic> identity,
    required String actor,
    required String sourceAssetId,
    int? expectedSourceVersion,
    required List<Map<String, dynamic>> replacementSections,
    List<Map<String, dynamic>> sourceRefs = const [],
    String? reason,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/memory/archival/evolution',
      data: {
        'identity': identity,
        'actor': actor,
        'source_asset_id': sourceAssetId,
        if (expectedSourceVersion != null)
          'expected_source_version': expectedSourceVersion,
        'replacement_sections': replacementSections,
        if (sourceRefs.isNotEmpty) 'source_refs': sourceRefs,
        if (reason != null && reason.isNotEmpty) 'reason': reason,
      },
    );
    _ensureSuccess(response, action: 'evolve archival memory');
    return RpMemoryActionResponse.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpRuntimeDebugSurface> getRuntimeDebug({
    required String sessionId,
  }) async {
    final response = await _controlDio.get(
      '$_baseUrl/api/rp/story-sessions/$sessionId/runtime/debug',
    );
    _ensureSuccess(response, action: 'get story runtime debug');
    return RpRuntimeDebugSurface.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<List<RpRuntimeConfigControlReceipt>> getRuntimeConfigHistory({
    required String sessionId,
  }) async {
    final response = await _controlDio.get(
      '$_baseUrl/api/rp/story-sessions/$sessionId/runtime-config/history',
    );
    _ensureSuccess(response, action: 'get story runtime config history');
    final payload = Map<String, dynamic>.from(response.data as Map);
    final items = payload['data'] as List? ?? const [];
    return items
        .whereType<Map>()
        .map(
          (item) => RpRuntimeConfigControlReceipt.fromJson(
            Map<String, dynamic>.from(item),
          ),
        )
        .toList();
  }

  Future<RpBranchControlResult> createBranchFromTurn({
    required String sessionId,
    required String originTurnId,
    String? branchName,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/branches',
      data: {
        'origin_turn_id': originTurnId,
        if (branchName != null && branchName.trim().isNotEmpty)
          'branch_name': branchName.trim(),
      },
    );
    _ensureSuccess(response, action: 'create story branch');
    return RpBranchControlResult.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpBranchControlResult> switchBranch({
    required String sessionId,
    required String branchHeadId,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/branches/$branchHeadId/switch',
    );
    _ensureSuccess(response, action: 'switch story branch');
    return RpBranchControlResult.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpBranchControlResult> deleteBranch({
    required String sessionId,
    required String branchHeadId,
  }) async {
    final response = await _controlDio.delete(
      '$_baseUrl/api/rp/story-sessions/$sessionId/branches/$branchHeadId',
    );
    _ensureSuccess(response, action: 'delete story branch');
    return RpBranchControlResult.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpBranchControlResult> rollbackToTurn({
    required String sessionId,
    required String targetTurnId,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/rollback',
      data: {'target_turn_id': targetTurnId},
    );
    _ensureSuccess(response, action: 'rollback story branch');
    return RpBranchControlResult.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpRevisionReviewSurface> getRevisionReviewSurface({
    required String sessionId,
    required String artifactId,
    required String mode,
  }) async {
    final response = await _controlDio.get(
      '$_baseUrl/api/rp/story-sessions/$sessionId/revision-review/$artifactId',
      queryParameters: {'mode': mode},
    );
    _ensureSuccess(response, action: 'get revision review surface');
    return RpRevisionReviewSurface.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpChapterSnapshot> updateRevisionDraft({
    required String sessionId,
    required String artifactId,
    required String contentText,
  }) async {
    final response = await _controlDio.patch(
      '$_baseUrl/api/rp/story-sessions/$sessionId/revision-review/$artifactId/draft',
      data: {'content_text': contentText},
    );
    _ensureSuccess(response, action: 'update revision draft');
    return RpChapterSnapshot.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpRevisionReviewSurface> addRevisionComment({
    required String sessionId,
    required String artifactId,
    required String blockId,
    required String instructionText,
    String? selectedExcerpt,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/revision-review/$artifactId/comments',
      data: {
        'block_id': blockId,
        'instruction_text': instructionText,
        if (selectedExcerpt != null && selectedExcerpt.isNotEmpty)
          'selected_excerpt': selectedExcerpt,
      },
    );
    _ensureSuccess(response, action: 'add revision comment');
    return RpRevisionReviewSurface.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpRevisionReviewSurface> addRevisionTrackedChange({
    required String sessionId,
    required String artifactId,
    required String blockId,
    String? originalText,
    String? suggestedText,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/revision-review/$artifactId/tracked-changes',
      data: {
        'block_id': blockId,
        if (originalText != null && originalText.isNotEmpty)
          'original_text': originalText,
        if (suggestedText != null && suggestedText.isNotEmpty)
          'suggested_text': suggestedText,
      },
    );
    _ensureSuccess(response, action: 'add revision tracked change');
    return RpRevisionReviewSurface.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpRevisionReviewSurface> resolveRevisionComment({
    required String sessionId,
    required String artifactId,
    required String commentId,
  }) async {
    final response = await _controlDio.post(
      '$_baseUrl/api/rp/story-sessions/$sessionId/revision-review/$artifactId/comments/$commentId/resolve',
    );
    _ensureSuccess(response, action: 'resolve revision comment');
    return RpRevisionReviewSurface.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<RpRevisionReviewSurface> deleteRevisionComment({
    required String sessionId,
    required String artifactId,
    required String commentId,
  }) async {
    final response = await _controlDio.delete(
      '$_baseUrl/api/rp/story-sessions/$sessionId/revision-review/$artifactId/comments/$commentId',
    );
    _ensureSuccess(response, action: 'delete revision comment');
    return RpRevisionReviewSurface.fromJson(
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

Map<String, dynamic> _mapOrEmpty(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) {
    return value.map((key, nested) => MapEntry(key.toString(), nested));
  }
  return const {};
}
