/// INPUT: AttachedFileSnapshot/SelectionArea + OwuiChatTheme
/// OUTPUT: _buildUserBubble(), _buildAttachmentsPreview() - 被 builders 调用
/// POS: UI 层 / Chat / V2 - 用户气泡渲染

part of '../conversation_view_v2.dart';

mixin _ConversationViewV2UserBubbleMixin on _ConversationViewV2StateBase {
  Widget _buildUserBubble({required chat.TextMessage message}) {
    final uiScale = context.owui.uiScale;
    final attached = message.metadata?['attachedFiles'] as List?;
    final attachedFiles = attached
        ?.whereType<Map>()
        .map((e) => AttachedFileSnapshot.fromJson(e.cast<String, dynamic>()))
        .toList();

    final children = <Widget>[];

    if (attachedFiles != null && attachedFiles.isNotEmpty) {
      children.add(_buildAttachmentsPreview(attachedFiles, uiScale));
    }

    if (message.text.isNotEmpty) {
      children.add(
        Text(
          message.text,
          style: TextStyle(
            color: OwuiPalette.textPrimary(context),
            fontSize: 15 * uiScale,
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
              constraints: BoxConstraints(maxWidth: 520 * uiScale),
              padding: EdgeInsets.all(12 * uiScale),
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
            _buildAssistantVariantSwitcher(message, uiScale),
          ],
        ),
      ),
    );
  }

  Widget _buildAssistantVariantSwitcher(chat.TextMessage message, double uiScale) {
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
          padding: EdgeInsets.all(4 * uiScale),
          child: Icon(icon, size: 16 * uiScale, color: fg),
        ),
      );
    }

    return Padding(
      padding: EdgeInsets.only(top: 6 * uiScale),
      child: Align(
        alignment: Alignment.centerRight,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(999),
            border: Border.all(color: border),
          ),
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: 6 * uiScale, vertical: 2 * uiScale),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                navButton(OwuiIcons.chevronLeft, -1),
                Padding(
                  padding: EdgeInsets.symmetric(horizontal: 4 * uiScale),
                  child: Text(
                    '< ${index + 1}/${variants.length} >',
                    style: TextStyle(
                      fontSize: 11 * uiScale,
                      height: 1.1,
                      fontWeight: FontWeight.w600,
                      color: fg,
                    ),
                  ),
                ),
                navButton(OwuiIcons.chevronRight, 1),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildAttachmentsPreview(List<AttachedFileSnapshot> files, double uiScale) {
    // 分离图片和非图片文件
    final imageFiles = files.where((f) => f.isImage).toList();
    final otherFiles = files.where((f) => !f.isImage).toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 图片网格预览
        if (imageFiles.isNotEmpty)
          Padding(
            padding: EdgeInsets.only(bottom: 8 * uiScale),
            child: Wrap(
              spacing: 8 * uiScale,
              runSpacing: 8 * uiScale,
              children: imageFiles.map((f) => _buildImageThumbnail(f, uiScale)).toList(),
            ),
          ),
        // 其他文件列表
        ...otherFiles.map(
          (f) => Padding(
            padding: EdgeInsets.only(bottom: 8 * uiScale),
            child: Row(
              children: [
                Icon(OwuiIcons.attachment, size: 16 * uiScale),
                SizedBox(width: 6 * uiScale),
                Expanded(
                  child: Text(
                    f.name,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: OwuiPalette.textPrimary(context),
                      fontSize: 13 * uiScale,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
        if (files.isNotEmpty) ...[
          const Divider(height: 1),
          SizedBox(height: 8 * uiScale),
        ],
      ],
    );
  }

  /// 构建图片缩略图
  Widget _buildImageThumbnail(AttachedFileSnapshot file, double uiScale) {
    final size = 80.0 * uiScale;
    final imageFile = File(file.path);

    return GestureDetector(
      onTap: () => _showImagePreview(file),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8 * uiScale),
        child: FutureBuilder<bool>(
          future: imageFile.exists(),
          builder: (context, snapshot) {
            if (snapshot.data != true) {
              // 文件不存在，显示占位符
              return Container(
                width: size,
                height: size,
                color: OwuiPalette.isDark(context)
                    ? Colors.white.withValues(alpha: 0.1)
                    : Colors.black.withValues(alpha: 0.05),
                child: Icon(
                  OwuiIcons.brokenImage,
                  size: 24 * uiScale,
                  color: OwuiPalette.textSecondary(context),
                ),
              );
            }
            return Image.file(
              imageFile,
              width: size,
              height: size,
              fit: BoxFit.cover,
              cacheWidth: (size * 2).toInt(), // 2x 用于高清屏
              errorBuilder: (_, __, ___) => Container(
                width: size,
                height: size,
                color: OwuiPalette.isDark(context)
                    ? Colors.white.withValues(alpha: 0.1)
                    : Colors.black.withValues(alpha: 0.05),
                child: Icon(
                  OwuiIcons.brokenImage,
                  size: 24 * uiScale,
                  color: OwuiPalette.textSecondary(context),
                ),
              ),
            );
          },
        ),
      ),
    );
  }

  /// 显示图片预览
  void _showImagePreview(AttachedFileSnapshot file) {
    final imageFile = File(file.path);
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        backgroundColor: Colors.transparent,
        insetPadding: const EdgeInsets.all(16),
        child: Stack(
          alignment: Alignment.center,
          children: [
            // 图片
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: InteractiveViewer(
                minScale: 0.5,
                maxScale: 4.0,
                child: Image.file(
                  imageFile,
                  fit: BoxFit.contain,
                  errorBuilder: (_, __, ___) => Container(
                    padding: const EdgeInsets.all(32),
                    decoration: BoxDecoration(
                      color: Theme.of(ctx).colorScheme.surface,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(OwuiIcons.brokenImage, size: 48, color: OwuiPalette.textSecondary(ctx)),
                        const SizedBox(height: 8),
                        Text('无法加载图片', style: TextStyle(color: OwuiPalette.textSecondary(ctx))),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            // 关闭按钮
            Positioned(
              top: 0,
              right: 0,
              child: IconButton(
                onPressed: () => Navigator.of(ctx).pop(),
                icon: Container(
                  padding: const EdgeInsets.all(4),
                  decoration: BoxDecoration(
                    color: Colors.black54,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Icon(OwuiIcons.close, color: Colors.white, size: 20),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
