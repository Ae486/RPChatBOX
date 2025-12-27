import 'package:flutter/material.dart';

import '../owui_tokens_ext.dart';

class OwuiDialog extends StatelessWidget {
  final Widget? title;
  final Widget? content;
  final List<Widget>? actions;

  const OwuiDialog({super.key, this.title, this.content, this.actions});

  @override
  Widget build(BuildContext context) {
    final colors = context.owuiColors;
    final radius = context.owuiRadius.rXl;

    return AlertDialog(
      backgroundColor: colors.surfaceCard,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(radius),
        side: BorderSide(color: colors.borderSubtle),
      ),
      title: title,
      content: content,
      actions: actions,
    );
  }
}
