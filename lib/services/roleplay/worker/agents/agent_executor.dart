/// Agent 执行器
///
/// 通用 Agent 执行器，负责调用 LLM 和处理 JSON 输出
/// POS: Services / Roleplay / Worker / Agents
library;

import 'agent_types.dart';
import 'agent_registry.dart';
import 'agent_prompts.dart';
import 'model_adapter.dart';
import 'proposal_transformer.dart';
import 'json/json_pipeline.dart';
import 'output/output_truncator.dart';
import 'telemetry/agent_metrics.dart';
import 'telemetry/error_codes.dart';

/// LLM 调用回调类型
typedef LlmCallCallback = Future<String> Function({
  required String systemPrompt,
  required String userPrompt,
  required String modelId,
  int? maxTokens,
  double? temperature,
});

/// 进度回调类型
///
/// stage: 当前阶段（如 'repairing'）
/// attempt: 当前尝试次数（可选）
typedef ProgressCallback = void Function(String stage, {int? attempt});

/// Agent 执行器
///
/// 职责：
/// - 获取 Agent 配置和提示词
/// - 调用 LLM
/// - 处理 JSON 输出（截断、解析、修复）
/// - 使用 Transformer 转换为 Proposals
class AgentExecutor {
  final AgentRegistry _registry;
  final ProposalTransformerRegistry _transformerRegistry;
  final ModelAdapter _modelAdapter;
  final JsonPipeline _jsonPipeline;
  final OutputTruncator _truncator;
  final AgentMetrics _metrics;
  final LlmCallCallback _llmCall;

  AgentExecutor({
    AgentRegistry? registry,
    ProposalTransformerRegistry? transformerRegistry,
    ModelAdapter? modelAdapter,
    JsonPipeline? jsonPipeline,
    OutputTruncator? truncator,
    AgentMetrics? metrics,
    required LlmCallCallback llmCall,
  })  : _registry = registry ?? agentRegistry,
        _transformerRegistry = transformerRegistry ?? proposalTransformerRegistry,
        _modelAdapter = modelAdapter ?? ModelAdapter(),
        _jsonPipeline = jsonPipeline ?? JsonPipeline(),
        _truncator = truncator ?? OutputTruncator(),
        _metrics = metrics ?? AgentMetrics(),
        _llmCall = llmCall;

  /// 执行 Agent 任务
  ///
  /// [onProgress] 可选的进度回调，用于报告执行阶段
  Future<AgentResult> execute(
    AgentRequest request, {
    ProgressCallback? onProgress,
  }) async {
    final stopwatch = Stopwatch()..start();
    final logs = <String>[];

    try {
      // 1. 获取 Agent 描述符
      final descriptor = _registry.get(request.agentId);
      if (descriptor == null) {
        return AgentResult.failed(
          agentId: request.agentId,
          errorCode: AgentErrorCodes.agentNotRegistered,
          errorMessage: 'Agent not registered: ${request.agentId}',
        );
      }

      // 2. 获取提示词集合
      final promptSet = AgentPrompts.getPromptSet(descriptor.promptKey);
      if (promptSet == null) {
        return AgentResult.failed(
          agentId: request.agentId,
          errorCode: AgentErrorCodes.agentUnknown,
          errorMessage: 'Unknown prompt key: ${descriptor.promptKey}',
        );
      }

      // 3. 根据模型能力选择提示词版本
      final effectiveModelId = descriptor.modelSpec?.modelId ?? request.modelId;
      final tier = descriptor.modelSpec?.promptTier ??
          _modelAdapter.getTier(effectiveModelId);
      final prompt = promptSet.getPrompt(tier);
      logs.add('Selected prompt tier: ${tier.name}');

      // 4. 构建完整提示词
      final userPrompt = _buildUserPrompt(prompt, request);

      // 5. 调用 LLM
      final temperature = descriptor.modelSpec?.temperature ?? 0.3;
      final maxTokens = descriptor.modelSpec?.maxOutputTokens ??
          _modelAdapter.getMaxOutputTokens(effectiveModelId);

      final rawOutput = await _llmCall(
        systemPrompt: promptSet.systemPrompt ??
            'You are a helpful assistant. Output JSON only.',
        userPrompt: userPrompt,
        modelId: effectiveModelId,
        maxTokens: maxTokens,
        temperature: temperature,
      );
      logs.add('LLM call completed, output length: ${rawOutput.length}');

      // 6. 输出截断
      final truncateResult =
          await _truncator.process(rawOutput, effectiveModelId);
      if (truncateResult.wasTruncated) {
        logs.add('Output truncated: ${truncateResult.method}');
        _metrics.recordTruncation(request.agentId);
      }

      // 7. JSON 解析管道
      final parseResult = await _jsonPipeline.process(
        truncateResult.text,
        schema: promptSet.schema,
        llmRepair:
            _modelAdapter.getJsonRepairStrategy(effectiveModelId) ==
                    JsonRepairStrategy.aggressive
                ? (broken, schema) {
                    // 报告修复阶段
                    onProgress?.call('repairing', attempt: 1);
                    return _llmRepair(broken, schema, effectiveModelId);
                  }
                : null,
      );

      logs.addAll(parseResult.logs);

      if (!parseResult.success) {
        _metrics.recordFailure(request.agentId, parseResult.errorCode!);
        return AgentResult.failed(
          agentId: request.agentId,
          errorCode: parseResult.errorCode!,
          logs: logs,
        );
      }

      _metrics.recordRepairStage(request.agentId, parseResult.repairStage);

      // 8. 获取转换器并转换为 Proposals
      final transformer = _transformerRegistry.get(descriptor.transformerId);
      List<Map<String, dynamic>> proposals;

      if (transformer != null) {
        final ctx = TransformContext(
          agent: descriptor,
          memoryReader: request.memoryReader,
          inputs: request.inputs,
        );
        proposals = transformer.transform(data: parseResult.data!, ctx: ctx);
      } else {
        // 回退：使用通用转换（仅返回原始数据）
        logs.add('Warning: No transformer found for ${descriptor.transformerId}');
        proposals = _fallbackTransform(parseResult.data!, request);
      }

      _metrics.recordSuccess(request.agentId, stopwatch.elapsedMilliseconds);

      return AgentResult.success(
        agentId: request.agentId,
        proposals: proposals,
        logs: logs,
        metrics: AgentResultMetrics(
          durationMs: stopwatch.elapsedMilliseconds,
          truncated: truncateResult.wasTruncated,
          repairStage: parseResult.repairStage,
          llmCallCount: 1,
        ),
      );
    } catch (e, st) {
      _metrics.recordError(request.agentId, e.toString());
      return AgentResult.error(
        agentId: request.agentId,
        errorCode: AgentErrorCodes.agentExecutionError,
        message: e.toString(),
        stackTrace: st.toString(),
      );
    }
  }

