/// INPUT: ProviderConfig? + ModelServiceManager
/// OUTPUT: ProviderDetailPage - Provider 详情（API 配置 + 模型列表/编辑/添加）
/// POS: UI 层 / Pages - Provider 详情页

import 'package:flutter/material.dart';

import '../chat_ui/owui/components/owui_app_bar.dart';
import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/components/owui_dialog.dart';
import '../chat_ui/owui/components/owui_scaffold.dart';
import '../chat_ui/owui/components/owui_snack_bar.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../data/model_capability_presets.dart';
import '../models/model_config.dart';
import '../models/provider_config.dart';
import '../services/model_service_manager.dart';
import '../utils/api_url_helper.dart';
import '../utils/global_toast.dart';
import '../widgets/add_model_dialog.dart';
import 'model_edit_page.dart';

part 'provider_detail_page_breathing_card.dart';

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

  /// 获取实际使用的完整 API 地址预览
  String get _apiUrlPreview {
    final url = _apiUrlController.text.trim();
    if (url.isEmpty) return '未设置';
    return ApiUrlHelper.getActualApiUrl(url, _selectedType);
  }

  /// 判断是否显示 API 预览
  /// 当输入非空且预览与输入不同时显示（说明会有补全）
  bool _shouldShowApiPreview() {
    final url = _apiUrlController.text.trim();
    if (url.isEmpty) return false;
    return _apiUrlPreview != url;
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
        OwuiSnackBars.warning(context, message: '请先保存Provider配置');
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
      
      if (!mounted) return;
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
    final scheme = Theme.of(context).colorScheme;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => OwuiDialog(
        title: const Text('确认删除'),
        content: Text('确定要删除模型 "${model.displayName}" 吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: scheme.error),
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
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final scheme = Theme.of(context).colorScheme;

    return OwuiScaffold(
      appBar: OwuiAppBar(
        title: Text(isNewProvider ? '添加服务' : '编辑服务'),
        actions: [
          TextButton(
            onPressed: _save,
            child: const Text('保存'),
          ),
          SizedBox(width: spacing.sm),
        ],
      ),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: EdgeInsets.all(spacing.lg),
          children: [
            // 管理区
            _buildSection(
              title: '管理',
              child: Column(
                children: [
                  // 🆕 现代化服务商类型选择器
                  _buildModernTypeSelector(),
                  SizedBox(height: spacing.lg),

                  // 名称
                  TextFormField(
                    controller: _nameController,
                    decoration: const InputDecoration(
                      labelText: '名称',
                      hintText: '例如：OpenAI 官方',
                    ),
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return '请输入名称';
                      }
                      return null;
                    },
                  ),
                  SizedBox(height: spacing.lg),

                  // 🆕 API地址输入框（带预览）
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      TextFormField(
                        controller: _apiUrlController,
                        decoration: const InputDecoration(
                          labelText: 'API 地址',
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
                          final uri = Uri.tryParse(cleanValue);
                          if (cleanValue.isNotEmpty && (uri == null || !uri.isAbsolute)) {
                            return 'API地址格式不正确';
                          }
                          return null;
                        },
                      ),
                      // 🆕 实际使用地址预览（仅在支持补全时显示）
                      if (_shouldShowApiPreview()) ...[
                        SizedBox(height: spacing.sm),
                        Container(
                          padding: EdgeInsets.symmetric(
                            horizontal: spacing.md,
                            vertical: spacing.sm,
                          ),
                          decoration: BoxDecoration(
                            color: colors.surface2,
                            borderRadius: BorderRadius.circular(
                              context.owuiRadius.rLg,
                            ),
                            border: Border.all(color: colors.borderSubtle),
                          ),
                          child: Row(
                            children: [
                              Icon(
                                OwuiIcons.link,
                                size: 16,
                                color: scheme.primary,
                              ),
                              SizedBox(width: spacing.sm),
                              Expanded(
                                child: Text(
                                  _apiUrlPreview,
                                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                        fontWeight: FontWeight.w500,
                                        color: colors.textPrimary,
                                      ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ],
                  ),
                  SizedBox(height: spacing.lg),

                  // API密钥
                  TextFormField(
                    controller: _apiKeyController,
                    decoration: InputDecoration(
                      labelText: 'API 密钥',
                      hintText: 'sk-...',
                      // 🆕 添加显示/隐藏按钮
                      suffixIcon: IconButton(
                        icon: Icon(
                          _isApiKeyVisible
                              ? OwuiIcons.visibilityOff
                              : OwuiIcons.visibility,
                          size: 18,
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

            SizedBox(height: spacing.xl),

            // 模型区
            if (!isNewProvider) ...[
              _buildSection(
                title: '模型',
                trailing: TextButton.icon(
                  onPressed: _isTestingMode ? _exitTestMode : _enterTestMode,
                  icon: Icon(
                    _isTestingMode ? OwuiIcons.close : OwuiIcons.signal,
                  ),
                  label: Text(_isTestingMode ? '取消' : '检测'),
                ),
                child: Column(
                  children: [
                    // 模型列表
                    if (_models.isEmpty)
                      Padding(
                        padding: EdgeInsets.symmetric(vertical: spacing.xxl),
                        child: Text(
                          '暂无模型',
                          style: TextStyle(color: colors.textSecondary),
                        ),
                      )
                    else
                      ..._models.map((model) => _buildModelCard(model)),

                    SizedBox(height: spacing.md),

                    // 添加模型按钮
                    OutlinedButton.icon(
                      onPressed: _addModel,
                      icon: const Icon(OwuiIcons.add),
                      label: const Text('添加模型'),
                      style: OutlinedButton.styleFrom(
                        minimumSize: const Size(
                          double.infinity,
                          kMinInteractiveDimension,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ] else
              _buildInfoCallout('保存Provider后可添加模型'),
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
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final theme = Theme.of(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text(
              title,
              style: (theme.textTheme.titleMedium ?? const TextStyle()).copyWith(
                color: colors.textPrimary,
                fontWeight: FontWeight.w600,
              ),
            ),
            const Spacer(),
            if (trailing != null) trailing,
          ],
        ),
        SizedBox(height: spacing.md),
        OwuiCard(
          padding: EdgeInsets.all(spacing.lg),
          child: child,
        ),
      ],
    );
  }

  Widget _buildInfoCallout(String message) {
    final colors = context.owuiColors;
    final spacing = context.owuiSpacing;
    final scheme = Theme.of(context).colorScheme;

    return OwuiCard(
      padding: EdgeInsets.all(spacing.lg),
      child: Row(
        children: [
          Icon(OwuiIcons.info, size: 18, color: scheme.primary),
          SizedBox(width: spacing.md),
          Expanded(
            child: Text(
              message,
              style: (Theme.of(context).textTheme.bodyMedium ?? const TextStyle())
                  .copyWith(color: colors.textSecondary),
            ),
          ),
        ],
      ),
    );
  }

  /// 🆕 现代化下拉框选择器
  Widget _buildModernTypeSelector() {
    final spacing = context.owuiSpacing;
    final theme = Theme.of(context);

    return DropdownButtonFormField<ProviderType>(
      initialValue: _selectedType,
      decoration: InputDecoration(
        labelText: '服务商类型',
        contentPadding: EdgeInsets.symmetric(
          horizontal: spacing.md,
          vertical: spacing.sm,
        ),
      ),
      isExpanded: true,
      icon: const Icon(OwuiIcons.chevronDown, size: 18),
      items: ProviderType.values.map((type) {
        return DropdownMenuItem(
          value: type,
          child: Row(
            children: [
              Icon(_getProviderIcon(type), size: 18),
              SizedBox(width: spacing.md),
              Text(type.displayName, style: theme.textTheme.bodyMedium),
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
        return OwuiIcons.auto;
      case ProviderType.gemini:
        return OwuiIcons.star;
      case ProviderType.deepseek:
        return OwuiIcons.psychology;
      case ProviderType.claude:
        return OwuiIcons.chatBubble;
    }
  }

  /// Model卡片
  Widget _buildModelCard(ModelConfig model) {
    final isTestingThis = _testingModelId == model.id;
    final isInTestMode = _isTestingMode && !isTestingThis;

    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final scheme = Theme.of(context).colorScheme;
    final radius = context.owuiRadius.rXl;

    final actionButtonShape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
      side: BorderSide(color: colors.borderSubtle),
    );

    return _BreathingBorderCard(
      isBreathing: isInTestMode,
      margin: EdgeInsets.only(bottom: spacing.md),
      isSelected: isTestingThis,
      child: InkWell(
        onTap: _isTestingMode && !isTestingThis ? () => _testModel(model) : null,
        borderRadius: BorderRadius.circular(radius),
        child: Padding(
          padding: EdgeInsets.all(spacing.lg),
          child: Row(
            children: [
              // 模型名称和能力图标
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      model.displayName,
                      style: (Theme.of(context).textTheme.titleSmall ??
                              const TextStyle())
                          .copyWith(
                        fontWeight: FontWeight.w600,
                        color: colors.textPrimary,
                      ),
                    ),
                    SizedBox(height: spacing.sm),
                    Wrap(
                      spacing: spacing.sm,
                      runSpacing: spacing.xs,
                      children: model.capabilities
                          .where((cap) => cap != ModelCapability.text)
                          .map((cap) {
                        return Tooltip(
                          message: cap.displayName,
                          child: Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: spacing.sm,
                              vertical: spacing.xs,
                            ),
                            decoration: BoxDecoration(
                              color: cap.color.withValues(alpha: 0.12),
                              borderRadius: BorderRadius.circular(
                                context.owuiRadius.rLg / 2,
                              ),
                              border: Border.all(
                                color: cap.color.withValues(alpha: 0.3),
                                width: 0.5,
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(cap.icon, size: 14, color: cap.color),
                                SizedBox(width: spacing.xs),
                                Text(
                                  cap.displayName,
                                  style: (Theme.of(context).textTheme.bodySmall ??
                                          const TextStyle())
                                      .copyWith(
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

              if (!_isTestingMode) ...[
                IconButton(
                  icon: Icon(
                    OwuiIcons.settings,
                    size: 20,
                    color: colors.textSecondary,
                  ),
                  onPressed: () => _openModelSettings(model),
                  tooltip: '模型设置',
                  padding: EdgeInsets.all(spacing.sm),
                  constraints: const BoxConstraints(),
                  style: IconButton.styleFrom(
                    backgroundColor: colors.surface2,
                    shape: actionButtonShape,
                  ),
                ),
                SizedBox(width: spacing.sm),
                IconButton(
                  icon: Icon(
                    OwuiIcons.removeCircle,
                    size: 20,
                    color: scheme.error,
                  ),
                  onPressed: () => _deleteModel(model),
                  tooltip: '删除模型',
                  padding: EdgeInsets.all(spacing.sm),
                  constraints: const BoxConstraints(),
                  style: IconButton.styleFrom(
                    backgroundColor: colors.surface2,
                    shape: actionButtonShape,
                  ),
                ),
              ],

              if (_isTestingMode && !isTestingThis)
                Container(
                  padding: EdgeInsets.all(spacing.sm),
                  decoration: BoxDecoration(
                    color: colors.surface2,
                    borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
                    border: Border.all(color: colors.borderSubtle),
                  ),
                  child: Icon(
                    OwuiIcons.send,
                    color: scheme.primary,
                    size: 20,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
