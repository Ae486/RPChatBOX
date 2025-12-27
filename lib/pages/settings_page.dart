import 'package:flutter/material.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';

import '../chat_ui/owui/components/owui_app_bar.dart';
import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/components/owui_dialog.dart';
import '../chat_ui/owui/components/owui_scaffold.dart';
import '../chat_ui/owui/components/owui_snack_bar.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../pages/display_settings_page.dart';
import '../pages/model_services_page.dart';
import '../pages/flyer_chat_demo_page.dart';
import '../main.dart' show globalModelServiceManager;
import '../models/chat_settings.dart';
import '../services/storage_service.dart';

/// 设置页面
class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final _storageService = StorageService();

  ChatSettings _settings = ChatSettings();
  bool _isLoadingSettings = true;
  bool _isClearing = false;

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    final settings = await _storageService.loadSettings();
    if (!mounted) return;
    setState(() {
      _settings = settings;
      _isLoadingSettings = false;
    });
  }

  Future<void> _toggleChatUiV2(bool enabled) async {
    // Prevent flutter_chat_ui keyboard observer from hitting a deactivated context
    // when toggling V1/V2 while the keyboard is visible.
    FocusManager.instance.primaryFocus?.unfocus();
    await Future<void>.delayed(const Duration(milliseconds: 16));

    setState(() {
      _settings = _settings.copyWith(enableChatUiV2: enabled);
    });
    await _storageService.saveSettings(_settings);
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
              leading: const Icon(Icons.chat_bubble_outline, size: 32),
              title: const Text('Flyer Chat Demo'),
              subtitle: const Text('查看 flutter_chat_ui 默认风格效果'),
              trailing: const Icon(OwuiIcons.chevronRight),
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const FlyerChatDemoPage(),
                  ),
                );
              },
            ),
          ),
          SizedBox(height: context.owuiSpacing.lg),

          OwuiCard(
            child: SwitchListTile(
              secondary: const Icon(Icons.auto_awesome, size: 32),
              title: const Text('启用新聊天界面（V2）'),
              subtitle: const Text('flutter_chat_ui + 助手无气泡输出'),
              value: _settings.enableChatUiV2,
              onChanged: _isLoadingSettings ? null : _toggleChatUiV2,
            ),
          ),
          SizedBox(height: context.owuiSpacing.lg),

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
              leading: const Icon(Icons.cloud_outlined, size: 32),
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

          // 缓存管理
          OwuiCard(
            child: ListTile(
              leading: const Icon(Icons.cleaning_services_outlined, size: 32),
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
