import 'package:flutter/material.dart';

/// Apple风格设计系统扩展
/// 
/// 提供Apple App Store级别的视觉设计Token，包括：
/// - 双层阴影系统
/// - Apple标准颜色
/// - SF风格字体层级
/// - 气泡特殊圆角
class AppleTokens {
  AppleTokens._();

  /// Apple风格阴影系统
  static const shadows = _AppleShadows();

  /// Apple标准颜色
  static const colors = _AppleColors();

  /// Apple字体系统
  static const typography = _AppleTypography();

  /// Apple特殊圆角
  static const corners = _AppleCorners();
}

/// 公开访问Apple颜色（用于外部导入）
typedef AppleColors = _AppleColors;

/// 公开访问Apple字体（用于外部导入）
typedef AppleTypography = _AppleTypography;

/// Apple双层阴影系统
/// 
/// Apple使用两层阴影营造更真实的深度感：
/// 1. 浅色大范围模糊（ambient shadow）
/// 2. 深色小范围锐利（direct shadow）
class _AppleShadows {
  const _AppleShadows();

  /// 气泡阴影 - 用于对话气泡
  /// 双层：淡模糊 + 深锐利
  List<BoxShadow> get bubble => const [
        BoxShadow(
          color: Color(0x14000000), // alpha 0.08
          offset: Offset(0, 2),
          blurRadius: 8,
          spreadRadius: 0,
        ),
        BoxShadow(
          color: Color(0x0A000000), // alpha 0.04
          offset: Offset(0, 1),
          blurRadius: 3,
          spreadRadius: 0,
        ),
      ];

  /// 卡片阴影 - 用于Provider/Model卡片
  List<BoxShadow> get card => const [
        BoxShadow(
          color: Color(0x0A000000), // alpha 0.04
          offset: Offset(0, 1),
          blurRadius: 3,
          spreadRadius: 0,
        ),
        BoxShadow(
          color: Color(0x1F000000), // alpha 0.12
          offset: Offset(0, 1),
          blurRadius: 2,
          spreadRadius: 0,
        ),
      ];

  /// Hover增强阴影 - 悬停时的阴影
  List<BoxShadow> get cardHover => const [
        BoxShadow(
          color: Color(0x1A000000), // alpha 0.10
          offset: Offset(0, 4),
          blurRadius: 12,
          spreadRadius: 0,
        ),
        BoxShadow(
          color: Color(0x14000000), // alpha 0.08
          offset: Offset(0, 2),
          blurRadius: 4,
          spreadRadius: 0,
        ),
      ];

  /// 浮动元素阴影 - 用于输入框、浮动按钮
  List<BoxShadow> get floating => const [
        BoxShadow(
          color: Color(0x0D000000), // alpha 0.05
          offset: Offset(0, 2),
          blurRadius: 8,
          spreadRadius: 0,
        ),
      ];

  /// 强调阴影 - 用于高亮、选中状态
  List<BoxShadow> highlight(Color accentColor) => [
        BoxShadow(
          color: accentColor.withValues(alpha: 0.3),
          offset: const Offset(0, 0),
          blurRadius: 12,
          spreadRadius: 2,
        ),
      ];
}

/// Apple标准颜色系统
/// 
/// 参考iOS Human Interface Guidelines
/// 包含亮色/暗色模式自适应
class _AppleColors {
  const _AppleColors();

  /// Apple蓝 - 主要强调色
  static const blue = Color(0xFF007AFF);

  /// Apple紫 - 思考气泡
  static const purple = Color(0xFFAF52DE);

  /// Apple粉 - 错误/警告
  static const pink = Color(0xFFFF2D55);

  /// Apple红 - 删除/危险操作
  static const red = Color(0xFFFF3B30);

  /// Apple橙 - 警告
  static const orange = Color(0xFFFF9500);

  /// Apple黄 - 提示
  static const yellow = Color(0xFFFFCC00);

  /// Apple绿 - 成功
  static const green = Color(0xFF34C759);

  /// Apple青 - 信息
  static const teal = Color(0xFF5AC8FA);

  /// Apple靛 - 次要强调
  static const indigo = Color(0xFF5856D6);

  /// 系统背景色（自适应）
  static Color systemBackground(BuildContext context) {
    return Theme.of(context).brightness == Brightness.dark
        ? const Color(0xFF000000) // 纯黑
        : const Color(0xFFFFFFFF); // 纯白
  }

  /// 次级背景色（自适应）
  static Color secondarySystemBackground(BuildContext context) {
    return Theme.of(context).brightness == Brightness.dark
        ? const Color(0xFF1C1C1E) // 深灰
        : const Color(0xFFF2F2F7); // 浅灰
  }

  /// 三级背景色（自适应）
  static Color tertiarySystemBackground(BuildContext context) {
    return Theme.of(context).brightness == Brightness.dark
        ? const Color(0xFF2C2C2E) // 中灰
        : const Color(0xFFFFFFFF); // 白色
  }

