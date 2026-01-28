# Framework Research Report

> ChatBoxApp 框架集成研究报告
>
> 版本: 1.0 | 日期: 2026-01-24

---

## 1. 研究目标

1. **替换自建组件**: 识别可替换 Provider 层、流式传输、消息处理的成熟框架
2. **RP 实现便利**: 评估框架对上下文组装、记忆管理、版本控制的支持
3. **平台功能扩展**: 研究 MCP 工具集成、知识库/RAG、Function Calling、Web Search 等能力

**约束条件**: RP 后端和 UI 保持自研设计，框架仅用于底层能力替换。

---

## 2. 框架概览

### 2.1 核心框架对比

| 框架 | 类型 | 成熟度 | 适用场景 |
|------|------|--------|----------|
| **LangChain.dart** | LLM 编排 | ⭐⭐⭐⭐ | Provider 层、RAG、Agent、Tool Calling |
| **Flutter AI Toolkit** | UI + LLM | ⭐⭐⭐ | Chat UI、Google AI 集成 |
| **MCP Dart SDK** | 工具协议 | ⭐⭐⭐ | 外部工具集成、标准化工具调用 |
| **sqlite-vec** | 向量存储 | ⭐⭐⭐⭐ | 本地 RAG、Embedding 检索 |

### 2.2 推荐组合

```
┌─────────────────────────────────────────────────────────────┐
│                     ChatBoxApp Architecture                  │
├─────────────────────────────────────────────────────────────┤
│  UI Layer (自研)          │  RP Backend (自研)              │
│  - conversation_view_v2   │  - RpContextCompiler            │
│  - custom widgets         │  - RpMemoryRepository           │
│                           │  - RpWorkerHost                 │
├───────────────────────────┴─────────────────────────────────┤
│                    Orchestration Layer                       │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              LangChain.dart (推荐引入)                   ││
│  │  - ChatModel (多 Provider 支持)                         ││
│  │  - RunnableSequence (LCEL 管道)                         ││
│  │  - ToolSpec (Function Calling)                          ││
│  │  - Retriever (RAG 接口)                                 ││
│  └─────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────┤
│                    Integration Layer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ MCP Client   │  │ sqlite-vec   │  │ Web Search   │      │
│  │ (mcp_client) │  │ (本地向量DB) │  │ (Tavily API) │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. LangChain.dart 详细分析

### 3.1 可用集成

#### Chat Models (7 个 Provider)
| Provider | Package | 状态 | 功能 |
|----------|---------|------|------|
| OpenAI | `langchain_openai` | ✅ 稳定 | GPT-4, GPT-4o, o1, o3 |
| Anthropic | `langchain_anthropic` | ✅ 稳定 | Claude 3.5/4 |
| Google Generative AI | `langchain_google` | ✅ 稳定 | Gemini 2.0 |
| Mistral AI | `langchain_mistralai` | ✅ 稳定 | Mistral Large |
| Ollama | `langchain_ollama` | ✅ 稳定 | 本地模型 |
| Firebase Vertex AI | `langchain_firebase` | ✅ 稳定 | Firebase 集成 |
| Vertex AI | `langchain_google` | ✅ 稳定 | GCP Vertex |

#### Embeddings (5 个 Provider)
- OpenAI Embeddings
- Google Generative AI Embeddings
- Mistral AI Embeddings
- Ollama Embeddings
- Vertex AI Embeddings

#### Vector Stores (6 种)
| 存储 | 特点 | 适用场景 |
|------|------|----------|
| **MemoryVectorStore** | 内存存储，零依赖 | 小规模、临时存储 |
| **ObjectBox** | 本地嵌入式数据库 | Flutter 本地优先 |
| **Chroma** | 开源向量数据库 | 服务端部署 |
| **Pinecone** | 云端向量数据库 | 大规模生产 |
| **Supabase** | PostgreSQL + pgvector | 已有 Supabase 用户 |
| **Vertex AI Matching Engine** | GCP 托管 | GCP 生态 |

#### Document Loaders
- TextLoader, CsvLoader, JsonLoader
- WebBaseLoader (网页抓取)
- DirectoryLoader (批量文件)

#### Tools
- CalculatorTool
- OpenAIDallETool (图片生成)
- TavilyAnswerTool (Web Search)
- TavilySearchResultsTool

### 3.2 对现有项目的影响评估

**结论: 零功能影响**

```dart
// 现有接口
abstract class AIProvider {
  Stream<String> sendMessageStream({...});
}

