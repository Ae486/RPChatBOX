/// INPUT: ConversationSettings/ModelServiceManager + flutter_chat_ui ComposerHeightNotifier
/// OUTPUT: OwuiComposer - V2 输入区（附件/联网/配置/模型/发送-停止）
/// POS: UI 层 / Chat / Owui - OpenWebUI 风格输入组件

import 'dart:io';
import 'dart:ui';

import 'package:file_picker/file_picker.dart' as file_picker;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_chat_ui/flutter_chat_ui.dart';
import 'package:provider/provider.dart';

import '../../../design_system/design_tokens.dart';
import '../../../models/attached_file.dart';
import '../../../models/conversation_settings.dart';
import '../../../models/model_config.dart';
import '../../../models/provider_config.dart';
import '../../../services/model_service_manager.dart';
import '../../../utils/global_toast.dart';
import '../../../widgets/conversation_config_dialog.dart';
import '../palette.dart';
import 'owui_model_selector_sheet.dart';

class OwuiComposer extends StatefulWidget {
  final TextEditingController textController;
  final bool isStreaming;
  final VoidCallback onSend;
  final VoidCallback onStop;
  final ModelServiceManager serviceManager;
  final ConversationSettings conversationSettings;
  final ValueChanged<ConversationSettings> onSettingsChanged;
  final bool attachmentBarVisible;

  /// Optional callback for the measured composer height (excluding bottom safe area).
  ///
  /// Useful for positioning external overlays relative to the top of the composer.
  final ValueChanged<double>? onHeightChanged;

  /// Optional background blur (glassmorphism). Default off.
  final double? sigmaX;
  final double? sigmaY;

  /// Whether to include bottom safe area padding in layout. Default true.
  final bool handleSafeArea;

  const OwuiComposer({
    super.key,
    required this.textController,
    required this.isStreaming,
    required this.onSend,
    required this.onStop,
    required this.serviceManager,
    required this.conversationSettings,
    required this.onSettingsChanged,
    this.attachmentBarVisible = true,
    this.onHeightChanged,
    this.sigmaX,
    this.sigmaY,
    this.handleSafeArea = true,
  });

  @override
  State<OwuiComposer> createState() => _OwuiComposerState();
}

class _OwuiComposerState extends State<OwuiComposer> {
  final _measureKey = GlobalKey();
  double? _lastMeasuredHeight;
  bool _pendingMeasure = false;

  final FocusNode _focusNode = FocusNode();
  late final ValueNotifier<bool> _hasTextNotifier;

