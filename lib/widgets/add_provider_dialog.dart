import 'package:flutter/material.dart';
import '../design_system/apple_icons.dart';
import 'apple_text_field.dart';
import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../services/model_service_manager.dart';
import '../design_system/design_tokens.dart';

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
              padding: EdgeInsets.all(ChatBoxTokens.spacing.lg + 4),
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
                    isEdit ? AppleIcons.edit : AppleIcons.addCircle,
                    color: Theme.of(context).colorScheme.onPrimaryContainer,
                  ),
                  SizedBox(width: ChatBoxTokens.spacing.md),
                  Text(
                    isEdit ? '编辑服务' : '添加服务',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                          color: Theme.of(context).colorScheme.onPrimaryContainer,
                        ),
                  ),
                  const Spacer(),
                  IconButton(
                    icon: const Icon(AppleIcons.close),
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
            ),

            // 表单内容
            Expanded(
              child: SingleChildScrollView(
                padding: EdgeInsets.all(ChatBoxTokens.spacing.lg + 4),
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
                      SizedBox(height: ChatBoxTokens.spacing.sm),
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

                      SizedBox(height: ChatBoxTokens.spacing.lg + 4),

                      // Provider名称
                      AppleTextField(
                        controller: _nameController,
                        labelText: '名称',
                        hintText: '例如：My OpenAI',
                        prefixIcon: AppleIcons.settings,
                        showClearButton: true,
                        validator: (value) {
                          if (value == null || value.trim().isEmpty) {
                            return '请输入名称';
                          }
                          return null;
                        },
                      ),

                      SizedBox(height: ChatBoxTokens.spacing.lg),

                      // API地址
                      AppleTextField(
                        controller: _apiUrlController,
                        labelText: 'API 地址',
                        hintText: _selectedType.defaultApiUrl,
                        prefixIcon: AppleIcons.link,
                        helperText: '结尾需包含 /v1 版本路径',
                        showClearButton: true,
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
                      Stack(
                        alignment: Alignment.centerRight,
                        children: [
                          AppleTextField(
                            controller: _apiKeyController,
                            labelText: 'API 密钥',
                            hintText: 'sk-...',
                            prefixIcon: AppleIcons.key,
                            obscureText: true, // 自动显示密码切换按钮
                            validator: (value) {
                              if (value == null || value.trim().isEmpty) {
                                return '请输入API密钥';
                              }
                              return null;
                            },
                          ),
                          // 测试连接按钮
                          Positioned(
                            right: 48, // 在密码切换按钮左边
                            child: IconButton(
                              icon: const Icon(Icons.wifi_tethering, size: 20),
                              onPressed: _isTesting ? null : _testConnection,
                              tooltip: '测试连接',
                              color: Colors.grey.shade600,
                            ),
                          ),
                        ],
                      ),

                      // 测试结果
                      if (_testMessage != null) ...[
                        SizedBox(height: ChatBoxTokens.spacing.sm),
                        Container(
                          padding: EdgeInsets.all(ChatBoxTokens.spacing.md),
                          decoration: BoxDecoration(
                            color: _testMessage!.startsWith('✓')
                                ? Colors.green.withValues(alpha: 0.1)
                                : Colors.red.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(ChatBoxTokens.radius.xs),
                            border: Border.all(
                              color: _testMessage!.startsWith('✓')
                                  ? Colors.green
                                  : Colors.red,
                            ),
                          ),
                          child: Row(
                            children: [
                              Icon(
                                _testMessage!.startsWith('✓') ? AppleIcons.checkCircle : AppleIcons.error,
                                color: _testMessage!.startsWith('✓') ? Colors.green : Colors.red,
                                size: 20,
                              ),
                              SizedBox(width: ChatBoxTokens.spacing.sm),
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

                      SizedBox(height: ChatBoxTokens.spacing.lg),

                      // 模型列表（仅新建时）
                      if (!isEdit) ...[
                        AppleTextArea(
                          controller: _modelsController,
                          labelText: '模型列表（可选）',
                          hintText: 'gpt-4, gpt-3.5-turbo',
                          helperText: '多个模型用逗号分隔，留空则稍后手动添加',
                          minLines: 3,
                          maxLines: 5,
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),

            // 底部按钮
            Container(
              padding: EdgeInsets.all(ChatBoxTokens.spacing.lg + 4),
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
                  SizedBox(width: ChatBoxTokens.spacing.md),
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
