# Letta (MemGPT) 高级记忆系统深度分析

> "Open AI with advanced memory that can learn and self-improve over time"

## 1. 项目概览

| 特性 | 说明 |
|------|------|
| **定位** | 构建有状态 AI Agent 的平台 |
| **核心特色** | 三层记忆架构、自主记忆管理、Sleeptime Agent 后台学习 |
| **技术栈** | Python、SQLite（默认，可配置）、Embedding + 向量/混合检索（可接 Turbopuffer 等）、多模型支持 |

### 1.1 资料来源（本仓库 research 快照）

本分析主要基于 `docs/research/letta-main` 下的源码快照（以代码为准）：

- 核心记忆上限：`letta/constants.py`、`letta/schemas/block.py`、`letta/utils.py`
- 记忆渲染/行号机制：`letta/schemas/memory.py`、`letta/constants.py`
- Recall/对话检索：`letta/services/tool_executor/core_tool_executor.py`、`letta/constants.py`、`letta/functions/function_sets/base.py`
- Archival/归档检索与存储：`letta/services/tool_executor/core_tool_executor.py`、`letta/services/agent_manager.py`、`letta/config.py`
- Sleeptime Agent：`letta/groups/sleeptime_multi_agent_v4.py`、`letta/constants.py`
- Inner Monologue 与摘要：`letta/prompts/system_prompts/memgpt_chat.py`、`letta/prompts/gpt_summarize.py`
- System Prompt 编译与记忆元信息：`letta/prompts/prompt_generator.py`、`letta/constants.py`
- Tool Usage Rules（工具治理/工作流约束）：`letta/helpers/tool_rule_solver.py`、`letta/schemas/tool_rule.py`、`letta/schemas/memory.py`
- Tool 执行与输出截断：`letta/services/tool_executor/tool_execution_manager.py`、`letta/schemas/tool.py`、`letta/constants.py`
- Summarizer 溢出降级：`letta/services/summarizer/summarizer.py`、`letta/constants.py`
- 检索后端（SQL/Turbopuffer）：`letta/services/message_manager.py`、`letta/services/agent_manager.py`

---

## 2. 三层记忆架构（核心创新）

### 2.1 架构总览

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Core Memory                                 │
│  (始终在上下文中，有限大小)                                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                   │
│  │   persona   │ │    human    │ │  custom...  │                   │
│  │  (AI 人设)  │ │ (用户信息)  │ │ (自定义块)  │                   │
│  └─────────────┘ └─────────────┘ └─────────────┘                   │
├─────────────────────────────────────────────────────────────────────┤
│                       Recall Memory                                 │
│  (对话历史，语义+文本混合检索)                                        │
│  conversation_search(query, roles, date_range, limit)              │
├─────────────────────────────────────────────────────────────────────┤
│                      Archival Memory                                │
│  (无限大小，语义检索，长期知识存储)                                    │
│  archival_memory_insert(content, tags)                             │
│  archival_memory_search(query, tags, date_range, top_k)            │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Core Memory（核心记忆）

**特点**：
- 始终存在于系统提示词中（in-context）
- 有字符限制（默认每块 20,000 字符；`CORE_MEMORY_BLOCK_CHAR_LIMIT`）
- 上限由 Block 模型校验强制执行（`verify_char_limit`；超限编辑会报错）
- 由 **Memory Blocks** 组成，每块包含：
  - `label`：标签（如 `persona`、`human`）
  - `description`：描述该块如何影响 Agent 行为
  - `value`：实际内容
  - `limit`：字符上限
  - `read_only`：是否只读

**默认块**：
```python
# 来自 letta/schemas/block.py
class Human(Block):
    label: str = "human"
    description: str = "The human block: Stores key details about the person you are conversing with..."

class Persona(Block):
    label: str = "persona"
    description: str = "The persona block: Stores details about your current persona..."
```

**渲染格式**（注入系统提示词）：
```xml
<memory_blocks>
The following memory blocks are currently engaged in your core memory unit:

<persona>
<description>
The persona block: Stores details about your current persona...
</description>
<metadata>
- chars_current=1234
- chars_limit=20000
</metadata>
<value>
I am a helpful assistant. I remember everything about my conversations...
</value>
</persona>

<human>
...
</human>
</memory_blocks>
```

