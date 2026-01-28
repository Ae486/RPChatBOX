# Flutter LLM 框架评估报告

> 自建架构 vs 框架采用策略分析
>
> 版本: 1.0 | 日期: 2026-01-24

---

## 1. 研究背景

### 1.1 核心问题

ChatBoxApp 当前采用自建组件架构，担忧：
- 后期扩展时，自建组件是否会成为阻碍？
- 是否应该迁移到专业 Flutter LLM 框架？

### 1.2 当前架构状态

| 组件 | 状态 | 问题 |
|------|------|------|
| AIProvider | 自建 | 仅 OpenAI 可用，Gemini/Claude/DeepSeek 为存根 |
| Message 模型 | 自建 | 缺少 metadata, toolCalls, toolResults |
| 持久化 | Hive 自建 | 无中间件、无事务 |
| 流式输出 | 自建 | 可用但不易扩展 |
| RP 后端 | 自建 | 存在但与基础 Chat 断开 |

---

## 2. 发现的 Flutter LLM 框架

### 2.1 主要框架

| 框架 | 定位 | 核心特性 | 维护者 |
|------|------|----------|--------|
| **LangChain.dart** | 后端逻辑/LLM 抽象 | LCEL 组合、多 Provider、RAG、Agents、Memory、Streaming | 社区 (davidmigloz) |
| **Flutter AI Toolkit** | 全栈 (UI + Backend) | LlmProvider 抽象、Chat UI 组件、Firebase/Vertex AI | Google 官方 |
| **flutter_chat_ui** | UI 层 | Chat SDK、后端无关、AI Agent 支持 | Flyer Chat |
| **GenUI SDK** | 动态 UI | A2UI 协议、LLM 生成 UI | Google |
| **dartantic_ai** | Agentic 框架 | 跨 Provider、客户端/服务端 | Chris Sells |

### 2.2 LangChain.dart 架构详解

```
┌─────────────────────────────────────────────────────────────┐
│                    LangChain.dart 架构                       │
├─────────────────────────────────────────────────────────────┤
│  langchain_core     - 核心抽象 + LCEL 原语                   │
│  langchain          - 高级 Chains, Agents, Retrieval        │
│  langchain_community - 第三方集成                            │
├─────────────────────────────────────────────────────────────┤
│  Integration Packages:                                       │
│  - langchain_openai    (OpenAI)                             │
│  - langchain_google    (Gemini/Vertex)                      │
│  - langchain_anthropic (Claude)                             │
│  - langchain_ollama    (本地模型)                           │
│  - langchain_mistralai (Mistral)                            │
│  - langchain_chroma    (向量存储)                           │
│  - langchain_pinecone  (向量存储)                           │
└─────────────────────────────────────────────────────────────┘
```

**核心抽象 - Runnable 接口**:
- 统一的 `invoke()`, `stream()`, `batch()` 方法
- LCEL (LangChain Expression Language) 组合语法
- `pipe()` 或 `|` 操作符链接组件

**支持能力**:
- 多 Provider 统一 API
- RAG: DocumentLoader → TextSplitter → Embeddings → VectorStore → Retriever
- Agents: Tool 接口 + AgentExecutor
- Memory: ChatMessageHistory, BufferMemory, ConversationSummaryMemory
- Streaming: 所有 Runnable 支持 `stream()` 方法

### 2.3 Flutter AI Toolkit 架构详解

```dart
// LlmProvider 抽象接口
abstract class LlmProvider implements Listenable {
  Stream<String> generateStream(String prompt, {Iterable<Attachment> attachments});
  Stream<String> sendMessageStream(String prompt, {Iterable<Attachment> attachments});
  Iterable<ChatMessage> get history;
  set history(Iterable<ChatMessage> history);
}

// 使用示例
LlmChatView(
  provider: FirebaseProvider(
    model: FirebaseAI.vertexAI().generativeModel(model: 'gemini-2.5-flash'),
  ),
)
```

**扩展点**:
- 自定义 `LlmProvider` 实现
- 自定义 `LlmStreamGenerator` (RAG/Prompt 工程)
- 自定义 `ResponseBuilder` (响应渲染)

---

## 3. 框架对比矩阵

### 3.1 功能对比

