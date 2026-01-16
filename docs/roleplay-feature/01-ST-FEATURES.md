# SillyTavern 核心特性深度分析

> 基于官方文档、GitHub Releases 和社区实践整理（研究笔记，细节以官方为准）

## 资料来源（建议优先阅读）

- ST 官方文档：World Info（Lorebook）https://docs.sillytavern.app/usage/core-concepts/worldinfo/
- ST 官方文档：Author's Note https://docs.sillytavern.app/usage/core-concepts/authors-note/
- ST 官方文档：Context Template / Story String https://docs.sillytavern.app/usage/prompts/context-template/
- ST 官方文档：Instruct Mode https://docs.sillytavern.app/usage/core-concepts/instructmode/
- ST 官方文档：Macros（含 `{{outlet::...}}` 等）https://docs.sillytavern.app/usage/core-concepts/macros/
- Character Card V2 规范（TavernCardV2）https://github.com/malfoyslastname/character-card-spec-v2
- timeline-memory（社区记忆扩展）https://github.com/unkarelian/timeline-memory
- ST Releases（特性变动参考）https://github.com/SillyTavern/SillyTavern/releases

## 1. World Info / Lorebook 系统

### 1.1 核心概念

World Info（又称 Lorebook）是 ST 最强大的特性之一：**按关键词触发的知识注入系统**。

```
用户输入: "我想去酒馆喝一杯"
         ↓
关键词匹配: "酒馆" 命中 Lorebook 条目
         ↓
注入内容: "黑狼酒馆位于城镇东区，老板是一个独眼老兵，常客包括..."
```

### 1.2 条目配置项

| 字段 | 说明 | 典型值 |
|------|------|--------|
| **Keys** | 触发关键词（支持多个） | `["酒馆", "tavern", "黑狼"]` |
| **Secondary Keys** | 次要关键词（AND 逻辑） | `["进入", "走进"]` |
| **Content** | 注入的内容 | 详细的地点/人物/事件描述 |
| **Scan Depth** | 扫描多少条历史消息 | `10` (扫描最近10条) |
| **Token Budget** | 该条目最多占用多少 token | `200` |
| **Priority** | 预算超限时的优先级 | `100` (越高越优先保留) |
| **Constant** | 是否始终注入（无需触发） | `false` |
| **Probability** | 触发后实际注入的概率 | `100%` |
| **Position** | 注入位置 | Before/After Char Defs / In-chat @ Depth / Top/Bottom of AN / Outlet 等 |
| **Case Sensitive** | 关键词大小写敏感 | `false` |

### 1.3 高级特性

- **递归扫描**：Content 中的关键词可触发其他条目
- **正则匹配**：Keys 支持正则表达式
- **条件逻辑**：可用额外过滤器/Secondary Keys 实现更复杂匹配（AND/NOT 等）
- **预算管理**：全局 Token Budget 限制所有条目总消耗
- **Outlet 位置**：条目可指定为 Outlet，并用 `{{outlet::Name}}` 宏在任意位置手动插入（名称区分大小写）

### 1.4 为什么有效？

1. **按需注入**：只有相关内容才进入上下文，节省 token
2. **结构化知识**：将世界观、角色关系、历史事件结构化存储
3. **持久记忆**：即使对话历史被截断，关键信息仍可通过关键词召回

---

## 2. Author's Note 系统

### 2.1 核心概念

Author's Note 是一段 **按频率注入** 的短文本，用于持续引导 AI 的行为。

### 2.2 关键参数

| 参数 | 说明 |
|------|------|
| **Content** | 注入的文本内容 |
| **Depth** | 插入深度（0=最后，N=倒数第N条消息之前） |
| **Role** | 以什么身份注入（system/user/assistant） |
| **Frequency** | 注入频率（例如每轮/每 N 轮/关闭） |

### 2.3 典型用法

```markdown
# 写作风格提醒（Depth=2）
[风格：细腻的心理描写，避免总结性语句，保持第一人称视角]

# 情节锚点（Depth=4）
[当前任务：找到失踪的妹妹。关键线索：旧照片上的神秘符号]

# 角色一致性提醒（Depth=0）
[{{char}}不会主动示好，对{{user}}保持警惕]
```

### 2.4 为什么有效？

- **位置靠后 = 权重更高**：放在用户输入附近，模型更关注
- **每轮刷新**：持续提醒，防止叙事漂移
- **灵活调整**：可根据剧情动态修改

---

## 3. Character Card 系统

### 3.1 V2 Spec 字段

ST 使用的角色卡格式（兼容 TavernAI V2）：

```json
{
  "spec": "chara_card_v2",
  "spec_version": "2.0",
  "data": {
    "name": "角色名",
    "description": "角色的详细描述（外貌、性格、背景）",
    "personality": "性格摘要（简短）",
    "scenario": "场景设定（当前情境）",
    "first_mes": "角色的开场白",
    "mes_example": "示例对话（few-shot）",
    "creator_notes": "创作者备注（不发送给模型）",
    "system_prompt": "角色专属系统提示词（覆盖全局或替换默认 system）",
    "post_history_instructions": "历史消息后的指令（PHI）",
    "tags": ["fantasy", "female", "elf"],
    "creator": "作者名",
    "character_version": "1.0",
    "extensions": {}
  }
}
```

