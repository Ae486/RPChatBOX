# M4: Agent Integration 技术规格（商业级版本）

> 状态：规划中
>
> 最后更新：2026-01-20
>
> 协作记录：Codex Session `019b8e40-021b-7563-b300-cf99e87f76ec`

---

## 0. 设计决策

### 0.1 为何不采用 Skill 化架构

| 特性 | Claude Code Skills | RP Agents |
|------|-------------------|-----------|
| 目的 | 让模型扮演专家角色与用户对话 | 执行特定数据处理任务 |
| 触发 | 模型意图识别 | 确定性调度器决定 |
| 执行 | 在主对话流中 | Worker Isolate 中，无用户交互 |
| 输出 | 自然语言对话 | 结构化 JSON（Proposals） |

**结论**：Skill 化架构是过度设计。我们不需要 YAML 配置、热更新、意图识别等。

### 0.2 商业级核心要求

基于 Codex 协作分析和参考项目研究（Letta、MuMu、Arboris），商业级 Agent 系统需要：

| 要求 | 解决方案 |
|------|----------|
| 错误韧性 | 多阶段 JSON 修复 + LLM 回退 |
| 输出治理 | 截断 + Summarizer 机制 |
| 后台维护 | Sleeptime/Idle Maintenance 层 |
| 可观测性 | 统一错误码 + 遥测指标 |
| 扩展性 | 轻量注册表（非 YAML） |

---

## 1. 商业级架构

### 1.1 架构概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Worker Isolate                                    │
│                                                                              │
│  ┌──────────────┐                                                            │
│  │ AgentRegistry│  Map<String, AgentHandler> (编译期注册)                     │
│  └──────┬───────┘                                                            │
│         │                                                                    │
│         ▼                                                                    │
│  ┌─────────────────┐     ┌─────────────────┐                                │
│  │ AgentExecutor   │────▶│  ModelAdapter   │                                │
│  │                 │     │ (prompt select) │                                │
│  └────────┬────────┘     └─────────────────┘                                │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐            │
│  │              Multi-Stage JSON Pipeline                       │            │
│  │  S0:Extract → S1:Sanitize → S2:Validate → S3:Repair         │            │
│  │       → S4:LLM Fallback → S5:Final Validate                 │            │
│  └─────────────────────────────────────────────────────────────┘            │
│           │                                                                  │
│           ▼                                                                  │
│  ┌─────────────────┐                                                        │
│  │ OutputTruncator │  30k soft / 50k hard → Summarizer fallback             │
│  └────────┬────────┘                                                        │
│           │                                                                  │
│           ▼                                                                  │
│      Proposals + Telemetry                                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           Main Isolate                                       │
│                                                                              │
│  ┌─────────────────┐     ┌─────────────────┐                                │
│  │SleeptimeManager │────▶│ IdleDetector    │                                │
│  │                 │     │ (45s threshold) │                                │
│  └────────┬────────┘     └─────────────────┘                                │
│           │                                                                  │
│           ▼                                                                  │
│      Idle Maintenance Tasks (low priority)                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 文件结构

```
lib/services/roleplay/worker/
├── agents/
│   ├── agent_registry.dart         # 轻量注册表
│   ├── agent_executor.dart         # 通用 Agent 执行器
│   ├── agent_prompts.dart          # 提示词模板（Dart 常量）
│   ├── model_adapter.dart          # 模型能力适配
│   │
│   ├── json/
│   │   ├── json_pipeline.dart      # 多阶段 JSON 修复管道
│   │   ├── json_extractor.dart     # S0: JSON 提取
│   │   ├── json_sanitizer.dart     # S1: 确定性清理
│   │   ├── json_validator.dart     # S2/S5: Schema 验证
│   │   ├── json_repairer.dart      # S3: 结构修复
│   │   └── json_llm_fallback.dart  # S4: LLM 修复回退
│   │
│   ├── output/
│   │   ├── output_truncator.dart   # 输出截断
│   │   └── output_summarizer.dart  # Summarizer 回退
│   │
│   ├── impl/
│   │   ├── scene_detector.dart     # SceneDetector 实现
│   │   ├── state_updater.dart      # StateUpdater 实现
│   │   ├── key_event_extractor.dart # KeyEventExtractor 实现
│   │   └── consistency_heavy.dart  # ConsistencyHeavy 实现
│   │
│   └── telemetry/
│       ├── agent_metrics.dart      # 遥测指标
│       └── error_codes.dart        # 错误码定义
│
├── idle/
│   ├── idle_detector.dart          # 空闲检测
│   └── sleeptime_manager.dart      # 后台维护管理器
│
└── rp_worker_entry.dart            # Worker 入口（添加 Agent 路由）
```

