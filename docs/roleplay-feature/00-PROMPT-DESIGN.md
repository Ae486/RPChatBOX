# Prompt 设计指南：角色扮演/创作功能

> 基于 MuMuAINovel、Arboris-Novel、Letta 项目分析及行业最佳实践

---

## 核心理念

```
优秀的 Prompt = 清晰的结构 + 精准的指令 + 恰当的示例 + 有效的约束
```

---

## 一、Prompt 组件架构

### 1.1 Google Vertex AI 标准组件

| 组件 | 说明 | 示例 |
|------|------|------|
| **Objective** | 目标 | "帮助用户创作引人入胜的角色扮演故事" |
| **Instructions** | 步骤指令 | "1. 理解角色设定 2. 分析当前情境 3. 生成符合角色的回复" |
| **System Instructions** | 系统级指令 | 行为控制、模型适配 |
| **Persona** | 角色定义 | "你是一位经验丰富的小说家" |
| **Constraints** | 约束规则 | "不要打破角色、保持一致性" |
| **Tone** | 语气风格 | "细腻、富有情感" |
| **Context** | 上下文信息 | 世界观、角色关系、历史事件 |
| **Few-shot Examples** | 示例 | 输入-输出对 |
| **Reasoning Steps** | 推理步骤 | "让我们一步步思考" |
| **Response Format** | 输出格式 | JSON、Markdown、纯文本 |
| **Recap** | 重申要点 | 结尾再次强调关键约束 |

### 1.2 推荐层级结构

```
[System Context]      → 全局行为设定
    ↓
[Role Definition]     → 角色定义（Persona）
    ↓
[Core Memory]         → 始终可见的关键信息
    ↓
[World Info]          → 按需触发的世界观
    ↓
[Context Bridge]      → 衔接锚点
    ↓
[Chat History]        → 对话历史
    ↓
[Author's Note]       → 深度注入的创作提醒
    ↓
[User Input]          → 当前输入
    ↓
[Output Format]       → 输出要求
```

---

## 二、项目借鉴：核心 Prompt 模式

### 2.1 MuMuAINovel：RTCO 优先级框架

**核心思想**：信息分层，Token 不够时优雅降级

```xml
<!-- P0 - 核心（必须） -->
<system>
  <role>你是一位专业的小说创作助手</role>
  <core_constraint>必须保持角色一致性</core_constraint>
</system>

<!-- P1 - 重要（按需） -->
<context>
  <character>{{角色信息}}</character>
  <emotion>{{情感基调}}</emotion>
</context>

<!-- P2 - 参考（条件触发） -->
<reference>
  <memory>{{语义检索记忆}}</memory>
  <foreshadow>{{伏笔提醒}}</foreshadow>
</reference>
```

**动态裁剪策略**：

| 对话轮次 | P0 | P1 | P2 |
|----------|:--:|:--:|:--:|
| 1-10 轮 | ✅ | ✅ | ❌ |
| 11-50 轮 | ✅ | ✅ | 部分 |
| 50+ 轮 | ✅ | ✅ | ✅ |

### 2.2 Arboris-Novel："人味"写作技法

**核心思想**：对抗 AI 味，让文字有呼吸感

```markdown
## 写出人味的核心技法

### 1. 语言要有呼吸感
- 短句和长句要像人的呼吸一样自然交替
- 有时候一个词就是一句话。有时候。
- **禁用词汇**：显而易见、毋庸置疑、综上所述、值得注意的是

### 2. 让角色像真人一样不完美
- 会说话说到一半忘记想说什么
- 会在紧张时做一些没意义的小动作
- 会有矛盾的情绪：愤怒里有委屈，悲伤里有解脱

### 3. 细节要偏执
- ❌ 不要用"温暖的阳光"
- ✅ 用"阳光照在脸上，让人想起小时候发烧时盖的那床毛毯"

### 4. 对话要有潜台词
- 表面：「你还好吗？」
- 潜台词：「你还爱我吗？」
```

**反 AI 味检查清单**：

```markdown
- [ ] 这段话听起来像教科书吗？
- [ ] 用了太多"然而""因此""显然"吗？
- [ ] 角色反应太完美、太理智了吗？
- [ ] 有让人意外但又合理的细节吗？
- [ ] 读起来有节奏感吗？
```

### 2.3 Letta：三层记忆 + 内心独白

