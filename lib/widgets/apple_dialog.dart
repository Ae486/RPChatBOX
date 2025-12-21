import 'package:flutter/material.dart';
import 'dart:ui';
import '../design_system/apple_tokens.dart';

/// Apple风格对话框
class AppleDialog {
  /// 显示确认对话框
  static Future<bool?> showConfirm(
    BuildContext context, {
    required String title,
    required String message,
    String confirmText = '确定',
    String cancelText = '取消',
    bool isDestructive = false,
  }) {
    return showDialog<bool>(
      context: context,
      builder: (context) => _AppleAlertDialog(
        title: title,
        message: message,
        actions: [
          AppleDialogAction(
            text: cancelText,
            onPressed: () => Navigator.of(context).pop(false),
          ),
          AppleDialogAction(
            text: confirmText,
            isPrimary: true,
            isDestructive: isDestructive,
            onPressed: () => Navigator.of(context).pop(true),
          ),
        ],
      ),
    );
  }

  /// 显示信息对话框
  static Future<void> showInfo(
    BuildContext context, {
    required String title,
    required String message,
    String buttonText = '确定',
  }) {
    return showDialog(
      context: context,
      builder: (context) => _AppleAlertDialog(
        title: title,
        message: message,
        actions: [
          AppleDialogAction(
            text: buttonText,
            isPrimary: true,
            onPressed: () => Navigator.of(context).pop(),
          ),
        ],
      ),
    );
  }

  /// 显示自定义对话框
  static Future<T?> show<T>(
    BuildContext context, {
    required String title,
    String? message,
    Widget? content,
    required List<AppleDialogAction> actions,
  }) {
    return showDialog<T>(
      context: context,
      builder: (context) => _AppleAlertDialog(
        title: title,
        message: message,
        content: content,
        actions: actions,
      ),
    );
  }

  /// 显示底部菜单
  static Future<T?> showActionSheet<T>(
    BuildContext context, {
    String? title,
    String? message,
    required List<AppleSheetAction<T>> actions,
    String cancelText = '取消',
  }) {
    return showModalBottomSheet<T>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (context) => _AppleActionSheet<T>(
        title: title,
        message: message,
        actions: actions,
        cancelText: cancelText,
      ),
    );
  }
}

/// Apple Alert Dialog Widget
class _AppleAlertDialog extends StatelessWidget {
  final String title;
  final String? message;
  final Widget? content;
  final List<AppleDialogAction> actions;