---

## 2. 核心组件

### 2.1 轻量注册表（替代 switch）

```dart
/// Agent 处理函数签名
typedef AgentHandler = Future<AgentResult> Function(AgentRequest request);

/// 轻量 Agent 注册表（编译期注册，非 YAML）
class AgentRegistry {
  final Map<String, AgentHandler> _handlers = {};

  void register(String taskType, AgentHandler handler) {
    _handlers[taskType] = handler;
  }

  AgentHandler? get(String taskType) => _handlers[taskType];

  bool has(String taskType) => _handlers.containsKey(taskType);
}

/// 全局注册表（编译期初始化）
final AgentRegistry agentRegistry = AgentRegistry()
  ..register('scene_detector', SceneDetector.handle)
  ..register('state_updater', StateUpdater.handle)
  ..register('key_event_extractor', KeyEventExtractor.handle)
  ..register('consistency_heavy', ConsistencyHeavy.handle);
```

### 2.2 AgentExecutor（增强版）

```dart
/// 通用 Agent 执行器（商业级）
class AgentExecutor {
  final ModelAdapter _modelAdapter;
  final JsonPipeline _jsonPipeline;
  final OutputTruncator _truncator;
  final AgentMetrics _metrics;

  Future<AgentResult> execute({
    required String agentId,
    required Map<String, dynamic> inputs,
    required RpWorkerMemoryReader memoryReader,
    required String modelId,
  }) async {
    final stopwatch = Stopwatch()..start();

    try {
      // 1. 获取提示词（根据模型能力选择版本）
      final prompt = _modelAdapter.selectPrompt(agentId, modelId);

      // 2. 构建完整提示词
      final fullPrompt = _buildPrompt(agentId, prompt, inputs, memoryReader);

      // 3. 调用 LLM
      final rawOutput = await _callLlm(fullPrompt, modelId);

      // 4. 输出截断（商业级）
      final truncatedOutput = await _truncator.process(rawOutput, modelId);

      // 5. 多阶段 JSON 解析（商业级）
      final parseResult = await _jsonPipeline.process(
        truncatedOutput.text,
        schema: AgentPrompts.getSchema(agentId),
        modelId: modelId,
      );

      if (!parseResult.success) {
        _metrics.recordFailure(agentId, parseResult.errorCode);
        return AgentResult.failed(
          agentId: agentId,
          errorCode: parseResult.errorCode,
          logs: parseResult.logs,
        );
      }

      // 6. 转换为 Proposals
      final proposals = _toProposals(agentId, parseResult.data, inputs);

      _metrics.recordSuccess(agentId, stopwatch.elapsedMilliseconds);
      return AgentResult.success(
        agentId: agentId,
        proposals: proposals,
        metrics: AgentResultMetrics(
          durationMs: stopwatch.elapsedMilliseconds,
          truncated: truncatedOutput.wasTruncated,
          repairStage: parseResult.repairStage,
        ),
      );
    } catch (e, st) {
      _metrics.recordError(agentId, e.toString());
      return AgentResult.error(
        agentId: agentId,
        errorCode: ErrorCodes.agentExecutionError,
        message: e.toString(),
        stackTrace: st.toString(),
      );
    }
  }
}
```

### 2.3 多阶段 JSON 修复管道

