/// INPUT: flutter_chat_ui.Chat + builders + OwuiChatTheme/OwuiPalette
/// OUTPUT: build() - 组装 Chat 列表/Composer/滚动按钮
/// POS: UI 层 / Chat / V2 - 组装层（变更需重点手测布局/滚动）

part of '../conversation_view_v2.dart';

mixin _ConversationViewV2BuildMixin on _ConversationViewV2StateBase {
  @override
  Widget build(BuildContext context) {
    super.build(context);
    final chatTheme = OwuiChatTheme.chatTheme(context);
    final colors = context.owuiColors;

    final chatWidget = Chat(
      chatController: _chatController,
      currentUserId: _v2CurrentUserId,
      theme: chatTheme,
      backgroundColor: colors.pageBg,
      builders: chat.Builders(
        textMessageBuilder:
            (context, message, index, {required isSentByMe, groupStatus}) {
              if (isSentByMe) {
                return _wrapExportSelectable(
                  message: message,
                  child: _wrapHighlighted(
                    messageId: message.id,
                    child: _buildUserBubble(message: message),
                  ),
                );
              }

              final metadata = message.metadata ?? const <String, dynamic>{};
              final streaming = metadata['streaming'] == true;
              final modelName = metadata['modelName'] as String?;
              final providerName = metadata['providerName'] as String?;
              final data = streaming && _streamManager.hasStream(message.id)
                  ? _streamManager.getData(message.id)
                  : null;

              final body = GestureDetector(
                behavior: HitTestBehavior.opaque,
                onLongPress: _isExportMode
                    ? null
                    : () => _showMessageActionsSheet(message),
                onSecondaryTap: _isExportMode
                    ? null
                    : () => _showMessageActionsSheet(message),
                child: _wrapHighlighted(
                  messageId: message.id,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      OwuiAssistantMessage(
                        messageId: message.id,
                        createdAt: message.createdAt ?? DateTime.now(),
                        bodyMarkdown: message.text,
                        isStreaming: streaming,
                        modelName: modelName,
                        providerName: providerName,
                        streamData: data,
                      ),
                      _buildTokenFooter(message, isSentByMe: false),
                    ],
                  ),
                ),
              );

              return _wrapExportSelectable(message: message, child: body);
            },
        customMessageBuilder:
            (context, message, index, {required isSentByMe, groupStatus}) {
              final metadata = message.metadata ?? const <String, dynamic>{};
              if (metadata['type'] != 'thinking_message') {
                return const SizedBox.shrink();
              }

              final thinking = (metadata['thinking'] as String?) ?? '';
              final body = (metadata['body'] as String?) ?? '';
              final modelName = metadata['modelName'] as String?;
              final providerName = metadata['providerName'] as String?;

              final bodyWidget = GestureDetector(
                behavior: HitTestBehavior.opaque,
                onLongPress: _isExportMode
                    ? null
                    : () => _showMessageActionsSheet(message),
                onSecondaryTap: _isExportMode
                    ? null
                    : () => _showMessageActionsSheet(message),
                child: _wrapHighlighted(
                  messageId: message.id,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      OwuiAssistantMessage(
                        messageId: message.id,
                        createdAt: message.createdAt ?? DateTime.now(),
                        bodyMarkdown: body,
                        isStreaming: false,
                        modelName: modelName,
                        providerName: providerName,
                        streamData: StreamData(
                          streamId: message.id,
                          status: StreamStatus.completed,
                          startTime: message.createdAt,
                          content: body,
                          thinkingContent: thinking,
                          isThinkingOpen: false,
                        ),
                      ),
                      _buildTokenFooter(message, isSentByMe: false),
                    ],
                  ),
                ),
              );

              return _wrapExportSelectable(message: message, child: bodyWidget);
            },
        imageMessageBuilder:
            (context, message, index, {required isSentByMe, groupStatus}) {
              final source = message.source;
              Widget errorBuilder(
                BuildContext context,
                Object error,
                StackTrace? stackTrace,
              ) {
                return Container(
                  color: Colors.black.withValues(alpha: 0.06),
                  child: const Center(child: Icon(Icons.broken_image_outlined)),
                );
              }

              if (!_isProbablyNetworkUrl(source)) {
                final filePath = _toFilePathIfNeeded(source);
                final file = File(filePath);
                if (!file.existsSync()) {
                  return _wrapExportSelectable(
                    message: message,
                    child: _wrapHighlighted(
                      messageId: message.id,
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Container(
                            width: 240,
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: Colors.black.withValues(alpha: 0.06),
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(
                                color: Colors.black.withValues(alpha: 0.08),
                              ),
                            ),
                            child: Row(
                              children: [
                                const Icon(
                                  Icons.broken_image_outlined,
                                  size: 18,
                                ),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    '图片文件不存在',
                                    style: TextStyle(
                                      color: OwuiPalette.textSecondary(context),
                                      fontSize: 13,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          _buildTokenFooter(message, isSentByMe: isSentByMe),
                        ],
                      ),
                    ),
                  );
                }
                return _wrapExportSelectable(
                  message: message,
                  child: _wrapHighlighted(
                    messageId: message.id,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        FlyerChatImageMessage(
                          message: message,
                          index: index,
                          customImageProvider: FileImage(file),
                          errorBuilder: errorBuilder,
                        ),
                        _buildTokenFooter(message, isSentByMe: isSentByMe),
                      ],
                    ),
                  ),
                );
              }

              return _wrapExportSelectable(
                message: message,
                child: _wrapHighlighted(
                  messageId: message.id,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      FlyerChatImageMessage(
                        message: message,
                        index: index,
                        errorBuilder: errorBuilder,
                      ),
                      _buildTokenFooter(message, isSentByMe: isSentByMe),
                    ],
                  ),
                ),
              );
            },
        fileMessageBuilder:
            (context, message, index, {required isSentByMe, groupStatus}) {
              final body = GestureDetector(
                behavior: HitTestBehavior.opaque,
                onLongPress: _isExportMode
                    ? null
                    : () => _showMessageActionsSheet(message),
                onSecondaryTap: _isExportMode
                    ? null
                    : () => _showMessageActionsSheet(message),
                child: _wrapHighlighted(
                  messageId: message.id,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      FlyerChatFileMessage(message: message, index: index),
                      _buildTokenFooter(message, isSentByMe: false),
                    ],
                  ),
                ),
              );

              return _wrapExportSelectable(message: message, child: body);
            },
        scrollToBottomBuilder: (context, animation, onPressed) {
          // 使用 Demo 同源的 “auto-follow + 浮动按钮” 方案，关闭 flutter_chat_ui 内置按钮以避免重复。
          return const SizedBox.shrink();
        },
        composerBuilder: (context) {
          // 使用 OwuiComposer（OpenWebUI 风格 + 可扩展动作栏）
          if (_isExportMode) {
            WidgetsBinding.instance.addPostFrameCallback((_) {
              if (!mounted || _isDisposed) return;
              context.read<ComposerHeightNotifier>().setHeight(0);
            });
            return const SizedBox.shrink();
          }

          return OwuiComposer(
            textController: _messageController,
            isStreaming: _isLoading || _streamController.isStreaming,
            onSend: _sendMessage,
            onStop: _stopStreaming,
            serviceManager: globalModelServiceManager,
            conversationSettings: _conversationSettings,
            attachmentBarVisible: _attachmentBarVisible,
            onSettingsChanged: (settings) {
              setState(() {
                _conversationSettings = settings;
              });
              globalModelServiceManager.updateConversationSettings(settings);
            },
          );
        },
      ),
      onMessageSend: (_) async {
        // composerBuilder 已接管发送逻辑，这里留空避免重复触发
      },
      resolveUser: (userId) async {
        return chat.User(
          id: userId,
          name: userId == _v2CurrentUserId ? '用户' : 'AI助手',
        );
      },
    );

    Widget scrollToBottomButton() {
      final colors = context.owuiColors;
      final fg = colors.textSecondary.withValues(alpha: 0.95);
      final bg = colors.surfaceCard;
      final border = colors.borderSubtle;

      return Positioned(
        right: 14,
        bottom: 86,
        child: Material(
          color: bg,
          shape: StadiumBorder(side: BorderSide(color: border)),
          elevation: 1,
          child: InkWell(
            onTap: () {
              setState(() {
                _autoFollowEnabled = true;
                _showScrollToBottom = false;
              });
              _requestAutoFollow(smooth: true);
            },
            customBorder: const StadiumBorder(),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.arrow_downward_rounded, size: 18, color: fg),
                  const SizedBox(width: 6),
                  Text(
                    '回到底部',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                      color: fg,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      );
    }

    final chatBody = Stack(
      children: [
        NotificationListener<ScrollNotification>(
          onNotification: _handleChatScrollNotification,
          child: chatWidget,
        ),
        if (!_isExportMode && _showScrollToBottom) scrollToBottomButton(),
      ],
    );

    if (_isExportMode) {
      return Column(
        children: [
          _buildExportModeToolbar(),
          Expanded(child: chatBody),
        ],
      );
    }

    return chatBody;
  }
}
