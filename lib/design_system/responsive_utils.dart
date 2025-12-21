import 'package:flutter/material.dart';
import 'design_tokens.dart';

/// 屏幕尺寸枚举
enum ScreenSize {
  /// 移动端 (< 600px)
  mobile,

  /// 平板端 (600px - 1024px)
  tablet,

  /// 桌面端 (>= 1024px)
  desktop,
}

/// 响应式工具类
/// 
/// 提供便捷的方法来判断当前屏幕尺寸和获取对应的布局参数。
/// 
/// 使用示例:
/// ```dart
/// if (ResponsiveUtils.isMobile(context)) {
///   // 移动端特定逻辑
/// }
/// 
/// final sidebarWidth = ResponsiveUtils.getSidebarWidth(context);
/// ```
class ResponsiveUtils {
  ResponsiveUtils._();

  /// 获取当前屏幕尺寸类型
  /// 
  /// 根据屏幕宽度返回对应的 [ScreenSize] 枚举值。
  /// 
  /// 断点:
  /// - < 600px: mobile
  /// - 600px - 1024px: tablet
  /// - >= 1024px: desktop
  static ScreenSize getScreenSize(BuildContext context) {
    final width = MediaQuery.of(context).size.width;
    if (width < ChatBoxTokens.breakpoints.mobile) {
      return ScreenSize.mobile;
    } else if (width < ChatBoxTokens.breakpoints.tablet) {
      return ScreenSize.tablet;
    } else {
      return ScreenSize.desktop;
    }
  }

  /// 判断是否为移动端 (< 600px)
  static bool isMobile(BuildContext context) {
    return getScreenSize(context) == ScreenSize.mobile;
  }

  /// 判断是否为平板端 (600px - 1024px)
  static bool isTablet(BuildContext context) {
    return getScreenSize(context) == ScreenSize.tablet;
  }

  /// 判断是否为桌面端 (>= 1024px)
  static bool isDesktop(BuildContext context) {
    return getScreenSize(context) == ScreenSize.desktop;
  }

  /// 判断是否应该显示侧边栏（非移动端）
  static bool shouldShowSidebar(BuildContext context) {
    return !isMobile(context);
  }

  /// 获取侧边栏宽度
  /// 
  /// 根据屏幕尺寸返回对应的侧边栏宽度：
  /// - 移动端: 0 (使用Drawer)
  /// - 平板端: 260px
  /// - 桌面端: 300px
  static double getSidebarWidth(BuildContext context) {
    final screenSize = getScreenSize(context);
    switch (screenSize) {
      case ScreenSize.mobile:
        return 0; // 使用Drawer，不占用空间
      case ScreenSize.tablet:
        return ChatBoxTokens.breakpoints.sidebarMedium;
      case ScreenSize.desktop:
        return ChatBoxTokens.breakpoints.sidebarLarge;
    }
  }

  /// 获取当前屏幕宽度
  static double getScreenWidth(BuildContext context) {
    return MediaQuery.of(context).size.width;
  }

  /// 获取当前屏幕高度
  static double getScreenHeight(BuildContext context) {
    return MediaQuery.of(context).size.height;
  }

  /// 根据屏幕尺寸返回不同的值
  /// 
  /// 使用示例:
  /// ```dart
  /// final padding = ResponsiveUtils.valueByScreen(
  ///   context,
  ///   mobile: 8.0,
  ///   tablet: 16.0,
  ///   desktop: 24.0,
  /// );
  /// ```
  static T valueByScreen<T>(
    BuildContext context, {
    required T mobile,
    required T tablet,
    required T desktop,
  }) {
    final screenSize = getScreenSize(context);
    switch (screenSize) {
      case ScreenSize.mobile:
        return mobile;
      case ScreenSize.tablet:
        return tablet;
      case ScreenSize.desktop:
        return desktop;
    }
  }

  /// 获取响应式的列数
  /// 
  /// 常用于Grid布局。
  static int getGridColumns(BuildContext context) {
    return valueByScreen(
      context,
      mobile: 1,
      tablet: 2,
      desktop: 3,
    );
  }

  /// 获取响应式的间距
  static double getResponsiveSpacing(BuildContext context) {
    return valueByScreen(
      context,
      mobile: ChatBoxTokens.spacing.sm,
      tablet: ChatBoxTokens.spacing.md,
      desktop: ChatBoxTokens.spacing.lg,
    );
  }
}