```dart
/// JSON 修复管道（6 阶段）
class JsonPipeline {
  final JsonExtractor _extractor;
  final JsonSanitizer _sanitizer;
  final JsonValidator _validator;
  final JsonRepairer _repairer;
  final JsonLlmFallback _llmFallback;

  /// 处理 LLM 原始输出
  Future<JsonPipelineResult> process(
    String raw, {
    required String schema,
    required String modelId,
  }) async {
    final logs = <String>[];

    // S0: 提取 JSON 块
    final extracted = _extractor.extract(raw);
    if (extracted == null) {
      return JsonPipelineResult.failed(
        errorCode: ErrorCodes.jsonExtractFailed,
        logs: [...logs, 'S0: No JSON block found'],
      );
    }
    logs.add('S0: Extracted ${extracted.length} chars');

    // S1: 确定性清理（语法）
    final sanitized = _sanitizer.sanitize(extracted);
    logs.add('S1: Sanitized');

    // S2: Schema 验证
    var validateResult = _validator.validate(sanitized, schema);
    if (validateResult.valid) {
      return JsonPipelineResult.success(
        data: validateResult.data!,
        repairStage: 0,
        logs: [...logs, 'S2: Valid on first try'],
      );
    }
    logs.add('S2: Validation failed: ${validateResult.error}');

    // S3: 确定性结构修复
    final repaired = _repairer.repair(sanitized, schema);
    validateResult = _validator.validate(repaired, schema);
    if (validateResult.valid) {
      return JsonPipelineResult.success(
        data: validateResult.data!,
        repairStage: 3,
        logs: [...logs, 'S3: Fixed by structural repair'],
      );
    }
    logs.add('S3: Structural repair insufficient');

    // S4: LLM 修复回退（仅一次）
    final llmRepaired = await _llmFallback.repair(
      brokenJson: repaired,
      schema: schema,
      modelId: modelId,
    );
    if (llmRepaired != null) {
      validateResult = _validator.validate(llmRepaired, schema);
      if (validateResult.valid) {
        return JsonPipelineResult.success(
          data: validateResult.data!,
          repairStage: 4,
          logs: [...logs, 'S4: Fixed by LLM repair'],
        );
      }
    }
    logs.add('S4: LLM repair failed');

    // S5: 最终失败
    return JsonPipelineResult.failed(
      errorCode: ErrorCodes.jsonRepairFailed,
      logs: [...logs, 'S5: All repair attempts exhausted'],
    );
  }
}
```

### 2.4 JSON 提取器（S0）

```dart
/// JSON 块提取器
class JsonExtractor {
  /// 提取 JSON 块
  String? extract(String text) {
    // 优先：fenced code block
    final fenced = RegExp(r'```json\s*([\s\S]*?)```', multiLine: true);
    final match = fenced.firstMatch(text);
    if (match != null) return match.group(1)!.trim();

    // 回退：平衡括号扫描
    int depth = 0, start = -1;
    for (int i = 0; i < text.length; i++) {
      final ch = text[i];
      if (ch == '{') {
        if (depth == 0) start = i;
        depth++;
      } else if (ch == '}') {
        depth--;
        if (depth == 0 && start != -1) {
          return text.substring(start, i + 1).trim();
        }
      }
    }
    return null;
  }
}
```

### 2.5 JSON 清理器（S1）

```dart
/// 确定性 JSON 清理
class JsonSanitizer {
  String sanitize(String s) {
    var out = s;
    // 移除 BOM 和零宽字符
    out = out.replaceAll(RegExp(r'[\uFEFF\u200B]'), '');
    // 智能引号 → ASCII 引号
    out = out.replaceAll('"', '"').replaceAll('"', '"');
    out = out.replaceAll("'", "'").replaceAll("'", "'");
    // 尾随逗号
    out = out.replaceAllMapped(RegExp(r',\s*([}\]])'), (m) => m.group(1)!);
    // 单引号 → 双引号（键和值）
    out = out.replaceAllMapped(
      RegExp(r"(?<=[:{,\s])'([^']*)'"),
      (m) => '"${m[1]}"',
    );
    // Python 布尔值
    out = out.replaceAll('True', 'true').replaceAll('False', 'false');
    out = out.replaceAll('None', 'null');
    return out;
  }
}
```

### 2.6 JSON 结构修复器（S3）

