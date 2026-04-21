import 'package:dio/dio.dart';

import '../models/mcp/mcp_server_config.dart';
import 'dio_service.dart';

class BackendMcpServerState {
  final String id;
  final String name;
  final String transport;
  final bool enabled;
  final String? command;
  final List<String> args;
  final Map<String, String>? env;
  final String? url;
  final Map<String, String>? headers;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final bool connected;
  final int toolCount;
  final String? error;

  const BackendMcpServerState({
    required this.id,
    required this.name,
    required this.transport,
    required this.enabled,
    required this.command,
    required this.args,
    required this.env,
    required this.url,
    required this.headers,
    required this.createdAt,
    required this.updatedAt,
    required this.connected,
    required this.toolCount,
    required this.error,
  });

  factory BackendMcpServerState.fromJson(Map<String, dynamic> json) {
    return BackendMcpServerState(
      id: json['id'] as String,
      name: json['name'] as String,
      transport: json['transport'] as String,
      enabled: json['enabled'] as bool? ?? true,
      command: json['command'] as String?,
      args: (json['args'] as List? ?? const []).cast<String>(),
      env: (json['env'] as Map?)?.cast<String, String>(),
      url: json['url'] as String?,
      headers: (json['headers'] as Map?)?.cast<String, String>(),
      createdAt: json['created_at'] != null
          ? DateTime.tryParse(json['created_at'] as String)
          : null,
      updatedAt: json['updated_at'] != null
          ? DateTime.tryParse(json['updated_at'] as String)
          : null,
      connected: json['connected'] as bool? ?? false,
      toolCount: json['tool_count'] as int? ?? 0,
      error: json['error'] as String?,
    );
  }

  McpServerConfig toFrontendConfig() {
    return McpServerConfig(
      id: id,
      name: name,
      transportType: switch (transport) {
        'stdio' => 'stdio',
        _ => 'http',
      },
      url: url,
      command: command,
      args: args.isEmpty ? null : args,
      env: env,
      enabled: enabled,
      createdAt: createdAt?.toLocal() ?? DateTime.now(),
      lastConnectedAt: connected ? updatedAt?.toLocal() : null,
      headers: headers,
    );
  }

  McpConnectionStatus toFrontendStatus() {
    if (connected) {
      return McpConnectionStatus.connected;
    }
    if (error != null && error!.trim().isNotEmpty) {
      return McpConnectionStatus.failed;
    }
    return McpConnectionStatus.disconnected;
  }
}

class BackendMcpToolState {
  final String serverId;
  final String serverName;
  final String name;
  final String description;
  final Map<String, dynamic>? inputSchema;

  const BackendMcpToolState({
    required this.serverId,
    required this.serverName,
    required this.name,
    required this.description,
    required this.inputSchema,
  });

  factory BackendMcpToolState.fromJson(Map<String, dynamic> json) {
    return BackendMcpToolState(
      serverId: json['server_id'] as String,
      serverName: json['server_name'] as String,
      name: json['name'] as String,
      description: json['description'] as String? ?? '',
      inputSchema: (json['input_schema'] as Map?)?.cast<String, dynamic>(),
    );
  }
}

class BackendMcpToolCallState {
  final bool success;
  final String content;
  final String? errorCode;

  const BackendMcpToolCallState({
    required this.success,
    required this.content,
    required this.errorCode,
  });

  factory BackendMcpToolCallState.fromJson(Map<String, dynamic> json) {
    return BackendMcpToolCallState(
      success: json['success'] as bool? ?? false,
      content: json['content'] as String? ?? '',
      errorCode: json['error_code'] as String?,
    );
  }
}

class BackendMcpService {
  static const String defaultBaseUrl = 'http://localhost:8765';

  final Dio _dio;

  BackendMcpService({Dio? dio}) : _dio = dio ?? DioService().controlPlaneDio;

  Options _buildOptions({
    Duration? receiveTimeout,
    Duration? sendTimeout,
  }) {
    return Options(
      headers: const <String, dynamic>{'Content-Type': 'application/json'},
      sendTimeout: sendTimeout,
      receiveTimeout: receiveTimeout,
    );
  }

  String? _extractErrorDetail(Object? data) {
    if (data is Map) {
      final detail = data['detail'];
      if (detail is String && detail.trim().isNotEmpty) {
        return detail;
      }
    }
    return null;
  }

  String _toBackendTransport(McpServerConfig config) {
    switch (config.transport) {
      case McpTransportType.http:
        return 'streamable_http';
      case McpTransportType.stdio:
        return 'stdio';
      case McpTransportType.websocket:
        throw Exception('Backend MCP 暂不支持 WebSocket 传输');
    }
  }