// LangChain.dart 返回类型
final chain = ChatOpenAI(...);
Stream<ChatResult> stream = chain.stream(prompt);
// 可转换为 Stream<String>

// 适配方案: 内部实现替换，外部接口不变
class LangChainProvider implements AIProvider {
  final BaseChatModel _model;

  @override
  Stream<String> sendMessageStream({...}) async* {
    await for (final chunk in _model.stream(prompt)) {
      yield chunk.output.content;
    }
  }
}
```

### 3.3 迁移策略

**Phase 1: Provider 层替换 (低风险)**
```dart
// Before: 手动实现每个 Provider
class OpenAIProvider implements AIProvider { /* 200+ 行 */ }
class GeminiProvider implements AIProvider { /* UnimplementedError */ }

// After: LangChain 适配器
class LangChainProvider implements AIProvider {
  final BaseChatModel _model;

  factory LangChainProvider.fromConfig(ProviderConfig config) {
    switch (config.type) {
      case ProviderType.openai:
        return LangChainProvider(ChatOpenAI(apiKey: config.apiKey));
      case ProviderType.gemini:
        return LangChainProvider(ChatGoogleGenerativeAI(apiKey: config.apiKey));
      case ProviderType.claude:
        return LangChainProvider(ChatAnthropic(apiKey: config.apiKey));
      // 所有 Provider 立即可用
    }
  }
}
```

**Phase 2: 中间件管道 (架构优化)**
```dart
// LCEL 管道示例
final chain = Runnable.fromMap({
  'context': RpContextRetriever(storyId), // 自研 RP 逻辑
  'history': ConversationMemory(),
  'question': Runnable.passthrough(),
}) | PromptTemplate.fromTemplate('''
{context}

Chat History: {history}

User: {question}
''') | ChatOpenAI() | StringOutputParser();
```

**Phase 3: RAG + Tools (功能扩展)**
```dart
// RAG 管道
final ragChain = Runnable.fromMap({
  'context': vectorStore.asRetriever(),
  'question': Runnable.passthrough(),
}) | ragPrompt | model | StringOutputParser();

// Tool Calling
final tools = [
  ToolSpec(
    name: 'web_search',
    description: 'Search the web for information',
    inputJsonSchema: {...},
  ),
];
final modelWithTools = model.bind(BindOptions(tools: tools));
```

---

## 4. MCP (Model Context Protocol) 集成

### 4.1 可用 Dart/Flutter 包

| 包名 | 版本 | 功能 |
|------|------|------|
| `mcp_client` | 0.1.x | MCP 客户端实现 |
| `mcp_dart` | 0.1.x | Dart MCP SDK |
| `mcp_server` | 0.1.x | MCP 服务端构建 |

### 4.2 MCP 架构

```
┌─────────────────┐     ┌─────────────────┐
│   ChatBoxApp    │────▶│   MCP Client    │
│   (Flutter)     │     │   (mcp_client)  │
└─────────────────┘     └────────┬────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │ Stdio    │ │ HTTP/SSE │ │ WebSocket│
              │ Transport│ │ Transport│ │ Transport│
              └────┬─────┘ └────┬─────┘ └────┬─────┘
                   ▼            ▼            ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │ Local    │ │ Remote   │ │ Cloud    │
              │ MCP Tool │ │ MCP Tool │ │ MCP Tool │
              └──────────┘ └──────────┘ └──────────┘
```

### 4.3 集成示例

```dart
import 'package:mcp_client/mcp_client.dart';

class McpToolManager {
  final McpClient _client;

  Future<void> connect(String serverPath) async {
    await _client.connect(StdioTransport(serverPath));
  }

  Future<List<Tool>> listTools() async {
    return await _client.listTools();
  }