  @override
  void initState() {
    super.initState();
    _hasTextNotifier = ValueNotifier<bool>(_hasText());
    widget.textController.addListener(_handleTextChanged);
    _focusNode.addListener(_handleFocusChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) => _measure());
  }

  @override
  void didUpdateWidget(covariant OwuiComposer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.textController != widget.textController) {
      oldWidget.textController.removeListener(_handleTextChanged);
      widget.textController.addListener(_handleTextChanged);
      _hasTextNotifier.value = _hasText();
    }
    WidgetsBinding.instance.addPostFrameCallback((_) => _measure());
  }

  @override
  void dispose() {
    widget.textController.removeListener(_handleTextChanged);
    _focusNode.removeListener(_handleFocusChanged);
    _hasTextNotifier.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  bool _hasText() => widget.textController.text.trim().isNotEmpty;

  void _handleTextChanged() {
    _hasTextNotifier.value = _hasText();
    _scheduleMeasure();
  }

  void _handleFocusChanged() {
    if (!mounted) return;
    setState(() {});
    _scheduleMeasure();
  }

  void _scheduleMeasure() {
    if (_pendingMeasure) return;
    _pendingMeasure = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _pendingMeasure = false;
      _measure();
    });
  }

  void _measure() {
    if (!mounted) return;
    final renderBox =
        _measureKey.currentContext?.findRenderObject() as RenderBox?;
    if (renderBox == null) return;

    final bottomSafeArea = widget.handleSafeArea
        ? MediaQuery.of(context).padding.bottom
        : 0.0;
    final heightWithoutSafeArea = renderBox.size.height - bottomSafeArea;

    if (_lastMeasuredHeight != null &&
        (_lastMeasuredHeight! - heightWithoutSafeArea).abs() < 0.5) {
      return;
    }
    _lastMeasuredHeight = heightWithoutSafeArea;
    context.read<ComposerHeightNotifier>().setHeight(heightWithoutSafeArea);
    widget.onHeightChanged?.call(heightWithoutSafeArea);
  }

  Future<void> _pickFiles() async {
    try {
      final result = await file_picker.FilePicker.platform.pickFiles(
        allowMultiple: true,
        type: file_picker.FileType.custom,
        allowedExtensions: const [
          // 图片文件
          'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg',
          // 文档文件
          'pdf', 'doc', 'docx', 'txt', 'md', 'rtf',
          // 代码文件
          'js', 'ts', 'dart', 'py', 'java', 'cpp', 'c', 'h', 'hpp',
          'cs', 'php', 'rb', 'go', 'rs', 'swift', 'kt',
          'html', 'htm', 'css', 'scss', 'less', 'sass',
          'json', 'xml', 'yaml', 'yml', 'toml', 'ini', 'cfg', 'conf',
          'sql', 'sh', 'bat', 'ps1', 'dockerfile',
          // 数据文件
          'csv', 'tsv', 'xls', 'xlsx',
          // 其他
          'log', 'gitignore', 'env', 'config',
        ],
      );

      if (result == null || result.files.isEmpty) return;

      final attachedFiles = <AttachedFile>[];
      for (final platformFile in result.files) {
        final path = platformFile.path;
        if (path == null) continue;
        final file = await AttachedFile.fromFile(
          File(path),
          widget.serviceManager.generateId(),
        );
        attachedFiles.add(file);
      }

      if (attachedFiles.isEmpty) return;

      var updatedSettings = widget.conversationSettings;
      for (final file in attachedFiles) {
        updatedSettings = updatedSettings.addFile(file);
      }
      widget.onSettingsChanged(updatedSettings);

      if (mounted) {
        GlobalToast.showSuccess(context, '成功添加 ${attachedFiles.length} 个文件');
      }
    } catch (e) {
      if (mounted) {
        GlobalToast.showError(context, '文件添加失败\n${e.toString()}');
      }
    }
  }

  void _toggleNetwork() {
    final updated = widget.conversationSettings.copyWith(
      enableNetwork: !widget.conversationSettings.enableNetwork,
    );
    widget.onSettingsChanged(updated);
  }

  void _showConfigDialog() {
    showDialog(
      context: context,
      builder: (context) => ConversationConfigDialog(
        settings: widget.conversationSettings,
        onSave: widget.onSettingsChanged,
      ),
    );
  }

  void _showModelSelector() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (context) => OwuiModelSelectorSheet(
        serviceManager: widget.serviceManager,
        currentModelId: widget.conversationSettings.selectedModelId,
        onModelSelected: (providerId, modelId) {
          final updated = widget.conversationSettings.copyWith(
            selectedProviderId: providerId,
            selectedModelId: modelId,
          );
          widget.onSettingsChanged(updated);
          Navigator.pop(context);
        },
      ),
    );
  }

  ({ProviderConfig provider, ModelConfig model})?
  _getCurrentModelWithProvider() {
    final modelId = widget.conversationSettings.selectedModelId;
    if (modelId == null) return null;
    final result = widget.serviceManager.getModelWithProvider(modelId);
    if (result == null) return null;
    return (provider: result.provider, model: result.model);
  }

  void _removeFile(AttachedFile file) {
    widget.onSettingsChanged(widget.conversationSettings.removeFile(file.id));
  }

  void _handleSendOrStop() {
    if (widget.isStreaming) {
      widget.onStop();
      return;
    }
    widget.onSend();
  }

  bool _canSend() {
    if (widget.isStreaming) return true;
    if (widget.conversationSettings.hasAttachedFiles) return true;
    return _hasText();
  }

  Map<ShortcutActivator, Intent> _shortcuts() {
    if (widget.isStreaming) return const <ShortcutActivator, Intent>{};
    return const <ShortcutActivator, Intent>{
      SingleActivator(LogicalKeyboardKey.enter): _SendIntent(),
    };
  }

  @override
  Widget build(BuildContext context) {
    final bottomSafeArea = widget.handleSafeArea
        ? MediaQuery.of(context).padding.bottom
        : 0.0;

    final containerBorder = BorderSide(
      color: OwuiPalette.borderSubtle(context),
    );
    final surface = OwuiPalette.pageBackground(context);
    final fieldSurface = OwuiPalette.surfaceCard(context);

    final currentModel = _getCurrentModelWithProvider();
    final hasFiles =
        widget.conversationSettings.hasAttachedFiles &&
        widget.attachmentBarVisible;

    final focusColor = Theme.of(
      context,
    ).colorScheme.primary.withValues(alpha: 0.35);
    final barBorderColor = _focusNode.hasFocus
        ? focusColor
        : containerBorder.color;

    final content = NotificationListener<SizeChangedLayoutNotification>(
      onNotification: (_) {
        _scheduleMeasure();
        return false;
      },
      child: SizeChangedLayoutNotifier(
        child: KeyedSubtree(
          key: _measureKey,
          child: Container(
            decoration: BoxDecoration(
              color: surface,
              border: Border(top: containerBorder),
            ),
            padding: EdgeInsets.fromLTRB(
              ChatBoxTokens.spacing.md,
              ChatBoxTokens.spacing.sm,
              ChatBoxTokens.spacing.md,
              ChatBoxTokens.spacing.sm + bottomSafeArea,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (hasFiles) _buildAttachedFilesPreview(),
                AnimatedContainer(
                  duration: const Duration(milliseconds: 140),
                  decoration: BoxDecoration(
                    color: fieldSurface,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: barBorderColor),
                  ),
                  padding: const EdgeInsets.fromLTRB(12, 12, 12, 10),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _buildInputField(),
                      const SizedBox(height: 10),
                      Row(
                        children: [
                          _buildActionButton(
                            tooltip: '上传文件',
                            icon: Icons.add_circle_outline,
                            onPressed: _pickFiles,
                          ),
                          const SizedBox(width: 6),
                          _buildActionButton(
                            tooltip: '联网',
                            icon: Icons.language,
                            isActive: widget.conversationSettings.enableNetwork,
                            onPressed: _toggleNetwork,
                          ),
                          const SizedBox(width: 6),
                          _buildActionButton(
                            tooltip: '对话配置',
                            icon: Icons.tune,
                            onPressed: _showConfigDialog,
                          ),
                          const Spacer(),
                          _buildModelPill(currentModel: currentModel),
                          const SizedBox(width: 10),
                          ValueListenableBuilder<bool>(
                            valueListenable: _hasTextNotifier,
                            builder: (context, _, __) {
                              return _buildSendButton();
                            },
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    final sigmaX = widget.sigmaX ?? 0;
    final sigmaY = widget.sigmaY ?? 0;
    final shouldUseBackdropFilter = sigmaX > 0 || sigmaY > 0;

    final body = ClipRect(
      child: shouldUseBackdropFilter
          ? BackdropFilter(
              filter: ImageFilter.blur(sigmaX: sigmaX, sigmaY: sigmaY),
              child: content,
            )
          : content,
    );

    // NOTE: `Positioned` must be the direct child of `flutter_chat_ui.Chat`'s
    // internal `Stack` (composerBuilder slot). Keep `Shortcuts/Actions` inside
    // the positioned content, otherwise the bottom positioning can be ignored
    // (esp. in release/profile builds).
    return Positioned(
      left: 0,
      right: 0,
      bottom: 0,
      child: Shortcuts(
        shortcuts: _shortcuts(),
        child: Actions(
          actions: <Type, Action<Intent>>{
            _SendIntent: CallbackAction<_SendIntent>(
              onInvoke: (_) {
                if (widget.isStreaming) return null;
                if (!_canSend()) return null;
                widget.onSend();
                return null;
              },
            ),
          },
          child: body,
        ),
      ),
    );
  }

  Widget _buildActionButton({
    required String tooltip,
    required IconData icon,
    bool isActive = false,
    required VoidCallback? onPressed,
  }) {
    final baseColor = isActive
        ? Theme.of(context).colorScheme.primary
        : OwuiPalette.textSecondary(context);

    return Tooltip(
      message: tooltip,
      child: IconButton(
        icon: Icon(icon),
        onPressed: onPressed,
        constraints: const BoxConstraints.tightFor(width: 40, height: 40),
        padding: EdgeInsets.zero,
        iconSize: 22,
        color: baseColor,
        splashRadius: 20,
      ),
    );
  }

  Widget _buildInputField() {
    final hintColor = OwuiPalette.textSecondary(context);
    final textColor = OwuiPalette.textPrimary(context);

    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 44 * 1, maxHeight: 44 * 3),
      child: TextField(
        controller: widget.textController,
        focusNode: _focusNode,
        minLines: 2,
        maxLines: 8,
        keyboardType: TextInputType.multiline,
        textInputAction: TextInputAction.newline,
        decoration: InputDecoration(
          isDense: true,
          contentPadding: EdgeInsets.zero,
          border: InputBorder.none,
          hintText: '输入消息...',
          hintStyle: TextStyle(color: hintColor),
        ),
        style: TextStyle(fontSize: 15, height: 1.45, color: textColor),
      ),
    );
  }

  Widget _buildModelPill({
    required ({ProviderConfig provider, ModelConfig model})? currentModel,
  }) {
    final label = currentModel?.model.displayName ?? '选择模型';
    final border = OwuiPalette.borderSubtle(context);
    final bg = OwuiPalette.surfaceCard(context);
    final textColor = OwuiPalette.textPrimary(context);
    final sub = OwuiPalette.textSecondary(context);

    return InkWell(
      onTap: _showModelSelector,
      borderRadius: BorderRadius.circular(999),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 170),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(999),
          border: Border.all(color: border),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.psychology, size: 18, color: sub),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                label,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 13,
                  color: textColor,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ),
            const SizedBox(width: 4),
            Icon(Icons.arrow_drop_down, size: 18, color: sub),
          ],
        ),
      ),
    );
  }

  Widget _buildSendButton() {
    final enabled = _canSend();
    final border = OwuiPalette.borderSubtle(context);

    final Color bgColor;
    final Color iconColor;
    if (widget.isStreaming) {
      bgColor = Theme.of(context).colorScheme.error.withValues(alpha: 0.14);
      iconColor = Theme.of(context).colorScheme.error;
    } else if (enabled) {
      bgColor = Theme.of(context).colorScheme.primary.withValues(alpha: 0.14);
      iconColor = Theme.of(context).colorScheme.primary;
    } else {
      bgColor = OwuiPalette.surfaceCard(context);
      iconColor = OwuiPalette.textSecondary(context);
    }

    return ConstrainedBox(
      constraints: const BoxConstraints.tightFor(width: 40, height: 40),
      child: Material(
        color: bgColor,
        shape: CircleBorder(side: BorderSide(color: border)),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: enabled ? _handleSendOrStop : null,
          child: Center(
            child: Icon(
              widget.isStreaming ? Icons.stop_circle : Icons.arrow_upward,
              size: 20,
              color: iconColor,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildAttachedFilesPreview() {
    final files = widget.conversationSettings.attachedFiles;
    final border = OwuiPalette.borderSubtle(context);
    final bg = OwuiPalette.surfaceCard(context);

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: border),
      ),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: files.map((file) {
          return InputChip(
            label: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 260),
              child: Text(
                file.name,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 12),
              ),
            ),
            avatar: Icon(_fileIcon(file.type), size: 18),
            onDeleted: () => _removeFile(file),
            deleteIcon: const Icon(Icons.close, size: 16),
            backgroundColor: bg,
            side: BorderSide(color: border),
            visualDensity: VisualDensity.compact,
          );
        }).toList(),
      ),
    );
  }

  IconData _fileIcon(FileType type) {
    switch (type) {
      case FileType.image:
        return Icons.image_outlined;
      case FileType.video:
        return Icons.movie_outlined;
      case FileType.audio:
        return Icons.audiotrack_outlined;
      case FileType.document:
        return Icons.description_outlined;
      case FileType.code:
        return Icons.code;
      case FileType.other:
        return Icons.insert_drive_file_outlined;
    }
  }
}

class _SendIntent extends Intent {
  const _SendIntent();
}
