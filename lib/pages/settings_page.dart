// INPUT: 全局 ModelServiceManager + 图片缓存/持久化服务 + UI Tokens
// OUTPUT: SettingsPage - 设置与工具入口（外观/模型管理/缓存清理/调试入口）
// POS: UI 层 / Pages - 设置页

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

import '../adapters/ai_provider.dart';
import '../chat_ui/owui/components/owui_app_bar.dart';
import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/components/owui_dialog.dart';
import '../chat_ui/owui/components/owui_scaffold.dart';
import '../chat_ui/owui/components/owui_snack_bar.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../models/langfuse_settings.dart';
import '../pages/display_settings_page.dart';
import '../pages/longform_story_page.dart';
import '../pages/prestory_setup_page.dart';
import '../pages/model_services_page.dart';
import '../pages/mcp_servers_page.dart';
import '../pages/keyboard_test_page.dart';
import '../main.dart' show globalModelServiceManager, globalMcpClientService;
import '../services/backend_langfuse_service.dart';
import '../services/image_persistence_service.dart';

/// 设置页面
class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  static const String _backendEnabledKey = 'python_backend_enabled';

  final BackendLangfuseService _langfuseService = BackendLangfuseService();
  bool _isClearing = false;
  bool _backendEnabled = ProviderFactory.pythonBackendEnabled;
  String _backendStatus = '';
  bool _isCheckingBackend = false;
  bool _isLoadingLangfuse = false;
  bool _isSavingLangfuse = false;
  LangfuseSettingsStatus? _langfuseSettings;

  @override
  void initState() {
    super.initState();
    _loadBackendEnabled();
  }

  Future<void> _loadBackendEnabled() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getBool(_backendEnabledKey) ?? false;
    if (mounted) {
      setState(() {
        _backendEnabled = saved;
        ProviderFactory.pythonBackendEnabled = saved;
      });
      if (saved) {
        _checkBackendHealth();
        _loadLangfuseSettings();
      }
    }
  }

  Future<void> _saveBackendEnabled(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_backendEnabledKey, value);
  }

  /// 检测 Python 后端状态
  Future<void> _checkBackendHealth() async {
    setState(() => _isCheckingBackend = true);
    try {
      final dio = Dio(
        BaseOptions(
          connectTimeout: const Duration(seconds: 3),
          receiveTimeout: const Duration(seconds: 3),
        ),
      );
      final response = await dio.get('http://localhost:8765/api/health');
      if (response.statusCode == 200 && mounted) {
        final data = response.data as Map<String, dynamic>;
        setState(() {
          _backendStatus = 'v${data['version'] ?? '?'}';
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() => _backendStatus = '未运行');
      }
    } finally {
      if (mounted) setState(() => _isCheckingBackend = false);
    }
  }

  Future<void> _toggleBackend(bool value) async {
    setState(() {
      _backendEnabled = value;
      ProviderFactory.pythonBackendEnabled = value;
    });
    await _saveBackendEnabled(value);
    if (value) {
      await _checkBackendHealth();
      try {
        await globalModelServiceManager.refreshBackendMirrors();
        await globalMcpClientService.reload();
        await globalMcpClientService.start();
      } catch (e) {
        if (mounted) {
          OwuiSnackBars.warning(
            context,
            message: 'Backend 同步失败: ${e.toString()}',
          );
        }
      }
      await _loadLangfuseSettings();
    } else {
      await globalMcpClientService.reload();
      await globalMcpClientService.start();
      setState(() {
        _backendStatus = '';
        _langfuseSettings = null;
      });
    }
  }

  Future<void> _loadLangfuseSettings() async {
    if (!_backendEnabled) return;
    setState(() => _isLoadingLangfuse = true);
    try {
      final settings = await _langfuseService.getSettings();
      if (!mounted) return;
      setState(() {
        _langfuseSettings = settings;
      });
    } catch (e) {
      if (!mounted) return;
      OwuiSnackBars.warning(
        context,
        message: '读取 Langfuse 配置失败: ${e.toString()}',
      );
    } finally {
      if (mounted) {
        setState(() => _isLoadingLangfuse = false);
      }
    }
  }

  Future<void> _toggleLangfuse(bool value) async {
    final current = _langfuseSettings;
    if (current == null) {
      await _loadLangfuseSettings();
      return;
    }
    if (value && !current.configured) {
      await _openLangfuseConfigDialog(forceEnable: true);
      return;
    }
    await _saveLangfuseSettings(
      LangfuseSettingsUpdateRequest(
        enabled: value,
        publicKey: current.publicKey,
        baseUrl: current.baseUrl,
        environment: current.environment,
        release: current.release,
        sampleRate: current.sampleRate,
        debug: current.debug,
      ),
      successMessage: value ? 'Langfuse 监控已开启' : 'Langfuse 监控已关闭',
    );
  }

  Future<void> _saveLangfuseSettings(
    LangfuseSettingsUpdateRequest request, {
    required String successMessage,
  }) async {
    setState(() => _isSavingLangfuse = true);
    try {
      final settings = await _langfuseService.updateSettings(request);
      if (!mounted) return;
      setState(() {
        _langfuseSettings = settings;
      });
      OwuiSnackBars.success(context, message: successMessage);
    } catch (e) {
      if (!mounted) return;
      OwuiSnackBars.error(
        context,
        message: '保存 Langfuse 配置失败: ${e.toString()}',
      );
    } finally {
      if (mounted) {
        setState(() => _isSavingLangfuse = false);
      }
    }
  }

  Future<void> _openLangfuseConfigDialog({bool forceEnable = false}) async {
    final current = _langfuseSettings;
    if (current == null) return;
    final request = await showDialog<LangfuseSettingsUpdateRequest>(
      context: context,
      builder: (context) {
        final formKey = GlobalKey<FormState>();
        final baseUrlController = TextEditingController(
          text: current.baseUrl ?? '',
        );
        final publicKeyController = TextEditingController(
          text: current.publicKey ?? '',
        );
        final secretKeyController = TextEditingController();
        final environmentController = TextEditingController(
          text: current.environment ?? '',
        );
        final releaseController = TextEditingController(
          text: current.release ?? '',
        );
        final sampleRateController = TextEditingController(
          text: current.sampleRate?.toString() ?? '',
        );
        var enabled = forceEnable ? true : current.enabled;
        var debug = current.debug;
        var clearSecretKey = false;
        var obscureSecret = true;
        return StatefulBuilder(
          builder: (context, setDialogState) {
            return OwuiDialog(
              title: const Text('Langfuse 监控配置'),
              content: SizedBox(
                width: 520,
                child: Form(
                  key: formKey,
                  child: SingleChildScrollView(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('启用监控'),
                          subtitle: const Text(
                            '开启后 setup/eval trace 会写入 Langfuse',
                          ),
                          value: enabled,
                          onChanged: (value) {
                            setDialogState(() => enabled = value);
                          },
                        ),
                        TextFormField(
                          controller: baseUrlController,
                          decoration: const InputDecoration(
                            labelText: 'Base URL',
                            hintText: '留空则使用 https://cloud.langfuse.com',
                          ),
                          validator: (value) {
                            final text = (value ?? '').trim();
                            if (text.isEmpty) return null;
                            final uri = Uri.tryParse(text);
                            if (uri == null || !uri.isAbsolute) {
                              return 'Base URL 格式不正确';
                            }
                            return null;
                          },
                        ),
                        SizedBox(height: context.owuiSpacing.md),
                        TextFormField(
                          controller: publicKeyController,
                          decoration: const InputDecoration(
                            labelText: 'Public Key',
                            hintText: 'pk-lf-...',
                          ),
                        ),
                        SizedBox(height: context.owuiSpacing.md),
                        TextFormField(
                          controller: secretKeyController,
                          decoration: InputDecoration(
                            labelText: 'Secret Key',
                            hintText: current.hasSecretKey
                                ? '留空则保持当前秘钥'
                                : 'sk-lf-...',
                            suffixIcon: IconButton(
                              icon: Icon(
                                obscureSecret
                                    ? OwuiIcons.visibility
                                    : OwuiIcons.visibilityOff,
                                size: 18,
                              ),
                              onPressed: () {
                                setDialogState(
                                  () => obscureSecret = !obscureSecret,
                                );
                              },
                            ),
                          ),
                          obscureText: obscureSecret,
                        ),
                        if (current.hasSecretKey) ...[
                          SizedBox(height: context.owuiSpacing.sm),
                          CheckboxListTile(
                            contentPadding: EdgeInsets.zero,
                            value: clearSecretKey,
                            title: const Text('清空已保存的 Secret Key'),
                            onChanged: (value) {
                              setDialogState(
                                () => clearSecretKey = value ?? false,
                              );
                            },
                          ),
                        ],
                        SizedBox(height: context.owuiSpacing.md),
                        TextFormField(
                          controller: environmentController,
                          decoration: const InputDecoration(
                            labelText: 'Environment',
                            hintText: 'setup-eval',
                          ),
                        ),
                        SizedBox(height: context.owuiSpacing.md),
                        TextFormField(
                          controller: releaseController,
                          decoration: const InputDecoration(
                            labelText: 'Release',
                            hintText: 'local-dev',
                          ),
                        ),
                        SizedBox(height: context.owuiSpacing.md),
                        TextFormField(
                          controller: sampleRateController,
                          decoration: const InputDecoration(
                            labelText: 'Sample Rate',
                            hintText: '0.0 - 1.0',
                          ),
                          keyboardType: const TextInputType.numberWithOptions(
                            decimal: true,
                          ),
                          validator: (value) {
                            final text = (value ?? '').trim();
                            if (text.isEmpty) return null;
                            final parsed = double.tryParse(text);
                            if (parsed == null || parsed < 0 || parsed > 1) {
                              return '采样率必须是 0 到 1 之间的数字';
                            }
                            return null;
                          },
                        ),
                        SizedBox(height: context.owuiSpacing.md),
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          title: const Text('调试日志'),
                          subtitle: const Text('将 Langfuse SDK 运行在 debug 模式'),
                          value: debug,
                          onChanged: (value) {
                            setDialogState(() => debug = value);
                          },
                        ),
                        SizedBox(height: context.owuiSpacing.sm),
                        Text(
                          current.configPath != null
                              ? '配置将写入 ${current.configPath}'
                              : '首次保存后会写入 backend 本地 storage 目录',
                          style: TextStyle(
                            fontSize: 12,
                            color: context.owuiColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('取消'),
                ),
                FilledButton(
                  onPressed: () {
                    if (!formKey.currentState!.validate()) return;
                    final sampleRateText = sampleRateController.text.trim();
                    Navigator.of(context).pop(
                      LangfuseSettingsUpdateRequest(
                        enabled: enabled,
                        publicKey: publicKeyController.text.trim(),
                        secretKey: secretKeyController.text.trim().isEmpty
                            ? null
                            : secretKeyController.text.trim(),
                        clearSecretKey: clearSecretKey,
                        baseUrl: baseUrlController.text.trim().isEmpty
                            ? null
                            : baseUrlController.text.trim(),
                        environment: environmentController.text.trim(),
                        release: releaseController.text.trim(),
                        sampleRate: sampleRateText.isEmpty
                            ? null
                            : double.tryParse(sampleRateText),
                        debug: debug,
                      ),
                    );
                  },
                  child: const Text('保存'),
                ),
              ],
            );
          },
        );
      },
    );
    if (request == null) return;
    await _saveLangfuseSettings(request, successMessage: 'Langfuse 配置已保存');
  }

  Future<void> _openLangfuseDashboard() async {
    final url = _langfuseSettings?.dashboardUrl ?? _langfuseSettings?.baseUrl;
    if (url == null || url.trim().isEmpty) {
      if (!mounted) return;
      OwuiSnackBars.warning(context, message: '当前没有可打开的 WebUI 地址');
      return;
    }
    final uri = Uri.tryParse(url);
    if (uri == null) {
      if (!mounted) return;
      OwuiSnackBars.warning(context, message: 'WebUI 地址格式不正确');
      return;
    }
    final opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!opened && mounted) {
      OwuiSnackBars.warning(context, message: '无法打开 Langfuse WebUI');
    }
  }

  String _langfuseSubtitle() {
    if (!_backendEnabled) {
      return '需要先启用 Python 后端';
    }
    if (_isLoadingLangfuse) {
      return '正在读取配置...';
    }
    final settings = _langfuseSettings;
    if (settings == null) {
      return '未读取到 Langfuse 配置';
    }
    switch (settings.statusReason) {
      case 'active':
        return '已启用，trace 会写入 Langfuse';
      case 'missing_api_keys':
        return '已开启但缺少 API Key';
      case 'sdk_unavailable':
        return '已配置，但当前 backend 未安装 Langfuse SDK';
      case 'sdk_incompatible':
        return '已配置，但当前 backend 的 Langfuse SDK 版本过旧或接口不兼容';
      case 'client_init_failed':
        return '已配置，但 Langfuse 客户端初始化失败';
      case 'disabled':
      default:
        return settings.configured ? '已配置，当前关闭' : '未启用';
    }
  }

  /// 清除图片缓存
  Future<void> _clearImageCache() async {
    // 显示确认对话框
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => OwuiDialog(
        title: const Text('确认清除缓存'),
        content: const Text('确定要清除所有缓存的图片吗？此操作无法撤销。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('清除'),
          ),
        ],
      ),
    );

    if (confirmed != true || !mounted) return;

    setState(() {
      _isClearing = true;
    });

    try {
      // 清除 cached_network_image 的缓存
      await DefaultCacheManager().emptyCache();

      // 清理持久化图片中的陈旧文件
      await ImagePersistenceService().cleanupStaleFiles();

      // 清除 Flutter 的图片缓存
      PaintingBinding.instance.imageCache.clear();
      PaintingBinding.instance.imageCache.clearLiveImages();

      if (mounted) {
        OwuiSnackBars.success(context, message: '图片缓存已清除');
      }
    } catch (e) {
      if (mounted) {
        OwuiSnackBars.error(context, message: '清除缓存失败: ${e.toString()}');
      }
    } finally {
      if (mounted) {
        setState(() {
          _isClearing = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return OwuiScaffold(
      appBar: const OwuiAppBar(title: Text('设置')),
      body: ListView(
        padding: EdgeInsets.all(context.owuiSpacing.lg),
        children: [
          OwuiCard(
            child: ListTile(
              leading: const Icon(OwuiIcons.sliders, size: 32),
              title: const Text('显示设置'),
              subtitle: const Text('UI 缩放、字体与样式'),
              trailing: const Icon(OwuiIcons.chevronRight),
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const DisplaySettingsPage(),
                  ),
                );
              },
            ),
          ),
          SizedBox(height: context.owuiSpacing.lg),

          // 模型服务管理入口
          OwuiCard(
            child: ListTile(
              leading: const Icon(OwuiIcons.cloud, size: 32),
              title: const Text('模型服务'),
              subtitle: const Text('管理AI服务提供商和模型配置'),
              trailing: const Icon(OwuiIcons.chevronRight),
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => ModelServicesPage(
                      serviceManager: globalModelServiceManager,
                    ),
                  ),
                );
              },
            ),
          ),
          SizedBox(height: context.owuiSpacing.lg),

          // MCP 服务器管理入口
          OwuiCard(
            child: ListTile(
              leading: const Icon(OwuiIcons.tools, size: 32),
              title: const Text('MCP 服务器'),
              subtitle: const Text('管理工具服务器与扩展功能'),
              trailing: const Icon(OwuiIcons.chevronRight),
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) =>
                        McpServersPage(mcpService: globalMcpClientService),
                  ),
                );
              },
            ),
          ),
          SizedBox(height: context.owuiSpacing.lg),

          OwuiCard(
            child: ListTile(
              leading: const Icon(Icons.auto_awesome, size: 32),
              title: const Text('Prestory Setup'),
              subtitle: const Text(
                'SetupAgent MVP、review/commit 与 activation check',
              ),
              trailing: const Icon(OwuiIcons.chevronRight),
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const PrestorySetupPage(),
                  ),
                );
              },
            ),
          ),
          SizedBox(height: context.owuiSpacing.lg),

          OwuiCard(
            child: ListTile(
              leading: const Icon(Icons.menu_book_outlined, size: 32),
              title: const Text('Longform Stories'),
              subtitle: const Text('Active story session 列表与双栏 story shell'),
              trailing: const Icon(OwuiIcons.chevronRight),
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const LongformStoryPage(),
                  ),
                );
              },
            ),
          ),
          SizedBox(height: context.owuiSpacing.lg),

          // Python 后端路由
          OwuiCard(
            child: Column(
              children: [
                SwitchListTile(
                  secondary: Icon(
                    _backendEnabled ? OwuiIcons.link : OwuiIcons.linkOff,
                    size: 32,
                    color: _backendEnabled
                        ? Theme.of(context).colorScheme.primary
                        : null,
                  ),
                  title: const Text('Python 后端'),
                  subtitle: Text(
                    _backendEnabled
                        ? (_backendStatus.isNotEmpty
                              ? '已启用 ($_backendStatus)'
                              : '已启用')
                        : '直连 LLM API',
                  ),
                  value: _backendEnabled,
                  onChanged: (value) {
                    _toggleBackend(value);
                  },
                ),
                if (_backendEnabled) ...[
                  const Divider(height: 1),
                  ListTile(
                    dense: true,
                    leading: const SizedBox(width: 32),
                    title: const Text('后端地址'),
                    subtitle: const SelectableText('http://localhost:8765'),
                    trailing: _isCheckingBackend
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : IconButton(
                            icon: const Icon(OwuiIcons.refresh, size: 18),
                            onPressed: _checkBackendHealth,
                            tooltip: '检测连接',
                          ),
                  ),
                ],
              ],
            ),
          ),
          SizedBox(height: context.owuiSpacing.lg),

          if (_backendEnabled)
            OwuiCard(
              child: Column(
                children: [
                  SwitchListTile(
                    secondary: Icon(
                      (_langfuseSettings?.serviceEnabled ?? false)
                          ? OwuiIcons.signal
                          : OwuiIcons.linkOff,
                      size: 32,
                      color: (_langfuseSettings?.enabled ?? false)
                          ? Theme.of(context).colorScheme.primary
                          : null,
                    ),
                    title: const Text('Langfuse 监控'),
                    subtitle: Text(_langfuseSubtitle()),
                    value: _langfuseSettings?.enabled ?? false,
                    onChanged: _isLoadingLangfuse || _isSavingLangfuse
                        ? null
                        : _toggleLangfuse,
                  ),
                  const Divider(height: 1),
                  ListTile(
                    dense: true,
                    leading: const SizedBox(width: 32),
                    title: const Text('监控配置'),
                    subtitle: Text(
                      _langfuseSettings == null
                          ? '未加载'
                          : (_langfuseSettings!.configured
                                ? '已配置 ${_langfuseSettings!.publicKey ?? ''}'
                                : '尚未配置 API Key'),
                    ),
                    trailing: TextButton(
                      onPressed: _isSavingLangfuse
                          ? null
                          : _openLangfuseConfigDialog,
                      child: const Text('编辑'),
                    ),
                  ),
                  ListTile(
                    dense: true,
                    leading: const SizedBox(width: 32),
                    title: const Text('Langfuse WebUI'),
                    subtitle: SelectableText(
                      _langfuseSettings?.dashboardUrl ??
                          'https://cloud.langfuse.com',
                    ),
                    trailing: _isLoadingLangfuse
                        ? const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : IconButton(
                            icon: const Icon(OwuiIcons.openInNew, size: 18),
                            onPressed: _openLangfuseDashboard,
                            tooltip: '打开 WebUI',
                          ),
                  ),
                ],
              ),
            ),
          if (_backendEnabled) SizedBox(height: context.owuiSpacing.lg),

          // 缓存管理
          OwuiCard(
            child: ListTile(
              leading: const Icon(OwuiIcons.cleaning, size: 32),
              title: const Text('清除图片缓存'),
              subtitle: const Text('清除应用内所有缓存的图片数据'),
              trailing: _isClearing
                  ? SpinKitThreeBounce(
                      color: Theme.of(context).colorScheme.primary,
                      size: 16.0,
                    )
                  : const Icon(OwuiIcons.chevronRight),
              onTap: _isClearing ? null : _clearImageCache,
            ),
          ),
          SizedBox(height: context.owuiSpacing.lg),

          // 键盘动画测试（调试入口，仅 debug 模式可见）
          if (kDebugMode)
            OwuiCard(
              child: ListTile(
                leading: const Icon(OwuiIcons.play, size: 32),
                title: const Text('键盘动画测试'),
                subtitle: const Text('验证 flutter_chat_ui 键盘滚动行为'),
                trailing: const Icon(OwuiIcons.chevronRight),
                onTap: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(
                      builder: (context) => const KeyboardTestPage(),
                    ),
                  );
                },
              ),
            ),
          SizedBox(height: context.owuiSpacing.lg),

          // 关于信息
          OwuiCard(
            padding: EdgeInsets.all(context.owuiSpacing.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('关于', style: Theme.of(context).textTheme.titleMedium),
                SizedBox(height: context.owuiSpacing.sm),
                Text(
                  'ChatBox App\n版本 2.0.0\n\n支持多个AI服务提供商，包括OpenAI、Gemini、DeepSeek等。',
                  style: TextStyle(
                    fontSize: 14,
                    color: context.owuiColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
