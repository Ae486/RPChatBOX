/// INPUT: MyAppState（themeMode/uiScale/fontFamily/codeFontFamily）
/// OUTPUT: DisplaySettingsPage - 显示设置（缩放/字体/主题等）
/// POS: UI 层 / Pages - 外观设置页

import 'package:flutter/material.dart';

import '../chat_ui/owui/components/owui_app_bar.dart';
import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/components/owui_dialog.dart';
import '../chat_ui/owui/components/owui_scaffold.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../main.dart';

class DisplaySettingsPage extends StatelessWidget {
  const DisplaySettingsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final app = MyApp.of(context);
    final uiScale = app?.uiScale ?? 1.0;
    final uiFontFamily = app?.uiFontFamily ?? 'system';
    final uiCodeFontFamily = app?.uiCodeFontFamily ?? 'system_mono';

    return OwuiScaffold(
      appBar: const OwuiAppBar(title: Text('显示设置')),
      body: ListView(
        padding: EdgeInsets.all(context.owuiSpacing.lg),
        children: [
          _UiScaleCard(value: uiScale),
          SizedBox(height: context.owuiSpacing.lg),
          _FontSettingsCard(
            uiFontFamily: uiFontFamily,
            uiCodeFontFamily: uiCodeFontFamily,
          ),
        ],
      ),
    );
  }
}

class _UiScaleCard extends StatelessWidget {
  final double value;

  const _UiScaleCard({required this.value});

  static const double _min = 0.85;
  static const double _max = 1.25;
  static const double _step = 0.05;

  @override
  Widget build(BuildContext context) {
    final colors = context.owuiColors;
    final scaleLabel = value.toStringAsFixed(2);
    final divisions = ((_max - _min) / _step).round();

    return OwuiCard(
      padding: EdgeInsets.all(context.owuiSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('界面缩放', style: Theme.of(context).textTheme.titleMedium),
          SizedBox(height: context.owuiSpacing.sm),
          Text(
            '缩放会影响字体、按钮、输入框等交互尺寸。',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: colors.textSecondary,
                ),
          ),
          SizedBox(height: context.owuiSpacing.md),
          Row(
            children: [
              Expanded(
                child: Slider(
                  value: value.clamp(_min, _max),
                  min: _min,
                  max: _max,
                  divisions: divisions,
                  label: scaleLabel,
                  onChanged: (v) => MyApp.of(context)?.setDisplaySettings(
                        uiScale: v,
                        persist: false,
                      ),
                  onChangeEnd: (v) => MyApp.of(context)?.setDisplaySettings(
                        uiScale: v,
                        persist: true,
                      ),
                ),
              ),
              SizedBox(width: context.owuiSpacing.md),
              SizedBox(
                width: 56,
                child: Text(
                  scaleLabel,
                  textAlign: TextAlign.right,
                  style: Theme.of(context).textTheme.labelLarge,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Option {
  final String id;
  final String label;

  const _Option(this.id, this.label);
}

class _FontSettingsCard extends StatelessWidget {
  final String uiFontFamily;
  final String uiCodeFontFamily;

  const _FontSettingsCard({
    required this.uiFontFamily,
    required this.uiCodeFontFamily,
  });

  static const _globalFontOptions = <_Option>[
    _Option('system', '系统默认'),
    _Option('noto_sans', 'Noto Sans'),
    _Option('noto_serif', 'Noto Serif'),
  ];

  static const _codeFontOptions = <_Option>[
    _Option('system_mono', '系统等宽'),
    _Option('jetbrains_mono', 'JetBrains Mono'),
    _Option('noto_sans_mono', 'Noto Sans Mono'),
  ];

  String _labelFor(String id, List<_Option> options) {
    for (final o in options) {
      if (o.id == id) return o.label;
    }
    return id;
  }

  Future<void> _pickOption(
    BuildContext context, {
    required String title,
    required String currentId,
    required List<_Option> options,
    required ValueChanged<String> onSelected,
  }) async {
    final selected = await showDialog<String>(
      context: context,
      builder: (dialogContext) {
        return OwuiDialog(
          title: Text(title),
          content: SizedBox(
            width: double.maxFinite,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final o in options) ...[
                  ListTile(
                    title: Text(o.label),
                    trailing:
                        o.id == currentId ? const Icon(OwuiIcons.check) : null,
                    onTap: () => Navigator.pop(dialogContext, o.id),
                  ),
                  if (o != options.last)
                    Divider(height: 1, color: dialogContext.owuiColors.borderSubtle),
                ],
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('取消'),
            ),
          ],
        );
      },
    );

    if (selected == null || selected == currentId) return;
    onSelected(selected);
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.owuiColors;
    final spacing = context.owuiSpacing;

    final globalLabel = _labelFor(uiFontFamily, _globalFontOptions);
    final codeLabel = _labelFor(uiCodeFontFamily, _codeFontOptions);
    final badgeBg =
        Theme.of(context).colorScheme.primary.withValues(alpha: 0.12);

    return OwuiCard(
      child: Column(
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              spacing.lg,
              spacing.lg,
              spacing.lg,
              spacing.sm,
            ),
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    '字体设置',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: spacing.sm,
                    vertical: 2,
                  ),
                  decoration: BoxDecoration(
                    color: badgeBg,
                    borderRadius: BorderRadius.circular(context.owuiRadius.rFull),
                    border: Border.all(color: colors.borderSubtle),
                  ),
                  child: Text(
                    'New',
                    style: Theme.of(context).textTheme.labelSmall?.copyWith(
                          color: Theme.of(context).colorScheme.primary,
                          fontWeight: FontWeight.w600,
                        ),
                  ),
                ),
              ],
            ),
          ),
          ListTile(
            leading: const Icon(OwuiIcons.type),
            title: const Text('全局字体'),
            subtitle: Text(globalLabel),
            trailing: const Icon(OwuiIcons.chevronRight),
            onTap: () => _pickOption(
              context,
              title: '全局字体',
              currentId: uiFontFamily,
              options: _globalFontOptions,
              onSelected: (id) => MyApp.of(context)?.setDisplaySettings(
                    uiFontFamily: id,
                    persist: true,
                  ),
            ),
          ),
          Divider(height: 1, color: colors.borderSubtle),
          ListTile(
            leading: const Icon(OwuiIcons.code),
            title: const Text('代码字体'),
            subtitle: Text(codeLabel),
            trailing: const Icon(OwuiIcons.chevronRight),
            onTap: () => _pickOption(
              context,
              title: '代码字体',
              currentId: uiCodeFontFamily,
              options: _codeFontOptions,
              onSelected: (id) => MyApp.of(context)?.setDisplaySettings(
                    uiCodeFontFamily: id,
                    persist: true,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}
