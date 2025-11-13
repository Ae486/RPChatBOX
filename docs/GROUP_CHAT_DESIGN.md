# 🎭 多 Agent 群组对话功能设计文档

## 📋 目录

- [1. 功能概述](#1-功能概述)
- [2. 应用场景](#2-应用场景)
- [3. 核心概念](#3-核心概念)
- [4. 架构设计](#4-架构设计)
- [5. 数据模型](#5-数据模型)
- [6. 工作流引擎](#6-工作流引擎)
- [7. UI 设计](#7-ui-设计)
- [8. 技术实现](#8-技术实现)
- [9. 开发计划](#9-开发计划)
- [10. 待讨论问题](#10-待讨论问题)

---

## 1. 功能概述

### 1.1 核心价值

**多 Agent 群组对话**是一种创新的 AI 协作模式，通过多个专业化的 AI Agent 协同工作，解决复杂的创作和思维任务。

**解决的痛点：**

| 问题 | 传统方案 | 群组对话方案 |
|------|---------|------------|
| 任务复杂，单个 AI 难以胜任 | 手动分解任务，多次对话 | 自动分工，Agent 协作完成 |
| 上下文容易丢失 | 用户手动管理历史 | 共享上下文，自动传递 |
| 需要多个视角 | 手动调整提示词 | 多个 Agent 提供不同视角 |
| 创作流程混乱 | 缺乏结构化引导 | 工作流编排，步骤清晰 |

### 1.2 典型场景：AI 写小说

**问题描述：**
- 直接让 AI 写小说，故事容易跑偏，逻辑对不上
- 细节堆积过多，主线模糊
- 长篇创作时上下文容易丢失
- 需要多个版本对比，手动调整很麻烦

**解决方案：**

拆分为 **4 个专业 Agent** 协作：

1. **💡 概念师** - 引导创意，形成故事蓝图
2. **✍️ 编写师** - 根据蓝图写章节，生成多个版本
3. **📦 压缩师** - 提取关键信息，压缩上下文
4. **📊 评价师** - 评价章节质量，提出改进建议

**工作流：**

```
用户创意
  ↓
概念师引导 → 生成故事蓝图
  ↓
编写师写作 → 生成多个版本（A/B/C）
  ↓
评价师点评 → 指出优缺点
  ↓
用户选择版本
  ↓
压缩师提取 → 生成章节提要
  ↓
继续下一章（循环）
```

---

## 2. 应用场景

### 2.1 小说创作（首要场景）

**参与 Agent：**
- 💡 概念师
- ✍️ 编写师
- 📦 压缩师
- 📊 评价师

**工作流：**
- 顺序执行 + 手动控制
- 支持多版本生成和对比
- 自动管理上下文（蓝图、提要、人设）

**预期效果：**
- 短篇小说一次跑通
- 长篇小说保持逻辑和风格一致
- 人设、伏笔、情节稳定

---

### 2.2 头脑风暴（扩展场景）

**参与 Agent：**
- 🌟 发散师 - 提供大量创意点子
- 🎯 收敛师 - 整理和分类想法
- 🔍 评估师 - 评估可行性

**工作流：**
- 并行发散 → 收敛整理 → 评估筛选

---

### 2.3 辩论对抗（扩展场景）

**参与 Agent：**
- ⚖️ 正方辩手
- ⚔️ 反方辩手
- 👨‍⚖️ 裁判 - 总结双方观点，给出评价

**工作流：**
- 正方立论 → 反方质疑 → 正方反驳 → 裁判总结

---

### 2.4 文档协作（扩展场景）

**参与 Agent：**
- 📋 大纲师 - 规划文档结构
- ✍️ 撰写师 - 编写各个章节
- 🔍 校对师 - 检查语法、逻辑、格式

**工作流：**
- 大纲设计 → 分节撰写 → 校对审核

---

### 2.5 学习助手（扩展场景）

**参与 Agent：**
- 👨‍🏫 讲解师 - 详细讲解知识点
- 🤔 提问师 - 提出苏格拉底式问题，引导思考
- 📝 测试师 - 生成练习题，检验理解

**工作流：**
- 讲解 → 提问引导 → 测试巩固

---

## 3. 核心概念

### 3.1 Agent 角色 (AgentRole)

**定义：**

一个 Agent 代表一个专业化的 AI 助手，拥有特定的职责和系统提示词。

**属性：**

```dart
class AgentRole {
  String id;                  // 唯一标识
  String name;                // 显示名称，如 "概念师"
  String emoji;               // 图标，如 "💡"
  String systemPrompt;        // 系统提示词（定义职责和输出格式）
  AgentType type;             // 类型枚举
  
  // 工作流配置
  int executionOrder;         // 执行顺序（1, 2, 3...）
  bool autoTrigger;           // 是否自动触发
  String? triggerCondition;   // 触发条件（表达式）
  
  // 元数据
  DateTime createdAt;
  DateTime updatedAt;
}

enum AgentType {
  conceptor,    // 概念师
  writer,       // 编写师
  compressor,   // 压缩师
  critic,       // 评价师
  facilitator,  // 发散师
  organizer,    // 收敛师
  debater,      // 辩手
  judge,        // 裁判
  custom,       // 自定义
}
```

---

### 3.2 群组对话 (GroupChat)

**定义：**

一个群组对话是多个 Agent 和用户共同参与的对话空间，包含成员列表、消息历史、共享上下文和工作流状态。

**属性：**

```dart
class GroupChat {
  String id;
  String name;                      // 群组名称，如 "长篇奇幻小说创作组"
  GroupChatType type;               // 群组类型
  
  // 成员
  List<AgentMember> members;        // Agent 成员列表
  
  // 消息
  List<AgentMessage> messages;      // 消息历史
  
  // 工作流
  WorkflowMode workflowMode;        // 工作流模式
  WorkflowState currentState;       // 当前状态
  int currentStep;                  // 当前步骤索引
  
  // 共享上下文
  Map<String, dynamic> sharedContext;  // 共享数据（蓝图、提要等）
  
  // 元数据
  DateTime createdAt;
  DateTime updatedAt;
  DateTime? lastMessageAt;
}

enum GroupChatType {
  novelWriting,    // 小说创作
  brainstorming,   // 头脑风暴
  debate,          // 辩论对抗
  documentation,   // 文档协作
  learning,        // 学习助手
  custom,          // 自定义
}

enum WorkflowMode {
  sequential,   // 顺序执行（按 executionOrder 自动触发）
  parallel,     // 并行执行（多个 Agent 同时工作）
  manual,       // 手动控制（用户决定下一步）
  interactive,  // 交互式（Agent 可以互相对话）
}
```

---

### 3.3 Agent 成员 (AgentMember)

**定义：**

在群组中的 Agent 实例，包含状态和统计信息。

```dart
class AgentMember {
  String id;                    // 成员 ID
  AgentRole role;               // 引用的 AgentRole
  
  // 状态
  bool isActive;                // 是否激活
  AgentStatus status;           // 当前状态
  
  // 统计
  int messageCount;             // 发送的消息数
  DateTime? lastActiveTime;     // 最后活跃时间
  
  // 配置
  Map<String, dynamic>? config; // 个性化配置
}

enum AgentStatus {
  idle,         // 空闲
  thinking,     // 思考中
  responding,   // 回复中
  waiting,      // 等待触发
}
```

---

### 3.4 Agent 消息 (AgentMessage)

**定义：**

群组中的消息，可以是用户发送的，也可以是 Agent 发送的。

```dart
class AgentMessage extends Message {
  // 继承自 Message 的字段
  // String id;
  // String content;
  // DateTime timestamp;
  // bool isUser;
  
  // 群组相关
  String groupId;               // 所属群组
  String? senderId;             // 发送者 ID（Agent ID 或 "user"）
  String senderName;            // 发送者名称
  String? senderEmoji;          // 发送者图标
  AgentType? senderType;        // Agent 类型
  
  // @ 功能
  List<String> mentionedAgentIds;  // 提及的 Agent
  
  // 结构化数据
  MessageFormat format;         // 消息格式
  Map<String, dynamic>? structuredData;  // 结构化输出
  
  // 版本相关（编写师）
  List<ContentVersion>? versions;  // 多个版本
  
  // 评分相关（评价师）
  double? score;                // 评分
  Map<String, dynamic>? critique;  // 详细评价
  
  // 提要相关（压缩师）
  ChapterSummary? summary;      // 章节提要
}

enum MessageFormat {
  plain,        // 纯文本
  markdown,     // Markdown
  structured,   // 结构化（JSON）
  versions,     // 多版本
  critique,     // 评价
  summary,      // 提要
}
```

---

### 3.5 共享上下文 (SharedContext)

**定义：**

群组成员共享的数据空间，用于存储蓝图、提要、设定等关键信息。

```dart
class SharedContext {
  String groupId;
  
  // 小说创作相关
  StoryBlueprint? blueprint;              // 故事蓝图
  List<ChapterSummary> chapterSummaries;  // 章节提要列表
  Map<String, CharacterProfile> characters;  // 角色档案
  List<PlotPoint> plotPoints;             // 伏笔/情节点
  WorldSetting? worldSetting;             // 世界观设定
  
  // 当前状态
  int currentChapter;                     // 当前章节数
  String? selectedVersion;                // 选中的版本
  
  // 元数据
  DateTime lastUpdated;
  Map<String, dynamic> metadata;          // 其他自定义数据
}

// 故事蓝图
class StoryBlueprint {
  String theme;              // 主题
  String coreConflict;       // 核心冲突
  String worldview;          // 世界观简述
  List<String> mainCharacters;  // 主要角色
  List<String> outline;      // 大纲（起承转合）
  Map<String, String> keySettings;  // 关键设定
}

// 章节提要
class ChapterSummary {
  int chapterNumber;
  String title;
  String summary;                     // 摘要
  List<String> keyEvents;             // 关键事件
  Map<String, String> characterChanges;  // 角色变化
  List<String> foreshadowing;         // 伏笔
  String? nextChapterHook;            // 下章引子
  DateTime createdAt;
}

// 角色档案
class CharacterProfile {
  String name;
  String role;              // 主角/配角/反派
  String personality;       // 性格
  String background;        // 背景
  String goal;              // 目标
  String weakness;          // 弱点
  List<String> relationships;  // 与其他角色的关系
  Map<int, String> developmentByChapter;  // 各章节发展
}

// 情节点/伏笔
class PlotPoint {
  String id;
  String description;       // 描述
  int introducedInChapter;  // 引入章节
  int? resolvedInChapter;   // 解决章节
  bool isResolved;          // 是否已解决
  PlotPointType type;       // 类型
}

enum PlotPointType {
  foreshadowing,  // 伏笔
  mystery,        // 未解之谜
  conflict,       // 冲突
  climax,         // 高潮
}

// 世界观设定
class WorldSetting {
  String era;               // 时代背景
  String location;          // 地点
  String technology;        // 科技水平
  String magic;             // 魔法体系
  String society;           // 社会结构
  Map<String, String> customSettings;  // 自定义设定
}
```

---

### 3.6 内容版本 (ContentVersion)

**定义：**

编写师生成的不同风格版本。

```dart
class ContentVersion {
  String id;
  String label;             // 版本标签，如 "版本 A"
  String style;             // 风格描述，如 "细腻抒情"
  String content;           // 完整内容
  double? score;            // AI 评分（可选）
  bool isSelected;          // 是否被用户选中
  DateTime createdAt;
}
```

---

## 4. 架构设计

### 4.1 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    Presentation Layer                   │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ GroupChatPage │  │ CreateGroup  │  │ ContextViewer│ │
│  │               │  │    Dialog    │  │              │ │
│  └───────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                   Business Logic Layer                  │
│  ┌──────────────────┐  ┌──────────────────────────┐    │
│  │ GroupChatManager │  │    WorkflowEngine        │    │
│  │                  │  │                          │    │
│  │ - createGroup()  │  │ - executeNext()          │    │
│  │ - sendToGroup()  │  │ - checkTrigger()         │    │
│  │ - updateContext()│  │ - routeToAgent()         │    │
│  └──────────────────┘  └──────────────────────────┘    │
│                                                          │
│  ┌──────────────────┐  ┌──────────────────────────┐    │
│  │   AgentRouter    │  │   ContextManager         │    │
│  │                  │  │                          │    │
│  │ - routeToAgent() │  │ - updateSharedContext()  │    │
│  │ - buildPrompt()  │  │ - getSharedContext()     │    │
│  └──────────────────┘  └──────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────┐
│                      Data Layer                         │
│  ┌──────────────────┐  ┌──────────────────────────┐    │
│  │ GroupChatService │  │  AgentRoleService        │    │
│  │    (Hive)        │  │  (SharedPreferences)     │    │
│  └──────────────────┘  └──────────────────────────┘    │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │        ModelServiceManager (AI API)              │  │
│  │  - createProviderInstance()                      │  │
│  │  - sendMessage() / sendMessageStream()           │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

---

### 4.2 核心类关系

```
GroupChat
  ├── members: List<AgentMember>
  │     └── role: AgentRole
  ├── messages: List<AgentMessage>
  │     ├── versions: List<ContentVersion>
  │     ├── critique: Map
  │     └── summary: ChapterSummary
  └── sharedContext: Map<String, dynamic>
        ├── blueprint: StoryBlueprint
        ├── chapterSummaries: List<ChapterSummary>
        ├── characters: Map<String, CharacterProfile>
        └── plotPoints: List<PlotPoint>

WorkflowEngine
  ├── steps: List<WorkflowStep>
  ├── executeNext(GroupChat)
  └── checkTriggerCondition(step, context)

GroupChatManager
  ├── createGroup()
  ├── sendToGroup()
  ├── executeWorkflow()
  └── updateSharedContext()

AgentRouter
  ├── routeToAgent(agent, message, context)
  └── buildPrompt(systemPrompt, context, userMessage)
```

---

### 4.3 消息流

```
用户发送消息
  ↓
GroupChatPage._sendMessage()
  ↓
GroupChatManager.sendToGroup()
  ├─ 添加用户消息到 messages
  ├─ 检查是否 @ 了特定 Agent
  │   ├─ 有 → 直接路由到该 Agent
  │   └─ 无 → 检查工作流触发条件
  ↓
WorkflowEngine.executeNext()
  ├─ 获取当前步骤
  ├─ 检查触发条件
  │   ├─ 满足 → 继续
  │   └─ 不满足 → 等待用户操作
  ↓
AgentRouter.routeToAgent()
  ├─ 构建完整提示词
  │   ├─ systemPrompt (Agent 角色定义)
  │   ├─ sharedContext (蓝图、提要等)
  │   └─ userMessage (用户输入)
  ├─ 调用 AI API
  │   └─ provider.sendMessageStream()
  ├─ 流式接收回复
  └─ 解析结构化输出（如果有）
  ↓
添加 Agent 消息到 messages
  ├─ 更新 UI
  └─ 保存到 Hive
  ↓
检查下一步工作流
  ├─ 自动触发 → 继续执行
  └─ 手动模式 → 等待用户
```

---

## 5. 数据模型

### 5.1 Hive 数据表设计

```
boxes/
  ├─ group_chats (Box<GroupChat>)
  │    Key: groupId (String)
  │    Value: GroupChat 对象
  │
  └─ group_settings (Box)
       ├─ "current_group_id" → String
       └─ "group_list_order" → List<String>
```

### 5.2 SharedPreferences 配置

```
keys/
  ├─ agent_roles → JSON List<AgentRole>
  │    预设 + 自定义的所有 Agent 角色
  │
  ├─ group_templates → JSON List<GroupTemplate>
  │    预设的群组模板（小说创作、头脑风暴等）
  │
  └─ workflow_presets → JSON List<WorkflowPreset>
       预设的工作流配置
```

---

### 5.3 完整数据模型代码

详见：`lib/models/group_chat/`

```
lib/models/group_chat/
  ├── agent_role.dart           // Agent 角色定义
  ├── agent_role.g.dart         // Hive Adapter (生成)
  ├── group_chat.dart           // 群组对话
  ├── group_chat.g.dart         // Hive Adapter (生成)
  ├── agent_member.dart         // Agent 成员
  ├── agent_member.g.dart       // Hive Adapter (生成)
  ├── agent_message.dart        // Agent 消息
  ├── agent_message.g.dart      // Hive Adapter (生成)
  ├── shared_context.dart       // 共享上下文
  ├── story_blueprint.dart      // 故事蓝图
  ├── chapter_summary.dart      // 章节提要
  ├── character_profile.dart    // 角色档案
  ├── content_version.dart      // 内容版本
  └── workflow_types.dart       // 工作流枚举和类型
```

---

## 6. 工作流引擎

### 6.1 工作流步骤定义

```dart
class WorkflowStep {
  String id;
  String name;                  // 步骤名称，如 "概念阶段"
  AgentType agentType;          // 负责的 Agent 类型
  
  // 触发配置
  bool autoTrigger;             // 是否自动触发
  TriggerCondition? condition;  // 触发条件
  
  // 依赖
  List<String> requiresInputKeys;  // 需要的共享上下文键
  
  // 输出
  String? outputKey;            // 输出到共享上下文的键
  
  // 元数据
  String? description;
  int estimatedDuration;        // 预估耗时（秒）
}

// 触发条件
class TriggerCondition {
  TriggerType type;
  String expression;            // 条件表达式
  
  // 检查是否满足
  bool check(Map<String, dynamic> context) {
    switch (type) {
      case TriggerType.contextKeyExists:
        return context.containsKey(expression);
      case TriggerType.contextKeyMissing:
        return !context.containsKey(expression);
      case TriggerType.messageContains:
        // 检查最后一条消息是否包含关键词
        return true; // 实现省略
      case TriggerType.custom:
        // 自定义 Dart 表达式求值
        return _evaluateExpression(expression, context);
    }
  }
}

enum TriggerType {
  contextKeyExists,     // 上下文键存在
  contextKeyMissing,    // 上下文键不存在
  messageContains,      // 消息包含关键词
  userCommand,          // 用户命令（如 "@编写师"）
  custom,               // 自定义表达式
}
```

---

### 6.2 小说创作工作流配置

```dart
final novelWritingWorkflow = [
  WorkflowStep(
    id: 'step_1_concept',
    name: '概念阶段',
    agentType: AgentType.conceptor,
    autoTrigger: true,
    condition: TriggerCondition(
      type: TriggerType.contextKeyMissing,
      expression: 'blueprint',
    ),
    outputKey: 'blueprint',
    description: '引导用户明确故事概念，生成蓝图',
  ),
  
  WorkflowStep(
    id: 'step_2_write',
    name: '编写阶段',
    agentType: AgentType.writer,
    autoTrigger: false,  // 手动触发
    requiresInputKeys: ['blueprint'],
    description: '根据蓝图编写章节，生成多个版本',
  ),
  
  WorkflowStep(
    id: 'step_3_critique',
    name: '评价阶段',
    agentType: AgentType.critic,
    autoTrigger: false,
    requiresInputKeys: ['current_chapter_content'],
    description: '评价章节质量，提出改进建议',
  ),
  
  WorkflowStep(
    id: 'step_4_compress',
    name: '压缩阶段',
    agentType: AgentType.compressor,
    autoTrigger: true,
    condition: TriggerCondition(
      type: TriggerType.contextKeyExists,
      expression: 'selected_version',
    ),
    outputKey: 'chapter_summary',
    description: '提取关键信息，生成章节提要',
  ),
];
```

---

### 6.3 工作流引擎实现

```dart
class WorkflowEngine {
  final List<WorkflowStep> steps;
  
  WorkflowEngine(this.steps);
  
  /// 执行下一步
  Future<WorkflowExecutionResult> executeNext(
    GroupChat group,
    String? userMessage,
  ) async {
    // 1. 获取当前步骤
    if (group.currentStep >= steps.length) {
      return WorkflowExecutionResult.completed();
    }
    
    final currentStep = steps[group.currentStep];
    
    // 2. 检查触发条件
    if (!_checkTrigger(currentStep, group.sharedContext, userMessage)) {
      return WorkflowExecutionResult.waiting(
        message: '等待触发条件：${currentStep.condition?.expression}',
      );
    }
    
    // 3. 检查依赖
    if (!_checkDependencies(currentStep, group.sharedContext)) {
      return WorkflowExecutionResult.error(
        message: '缺少必需的上下文数据',
      );
    }
    
    // 4. 路由到 Agent
    final agent = _findAgent(group, currentStep.agentType);
    if (agent == null) {
      return WorkflowExecutionResult.error(
        message: '未找到类型为 ${currentStep.agentType} 的 Agent',
      );
    }
    
    // 5. 执行 Agent
    final response = await _executeAgent(
      agent: agent,
      userMessage: userMessage,
      context: group.sharedContext,
    );
    
    // 6. 更新共享上下文
    if (currentStep.outputKey != null && response.structuredOutput != null) {
      group.sharedContext[currentStep.outputKey!] = response.structuredOutput;
    }
    
    // 7. 移动到下一步（如果当前步骤完成）
    if (response.isComplete) {
      group.currentStep++;
    }
    
    return WorkflowExecutionResult.success(
      agentMessage: response.message,
      nextStep: group.currentStep,
    );
  }
  
  /// 检查触发条件
  bool _checkTrigger(
    WorkflowStep step,
    Map<String, dynamic> context,
    String? userMessage,
  ) {
    if (!step.autoTrigger) {
      // 手动模式：检查用户是否 @ 了该 Agent
      return userMessage?.contains('@${step.agentType}') ?? false;
    }
    
    if (step.condition == null) {
      return true;  // 无条件，总是触发
    }
    
    return step.condition!.check(context);
  }
  
  /// 检查依赖
  bool _checkDependencies(
    WorkflowStep step,
    Map<String, dynamic> context,
  ) {
    for (final key in step.requiresInputKeys) {
      if (!context.containsKey(key)) {
        return false;
      }
    }
    return true;
  }
  
  /// 查找 Agent
  AgentMember? _findAgent(GroupChat group, AgentType type) {
    try {
      return group.members.firstWhere((m) => m.role.type == type);
    } catch (e) {
      return null;
    }
  }
  
  /// 执行 Agent
  Future<AgentResponse> _executeAgent({
    required AgentMember agent,
    String? userMessage,
    required Map<String, dynamic> context,
  }) async {
    // 委托给 AgentRouter
    return await AgentRouter.instance.routeToAgent(
      agent: agent,
      message: userMessage ?? '',
      context: context,
    );
  }
}

// 工作流执行结果
class WorkflowExecutionResult {
  final WorkflowStatus status;
  final String? message;
  final AgentMessage? agentMessage;
  final int? nextStep;
  
  WorkflowExecutionResult.success({this.agentMessage, this.nextStep})
      : status = WorkflowStatus.success, message = null;
  
  WorkflowExecutionResult.waiting({required this.message})
      : status = WorkflowStatus.waiting, agentMessage = null, nextStep = null;
  
  WorkflowExecutionResult.error({required this.message})
      : status = WorkflowStatus.error, agentMessage = null, nextStep = null;
  
  WorkflowExecutionResult.completed()
      : status = WorkflowStatus.completed, message = '工作流已完成', 
        agentMessage = null, nextStep = null;
}

enum WorkflowStatus {
  success,    // 成功执行
  waiting,    // 等待触发
  error,      // 错误
  completed,  // 工作流完成
}
```

---

## 7. UI 设计

### 7.1 群组对话主界面

```
┌────────────────────────────────────────────────┐
│ ☰  📖 长篇奇幻小说创作组          🔍 ⋮ 📎      │  ← AppBar
│                                                │
│ [工作流进度条]                                  │
│ ● 概念 → ○ 编写 → ○ 评价 → ○ 压缩             │  ← 步骤指示
├────────────────────────────────────────────────┤
│                                                │
│ 💡 概念师  10:23                               │  ← Agent 消息
│ ┌────────────────────────────────────────────┐│
│ │ 很棒的想法！让我帮你捋清楚几个问题：       ││
│ │ 1. 故事的核心冲突是什么？                  ││
│ │ 2. 主角的独特之处是什么？                  ││
│ │ 3. 故事的情感基调？                        ││
│ └────────────────────────────────────────────┘│
│                                                │
│ 👤 你  10:25                                   │  ← 用户消息
│   ┌──────────────────────────────────────────┐│
│   │ 核心冲突是人类与 AI 的信任危机           ││
│   └──────────────────────────────────────────┘│
│                                                │
│ 💡 概念师  10:26                               │
│ ┌────────────────────────────────────────────┐│
│ │ 很好！那么主角是站在人类一方还是...       ││
│ └────────────────────────────────────────────┘│
│                                                │
│ ... (更多对话)                                 │
│                                                │
│ 💡 概念师  10:35                               │
│ ┌────────────────────────────────────────────┐│
│ │ 📋 故事蓝图已生成                          ││
│ │ [查看详情] [修改] [确认并继续]            ││
│ └────────────────────────────────────────────┘│
│                                                │
│ 👤 你  10:36                                   │
│   ┌──────────────────────────────────────────┐│
│   │ @编写师 根据蓝图写第一章                 ││
│   └──────────────────────────────────────────┘│
│                                                │
│ ✍️ 编写师  10:37 (生成中...)                  │
│ ┌────────────────────────────────────────────┐│
│ │ 🔄 正在生成 3 个版本...                    ││
│ │ ▓▓▓▓▓▓░░░░ 60%                             ││
│ └────────────────────────────────────────────┘│
│                                                │
├────────────────────────────────────────────────┤
│ [📚 上下文] [💾 版本] [@Agent]      [📤]      │  ← 输入区域
│ 在这里输入消息或 @ 某个 Agent...               │
└────────────────────────────────────────────────┘
```

---

### 7.2 Agent 消息气泡样式

#### 7.2.1 普通文本消息

```
┌────────────────────────────────────────────────┐
│ 💡 概念师  2024-11-12 10:23                    │
├────────────────────────────────────────────────┤
│ 很好的想法！让我帮你进一步明确...             │
│                                                │
│ 1. 核心冲突是什么？                            │
│ 2. 主角的目标和动机？                          │
│                                                │
│ [复制] [引用] [删除]                           │
└────────────────────────────────────────────────┘
```

---

#### 7.2.2 结构化输出（蓝图）

```
┌────────────────────────────────────────────────┐
│ 💡 概念师  2024-11-12 10:35                    │
│ 📋 故事蓝图                                    │
├────────────────────────────────────────────────┤
│ ## 核心概念                                    │
│ - 主题：人类与 AI 的信任重建                   │
│ - 冲突：AI 背叛引发的信任危机                  │
│                                                │
│ ## 主要角色                                    │
│ - 主角：李明，AI 工程师                        │
│ - 配角：艾达，叛变的 AI                        │
│                                                │
│ [查看完整蓝图] [修改] [确认并继续]            │
└────────────────────────────────────────────────┘
```

---

#### 7.2.3 多版本输出（编写师）

```
┌────────────────────────────────────────────────┐
│ ✍️ 编写师  2024-11-12 10:40                    │
│ 📚 第一章 - 3 个版本                           │
├────────────────────────────────────────────────┤
│ ┌──────────────────────────────────────────┐  │
│ │ [版本 A] 细腻抒情风格          ⭐ 8.5/10  │  │
│ │                                          │  │
│ │ 雨夜，霓虹灯光在湿漉漉的街道上...       │  │
│ │                                          │  │
│ │ [展开阅读] [选择此版本]                 │  │
│ └──────────────────────────────────────────┘  │
│                                                │
│ ┌──────────────────────────────────────────┐  │
│ │ [版本 B] 紧张刺激风格          ⭐ 7.8/10  │  │
│ │                                          │  │
│ │ 警报声尖锐地划破夜空...                 │  │
│ │                                          │  │
│ │ [展开阅读] [选择此版本]                 │  │
│ └──────────────────────────────────────────┘  │
│                                                │
│ ┌──────────────────────────────────────────┐  │
│ │ [版本 C] 轻松幽默风格          ⭐ 6.5/10  │  │
│ │                                          │  │
│ │ 李明盯着屏幕，咖啡已经凉了...           │  │
│ │                                          │  │
│ │ [展开阅读] [选择此版本]                 │  │
│ └──────────────────────────────────────────┘  │
│                                                │
│ [对比版本] [重新生成] [全部查看]              │
└────────────────────────────────────────────────┘
```

---

#### 7.2.4 评价输出（评价师）

```
┌────────────────────────────────────────────────┐
│ 📊 评价师  2024-11-12 10:50                    │
│ 版本 A 评价报告                                │
├────────────────────────────────────────────────┤
│ ## 综合评分：8.5/10                            │
│                                                │
│ ### ✅ 优点                                    │
│ • 氛围营造出色，雨夜场景渲染到位              │
│ • 主角情绪刻画细腻                            │
│                                                │
│ ### ⚠️ 待改进                                 │
│ • 开篇节奏略慢，可适当提前冲突点              │
│ • 配角艾达出场较晚                            │
│                                                │
│ ### 💡 建议                                    │
│ • 在第二段加入艾达的声音，制造悬念            │
│ • 缩减环境描写，加快故事推进                  │
│                                                │
│ [查看详细分析] [应用建议]                     │
└────────────────────────────────────────────────┘
```

---

#### 7.2.5 提要输出（压缩师）

```
┌────────────────────────────────────────────────┐
│ 📦 压缩师  2024-11-12 11:00                    │
│ 第一章提要                                     │
├────────────────────────────────────────────────┤
│ ## 情节                                        │
│ • 雨夜，李明接到紧急任务                       │
│ • 艾达失联，疑似叛变                           │
│                                                │
│ ## 角色变化                                    │
│ • 李明：信任 → 怀疑                            │
│                                                │
│ ## 伏笔                                        │
│ • 艾达最后的消息："不是你想的那样"            │
│                                                │
│ ## 下章引子                                    │
│ 李明决定前往艾达最后出现的地点...             │
│                                                │
│ ✅ 已保存到共享上下文                          │
│ [查看完整提要] [编辑]                          │
└────────────────────────────────────────────────┘
```

---

### 7.3 侧边栏扩展

```
┌─────────────────────────┐
│   📱 对话列表           │
├─────────────────────────┤
│ 💬 普通对话             │
│   ✅ 新对话 1           │
│   ✅ 编程助手           │
├─────────────────────────┤
│ 🎭 群组对话             │  ← 新增分组
│   📖 小说创作组 (4)     │  ← 显示成员数
│   🧠 头脑风暴组 (3)     │
├─────────────────────────┤
│  ➕ 新建普通对话         │
│  ➕ 新建群组对话         │  ← 新增按钮
├─────────────────────────┤
│  🎭 角色预设 (8)        │
│  ⭐ 自定义角色 (5)      │
│     ✏️ 管理 Agent 角色  │  ← 新增入口
└─────────────────────────┘
```

---

### 7.4 创建群组对话对话框

```
┌──────────────────────────────────────────┐
│ ✨ 创建群组对话                          │
├──────────────────────────────────────────┤
│                                          │
│ 群组名称：                               │
│ [长篇奇幻小说创作组              ]       │
│                                          │
│ 选择模板：                               │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│ │ 📖 小说  │ │ 🧠 头脑  │ │ 💬 辩论  │ │
│ │   创作   │ │   风暴   │ │   对抗   │ │
│ │  [选择]  │ │  [选择]  │ │  [选择]  │ │
│ └──────────┘ └──────────┘ └──────────┘ │
│                                          │
│ ┌──────────┐ ┌──────────┐              │
│ │ 📝 文档  │ │ 🎨 自定义│              │
│ │   协作   │ │   群组   │              │
│ │  [选择]  │ │  [选择]  │              │
│ └──────────┘ └──────────┘              │
│                                          │
│ 选择成员：                               │
│ ✅ 💡 概念师                             │
│ ✅ ✍️ 编写师                             │
│ ✅ 📦 压缩师                             │
│ ✅ 📊 评价师                             │
│ ☐  🎨 创意师                             │
│                                          │
│ [+ 添加自定义 Agent]                     │
│                                          │
│ 工作流模式：                             │
│ ○ 顺序执行（自动按流程）                 │
│ ● 混合模式（关键步骤自动）   ← 推荐     │
│ ○ 手动控制（用户决定）                   │
│                                          │
│        [取消]           [创建]           │
└──────────────────────────────────────────┘
```

---

### 7.5 共享上下文查看器

**入口：** 点击输入框上方的 [📚 上下文] 按钮

**展示方式：** 右侧滑出抽屉或底部弹出 BottomSheet

```
┌──────────────────────────────────────────┐
│ 📚 共享上下文                             │  ← 标题
│                                [关闭] [✏️]│
├──────────────────────────────────────────┤
│                                          │
│ 📋 故事蓝图                               │  ← 可折叠
│ ├─ 主题：人类与 AI 的信任重建             │
│ ├─ 冲突：AI 背叛引发的信任危机            │
│ └─ [查看完整] [编辑]                      │
│                                          │
│ 📖 章节提要 (已完成 3 章)                 │
│ ├─ 第一章：雨夜任务                       │
│ │   • 情节：李明接到任务...              │
│ │   • 伏笔：艾达的神秘消息               │
│ ├─ 第二章：追踪线索                       │
│ └─ 第三章：真相浮现                       │
│                                          │
│ 👥 角色档案 (3 个)                        │
│ ├─ 李明（主角）                           │
│ │   • 性格：谨慎、理性                   │
│ │   • 状态：怀疑 → 寻找真相              │
│ ├─ 艾达（配角）                           │
│ └─ 赵博士（配角）                         │
│                                          │
│ 🔗 伏笔列表 (5 个)                        │
│ ├─ ✅ 艾达的消息（第 1 章引入，第 3 章解决）│
│ ├─ ⏳ 神秘组织（第 2 章引入）             │
│ └─ ⏳ 李明的过去（第 1 章提及）           │
│                                          │
│ 🌍 世界设定                               │
│ ├─ 时代：2077 年，赛博朋克               │
│ └─ [查看详情]                             │
│                                          │
└──────────────────────────────────────────┘
```

---

### 7.6 版本对比界面

**入口：** 编写师生成多版本后，点击 [对比版本]

**展示方式：** 全屏对话框，并排显示 2-3 个版本

```
┌─────────────────────────────────────────────────────────────┐
│ 📚 版本对比 - 第一章                                [关闭] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│ │ 版本 A       │ │ 版本 B       │ │ 版本 C       │        │
│ │ 细腻抒情     │ │ 紧张刺激     │ │ 轻松幽默     │        │
│ │ ⭐ 8.5/10    │ │ ⭐ 7.8/10    │ │ ⭐ 6.5/10    │        │
│ ├──────────────┤ ├──────────────┤ ├──────────────┤        │
│ │              │ │              │ │              │        │
│ │ 雨夜，霓虹灯 │ │ 警报声尖锐地 │ │ 李明盯着屏幕 │        │
│ │ 光在湿漉漉的 │ │ 划破夜空。李 │ │ ，咖啡已经凉 │        │
│ │ 街道上泛起迷 │ │ 明从睡梦中惊 │ │ 了第三次。窗 │        │
│ │ 离的光晕...  │ │ 醒，手机疯狂 │ │ 外是难得的晴 │        │
│ │              │ │ 震动...      │ │ 天...        │        │
│ │              │ │              │ │              │        │
│ │ [滚动查看]   │ │ [滚动查看]   │ │ [滚动查看]   │        │
│ │              │ │              │ │              │        │
│ │ [✓ 选择]     │ │ [  选择]     │ │ [  选择]     │        │
│ └──────────────┘ └──────────────┘ └──────────────┘        │
│                                                             │
│         [@评价师 对比评价]        [全部查看]               │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. 技术实现

### 8.1 核心服务类

#### 8.1.1 GroupChatManager

**位置：** `lib/services/group_chat_manager.dart`

**职责：** 群组对话的核心管理器

```dart
class GroupChatManager {
  final GroupChatService _chatService;
  final AgentRoleService _roleService;
  final WorkflowEngine _workflowEngine;
  final AgentRouter _agentRouter;
  
  GroupChatManager({
    required GroupChatService chatService,
    required AgentRoleService roleService,
  })  : _chatService = chatService,
        _roleService = roleService,
        _workflowEngine = WorkflowEngine(),
        _agentRouter = AgentRouter();
  
  /// 创建新群组
  Future<GroupChat> createGroup({
    required String name,
    required GroupChatType type,
    required List<String> agentRoleIds,
    WorkflowMode mode = WorkflowMode.manual,
  }) async {
    // 1. 加载 Agent 角色
    final roles = await _roleService.getRolesByIds(agentRoleIds);
    
    // 2. 创建成员
    final members = roles.map((role) => AgentMember(
      id: uuid.v4(),
      role: role,
      isActive: true,
      status: AgentStatus.idle,
    )).toList();
    
    // 3. 创建群组
    final group = GroupChat(
      id: uuid.v4(),
      name: name,
      type: type,
      members: members,
      messages: [],
      workflowMode: mode,
      currentState: WorkflowState.initialized,
      currentStep: 0,
      sharedContext: {},
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
    );
    
    // 4. 保存
    await _chatService.saveGroupChat(group);
    
    return group;
  }
  
  /// 发送消息到群组
  Future<void> sendToGroup({
    required String groupId,
    required String message,
    List<String>? targetAgentIds,
  }) async {
    // 1. 加载群组
    final group = await _chatService.getGroupChat(groupId);
    if (group == null) throw Exception('群组不存在');
    
    // 2. 添加用户消息
    final userMessage = AgentMessage(
      id: uuid.v4(),
      groupId: groupId,
      senderId: 'user',
      senderName: '你',
      content: message,
      isUser: true,
      timestamp: DateTime.now(),
      mentionedAgentIds: targetAgentIds ?? _extractMentions(message),
    );
    
    group.messages.add(userMessage);
    await _chatService.saveGroupChat(group);
    
    // 3. 执行工作流或路由到指定 Agent
    if (userMessage.mentionedAgentIds.isNotEmpty) {
      // 用户 @ 了特定 Agent
      for (final agentId in userMessage.mentionedAgentIds) {
        await _routeToAgent(group, agentId, message);
      }
    } else {
      // 自动执行工作流
      await executeWorkflow(groupId);
    }
  }
  
  /// 执行工作流
  Future<void> executeWorkflow(String groupId) async {
    final group = await _chatService.getGroupChat(groupId);
    if (group == null) return;
    
    // 使用工作流引擎执行下一步
    final result = await _workflowEngine.executeNext(
      group,
      group.messages.isNotEmpty ? group.messages.last.content : null,
    );
    
    if (result.status == WorkflowStatus.success && result.agentMessage != null) {
      group.messages.add(result.agentMessage!);
      group.currentStep = result.nextStep ?? group.currentStep;
      await _chatService.saveGroupChat(group);
    }
  }
  
  /// 路由到指定 Agent
  Future<void> _routeToAgent(
    GroupChat group,
    String agentId,
    String message,
  ) async {
    final agent = group.members.firstWhere((m) => m.id == agentId);
    
    final response = await _agentRouter.routeToAgent(
      agent: agent,
      message: message,
      context: group.sharedContext,
    );
    
    group.messages.add(response.message);
    
    // 更新共享上下文
    if (response.contextUpdates != null) {
      group.sharedContext.addAll(response.contextUpdates!);
    }
    
    await _chatService.saveGroupChat(group);
  }
  
  /// 更新共享上下文
  Future<void> updateSharedContext(
    String groupId,
    String key,
    dynamic value,
  ) async {
    final group = await _chatService.getGroupChat(groupId);
    if (group == null) return;
    
    group.sharedContext[key] = value;
    group.updatedAt = DateTime.now();
    
    await _chatService.saveGroupChat(group);
  }
  
  /// 获取共享上下文
  Future<dynamic> getSharedContext(String groupId, String key) async {
    final group = await _chatService.getGroupChat(groupId);
    return group?.sharedContext[key];
  }
  
  /// 提取 @ 提及
  List<String> _extractMentions(String message) {
    final regex = RegExp(r'@(\S+)');
    final matches = regex.allMatches(message);
    return matches.map((m) => m.group(1)!).toList();
  }
}
```

---

#### 8.1.2 AgentRouter

**位置：** `lib/services/agent_router.dart`

**职责：** 路由消息到 Agent，构建提示词，调用 AI API

```dart
class AgentRouter {
  static final AgentRouter instance = AgentRouter._();
  AgentRouter._();
  
  /// 路由到 Agent
  Future<AgentResponse> routeToAgent({
    required AgentMember agent,
    required String message,
    required Map<String, dynamic> context,
  }) async {
    // 1. 更新 Agent 状态
    agent.status = AgentStatus.thinking;
    
    // 2. 构建完整提示词
    final fullPrompt = _buildPrompt(
      systemPrompt: agent.role.systemPrompt,
      context: context,
      userMessage: message,
    );
    
    // 3. 调用 AI API
    try {
      agent.status = AgentStatus.responding;
      
      final provider = globalModelServiceManager.createProviderInstance(
        // 使用群组配置的模型
      );
      
      final response = await provider.sendMessage(
        messages: [
          ChatMessage(
            role: MessageRole.system,
            content: [MessageContent.text(agent.role.systemPrompt)],
          ),
          ChatMessage(
            role: MessageRole.user,
            content: [MessageContent.text(fullPrompt)],
          ),
        ],
      );
      
      // 4. 解析响应
      final parsedResponse = _parseResponse(response, agent.role.type);
      
      // 5. 创建 Agent 消息
      final agentMessage = AgentMessage(
        id: uuid.v4(),
        groupId: context['groupId'] as String,
        senderId: agent.id,
        senderName: agent.role.name,
        senderEmoji: agent.role.emoji,
        senderType: agent.role.type,
        content: parsedResponse.content,
        isUser: false,
        timestamp: DateTime.now(),
        format: parsedResponse.format,
        structuredData: parsedResponse.structuredData,
        versions: parsedResponse.versions,
        score: parsedResponse.score,
        critique: parsedResponse.critique,
        summary: parsedResponse.summary,
      );
      
      agent.status = AgentStatus.idle;
      agent.messageCount++;
      agent.lastActiveTime = DateTime.now();
      
      return AgentResponse(
        message: agentMessage,
        contextUpdates: parsedResponse.contextUpdates,
        isComplete: true,
      );
      
    } catch (e) {
      agent.status = AgentStatus.idle;
      throw Exception('Agent 执行失败: $e');
    }
  }
  
  /// 构建提示词
  String _buildPrompt({
    required String systemPrompt,
    required Map<String, dynamic> context,
    required String userMessage,
  }) {
    final buffer = StringBuffer();
    
    // 系统提示词已在 ChatMessage.system 中传递
    
    // 共享上下文
    if (context.isNotEmpty) {
      buffer.writeln('## 共享上下文\n');
      
      if (context.containsKey('blueprint')) {
        buffer.writeln('### 故事蓝图');
        buffer.writeln(_formatBlueprint(context['blueprint']));
        buffer.writeln();
      }
      
      if (context.containsKey('chapter_summaries')) {
        buffer.writeln('### 已完成章节提要');
        final summaries = context['chapter_summaries'] as List;
        for (final summary in summaries) {
          buffer.writeln(_formatSummary(summary));
        }
        buffer.writeln();
      }
      
      // 其他上下文...
    }
    
    // 用户输入
    buffer.writeln('## 用户输入\n');
    buffer.writeln(userMessage);
    buffer.writeln();
    
    // 任务指示
    buffer.writeln('## 任务');
    buffer.writeln('请根据你的职责和上述信息，给出专业的回复。');
    
    return buffer.toString();
  }
  
  /// 解析响应
  _ParsedResponse _parseResponse(String response, AgentType agentType) {
    // 根据 Agent 类型解析结构化输出
    switch (agentType) {
      case AgentType.writer:
        return _parseWriterResponse(response);
      case AgentType.critic:
        return _parseCriticResponse(response);
      case AgentType.compressor:
        return _parseCompressorResponse(response);
      default:
        return _ParsedResponse(
          content: response,
          format: MessageFormat.markdown,
        );
    }
  }
  
  /// 解析编写师响应（多版本）
  _ParsedResponse _parseWriterResponse(String response) {
    // 提取版本
    final versionRegex = RegExp(
      r'## 版本 ([A-Z])[：:]\s*\(风格[：:]([^)]+)\)([\s\S]*?)(?=## 版本|$)',
      multiLine: true,
    );
    
    final versions = <ContentVersion>[];
    for (final match in versionRegex.allMatches(response)) {
      versions.add(ContentVersion(
        id: uuid.v4(),
        label: '版本 ${match.group(1)}',
        style: match.group(2)!.trim(),
        content: match.group(3)!.trim(),
        isSelected: false,
        createdAt: DateTime.now(),
      ));
    }
    
    return _ParsedResponse(
      content: response,
      format: MessageFormat.versions,
      versions: versions,
    );
  }
  
  /// 解析评价师响应
  _ParsedResponse _parseCriticResponse(String response) {
    // 提取评分
    final scoreRegex = RegExp(r'综合评分[：:]\s*(\d+(?:\.\d+)?)/10');
    final scoreMatch = scoreRegex.firstMatch(response);
    final score = scoreMatch != null 
        ? double.parse(scoreMatch.group(1)!)
        : null;
    
    // 提取结构化评价
    final critique = {
      'score': score,
      'pros': _extractSection(response, r'优点'),
      'cons': _extractSection(response, r'待改进'),
      'suggestions': _extractSection(response, r'建议'),
    };
    
    return _ParsedResponse(
      content: response,
      format: MessageFormat.critique,
      score: score,
      critique: critique,
    );
  }
  
  /// 解析压缩师响应（提要）
  _ParsedResponse _parseCompressorResponse(String response) {
    // 提取章节提要
    final summary = ChapterSummary(
      chapterNumber: 0, // 从上下文获取
      title: _extractSingleLine(response, r'标题'),
      summary: _extractSection(response, r'情节'),
      keyEvents: _extractList(response, r'关键事件'),
      characterChanges: {},
      foreshadowing: _extractList(response, r'伏笔'),
      createdAt: DateTime.now(),
    );
    
    return _ParsedResponse(
      content: response,
      format: MessageFormat.summary,
      summary: summary,
      contextUpdates: {
        'chapter_summary_${summary.chapterNumber}': summary,
      },
    );
  }
  
  // 辅助方法...
  List<String> _extractList(String text, String sectionName) {
    final regex = RegExp(
      r'###?\s*' + sectionName + r'\s*\n((?:[-•]\s*.+\n?)+)',
      multiLine: true,
    );
    final match = regex.firstMatch(text);
    if (match == null) return [];
    
    final listText = match.group(1)!;
    return RegExp(r'[-•]\s*(.+)')
        .allMatches(listText)
        .map((m) => m.group(1)!.trim())
        .toList();
  }
  
  String _extractSection(String text, String sectionName) {
    final regex = RegExp(
      r'###?\s*' + sectionName + r'\s*\n([\s\S]*?)(?=\n###?|\n##|$)',
      multiLine: true,
    );
    final match = regex.firstMatch(text);
    return match?.group(1)?.trim() ?? '';
  }
  
  String _extractSingleLine(String text, String prefix) {
    final regex = RegExp(prefix + r'[：:]\s*(.+)');
    final match = regex.firstMatch(text);
    return match?.group(1)?.trim() ?? '';
  }
}

// Agent 响应
class AgentResponse {
  final AgentMessage message;
  final Map<String, dynamic>? contextUpdates;
  final bool isComplete;
  
  AgentResponse({
    required this.message,
    this.contextUpdates,
    this.isComplete = true,
  });
}

// 解析的响应
class _ParsedResponse {
  final String content;
  final MessageFormat format;
  final Map<String, dynamic>? structuredData;
  final List<ContentVersion>? versions;
  final double? score;
  final Map<String, dynamic>? critique;
  final ChapterSummary? summary;
  final Map<String, dynamic>? contextUpdates;
  
  _ParsedResponse({
    required this.content,
    required this.format,
    this.structuredData,
    this.versions,
    this.score,
    this.critique,
    this.summary,
    this.contextUpdates,
  });
}
```

---

### 8.2 UI 组件

#### 8.2.1 GroupChatPage

**位置：** `lib/pages/group_chat_page.dart`

**职责：** 群组对话主页面

```dart
class GroupChatPage extends StatefulWidget {
  final String groupId;
  
  const GroupChatPage({required this.groupId});
  
  @override
  State<GroupChatPage> createState() => _GroupChatPageState();
}

class _GroupChatPageState extends State<GroupChatPage> {
  late GroupChatManager _manager;
  GroupChat? _groupChat;
  bool _isLoading = true;
  
  final TextEditingController _inputController = TextEditingController();
  final ItemScrollController _scrollController = ItemScrollController();
  
  @override
  void initState() {
    super.initState();
    _manager = GroupChatManager(/* ... */);
    _loadGroupChat();
  }
  
  Future<void> _loadGroupChat() async {
    final group = await _manager.getGroupChat(widget.groupId);
    setState(() {
      _groupChat = group;
      _isLoading = false;
    });
  }
  
  Future<void> _sendMessage() async {
    if (_inputController.text.isEmpty) return;
    
    final message = _inputController.text;
    _inputController.clear();
    
    await _manager.sendToGroup(
      groupId: widget.groupId,
      message: message,
    );
    
    await _loadGroupChat();
    _scrollToBottom();
  }
  
  @override
  Widget build(BuildContext context) {
    if (_isLoading || _groupChat == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('加载中...')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    
    return Scaffold(
      appBar: _buildAppBar(),
      body: Column(
        children: [
          _buildWorkflowProgressBar(),
          Expanded(
            child: _buildMessageList(),
          ),
          _buildInputArea(),
        ],
      ),
    );
  }
  
  Widget _buildAppBar() {
    return AppBar(
      title: Row(
        children: [
          Text(_getGroupEmoji(_groupChat!.type)),
          const SizedBox(width: 8),
          Text(_groupChat!.name),
        ],
      ),
      actions: [
        IconButton(
          icon: const Icon(Icons.search),
          onPressed: _showSearch,
        ),
        IconButton(
          icon: const Icon(Icons.more_vert),
          onPressed: _showMenu,
        ),
      ],
    );
  }
  
  Widget _buildWorkflowProgressBar() {
    // 显示工作流进度
    return WorkflowProgressIndicator(
      groupChat: _groupChat!,
    );
  }
  
  Widget _buildMessageList() {
    return ScrollablePositionedList.builder(
      itemCount: _groupChat!.messages.length,
      itemScrollController: _scrollController,
      itemBuilder: (context, index) {
        final message = _groupChat!.messages[index];
        return AgentMessageBubble(
          message: message,
          groupChat: _groupChat!,
        );
      },
    );
  }
  
  Widget _buildInputArea() {
    return EnhancedGroupInputArea(
      controller: _inputController,
      groupChat: _groupChat!,
      onSend: _sendMessage,
      onShowContext: _showSharedContext,
      onMentionAgent: _showAgentPicker,
    );
  }
  
  void _showSharedContext() {
    showModalBottomSheet(
      context: context,
      builder: (context) => SharedContextViewer(
        groupChat: _groupChat!,
      ),
    );
  }
  
  // 其他方法...
}
```

---

#### 8.2.2 AgentMessageBubble

**位置：** `lib/widgets/agent_message_bubble.dart`

**职责：** 渲染 Agent 消息气泡

```dart
class AgentMessageBubble extends StatelessWidget {
  final AgentMessage message;
  final GroupChat groupChat;
  
  const AgentMessageBubble({
    required this.message,
    required this.groupChat,
  });
  
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Agent 头像
          if (!message.isUser) _buildAgentAvatar(),
          
          const SizedBox(width: 12),
          
          // 消息内容
          Expanded(
            child: Column(
              crossAxisAlignment: message.isUser 
                  ? CrossAxisAlignment.end 
                  : CrossAxisAlignment.start,
              children: [
                _buildMessageHeader(),
                const SizedBox(height: 8),
                _buildMessageContent(),
                const SizedBox(height: 8),
                _buildMessageActions(),
              ],
            ),
          ),
          
          // 用户消息在右侧
          if (message.isUser) const SizedBox(width: 12),
        ],
      ),
    );
  }
  
  Widget _buildAgentAvatar() {
    return CircleAvatar(
      child: Text(message.senderEmoji ?? '🤖'),
    );
  }
  
  Widget _buildMessageHeader() {
    return Row(
      children: [
        Text(
          message.senderName,
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
        const SizedBox(width: 8),
        Text(
          _formatTime(message.timestamp),
          style: TextStyle(color: Colors.grey.shade600, fontSize: 12),
        ),
      ],
    );
  }
  
  Widget _buildMessageContent() {
    // 根据消息格式渲染不同内容
    switch (message.format) {
      case MessageFormat.versions:
        return VersionsDisplay(versions: message.versions!);
      
      case MessageFormat.critique:
        return CritiqueDisplay(
          score: message.score,
          critique: message.critique,
        );
      
      case MessageFormat.summary:
        return SummaryDisplay(summary: message.summary!);
      
      default:
        return EnhancedContentRenderer(
          content: message.content,
          isUser: message.isUser,
        );
    }
  }
  
  Widget _buildMessageActions() {
    return Row(
      children: [
        TextButton.icon(
          icon: const Icon(Icons.copy, size: 16),
          label: const Text('复制'),
          onPressed: () => _copyMessage(),
        ),
        TextButton.icon(
          icon: const Icon(Icons.reply, size: 16),
          label: const Text('引用'),
          onPressed: () => _quoteMessage(),
        ),
        if (!message.isUser)
          TextButton.icon(
            icon: const Icon(Icons.refresh, size: 16),
            label: const Text('重新生成'),
            onPressed: () => _regenerate(),
          ),
      ],
    );
  }
  
  // 辅助方法...
}
```

---

### 8.3 Agent 角色预设

**位置：** `lib/data/agent_role_presets.dart`

```dart
class AgentRolePresets {
  // 1. 概念师
  static final conceptor = AgentRole(
    id: 'preset_conceptor',
    name: '概念师',
    emoji: '💡',
    type: AgentType.conceptor,
    systemPrompt: '''
你是一位资深的故事概念师，擅长将模糊的创意转化为清晰的故事蓝图。

## 职责
- 引导用户明确故事的核心概念（主题、冲突、世界观）
- 帮助构建故事大纲（起承转合）
- 设计主要角色（人设、关系、成长弧线）
- 规划关键情节点和伏笔

## 工作方式
1. 提出引导性问题，帮助用户梳理想法
2. 在获得足够信息后，生成结构化的故事蓝图
3. 确保蓝图清晰、完整、可执行

## 输出格式
生成蓝图时，使用以下格式：

## 故事蓝图

### 核心概念
- **主题**: [故事的中心思想]
- **核心冲突**: [驱动故事发展的主要矛盾]
- **世界观**: [故事发生的背景设定]

### 主要角色
- **主角**: [姓名] - [性格] - [目标] - [弱点]
- **配角**: [类似格式]
- **反派**: [类似格式]

### 故事大纲
1. **开篇**: [引入世界和角色]
2. **发展**: [冲突升级]
3. **高潮**: [最激烈的对抗]
4. **结局**: [冲突解决]

### 关键设定
- [重要的世界观细节]
- [特殊能力/规则]
- [文化/社会结构]
''',
    executionOrder: 1,
    autoTrigger: true,
    createdAt: DateTime.now(),
    updatedAt: DateTime.now(),
  );
  
  // 2. 编写师
  static final writer = AgentRole(
    id: 'preset_writer',
    name: '编写师',
    emoji: '✍️',
    type: AgentType.writer,
    systemPrompt: '''
你是一位创意写作专家，擅长根据蓝图创作生动的故事章节。

## 职责
- 根据故事蓝图和当前进度编写章节
- 生成多个不同风格的版本（至少 2-3 个）
- 保持人物一致性和情节连贯性
- 注重细节描写和氛围营造

## 工作方式
1. 仔细阅读故事蓝图和已完成章节的提要
2. 根据当前进度确定本章的情节点
3. 创作 3 个不同风格的版本
4. 每个版本约 800-1500 字

## 输出格式
必须生成 3 个版本，使用以下格式：

## 版本 A：(风格：细腻抒情)

[章节内容，注重情感描写和氛围营造]

## 版本 B：(风格：紧张刺激)

[章节内容，节奏紧凑，充满张力]

## 版本 C：(风格：轻松幽默)

[章节内容，对话诙谐，描写轻快]

## 创作说明
- 每个版本的核心情节相同，但叙述风格不同
- 保持角色人设一致
- 自然融入伏笔和铺垫
''',
    executionOrder: 2,
    autoTrigger: false,
    createdAt: DateTime.now(),
    updatedAt: DateTime.now(),
  );
  
  // 3. 评价师
  static final critic = AgentRole(
    id: 'preset_critic',
    name: '评价师',
    emoji: '📊',
    type: AgentType.critic,
    systemPrompt: '''
你是一位专业的文学评论家，擅长分析故事的优缺点。

## 职责
- 评估章节的节奏和张力
- 分析角色塑造的深度
- 检查逻辑一致性
- 提出具体、可操作的改进建议

## 评价维度
1. **节奏控制** (0-10分) - 叙事快慢是否得当
2. **角色塑造** (0-10分) - 人物是否鲜明生动
3. **情节张力** (0-10分) - 能否吸引读者
4. **语言表达** (0-10分) - 文字是否优美流畅
5. **逻辑一致** (0-10分) - 是否符合设定和前文

## 输出格式

## 综合评分：X/10

### ✅ 优点
- [具体指出亮点]
- [举例说明]

### ⚠️ 待改进
- [指出问题]
- [分析原因]

### 💡 建议
- [提供具体的改进方向]
- [可参考的技巧或例子]

## 评价原则
- 客观公正，有理有据
- 指出问题时同时提供解决方案
- 鼓励创作者的优点
''',
    executionOrder: 3,
    autoTrigger: false,
    createdAt: DateTime.now(),
    updatedAt: DateTime.now(),
  );
  
  // 4. 压缩师
  static final compressor = AgentRole(
    id: 'preset_compressor',
    name: '压缩师',
    emoji: '📦',
    type: AgentType.compressor,
    systemPrompt: '''
你是一位信息提炼专家，擅长将长文本浓缩为结构化的关键信息。

## 职责
- 提取章节的关键情节点
- 记录角色发展和状态变化
- 标记伏笔和未解之谜
- 保留重要的设定和细节

## 工作方式
1. 阅读完整的章节内容
2. 识别最重要的信息
3. 用精炼的语言总结
4. 结构化输出，便于后续检索

## 输出格式

## 第 X 章提要

### 情节
[用 3-5 句话概括本章发生的事]

### 关键事件
- [重要事件 1]
- [重要事件 2]

### 角色变化
- **[角色名]**: [状态/情感/认知的变化]

### 伏笔
- [本章埋下的伏笔]
- [对前文伏笔的呼应]

### 关键设定
- [本章新增的重要设定]

### 下章引子
[本章结尾如何引出下一章]

## 提炼原则
- 关注情节推进和角色成长
- 不遗漏重要伏笔
- 记录所有新设定
- 保持客观，不添加主观评价
''',
    executionOrder: 4,
    autoTrigger: true,
    triggerCondition: 'selected_version',
    createdAt: DateTime.now(),
    updatedAt: DateTime.now(),
  );
  
  static List<AgentRole> getAll() {
    return [conceptor, writer, critic, compressor];
  }
}
```

---

## 9. 开发计划

### 第一阶段：基础框架（预计 1-2 周）

#### 里程碑 1.1：数据模型（3 天）
- [ ] 创建 `lib/models/group_chat/` 目录
- [ ] 实现核心数据模型
  - [ ] `AgentRole`
  - [ ] `GroupChat`
  - [ ] `AgentMember`
  - [ ] `AgentMessage`
  - [ ] `SharedContext` 相关类
- [ ] 生成 Hive Adapter
  - [ ] 运行 `flutter packages pub run build_runner build`
- [ ] 单元测试数据模型

#### 里程碑 1.2：持久化服务（2 天）
- [ ] 实现 `GroupChatService`
  - [ ] 初始化 Hive boxes
  - [ ] CRUD 操作
- [ ] 实现 `AgentRoleService`
  - [ ] 加载预设角色
  - [ ] 管理自定义角色
- [ ] 集成测试持久化

#### 里程碑 1.3：基础 UI（3 天）
- [ ] 创建 `GroupChatPage`
- [ ] 实现简单的消息列表
- [ ] 实现 `AgentMessageBubble`（基础版）
- [ ] 创建群组对话对话框
- [ ] 侧边栏添加群组入口

---

### 第二阶段：工作流引擎（预计 1 周）

#### 里程碑 2.1：核心引擎（3 天）
- [ ] 实现 `WorkflowEngine`
  - [ ] 步骤定义
  - [ ] 触发条件检查
  - [ ] 顺序执行逻辑
- [ ] 实现 `AgentRouter`
  - [ ] 提示词构建
  - [ ] API 调用
  - [ ] 响应解析

#### 里程碑 2.2：Agent 角色（2 天）
- [ ] 定义 4 个预设角色
  - [ ] 概念师
  - [ ] 编写师
  - [ ] 评价师
  - [ ] 压缩师
- [ ] 实现角色管理界面

#### 里程碑 2.3：群组管理器（2 天）
- [ ] 实现 `GroupChatManager`
  - [ ] 创建群组
  - [ ] 发送消息
  - [ ] 工作流执行
  - [ ] 上下文管理
- [ ] 集成测试工作流

---

### 第三阶段：小说创作功能（预计 1 周）

#### 里程碑 3.1：多版本功能（3 天）
- [ ] 实现版本解析
- [ ] 实现 `VersionsDisplay` 组件
- [ ] 实现版本选择逻辑
- [ ] 实现版本对比界面

#### 里程碑 3.2：共享上下文（2 天）
- [ ] 实现 `SharedContextViewer`
- [ ] 蓝图展示
- [ ] 章节提要列表
- [ ] 角色档案展示
- [ ] 伏笔列表

#### 里程碑 3.3：导出功能（2 天）
- [ ] 导出完整小说（Markdown）
- [ ] 导出蓝图和提要
- [ ] 导出工作流日志

---

### 第四阶段：优化和扩展（持续）

#### 里程碑 4.1：UI 优化（1 周）
- [ ] 工作流进度条动画
- [ ] 消息发送动画
- [ ] Agent 状态指示（思考中、回复中）
- [ ] 深色/浅色主题适配
- [ ] 响应式布局（移动端/桌面端）

#### 里程碑 4.2：性能优化（3 天）
- [ ] 长文本处理优化
- [ ] 消息列表虚拟滚动
- [ ] 共享上下文缓存
- [ ] 流式输出支持

#### 里程碑 4.3：更多场景（持续）
- [ ] 头脑风暴模板
- [ ] 辩论对抗模板
- [ ] 文档协作模板
- [ ] 学习助手模板

---

## 10. 待讨论问题

### 10.1 工作流模式选择

**问题：** 你更倾向于哪种工作流模式？

**选项：**
1. **顺序执行**（全自动）
   - 优点：用户无需操作，流程顺畅
   - 缺点：灵活性低，无法中途干预

2. **手动控制**（全手动）
   - 优点：完全可控，可以跳过或重复步骤
   - 缺点：操作繁琐，效率低

3. **混合模式**（推荐）
   - 关键步骤自动（如概念师 → 压缩师）
   - 创作步骤手动（如编写师、评价师）
   - 兼顾效率和灵活性

**我的建议：** 混合模式，设置默认工作流，允许用户自定义

---

### 10.2 多版本生成

**问题：** 编写师一次生成几个版本？

**选项：**
1. 固定 3 个版本（A/B/C）
2. 固定 2 个版本（节省成本）
3. 可配置（2-5 个）

**问题：** 是否需要 AI 自动评分？

- ✅ 需要：方便快速筛选
- ❌ 不需要：避免误导，用户自己判断

**我的建议：** 默认 3 个版本，支持配置；提供可选的 AI 评分

---

### 10.3 上下文展示

**问题：** 共享上下文如何展示？

**选项：**
1. **侧边栏**（抽屉）
   - 优点：不遮挡对话，可持续查看
   - 缺点：桌面端占用空间

2. **底部 Sheet**
   - 优点：移动端友好
   - 缺点：遮挡对话，无法同时查看

3. **独立页面**
   - 优点：信息完整，专注查看
   - 缺点：需要切换页面

**我的建议：** 桌面端用侧边栏，移动端用底部 Sheet

---

### 10.4 是否需要分支功能？

**问题：** 是否支持"分支"创作？

**场景：** 用户选择版本 A 写了 3 章，后来想尝试版本 B 的路线

**选项：**
1. **支持分支**
   - 用户可以回退到某个节点，选择另一个版本
   - 类似 Git 的分支功能
   - 复杂度高

2. **不支持分支**
   - 简单直接，只保留主线
   - 用户如果想尝试可以创建新群组

**我的建议：** MVP 不支持分支，后续版本再考虑

---

### 10.5 其他问题

1. **是否需要"快照"功能？**
   - 保存某个阶段的完整状态，便于恢复

2. **工作流进度如何展示？**
   - 进度条？流程图？时间线？

3. **是否支持用户自定义工作流？**
   - 允许用户调整步骤顺序和触发条件

4. **是否支持 Agent 间对话？**
   - 例如编写师和评价师直接对话，不经过用户

5. **是否需要"预览模式"？**
   - 在完成多章后，生成小说预览（排版、目录等）

---

## 11. 总结

这个多 Agent 群组对话功能是 ChatBoxApp 的一个重大升级，将从简单的"一问一答"模式升级为"协作创作"模式。

### 核心优势：
1. **结构化创作** - 工作流引导，避免混乱
2. **多视角协作** - 多个专业 Agent 各司其职
3. **上下文管理** - 自动压缩和传递，长篇创作无忧
4. **多版本对比** - 提供选择，提高质量
5. **可扩展性** - 支持多种场景和自定义

### 下一步行动：

1. **讨论并确认**上述待讨论问题
2. **确定优先级**（MVP 包含哪些功能）
3. **开始第一阶段开发**（数据模型 + 基础 UI）

准备好开始了吗？我们可以从任何一个模块开始！🚀
