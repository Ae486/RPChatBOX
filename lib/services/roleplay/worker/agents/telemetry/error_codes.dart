/// Agent 错误码定义
///
/// 统一的错误码规范，用于可观测性和调试
/// POS: Services / Roleplay / Worker / Agents / Telemetry
library;

/// 统一错误码
abstract class AgentErrorCodes {
  // JSON 解析相关 (1xx)
  /// JSON 块提取失败
  static const jsonExtractFailed = 'E101';

  /// JSON 清理失败
  static const jsonSanitizeFailed = 'E102';

  /// JSON Schema 验证失败
  static const jsonSchemaInvalid = 'E103';

  /// JSON 结构修复失败
  static const jsonStructuralRepairFailed = 'E104';

  /// JSON LLM 修复失败
  static const jsonLlmRepairFailed = 'E105';

  /// JSON 修复完全失败
  static const jsonRepairFailed = 'E106';

  // Agent 执行相关 (2xx)
  /// Agent 执行错误
  static const agentExecutionError = 'E201';

  /// Agent 超时
  static const agentTimeout = 'E202';

  /// 未知 Agent
  static const agentUnknown = 'E203';

  /// Agent 未注册
  static const agentNotRegistered = 'E204';

  /// Agent 输入无效
  static const agentInvalidInput = 'E205';

  // 输出处理相关 (3xx)
  /// 输出被截断
  static const outputTruncated = 'E301';

  /// 输出摘要失败
  static const outputSummarizeFailed = 'E302';

  /// 输出过大
  static const outputTooLarge = 'E303';

  // Worker 相关 (4xx)
  /// Worker 崩溃
  static const workerCrash = 'E401';

  /// Worker 超时
  static const workerTimeout = 'E402';

  /// Worker 通信错误
  static const workerCommunicationError = 'E403';

  // LLM 相关 (5xx)
  /// LLM 调用失败
  static const llmCallFailed = 'E501';

  /// LLM 响应无效
  static const llmInvalidResponse = 'E502';

  /// LLM 超时
  static const llmTimeout = 'E503';

  /// 获取错误码描述
  static String getDescription(String code) {
    return switch (code) {
      jsonExtractFailed => 'JSON 块提取失败',
      jsonSanitizeFailed => 'JSON 清理失败',
      jsonSchemaInvalid => 'JSON Schema 验证失败',
      jsonStructuralRepairFailed => 'JSON 结构修复失败',
      jsonLlmRepairFailed => 'JSON LLM 修复失败',
      jsonRepairFailed => 'JSON 修复完全失败',
      agentExecutionError => 'Agent 执行错误',
      agentTimeout => 'Agent 超时',
      agentUnknown => '未知 Agent',
      agentNotRegistered => 'Agent 未注册',
      agentInvalidInput => 'Agent 输入无效',
      outputTruncated => '输出被截断',
      outputSummarizeFailed => '输出摘要失败',
      outputTooLarge => '输出过大',
      workerCrash => 'Worker 崩溃',
      workerTimeout => 'Worker 超时',
      workerCommunicationError => 'Worker 通信错误',
      llmCallFailed => 'LLM 调用失败',
      llmInvalidResponse => 'LLM 响应无效',
      llmTimeout => 'LLM 超时',
      _ => '未知错误: $code',
    };
  }

  /// 判断是否为可重试错误
  static bool isRetryable(String code) {
    return switch (code) {
      llmCallFailed || llmTimeout || workerTimeout => true,
      _ => false,
    };
  }

  /// 判断是否为严重错误
  static bool isCritical(String code) {
    return switch (code) {
      workerCrash || workerCommunicationError => true,
      _ => false,
    };
  }

  /// 获取用户友好的错误提示
  ///
  /// 将内部错误码转换为用户可理解的中文提示
  static String getUserFriendlyMessage(String code) {
    return switch (code) {
      // JSON 管道 (E1xx) - 可自动重试
      jsonExtractFailed ||
      jsonSanitizeFailed ||
      jsonSchemaInvalid ||
      jsonStructuralRepairFailed ||
      jsonLlmRepairFailed =>
        'AI 正在整理思路，请稍候...',

      // JSON 完全失败
      jsonRepairFailed => 'AI 无法生成有效格式，建议简化输入后重试',

      // Agent 执行 (E2xx)
      agentExecutionError => 'AI 遇到意外错误',
      agentTimeout => 'AI 响应超时，请检查网络后重试',
      agentUnknown || agentNotRegistered => '功能暂不可用',
      agentInvalidInput => '输入内容无效，请检查后重试',

      // 输出处理 (E3xx)
      outputTruncated => 'AI 结果过长，已自动精简',
      outputSummarizeFailed => 'AI 摘要生成失败',
      outputTooLarge => 'AI 结果超出限制',

      // Worker (E4xx)
      workerCrash => '后台服务正在重启...',
      workerTimeout => '处理超时，请稍后重试',
      workerCommunicationError => '连接不稳定，请重试',

      // LLM (E5xx)
      llmCallFailed => 'AI 服务暂时不可用',
      llmInvalidResponse => 'AI 返回了无效响应',
      llmTimeout => 'AI 响应超时',

      _ => '发生未知错误',
    };
  }

  /// 判断是否应自动重试（不打扰用户）
  static bool shouldAutoRetry(String code) {
    return switch (code) {
      jsonExtractFailed ||
      jsonSanitizeFailed ||
      jsonSchemaInvalid ||
      jsonStructuralRepairFailed ||
      llmTimeout =>
        true,
      _ => false,
    };
  }

  /// 判断是否需要用户介入
  static bool requiresUserAction(String code) {
    return switch (code) {
      jsonRepairFailed || agentInvalidInput || outputTooLarge => true,
      _ => false,
    };
  }
}
