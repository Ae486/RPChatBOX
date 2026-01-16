# Skill 化 Agent 设计方案

> 目标：借鉴 Claude Code Skill 系统的声明式设计思想，为 roleplay-feature 构建一套**跨模型兼容、可配置、可扩展**的 Agent 体系。
>
> 前置文档：`19-ARCHITECTURE-REVIEW.md`、`20-AGENT-ORCHESTRATION-DESIGN.md`、`21-TECHNICAL-IMPLEMENTATION-MAPPING.md`
>
> 最后更新：2026-01-15

---

## 0. 背景与动机

### 0.1 Claude Skill 的优势

Claude Code 的 Skill 系统具有以下特点：

| 特点 | 说明 |
|------|------|
| 声明式配置 | YAML frontmatter + Markdown 指令，配置与代码分离 |
| 自动发现 | 基于 description 关键词自动触发 |
| 渐进加载 | 启动只加载元数据，激活时才加载完整内容 |
| 工具访问控制 | `allowed-tools` 限制可用工具 |
| 隔离执行 | `context: fork` 在独立上下文中运行 |
| 生命周期钩子 | PreToolUse / PostToolUse / Stop |

### 0.2 直接照搬的问题

Claude Skill 的"自动发现"依赖 Claude 模型的特定能力，在多模型场景下存在问题：

```
问题 1：不同模型对 description 的理解能力不同
问题 2：让模型自己决定"是否触发"会导致行为不可预测
问题 3：没有 Claude Code CLI 的基础设施支持
```

### 0.3 设计目标

借鉴 Skill 的**声明式配置**优势，但用**确定性调度**解决多模型兼容问题：

```
┌─────────────────────────────────────────────────────────────────┐
│  借鉴                          │  改进                          │
├─────────────────────────────────────────────────────────────────┤
│  声明式 Agent 定义              │  保留                          │
│  元数据驱动的模块化              │  保留                          │
│  渐进式加载                     │  保留                          │
│  工具访问控制                   │  保留（改为 domain 权限）        │
│  生命周期钩子                   │  保留（对应一致性闸门）          │
│  模型理解触发（description）    │  改为确定性规则触发              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. 需求定义

### 1.1 功能需求

| ID | 需求 | 优先级 | 说明 |
|----|------|--------|------|
| SK-01 | 声明式 Agent 配置 | P0 | Agent 行为通过配置文件定义，支持热更新 |
| SK-02 | 确定性触发规则 | P0 | 关键词、正则、信号条件，跨模型一致 |
| SK-03 | 模型适配层 | P0 | 根据模型能力选择提示词模板和解析策略 |
| SK-04 | 权限边界控制 | P1 | 每个 Agent 只能访问/修改特定 domain |
| SK-05 | 生命周期钩子 | P1 | 执行前后的验证和拦截机制 |
| SK-06 | 用户自定义 Agent | P2 | 用户可创建/编辑/分享 Agent 配置 |
| SK-07 | Agent 模板市场 | P3 | 社区分享的 Agent 配置（类似创意工坊） |

### 1.2 非功能需求

| ID | 需求 | 目标 |
|----|------|------|
| SK-NF-01 | 调度可预测性 | 相同输入 + 相同配置 = 相同调度决策（100%） |
| SK-NF-02 | 跨模型一致性 | 调度层行为与使用的模型无关 |
| SK-NF-03 | 配置热更新 | 修改配置后无需重启应用 |
| SK-NF-04 | 降级容错 | 模型输出异常时有明确的降级路径 |

### 1.3 与现有设计的映射

| 现有设计（20-AGENT-ORCHESTRATION） | Skill 化增强 |
|----------------------------------|-------------|
| Orchestrator（确定性状态机） | 保留，增加声明式触发规则配置 |
| 8 个 Specialist Agents | 改为声明式配置 + 执行器分离 |
| 版本闸门 | 保留，作为执行前钩子 |
| 失败处理矩阵 | 改为声明式降级策略配置 |

---

## 2. 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Skill-Based Agent 架构                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                    Layer 1: 配置层（声明式）                            │ │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐     │ │
│  │  │ Agent 配置   │ │ 触发规则    │ │ 模型适配    │ │ 钩子配置    │     │ │
│  │  │ (YAML/JSON) │ │ (YAML/JSON) │ │ (YAML/JSON) │ │ (YAML/JSON) │     │ │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘     │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                      ↓                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                    Layer 2: 调度层（确定性）                            │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │ │
│  │  │                     RpOrchestrator                              │ │ │
│  │  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐      │ │ │
│  │  │  │ 触发评估   │ │ 优先级排序 │ │ 预算检查   │ │ 任务分发   │      │ │ │
│  │  │  │(规则匹配)  │ │(确定性)   │ │(确定性)   │ │(确定性)   │      │ │ │
│  │  │  └───────────┘ └───────────┘ └───────────┘ └───────────┘      │ │ │
│  │  └─────────────────────────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                      ↓                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                    Layer 3: 适配层（处理模型差异）                       │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │ │
│  │  │                     ModelAdapter                                │ │ │
│  │  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐      │ │ │
│  │  │  │ 能力检测   │ │ 模板选择   │ │ 输出解析   │ │ 重试降级   │      │ │ │
│  │  │  └───────────┘ └───────────┘ └───────────┘ └───────────┘      │ │ │
│  │  └─────────────────────────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                      ↓                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                    Layer 4: 执行层（调用 LLM）                          │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐       │ │
│  │  │ Scene   │ │ State   │ │KeyEvent │ │ Goals   │ │Foreshadow│       │ │
│  │  │Detector │ │ Updater │ │Extractor│ │ Updater │ │ Linker  │       │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘       │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                      ↓                                      │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                    Layer 5: 输出层（统一契约）                          │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐ │ │
│  │  │                     Proposal 验证 & 路由                         │ │ │
│  │  └─────────────────────────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
lib/services/roleplay/
├── skills/                              # Skill 化 Agent 系统
│   ├── config/                          # 配置定义
│   │   ├── agent_config.dart            # Agent 配置数据结构
│   │   ├── trigger_rule.dart            # 触发规则数据结构
│   │   ├── model_profile.dart           # 模型能力配置
│   │   └── hook_config.dart             # 钩子配置
│   │
│   ├── registry/                        # 注册表
│   │   ├── agent_registry.dart          # Agent 注册与发现
│   │   ├── trigger_registry.dart        # 触发规则注册
│   │   └── model_registry.dart          # 模型配置注册
│   │
│   ├── scheduler/                       # 调度器
│   │   ├── trigger_evaluator.dart       # 触发条件评估
│   │   ├── priority_sorter.dart         # 优先级排序
│   │   └── task_dispatcher.dart         # 任务分发
│   │
│   ├── adapter/                         # 模型适配
│   │   ├── model_adapter.dart           # 适配器主类
│   │   ├── prompt_selector.dart         # 提示词选择
│   │   ├── output_parser.dart           # 输出解析
│   │   └── fallback_handler.dart        # 降级处理
│   │
│   ├── executor/                        # Agent 执行器
│   │   ├── base_executor.dart           # 基础执行器
│   │   ├── scene_detector_executor.dart
│   │   ├── state_updater_executor.dart
│   │   ├── key_event_extractor_executor.dart
│   │   ├── goals_updater_executor.dart
│   │   ├── foreshadow_linker_executor.dart
│   │   ├── consistency_gate_executor.dart
│   │   ├── summarizer_executor.dart
│   │   └── edit_interpreter_executor.dart
│   │
│   └── hooks/                           # 生命周期钩子
│       ├── hook_runner.dart             # 钩子执行器
│       ├── pre_execute_hooks.dart       # 执行前钩子
│       └── post_execute_hooks.dart      # 执行后钩子
│
├── configs/                             # 声明式配置文件
│   ├── agents/                          # Agent 配置
│   │   ├── scene_detector.yaml
│   │   ├── state_updater.yaml
│   │   ├── key_event_extractor.yaml
│   │   ├── goals_updater.yaml
│   │   ├── foreshadow_linker.yaml
│   │   ├── consistency_gate.yaml
│   │   ├── summarizer.yaml
│   │   └── edit_interpreter.yaml
│   │
│   ├── models/                          # 模型能力配置
│   │   ├── openai.yaml
│   │   ├── anthropic.yaml
│   │   ├── google.yaml
│   │   ├── deepseek.yaml
│   │   └── local.yaml
│   │
│   └── hooks/                           # 钩子配置
│       ├── consistency_checks.yaml
│       └── permission_checks.yaml
│
└── templates/                           # 提示词模板
    ├── scene_detector/
    │   ├── high.md
    │   ├── medium.md
    │   └── low.md
    ├── state_updater/
    │   └── ...
    └── ...
```

