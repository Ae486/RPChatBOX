# ChatBoxApp 内嵌 Python 后端 - 实施计划

> **文档类型**: Implementation Plan
> **创建日期**: 2025-02-02
> **状态**: Approved

---

## 1. 项目目标

为 ChatBoxApp 设计内嵌 Python 后端，支持：
- **MCP 工具集成**：作为 MCP Host 管理多个 MCP Server
- **RAG 知识库**：设备端向量存储和语义检索
- **LLM 代理**：统一处理 tool_call 循环
- **全平台支持**：桌面端（subprocess）+ Android（Chaquopy）

---

## 2. 架构概览

```
┌──────────────────────────────────────────────────────────┐
│                     Flutter App                          │
│   所有平台统一调用: http://localhost:8765/api/xxx        │
└──────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────┐
│                  Python 后端 (FastAPI)                   │
│                                                          │
│   桌面端: 独立进程 (PyInstaller 打包)                    │
│   Android: Chaquopy 内嵌运行                             │
│                                                          │
│   ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │
│   │  MCP Host   │ │ RAG Service │ │ LLM Proxy   │       │
│   └─────────────┘ └─────────────┘ └─────────────┘       │
└──────────────────────────────────────────────────────────┘
```

---

## 3. API 端点设计

### 3.1 健康检查

```
GET /api/health
Response: { "status": "ok", "version": "1.0.0" }
```

### 3.2 MCP 管理

#### 3.2.1 MCP Server 配置

```
# 获取所有配置的 MCP Server
GET /api/mcp/servers
Response: {
  "servers": [
    {
      "id": "tavily",
      "name": "Tavily Search",
      "type": "http",              # http | sse | stdio
      "url": "https://mcp.tavily.com/mcp",
      "enabled": true,
      "connected": true,
      "tools": ["tavily_search", "tavily_extract"]
    }
  ]
}

# 添加 MCP Server
POST /api/mcp/servers
Body: {
  "name": "Tavily Search",
  "type": "http",
  "url": "https://mcp.tavily.com/mcp?apiKey=xxx",
  "headers": {}
}
Response: { "id": "tavily", "status": "connected" }

# 更新 MCP Server
PUT /api/mcp/servers/{id}
Body: { "enabled": false }

# 删除 MCP Server
DELETE /api/mcp/servers/{id}

# 测试 MCP Server 连接
POST /api/mcp/servers/{id}/test
Response: { "status": "ok", "tools": [...], "latency_ms": 120 }
```

#### 3.2.2 MCP 工具操作

```
# 获取所有可用工具（合并所有 Server）
GET /api/mcp/tools
Response: {
  "tools": [
    {
      "name": "tavily_search",
      "server_id": "tavily",
      "description": "Search the web",
      "input_schema": { ... }
    }
  ]
}

# 手动调用工具（调试用）
POST /api/mcp/tools/{tool_name}/call
Body: { "arguments": { "query": "test" } }
Response: { "result": { ... }, "duration_ms": 500 }
```

### 3.3 RAG 知识库

#### 3.3.1 知识库管理

```
# 获取所有知识库
GET /api/rag/collections
Response: {
  "collections": [
    {
      "id": "default",
      "name": "默认知识库",
      "document_count": 42,
      "embedding_model": "text-embedding-3-small"
    }
  ]
}

# 创建知识库
POST /api/rag/collections
Body: {
  "name": "项目文档",
  "embedding_model": "text-embedding-3-small"  # 可选
}

# 删除知识库
DELETE /api/rag/collections/{id}
```

#### 3.3.2 文档索引

```
# 添加文档
POST /api/rag/collections/{id}/documents
Body: {
  "content": "文档内容...",
  "metadata": { "source": "manual", "title": "xxx" }
}
# 或上传文件
POST /api/rag/collections/{id}/documents/upload
Content-Type: multipart/form-data
file: (binary)

# 批量添加
POST /api/rag/collections/{id}/documents/batch
Body: {
  "documents": [
    { "content": "...", "metadata": {} }
  ]
}

# 删除文档
DELETE /api/rag/collections/{id}/documents/{doc_id}
```

#### 3.3.3 语义检索