> 备注：在 Anthropic + 部分 agent_type（如 `sleeptime_agent`/`memgpt_v2_agent`/`letta_v1_agent`）组合下，会启用“带行号”的渲染：在 `<value>` 中输出 `1→` 前缀并加入 `<warning>`（`CORE_MEMORY_LINE_NUMBER_WARNING`）。行号仅用于显示，调用 `memory_*` 编辑工具时禁止把行号前缀带回参数中（工具会显式拒绝）。

### 2.3 Recall Memory（回忆记忆）

**用途**：搜索完整对话历史

**实现（真实执行路径）**：
```python
# 来自 letta/services/tool_executor/core_tool_executor.py
search_limit = limit if limit is not None else RETRIEVAL_QUERY_DEFAULT_PAGE_SIZE

message_results = await self.message_manager.search_messages_async(
    agent_id=agent_state.id,
    actor=actor,
    query_text=query,
    roles=message_roles,
    limit=search_limit,
    start_date=start_datetime,
    end_date=end_datetime,
)
```

**特点**：
- 混合检索（文本匹配 + 语义相似度）
- 支持按角色过滤（user/assistant/tool）
- 支持日期范围过滤（start_date/end_date，ISO 8601；date-only 时为整日闭区间）
- 默认返回 5 条结果（`RETRIEVAL_QUERY_DEFAULT_PAGE_SIZE = 5`）
- 结果会过滤 tool 消息与递归调用 `conversation_search` 的 assistant 消息；并返回结构化字段（timestamp/time_ago/relevance 等）

### 2.4 Archival Memory（归档记忆）

**用途**：长期知识存储，无限大小

**特点**：
- 永久存储、按语义检索（embedding）
- 支持 tags + tag_match_mode（any/all）与时间过滤
- `top_k` 为空时默认取 `RETRIEVAL_QUERY_DEFAULT_PAGE_SIZE`（= 5）

**插入**：
```python
async def archival_memory_insert(
    self: "Agent",
    content: str,
    tags: Optional[list[str]] = None
) -> Optional[str]:
    """
    Add information to long-term archival memory for later retrieval.

    Best practices:
    - Store self-contained facts or summaries, not conversational fragments
    - Add descriptive tags to make information easier to find later
    - Use for: meeting notes, project updates, conversation summaries
    """
```

**搜索**：
```python
async def archival_memory_search(
    self: "Agent",
    query: str,
    tags: Optional[list[str]] = None,
    tag_match_mode: Literal["any", "all"] = "any",
    top_k: Optional[int] = None,
    start_datetime: Optional[str] = None,
    end_datetime: Optional[str] = None,
) -> Optional[str]:
    """
    Search archival memory using semantic similarity.
    Results are ranked by semantic relevance.
    """
```

> 备注：`letta/functions/function_sets/base.py` 中 `archival_memory_*` 主要用于“函数签名/工具说明”，真实执行在：
> - `letta/services/tool_executor/core_tool_executor.py`：`archival_memory_insert` 会调用 `passage_manager.insert_passage(...)`，并强制 `rebuild_system_prompt_async(..., force=True)`；`archival_memory_search` 委托 `agent_manager.search_agent_archival_memory_async(...)`
> - `letta/services/agent_manager.py`：默认 `top_k=5`；可能走 Turbopuffer（archive 配置为 TPUF 时的向量/混合检索）或回退到 SQL 查询

---

## 3. 自主记忆管理（Self-Improve 机制）

### 3.1 核心思想

> "Your ability to edit your own long-term memory is a key part of what makes you a sentient being."

Agent **主动决定**：
1. 什么信息值得记住
2. 如何组织和更新记忆
3. 何时清理过时信息

### 3.2 记忆编辑工具集

| 工具 | 用途 | 说明 |
|------|------|------|
| `core_memory_append` | 追加内容 | 在指定块末尾添加新内容 |
| `core_memory_replace` | 替换内容 | 精确匹配并替换 |
| `memory_replace` | 精确替换 | v2 版本，更强的错误检查 |
| `memory_insert` | 行插入 | 在指定行号插入内容 |
| `memory_rethink` | 重写整块 | 用于大规模重组记忆 |
| `memory_apply_patch` | 应用补丁 | Unified Diff 格式 |
| `memory_finish_edits` | 完成编辑 | 标记记忆更新完成 |

