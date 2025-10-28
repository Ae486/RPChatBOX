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
  late int _contextLength;

  @override
  void initState() {
    super.initState();
    _parameters = widget.settings.parameters;
    _contextLength = widget.settings.contextLength;
  }

  void _save() {
    final updated = widget.settings.copyWith(
      parameters: _parameters,
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
                    // Temperature
                    _buildSliderSetting(
                      label: 'Temperature (温度)',
                      value: _parameters.temperature,
                      min: 0.0,
                      max: 2.0,
                      divisions: 20,
                      onChanged: (value) {
                        setState(() {
                          _parameters = _parameters.copyWith(temperature: value);
                        });
                      },
                      description: '控制输出的随机性。较低值(0.1-0.3)更确定和聚焦，较高值(0.7-1.0)更有创造性。',
                    ),

                    const SizedBox(height: 24),

                    // Top P
                    _buildSliderSetting(
                      label: 'Top P (核采样)',
                      value: _parameters.topP,
                      min: 0.0,
                      max: 1.0,
                      divisions: 20,
                      onChanged: (value) {
                        setState(() {
                          _parameters = _parameters.copyWith(topP: value);
                        });
                      },
                      description: '核采样参数。控制输出的多样性。建议值0.9-1.0。',
                    ),

                    const SizedBox(height: 24),

                    // Max Tokens
                    _buildSliderSetting(
                      label: 'Max Tokens (最大输出)',
                      value: _parameters.maxTokens.toDouble(),
                      min: 256,
                      max: 16384,
                      divisions: 63,
                      onChanged: (value) {
                        setState(() {
                          _parameters = _parameters.copyWith(maxTokens: value.toInt());
                        });
                      },
                      description: '单次响应的最大Token数量。过小可能导致回复被截断。',
                      valueFormatter: (value) => value.toInt().toString(),
                    ),

                    const SizedBox(height: 24),

                    // Context Length - 特殊范围：1-30普通值，500特殊值，-1无限制
                    _buildContextLengthSlider(),

                    const SizedBox(height: 24),

                    // 说明卡片
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: Theme.of(context).colorScheme.surfaceVariant.withOpacity(0.3),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                          color: Theme.of(context).colorScheme.outline.withOpacity(0.2),
                        ),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(
                                Icons.info_outline,
                                size: 18,
                                color: Theme.of(context).colorScheme.onSurfaceVariant,
                              ),
                              const SizedBox(width: 8),
                              Text(
                                '提示',
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          Text(
                            '这些参数会影响模型的输出行为。不同模型对参数的支持可能不同，如果遇到错误，请尝试使用默认值。',
                            style: TextStyle(
                              fontSize: 12,
                              color: Theme.of(context).colorScheme.onSurfaceVariant.withOpacity(0.8),
                            ),
                          ),
                        ],
                      ),
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

  Widget _buildContextLengthSlider() {
    // 滑块值映射：0-30对应1-30条，31对应500条，32对应无限制
    double sliderValue;
    if (_contextLength == -1) {
      sliderValue = 32; // 无限制
    } else if (_contextLength == 500) {
      sliderValue = 31; // 500条
    } else {
      sliderValue = _contextLength.toDouble().clamp(1, 30);
    }

    String displayValue;
    if (_contextLength == -1) {
      displayValue = '无限制';
    } else {
      displayValue = '$_contextLength 条';
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              '上下文消息数',
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
                displayValue,
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
          value: sliderValue,
          min: 1,
          max: 32,
          divisions: 31,
          onChanged: (value) {
            setState(() {
              if (value >= 32) {
                _contextLength = -1; // 无限制
              } else if (value >= 31) {
                _contextLength = 500; // 500条
              } else {
                _contextLength = value.toInt();
              }
            });
          },
        ),
        Text(
          '包含在请求中的历史消息数量。更多上下文消耗更多Token。无限制时将发送所有历史消息。',
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
              ),
        ),
      ],
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
