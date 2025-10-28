import 'package:flutter/material.dart';
import '../models/conversation_settings.dart';
import '../models/model_config.dart';

/// 对话配置对话框
/// 允许用户调整单个对话的参数和功能开关
class ConversationConfigDialog extends StatefulWidget {
  final ConversationSettings settings;
  final Function(ConversationSettings) onSave;

  const ConversationConfigDialog({
    super.key,
    required this.settings,
    required this.onSave,
  });

  @override
  State<ConversationConfigDialog> createState() => _ConversationConfigDialogState();
}

class _ConversationConfigDialogState extends State<ConversationConfigDialog> {
  late ModelParameters _parameters;
  late bool _enableVision;
  late bool _enableTools;
  late bool _enableNetwork;
  late int _contextLength;

  @override
  void initState() {
    super.initState();
    _parameters = widget.settings.parameters;
    _enableVision = widget.settings.enableVision;
    _enableTools = widget.settings.enableTools;
    _enableNetwork = widget.settings.enableNetwork;
    _contextLength = widget.settings.contextLength;
  }

  void _applyPreset(ConversationPreset preset) {
    setState(() {
      _parameters = preset.parameters;
      _enableVision = preset.enableVision;
      _enableTools = preset.enableTools;
      _contextLength = preset.contextLength;
    });
  }

  void _save() {
    final updated = widget.settings.copyWith(
      parameters: _parameters,
      enableVision: _enableVision,
      enableTools: _enableTools,
      enableNetwork: _enableNetwork,
      contextLength: _contextLength,
    );

    widget.onSave(updated);
    Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      child: Container(
        width: 500,
        constraints: const BoxConstraints(maxHeight: 700),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // 标题栏
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primaryContainer,
                borderRadius: const BorderRadius.only(
                  topLeft: Radius.circular(4),
                  topRight: Radius.circular(4),
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    Icons.tune,
                    color: Theme.of(context).colorScheme.onPrimaryContainer,
                  ),
                  const SizedBox(width: 12),
                  Text(
                    '对话配置',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          color: Theme.of(context).colorScheme.onPrimaryContainer,
                        ),
                  ),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(Icons.close),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
            ),

            // 内容区域
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // 配置预设
                    Text(
                      '快速预设',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                    ),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: ConversationPreset.presets.map((preset) {
                        return ActionChip(
                          label: Text(preset.name),
                          onPressed: () => _applyPreset(preset),
                          avatar: const Icon(Icons.flash_on, size: 18),
                        );
                      }).toList(),
                    ),

                    const SizedBox(height: 24),
                    const Divider(),
                    const SizedBox(height: 24),

                    // Temperature
                    _buildSliderSetting(
                      label: 'Temperature',
                      value: _parameters.temperature,
                      min: 0.0,
                      max: 2.0,
                      divisions: 20,
                      onChanged: (value) {
                        setState(() {
                          _parameters = _parameters.copyWith(temperature: value);
                        });
                      },
                      description: '控制输出的随机性。较低值更确定，较高值更有创造性。',
                    ),

                    const SizedBox(height: 20),

                    // Max Tokens
                    _buildSliderSetting(
                      label: 'Max Tokens',
                      value: _parameters.maxTokens.toDouble(),
                      min: 256,
                      max: 16384,
                      divisions: 63,
                      onChanged: (value) {
                        setState(() {
                          _parameters = _parameters.copyWith(maxTokens: value.toInt());
                        });
                      },
                      description: '单次响应的最大Token数量。',
                      valueFormatter: (value) => value.toInt().toString(),
                    ),

                    const SizedBox(height: 20),

                    // Top P
                    _buildSliderSetting(
                      label: 'Top P',
                      value: _parameters.topP,
                      min: 0.0,
                      max: 1.0,
                      divisions: 20,
                      onChanged: (value) {
                        setState(() {
                          _parameters = _parameters.copyWith(topP: value);
                        });
                      },
                      description: '核采样参数。控制输出的多样性。',
                    ),

                    const SizedBox(height: 20),

                    // Frequency Penalty
                    _buildSliderSetting(
                      label: 'Frequency Penalty',
                      value: _parameters.frequencyPenalty,
                      min: -2.0,
                      max: 2.0,
                      divisions: 40,
                      onChanged: (value) {
                        setState(() {
                          _parameters = _parameters.copyWith(frequencyPenalty: value);
                        });
                      },
                      description: '降低重复词汇的频率。',
                    ),

                    const SizedBox(height: 20),

                    // Presence Penalty
                    _buildSliderSetting(
                      label: 'Presence Penalty',
                      value: _parameters.presencePenalty,
                      min: -2.0,
                      max: 2.0,
                      divisions: 40,
                      onChanged: (value) {
                        setState(() {
                          _parameters = _parameters.copyWith(presencePenalty: value);
                        });
                      },
                      description: '鼓励谈论新话题。',
                    ),

                    const SizedBox(height: 20),

                    // Context Length
                    _buildSliderSetting(
                      label: '上下文长度',
                      value: _contextLength.toDouble(),
                      min: 1,
                      max: 30,
                      divisions: 29,
                      onChanged: (value) {
                        setState(() {
                          _contextLength = value.toInt();
                        });
                      },
                      description: '包含在请求中的历史消息数量。',
                      valueFormatter: (value) => '${value.toInt()} 条消息',
                    ),

                    const SizedBox(height: 24),
                    const Divider(),
                    const SizedBox(height: 24),

                    // 功能开关
                    Text(
                      '功能开关',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                    ),
                    const SizedBox(height: 12),

                    SwitchListTile(
                      title: const Text('流式输出'),
                      subtitle: const Text('实时显示AI响应内容'),
                      value: _parameters.streamOutput,
                      onChanged: (value) {
                        setState(() {
                          _parameters = _parameters.copyWith(streamOutput: value);
                        });
                      },
                    ),

                    SwitchListTile(
                      title: const Text('视觉功能'),
                      subtitle: const Text('允许上传和分析图片'),
                      value: _enableVision,
                      onChanged: (value) {
                        setState(() {
                          _enableVision = value;
                        });
                      },
                    ),

                    SwitchListTile(
                      title: const Text('工具调用'),
                      subtitle: const Text('允许模型使用外部工具'),
                      value: _enableTools,
                      onChanged: (value) {
                        setState(() {
                          _enableTools = value;
                        });
                      },
                    ),

                    SwitchListTile(
                      title: const Text('联网功能'),
                      subtitle: const Text('允许模型访问网络（开发中）'),
                      value: _enableNetwork,
                      onChanged: null, // 暂未实现
                    ),
                  ],
                ),
              ),
            ),

            // 底部按钮
            Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                border: Border(
                  top: BorderSide(color: Colors.grey.shade300),
                ),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('取消'),
                  ),
                  const SizedBox(width: 12),
                  ElevatedButton(
                    onPressed: _save,
                    child: const Text('保存'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSliderSetting({
    required String label,
    required double value,
    required double min,
    required double max,
    required int divisions,
    required ValueChanged<double> onChanged,
    required String description,
    String Function(double)? valueFormatter,
  }) {
    final formatter = valueFormatter ?? (v) => v.toStringAsFixed(2);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              label,
              style: Theme.of(context).textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.secondaryContainer,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                formatter(value),
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.bold,
                  color: Theme.of(context).colorScheme.onSecondaryContainer,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        Slider(
          value: value,
          min: min,
          max: max,
          divisions: divisions,
          onChanged: onChanged,
        ),
        Text(
          description,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Colors.grey.shade600,
              ),
        ),
      ],
    );
  }
}