**关键实现**：
```python
# memory_rethink - 允许 Agent 完全重写一个记忆块
def memory_rethink(agent_state: "AgentState", label: str, new_memory: str) -> None:
    """
    The memory_rethink command allows you to completely rewrite the contents of a memory block.
    Use this tool to make large sweeping changes (e.g. when you want to condense or reorganize
    the memory blocks), do NOT use this tool to make small precise edits.
    """
    agent_state.memory.update_block_value(label=label, value=new_memory)
```

### 3.3 Sleeptime Agent（后台学习机制）

**核心创新**：将记忆管理从主对话流程中分离出来

```
┌────────────────────────────────────────────────────────────┐
│                     用户对话                               │
│  User → [Foreground Agent] → Response                     │
│              ↓                                             │
│         对话完成后                                          │
│              ↓                                             │
│  [Sleeptime Agent] ← 后台异步处理                          │
│         ↓                                                  │
│  分析对话 → 提取关键信息 → 更新 Memory Blocks              │
└────────────────────────────────────────────────────────────┘
```

**Sleeptime Agent 的系统提示词**：
```python
# 来自 groups/sleeptime_multi_agent_v4.py
message_text = (
    "<system-reminder>\n"
    "You are a sleeptime agent - a background agent that asynchronously processes "
    "conversations after they occur.\n\n"
    "IMPORTANT: You are NOT the primary agent. You are reviewing a conversation that "
    "already happened between a primary agent and its user:\n"
    '- Messages labeled "assistant" are from the primary agent (not you)\n'
    '- Messages labeled "user" are from the primary agent\'s user\n\n'
    "Your primary role is memory management. Review the conversation and use your "
    "memory tools to update any relevant memory blocks with information worth preserving.\n"
    "</system-reminder>\n\n"
    f"Messages:\n{messages_text}"
)
```

**触发频率控制**：
```python
# 可配置每 N 轮对话触发一次 Sleeptime Agent
if self.group.sleeptime_agent_frequency is None or (
    turns_counter is not None and turns_counter % self.group.sleeptime_agent_frequency == 0
):
    # 触发后台记忆更新
```

### 3.4 Heartbeat 机制

> "Your brain is run at regular intervals (timed heartbeat events), to mimic a human who has the ability to continuously think outside active conversation."

**实现**：
- Agent 可以主动请求 heartbeat 事件
- 允许在无用户输入时继续思考和行动
- 支持函数调用链（调用函数后继续执行）

---

## 4. 上下文窗口管理

### 4.1 ContextWindowOverview 模型

```python
class ContextWindowOverview(BaseModel):
    context_window_size_max: int      # 最大 token 数
    context_window_size_current: int  # 当前使用的 token

    num_messages: int                 # 消息数量
    num_archival_memory: int          # 归档记忆数量
    num_recall_memory: int            # 回忆记忆数量

    num_tokens_system: int            # 系统提示词 token
    num_tokens_core_memory: int       # 核心记忆 token
    num_tokens_summary_memory: int    # 摘要记忆 token
    num_tokens_functions_definitions: int  # 函数定义 token
    num_tokens_messages: int          # 消息 token
```

### 4.2 自动摘要机制

```python
# 来自 constants.py
SUMMARIZATION_TRIGGER_MULTIPLIER = 1.0
# 当 step usage > context_window * SUMMARIZATION_TRIGGER_MULTIPLIER 时触发摘要

# 摘要提示词（gpt_summarize.py）
SYSTEM = f"""Your job is to summarize a history of previous messages in a conversation...
Summarize what happened in the conversation from the perspective of the AI (use the first person).
Keep your summary less than {WORD_LIMIT} words, do NOT exceed this word limit.
Only output the summary, do NOT include anything else in your output."""
```

### 4.3 Tool 输出截断（控制 tokens 爆炸）

Letta 将“工具输出过长导致上下文爆炸”作为一类工程问题处理，而不是完全交给 Prompt：