  Future<ToolResult> callTool(String name, Map<String, dynamic> args) async {
    return await _client.callTool(name, args);
  }
}
```

### 4.4 MCP 对 RP 的价值

| 场景 | MCP 工具 | 价值 |
|------|----------|------|
| 世界观检索 | `lore_search` | 角色/场景知识库查询 |
| 角色一致性 | `character_validator` | 自动校验角色行为 |
| 图片生成 | `image_generation` | 场景/角色插图 |
| 网页搜索 | `web_search` | 参考资料检索 |

---

## 5. 本地 RAG 方案

### 5.1 Vector Database 选择

| 方案 | 类型 | 优点 | 缺点 | 推荐度 |
|------|------|------|------|--------|
| **sqlite-vec** | SQLite 扩展 | 零依赖、跨平台、SQL 查询 | 需要编译 | ⭐⭐⭐⭐⭐ |
| **ObjectBox** | 嵌入式 DB | Flutter 原生、高性能 | 向量支持有限 | ⭐⭐⭐⭐ |
| **MemoryVectorStore** | 内存 | 零配置、即用 | 无持久化 | ⭐⭐⭐ |
| **Chroma** | 服务端 | 功能丰富 | 需要服务器 | ⭐⭐ |

### 5.2 推荐方案: sqlite-vec

```dart
// sqlite-vec 集成示例
import 'package:sqlite3/sqlite3.dart';

class LocalVectorStore {
  final Database _db;

  void createTable() {
    _db.execute('''
      CREATE VIRTUAL TABLE IF NOT EXISTS embeddings
      USING vec0(
        id TEXT PRIMARY KEY,
        content TEXT,
        embedding FLOAT[1536]  -- OpenAI embedding 维度
      )
    ''');
  }

  Future<void> insert(String id, String content, List<double> embedding) async {
    _db.execute(
      'INSERT INTO embeddings VALUES (?, ?, vec_f32(?))',
      [id, content, embedding],
    );
  }

  Future<List<Document>> search(List<double> query, {int limit = 5}) async {
    final results = _db.select('''
      SELECT id, content, vec_distance_cosine(embedding, vec_f32(?)) as distance
      FROM embeddings
      ORDER BY distance
      LIMIT ?
    ''', [query, limit]);
    return results.map((r) => Document(id: r['id'], content: r['content'])).toList();
  }
}
```

### 5.3 RAG 对 RP 的价值

| 场景 | 实现方式 | 价值 |
|------|----------|------|
| 世界观知识库 | Lorebook → Embedding → Vector DB | 自动检索相关设定 |
| 历史对话检索 | 对话 → 摘要 → Embedding | 长期记忆支持 |
| 角色卡片库 | 角色定义 → Embedding | 动态角色检索 |

---

## 6. Function Calling / Tool Use

### 6.1 LangChain.dart Tool 接口

```dart
// Tool 定义
final webSearchTool = ToolSpec(
  name: 'web_search',
  description: 'Search the web for current information',
  inputJsonSchema: {
    'type': 'object',
    'properties': {
      'query': {'type': 'string', 'description': 'Search query'},
    },
    'required': ['query'],
  },
);

// 绑定到模型
final modelWithTools = ChatOpenAI(
  apiKey: apiKey,
).bind(BindOptions(tools: [webSearchTool]));

// 处理 Tool Call
final response = await modelWithTools.invoke(prompt);
if (response.output.toolCalls.isNotEmpty) {
  for (final call in response.output.toolCalls) {
    final result = await executeToolCall(call);
    // 将结果反馈给模型
  }
}
```

### 6.2 Message 模型扩展建议

```dart
class Message {
  String content;
  List<AttachedFileSnapshot>? attachedFiles;
  String? parentId;

  // 新增字段
  Map<String, dynamic>? metadata;      // 通用元数据
  List<ToolCall>? toolCalls;           // 工具调用请求
  List<ToolResult>? toolResults;       // 工具调用结果
  List<Citation>? citations;           // RAG 引用来源
}

class ToolCall {
  String id;
  String name;
  Map<String, dynamic> arguments;
}

