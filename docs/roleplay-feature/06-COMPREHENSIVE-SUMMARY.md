# 四大项目可借鉴优势综合总结

> SillyTavern + MuMuAINovel + Arboris-Novel + Letta

---

## 核心问题与解决方案映射

| 核心问题 | ST | MuMu | Arboris | Letta |
|----------|:--:|:----:|:-------:|:-----:|
| **上下文丢失** | World Info | 动态裁剪 | RAG 检索 | 三层记忆 |
| **角色一致性** | Character Card | — | 世界蓝图 | Memory Blocks |
| **长对话失忆** | Author's Note | 伏笔追踪 | 章节摘要 | Archival Memory |
| **叙事漂移** | 深度注入 | 衔接锚点 | 上下文桥接 | 自主记忆编辑 |
| **AI 味过重** | — | — | "人味"提示词 | Inner Monologue |
| **记忆管理负担** | 手动编辑 | 自动提取 | 自动摘要 | **后台自主学习** |
| **Token 成本失控** | Token Budget/Scan Depth | RTCO 优先级裁剪 | 分层注入 + RAG | Tool 输出截断 + 摘要兜底 + Max Steps |

---

## 一、SillyTavern 的优势

### 1.1 World Info / Lorebook（按需注入）

```
用户输入: "我想去酒馆喝一杯"
         ↓
关键词匹配: "酒馆" 命中
         ↓
自动注入: "黑狼酒馆位于城镇东区，老板是独眼老兵..."
```

**核心价值**：
- 📦 **节省 Token**：只在需要时注入相关信息
- 🔗 **结构化知识**：世界观、角色关系、历史事件分门别类
- 🔄 **持久召回**：即使对话历史被截断，关键词仍可触发

**关键配置**：
- `Keys` / `Secondary Keys`：主次关键词（OR / AND 逻辑）
- `Scan Depth`：扫描最近 N 条消息
- `Token Budget`：单条目 / 全局预算
- `Priority`：超预算时的保留优先级
- `Position`：注入位置（角色前/后、指定深度）

### 1.2 Author's Note（持续锚定）

**核心价值**：
- 🎯 **防止漂移**：按配置频率注入（可每轮/每 N 轮）提醒当前情节锚点
- ⚡ **位置靠后 = 权重高**：放在用户输入附近，模型更关注
- 🔧 **灵活调整**：可根据剧情动态修改

**典型用法**：
```markdown
[风格：细腻心理描写，避免总结性语句，保持第一人称]
[当前任务：找到失踪的妹妹。线索：旧照片上的神秘符号]
[{{char}} 对 {{user}} 保持警惕，不会主动示好]
```

### 1.3 Character Card V2（结构化角色）

| 字段 | 作用 |
|------|------|
| `description` | 外貌、性格、背景（核心权重） |
| `personality` | 性格速查（冗余强化） |
| `scenario` | 场景设定（初始情境） |
| `first_mes` | 开场白（定下基调） |
| `mes_example` | Few-shot 示例（教说话风格） |
| `system_prompt` | 角色级系统提示词覆盖 |
| `depth_prompt` | 任意深度的提醒注入 |

> 注：Character Card V2 的 JSON 通常有 `spec/spec_version/data` 的 wrapper，上表字段一般位于 `data` 内。

---

## 二、MuMuAINovel 的优势

### 2.1 RTCO 框架（上下文优先级）

```
P0 - 核心（必须）
├── 章节大纲
├── 衔接锚点（上一章结尾 300-500 字）
└── 字数要求

P1 - 重要（按需）
├── 涉及角色信息
├── 情感基调
└── 写作风格

P2 - 参考（条件触发）
├── 语义检索记忆
├── 故事骨架（50 章+）
└── 伏笔提醒
```

**核心价值**：明确的优先级层次，Token 不够时优雅降级

### 2.2 动态上下文裁剪

| 章节范围 | 衔接长度 | 记忆数量 | 额外内容 |
|----------|----------|----------|----------|
| 第 1 章 | 无 | 无 | 仅大纲+角色 |
| 第 2-10 章 | 300 字 | 无 | 涉及角色 |
| 第 11-50 章 | 500 字 | 3 条 | 相关记忆 |
| 第 51+ 章 | 500 字 | 5 条 | 故事骨架 |

