/// INPUT: McpServerConfig（可选，编辑模式）+ McpClientService
/// OUTPUT: McpServerConfigDialog - 添加/编辑 MCP 服务器配置
/// POS: UI 层 / Widgets - MCP 服务器配置对话框

import 'dart:io';

import 'package:flutter/material.dart';

import '../adapters/ai_provider.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../design_system/design_tokens.dart';
import '../models/mcp/mcp_server_config.dart';

/// MCP 服务器配置对话框
class McpServerConfigDialog extends StatefulWidget {
  /// 编辑模式时传入现有配置
  final McpServerConfig? config;

  const McpServerConfigDialog({
    super.key,
    this.config,
  });

  @override
  State<McpServerConfigDialog> createState() => _McpServerConfigDialogState();
}

class _McpServerConfigDialogState extends State<McpServerConfigDialog> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _urlController = TextEditingController();
  final _commandController = TextEditingController();

  McpTransportType _transportType = McpTransportType.http;
  final List<TextEditingController> _argsControllers = [];
  final List<MapEntry<TextEditingController, TextEditingController>>
      _envControllers = [];

  bool get _isEditMode => widget.config != null;
  bool get _isMobile => Platform.isAndroid || Platform.isIOS;
  bool get _backendOwned => ProviderFactory.pythonBackendEnabled;

  @override
  void initState() {
    super.initState();
    if (_isEditMode) {
      _loadConfig(widget.config!);
    }
  }

  void _loadConfig(McpServerConfig config) {
    _nameController.text = config.name;
    _transportType = config.transport;
    _urlController.text = config.url ?? '';
    _commandController.text = config.command ?? '';

    // 加载参数
    for (final arg in config.args ?? []) {
      _argsControllers.add(TextEditingController(text: arg));
    }

    // 加载环境变量
    if (config.env != null) {
      for (final entry in config.env!.entries) {
        _envControllers.add(MapEntry(
          TextEditingController(text: entry.key),
          TextEditingController(text: entry.value),
        ));
      }
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _urlController.dispose();
    _commandController.dispose();
    for (final c in _argsControllers) {
      c.dispose();
    }
    for (final e in _envControllers) {
      e.key.dispose();
      e.value.dispose();
    }
    super.dispose();
  }

  void _addArg() {
    setState(() {
      _argsControllers.add(TextEditingController());
    });
  }

  void _removeArg(int index) {
    setState(() {
      _argsControllers[index].dispose();
      _argsControllers.removeAt(index);
    });
  }

  void _addEnv() {
    setState(() {
      _envControllers.add(MapEntry(
        TextEditingController(),
        TextEditingController(),
      ));
    });
  }

  void _removeEnv(int index) {
    setState(() {
      _envControllers[index].key.dispose();
      _envControllers[index].value.dispose();
      _envControllers.removeAt(index);
    });
  }

  void _submit() {
    if (!_formKey.currentState!.validate()) return;

    // 构建参数列表
    final args = _argsControllers
        .map((c) => c.text.trim())
        .where((s) => s.isNotEmpty)
        .toList();

    // 构建环境变量
    final env = <String, String>{};
    for (final e in _envControllers) {
      final key = e.key.text.trim();
      final value = e.value.text.trim();
      if (key.isNotEmpty) {
        env[key] = value;
      }
    }

    final config = McpServerConfig(
      id: widget.config?.id ?? DateTime.now().millisecondsSinceEpoch.toString(),
      name: _nameController.text.trim(),
      transportType: _transportType.name,
      url: _transportType != McpTransportType.stdio
          ? _urlController.text.trim()
          : null,
      command: _transportType == McpTransportType.stdio
          ? _commandController.text.trim()
          : null,
      args: _transportType == McpTransportType.stdio && args.isNotEmpty
          ? args
          : null,
      env: _transportType == McpTransportType.stdio && env.isNotEmpty
          ? env
          : null,
      enabled: widget.config?.enabled ?? true,
      createdAt: widget.config?.createdAt ?? DateTime.now(),
    );

    Navigator.pop(context, config);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(_isEditMode ? '编辑 MCP 服务器' : '添加 MCP 服务器'),
      content: SizedBox(
        width: 500,
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.7,
          ),
          child: Form(
            key: _formKey,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // 服务器名称
                  TextFormField(
                    controller: _nameController,
                    decoration: const InputDecoration(
                      labelText: '服务器名称',
                      hintText: '例如: Filesystem、GitHub',
                      border: OutlineInputBorder(),
                    ),
                    autofocus: true,
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return '请输入服务器名称';
                      }
                      return null;
                    },
                  ),

                  SizedBox(height: ChatBoxTokens.spacing.lg),

                  // 传输类型选择
                  DropdownButtonFormField<McpTransportType>(
                    initialValue: _transportType,
                    decoration: const InputDecoration(
                      labelText: '传输类型',
                      border: OutlineInputBorder(),
                    ),
                    items: [
                      const DropdownMenuItem(
                        value: McpTransportType.http,
                        child: Text('HTTP (SSE)'),
                      ),
                      if (!_backendOwned)
                        const DropdownMenuItem(
                          value: McpTransportType.websocket,
                          child: Text('WebSocket'),
                        ),
                      // 移动端不支持 stdio
                      if (!_isMobile)
                        const DropdownMenuItem(
                          value: McpTransportType.stdio,
                          child: Text('Stdio (本地进程)'),
                        ),
                    ],
                    onChanged: (value) {
                      if (value != null) {
                        setState(() => _transportType = value);
                      }
                    },
                  ),

                  SizedBox(height: ChatBoxTokens.spacing.lg),

                  // 根据传输类型显示不同配置
                  if (_transportType != McpTransportType.stdio) ...[
                    // HTTP/WebSocket URL
                    TextFormField(
                      controller: _urlController,
                      decoration: InputDecoration(
                        labelText: 'URL',
                        hintText: _transportType == McpTransportType.http
                            ? 'http://localhost:8000/sse'
                            : 'ws://localhost:8000/ws',
                        border: const OutlineInputBorder(),
                      ),
                      validator: (value) {
                        if (value == null || value.trim().isEmpty) {
                          return '请输入服务器 URL';
                        }
                        final uri = Uri.tryParse(value.trim());
                        if (uri == null || !uri.hasScheme) {
                          return '请输入有效的 URL';
                        }
                        return null;
                      },
                    ),
                  ] else ...[
                    // Stdio 命令
                    TextFormField(
                      controller: _commandController,
                      decoration: const InputDecoration(
                        labelText: '命令',
                        hintText: '例如: npx、python、node',
                        border: OutlineInputBorder(),
                      ),
                      validator: (value) {
                        if (value == null || value.trim().isEmpty) {
                          return '请输入启动命令';
                        }
                        return null;
                      },
                    ),

                    SizedBox(height: ChatBoxTokens.spacing.lg),

                    // 参数列表
                    _buildSection(
                      title: '参数',
                      onAdd: _addArg,
                      addLabel: '添加参数',
                      children: _argsControllers.asMap().entries.map((entry) {
                        return Padding(
                          padding: EdgeInsets.only(
                            bottom: ChatBoxTokens.spacing.sm,
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                child: TextFormField(
                                  controller: entry.value,
                                  decoration: InputDecoration(
                                    hintText: '参数 ${entry.key + 1}',
                                    border: const OutlineInputBorder(),
                                    isDense: true,
                                  ),
                                ),
                              ),
                              IconButton(
                                icon: const Icon(OwuiIcons.remove, size: 20),
                                onPressed: () => _removeArg(entry.key),
                                tooltip: '移除',
                              ),
                            ],
                          ),
                        );
                      }).toList(),
                    ),

                    SizedBox(height: ChatBoxTokens.spacing.lg),

                    // 环境变量
                    _buildSection(
                      title: '环境变量',
                      onAdd: _addEnv,
                      addLabel: '添加变量',
                      children: _envControllers.asMap().entries.map((entry) {
                        return Padding(
                          padding: EdgeInsets.only(
                            bottom: ChatBoxTokens.spacing.sm,
                          ),
                          child: Row(
                            children: [
                              Expanded(
                                flex: 2,
                                child: TextFormField(
                                  controller: entry.value.key,
                                  decoration: const InputDecoration(
                                    hintText: 'KEY',
                                    border: OutlineInputBorder(),
                                    isDense: true,
                                  ),
                                ),
                              ),
                              SizedBox(width: ChatBoxTokens.spacing.sm),
                              Expanded(
                                flex: 3,
                                child: TextFormField(
                                  controller: entry.value.value,
                                  decoration: const InputDecoration(
                                    hintText: 'VALUE',
                                    border: OutlineInputBorder(),
                                    isDense: true,
                                  ),
                                ),
                              ),
                              IconButton(
                                icon: const Icon(OwuiIcons.remove, size: 20),
                                onPressed: () => _removeEnv(entry.key),
                                tooltip: '移除',
                              ),
                            ],
                          ),
                        );
                      }).toList(),
                    ),
                  ],

                  SizedBox(height: ChatBoxTokens.spacing.lg),

                  // 提示信息
                  Container(
                    padding: EdgeInsets.all(ChatBoxTokens.spacing.md),
                    decoration: BoxDecoration(
                      color: Theme.of(context)
                          .colorScheme
                          .surfaceContainerHighest
                          .withValues(alpha: 0.5),
                      borderRadius:
                          BorderRadius.circular(ChatBoxTokens.radius.small),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          OwuiIcons.info,
                          size: 18,
                          color: Theme.of(context).colorScheme.primary,
                        ),
                        SizedBox(width: ChatBoxTokens.spacing.sm),
                        Expanded(
                          child: Text(
                            _transportType == McpTransportType.stdio
                                ? '💡 Stdio 模式通过本地进程通信，需要预先安装相关工具'
                                : '💡 HTTP/WebSocket 模式连接远程 MCP 服务器',
                            style: TextStyle(
                              fontSize: 12,
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurface
                                  .withValues(alpha: 0.7),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('取消'),
        ),
        ElevatedButton(
          onPressed: _submit,
          child: Text(_isEditMode ? '保存' : '添加'),
        ),
      ],
    );
  }

  Widget _buildSection({
    required String title,
    required VoidCallback onAdd,
    required String addLabel,
    required List<Widget> children,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              title,
              style: Theme.of(context).textTheme.titleSmall,
            ),
            TextButton.icon(
              onPressed: onAdd,
              icon: const Icon(OwuiIcons.add, size: 16),
              label: Text(addLabel),
              style: TextButton.styleFrom(
                visualDensity: VisualDensity.compact,
              ),
            ),
          ],
        ),
        SizedBox(height: ChatBoxTokens.spacing.sm),
        if (children.isEmpty)
          Text(
            '暂无$title',
            style: TextStyle(
              fontSize: 12,
              color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.5),
            ),
          )
        else
          ...children,
      ],
    );
  }
}
