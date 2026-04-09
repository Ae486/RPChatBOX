import 'dart:async';
import 'dart:io';
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:provider/provider.dart';

import 'chat_ui/owui/owui_tokens.dart';
import 'pages/chat_page.dart';
import 'providers/chat_session_provider.dart';
import 'services/backend_lifecycle_service.dart';
import 'services/data_migration_service.dart';
import 'services/hive_conversation_service.dart';
import 'services/model_service_manager.dart';
import 'services/mcp_client_service.dart';
import 'adapters/ai_provider.dart';

// 全局ModelServiceManager实例
late ModelServiceManager globalModelServiceManager;

// 全局McpClientService实例
late McpClientService globalMcpClientService;

const _prefsThemeModeKey = 'theme_mode';
const _prefsUiScaleKey = 'ui_scale';
const _prefsUiFontFamilyKey = 'ui_font_family';
const _prefsUiCodeFontFamilyKey = 'ui_code_font_family';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // 初始化 Hive（必须在所有服务初始化之前）
  await Hive.initFlutter();

  // 初始化 WebView 平台（Windows/Android）
  if (Platform.isWindows) {
    // Windows 平台 WebView 初始化会在第一次使用时自动完成
    // 无需手动初始化
  } else if (Platform.isAndroid) {
    // Android 平台也会自动初始化
  }

  final prefs = await SharedPreferences.getInstance();

  // 恢复 Python 后端开关状态
  ProviderFactory.pythonBackendEnabled =
      prefs.getBool('python_backend_enabled') ?? false;

  // 执行数据迁移（如果需要）
  final migrationService = DataMigrationService();
  if (await migrationService.needsMigration()) {
    try {
      await migrationService.migrate();
    } catch (e) {
      debugPrint('⚠️ 数据迁移失败，将继续使用旧数据: $e');
    }
  }

  // 初始化ModelServiceManager
  globalModelServiceManager = ModelServiceManager(prefs);
  await globalModelServiceManager.initialize();

  // 初始化McpClientService
  globalMcpClientService = McpClientService();
  await globalMcpClientService.initialize();

  // 自动连接已启用的 MCP 服务器（非阻塞）
  unawaited(globalMcpClientService.start());

  // 启动 Python 后端（桌面端 + 移动端）
  if (!kIsWeb) {
    _startBackendSilently();
  }

  final themeMode = prefs.getString(_prefsThemeModeKey) ?? 'system';
  final uiScale = prefs.getDouble(_prefsUiScaleKey) ?? 1.0;
  final uiFontFamily = prefs.getString(_prefsUiFontFamilyKey) ?? 'system';
  final uiCodeFontFamily =
      prefs.getString(_prefsUiCodeFontFamilyKey) ?? 'system_mono';

  runApp(
    MyApp(
      initialThemeMode: themeMode,
      initialUiScale: uiScale,
      initialUiFontFamily: uiFontFamily,
      initialUiCodeFontFamily: uiCodeFontFamily,
    ),
  );
}

/// Start backend silently, non-blocking.
/// Failures are logged but don't prevent app startup.
void _startBackendSilently() {
  Future(() async {
    try {
      final backend = BackendLifecycleService.instance;
      await backend.start();
      debugPrint('Backend started: ${backend.baseUrl}');
    } catch (e) {
      debugPrint('Backend startup failed (will use direct mode): $e');
    }
  });
}

class MyApp extends StatefulWidget {
  final String initialThemeMode;
  final double initialUiScale;
  final String initialUiFontFamily;
  final String initialUiCodeFontFamily;

  const MyApp({
    super.key,
    required this.initialThemeMode,
    required this.initialUiScale,
    required this.initialUiFontFamily,
    required this.initialUiCodeFontFamily,
  });

  @override
  State<MyApp> createState() => MyAppState();

  static MyAppState? of(BuildContext context) =>
      context.findAncestorStateOfType<MyAppState>();
}

