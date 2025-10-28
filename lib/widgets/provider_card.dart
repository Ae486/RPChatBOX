import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../services/model_service_manager.dart';

/// Provider卡片组件
/// 展示Provider信息、API配置、模型列表
class ProviderCard extends StatefulWidget {
  final ProviderConfig provider;
  final List<ModelConfig> models;
  final VoidCallback onToggle;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  final Function(ModelConfig) onToggleModel;
  final ModelServiceManager serviceManager;

  const ProviderCard({
    super.key,
    required this.provider,
    required this.models,
    required this.onToggle,
    required this.onEdit,
    required this.onDelete,
    required this.onToggleModel,
    required this.serviceManager,
  });

  @override
  State<ProviderCard> createState() => _ProviderCardState();
}

class _ProviderCardState extends State<ProviderCard> {
  bool _isExpanded = false;
  bool _isTesting = false;
  String? _testResult;

  Future<void> _testConnection() async {
    setState(() {
      _isTesting = true;
      _testResult = null;
    });

    try {
      final result = await widget.serviceManager.testProvider(widget.provider);

      setState(() {
        _isTesting = false;
        if (result.success) {
          _testResult = '连接成功 (${result.responseTimeMs}ms)';
        } else {
          _testResult = '连接失败: ${result.errorMessage}';
        }
      });

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(_testResult!),
            backgroundColor: result.success ? Colors.green : Colors.red,
          ),
        );
      }
    } catch (e) {
      setState(() {
        _isTesting = false;
        _testResult = '测试失败: ${e.toString()}';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      elevation: 2,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header: Provider名称和开关
          Container(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                // Provider图标
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: widget.provider.isEnabled
                        ? Theme.of(context).colorScheme.primaryContainer
                        : Colors.grey.shade200,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(
                    _getProviderIcon(widget.provider.type),
                    color: widget.provider.isEnabled
                        ? Theme.of(context).colorScheme.primary
                        : Colors.grey.shade600,
                  ),
                ),
                const SizedBox(width: 12),

                // Provider名称和类型
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        widget.provider.name,
                        style: Theme.of(context).textTheme.titleMedium?.copyWith(
                              fontWeight: FontWeight.bold,
                            ),
                      ),
                      const SizedBox(height: 2),
                      Text(
                        widget.provider.type.displayName,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: Colors.grey.shade600,
                            ),
                      ),
                    ],
                  ),
                ),

                // 开关
                Switch(
                  value: widget.provider.isEnabled,
                  onChanged: (_) => widget.onToggle(),
                ),

                // 更多菜单
                PopupMenuButton(
                  icon: const Icon(Icons.more_vert),
                  itemBuilder: (context) => [
                    const PopupMenuItem(
                      value: 'edit',
                      child: Row(
                        children: [
                          Icon(Icons.edit, size: 20),
                          SizedBox(width: 12),
                          Text('编辑'),
                        ],
                      ),
                    ),
                    const PopupMenuItem(
                      value: 'delete',
                      child: Row(
                        children: [
                          Icon(Icons.delete, size: 20, color: Colors.red),
                          SizedBox(width: 12),
                          Text('删除', style: TextStyle(color: Colors.red)),
                        ],
                      ),
                    ),
                  ],
                  onSelected: (value) {
                    if (value == 'edit') {
                      widget.onEdit();
                    } else if (value == 'delete') {
                      widget.onDelete();
                    }
                  },
                ),
              ],
            ),
          ),

          const Divider(height: 1),

          // API密钥
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text(
                      'API 密钥',
                      style: Theme.of(context).textTheme.labelMedium?.copyWith(
                            color: Colors.grey.shade700,
                          ),
                    ),
                    const Spacer(),
                    if (_isTesting)
                      const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    else
                      TextButton.icon(
                        onPressed: _testConnection,
                        icon: const Icon(Icons.wifi_tethering, size: 16),
                        label: const Text('检测'),
                        style: TextButton.styleFrom(
                          visualDensity: VisualDensity.compact,
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: isDark ? Colors.grey.shade900 : Colors.grey.shade100,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          widget.provider.maskedApiKey,
                          style: const TextStyle(
                            fontFamily: 'monospace',
                            fontSize: 13,
                          ),
                        ),
                      ),
                      IconButton(
                        icon: const Icon(Icons.visibility, size: 18),
                        onPressed: () {
                          // TODO: 显示完整API密钥
                        },
                        visualDensity: VisualDensity.compact,
                        tooltip: '查看',
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // API地址
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'API 地址',
                  style: Theme.of(context).textTheme.labelMedium?.copyWith(
                        color: Colors.grey.shade700,
                      ),
                ),
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  decoration: BoxDecoration(
                    color: isDark ? Colors.grey.shade900 : Colors.grey.shade100,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          widget.provider.apiUrl,
                          style: const TextStyle(
                            fontFamily: 'monospace',
                            fontSize: 13,
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(height: 16),

          // 模型列表
          if (widget.models.isNotEmpty) ...[
            InkWell(
              onTap: () => setState(() => _isExpanded = !_isExpanded),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                child: Row(
                  children: [
                    Text(
                      '模型 (${widget.models.length})',
                      style: Theme.of(context).textTheme.labelMedium?.copyWith(
                            color: Colors.grey.shade700,
                          ),
                    ),
                    const Spacer(),
                    Icon(
                      _isExpanded ? Icons.expand_less : Icons.expand_more,
                      size: 20,
                    ),
                  ],
                ),
              ),
            ),
            if (_isExpanded)
              ...widget.models.map((model) => _buildModelItem(model)),
          ],

          const SizedBox(height: 8),
        ],
      ),
    );
  }

  Widget _buildModelItem(ModelConfig model) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.grey.shade50,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: Colors.grey.shade200),
      ),
      child: Row(
        children: [
          // 模型名称
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  model.displayName,
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w500,
                      ),
                ),
                const SizedBox(height: 4),
                // 能力图标
                Wrap(
                  spacing: 6,
                  children: model.capabilities.map((cap) {
                    return Tooltip(
                      message: cap.displayName,
                      child: Container(
                        padding: const EdgeInsets.all(4),
                        decoration: BoxDecoration(
                          color: cap.color.withValues(alpha: 0.1),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Icon(
                          cap.icon,
                          size: 14,
                          color: cap.color,
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ],
            ),
          ),

          // 开关
          Switch(
            value: model.isEnabled,
            onChanged: (_) => widget.onToggleModel(model),
          ),
        ],
      ),
    );
  }

  IconData _getProviderIcon(ProviderType type) {
    switch (type) {
      case ProviderType.openai:
        return Icons.auto_awesome;
      case ProviderType.gemini:
        return Icons.stars;
      case ProviderType.deepseek:
        return Icons.psychology;
      case ProviderType.claude:
        return Icons.chat_bubble_outline;
      case ProviderType.custom:
        return Icons.code;
    }
  }
}
