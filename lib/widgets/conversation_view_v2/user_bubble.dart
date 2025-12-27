/// INPUT: AttachedFileSnapshot/SelectionArea + OwuiChatTheme
/// OUTPUT: _buildUserBubble(), _buildAttachmentsPreview() - 被 builders 调用
/// POS: UI 层 / Chat / V2 - 用户气泡渲染

part of '../conversation_view_v2.dart';

mixin _ConversationViewV2UserBubbleMixin on _ConversationViewV2StateBase {
  Widget _buildUserBubble({required chat.TextMessage message}) {
    final attached = message.metadata?['attachedFiles'] as List?;
    final attachedFiles = attached
        ?.whereType<Map>()
        .map((e) => AttachedFileSnapshot.fromJson(e.cast<String, dynamic>()))
        .toList();

    final children = <Widget>[];

    if (attachedFiles != null && attachedFiles.isNotEmpty) {
      children.add(_buildAttachmentsPreview(attachedFiles));
    }

    if (message.text.isNotEmpty) {
      children.add(
        Text(
          message.text,
          style: TextStyle(
            color: OwuiPalette.textPrimary(context),
            fontSize: 15,
            height: 1.5,
          ),
        ),
      );
    }

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      // Preserve selection on mobile (long-press), use double-tap for actions.
      onDoubleTap: _isExportMode ? null : () => _showMessageActionsSheet(message),
      onSecondaryTap: _isExportMode ? null : () => _showMessageActionsSheet(message),
      child: Align(
        alignment: Alignment.centerRight,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              constraints: const BoxConstraints(maxWidth: 520),
              padding: const EdgeInsets.all(12),
              decoration: OwuiChatTheme.userBubbleDecoration(context),
              child: SelectionArea(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: children,
                ),
              ),
            ),
            _buildTokenFooter(message, isSentByMe: true),
            _buildAssistantVariantSwitcher(message),
          ],
        ),
      ),
    );
  }

  Widget _buildAssistantVariantSwitcher(chat.TextMessage message) {
    if (_isExportMode) return const SizedBox.shrink();

    final thread = _getThread(rebuildFromMessagesIfMismatch: false);
    final variants = _assistantVariantIdsForUser(message.id, thread);
    if (variants.length <= 1) return const SizedBox.shrink();

    final selected = thread.selectedChild[message.id];
    var index = selected == null ? -1 : variants.indexOf(selected);
    if (index < 0) index = variants.length - 1;

    final disabled = _isLoading || _streamController.isStreaming;
    final isDark = OwuiPalette.isDark(context);
    final fg = disabled
        ? OwuiPalette.textSecondary(context).withValues(alpha: 0.45)
        : OwuiPalette.textSecondary(context).withValues(alpha: 0.9);
    final bg = isDark
        ? Colors.white.withValues(alpha: 0.06)
        : Colors.black.withValues(alpha: 0.04);
    final border = isDark
        ? Colors.white.withValues(alpha: 0.10)
        : Colors.black.withValues(alpha: 0.08);

    Widget navButton(IconData icon, int delta) {
      return InkWell(
        onTap: disabled ? null : () => _switchAssistantVariant(message.id, delta),
        customBorder: const CircleBorder(),
        child: Padding(
          padding: const EdgeInsets.all(4),
          child: Icon(icon, size: 16, color: fg),
        ),
      );
    }

    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Align(
        alignment: Alignment.centerRight,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: border),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                navButton(Icons.chevron_left_rounded, -1),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 4),
                  child: Text(
                    '< ${index + 1}/${variants.length} >',
                    style: TextStyle(
                      fontSize: 11,
                      height: 1.1,
                      fontWeight: FontWeight.w600,
                      color: fg,
                    ),
                  ),
                ),
                navButton(Icons.chevron_right_rounded, 1),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildAttachmentsPreview(List<AttachedFileSnapshot> files) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ...files.map(
          (f) => Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              children: [
                const Icon(Icons.attach_file, size: 16),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    f.name,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: OwuiPalette.textPrimary(context),
                      fontSize: 13,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
        const Divider(height: 1),
        const SizedBox(height: 8),
      ],
    );
  }
}
