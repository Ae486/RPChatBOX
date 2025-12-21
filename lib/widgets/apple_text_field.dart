import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../design_system/apple_tokens.dart';
import '../design_system/apple_icons.dart';

/// Apple风格文本输入框
/// 
/// 特性：
/// - 圆角边框（8-12px）
/// - 聚焦状态蓝色边框
/// - 错误状态红色边框
/// - 清除按钮
/// - 密码可见性切换
/// - 表单验证支持
class AppleTextField extends StatefulWidget {
  final TextEditingController? controller;
  final String? labelText;
  final String? hintText;
  final String? helperText;
  final String? errorText;
  final IconData? prefixIcon;
  final IconData? suffixIcon;
  final bool obscureText;
  final bool showClearButton;
  final TextInputType? keyboardType;
  final int? maxLines;
  final int? minLines;
  final int? maxLength;
  final bool enabled;
  final bool readOnly;
  final void Function(String)? onChanged;
  final void Function(String)? onSubmitted;
  final void Function()? onTap;
  final List<TextInputFormatter>? inputFormatters;
  final TextInputAction? textInputAction;
  final FocusNode? focusNode;
  final EdgeInsetsGeometry? contentPadding;
  final String? Function(String?)? validator; // 🆕 表单验证

  const AppleTextField({
    super.key,
    this.controller,
    this.labelText,
    this.hintText,
    this.helperText,
    this.errorText,
    this.prefixIcon,
    this.suffixIcon,
    this.obscureText = false,
    this.showClearButton = false,
    this.keyboardType,
    this.maxLines = 1,
    this.minLines,
    this.maxLength,
    this.enabled = true,
    this.readOnly = false,
    this.onChanged,
    this.onSubmitted,
    this.onTap,
    this.inputFormatters,
    this.textInputAction,
    this.focusNode,
    this.contentPadding,
    this.validator, // 🆕
  });

  @override
  State<AppleTextField> createState() => _AppleTextFieldState();
}

class _AppleTextFieldState extends State<AppleTextField> {
  late FocusNode _focusNode;
  bool _obscureText = false;
  bool _hasFocus = false;

  @override
  void initState() {
    super.initState();
    _focusNode = widget.focusNode ?? FocusNode();
    _obscureText = widget.obscureText;
    _focusNode.addListener(_onFocusChange);
  }

  @override
  void dispose() {
    if (widget.focusNode == null) {
      _focusNode.dispose();
    } else {
      _focusNode.removeListener(_onFocusChange);
    }
    super.dispose();
  }

  void _onFocusChange() {
    setState(() {
      _hasFocus = _focusNode.hasFocus;
    });
  }

  Color _getBorderColor(BuildContext context) {
    if (widget.errorText != null) {
      return AppleColors.red;
    }
    if (_hasFocus) {
      return AppleColors.blue;
    }
    return AppleColors.separator(context);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Label
        if (widget.labelText != null) ...[
          Text(
            widget.labelText!,
            style: AppleTokens.typography.footnote.copyWith(
              color: widget.errorText != null
                  ? AppleColors.red
                  : AppleColors.secondaryLabel(context),
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 6),
        ],

        // TextField Container
        AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          decoration: BoxDecoration(
            color: isDark
                ? Colors.white.withValues(alpha: 0.05)
                : Colors.black.withValues(alpha: 0.03),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: _getBorderColor(context),
              width: _hasFocus ? 2 : 1,
            ),
          ),
          child: TextFormField(
            controller: widget.controller,
            focusNode: _focusNode,
            obscureText: _obscureText,
            keyboardType: widget.keyboardType,
            maxLines: widget.obscureText ? 1 : widget.maxLines,
            minLines: widget.minLines,
            maxLength: widget.maxLength,
            enabled: widget.enabled,
            readOnly: widget.readOnly,
            onChanged: widget.onChanged,
            onFieldSubmitted: widget.onSubmitted,
            onTap: widget.onTap,
            inputFormatters: widget.inputFormatters,
            textInputAction: widget.textInputAction,
            validator: widget.validator,
            style: AppleTokens.typography.body.copyWith(
              color: widget.enabled
                  ? (isDark ? Colors.white : Colors.black)
                  : AppleColors.tertiaryLabel(context),
            ),
            decoration: InputDecoration(
              hintText: widget.hintText,
              hintStyle: AppleTokens.typography.body.copyWith(
                color: AppleColors.tertiaryLabel(context),
              ),
              prefixIcon: widget.prefixIcon != null
                  ? Icon(
                      widget.prefixIcon,
                      size: 20,
                      color: AppleColors.secondaryLabel(context),
                    )
                  : null,
              suffixIcon: _buildSuffixIcon(context),
              border: InputBorder.none,
              contentPadding: widget.contentPadding ??
                  const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 12,
                  ),
              counterText: '',
            ),
          ),
        ),

        // Helper/Error Text
        if (widget.errorText != null || widget.helperText != null) ...[
          const SizedBox(height: 6),
          Text(
            widget.errorText ?? widget.helperText!,
            style: AppleTokens.typography.caption2.copyWith(
              color: widget.errorText != null
                  ? AppleColors.red
                  : AppleColors.tertiaryLabel(context),
            ),
          ),
        ],
      ],
    );
  }

  Widget? _buildSuffixIcon(BuildContext context) {
    final hasText = widget.controller?.text.isNotEmpty ?? false;

    // 密码可见性切换
    if (widget.obscureText) {
      return IconButton(
        icon: Icon(
          _obscureText ? AppleIcons.visibilityOff : AppleIcons.visibility,
          size: 20,
          color: AppleColors.secondaryLabel(context),
        ),
        onPressed: () {
          setState(() {
            _obscureText = !_obscureText;
          });
        },
      );
    }

    // 清除按钮
    if (widget.showClearButton && hasText && widget.enabled) {
      return IconButton(
        icon: Icon(
          AppleIcons.close,
          size: 18,
          color: AppleColors.secondaryLabel(context),
        ),
        onPressed: () {
          widget.controller?.clear();
          widget.onChanged?.call('');
        },
      );
    }

    // 自定义后缀图标
    if (widget.suffixIcon != null) {
      return Icon(
        widget.suffixIcon,
        size: 20,
        color: AppleColors.secondaryLabel(context),
      );
    }

    return null;
  }
}

