/// INPUT: BuildContext + message + kind/duration
/// OUTPUT: OwuiSnackBars.show/success/warning/error - 统一浮动 SnackBar
/// POS: UI 层 / Owui Components - 提示反馈组件（避免各处重复样式）

import 'package:flutter/material.dart';

import '../owui_tokens_ext.dart';

enum OwuiSnackBarKind { info, success, warning, error }

class OwuiSnackBars {
  static void show(
    BuildContext context, {
    required String message,
    OwuiSnackBarKind kind = OwuiSnackBarKind.info,
    Duration duration = const Duration(seconds: 3),
  }) {
    final colors = context.owuiColors;

    final scheme = Theme.of(context).colorScheme;

    final Color accent = switch (kind) {
      OwuiSnackBarKind.info => scheme.primary,
      OwuiSnackBarKind.success => scheme.secondary,
      OwuiSnackBarKind.warning => scheme.tertiary,
      OwuiSnackBarKind.error => scheme.error,
    };

    final snackBar = SnackBar(
      behavior: SnackBarBehavior.floating,
      backgroundColor: Colors.transparent,
      elevation: 0,
      duration: duration,
      content: Container(
        padding: EdgeInsets.symmetric(
          horizontal: context.owuiSpacing.md,
          vertical: context.owuiSpacing.sm,
        ),
        decoration: BoxDecoration(
          color: colors.surfaceCard,
          borderRadius: BorderRadius.circular(context.owuiRadius.rXl),
          border: Border.all(color: colors.borderSubtle),
        ),
        child: Row(
          children: [
            Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: accent, shape: BoxShape.circle),
            ),
            SizedBox(width: context.owuiSpacing.sm),
            Expanded(
              child: Text(
                message,
                style:
                    Theme.of(context).textTheme.bodyMedium?.copyWith(
                          color: colors.textPrimary,
                        ) ??
                        TextStyle(color: colors.textPrimary),
              ),
            ),
          ],
        ),
      ),
    );

    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(snackBar);
  }

  static void success(
    BuildContext context, {
    required String message,
    Duration duration = const Duration(seconds: 3),
  }) {
    show(
      context,
      message: message,
      kind: OwuiSnackBarKind.success,
      duration: duration,
    );
  }

  static void warning(
    BuildContext context, {
    required String message,
    Duration duration = const Duration(seconds: 3),
  }) {
    show(
      context,
      message: message,
      kind: OwuiSnackBarKind.warning,
      duration: duration,
    );
  }

  static void error(
    BuildContext context, {
    required String message,
    Duration duration = const Duration(seconds: 4),
  }) {
    show(
      context,
      message: message,
      kind: OwuiSnackBarKind.error,
      duration: duration,
    );
  }
}