```dart
/// 确定性结构修复
class JsonRepairer {
  Map<String, dynamic> repair(String json, String schema) {
    Map<String, dynamic> obj;
    try {
      obj = jsonDecode(json) as Map<String, dynamic>;
    } catch (_) {
      return {'ok': false, 'error': 'parse_failed', 'proposals': []};
    }

    // 确保必需字段存在
    obj.putIfAbsent('proposals', () => []);
    obj.putIfAbsent('logs', () => []);
    if (!obj.containsKey('ok')) {
      obj['ok'] = obj['error'] == null;
    }

    // 数组包装（如果 schema 期望对象但收到数组）
    if (obj['proposals'] is! List) {
      obj['proposals'] = [];
    }

    return obj;
  }
}
```

### 2.7 LLM 修复回退（S4）

```dart
/// LLM 修复回退（仅调用一次）
class JsonLlmFallback {
  /// 修复 Prompt 模板
  static const _systemPrompt = '''
You are a JSON repair tool. Output ONLY valid JSON, no extra text.
''';

  static String _userPrompt(String schema, String broken) => '''
Schema:
$schema

Broken JSON:
$broken

Fix it so it matches schema. Preserve as much content as possible.
If data is irrecoverable, return:
{ "ok": false, "error": "unrecoverable_json", "proposals": [], "logs": [] }
''';

  Future<String?> repair({
    required String brokenJson,
    required String schema,
    required String modelId,
  }) async {
    try {
      final response = await _callLlm(
        systemPrompt: _systemPrompt,
        userPrompt: _userPrompt(schema, brokenJson),
        modelId: modelId,
        maxTokens: 2000,
        temperature: 0.0, // 低温确保稳定
      );
      return response;
    } catch (_) {
      return null;
    }
  }
}
```

### 2.8 输出截断器

```dart
/// 输出截断常量
const int kSoftCharLimit = 30000;
const int kHardCharLimit = 50000;

/// 输出截断器
class OutputTruncator {
  final OutputSummarizer _summarizer;

  Future<TruncationResult> process(String text, String modelId) async {
    // 小于软限 → 直接返回
    if (text.length <= kSoftCharLimit) {
      return TruncationResult(text: text, wasTruncated: false);
    }

    // 软限 < 长度 <= 硬限 → 尝试 Summarizer
    if (text.length <= kHardCharLimit) {
      final summarized = await _summarizer.summarize(text, modelId);
      if (summarized != null && summarized.length <= kSoftCharLimit) {
        return TruncationResult(
          text: summarized,
          wasTruncated: true,
          method: 'summarized',
        );
      }
    }

    // 超过硬限 → 强制截断
    final truncated = text.substring(0, kHardCharLimit) + '\n...[TRUNCATED]';
    return TruncationResult(
      text: truncated,
      wasTruncated: true,
      method: 'hard_truncate',
    );
  }
}

class TruncationResult {
  final String text;
  final bool wasTruncated;
  final String? method;

  TruncationResult({
    required this.text,
    required this.wasTruncated,
    this.method,
  });
}
```

### 2.9 Summarizer

```dart
/// 输出 Summarizer
class OutputSummarizer {
  static const _systemPrompt = '''
You are a summarizer for tool outputs. Output strictly valid JSON that fits the schema.
''';

  static String _userPrompt(String content) => '''
Raw output (may be long/truncated):
$content

Summarize into valid JSON proposals only. Preserve key facts, drop verbose details.
''';

  Future<String?> summarize(String content, String modelId) async {
    try {
      return await _callLlm(
        systemPrompt: _systemPrompt,
        userPrompt: _userPrompt(content),
        modelId: modelId,
        maxTokens: 4000,
        temperature: 0.3,
      );
    } catch (_) {
      return null;
    }
  }
}
```

---

## 3. Sleeptime/Idle Maintenance

### 3.1 空闲检测器

```dart
/// 空闲检测器
class IdleDetector {
  final Duration idleThreshold;
  DateTime _lastInteraction = DateTime.now();

  IdleDetector({this.idleThreshold = const Duration(seconds: 45)});

  /// 记录用户交互
  void recordInteraction() => _lastInteraction = DateTime.now();

  /// 是否空闲
  bool get isIdle => DateTime.now().difference(_lastInteraction) > idleThreshold;

  /// 空闲持续时间
  Duration get idleDuration => DateTime.now().difference(_lastInteraction);
}
```

