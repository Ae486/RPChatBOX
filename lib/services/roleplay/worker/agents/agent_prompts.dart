/// Agent 提示词模板
///
/// 静态定义所有 Agent 的三级提示词（高/中/低能力模型）
/// POS: Services / Roleplay / Worker / Agents
library;

import 'model_adapter.dart';

/// 提示词集合（三级）
class AgentPromptSet {
  /// Agent ID
  final String id;

  /// 高能力模型提示词
  final String high;

  /// 中等能力模型提示词
  final String medium;

  /// 低能力模型提示词
  final String low;

  /// 输出 JSON Schema
  final String schema;

  /// 系统提示词（可选）
  final String? systemPrompt;

  const AgentPromptSet({
    required this.id,
    required this.high,
    required this.medium,
    required this.low,
    required this.schema,
    this.systemPrompt,
  });

  /// 根据层级选择提示词
  String getPrompt(PromptTier tier) {
    return switch (tier) {
      PromptTier.high => high,
      PromptTier.medium => medium,
      PromptTier.low => low,
    };
  }
}

/// Agent 提示词模板集合
abstract class AgentPrompts {
  // ===========================================================================
  // SceneDetector - 场景检测器
  // ===========================================================================

  static const sceneDetector = AgentPromptSet(
    id: 'scene_detector',
    high: '''
You are SceneDetector for an interactive fiction system. Detect scene transitions.

## Task
Analyze the latest conversation turn and detect if a scene transition occurred.

## Transition Types
- location_change: Characters move to a new location
- time_skip: Significant time passes (hours, days, etc.)
- goal_completed: A major story goal is achieved
- new_character: A significant new character enters the scene

## Instructions
1. Read the latest messages carefully
2. Compare with current scene state
3. Detect any transition signals
4. Output JSON only, no explanation

## Output Format
```json
{
  "detected": boolean,
  "transition_type": "location_change" | "time_skip" | "goal_completed" | "new_character" | null,
  "confidence": 0.0-1.0,
  "evidence": "quote from conversation that triggered detection",
  "proposal": {
    "from_scene_id": "current scene ID",
    "to_scene": {
      "location": "new location name",
      "time": "new time description",
      "atmosphere": "mood/atmosphere description"
    }
  }
}
```

If no transition detected, return: {"detected": false}
''',
    medium: '''
# Scene Transition Detector

You are SceneDetector for an interactive fiction system.

## Your Task
Detect if a scene transition occurred in the latest conversation.

## Transition Types
- location_change: Moving to new place
- time_skip: Time passes significantly
- goal_completed: Major goal achieved
- new_character: Important character appears

## Output (JSON only)
```json
{
  "detected": true/false,
  "transition_type": "type_name" or null,
  "confidence": 0.0-1.0,
  "evidence": "quote from text",
  "proposal": {
    "from_scene_id": "current_id",
    "to_scene": {
      "location": "new place",
      "time": "new time",
      "atmosphere": "mood"
    }
  }
}
```

No transition? Return: {"detected": false}
''',
    low: '''
# Scene Detector

Check if the scene changed.

## Types
- location_change
- time_skip
- goal_completed
- new_character

## Output JSON
{"detected": false} if no change

Or:
{
  "detected": true,
  "transition_type": "type",
  "evidence": "quote",
  "proposal": {"to_scene": {"location": "place"}}
}
''',
    schema: '''
{
  "detected": "boolean (required)",
  "transition_type": "string (optional): location_change|time_skip|goal_completed|new_character",
  "confidence": "number 0.0-1.0 (optional)",
  "evidence": "string (optional)",
  "proposal": {
    "from_scene_id": "string (optional)",
    "to_scene": {
      "location": "string (optional)",
      "time": "string (optional)",
      "atmosphere": "string (optional)"
    }
  }
}
''',
  );

  // ===========================================================================
  // StateUpdater - 状态更新器
  // ===========================================================================

  static const stateUpdater = AgentPromptSet(
    id: 'state_updater',
    high: '''
You are StateUpdater for an interactive fiction system. Track state changes.

## Task
Analyze the latest conversation and detect changes to character states, items, relationships, or world state.

## Change Types
- character: Character attributes (health, mood, skills, etc.)
- item: Item acquisition, loss, or modification
- relationship: Relationship changes between characters
- world: World state changes (weather, time, events)

## Instructions
1. Compare current state with conversation content
2. Identify explicit or implied changes
3. Extract old and new values
4. Provide evidence from text

## Output Format
```json
{
  "updates": [
    {
      "domain": "character" | "item" | "relationship" | "world",
      "targetId": "entity identifier",
      "field": "specific field that changed",
      "oldValue": "previous value or null",
      "newValue": "new value",
      "evidence": "quote from conversation",
      "reason": "why this change was detected"
    }
  ]
}
```

If no updates: {"updates": []}
''',
    medium: '''
# State Updater

Track changes in the story.

## Change Types
- character: Health, mood, skills
- item: Gained, lost, modified
- relationship: Between characters
- world: Environment changes

## Output JSON
```json
{
  "updates": [
    {
      "domain": "type",
      "targetId": "who/what",
      "field": "what changed",
      "oldValue": "before",
      "newValue": "after",
      "evidence": "quote",
      "reason": "why"
    }
  ]
}
```

No changes? {"updates": []}
''',
    low: '''
# State Updater

Find changes in the story.

## Output
{
  "updates": [
    {
      "domain": "character/item/relationship/world",
      "targetId": "name",
      "field": "what",
      "newValue": "value",
      "evidence": "quote"
    }
  ]
}

No changes: {"updates": []}
''',
    schema: '''
{
  "updates": [
    {
      "domain": "string (required): character|item|relationship|world",
      "targetId": "string (required)",
      "field": "string (required)",
      "oldValue": "any (optional)",
      "newValue": "any (required)",
      "evidence": "string (optional)",
      "reason": "string (optional)"
    }
  ]
}
''',
  );