### 3.2 关键字段解析

| 字段 | 位置 | 作用 |
|------|------|------|
| `description` | Story String | 角色核心定义，权重最高 |
| `personality` | Story String | 性格速查，冗余但有助强化 |
| `scenario` | Story String | 场景设定，建立初始情境 |
| `first_mes` | 首条 AI 消息 | 定下对话基调 |
| `mes_example` | Story String | Few-shot 示例，教模型说话风格 |
| `system_prompt` | System | 角色级系统提示词覆盖 |
| `post_history_instructions` | 历史后 | 历史消息之后的补充指令 |
| `depth_prompt` | @Depth N | 任意深度的提醒注入 |

### 3.3 宏系统

ST 支持大量模板变量：

```
{{char}}        → 角色名
{{user}}        → 用户名
{{description}} → 角色描述
{{personality}} → 角色性格
{{scenario}}    → 场景设定
{{persona}}     → 用户人设
{{mesExamples}} → 格式化后的示例对话
{{authorsNote}} → Author's Note 内容
{{time}}        → 当前时间
{{date}}        → 当前日期
{{random::a::b::c}} → 随机选择
{{roll::d20}}   → 骰子
```

---

## 4. Context Template 系统

### 4.1 Story String

Story String 是 ST 组装角色信息的核心模板：

```
{{#if system}}{{system}}{{/if}}
{{#if description}}{{description}}{{/if}}
{{#if personality}}Personality: {{personality}}{{/if}}
{{#if scenario}}Scenario: {{scenario}}{{/if}}
{{#if persona}}{{persona}}{{/if}}
```

### 4.2 深度注入（@Depth）

ST 支持将 Story String 放在对话历史的任意深度（In-chat @ Depth）：

```
Depth 0: [用户输入]
Depth 1: [AI最后回复]
Depth 2: [用户倒数第二条]  ← Story String 可插入这里
Depth 3: [AI倒数第二条]
...
```

### 4.3 锚点占位符

```
{{anchorBefore}} - Story String 前的锚点
{{anchorAfter}}  - Story String 后的锚点
```

---

## 5. Instruct Mode

### 5.1 作用

不同模型对提示词格式有不同要求，Instruct Mode 负责将内容包装成模型期望的格式。

### 5.2 常见格式

**ChatML（OpenAI/通用）**：
```
<|im_start|>system
系统提示词
<|im_end|>
<|im_start|>user
用户消息
<|im_end|>
<|im_start|>assistant
AI回复
<|im_end|>
```

**Llama 3**：
```
<|begin_of_text|><|start_header_id|>system<|end_header_id|>
系统提示词<|eot_id|>
<|start_header_id|>user<|end_header_id|>
用户消息<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>
```

### 5.3 ST 的处理方式

ST 为每种模型预置了 Instruct 模板，包含：
- `system_prefix` / `system_suffix`
- `user_prefix` / `user_suffix`
- `assistant_prefix` / `assistant_suffix`
- `stop_strings`（停止序列）

---

## 6. Memory Management

### 6.1 问题：Memory Snap

当上下文超出模型限制时，旧消息被截断，导致 AI 突然"失忆"。

### 6.2 ST 的解决方案

1. **World Info**：关键信息通过关键词召回
2. **Author's Note**：持续提醒关键情节点
3. **Timeline-memory 扩展**：自动生成章节摘要
4. **手动摘要**：用户可编辑"记忆"字段

### 6.3 Timeline-memory 扩展

社区开发的智能记忆扩展：
- 自动将对话分割为"章节"
- 每章生成摘要存入 Lorebook
- 支持智能检索（根据当前对话召回相关章节）
- Inject at Depth 自动注入

---

## 7. 群聊 / 多角色系统

### 7.1 特性

- 多角色同时在场
- 回合制或自由发言
- 每个角色独立的 Character Card
- 角色间互动

### 7.2 实现要点

- 角色标签：`[角色名]: 发言内容`
- 回合控制：指定下一个发言者
- 角色关系：通过 World Info 定义

---

## 8. ST 优势总结

| 特性 | 核心价值 | 实现复杂度 |
|------|----------|------------|
| World Info | 按需注入，节省 token | 中 |
| Author's Note | 持续引导，防止漂移 | 低 |
| Character Card V2 | 结构化角色定义 | 低 |
| Depth Injection | 精细控制上下文位置 | 中 |
| Instruct Templates | 适配多种模型 | 中 |
| Memory Summary | 解决长文失忆 | 高 |
| 群聊系统 | 多角色互动 | 高 |

--- 

## 9. 待深入研究

- [ ] ST 源码中 World Info 触发的具体算法
- [ ] Token 预算分配的优先级策略
- [ ] Timeline-memory 的摘要生成 Prompt
- [ ] 群聊回合调度逻辑

---

**建议**：如需对齐行为，建议基于 ST release 分支源码做针对性分析（World Info 引擎 + Prompt 组装逻辑），避免被旧文章/旧文件路径误导。
