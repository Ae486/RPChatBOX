# MCP 集成提案

> OpenSpec 提案文档
> 状态: DRAFT
> 创建: 2026-02-04
> 前置文档: CONSTRAINT_SET.md

---

## 提案概述

为 ChatBoxApp 引入 MCP (Model Context Protocol) 支持，使 AI 助手能够调用外部工具、访问资源，实现更强大的能力扩展。

**核心价值**：
- 标准化的工具扩展机制
- 丰富的 MCP 服务器生态可复用
- 文件操作、数据库、API 集成等能力

---

## 问题陈述

### 当前状态

1. AI 助手仅能进行文本对话
2. 无法访问本地文件系统
3. 无法执行外部工具
4. 功能扩展需要自定义开发

### 核心需求

| 需求 | 优先级 | 说明 |
|------|--------|------|
| 工具调用 | P0 | 支持 LLM 调用外部工具 |
| 工具结果显示 | P0 | UI 展示工具执行过程和结果 |
| 服务器管理 | P1 | 用户配置和管理 MCP 服务器 |
| 资源访问 | P2 | 支持 MCP Resource 协议 |
| 提示模板 | P3 | 支持 MCP Prompts |

---

## 提案方案

### 架构决策

```
                    ┌─────────────────────┐
                    │   HybridLangChain   │
                    │      Provider       │
                    └──────────┬──────────┘
                               │
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
   ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
   │   LLM API     │   │ McpToolAdapter│   │ McpClientSvc  │
   │  (existing)   │   │   (新增)      │   │   (新增)      │
   └───────────────┘   └───────────────┘   └───────────────┘
                               │                   │
                               └─────────┬─────────┘
                                         ▼
                               ┌───────────────────┐
                               │   MCP Servers     │
                               └───────────────────┘
```

### 模块划分

| 模块 | 来源 | 理由 |
|------|------|------|
| MCP Client | mcp_dart 包 | 成熟、功能完整 |
| Tool Adapter | 自实现 | 与 HybridProvider 集成 |
| UI 组件 | 自实现 | 匹配现有 OWUI 风格 |
| 配置存储 | Hive | 现有基础设施 |

---

## 实施计划

### Phase 1: MCP 客户端基础

**目标**：建立 MCP 通信能力

**产出**：
- `lib/services/mcp_client_service.dart`
- `lib/models/mcp/mcp_server_config.dart`
- `lib/models/mcp/mcp_tool_call.dart`

### Phase 2: 工具执行集成

**目标**：LLM 能够调用 MCP 工具

**产出**：
- `lib/adapters/mcp_tool_adapter.dart`
- 扩展 `HybridLangChainProvider`
- 扩展 `StreamManager`

### Phase 3: UI 组件

**目标**：用户可见的工具调用体验

**产出**：
- `lib/chat_ui/owui/tool_call_bubble.dart`
- 扩展 `OwuiAssistantMessage`

### Phase 4: 配置管理

**目标**：用户可配置 MCP 服务器

**产出**：
- `lib/widgets/mcp_server_config_dialog.dart`
- `lib/chat_ui/owui/mcp_resource_sheet.dart`
- 设置页面集成

---

## 验收标准

### 功能验收

| 场景 | 预期结果 |
|------|---------|
| 连接 MCP 服务器 | 成功建立连接，获取工具列表 |
| 工具调用 | LLM 能调用工具，结果正确返回 |
| UI 展示 | ToolCallBubble 正确显示状态和结果 |
| 错误处理 | 连接失败/执行失败正确提示 |
| 服务器配置 | 可添加/删除/编辑服务器 |
| 移动端 | HTTP 传输正常工作 |

### 非功能验收

| 指标 | 要求 |
|------|------|
| 工具调用延迟 | 额外开销 < 100ms |
| 内存占用 | 增加 < 10MB |
| 连接稳定性 | 自动重连机制 |

---

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| mcp_dart 版本兼容 | 锁定版本，定期评估 |
| 移动端后台限制 | 前台服务 + 用户提示 |
| 安全性问题 | 严格权限控制 |
| UI 复杂度 | 渐进式功能暴露 |

---

## 决策请求

请确认以下决策：

1. **是否采用 mcp_dart 作为 MCP SDK？** (推荐: 是)
2. **移动端是否仅支持 HTTP 传输？** (推荐: 是)
3. **是否在 Phase 1 就支持多服务器？** (推荐: 是)
4. **高危工具是否强制用户确认？** (推荐: 是)

---

## 参考文档

- [CONSTRAINT_SET.md](./CONSTRAINT_SET.md) - 完整约束集
- [MCP 官方规范](https://spec.modelcontextprotocol.io/)
- [mcp_dart 文档](https://github.com/leehack/mcp_dart)
