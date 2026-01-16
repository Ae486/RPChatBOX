/// INPUT: ConversationViewV2State.conversation/chatController, ExportService
/// OUTPUT: enterExportMode(), _exportSelectedMessages() - 被 ConversationViewHost/菜单调用
/// POS: UI 层 / Chat / V2 - 批量导出模式

part of '../conversation_view_v2.dart';

mixin _ConversationViewV2ExportMixin on _ConversationViewV2StateBase {
  void enterExportMode() {
    if (_isDisposed) return;
    if (_isLoading || _streamController.isStreaming) {
      GlobalToast.warning(context, message: '请先停止输出再进入导出模式');
      return;
    }

    if (!mounted) return;
    setState(() {
      _isExportMode = true;
      _selectedMessageIds.clear();
    });
  }

  void _exitExportMode() {
    if (_isDisposed) return;
    if (!mounted) return;
    setState(() {
      _isExportMode = false;
      _selectedMessageIds.clear();
    });
  }

  void _toggleMessageSelection(String messageId) {
    if (!_isExportMode) return;
    if (!mounted || _isDisposed) return;

    // Only allow selecting persisted messages.
    final exists = widget.conversation.messages.any((m) => m.id == messageId);
    if (!exists) {
      GlobalToast.warning(context, message: '该消息尚未落盘，暂不支持导出');
      return;
    }

    setState(() {
      if (_selectedMessageIds.contains(messageId)) {
        _selectedMessageIds.remove(messageId);
      } else {
        _selectedMessageIds.add(messageId);
      }
    });
  }

  void _selectAllMessages() {
    if (!_isExportMode) return;
    if (!mounted || _isDisposed) return;

    setState(() {
      _selectedMessageIds
        ..clear()
        ..addAll(widget.conversation.messages.map((m) => m.id));
    });
  }

  void _deselectAllMessages() {
    if (!_isExportMode) return;
    if (!mounted || _isDisposed) return;
    setState(() {
      _selectedMessageIds.clear();
    });
  }

  Future<void> _exportSelectedMessages() async {
    if (!_isExportMode) return;
    if (!mounted || _isDisposed) return;

    final selectedMessages = widget.conversation.messages
        .where((m) => _selectedMessageIds.contains(m.id))
        .toList(growable: false);

    if (selectedMessages.isEmpty) {
      GlobalToast.warning(context, message: '请先选择要导出的消息');
      return;
    }

    final format = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('导出消息'),
        content: Text(
          '已选择 ${selectedMessages.length} 条消息，选择导出格式',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop('txt'),
            child: const Text('纯文本'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop('md'),
            child: const Text('Markdown'),
          ),
        ],
      ),
    );

    if (format == null) return;
    if (!mounted || _isDisposed) return;

    try {
      final content = format == 'md'
          ? ExportService.exportMessagesToMarkdown(
              selectedMessages,
              widget.conversation.title,
            )
          : ExportService.exportMessagesToText(
              selectedMessages,
              widget.conversation.title,
            );

      final fileName = ExportService.generateMultiMessageFileName(
        widget.conversation.title,
        selectedMessages.length,
        format,
      );

      final filePath = await ExportService.saveToFile(content, fileName);
      await Clipboard.setData(ClipboardData(text: filePath));
      if (!mounted || _isDisposed) return;

      GlobalToast.success(
        context,
        message: '已导出 ${selectedMessages.length} 条消息，路径已复制到剪贴板',
      );
      _exitExportMode();
    } catch (e) {
      if (!mounted || _isDisposed) return;
      GlobalToast.error(context, message: '导出失败: $e');
    }
  }

  Widget _wrapExportSelectable({
    required chat.Message message,
    required Widget child,
  }) {
    if (!_isExportMode) return child;

    final selected = _selectedMessageIds.contains(message.id);
    final isDark = OwuiPalette.isDark(context);
    final primary = Theme.of(context).colorScheme.primary;

    Widget checkIndicator() {
      return Container(
        width: 22,
        height: 22,
        decoration: BoxDecoration(
          color: selected
              ? primary
              : (isDark ? const Color(0xFF0D0D0D) : Colors.white),
          shape: BoxShape.circle,
          border: Border.all(
            color: selected
                ? primary.withValues(alpha: 0.8)
                : (isDark
                    ? Colors.white.withValues(alpha: 0.18)
                    : Colors.black.withValues(alpha: 0.14)),
          ),
        ),
        child: selected
            ? Icon(
                OwuiIcons.check,
                size: 16,
                color: Theme.of(context).colorScheme.onPrimary,
              )
            : null,
      );
    }

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => _toggleMessageSelection(message.id),
      child: Stack(
        fit: StackFit.passthrough,
        children: [
          child,
          if (selected)
            Positioned.fill(
              child: IgnorePointer(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(24),
                  child: ColoredBox(
                    color: primary.withValues(alpha: isDark ? 0.10 : 0.06),
                  ),
                ),
              ),
            ),
          Positioned(
            top: 8,
            right: 8,
            child: IgnorePointer(child: checkIndicator()),
          ),
        ],
      ),
    );
  }

  Widget _buildExportModeToolbar() {
    final selectedCount = _selectedMessageIds.length;
    final totalCount = widget.conversation.messages.length;
    final isDark = OwuiPalette.isDark(context);

    return Material(
      color: isDark ? const Color(0xFF0D0D0D) : Colors.white,
      elevation: 1,
      child: SafeArea(
        bottom: false,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 8),
          height: 52,
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(color: OwuiPalette.borderSubtle(context)),
            ),
          ),
          child: Row(
            children: [
              IconButton(
                onPressed: _exitExportMode,
                icon: const Icon(OwuiIcons.close),
                tooltip: '退出导出模式',
              ),
              const SizedBox(width: 4),
              const Text('导出模式'),
              const Spacer(),
              Text(
                '$selectedCount/$totalCount',
                style: TextStyle(
                  color: Theme.of(context)
                      .colorScheme
                      .onSurface
                      .withValues(alpha: 0.6),
                ),
              ),
              const SizedBox(width: 8),
              TextButton(
                onPressed: totalCount == 0 ? null : _selectAllMessages,
                child: const Text('全选'),
              ),
              TextButton(
                onPressed: totalCount == 0 ? null : _deselectAllMessages,
                child: const Text('清空'),
              ),
              const SizedBox(width: 4),
              FilledButton(
                onPressed: selectedCount == 0 ? null : _exportSelectedMessages,
                child: const Text('导出'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