  /// 主要标签色（自适应）
  static Color label(BuildContext context) {
    return Theme.of(context).brightness == Brightness.dark
        ? const Color(0xFFFFFFFF) // 白色
        : const Color(0xFF000000); // 黑色
  }

  /// 次级标签色（自适应）
  static Color secondaryLabel(BuildContext context) {
    return Theme.of(context).brightness == Brightness.dark
        ? const Color(0x99FFFFFF) // 白色 60%
        : const Color(0x99000000); // 黑色 60%
  }

  /// 三级标签色（自适应）
  static Color tertiaryLabel(BuildContext context) {
    return Theme.of(context).brightness == Brightness.dark
        ? const Color(0x4DFFFFFF) // 白色 30%
        : const Color(0x4D000000); // 黑色 30%
  }

  /// 四级标签色（自适应）
  static Color quaternaryLabel(BuildContext context) {
    return Theme.of(context).brightness == Brightness.dark
        ? const Color(0x26FFFFFF) // 白色 15%
        : const Color(0x26000000); // 黑色 15%
  }

  /// 分隔线颜色（自适应）
  static Color separator(BuildContext context) {
    return Theme.of(context).brightness == Brightness.dark
        ? const Color(0x26FFFFFF) // 白色 15%
        : const Color(0x26000000); // 黑色 15%
  }
}

/// Apple字体层级系统
/// 
/// 参考iOS Typography标准
/// 包含fontSize, fontWeight, letterSpacing, height(lineHeight)
class _AppleTypography {
  const _AppleTypography();

  /// Large Title - 34pt
  /// 用于：页面大标题
  final largeTitle = const TextStyle(
    fontSize: 34,
    fontWeight: FontWeight.w700,
    letterSpacing: 0.37,
    height: 1.18, // 40/34
  );

  /// Title 1 - 28pt
  /// 用于：主标题
  final title1 = const TextStyle(
    fontSize: 28,
    fontWeight: FontWeight.w700,
    letterSpacing: 0.36,
    height: 1.21, // 34/28
  );

  /// Title 2 - 22pt
  /// 用于：次级标题
  final title2 = const TextStyle(
    fontSize: 22,
    fontWeight: FontWeight.w700,
    letterSpacing: 0.35,
    height: 1.27, // 28/22
  );

  /// Title 3 - 20pt
  /// 用于：三级标题、卡片标题
  final title3 = const TextStyle(
    fontSize: 20,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.38,
    height: 1.25, // 25/20
  );

  /// Headline - 17pt (Semi-bold)
  /// 用于：列表项标题、强调文本
  final headline = const TextStyle(
    fontSize: 17,
    fontWeight: FontWeight.w600,
    letterSpacing: -0.41,
    height: 1.29, // 22/17
  );

  /// Body - 17pt (Regular)
  /// 用于：正文内容
  final body = const TextStyle(
    fontSize: 17,
    fontWeight: FontWeight.w400,
    letterSpacing: -0.41,
    height: 1.29, // 22/17
  );

  /// Callout - 16pt
  /// 用于：次要正文、说明文字
  final callout = const TextStyle(
    fontSize: 16,
    fontWeight: FontWeight.w400,
    letterSpacing: -0.32,
    height: 1.31, // 21/16
  );

  /// Subheadline - 15pt
  /// 用于：消息气泡、列表副标题
  final subheadline = const TextStyle(
    fontSize: 15,
    fontWeight: FontWeight.w400,
    letterSpacing: -0.24,
    height: 1.33, // 20/15
  );

  /// Footnote - 13pt
  /// 用于：时间戳、辅助信息
  final footnote = const TextStyle(
    fontSize: 13,
    fontWeight: FontWeight.w400,
    letterSpacing: -0.08,
    height: 1.38, // 18/13
  );

  /// Caption 1 - 12pt
  /// 用于：图片说明、极小文本
  final caption1 = const TextStyle(
    fontSize: 12,
    fontWeight: FontWeight.w400,
    letterSpacing: 0,
    height: 1.33, // 16/12
  );

  /// Caption 2 - 11pt
  /// 用于：最小文本
  final caption2 = const TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w400,
    letterSpacing: 0.07,
    height: 1.27, // 14/11
  );
}

/// Apple特殊圆角系统
class _AppleCorners {
  const _AppleCorners();

  /// 消息气泡圆角 - 20px (Apple Messages标准)
  final double bubble = 20.0;

  /// 输入框圆角 - 18px (Apple Messages输入框)
  final double inputField = 18.0;

  /// 思考气泡圆角 - 16px (略小于普通气泡)
  final double thinkingBubble = 16.0;

  /// App图标圆角比例 - 23%
  /// 
  /// 使用示例：
  /// ```dart
  /// BorderRadius.circular(AppleTokens.corners.appIconRadius(64))
  /// ```
  double appIconRadius(double size) => size * 0.23;
}
