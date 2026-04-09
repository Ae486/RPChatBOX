# MCP (Model Context Protocol) 集成约束集

> 生成时间: 2026-02-04
> 分析范围: MCP 协议在 Flutter LLM 客户端的实现方案
> 前置调研: Codex 后端分析 + Gemini 前端分析 + DeepWiki/Tavily 资料

---

## 1. 执行摘要

**核心结论**：MCP 在 Flutter 中实现完全可行，已有成熟的 Dart SDK 支持。推荐采用 `mcp_dart` 包，通过 Adapter 模式将 MCP Tools 集成到现有 LLM 调用流程。

| 维度 | 方案 | 推荐 |
|------|------|------|
| SDK 选择 | mcp_dart vs dart_mcp | mcp_dart (功能更全) |
| 传输层 | Stdio vs HTTP | 移动端用 HTTP，桌面可选 |
| 集成方式 | 独立层 vs 嵌入 Provider | 独立服务层 + Adapter |
| UI 模式 | 内联 vs 独立气泡 | 独立 ToolCallBubble |

---

## 2. MCP 协议概述

### 2.1 核心概念

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   MCP Host      │     │   MCP Client    │     │   MCP Server    │
│ (ChatBoxApp)    │<--->│ (mcp_dart)      │<--->│ (外部服务)       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

**三大核心能力**：

| 能力 | 描述 | 示例 |
|------|------|------|
| **Tools** | 可执行操作 | 文件读写、API 调用、数据库查询 |
| **Resources** | 上下文数据 | 文件内容、配置、文档 |
| **Prompts** | 预构建模板 | 代码生成模板、分析模板 |

### 2.2 协议版本

- **当前最新**: `2025-11-25`
- **向后兼容**: `2025-06-18`, `2025-03-26`, `2024-11-05`

### 2.3 通信流程

```
1. 初始化: initialize → InitializeResult → notifications/initialized
2. 发现: tools/list, resources/list, prompts/list
3. 调用: tools/call → Result
```

---

## 3. Dart/Flutter SDK 对比

### 3.1 可选方案

| 包名 | 维护者 | 版本 | 特点 | 推荐度 |
|------|-------|------|------|--------|
| **mcp_dart** | leehack | 1.2.2 | 功能最全、文档好、CLI 工具 | ★★★★★ |
| **dart_mcp** | Dart 官方 | 0.4.1 | 官方支持、稳定 | ★★★★☆ |
| **mcp_client** | app-appplayer | 1.0.2 | 客户端专用 | ★★★☆☆ |

### 3.2 mcp_dart 能力矩阵

| 能力 | 支持状态 |
|------|---------|
| Tools | ✅ 完整支持 |
| Resources | ✅ 完整支持 |
| Prompts | ✅ 完整支持 |
| Sampling | ✅ 支持 |
| Roots | ✅ 支持 |
| OAuth2 | ✅ 支持 |
| Stdio Transport | ✅ 支持 |
| HTTP Transport | ✅ 支持 |
| Stream Transport | ✅ 支持 |

### 3.3 平台支持

| 平台 | Stdio | HTTP | WebSocket |
|------|-------|------|-----------|
| Windows | ✅ | ✅ | ✅ |
| macOS | ✅ | ✅ | ✅ |
| Linux | ✅ | ✅ | ✅ |
| **Android** | ❌ | ✅ | ✅ |
| **iOS** | ❌ | ✅ | ✅ |
| Web | ❌ | ✅ | ✅ |

---

## 4. 约束定义

### 4.1 硬约束 (MUST)

| ID | 约束 | 原因 |
|----|------|------|
| HC-01 | **移动端仅支持 HTTP/WebSocket 传输** | 移动端无法稳定运行 stdio 子进程 |
| HC-02 | **工具执行结果必须显示在 UI** | 用户需要可见性 |
| HC-03 | **敏感工具执行前必须用户确认** | 安全性要求 |
| HC-04 | **MCP 错误必须映射到 ApiError** | 统一错误处理 |
| HC-05 | **不能阻塞 UI 线程** | 工具执行异步化 |

### 4.2 软约束 (SHOULD)

