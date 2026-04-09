/// MCP 客户端服务
/// 管理多个 MCP 服务器连接、工具发现和执行
import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:mcp_dart/mcp_dart.dart';

import '../models/mcp/mcp_server_config.dart';
import 'mcp_config_service.dart';

/// MCP 工具信息（包含 server 信息）
class McpToolInfo {
  final String serverId;
  final String serverName;
  final String name;
  final String description;
  final Map<String, dynamic>? inputSchema;

  McpToolInfo({
    required this.serverId,
    required this.serverName,
    required this.name,
    required this.description,
    this.inputSchema,
  });

  /// 获取限定名称（多服务器时使用）
  String qualifiedName(bool useNamespace) {
    return useNamespace ? '${serverId}__$name' : name;
  }
}

/// MCP 异常
class McpException implements Exception {
  final String message;
  final String? code;

  McpException(this.message, {this.code});

  @override
  String toString() => 'McpException: $message';
}

/// MCP 客户端服务
class McpClientService extends ChangeNotifier {
  /// 客户端实例映射
  final Map<String, McpClient> _clients = {};

  /// 服务器配置映射
  final Map<String, McpServerConfig> _configs = {};

  /// 连接状态映射
  final Map<String, McpConnectionStatus> _statuses = {};

  /// 工具缓存映射
  final Map<String, List<Tool>> _toolsCache = {};

  /// 主服务器 ID
  String? _primaryServerId;

  /// 工具调用超时（毫秒）
  final int toolCallTimeoutMs;

  /// 是否自动重连
  final bool autoReconnect;

  /// 持久化服务
  final McpConfigService _configService = McpConfigService();

  /// 是否已初始化
  bool _initialized = false;

  McpClientService({
    this.toolCallTimeoutMs = 30000,
    this.autoReconnect = true,
  });

  /// 初始化：从持久化存储加载配置
  Future<void> initialize() async {
    if (_initialized) return;

    await _configService.initialize();
    final configs = _configService.getAllConfigs();
    for (final config in configs) {
      _configs[config.id] = config;
      _statuses[config.id] = McpConnectionStatus.disconnected;
      if (_primaryServerId == null) {
        _primaryServerId = config.id;
      }
    }
    _initialized = true;
    debugPrint('[MCP] Loaded ${configs.length} server configs from storage');
    notifyListeners();
  }

  // ===== 状态查询 =====

  /// 获取主服务器 ID
  String? get primaryServerId => _primaryServerId;

  /// 获取所有服务器 ID
  List<String> get serverIds => _configs.keys.toList();

  /// 获取服务器配置
  McpServerConfig? getConfig(String serverId) => _configs[serverId];

  /// 获取服务器连接状态
  McpConnectionStatus getStatus(String serverId) {
    return _statuses[serverId] ?? McpConnectionStatus.disconnected;
  }

  /// 检查是否有任何已连接的服务器
  bool get hasConnectedServer {
    return _statuses.values.any((s) => s == McpConnectionStatus.connected);
  }

  /// 获取服务器数量
  int get serverCount => _configs.length;

  // ===== 服务器管理 =====

  /// 添加服务器配置
  Future<void> addServer(McpServerConfig config) async {
    _configs[config.id] = config;

    // 如果是第一个服务器，设为主服务器
    if (_primaryServerId == null) {
      _primaryServerId = config.id;
    }

    _statuses[config.id] = McpConnectionStatus.disconnected;

    // 持久化
    await _configService.saveConfig(config);

    notifyListeners();
  }

  /// 移除服务器
  Future<void> removeServer(String serverId) async {
    await disconnect(serverId);
    _configs.remove(serverId);
    _statuses.remove(serverId);
    _toolsCache.remove(serverId);

    // 如果移除的是主服务器，选择另一个
    if (_primaryServerId == serverId) {
      _primaryServerId = _configs.keys.isNotEmpty ? _configs.keys.first : null;
    }

    // 持久化
    await _configService.deleteConfig(serverId);

    notifyListeners();
  }

  /// 设置主服务器
  void setPrimaryServer(String serverId) {
    if (_configs.containsKey(serverId)) {
      _primaryServerId = serverId;
      notifyListeners();
    }
  }

