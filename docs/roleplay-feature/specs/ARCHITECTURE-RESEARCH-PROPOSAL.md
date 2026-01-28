# Architecture Research Proposal: Commercial-Grade LLM Platform

> OpenSpec Research Phase Output
>
> Version: 1.0 | Date: 2026-01-27
>
> Multi-Model Collaboration: Claude (Synthesis) + Codex (Backend Analysis)

---

## Executive Summary

**项目目标**: 开源 + 商业级体验的多模型 LLM 平台

**核心发现**:
1. 当前纯前端架构是**正确的基础**，不需要推翻
2. 需要**中间件模式重构**以支持 RAG/MCP/Skills 扩展
3. 建议**三模式共存架构**：纯前端 → 本地服务 → 云端（渐进式）
4. LangChain.dart **不建议作为核心依赖**，保持自建 Provider

---

## 1. 当前架构评估

### 1.1 综合评分（基于多模型审查）

| 层级 | 评分 | 说明 |
|------|------|------|
| **业务层** | 6.0/10 | 功能够用但单一，缺 RAG/Search/Tools |
| **技术层** | 4.3/10 | 架构扩展性差，急需中间件模式 |
| **成本层** | 7.3/10 | Local-First 优势明显，零服务器成本 |
| **综合** | **5.8/10** | 基础扎实，商业级扩展性不足 |

### 1.2 架构优势（保留）

```
┌─────────────────────────────────────────────────────────────┐
│                   当前架构优势                               │
├─────────────────────────────────────────────────────────────┤
│  ✅ Local-First: 用户数据完全本地，隐私友好                  │
│  ✅ Zero Server Cost: 用户自带 API Key                      │
│  ✅ Cross-Platform: Flutter 一次编写多端运行                │
│  ✅ Thread Support: 消息树结构已实现                        │
│  ✅ RP Foundation: M0-M4 后端逻辑已实现                     │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 架构问题（需改进）

| 问题 | 严重度 | 影响 |
|------|--------|------|
| **无中间件管道** | Critical | 无法优雅扩展 RAG/Search/Tools |
| **Provider 不完整** | High | 仅 OpenAI 完整，Claude/Gemini 存根 |
| **Message 模型受限** | High | 缺 metadata、toolCalls、thinking |
| **LangChain 抽象泄漏** | Medium | thinking 标签被丢失 |
| **RP 后端孤岛** | Medium | 未接入基础 Chat 流程 |

---

## 2. 目标架构设计

### 2.1 三模式共存架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      ChatBoxApp 架构                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    Flutter Frontend                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │   │
│  │  │   Chat UI   │  │  RP Engine  │  │   Settings      │  │   │
│  │  └──────┬──────┘  └──────┬──────┘  └─────────────────┘  │   │
│  │         │                │                              │   │
│  │         └────────────────┴──────────────────────────────┤   │
│  │                          │                              │   │
│  │  ┌───────────────────────▼───────────────────────────┐  │   │
│  │  │              ChatPipeline (中间件)                 │  │   │
│  │  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────────────┐ │  │   │
│  │  │  │ RAG │→│Search│→│Tools│→│ RP  │→│ AI Provider │ │  │   │
│  │  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────────────┘ │  │   │
│  │  └───────────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                     │
│  ════════════════════════╪═══════════════════════════════════  │
│                          │                                     │
│         Mode A           │         Mode B          Mode C      │
│      (Pure Frontend)     │    (Local Service)   (Cloud)       │
│            │             │           │             │           │
│            ▼             │           ▼             ▼           │
│     ┌──────────┐         │    ┌──────────┐  ┌──────────┐      │
│     │ LLM APIs │         │    │ Local    │  │ Cloud    │      │
│     │ (Direct) │         │    │ Sidecar  │  │ Backend  │      │
│     └──────────┘         │    │ (MCP/RAG)│  │ (SaaS)   │      │
│                          │    └──────────┘  └──────────┘      │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 模式说明

| 模式 | 适用场景 | 功能范围 | 复杂度 |
|------|---------|---------|--------|
| **Mode A: 纯前端** | 默认模式，基础聊天 | Chat + RP | 最低 |
| **Mode B: 本地服务** | 桌面端高级功能 | + RAG + MCP + 本地模型 | 中等 |
| **Mode C: 云端** | 企业/商业化 | + 多人协作 + 审计 | 最高 |

### 2.3 渐进式实现路径

```
Phase 1 (当前)          Phase 2              Phase 3              Phase 4
────────────────────────────────────────────────────────────────────────────
Mode A Only        →   Mode A + Pipeline  →  Mode A + B        →  Mode A + B + C
纯前端直连              中间件重构             本地服务支持          云端可选

