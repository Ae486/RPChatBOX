/// Agent 遥测指标
///
/// 收集 Agent 执行的性能和成功率指标
/// POS: Services / Roleplay / Worker / Agents / Telemetry
library;

/// Agent 遥测指标收集器
class AgentMetrics {
  final Map<String, int> _successCount = {};
  final Map<String, int> _failureCount = {};
  final Map<String, List<int>> _durations = {};
  final Map<String, Map<String, int>> _errorCodes = {};
  final Map<String, int> _repairStages = {};
  final Map<String, int> _truncationCount = {};

  /// 记录成功执行
  void recordSuccess(String agentId, int durationMs) {
    _successCount[agentId] = (_successCount[agentId] ?? 0) + 1;
    _durations.putIfAbsent(agentId, () => []).add(durationMs);
  }

  /// 记录失败执行
  void recordFailure(String agentId, String errorCode) {
    _failureCount[agentId] = (_failureCount[agentId] ?? 0) + 1;
    _errorCodes.putIfAbsent(agentId, () => {});
    _errorCodes[agentId]![errorCode] =
        (_errorCodes[agentId]![errorCode] ?? 0) + 1;
  }

  /// 记录错误
  void recordError(String agentId, String errorMessage) {
    _failureCount[agentId] = (_failureCount[agentId] ?? 0) + 1;
  }

  /// 记录 JSON 修复阶段
  void recordRepairStage(String agentId, int stage) {
    final key = '$agentId:S$stage';
    _repairStages[key] = (_repairStages[key] ?? 0) + 1;
  }

  /// 记录输出截断
  void recordTruncation(String agentId) {
    _truncationCount[agentId] = (_truncationCount[agentId] ?? 0) + 1;
  }

  /// 获取成功次数
  int getSuccessCount(String agentId) => _successCount[agentId] ?? 0;

  /// 获取失败次数
  int getFailureCount(String agentId) => _failureCount[agentId] ?? 0;

  /// 获取成功率
  double getSuccessRate(String agentId) {
    final success = _successCount[agentId] ?? 0;
    final failure = _failureCount[agentId] ?? 0;
    final total = success + failure;
    return total > 0 ? success / total : 0.0;
  }

  /// 获取首次解析成功率（S0 成功 / 总成功数）
  double getFirstTryRate(String agentId) {
    final s0 = _repairStages['$agentId:S0'] ?? 0;
    final total = _successCount[agentId] ?? 0;
    return total > 0 ? s0 / total : 0.0;
  }

  /// 获取平均耗时
  double getAvgDuration(String agentId) {
    final durations = _durations[agentId] ?? [];
    if (durations.isEmpty) return 0.0;
    return durations.reduce((a, b) => a + b) / durations.length;
  }

  /// 获取 P95 耗时
  int getP95Duration(String agentId) {
    final durations = _durations[agentId] ?? [];
    if (durations.isEmpty) return 0;
    final sorted = List<int>.from(durations)..sort();
    final index = (sorted.length * 0.95).floor();
    return sorted[index.clamp(0, sorted.length - 1)];
  }

  /// 获取截断率
  double getTruncationRate(String agentId) {
    final truncated = _truncationCount[agentId] ?? 0;
    final total = (_successCount[agentId] ?? 0) + (_failureCount[agentId] ?? 0);
    return total > 0 ? truncated / total : 0.0;
  }

  /// 获取错误分布
  Map<String, int> getErrorDistribution(String agentId) {
    return Map.unmodifiable(_errorCodes[agentId] ?? {});
  }

  /// 获取修复阶段分布
  Map<int, int> getRepairStageDistribution(String agentId) {
    final result = <int, int>{};
    for (int stage = 0; stage <= 4; stage++) {
      final count = _repairStages['$agentId:S$stage'] ?? 0;
      if (count > 0) result[stage] = count;
    }
    return result;
  }

  /// 导出所有指标
  Map<String, dynamic> exportAll() {
    final agents = <String>{
      ..._successCount.keys,
      ..._failureCount.keys,
    };

    return {
      for (final agentId in agents)
        agentId: {
          'successCount': getSuccessCount(agentId),
          'failureCount': getFailureCount(agentId),
          'successRate': getSuccessRate(agentId),
          'firstTryRate': getFirstTryRate(agentId),
          'avgDurationMs': getAvgDuration(agentId),
          'p95DurationMs': getP95Duration(agentId),
          'truncationRate': getTruncationRate(agentId),
          'errorDistribution': getErrorDistribution(agentId),
          'repairStageDistribution': getRepairStageDistribution(agentId),
        },
    };
  }

  /// 重置所有指标
  void reset() {
    _successCount.clear();
    _failureCount.clear();
    _durations.clear();
    _errorCodes.clear();
    _repairStages.clear();
    _truncationCount.clear();
  }
}

/// Agent 执行结果指标
class AgentResultMetrics {
  /// 执行耗时（毫秒）
  final int durationMs;

  /// 是否被截断
  final bool truncated;

  /// JSON 修复阶段（0=首次成功，1-4=各修复阶段）
  final int repairStage;

  /// LLM 调用次数
  final int llmCallCount;

  /// 输入 token 数
  final int inputTokens;

  /// 输出 token 数
  final int outputTokens;

  const AgentResultMetrics({
    this.durationMs = 0,
    this.truncated = false,
    this.repairStage = 0,
    this.llmCallCount = 0,
    this.inputTokens = 0,
    this.outputTokens = 0,
  });

  Map<String, dynamic> toJson() => {
        'durationMs': durationMs,
        'truncated': truncated,
        'repairStage': repairStage,
        'llmCallCount': llmCallCount,
        'inputTokens': inputTokens,
        'outputTokens': outputTokens,
      };

  factory AgentResultMetrics.fromJson(Map<String, dynamic> json) {
    return AgentResultMetrics(
      durationMs: json['durationMs'] as int? ?? 0,
      truncated: json['truncated'] as bool? ?? false,
      repairStage: json['repairStage'] as int? ?? 0,
      llmCallCount: json['llmCallCount'] as int? ?? 0,
      inputTokens: json['inputTokens'] as int? ?? 0,
      outputTokens: json['outputTokens'] as int? ?? 0,
    );
  }
}