### 3.2 Sleeptime 管理器

```dart
/// 后台维护任务类型
enum IdleTaskType {
  summarize,           // 摘要压缩
  foreshadowRefresh,   // 伏笔链接刷新
  goalCleanup,         // 目标清理
  memoryGc,            // Memory GC
}

/// Sleeptime 管理器
class SleeptimeManager {
  final RpTaskScheduler _scheduler;
  final IdleDetector _idleDetector;
  Timer? _ticker;

  void start() {
    _ticker = Timer.periodic(const Duration(seconds: 10), (_) => _tick());
  }

  void stop() {
    _ticker?.cancel();
    _ticker = null;
  }

  void _tick() {
    if (!_idleDetector.isIdle) return;

    // 检查是否有待处理的空闲任务
    final pendingTasks = _getPendingIdleTasks();
    if (pendingTasks.isEmpty) return;

    // 入队最高优先级任务
    final task = pendingTasks.first;
    _scheduler.enqueue(
      _buildIdleTask(task),
      priority: RpTaskPriority.idle,
    );
  }

  List<IdleTaskType> _getPendingIdleTasks() {
    // 根据当前状态决定需要运行的后台任务
    return [
      if (_needsSummarize()) IdleTaskType.summarize,
      if (_needsForeshadowRefresh()) IdleTaskType.foreshadowRefresh,
      if (_needsGoalCleanup()) IdleTaskType.goalCleanup,
    ];
  }
}
```

### 3.3 与 App 生命周期集成

```dart
/// App 生命周期监听
class RoleplayLifecycleObserver extends WidgetsBindingObserver {
  final IdleDetector idleDetector;
  final SleeptimeManager sleeptimeManager;

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.paused:
      case AppLifecycleState.inactive:
        // App 进入后台 → 触发空闲检测
        sleeptimeManager.start();
      case AppLifecycleState.resumed:
        // App 恢复 → 记录交互，暂停后台任务
        idleDetector.recordInteraction();
        sleeptimeManager.stop();
      default:
        break;
    }
  }
}
```

---

## 4. 错误码与遥测

### 4.1 错误码定义

```dart
/// 统一错误码
abstract class ErrorCodes {
  // JSON 解析相关 (1xx)
  static const jsonExtractFailed = 'E101';
  static const jsonSanitizeFailed = 'E102';
  static const jsonSchemaInvalid = 'E103';
  static const jsonStructuralRepairFailed = 'E104';
  static const jsonLlmRepairFailed = 'E105';
  static const jsonRepairFailed = 'E106';

  // Agent 执行相关 (2xx)
  static const agentExecutionError = 'E201';
  static const agentTimeout = 'E202';
  static const agentUnknown = 'E203';

  // 输出处理相关 (3xx)
  static const outputTruncated = 'E301';
  static const outputSummarizeFailed = 'E302';

  // Worker 相关 (4xx)
  static const workerCrash = 'E401';
  static const workerTimeout = 'E402';
}
```

### 4.2 遥测指标

```dart
/// Agent 遥测指标
class AgentMetrics {
  final Map<String, int> _successCount = {};
  final Map<String, int> _failureCount = {};
  final Map<String, List<int>> _durations = {};
  final Map<String, Map<String, int>> _errorCodes = {};
  final Map<String, int> _repairStages = {};

  void recordSuccess(String agentId, int durationMs) {
    _successCount[agentId] = (_successCount[agentId] ?? 0) + 1;
    _durations.putIfAbsent(agentId, () => []).add(durationMs);
  }

  void recordFailure(String agentId, String errorCode) {
    _failureCount[agentId] = (_failureCount[agentId] ?? 0) + 1;
    _errorCodes.putIfAbsent(agentId, () => {});
    _errorCodes[agentId]![errorCode] =
        (_errorCodes[agentId]![errorCode] ?? 0) + 1;
  }

  void recordRepairStage(String agentId, int stage) {
    final key = '$agentId:S$stage';
    _repairStages[key] = (_repairStages[key] ?? 0) + 1;
  }

  /// 获取修复率（S0 成功 / 总数）
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
}
```

---

## 5. Agent 实现

### 5.1 AgentHandler 接口

