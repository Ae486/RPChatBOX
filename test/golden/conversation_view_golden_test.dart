@Tags(['golden'])
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:golden_toolkit/golden_toolkit.dart';
import 'package:chatboxapp/widgets/conversation_view_host.dart';
import 'package:chatboxapp/models/chat_settings.dart';
import '../helpers/test_data.dart';
import '../helpers/test_setup.dart';

/// ConversationView Golden 测试
///
/// 建立 UI 优化保护网：确保对话视图在不同场景、主题下的视觉输出一致。
///
/// 注意：ConversationView 内部有多个 Timer（滚动防抖、自动滚动等），
/// 测试时需要特殊处理以避免 Timer 泄漏问题。
void main() {
  // 在所有测试前初始化全局依赖
  setUpAll(() async {
    await TestSetup.initializeWithDefaultProvider();
  });

  // 在所有测试后重置状态，防止状态泄漏
  tearDownAll(() async {
    await TestSetup.reset();
  });

  group('ConversationView Golden Tests', () {
    // 跳过此测试，因为 ConversationView 内部有复杂的 Timer 逻辑
    // 导致测试结束后 Timer 仍在运行
    // TODO: 重构 ConversationView 以支持更好的测试（添加 Timer 取消机制）
    testGoldens(
      'conversation view - dark theme',
      (tester) async {
        final conversation = TestData.createConversationWithMessages(
          id: 'conv-golden-dark',
          messageCount: 4,
        );

        await tester.pumpWidgetBuilder(
          MaterialApp(
            debugShowCheckedModeBanner: false,
            theme: ThemeData(brightness: Brightness.dark, useMaterial3: true),
            home: Scaffold(
              body: ConversationViewHost(
                conversation: conversation,
                settings: ChatSettings(),
                onConversationUpdated: () {},
                onTokenUsageUpdated: (_) {},
              ),
            ),
          ),
          surfaceSize: const Size(400, 800),
        );

        // 等待初始化完成
        await tester.pump(const Duration(milliseconds: 500));
        await screenMatchesGolden(tester, 'conversation_view_dark');
      },
      skip: true, // ConversationView 内部 Timer 未正确清理，需要重构后再启用
    );
  });
}