**核心价值**：根据故事进度**自动调整**上下文复杂度

### 2.3 伏笔追踪系统

```python
is_foreshadow: int
# 0 = 普通记忆
# 1 = 已埋下伏笔（待回收）
# 2 = 伏笔已回收

foreshadow_strength: float   # 强度 0.0-1.0
foreshadow_resolved_at: str  # 回收章节
```

**核心价值**：
- 自动检测即将"到期"的伏笔（lookahead=5 章）
- 在合适时机提醒回收

---

## 三、Arboris-Novel 的优势

### 3.1 五层信息架构

```
L1 世界蓝图   │ JSON   │ 世界设定、人物档案   │ ❌ 不检索（固定约束）
L2 剧情记忆   │ 向量库 │ 已生成章节分块       │ ✅ RAG 检索
L3 章节摘要   │ JSON   │ 标题 + 摘要 + 人物   │ ✅ RAG 检索
L4 上下文桥接 │ MD     │ 上一章摘要 + 结尾    │ ✅ 固定注入
L5 当前输入   │ 文本   │ 标题、摘要、指令     │ ❌ 不检索
```

**核心价值**：
- L1 作为**不可变约束**，保证世界观一致
- L2-L3 通过 RAG **动态召回**相关内容
- L4 保证**衔接自然**

### 3.2 "人味"写作技法

| 技法 | 说明 |
|------|------|
| **语言呼吸感** | 短句长句交替，偶尔不完整句 |
| **角色不完美** | 说话说一半忘记，紧张时无意义小动作 |
| **细节偏执** | 不用"温暖的阳光"，用"阳光照在脸上，让人想起小时候发烧时盖的那床毛毯" |
| **情绪复杂性** | 愤怒里有委屈，悲伤里有解脱 |
| **对话潜台词** | "你还好吗？" → "你还爱我吗？" |

**反 AI 味检查清单**：
- [ ] 听起来像教科书吗？
- [ ] 太多"然而""因此""显然"吗？
- [ ] 角色反应太完美、太理智了吗？
- [ ] 有让人意外但又合理的细节吗？
- [ ] 读起来有节奏感吗？

### 3.3 各阶段温度控制

| 阶段 | 温度 | 目的 |
|------|------|------|
| 概念对话 | 0.8 | 发散思维 |
| 蓝图生成 | 0.3 | 结构稳定 |
| 章节生成 | **0.9** | 创意表达 |
| 章节评审 | 0.3 | 理性分析 |
| 摘要提取 | 0.15 | 精确提炼 |

---

## 四、Letta 的优势

### 4.1 三层记忆架构

| 层级 | 位置 | 大小 | 检索 | 用途 |
|------|------|------|------|------|
| **Core Memory** | 始终在 context | 有限 | 直接可见 | persona/human/scenario |
| **Recall Memory** | 外部数据库 | 对话历史 | 混合检索 | 过往对话搜索 |
| **Archival Memory** | 外部数据库 | 无限 | 语义检索 | 长期知识存储 |

**核心价值**：
- Core 保证**关键信息始终可见**
- Recall/Archival 按需检索，**无限扩展**

### 4.2 自主记忆编辑

Agent 拥有**编辑自己记忆的权限**：

| 工具 | 用途 |
|------|------|
| `core_memory_append` | 追加内容到指定 Core Memory block |
| `core_memory_replace` | 在指定 Core Memory block 内精确替换 |
| `memory_replace` | 更强校验的精确替换（例如拒绝行号前缀） |
| `memory_insert` | 行插入 |
| `memory_rethink` | 重写整块（大规模重组） |
| `memory_apply_patch` | Unified Diff 方式应用补丁 |
| `memory_finish_edits` | 标记编辑完成 |

**核心价值**：Agent 自己决定**记住什么、忘记什么、如何组织**

### 4.3 Sleeptime Agent（后台学习）

