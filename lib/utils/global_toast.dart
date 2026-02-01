import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';

import '../chat_ui/owui/owui_icons.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';

/// 全局浮动提示框工具类（OWUI 风格）
///
/// 从左上方由左向右动画飘出，位于 Overlay 最上层。
class GlobalToast {
  static OverlayEntry? _currentEntry;
  static bool _isShowing = false;
  static Timer? _autoDismissTimer;

  static void loading(BuildContext context, {required String message}) =>
      showLoading(context, message);

  static void success(
    BuildContext context, {
    required String message,
    Duration duration = const Duration(seconds: 3),
  }) =>
      showSuccess(context, message, duration: duration);

  static void error(
    BuildContext context, {
    required String message,
    Duration duration = const Duration(seconds: 3),
  }) =>
      showError(context, message, duration: duration);

  static void info(
    BuildContext context, {
    required String message,
    Duration duration = const Duration(seconds: 3),
  }) =>
      showInfo(context, message, duration: duration);

  static void warning(
    BuildContext context, {
    required String message,
    Duration duration = const Duration(seconds: 3),
  }) =>
      showWarning(context, message, duration: duration);

  static void showLoading(BuildContext context, String message) {
    _show(context, message: message, type: _ToastType.loading, duration: null);
  }

  static void showSuccess(
    BuildContext context,
    String message, {
    Duration duration = const Duration(seconds: 3),
  }) {
    _show(context, message: message, type: _ToastType.success, duration: duration);
  }

  static void showError(
    BuildContext context,
    String message, {
    Duration duration = const Duration(seconds: 3),
  }) {
    _show(context, message: message, type: _ToastType.error, duration: duration);
  }

  static void showInfo(
    BuildContext context,
    String message, {
    Duration duration = const Duration(seconds: 3),
  }) {
    _show(context, message: message, type: _ToastType.info, duration: duration);
  }

  static void showWarning(
    BuildContext context,
    String message, {
    Duration duration = const Duration(seconds: 3),
  }) {
    _show(context, message: message, type: _ToastType.warning, duration: duration);
  }

  static void hide() {
    _autoDismissTimer?.cancel();
    _autoDismissTimer = null;
    if (_currentEntry == null || !_isShowing) return;
    _currentEntry!.remove();
    _currentEntry = null;
    _isShowing = false;
  }

  static void _show(
    BuildContext context, {
    required String message,
    required _ToastType type,
    Duration? duration,
  }) {
    if (_isShowing) hide();

    _isShowing = true;
    _currentEntry = OverlayEntry(
      builder: (context) => _GlobalToastWidget(
        message: message,
        type: type,
        onDismiss: hide,
      ),
    );

    Overlay.of(context).insert(_currentEntry!);

    if (duration != null) {
      _autoDismissTimer?.cancel();
      _autoDismissTimer = Timer(duration, hide);
    }
  }
}

enum _ToastType { loading, success, error, info, warning }

class _GlobalToastWidget extends StatefulWidget {
  final String message;
  final _ToastType type;
  final VoidCallback onDismiss;

  const _GlobalToastWidget({
    required this.message,
    required this.type,
    required this.onDismiss,
  });

  @override
  State<_GlobalToastWidget> createState() => _GlobalToastWidgetState();
}

class _GlobalToastWidgetState extends State<_GlobalToastWidget>
    with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<Offset> _slideAnimation;
  late Animation<double> _fadeAnimation;

  @override
  void initState() {
    super.initState();

    _controller = AnimationController(
      duration: const Duration(milliseconds: 240),
      vsync: this,
    );

    _slideAnimation = Tween<Offset>(
      begin: const Offset(-1.0, 0.0),
      end: Offset.zero,
    ).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeOutCubic),
    );

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _controller, curve: Curves.easeOut),
    );

    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _dismiss() async {
    await _controller.reverse();
    widget.onDismiss();
  }

  @override
  Widget build(BuildContext context) {
    final tokens = context.owuiTokens;
    final colors = tokens.colors;
    final scale = tokens.uiScale;

    final scheme = Theme.of(context).colorScheme;

    final Color accent = switch (widget.type) {
      _ToastType.loading || _ToastType.info => scheme.primary,
      _ToastType.success => scheme.secondary,
      _ToastType.warning => scheme.tertiary,
      _ToastType.error => scheme.error,
    };

    final IconData icon = switch (widget.type) {
      _ToastType.loading => OwuiIcons.info,
      _ToastType.success => OwuiIcons.checkCircle,
      _ToastType.warning => OwuiIcons.warning,
      _ToastType.error => OwuiIcons.error,
      _ToastType.info => OwuiIcons.info,
    };

    final spacing = context.owuiSpacing;

    final topInset = MediaQuery.paddingOf(context).top;
    final toastTop = topInset + spacing.lg;

    final padding = EdgeInsets.symmetric(
      horizontal: spacing.md,
      vertical: spacing.sm,
    );

    final iconSize = 20 * scale;

    return Positioned(
      top: toastTop,
      left: spacing.lg,
      right: spacing.lg,
      child: SlideTransition(
        position: _slideAnimation,
        child: FadeTransition(
          opacity: _fadeAnimation,
          child: Material(
            color: Colors.transparent,
            child: Container(
              padding: padding,
              decoration: BoxDecoration(
                color: colors.surfaceCard,
                borderRadius: BorderRadius.circular(context.owuiRadius.rXl),
                border: Border.all(color: colors.borderSubtle),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.08),
                    blurRadius: 16 * scale,
                    offset: Offset(0, 6 * scale),
                  ),
                ],
              ),
              child: Row(
                children: [
                  if (widget.type == _ToastType.loading)
                    SpinKitThreeBounce(color: accent, size: iconSize)
                  else
                    Icon(icon, color: accent, size: iconSize),
                  SizedBox(width: spacing.sm),
                  Expanded(
                    child: Text(
                      widget.message,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color: colors.textPrimary,
                          ),
                    ),
                  ),
                  if (widget.type != _ToastType.loading)
                    IconButton(
                      icon: Icon(OwuiIcons.close, size: iconSize),
                      onPressed: _dismiss,
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                      visualDensity: VisualDensity.compact,
                      color: colors.textSecondary,
                      tooltip: '关闭',
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