---

## 3. 配置规范

### 3.1 Agent 配置格式

```yaml
# configs/agents/scene_detector.yaml
---
# === 元数据 ===
id: scene-detector
version: "1.0.0"
name: 场景检测器
description: |
  检测场景转换信号，包括：地点变化、时间跳转、目标完成、新角色登场。
  当检测到场景转换时，生成 SCENE_TRANSITION 提议。

# === 类型与优先级 ===
type: hybrid                    # deterministic | hybrid | full_agent
priority: 1                     # 调度优先级（1 最高）
enabled: true                   # 默认启用

# === 触发规则（确定性，不依赖模型） ===
triggers:
  # 关键词触发
  keywords:
    zh:
      - "来到"
      - "前往"
      - "抵达"
      - "走进"
      - "离开"
      - "第二天"
      - "几小时后"
      - "翌日"
      - "次日"
    en:
      - "arrived at"
      - "went to"
      - "entered"
      - "left"
      - "the next day"
      - "hours later"

  # 正则模式
  patterns:
    - "\\d+[小时天周月年]后"
    - "(走进|进入|离开|来到|抵达)[^，。,\\.]{1,20}"
    - "(the next|\\d+ hours?|\\d+ days?) later"

  # 信号条件
  signals:
    - condition: "goal_completed_this_turn"
      weight: 0.4
    - condition: "new_character_appeared"
      weight: 0.3
    - condition: "location_keyword_density > 0.1"
      weight: 0.2

  # 周期触发
  interval:
    turns: 15                   # 每 15 轮至少检查一次

  # 触发阈值
  threshold: 0.3                # 综合得分超过此值才触发

# === 权限边界 ===
permissions:
  read:                         # 可读取的 domain
    - scene
    - timeline
    - goals
    - character
  write: []                     # 不直接写入（通过 Proposal）
  propose:                      # 可生成的 Proposal 类型
    - SCENE_TRANSITION

# === 执行配置 ===
execution:
  max_input_tokens: 2000        # 输入 token 上限
  max_output_tokens: 800        # 输出 token 上限
  timeout_ms: 30000             # 超时时间
  retry:
    max_attempts: 2             # 最大重试次数
    backoff_ms: 1000            # 重试间隔

# === 降级策略 ===
fallback:
  on_parse_error: "retry_with_simpler_prompt"
  on_timeout: "skip_this_turn"
  on_model_error: "queue_for_next_turn"

# === 生命周期钩子 ===
hooks:
  pre_execute:
    - type: version_gate        # 版本闸门检查
      config:
        check_source_rev: true
        check_story_rev: true
    - type: budget_check        # 预算检查
      config:
        min_headroom: 500

  post_execute:
    - type: schema_validate     # Schema 验证
    - type: semantic_validate   # 语义验证
      config:
        require_evidence: true
    - type: log_result          # 记录结果

# === 模型特定配置 ===
model_overrides:
  "gpt-4*":
    execution:
      max_output_tokens: 600    # GPT-4 输出更精简
  "claude-*":
    execution:
      max_output_tokens: 1000   # Claude 允许更长输出
  "local-*":
    triggers:
      threshold: 0.5            # 本地模型提高触发阈值
    execution:
      max_input_tokens: 1500    # 本地模型减少输入
---

## System Prompt

你是 SceneDetector，负责检测互动小说中的场景转换。

## 检测信号

1. **地点变化**：角色移动到新位置
2. **时间跳转**：时间明显推进（小时/天/更长）
3. **目标完成**：当前目标已达成
4. **新角色登场**：之前未出场的角色出现

## 输出格式

必须输出有效 JSON：

```json
{
  "detected": true,
  "transition_type": "location_change",
  "evidence": "引用的文本片段",
  "proposal": {
    "from_scene_id": "current",
    "to_scene": {
      "location": "新地点",
      "time": "时间描述",
      "present_characters": ["角色ID"],
      "recap": "场景概要"
    }
  }
}
```

如果没有检测到场景转换：
```json
{
  "detected": false
}
```

## 重要规则

- 只检测**明确发生**的转换，不要推测
- 必须提供 evidence（原文引用）
- 输出纯 JSON，不要有其他文字
```