```
┌────────────────────────────────────────────────┐
│  用户对话                                       │
│  User → [Foreground Agent] → Response          │
│              ↓                                  │
│         对话完成后（可配置频率）                 │
│              ↓                                  │
│  [Sleeptime Agent] 后台异步处理                 │
│         ↓                                       │
│  分析对话 → 提取关键信息 → 更新 Memory Blocks   │
└────────────────────────────────────────────────┘
```

**核心价值**：
- 记忆管理与主对话**解耦**
- 用户无感知的**持续学习**
- 可配置触发频率

### 4.4 Inner Monologue（内心独白）

```
Agent Response
├── inner_thoughts（私密，用户不可见）
│     → 规划、反思、个人成长
│     → 限制 50 词
└── send_message（公开，用户可见）
      → 实际发送给用户的消息
```

**核心价值**：
- 分离"思考"与"表达"
- 角色可以有**隐藏的想法和动机**
- 增强角色扮演的**沉浸感**

### 4.5 System Prompt 编译化（Memory + Sources + Metadata）

Letta 不只是在“对话前拼接 prompt”，而是把系统提示词做成**编译管线**：

- 使用 `{CORE_MEMORY}` 作为注入点（保留变量 `IN_CONTEXT_MEMORY_KEYWORD = "CORE_MEMORY"`）；若缺失则可自动追加，保证记忆不丢。
- `in_context_memory.compile(...)` 会把 Core Memory Blocks、`tool_usage_rules`（工具规则块）、`directories`（资料源/文件块）统一编译为结构化片段。
- 再追加 `<memory_metadata>`（当前系统日期、记忆最后编辑时间、recall 条数、archival 数量与 tags 等），让模型“知道还有哪些外部信息可检索”。

### 4.6 Token/稳定性护栏（可控退化）

Letta 为长对话与工具链引入了多层“工程级护栏”，核心目标是**成本可控 + 持续可用**：

- **Tool 输出截断**：工具返回按 `tool.return_char_limit` 做硬截断，避免检索/文件内容把上下文炸穿。
- **Summarizer 溢出兜底**：摘要溢出时，先对工具返回做截断（clamp），再对 transcript 做预算截断（middle truncate）后重试。
- **递归/污染防护**：对话检索会过滤 tool 消息与递归调用的检索消息；记忆编辑工具拒绝带行号前缀与 line-number warning 的输入。
- **Max Steps**：通过 `DEFAULT_MAX_STEPS` 限制 agent loop，避免意外循环导致 token 成本失控。

### 4.7 Tool Usage Rules（工具治理 / 工作流约束层）

Letta 支持将一组 Tool Rules 编译为 `<tool_usage_rules>` 注入 system prompt，用于把“工作流约束”显式固化（例如：某工具每步最多调用次数、退出前必须完成某动作、需要审批的工具等）。

### 4.8 检索后端与相关性信号（可解释）

Recall/Archival 检索支持不同后端与搜索模式（如 SQL / Turbopuffer，vector/fts/hybrid），并在结果中携带相关性 metadata（如 `rrf_score/vector_rank/fts_rank/search_mode`），便于解释与二次重排。

---

## 五、整合建议：最佳实践组合

### 5.1 分层记忆系统（融合 Letta + Arboris）

```
┌─────────────────────────────────────────────────────────────┐
│ L0: System Prompt                                           │
│     全局指令、模型适配 + {CORE_MEMORY} 注入点                 │
├─────────────────────────────────────────────────────────────┤
│ L1: Core Memory Blocks（始终可见）                          │
│     ├── persona（AI 角色定义）                              │
│     ├── human（用户信息）                                   │
│     ├── scenario（当前场景）                                │
│     └── [custom]（自定义块）                                │
├─────────────────────────────────────────────────────────────┤
│ L2: World Info（关键词触发）                                │
│     按需注入世界观、角色关系、事件细节                       │
├─────────────────────────────────────────────────────────────┤
│ L3: Context Bridge（固定注入）                              │
│     上一段摘要 + 结尾 300-500 字                            │
├─────────────────────────────────────────────────────────────┤
│ L4: Chat History（动态裁剪）                                │
│     根据进度调整保留条数                                     │
│     @Depth N: Author's Note                                 │
├─────────────────────────────────────────────────────────────┤
│ L5: User Input                                              │
└─────────────────────────────────────────────────────────────┘
```