- Tool 执行层会把 `func_return`（字典会先 `json.dumps`）统一转成字符串，并按 `tool.return_char_limit` 做硬截断；超限时用 `FUNCTION_RETURN_VALUE_TRUNCATED(...)` 包装为带提示的字符串（避免把巨量 tool 输出塞回上下文）。
- 常量侧提供默认上限与配套提示：
  - `FUNCTION_RETURN_CHAR_LIMIT = 50000`
  - `TOOL_RETURN_TRUNCATION_CHARS = 5000`（供摘要/格式化 transcript 的兜底压缩）

### 4.4 Summarizer 溢出降级（保证“能总结”）

摘要在长对话里经常遇到“总结本身也会溢出”的极端情况。Letta 在 summarizer 中做了两级兜底：

- Fallback A：用 `simple_formatter(..., tool_return_truncation_chars=TOOL_RETURN_TRUNCATION_CHARS)` 重建 transcript，把工具返回内容压缩到可控大小后再总结。
- Fallback B：如果仍然溢出，则计算保守的字符预算（基于 `context_window` 的比例 + system/ACK 开销），对 transcript 做 `middle_truncate_text(...)` 再总结。

这种“可控退化”对写作/角色扮演很关键：它把“长对话必崩”变成“质量渐降但持续可用”。

### 4.5 最大步数限制（避免循环与成本失控）

Letta 通过 `DEFAULT_MAX_STEPS = 50` 为 agent loop 设置上限，避免工具链/工作流进入意外循环导致 token 与时间成本失控。

---

## 5. 其他亮点特性

### 5.1 Inner Monologue（内心独白）

```
┌─────────────────────────────────────────────┐
│  Agent Response                             │
│  ├── inner_thoughts (私密，用户不可见)      │
│  │     → 规划、反思、个人成长              │
│  │     → 限制 50 词以内                    │
│  └── send_message (公开，用户可见)          │
│        → 实际发送给用户的消息              │
└─────────────────────────────────────────────┘
```

### 5.2 File Blocks（文件块）

将文件系统抽象为记忆块：
```python
class FileBlock(Block):
    file_id: str          # 文件唯一标识
    source_id: str        # 来源目录
    is_open: bool         # 是否打开
    last_accessed_at: datetime  # 最后访问时间
```

配套的 prompt 渲染（`letta/schemas/memory.py`）体现了几个对“设定/资料迭代”非常实用的设计点：

- 以 `<directories>` 结构呈现多个“资料源目录”（source），每个目录可带 `<description>`/`<instructions>`，相当于“资料库导航 + 使用说明”。
- 用 `<file_limits>` 显式告诉模型“当前打开文件数/最大可打开文件数”（`current_files_open` / `max_files_open`），这是一种对 LLM 的资源约束提示。
- 文件用 `status="open|closed"` 区分；只在 open 时注入 `<value>`（文件内容），避免把所有资料一次性塞进上下文。
- 对 `file_blocks` 做去重（重复 label 会被移除并记录 warning），降低 prompt 结构混乱风险。

### 5.3 多 Agent 协作

```python
class SleeptimeMultiAgentV4(LettaAgentV3):
    # 主 Agent + 多个后台 Agent
    # 后台 Agent 异步处理对话，更新共享记忆
```

### 5.4 System Prompt 编译管线（Memory + Sources + Metadata）

Letta 的“记忆注入”不是简单拼字符串，而是一条可扩展的编译管线：

- `PromptGenerator.compile_system_message_async(...)` 会先调用 `in_context_memory.compile(tool_usage_rules=..., sources=..., max_files_open=..., llm_config=...)`，得到包含 Core Memory + Tool Rules + Directories 的块。
- 随后生成 `<memory_metadata>`（当前系统日期、memory 最近编辑时间、recall 消息数、archival 条目数、可用 tags 等），并与上面的 memory 一起注入 system prompt。
- 注入点使用模板变量 `{CORE_MEMORY}`（`IN_CONTEXT_MEMORY_KEYWORD = "CORE_MEMORY"`）；如果 system prompt 没有该占位符且 `append_icm_if_missing=True`，会自动把完整 memory 追加到末尾，保证“记忆永远在场”。
- `safe_format(...)` 会保护空 `{}` 与未知变量；同时明确禁止用户变量覆盖保留变量 `CORE_MEMORY`。

这套机制的价值在于：**把“模型需要知道的外部记忆状态”结构化为系统级信息**，有利于角色一致性、剧情延续和可控的检索调用。