### 3.2 模型能力配置格式

```yaml
# configs/models/openai.yaml
---
provider: openai
models:
  gpt-4o:
    capabilities:
      structured_output: true       # 支持 JSON mode
      function_calling: true        # 支持 Tool use
      reliable_json: true           # JSON 输出稳定
      instruction_following: 0.95   # 指令遵循能力
      context_window: 128000

    prompt_tier: high               # 使用精简提示词

    output_parsing:
      strategy: direct              # 直接解析
      json_repair: false            # 不需要修复

  gpt-4o-mini:
    capabilities:
      structured_output: true
      function_calling: true
      reliable_json: true
      instruction_following: 0.90
      context_window: 128000

    prompt_tier: high

    output_parsing:
      strategy: direct
      json_repair: false

  gpt-3.5-turbo:
    capabilities:
      structured_output: true
      function_calling: true
      reliable_json: false          # 偶尔不稳定
      instruction_following: 0.80
      context_window: 16000

    prompt_tier: medium             # 使用详细提示词

    output_parsing:
      strategy: extract_json        # 提取 JSON
      json_repair: true             # 启用修复
---
```

```yaml
# configs/models/local.yaml
---
provider: local
models:
  llama-3-8b:
    capabilities:
      structured_output: false
      function_calling: false
      reliable_json: false
      instruction_following: 0.60
      context_window: 8000

    prompt_tier: low                # 使用详细 + 示例提示词

    output_parsing:
      strategy: extract_and_repair  # 提取 + 修复
      json_repair: true
      max_repair_attempts: 2

    # 本地模型特殊配置
    special:
      add_json_examples: true       # 在提示词中添加示例
      repeat_format_instruction: 3  # 重复格式指令次数

  qwen-7b:
    capabilities:
      structured_output: false
      function_calling: false
      reliable_json: false
      instruction_following: 0.65
      context_window: 32000

    prompt_tier: low

    output_parsing:
      strategy: extract_and_repair
      json_repair: true
---
```

### 3.3 钩子配置格式

```yaml
# configs/hooks/consistency_checks.yaml
---
hooks:
  # 执行前钩子
  pre_execute:
    version_gate:
      description: 检查版本是否过期
      type: deterministic
      config:
        check_fields:
          - source_rev
          - foundation_rev
          - story_rev
        on_stale: reject

    budget_check:
      description: 检查 token 预算
      type: deterministic
      config:
        min_headroom: 500
        on_insufficient: defer

    permission_check:
      description: 检查 Agent 权限
      type: deterministic
      config:
        on_violation: reject_with_log

  # 执行后钩子
  post_execute:
    schema_validate:
      description: 验证输出 schema
      type: deterministic
      config:
        strict: true
        on_invalid: retry_once

    semantic_validate:
      description: 语义验证（证据存在、ID有效）
      type: deterministic
      config:
        checks:
          - evidence_exists
          - referenced_ids_valid
          - no_future_knowledge
        on_invalid: downgrade_to_draft

    consistency_gate:
      description: 一致性闸门
      type: hybrid              # 可能需要 LLM 辅助
      applies_to:
        - consistency_gate      # 只对特定 Agent 启用
      config:
        light_checks:           # 始终运行
          - appearance_invariant
          - state_constraint
          - present_characters
        heavy_checks:           # 条件触发
          - timeline_order
          - knowledge_leak
        trigger_heavy_when:
          - "prompt_utilization >= 0.85"
          - "recent_edit_in_2_turns"
---
```

---

## 4. 核心组件设计

### 4.1 触发评估器（TriggerEvaluator）