> 注：如果对话支持“分支/树状线程”，所有裁剪/摘要/检索应基于当前 active chain（避免把未选分支内容混入上下文）。

### 5.2 记忆管理策略（融合全部）

| 策略 | 来源 | 实现 |
|------|------|------|
| **关键词触发注入** | ST World Info | 扫描最近 N 条消息，匹配关键词 |
| **持续锚定** | ST Author's Note | 在指定深度按频率注入当前情节提醒 |
| **动态裁剪** | MuMu RTCO | 根据对话轮次调整上下文复杂度 |
| **自动摘要** | Arboris + Letta | 上下文超限时生成摘要 |
| **自主编辑** | Letta | Agent 可通过工具编辑记忆块 |
| **后台学习** | Letta Sleeptime | 对话后异步更新记忆（可选） |
| **工具治理** | Letta Tool Rules | 将工具使用约束编译注入系统提示词 |
| **工具输出截断** | Letta | 限制工具返回字符数，避免 token 爆炸 |
| **摘要溢出兜底** | Letta Summarizer | clamp 工具输出 + transcript 截断重试 |
| **资料源窗口** | Letta Directories/File Blocks | 目录 + open/closed 文件块，限制 max_files_open |

### 5.3 角色一致性保障（融合 ST + Letta）

```dart
class RoleCard {
  // === Core Memory Blocks ===
  MemoryBlock persona;        // 角色定义（始终可见）
  MemoryBlock scenario;       // 场景设定

  // === ST Character Card ===
  String description;         // 详细描述
  String personality;         // 性格摘要
  String firstMessage;        // 开场白
  String exampleDialogue;     // Few-shot 示例

  // === 高级字段 ===
  String? depthPrompt;        // 深度注入内容
  int? depthPromptDepth;      // 深度注入位置
  String? authorsNote;        // Author's Note
  int authorsNoteDepth;       // AN 深度（可配置）
}
```

### 5.4 创作质量保障（Arboris）

1. **"人味"写作提示词**：融入系统提示词
2. **温度分场景控制**：创作 0.9，摘要 0.15
3. **反 AI 味检查**：可作为可选的后处理检查

---

## 六、实现优先级建议

### MVP（核心功能）

| 优先级 | 功能 | 来源 | 复杂度 |
|--------|------|------|--------|
| P0 | **Author's Note** | ST | 低 |
| P0 | **角色卡增强**（description/personality/scenario） | ST | 低 |
| P0 | **Memory Blocks 基础**（persona/human） | Letta | 低 |
| P0 | **Tool 输出截断**（工具结果字符上限） | Letta | 低 |
| P1 | **World Info MVP**（关键词触发） | ST | 中 |
| P1 | **衔接锚点**（上段结尾 300-500 字） | MuMu/Arboris | 低 |
| P1 | **System Prompt 编译化**（{CORE_MEMORY} + memory_metadata） | Letta | 中 |

### 进阶功能

| 优先级 | 功能 | 来源 | 复杂度 |
|--------|------|------|--------|
| P2 | 自动记忆摘要 | Arboris/Letta | 中 |
| P2 | 自主记忆编辑工具 | Letta | 中 |
| P2 | 对话历史语义搜索 | Letta Recall | 高 |
| P2 | 工具治理（Tool Usage Rules） | Letta | 中 |
| P3 | 伏笔追踪系统 | MuMu | 高 |
| P3 | Sleeptime Agent 后台学习 | Letta | 高 |
| P3 | 归档记忆（无限存储） | Letta Archival | 高 |

---

## 七、一句话总结

| 项目 | 核心贡献 |
|------|----------|
| **SillyTavern** | 关键词触发注入 + 深度锚定 + 结构化角色卡 |
| **MuMuAINovel** | 优先级裁剪 + 动态复杂度 + 伏笔追踪 |
| **Arboris-Novel** | 五层架构 + RAG 检索 + "人味"写作 |
| **Letta** | 三层记忆 + 自主编辑 + 后台学习 + 编译化注入与护栏 |

**整合后的核心理念**：

> 分层记忆 + 按需注入 + 动态裁剪 + 可控退化 + 自主管理 = 更接近“无限上下文”的角色扮演体验
