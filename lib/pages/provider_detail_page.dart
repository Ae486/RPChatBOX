import 'package:flutter/material.dart';
import '../models/provider_config.dart';
import '../models/model_config.dart';
import '../services/model_service_manager.dart';
import '../widgets/add_model_dialog.dart';
import '../utils/global_toast.dart';
import '../design_system/design_tokens.dart';
import '../design_system/apple_tokens.dart';
import '../design_system/apple_icons.dart';
import '../data/model_capability_presets.dart';
import 'model_edit_page.dart';

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
  bool _isApiKeyVisible = false; // 🆕 API密钥是否可见

  List<ModelConfig> _models = [];
  bool _isTestingMode = false; // 是否处于检测模式
  String? _testingModelId; // 当前正在测试的模型ID

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

  /// 🆕 获取实际使用的API地址预览
  String get _apiUrlPreview {
    final url = _apiUrlController.text.trim();
    if (url.isEmpty) return '未设置';
    // 自动补全 /v1 后缀
    if (_selectedType == ProviderType.openai || _selectedType == ProviderType.claude) {
      if (!url.endsWith('/v1') && !url.contains('/v1/')) {
        return '$url/v1';
      }
    }
    return url;
  }

  /// 🆕 判断是否显示API预览（仅支持补全的服务商类型）
  bool _shouldShowApiPreview() {
    // 只有 OpenAI 和 Claude 类型支持补全
    return _selectedType == ProviderType.openai || _selectedType == ProviderType.claude;
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
        // 🔧 使用全局提示框
        if (result.success) {
          GlobalToast.showSuccess(
            context,
            '响应时间: ${result.responseTimeMs}ms',
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
          _testingModelId = null;
        });
        // 🔧 使用全局提示框
        GlobalToast.showError(context, '❌ 测试失败\n${e.toString()}');
      }
    }
  }

  Future<void> _addModel() async {
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

    final result = await showDialog<String>(
      context: context,
      builder: (context) => AddModelDialog(provider: provider),
    );

    if (result != null && result.isNotEmpty) {
      // 🆕 支持批量添加：用逗号分隔的模型ID列表
      final modelIds = result.split(',').map((id) => id.trim()).where((id) => id.isNotEmpty).toList();
      
      if (modelIds.isEmpty) return;
      
      for (final modelId in modelIds) {
        // 🆕 使用预设能力数据库自动识别模型能力
        final presetCapabilities = ModelCapabilityPresets.getCapabilities(modelId);
        
        final newModel = ModelConfig(
          id: widget.serviceManager.generateId(),
          providerId: provider.id,
          modelName: modelId,
          displayName: modelId,
          capabilities: presetCapabilities,
        );

        await widget.serviceManager.addModel(newModel);
      }
      
      setState(() {
        _models = widget.serviceManager.getModelsByProvider(provider.id);
      });

      if (mounted) {
        if (modelIds.length == 1) {
          GlobalToast.showSuccess(context, '已添加模型: ${modelIds[0]}');
        } else {
          GlobalToast.showSuccess(context, '已批量添加 ${modelIds.length} 个模型');
        }
      }
    }
  }

  /// 🆕 打开模型设置页面
  Future<void> _openModelSettings(ModelConfig model) async {
    final result = await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => ModelEditPage(
          model: model,
          serviceManager: widget.serviceManager,
        ),
      ),
    );

    // 如果有更新，刷新模型列表
    if (result != null && mounted) {
      setState(() {
        _models = widget.serviceManager.getModelsByProvider(widget.provider!.id);
      });
    }
  }

  /// 🆕 删除模型
  Future<void> _deleteModel(ModelConfig model) async {
    // 🚧 TODO: 第四批 - 实现确认对话框
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('确认删除'),
        content: Text('确定要删除模型 "${model.displayName}" 吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('删除'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      await widget.serviceManager.deleteModel(model.id);
      setState(() {
        _models = widget.serviceManager.getModelsByProvider(widget.provider!.id);
      });
      if (mounted) {
        GlobalToast.showSuccess(context, '已删除模型: ${model.displayName}');
      }
    }
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
          SizedBox(width: ChatBoxTokens.spacing.sm),
        ],
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: EdgeInsets.all(ChatBoxTokens.spacing.lg),
          children: [
            // 🔧 移除页面内提示框，改用全局浮动提示框

            // 管理区
            _buildSection(
              title: '管理',
              child: Column(
                children: [
                  // 🆕 现代化服务商类型选择器
                  _buildModernTypeSelector(),
                  SizedBox(height: ChatBoxTokens.spacing.lg),

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
                  SizedBox(height: ChatBoxTokens.spacing.lg),

                  // 🆕 API地址输入框（带预览）
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      TextFormField(
                        controller: _apiUrlController,
                        decoration: const InputDecoration(
                          labelText: 'API 地址',
                          border: OutlineInputBorder(),
                          hintText: 'https://api.openai.com/v1',
                          helperText: '结尾添加 "/" 忽略v1版本，"#" 强制使用输入地址',
                        ),
                        onChanged: (_) => setState(() {}), // 🔧 更新预览
                        validator: (value) {
                          if (value == null || value.trim().isEmpty) {
                            return '请输入API地址';
                          }
                          // 🔧 移除#和/后验证
                          final cleanValue = value.trim().replaceAll(RegExp(r'[#/]+$'), '');
                          if (cleanValue.isNotEmpty && !Uri.tryParse(cleanValue)!.isAbsolute) {
                            return 'API地址格式不正确';
                          }
                          return null;
                        },
                      ),
                      // 🆕 实际使用地址预览（仅在支持补全时显示）
                      if (_shouldShowApiPreview()) ...[
                        SizedBox(height: ChatBoxTokens.spacing.sm),
                        Container(
                          padding: EdgeInsets.symmetric(
                            horizontal: ChatBoxTokens.spacing.md,
                            vertical: ChatBoxTokens.spacing.sm,
                          ),
                          decoration: BoxDecoration(
                            color: Theme.of(context).colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
                            borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
                            border: Border.all(
                              color: Theme.of(context).colorScheme.outline.withValues(alpha: 0.3),
                            ),
                          ),
                          child: Row(
                            children: [
                              Icon(
                                Icons.link,
                                size: 16,
                                color: Theme.of(context).colorScheme.primary,
                              ),
                              SizedBox(width: ChatBoxTokens.spacing.sm),
                              Expanded(
                                child: Text(
                                  _apiUrlPreview,
                                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ],
                  ),
                  SizedBox(height: ChatBoxTokens.spacing.lg),

                  // API密钥
                  TextFormField(
                    controller: _apiKeyController,
                    decoration: InputDecoration(
                      labelText: 'API 密钥',
                      border: const OutlineInputBorder(),
                      hintText: 'sk-...',
                      // 🆕 添加显示/隐藏按钮
                      suffixIcon: IconButton(
                        icon: Icon(
                          _isApiKeyVisible ? Icons.visibility_off : Icons.visibility,
                          size: 20,
                        ),
                        onPressed: () {
                          setState(() {
                            _isApiKeyVisible = !_isApiKeyVisible;
                          });
                        },
                        tooltip: _isApiKeyVisible ? '隐藏密钥' : '显示密钥',
                      ),
                    ),
                    obscureText: !_isApiKeyVisible, // 🔧 根据状态切换
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

            SizedBox(height: ChatBoxTokens.spacing.xl),

            // 模型区
            if (!isNewProvider) ...[
              _buildSection(
                title: '模型',
                trailing: TextButton.icon(
                  onPressed: _isTestingMode ? _exitTestMode : _enterTestMode,
                  icon: Icon(_isTestingMode ? AppleIcons.close : Icons.wifi_tethering),
                  label: Text(_isTestingMode ? '取消' : '检测'),
                ),
                child: Column(
                  children: [
                    // 模型列表
                    if (_models.isEmpty)
                      Container(
                        padding: EdgeInsets.all(ChatBoxTokens.spacing.xl + 8),
                        alignment: Alignment.center,
                        child: Text(
                          '暂无模型',
                          style: TextStyle(color: Colors.grey.shade600),
                        ),
                      )
                    else
                      ..._models.map((model) => _buildModelCard(model)),

                    SizedBox(height: ChatBoxTokens.spacing.md),

                    // 添加模型按钮
                    OutlinedButton.icon(
                      onPressed: _addModel,
                      icon: const Icon(AppleIcons.add),
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
                padding: EdgeInsets.all(ChatBoxTokens.spacing.lg),
                decoration: BoxDecoration(
                  color: Colors.blue.shade50,
                  borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
                  border: Border.all(color: Colors.blue.shade200),
                ),
                child: const Row(
                  children: [
                    Icon(AppleIcons.info, color: Colors.blue),
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
        SizedBox(height: ChatBoxTokens.spacing.lg),
        child,
      ],
    );
  }

  /// 🆕 现代化下拉框选择器
  Widget _buildModernTypeSelector() {
    return DropdownButtonFormField<ProviderType>(
      initialValue: _selectedType,
      decoration: const InputDecoration(
        labelText: '服务商类型',
        border: OutlineInputBorder(),
        contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      ),
      isExpanded: true,
      icon: const Icon(Icons.arrow_drop_down, size: 24),
      items: ProviderType.values.map((type) {
        return DropdownMenuItem(
          value: type,
          child: Row(
            children: [
              Icon(
                _getProviderIcon(type),
                size: 20,
              ),
              SizedBox(width: ChatBoxTokens.spacing.md),
              Text(
                type.displayName,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w400,
                ),
              ),
            ],
          ),
        );
      }).toList(),
      onChanged: (value) {
        if (value != null) {
          setState(() {
            _selectedType = value;
          });
        }
      },
    );
  }

  /// 🆕 获取Provider图标
  IconData _getProviderIcon(ProviderType type) {
    switch (type) {
      case ProviderType.openai:
        return Icons.auto_awesome;
      case ProviderType.gemini:
        return Icons.stars;
      case ProviderType.deepseek:
        return Icons.psychology;
      case ProviderType.claude:
        return Icons.chat_bubble_outline;
    }
  }

  /// Model卡片 - Apple风格
  Widget _buildModelCard(ModelConfig model) {
    final isTestingThis = _testingModelId == model.id;
    final isInTestMode = _isTestingMode && !isTestingThis;

    return _BreathingBorderCard(
      isBreathing: isInTestMode,
      margin: EdgeInsets.only(bottom: ChatBoxTokens.spacing.md),
      isSelected: isTestingThis,
      child: InkWell(
        onTap: _isTestingMode && !isTestingThis ? () => _testModel(model) : null,
        borderRadius: BorderRadius.circular(12), // Apple圆角
        child: Padding(
          padding: EdgeInsets.all(ChatBoxTokens.spacing.lg),
          child: Row(
            children: [
              // 模型名称和能力图标
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // 模型名称 - Apple字体
                    Text(
                      model.displayName,
                      style: AppleTokens.typography.body.copyWith(
                        fontWeight: FontWeight.w600,
                        fontSize: 16,
                      ),
                    ),
                    SizedBox(height: ChatBoxTokens.spacing.sm),
                    // 能力图标 - 优化样式
                    Wrap(
                      spacing: 8,
                      runSpacing: 6,
                      children: model.capabilities
                          .where((cap) => cap != ModelCapability.text)
                          .map((cap) {
                        return Tooltip(
                          message: cap.displayName,
                          child: Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: cap.color.withValues(alpha: 0.12),
                              borderRadius: BorderRadius.circular(6), // 更圆润
                              border: Border.all(
                                color: cap.color.withValues(alpha: 0.3),
                                width: 0.5,
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  cap.icon,
                                  size: 14,
                                  color: cap.color,
                                ),
                                SizedBox(width: 4),
                                Text(
                                  cap.displayName,
                                  style: AppleTokens.typography.caption2.copyWith(
                                    color: cap.color,
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      }).toList(),
                    ),
                  ],
                ),
              ),

              // 设置和删除按钮 - Apple风格
              if (!_isTestingMode) ...[
                IconButton(
                  icon: Icon(
                    AppleIcons.settings,
                    size: 22,
                    color: AppleColors.secondaryLabel(context),
                  ),
                  onPressed: () => _openModelSettings(model),
                  tooltip: '模型设置',
                  padding: EdgeInsets.all(8),
                  constraints: const BoxConstraints(),
                  style: IconButton.styleFrom(
                    backgroundColor: Theme.of(context).cardColor,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                ),
                SizedBox(width: ChatBoxTokens.spacing.sm),
                IconButton(
                  icon: Icon(
                    AppleIcons.removeCircle,
                    size: 22,
                    color: AppleColors.red,
                  ),
                  onPressed: () => _deleteModel(model),
                  tooltip: '删除模型',
                  padding: EdgeInsets.all(8),
                  constraints: const BoxConstraints(),
                  style: IconButton.styleFrom(
                    backgroundColor: AppleColors.red.withValues(alpha: 0.1),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8),
                    ),
                  ),
                ),
              ],

              // 测试模式下的箭头
              if (_isTestingMode && !isTestingThis)
                Container(
                  padding: EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AppleColors.blue.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(
                    AppleIcons.send,
                    color: AppleColors.blue,
                    size: 22,
                  ),
                ),
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
    final theme = Theme.of(context);
    final primaryColor = AppleColors.blue;

    return AnimatedBuilder(
      animation: _animation,
      builder: (context, child) {
        return Container(
          margin: widget.margin,
          decoration: BoxDecoration(
            color: theme.cardColor,
            borderRadius: BorderRadius.circular(12), // Apple圆角
            border: Border.all(
              color: widget.isSelected
                  ? primaryColor
                  : (widget.isBreathing
                      ? primaryColor.withValues(alpha: _animation.value * 0.6)
                      : AppleColors.separator(context)),
              width: widget.isSelected ? 2 : 0.5,
            ),
            boxShadow: widget.isSelected
                ? [
                    // 选中状态：Apple蓝色阴影
                    BoxShadow(
                      color: primaryColor.withValues(alpha: 0.2),
                      blurRadius: 12,
                      offset: Offset(0, 4),
                    ),
                    BoxShadow(
                      color: primaryColor.withValues(alpha: 0.1),
                      blurRadius: 24,
                      offset: Offset(0, 8),
                    ),
                  ]
                : widget.isBreathing
                    ? [
                        // 呼吸状态：动态阴影
                        BoxShadow(
                          color: primaryColor.withValues(alpha: _animation.value * 0.15),
                          blurRadius: 12 * _animation.value,
                          offset: Offset(0, 4 * _animation.value),
                        ),
                      ]
                    : AppleTokens.shadows.card, // 默认：Apple卡片阴影
          ),
          child: child,
        );
      },
      child: widget.child,
    );
  }
}
