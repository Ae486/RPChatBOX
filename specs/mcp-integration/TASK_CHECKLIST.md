# MCP 集成实施计划

> 生成时间: 2026-02-04
> 基于: CONSTRAINT_SET.md + PROPOSAL.md + 多模型分析
> 状态: READY_FOR_EXECUTION

---

## 决策确认

根据架构分析和前端分析的综合结论：

| 决策点 | 结论 | 理由 |
|--------|------|------|
| SDK 选择 | **mcp_dart 1.2.2** | 功能完整、文档好、支持所有传输方式 |
| 移动端传输 | **仅 HTTP/WebSocket** | 移动端无法稳定运行 stdio 子进程 |
| 多服务器支持 | **Phase 1 支持** | 架构设计天然支持，无额外成本 |
| 高危工具确认 | **必须用户确认** | 安全性要求 |

---

## Phase 1: MCP 客户端基础设施

### 1.1 添加 mcp_dart 依赖

**文件**: `pubspec.yaml`

```yaml
dependencies:
  # MCP 客户端
  mcp_dart: ^1.2.2
```

**验收**: `flutter pub get` 成功

---

### 1.2 创建 MCP 数据模型

**文件**: `lib/models/mcp/mcp_server_config.dart`

```dart
/// MCP 服务器配置模型
/// Hive TypeId: 60
@HiveType(typeId: 60)
class McpServerConfig {
  @HiveField(0)
  final String id;

  @HiveField(1)
  final String name;

  @HiveField(2)
  final String transportType; // 'http' | 'stdio' | 'websocket'

  @HiveField(3)
  final String? url; // HTTP/WebSocket URL

  @HiveField(4)
  final String? command; // Stdio command

  @HiveField(5)
  final List<String>? args; // Stdio args

  @HiveField(6)
  final Map<String, String>? env; // Environment variables

  @HiveField(7)
  final bool enabled;

  @HiveField(8)
  final DateTime createdAt;

  @HiveField(9)
  final DateTime? lastConnectedAt;
}
```

**验收**:
- [ ] 模型定义完成
- [ ] `flutter pub run build_runner build` 生成 .g.dart
- [ ] Hive adapter 注册

---

### 1.3 创建 MCP 工具调用数据模型

**文件**: `lib/models/mcp/mcp_tool_call.dart`

```dart
/// 工具调用状态枚举
enum ToolCallStatus {
  pending,  // 等待执行
  running,  // 执行中
  success,  // 成功
  error,    // 失败
}

/// 工具调用数据（流式状态，不持久化）
class ToolCallData {
  final String callId;
  final String toolName;
  final String? serverName;
  ToolCallStatus status;
  DateTime? startTime;
  DateTime? endTime;
  Map<String, dynamic>? arguments;
  String? result;
  String? errorMessage;

  int? get durationMs {
    if (startTime == null) return null;
    final end = endTime ?? DateTime.now();
    return end.difference(startTime!).inMilliseconds;
  }
}

/// 工具调用记录（持久化）
/// Hive TypeId: 61
@HiveType(typeId: 61)
class McpToolCallRecord {
  @HiveField(0)
  final String callId;

  @HiveField(1)
  final String messageId;

  @HiveField(2)
  final String toolName;

  @HiveField(3)
  final String? serverName;

  @HiveField(4)
  final String status; // pending/running/success/error

  @HiveField(5)
  final int? durationMs;

  @HiveField(6)
  final String? argumentsJson;

  @HiveField(7)
  final String? result;

  @HiveField(8)
  final String? errorMessage;

  @HiveField(9)
  final DateTime timestamp;
}
```

**验收**:
- [ ] ToolCallData 定义完成
- [ ] McpToolCallRecord 定义完成
- [ ] 生成 Hive adapter

---

### 1.4 创建 MCP 客户端服务

**文件**: `lib/services/mcp_client_service.dart`