| ID | 约束 | 原因 |
|----|------|------|
| SC-01 | 应支持多 MCP 服务器同时连接 | 灵活性 |
| SC-02 | 应支持工具执行取消 | 用户控制 |
| SC-03 | 应缓存服务器能力列表 | 性能 |
| SC-04 | 应支持服务器自动重连 | 稳定性 |
| SC-05 | 工具调用应显示耗时 | 用户体验 |

### 4.3 禁止约束 (MUST NOT)

| ID | 约束 | 原因 |
|----|------|------|
| PC-01 | **禁止在移动端使用 stdio 传输** | 不稳定 |
| PC-02 | **禁止存储 MCP 服务器密钥明文** | 安全性 |
| PC-03 | **禁止自动执行高危工具** | 安全性 |

---

## 5. 架构设计

### 5.1 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                        ChatBoxApp (Flutter)                       │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │                      UI Layer                               │  │
│  │  + OwuiToolCallBubble (新增)                               │  │
│  │  + OwuiMcpResourceSheet (新增)                             │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
│                             │                                     │
│  ┌──────────────────────────▼─────────────────────────────────┐  │
│  │                    Service Layer                            │  │
│  │  ┌─────────────────┐     ┌─────────────────────────────┐   │  │
│  │  │  LLM Services   │     │   McpClientService (新增)   │   │  │
│  │  │  (existing)     │<--->│   - Server Management       │   │  │
│  │  │                 │     │   - Tool Execution          │   │  │
│  │  │                 │     │   - Resource Access         │   │  │
│  │  └────────┬────────┘     └──────────────┬──────────────┘   │  │
│  └───────────┼────────────────────────────┼──────────────────┘  │
│              │                             │                      │
│  ┌───────────▼─────────────────────────────▼──────────────────┐  │
│  │                    Adapter Layer                            │  │
│  │  ┌─────────────────┐     ┌─────────────────────────────┐   │  │
│  │  │ HybridLangChain │     │   McpToolAdapter (新增)     │   │  │
│  │  │ Provider        │<--->│   Tool → Function Call      │   │  │
│  │  └─────────────────┘     └─────────────────────────────┘   │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   ┌───────────┐       ┌───────────┐       ┌───────────┐
   │ MCP Server│       │ MCP Server│       │ MCP Server│
   │ (Local)   │       │ (Remote)  │       │ (Custom)  │
   └───────────┘       └───────────┘       └───────────┘
```

### 5.2 关键组件

| 组件 | 文件 | 职责 |
|------|------|------|
| `McpClientService` | `lib/services/mcp_client_service.dart` | 服务器连接、工具执行 |
| `McpToolAdapter` | `lib/adapters/mcp_tool_adapter.dart` | Tool → Function Call 转换 |
| `McpServerConfig` | `lib/models/mcp/mcp_server_config.dart` | 服务器配置模型 |
| `McpToolCallData` | `lib/models/mcp/mcp_tool_call.dart` | 工具调用状态模型 |
| `OwuiToolCallBubble` | `lib/chat_ui/owui/tool_call_bubble.dart` | 工具调用 UI 组件 |

### 5.3 Hive TypeId 分配

| TypeId | 模型 |
|--------|------|
| 60 | `McpServerConfig` |
| 61 | `McpToolCallRecord` |

---

## 6. UI 设计规范

### 6.1 ToolCallBubble 视觉设计

```
┌──────────────────────────────────────────────────────────┐
│ [🔧] tool_name · server_name · 3.2s                  [▼] │
├──────────────────────────────────────────────────────────┤
│ 参数: {"path": "/docs", "recursive": true}               │
├──────────────────────────────────────────────────────────┤
│ (展开后)                                                 │
│ ┌─ 输入 ───────────────────────────────────────────────┐ │
│ │ {"path": "/docs", "recursive": true}                 │ │
│ └──────────────────────────────────────────────────────┘ │
│ ┌─ 输出 ───────────────────────────────────────────────┐ │
│ │ Found 15 files...                                    │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### 6.2 状态颜色

| 状态 | 颜色 | 图标动画 |
|------|------|---------|
| pending | `Colors.grey` | 无 |
| running | `Colors.amber` | 脉冲动画 |
| success | `Colors.green` | 淡入 |
| error | `Colors.red` | 抖动 |

