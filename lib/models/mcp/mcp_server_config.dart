/// MCP 服务器配置模型
/// Hive TypeId: 60
import 'package:hive/hive.dart';

part 'mcp_server_config.g.dart';

/// MCP 传输类型
enum McpTransportType {
  /// HTTP (SSE) - 移动端和桌面端都支持
  http,

  /// WebSocket - 移动端和桌面端都支持
  websocket,

  /// Stdio (子进程) - 仅桌面端支持
  stdio,
}

/// MCP 连接状态
enum McpConnectionStatus {
  /// 未连接
  disconnected,

  /// 连接中
  connecting,

  /// 已连接
  connected,

  /// 连接失败
  failed,

  /// 重连中
  reconnecting,
}

/// MCP 服务器配置
@HiveType(typeId: 60)
class McpServerConfig {
  /// 服务器唯一标识
  @HiveField(0)
  final String id;

  /// 服务器显示名称
  @HiveField(1)
  final String name;

  /// 传输类型
  @HiveField(2)
  final String transportType;

  /// HTTP/WebSocket URL
  @HiveField(3)
  final String? url;

  /// Stdio 命令
  @HiveField(4)
  final String? command;

  /// Stdio 命令参数
  @HiveField(5)
  final List<String>? args;

  /// 环境变量
  @HiveField(6)
  final Map<String, String>? env;

  /// 是否启用
  @HiveField(7)
  final bool enabled;

  /// 创建时间
  @HiveField(8)
  final DateTime createdAt;

  /// 最后连接时间
  @HiveField(9)
  final DateTime? lastConnectedAt;

  /// HTTP 请求头（用于认证等）
  @HiveField(10)
  final Map<String, String>? headers;

  /// 描述
  @HiveField(11)
  final String? description;

  McpServerConfig({
    required this.id,
    required this.name,
    required this.transportType,
    this.url,
    this.command,
    this.args,
    this.env,
    this.enabled = true,
    required this.createdAt,
    this.lastConnectedAt,
    this.headers,
    this.description,
  });

  /// 获取传输类型枚举
  McpTransportType get transport {
    switch (transportType) {
      case 'http':
        return McpTransportType.http;
      case 'websocket':
        return McpTransportType.websocket;
      case 'stdio':
        return McpTransportType.stdio;
      default:
        return McpTransportType.http;
    }
  }

  /// 创建副本
  McpServerConfig copyWith({
    String? id,
    String? name,
    String? transportType,
    String? url,
    String? command,
    List<String>? args,
    Map<String, String>? env,
    bool? enabled,
    DateTime? createdAt,
    DateTime? lastConnectedAt,
    Map<String, String>? headers,
    String? description,
  }) {
    return McpServerConfig(
      id: id ?? this.id,
      name: name ?? this.name,
      transportType: transportType ?? this.transportType,
      url: url ?? this.url,
      command: command ?? this.command,
      args: args ?? this.args,
      env: env ?? this.env,
      enabled: enabled ?? this.enabled,
      createdAt: createdAt ?? this.createdAt,
      lastConnectedAt: lastConnectedAt ?? this.lastConnectedAt,
      headers: headers ?? this.headers,
      description: description ?? this.description,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'transportType': transportType,
      'url': url,
      'command': command,
      'args': args,
      'env': env,
      'enabled': enabled,
      'createdAt': createdAt.toIso8601String(),
      'lastConnectedAt': lastConnectedAt?.toIso8601String(),
      'headers': headers,
      'description': description,
    };
  }

  factory McpServerConfig.fromJson(Map<String, dynamic> json) {
    return McpServerConfig(
      id: json['id'] as String,
      name: json['name'] as String,
      transportType: json['transportType'] as String,
      url: json['url'] as String?,
      command: json['command'] as String?,
      args: (json['args'] as List?)?.cast<String>(),
      env: (json['env'] as Map?)?.cast<String, String>(),
      enabled: json['enabled'] as bool? ?? true,
      createdAt: DateTime.parse(json['createdAt'] as String),
      lastConnectedAt: json['lastConnectedAt'] != null
          ? DateTime.parse(json['lastConnectedAt'] as String)
          : null,
      headers: (json['headers'] as Map?)?.cast<String, String>(),
      description: json['description'] as String?,
    );
  }
}
