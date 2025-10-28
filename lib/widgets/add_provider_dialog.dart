import 'package:flutter/material.dart';
import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../services/model_service_manager.dart';

/// 添加/编辑Provider对话框
class AddProviderDialog extends StatefulWidget {
  final ModelServiceManager serviceManager;
  final ProviderConfig? existingProvider;

  const AddProviderDialog({
    super.key,
    required this.serviceManager,
    this.existingProvider,
  });

  @override
  State<AddProviderDialog> createState() => _AddProviderDialogState();
}

class _AddProviderDialogState extends State<AddProviderDialog> {
  final _formKey = GlobalKey<FormState>();
  late TextEditingController _nameController;
  late TextEditingController _apiUrlController;
  late TextEditingController _apiKeyController;
  late TextEditingController _modelsController;

  ProviderType _selectedType = ProviderType.openai;
  bool _isLoading = false;
  bool _isTesting = false;
  String? _testMessage;

  @override
  void initState() {
    super.initState();
    final existing = widget.existingProvider;

    _nameController = TextEditingController(text: existing?.name ?? '');
    _apiUrlController = TextEditingController(text: existing?.apiUrl ?? '');
    _apiKeyController = TextEditingController(text: existing?.apiKey ?? '');
    _modelsController = TextEditingController();

    if (existing != null) {
      _selectedType = existing.type;
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _apiUrlController.dispose();
    _apiKeyController.dispose();
    _modelsController.dispose();
    super.dispose();
  }

  Future<void> _testConnection() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isTesting = true;
      _testMessage = null;
    });

    try {
      final tempProvider = ProviderConfig(
        id: 'temp',
        name: _nameController.text,
        type: _selectedType,
        apiUrl: _apiUrlController.text,
        apiKey: _apiKeyController.text,
      );

      final result = await widget.serviceManager.testProvider(tempProvider);

      setState(() {
        _isTesting = false;
        if (result.success) {
          _testMessage = '✓ 连接成功 (${result.responseTimeMs}ms)';
          // 自动填充可用模型
          if (result.availableModels != null && result.availableModels!.isNotEmpty) {
            _modelsController.text = result.availableModels!.join(', ');
          }
        } else {
          _testMessage = '✗ ${result.errorMessage}';
        }
      });
    } catch (e) {
      setState(() {
        _isTesting = false;
        _testMessage = '✗ 测试失败: ${e.toString()}';
      });
    }
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() => _isLoading = true);

    try {
      final provider = widget.existingProvider?.copyWith(
            name: _nameController.text.trim(),
            type: _selectedType,
            apiUrl: _apiUrlController.text.trim(),
            apiKey: _apiKeyController.text.trim(),
          ) ??
          ProviderConfig(
            id: widget.serviceManager.generateId(),
            name: _nameController.text.trim(),
            type: _selectedType,
            apiUrl: _apiUrlController.text.trim(),
            apiKey: _apiKeyController.text.trim(),
          );

      if (widget.existingProvider != null) {
        await widget.serviceManager.updateProvider(provider);
      } else {
        await widget.serviceManager.addProvider(provider);

        // 创建模型配置
        final modelNames = _modelsController.text
            .split(',')
            .map((s) => s.trim())
            .where((s) => s.isNotEmpty)
            .toList();

        if (modelNames.isNotEmpty) {
          final models = modelNames.map((name) {
            return ModelConfig(
              id: widget.serviceManager.generateId(),
              providerId: provider.id,
              modelName: name,
              displayName: name,
              capabilities: _inferCapabilities(name),
            );
          }).toList();

          await widget.serviceManager.addModels(models);
        }
      }

      if (mounted) {
        Navigator.pop(context, provider);
      }
    } catch (e) {
      setState(() => _isLoading = false);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('保存失败: ${e.toString()}')),
        );
      }
    }
  }

  Set<ModelCapability> _inferCapabilities(String modelName) {
    final capabilities = <ModelCapability>{ModelCapability.text};
    final nameLower = modelName.toLowerCase();

    if (nameLower.contains('vision') ||
        nameLower.contains('gpt-4') ||
        nameLower.contains('claude-3') ||
        nameLower.contains('gemini')) {
      capabilities.add(ModelCapability.vision);
    }

    if (nameLower.contains('gpt-4') ||
        nameLower.contains('gpt-3.5') ||
        nameLower.contains('claude') ||
        nameLower.contains('gemini')) {
      capabilities.add(ModelCapability.tool);
    }

    return capabilities;
  }

  @override
  Widget build(BuildContext context) {
    final isEdit = widget.existingProvider != null;

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
                    isEdit ? Icons.edit : Icons.add_circle_outline,
                    color: Theme.of(context).colorScheme.onPrimaryContainer,
                  ),
                  const SizedBox(width: 12),
                  Text(
                    isEdit ? '编辑服务' : '添加服务',
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

            // 表单内容
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(20),
                child: Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // Provider类型选择
                      Text(
                        'Provider 类型',
                        style: Theme.of(context).textTheme.labelLarge,
                      ),
                      const SizedBox(height: 8),
                      SegmentedButton<ProviderType>(
                        segments: ProviderType.values.map((type) {
                          return ButtonSegment<ProviderType>(
                            value: type,
                            label: Text(type.displayName),
                          );
                        }).toList(),
                        selected: {_selectedType},
                        onSelectionChanged: (Set<ProviderType> selection) {
                          setState(() {
                            _selectedType = selection.first;
                            // 自动填充默认API地址
                            if (_apiUrlController.text.isEmpty) {
                              _apiUrlController.text = _selectedType.defaultApiUrl;
                            }
                          });
                        },
                      ),

                      const SizedBox(height: 20),

                      // Provider名称
                      TextFormField(
                        controller: _nameController,
                        decoration: const InputDecoration(
                          labelText: '名称',
                          hintText: '例如：My OpenAI',
                          border: OutlineInputBorder(),
                        ),
                        validator: (value) {
                          if (value == null || value.trim().isEmpty) {
                            return '请输入名称';
                          }
                          return null;
                        },
                      ),

                      const SizedBox(height: 16),

                      // API地址
                      TextFormField(
                        controller: _apiUrlController,
                        decoration: InputDecoration(
                          labelText: 'API 地址',
                          hintText: _selectedType.defaultApiUrl,
                          border: const OutlineInputBorder(),
                          helperText: '结尾需包含 /v1 版本路径',
                        ),
                        validator: (value) {
                          if (value == null || value.trim().isEmpty) {
                            return '请输入API地址';
                          }
                          final uri = Uri.tryParse(value);
                          if (uri == null || !uri.isAbsolute) {
                            return '请输入有效的URL';
                          }
                          return null;
                        },
                      ),

                      const SizedBox(height: 16),

                      // API密钥
                      TextFormField(
                        controller: _apiKeyController,
                        decoration: InputDecoration(
                          labelText: 'API 密钥',
                          hintText: 'sk-...',
                          border: const OutlineInputBorder(),
                          suffixIcon: IconButton(
                            icon: const Icon(Icons.wifi_tethering),
                            onPressed: _isTesting ? null : _testConnection,
                            tooltip: '测试连接',
                          ),
                        ),
                        obscureText: true,
                        validator: (value) {
                          if (value == null || value.trim().isEmpty) {
                            return '请输入API密钥';
                          }
                          return null;
                        },
                      ),

                      // 测试结果
                      if (_testMessage != null) ...[
                        const SizedBox(height: 8),
                        Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: _testMessage!.startsWith('✓')
                                ? Colors.green.withValues(alpha: 0.1)
                                : Colors.red.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(6),
                            border: Border.all(
                              color: _testMessage!.startsWith('✓')
                                  ? Colors.green
                                  : Colors.red,
                            ),
                          ),
                          child: Row(
                            children: [
                              Icon(
                                _testMessage!.startsWith('✓') ? Icons.check_circle : Icons.error,
                                color: _testMessage!.startsWith('✓') ? Colors.green : Colors.red,
                                size: 20,
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  _testMessage!,
                                  style: TextStyle(
                                    color: _testMessage!.startsWith('✓')
                                        ? Colors.green.shade700
                                        : Colors.red.shade700,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],

                      const SizedBox(height: 16),

                      // 模型列表（仅新建时）
                      if (!isEdit) ...[
                        TextFormField(
                          controller: _modelsController,
                          decoration: const InputDecoration(
                            labelText: '模型列表（可选）',
                            hintText: 'gpt-4, gpt-3.5-turbo',
                            border: OutlineInputBorder(),
                            helperText: '多个模型用逗号分隔，留空则稍后手动添加',
                          ),
                          maxLines: 3,
                        ),
                      ],
                    ],
                  ),
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
                    onPressed: _isLoading ? null : () => Navigator.pop(context),
                    child: const Text('取消'),
                  ),
                  const SizedBox(width: 12),
                  ElevatedButton(
                    onPressed: _isLoading ? null : _save,
                    child: _isLoading
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : Text(isEdit ? '保存' : '创建'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