```dart
/// 触发规则评估器（100% 确定性）
class TriggerEvaluator {
  final Map<String, AgentConfig> _agentConfigs;

  /// 评估哪些 Agent 应该被触发
  List<AgentTriggerResult> evaluate(TurnContext ctx) {
    final results = <AgentTriggerResult>[];

    for (final config in _agentConfigs.values) {
      if (!config.enabled) continue;

      final score = _calculateTriggerScore(config, ctx);

      if (score >= config.triggers.threshold) {
        results.add(AgentTriggerResult(
          agentId: config.id,
          score: score,
          matchedRules: _getMatchedRules(config, ctx),
          priority: config.priority,
        ));
      }
    }

    // 按优先级和得分排序
    results.sort((a, b) {
      final priorityCompare = a.priority.compareTo(b.priority);
      if (priorityCompare != 0) return priorityCompare;
      return b.score.compareTo(a.score);
    });

    return results;
  }

  /// 计算触发得分（确定性）
  double _calculateTriggerScore(AgentConfig config, TurnContext ctx) {
    double score = 0.0;

    // 关键词匹配
    final keywordScore = _evaluateKeywords(
      config.triggers.keywords,
      ctx.userInput,
      ctx.assistantOutput,
      ctx.language,
    );
    score += keywordScore * 0.4;

    // 正则模式匹配
    final patternScore = _evaluatePatterns(
      config.triggers.patterns,
      ctx.userInput,
      ctx.assistantOutput,
    );
    score += patternScore * 0.3;

    // 信号条件评估
    final signalScore = _evaluateSignals(
      config.triggers.signals,
      ctx.signals,
    );
    score += signalScore * 0.2;

    // 周期触发
    if (config.triggers.interval != null) {
      if (ctx.turnNumber % config.triggers.interval!.turns == 0) {
        score += 0.1;
      }
    }

    return score.clamp(0.0, 1.0);
  }

  /// 关键词评估
  double _evaluateKeywords(
    Map<String, List<String>> keywords,
    String userInput,
    String? assistantOutput,
    String language,
  ) {
    final targetKeywords = keywords[language] ?? keywords['en'] ?? [];
    if (targetKeywords.isEmpty) return 0.0;

    final text = '$userInput ${assistantOutput ?? ''}'.toLowerCase();

    int matchCount = 0;
    for (final keyword in targetKeywords) {
      if (text.contains(keyword.toLowerCase())) {
        matchCount++;
      }
    }

    return matchCount / targetKeywords.length;
  }

  /// 正则模式评估
  double _evaluatePatterns(
    List<String> patterns,
    String userInput,
    String? assistantOutput,
  ) {
    if (patterns.isEmpty) return 0.0;

    final text = '$userInput ${assistantOutput ?? ''}';

    int matchCount = 0;
    for (final pattern in patterns) {
      final regex = RegExp(pattern, caseSensitive: false);
      if (regex.hasMatch(text)) {
        matchCount++;
      }
    }

    return matchCount / patterns.length;
  }

  /// 信号条件评估
  double _evaluateSignals(
    List<SignalCondition> conditions,
    TurnSignals signals,
  ) {
    if (conditions.isEmpty) return 0.0;

    double weightedSum = 0.0;
    double totalWeight = 0.0;

    for (final condition in conditions) {
      final met = _checkSignalCondition(condition.condition, signals);
      if (met) {
        weightedSum += condition.weight;
      }
      totalWeight += condition.weight;
    }

    return totalWeight > 0 ? weightedSum / totalWeight : 0.0;
  }

  /// 检查单个信号条件
  bool _checkSignalCondition(String condition, TurnSignals signals) {
    // 简单的条件表达式解析
    // 支持：goal_completed_this_turn, new_character_appeared, etc.
    switch (condition) {
      case 'goal_completed_this_turn':
        return signals.goalCompletedThisTurn;
      case 'new_character_appeared':
        return signals.newCharacterAppeared;
      case 'user_edited_old_message':
        return signals.userEditedOldMessage;
      case 'token_pressure_high':
        return signals.promptUtilization >= 0.85;
      default:
        // 支持表达式：location_keyword_density > 0.1
        return _evaluateExpression(condition, signals);
    }
  }
}
```

### 4.2 模型适配器（ModelAdapter）

