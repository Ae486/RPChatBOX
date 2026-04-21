/// MCP 客户端服务
/// 管理多个 MCP 服务器连接、工具发现和执行
import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:mcp_dart/mcp_dart.dart';

import '../adapters/ai_provider.dart';
import '../models/mcp/mcp_server_config.dart';
import 'backend_mcp_service.dart';
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
  /// 仅 direct 模式使用的本地客户端实例映射
  final Map<String, McpClient> _clients = {};

  /// 服务器配置映射
  final Map<String, McpServerConfig> _configs = {};

  /// 连接状态映射
  final Map<String, McpConnectionStatus> _statuses = {};

  /// 工具缓存映射
  final Map<String, List<McpToolInfo>> _toolsCache = {};

  /// 主服务器 ID
  String? _primaryServerId;

  /// 工具调用超时（毫秒）
  final int toolCallTimeoutMs;

  /// 是否自动重连
  final bool autoReconnect;

  /// 本地持久化服务（仅 direct 模式使用；backend 模式只作为迁移来源）
  final McpConfigService _configService = McpConfigService();

  /// 后端 MCP 控制面服务
  final BackendMcpService _backendService = BackendMcpService();

  /// 是否已初始化
  bool _initialized = false;

  McpClientService({
    this.toolCallTimeoutMs = 30000,
    this.autoReconnect = true,
  });

  bool get _useBackend => ProviderFactory.pythonBackendEnabled;

  /// 初始化：加载当前模式的配置与状态
  Future<void> initialize() async {
    if (_initialized) return;

    await _configService.initialize();
    await _loadCurrentModeState();
    _initialized = true;
    notifyListeners();
  }

  Future<void> reload() async {
    if (!_initialized) {
      await initialize();
      return;
    }

    await _closeLocalClients();
    _resetState();
    await _loadCurrentModeState();
    notifyListeners();
  }

  Future<void> _loadCurrentModeState() async {
    if (_useBackend) {
      try {
        await _loadFromBackend();
      } catch (e) {
        debugPrint('[MCP] Backend bootstrap failed: $e');
      }
      return;
    }

    _loadFromLocal();
  }

  void _resetState() {
    _configs.clear();
    _statuses.clear();
    _toolsCache.clear();
    _primaryServerId = null;
  }

  void _loadFromLocal() {
    final configs = _configService.getAllConfigs();
    for (final config in configs) {
      _configs[config.id] = config;
      _statuses[config.id] = McpConnectionStatus.disconnected;
    }
    _ensurePrimaryServer();
    debugPrint('[MCP] Loaded ${configs.length} local server configs');
  }

  Future<void> _loadFromBackend() async {
    var servers = await _backendService.listServers();
    final imported = await _importMissingLocalConfigsToBackend(
      existingServerIds: servers.map((server) => server.id).toSet(),
    );
    if (imported) {
      servers = await _backendService.listServers();
    }

    final tools = await _backendService.listAllTools();
    final toolsByServer = <String, List<McpToolInfo>>{};
    for (final tool in tools) {
      toolsByServer.putIfAbsent(tool.serverId, () => <McpToolInfo>[]).add(
        McpToolInfo(
          serverId: tool.serverId,
          serverName: tool.serverName,
          name: tool.name,
          description: tool.description,
          inputSchema: tool.inputSchema,
        ),
      );
    }

    for (final server in servers) {
      _configs[server.id] = server.toFrontendConfig();
      _statuses[server.id] = server.toFrontendStatus();
      _toolsCache[server.id] = List<McpToolInfo>.unmodifiable(
        toolsByServer[server.id] ?? const <McpToolInfo>[],
      );
    }

    _ensurePrimaryServer();
    debugPrint('[MCP] Loaded ${servers.length} backend server configs');
  }

  Future<bool> _importMissingLocalConfigsToBackend({
    required Set<String> existingServerIds,
  }) async {
    final localConfigs = _configService.getAllConfigs();
    var imported = false;

    for (final config in localConfigs) {
      if (existingServerIds.contains(config.id)) {
        continue;
      }
      if (config.transport == McpTransportType.websocket) {
        debugPrint(
          '[MCP] Skip backend import for ${config.id}: WebSocket transport unsupported on backend',
        );
        continue;
      }
      try {
        await _backendService.upsertServer(config);
        imported = true;
      } catch (e) {
        debugPrint('[MCP] Failed to import local config ${config.id}: $e');
      }
    }

    return imported;
  }

  void _ensurePrimaryServer() {
    if (_primaryServerId != null && _configs.containsKey(_primaryServerId)) {
      return;
    }
    _primaryServerId = _configs.keys.isNotEmpty ? _configs.keys.first : null;
  }

  Future<void> _closeLocalClients() async {
    for (final entry in _clients.entries.toList()) {
      try {
        await entry.value.close();
      } catch (e) {
        debugPrint('[MCP] Error closing local client ${entry.key}: $e');
      }
    }
    _clients.clear();
  }

  McpToolInfo _mapLocalToolInfo(
    String serverId,
    McpServerConfig? config,
    Tool tool,
  ) {
    return McpToolInfo(
      serverId: serverId,
      serverName: config?.name ?? serverId,
      name: tool.name,
      description: tool.description ?? '',
      inputSchema: tool.inputSchema.toJson(),
    );
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
    if (_useBackend) {
      final stored = await _backendService.upsertServer(config);
      _configs[stored.id] = stored.toFrontendConfig();
      _statuses[stored.id] = stored.toFrontendStatus();
      _toolsCache[stored.id] = const <McpToolInfo>[];
      _ensurePrimaryServer();
      notifyListeners();
      return;
    }

    _configs[config.id] = config;
    if (_primaryServerId == null) {
      _primaryServerId = config.id;
    }
    _statuses[config.id] = McpConnectionStatus.disconnected;
    await _configService.saveConfig(config);
    notifyListeners();
  }

  /// 移除服务器
  Future<void> removeServer(String serverId) async {
    if (_useBackend) {
      await _backendService.deleteServer(serverId);
      _configs.remove(serverId);
      _statuses.remove(serverId);
      _toolsCache.remove(serverId);
      _ensurePrimaryServer();
      notifyListeners();
      return;
    }

    await disconnect(serverId);
    _configs.remove(serverId);
    _statuses.remove(serverId);
    _toolsCache.remove(serverId);
    _ensurePrimaryServer();
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
    if (_useBackend) {
      final stored = await _backendService.upsertServer(config);
      _configs[stored.id] = stored.toFrontendConfig();
      _statuses[stored.id] = stored.toFrontendStatus();
      if (!stored.connected) {
        _toolsCache[stored.id] = const <McpToolInfo>[];
      }
      _ensurePrimaryServer();
      notifyListeners();
      return;
    }

    _configs[config.id] = config;
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

    if (_useBackend) {
      try {
        await _backendService.connectServer(serverId);
        final server = await _backendService.getServer(serverId);
        _configs[serverId] = server.toFrontendConfig();
        _statuses[serverId] = server.toFrontendStatus();
        await refreshTools(serverId);
        debugPrint('[MCP] Connected to backend server: $serverId');
        notifyListeners();
      } catch (e) {
        _statuses[serverId] = McpConnectionStatus.failed;
        notifyListeners();
        throw McpException('Failed to connect: $e');
      }
      return;
    }

    try {
      final client = McpClient(
        Implementation(name: 'ChatBoxApp', version: '1.0.0'),
      );

      final transport = _createTransport(config);
      await client.connect(transport);

      _clients[serverId] = client;
      _statuses[serverId] = McpConnectionStatus.connected;

      await refreshTools(serverId);
      _configs[serverId] = config.copyWith(lastConnectedAt: DateTime.now());

      debugPrint('[MCP] Connected to local server: $serverId');
      notifyListeners();
    } catch (e) {
      _statuses[serverId] = McpConnectionStatus.failed;
      notifyListeners();
      throw McpException('Failed to connect: $e');
    }
  }

  /// 断开服务器连接
  Future<void> disconnect(String serverId) async {
    if (_useBackend) {
      await _backendService.disconnectServer(serverId);
      final server = await _backendService.getServer(serverId);
      _configs[serverId] = server.toFrontendConfig();
      _statuses[serverId] = server.toFrontendStatus();
      _toolsCache[serverId] = const <McpToolInfo>[];
      notifyListeners();
      return;
    }

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
    _toolsCache[serverId] = const <McpToolInfo>[];
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
    if (_useBackend) {
      if (_statuses[serverId] != McpConnectionStatus.connected) {
        _toolsCache[serverId] = const <McpToolInfo>[];
        notifyListeners();
        return;
      }

      final tools = await _backendService.listServerTools(serverId);
      _toolsCache[serverId] = List<McpToolInfo>.unmodifiable(
        tools
            .map(
              (tool) => McpToolInfo(
                serverId: tool.serverId,
                serverName: tool.serverName,
                name: tool.name,
                description: tool.description,
                inputSchema: tool.inputSchema,
              ),
            )
            .toList(),
      );
      notifyListeners();
      return;
    }

    final client = _clients[serverId];
    if (client == null) {
      throw McpException('Server not connected: $serverId');
    }

    try {
      final result = await client.listTools();
      final config = _configs[serverId];
      _toolsCache[serverId] = List<McpToolInfo>.unmodifiable(
        result.tools
            .map((tool) => _mapLocalToolInfo(serverId, config, tool))
            .toList(),
      );
      debugPrint('[MCP] Loaded ${result.tools.length} tools from $serverId');
      notifyListeners();
    } catch (e) {
      debugPrint('[MCP] Failed to list tools: $e');
      _toolsCache[serverId] = const <McpToolInfo>[];
    }
  }

  /// 获取指定服务器的工具
  List<McpToolInfo> getServerTools(String serverId) {
    return List<McpToolInfo>.unmodifiable(
      _toolsCache[serverId] ?? const <McpToolInfo>[],
    );
  }

  /// 获取所有可用工具
  List<McpToolInfo> getAllTools() {
    final tools = <McpToolInfo>[];

    for (final serverId in _configs.keys) {
      if (_statuses[serverId] == McpConnectionStatus.connected) {
        tools.addAll(_toolsCache[serverId] ?? const <McpToolInfo>[]);
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
    if (_useBackend) {
      return callToolByQualifiedName(
        qualifiedName: '${serverId}__$toolName',
        arguments: arguments,
      );
    }

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
    if (_useBackend) {
      try {
        final result = await _backendService.callToolByQualifiedName(
          qualifiedName: qualifiedName,
          arguments: arguments,
        );
        return ToolCallResult(
          isSuccess: result.success,
          content: result.content,
          errorCode: result.errorCode,
        );
      } catch (e) {
        return ToolCallResult(
          isSuccess: false,
          content: 'Tool execution failed: $e',
          errorCode: 'EXECUTION_ERROR',
        );
      }
    }

    final parts = qualifiedName.split('__');
    String serverId;
    String toolName;

    if (parts.length >= 2) {
      serverId = parts[0];
      toolName = parts.sublist(1).join('__');
    } else {
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

  /// 启动服务
  Future<void> start() async {
    if (!_initialized) {
      await initialize();
    }

    if (_useBackend) {
      try {
        _resetState();
        await _loadFromBackend();
        final enabledDisconnected = _configs.entries
            .where(
              (entry) =>
                  entry.value.enabled &&
                  _statuses[entry.key] != McpConnectionStatus.connected,
            )
            .map((entry) => entry.key)
            .toList();
        for (final serverId in enabledDisconnected) {
          try {
            await _backendService.connectServer(serverId);
          } catch (e) {
            debugPrint('[MCP] Failed to auto-connect backend server $serverId: $e');
          }
        }
        if (enabledDisconnected.isNotEmpty) {
          _resetState();
          await _loadFromBackend();
        }
        notifyListeners();
      } catch (e) {
        debugPrint('[MCP] Failed to refresh backend MCP state: $e');
      }
      return;
    }

    for (final config in _configs.values) {
      if (!config.enabled) {
        continue;
      }
      try {
        await connect(config.id);
      } catch (e) {
        debugPrint('[MCP] Failed to connect to ${config.id}: $e');
      }
    }
  }

  /// 停止服务（仅 direct 模式关闭本地连接）
  Future<void> stop() async {
    if (_useBackend) {
      return;
    }
    await _closeLocalClients();
    for (final serverId in _configs.keys) {
      _statuses[serverId] = McpConnectionStatus.disconnected;
      _toolsCache[serverId] = const <McpToolInfo>[];
    }
    notifyListeners();
  }

  @override
  void dispose() {
    unawaited(stop());
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
