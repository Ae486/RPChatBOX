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


  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      elevation: 2,
      child: InkWell(
        onTap: widget.onEdit, // 点击卡片进入编辑页面
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              // Provider图标
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: widget.provider.isEnabled
                      ? Theme.of(context).colorScheme.primaryContainer
                      : Colors.grey.shade200,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  _getProviderIcon(widget.provider.type),
                  size: 24,
                  color: widget.provider.isEnabled
                      ? Theme.of(context).colorScheme.primary
                      : Colors.grey.shade600,
                ),
              ),
              const SizedBox(width: 16),

              // Provider名称和类型
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          widget.provider.name,
                          style: Theme.of(context).textTheme.titleMedium?.copyWith(
                                fontWeight: FontWeight.bold,
                              ),
                        ),
                        const SizedBox(width: 8),
                        // 模型数量徽章
                        if (widget.models.isNotEmpty)
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: Theme.of(context).colorScheme.primary,
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Text(
                              '${widget.models.length}',
                              style: const TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                              ),
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 4),
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

              const SizedBox(width: 8),

              // 箭头图标
              Icon(
                Icons.arrow_forward_ios,
                size: 16,
                color: Colors.grey.shade400,
              ),
            ],
          ),
        ),
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