```dart
/// 模型适配器（处理不同模型的差异）
class ModelAdapter {
  final Map<String, ModelProfile> _modelProfiles;
  final Map<String, Map<String, String>> _promptTemplates;

  /// 获取适配后的执行配置
  AdaptedExecutionConfig adapt(
    String agentId,
    AgentConfig agentConfig,
    String modelId,
  ) {
    final profile = _getModelProfile(modelId);
    final tier = profile.promptTier;

    // 获取提示词模板
    final promptTemplate = _promptTemplates[agentId]?[tier]
        ?? _promptTemplates[agentId]?['medium']
        ?? agentConfig.defaultPrompt;

    // 应用模型特定覆盖
    final executionConfig = _applyModelOverrides(
      agentConfig.execution,
      agentConfig.modelOverrides,
      modelId,
    );

    return AdaptedExecutionConfig(
      prompt: promptTemplate,
      maxInputTokens: executionConfig.maxInputTokens,
      maxOutputTokens: executionConfig.maxOutputTokens,
      parsingStrategy: profile.outputParsing.strategy,
      jsonRepairEnabled: profile.outputParsing.jsonRepair,
      capabilities: profile.capabilities,
    );
  }

  /// 解析模型输出
  ParseResult parseOutput(
    String raw,
    String modelId,
    String expectedSchema,
  ) {
    final profile = _getModelProfile(modelId);
    final strategy = profile.outputParsing.strategy;

    switch (strategy) {
      case 'direct':
        return _parseDirect(raw, expectedSchema);

      case 'extract_json':
        return _parseExtractJson(raw, expectedSchema);

      case 'extract_and_repair':
        return _parseExtractAndRepair(
          raw,
          expectedSchema,
          profile.outputParsing.maxRepairAttempts,
        );

      default:
        return _parseDirect(raw, expectedSchema);
    }
  }

  /// 直接解析
  ParseResult _parseDirect(String raw, String expectedSchema) {
    try {
      final json = jsonDecode(raw);
      final valid = _validateSchema(json, expectedSchema);
      return ParseResult(
        success: valid,
        data: valid ? json : null,
        error: valid ? null : 'Schema validation failed',
      );
    } catch (e) {
      return ParseResult(
        success: false,
        error: 'JSON parse error: $e',
      );
    }
  }

  /// 提取 JSON
  ParseResult _parseExtractJson(String raw, String expectedSchema) {
    // 策略 1：提取 markdown 代码块
    final codeBlockMatch = RegExp(r'```(?:json)?\s*([\s\S]*?)```').firstMatch(raw);
    if (codeBlockMatch != null) {
      final result = _parseDirect(codeBlockMatch.group(1)!.trim(), expectedSchema);
      if (result.success) return result;
    }

    // 策略 2：提取 {...} 子串
    final start = raw.indexOf('{');
    final end = raw.lastIndexOf('}');
    if (start >= 0 && end > start) {
      final jsonStr = raw.substring(start, end + 1);
      final result = _parseDirect(jsonStr, expectedSchema);
      if (result.success) return result;
    }

    return ParseResult(
      success: false,
      error: 'Could not extract valid JSON',
      rawOutput: raw,
    );
  }

  /// 提取并修复 JSON
  ParseResult _parseExtractAndRepair(
    String raw,
    String expectedSchema,
    int maxAttempts,
  ) {
    // 先尝试提取
    var result = _parseExtractJson(raw, expectedSchema);
    if (result.success) return result;

    // 尝试修复常见错误
    final repaired = _repairCommonErrors(raw);
    result = _parseExtractJson(repaired, expectedSchema);
    if (result.success) return result;

    return ParseResult(
      success: false,
      error: 'JSON extraction and repair failed',
      rawOutput: raw,
    );
  }

  /// 修复常见 JSON 错误
  String _repairCommonErrors(String raw) {
    var repaired = raw;

    // 修复：缺少引号的键
    repaired = repaired.replaceAllMapped(
      RegExp(r'(\{|\,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:'),
      (m) => '${m.group(1)}"${m.group(2)}":',
    );

    // 修复：单引号改双引号
    repaired = repaired.replaceAll("'", '"');

    // 修复：尾随逗号
    repaired = repaired.replaceAll(RegExp(r',\s*([}\]])'), r'$1');

    // 修复：Python 布尔值
    repaired = repaired.replaceAll('True', 'true');
    repaired = repaired.replaceAll('False', 'false');
    repaired = repaired.replaceAll('None', 'null');

    return repaired;
  }

  /// 获取模型配置（支持通配符匹配）
  ModelProfile _getModelProfile(String modelId) {
    // 精确匹配
    if (_modelProfiles.containsKey(modelId)) {
      return _modelProfiles[modelId]!;
    }

    // 通配符匹配（gpt-4* 匹配 gpt-4o, gpt-4-turbo 等）
    for (final entry in _modelProfiles.entries) {
      if (entry.key.endsWith('*')) {
        final prefix = entry.key.substring(0, entry.key.length - 1);
        if (modelId.startsWith(prefix)) {
          return entry.value;
        }
      }
    }

    // 默认配置
    return _defaultProfile;
  }
}
```

### 4.3 Agent 执行器基类

```dart
/// Agent 执行器基类
abstract class BaseAgentExecutor {
  final String agentId;
  final AgentConfig config;
  final ModelAdapter modelAdapter;
  final HookRunner hookRunner;

  BaseAgentExecutor({
    required this.agentId,
    required this.config,
    required this.modelAdapter,
    required this.hookRunner,
  });

  /// 执行 Agent
  Future<AgentResult> execute(AgentInput input) async {
    // 1. 执行前钩子
    final preHookResult = await hookRunner.runPreExecuteHooks(
      agentId: agentId,
      input: input,
      hooks: config.hooks.preExecute,
    );

    if (!preHookResult.shouldContinue) {
      return AgentResult.skipped(
        agentId: agentId,
        reason: preHookResult.reason,
      );
    }

    // 2. 适配模型配置
    final adaptedConfig = modelAdapter.adapt(
      agentId,
      config,
      input.modelId,
    );

    // 3. 构建提示词
    final prompt = buildPrompt(input, adaptedConfig);

    // 4. 调用 LLM
    String rawOutput;
    try {
      rawOutput = await _callLLM(
        prompt: prompt,
        provider: input.provider,
        config: adaptedConfig,
      );
    } catch (e) {
      return _handleExecutionError(e, input);
    }

    // 5. 解析输出
    final parseResult = modelAdapter.parseOutput(
      rawOutput,
      input.modelId,
      getExpectedSchema(),
    );

    if (!parseResult.success) {
      return _handleParseError(parseResult, input, adaptedConfig);
    }

    // 6. 转换为 Proposals
    final proposals = transformToProposals(parseResult.data!, input);

    // 7. 执行后钩子
    final postHookResult = await hookRunner.runPostExecuteHooks(
      agentId: agentId,
      input: input,
      proposals: proposals,
      hooks: config.hooks.postExecute,
    );

    // 8. 返回结果
    return AgentResult.success(
      agentId: agentId,
      proposals: postHookResult.filteredProposals,
      diagnostics: AgentDiagnostics(
        inputTokens: _estimateTokens(prompt),
        outputTokens: _estimateTokens(rawOutput),
        parseAttempts: parseResult.attempts,
        hookResults: [preHookResult, postHookResult],
      ),
    );
  }

  /// 子类实现：构建提示词
  String buildPrompt(AgentInput input, AdaptedExecutionConfig config);

  /// 子类实现：获取期望的输出 schema
  String getExpectedSchema();

  /// 子类实现：转换为 Proposals
  List<Proposal> transformToProposals(Map<String, dynamic> data, AgentInput input);

  /// 处理执行错误
  AgentResult _handleExecutionError(dynamic error, AgentInput input) {
    final fallback = config.fallback.onModelError;

    switch (fallback) {
      case 'skip_this_turn':
        return AgentResult.skipped(
          agentId: agentId,
          reason: 'Model error: $error',
        );
      case 'queue_for_next_turn':
        return AgentResult.deferred(
          agentId: agentId,
          reason: 'Model error, queued for retry',
        );
      default:
        return AgentResult.failed(
          agentId: agentId,
          error: error.toString(),
        );
    }
  }

  /// 处理解析错误
  Future<AgentResult> _handleParseError(
    ParseResult parseResult,
    AgentInput input,
    AdaptedExecutionConfig config,
  ) async {
    final fallback = this.config.fallback.onParseError;

    switch (fallback) {
      case 'retry_with_simpler_prompt':
        // 降级到更简单的提示词重试一次
        if (config.capabilities.instructionFollowing < 0.7) {
          return AgentResult.failed(
            agentId: agentId,
            error: 'Parse failed, model capability too low for retry',
          );
        }

        final simplerPrompt = _buildSimplerPrompt(input);
        // ... 重试逻辑

      case 'return_empty':
        return AgentResult.success(
          agentId: agentId,
          proposals: [],
          diagnostics: AgentDiagnostics(parseError: parseResult.error),
        );

      default:
        return AgentResult.failed(
          agentId: agentId,
          error: parseResult.error,
        );
    }
  }
}
```