class ToolResult {
  String toolCallId;
  String output;
  bool isError;
}
```

---

## 7. 对 RP 实现的便利

### 7.1 现有 RP 架构与框架集成点

| RP 组件 | 框架集成方式 | 价值 |
|---------|-------------|------|
| **RpContextCompiler** | 实现为 LangChain `Retriever` | 可插入 LCEL 管道 |
| **RpMemoryRepository** | 实现为 LangChain `BaseMemory` | 统一记忆管理接口 |
| **RpConsistencyGate** | 实现为 LCEL `Runnable` 中间件 | 管道化验证 |
| **世界观检索** | sqlite-vec + Retriever | 自动上下文注入 |

### 7.2 RpContextCompiler 作为 Retriever

```dart
class RpContextRetriever extends Retriever {
  final RpContextCompiler _compiler;
  final String _storyId;

  @override
  Future<List<Document>> getRelevantDocuments(String query) async {
    final context = await _compiler.compile(
      storyId: _storyId,
      query: query,
    );
    return [
      Document(
        pageContent: context.systemPrompt,
        metadata: {'source': 'rp_context'},
      ),
    ];
  }
}
```

### 7.3 LCEL 管道示例 (RP 模式)

```dart
// RP 增强的聊天管道
final rpChain = Runnable.fromMap({
  // 1. RP 上下文编译
  'rp_context': RpContextRetriever(storyId),
  // 2. 世界观知识库检索
  'lore': LoreRetriever(vectorStore),
  // 3. 历史对话
  'history': ConversationBufferMemory(),
  // 4. 用户输入
  'input': Runnable.passthrough(),
})
// 5. 组装 Prompt
| PromptTemplate.fromTemplate('''
# System
{rp_context}

# World Knowledge
{lore}

# Chat History
{history}

# User
{input}
''')
// 6. LLM 调用
| ChatOpenAI()
// 7. 一致性校验 (可选)
| ConsistencyGateRunnable()
// 8. 输出解析
| StringOutputParser();
```

---

## 8. 迁移风险评估

### 8.1 风险矩阵

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| LangChain.dart API 变更 | 中 | 中 | 薄适配层隔离 |
| 性能开销 | 低 | 低 | 管道优化、缓存 |
| 学习曲线 | 中 | 低 | 渐进式迁移 |
| 依赖膨胀 | 中 | 低 | 按需引入包 |

### 8.2 渐进式迁移路径

```
Week 1-2: Provider 层替换
├── 引入 langchain_openai, langchain_google, langchain_anthropic
├── 创建 LangChainProvider 适配器
└── 测试: 所有现有功能不变

Week 3-4: 中间件管道
├── 重构 ConversationService 使用 LCEL
├── RpContextCompiler 实现 Retriever 接口
└── 测试: RP 功能正常

Week 5-6: RAG 集成
├── 引入 sqlite-vec
├── 实现 Lorebook 向量化
└── 测试: 知识库检索

Week 7-8: Tool Calling
├── Message 模型扩展
├── MCP 客户端集成
└── 测试: 工具调用流程
```

---

## 9. 结论与建议

### 9.1 推荐采纳框架

| 优先级 | 框架 | 用途 | 理由 |
|--------|------|------|------|
| **P0** | LangChain.dart | Provider + 编排 | 立即解决多 Provider 问题 |
| **P1** | sqlite-vec | 本地向量存储 | 零服务器成本的 RAG |
| **P2** | mcp_client | 工具集成 | 标准化工具调用协议 |
| **P3** | TavilyAPI | Web Search | LangChain 内置支持 |

### 9.2 不推荐采纳

| 框架 | 理由 |
|------|------|
| Flutter AI Toolkit | UI 已自研，仅 Google 生态 |
| GenUI SDK | 动态 UI 非当前需求 |
| Chroma (服务端) | 增加部署复杂度 |

### 9.3 最终建议

**采用 "Hybrid Core" 策略**:

1. **LangChain.dart 作为编排核心** - 替换 Provider 层、提供 LCEL 管道
2. **保留自研 RP 后端** - RpContextCompiler、RpMemoryRepository、RpWorkerHost
3. **保留自研 UI** - conversation_view_v2、自定义组件
4. **sqlite-vec 作为本地 RAG** - 世界观知识库、历史检索
5. **MCP 作为工具扩展** - 按需集成外部工具

**核心价值**:
- 立即获得 7 个 LLM Provider 支持
- 标准化的 RAG/Tool Calling 接口
- 保持 Local-First 架构优势 (零服务器成本)
- 保护现有 RP 投资

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-01-24 | 初版，基于多模型研究结果 |
