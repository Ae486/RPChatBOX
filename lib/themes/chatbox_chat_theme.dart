import 'package:flutter/material.dart';

/// ChatBox 自定义聊天主题
///
/// 提供统一的视觉风格，支持亮色和暗色模式自动切换
/// 基于 Apple Design Guidelines
class ChatBoxChatTheme {
  ChatBoxChatTheme._();

  /// 用户消息气泡装饰
  static BoxDecoration userBubbleDecoration(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return BoxDecoration(
      color: isDark ? const Color(0xFF0A84FF) : const Color(0xFF007AFF),
      borderRadius: BorderRadius.circular(20),
      boxShadow: [
        BoxShadow(
          color: Colors.black.withValues(alpha: 0.08),
          offset: const Offset(0, 2),
          blurRadius: 8,
        ),
        BoxShadow(
          color: Colors.black.withValues(alpha: 0.04),
          offset: const Offset(0, 1),
          blurRadius: 3,
        ),
      ],
    );
  }

  /// 助手消息气泡装饰
  static BoxDecoration assistantBubbleDecoration(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return BoxDecoration(
      color: isDark ? const Color(0xFF2C2C2E) : const Color(0xFFF2F2F7),
      borderRadius: BorderRadius.circular(20),
      boxShadow: [
        BoxShadow(
          color: Colors.black.withValues(alpha: 0.08),
          offset: const Offset(0, 2),
          blurRadius: 8,
        ),
        BoxShadow(
          color: Colors.black.withValues(alpha: 0.04),
          offset: const Offset(0, 1),
          blurRadius: 3,
        ),
      ],
    );
  }

  /// 思考气泡装饰
  static BoxDecoration thinkingBubbleDecoration(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return BoxDecoration(
      color: isDark ? const Color(0xFF3A3A3C) : const Color(0xFFE5E5EA),
      borderRadius: BorderRadius.circular(16),
      boxShadow: [
        BoxShadow(
          color: Colors.black.withValues(alpha: 0.08),
          offset: const Offset(0, 2),
          blurRadius: 8,
        ),
        BoxShadow(
          color: Colors.black.withValues(alpha: 0.04),
          offset: const Offset(0, 1),
          blurRadius: 3,
        ),
      ],
    );
  }

  /// 输入框装饰
  static BoxDecoration inputDecoration(BuildContext context, {bool hasFocus = false}) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final primaryColor = isDark ? const Color(0xFF0A84FF) : const Color(0xFF007AFF);

    return BoxDecoration(
      color: isDark ? const Color(0xFF1C1C1E) : Colors.white,
      borderRadius: BorderRadius.circular(24),
      border: Border.all(
        color: hasFocus ? primaryColor : (isDark ? const Color(0xFF3A3A3C) : const Color(0xFFE5E5EA)),
        width: hasFocus ? 2 : 1,
      ),
    );
  }

  /// 获取主要颜色
  static Color primaryColor(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? const Color(0xFF0A84FF) : const Color(0xFF007AFF);
  }

  /// 获取表面颜色
  static Color surfaceColor(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? const Color(0xFF000000) : const Color(0xFFFFFFFF);
  }

  /// 获取文本颜色
  static Color onSurfaceColor(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? const Color(0xFFFFFFFF) : const Color(0xFF000000);
  }

  /// 获取次要文本颜色
  static Color secondaryTextColor(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? const Color(0x99FFFFFF) : const Color(0x99000000);
  }

  /// 获取分隔线颜色
  static Color separatorColor(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? const Color(0x26FFFFFF) : const Color(0x26000000);
  }

  /// 获取容器颜色
  static Color containerColor(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? const Color(0xFF1C1C1E) : const Color(0xFFF2F2F7);
  }

  /// 获取容器高亮颜色
  static Color containerHighColor(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? const Color(0xFF3A3A3C) : const Color(0xFFE5E5EA);
  }

  /// 获取助手气泡背景色（与 assistantBubbleDecoration 一致）
  static Color assistantBubbleColor(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? const Color(0xFF2C2C2E) : const Color(0xFFF2F2F7);
  }

  /// 获取思考气泡背景色（与 thinkingBubbleDecoration 一致）
  static Color thinkingBubbleColor(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    return isDark ? const Color(0xFF3A3A3C) : const Color(0xFFE5E5EA);
  }
}