### 4.4 SceneDetector 执行器示例

```dart
/// SceneDetector 执行器
class SceneDetectorExecutor extends BaseAgentExecutor {
  SceneDetectorExecutor({
    required super.config,
    required super.modelAdapter,
    required super.hookRunner,
  }) : super(agentId: 'scene-detector');

  @override
  String buildPrompt(AgentInput input, AdaptedExecutionConfig config) {
    final template = config.prompt;

    // 替换模板变量
    return template
        .replaceAll('{{CURRENT_SCENE}}', _formatCurrentScene(input.scene))
        .replaceAll('{{RECENT_MESSAGES}}', _formatRecentMessages(input.messages))
        .replaceAll('{{ACTIVE_GOALS}}', _formatActiveGoals(input.goals));
  }

  @override
  String getExpectedSchema() {
    return '''
{
  "detected": boolean,
  "transition_type"?: "location_change" | "time_skip" | "goal_completed" | "new_character",
  "evidence"?: string,
  "proposal"?: {
    "from_scene_id"?: string,
    "to_scene": {
      "location"?: string,
      "time"?: string,
      "present_characters": string[],
      "recap": string
    }
  }
}
''';
  }

  @override
  List<Proposal> transformToProposals(
    Map<String, dynamic> data,
    AgentInput input,
  ) {
    if (data['detected'] != true) {
      return [];
    }

    final toScene = data['proposal']?['to_scene'];
    if (toScene == null) {
      return [];
    }

    return [
      Proposal(
        proposalId: generateProposalId(),
        storyId: input.storyId,
        branchId: input.branchId,
        kind: ProposalKind.sceneTransition,
        domain: 'scene',
        policyTier: PolicyTier.reviewRequired,
        payload: SceneTransitionPayload(
          fromSceneId: data['proposal']?['from_scene_id'],
          toScene: SceneState(
            sceneId: generateSceneId(),
            location: toScene['location'],
            time: toScene['time'],
            presentCharacters: List<String>.from(toScene['present_characters'] ?? []),
            recap: toScene['recap'],
          ),
        ),
        evidence: [
          EvidenceRef(
            type: 'message_span',
            refId: input.lastMessageId,
            note: data['evidence'],
          ),
        ],
        reason: 'Detected ${data['transition_type']} transition',
        sourceRev: input.sourceRev,
      ),
    ];
  }
}
```

---

## 5. 提示词模板设计

### 5.1 模板分级策略

```
┌─────────────────────────────────────────────────────────────────┐
│                    提示词模板分级                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  high (instruction_following >= 0.9)                            │
│  ├── 精简指令                                                    │
│  ├── 最小示例                                                    │
│  └── 依赖模型理解能力                                            │
│                                                                 │
│  medium (0.7 <= instruction_following < 0.9)                    │
│  ├── 详细指令                                                    │
│  ├── 完整示例                                                    │
│  └── 明确的格式要求                                              │
│                                                                 │
│  low (instruction_following < 0.7)                              │
│  ├── 极度详细的指令                                              │
│  ├── 多个示例                                                    │
│  ├── 重复格式要求                                                │
│  └── 显式的错误提示                                              │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 SceneDetector 模板示例

**high.md**（用于 GPT-4、Claude 等高能力模型）

```markdown
# SceneDetector

Detect scene transitions. Output JSON only.

Types: location_change | time_skip | goal_completed | new_character

## Current Scene
{{CURRENT_SCENE}}

## Recent Messages
{{RECENT_MESSAGES}}

## Output
```json
{"detected": bool, "transition_type"?: string, "evidence"?: string, "proposal"?: {...}}
```
```

**medium.md**（用于 GPT-3.5、Gemini 等中等能力模型）

```markdown
# Scene Transition Detector

You are SceneDetector for an interactive fiction system.

## Task
Analyze the conversation and detect if a scene transition occurred.

## Transition Types
1. **location_change** - Character moved to a new location
2. **time_skip** - Significant time passed (hours, days, etc.)
3. **goal_completed** - Current objective was achieved
4. **new_character** - Previously absent character appeared

## Current Scene
{{CURRENT_SCENE}}

## Recent Messages
{{RECENT_MESSAGES}}

## Output Format
You MUST output valid JSON in exactly this format:

