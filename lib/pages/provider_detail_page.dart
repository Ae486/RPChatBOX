import 'package:flutter/material.dart';
import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../services/model_service_manager.dart';
import '../widgets/add_model_dialog.dart';
import '../utils/global_toast.dart';

/// Provider详情编辑页面
/// 包含管理区（服务商类型、名称、API配置）和模型区（模型列表、检测、添加）
class ProviderDetailPage extends StatefulWidget {
  final ProviderConfig? provider; // null表示新建
  final ModelServiceManager serviceManager;

  const ProviderDetailPage({
    super.key,
    this.provider,
    required this.serviceManager,
  });

  @override
  State<ProviderDetailPage> createState() => _ProviderDetailPageState();
}

class _ProviderDetailPageState extends State<ProviderDetailPage> {
  final _formKey = GlobalKey<FormState>();
  late TextEditingController _nameController;
  late TextEditingController _apiUrlController;
  late TextEditingController _apiKeyController;
  late ProviderType _selectedType;
  late bool _isEnabled;

  List<ModelConfig> _models = [];
  bool _isTestingMode = false; // 是否处于检测模式
  String? _testingModelId; // 当前正在测试的模型ID
  String? _testMessage; // 测试消息
  bool _isTestLoading = false; // 是否正在测试

  @override
  void initState() {
    super.initState();
    final provider = widget.provider;
    
    _nameController = TextEditingController(text: provider?.name ?? '');
    _apiUrlController = TextEditingController(text: provider?.apiUrl ?? '');
    _apiKeyController = TextEditingController(text: provider?.apiKey ?? '');
    _selectedType = provider?.type ?? ProviderType.openai;
    _isEnabled = provider?.isEnabled ?? true;

    if (provider != null) {
      _models = widget.serviceManager.getModelsByProvider(provider.id);
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _apiUrlController.dispose();
    _apiKeyController.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;

    final provider = widget.provider;
    final newProvider = ProviderConfig(
      id: provider?.id ?? widget.serviceManager.generateId(),
      name: _nameController.text.trim(),
      type: _selectedType,
      apiUrl: _apiUrlController.text.trim(),
      apiKey: _apiKeyController.text.trim(),
      isEnabled: _isEnabled,
    );

    if (provider == null) {
      await widget.serviceManager.addProvider(newProvider);
    } else {
      await widget.serviceManager.updateProvider(newProvider);
    }

    if (mounted) {
      Navigator.pop(context, newProvider);
    }
  }

  void _enterTestMode() {
    setState(() {
      _isTestingMode = true;
      _testingModelId = null;
    });
    // 🔧 使用全局提示框
    GlobalToast.showLoading(context, '请点击某个模型进行测试');
  }

  void _exitTestMode() {
    setState(() {
      _isTestingMode = false;
      _testingModelId = null;
    });
    // 🔧 隐藏全局提示框
    GlobalToast.hide();
  }

  Future<void> _testModel(ModelConfig model) async {
    if (_testingModelId != null) return; // 防止重复点击

    setState(() {
      _testingModelId = model.id;
      _isTestLoading = true;
    });
    
    // 🔧 使用全局提示框
    GlobalToast.showLoading(context, '正在测试 ${model.displayName}...');

    try {
      // 创建临时Provider配置用于测试
      final tempProvider = ProviderConfig(
        id: 'temp',
        name: _nameController.text.trim(),
        type: _selectedType,
        apiUrl: _apiUrlController.text.trim(),
        apiKey: _apiKeyController.text.trim(),
        isEnabled: true,
      );

      // 🔧 修复：使用所选模型进行测试，而不是只检测 Provider 连接
      final result = await widget.serviceManager.testProviderWithModel(
        tempProvider,
        model.modelName,
      );

      if (mounted) {
        setState(() {
          _isTestLoading = false;
        });

        // 🔧 使用全局提示框
        if (result.success) {
          GlobalToast.showSuccess(
            context,
            '✅ 测试成功\n响应时间: ${result.responseTimeMs}ms\n可用模型数: ${result.availableModels?.length ?? 0}',
          );
        } else {
          GlobalToast.showError(
            context,
            '❌ 测试失败\n${result.errorMessage}',
          );
        }

        // 3秒后自动退出测试模式
        Future.delayed(const Duration(seconds: 3), () {
          if (mounted && _testingModelId == model.id) {
            _exitTestMode();
          }
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isTestLoading = false;
        });
        // 🔧 使用全局提示框
        GlobalToast.showError(context, '❌ 测试失败\n${e.toString()}');
      }
    }
  }

  Future<void> _addModel() async {
    final modelId = await showDialog<String>(
      context: context,
      builder: (context) => const AddModelDialog(),
    );

    if (modelId != null && modelId.isNotEmpty) {
      final provider = widget.provider;
      if (provider == null) {
        // 新建Provider时暂存模型，保存Provider后再添加
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('请先保存Provider配置')),
          );
        }
        return;
      }

