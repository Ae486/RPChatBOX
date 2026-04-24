import 'package:flutter/material.dart';

import '../chat_ui/owui/components/owui_app_bar.dart';
import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/components/owui_scaffold.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
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
  String? _editedCapabilitySource;
  ModelCapabilityProfile? _editedCapabilityProfile;
  bool _manualOverrideEnabled = false;
  bool _hasModifications = false;

  @override
  void initState() {
    super.initState();
    _selectedCapabilities = Set.from(widget.model.capabilities);
    _editedCapabilitySource = widget.model.capabilitySource;
    _editedCapabilityProfile = widget.model.capabilityProfile;
    _manualOverrideEnabled = widget.model.capabilitySource == 'user_declared';
  }

  void _toggleCapability(ModelCapability capability) {
    if (!_manualOverrideEnabled) return;
    setState(() {
      if (_selectedCapabilities.contains(capability)) {
        _selectedCapabilities.remove(capability);
        _hasModifications = true;
      } else {
        _selectedCapabilities.add(capability);
        _hasModifications = true;
      }
    });
  }

  void _enableManualOverride() {
    setState(() {
      _manualOverrideEnabled = true;
      _editedCapabilitySource = 'user_declared';
      _editedCapabilityProfile = null;
      _hasModifications = true;
    });
  }

  Future<void> _restoreTemplate() async {
    final provider = widget.serviceManager.getProvider(widget.model.providerId);
    if (provider == null) {
      GlobalToast.showError(context, 'Provider 不存在，无法恢复模板能力');
      return;
    }

    try {
      final suggested = await widget.serviceManager.buildSuggestedModel(
        provider: provider,
        modelName: widget.model.modelName,
        modelId: widget.model.id,
      );
      setState(() {
        _selectedCapabilities = Set<ModelCapability>.from(
          suggested.capabilities,
        );
        _editedCapabilitySource = suggested.capabilitySource;
        _editedCapabilityProfile = suggested.capabilityProfile;
        _manualOverrideEnabled = false;
        _hasModifications = true;
      });
    } catch (e) {
      if (!mounted) return;
      GlobalToast.showError(context, '恢复模板能力失败: $e');
    }
  }

  Future<void> _save() async {
    final updatedModel = widget.model.copyWith(
      capabilities: _selectedCapabilities,
      capabilitySource: _manualOverrideEnabled
          ? 'user_declared'
          : _editedCapabilitySource,
      capabilityProfile: _manualOverrideEnabled
          ? null
          : _editedCapabilityProfile,
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
                if (_effectiveCapabilityProfile != null) ...[
                  _buildNativeCapabilitySummary(_effectiveCapabilityProfile!),
                  SizedBox(height: spacing.lg),
                ],
                if ((_effectiveCapabilityProfile?.known ?? false) == false)
                  _UnknownModelCallout(),
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        '兼容标签 Override',
                        style: Theme.of(context).textTheme.labelLarge,
                      ),
                    ),
                    if (!_manualOverrideEnabled)
                      OutlinedButton(
                        onPressed: _enableManualOverride,
                        child: const Text('启用 Override'),
                      ),
                    if (_manualOverrideEnabled)
                      OutlinedButton(
                        onPressed: _restoreTemplate,
                        child: const Text('恢复模板'),
                      ),
                  ],
                ),
                SizedBox(height: spacing.sm),
                if (_manualOverrideEnabled)
                  Padding(
                    padding: EdgeInsets.only(bottom: spacing.sm),
                    child: Text(
                      '当前为手工 override 模式。保存后将以 user_declared 写入，覆盖模板能力。',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                  )
                else
                  Padding(
                    padding: EdgeInsets.only(bottom: spacing.sm),
                    child: Text(
                      '默认使用 LiteLLM 模板能力；只有启用 Override 后，下面的兼容标签才会生效。',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: colors.textSecondary,
                      ),
                    ),
                  ),
                Wrap(
                  spacing: spacing.md,
                  runSpacing: spacing.md,
                  children: ModelCapability.values.map((capability) {
                        final isSelected = _selectedCapabilities.contains(
                          capability,
                        );

                        return _buildCapabilityChip(
                          capability: capability,
                          isSelected: isSelected,
                          enabled: _manualOverrideEnabled,
                        );
                      }).toList(),
                ),
                SizedBox(height: spacing.lg),
                Text(
                  '上方原生能力来自 LiteLLM 模板；下方兼容标签仅用于当前项目过渡期兼容。',
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

  ModelCapabilityProfile? get _effectiveCapabilityProfile =>
      _editedCapabilityProfile ?? widget.model.capabilityProfile;

  Widget _buildNativeCapabilitySummary(ModelCapabilityProfile profile) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final rows = <String>[
      '来源: ${profile.capabilitySource}',
      if (profile.mode != null) '模式: ${profile.mode}',
      '模板命中: ${profile.known ? '是' : '否'}',
      '传输 Provider: ${profile.transportProviderType ?? 'unknown'}',
      if (profile.semanticProviderType != null)
        '语义 Provider: ${profile.semanticProviderType}',
      if (profile.semanticLookupModel != null)
        '模板键: ${profile.semanticLookupModel}',
      if (profile.maxInputTokens != null)
        'Max Input: ${profile.maxInputTokens}',
      if (profile.maxOutputTokens != null)
        'Max Output: ${profile.maxOutputTokens}',
    ];
    final nativeFlags = <String>[
      if (profile.supportsFunctionCalling == true) 'supports_function_calling',
      if (profile.supportsToolChoice == true) 'supports_tool_choice',
      if (profile.supportsResponseSchema == true) 'supports_response_schema',
      if (profile.supportsReasoning == true) 'supports_reasoning',
      if (profile.supportsVision == true) 'supports_vision',
      if (profile.supportsPdfInput == true) 'supports_pdf_input',
      if (profile.supportsWebSearch == true) 'supports_web_search',
      if (profile.supportsAudioInput == true) 'supports_audio_input',
      if (profile.supportsAudioOutput == true) 'supports_audio_output',
      if (profile.supportsSystemMessages == true) 'supports_system_messages',
    ];

    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(spacing.md),
      decoration: BoxDecoration(
        color: colors.surface2,
        borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
        border: Border.all(color: colors.borderSubtle),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('LiteLLM 原生能力', style: Theme.of(context).textTheme.labelLarge),
          SizedBox(height: spacing.sm),
          ...rows.map(
            (row) => Padding(
              padding: EdgeInsets.only(bottom: spacing.xs),
              child: Text(
                row,
                style: Theme.of(
                  context,
                ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
              ),
            ),
          ),
          if (nativeFlags.isNotEmpty) ...[
            SizedBox(height: spacing.sm),
            Wrap(
              spacing: spacing.sm,
              runSpacing: spacing.sm,
              children: nativeFlags
                  .map(
                    (flag) => Chip(
                      label: Text(flag),
                      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                  )
                  .toList(),
            ),
          ],
          if (profile.supportedOpenaiParams.isNotEmpty) ...[
            SizedBox(height: spacing.sm),
            Text(
              'Supported OpenAI Params',
              style: Theme.of(context).textTheme.labelMedium,
            ),
            SizedBox(height: spacing.xs),
            Text(
              profile.supportedOpenaiParams.join(', '),
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: colors.textSecondary),
            ),
          ],
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
    required bool enabled,
  }) {
    final colors = context.owuiColors;
    final spacing = context.owuiSpacing;
    final radius = context.owuiRadius;

    final accentColor = isSelected ? capability.color : colors.textSecondary;
    final borderColor = isSelected
        ? capability.color.withValues(alpha: 0.55)
        : colors.borderSubtle;
    final chipBg = enabled ? colors.surfaceCard : colors.surface2;

    final iconSize = 20 * context.owui.uiScale;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: enabled ? () => _toggleCapability(capability) : null,
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
              'LiteLLM 模板未命中该模型，或当前正在使用手工 override。请谨慎维护兼容标签。',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}