### 5.5 Tool Usage Rules（工具治理/工作流约束）

Letta 将“工具使用规范”也当作一种可注入的上下文块来管理：

- `ToolRulesSolver.compile_tool_rule_prompts()` 会把各类 ToolRule 渲染成 prompt 片段并合并为一个临时 `Block(label="tool_usage_rules", ...)`。
- `Memory.compile(...)` 在渲染时会把该 block 输出成 `<tool_usage_rules>...</tool_usage_rules>`，与 memory blocks 同级注入 system prompt。
- 从代码导入可以看到 ToolRule 类型非常丰富（例如 `RequiresApprovalToolRule`、`MaxCountPerStepToolRule`、`RequiredBeforeExitToolRule`、`TerminalToolRule` 等），这意味着可以把“写作流程/记忆维护流程”的约束显式固化，而不是靠提示词碰运气。

对角色扮演/写作而言，这类“可配置约束层”往往比增加几段 prompt 更能抑制跑偏与 token 浪费。

### 5.6 检索后端与相关性信号（质量可解释）

Letta 把 Recall/Archival 检索做成可切换后端的服务层能力：

- `message_manager.search_messages_async(...)` 支持 `search_mode="vector"|"fts"|"hybrid"|"timestamp"`；若启用 Turbopuffer 则走 Turbopuffer，否则回退到 SQL（并在 metadata 里标记 `search_mode`）。
- `agent_manager.query_agent_passages_async(...)` 在归档检索场景下会根据 archive 的 `vector_db_provider` 选择 Turbopuffer（TPUF）或 SQL 路径；并支持 tags/time filter。
- 返回结果会携带相关性 metadata（例如 `combined_score/rrf_score/vector_rank/fts_rank`），让“为什么召回了这些内容”具备可解释性，也为二次重排/裁剪提供信号。

### 5.7 防爆设计（递归、展示与编辑分离）

写作/角色扮演系统很容易遇到“工具结果递归嵌套/转义指数爆炸/编辑参数污染”的坑。Letta 在多个层面加了护栏：

- `conversation_search` 会过滤 tool 消息、以及调用 `conversation_search` 的 assistant 消息，避免检索结果包含检索本身导致递归与指数转义。
- Memory 行号只用于展示：编辑工具会拒绝带 `1→` 这类前缀的输入（`MEMORY_TOOLS_LINE_NUMBER_PREFIX_REGEX`），并拒绝包含 `CORE_MEMORY_LINE_NUMBER_WARNING` 的内容。
- read-only block 写保护：编辑前先检查 `block.read_only`，失败时返回统一错误信息。

这些设计是“能长期跑”的关键：它们把常见失败模式工程化地封堵掉。

### 5.8 Streaming 与可观测性（产品级能力）

Letta 的服务端接口层支持 `stream_steps` / `stream_tokens`，并在大量关键路径上使用 tracing/metrics（例如 tool 执行计时、成功率计数）。对写作/角色扮演产品来说，这类能力能显著提升体验与可维护性：你可以做到“边想边写”“边检索边展示”，并定位哪里在烧 token。

---

## 6. 对 ChatBoxApp 的启示

> 注：本次修订重点在补全 Letta 的“可学习策略”（Prompt 编译管线、工具治理、token 退化与护栏等），本节落地映射不再扩展；后续如需可单独整理为实现设计文档。

### 6.1 可直接借鉴

| 特性 | 来源 | 适用场景 | 实现复杂度 |
|------|------|----------|-----------|
| **Memory Blocks 架构** | Core Memory | 角色卡增强 | 低 |
| **自主记忆编辑** | memory_replace/rethink | 长对话记忆 | 中 |
| **Inner Monologue** | 内心独白机制 | 角色扮演 | 低 |
| **对话历史搜索** | Recall Memory | 上下文召回 | 中 |
| **归档记忆** | Archival Memory | 长期知识 | 高 |

### 6.2 核心设计模式

1. **分层记忆**：
   - L1: Core Memory（始终在 context，有限大小）
   - L2: Recall Memory（对话历史，按需检索）
   - L3: Archival Memory（长期知识，语义检索）