  Map<String, dynamic> _buildPayload(McpServerConfig config) {
    return {
      'id': config.id,
      'name': config.name,
      'transport': _toBackendTransport(config),
      'enabled': config.enabled,
      'command': config.command,
      'args': config.args ?? const <String>[],
      'env': config.env,
      'url': config.url,
      'headers': config.headers,
      'created_at': config.createdAt.toUtc().toIso8601String(),
      'updated_at': DateTime.now().toUtc().toIso8601String(),
    };
  }

  Future<List<BackendMcpServerState>> listServers() async {
    final response = await _dio.get(
      '$defaultBaseUrl/api/mcp/servers',
      options: _buildOptions(),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend MCP server list failed: $statusCode');
    }

    final data = response.data as Map<String, dynamic>;
    final items = data['data'] as List? ?? const [];
    return items
        .whereType<Map>()
        .map(
          (item) => BackendMcpServerState.fromJson(
            Map<String, dynamic>.from(item),
          ),
        )
        .toList();
  }

  Future<BackendMcpServerState> getServer(String serverId) async {
    final response = await _dio.get(
      '$defaultBaseUrl/api/mcp/servers/$serverId',
      options: _buildOptions(),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend MCP server get failed: $statusCode');
    }
    return BackendMcpServerState.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<BackendMcpServerState> upsertServer(McpServerConfig config) async {
    final response = await _dio.put(
      '$defaultBaseUrl/api/mcp/servers/${config.id}',
      data: _buildPayload(config),
      options: _buildOptions(),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend MCP server upsert failed: $statusCode');
    }
    return BackendMcpServerState.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }

  Future<void> deleteServer(String serverId) async {
    final response = await _dio.delete(
      '$defaultBaseUrl/api/mcp/servers/$serverId',
      options: _buildOptions(),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode == 404) {
      return;
    }
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend MCP server delete failed: $statusCode');
    }
  }

  Future<void> connectServer(String serverId) async {
    final response = await _dio.post(
      '$defaultBaseUrl/api/mcp/servers/$serverId/connect',
      options: _buildOptions(
        receiveTimeout: const Duration(minutes: 2),
        sendTimeout: const Duration(seconds: 30),
      ),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      final detail = _extractErrorDetail(response.data);
      throw Exception(
        detail == null
            ? 'Backend MCP server connect failed: $statusCode'
            : 'Backend MCP server connect failed: $statusCode ($detail)',
      );
    }
  }

  Future<void> disconnectServer(String serverId) async {
    final response = await _dio.post(
      '$defaultBaseUrl/api/mcp/servers/$serverId/disconnect',
      options: _buildOptions(),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend MCP server disconnect failed: $statusCode');
    }
  }

  Future<List<BackendMcpToolState>> listServerTools(String serverId) async {
    final response = await _dio.get(
      '$defaultBaseUrl/api/mcp/servers/$serverId/tools',
      options: _buildOptions(),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend MCP server tools failed: $statusCode');
    }
    final data = response.data as Map<String, dynamic>;
    final items = data['data'] as List? ?? const [];
    return items
        .whereType<Map>()
        .map(
          (item) => BackendMcpToolState.fromJson(
            Map<String, dynamic>.from(item),
          ),
        )
        .toList();
  }

  Future<List<BackendMcpToolState>> listAllTools() async {
    final response = await _dio.get(
      '$defaultBaseUrl/api/mcp/tools',
      options: _buildOptions(),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend MCP tools list failed: $statusCode');
    }
    final data = response.data as Map<String, dynamic>;
    final items = data['data'] as List? ?? const [];
    return items
        .whereType<Map>()
        .map(
          (item) => BackendMcpToolState.fromJson(
            Map<String, dynamic>.from(item),
          ),
        )
        .toList();
  }

  Future<BackendMcpToolCallState> callToolByQualifiedName({
    required String qualifiedName,
    required Map<String, dynamic> arguments,
  }) async {
    final response = await _dio.post(
      '$defaultBaseUrl/api/mcp/tools/call',
      data: {
        'qualified_name': qualifiedName,
        'arguments': arguments,
      },
      options: _buildOptions(),
    );
    final statusCode = response.statusCode ?? 500;
    if (statusCode < 200 || statusCode >= 300) {
      throw Exception('Backend MCP tool call failed: $statusCode');
    }
    return BackendMcpToolCallState.fromJson(
      Map<String, dynamic>.from(response.data as Map),
    );
  }
}