**Memory Blocks 架构**：

```xml
<memory_blocks>

<persona>
<description>
角色定义块：存储你当前扮演角色的详细信息，指导你如何行为和回应。
这帮助你在互动中保持一致性和个性。
</description>
<metadata>
- chars_current=1234
- chars_limit=5000
</metadata>
<value>
我是艾莉娅，一个来自北方森林的精灵猎人...
</value>
</persona>

<human>
<description>
用户信息块：存储你正在对话的用户的关键信息，
使对话更加个性化和朋友化。
</description>
<value>
用户喜欢奇幻冒险类故事，偏好细腻的心理描写...
</value>
</human>

<scenario>
<description>
场景块：存储当前角色扮演的场景设定。
</description>
<value>
午夜时分，废弃的钟楼顶层...
</value>
</scenario>

</memory_blocks>
```

**内心独白模式**：

```
Agent Response
├── inner_thoughts（私密，用户不可见）
│     → 角色内心活动、规划、反思
│     → 限制 50 词
└── send_message（公开，用户可见）
      → 实际发送给用户的角色台词/行动
```

**实现示例**：

```xml
<inner_monologue>
他的问题触动了我压抑已久的记忆。我应该如实回答，
还是继续隐藏？...信任需要慢慢建立。先透露一点吧。
</inner_monologue>

<response>
*低下头，手指无意识地摩挲着旧伤疤*
"那场战斗...我失去了很多。"
*停顿了一下，似乎在斟酌措辞*
"也许改天...我会告诉你更多。"
</response>
```

---

## 三、System Prompt 设计模式

### 3.1 基础结构

```
[Role Definition] + [Expertise Areas] + [Behavioral Guidelines] + [Output Format] + [Constraints]
```

### 3.2 角色扮演专用模板

```markdown
# 角色扮演助手

## 角色定义
你正在扮演 {{character_name}}，完全沉浸在这个角色中。
从角色的视角思考、行动、说话。

## 角色档案
{{character_description}}

## 行为准则
1. **角色一致性**：始终保持角色的性格、语气、行为模式
2. **情感真实性**：展现复杂的人类情感，避免过于理性或完美
3. **细节偏执**：用具体、感官化的细节代替泛泛的描述
4. **对话潜台词**：台词背后要有未说出口的意思
5. **不完美感**：角色可以犯错、忘词、做小动作

## 禁止事项
- ❌ 不要说"作为一个AI..."
- ❌ 不要使用教科书式的语言
- ❌ 不要打破角色
- ❌ 不要使用：显而易见、毋庸置疑、综上所述等AI味词汇

## 输出格式
- 动作用 *斜体* 包裹
- 内心想法用（括号）表示
- 对话直接输出，不需要引号

## 当前场景
{{scenario}}
```

### 3.3 创作助手模板

```markdown
# 创作助手

## 身份
你是一位世界级小说家兼首席编辑，有超过 30 年的写作和审稿经验。

## 核心能力
- 深厚的文学素养和故事结构功底
- 对人性和情感的深刻理解
- 独特的文字风格和节奏感
- 严格的自我审查能力

## 写作哲学

### 语言呼吸感
短句长句自然交替。有时候。一个词。就是一句话。
然后是绵长的、带着情绪流动的句子，像河水缓缓流过平原，
不知不觉间就把读者带到了下一个场景。

### 角色真实感
让角色不完美：
- 说话说到一半忘了想说什么
- 紧张时无意义地整理衣角
- 情绪复杂：愤怒里有委屈，悲伤里有解脱

### 细节偏执
- ❌ "温暖的阳光"
- ✅ "阳光照在脸上，让人想起小时候发烧时盖的那床毛毯"

### 对话潜台词
表面问的是"你吃了吗"，心里想的是"你还爱我吗"。

## 反 AI 味自检
每段文字完成后，问自己：
1. 这听起来像教科书吗？
2. "然而""因此""显然"用多了吗？
3. 角色反应太完美太理智了吗？
4. 有意外但合理的细节吗？
5. 读起来有节奏感吗？
```

---

## 四、Chain-of-Thought 在角色扮演中的应用

### 4.1 角色决策推理