```dart
/// MCP 客户端服务
/// 负责管理多个 MCP 服务器连接、工具发现和执行
class McpClientService extends ChangeNotifier {
  final Map<String, Client> _clients = {};
  final Map<String, List<Tool>> _toolsCache = {};
  final Map<String, McpServerConfig> _configs = {};

  // ===== 连接管理 =====

  /// 添加服务器配置
  Future<void> addServer(McpServerConfig config);

  /// 连接到服务器
  Future<void> connect(String serverId);

  /// 断开服务器连接
  Future<void> disconnect(String serverId);

  /// 获取服务器连接状态
  McpConnectionStatus getStatus(String serverId);

  // ===== 工具发现 =====

  /// 获取所有可用工具
  List<McpTool> getAllTools();

  /// 获取指定服务器的工具
  List<McpTool> getServerTools(String serverId);

  /// 刷新服务器工具列表
  Future<void> refreshTools(String serverId);

  // ===== 工具执行 =====

  /// 执行工具
  Future<McpToolResult> callTool({
    required String serverId,
    required String toolName,
    required Map<String, dynamic> arguments,
  });

  // ===== 生命周期 =====

  /// 启动服务（连接所有已启用的服务器）
  Future<void> start();

  /// 停止服务（断开所有连接）
  Future<void> stop();

  @override
  void dispose();
}
```

**验收**:
- [ ] 服务框架实现
- [ ] HTTP Transport 连接测试
- [ ] 工具发现测试
- [ ] 工具执行测试

---

### 1.5 创建平台特定的 Transport Factory

**文件**: `lib/services/mcp_transport_factory.dart`

```dart
/// MCP Transport 工厂
/// 根据平台和配置创建合适的传输层
class McpTransportFactory {
  /// 创建 Transport
  /// - 移动端: 仅支持 HTTP/WebSocket
  /// - 桌面端: 支持 Stdio/HTTP/WebSocket
  static Transport create(McpServerConfig config) {
    if (Platform.isAndroid || Platform.isIOS) {
      if (config.transportType == 'stdio') {
        throw UnsupportedError('Stdio transport not supported on mobile');
      }
    }

    switch (config.transportType) {
      case 'http':
        return StreamableHttpClientTransport(Uri.parse(config.url!));
      case 'websocket':
        return WebSocketClientTransport(Uri.parse(config.url!));
      case 'stdio':
        return StdioClientTransport(
          command: config.command!,
          args: config.args ?? [],
          env: config.env,
        );
      default:
        throw ArgumentError('Unknown transport type: ${config.transportType}');
    }
  }
}
```

**验收**:
- [ ] HTTP Transport 创建
- [ ] WebSocket Transport 创建
- [ ] Stdio Transport 创建（桌面端）
- [ ] 移动端 Stdio 抛出正确异常

---

## Phase 2: 工具执行集成

### 2.1 创建 MCP Tool Adapter

**文件**: `lib/adapters/mcp_tool_adapter.dart`

```dart
/// MCP Tool → LLM Function Call 适配器
/// 将 MCP 工具转换为 OpenAI function calling 格式
class McpToolAdapter {
  final McpClientService _mcpService;

  /// 获取所有工具定义（OpenAI 格式）
  List<Map<String, dynamic>> getToolDefinitions() {
    final tools = _mcpService.getAllTools();
    return tools.map((tool) => {
      'type': 'function',
      'function': {
        'name': _encodeToolName(tool.serverId, tool.name),
        'description': tool.description,
        'parameters': tool.inputSchema,
      },
    }).toList();
  }

  /// 执行工具调用
  Future<String> executeToolCall(String encodedName, Map<String, dynamic> args) async {
    final (serverId, toolName) = _decodeToolName(encodedName);
    final result = await _mcpService.callTool(
      serverId: serverId,
      toolName: toolName,
      arguments: args,
    );
    return result.toJson();
  }

  /// 编码工具名称: server__toolname
  String _encodeToolName(String serverId, String toolName);

  /// 解码工具名称
  (String serverId, String toolName) _decodeToolName(String encoded);
}
```

**验收**:
- [ ] 工具定义转换正确
- [ ] 工具名称编解码正确
- [ ] 工具执行返回正确结果

---

### 2.2 创建 Tool Call Extractor

**文件**: `lib/adapters/sse/tool_call_extractor.dart`

