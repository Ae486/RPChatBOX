# 数据模型设计草案

> 角色扮演特化功能的数据结构设计

## 1. 现有模型回顾

### 1.1 当前 CustomRole

```dart
// lib/models/custom_role.dart
class CustomRole {
  String id;
  String name;
  String description;
  String systemPrompt;
  String icon;
}
```

### 1.2 当前 Conversation

```dart
// lib/models/conversation.dart
class Conversation {
  String id;
  String title;
  List<Message> messages;
  DateTime createdAt;
  DateTime updatedAt;
  String? systemPrompt;
  int? scrollIndex;
  String? roleId;
  String? roleType;  // 'preset' | 'custom'
  String? threadJson;
}
```

> 备注：当前会话已支持 **树状消息链**（`threadJson` → `ConversationThread`），后续“记忆摘要/World Info 扫描/上下文组装”需要明确作用域：按会话全局，还是按当前选中分支（active chain）。建议 MVP 先以 active chain 作为 Chat History 输入，避免未选中的分支污染上下文。

---

## 2. 增强角色卡模型

### 2.1 RoleCard（替代 CustomRole）

```dart
/// 增强角色卡（兼容 TavernAI V2 Spec）
@HiveType(typeId: 10)
class RoleCard {
  @HiveField(0)
  final String id;

  @HiveField(1)
  String name;

  @HiveField(2)
  String? avatar;  // 头像路径或 base64

  // === 核心字段 ===

  @HiveField(3)
  String description;  // 详细描述（外貌、性格、背景）

  @HiveField(4)
  String? personality;  // 性格摘要（可选）

  @HiveField(5)
  String? scenario;  // 场景设定

  @HiveField(6)
  String? firstMessage;  // 开场白

  @HiveField(7)
  String? exampleDialogue;  // 示例对话（few-shot）

  @HiveField(8)
  String? systemPrompt;  // 角色级系统提示词（覆盖全局）

  // === 高级字段 ===

  @HiveField(9)
  String? postHistoryInstructions;  // 历史消息后的指令

  @HiveField(10)
  String? depthPrompt;  // 深度注入内容

  @HiveField(11)
  int? depthPromptDepth;  // 深度注入位置（默认 4）

  // === 元数据 ===

  @HiveField(12)
  String? creatorNotes;  // 创作者备注（不发送给模型）

  @HiveField(13)
  List<String>? tags;  // 标签

  @HiveField(14)
  String? creator;  // 作者

  @HiveField(15)
  String? version;  // 版本号

  @HiveField(16)
  DateTime createdAt;

  @HiveField(17)
  DateTime updatedAt;

  // === 关联 ===

  @HiveField(18)
  String? worldInfoBookId;  // 绑定的 World Info Book
}
```

### 2.2 兼容性转换

```dart
extension CustomRoleToRoleCard on CustomRole {
  RoleCard toRoleCard() {
    return RoleCard(
      id: id,
      name: name,
      description: description,
      systemPrompt: systemPrompt,
      avatar: null,  // icon 转 avatar
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
    );
  }
}
```

---

## 3. World Info 模型

### 3.1 WorldInfoEntry（单条知识）

```dart
@HiveType(typeId: 11)
class WorldInfoEntry {
  @HiveField(0)
  final String id;

  @HiveField(1)
  String name;  // 条目名称（用于管理）

  // === 触发条件 ===

  @HiveField(2)
  List<String> keys;  // 主关键词（OR 逻辑）

  @HiveField(3)
  List<String>? secondaryKeys;  // 次要关键词（AND 逻辑，可选）

  @HiveField(4)
  bool caseSensitive;  // 大小写敏感

  @HiveField(5)
  bool useRegex;  // 使用正则匹配（MVP 可不实现）

  // === 内容 ===

  @HiveField(6)
  String content;  // 注入内容

  // === 预算控制 ===

  @HiveField(7)
  int tokenBudget;  // 该条目 token 上限（默认 200）

  @HiveField(8)
  int priority;  // 优先级（越高越优先，默认 100）

  // === 行为控制 ===

  @HiveField(9)
  bool isConstant;  // 始终注入（无需触发）

  @HiveField(10)
  bool isEnabled;  // 是否启用

  @HiveField(11)
  int? probability;  // 触发概率（1-100，默认 100）

  // === 位置控制 ===

  @HiveField(12)
  WorldInfoPosition position;  // 注入位置

  @HiveField(13)
  int? depth;  // 当 position 为 atDepth 时使用

  // === 元数据 ===

  @HiveField(14)
  String? comment;  // 备注

  @HiveField(15)
  DateTime createdAt;

  @HiveField(16)
  DateTime updatedAt;
}

/// 注入位置枚举
@HiveType(typeId: 12)
enum WorldInfoPosition {
  @HiveField(0)
  beforeCharacter,  // 角色定义之前

  @HiveField(1)
  afterCharacter,   // 角色定义之后

  @HiveField(2)
  atDepth,          // 指定深度

  @HiveField(3)
  authorNote,       // 作为 Author's Note
}
```

