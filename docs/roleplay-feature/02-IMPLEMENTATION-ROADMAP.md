# 实现路线图与优先级

> 基于 ST 特性分析，规划 ChatBoxApp 角色扮演特化功能的实现路径

## 设计原则

1. **渐进增强**：从核心痛点入手，逐步扩展
2. **兼容现有**：不破坏现有聊天功能
3. **轻量优先**：在效果和复杂度之间寻求平衡
4. **用户可控**：高级功能可选启用

---

## Phase 0：基础设施（前置条件）

### 0.1 Token 计数器增强

**现状**：`lib/utils/token_counter.dart` 存在基础实现

**需增强**：
- [ ] 支持多种 tokenizer（GPT-4、Claude、Llama）
- [ ] 实时上下文 token 统计
- [ ] 预估剩余可用 token

### 0.2 上下文组装器抽象

**目标**：将上下文组装逻辑从 Adapter 中解耦

**注意**：ChatBoxApp 的 V2 对话支持树状消息链（`Conversation.threadJson`）。为与 UI/重生成行为一致，`history` 建议传入“当前选中分支（active chain）”的线性消息列表，避免把未选中的分支也纳入上下文。

```dart
abstract class ContextBuilder {
  List<ChatMessage> build({
    required String systemPrompt,
    required List<Message> history,
    required int maxTokens,
    // 扩展点
    String? authorsNote,
    int? authorsNoteDepth,
    List<WorldInfoEntry>? worldInfo,
  });
}
```

---

## Phase 1：核心功能（MVP）

### 1.1 Author's Note（P0 - 最高优先级）

**价值**：低成本高收益，立即解决"叙事漂移"问题

**实现要点**：
- 会话级配置：`Conversation.authorsNote` + `Conversation.authorsNoteDepth`
- 上下文组装时在指定深度插入
- UI：设置对话框中添加 Author's Note 编辑区

**预计工作量**：1-2 天

### 1.2 角色卡增强（P0）

**现状**：`CustomRole` 仅有 `name`、`description`、`systemPrompt`

**需增加字段**：
```dart
class EnhancedRole {
  String name;
  String description;      // 详细描述（外貌、性格、背景）
  String personality;      // 性格摘要
  String scenario;         // 场景设定
  String firstMessage;     // 开场白
  String exampleDialogue;  // 示例对话
  String systemPrompt;     // 系统提示词
  String? depthPrompt;     // 深度注入内容
  int? depthPromptDepth;   // 深度注入位置
}
```

**预计工作量**：2-3 天

### 1.3 World Info 基础版（P1）

**MVP 范围**：
- 简单的关键词 → 内容映射
- 扫描最近 N 条消息
- 全局 token 预算控制

**暂不实现**：
- 正则匹配
- Secondary Keys
- 递归触发
- 概率触发

**数据结构**：
```dart
class WorldInfoEntry {
  String id;
  List<String> keys;        // 触发关键词
  String content;           // 注入内容
  int tokenBudget;          // 该条目 token 上限
  int priority;             // 优先级
  bool isConstant;          // 是否始终注入
  bool isEnabled;           // 是否启用
}

class WorldInfoBook {
  String id;
  String name;
  List<WorldInfoEntry> entries;
  int globalBudget;         // 全局 token 预算
  int scanDepth;            // 扫描深度
}
```

**预计工作量**：3-5 天

---

## Phase 2：记忆系统

### 2.1 手动记忆编辑（P1）

**功能**：用户可编辑"长期记忆"文本，始终注入上下文

**实现**：
- `Conversation.memory` 字段
- 作为 Constant World Info 处理

### 2.2 自动记忆摘要（P2）

**功能**：上下文超限时，自动生成历史摘要

**策略**：
1. 检测上下文即将超限
2. 将旧消息送给 AI 生成摘要
3. 摘要存入 `Conversation.memorySummary`
4. 下次组装时注入摘要

**挑战**：
- 摘要时机：主动触发 vs 被动触发
- 摘要质量：需要精心设计 Prompt
- 用户控制：是否允许编辑摘要

**预计工作量**：5-7 天

---

## Phase 3：高级特性

### 3.1 深度注入控制（P2）

**功能**：允许用户控制各组件在上下文中的位置

**配置项**：
- System Prompt 位置
- Character Card 位置
- World Info 位置
- Author's Note 位置

### 3.2 宏系统（P2）

**功能**：支持 `{{char}}`、`{{user}}` 等模板变量

**实现**：在上下文组装前进行文本替换

### 3.3 角色卡导入/导出（P2）

**功能**：兼容 ST V2 格式的 PNG/JSON 角色卡

**格式**：
- PNG：图片 + EXIF 元数据
- JSON：纯文本格式

---

## Phase 4：多角色系统（可选）

### 4.1 群聊基础

- 多角色在同一会话
- 角色轮换发言
- 角色标签格式化

### 4.2 角色关系

- 通过 World Info 定义角色间关系
- 角色互动规则

---

## 优先级矩阵

```
        ┌─────────────────────────────────────────┐
 高价值 │  Author's Note    │  World Info MVP    │
        │  角色卡增强        │  自动记忆摘要      │
        ├───────────────────┼────────────────────┤
 低价值 │  宏系统           │  群聊系统          │
        │  角色卡导入       │  深度注入控制       │
        └───────────────────┴────────────────────┘
              低复杂度              高复杂度
```

---

## 建议实施顺序

```
Week 1-2: Phase 0 + Phase 1.1 (Author's Note)
Week 3-4: Phase 1.2 (角色卡增强)
Week 5-6: Phase 1.3 (World Info MVP)
Week 7+:  Phase 2+ (根据用户反馈调整)
```

---

## 技术债务预防

1. **抽象先行**：先定义接口，再实现具体功能
2. **配置驱动**：功能开关、参数可配置
3. **测试覆盖**：核心逻辑（关键词匹配、token 计算）需有单测
4. **文档同步**：每个 Phase 结束更新此文档

---

## 待讨论问题

1. **World Info 存储位置**：全局 vs 会话级 vs 角色级？
2. **记忆摘要触发时机**：自动 vs 手动 vs 询问用户？
3. **是否兼容 ST 角色卡格式**：完全兼容 vs 自定义格式？
4. **MVP 是否包含 World Info**：还是只做 Author's Note + 角色卡增强？