If transition detected:
```json
{
  "detected": true,
  "transition_type": "location_change",
  "evidence": "exact quote from text",
  "proposal": {
    "to_scene": {
      "location": "new location",
      "time": "time description",
      "present_characters": ["character_id"],
      "recap": "brief scene summary"
    }
  }
}
```

If no transition:
```json
{
  "detected": false
}
```

IMPORTANT: Output JSON only. No explanation or other text.
```

**low.md**（用于本地模型等低能力模型）

```markdown
# Scene Transition Detector

## Your Job
You must check if the scene changed in the story.

## What is a scene change?
A scene change happens when ONE of these things occurs:
1. The character goes to a NEW PLACE
2. Time jumps forward (like "the next day" or "hours later")
3. A goal is completed
4. A new character appears

## Current Scene Information
{{CURRENT_SCENE}}

## Recent Conversation
{{RECENT_MESSAGES}}

## How to Answer

STEP 1: Read the conversation carefully
STEP 2: Check if any scene change happened
STEP 3: Write your answer in JSON format

### If a scene change happened, write this:

```json
{
  "detected": true,
  "transition_type": "location_change",
  "evidence": "copy the exact text that shows the change",
  "proposal": {
    "to_scene": {
      "location": "write the new location",
      "time": "write the time if mentioned",
      "present_characters": ["list character names"],
      "recap": "write a short summary"
    }
  }
}
```

### If NO scene change happened, write this:

```json
{
  "detected": false
}
```

## Examples

INPUT: "Alice walked into the dark tavern and sat at the bar."
OUTPUT:
```json
{
  "detected": true,
  "transition_type": "location_change",
  "evidence": "walked into the dark tavern",
  "proposal": {
    "to_scene": {
      "location": "dark tavern",
      "present_characters": ["Alice"],
      "recap": "Alice entered a tavern"
    }
  }
}
```

INPUT: "Alice continued talking to Bob about the weather."
OUTPUT:
```json
{
  "detected": false
}
```

## VERY IMPORTANT RULES
1. ONLY output JSON
2. Do NOT write any explanation
3. Do NOT write anything before or after the JSON
4. Make sure your JSON is valid

Now analyze the conversation and output your JSON:
```

---

## 6. 与现有设计的整合

### 6.1 Orchestrator 改造

```dart
/// 改造后的 Orchestrator
class RpOrchestrator {
  final AgentRegistry agentRegistry;
  final TriggerEvaluator triggerEvaluator;
  final ModelAdapter modelAdapter;
  final TaskDispatcher taskDispatcher;
  final BudgetBroker budgetBroker;

  /// 每轮调度流程
  Future<OrchestratorResult> processTurn(TurnContext ctx) async {
    // 1. 评估触发条件（确定性）
    final triggeredAgents = triggerEvaluator.evaluate(ctx);

    // 2. 预算检查（确定性）
    final affordableAgents = budgetBroker.filterByBudget(
      triggeredAgents,
      ctx.availableTokens,
    );

    // 3. 分发任务
    final tasks = affordableAgents.map((agent) => AgentTask(
      agentId: agent.agentId,
      priority: agent.priority,
      input: _buildAgentInput(agent, ctx),
    )).toList();

    // 4. 执行（可能在 Worker Isolate）
    final results = await taskDispatcher.dispatch(tasks);

    // 5. 收集 Proposals
    final proposals = results
        .where((r) => r.success)
        .expand((r) => r.proposals)
        .toList();

    // 6. 应用 Tier Policy
    return OrchestratorResult(
      proposals: proposals,
      diagnostics: _buildDiagnostics(results),
    );
  }
}
```

### 6.2 配置加载器

```dart
/// 配置加载器（支持热更新）
class SkillConfigLoader {
  final String configPath;
  final FileWatcher? watcher;

  Map<String, AgentConfig>? _cachedAgentConfigs;
  Map<String, ModelProfile>? _cachedModelProfiles;

  /// 加载所有 Agent 配置
  Future<Map<String, AgentConfig>> loadAgentConfigs() async {
    if (_cachedAgentConfigs != null) return _cachedAgentConfigs!;

    final configs = <String, AgentConfig>{};
    final agentDir = Directory('$configPath/agents');

    await for (final file in agentDir.list()) {
      if (file.path.endsWith('.yaml')) {
        final content = await File(file.path).readAsString();
        final config = AgentConfig.fromYaml(content);
        configs[config.id] = config;
      }
    }

    _cachedAgentConfigs = configs;
    return configs;
  }

  /// 加载模型配置
  Future<Map<String, ModelProfile>> loadModelProfiles() async {
    if (_cachedModelProfiles != null) return _cachedModelProfiles!;

    final profiles = <String, ModelProfile>{};
    final modelDir = Directory('$configPath/models');

    await for (final file in modelDir.list()) {
      if (file.path.endsWith('.yaml')) {
        final content = await File(file.path).readAsString();
        final providerConfig = ModelProviderConfig.fromYaml(content);

        for (final entry in providerConfig.models.entries) {
          profiles[entry.key] = entry.value;
        }
      }
    }

    _cachedModelProfiles = profiles;
    return profiles;
  }

  /// 启用热更新
  void enableHotReload() {
    watcher?.watch(configPath, (event) {
      if (event.path.contains('/agents/')) {
        _cachedAgentConfigs = null;
      } else if (event.path.contains('/models/')) {
        _cachedModelProfiles = null;
      }
    });
  }
}
```

---

## 7. 用户自定义 Agent（P2 功能）

### 7.1 用户可配置的范围

```yaml
# 用户可修改的配置项
user_customizable:
  # 触发规则
  triggers:
    keywords: true          # 可添加/删除关键词
    patterns: true          # 可添加/删除正则
    threshold: true         # 可调整阈值
    interval: true          # 可调整周期

  # 执行配置
  execution:
    enabled: true           # 可启用/禁用
    priority: true          # 可调整优先级

  # 不可修改
  permissions: false        # 权限边界不可修改
  hooks: false              # 钩子不可修改（安全考虑）