实现内容:              实现内容:             实现内容:            实现内容:
- 现有功能             - ChatPipeline       - Local Sidecar     - 云端 API
- Provider 补全        - Interceptor 接口   - MCP Client        - 用户系统
- Message 扩展         - RP 集成            - sqlite-vec RAG    - 计费审计
```

---

## 3. 核心模块设计

### 3.1 ChatPipeline（中间件架构）

**目的**: 解决"无法优雅扩展"问题

```dart
/// 中间件接口
abstract class ChatInterceptor {
  /// 处理请求，调用 next 传递给下一个中间件
  Future<ChatPayload> process(
    ChatPayload payload,
    Future<ChatPayload> Function(ChatPayload) next,
  );
}

/// 处理管道
class ChatPipeline {
  final List<ChatInterceptor> interceptors;
  final AIProvider provider;

  Future<ChatPayload> execute(ChatPayload payload) async {
    // 构建中间件链
    var chain = (ChatPayload p) => provider.send(p);
    for (final interceptor in interceptors.reversed) {
      final next = chain;
      chain = (p) => interceptor.process(p, next);
    }
    return chain(payload);
  }
}

/// 使用示例
final pipeline = ChatPipeline(
  interceptors: [
    RagInterceptor(ragService),       // 1. RAG 上下文注入
    WebSearchInterceptor(searchSvc),  // 2. Web 搜索增强
    ToolInterceptor(toolRegistry),    // 3. Tool Calling
    RpContextInterceptor(rpCompiler), // 4. RP 上下文编译
    LoggingInterceptor(),             // 5. 日志审计
  ],
  provider: openAIProvider,
);
```

**实现优先级**: P1（架构扩展性）

### 3.2 Provider 层重构

**目的**: 解决"Provider 不完整"和"LangChain 抽象泄漏"问题

```dart
/// 增强的 AIProvider 接口
abstract class AIProvider {
  /// Provider 能力声明
  ProviderCapabilities get capabilities;

  /// 流式发送（保留完整响应结构）
  Stream<ChatChunk> sendMessageStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    List<Tool>? tools,  // 新增: Tool Calling
  });
}

/// 能力声明（优雅降级而非 UnimplementedError）
class ProviderCapabilities {
  final bool supportsStreaming;
  final bool supportsVision;
  final bool supportsTools;
  final bool supportsThinking;  // Claude extended thinking
  final int maxContextTokens;
}

/// 流式响应块（保留完整结构）
class ChatChunk {
  final String? content;
  final String? thinking;      // 新增: thinking 标签内容
  final List<ToolCall>? toolCalls;
  final UsageInfo? usage;
  final bool isComplete;
}
```

**实现优先级**: P1（基础功能）

### 3.3 Message 模型扩展

**目的**: 支持 Tool Calling、Thinking、元数据

```dart
@HiveType(typeId: 1)
class Message {
  // 现有字段保持不变
  @HiveField(0)  String content;
  @HiveField(1)  MessageRole role;
  @HiveField(2)  String? parentId;
  @HiveField(3)  List<AttachedFileSnapshot>? attachedFiles;