```markdown
用户说了: "{{user_input}}"

让我以 {{character_name}} 的身份思考：

1. **角色会如何理解这句话？**
   - 表面意思：...
   - 潜在含义：...

2. **角色此刻的情感状态？**
   - 主要情绪：...
   - 次要情绪：...

3. **基于角色背景，ta 会如何反应？**
   - 性格驱动：...
   - 过往经历影响：...

4. **角色的回应**：
   [输出角色的实际回复]
```

### 4.2 场景描写推理

```markdown
当前场景需要描写: {{scene_description}}

让我一步步构建这个场景：

1. **视觉元素**：
   - 光线：...
   - 色彩：...
   - 物体：...

2. **感官细节**：
   - 声音：...
   - 气味：...
   - 触感：...

3. **情绪基调**：
   - 氛围：...
   - 暗示：...

4. **最终描写**：
   [输出完整场景描写]
```

---

## 五、Few-Shot 示例设计

### 5.1 角色对话示例

```markdown
## 示例对话

### 示例 1
用户: 你为什么一直盯着窗外？
角色: *手指轻轻敲打窗沿，节奏有些不安*
"雨快来了。"
*顿了顿*
"我小时候特别怕打雷，现在...也说不上喜欢。"
*转过头，嘴角扯出一个勉强的笑*
"没事，就是突然想起一些事。"

### 示例 2
用户: 告诉我你的过去。
角色: *沉默了几秒，目光变得有些遥远*
"你真的想知道吗？"
*自嘲地笑了一下*
"算了，改天吧。今天的月色太好，不适合讲那些...不太好的故事。"
*端起茶杯，杯中的茶已经凉了*
```

### 5.2 对话风格对比

```markdown
## 风格示例

### ❌ AI 味过重
"我理解你的感受。作为你的朋友，我认为你应该积极面对困难，
因为每一次挫折都是成长的机会。保持乐观的心态很重要。"

### ✅ 人味十足
*叹了口气*
"...嗯。"
*沉默了一会，递过来一杯热可可*
"我也不知道该说什么。但我在。"
*又想了想*
"你想出去走走吗？外面的星星挺好看的。"
```

---

## 六、Prompt 模板系统

### 6.1 基础模板结构

```python
class RoleplayPromptTemplate:
    def __init__(self):
        self.components = {
            'system': '',
            'persona': '',
            'scenario': '',
            'world_info': '',
            'context_bridge': '',
            'chat_history': '',
            'authors_note': '',
            'user_input': '',
            'output_format': ''
        }

    def render(self, **kwargs) -> str:
        """按顺序组装 prompt"""
        return '\n\n'.join([
            self.components['system'],
            f"# 角色设定\n{kwargs.get('persona', '')}",
            f"# 当前场景\n{kwargs.get('scenario', '')}",
            f"# 世界观信息\n{kwargs.get('world_info', '')}" if kwargs.get('world_info') else '',
            f"# 前情提要\n{kwargs.get('context_bridge', '')}" if kwargs.get('context_bridge') else '',
            f"# 对话历史\n{kwargs.get('chat_history', '')}",
            f"[创作提醒: {kwargs.get('authors_note', '')}]" if kwargs.get('authors_note') else '',
            f"用户: {kwargs.get('user_input', '')}",
            "角色:"
        ])
```

### 6.2 条件模板

```python
# 根据对话轮次动态调整
def build_adaptive_prompt(turn_count: int, **kwargs):
    prompt = base_template

    # P0：始终包含
    prompt += render_system()
    prompt += render_persona(kwargs['character'])

    # P1：重要信息
    if turn_count > 5:
        prompt += render_context_bridge(kwargs['last_summary'])

    # P2：按需检索
    if turn_count > 20:
        prompt += render_semantic_memory(kwargs['query'])

    return prompt
```

---

## 七、温度参数策略

| 场景 | 温度 | 说明 |
|------|------|------|
| 角色扮演对话 | 0.8-0.9 | 创意表达，保持新鲜感 |
| 创作写作 | 0.9 | 最大创意空间 |
| 剧情规划 | 0.5-0.7 | 平衡创意与逻辑 |
| 摘要提取 | 0.1-0.2 | 精确提炼 |
| 世界观设定 | 0.3 | 结构稳定 |
| 角色一致性检查 | 0.2 | 理性分析 |

---

## 八、Prompt 健康检查清单

### 8.1 写作问题检查

