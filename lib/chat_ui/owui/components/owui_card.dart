/// INPUT: child +（可选）margin/padding/radius + OwuiTokens
/// OUTPUT: OwuiCard - OpenWebUI 风格 Card（surface + subtle border）
/// POS: UI 层 / Owui Components - 基础容器组件

import 'package:flutter/material.dart';

import '../owui_tokens_ext.dart';

class OwuiCard extends StatelessWidget {
  final Widget child;
  final EdgeInsetsGeometry? margin;
  final EdgeInsetsGeometry? padding;
  final double? radius;

  const OwuiCard({
    super.key,
    required this.child,
    this.margin,
    this.padding,
    this.radius,
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.owuiColors;
    final r = radius ?? context.owuiRadius.rXl;

    final content = padding == null
        ? child
        : Padding(padding: padding!, child: child);

    return Padding(
      padding: margin ?? EdgeInsets.zero,
      child: Material(
        color: colors.surfaceCard,
        clipBehavior: Clip.antiAlias,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(r),
          side: BorderSide(color: colors.borderSubtle),
        ),
        child: content,
      ),
    );
  }
}
