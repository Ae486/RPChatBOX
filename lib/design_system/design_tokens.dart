import 'package:flutter/material.dart';

/// ChatBox 设计系统 - 设计令牌
/// 
/// 参考Apple App Store的视觉系统，统一管理所有设计值。
/// 这些值将逐步替换代码中的硬编码值，提升一致性和可维护性。
/// 
/// 主要的设计令牌类，提供对所有设计值的访问
class ChatBoxTokens {
  ChatBoxTokens._();

  /// 间距系统 (基于8px网格)
  static const spacing = _Spacing();

  /// 圆角系统
  static const radius = _Radius();

  /// 阴影/高度系统
  static const elevation = _Elevation();

  /// 动画系统
  static const animation = _Animation();

  /// 响应式断点
  static const breakpoints = _Breakpoints();
}

/// 间距系统
/// 
/// 基于8px网格，所有值都是8的倍数或半数。
/// 
/// 使用示例:
/// ```dart
/// EdgeInsets.all(ChatBoxTokens.spacing.md)  // 12px
/// SizedBox(height: ChatBoxTokens.spacing.lg)  // 16px
/// ```
class _Spacing {
  const _Spacing();

  /// 4px - 最小间距，用于非常紧密的元素
  final double xs = 4.0;

  /// 8px - 小间距，用于相关元素之间
  final double sm = 8.0;

  /// 12px - 中等间距，最常用的内边距
  final double md = 12.0;

  /// 16px - 大间距，用于组件之间
  final double lg = 16.0;

  /// 24px - 超大间距，用于分隔不同区域
  final double xl = 24.0;

  /// 32px - 最大间距，用于大型布局分隔
  final double xxl = 32.0;

  /// 48px - 超大间距，用于页面级别分隔
  final double xxxl = 48.0;
}

/// 圆角系统
/// 
/// 提供统一的圆角值，确保视觉一致性。
/// 
/// 使用示例:
/// ```dart
/// BorderRadius.circular(ChatBoxTokens.radius.medium)  // 12px
/// ```
class _Radius {
  const _Radius();

  /// 4px - 小圆角，用于小型元素
  final double xs = 4.0;

  /// 8px - 小圆角，用于按钮、标签等
  final double small = 8.0;

  /// 12px - 中等圆角，最常用的值（消息气泡、卡片）
  final double medium = 12.0;

  /// 16px - 大圆角，用于大型卡片
  final double large = 16.0;

  /// 24px - 药丸形状，用于输入框
  final double pill = 24.0;

  /// 完全圆形 (50%)
  final double circle = 9999.0;

  /// App图标样式圆角 (23%的宽度)
  /// 
  /// 使用示例:
  /// ```dart
  /// BorderRadius.circular(ChatBoxTokens.radius.appIcon(64))
  /// ```
  double appIcon(double size) => size * 0.23;
}

/// 阴影/高度系统
/// 
/// 提供统一的阴影效果，模拟Material Design的elevation。
/// 
/// 使用示例:
/// ```dart
/// BoxDecoration(
///   boxShadow: ChatBoxTokens.elevation.small,
/// )
/// ```
class _Elevation {
  const _Elevation();

  /// 无阴影
  List<BoxShadow> get none => const [];

  /// 小阴影 - 用于卡片、按钮等
  /// Apple风格: 0 2px 8px rgba(0,0,0,0.05)
  List<BoxShadow> get small => const [
        BoxShadow(
          color: Color(0x0D000000), // rgba(0,0,0,0.05)
          blurRadius: 8,
          offset: Offset(0, 2),
        ),
      ];

  /// 中等阴影 - 用于对话框、抽屉等
  List<BoxShadow> get medium => const [
        BoxShadow(
          color: Color(0x1A000000), // rgba(0,0,0,0.10)
          blurRadius: 16,
          offset: Offset(0, 4),
        ),
      ];

  /// 大阴影 - 用于浮动操作按钮、模态框等
  List<BoxShadow> get large => const [
        BoxShadow(
          color: Color(0x26000000), // rgba(0,0,0,0.15)
          blurRadius: 24,
          offset: Offset(0, 8),
        ),
      ];
}

/// 动画系统
/// 
/// 提供统一的动画时长和缓动曲线。
/// Apple使用210ms作为标准悬停动画时长。
/// 
/// 使用示例:
/// ```dart
/// AnimatedContainer(
///   duration: ChatBoxTokens.animation.normal,
///   curve: ChatBoxTokens.animation.standard,
/// )
/// ```
class _Animation {
  const _Animation();

  /// 150ms - 快速动画 (按钮点击反馈)
  final Duration fast = const Duration(milliseconds: 150);

  /// 210ms - 标准动画 (悬停效果) - Apple标准
  final Duration normal = const Duration(milliseconds: 210);

  /// 300ms - 慢速动画 (页面切换、展开折叠)
  final Duration slow = const Duration(milliseconds: 300);

  /// 560ms - 菜单动画 (Apple特有的菜单展开时长)
  final Duration menu = const Duration(milliseconds: 560);

  /// 1200ms - 呼吸灯动画 (思考气泡)
  final Duration breathe = const Duration(milliseconds: 1200);

  /// 标准缓动曲线 - ease-out
  final Curve standard = Curves.easeOut;

  /// Apple强调缓动曲线 - cubic-bezier(0.52, 0.16, 0.24, 1)
  final Curve emphasized = const Cubic(0.52, 0.16, 0.24, 1.0);

  /// 平滑进入 - ease-in
  final Curve easeIn = Curves.easeIn;

  /// 平滑进出 - ease-in-out
  final Curve easeInOut = Curves.easeInOut;
}

/// 响应式断点
/// 
/// 定义不同屏幕尺寸的断点和对应的布局参数。
/// 
/// 使用示例:
/// ```dart
/// final width = MediaQuery.of(context).size.width;
/// if (width < ChatBoxTokens.breakpoints.tablet) {
///   // 移动端布局
/// }
/// ```
class _Breakpoints {
  const _Breakpoints();

  /// 600px - 移动端/平板分界点
  final double mobile = 600;

  /// 1024px - 平板/桌面分界点
  final double tablet = 1024;

  /// 1440px - 桌面/大屏分界点
  final double desktop = 1440;

  /// 260px - 平板端侧边栏宽度 (参考Apple)
  final double sidebarMedium = 260;

  /// 300px - 桌面端侧边栏宽度 (参考Apple)
  final double sidebarLarge = 300;

  /// 44px - 移动端顶部导航高度 (参考Apple)
  final double mobileHeaderHeight = 44;
}