  // ===========================================================================
  // KeyEventExtractor - 关键事件提取器
  // ===========================================================================

  static const keyEventExtractor = AgentPromptSet(
    id: 'key_event_extractor',
    high: '''
You are KeyEventExtractor for an interactive fiction system. Extract significant story events.

## Task
Identify key events from the latest conversation that should be recorded in the timeline.

## Event Criteria
- Plot-significant actions or decisions
- Character revelations or developments
- Important discoveries or achievements
- Relationship milestones
- Turning points in the narrative

## Instructions
1. Read the conversation carefully
2. Identify events worth remembering
3. Summarize each event concisely
4. Tag with relevant categories
5. Note participants

## Output Format
```json
{
  "events": [
    {
      "summary": "Brief description of what happened",
      "tags": ["plot", "character", "discovery", etc.],
      "timestamp": "in-story time if mentioned",
      "participants": ["character names involved"],
      "significance": "low" | "medium" | "high",
      "evidence": "quote from conversation"
    }
  ]
}
```

No significant events? {"events": []}
''',
    medium: '''
# Key Event Extractor

Find important events in the story.

## What counts as key event
- Important actions or choices
- Character revelations
- Major discoveries
- Relationship changes
- Plot turning points

## Output JSON
```json
{
  "events": [
    {
      "summary": "what happened",
      "tags": ["category"],
      "timestamp": "when",
      "participants": ["who"],
      "significance": "low/medium/high",
      "evidence": "quote"
    }
  ]
}
```

Nothing important? {"events": []}
''',
    low: '''
# Event Extractor

Find important story events.

## Output
{
  "events": [
    {
      "summary": "what happened",
      "tags": ["tag"],
      "participants": ["who"],
      "evidence": "quote"
    }
  ]
}

Nothing: {"events": []}
''',
    schema: '''
{
  "events": [
    {
      "summary": "string (required)",
      "tags": ["string"] (optional)",
      "timestamp": "string (optional)",
      "participants": ["string"] (optional)",
      "significance": "string (optional): low|medium|high",
      "evidence": "string (optional)"
    }
  ]
}
''',
  );

  // ===========================================================================
  // ConsistencyHeavy - 重量级一致性检测
  // ===========================================================================

  static const consistencyHeavy = AgentPromptSet(
    id: 'consistency_heavy',
    high: '''
You are ConsistencyChecker for an interactive fiction system. Detect narrative inconsistencies.

## Task
Analyze the AI's response for consistency violations against the established story context.

## Violation Types
- timeline: Events contradicting established timeline
- character: Out-of-character behavior or trait contradictions
- knowledge: Characters knowing things they shouldn't
- location: Impossible locations or movements
- item: Items appearing/disappearing without explanation
- relationship: Inconsistent relationship dynamics

## Instructions
1. Compare AI response against memory context
2. Identify any contradictions or impossibilities
3. Assess severity and confidence
4. Suggest corrections if possible

## Output Format
```json
{
  "violations": [
    {
      "type": "timeline" | "character" | "knowledge" | "location" | "item" | "relationship",
      "domain": "affected domain",
      "description": "what is inconsistent",
      "evidence": "quote from AI response",
      "conflictsWith": "what it contradicts in memory",
      "confidence": 0.0-1.0,
      "suggestedFix": "how to fix it (optional)"
    }
  ]
}
```

No violations? {"violations": []}
''',
    medium: '''
# Consistency Checker

Find errors in the AI's story response.

## Error Types
- timeline: Wrong order of events
- character: Acting out of character
- knowledge: Knowing impossible things
- location: Wrong place
- item: Missing/extra items
- relationship: Wrong relationships

## Output JSON
```json
{
  "violations": [
    {
      "type": "error_type",
      "domain": "area",
      "description": "what's wrong",
      "evidence": "quote",
      "conflictsWith": "the truth",
      "confidence": 0.0-1.0,
      "suggestedFix": "how to fix"
    }
  ]
}
```

All good? {"violations": []}
''',
    low: '''
# Consistency Check

Find story errors.

## Types
timeline, character, knowledge, location, item, relationship

## Output
{
  "violations": [
    {
      "type": "error_type",
      "description": "problem",
      "evidence": "quote",
      "suggestedFix": "fix"
    }
  ]
}

OK: {"violations": []}
''',
    schema: '''
{
  "violations": [
    {
      "type": "string (required): timeline|character|knowledge|location|item|relationship",
      "domain": "string (optional)",
      "description": "string (required)",
      "evidence": "string (optional)",
      "conflictsWith": "string (optional)",
      "confidence": "number 0.0-1.0 (optional)",
      "suggestedFix": "string (optional)"
    }
  ]
}
''',
  );

  // ===========================================================================
  // 辅助方法
  // ===========================================================================

  /// 获取指定 Agent 的提示词集合
  static AgentPromptSet? getPromptSet(String agentId) {
    return switch (agentId) {
      'scene_detector' => sceneDetector,
      'state_updater' => stateUpdater,
      'key_event_extractor' => keyEventExtractor,
      'consistency_heavy' => consistencyHeavy,
      _ => null,
    };
  }

  /// 获取指定 Agent 的 Schema
  static String? getSchema(String agentId) {
    return getPromptSet(agentId)?.schema;
  }

  /// 获取所有已定义的 Agent ID
  static List<String> get allAgentIds => [
        'scene_detector',
        'state_updater',
        'key_event_extractor',
        'consistency_heavy',
      ];
}
