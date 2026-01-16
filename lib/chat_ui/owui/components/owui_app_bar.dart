/// INPUT: leading/title/actions/bottom + OwuiTokens
/// OUTPUT: OwuiAppBar - 带底部分割线的 AppBar 壳
/// POS: UI 层 / Owui Components - 页面级通用 AppBar

import 'package:flutter/material.dart';

import '../owui_tokens_ext.dart';

class OwuiAppBar extends StatelessWidget implements PreferredSizeWidget {
  final Widget? leading;
  final bool automaticallyImplyLeading;
  final Widget? title;
  final List<Widget>? actions;
  final PreferredSizeWidget? bottom;

  const OwuiAppBar({
    super.key,
    this.leading,
    this.automaticallyImplyLeading = true,
    this.title,
    this.actions,
    this.bottom,
  });

  @override
  Size get preferredSize {
    final bottomHeight = bottom?.preferredSize.height ?? 0;
    return Size.fromHeight(kToolbarHeight + bottomHeight + 1);
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.owuiColors;
    final bottomHeight = bottom?.preferredSize.height ?? 0;

    return AppBar(
      leading: leading,
      automaticallyImplyLeading: automaticallyImplyLeading,
      title: title,
      actions: actions,
      backgroundColor: colors.pageBg,
      foregroundColor: colors.textPrimary,
      elevation: 0,
      scrolledUnderElevation: 0,
      surfaceTintColor: Colors.transparent,
      centerTitle: false,
      bottom: PreferredSize(
        preferredSize: Size.fromHeight(bottomHeight + 1),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (bottom != null) bottom!,
            Container(height: 1, color: colors.borderSubtle),
          ],
        ),
      ),
    );
  }
}