/// Apple风格搜索框
class AppleSearchField extends StatelessWidget {
  final TextEditingController? controller;
  final String? hintText;
  final void Function(String)? onChanged;
  final void Function(String)? onSubmitted;
  final bool autofocus;
  final FocusNode? focusNode;

  const AppleSearchField({
    super.key,
    this.controller,
    this.hintText = '搜索',
    this.onChanged,
    this.onSubmitted,
    this.autofocus = false,
    this.focusNode,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    return Container(
      height: 40,
      decoration: BoxDecoration(
        color: isDark
            ? Colors.white.withValues(alpha: 0.1)
            : Colors.black.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(10),
      ),
      child: TextField(
        controller: controller,
        focusNode: focusNode,
        autofocus: autofocus,
        onChanged: onChanged,
        onSubmitted: onSubmitted,
        style: AppleTokens.typography.body,
        decoration: InputDecoration(
          hintText: hintText,
          hintStyle: AppleTokens.typography.body.copyWith(
            color: AppleColors.tertiaryLabel(context),
          ),
          prefixIcon: Icon(
            AppleIcons.search,
            size: 20,
            color: AppleColors.secondaryLabel(context),
          ),
          suffixIcon: controller?.text.isNotEmpty ?? false
              ? IconButton(
                  icon: Icon(
                    AppleIcons.close,
                    size: 18,
                    color: AppleColors.secondaryLabel(context),
                  ),
                  onPressed: () {
                    controller?.clear();
                    onChanged?.call('');
                  },
                )
              : null,
          border: InputBorder.none,
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 12,
            vertical: 10,
          ),
        ),
      ),
    );
  }
}

/// Apple风格多行文本框
class AppleTextArea extends StatelessWidget {
  final TextEditingController? controller;
  final String? labelText;
  final String? hintText;
  final String? helperText;
  final String? errorText;
  final int minLines;
  final int maxLines;
  final int? maxLength;
  final bool enabled;
  final void Function(String)? onChanged;
  final EdgeInsetsGeometry? contentPadding;
  final String? Function(String?)? validator; // 🆕

  const AppleTextArea({
    super.key,
    this.controller,
    this.labelText,
    this.hintText,
    this.helperText,
    this.errorText,
    this.minLines = 3,
    this.maxLines = 8,
    this.maxLength,
    this.enabled = true,
    this.onChanged,
    this.contentPadding,
    this.validator, // 🆕
  });

  @override
  Widget build(BuildContext context) {
    return AppleTextField(
      controller: controller,
      labelText: labelText,
      hintText: hintText,
      helperText: helperText,
      errorText: errorText,
      minLines: minLines,
      maxLines: maxLines,
      maxLength: maxLength,
      enabled: enabled,
      onChanged: onChanged,
      validator: validator, // 🆕
      contentPadding: contentPadding ??
          const EdgeInsets.symmetric(
            horizontal: 16,
            vertical: 14,
          ),
    );
  }
}