```dart
/// Agent 请求
class AgentRequest {
  final String agentId;
  final Map<String, dynamic> inputs;
  final RpWorkerMemoryReader memoryReader;
  final String modelId;

  AgentRequest({
    required this.agentId,
    required this.inputs,
    required this.memoryReader,
    required this.modelId,
  });
}

/// Agent 结果
class AgentResult {
  final bool ok;
  final String agentId;
  final List<Map<String, dynamic>> proposals;
  final String? errorCode;
  final String? errorMessage;
  final List<String> logs;
  final AgentResultMetrics? metrics;

  AgentResult.success({
    required this.agentId,
    required this.proposals,
    this.metrics,
  }) : ok = true, errorCode = null, errorMessage = null, logs = const [];

  AgentResult.failed({
    required this.agentId,
    required String errorCode,
    List<String>? logs,
  }) : ok = false,
       proposals = const [],
       this.errorCode = errorCode,
       errorMessage = null,
       this.logs = logs ?? const [],
       metrics = null;

  AgentResult.error({
    required this.agentId,
    required String errorCode,
    required String message,
    String? stackTrace,
  }) : ok = false,
       proposals = const [],
       this.errorCode = errorCode,
       errorMessage = message,
       logs = [if (stackTrace != null) stackTrace],
       metrics = null;
}
```

### 5.2 SceneDetector

```dart
/// 场景检测器
class SceneDetector {
  static Future<AgentResult> handle(AgentRequest req) async {
    // 由 AgentExecutor 调用，返回解析后的 JSON
    // 这里只负责 Proposals 转换
    return AgentResult.success(
      agentId: req.agentId,
      proposals: _toProposals(req.inputs['parsedData'], req.inputs),
    );
  }

  static List<Map<String, dynamic>> _toProposals(
    Map<String, dynamic> data,
    Map<String, dynamic> inputs,
  ) {
    if (data['detected'] != true) return [];

    final toScene = data['proposal']?['to_scene'];
    if (toScene == null) return [];

    return [
      {
        'kind': 'SCENE_TRANSITION',
        'domain': 'scene',
        'policyTier': 'reviewRequired',
        'payload': {
          'fromSceneId': data['proposal']?['from_scene_id'],
          'toScene': toScene,
        },
        'evidence': [
          {'type': 'message_span', 'note': data['evidence']},
        ],
        'reason': 'Detected ${data['transition_type']} transition',
      },
    ];
  }
}
```

### 5.3 StateUpdater

```dart
/// 状态更新器
class StateUpdater {
  static Future<AgentResult> handle(AgentRequest req) async {
    return AgentResult.success(
      agentId: req.agentId,
      proposals: _toProposals(req.inputs['parsedData'], req.inputs),
    );
  }

  static List<Map<String, dynamic>> _toProposals(
    Map<String, dynamic> data,
    Map<String, dynamic> inputs,
  ) {
    final updates = data['updates'] as List? ?? [];
    if (updates.isEmpty) return [];

    return updates.map((u) => {
      'kind': 'DRAFT_UPDATE',
      'domain': u['domain'],
      'policyTier': 'notifyApply',
      'payload': {
        'targetId': u['targetId'],
        'field': u['field'],
        'oldValue': u['oldValue'],
        'newValue': u['newValue'],
      },
      'evidence': [
        {'type': 'message_span', 'note': u['evidence']},
      ],
      'reason': u['reason'],
    }).toList();
  }
}
```

### 5.4 KeyEventExtractor

```dart
/// 关键事件提取器
class KeyEventExtractor {
  static Future<AgentResult> handle(AgentRequest req) async {
    return AgentResult.success(
      agentId: req.agentId,
      proposals: _toProposals(req.inputs['parsedData'], req.inputs),
    );
  }

  static List<Map<String, dynamic>> _toProposals(
    Map<String, dynamic> data,
    Map<String, dynamic> inputs,
  ) {
    final events = data['events'] as List? ?? [];
    if (events.isEmpty) return [];

    return events.map((e) => {
      'kind': 'CONFIRMED_WRITE',
      'domain': 'timeline',
      'policyTier': 'silent',
      'payload': {
        'eventId': _generateEventId(),
        'summary': e['summary'],
        'tags': e['tags'] ?? [],
        'timestamp': e['timestamp'],
        'participants': e['participants'] ?? [],
      },
      'evidence': [
        {'type': 'message_span', 'note': e['evidence']},
      ],
      'reason': 'Extracted key event',
    }).toList();
  }

  static String _generateEventId() =>
      'ev_${DateTime.now().millisecondsSinceEpoch}';
}
```

