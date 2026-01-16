/// INPUT: 全局 ModelServiceManager + 图片缓存/持久化服务 + UI Tokens
/// OUTPUT: SettingsPage - 设置与工具入口（外观/模型管理/缓存清理/调试入口）
/// POS: UI 层 / Pages - 设置页

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
import '../main.dart' show globalModelServiceManager;
import '../services/image_persistence_service.dart';

/// 设置页面
class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  bool _isClearing = false;

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
