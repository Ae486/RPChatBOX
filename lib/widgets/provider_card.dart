/// INPUT: ProviderConfig + models +（管理模式）回调集合
/// OUTPUT: ProviderCard - Provider 展示卡片（启用/编辑/删除/模型开关）
/// POS: UI 层 / Widgets - ModelServicesPage 列表项

import 'package:flutter/material.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../services/model_service_manager.dart';
import '../design_system/design_tokens.dart';

/// Provider卡片组件
/// 展示Provider信息、API配置、模型列表
class ProviderCard extends StatefulWidget {
  final ProviderConfig provider;
  final List<ModelConfig> models;
  final bool isManagementMode; // 🆕 是否处于管理模式
  final VoidCallback onToggle;
  final VoidCallback onEdit;
  final VoidCallback onDelete;
  final VoidCallback onLongPress; // 🆕 长按回调
  final Function(ModelConfig) onToggleModel;
  final ModelServiceManager serviceManager;

  const ProviderCard({
    super.key,
    required this.provider,
    required this.models,
    this.isManagementMode = false,
    required this.onToggle,
    required this.onEdit,
    required this.onDelete,
    required this.onLongPress,
    required this.onToggleModel,
    required this.serviceManager,
  });

  @override
  State<ProviderCard> createState() => _ProviderCardState();
}

class _ProviderCardState extends State<ProviderCard> {
  @override
  Widget build(BuildContext context) {
    return Container(
      margin: EdgeInsets.only(bottom: ChatBoxTokens.spacing.md),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        borderRadius: BorderRadius.circular(ChatBoxTokens.radius.medium),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 4,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: widget.isManagementMode ? null : widget.onEdit,
          onLongPress: widget.onLongPress,
          borderRadius: BorderRadius.circular(ChatBoxTokens.radius.medium),
          child: Padding(
            padding: EdgeInsets.all(ChatBoxTokens.spacing.lg),
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
                  borderRadius: BorderRadius.circular(ChatBoxTokens.radius.medium),
                ),
                child: Icon(
                  _getProviderIcon(widget.provider.type),
                  size: 24,
                  color: widget.provider.isEnabled
                      ? Theme.of(context).colorScheme.primary
                      : Colors.grey.shade600,
                ),
              ),
              SizedBox(width: ChatBoxTokens.spacing.lg),

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
                        SizedBox(width: ChatBoxTokens.spacing.sm),
                        // 模型数量徽章
                        if (widget.models.isNotEmpty)
                          Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: ChatBoxTokens.spacing.sm,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: Theme.of(context).colorScheme.primary,
                              borderRadius: BorderRadius.circular(ChatBoxTokens.radius.medium),
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
                    SizedBox(height: ChatBoxTokens.spacing.xs),
                    Text(
                      widget.provider.type.displayName,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Colors.grey.shade600,
                          ),
                    ),
                  ],
                ),
              ),

              // 🆕 管理模式：删除按钮 / 普通模式：开关和箭头
              if (widget.isManagementMode) ...[
                // 删除按钮（阻止拖动手势）
                GestureDetector(
                  onTapDown: (_) {}, // 🔧 阻止拖动手势传播
                  child: IconButton(
                    icon: const Icon(
                      OwuiIcons.removeCircle,
                      color: Colors.red,
                      size: 28,
                    ),
                    onPressed: widget.onDelete,
                    tooltip: '删除',
                  ),
                ),
              ] else ...[
                // 开关
                Switch(
                  value: widget.provider.isEnabled,
                  onChanged: (_) => widget.onToggle(),
                ),
                SizedBox(width: ChatBoxTokens.spacing.sm),
                // 箭头图标
                Icon(
                  OwuiIcons.chevronRight,
                  size: 16,
                  color: Colors.grey.shade400,
                ),
              ],
            ],
          ),
        ),
        ),
      ),
    );
  }

  IconData _getProviderIcon(ProviderType type) {
    switch (type) {
      case ProviderType.openai:
        return OwuiIcons.auto;
      case ProviderType.gemini:
        return OwuiIcons.star;
      case ProviderType.deepseek:
        return OwuiIcons.psychology;
      case ProviderType.claude:
        return OwuiIcons.chatBubble;
      // 🔧 修复：已移除 custom 选项
    }
  }
}