  const _AppleAlertDialog({
    required this.title,
    this.message,
    this.content,
    required this.actions,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Dialog(
      backgroundColor: Colors.transparent,
      elevation: 0,
      insetPadding: const EdgeInsets.symmetric(horizontal: 40),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(14),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
          child: Container(
            decoration: BoxDecoration(
              color: isDark
                  ? Colors.black.withValues(alpha: 0.8)
                  : Colors.white.withValues(alpha: 0.95),
              borderRadius: BorderRadius.circular(14),
              boxShadow: AppleTokens.shadows.card,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // 标题和消息
                Padding(
                  padding: const EdgeInsets.fromLTRB(24, 24, 24, 16),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        title,
                        style: AppleTokens.typography.title3.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      if (message != null) ...[
                        const SizedBox(height: 8),
                        Text(
                          message!,
                          style: AppleTokens.typography.body.copyWith(
                            color: AppleColors.secondaryLabel(context),
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ],
                      if (content != null) ...[
                        const SizedBox(height: 16),
                        content!,
                      ],
                    ],
                  ),
                ),

                // 分隔线
                Divider(
                  height: 1,
                  thickness: 0.5,
                  color: AppleColors.separator(context),
                ),

                // 操作按钮
                if (actions.length == 1)
                  _buildSingleAction(context, actions[0])
                else if (actions.length == 2)
                  _buildTwoActions(context, actions)
                else
                  _buildMultipleActions(context, actions),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSingleAction(
    BuildContext context,
    AppleDialogAction action,
  ) {
    return SizedBox(
      width: double.infinity,
      height: 44,
      child: TextButton(
        onPressed: action.onPressed,
        style: TextButton.styleFrom(
          shape: const RoundedRectangleBorder(),
        ),
        child: Text(
          action.text,
          style: AppleTokens.typography.body.copyWith(
            color: action.isDestructive
                ? AppleColors.red
                : AppleColors.blue,
            fontWeight: action.isPrimary ? FontWeight.w600 : FontWeight.w400,
          ),
        ),
      ),
    );
  }

  Widget _buildTwoActions(
    BuildContext context,
    List<AppleDialogAction> actions,
  ) {
    return Row(
      children: [
        Expanded(
          child: SizedBox(
            height: 44,
            child: TextButton(
              onPressed: actions[0].onPressed,
              style: TextButton.styleFrom(
                shape: const RoundedRectangleBorder(),
              ),
              child: Text(
                actions[0].text,
                style: AppleTokens.typography.body.copyWith(
                  color: actions[0].isDestructive
                      ? AppleColors.red
                      : AppleColors.blue,
                  fontWeight: FontWeight.w400,
                ),
              ),
            ),
          ),
        ),
        Container(
          width: 0.5,
          height: 44,
          color: AppleColors.separator(context),
        ),
        Expanded(
          child: SizedBox(
            height: 44,
            child: TextButton(
              onPressed: actions[1].onPressed,
              style: TextButton.styleFrom(
                shape: const RoundedRectangleBorder(),
              ),
              child: Text(
                actions[1].text,
                style: AppleTokens.typography.body.copyWith(
                  color: actions[1].isDestructive
                      ? AppleColors.red
                      : AppleColors.blue,
                  fontWeight: actions[1].isPrimary
                      ? FontWeight.w600
                      : FontWeight.w400,
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildMultipleActions(
    BuildContext context,
    List<AppleDialogAction> actions,
  ) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: actions.map((action) {
        final isLast = action == actions.last;
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: double.infinity,
              height: 44,
              child: TextButton(
                onPressed: action.onPressed,
                style: TextButton.styleFrom(
                  shape: const RoundedRectangleBorder(),
                ),
                child: Text(
                  action.text,
                  style: AppleTokens.typography.body.copyWith(
                    color: action.isDestructive
                        ? AppleColors.red
                        : AppleColors.blue,
                    fontWeight:
                        action.isPrimary ? FontWeight.w600 : FontWeight.w400,
                  ),
                ),
              ),
            ),
            if (!isLast)
              Divider(
                height: 1,
                thickness: 0.5,
                color: AppleColors.separator(context),
              ),
          ],
        );
      }).toList(),
    );
  }
}

/// Dialog Action
class AppleDialogAction {
  final String text;
  final VoidCallback onPressed;
  final bool isPrimary;
  final bool isDestructive;

  const AppleDialogAction({
    required this.text,
    required this.onPressed,
    this.isPrimary = false,
    this.isDestructive = false,
  });
}

/// Apple Action Sheet Widget
class _AppleActionSheet<T> extends StatelessWidget {
  final String? title;
  final String? message;
  final List<AppleSheetAction<T>> actions;
  final String cancelText;

  const _AppleActionSheet({
    this.title,
    this.message,
    required this.actions,
    required this.cancelText,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // 主内容
            ClipRRect(
              borderRadius: BorderRadius.circular(14),
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
                child: Container(
                  decoration: BoxDecoration(
                    color: isDark
                        ? Colors.black.withValues(alpha: 0.8)
                        : Colors.white.withValues(alpha: 0.95),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // 标题和消息
                      if (title != null || message != null)
                        Padding(
                          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              if (title != null)
                                Text(
                                  title!,
                                  style: AppleTokens.typography.footnote
                                      .copyWith(
                                    color: AppleColors.secondaryLabel(context),
                                    fontWeight: FontWeight.w600,
                                  ),
                                  textAlign: TextAlign.center,
                                ),
                              if (message != null) ...[
                                const SizedBox(height: 4),
                                Text(
                                  message!,
                                  style: AppleTokens.typography.caption2
                                      .copyWith(
                                    color: AppleColors.tertiaryLabel(context),
                                  ),
                                  textAlign: TextAlign.center,
                                ),
                              ],
                            ],
                          ),
                        ),

                      // 操作项
                      ...actions.asMap().entries.map((entry) {
                        final index = entry.key;
                        final action = entry.value;

                        return Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            if (index > 0 || title != null || message != null)
                              Divider(
                                height: 1,
                                thickness: 0.5,
                                color: AppleColors.separator(context),
                              ),
                            InkWell(
                              onTap: () {
                                Navigator.of(context).pop(action.value);
                              },
                              child: Container(
                                width: double.infinity,
                                padding: const EdgeInsets.symmetric(
                                  horizontal: 16,
                                  vertical: 16,
                                ),
                                child: Row(
                                  children: [
                                    if (action.icon != null) ...[
                                      Icon(
                                        action.icon,
                                        size: 22,
                                        color: action.isDestructive
                                            ? AppleColors.red
                                            : AppleColors.blue,
                                      ),
                                      const SizedBox(width: 12),
                                    ],
                                    Expanded(
                                      child: Text(
                                        action.text,
                                        style:
                                            AppleTokens.typography.body.copyWith(
                                          color: action.isDestructive
                                              ? AppleColors.red
                                              : (isDark
                                                  ? Colors.white
                                                  : Colors.black),
                                          fontWeight: FontWeight.w400,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ],
                        );
                      }),
                    ],
                  ),
                ),
              ),
            ),

            const SizedBox(height: 8),

            // 取消按钮
            ClipRRect(
              borderRadius: BorderRadius.circular(14),
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
                child: Container(
                  width: double.infinity,
                  decoration: BoxDecoration(
                    color: isDark
                        ? Colors.black.withValues(alpha: 0.8)
                        : Colors.white.withValues(alpha: 0.95),
                    borderRadius: BorderRadius.circular(14),
                  ),
                  child: TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    style: TextButton.styleFrom(
                      padding: const EdgeInsets.symmetric(vertical: 16),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(14),
                      ),
                    ),
                    child: Text(
                      cancelText,
                      style: AppleTokens.typography.body.copyWith(
                        color: AppleColors.blue,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Sheet Action
class AppleSheetAction<T> {
  final String text;
  final T value;
  final IconData? icon;
  final bool isDestructive;

  const AppleSheetAction({
    required this.text,
    required this.value,
    this.icon,
    this.isDestructive = false,
  });
}
