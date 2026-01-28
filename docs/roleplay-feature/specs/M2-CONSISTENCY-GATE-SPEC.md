# M2 Consistency Gate Spec

> 版本: 1.1.0
> 创建日期: 2026-01-18
> 最后更新: 2026-01-19
> 状态: 📋 设计中（已通过多模型审查）

---

## 1. 目标

为 Roleplay Feature 实现一致性闸门，在流式输出场景下检测并处理低级设定错误：
- 轻量闸门（始终运行）：外观/状态/在场角色
- 重量闸门（触发式）：时间线/知识泄露
- 与流式输出集成（永不阻塞已输出文本）
- OUTPUT_FIX Proposal 生成

---

## 2. 设计来源

### 2.1 项目内设计文档

| 文档 | 相关章节 |
|------|----------|
| 22-FINAL-SUMMARY.md | ADR-007: 一致性闸门两阶段 |
| 12-KEY-EVENTS-LINKER-AND-CONSISTENCY-GATES.md | 第 6 节: 一致性闸门 |
| 21-TECHNICAL-IMPLEMENTATION-MAPPING.md | OUTPUT_FIX Payload Schema |

### 2.2 外部参考（胶水编程原则）

| 框架/项目 | 借鉴点 | 适配方式 |
|-----------|--------|----------|
| Guardrails AI | Validator 模式、流式验证分块处理 | Dart 实现 |
| NVIDIA NeMo Guardrails | 解耦响应生成与验证 | 架构模式 |
| LlamaFirewall | Agent 输出过滤 | 概念参考 |

**评估结论**：
- 无现成 Dart/Flutter guardrail 框架可直接引入
- 借鉴 Guardrails AI 的 Validator + StreamingFix 模式
- 自实现轻量级验证器，保持最小侵入性

---

## 3. 架构设计

### 3.1 两阶段闸门

```
┌─────────────────────────────────────────────────────────────────┐
│                      轻量闸门 (Always-On)                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Appearance  │  │   State     │  │  Presence   │             │
│  │ Validator   │  │ Validator   │  │ Validator   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│        ↓                ↓                ↓                      │
│              ┌─────────────────────────┐                        │
│              │   ViolationCollector    │                        │
│              └─────────────────────────┘                        │
├─────────────────────────────────────────────────────────────────┤
│                      重量闸门 (Triggered)                        │
│  触发条件: prompt_utilization >= 0.85 OR headroom < 800        │
│  ┌─────────────┐  ┌─────────────┐                              │
│  │  Timeline   │  │  Knowledge  │                              │
│  │ Validator   │  │  Validator  │                              │
│  └─────────────┘  └─────────────┘                              │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 数据流

```
LLM Streaming Output
        │
        ▼
┌───────────────────┐
│  StreamBuffer     │─────→ UI (实时渲染)
│  (accumulate)     │
└───────────────────┘
        │
        ▼ (flush 时)
┌───────────────────┐
│  ConsistencyGate  │
│  .validate()      │
└───────────────────┘
        │
        ├── violations.isEmpty → ✅ Pass
        │
        └── violations.isNotEmpty
                │
                ▼
        ┌───────────────────┐
        │ OUTPUT_FIX        │
        │ Proposal          │
        └───────────────────┘
                │
                ▼
        ┌───────────────────┐
        │ Policy Tiering    │
        │ (notify/review)   │
        └───────────────────┘
```

### 3.3 核心原则

1. **永不阻塞流式输出**：检测异步进行，违规后置处理
2. **不修改已输出文本**：违规发现后提供修复建议，不回滚
3. **轻量优先**：默认只运行低成本检测
4. **可解释**：每个违规带证据链和修复建议

---

## 4. 数据模型

### 4.1 Validator 接口

```dart
/// 验证器接口
abstract class RpValidator {
  String get id;
  String get displayName;
  ValidatorWeight get weight;  // light | heavy

  /// 执行验证
  Future<List<RpViolation>> validate(RpValidationContext ctx);
}

enum ValidatorWeight { light, heavy }
```

### 4.2 Violation 结构

```dart
/// 违规条目
class RpViolation {
  final String code;           // e.g., 'APPEARANCE_MISMATCH'
  final ViolationSeverity severity;  // info | warn | error
  final String message;        // 人类可读描述
  final String? expected;      // 期望值
  final String? found;         // 实际值
  final double confidence;     // 置信度 (0.0 ~ 1.0) [v1.1 新增]
  final List<RpEvidenceRef> evidence;  // 证据链
  final List<RpRecommendation> recommended;  // 修复建议