      final newModel = ModelConfig(
        id: widget.serviceManager.generateId(),
        providerId: provider.id,
        modelName: modelId,
        displayName: modelId,
        capabilities: {ModelCapability.text}, // 默认只有文本能力
      );

      await widget.serviceManager.addModel(newModel);
      
      setState(() {
        _models = widget.serviceManager.getModelsByProvider(provider.id);
      });

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('已添加模型: $modelId')),
        );
      }
    }
  }

  Future<void> _toggleModel(ModelConfig model) async {
    final updated = model.copyWith(isEnabled: !model.isEnabled);
    await widget.serviceManager.updateModel(updated);
    setState(() {
      _models = widget.serviceManager.getModelsByProvider(widget.provider!.id);
    });
  }

  @override
  Widget build(BuildContext context) {
    final isNewProvider = widget.provider == null;

    return Scaffold(
      appBar: AppBar(
        title: Text(isNewProvider ? '添加服务' : '编辑服务'),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        actions: [
          TextButton(
            onPressed: _save,
            child: const Text('保存', style: TextStyle(fontSize: 16)),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            // 🔧 移除页面内提示框，改用全局浮动提示框

            // 管理区
            _buildSection(
              title: '管理',
              child: Column(
                children: [
                  // 服务商类型下拉
                  DropdownButtonFormField<ProviderType>(
                    initialValue: _selectedType,
                    decoration: const InputDecoration(
                      labelText: '服务商类型',
                      border: OutlineInputBorder(),
                    ),
                    isExpanded: true, // 🔧 修复：让下拉框占满容器宽度
                    items: ProviderType.values.map((type) {
                      return DropdownMenuItem(
                        value: type,
                        child: Text(type.displayName),
                      );
                    }).toList(),
                    onChanged: (value) {
                      if (value != null) {
                        setState(() => _selectedType = value);
                      }
                    },
                  ),
                  const SizedBox(height: 16),

                  // 名称
                  TextFormField(
                    controller: _nameController,
                    decoration: const InputDecoration(
                      labelText: '名称',
                      border: OutlineInputBorder(),
                      hintText: '例如：OpenAI 官方',
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
                    decoration: const InputDecoration(
                      labelText: 'API 地址',
                      border: OutlineInputBorder(),
                      hintText: 'https://api.openai.com/v1',
                    ),
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return '请输入API地址';
                      }
                      if (!Uri.tryParse(value)!.isAbsolute) {
                        return 'API地址格式不正确';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),

                  // API密钥
                  TextFormField(
                    controller: _apiKeyController,
                    decoration: const InputDecoration(
                      labelText: 'API 密钥',
                      border: OutlineInputBorder(),
                      hintText: 'sk-...',
                    ),
                    obscureText: true,
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return '请输入API密钥';
                      }
                      return null;
                    },
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),

            // 模型区
            if (!isNewProvider) ...[
              _buildSection(
                title: '模型',
                trailing: TextButton.icon(
                  onPressed: _isTestingMode ? _exitTestMode : _enterTestMode,
                  icon: Icon(_isTestingMode ? Icons.close : Icons.wifi_tethering),
                  label: Text(_isTestingMode ? '取消' : '检测'),
                ),
                child: Column(
                  children: [
                    // 模型列表
                    if (_models.isEmpty)
                      Container(
                        padding: const EdgeInsets.all(32),
                        alignment: Alignment.center,
                        child: Text(
                          '暂无模型',
                          style: TextStyle(color: Colors.grey.shade600),
                        ),
                      )
                    else
                      ..._models.map((model) => _buildModelCard(model)),

                    const SizedBox(height: 12),

                    // 添加模型按钮
                    OutlinedButton.icon(
                      onPressed: _addModel,
                      icon: const Icon(Icons.add),
                      label: const Text('添加模型'),
                      style: OutlinedButton.styleFrom(
                        minimumSize: const Size(double.infinity, 48),
                      ),
                    ),
                  ],
                ),
              ),
            ] else
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: Colors.blue.shade50,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.blue.shade200),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.info_outline, color: Colors.blue),
                    SizedBox(width: 12),
                    Expanded(
                      child: Text(
                        '保存Provider后可添加模型',
                        style: TextStyle(color: Colors.blue),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildSection({
    required String title,
    required Widget child,
    Widget? trailing,
  }) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              title,
              style: Theme.of(context).textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
            ),
            const Spacer(),
            if (trailing != null) trailing,
          ],
        ),
        const SizedBox(height: 16),
        child,
      ],
    );
  }

  Widget _buildModelCard(ModelConfig model) {
    final isTestingThis = _testingModelId == model.id;
    final isInTestMode = _isTestingMode && !isTestingThis;

    return _BreathingBorderCard(
      isBreathing: isInTestMode,
      margin: const EdgeInsets.only(bottom: 12),
      isSelected: isTestingThis,
      child: InkWell(
        onTap: _isTestingMode && !isTestingThis ? () => _testModel(model) : null,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              // 模型名称和能力图标
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      model.displayName,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            fontWeight: FontWeight.w500,
                          ),
                    ),
                    const SizedBox(height: 8),
                    // 🔧 修复：移除图标旋转动画
                    Wrap(
                      spacing: 6,
                      children: model.capabilities.map((cap) {
                        return Tooltip(
                          message: cap.displayName,
                          child: Container(
                            padding: const EdgeInsets.all(4),
                            decoration: BoxDecoration(
                              color: cap.color.withValues(alpha: 0.1),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Icon(
                              cap.icon,
                              size: 14,
                              color: cap.color,
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                  ],
                ),
              ),

              // 开关
              if (!_isTestingMode)
                Switch(
                  value: model.isEnabled,
                  onChanged: (_) => _toggleModel(model),
                ),

              // 测试模式下的箭头
              if (_isTestingMode && !isTestingThis)
                const Icon(Icons.touch_app, color: Colors.blue, size: 20),
            ],
          ),
        ),
      ),
    );
  }
}

