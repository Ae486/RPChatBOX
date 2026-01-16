/// INPUT: BuildContext -> Theme.of(context) + OwuiTokens ThemeExtension
/// OUTPUT: context.owui / context.owuiColors / ... 便捷访问器
/// POS: UI 层 / Design System / Owui - Token 访问扩展

import 'package:flutter/material.dart';

import 'owui_tokens.dart';

extension OwuiTokensContextX on BuildContext {
  /// Primary entry point. Intended usage: `context.owui.colors.pageBg`.
  OwuiTokens get owui {
    final theme = Theme.of(this);
    return theme.extension<OwuiTokens>() ??
        (theme.brightness == Brightness.dark
            ? OwuiTokens.dark()
            : OwuiTokens.light());
  }

  /// Back-compat alias.
  OwuiTokens get owuiTokens => owui;

  OwuiColorTokens get owuiColors => owui.colors;
  OwuiRadiusTokens get owuiRadius => owui.radius;
  OwuiSpacingTokens get owuiSpacing => owui.spacing;
  OwuiTypographyTokens get owuiTypography => owui.typography;
}
