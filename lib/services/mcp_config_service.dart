/// MCP 服务器配置持久化服务
/// 使用 Hive 存储 MCP 服务器配置
import 'package:hive_flutter/hive_flutter.dart';
import 'package:flutter/foundation.dart';

import '../models/mcp/mcp_server_config.dart';

class McpConfigService {
  static const String _boxName = 'mcp_servers';

  Box<McpServerConfig>? _box;

  /// 单例
  static final McpConfigService _instance = McpConfigService._internal();
  factory McpConfigService() => _instance;
  McpConfigService._internal();

  /// 初始化（在 Hive.initFlutter 之后调用）
  Future<void> initialize() async {
    // 注册 adapter（如果未注册）
    if (!Hive.isAdapterRegistered(60)) {
      Hive.registerAdapter(McpServerConfigAdapter());
    }

    _box = await Hive.openBox<McpServerConfig>(_boxName);
    debugPrint('[McpConfigService] Initialized with ${_box!.length} servers');
  }

  /// 获取所有服务器配置
  List<McpServerConfig> getAllConfigs() {
    return _box?.values.toList() ?? [];
  }

  /// 获取单个配置
  McpServerConfig? getConfig(String id) {
    return _box?.get(id);
  }

  /// 保存配置
  Future<void> saveConfig(McpServerConfig config) async {
    await _box?.put(config.id, config);
    debugPrint('[McpConfigService] Saved config: ${config.id}');
  }

  /// 删除配置
  Future<void> deleteConfig(String id) async {
    await _box?.delete(id);
    debugPrint('[McpConfigService] Deleted config: $id');
  }

  /// 更新配置
  Future<void> updateConfig(McpServerConfig config) async {
    await saveConfig(config);
  }

  /// 批量保存
  Future<void> saveAll(List<McpServerConfig> configs) async {
    final map = <String, McpServerConfig>{};
    for (final config in configs) {
      map[config.id] = config;
    }
    await _box?.putAll(map);
  }

  /// 清空所有配置
  Future<void> clear() async {
    await _box?.clear();
  }
}
