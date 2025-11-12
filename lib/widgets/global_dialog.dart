import 'package:flutter/material.dart';

/// 弹窗类型
enum DialogType {
  success('✅ 成功', Colors.green),
  error('❌ 错误', Colors.red),
  warning('⚠️ 警告', Colors.orange),
  info('ℹ️ 信息', Colors.blue),
  question('❓ 确认', Colors.blue);

  final String label;
  final Color color;
  const DialogType(this.label, this.color);
}

/// 全局统一弹窗工具类
class GlobalDialog {
  /// 显示成功弹窗
  static Future<void> showSuccess(
    BuildContext context, {
    required String title,
    required String message,
    String? confirmText,
    VoidCallback? onConfirm,
  }) async {
    return show(
      context,
      type: DialogType.success,
      title: title,
      message: message,
      confirmText: confirmText,
      onConfirm: onConfirm,
    );
  }

  /// 显示错误弹窗
  static Future<void> showError(
    BuildContext context, {
    required String title,
    required String message,
    String? confirmText,
    VoidCallback? onConfirm,
    String? errorCode,
    String? details,
  }) async {
    return show(
      context,
      type: DialogType.error,
      title: title,
      message: message,
      confirmText: confirmText,
      onConfirm: onConfirm,
      errorCode: errorCode,
      details: details,
    );
  }

  /// 显示警告弹窗
  static Future<void> showWarning(
    BuildContext context, {
    required String title,
    required String message,
    String? confirmText,
    VoidCallback? onConfirm,
  }) async {
    return show(
      context,
      type: DialogType.warning,
      title: title,
      message: message,
      confirmText: confirmText,
      onConfirm: onConfirm,
    );
  }

  /// 显示信息弹窗
  static Future<void> showInfo(
    BuildContext context, {
    required String title,
    required String message,
    String? confirmText,
    VoidCallback? onConfirm,
  }) async {
    return show(
      context,
      type: DialogType.info,
      title: title,
      message: message,
      confirmText: confirmText,
      onConfirm: onConfirm,
    );
  }

  /// 显示确认弹窗（带取消和确认按钮）
  static Future<bool?> showConfirm(
    BuildContext context, {
    required String title,
    required String message,
    String? confirmText,
    String? cancelText,
  }) async {
    return showDialog<bool?>(
      context: context,
      barrierDismissible: false,
      builder: (context) => _GlobalDialogWidget(
        type: DialogType.question,
        title: title,
        message: message,
        confirmText: confirmText ?? '确认',
        cancelText: cancelText ?? '取消',
        showCancel: true,
      ),
    );
  }

  /// 通用弹窗方法
  static Future<void> show(
    BuildContext context, {
    required DialogType type,
    required String title,
    required String message,
    String? confirmText,
    VoidCallback? onConfirm,
    String? errorCode,
    String? details,
    bool canPop = true,
  }) async {
    final result = await showDialog<bool>(
      context: context,
      barrierDismissible: canPop,
      builder: (context) => _GlobalDialogWidget(
        type: type,
        title: title,
        message: message,
        confirmText: confirmText,
        errorCode: errorCode,
        details: details,
      ),
    );

    if (result == true && onConfirm != null) {
      onConfirm();
    }
  }
}

/// 全局弹窗 Widget
class _GlobalDialogWidget extends StatefulWidget {
  final DialogType type;
  final String title;
  final String message;
  final String? confirmText;
  final String? cancelText;
  final String? errorCode;
  final String? details;
  final bool showCancel;

  const _GlobalDialogWidget({
    required this.type,
    required this.title,
    required this.message,
    this.confirmText,
    this.cancelText,
    this.errorCode,
    this.details,
    this.showCancel = false,
  });

  @override
  State<_GlobalDialogWidget> createState() => _GlobalDialogWidgetState();
}

class _GlobalDialogWidgetState extends State<_GlobalDialogWidget> {
  bool _showDetails = false;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return AlertDialog(
      backgroundColor: isDark ? Colors.grey.shade900 : Colors.white,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: BorderSide(
          color: widget.type.color.withOpacity(0.3),
          width: 2,
        ),
      ),
      title: Row(
        children: [
          Icon(
            _getIconData(),
            color: widget.type.color,
            size: 28,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              widget.title,
              style: TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: widget.type.color,
              ),
            ),
          ),
        ],
      ),
      content: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            // 主消息
            Text(
              widget.message,
              style: TextStyle(
                fontSize: 15,
                height: 1.5,
                color: isDark ? Colors.grey.shade200 : Colors.grey.shade800,
              ),
            ),

            // 错误代码
            if (widget.errorCode != null) ...[
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: widget.type.color.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: widget.type.color.withOpacity(0.3),
                  ),
                ),
                child: Row(
                  children: [
                    Icon(Icons.code, size: 16, color: widget.type.color),
                    const SizedBox(width: 8),
                    Expanded(
                      child: SelectableText(
                        'Code: ${widget.errorCode}',
                        style: TextStyle(
                          fontSize: 12,
                          fontFamily: 'monospace',
                          color: widget.type.color,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],

            // 详情信息（可折叠）
            if (widget.details != null && widget.details!.isNotEmpty) ...[
              const SizedBox(height: 12),
              MouseRegion(
                cursor: SystemMouseCursors.click,
                child: GestureDetector(
                  onTap: () {
                    setState(() {
                      _showDetails = !_showDetails;
                    });
                  },
                  child: Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    decoration: BoxDecoration(
                      color:
                          isDark ? Colors.grey.shade800 : Colors.grey.shade100,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          _showDetails ? Icons.expand_less : Icons.expand_more,
                          size: 18,
                          color: Colors.grey,
                        ),
                        const SizedBox(width: 8),
                        Text(
                          _showDetails ? '隐藏详情' : '显示详情',
                          style: const TextStyle(
                            fontSize: 13,
                            color: Colors.grey,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              if (_showDetails) ...[
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color:
                        isDark ? Colors.grey.shade800 : Colors.grey.shade100,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                      color: Colors.grey.withOpacity(0.3),
                    ),
                  ),
                  child: SelectableText(
                    widget.details!,
                    style: TextStyle(
                      fontSize: 12,
                      fontFamily: 'monospace',
                      color: isDark ? Colors.grey.shade300 : Colors.grey.shade700,
                      height: 1.6,
                    ),
                  ),
                ),
              ],
            ],
          ],
        ),
      ),
      actions: [
        // 取消按钮（仅在需要时显示）
        if (widget.showCancel)
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            style: TextButton.styleFrom(
              foregroundColor: Colors.grey,
            ),
            child: Text(widget.cancelText ?? '取消'),
          ),

        // 确认按钮
        ElevatedButton(
          onPressed: () => Navigator.pop(context, true),
          style: ElevatedButton.styleFrom(
            backgroundColor: widget.type.color,
            foregroundColor: Colors.white,
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          ),
          child: Text(
            widget.confirmText ?? '确定',
            style: const TextStyle(fontWeight: FontWeight.bold),
          ),
        ),
      ],
      actionsPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
    );
  }

  IconData _getIconData() {
    switch (widget.type) {
      case DialogType.success:
        return Icons.check_circle_outline;
      case DialogType.error:
        return Icons.error_outline;
      case DialogType.warning:
        return Icons.warning_amber_rounded;
      case DialogType.info:
        return Icons.info_outline;
      case DialogType.question:
        return Icons.help_outline;
    }
  }
}