| 特性 | 自建 (当前) | LangChain.dart | Flutter AI Toolkit | flutter_chat_ui |
|------|------------|----------------|-------------------|-----------------|
| **定位** | 全栈 (手动) | 后端逻辑/LLM 抽象 | 全栈 (UI + Backend) | UI 层 |
| **UI 定制性** | ⭐⭐⭐⭐⭐ | N/A | ⭐⭐ (Material 3 固定) | ⭐⭐⭐ |
| **RP 适配** | ✅ 原生支持 | ✅ 好 (自定义 Prompt) | ❌ 差 (通用 Chat) | ❌ 差 |
| **Provider 支持** | ⚠️ 差 (手动实现) | ✅ **优秀** | ⚠️ Google 为主 | N/A |
| **中间件/RAG** | ❌ 无 | ✅ **优秀** (LCEL) | ⚠️ 有限 | N/A |
| **Tool Calling** | ❌ 无 | ✅ 标准接口 | ✅ Google Tools | N/A |
| **维护成本** | 🔴 高 (API 变更) | 🟢 低 (社区维护) | 🟢 低 (Google 维护) | 🟢 低 |

### 3.2 RP 功能支撑对比

| RP 需求 | 自建 | LangChain.dart | Flutter AI Toolkit |
|---------|------|----------------|-------------------|
| 角色卡/世界书 | ✅ 可实现 | ✅ 作为 Retriever | ❌ 不支持 |
| 分支版本控制 | ✅ RpSnapshot | ✅ 可包装 | ❌ 不支持 |
| 上下文组装 | ✅ ContextCompiler | ✅ LCEL 管道 | ⚠️ 有限 |
| 自定义 UI | ✅ 完全控制 | N/A | ⚠️ 受限 |
| 多 Provider | ❌ 仅 OpenAI | ✅ 全部 | ⚠️ Google 为主 |

---

## 4. 风险评估

### 4.1 继续自建路径

| 风险类型 | 严重度 | 说明 |
|----------|--------|------|
| 技术债务复利 | ⚠️⚠️⚠️ | 核心抽象不完整，每个新功能都成为定制管道 |
| 产品竞争力 | ⚠️⚠️⚠️ | 缺少 RAG/MCP/Function Calling，功能路线图变长 |
| 可靠性 | ⚠️⚠️ | 无标准化 tool-call trace、消息元数据、事务边界 |
| 人才/入职 | ⚠️⚠️ | 自定义架构增加认知负担，难以与生态共享知识 |
| 成本 | ⚠️ | 短期便宜，长期因重复工作和维护而昂贵 |

### 4.2 框架采用路径

| 风险类型 | 严重度 | 说明 |
|----------|--------|------|
| 集成风险 | ⚠️⚠️ | 现有模型/持久化/流式映射到框架原语需要适配工作 |
| 锁定风险 | ⚠️⚠️ | 框架驱动核心编排后，后续替换更难 |
| 依赖风险 | ⚠️ | 框架生命周期（更新、破坏性变更）增加发布管理开销 |
| 性能风险 | ⚠️ | 抽象层可能增加开销，通常可通过 profiling 管理 |

---

## 5. 双模型分析结论

### 5.1 Codex 分析结论

**推荐核心框架: LangChain.dart**

理由：
- 直接覆盖 RAG、Agents、Memory、Streaming、多 Provider
- 允许保留现有 UI + Hive 存储，仅引入"LLM 编排"层
- 提供 function calling 和 tool execution 的最清晰路径

**工作量估算**:
- 完整框架迁移 (LangChain.dart 核心 + 适配器 + 数据模型对齐): 6-12 周
- 渐进式自建增强 (多 Provider + metadata + tools + RAG + MCP): 10-20 周

### 5.2 Gemini 分析结论

**推荐: 混合方法 (Hybrid Approach)**

1. **采用 LangChain.dart (仅核心)**: 替换脆弱的 `AIProvider` 层
2. **保留自定义 UI**: RP 应用需要独特 UI (角色卡、背景)，`flutter_chat_ui` 难以定制
3. **保留自定义存储**: Hive + `RpStoryMeta` 逻辑优于通用框架 memory

**框架角色分工**:
- LangChain.dart → 后端 LLM 抽象 + 中间件管道
- 自建 UI → RP 专属界面 (角色卡、背景、分支)
- 自建存储 → RpMemoryRepository 包装为 LangChain Retriever

---

## 6. 推荐策略: LangChain Adapter 模式

### 6.1 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                      UI Layer (保留)                         │
│          ConversationView / RP 专属组件                      │
├─────────────────────────────────────────────────────────────┤
│                   Service Layer (改造)                       │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           LLM Orchestration Service                  │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │   │
│  │  │ RpRetriever │  │ PromptChain │  │ ChatModel   │  │   │
│  │  │(包装 Context│  │ (LCEL)      │  │(LangChain)  │  │   │
│  │  │ Compiler)   │  │             │  │             │  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  │   │
│  └─────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────┤
│                  Persistence Layer (保留)                    │
│          Hive + RpMemoryRepository + RpStoryMeta            │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 核心改造点

**1. Provider 替换**

