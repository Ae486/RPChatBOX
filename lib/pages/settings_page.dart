import 'package:flutter/material.dart';
import '../models/chat_settings.dart';
import '../services/storage_service.dart';
import '../services/openai_service.dart';

/// 设置页面
class SettingsPage extends StatefulWidget {
  final ChatSettings initialSettings;
  final Function(ChatSettings) onSettingsChanged;

  const SettingsPage({
    super.key,
    required this.initialSettings,
    required this.onSettingsChanged,
  });

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final _formKey = GlobalKey<FormState>();
  final _storageService = StorageService();
  
  late TextEditingController _apiUrlController;
  late TextEditingController _apiKeyController;
  late TextEditingController _modelController;
  late TextEditingController _providerController;
  late double _temperature;
  late double _topP;
  late int _maxTokens;
  
  bool _isLoading = false;
  String? _testResult;

  @override
  void initState() {
    super.initState();
    _apiUrlController = TextEditingController(text: widget.initialSettings.apiUrl);
    _apiKeyController = TextEditingController(text: widget.initialSettings.apiKey);
    _modelController = TextEditingController(text: widget.initialSettings.model);
    _providerController = TextEditingController(text: widget.initialSettings.providerName);
    _temperature = widget.initialSettings.temperature;
    _topP = widget.initialSettings.topP;
    _maxTokens = widget.initialSettings.maxTokens;
  }

  @override
  void dispose() {
    _apiUrlController.dispose();
    _apiKeyController.dispose();
    _modelController.dispose();
    _providerController.dispose();
    super.dispose();
  }

  /// 保存设置
  Future<void> _saveSettings() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    final settings = ChatSettings(
      apiUrl: _apiUrlController.text.trim(),
      apiKey: _apiKeyController.text.trim(),
      model: _modelController.text.trim(),
      providerName: _providerController.text.trim(),
      temperature: _temperature,
      topP: _topP,
      maxTokens: _maxTokens,
    );