  /// 是否通过置信度阈值过滤
  bool passesThreshold(double threshold) => confidence >= threshold;
}

enum ViolationSeverity { info, warn, error }

/// 各验证器默认置信度阈值
class ValidatorThresholds {
  static const appearance = 0.7;  // 外观描述可能有修饰语干扰
  static const state = 0.8;       // 状态检测较确定
  static const presence = 0.9;    // 在场判断应高置信度
  static const timeline = 0.85;   // 时间线较复杂
  static const knowledge = 0.75;  // 知识边界模糊
}
```

### 4.3 Recommendation 类型

```dart
/// 修复建议
sealed class RpRecommendation {
  const RpRecommendation();
}

/// 建议修正内存
class ProposeMemoryPatch extends RpRecommendation {
  final String domain;
  final String logicalId;
  final Map<String, dynamic> patch;
  const ProposeMemoryPatch({...});
}

/// 建议用户更正
class SuggestUserCorrection extends RpRecommendation {
  final String text;
  const SuggestUserCorrection(this.text);
}

/// 建议重新生成
class SuggestRetryGeneration extends RpRecommendation {
  final String reason;
  final List<String>? constraintsToAdd;
  const SuggestRetryGeneration({...});
}
```

### 4.4 ValidationContext

```dart
/// 验证上下文
class RpValidationContext {
  final String storyId;
  final String branchId;
  final String outputText;        // 待验证的输出文本
  final RpMemoryReader memory;    // 内存读取器
  final RpPackedContext? context; // 已编译的上下文（可选）
  final double promptUtilization; // 上下文使用率
  final int headroomTokens;       // 剩余 token 空间
}
```

---

## 5. 验证器实现

### 5.1 外观验证器 (Light)

```dart
/// 检测外观描述不一致
class AppearanceValidator implements RpValidator {
  @override String get id => 'appearance';
  @override ValidatorWeight get weight => ValidatorWeight.light;

  /// 检测字段
  static const checkFields = [
    'hair_color',      // 发色
    'eye_color',       // 瞳色
    'height',          // 身高
    'distinctive_marks', // 特征标记
  ];

  @override
  Future<List<RpViolation>> validate(RpValidationContext ctx) async {
    // 1. 从内存读取角色外观
    // 2. 在输出文本中检测外观描述
    // 3. 比对是否一致
  }
}
```

### 5.2 状态验证器 (Light)

```dart
/// 检测状态约束违反
class StateValidator implements RpValidator {
  @override String get id => 'state';
  @override ValidatorWeight get weight => ValidatorWeight.light;

  /// 检测规则
  /// - 使用未拥有的物品
  /// - 忽略当前伤势/状态效果
  /// - 违反角色能力限制

  @override
  Future<List<RpViolation>> validate(RpValidationContext ctx) async {
    // 1. 从内存读取状态（injury/inventory/flags）
    // 2. 解析输出文本中的动作/状态引用
    // 3. 检测冲突
  }
}
```

### 5.3 在场验证器 (Light)

```dart
/// 检测在场角色一致性
class PresenceValidator implements RpValidator {
  @override String get id => 'presence';
  @override ValidatorWeight get weight => ValidatorWeight.light;

  /// 检测规则
  /// - 不在场角色出现对话/动作
  /// - 已离场角色继续参与

  @override
  Future<List<RpViolation>> validate(RpValidationContext ctx) async {
    // 1. 从 Scene 读取在场角色列表
    // 2. 检测输出中的角色引用
    // 3. 验证在场状态
  }
}
```

### 5.4 时间线验证器 (Heavy)

```dart
/// 检测时间线矛盾
class TimelineValidator implements RpValidator {
  @override String get id => 'timeline';
  @override ValidatorWeight get weight => ValidatorWeight.heavy;

  /// 检测规则
  /// - 引用未发生的事件
  /// - 时序矛盾（事件顺序颠倒）
  /// - 与已确认事件冲突

  @override
  Future<List<RpViolation>> validate(RpValidationContext ctx) async {
    // 仅在 heavy 模式触发
    // 1. 从 Timeline 读取关键事件
    // 2. 检测输出中的时间引用
    // 3. 验证时序一致性
  }
}
```

### 5.5 知识泄露验证器 (Heavy)

```dart
/// 检测角色知识边界
class KnowledgeValidator implements RpValidator {
  @override String get id => 'knowledge';
  @override ValidatorWeight get weight => ValidatorWeight.heavy;

  /// 检测规则
  /// - 角色知道不应知道的信息
  /// - 元游戏信息泄露

