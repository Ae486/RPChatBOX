import 'package:flutter/material.dart';

/// OpenWebUI-inspired grayscale palette and primitives.
///
/// Reference: `.tmp/open-webui/tailwind.config.js` (gray 50..950).
class OwuiPalette {
  OwuiPalette._();

  // Tailwind gray scale (default fallbacks from OpenWebUI).
  static const gray50 = Color(0xFFF9F9F9);
  static const gray100 = Color(0xFFECECEC);
  static const gray200 = Color(0xFFE3E3E3);
  static const gray300 = Color(0xFFCDCDCD);
  static const gray400 = Color(0xFFB4B4B4);
  static const gray500 = Color(0xFF9B9B9B);
  static const gray600 = Color(0xFF676767);
  static const gray700 = Color(0xFF4E4E4E);
  static const gray800 = Color(0xFF333333);
  static const gray850 = Color(0xFF262626);
  static const gray900 = Color(0xFF171717);
  static const gray950 = Color(0xFF0D0D0D);

  static bool isDark(BuildContext context) =>
      Theme.of(context).brightness == Brightness.dark;

  static Color pageBackground(BuildContext context) =>
      isDark(context) ? gray900 : Colors.white;

  static Color surfaceCard(BuildContext context) =>
      isDark(context) ? gray850 : gray50;

  static Color borderSubtle(BuildContext context) =>
      isDark(context) ? const Color(0x26FFFFFF) : const Color(0x1A000000);

  static Color textPrimary(BuildContext context) =>
      isDark(context) ? Colors.white : Colors.black;

  static Color textSecondary(BuildContext context) =>
      isDark(context) ? gray400 : gray600;
}

