/// INPUT: uiScale/typography（可选）+ ThemeData
/// OUTPUT: OwuiTokens ThemeExtension（颜色/圆角/间距/字体）+ light/dark 构建器
/// POS: UI 层 / Design System / Owui - 主题 Token（供全局 Theme 与组件读取）

import 'dart:ui' show lerpDouble;

import 'package:flutter/material.dart';

import 'palette.dart';

@immutable
class OwuiColorTokens {
  final Color pageBg;
  final Color surface;
  final Color surface2;
  final Color surfaceCard;
  final Color borderSubtle;
  final Color borderStrong;
  final Color textPrimary;
  final Color textSecondary;
  final Color hoverOverlay;

  const OwuiColorTokens({
    required this.pageBg,
    required this.surface,
    required this.surface2,
    required this.surfaceCard,
    required this.borderSubtle,
    required this.borderStrong,
    required this.textPrimary,
    required this.textSecondary,
    required this.hoverOverlay,
  });

  OwuiColorTokens copyWith({
    Color? pageBg,
    Color? surface,
    Color? surface2,
    Color? surfaceCard,
    Color? borderSubtle,
    Color? borderStrong,
    Color? textPrimary,
    Color? textSecondary,
    Color? hoverOverlay,
  }) {
    return OwuiColorTokens(
      pageBg: pageBg ?? this.pageBg,
      surface: surface ?? this.surface,
      surface2: surface2 ?? this.surface2,
      surfaceCard: surfaceCard ?? this.surfaceCard,
      borderSubtle: borderSubtle ?? this.borderSubtle,
      borderStrong: borderStrong ?? this.borderStrong,
      textPrimary: textPrimary ?? this.textPrimary,
      textSecondary: textSecondary ?? this.textSecondary,
      hoverOverlay: hoverOverlay ?? this.hoverOverlay,
    );
  }

  static OwuiColorTokens lerp(OwuiColorTokens a, OwuiColorTokens b, double t) {
    return OwuiColorTokens(
      pageBg: Color.lerp(a.pageBg, b.pageBg, t)!,
      surface: Color.lerp(a.surface, b.surface, t)!,
      surface2: Color.lerp(a.surface2, b.surface2, t)!,
      surfaceCard: Color.lerp(a.surfaceCard, b.surfaceCard, t)!,
      borderSubtle: Color.lerp(a.borderSubtle, b.borderSubtle, t)!,
      borderStrong: Color.lerp(a.borderStrong, b.borderStrong, t)!,
      textPrimary: Color.lerp(a.textPrimary, b.textPrimary, t)!,
      textSecondary: Color.lerp(a.textSecondary, b.textSecondary, t)!,
      hoverOverlay: Color.lerp(a.hoverOverlay, b.hoverOverlay, t)!,
    );
  }
}

@immutable
class OwuiRadiusTokens {
  final double rLg;
  final double rXl;
  final double r3xl;
  final double rFull;

  const OwuiRadiusTokens({
    required this.rLg,
    required this.rXl,
    required this.r3xl,
    required this.rFull,
  });

  OwuiRadiusTokens copyWith({
    double? rLg,
    double? rXl,
    double? r3xl,
    double? rFull,
  }) {
    return OwuiRadiusTokens(
      rLg: rLg ?? this.rLg,
      rXl: rXl ?? this.rXl,
      r3xl: r3xl ?? this.r3xl,
      rFull: rFull ?? this.rFull,
    );
  }

  static OwuiRadiusTokens lerp(
    OwuiRadiusTokens a,
    OwuiRadiusTokens b,
    double t,
  ) {
    return OwuiRadiusTokens(
      rLg: lerpDouble(a.rLg, b.rLg, t)!,
      rXl: lerpDouble(a.rXl, b.rXl, t)!,
      r3xl: lerpDouble(a.r3xl, b.r3xl, t)!,
      rFull: lerpDouble(a.rFull, b.rFull, t)!,
    );
  }
}

@immutable
class OwuiSpacingTokens {
  final double xs;
  final double sm;
  final double md;
  final double lg;
  final double xl;
  final double xxl;

  const OwuiSpacingTokens({
    required this.xs,
    required this.sm,
    required this.md,
    required this.lg,
    required this.xl,
    required this.xxl,
  });

  OwuiSpacingTokens copyWith({
    double? xs,
    double? sm,
    double? md,
    double? lg,
    double? xl,
    double? xxl,
  }) {
    return OwuiSpacingTokens(
      xs: xs ?? this.xs,
      sm: sm ?? this.sm,
      md: md ?? this.md,
      lg: lg ?? this.lg,
      xl: xl ?? this.xl,
      xxl: xxl ?? this.xxl,
    );
  }

  static OwuiSpacingTokens lerp(
    OwuiSpacingTokens a,
    OwuiSpacingTokens b,
    double t,
  ) {
    return OwuiSpacingTokens(
      xs: lerpDouble(a.xs, b.xs, t)!,
      sm: lerpDouble(a.sm, b.sm, t)!,
      md: lerpDouble(a.md, b.md, t)!,
      lg: lerpDouble(a.lg, b.lg, t)!,
      xl: lerpDouble(a.xl, b.xl, t)!,
      xxl: lerpDouble(a.xxl, b.xxl, t)!,
    );
  }
}

