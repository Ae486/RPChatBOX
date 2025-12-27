import 'package:flutter/material.dart';
import 'dart:ui';
import '../design_system/apple_tokens.dart';
import '../design_system/apple_icons.dart';

/// Apple风格Toast类型
enum AppleToastType {
  success,
  error,
  warning,
  info,
}

/// Apple风格Toast显示器
///
/// Legacy: 请勿在新代码中使用；请优先使用 `GlobalToast`（OWUI 风格）。
@Deprecated('Legacy Apple Toast 已废弃，请使用 GlobalToast（lib/utils/global_toast.dart）')
class AppleToast {
  static OverlayEntry? _currentEntry;
  static bool _isShowing = false;

  /// 显示Toast
  static void show(
    BuildContext context, {
    required String message,
    AppleToastType type = AppleToastType.info,
    Duration duration = const Duration(seconds: 3),
    IconData? icon,
    VoidCallback? onTap,
  }) {
    if (_isShowing) {
      hide();
    }

    _isShowing = true;

    final overlay = Overlay.of(context);
    _currentEntry = OverlayEntry(
      builder: (context) => _AppleToastWidget(
        message: message,
        type: type,
        icon: icon,
        onTap: onTap,
        onDismiss: hide,
      ),
    );

    overlay.insert(_currentEntry!);

    Future.delayed(duration, () {
      hide();
    });
  }

  /// 成功Toast
  static void success(
    BuildContext context, {
    required String message,
    Duration duration = const Duration(seconds: 3),
  }) {
    show(
      context,
      message: message,
      type: AppleToastType.success,
      duration: duration,
    );
  }

  /// 错误Toast
  static void error(
    BuildContext context, {
    required String message,
    Duration duration = const Duration(seconds: 3),
  }) {
    show(
      context,
      message: message,
      type: AppleToastType.error,
      duration: duration,
    );
  }

  /// 警告Toast
  static void warning(
    BuildContext context, {
    required String message,
    Duration duration = const Duration(seconds: 3),
  }) {
    show(
      context,
      message: message,
      type: AppleToastType.warning,
      duration: duration,
    );
  }

  /// 信息Toast
  static void info(
    BuildContext context, {
    required String message,
    Duration duration = const Duration(seconds: 3),
  }) {
    show(
      context,
      message: message,
      type: AppleToastType.info,
      duration: duration,
    );
  }

  /// 隐藏Toast
  static void hide() {
    if (_currentEntry != null) {
      _currentEntry!.remove();
      _currentEntry = null;
      _isShowing = false;
    }
  }
}

/// Apple Toast Widget
class _AppleToastWidget extends StatefulWidget {
  final String message;
  final AppleToastType type;
  final IconData? icon;
  final VoidCallback? onTap;
  final VoidCallback onDismiss;

  const _AppleToastWidget({
    required this.message,
    required this.type,
    this.icon,
    this.onTap,
    required this.onDismiss,
  });

  @override
  State<_AppleToastWidget> createState() => _AppleToastWidgetState();
}

class _AppleToastWidgetState extends State<_AppleToastWidget>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<Offset> _slideAnimation;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );

    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, -1),
      end: Offset.zero,
    ).animate(CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOutCubic,
    ));

    _fadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOut,
    ));

    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Color _getColor() {
    switch (widget.type) {
      case AppleToastType.success:
        return AppleColors.green;
      case AppleToastType.error:
        return AppleColors.red;
      case AppleToastType.warning:
        return AppleColors.orange;
      case AppleToastType.info:
        return AppleColors.blue;
    }
  }

  IconData _getIcon() {
    if (widget.icon != null) return widget.icon!;

    switch (widget.type) {
      case AppleToastType.success:
        return AppleIcons.checkCircle;
      case AppleToastType.error:
        return AppleIcons.error;
      case AppleToastType.warning:
        return AppleIcons.warning;
      case AppleToastType.info:
        return AppleIcons.info;
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = _getColor();
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Positioned(
      top: MediaQuery.of(context).padding.top + 16,
      left: 16,
      right: 16,
      child: SlideTransition(
        position: _slideAnimation,
        child: FadeTransition(
          opacity: _fadeAnimation,
          child: GestureDetector(
            onTap: widget.onTap ?? widget.onDismiss,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(14),
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 14,
                  ),
                  decoration: BoxDecoration(
                    color: isDark
                        ? Colors.black.withValues(alpha: 0.8)
                        : Colors.white.withValues(alpha: 0.9),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: color.withValues(alpha: 0.3),
                      width: 1,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.1),
                        blurRadius: 20,
                        offset: const Offset(0, 8),
                      ),
                    ],
                  ),
                  child: Row(
                    children: [
                      // 图标
                      Container(
                        padding: const EdgeInsets.all(8),
                        decoration: BoxDecoration(
                          color: color.withValues(alpha: 0.15),
                          shape: BoxShape.circle,
                        ),
                        child: Icon(
                          _getIcon(),
                          color: color,
                          size: 20,
                        ),
                      ),
                      const SizedBox(width: 12),
                      // 消息文本
                      Expanded(
                        child: Text(
                          widget.message,
                          style: AppleTokens.typography.body.copyWith(
                            fontWeight: FontWeight.w500,
                          ),
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      // 关闭按钮
                      IconButton(
                        icon: Icon(
                          AppleIcons.close,
                          size: 18,
                          color: AppleColors.tertiaryLabel(context),
                        ),
                        onPressed: widget.onDismiss,
                        padding: EdgeInsets.zero,
                        constraints: const BoxConstraints(),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Apple风格加载Toast
///
/// Legacy: 请勿在新代码中使用；请优先使用 `GlobalToast.showLoading`。
@Deprecated('Legacy Apple LoadingToast 已废弃，请使用 GlobalToast.showLoading')
class AppleLoadingToast {
  static OverlayEntry? _currentEntry;

  /// 显示加载Toast
  static void show(
    BuildContext context, {
    String message = '加载中...',
  }) {
    hide();

    final overlay = Overlay.of(context);
    _currentEntry = OverlayEntry(
      builder: (context) => _AppleLoadingToastWidget(
        message: message,
      ),
    );

    overlay.insert(_currentEntry!);
  }

  /// 隐藏加载Toast
  static void hide() {
    if (_currentEntry != null) {
      _currentEntry!.remove();
      _currentEntry = null;
    }
  }
}

/// Apple Loading Toast Widget
class _AppleLoadingToastWidget extends StatelessWidget {
  final String message;

  const _AppleLoadingToastWidget({
    required this.message,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Center(
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
          child: Container(
            padding: const EdgeInsets.symmetric(
              horizontal: 24,
              vertical: 20,
            ),
            decoration: BoxDecoration(
              color: isDark
                  ? Colors.black.withValues(alpha: 0.8)
                  : Colors.white.withValues(alpha: 0.9),
              borderRadius: BorderRadius.circular(16),
              boxShadow: AppleTokens.shadows.card,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                const SizedBox(
                  width: 40,
                  height: 40,
                  child: CircularProgressIndicator(
                    strokeWidth: 3,
                    valueColor: AlwaysStoppedAnimation<Color>(
                      AppleColors.blue,
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                Text(
                  message,
                  style: AppleTokens.typography.body.copyWith(
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