/// 🔧 呼吸边框卡片组件
class _BreathingBorderCard extends StatefulWidget {
  final Widget child;
  final EdgeInsetsGeometry margin;
  final bool isBreathing;
  final bool isSelected;

  const _BreathingBorderCard({
    required this.child,
    required this.margin,
    required this.isBreathing,
    required this.isSelected,
  });

  @override
  State<_BreathingBorderCard> createState() => _BreathingBorderCardState();
}

class _BreathingBorderCardState extends State<_BreathingBorderCard>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _animation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    );

    _animation = Tween<double>(begin: 0.3, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeInOut),
    );

    if (widget.isBreathing) {
      _controller.repeat(reverse: true);
    }
  }

  @override
  void didUpdateWidget(_BreathingBorderCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isBreathing && !oldWidget.isBreathing) {
      _controller.repeat(reverse: true);
    } else if (!widget.isBreathing && oldWidget.isBreathing) {
      _controller.stop();
      _controller.value = 1.0;
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _animation,
      builder: (context, child) {
        return Container(
          margin: widget.margin,
          decoration: BoxDecoration(
            color: Colors.grey.shade50,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(
              color: widget.isSelected
                  ? Colors.blue
                  : (widget.isBreathing
                      ? Colors.blue.withValues(alpha: _animation.value)
                      : Colors.grey.shade200),
              width: widget.isSelected ? 2 : 1,
            ),
            boxShadow: widget.isBreathing
                ? [
                    BoxShadow(
                      color: Colors.blue.withValues(alpha: _animation.value * 0.3),
                      blurRadius: 8,
                      spreadRadius: 1,
                    )
                  ]
                : null,
          ),
          child: child,
        );
      },
      child: widget.child,
    );
  }
}