  /// 构建用户提示词
  String _buildUserPrompt(String basePrompt, AgentRequest request) {
    final buffer = StringBuffer(basePrompt);
    buffer.writeln();
    buffer.writeln('## Context');

    // 添加内存上下文
    final memory = request.memoryReader;

    // 当前场景
    final currentScene = memory.getCurrentScene();
    if (currentScene != null) {
      buffer.writeln('### Current Scene');
      buffer.writeln('Location: ${currentScene['location'] ?? 'Unknown'}');
      buffer.writeln('Time: ${currentScene['time'] ?? 'Unknown'}');
    }

    // 角色信息
    final characters = memory.getCharacters();
    if (characters.isNotEmpty) {
      buffer.writeln('### Characters');
      for (final char in characters) {
        buffer.writeln('- ${char['name']}: ${char['description'] ?? ''}');
      }
    }

    // 最近消息
    final recentMessages = memory.getRecentMessages(limit: 5);
    if (recentMessages.isNotEmpty) {
      buffer.writeln('### Recent Messages');
      for (final msg in recentMessages) {
        buffer.writeln('${msg['role']}: ${msg['content']}');
      }
    }

    // 额外输入
    if (request.inputs.isNotEmpty) {
      buffer.writeln('### Additional Input');
      for (final entry in request.inputs.entries) {
        if (entry.key != 'modelId') {
          buffer.writeln('${entry.key}: ${entry.value}');
        }
      }
    }

    return buffer.toString();
  }

  /// LLM 修复回调
  Future<String?> _llmRepair(
      String brokenJson, String schema, String modelId) async {
    try {
      return await _llmCall(
        systemPrompt:
            'You are a JSON repair tool. Output ONLY valid JSON, no extra text.',
        userPrompt: '''
Schema:
$schema

Broken JSON:
$brokenJson

Fix it so it matches schema. Preserve as much content as possible.
If data is irrecoverable, return:
{"ok": false, "error": "unrecoverable_json"}
''',
        modelId: modelId,
        maxTokens: 2000,
        temperature: 0.0,
      );
    } catch (_) {
      return null;
    }
  }

  /// 回退转换（当没有注册转换器时）
  List<Map<String, dynamic>> _fallbackTransform(
    Map<String, dynamic> data,
    AgentRequest request,
  ) {
    final version = request.memoryReader.version;

    // 检查是否有 proposals 字段
    if (data.containsKey('proposals') && data['proposals'] is List) {
      final proposals = (data['proposals'] as List).cast<Map<String, dynamic>>();
      for (final p in proposals) {
        p['sourceRev'] = version?.sourceRev ?? 0;
        p['expectedFoundationRev'] = version?.foundationRev ?? 0;
        p['expectedStoryRev'] = version?.storyRev ?? 0;
      }
      return proposals;
    }

    // 返回空列表
    return [];
  }

  /// 获取指标
  AgentMetrics get metrics => _metrics;
}
