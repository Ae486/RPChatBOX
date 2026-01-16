/// INPUT: ModelConfig + ModelServiceManager
/// OUTPUT: ModelEditPage - 编辑模型能力/参数（capabilities presets 等）
/// POS: UI 层 / Pages - 模型编辑页

import 'package:flutter/material.dart';

import '../chat_ui/owui/components/owui_app_bar.dart';
import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/components/owui_scaffold.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../data/model_capability_presets.dart';
import '../models/model_config.dart';
import '../services/model_service_manager.dart';
import '../utils/global_toast.dart';

/// 模型设置页面
/// 用于编辑模型的能力配置
class ModelEditPage extends StatefulWidget {
  final ModelConfig model;
  final ModelServiceManager serviceManager;

  const ModelEditPage({
    super.key,
    required this.model,
    required this.serviceManager,
  });

  @override
  State<ModelEditPage> createState() => _ModelEditPageState();
}

class _ModelEditPageState extends State<ModelEditPage> {
  late Set<ModelCapability> _selectedCapabilities;
  late Set<ModelCapability> _presetCapabilities;
  bool _hasModifications = false;

  @override
  void initState() {
    super.initState();
    _selectedCapabilities = Set.from(widget.model.capabilities);
    _presetCapabilities = ModelCapabilityPresets.getCapabilities(
      widget.model.modelName,
    );
  }

  void _toggleCapability(ModelCapability capability) {
    setState(() {
      if (_selectedCapabilities.contains(capability)) {
        _selectedCapabilities.remove(capability);
        _hasModifications = true;
      } else {
        _selectedCapabilities.add(capability);
        _hasModifications = true;
      }

      // 🔧 确保始终包含文本能力（不显示但必须有）
      _selectedCapabilities.add(ModelCapability.text);
    });
  }

  Future<void> _save() async {
    final updatedModel = widget.model.copyWith(
      capabilities: _selectedCapabilities,
    );

    await widget.serviceManager.updateModel(updatedModel);

    if (mounted) {
      GlobalToast.showSuccess(context, '已保存模型设置');
      Navigator.pop(context, updatedModel);
    }
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.owuiColors;
    final spacing = context.owuiSpacing;

    return OwuiScaffold(
      appBar: OwuiAppBar(
        title: const Text('模型设置'),
        actions: [
          if (_hasModifications)
            TextButton(onPressed: _save, child: const Text('保存')),
          SizedBox(width: spacing.sm),
        ],
      ),
      body: ListView(
        padding: EdgeInsets.all(spacing.lg),
        children: [
          _buildSection(
            title: '模型信息',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildInfoRow('模型 ID', widget.model.modelName),
                SizedBox(height: spacing.md),
                _buildInfoRow('显示名称', widget.model.displayName),
              ],
            ),
          ),
          SizedBox(height: spacing.xl),
          _buildSection(
            title: '模型能力',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!ModelCapabilityPresets.isKnownModel(
                  widget.model.modelName,
                ))
                  _UnknownModelCallout(),
                Wrap(
                  spacing: spacing.md,
                  runSpacing: spacing.md,
                  children: ModelCapability.values
                      .where((cap) => cap != ModelCapability.text)
                      .map((capability) {
                        final isSelected = _selectedCapabilities.contains(
                          capability,
                        );
                        final isPreset = _presetCapabilities.contains(
                          capability,
                        );

                        return _buildCapabilityChip(
                          capability: capability,
                          isSelected: isSelected,
                          isPreset: isPreset,
                        );
                      })
                      .toList(),
                ),
                SizedBox(height: spacing.lg),
                Text(
                  '请慎重更改模型类型，选择错误的类型会导致模型无法正常使用！',
                  style: Theme.of(
                    context,
                  ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSection({required String title, required Widget child}) {
    final spacing = context.owuiSpacing;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: Theme.of(
            context,
          ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w600),
        ),
        SizedBox(height: spacing.sm),
        OwuiCard(padding: EdgeInsets.all(spacing.lg), child: child),
      ],
    );
  }

  Widget _buildInfoRow(String label, String value) {
    final colors = context.owuiColors;

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 80 * context.owui.uiScale,
          child: Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: Theme.of(
              context,
            ).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
          ),
        ),
      ],
    );
  }

  Widget _buildCapabilityChip({
    required ModelCapability capability,
    required bool isSelected,
    required bool isPreset,
  }) {
    final colors = context.owuiColors;
    final spacing = context.owuiSpacing;
    final radius = context.owuiRadius;

    final accentColor = isSelected ? capability.color : colors.textSecondary;
    final borderColor = isSelected
        ? capability.color.withValues(alpha: 0.55)
        : colors.borderSubtle;

    final chipBg = isPreset ? colors.surface2 : colors.surfaceCard;

    final iconSize = 20 * context.owui.uiScale;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => _toggleCapability(capability),
        borderRadius: BorderRadius.circular(radius.rXl),
        child: Container(
          padding: EdgeInsets.symmetric(
            horizontal: spacing.lg,
            vertical: spacing.md,
          ),
          decoration: BoxDecoration(
            color: chipBg,
            borderRadius: BorderRadius.circular(radius.rXl),
            border: Border.all(color: borderColor),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(capability.icon, size: iconSize, color: accentColor),
              SizedBox(width: spacing.sm),
              Text(
                capability.displayName,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  fontWeight: FontWeight.w500,
                  color: accentColor,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _UnknownModelCallout extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final colors = context.owuiColors;
    final spacing = context.owuiSpacing;
    final radius = context.owuiRadius;
    final scheme = Theme.of(context).colorScheme;

    final iconSize = 20 * context.owui.uiScale;

    return Container(
      margin: EdgeInsets.only(bottom: spacing.lg),
      padding: EdgeInsets.all(spacing.md),
      decoration: BoxDecoration(
        color: colors.surface2,
        borderRadius: BorderRadius.circular(radius.rLg),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(OwuiIcons.warning, color: scheme.error, size: iconSize),
          SizedBox(width: spacing.md),
          Expanded(
            child: Text(
              '未识别的模型，请根据实际情况手动配置能力',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}