```dart
/// Tool Call 提取器
/// 从 SSE delta 中提取工具调用
class ToolCallExtractor {
  final Map<int, _ToolCallAccumulator> _accumulators = {};

  /// 提取工具调用事件
  /// 返回: List<ToolCallEvent> (started/updated/completed)
  List<ToolCallEvent> extract(Map<String, dynamic> delta) {
    final toolCalls = delta['tool_calls'] as List?;
    if (toolCalls == null) return [];

    final events = <ToolCallEvent>[];

    for (final tc in toolCalls) {
      final index = tc['index'] as int;
      final id = tc['id'] as String?;
      final function = tc['function'] as Map<String, dynamic>?;

      if (id != null) {
        // 新工具调用开始
        _accumulators[index] = _ToolCallAccumulator(
          id: id,
          name: function?['name'] ?? '',
          arguments: '',
        );
        events.add(ToolCallStarted(callId: id, name: function?['name'] ?? ''));
      }

      if (function?['arguments'] != null) {
        // 参数累积
        _accumulators[index]?.arguments += function!['arguments'] as String;
      }
    }

    return events;
  }

  /// 获取已完成的工具调用
  List<CompletedToolCall> getCompletedCalls() {
    return _accumulators.values
        .where((a) => a.isComplete)
        .map((a) => CompletedToolCall(
          callId: a.id,
          name: a.name,
          arguments: jsonDecode(a.arguments),
        ))
        .toList();
  }

  /// 重置状态
  void reset() => _accumulators.clear();
}

/// 工具调用事件
sealed class ToolCallEvent {}

class ToolCallStarted extends ToolCallEvent {
  final String callId;
  final String name;
  ToolCallStarted({required this.callId, required this.name});
}

class ToolCallArgumentsUpdated extends ToolCallEvent {
  final String callId;
  final String partialArguments;
  ToolCallArgumentsUpdated({required this.callId, required this.partialArguments});
}

class ToolCallCompleted extends ToolCallEvent {
  final String callId;
  final String name;
  final Map<String, dynamic> arguments;
  ToolCallCompleted({required this.callId, required this.name, required this.arguments});
}
```

**验收**:
- [ ] 正确解析 tool_calls delta
- [ ] 正确累积 arguments
- [ ] 正确发出开始/更新/完成事件

---

### 2.3 扩展 HybridLangChainProvider

**文件**: `lib/adapters/hybrid_langchain_provider.dart`

修改内容:

1. 添加 `McpToolAdapter` 依赖
2. 在请求体中添加 `tools` 定义
3. 使用 `ToolCallExtractor` 解析工具调用
4. Yield tool call 事件

```dart
class HybridLangChainProvider extends AIProvider {
  McpToolAdapter? _mcpAdapter;

  void setMcpAdapter(McpToolAdapter adapter) {
    _mcpAdapter = adapter;
  }

  @override
  Stream<String> sendMessageStream({...}) async* {
    // ... existing code ...

    final toolCallExtractor = ToolCallExtractor();

    await for (final event in sseStream) {
      switch (event) {
        case SseDataEvent(:final data):
          // Extract tool calls
          final toolEvents = toolCallExtractor.extract(
            data['choices']?[0]?['delta'] ?? {}
          );
          for (final te in toolEvents) {
            yield _encodeToolCallEvent(te);
          }

          // ... existing content extraction ...
      }
    }
  }

  /// 编码工具调用事件为特殊格式字符串
  /// 格式: <tool_call:event_type>json</tool_call>
  String _encodeToolCallEvent(ToolCallEvent event);
}
```

**验收**:
- [ ] 工具定义正确添加到请求
- [ ] 工具调用事件正确提取
- [ ] 工具调用事件正确 yield

---

### 2.4 扩展 StreamManager

**文件**: `lib/widgets/stream_manager.dart`

修改内容:

```dart
class StreamData {
  // ... existing fields ...

  // NEW: Tool calls tracking
  List<ToolCallData> toolCalls = [];
}

class StreamManager extends ChangeNotifier {
  // ... existing code ...

  /// 解析工具调用事件标签
  static const _toolCallStartTag = '<tool_call:started>';
  static const _toolCallEndTag = '</tool_call>';

  /// 添加工具调用
  void addToolCall(String streamId, ToolCallData toolCall) {
    final data = _streams[streamId];
    if (data == null) return;

    data.toolCalls = [...data.toolCalls, toolCall];
    notifyListeners();
  }

  /// 更新工具调用状态为 running
  void startToolCall(String streamId, String callId) {
    final data = _streams[streamId];
    if (data == null) return;

    final idx = data.toolCalls.indexWhere((tc) => tc.callId == callId);
    if (idx == -1) return;

    data.toolCalls[idx].status = ToolCallStatus.running;
    data.toolCalls[idx].startTime = DateTime.now();
    notifyListeners();
  }

  /// 完成工具调用
  void completeToolCall(
    String streamId,
    String callId, {
    required bool success,
    String? result,
    String? errorMessage,
  }) {
    final data = _streams[streamId];
    if (data == null) return;

    final idx = data.toolCalls.indexWhere((tc) => tc.callId == callId);
    if (idx == -1) return;

    data.toolCalls[idx].status = success
        ? ToolCallStatus.success
        : ToolCallStatus.error;
    data.toolCalls[idx].endTime = DateTime.now();
    data.toolCalls[idx].result = result;
    data.toolCalls[idx].errorMessage = errorMessage;
    notifyListeners();
  }

  /// 扩展 _parseThinkingContent 以处理工具调用标签
  void _parseContent(StreamData data, String chunk) {
    // Parse tool call tags
    // Parse thinking tags (existing)
    // Append remaining content
  }
}
```

**验收**:
- [ ] ToolCallData 添加到 StreamData
- [ ] 工具调用状态更新正确
- [ ] 工具调用标签解析正确
- [ ] notifyListeners 正确触发

---

## Phase 3: UI 组件

### 3.1 创建 OwuiToolCallBubble

**文件**: `lib/chat_ui/owui/tool_call_bubble.dart`

组件实现要点：

1. **状态样式**:
   - pending: 灰色，无动画
   - running: 琥珀色，脉冲动画
   - success: 绿色，淡入
   - error: 红色，抖动

2. **布局**:
   - 折叠: 图标 + 工具名 + 服务器 + 耗时 + 参数摘要
   - 展开: 完整参数 + 完整结果

3. **动画**:
   - 脉冲: 参考 OwuiThinkBubble._breatheAnimation
   - 抖动: 水平位移 3 次

```dart
class OwuiToolCallBubble extends StatefulWidget {
  final String callId;
  final String toolName;
  final String? serverName;
  final ToolCallStatus status;
  final int? durationMs;
  final Map<String, dynamic>? arguments;
  final String? result;
  final String? errorMessage;
  final double uiScale;

  const OwuiToolCallBubble({...});
}

class _OwuiToolCallBubbleState extends State<OwuiToolCallBubble>
    with TickerProviderStateMixin {
  bool _expanded = false;
  late AnimationController _pulseController;
  late AnimationController _shakeController;

  // ... implementation ...
}
```

**验收**:
- [ ] 4 种状态样式正确
- [ ] 脉冲动画 (running) 正常
- [ ] 抖动动画 (error) 正常
- [ ] 展开/折叠正常
- [ ] 参数/结果 JSON 格式化显示

---

### 3.2 扩展 OwuiAssistantMessage

**文件**: `lib/chat_ui/owui/assistant_message.dart`

修改内容:

```dart
class OwuiAssistantMessage extends StatelessWidget {
  // ... existing props ...

  /// 工具调用列表
  final List<ToolCallData> toolCalls;

  const OwuiAssistantMessage({
    // ... existing ...
    this.toolCalls = const [],
  });

  @override
  Widget build(BuildContext context) {
    final children = <Widget>[
      // Header (existing)
      // ThinkingBubble (existing)
    ];

    // NEW: ToolCallBubbles
    if (toolCalls.isNotEmpty) {
      children.add(
        Padding(
          padding: EdgeInsets.only(bottom: 10 * uiScale),
          child: Column(
            children: toolCalls.map((tc) => Padding(
              padding: EdgeInsets.only(bottom: 6 * uiScale),
              child: OwuiToolCallBubble(
                key: ValueKey('${messageId}_tool_${tc.callId}'),
                callId: tc.callId,
                toolName: tc.toolName,
                serverName: tc.serverName,
                status: tc.status,
                durationMs: tc.durationMs,
                arguments: tc.arguments,
                result: tc.result,
                errorMessage: tc.errorMessage,
                uiScale: uiScale,
              ),
            )).toList(),
          ),
        ),
      );
    }

    // Loading indicator - 修改条件
    if (isStreaming && bodyMarkdown.trim().isEmpty &&
        thinking.trim().isEmpty && !thinkingOpen &&
        toolCalls.isEmpty) {  // 新增条件
      children.add(IsTypingIndicator(...));
    }

    // Body Markdown (existing)
    // Images (existing)
  }
}
```

