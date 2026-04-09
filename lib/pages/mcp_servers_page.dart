/// INPUT: McpClientService
/// OUTPUT: McpServersPage - MCP 服务器管理页面
/// POS: UI 层 / Pages - MCP 服务器列表与管理

import 'package:flutter/material.dart';

import '../chat_ui/owui/components/owui_app_bar.dart';
import '../chat_ui/owui/components/owui_scaffold.dart';
import '../chat_ui/owui/components/owui_snack_bar.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../models/mcp/mcp_server_config.dart';
import '../services/mcp_client_service.dart';
import '../widgets/mcp_server_config_dialog.dart';

class McpServersPage extends StatefulWidget {
  final McpClientService mcpService;

  const McpServersPage({
    super.key,
    required this.mcpService,
  });

  @override
  State<McpServersPage> createState() => _McpServersPageState();
}

class _McpServersPageState extends State<McpServersPage> {
  @override
  void initState() {
    super.initState();
    widget.mcpService.addListener(_onServiceChanged);
  }

  @override
  void dispose() {
    widget.mcpService.removeListener(_onServiceChanged);
    super.dispose();
  }

  void _onServiceChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _addServer() async {
    final config = await showDialog<McpServerConfig>(
      context: context,
      builder: (context) => const McpServerConfigDialog(),
    );
    if (config == null || !mounted) return;

    await widget.mcpService.addServer(config);
    try {
      await widget.mcpService.connect(config.id);
      if (mounted) {
        OwuiSnackBars.success(context, message: '已连接 "${config.name}"');
      }
    } catch (e) {
      if (mounted) {
        OwuiSnackBars.error(context, message: '连接失败: $e');
      }
    }
  }

  Future<void> _editServer(McpServerConfig config) async {
    final updated = await showDialog<McpServerConfig>(
      context: context,
      builder: (context) => McpServerConfigDialog(config: config),
    );
    if (updated == null || !mounted) return;

    // 断开旧连接，更新配置，重新连接
    await widget.mcpService.disconnect(config.id);
    await widget.mcpService.updateServer(updated);

    if (updated.enabled) {
      try {
        await widget.mcpService.connect(updated.id);
        if (mounted) {
          OwuiSnackBars.success(context, message: '已更新 "${updated.name}"');
        }
      } catch (e) {
        if (mounted) {
          OwuiSnackBars.error(context, message: '重新连接失败: $e');
        }
      }
    }
  }

  Future<void> _deleteServer(McpServerConfig config) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('确认删除'),
        content: Text('确定要删除 "${config.name}" 吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('删除'),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    await widget.mcpService.removeServer(config.id);
    if (mounted) {
      OwuiSnackBars.success(context, message: '已删除 "${config.name}"');
    }
  }

  Future<void> _toggleServer(String serverId, bool enabled) async {
    final config = widget.mcpService.getConfig(serverId);
    if (config == null) return;

    await widget.mcpService.updateServer(config.copyWith(enabled: enabled));

    if (enabled) {
      try {
        await widget.mcpService.connect(serverId);
      } catch (e) {
        if (mounted) {
          OwuiSnackBars.error(context, message: '连接失败: $e');
        }
      }
    } else {
      await widget.mcpService.disconnect(serverId);
    }
  }

  Future<void> _reconnect(String serverId) async {
    try {
      await widget.mcpService.reconnect(serverId);
      if (mounted) {
        OwuiSnackBars.success(context, message: '重新连接成功');
      }
    } catch (e) {
      if (mounted) {
        OwuiSnackBars.error(context, message: '重新连接失败: $e');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final serverIds = widget.mcpService.serverIds;

    return OwuiScaffold(
      appBar: OwuiAppBar(
        title: const Text('MCP 服务器'),
        actions: [
          IconButton(
            icon: const Icon(OwuiIcons.add),
            onPressed: _addServer,
            tooltip: '添加服务器',
          ),
        ],
      ),
      body: serverIds.isEmpty
          ? _buildEmptyState(context)
          : ListView.separated(
              padding: EdgeInsets.all(context.owuiSpacing.lg),
              itemCount: serverIds.length,
              separatorBuilder: (_, __) =>
                  SizedBox(height: context.owuiSpacing.md),
              itemBuilder: (context, index) {
                final serverId = serverIds[index];
                final config = widget.mcpService.getConfig(serverId);
                if (config == null) return const SizedBox.shrink();

                final status = widget.mcpService.getStatus(serverId);
                final tools = widget.mcpService.getServerTools(serverId);

                return _ServerCard(
                  config: config,
                  status: status,
                  toolCount: tools.length,
                  onTap: () => _editServer(config),
                  onToggle: (v) => _toggleServer(serverId, v),
                  onDelete: () => _deleteServer(config),
                  onReconnect: () => _reconnect(serverId),
                );
              },
            ),
    );
  }

  Widget _buildEmptyState(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            OwuiIcons.tools,
            size: 64,
            color: context.owuiColors.textSecondary.withValues(alpha: 0.4),
          ),
          SizedBox(height: context.owuiSpacing.lg),
          Text(
            '暂无 MCP 服务器',
            style: TextStyle(
              fontSize: 16,
              color: context.owuiColors.textSecondary,
            ),
          ),
          SizedBox(height: context.owuiSpacing.sm),
          Text(
            '添加 MCP 服务器以启用工具调用功能',
            style: TextStyle(
              fontSize: 13,
              color: context.owuiColors.textSecondary.withValues(alpha: 0.7),
            ),
          ),
          SizedBox(height: context.owuiSpacing.xl),
          FilledButton.icon(
            onPressed: _addServer,
            icon: const Icon(OwuiIcons.add),
            label: const Text('添加服务器'),
          ),
        ],
      ),
    );
  }
}