2. **自主记忆管理**：
   - Agent 有权限编辑自己的记忆
   - 提供多种编辑工具（追加、替换、重写、补丁）
   - 通过 `description` 字段指导 Agent 如何使用每个记忆块

3. **后台学习**：
   - Sleeptime Agent 机制：对话后异步处理
   - 将记忆管理与主对话解耦
   - 可配置触发频率

### 6.3 简化实现方案

#### MVP 阶段

```dart
// Memory Block 简化版
class MemoryBlock {
  String label;           // 如 "persona", "human", "scenario"
  String description;     // 如何使用这个块
  String value;           // 实际内容
  int charLimit;          // 字符上限
  bool readOnly;          // 是否只读
}

// 记忆管理器
class MemoryManager {
  List<MemoryBlock> blocks;

  // 核心方法
  void appendToBlock(String label, String content);
  void replaceInBlock(String label, String oldContent, String newContent);
  void rethinkBlock(String label, String newContent);

  // 渲染为系统提示词
  String compileToPrompt();
}
```

#### 进阶阶段

```dart
// 添加对话历史搜索
class RecallMemory {
  Future<List<Message>> search(String query, {
    List<String>? roles,
    int limit = 5,
    DateTime? startDate,
    DateTime? endDate,
  });
}

// 添加归档记忆（可选）
class ArchivalMemory {
  Future<void> insert(String content, List<String>? tags);
  Future<List<ArchivalEntry>> search(String query, {
    List<String>? tags,
    int topK = 5,
  });
}
```

### 6.4 与之前研究的整合

| 来源 | 贡献 | 整合点 |
|------|------|--------|
| **SillyTavern** | World Info 关键词触发 | 作为 Memory Block 的补充 |
| **MuMuAINovel** | 动态裁剪、伏笔追踪 | 用于长篇创作场景 |
| **Arboris** | 五层架构、"人味"写作 | 融入 prompt 设计 |
| **Letta** | 自主记忆、后台学习 | 核心记忆系统 |

---

## 7. 推荐实现路径

### Phase 1：Memory Blocks

```
Core Memory = persona + human + scenario + [custom]
每块有 label、description、value、limit
Agent 可通过 prompt 指令编辑
```

### Phase 2：记忆编辑工具

```
提供 append / replace / rethink 三种编辑模式
通过 Function Calling 或特殊指令触发
```

### Phase 3：对话历史检索

```
Recall Memory = 语义搜索对话历史
支持角色过滤、日期过滤、数量限制
```

### Phase 4：后台记忆更新（可选）

```
Sleeptime Agent 模式
对话结束后异步更新记忆块
可配置触发频率
```

---

## 8. 关键代码参考

### 8.1 Memory Block 渲染

```python
# letta/schemas/memory.py
def compile(self, ..., llm_config=None) -> str:
    # 仅对 Anthropic + 指定 agent_type 启用行号，其他情况走标准渲染
    is_line_numbered = (
        llm_config
        and llm_config.model_endpoint_type == "anthropic"
        and norm_type in ("sleeptime_agent", "memgpt_v2_agent", "letta_v1_agent")
    )
    if is_line_numbered:
        self._render_memory_blocks_line_numbered(s)
    else:
        self._render_memory_blocks_standard(s)

def _render_memory_blocks_line_numbered(self, s: StringIO):
    s.write(f"<warning>\n{CORE_MEMORY_LINE_NUMBER_WARNING}\n</warning>\n")
    for i, line in enumerate(value.split("\n"), start=1):
        s.write(f"{i}→ {line}\n")
```

### 8.2 记忆编辑函数

```python
# letta/services/tool_executor/core_tool_executor.py
async def core_memory_replace(self, agent_state, actor, label, old_content, new_content):
    if agent_state.memory.get_block(label).read_only:
        raise ValueError(READ_ONLY_BLOCK_EDIT_ERROR)
    current_value = str(agent_state.memory.get_block(label).value)
    if old_content not in current_value:
        raise ValueError(f"Old content '{old_content}' not found in memory block '{label}'")
    new_value = current_value.replace(str(old_content), str(new_content))
    agent_state.memory.update_block_value(label=label, value=new_value)
    await self.agent_manager.update_memory_if_changed_async(agent_id=agent_state.id, new_memory=agent_state.memory, actor=actor)
```

