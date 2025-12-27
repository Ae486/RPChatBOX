import 'package:flutter/material.dart';

import '../owui_tokens_ext.dart';

class OwuiTextField extends StatelessWidget {
  final TextEditingController? controller;
  final FocusNode? focusNode;
  final bool autofocus;
  final String? hintText;
  final ValueChanged<String>? onChanged;
  final TextStyle? style;
  final TextInputAction? textInputAction;
  final int maxLines;
  final Widget? prefixIcon;

  const OwuiTextField({
    super.key,
    this.controller,
    this.focusNode,
    this.autofocus = false,
    this.hintText,
    this.onChanged,
    this.style,
    this.textInputAction,
    this.maxLines = 1,
    this.prefixIcon,
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.owuiColors;
    final spacing = context.owuiSpacing;
    final theme = Theme.of(context);

    final baseTextStyle = theme.textTheme.bodyLarge ?? const TextStyle();
    final mergedStyle = baseTextStyle.merge(style);
    final effectiveStyle = mergedStyle.color == null
        ? mergedStyle.copyWith(color: colors.textPrimary)
        : mergedStyle;

    return TextField(
      controller: controller,
      focusNode: focusNode,
      autofocus: autofocus,
      maxLines: maxLines,
      textInputAction: textInputAction,
      onChanged: onChanged,
      style: effectiveStyle,
      decoration: InputDecoration(
        hintText: hintText,
        hintStyle: baseTextStyle.copyWith(color: colors.textSecondary),
        prefixIcon: prefixIcon,
        filled: true,
        fillColor: colors.surfaceCard,
        contentPadding: EdgeInsets.symmetric(
          horizontal: spacing.md,
          vertical: spacing.sm,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(context.owuiRadius.r3xl),
          borderSide: BorderSide(color: colors.borderSubtle),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(context.owuiRadius.r3xl),
          borderSide: BorderSide(color: colors.borderSubtle),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(context.owuiRadius.r3xl),
          borderSide: BorderSide(color: colors.borderStrong),
        ),
      ),
    );
  }
}

class OwuiSearchField extends StatelessWidget {
  final TextEditingController controller;
  final bool autofocus;
  final String? hintText;
  final ValueChanged<String>? onChanged;

  const OwuiSearchField({
    super.key,
    required this.controller,
    this.autofocus = false,
    this.hintText,
    this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return OwuiTextField(
      controller: controller,
      autofocus: autofocus,
      hintText: hintText,
      onChanged: onChanged,
      textInputAction: TextInputAction.search,
      prefixIcon: const Icon(Icons.search_rounded),
    );
  }
}