  /// 更新服务器配置
  Future<void> updateServer(McpServerConfig config) async {
    _configs[config.id] = config;

    // 持久化
    await _configService.updateConfig(config);

    notifyListeners();
  }

  // ===== 连接管理 =====

  /// 连接到服务器
  Future<void> connect(String serverId) async {
    final config = _configs[serverId];
    if (config == null) {
      throw McpException('Server not found: $serverId');
    }

    if (!config.enabled) {
      throw McpException('Server is disabled: $serverId');
    }

    _statuses[serverId] = McpConnectionStatus.connecting;
    notifyListeners();

    try {
      final client = McpClient(
        Implementation(name: 'ChatBoxApp', version: '1.0.0'),
      );

      final transport = _createTransport(config);
      await client.connect(transport);

      _clients[serverId] = client;
      _statuses[serverId] = McpConnectionStatus.connected;

      // 刷新工具列表
      await refreshTools(serverId);

      // 更新最后连接时间
      _configs[serverId] = config.copyWith(lastConnectedAt: DateTime.now());

      debugPrint('[MCP] Connected to server: $serverId');
      notifyListeners();
    } catch (e) {
      _statuses[serverId] = McpConnectionStatus.failed;
      notifyListeners();
      throw McpException('Failed to connect: $e');
    }
  }

  /// 断开服务器连接
  Future<void> disconnect(String serverId) async {
    final client = _clients[serverId];
    if (client != null) {
      try {
        await client.close();
      } catch (e) {
        debugPrint('[MCP] Error closing client: $e');
      }
      _clients.remove(serverId);
    }

    _statuses[serverId] = McpConnectionStatus.disconnected;
    _toolsCache.remove(serverId);
    notifyListeners();
  }

  /// 重新连接服务器
  Future<void> reconnect(String serverId) async {
    _statuses[serverId] = McpConnectionStatus.reconnecting;
    notifyListeners();

    await disconnect(serverId);
    await connect(serverId);
  }

  /// 创建传输层
  Transport _createTransport(McpServerConfig config) {
    // 移动端检查
    if ((Platform.isAndroid || Platform.isIOS) &&
        config.transport == McpTransportType.stdio) {
      throw McpException(
        'Stdio transport not supported on mobile',
        code: 'UNSUPPORTED_TRANSPORT',
      );
    }

    switch (config.transport) {
      case McpTransportType.http:
        if (config.url == null) {
          throw McpException('URL is required for HTTP transport');
        }
        return StreamableHttpClientTransport(
          Uri.parse(config.url!),
          opts: config.headers != null
              ? StreamableHttpClientTransportOptions(
                  requestInit: {'headers': config.headers!},
                )
              : null,
        );

      case McpTransportType.websocket:
        if (config.url == null) {
          throw McpException('URL is required for WebSocket transport');
        }
        return StreamableHttpClientTransport(
          Uri.parse(config.url!),
          opts: config.headers != null
              ? StreamableHttpClientTransportOptions(
                  requestInit: {'headers': config.headers!},
                )
              : null,
        );

      case McpTransportType.stdio:
        if (config.command == null) {
          throw McpException('Command is required for Stdio transport');
        }
        return StdioClientTransport(
          StdioServerParameters(
            command: config.command!,
            args: config.args ?? [],
            environment: config.env,
          ),
        );
    }
  }

  // ===== 工具发现 =====

  /// 刷新服务器工具列表
  Future<void> refreshTools(String serverId) async {
    final client = _clients[serverId];
    if (client == null) {
      throw McpException('Server not connected: $serverId');
    }

    try {
      final result = await client.listTools();
      _toolsCache[serverId] = result.tools;
      debugPrint('[MCP] Loaded ${result.tools.length} tools from $serverId');
      notifyListeners();
    } catch (e) {
      debugPrint('[MCP] Failed to list tools: $e');
      _toolsCache[serverId] = [];
    }
  }

  /// 获取指定服务器的工具
  List<McpToolInfo> getServerTools(String serverId) {
    final config = _configs[serverId];
    final tools = _toolsCache[serverId] ?? [];

    return tools.map((tool) {
      return McpToolInfo(
        serverId: serverId,
        serverName: config?.name ?? serverId,
        name: tool.name,
        description: tool.description ?? '',
        inputSchema: tool.inputSchema.toJson(),
      );
    }).toList();
  }

