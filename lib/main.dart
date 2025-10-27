import 'dart:io';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:webview_flutter/webview_flutter.dart';
import 'pages/chat_page.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  
  // 初始化 WebView 平台（Windows/Android）
  if (Platform.isWindows) {
    // Windows 平台 WebView 初始化会在第一次使用时自动完成
    // 无需手动初始化
  } else if (Platform.isAndroid) {
    // Android 平台也会自动初始化
  }
  
  final prefs = await SharedPreferences.getInstance();
  final themeMode = prefs.getString('theme_mode') ?? 'system';
  runApp(MyApp(initialThemeMode: themeMode));
}

class MyApp extends StatefulWidget {
  final String initialThemeMode;

  const MyApp({super.key, required this.initialThemeMode});

  @override
  State<MyApp> createState() => _MyAppState();
  
  static _MyAppState? of(BuildContext context) =>
      context.findAncestorStateOfType<_MyAppState>();
}

class _MyAppState extends State<MyApp> {
  late ThemeMode _themeMode;

  @override
  void initState() {
    super.initState();
    _themeMode = _themeModeFromString(widget.initialThemeMode);
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

  /// 切换主题
  Future<void> setThemeMode(ThemeMode mode) async {
    setState(() {
      _themeMode = mode;
    });
    
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('theme_mode', mode.toString().split('.').last);
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI ChatBox',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.blue,
          brightness: Brightness.light,
        ),
        useMaterial3: true,
      ),
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.blue,
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      themeMode: _themeMode,
      home: const ChatPage(),
    );
  }
}