  @override
  Future<List<RpViolation>> validate(RpValidationContext ctx) async {
    // 仅在 heavy 模式触发
    // 1. 从 Character.knowledge 读取角色知识边界
    // 2. 检测输出中的信息引用
    // 3. 验证知识来源合法性
  }
}
```

---

## 6. 闸门服务

### 6.1 ConsistencyGate

```dart
/// 一致性闸门服务
class RpConsistencyGate {
  final List<RpValidator> _lightValidators;
  final List<RpValidator> _heavyValidators;

  /// 执行轻量验证（始终运行）
  Future<List<RpViolation>> validateLight(RpValidationContext ctx);

  /// 执行重量验证（触发式）
  Future<List<RpViolation>> validateHeavy(RpValidationContext ctx);

  /// 判断是否需要 heavy 验证
  bool shouldRunHeavy(RpValidationContext ctx) {
    return ctx.promptUtilization >= 0.85 || ctx.headroomTokens < 800;
  }

  /// 生成 OUTPUT_FIX Proposal
  RpProposal? buildOutputFixProposal(List<RpViolation> violations);
}
```

### 6.2 ViolationCode 定义

```dart
/// 违规代码
class ViolationCode {
  // 外观类
  static const hairColorMismatch = 'APPEARANCE_HAIR_COLOR';
  static const eyeColorMismatch = 'APPEARANCE_EYE_COLOR';
  static const heightMismatch = 'APPEARANCE_HEIGHT';

  // 状态类
  static const itemNotOwned = 'STATE_ITEM_NOT_OWNED';
  static const injuryIgnored = 'STATE_INJURY_IGNORED';
  static const abilityExceeded = 'STATE_ABILITY_EXCEEDED';

  // 在场类
  static const characterAbsent = 'PRESENCE_CHARACTER_ABSENT';
  static const characterLeft = 'PRESENCE_CHARACTER_LEFT';

  // 时间线类
  static const eventNotOccurred = 'TIMELINE_EVENT_NOT_OCCURRED';
  static const timeSequenceError = 'TIMELINE_SEQUENCE_ERROR';

  // 知识类
  static const knowledgeLeak = 'KNOWLEDGE_LEAK';
  static const metagaming = 'KNOWLEDGE_METAGAMING';
}
```

---

## 7. 与流式输出集成

### 7.1 集成点

在 `streaming.dart` 的 `_handleStreamFlush()` 中集成：

```dart
Future<void> _handleStreamFlush(String accumulatedText) async {
  // 现有逻辑：更新 UI

  // 新增：一致性检测（异步，不阻塞）
  if (_isRoleplaySession(widget.conversation)) {
    _runConsistencyCheck(accumulatedText);
  }
}

Future<void> _runConsistencyCheck(String text) async {
  final ctx = RpValidationContext(
    storyId: widget.conversation.id,
    branchId: 'main',
    outputText: text,
    memory: await _ensureMemoryReader(),
    promptUtilization: _calculatePromptUtilization(),
    headroomTokens: _calculateHeadroom(),
  );

  // 轻量闸门（始终运行）
  final violations = await _consistencyGate.validateLight(ctx);

  // 重量闸门（条件触发）
  if (_consistencyGate.shouldRunHeavy(ctx)) {
    violations.addAll(await _consistencyGate.validateHeavy(ctx));
  }

  // 处理违规
  if (violations.isNotEmpty) {
    _handleViolations(violations);
  }
}
```

### 7.2 违规处理策略

```dart
void _handleViolations(List<RpViolation> violations) {
  // 按严重性分组
  final errors = violations.where((v) => v.severity == ViolationSeverity.error);
  final warnings = violations.where((v) => v.severity == ViolationSeverity.warn);

  // error: 生成 Proposal，policy = reviewRequired
  // warn: 生成 Proposal，policy = notifyApply
  // info: 仅记录日志

  if (errors.isNotEmpty || warnings.isNotEmpty) {
    final proposal = _consistencyGate.buildOutputFixProposal(violations);
    if (proposal != null) {
      _proposalQueue.add(proposal);
    }
  }
}
```

---

## 8. 文本分析工具

### 8.1 文本提取器

```dart
/// 从输出文本中提取关键信息
class RpTextExtractor {
  /// 提取外观描述
  static Map<String, String?> extractAppearanceRefs(String text);

  /// 提取物品引用
  static List<String> extractItemRefs(String text);

  /// 提取角色引用
  static List<String> extractCharacterRefs(String text);

  /// 提取动作描述
  static List<String> extractActions(String text);
}
```

### 8.2 模式匹配（v0 简单实现）

```dart
/// v0: 基于关键词的简单匹配
class RpPatternMatcher {
  /// 外观关键词
  static const appearancePatterns = {
    'hair': r'(头发|发色|hair)',
    'eye': r'(眼睛|瞳色|eyes?)',
    'height': r'(身高|height)',
  };

