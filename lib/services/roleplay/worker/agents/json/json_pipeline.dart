/// JSON 修复管道
///
/// 6 阶段 JSON 处理管道：提取 → 清理 → 验证 → 修复 → LLM回退 → 最终验证
/// POS: Services / Roleplay / Worker / Agents / JSON
library;

import 'json_extractor.dart';
import 'json_sanitizer.dart';
import 'json_validator.dart';
import 'json_repairer.dart';
import '../telemetry/error_codes.dart';

/// JSON 管道处理结果
class JsonPipelineResult {
  final bool success;
  final Map<String, dynamic>? data;
  final String? errorCode;
  final int repairStage;
  final List<String> logs;

  const JsonPipelineResult._({
    required this.success,
    this.data,
    this.errorCode,
    required this.repairStage,
    required this.logs,
  });

  factory JsonPipelineResult.success({
    required Map<String, dynamic> data,
    required int repairStage,
    required List<String> logs,
  }) {
    return JsonPipelineResult._(
      success: true,
      data: data,
      repairStage: repairStage,
      logs: logs,
    );
  }

  factory JsonPipelineResult.failed({
    required String errorCode,
    required List<String> logs,
  }) {
    return JsonPipelineResult._(
      success: false,
      errorCode: errorCode,
      repairStage: -1,
      logs: logs,
    );
  }
}

/// LLM 修复回调类型
typedef LlmRepairCallback = Future<String?> Function(String brokenJson, String schema);

/// JSON 修复管道
class JsonPipeline {
  final JsonExtractor _extractor;
  final JsonSanitizer _sanitizer;
  final JsonValidator _validator;
  final JsonRepairer _repairer;

  JsonPipeline({
    JsonExtractor? extractor,
    JsonSanitizer? sanitizer,
    JsonValidator? validator,
    JsonRepairer? repairer,
  })  : _extractor = extractor ?? JsonExtractor(),
        _sanitizer = sanitizer ?? JsonSanitizer(),
        _validator = validator ?? JsonValidator(),
        _repairer = repairer ?? JsonRepairer();

  /// 处理 LLM 原始输出
  ///
  /// [raw] LLM 原始输出
  /// [schema] JSON Schema（可选）
  /// [llmRepair] LLM 修复回调（可选，用于 S4 阶段）
  Future<JsonPipelineResult> process(
    String raw, {
    String? schema,
    LlmRepairCallback? llmRepair,
  }) async {
    final logs = <String>[];

    // S0: 提取 JSON 块
    final extracted = _extractor.extract(raw);
    if (extracted == null) {
      logs.add('S0: No JSON block found in output');
      return JsonPipelineResult.failed(
        errorCode: AgentErrorCodes.jsonExtractFailed,
        logs: logs,
      );
    }
    logs.add('S0: Extracted ${extracted.length} chars');

    // S1: 确定性清理
    final sanitized = _sanitizer.sanitize(extracted);
    logs.add('S1: Sanitized');

    // S2: 首次验证
    var validateResult = _validator.validate(sanitized, schema: schema);
    if (validateResult.valid) {
      logs.add('S2: Valid on first try');
      return JsonPipelineResult.success(
        data: validateResult.data!,
        repairStage: 0,
        logs: logs,
      );
    }
    logs.add('S2: Validation failed: ${validateResult.error}');

    // S3: 确定性结构修复
    final repaired = _repairer.repair(sanitized, schema: schema);
    validateResult = _validator.validate(repaired, schema: schema);
    if (validateResult.valid) {
      logs.add('S3: Fixed by structural repair');
      return JsonPipelineResult.success(
        data: validateResult.data!,
        repairStage: 3,
        logs: logs,
      );
    }
    logs.add('S3: Structural repair insufficient');

    // S4: LLM 修复回退（如果提供了回调）
    if (llmRepair != null && schema != null) {
      try {
        final llmRepaired = await llmRepair(repaired, schema);
        if (llmRepaired != null) {
          final llmSanitized = _sanitizer.sanitize(llmRepaired);
          validateResult = _validator.validate(llmSanitized, schema: schema);
          if (validateResult.valid) {
            logs.add('S4: Fixed by LLM repair');
            return JsonPipelineResult.success(
              data: validateResult.data!,
              repairStage: 4,
              logs: logs,
            );
          }
        }
      } catch (e) {
        logs.add('S4: LLM repair error: $e');
      }
    }
    logs.add('S4: LLM repair skipped or failed');

    // S5: 最终失败
    logs.add('S5: All repair attempts exhausted');
    return JsonPipelineResult.failed(
      errorCode: AgentErrorCodes.jsonRepairFailed,
      logs: logs,
    );
  }
}