  // 新增字段
  @HiveField(10) Map<String, dynamic>? metadata;     // 扩展元数据
  @HiveField(11) List<ToolCall>? toolCalls;          // Tool 调用
  @HiveField(12) String? toolCallId;                 // Tool 响应关联
  @HiveField(13) List<ToolResult>? toolResults;      // Tool 执行结果
  @HiveField(14) String? thinking;                   // Thinking 内容
  @HiveField(15) List<Citation>? citations;          // RAG 引用来源
}
```

**实现优先级**: P2（功能扩展）

### 3.4 Local RAG 方案

**目的**: 实现本地知识库支持

```
┌─────────────────────────────────────────────────────────────┐
│                    Local RAG Stack                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐ │
│  │  文档解析   │ →  │  Embedding  │ →  │  向量存储       │ │
│  │  (PDF/TXT)  │    │  (Cloud API)│    │  (sqlite-vec)   │ │
│  └─────────────┘    └─────────────┘    └─────────────────┘ │
│                                                             │
│  检索流程:                                                  │
│  Query → Embedding → Nearest Neighbor → Top-K → 注入上下文  │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  技术选型:                                                  │
│  - 向量存储: sqlite-vec (SQLite 扩展，Dart FFI 调用)       │
│  - Embedding: OpenAI text-embedding-3-small (云端 API)     │
│  - 分块策略: 语义块 300-800 tokens, 10-20% overlap         │
│  - 文档解析: pdf_text (Dart), 结构化分块                   │
└─────────────────────────────────────────────────────────────┘
```

**实现优先级**: P3（功能扩展）

### 3.5 MCP 集成方案

**目的**: 支持 MCP 工具生态

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Integration                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                  MCPClient (Dart)                    │   │
│  │  - JSON-RPC 2.0 通信层                               │   │
│  │  - Tool Registry (工具注册)                          │   │
│  │  - Permission Model (权限模型)                       │   │
│  └──────────────────────────┬──────────────────────────┘   │
│                             │                               │
│            ┌────────────────┼────────────────┐             │
│            │                │                │             │
│            ▼                ▼                ▼             │
│     ┌──────────┐     ┌──────────┐     ┌──────────┐        │
│     │ Local    │     │ Remote   │     │ Bundled  │        │
│     │ Process  │     │ Server   │     │ (内置)   │        │
│     │ (stdio)  │     │ (HTTP)   │     │          │        │
│     └──────────┘     └──────────┘     └──────────┘        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  Mode A (纯前端): 仅支持 Remote MCP Server                  │
│  Mode B (本地服务): 支持 Local Process + Remote            │
│  Mode C (云端): 统一代理所有 MCP 调用                       │
└─────────────────────────────────────────────────────────────┘
```

**实现优先级**: P3（未来竞争力）

### 3.6 Skills 系统

**目的**: 类似 Claude Code/Codex CLI 的 Skill 能力

```dart
/// Skill = Prompt Template + Tool Binding + Context Injection
class Skill {
  final String id;
  final String name;
  final String description;

  /// 系统提示词模板
  final String systemPromptTemplate;

  /// 绑定的 MCP 工具列表
  final List<String> boundTools;

  /// 上下文注入器
  final ContextInjector? contextInjector;

  /// 执行时注入的变量
  final Map<String, dynamic> variables;
}

/// Skill 执行器
class SkillExecutor {
  final MCPClient mcpClient;
  final ChatPipeline pipeline;

  Future<void> execute(Skill skill, ChatPayload payload) async {
    // 1. 注入 Skill 系统提示词
    payload = payload.withSystemPrompt(
      skill.systemPromptTemplate.render(skill.variables),
    );

    // 2. 注入上下文
    if (skill.contextInjector != null) {
      payload = await skill.contextInjector!.inject(payload);
    }

    // 3. 绑定工具
    payload = payload.withTools(
      await mcpClient.getTools(skill.boundTools),
    );

    // 4. 执行
    return pipeline.execute(payload);
  }
}
```

**实现优先级**: P4（差异化功能）

---

## 4. 关于框架选择的决策

### 4.1 LangChain.dart 评估

| 维度 | 评估 | 结论 |
|------|------|------|
| **成熟度** | Dart 版滞后 Python 版，缺少 langchain_anthropic | 不推荐作为核心 |
| **抽象泄漏** | thinking 标签被丢失，Tool Calling 支持不完整 | 不满足需求 |
| **灵活性** | 框架强制约束，难以定制 | 与 RP 冲突 |
| **维护负担** | 需要跟踪上游更新 | 增加复杂度 |

**决策**:
- ❌ 不使用 LangChain.dart 作为核心依赖
- ✅ 保持自建 Provider 层
- ✅ 可选择性使用 LangChain 的特定组件（如 OutputParser）

### 4.2 推荐技术栈

| 层级 | 技术选择 | 理由 |
|------|---------|------|
| **UI** | Flutter (现有) | 跨平台、成熟 |
| **状态管理** | 现有方案 | 无需更换 |
| **持久化** | Hive (现有) | 性能好、无需迁移 |
| **网络** | Dio (现有) | 完善的 SSE 支持 |
| **向量存储** | sqlite-vec | 轻量、Dart FFI 可用 |
| **MCP** | 自建 MCPClient | 无成熟 Dart 库 |
| **Embedding** | 云端 API | 本地模型过重 |

### 4.3 关于后端语言

**当前阶段（Mode A/B）**: 不需要后端

**未来 Mode C（如需要）**:
| 语言 | 适用场景 | 推荐度 |
|------|---------|--------|
| **Go** | API Gateway、高并发 | ⭐⭐⭐⭐ |
| **Python** | RAG 服务、Agent 编排 | ⭐⭐⭐⭐ |
| **TypeScript** | MCP Server 开发 | ⭐⭐⭐ |
| **Rust** | 高性能计算、边缘部署 | ⭐⭐ |