  /// 获取所有可用工具
  List<McpToolInfo> getAllTools() {
    final tools = <McpToolInfo>[];

    for (final serverId in _configs.keys) {
      if (_statuses[serverId] == McpConnectionStatus.connected) {
        tools.addAll(getServerTools(serverId));
      }
    }

    return tools;
  }

  /// 获取主服务器的工具
  List<McpToolInfo> getPrimaryTools() {
    if (_primaryServerId == null) return [];
    return getServerTools(_primaryServerId!);
  }

  // ===== 工具执行 =====

  /// 执行工具调用
  Future<ToolCallResult> callTool({
    required String serverId,
    required String toolName,
    required Map<String, dynamic> arguments,
  }) async {
    final client = _clients[serverId];
    if (client == null) {
      return ToolCallResult(
        isSuccess: false,
        content: 'Server not connected: $serverId',
        errorCode: 'NOT_CONNECTED',
      );
    }

    try {
      final result = await client
          .callTool(
            CallToolRequest(name: toolName, arguments: arguments),
          )
          .timeout(Duration(milliseconds: toolCallTimeoutMs));

      if (result.isError == true) {
        return ToolCallResult(
          isSuccess: false,
          content: _formatToolContent(result.content),
          errorCode: 'TOOL_ERROR',
        );
      }

      return ToolCallResult(
        isSuccess: true,
        content: _formatToolContent(result.content),
      );
    } on TimeoutException {
      return ToolCallResult(
        isSuccess: false,
        content: 'Tool execution timed out after ${toolCallTimeoutMs}ms',
        errorCode: 'TIMEOUT',
      );
    } catch (e) {
      return ToolCallResult(
        isSuccess: false,
        content: 'Tool execution failed: $e',
        errorCode: 'EXECUTION_ERROR',
      );
    }
  }

  /// 通过限定名称执行工具
  Future<ToolCallResult> callToolByQualifiedName({
    required String qualifiedName,
    required Map<String, dynamic> arguments,
  }) async {
    // 解析 serverId__toolName 格式
    final parts = qualifiedName.split('__');
    String serverId;
    String toolName;

    if (parts.length >= 2) {
      serverId = parts[0];
      toolName = parts.sublist(1).join('__');
    } else {
      // 单服务器模式，使用主服务器
      serverId = _primaryServerId ?? '';
      toolName = qualifiedName;
    }

    if (serverId.isEmpty) {
      return ToolCallResult(
        isSuccess: false,
        content: 'No server specified and no primary server set',
        errorCode: 'NO_SERVER',
      );
    }

    return callTool(
      serverId: serverId,
      toolName: toolName,
      arguments: arguments,
    );
  }

  /// 格式化工具内容
  String _formatToolContent(List<Content> contents) {
    final buffer = StringBuffer();

    for (final content in contents) {
      switch (content) {
        case TextContent():
          buffer.writeln(content.text);
        case ImageContent():
          buffer.writeln('[Image: ${content.mimeType}]');
        case EmbeddedResource():
          buffer.writeln('[Resource: ${content.resource}]');
        default:
          buffer.writeln('[Unknown content type]');
      }
    }

    return buffer.toString().trim();
  }

  // ===== 生命周期 =====

  /// 启动服务（连接所有已启用的服务器）
  Future<void> start() async {
    for (final config in _configs.values) {
      if (config.enabled) {
        try {
          await connect(config.id);
        } catch (e) {
          debugPrint('[MCP] Failed to connect to ${config.id}: $e');
        }
      }
    }
  }

  /// 停止服务（断开所有连接）
  Future<void> stop() async {
    for (final serverId in _clients.keys.toList()) {
      await disconnect(serverId);
    }
  }

  @override
  void dispose() {
    stop();
    super.dispose();
  }
}

/// 工具调用结果
class ToolCallResult {
  final bool isSuccess;
  final String content;
  final String? errorCode;

  ToolCallResult({
    required this.isSuccess,
    required this.content,
    this.errorCode,
  });
}
