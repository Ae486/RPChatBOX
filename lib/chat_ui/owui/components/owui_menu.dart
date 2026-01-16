/// INPUT: PopupMenuItemBuilder/onSelected 等 + OwuiTokens
/// OUTPUT: OwuiMenuButton<T> - OpenWebUI 风格 PopupMenuButton
/// POS: UI 层 / Owui Components - 菜单样式壳

import 'package:flutter/material.dart';

import '../owui_tokens_ext.dart';

class OwuiMenuButton<T> extends StatelessWidget {
  final Widget? icon;
  final String? tooltip;
  final PopupMenuItemBuilder<T> itemBuilder;
  final PopupMenuItemSelected<T>? onSelected;
  final PopupMenuCanceled? onCanceled;
  final Offset offset;
  final EdgeInsetsGeometry padding;

  const OwuiMenuButton({
    super.key,
    this.icon,
    this.tooltip,
    required this.itemBuilder,
    this.onSelected,
    this.onCanceled,
    this.offset = Offset.zero,
    this.padding = const EdgeInsets.all(8),
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.owuiColors;

    return PopupMenuButton<T>(
      icon: icon,
      tooltip: tooltip,
      itemBuilder: itemBuilder,
      onSelected: onSelected,
      onCanceled: onCanceled,
      offset: offset,
      padding: padding,
      color: colors.surfaceCard,
      elevation: 2,
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(context.owuiRadius.rXl),
        side: BorderSide(color: colors.borderSubtle),
      ),
    );
  }
}