```

### 7.2 自定义 Agent UI

```
┌─────────────────────────────────────────────────────────────────┐
│  Agent 配置 - SceneDetector                                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  [✓] 启用                                    优先级: [1▼]       │
│                                                                 │
│  ─── 触发条件 ───────────────────────────────────────────────── │
│                                                                 │
│  关键词（检测到这些词时触发）:                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 来到 × │ 前往 × │ 抵达 × │ 第二天 × │ [+ 添加]          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  触发阈值: [====●====] 0.3                                      │
│  （越低越容易触发，越高越严格）                                    │
│                                                                 │
│  周期检查: 每 [15] 轮至少检查一次                                 │
│                                                                 │
│  ─── 高级选项 ───────────────────────────────────────────────── │
│                                                                 │
│  [展开] 正则表达式                                               │
│  [展开] 信号条件                                                 │
│                                                                 │
│  ────────────────────────────────────────────────────────────── │
│                                                                 │
│  [恢复默认]                              [保存] [取消]           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. 实现路线图

### 8.1 与现有里程碑的整合

```
M0: Foundation（基础设施）
    └── 无变化

M1: Context Compiler（上下文编译）
    └── 无变化

M2: Consistency Gate（一致性闸门）
    └── 整合到钩子系统

M3: Worker Isolate（后台任务）
    └── 整合 Skill 化执行器

M4: Agent Integration（Agent 集成）    ← 主要变更
    ├── M4.1: 配置系统
    │   ├── 定义 Agent 配置格式
    │   ├── 定义模型能力配置格式
    │   ├── 实现配置加载器
    │   └── 实现热更新机制
    │
    ├── M4.2: 触发系统
    │   ├── 实现 TriggerEvaluator
    │   ├── 关键词匹配
    │   ├── 正则模式匹配
    │   └── 信号条件评估
    │
    ├── M4.3: 模型适配
    │   ├── 实现 ModelAdapter
    │   ├── 提示词模板分级
    │   ├── 输出解析策略
    │   └── JSON 修复机制
    │
    ├── M4.4: 执行器
    │   ├── 实现 BaseAgentExecutor
    │   ├── 实现各 Agent 执行器
    │   └── 集成钩子系统
    │
    └── M4.5: 迁移现有 Agent
        ├── SceneDetector
        ├── StateUpdater
        ├── KeyEventExtractor
        ├── GoalsUpdater
        ├── ForeshadowLinker
        ├── ConsistencyGate
        ├── Summarizer
        └── EditInterpreter

M5: Advanced Features（高级功能）
    └── 增加用户自定义 Agent

M6: Polish & Optimization（优化）
    └── 增加 Agent 模板市场
```

### 8.2 M4 详细任务

| 任务 | 输出 | 验收标准 |
|------|------|----------|
| 定义配置格式 | `config/*.dart` | Schema 完整、可解析 |
| 实现配置加载 | `SkillConfigLoader` | 支持 YAML、热更新 |
| 实现触发评估 | `TriggerEvaluator` | 100% 确定性、跨模型一致 |
| 实现模型适配 | `ModelAdapter` | 支持 5+ 主流模型 |
| 提示词模板 | `templates/*` | high/medium/low 三级 |
| 执行器基类 | `BaseAgentExecutor` | 钩子集成、错误处理 |
| 迁移 8 个 Agent | `*_executor.dart` | 功能等价、测试通过 |

---

## 9. 验收测试

### 9.1 触发一致性测试

| 测试场景 | 预期结果 |
|----------|----------|
| 相同输入 + 相同配置 + 不同模型 | 触发的 Agent 列表相同 |
| 关键词命中 | 对应 Agent 触发 |
| 阈值边界 | 得分 = 阈值时触发，得分 < 阈值时不触发 |
| 周期触发 | 到达周期轮数时触发 |

### 9.2 模型适配测试

| 测试场景 | 预期结果 |
|----------|----------|
| GPT-4 输出 | 直接解析成功 |
| Gemini 带 markdown 输出 | 提取后解析成功 |
| 本地模型混杂文字输出 | 修复后解析成功 |
| 无法修复的输出 | 返回空 proposals + 日志 |

### 9.3 端到端测试

| 测试场景 | 预期结果 |
|----------|----------|
| 用户输入"来到酒馆" | SceneDetector 触发，生成 SCENE_TRANSITION |
| 用户输入普通对话 | 无 Agent 触发 |
| 修改触发阈值 | 触发行为相应变化 |
| 热更新配置 | 无需重启，新配置生效 |

---

## 10. 附录

### 10.1 术语表

| 术语 | 定义 |
|------|------|
| **Skill** | 声明式配置的 Agent 能力单元 |
| **触发规则** | 确定性的 Agent 激活条件（关键词、正则、信号） |
| **模型适配** | 根据模型能力调整提示词和解析策略 |
| **提示词模板** | 分级的提示词（high/medium/low） |
| **钩子** | 执行前后的验证和拦截机制 |

### 10.2 相关文档

- `19-ARCHITECTURE-REVIEW.md`：架构审查
- `20-AGENT-ORCHESTRATION-DESIGN.md`：Agent 编排设计
- `21-TECHNICAL-IMPLEMENTATION-MAPPING.md`：技术实现映射
- `22-FINAL-SUMMARY.md`：设计总结

### 10.3 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-01-15 | 初版，Skill 化 Agent 设计 |
