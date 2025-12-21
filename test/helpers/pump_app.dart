import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Widget 测试辅助扩展
/// 
/// 提供便捷的方法来在测试中渲染 Widget，自动包装 MaterialApp 和主题配置。
extension PumpApp on WidgetTester {
  /// 渲染一个 Widget，自动包装 MaterialApp
  /// 
  /// [widget] 要测试的 Widget
  /// [themeMode] 主题模式（light/dark/system），默认 light
  /// [locale] 语言环境，默认 Locale('zh', 'CN')
  /// 
  /// 示例:
  /// ```dart
  /// testWidgets('renders correctly', (tester) async {
  ///   await tester.pumpTestApp(MyWidget());
  ///   expect(find.byType(MyWidget), findsOneWidget);
  /// });
  /// ```
  Future<void> pumpTestApp(
    Widget widget, {
    ThemeMode themeMode = ThemeMode.light,
    Locale locale = const Locale('zh', 'CN'),
  }) async {
    await pumpWidget(
      MaterialApp(
        theme: ThemeData(
          brightness: Brightness.light,
          useMaterial3: true,
          colorScheme: ColorScheme.fromSeed(
            seedColor: Colors.blue,
            brightness: Brightness.light,
          ),
        ),
        darkTheme: ThemeData(
          brightness: Brightness.dark,
          useMaterial3: true,
          colorScheme: ColorScheme.fromSeed(
            seedColor: Colors.blue,
            brightness: Brightness.dark,
          ),
        ),
        themeMode: themeMode,
        locale: locale,
        home: Scaffold(
          body: widget,
        ),
      ),
    );
  }

  /// 渲染一个 Widget，使用亮色主题
  Future<void> pumpTestAppLight(Widget widget) async {
    await pumpTestApp(
      widget,
      themeMode: ThemeMode.light,
    );
  }

  /// 渲染一个 Widget，使用暗色主题
  Future<void> pumpTestAppDark(Widget widget) async {
    await pumpTestApp(
      widget,
      themeMode: ThemeMode.dark,
    );
  }

  /// 渲染一个页面级 Widget（不额外包装 Scaffold）
  /// 
  /// [page] 要测试的页面 Widget
  /// [themeMode] 主题模式，默认 light
  /// 
  /// 用于测试完整的页面组件，页面通常已包含 Scaffold
  Future<void> pumpTestPage(
    Widget page, {
    ThemeMode themeMode = ThemeMode.light,
  }) async {
    await pumpWidget(
      MaterialApp(
        theme: ThemeData(
          brightness: Brightness.light,
          useMaterial3: true,
        ),
        darkTheme: ThemeData(
          brightness: Brightness.dark,
          useMaterial3: true,
        ),
        themeMode: themeMode,
        home: page,
      ),
    );
  }

  /// 等待所有动画完成并稳定
  /// 
  /// 相当于 pump() + pumpAndSettle() 的组合
  Future<void> pumpAndStabilize({
    Duration duration = const Duration(milliseconds: 100),
  }) async {
    await pump(duration);
    await pumpAndSettle();
  }

  /// 点击并等待动画完成
  /// 
  /// [finder] 要点击的元素 Finder
  /// [settle] 是否等待动画完成，默认 true
  Future<void> tapAndSettle(
    Finder finder, {
    bool settle = true,
  }) async {
    await tap(finder);
    await pump();
    if (settle) {
      await pumpAndSettle();
    }
  }

  /// 输入文本并等待
  /// 
  /// [finder] TextField 的 Finder
  /// [text] 要输入的文本
  Future<void> enterTextAndSettle(
    Finder finder,
    String text,
  ) async {
    await enterText(finder, text);
    await pump();
    await pumpAndSettle();
  }

  /// 滚动到元素并等待
  /// 
  /// [finder] 要滚动到的元素
  /// [scrollable] 可滚动容器的 Finder
  Future<void> scrollToAndSettle(
    Finder finder, {
    Finder? scrollable,
  }) async {
    if (scrollable != null) {
      await scrollUntilVisible(
        finder,
        100,
        scrollable: scrollable,
      );
    }
    await pump();
    await pumpAndSettle();
  }
}

/// 测试主题辅助类
class TestThemes {
  /// 获取亮色主题
  static ThemeData get light => ThemeData(
        brightness: Brightness.light,
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.blue,
          brightness: Brightness.light,
        ),
      );

  /// 获取暗色主题
  static ThemeData get dark => ThemeData(
        brightness: Brightness.dark,
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.blue,
          brightness: Brightness.dark,
        ),
      );
}
