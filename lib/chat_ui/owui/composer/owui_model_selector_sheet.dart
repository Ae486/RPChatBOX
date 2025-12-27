/// INPUT: ModelServiceManager providers/models
/// OUTPUT: OwuiModelSelectorSheet - 模型选择 bottom sheet
/// POS: UI 层 / Chat / Owui - 输入区配套组件
import 'package:flutter/material.dart';

import '../../../design_system/design_tokens.dart';
import '../../../models/model_config.dart';
import '../../../services/model_service_manager.dart';
import '../owui_icons.dart';
import '../palette.dart';

class OwuiModelSelectorSheet extends StatelessWidget {
  final ModelServiceManager serviceManager;
  final String? currentModelId;
  final void Function(String providerId, String modelId) onModelSelected;

  const OwuiModelSelectorSheet({
    super.key,
    required this.serviceManager,
    required this.currentModelId,
    required this.onModelSelected,
  });

  @override
  Widget build(BuildContext context) {
    final providers = serviceManager.getEnabledProviders();

    return SafeArea(
      top: false,
      child: Container(
        decoration: BoxDecoration(
          color: OwuiPalette.pageBackground(context),
          borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
          border: Border.all(color: OwuiPalette.borderSubtle(context)),
        ),
        padding: EdgeInsets.all(ChatBoxTokens.spacing.lg + 4),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text('閫夋嫨妯″瀷', style: Theme.of(context).textTheme.titleLarge),
                const Spacer(),
                IconButton(
                  icon: const Icon(OwuiIcons.close),
                  onPressed: () => Navigator.pop(context),
                  tooltip: '鍏抽棴',
                ),
              ],
            ),
            SizedBox(height: ChatBoxTokens.spacing.lg),
            if (providers.isEmpty)
              Center(
                child: Padding(
                  padding: EdgeInsets.all(ChatBoxTokens.spacing.xxl),
                  child: const Text('鏆傛棤鍙敤妯″瀷鏈嶅姟\n璇峰厛鍦ㄨ缃腑娣诲姞'),
                ),
              )
            else
              Expanded(
                child: ListView.builder(
                  itemCount: providers.length,
                  itemBuilder: (context, index) {
                    final provider = providers[index];
                    final models = serviceManager
                        .getModelsByProvider(provider.id)
                        .where((m) => m.isEnabled)
                        .toList();

                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Padding(
                          padding:
                              EdgeInsets.symmetric(vertical: ChatBoxTokens.spacing.sm),
                          child: Text(
                            provider.name,
                            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                                  color: OwuiPalette.textSecondary(context),
                                ),
                          ),
                        ),
                        ...models.map((model) {
                          final isSelected = model.id == currentModelId;
                          return ListTile(
                            selected: isSelected,
                            leading: Icon(
                              Icons.psychology,
                              color: isSelected
                                  ? Theme.of(context).colorScheme.primary
                                  : OwuiPalette.textSecondary(context),
                            ),
                            title: Text(model.displayName),
                            subtitle: _buildCapabilities(context, model),
                            trailing: isSelected ? const Icon(OwuiIcons.check) : null,
                            onTap: () => onModelSelected(provider.id, model.id),
                          );
                        }),
                        if (index < providers.length - 1) const Divider(),
                      ],
                    );
                  },
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildCapabilities(BuildContext context, ModelConfig model) {
    if (model.capabilities.isEmpty) return const SizedBox.shrink();
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: model.capabilities.map((cap) {
        return Tooltip(
          message: cap.displayName,
          child: Container(
            padding: EdgeInsets.all(ChatBoxTokens.spacing.xs),
            decoration: BoxDecoration(
              color: cap.color.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(ChatBoxTokens.radius.xs),
            ),
            child: Icon(cap.icon, size: 14, color: cap.color),
          ),
        );
      }).toList(),
    );
  }
}