class _ServerCard extends StatelessWidget {
  final McpServerConfig config;
  final McpConnectionStatus status;
  final int toolCount;
  final VoidCallback onTap;
  final ValueChanged<bool> onToggle;
  final VoidCallback onDelete;
  final VoidCallback onReconnect;

  const _ServerCard({
    required this.config,
    required this.status,
    required this.toolCount,
    required this.onTap,
    required this.onToggle,
    required this.onDelete,
    required this.onReconnect,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Card(
      margin: EdgeInsets.zero,
      color: isDark ? const Color(0xFF1E1E1E) : Colors.white,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(
          color: isDark
              ? Colors.white.withValues(alpha: 0.1)
              : Colors.black.withValues(alpha: 0.08),
        ),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          child: Row(
            children: [
              // 状态指示灯 + 传输类型图标
              _buildStatusIcon(context),
              const SizedBox(width: 12),

              // 服务器信息
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      config.name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 15,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      _buildSubtitle(),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 12,
                        color: context.owuiColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),

              const SizedBox(width: 8),

              // 重连按钮（连接失败时）
              if (status == McpConnectionStatus.failed && config.enabled)
                IconButton(
                  icon: const Icon(OwuiIcons.refresh, size: 18),
                  onPressed: onReconnect,
                  tooltip: '重新连接',
                  visualDensity: VisualDensity.compact,
                ),

              // 更多菜单
              PopupMenuButton<String>(
                icon: const Icon(OwuiIcons.moreVert, size: 20),
                onSelected: (value) {
                  if (value == 'delete') onDelete();
                },
                itemBuilder: (context) => [
                  const PopupMenuItem(
                    value: 'delete',
                    child: Row(
                      children: [
                        Icon(OwuiIcons.delete, size: 18, color: Colors.red),
                        SizedBox(width: 8),
                        Text('删除', style: TextStyle(color: Colors.red)),
                      ],
                    ),
                  ),
                ],
              ),

              // 启用/禁用开关
              Switch(
                value: config.enabled,
                onChanged: onToggle,
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildStatusIcon(BuildContext context) {
    final (icon, color) = switch (config.transport) {
      McpTransportType.stdio => (OwuiIcons.terminal, _getStatusColor()),
      McpTransportType.http => (OwuiIcons.globe, _getStatusColor()),
      McpTransportType.websocket => (OwuiIcons.link, _getStatusColor()),
    };

    return Stack(
      children: [
        Icon(icon, size: 28, color: color),
        // 状态圆点
        Positioned(
          right: -2,
          bottom: -2,
          child: Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(
              color: _getStatusDotColor(),
              shape: BoxShape.circle,
              border: Border.all(
                color: Theme.of(context).scaffoldBackgroundColor,
                width: 2,
              ),
            ),
          ),
        ),
      ],
    );
  }

  Color _getStatusColor() {
    if (!config.enabled) return Colors.grey;
    return switch (status) {
      McpConnectionStatus.connected => Colors.green[700]!,
      McpConnectionStatus.connecting ||
      McpConnectionStatus.reconnecting =>
        Colors.amber[700]!,
      McpConnectionStatus.failed => Colors.red[700]!,
      McpConnectionStatus.disconnected => Colors.grey,
    };
  }

  Color _getStatusDotColor() {
    if (!config.enabled) return Colors.grey;
    return switch (status) {
      McpConnectionStatus.connected => Colors.green,
      McpConnectionStatus.connecting ||
      McpConnectionStatus.reconnecting =>
        Colors.amber,
      McpConnectionStatus.failed => Colors.red,
      McpConnectionStatus.disconnected => Colors.grey,
    };
  }

  String _buildSubtitle() {
    if (!config.enabled) return '已禁用';

    final statusText = switch (status) {
      McpConnectionStatus.connected => '已连接',
      McpConnectionStatus.connecting => '连接中...',
      McpConnectionStatus.reconnecting => '重连中...',
      McpConnectionStatus.failed => '连接失败',
      McpConnectionStatus.disconnected => '未连接',
    };

    if (status == McpConnectionStatus.connected && toolCount > 0) {
      return '$statusText · $toolCount 个工具';
    }
    return statusText;
  }
}