### 5.5 ConsistencyHeavy

```dart
/// 一致性重检测
class ConsistencyHeavy {
  static Future<AgentResult> handle(AgentRequest req) async {
    return AgentResult.success(
      agentId: req.agentId,
      proposals: _toProposals(req.inputs['parsedData'], req.inputs),
    );
  }

  static List<Map<String, dynamic>> _toProposals(
    Map<String, dynamic> data,
    Map<String, dynamic> inputs,
  ) {
    final violations = data['violations'] as List? ?? [];
    if (violations.isEmpty) return [];

    return violations.map((v) => {
      'kind': 'OUTPUT_FIX',
      'domain': v['domain'],
      'policyTier': 'reviewRequired',
      'payload': {
        'violationType': v['type'],
        'description': v['description'],
        'suggestedFix': v['suggestedFix'],
        'confidence': v['confidence'],
      },
      'evidence': [
        {'type': 'output_span', 'note': v['evidence']},
      ],
      'reason': 'Consistency violation detected',
    }).toList();
  }
}
```

---

## 6. 与 M3 Worker Isolate 集成

### 6.1 Task Router（增强版）

```dart
// rp_worker_entry.dart

Future<TaskResult> _executeTask(
  String taskType,
  RpWorkerRequest request,
  RpWorkerMemoryReader memoryReader,
) async {
  // 优先：注册表路由
  if (agentRegistry.has(taskType)) {
    return _executeRegisteredAgent(taskType, request, memoryReader);
  }

  // Agent 前缀路由（向后兼容）
  if (taskType.startsWith('agent:')) {
    final agentId = taskType.substring(6);
    if (agentRegistry.has(agentId)) {
      return _executeRegisteredAgent(agentId, request, memoryReader);
    }
  }

  // 其他任务类型...
  throw UnknownTaskTypeException(taskType);
}

Future<TaskResult> _executeRegisteredAgent(
  String agentId,
  RpWorkerRequest request,
  RpWorkerMemoryReader memoryReader,
) async {
  final executor = AgentExecutor(
    modelAdapter: ModelAdapter(),
    jsonPipeline: JsonPipeline(),
    truncator: OutputTruncator(),
    metrics: AgentMetrics(),
  );

  final result = await executor.execute(
    agentId: agentId,
    inputs: request.inputs,
    memoryReader: memoryReader,
    modelId: request.inputs['modelId'] ?? 'unknown',
  );

  return TaskResult(
    ok: result.ok,
    proposals: result.proposals,
    logs: result.logs,
    errorCode: result.errorCode,
    metrics: result.metrics?.toJson(),
  );
}
```

### 6.2 任务类型定义

```dart
// rp_task_spec.dart

abstract class RpTaskTypes {
  // Agent 任务
  static const sceneDetector = 'scene_detector';
  static const stateUpdater = 'state_updater';
  static const keyEventExtractor = 'key_event_extractor';
  static const consistencyHeavy = 'consistency_heavy';

  // 向后兼容（带 agent: 前缀）
  static const agentSceneDetector = 'agent:scene_detector';
  static const agentStateUpdater = 'agent:state_updater';
  static const agentKeyEventExtractor = 'agent:key_event_extractor';
  static const agentConsistencyHeavy = 'agent:consistency_heavy';
}
```

---

## 7. 实施计划（商业级）

### Phase 1: 核心框架（3-4 天）

| 任务 | 输出 | 验收 |
|------|------|------|
| AgentRegistry | `agent_registry.dart` | 编译期注册工作 |
| AgentExecutor | `agent_executor.dart` | LLM 调用 + 遥测 |
| AgentPrompts | `agent_prompts.dart` | 4 个 Agent 的三级提示词 |
| ModelAdapter | `model_adapter.dart` | 提示词选择正确 |