---

## 5. 实施优先级

### 5.1 Phase 1: 基础补全（P0/P1）

| 任务 | 优先级 | 预期效果 |
|------|--------|---------|
| 修复 M3 switch 编译错误 | P0 | RP 功能解锁 |
| 统一 Domain 命名 | P0 | 数据一致性 |
| 实现 ChatPipeline 中间件 | P1 | 架构扩展性 |
| 完成 Claude/Gemini Provider | P1 | 多模型支持 |
| 修复 LangChain thinking 泄漏 | P1 | 功能完整性 |

### 5.2 Phase 2: 功能扩展（P2）

| 任务 | 优先级 | 预期效果 |
|------|--------|---------|
| Message 模型扩展 | P2 | Tool/Thinking 支持 |
| 创建 RoleplayOrchestrator | P2 | RP 功能打通 |
| 实现 ToolInterceptor | P2 | Tool Calling 基础 |

### 5.3 Phase 3: 高级功能（P3）

| 任务 | 优先级 | 预期效果 |
|------|--------|---------|
| Local RAG (sqlite-vec) | P3 | 知识库支持 |
| MCPClient 实现 | P3 | 工具生态接入 |
| Web Search 集成 | P3 | 信息增强 |

### 5.4 Phase 4: 差异化（P4）

| 任务 | 优先级 | 预期效果 |
|------|--------|---------|
| Skills 系统 | P4 | 独特功能 |
| 语音输入 | P4 | 多模态支持 |
| Local Sidecar (Mode B) | P4 | 高级用户支持 |

---

## 6. 约束与风险

### 6.1 技术约束

| 约束 | 影响 | 缓解策略 |
|------|------|---------|
| Dart 生态 AI 库不成熟 | MCP/RAG 需自建 | 最小可用实现，渐进增强 |
| 移动端计算受限 | 本地 RAG 性能 | 云端 Embedding + 本地存储 |
| 跨平台差异 | MCP Local Process | Mode B 仅桌面端 |

### 6.2 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| sqlite-vec Dart FFI 不稳定 | 中 | RAG 功能受阻 | 准备 fallback 方案 |
| MCP 协议变更 | 低 | 重构 MCPClient | 抽象层隔离 |
| 多模型 API 差异 | 高 | Provider 维护负担 | 能力声明 + 优雅降级 |

### 6.3 兼容性保证

```
┌─────────────────────────────────────────────────────────────┐
│                    兼容性原则                                │
├─────────────────────────────────────────────────────────────┤
│  1. 现有功能不破坏: 所有改动通过扩展而非修改                  │
│  2. 数据迁移透明: Hive 新字段使用可选类型                    │
│  3. 渐进式启用: 新功能通过 Feature Flag 控制                 │
│  4. 默认行为不变: Mode A 保持当前体验                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. 与竞品差异化定位

### 7.1 定位矩阵

```
                    功能丰富度
                        ↑
                        │
        Open WebUI ●    │    ● Cherry Studio
        (Web App)       │    (Electron)
                        │
                        │
        ────────────────┼────────────────→ 隐私/本地化
                        │
                        │    ● ChatBoxApp (目标)
        简单工具 ●       │    (Flutter Local-First)
                        │
```

### 7.2 独特卖点（USP）

| 卖点 | 说明 | 竞品对比 |
|------|------|---------|
| **Privacy-First** | 数据完全本地，用户自带 Key | Open WebUI 需要部署服务器 |
| **Zero Server Cost** | 无需后端服务器 | Cherry Studio 需要 Electron 后端 |
| **RP 专业支持** | 记忆系统、一致性检查、版本控制 | 无竞品有此功能 |
| **真正跨平台** | iOS/Android/Desktop/Web | Electron 仅桌面 |

---

## 8. Session 记录

### 8.1 Codex 分析 Session

```
SESSION_ID: 019bff7a-473b-7410-a5e0-96d4f49dac70
```

**关键结论**:
1. 三模式共存架构（纯前端/本地服务/云端）
2. HTTP/2 连接复用、prompt 压缩优化
3. RAG MVP: 云端 embedding + 本地存储
4. MCP 默认本地，企业可选远程
5. 四类插件接口（模型/RAG/工具/UI）

### 8.2 后续研究方向

- [ ] sqlite-vec Dart FFI 可行性验证
- [ ] MCPClient 协议实现细节
- [ ] Skills 配置格式设计
- [ ] Mode B Local Sidecar 架构

---

## 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-01-27 | 初版，基于多模型协作研究 |