### 6.3 消息渲染顺序

```
OwuiAssistantMessage:
├── ThinkingBubble (if any)
├── ToolCallBubble[] (if any)  ← 新增
├── Markdown Body
└── Images (if any)
```

---

## 7. 移动端约束

### 7.1 传输层限制

| 平台 | 推荐传输 | 原因 |
|------|---------|------|
| Android | HTTP (SSE/WebSocket) | 进程管理受限 |
| iOS | HTTP (SSE/WebSocket) | 沙箱限制 |

### 7.2 后台执行

- Android: 使用 `flutter_foreground_task` 前台服务
- iOS: 使用 `beginBackgroundTask` (限时 ~30s)
- 长任务需提示用户保持前台

### 7.3 权限需求

| 权限 | Android | iOS |
|------|---------|-----|
| 网络 | `INTERNET` | 默认 |
| 文件 | `READ_EXTERNAL_STORAGE` | `NSDocumentDirectory` |
| 后台 | `FOREGROUND_SERVICE` | `UIBackgroundModes` |

---

## 8. 安全考虑

### 8.1 服务器验证

- 仅允许连接用户配置的服务器
- 远程服务器强制 HTTPS
- 支持 OAuth2 认证

### 8.2 工具执行控制

| 工具类型 | 执行前确认 | 示例 |
|---------|-----------|------|
| 读取类 | 可选 | `read_file`, `list_directory` |
| 写入类 | **必须** | `write_file`, `delete_file` |
| 系统类 | **必须** | `execute_command`, `install_package` |

### 8.3 数据隔离

- MCP 服务器无法直接访问 App 沙箱
- 文件资源通过 MCP Resource 协议传递

---

## 9. 实施路线图

### Phase 1: 基础设施 (Week 1-2)

- [ ] 集成 `mcp_dart` 包
- [ ] 实现 `McpClientService` 基础框架
- [ ] 创建 `McpServerConfig` 数据模型
- [ ] 支持 HTTP Transport

### Phase 2: 核心功能 (Week 2-3)

- [ ] 实现服务器连接管理
- [ ] 实现工具发现和调用
- [ ] 实现 `McpToolAdapter`
- [ ] 集成到 `HybridLangChainProvider`

### Phase 3: UI 组件 (Week 3-4)

- [ ] 创建 `OwuiToolCallBubble`
- [ ] 扩展 `StreamManager` 支持工具调用
- [ ] 集成到 `OwuiAssistantMessage`

### Phase 4: 配置界面 (Week 4-5)

- [ ] MCP 服务器管理 UI
- [ ] 资源选择器 UI
- [ ] Composer 扩展

### Phase 5: 移动端优化 (Week 5-6)

- [ ] 后台执行支持
- [ ] 权限请求流程
- [ ] 平台特定适配

---

## 10. 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| mcp_dart 库不稳定 | 中 | 锁定版本，保持更新 |
| 移动端后台限制 | 中 | 前台服务 + 用户提示 |
| 安全漏洞 | 高 | 严格权限控制 + 白名单 |
| 协议版本兼容 | 低 | 使用支持多版本的库 |
| UI 复杂度 | 中 | 渐进式暴露功能 |

---

## 附录 A: mcp_dart 使用示例

```dart
import 'package:mcp_dart/mcp_dart.dart';

// 创建客户端
final client = Client(Implementation(name: 'ChatBoxApp', version: '1.0.0'));

// HTTP 传输连接
final transport = StreamableHttpClientTransport(Uri.parse('http://localhost:8080/mcp'));
await client.connect(transport);

// 发现工具
final tools = await client.listTools();

// 调用工具
final result = await client.callTool(
  CallToolRequestParams(
    name: 'read_file',
    arguments: {'path': '/tmp/test.txt'},
  ),
);

// 关闭连接
await client.close();
```

## 附录 B: 相关文档

- MCP 官方规范: https://spec.modelcontextprotocol.io/
- mcp_dart GitHub: https://github.com/leehack/mcp_dart
- Flutter MCP Server: https://docs.flutter.dev/ai/mcp-server