@immutable
class OwuiTypographyTokens {
  final String? fontFamily;
  final String codeFontFamily;
  final List<String> codeFontFallback;

  const OwuiTypographyTokens({
    this.fontFamily,
    this.codeFontFamily = 'monospace',
    this.codeFontFallback = const ['Consolas', 'Menlo', 'Monaco', 'monospace'],
  });

  OwuiTypographyTokens copyWith({
    String? fontFamily,
    String? codeFontFamily,
    List<String>? codeFontFallback,
  }) {
    return OwuiTypographyTokens(
      fontFamily: fontFamily ?? this.fontFamily,
      codeFontFamily: codeFontFamily ?? this.codeFontFamily,
      codeFontFallback: codeFontFallback ?? this.codeFontFallback,
    );
  }

  static OwuiTypographyTokens lerp(
    OwuiTypographyTokens a,
    OwuiTypographyTokens b,
    double t,
  ) {
    return t < 0.5 ? a : b;
  }
}

@immutable
class OwuiTokens extends ThemeExtension<OwuiTokens> {
  final double uiScale;
  final OwuiColorTokens colors;
  final OwuiRadiusTokens radius;
  final OwuiSpacingTokens spacing;
  final OwuiTypographyTokens typography;

  const OwuiTokens({
    required this.uiScale,
    required this.colors,
    required this.radius,
    required this.spacing,
    required this.typography,
  });

  factory OwuiTokens.light({
    double uiScale = 1.0,
    OwuiTypographyTokens typography = const OwuiTypographyTokens(),
  }) {
    return OwuiTokens(
      uiScale: uiScale,
      colors: OwuiColorTokens(
        pageBg: Colors.white,
        surface: Colors.white,
        surface2: OwuiPalette.gray50,
        surfaceCard: OwuiPalette.gray50,
        borderSubtle: OwuiPalette.gray100.withValues(alpha: 0.30),
        borderStrong: OwuiPalette.gray200,
        textPrimary: Colors.black,
        textSecondary: OwuiPalette.gray600,
        hoverOverlay: Colors.black.withValues(alpha: 0.05),
      ),
      radius: OwuiRadiusTokens(
        rLg: 8 * uiScale,
        rXl: 12 * uiScale,
        r3xl: 24 * uiScale,
        rFull: 9999,
      ),
      spacing: OwuiSpacingTokens(
        xs: 4 * uiScale,
        sm: 8 * uiScale,
        md: 12 * uiScale,
        lg: 16 * uiScale,
        xl: 24 * uiScale,
        xxl: 32 * uiScale,
      ),
      typography: typography,
    );
  }

  factory OwuiTokens.dark({
    double uiScale = 1.0,
    OwuiTypographyTokens typography = const OwuiTypographyTokens(),
  }) {
    return OwuiTokens(
      uiScale: uiScale,
      colors: OwuiColorTokens(
        pageBg: OwuiPalette.gray900,
        surface: OwuiPalette.gray900,
        surface2: OwuiPalette.gray850,
        surfaceCard: OwuiPalette.gray850,
        borderSubtle: OwuiPalette.gray850.withValues(alpha: 0.30),
        borderStrong: OwuiPalette.gray800,
        textPrimary: Colors.white,
        textSecondary: OwuiPalette.gray400,
        hoverOverlay: Colors.white.withValues(alpha: 0.05),
      ),
      radius: OwuiRadiusTokens(
        rLg: 8 * uiScale,
        rXl: 12 * uiScale,
        r3xl: 24 * uiScale,
        rFull: 9999,
      ),
      spacing: OwuiSpacingTokens(
        xs: 4 * uiScale,
        sm: 8 * uiScale,
        md: 12 * uiScale,
        lg: 16 * uiScale,
        xl: 24 * uiScale,
        xxl: 32 * uiScale,
      ),
      typography: typography,
    );
  }

  @override
  OwuiTokens copyWith({
    double? uiScale,
    OwuiColorTokens? colors,
    OwuiRadiusTokens? radius,
    OwuiSpacingTokens? spacing,
    OwuiTypographyTokens? typography,
  }) {
    return OwuiTokens(
      uiScale: uiScale ?? this.uiScale,
      colors: colors ?? this.colors,
      radius: radius ?? this.radius,
      spacing: spacing ?? this.spacing,
      typography: typography ?? this.typography,
    );
  }

  @override
  OwuiTokens lerp(ThemeExtension<OwuiTokens>? other, double t) {
    if (other is! OwuiTokens) return this;

    return OwuiTokens(
      uiScale: lerpDouble(uiScale, other.uiScale, t)!,
      colors: OwuiColorTokens.lerp(colors, other.colors, t),
      radius: OwuiRadiusTokens.lerp(radius, other.radius, t),
      spacing: OwuiSpacingTokens.lerp(spacing, other.spacing, t),
      typography: OwuiTypographyTokens.lerp(typography, other.typography, t),
    );
  }
}
