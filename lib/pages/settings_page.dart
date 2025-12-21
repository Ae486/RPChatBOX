import 'package:flutter/material.dart';
import '../design_system/apple_icons.dart';
import 'package:flutter_cache_manager/flutter_cache_manager.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';
import '../pages/model_services_page.dart';
import '../pages/flyer_chat_demo_page.dart';
import '../main.dart' show globalModelServiceManager;
import '../design_system/design_tokens.dart';

/// 设置页面
class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  bool _isClearing = false;

  /// 清除图片缓存
  Future<void> _clearImageCache(BuildContext context) async {
    // 显示确认对话框
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
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
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('✅ 图片缓存已清除'),
            backgroundColor: Colors.green,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('❌ 清除缓存失败: ${e.toString()}'),
            backgroundColor: Colors.red,
          ),
        );
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
    return Scaffold(
      appBar: AppBar(
        title: const Text('设置'),
      ),
      body: ListView(
        padding: EdgeInsets.all(ChatBoxTokens.spacing.lg),
        children: [
          Card(
            child: ListTile(
              leading: const Icon(Icons.chat_bubble_outline, size: 32),
              title: const Text('Flyer Chat Demo'),
              subtitle: const Text('查看 flutter_chat_ui 默认风格效果'),
              trailing: const Icon(AppleIcons.arrowRight),
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
          SizedBox(height: ChatBoxTokens.spacing.lg),

          // 模型服务管理入口
          Card(
            child: ListTile(
              leading: const Icon(Icons.cloud_outlined, size: 32),
              title: const Text('模型服务'),
              subtitle: const Text('管理AI服务提供商和模型配置'),
              trailing: const Icon(AppleIcons.arrowRight),
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
          SizedBox(height: ChatBoxTokens.spacing.lg),

          // 缓存管理
          Card(
            child: ListTile(
              leading: const Icon(Icons.cleaning_services_outlined, size: 32),
              title: const Text('清除图片缓存'),
              subtitle: const Text('清除应用内所有缓存的图片数据'),
              trailing: _isClearing
                  ? SpinKitThreeBounce(
                      color: Theme.of(context).colorScheme.primary,
                      size: 16.0,
                    )
                  : const Icon(AppleIcons.arrowRight),
              onTap: _isClearing ? null : () => _clearImageCache(context),
            ),
          ),
          SizedBox(height: ChatBoxTokens.spacing.lg),

          // 关于信息
          Card(
            child: Padding(
              padding: EdgeInsets.all(ChatBoxTokens.spacing.lg),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '关于',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  SizedBox(height: ChatBoxTokens.spacing.sm),
                  const Text(
                    'ChatBox App\n版本 2.0.0\n\n支持多个AI服务提供商，包括OpenAI、Gemini、DeepSeek等。',
                    style: TextStyle(fontSize: 14, color: Colors.grey),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