### Phase 2: JSON 管道（2-3 天）

| 任务 | 输出 | 验收 |
|------|------|------|
| JsonPipeline | `json_pipeline.dart` | 6 阶段管道工作 |
| S0-S3 组件 | `json_*.dart` | 确定性修复正确 |
| S4 LLM 回退 | `json_llm_fallback.dart` | 回退触发正确 |
| 单元测试 | `test/json_pipeline_test.dart` | 覆盖各种损坏 JSON |

### Phase 3: 输出治理（1-2 天）

| 任务 | 输出 | 验收 |
|------|------|------|
| OutputTruncator | `output_truncator.dart` | 截断阈值正确 |
| OutputSummarizer | `output_summarizer.dart` | Summarizer 工作 |

### Phase 4: Agent 实现（2-3 天）

| 任务 | 输出 | 验收 |
|------|------|------|
| SceneDetector | `scene_detector.dart` | SCENE_TRANSITION 正确 |
| StateUpdater | `state_updater.dart` | DRAFT_UPDATE 正确 |
| KeyEventExtractor | `key_event_extractor.dart` | Timeline 条目正确 |
| ConsistencyHeavy | `consistency_heavy.dart` | OUTPUT_FIX 正确 |

### Phase 5: Sleeptime（1-2 天）

| 任务 | 输出 | 验收 |
|------|------|------|
| IdleDetector | `idle_detector.dart` | 空闲检测正确 |
| SleeptimeManager | `sleeptime_manager.dart` | 后台任务入队正确 |
| 生命周期集成 | 修改主页面 | App 后台时触发 |

### Phase 6: 集成测试（2-3 天）

| 任务 | 输出 | 验收 |
|------|------|------|
| Worker 集成 | 修改 `rp_worker_entry.dart` | Agent 路由正确 |
| 错误码/遥测 | `error_codes.dart`, `agent_metrics.dart` | 指标收集正确 |
| 端到端测试 | `test/integration/` | 完整流程正确 |

**总计：11-17 天**

---

## 8. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| JSON 解析失败 | 6 阶段修复管道 + LLM 回退 |
| 模型输出不稳定 | 三级提示词适配 + 低温修复 |
| 输出过长 | 截断 + Summarizer |
| Worker 饱和 | 复用 M3 背压机制 |
| 后台任务干扰 | Idle 优先级 + 用户交互打断 |

---

## 9. 对比参考项目

| 特性 | Letta | MuMu | 本设计 |
|------|-------|------|--------|
| JSON 修复 | 多阶段 + LLM 回退 | 基础修复 | 6 阶段 + LLM 回退 |
| 输出截断 | 50k 硬限 | 动态裁剪 | 30k soft / 50k hard |
| 后台维护 | Sleeptime Agent | 章节后处理 | SleeptimeManager |
| 错误处理 | Summarizer fallback | 重试 | 降级 + 空提案 |
| 可观测性 | 详细日志 | 基础日志 | 错误码 + 遥测 |

---

## 附录 A: 提示词模板示例

### SceneDetector（高能力模型）

```
You are SceneDetector for an interactive fiction system.

## Task
Detect scene transitions in the latest conversation turn.

## Transition Types
- location_change: Characters move to a new location
- time_skip: Time passes (hours, days, etc.)
- goal_completed: A major goal is achieved
- new_character: A significant new character appears

## Output Format (JSON only)
{
  "detected": boolean,
  "transition_type": "location_change" | "time_skip" | "goal_completed" | "new_character",
  "confidence": 0.0-1.0,
  "evidence": "quote from conversation",
  "proposal": {
    "from_scene_id": "current scene ID",
    "to_scene": {
      "location": "new location name",
      "time": "new time description",
      "atmosphere": "mood/atmosphere"
    }
  }
}

If no transition detected, return: {"detected": false}
```

---

## 附录 B: 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-01-20 | 初版（Skill 化架构） |
| 2.0 | 2026-01-20 | 精简版（删除过度设计） |
| 3.0 | 2026-01-20 | 商业级版本，增加：多阶段 JSON 修复、输出截断/Summarizer、Sleeptime、遥测 |