**验收**:
- [ ] toolCalls prop 添加
- [ ] ToolCallBubble 渲染位置正确
- [ ] Loading 条件更新正确
- [ ] 无 toolCalls 时向后兼容

---

### 3.3 添加工具图标

**文件**: `lib/chat_ui/owui/owui_icons.dart`

```dart
class OwuiIcons {
  // ... existing icons ...

  /// 工具/扳手图标
  static const IconData tool = Icons.build_outlined;

  /// 工具成功图标
  static const IconData toolSuccess = Icons.check_circle_outline;

  /// 工具失败图标
  static const IconData toolError = Icons.error_outline;
}
```

**验收**:
- [ ] 图标定义完成
- [ ] 图标在 ToolCallBubble 中正确显示

---

### 3.4 扩展 OwuiChatTheme

**文件**: `lib/chat_ui/owui/chat_theme.dart`

```dart
class OwuiChatTheme {
  // ... existing ...

  /// 工具调用装饰
  static BoxDecoration toolCallDecoration(
    BuildContext context,
    ToolCallStatus status,
  ) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final (bgColor, borderColor) = switch (status) {
      ToolCallStatus.pending => (
        isDark ? const Color(0xFF1F1F1F) : const Color(0xFFF5F5F5),
        isDark ? Colors.white.withOpacity(0.1) : Colors.black.withOpacity(0.06),
      ),
      ToolCallStatus.running => (
        isDark ? const Color(0xFF2A2517) : const Color(0xFFFFFBEB),
        Colors.amber.withOpacity(0.3),
      ),
      ToolCallStatus.success => (
        isDark ? const Color(0xFF1A2A1F) : const Color(0xFFECFDF5),
        Colors.green.withOpacity(0.3),
      ),
      ToolCallStatus.error => (
        isDark ? const Color(0xFF2A1A1A) : const Color(0xFFFEECEC),
        Colors.red.withOpacity(0.3),
      ),
    };

    return BoxDecoration(
      color: bgColor,
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: borderColor),
    );
  }
}
```

**验收**:
- [ ] 4 种状态装饰定义完成
- [ ] 明暗主题正确

---

## Phase 4: 配置管理

### 4.1 创建 MCP 服务器配置对话框

**文件**: `lib/widgets/mcp_server_config_dialog.dart`

功能：
- 添加新服务器
- 编辑现有服务器
- 选择传输类型（移动端隐藏 stdio）
- 测试连接

**验收**:
- [ ] 添加服务器功能
- [ ] 编辑服务器功能
- [ ] 传输类型选择（平台适配）
- [ ] 连接测试功能

---

### 4.2 创建 MCP 服务器列表页面

**文件**: `lib/pages/mcp_servers_page.dart`

功能：
- 列出所有配置的服务器
- 显示连接状态
- 启用/禁用服务器
- 删除服务器
- 显示每个服务器的工具数量

**验收**:
- [ ] 服务器列表展示
- [ ] 连接状态指示
- [ ] 启用/禁用切换
- [ ] 删除确认

---

### 4.3 集成到设置页面

**文件**: `lib/pages/settings_page.dart`

在设置页面添加 MCP 配置入口。

**验收**:
- [ ] MCP 设置入口添加
- [ ] 导航到 MCP 服务器页面

---

## Phase 5: 移动端优化

### 5.1 前台服务支持 (Android)

**文件**: `android/app/src/main/AndroidManifest.xml`

添加前台服务权限和声明。

**文件**: `lib/services/mcp_foreground_service.dart`

实现 Android 前台服务以保持 MCP 连接活跃。

**验收**:
- [ ] 前台服务权限配置
- [ ] 前台服务启动/停止
- [ ] 通知显示

---

### 5.2 后台任务支持 (iOS)

**文件**: `ios/Runner/Info.plist`

添加后台模式配置。

**验收**:
- [ ] Background modes 配置
- [ ] beginBackgroundTask 实现

---

### 5.3 连接重连机制

**文件**: `lib/services/mcp_client_service.dart`

添加自动重连逻辑：
- 连接失败时指数退避重试
- 网络恢复时自动重连
- 最大重试次数限制