### 3.2 WorldInfoBook（知识书）

```dart
@HiveType(typeId: 13)
class WorldInfoBook {
  @HiveField(0)
  final String id;

  @HiveField(1)
  String name;

  @HiveField(2)
  String? description;

  @HiveField(3)
  List<WorldInfoEntry> entries;

  // === 全局配置 ===

  @HiveField(4)
  int globalTokenBudget;  // 全局 token 预算（默认 1024）

  @HiveField(5)
  int scanDepth;  // 扫描深度（默认 10）

  @HiveField(6)
  bool isEnabled;  // 是否启用

  // === 元数据 ===

  @HiveField(7)
  DateTime createdAt;

  @HiveField(8)
  DateTime updatedAt;
}
```

---

## 4. 会话扩展模型

### 4.1 Conversation 扩展字段

```dart
// 在现有 Conversation 基础上添加
class Conversation {
  // ... 现有字段 ...

  // === 角色扮演扩展 ===

  @HiveField(10)
  String? authorsNote;  // Author's Note 内容

  @HiveField(11)
  int authorsNoteDepth;  // 深度（默认 4）

  @HiveField(12)
  String? memory;  // 手动编辑的长期记忆

  @HiveField(13)
  String? memorySummary;  // 自动生成的记忆摘要

  @HiveField(14)
  String? worldInfoBookId;  // 绑定的 World Info Book

  @HiveField(15)
  RolePlaySettings? rolePlaySettings;  // 角色扮演设置
}
```

### 4.2 RolePlaySettings（会话级配置）

```dart
@HiveType(typeId: 14)
class RolePlaySettings {
  @HiveField(0)
  bool isEnabled;  // 是否启用角色扮演模式

  @HiveField(1)
  String? userName;  // 用户名（用于 {{user}} 宏）

  @HiveField(2)
  String? userPersona;  // 用户人设

  @HiveField(3)
  bool autoSummarize;  // 自动摘要开关

  @HiveField(4)
  int? summarizeThreshold;  // 触发摘要的 token 阈值

  @HiveField(5)
  ContextBuildingStrategy contextStrategy;  // 上下文组装策略
}

@HiveType(typeId: 15)
enum ContextBuildingStrategy {
  @HiveField(0)
  standard,  // 标准（兼容现有逻辑）

  @HiveField(1)
  rolePlay,  // 角色扮演优化

  @HiveField(2)
  creative,  // 创作优化
}
```

---

## 5. 上下文组装顺序

### 5.1 标准模式

```
1. System Prompt
2. Chat History
3. User Input
```

### 5.2 角色扮演模式

```
1. System Prompt（全局或角色覆盖）
2. [Memory Summary]（如有）
3. [User Persona]（如有）
4. Character Card（description + personality + scenario）
5. [Example Dialogue]（如有）
6. [World Info - Constant]（始终注入的条目）
7. Chat History（active chain；含 World Info 触发注入）
   - @Depth N: [Depth Prompt]
   - @Depth M: [Author's Note]
8. [Post History Instructions]（如有）
9. User Input
```

---

## 6. 存储策略

### 6.1 Hive Box 分配

| Box 名称 | 内容 | TypeId 范围 |
|----------|------|-------------|
| `roleCards` | 角色卡 | 10 |
| `worldInfo` | World Info Books | 11-13 |
| `conversations` | 会话（含扩展字段） | 0-1, 14-15 |

### 6.2 迁移策略

1. 保留现有 `CustomRole`，新增 `RoleCard`
2. 提供一键迁移工具：`CustomRole` → `RoleCard`
3. 旧版角色使用 `roleType: 'legacy'` 标记

---

## 7. 待确认事项

1. **TypeId 分配**：确认现有 Hive TypeId 使用情况，避免冲突
2. **头像存储**：路径 vs base64 vs 单独 box
3. **World Info 作用域**：全局 / 会话 / 角色三级？
4. **向后兼容**：如何处理已有的 CustomRole 数据

---

## 8. 下一步

- [ ] 确认 TypeId 分配
- [ ] 审查现有 Hive 迁移策略
- [ ] 设计 World Info 触发算法
- [ ] 设计上下文组装器接口