  /// 状态关键词
  static const statePatterns = {
    'injury': r'(伤|痛|受伤|injured)',
    'item': r'(拿着|持有|手中|携带)',
  };

  /// 未来可升级为 NLP 模型
}
```

---

## 9. 文件结构

```
lib/services/roleplay/consistency_gate/
├── rp_validator.dart           # Validator 接口
├── rp_violation.dart           # Violation 数据结构
├── rp_validation_context.dart  # 验证上下文
├── rp_consistency_gate.dart    # 闸门服务
├── validators/
│   ├── appearance_validator.dart
│   ├── state_validator.dart
│   ├── presence_validator.dart
│   ├── timeline_validator.dart
│   └── knowledge_validator.dart
└── utils/
    ├── rp_text_extractor.dart
    └── rp_pattern_matcher.dart

test/unit/services/roleplay/consistency_gate/
├── rp_consistency_gate_test.dart
├── appearance_validator_test.dart
├── state_validator_test.dart
├── presence_validator_test.dart
└── rp_text_extractor_test.dart
```

---

## 10. 测试计划

### 10.1 单元测试

| 测试 | 验收标准 |
|------|----------|
| Validator 接口 | 各验证器正确实现接口 |
| Violation 生成 | 违规检测准确，证据链完整 |
| 闸门触发条件 | heavy 模式正确触发 |
| Proposal 生成 | OUTPUT_FIX Payload 符合 schema |

### 10.2 集成测试场景

| 场景 | 输入 | 期望输出 |
|------|------|----------|
| 发色错误 | 角色发色=黑，输出提及金发 | APPEARANCE_HAIR_COLOR violation |
| 物品不存在 | 角色无剑，输出拔剑 | STATE_ITEM_NOT_OWNED violation |
| 角色不在场 | 角色A离场，输出A对话 | PRESENCE_CHARACTER_ABSENT violation |

---

## 11. 风险与缓解

| 风险 | 缓解措施 |
|------|----------|
| 误报干扰用户 | 轻量闸门高置信度阈值；用户可禁用 |
| 文本分析不准 | v0 保守匹配；后续升级 NLP |
| 性能影响 | 异步执行；不阻塞流式输出 |
| 中英文混合 | 双语模式匹配 |

---

## 12. 依赖

- M0: Hive 数据模型（RpEntryBlob, RpEvidenceRef）
- M1: RpMemoryReader, RpPackedContext

---

## 13. 进度追踪

| 任务 | 状态 | 完成日期 |
|------|------|----------|
| Spec 文档 | ✅ 完成 | 2026-01-18 |
| 多模型 Code Review | ✅ 完成 | 2026-01-19 |
| rp_validator.dart | ⏳ 待开始 | - |
| rp_violation.dart | ⏳ 待开始 | - |
| rp_validation_context.dart | ⏳ 待开始 | - |
| appearance_validator.dart | ⏳ 待开始 | - |
| state_validator.dart | ⏳ 待开始 | - |
| presence_validator.dart | ⏳ 待开始 | - |
| rp_consistency_gate.dart | ⏳ 待开始 | - |
| streaming.dart 集成 | ⏳ 待开始 | - |
| 单元测试 | ⏳ 待开始 | - |

---

## 14. 置信度与降级策略 [v1.1 新增]

> 来源: Codex 架构评审建议

### 14.1 置信度机制

每个 `RpViolation` 携带 `confidence` 字段（0.0 ~ 1.0），仅当 `confidence >= 阈值` 时生成 Proposal。

**置信度计算因素**：
- 关键词精确匹配 vs 模糊匹配
- 上下文语义确定性
- 证据链完整度

### 14.2 降级策略

| 策略 | 触发条件 | 行为 |
|------|----------|------|
| **用户反馈降级** | 用户连续 3 次驳回同类型 Proposal | 该 Validator 临时禁用 24 小时 |
| **误报率降级** | 单 Session 某 Validator 误报 > 5 次 | 动态提升该 Validator 置信度阈值 +20% |
| **全局禁用** | 用户在设置中关闭 | 完全跳过 ConsistencyGate |
| **静默模式** | 误报率过高时自动触发 | 仅记录日志，不生成 Proposal |

```dart
/// 降级策略配置
class RpGateDegradationPolicy {
  /// 每种 Validator 的用户驳回计数
  final Map<String, int> dismissCount;

  /// 临时禁用的 Validator（带过期时间）
  final Map<String, DateTime> temporarilyDisabled;

