import 'package:flutter/material.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';

/// 全局浮动提示框工具类
/// 从左上方由左向右曲线动画飘出，位于所有窗口最上层
class GlobalToast {
  static OverlayEntry? _currentEntry;
  static bool _isShowing = false;

  /// 显示加载中提示
  static void showLoading(
    BuildContext context,
    String message,
  ) {
    if (_isShowing) {
      hide(); // 先隐藏之前的
    }

    _isShowing = true;
    _currentEntry = _createToastEntry(
      context: context,
      message: message,
      type: _ToastType.loading,
    );

    Overlay.of(context).insert(_currentEntry!);
  }

  /// 显示成功提示
  static void showSuccess(
    BuildContext context,
    String message, {
    Duration duration = const Duration(seconds: 3),
  }) {
    if (_isShowing) {
      hide(); // 先隐藏之前的
    }

    _isShowing = true;
    _currentEntry = _createToastEntry(
      context: context,
      message: message,
      type: _ToastType.success,
    );

    Overlay.of(context).insert(_currentEntry!);

    // 自动隐藏
    Future.delayed(duration, () {
      hide();
    });
  }

  /// 显示失败提示
  static void showError(
    BuildContext context,
    String message, {
    Duration duration = const Duration(seconds: 3),
  }) {
    if (_isShowing) {
      hide(); // 先隐藏之前的
    }

    _isShowing = true;
    _currentEntry = _createToastEntry(
      context: context,
      message: message,
      type: _ToastType.error,
    );

    Overlay.of(context).insert(_currentEntry!);

    // 自动隐藏
    Future.delayed(duration, () {
      hide();
    });
  }

  /// 🆕 显示信息提示
  static void showInfo(
    BuildContext context,
    String message, {
    Duration duration = const Duration(seconds: 3),
  }) {
    if (_isShowing) {
      hide(); // 先隐藏之前的
    }

    _isShowing = true;
    _currentEntry = _createToastEntry(
      context: context,
      message: message,
      type: _ToastType.info,
    );

    Overlay.of(context).insert(_currentEntry!);

    // 自动隐藏
    Future.delayed(duration, () {
      hide();
    });
  }

  /// 隐藏提示框
  static void hide() {
    if (_currentEntry != null && _isShowing) {
      _currentEntry!.remove();
      _currentEntry = null;
      _isShowing = false;
    }
  }

  /// 创建提示框 OverlayEntry
  static OverlayEntry _createToastEntry({
    required BuildContext context,
    required String message,
    required _ToastType type,
  }) {
    return OverlayEntry(
      builder: (context) => _GlobalToastWidget(
        message: message,
        type: type,
        onDismiss: hide,
      ),
    );
  }
}

/// 提示框类型
enum _ToastType {
  loading,
  success,
  error,
  info, // 🆕 信息提示
}

/// 全局提示框 Widget
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
      duration: const Duration(milliseconds: 400),
      vsync: this,
    );

    // 🔧 从左向右滑入（曲线动画）
    _slideAnimation = Tween<Offset>(
      begin: const Offset(-1.0, 0.0), // 从屏幕左侧外
      end: Offset.zero, // 到正常位置
    ).animate(CurvedAnimation(
      parent: _controller,
      curve: Curves.easeOutCubic, // 平滑曲线
    ));

    // 淡入动画
    _fadeAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _controller,
      curve: Curves.easeIn,
    ));

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
    Color backgroundColor;
    IconData iconData;
    Color iconColor;
    bool showLoading = false;

    switch (widget.type) {
      case _ToastType.loading:
        backgroundColor = Colors.blue.shade50;
        iconData = Icons.info;
        iconColor = Colors.blue;
        showLoading = true;
        break;
      case _ToastType.success:
        backgroundColor = Colors.green.shade50;
        iconData = Icons.check_circle;
        iconColor = Colors.green;
        break;
      case _ToastType.error:
        backgroundColor = Colors.red.shade50;
        iconData = Icons.error;
        iconColor = Colors.red;
        break;
      case _ToastType.info: // 🆕 信息提示
        backgroundColor = Colors.orange.shade50;
        iconData = Icons.info_outline;
        iconColor = Colors.orange;
        break;
    }

    return Positioned(
      top: 16,
      left: 16,
      right: 16,
      child: SlideTransition(
        position: _slideAnimation,
        child: FadeTransition(
          opacity: _fadeAnimation,
          child: Material(
            color: Colors.transparent,
            child: Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: backgroundColor,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: widget.type == _ToastType.loading
                      ? Colors.blue.shade200
                      : (widget.type == _ToastType.success
                          ? Colors.green.shade200
                          : (widget.type == _ToastType.error
                              ? Colors.red.shade200
                              : Colors.orange.shade200)), // 🆕 info 边框颜色
                  width: 1.5,
                ),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.1),
                    blurRadius: 12,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Row(
                children: [
                  // 图标或加载动画
                  if (showLoading)
                    SpinKitThreeBounce(
                      color: iconColor,
                      size: 20.0,
                    )
                  else
                    Icon(iconData, color: iconColor, size: 24),

                  const SizedBox(width: 12),

                  // 消息文本
                  Expanded(
                    child: Text(
                      widget.message,
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w500,
                        color: Colors.grey.shade800,
                      ),
                    ),
                  ),

                  // 关闭按钮（非加载状态）
                  if (!showLoading)
                    IconButton(
                      icon: const Icon(Icons.close, size: 20),
                      onPressed: _dismiss,
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                      visualDensity: VisualDensity.compact,
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
