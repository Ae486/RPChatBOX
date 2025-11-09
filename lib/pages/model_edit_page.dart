import 'package:flutter/material.dart';
import '../models/model_config.dart';
import '../services/model_service_manager.dart';
import '../data/model_capability_presets.dart';
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
    _presetCapabilities = ModelCapabilityPresets.getCapabilities(widget.model.modelName);
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

  bool _isPresetCapability(ModelCapability capability) {
    return _presetCapabilities.contains(capability);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('模型设置'),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        actions: [
          if (_hasModifications)
            TextButton(
              onPressed: _save,
              child: const Text('保存', style: TextStyle(fontSize: 16)),
            ),
          const SizedBox(width: 8),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // 模型ID（只读）
          _buildSection(
            title: '模型信息',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildInfoRow('模型 ID', widget.model.modelName),
                const SizedBox(height: 12),
                _buildInfoRow('显示名称', widget.model.displayName),
              ],
            ),
          ),

          const SizedBox(height: 24),

          // 模型能力设置
          _buildSection(
            title: '模型能力',
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 警告提示
                if (!ModelCapabilityPresets.isKnownModel(widget.model.modelName))
                  Container(
                    margin: const EdgeInsets.only(bottom: 16),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.errorContainer.withOpacity(0.3),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                        color: Theme.of(context).colorScheme.error.withOpacity(0.3),
                      ),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          Icons.warning_amber_rounded,
                          color: Theme.of(context).colorScheme.error,
                          size: 20,
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Text(
                            '未识别的模型，请根据实际情况手动配置能力',
                            style: TextStyle(
                              fontSize: 13,
                              color: Theme.of(context).colorScheme.error,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),

                // 能力选择网格（移除文本能力）
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: ModelCapability.values
                      .where((cap) => cap != ModelCapability.text) // 🔧 移除文本能力
                      .map((capability) {
                    final isSelected = _selectedCapabilities.contains(capability);

                    return _buildCapabilityChip(
                      capability: capability,
                      isSelected: isSelected,
                    );
                  }).toList(),
                ),

                const SizedBox(height: 16),

                // 说明文本
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '请慎重更改模型类型，选择错误的类型会导致模型无法正常使用！',
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
                          ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSection({
    required String title,
    required Widget child,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: Theme.of(context).textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.bold,
              ),
        ),
        const SizedBox(height: 16),
        child,
      ],
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 80,
          child: Text(
            label,
            style: TextStyle(
              fontSize: 14,
              color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
            ),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w500,
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildCapabilityChip({
    required ModelCapability capability,
    required bool isSelected,
  }) {
    final theme = Theme.of(context);
    
    // 🔧 开启时显示彩色，关闭时显示灰色
    final chipColor = isSelected
        ? capability.color
        : theme.colorScheme.onSurface.withOpacity(0.4);
    
    final backgroundColor = isSelected
        ? capability.color.withOpacity(0.15)
        : theme.colorScheme.surfaceContainerHighest.withOpacity(0.5);

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => _toggleCapability(capability),
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: backgroundColor,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: chipColor.withOpacity(0.5),
              width: 2, // 🔧 固定边框宽度
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                capability.icon,
                size: 20,
                color: chipColor,
              ),
              const SizedBox(width: 8),
              Text(
                capability.displayName,
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w500, // 🔧 固定字体粗细
                  color: chipColor,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