```dart
// Before: 自建 Provider (仅 OpenAI 可用)
class OpenAIProvider extends AIProvider { ... }
class GeminiProvider extends AIProvider { throw UnimplementedError(); }

// After: LangChain ChatModel
import 'package:langchain_openai/langchain_openai.dart';
import 'package:langchain_google/langchain_google.dart';

BaseChatModel createChatModel(ProviderConfig config) {
  switch (config.type) {
    case ProviderType.openai:
      return ChatOpenAI(apiKey: config.apiKey);
    case ProviderType.gemini:
      return ChatGoogleGenerativeAI(apiKey: config.apiKey);
    case ProviderType.ollama:
      return ChatOllama(baseUrl: config.baseUrl);
    // 即刻支持所有 Provider!
  }
}
```

**2. RP 上下文作为 Retriever**

```dart
// 包装 RpContextCompiler 为 LangChain Retriever
class RpContextRetriever extends BaseRetriever {
  final RpContextCompiler _compiler;
  final String _storyId;

  @override
  Future<List<Document>> getRelevantDocuments(String query) async {
    final context = await _compiler.compile(_storyId);
    return [Document(pageContent: context.renderedText)];
  }
}
```

**3. LCEL 中间件管道**

```dart
// 替换硬编码 sendMessage 逻辑
final chain = Runnable.fromMap({
  'context': RpContextRetriever(storyId),
  'question': Runnable.passthrough(),
}) | PromptTemplate.fromTemplate(
  "{context}\n\nUser: {question}"
) | chatModel | StringOutputParser();

// 调用
final response = await chain.stream(userMessage);
```

---

## 7. 分阶段采用计划

### Phase 1: Provider 替换 (低风险，高价值)

**目标**: 立即支持 Gemini、Claude、DeepSeek

**任务**:
1. 添加依赖: `langchain`, `langchain_openai`, `langchain_google`, `langchain_ollama`
2. 重写 `ProviderFactory` 返回 `BaseChatModel`
3. 更新 `ConversationService.sendMessage` 调用 `model.stream()`

**结果**: 所有 Provider 立即可用，UI 和持久化无需改动

**工作量**: 1-2 周

### Phase 2: 中间件管道 (架构修复)

**目标**: 连接"断开"的 Roleplay 后端

**任务**:
1. 创建 `RoleplayRetriever` 包装 `RpMemoryRepository`
2. 在 `ConversationService` 中构建 `RunnableSequence`
3. 动态注入系统 prompt

**结果**: RP 上下文自动注入到聊天中

**工作量**: 2-3 周

### Phase 3: 高级功能 (商业平价)

**目标**: RAG & Tools 支持

**任务**:
1. **RAG**: 添加 `langchain_chroma` 或本地向量存储，创建 `DocumentRetriever`
2. **Tools**: 使用 LangChain `Tool` 类定义 Web Search，绑定到 `ChatModel`

**结果**: ChatBoxApp 成为可搜索网页和读取文件的 Agent

**工作量**: 3-4 周

### Phase 4: 清理与优化

**目标**: 去除遗留代码

**任务**:
1. 弃用自定义 streaming 和定制 tool parsing
2. 统一错误处理和重试逻辑
3. 添加可观测性 (traces, metrics)

**工作量**: 2 周

---

## 8. 优缺点总结

### 8.1 推荐方案: LangChain.dart 编排 + 保留 UI/Hive

| 优点 | 缺点 |
|------|------|
| RAG/MCP/Function Calling 最快路径 | 前期集成工作 |
| 可扩展的 Provider 支持 | 如果适配器不够薄，可能锁定 |
| 长期维护性更好 | 学习曲线 (LCEL) |
| 与生态系统共享知识 | 依赖框架更新周期 |

### 8.2 备选方案: 继续自建 (渐进增强)

| 优点 | 缺点 |
|------|------|
| 完全控制 | 长期成本最高 |
| 无外部依赖风险 | 功能平价最慢路径 |
| | 最难维护 |

---

## 9. 最终建议

**立即采用 LangChain.dart 作为后端逻辑层**

理由：
1. 解决最大技术债务 (Provider 实现 + 中间件结构)
2. 不强迫妥协高价值的自定义 UI 和 RP Memory 架构
3. 提供清晰的 RAG/MCP/Tool Calling 扩展路径
4. 社区维护，降低 API 变更追踪成本

**不建议采用 Flutter AI Toolkit 作为主框架**

理由：
1. UI 定制性受限，不适合 RP 专属界面
2. Google 生态依赖，Provider 选择受限
3. 会强迫放弃已有的 RpStoryMeta 版本控制逻辑

---

## 10. Session IDs

- Codex: `019bef74-747c-7d23-b7e8-54aaa491b4f8`
- Gemini: `cc0bcba3-e13a-4780-a8b1-d16c892ba3c8`

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-01-24 | 初版，基于多模型协作分析 + MCP 工具搜索 |
