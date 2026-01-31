/// INPUT: BuildContext（主题/调色板）
/// OUTPUT: OwuiChatTheme.chatTheme()/userBubbleDecoration()/thinkingDecoration()
/// POS: UI 层 / Chat / Owui - flutter_chat_ui 主题映射与气泡装饰

import 'package:flutter/material.dart';
import 'package:flutter_chat_core/flutter_chat_core.dart';

import 'palette.dart';

class OwuiChatTheme {
  OwuiChatTheme._();

  static ChatTheme chatTheme(BuildContext context) {
    final isDark = OwuiPalette.isDark(context);
    final primary = Theme.of(context).colorScheme.primary;

    return ChatTheme(
      colors: ChatColors(
        primary: primary,
        onPrimary: Theme.of(context).colorScheme.onPrimary,
        surface: isDark ? OwuiPalette.gray900 : Colors.white,
        onSurface: isDark ? Colors.white : Colors.black,
        surfaceContainerLow: isDark ? OwuiPalette.gray900 : Colors.white,
        surfaceContainer: isDark ? OwuiPalette.gray850 : OwuiPalette.gray50,
        surfaceContainerHigh: isDark ? OwuiPalette.gray800 : OwuiPalette.gray100,
      ),
      typography: ChatTypography.fromThemeData(Theme.of(context)),
      shape: const BorderRadius.all(Radius.circular(24)), // tailwind: rounded-3xl
    );
  }

  static BoxDecoration userBubbleDecoration(BuildContext context) {
    return BoxDecoration(
      color: OwuiPalette.surfaceCard(context),
      borderRadius: BorderRadius.circular(24),
      border: Border.all(color: OwuiPalette.borderSubtle(context)),
    );
  }

  static BoxDecoration thinkingDecoration(BuildContext context) {
    final isDark = OwuiPalette.isDark(context);
    return BoxDecoration(
      color: isDark ? const Color(0xFF171717) : const Color(0xFFF9F9F9),
      borderRadius: BorderRadius.circular(12),
      border: Border.all(
        color: isDark
            ? Colors.white.withValues(alpha: 0.1)
            : Colors.black.withValues(alpha: 0.06),
      ),
    );
  }
}