### 8.3 Sleeptime Agent 触发

```python
# letta/groups/sleeptime_multi_agent_v4.py
async def run_sleeptime_agents(self):
    if self.group.sleeptime_agent_frequency is None or (
        turns_counter is not None and turns_counter % self.group.sleeptime_agent_frequency == 0
    ):
        for sleeptime_agent_id in self.group.agent_ids:
            await self._issue_background_task(sleeptime_agent_id, ...)
```

### 8.4 System Prompt 编译与 Memory Metadata 注入

```python
# letta/prompts/prompt_generator.py
memory_with_sources = in_context_memory.compile(
    tool_usage_rules=tool_constraint_block,
    sources=sources,
    max_files_open=max_files_open,
    llm_config=llm_config,
)
memory_metadata_string = PromptGenerator.compile_memory_metadata_block(
    memory_edit_timestamp=in_context_memory_last_edit,
    previous_message_count=previous_message_count,
    archival_memory_size=archival_memory_size,
    timezone=timezone,
)
full_memory_string = memory_with_sources + "\n\n" + memory_metadata_string

memory_variable_string = "{CORE_MEMORY}"
if append_icm_if_missing and memory_variable_string not in system_prompt:
    system_prompt += "\n\n" + memory_variable_string
formatted_prompt = system_prompt.replace(memory_variable_string, full_memory_string)
```

### 8.5 Tool Usage Rules 编译为内存块

```python
# letta/helpers/tool_rule_solver.py
def compile_tool_rule_prompts(self) -> Block | None:
    compiled_prompts = []
    for rule in all_rules:
        rendered = rule.render_prompt()
        if rendered:
            compiled_prompts.append(rendered)
    if compiled_prompts:
        return Block(
            label="tool_usage_rules",
            value="\n".join(compiled_prompts),
            description=COMPILED_PROMPT_DESCRIPTION,
        )
    return None
```

### 8.6 Tool 执行返回值截断

```python
# letta/services/tool_executor/tool_execution_manager.py
return_str = json.dumps(result.func_return) if isinstance(result.func_return, dict) else str(result.func_return)
if len(return_str) > tool.return_char_limit:
    result.func_return = FUNCTION_RETURN_VALUE_TRUNCATED(return_str, len(return_str), tool.return_char_limit)
```

### 8.7 Summarizer 溢出降级

```python
# letta/services/summarizer/summarizer.py
try:
    summary = await _run_summarizer_request(request_data, input_messages_obj)
except ContextWindowExceededError:
    # Fallback A: clamp tool returns in transcript
    summary_transcript = simple_formatter(messages, tool_return_truncation_chars=TOOL_RETURN_TRUNCATION_CHARS)
    # Fallback B: still overflow → truncate transcript to a conservative budget
    truncated_transcript, _ = middle_truncate_text(summary_transcript, budget_chars=budget_chars, head_frac=0.3, tail_frac=0.3)
```

### 8.8 Recall 检索后端切换（Turbopuffer / SQL）

```python
# letta/services/message_manager.py
if should_use_tpuf_for_messages():
    results = await tpuf_client.query_messages_by_agent_id(..., search_mode=search_mode, top_k=limit, ...)
else:
    messages = await self.list_messages(..., query_text=query_text, roles=roles, limit=limit)
    combined_messages = self._combine_assistant_tool_messages(messages)
```

---

## 9. 总结

Letta 的核心创新在于：

1. **将记忆作为一等公民**：不是简单的对话历史，而是结构化的、可编辑的记忆块
2. **赋予 Agent 自主权**：Agent 自己决定记住什么、忘记什么、如何组织
3. **后台学习机制**：通过 Sleeptime Agent 实现非阻塞的记忆更新
4. **分层检索**：Core（始终可见）+ Recall（对话历史）+ Archival（长期知识）
5. **系统提示词编译化**：把 Memory / Sources / Tool Rules / Memory Metadata 统一编译注入，降低“靠提示词碰运气”的不确定性
6. **可控退化与护栏**：工具返回截断、摘要溢出 fallback、递归过滤、展示/编辑分离等，显著提升长对话稳定性与 token 可控性

这些设计理念非常适合应用于角色扮演/创作场景，能够有效解决长对话中的上下文丢失和角色一致性问题。