  /// 动态置信度调整（阈值提升百分比）
  final Map<String, double> confidenceBoost;

  /// 是否进入静默模式
  final bool silentMode;
}
```

---

## 15. 验证时机 [v1.1 新增]

> 来源: Codex 架构评审建议

### 15.1 v0 策略: onStreamEnd

**验证时机**: 仅在流式输出**完全结束**后执行一次验证。

```dart
enum ValidationTiming {
  onStreamEnd,    // v0: 流式结束后（推荐）
  onChunkFlush,   // v1 考虑: 每次 chunk 刷新
}
```

**原因**：
- 避免中途误判（句子未完成时外观描述可能不完整）
- 降低性能开销
- 简化实现复杂度

### 15.2 超长输出处理

当输出超过 `maxValidationLength`（默认 5000 字符）时：

```dart
/// 超长输出采样验证策略
String sampleForValidation(String text, {int maxLength = 5000}) {
  if (text.length <= maxLength) return text;

  // 采样前 2000 + 后 2000 字符
  final head = text.substring(0, 2000);
  final tail = text.substring(text.length - 2000);
  return '$head\n...[省略中间内容]...\n$tail';
}
```

---

## 16. UI/UX 设计 [v1.1 新增]

> 来源: 前端 UX 视角评审建议

### 16.1 通知呈现策略

**核心原则**: 不打断角色扮演沉浸感

| Severity | 桌面端 | 移动端 |
|----------|--------|--------|
| error | 侧边栏面板 + Toast | 内联消息 + 角标 |
| warn | 内联标记 + Toast | 内联消息 |
| info | 无显式通知 | 无显式通知 |

### 16.2 多违规聚合

```
┌───────────────────────────────────────────────────────┐
│  ⚠ 检测到 3 处不一致                          [收起] │
├───────────────────────────────────────────────────────┤
│  🔴 外观不一致: 发色 黑→金                           │
│  🟡 物品不存在: 魔法杖                               │
│  🟡 角色不在场: 鲍勃                                 │
├───────────────────────────────────────────────────────┤
│  [全部忽略]  [全部应用建议]  [逐条审核]              │
└───────────────────────────────────────────────────────┘
```

### 16.3 响应式断点

| 设备 | 断点 | 呈现方式 |
|------|------|----------|
| Mobile | < 640px | 内联消息式（作为聊天消息出现） |
| Tablet | 640px - 1023px | 底部抽屉（半屏高度） |
| Desktop | >= 1024px | 侧边栏面板 |

### 16.4 用户设置项

```dart
/// 一致性检测用户偏好
class RpConsistencyPreferences {
  bool enabled;                    // 总开关
  Map<String, bool> validators;    // 各检测类型开关
  NotificationLevel notifyLevel;   // 通知级别
}

enum NotificationLevel {
  always,      // 始终通知
  errorOnly,   // 仅错误级别
  silent,      // 静默模式（仅记录日志）
}
```

### 16.5 期望 vs 实际对比

**双列对比卡片**:
```
┌──────────────────────────┬──────────────────────────┐
│  📋 设定值               │  📝 输出内容             │
├──────────────────────────┼──────────────────────────┤
│  发色: 黑色              │  \"她甩了甩金色的长发\"   │
│  [角色卡: 艾拉]          │            ^^^^          │
└──────────────────────────┴──────────────────────────┘
```

---

## 17. 多模型审查记录 [v1.1 新增]

### 17.1 Codex 架构评审 (2026-01-19)

**评分**: 架构清晰度 8/10, 容错能力 5/10 → 已优化

**采纳建议**:
- ✅ P0: 在 `RpViolation` 中增加 `confidence` 字段
- ✅ P0: 明确验证时机为 `onStreamEnd`（v0）
- ✅ P0: 补充降级策略章节
- ⏳ P1: 增加 `GenderValidator` 到 Light 分类（实现阶段添加）
- ⏳ P1: 完善同义词映射表（实现阶段添加）

### 17.2 前端 UX 评审 (2026-01-19)

**评估**: 后端设计扎实，UI/UX 层需补充

**采纳建议**:
- ✅ P0: 违规通知呈现方式
- ✅ P0: 多违规聚合 UI
- ✅ P0: 移动端适配方案
- ✅ P1: 用户禁用设置设计
- ✅ P1: 期望 vs 实际对比展示

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.1.0 | 2026-01-19 | 根据多模型审查添加: confidence 字段、降级策略、验证时机、UI/UX 设计章节 |
| 1.0.0 | 2026-01-18 | 初版 Spec，基于设计文档和框架调研 |