    await _storageService.saveSettings(settings);
    widget.onSettingsChanged(settings);

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('✅ 设置已保存')),
      );
      Navigator.pop(context);
    }
  }

  /// 测试连接
  Future<void> _testConnection() async {
    if (_apiUrlController.text.trim().isEmpty || _apiKeyController.text.trim().isEmpty) {
      setState(() {
        _testResult = '❌ 请先填写 API URL 和 API Key';
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _testResult = null;
    });

    try {
      final testSettings = ChatSettings(
        apiUrl: _apiUrlController.text.trim(),
        apiKey: _apiKeyController.text.trim(),
        model: _modelController.text.trim(),
      );

      final service = OpenAIService(testSettings);
      final success = await service.testConnection();

      setState(() {
        _testResult = success ? '✅ 连接成功！' : '❌ 连接失败';
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _testResult = '❌ 测试失败: $e';
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('设置'),
        actions: [
          IconButton(
            icon: const Icon(Icons.save),
            onPressed: _saveSettings,
            tooltip: '保存设置',
          ),
        ],
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // AI 服务商选择
            Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'AI 服务商快速配置',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      children: AIProviderPreset.presets.map((preset) {
                        return ChoiceChip(
                          label: Text(preset.name),
                          selected: _providerController.text == preset.name,
                          onSelected: (selected) {
                            if (selected) {
                              setState(() {
                                _providerController.text = preset.name;
                                if (preset.apiUrl.isNotEmpty) {
                                  _apiUrlController.text = preset.apiUrl;
                                }
                                if (preset.defaultModel.isNotEmpty) {
                                  _modelController.text = preset.defaultModel;
                                }
                              });
                            }
                          },
                        );
                      }).toList(),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 16),

            // 服务商名称
            TextFormField(
              controller: _providerController,
              decoration: const InputDecoration(
                labelText: '服务商名称',
                hintText: 'OpenAI',
                border: OutlineInputBorder(),
                prefixIcon: Icon(Icons.cloud),
              ),
            ),
            const SizedBox(height: 16),

            // API URL
            TextFormField(
              controller: _apiUrlController,
              decoration: const InputDecoration(
                labelText: 'API URL',
                hintText: 'https://api.openai.com/v1/chat/completions',
                border: OutlineInputBorder(),
                prefixIcon: Icon(Icons.link),
              ),
              validator: (value) {
                if (value == null || value.trim().isEmpty) {
                  return '请输入 API URL';
                }
                if (!value.startsWith('http')) {
                  return 'URL 必须以 http:// 或 https:// 开头';
                }
                return null;
              },
            ),
            const SizedBox(height: 16),

            // API Key
            TextFormField(
              controller: _apiKeyController,
              decoration: const InputDecoration(
                labelText: 'API Key',
                hintText: 'sk-...',
                border: OutlineInputBorder(),
                prefixIcon: Icon(Icons.key),
              ),
              obscureText: true,
              validator: (value) {
                if (value == null || value.trim().isEmpty) {
                  return '请输入 API Key';
                }
                return null;
              },
            ),
            const SizedBox(height: 16),

            // Model
            TextFormField(
              controller: _modelController,
              decoration: const InputDecoration(
                labelText: '模型',
                hintText: 'gpt-3.5-turbo',
                border: OutlineInputBorder(),
                prefixIcon: Icon(Icons.model_training),
              ),
              validator: (value) {
                if (value == null || value.trim().isEmpty) {
                  return '请输入模型名称';
                }
                return null;
              },
            ),
            const SizedBox(height: 24),

            // Temperature
            _buildSliderField(
              label: 'Temperature',
              value: _temperature,
              min: 0.0,
              max: 2.0,
              divisions: 20,
              onChanged: (value) => setState(() => _temperature = value),
            ),
            const SizedBox(height: 16),

            // Top P
            _buildSliderField(
              label: 'Top P',
              value: _topP,
              min: 0.0,
              max: 1.0,
              divisions: 10,
              onChanged: (value) => setState(() => _topP = value),
            ),
            const SizedBox(height: 16),

            // Max Tokens
            _buildSliderField(
              label: 'Max Tokens',
              value: _maxTokens.toDouble(),
              min: 100,
              max: 4000,
              divisions: 39,
              onChanged: (value) => setState(() => _maxTokens = value.toInt()),
              displayValue: _maxTokens.toString(),
            ),
            const SizedBox(height: 24),

            // 测试连接按钮
            ElevatedButton.icon(
              onPressed: _isLoading ? null : _testConnection,
              icon: _isLoading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.wifi_tethering),
              label: Text(_isLoading ? '测试中...' : '测试连接'),
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.all(16),
              ),
            ),

            // 测试结果
            if (_testResult != null) ...[
              const SizedBox(height: 16),
              Card(
                color: _testResult!.startsWith('✅')
                    ? Colors.green.shade50
                    : Colors.red.shade50,
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(
                    _testResult!,
                    style: TextStyle(
                      color: _testResult!.startsWith('✅')
                          ? Colors.green.shade900
                          : Colors.red.shade900,
                    ),
                  ),
                ),
              ),
            ],

            const SizedBox(height: 24),

            // 说明文本
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '参数说明',
                      style: Theme.of(context).textTheme.titleMedium,
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      '• Temperature: 控制回复的随机性，值越高越随机 (0-2)\n'
                      '• Top P: 核采样参数，控制多样性 (0-1)\n'
                      '• Max Tokens: 单次回复的最大token数量',
                      style: TextStyle(fontSize: 12, color: Colors.grey),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// 构建滑块字段
  Widget _buildSliderField({
    required String label,
    required double value,
    required double min,
    required double max,
    required int divisions,
    required ValueChanged<double> onChanged,
    String? displayValue,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(fontSize: 16)),
            Text(
              displayValue ?? value.toStringAsFixed(2),
              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
          ],
        ),
        Slider(
          value: value,
          min: min,
          max: max,
          divisions: divisions,
          label: displayValue ?? value.toStringAsFixed(2),
          onChanged: onChanged,
        ),
      ],
    );
  }
}