**验收**:
- [ ] 指数退避重试
- [ ] 网络状态监听
- [ ] 重试次数限制

---

## 文件清单汇总

### 新增文件

| 文件路径 | 描述 |
|----------|------|
| `lib/models/mcp/mcp_server_config.dart` | 服务器配置模型 |
| `lib/models/mcp/mcp_tool_call.dart` | 工具调用数据模型 |
| `lib/services/mcp_client_service.dart` | MCP 客户端服务 |
| `lib/services/mcp_transport_factory.dart` | 传输层工厂 |
| `lib/adapters/mcp_tool_adapter.dart` | 工具适配器 |
| `lib/adapters/sse/tool_call_extractor.dart` | 工具调用提取器 |
| `lib/chat_ui/owui/tool_call_bubble.dart` | 工具调用气泡组件 |
| `lib/widgets/mcp_server_config_dialog.dart` | 服务器配置对话框 |
| `lib/pages/mcp_servers_page.dart` | 服务器管理页面 |
| `lib/services/mcp_foreground_service.dart` | Android 前台服务 |

### 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `pubspec.yaml` | 添加 mcp_dart 依赖 |
| `lib/adapters/hybrid_langchain_provider.dart` | 集成 MCP 工具 |
| `lib/widgets/stream_manager.dart` | 扩展工具调用状态 |
| `lib/chat_ui/owui/assistant_message.dart` | 添加 ToolCallBubble 渲染 |
| `lib/chat_ui/owui/owui_icons.dart` | 添加工具图标 |
| `lib/chat_ui/owui/chat_theme.dart` | 添加工具调用装饰 |
| `lib/pages/settings_page.dart` | 添加 MCP 设置入口 |
| `lib/main.dart` | 初始化 McpClientService |

---

## 验收标准汇总

### 功能验收

| 场景 | 预期结果 |
|------|----------|
| 连接 HTTP MCP 服务器 | 成功建立连接，获取工具列表 |
| 连接 Stdio MCP 服务器 (桌面) | 成功建立连接，获取工具列表 |
| 移动端尝试 Stdio | 抛出 UnsupportedError，UI 隐藏 stdio 选项 |
| LLM 返回 tool_call | ToolCallBubble 显示 pending → running |
| 工具执行成功 | ToolCallBubble 显示 success，结果可展开 |
| 工具执行失败 | ToolCallBubble 显示 error，错误信息可展开 |
| 多工具并行 | 多个 ToolCallBubble 正确渲染 |
| 服务器断开 | 自动重连，UI 显示连接状态 |

### 非功能验收

| 指标 | 要求 |
|------|------|
| 工具调用额外延迟 | < 100ms |
| 内存占用增加 | < 10MB |
| 动画帧率 | 60fps |
| 连接稳定性 | 自动重连成功率 > 95% |

---

## 执行顺序

```
Phase 1 (基础) ─────────────────────────────────────────────┐
  1.1 添加依赖                                               │
  1.2 数据模型                                               │
  1.3 工具调用模型                                           │
  1.4 MCP 客户端服务                                         │
  1.5 Transport 工厂                                         │
                                                             │
Phase 2 (集成) ◄─────────────────────────────────────────────┘
  2.1 Tool Adapter
  2.2 Tool Call Extractor
  2.3 扩展 HybridLangChainProvider
  2.4 扩展 StreamManager
                │
Phase 3 (UI) ◄──┘
  3.1 ToolCallBubble
  3.2 扩展 AssistantMessage
  3.3 添加图标
  3.4 扩展主题
                │
Phase 4 (配置) ◄┘
  4.1 配置对话框
  4.2 服务器列表页
  4.3 设置集成
                │
Phase 5 (移动) ◄┘
  5.1 Android 前台服务
  5.2 iOS 后台任务
  5.3 重连机制
```

---

## 风险缓解

| 风险 | 缓解措施 |
|------|----------|
| mcp_dart 版本兼容 | 锁定 1.2.2 版本，每月评估更新 |
| 移动端后台限制 | 前台服务 + 用户提示 + 重连机制 |
| 工具执行安全 | 高危工具强制确认，白名单机制 |
| UI 动画性能 | 动画控制器正确 dispose，减少重建 |
| SSE 解析边界 | 复用现有 SseParser，单元测试覆盖 |

---

*计划生成完成，等待用户确认后开始执行*