```
POST /api/rag/collections/{id}/query
Body: {
  "query": "用户问题",
  "top_k": 5,
  "threshold": 0.7  # 可选，相似度阈值
}
Response: {
  "results": [
    {
      "content": "相关文档片段",
      "score": 0.85,
      "metadata": { "source": "..." }
    }
  ]
}
```

### 3.4 LLM 代理（核心端点）

```
# 聊天完成（兼容 OpenAI 格式）
POST /api/chat/completions
Body: {
  "model": "gpt-4o",
  "messages": [
    { "role": "user", "content": "搜索一下今天的新闻" }
  ],
  "stream": true,
  "temperature": 0.7,

  # 扩展字段
  "provider": {                    # LLM 提供商配置
    "type": "openai",
    "api_key": "sk-xxx",
    "api_url": "https://api.openai.com/v1"
  },
  "mcp_enabled": true,             # 是否启用 MCP 工具
  "mcp_servers": ["tavily"],       # 指定使用的 MCP Server（可选）
  "rag_enabled": true,             # 是否启用 RAG 增强
  "rag_collection": "default"      # 指定知识库（可选）
}

Response (stream=false):
{
  "id": "chatcmpl-xxx",
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "根据搜索结果..."
      }
    }
  ],
  "usage": { ... },
  "tool_calls_made": [             # 扩展：记录工具调用
    {
      "tool": "tavily_search",
      "arguments": { "query": "今天新闻" },
      "result_summary": "找到 10 条结果"
    }
  ]
}

Response (stream=true):
# SSE 格式
data: {"choices":[{"delta":{"role":"assistant"}}]}
data: {"choices":[{"delta":{"content":"根据"}}]}
data: {"choices":[{"delta":{"tool_call":{"name":"tavily_search","status":"executing"}}}]}
data: {"choices":[{"delta":{"tool_call":{"name":"tavily_search","status":"completed"}}}]}
data: {"choices":[{"delta":{"content":"搜索结果..."}}]}
data: [DONE]
```

### 3.5 配置管理

```
# 获取后端配置
GET /api/config
Response: {
  "default_embedding_model": "text-embedding-3-small",
  "mcp_timeout_ms": 30000,
  "rag_chunk_size": 500
}

# 更新配置
PATCH /api/config
Body: { "mcp_timeout_ms": 60000 }
```

---

## 4. 数据模型

### 4.1 MCP Server 配置

```python
class MCPServerConfig(BaseModel):
    id: str
    name: str
    type: Literal["http", "sse", "stdio"]

    # HTTP/SSE 类型
    url: Optional[str] = None
    headers: Dict[str, str] = {}

    # stdio 类型（仅桌面端）
    command: Optional[str] = None
    args: List[str] = []
    env: Dict[str, str] = {}

    enabled: bool = True
    created_at: datetime
    updated_at: datetime
```

### 4.2 RAG 文档

```python
class RAGDocument(BaseModel):
    id: str
    collection_id: str
    content: str
    embedding: List[float]
    metadata: Dict[str, Any]
    created_at: datetime
```

---

## 5. 内部处理流程

### 5.1 /chat/completions 处理流程

```
1. 接收请求
2. 如果 rag_enabled:
   - 用用户消息做语义检索
   - 将检索结果注入 system prompt
3. 如果 mcp_enabled:
   - 收集所有启用的 MCP Server 的工具定义
   - 转换为 LLM 的 tools 格式
4. 调用 LLM API（带 tools）
5. 循环处理 tool_calls:
   while response.has_tool_calls:
     - 执行 MCP tool call
     - 将结果发回 LLM
     - 如果 stream=true，实时推送工具执行状态
6. 返回最终响应
```

---

## 6. 文件结构

```
backend/
├── main.py                    # FastAPI 入口
├── config.py                  # 配置管理
├── requirements.txt
│
├── api/                       # API 路由
│   ├── __init__.py
│   ├── health.py
│   ├── mcp.py                 # MCP 相关端点
│   ├── rag.py                 # RAG 相关端点
│   └── chat.py                # LLM 代理端点
│
├── services/                  # 业务逻辑
│   ├── __init__.py
│   ├── mcp_host.py            # MCP Host 实现
│   ├── rag_service.py         # RAG 服务
│   ├── llm_proxy.py           # LLM 代理
│   └── embedding_service.py   # Embedding 服务
│
├── models/                    # 数据模型
│   ├── __init__.py
│   ├── mcp.py
│   ├── rag.py
│   └── chat.py
│
└── storage/                   # 本地存储
    ├── mcp_config.json        # MCP Server 配置
    └── chroma_db/             # ChromaDB 向量数据
```