class MyAppState extends State<MyApp> with WidgetsBindingObserver {
  late ThemeMode _themeMode;
  late double _uiScale;
  late String _uiFontFamily;
  late String _uiCodeFontFamily;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _themeMode = _themeModeFromString(widget.initialThemeMode);
    _uiScale = _clampUiScale(widget.initialUiScale);
    _uiFontFamily = widget.initialUiFontFamily;
    _uiCodeFontFamily = widget.initialUiCodeFontFamily;
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    // Stop backend on app dispose
    if (!kIsWeb) {
      BackendLifecycleService.instance.dispose();
    }
    super.dispose();
  }

  @override
  Future<AppExitResponse> didRequestAppExit() async {
    // Graceful backend shutdown on app exit
    if (!kIsWeb) {
      try {
        await BackendLifecycleService.instance.stop();
      } catch (_) {}
    }
    return AppExitResponse.exit;
  }

  ThemeMode _themeModeFromString(String mode) {
    switch (mode) {
      case 'light':
        return ThemeMode.light;
      case 'dark':
        return ThemeMode.dark;
      default:
        return ThemeMode.system;
    }
  }

  double _clampUiScale(double value) => value.clamp(0.85, 1.25).toDouble();

  String? _resolveUiFontFamily(String id) {
    switch (id) {
      case 'noto_sans':
        return 'NotoSans';
      case 'noto_serif':
        return 'NotoSerif';
      case 'system':
      default:
        return null;
    }
  }

  String _resolveUiCodeFontFamily(String id) {
    switch (id) {
      case 'jetbrains_mono':
        return 'JetBrainsMono';
      case 'noto_sans_mono':
        return 'NotoSansMono';
      case 'system_mono':
      default:
        return 'monospace';
    }
  }

  List<String> _codeFontFallback() => const ['Consolas', 'Menlo', 'Monaco'];

  /// 切换主题
  Future<void> setThemeMode(ThemeMode mode) async {
    setState(() {
      _themeMode = mode;
    });

    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_prefsThemeModeKey, mode.toString().split('.').last);
  }

  double get uiScale => _uiScale;
  String get uiFontFamily => _uiFontFamily;
  String get uiCodeFontFamily => _uiCodeFontFamily;

  Future<void> setDisplaySettings({
    double? uiScale,
    String? uiFontFamily,
    String? uiCodeFontFamily,
    bool persist = true,
  }) async {
    setState(() {
      if (uiScale != null) _uiScale = _clampUiScale(uiScale);
      if (uiFontFamily != null) _uiFontFamily = uiFontFamily;
      if (uiCodeFontFamily != null) _uiCodeFontFamily = uiCodeFontFamily;
    });

    if (!persist) return;

    final prefs = await SharedPreferences.getInstance();
    if (uiScale != null) await prefs.setDouble(_prefsUiScaleKey, _uiScale);
    if (uiFontFamily != null) {
      await prefs.setString(_prefsUiFontFamilyKey, _uiFontFamily);
    }
    if (uiCodeFontFamily != null) {
      await prefs.setString(_prefsUiCodeFontFamilyKey, _uiCodeFontFamily);
    }
  }

  /// 安全地缩放 TextTheme，避免 fontSize 为 null 时的断言错误
  TextTheme _scaleTextTheme(
    TextTheme base, {
    required double scale,
    String? fontFamily,
    Color? displayColor,
    Color? bodyColor,
  }) {
    TextStyle? scaleStyle(TextStyle? style, {Color? color}) {
      if (style == null) return null;
      final baseFontSize = style.fontSize ?? 14.0;
      return style.copyWith(
        fontFamily: fontFamily ?? style.fontFamily,
        fontSize: baseFontSize * scale,
        color: color ?? style.color,
      );
    }

    return TextTheme(
      displayLarge: scaleStyle(base.displayLarge, color: displayColor),
      displayMedium: scaleStyle(base.displayMedium, color: displayColor),
      displaySmall: scaleStyle(base.displaySmall, color: displayColor),
      headlineLarge: scaleStyle(base.headlineLarge, color: displayColor),
      headlineMedium: scaleStyle(base.headlineMedium, color: displayColor),
      headlineSmall: scaleStyle(base.headlineSmall, color: bodyColor),
      titleLarge: scaleStyle(base.titleLarge, color: bodyColor),
      titleMedium: scaleStyle(base.titleMedium, color: bodyColor),
      titleSmall: scaleStyle(base.titleSmall, color: bodyColor),
      bodyLarge: scaleStyle(base.bodyLarge, color: bodyColor),
      bodyMedium: scaleStyle(base.bodyMedium, color: bodyColor),
      bodySmall: scaleStyle(base.bodySmall, color: displayColor),
      labelLarge: scaleStyle(base.labelLarge, color: bodyColor),
      labelMedium: scaleStyle(base.labelMedium, color: bodyColor),
      labelSmall: scaleStyle(base.labelSmall, color: bodyColor),
    );
  }

  ThemeData _buildOwuiTheme({
    required Brightness brightness,
    required OwuiTokens tokens,
  }) {
    final colors = tokens.colors;
    final scale = tokens.uiScale;
    final fontFamily = tokens.typography.fontFamily;

    final ColorScheme colorScheme = ColorScheme.fromSeed(
      seedColor: Colors.blue,
      brightness: brightness,
    ).copyWith(surface: colors.surface, onSurface: colors.textPrimary);

    final base = ThemeData(
      useMaterial3: true,
      colorScheme: colorScheme,
      extensions: [tokens],
      scaffoldBackgroundColor: colors.pageBg,
      dividerColor: colors.borderSubtle,
      appBarTheme: AppBarTheme(
        backgroundColor: colors.pageBg,
        foregroundColor: colors.textPrimary,
        elevation: 0,
        scrolledUnderElevation: 0,
        surfaceTintColor: Colors.transparent,
      ),
    );

    // 使用安全的 textTheme 缩放，避免 fontSize 为 null 时的断言错误
    final textTheme = _scaleTextTheme(
      base.textTheme,
      scale: scale,
      fontFamily: fontFamily,
      displayColor: colors.textPrimary,
      bodyColor: colors.textPrimary,
    );

    final minInteractiveHeight = (44 * scale).clamp(40, 64).toDouble();
    final buttonPadding = EdgeInsets.symmetric(
      horizontal: 16 * scale,
      vertical: 12 * scale,
    );

    final buttonShape = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(tokens.radius.rXl),
    );

    return base.copyWith(
      textTheme: textTheme,
      primaryTextTheme: textTheme,
      iconTheme: base.iconTheme.copyWith(size: 20 * scale),
      // 桌面端使用 Fade 转场，避免 scale/translate 导致的子像素抖动
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: {
          TargetPlatform.windows: FadeUpwardsPageTransitionsBuilder(),
          TargetPlatform.linux: FadeUpwardsPageTransitionsBuilder(),
          TargetPlatform.macOS: FadeUpwardsPageTransitionsBuilder(),
          TargetPlatform.android: ZoomPageTransitionsBuilder(),
          TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
        },
      ),
      scrollbarTheme: ScrollbarThemeData(
        thickness: WidgetStatePropertyAll((8 * scale).clamp(6, 12).toDouble()),
        radius: Radius.circular(tokens.radius.rFull),
        thumbColor: WidgetStatePropertyAll(
          colors.borderStrong.withValues(alpha: 0.6),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          padding: buttonPadding,
          minimumSize: Size(0, minInteractiveHeight),
          shape: buttonShape,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          padding: buttonPadding,
          minimumSize: Size(0, minInteractiveHeight),
          shape: buttonShape,
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          padding: buttonPadding,
          minimumSize: Size(0, minInteractiveHeight),
          shape: buttonShape,
          side: BorderSide(color: colors.borderSubtle),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          padding: buttonPadding,
          minimumSize: Size(0, minInteractiveHeight),
          shape: buttonShape,
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: colors.surfaceCard,
        isDense: true,
        contentPadding: EdgeInsets.symmetric(
          horizontal: 12 * scale,
          vertical: 12 * scale,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(tokens.radius.r3xl),
          borderSide: BorderSide(color: colors.borderSubtle),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(tokens.radius.r3xl),
          borderSide: BorderSide(color: colors.borderSubtle),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(tokens.radius.r3xl),
          borderSide: BorderSide(color: colors.borderStrong),
        ),
      ),
      listTileTheme: ListTileThemeData(
        iconColor: colors.textSecondary,
        textColor: colors.textPrimary,
        contentPadding: EdgeInsets.symmetric(
          horizontal: 12 * scale,
          vertical: 2 * scale,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final fontFamily = _resolveUiFontFamily(_uiFontFamily);
    final codeFontFamily = _resolveUiCodeFontFamily(_uiCodeFontFamily);

    final typography = OwuiTypographyTokens(
      fontFamily: fontFamily,
      codeFontFamily: codeFontFamily,
      codeFontFallback: _codeFontFallback(),
    );

    final owuiLight = OwuiTokens.light(uiScale: _uiScale, typography: typography);
    final owuiDark = OwuiTokens.dark(uiScale: _uiScale, typography: typography);

    return MultiProvider(
      providers: [
        ChangeNotifierProvider(
          create: (_) => ChatSessionProvider(HiveConversationService()),
        ),
      ],
      child: MaterialApp(
        title: 'AI ChatBox',
        debugShowCheckedModeBanner: false,
        theme: _buildOwuiTheme(brightness: Brightness.light, tokens: owuiLight),
        darkTheme: _buildOwuiTheme(brightness: Brightness.dark, tokens: owuiDark),
        themeMode: _themeMode,
        home: const ChatPage(),
      ),
    );
  }
}
