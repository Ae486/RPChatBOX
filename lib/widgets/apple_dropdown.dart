import 'package:flutter/material.dart';
import '../design_system/apple_tokens.dart';
import '../design_system/apple_icons.dart';

/// Apple风格下拉选择框
class AppleDropdown<T> extends StatelessWidget {
  final T? value;
  final List<DropdownMenuItem<T>> items;
  final void Function(T?)? onChanged;
  final String? labelText;
  final String? hintText;
  final String? helperText;
  final String? errorText;
  final IconData? prefixIcon;
  final bool enabled;

  const AppleDropdown({
    super.key,
    this.value,
    required this.items,
    this.onChanged,
    this.labelText,
    this.hintText,
    this.helperText,
    this.errorText,
    this.prefixIcon,
    this.enabled = true,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Label
        if (labelText != null) ...[
          Text(
            labelText!,
            style: AppleTokens.typography.footnote.copyWith(
              color: errorText != null
                  ? AppleColors.red
                  : AppleColors.secondaryLabel(context),
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 6),
        ],

        // Dropdown Container
        Container(
          decoration: BoxDecoration(
            color: isDark
                ? Colors.white.withValues(alpha: 0.05)
                : Colors.black.withValues(alpha: 0.03),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: errorText != null
                  ? AppleColors.red
                  : AppleColors.separator(context),
              width: 1,
            ),
          ),
          child: DropdownButtonFormField<T>(
            initialValue: value,
            items: items,
            onChanged: enabled ? onChanged : null,
            decoration: InputDecoration(
              hintText: hintText,
              hintStyle: AppleTokens.typography.body.copyWith(
                color: AppleColors.tertiaryLabel(context),
              ),
              prefixIcon: prefixIcon != null
                  ? Icon(
                      prefixIcon,
                      size: 20,
                      color: AppleColors.secondaryLabel(context),
                    )
                  : null,
              border: InputBorder.none,
              contentPadding: const EdgeInsets.symmetric(
                horizontal: 16,
                vertical: 12,
              ),
              counterText: '',
            ),
            icon: Icon(
              AppleIcons.arrowDown,
              size: 20,
              color: enabled
                  ? AppleColors.secondaryLabel(context)
                  : AppleColors.tertiaryLabel(context),
            ),
            isExpanded: true,
            style: AppleTokens.typography.body.copyWith(
              color: enabled
                  ? (isDark ? Colors.white : Colors.black)
                  : AppleColors.tertiaryLabel(context),
            ),
            dropdownColor: isDark ? Colors.grey.shade900 : Colors.white,
          ),
        ),

        // Helper/Error Text
        if (errorText != null || helperText != null) ...[
          const SizedBox(height: 6),
          Text(
            errorText ?? helperText!,
            style: AppleTokens.typography.caption2.copyWith(
              color: errorText != null
                  ? AppleColors.red
                  : AppleColors.tertiaryLabel(context),
            ),
          ),
        ],
      ],
    );
  }
}