---

## 7. 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| Web 框架 | FastAPI | 异步、类型安全、自动文档 |
| MCP SDK | mcp (官方) | 官方维护，功能完整 |
| 向量数据库 | ChromaDB | 轻量、嵌入式、pip 安装 |
| Embedding | OpenAI API | 用户已有 key，质量高 |
| 桌面打包 | PyInstaller | 单文件可执行 |
| Android 集成 | Chaquopy | Flutter 官方推荐 |

---

## 8. 实现阶段

### Phase 1: 基础框架
- [ ] FastAPI 项目结构
- [ ] 健康检查 API
- [ ] 基础配置管理
- [ ] Flutter 端 BackendService 类

### Phase 2: MCP 集成
- [ ] MCP Server 配置管理
- [ ] HTTP/SSE 类型 MCP 连接
- [ ] 工具列表获取
- [ ] 工具调用执行
- [ ] Flutter 端 MCP 管理 UI

### Phase 3: LLM 代理
- [ ] /chat/completions 端点
- [ ] Tool call 循环处理
- [ ] 流式响应支持
- [ ] Flutter 端对接（替换直连）

### Phase 4: RAG 功能
- [ ] ChromaDB 集成
- [ ] 文档索引 API
- [ ] 语义检索 API
- [ ] RAG 增强聊天
- [ ] Flutter 端知识库管理 UI

### Phase 5: 打包部署
- [ ] PyInstaller 桌面打包
- [ ] Chaquopy Android 集成
- [ ] 自动启动机制
- [ ] 错误处理和日志

---

## 9. 验证方式

### 9.1 单元测试
```bash
cd backend
pytest tests/
```

### 9.2 API 测试
```bash
# 启动后端
uvicorn main:app --port 8765

# 测试健康检查
curl http://localhost:8765/api/health

# 测试 MCP 工具列表
curl http://localhost:8765/api/mcp/tools

# 测试聊天
curl -X POST http://localhost:8765/api/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o","messages":[{"role":"user","content":"hello"}]}'
```

### 9.3 Flutter 端集成测试
```bash
cd chatboxapp
flutter test test/integration/backend_test.dart
```

---

## 10. 安全考虑

- API Key 仅在请求中传递，后端不持久化
- localhost 绑定，不暴露外网
- 敏感操作需要确认（如 stdio MCP 执行命令）
- 工具执行超时控制

---

## 11. 架构决策记录

### ADR-001: LLM 通信全量迁移到后端

**背景**: 最初计划仅将 MCP/RAG 相关请求走后端，简单对话保持直连。

**决策**: 采用全量迁移方案，所有 LLM 请求都通过 Python 后端。

**理由**:
1. MCP tool_call 循环必须在后端处理，如果保留前端直连会导致架构分裂
2. Python SDK 更新更快，适配新模型更容易
3. 10-50ms 额外延迟在 LLM 响应时间面前可忽略
4. Flutter 端可大幅简化

**后果**:
- 需要实现完整的 SSE 代理
- 需要实现 fallback 机制确保可靠性

### ADR-002: 保留直连作为回滚选项

**背景**: 全量迁移存在风险，需要降级方案。

**决策**: 保留现有 `OpenAIProvider`/`LangChainProvider` 实现，通过 `backendMode` 配置切换。

**理由**:
1. 迁移期间可随时回滚
2. 调试时可排除后端因素
3. 后端异常时可自动回退（auto 模式）

**后果**:
- 需要维护两套 Provider 实现
- 需要实现 Circuit Breaker 控制回退逻辑

---

## 相关文档

- [CONSTRAINT_SET.md](./CONSTRAINT_SET.md) - 详细约束列表
- [OPENSPEC_PROPOSAL.md](./OPENSPEC_PROPOSAL.md) - OpenSpec 技术提案