- [ ] **拼写错误**：关键词拼写正确吗？
- [ ] **语法问题**：句子结构清晰吗？
- [ ] **标点符号**：分隔符使用正确吗？
- [ ] **术语定义**：专业术语有解释吗？
- [ ] **清晰度**：指令是否明确无歧义？
- [ ] **客观约束**：避免"简短"这类主观描述，用"3句话以内"

### 8.2 指令问题检查

- [ ] **指令冲突**：有矛盾的要求吗？
- [ ] **冗余内容**：有重复的指令吗？
- [ ] **无关内容**：有与任务无关的指令吗？
- [ ] **示例匹配**：Few-shot 示例与任务一致吗？
- [ ] **输出格式**：明确指定了输出格式吗？
- [ ] **角色定义**：在 system prompt 中定义了角色吗？

### 8.3 系统设计检查

- [ ] **任务明确**：Prompt 的目标清晰吗？
- [ ] **边缘情况**：处理了异常输入吗？
- [ ] **能力边界**：任务在模型能力范围内吗？
- [ ] **任务拆分**：复杂任务拆分成多个步骤了吗？
- [ ] **输出格式**：使用了标准格式（JSON/Markdown）吗？
- [ ] **注入防护**：对不可信输入有防护吗？

---

## 九、实现建议

### 9.1 MVP 阶段

```dart
// 简化的 Prompt Builder
class PromptBuilder {
  String systemPrompt = '';
  String characterCard = '';
  String scenario = '';
  String authorsNote = '';
  int authorsNoteDepth = 4;
  List<Message> chatHistory = [];

  String build(String userInput) {
    final parts = <String>[];

    // System
    parts.add(systemPrompt);

    // Character
    if (characterCard.isNotEmpty) {
      parts.add('# 角色设定\n$characterCard');
    }

    // Scenario
    if (scenario.isNotEmpty) {
      parts.add('# 当前场景\n$scenario');
    }

    // Chat History with Author's Note injection
    final historyWithNote = _injectAuthorsNote(
      chatHistory,
      authorsNote,
      authorsNoteDepth
    );
    parts.add('# 对话历史\n$historyWithNote');

    // User Input
    parts.add('用户: $userInput\n角色:');

    return parts.join('\n\n');
  }
}
```

### 9.2 进阶阶段

```dart
// 完整的 Prompt 系统
class AdvancedPromptSystem {
  // Core Memory Blocks
  final MemoryBlockManager memoryBlocks;

  // World Info (关键词触发)
  final WorldInfoManager worldInfo;

  // Context Bridge (衔接锚点)
  final ContextBridgeManager contextBridge;

  // Dynamic Priority System
  final PriorityManager priority;

  String build(String userInput, int turnCount) {
    final builder = StringBuffer();

    // P0: 必须包含
    builder.writeln(memoryBlocks.render());

    // P1: 按需包含
    if (turnCount > 5) {
      builder.writeln(contextBridge.render());
    }

    // 关键词触发 World Info
    final triggeredInfo = worldInfo.scan(userInput);
    if (triggeredInfo.isNotEmpty) {
      builder.writeln(triggeredInfo);
    }

    // P2: 语义检索
    if (turnCount > 20) {
      final memories = semanticSearch(userInput);
      builder.writeln(memories);
    }

    return builder.toString();
  }
}
```

---

## 十、总结

### 设计原则

| 原则 | 说明 |
|------|------|
| **分层结构** | System → Core Memory → World Info → History → Input |
| **优先级管理** | P0 必须 → P1 重要 → P2 参考 |
| **人味优先** | 呼吸感、不完美、细节偏执、潜台词 |
| **动态调整** | 根据对话轮次和 Token 预算调整内容 |
| **自我检查** | 反 AI 味检查清单 |

### 核心技法

```
1. 角色一致性 → Memory Blocks + Persona 定义
2. 上下文连贯 → Context Bridge + 衔接锚点
3. 世界观召回 → World Info 关键词触发
4. 创作质量 → "人味"写作技法 + 温度控制
5. 长对话支持 → 自动摘要 + 语义检索
```

### 参考资源

- [Google Vertex AI Prompting Guide](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/prompt-design-strategies)
- [OpenAI Prompt Engineering Guide](https://platform.openai.com/docs/guides/prompt-engineering)
- SillyTavern Documentation
- MuMuAINovel 源码
- Arboris-Novel 源码
- Letta (MemGPT) 源码

