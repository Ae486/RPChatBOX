/// INPUT: _chatController, StreamManager, OwuiMessageHighlightSweep
/// OUTPUT: scrollToMessage(), _requestAutoFollow(), _wrapHighlighted() - 被搜索定位/流式输出调用
/// POS: UI 层 / Chat / V2 - 滚动与高亮（体验核心）

part of '../conversation_view_v2.dart';

mixin _ConversationViewV2ScrollMixin on _ConversationViewV2StateBase {
  List<chat.Message> _dedupeChatMessagesById(List<chat.Message> messages) {
    if (messages.length <= 1) return messages;

    final seen = <String>{};
    final dedupedReversed = <chat.Message>[];
    for (final message in messages.reversed) {
      if (seen.add(message.id)) {
        dedupedReversed.add(message);
      }
    }

    return dedupedReversed.reversed.toList(growable: false);
  }

  void scrollToMessage(String messageId) {
    _pendingScrollToMessageId = messageId;
    _pendingScrollToMessageAttempts = 0;
    _tryScrollToPendingMessage();
  }

  void _syncConversationToChatController({bool autoFollow = true}) {
    final chain = ai.ProviderFactory.pythonBackendEnabled
        ? widget.conversation.messages
        : buildActiveMessageChain(_getThread());
    final msgs = chain.map(ChatMessageAdapter.toFlutterChatMessage).toList();

    // Keep the active streaming placeholder in the list during a best-effort sync,
    // otherwise a mid-stream sync (e.g. from a catch/fallback path) may remove the
    // placeholder and cause subsequent stream flush updates to become no-ops.
    final placeholder = _activeAssistantPlaceholder;
    final streamId = _activeStreamId;
    if (placeholder != null &&
        streamId != null &&
        !msgs.any((m) => m.id == placeholder.id)) {
      msgs.add(placeholder);
    }

    final normalizedMsgs = _dedupeChatMessagesById(msgs);
    // During backend streaming the live assistant row is owned by incremental
    // `updateMessage` calls only. Replacing the full list here reintroduces a
    // second writer and can leave two visible assistant rows racing in the UI.
    final shouldFreezeBackendStreamingList =
        ai.ProviderFactory.pythonBackendEnabled &&
        streamId != null &&
        placeholder != null &&
        _chatController.messages.any((m) => m.id == placeholder.id);
    if (shouldFreezeBackendStreamingList) {
      _tryScrollToPendingMessage();
      if (autoFollow && _pendingScrollToMessageId == null) {
        _requestAutoFollow(smooth: false, force: true);
      }
      return;
    }

    final shouldKeepStreamingList =
        ai.ProviderFactory.pythonBackendEnabled &&
        streamId != null &&
        placeholder != null &&
        _sameChatMessageIds(_chatController.messages, normalizedMsgs);
    if (shouldKeepStreamingList) {
      _tryScrollToPendingMessage();
      if (autoFollow && _pendingScrollToMessageId == null) {
        _requestAutoFollow(smooth: false, force: true);
      }
      return;
    }

    _chatController.setMessages(normalizedMsgs, animated: false);
    _tryScrollToPendingMessage();

    // Scroll to bottom after messages are set
    if (autoFollow && _pendingScrollToMessageId == null) {
      _requestAutoFollow(smooth: false, force: true);
    }
  }

  void _setHighlightedMessage(String messageId) {
    _clearHighlightTimer?.cancel();
    if (mounted && !_isDisposed) {
      setState(() {
        _highlightedMessageId = messageId;
        _highlightNonce++;
      });
    }

    final nonce = _highlightNonce;
    final total =
        OwuiMessageHighlightSweep.defaultExpandDuration +
        OwuiMessageHighlightSweep.defaultHoldDuration +
        OwuiMessageHighlightSweep.defaultFadeOutDuration +
        const Duration(milliseconds: 120);

    _clearHighlightTimer = Timer(total, () {
      if (!mounted || _isDisposed) return;
      setState(() {
        if (_highlightedMessageId == messageId && _highlightNonce == nonce) {
          _highlightedMessageId = null;
        }
      });
    });
  }

  void _tryScrollToPendingMessage() {
    final messageId = _pendingScrollToMessageId;
    if (messageId == null) return;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _isDisposed) return;

      final idx = _chatController.messages.indexWhere((m) => m.id == messageId);
      if (idx < 0) {
        _pendingScrollToMessageAttempts++;
        if (_pendingScrollToMessageAttempts > 120) {
          _pendingScrollToMessageId = null;
          return;
        }

        Future.delayed(const Duration(milliseconds: 16), () {
          if (!mounted || _isDisposed) return;
          _tryScrollToPendingMessage();
        });
        return;
      }

      _pendingScrollToMessageId = null;
      _setHighlightedMessage(messageId);

      try {
        MarkstreamV2StreamingMetrics.onScrollToIndex();
        _chatController.scrollToIndex(
          idx,
          duration: const Duration(milliseconds: 260),
          curve: Curves.easeOutCubic,
          alignment: 0.0,
        );
      } catch (_) {
        // Ignore: chat list may not be attached yet; next frame/sync will retry.
        _pendingScrollToMessageId = messageId;
        _pendingScrollToMessageAttempts++;
        if (_pendingScrollToMessageAttempts > 120) {
          _pendingScrollToMessageId = null;
          return;
        }
        Future.delayed(const Duration(milliseconds: 16), () {
          if (!mounted || _isDisposed) return;
          _tryScrollToPendingMessage();
        });
      }
    });
  }

  Widget _wrapHighlighted({required String messageId, required Widget child}) {
    if (_highlightedMessageId != messageId) return child;

    final primary = Theme.of(context).colorScheme.primary;
    final isDark = OwuiPalette.isDark(context);
    final maxOpacity = isDark
        ? OwuiMessageHighlightSweep.defaultMaxOpacity
        : OwuiMessageHighlightSweep.defaultMaxOpacity * 0.75;

    return Stack(
      fit: StackFit.passthrough,
      children: [
        child,
        Positioned.fill(
          child: OwuiMessageHighlightSweep(
            key: ValueKey('$messageId-$_highlightNonce'),
            color: primary,
            borderRadius: BorderRadius.zero,
            maxOpacity: maxOpacity,
          ),
        ),
      ],
    );
  }

  /// 请求自动跟随滚动到底部。
  /// [smooth] 是否使用平滑动画滚动。
  /// [force] 是否强制执行（绕过节流和 autoFollowEnabled 检查），用于"回到底部"按钮点击。
  void _requestAutoFollow({required bool smooth, bool force = false}) {
    if (_isDisposed) return;
    if (!force && !_autoFollowEnabled) return;
    if (_chatController.messages.isEmpty) return;

    final useAnchor =
        !force && MarkstreamV2StreamingFlags.anchorAutoFollow(_conversationSettings);
    if (!useAnchor) {
      // force 模式绕过节流检查
      if (!force) {
        final now = DateTime.now();
        final throttleMs = MarkstreamV2StreamingFlags.scrollThrottleMs(_conversationSettings);
        if (now.difference(_lastAutoFollowRequest) <
            Duration(milliseconds: throttleMs)) {
          return;
        }
        _lastAutoFollowRequest = now;
      }

      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || _isDisposed) return;
        final lastIndex = _chatController.messages.length - 1;
        if (lastIndex < 0) return;
        final durationMs = MarkstreamV2StreamingFlags.scrollDurationMs(_conversationSettings);
        MarkstreamV2StreamingMetrics.onScrollToIndex();
        _chatController.scrollToIndex(
          lastIndex,
          duration: smooth ? Duration(milliseconds: durationMs) : Duration.zero,
          curve: Curves.easeOutCubic,
          alignment: 1.0,
          offset: 0,
        );
      });
      return;
    }

    if (!_isNearBottom) return;

    _pendingAutoFollow = true;
    _pendingAutoFollowSmooth = _pendingAutoFollowSmooth || smooth;

    if (_autoFollowScheduled) return;
    _autoFollowScheduled = true;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      _autoFollowScheduled = false;

      if (!mounted || _isDisposed) return;
      if (!_pendingAutoFollow) return;

      final smoothNow = _pendingAutoFollowSmooth;
      _pendingAutoFollow = false;
      _pendingAutoFollowSmooth = false;

      if (!_autoFollowEnabled) return;
      if (!_isNearBottom) return;

      final lastIndex = _chatController.messages.length - 1;
      if (lastIndex < 0) return;

      try {
        final durationMs = MarkstreamV2StreamingFlags.scrollDurationMs(_conversationSettings);
        MarkstreamV2StreamingMetrics.onScrollToIndex();
        _chatController.scrollToIndex(
          lastIndex,
          duration: smoothNow ? Duration(milliseconds: durationMs) : Duration.zero,
          curve: Curves.easeOutCubic,
          alignment: 1.0,
          offset: 0,
        );
      } catch (_) {
        // Ignore: chat list may not be attached yet.
      }
    });
  }

  bool _handleChatScrollNotification(ScrollNotification notification) {
    if (_isDisposed) return false;
    if (notification.depth != 0) return false;

    final metrics = notification.metrics;
    final extentAfter = metrics.extentAfter;
    final threshold = MarkstreamV2StreamingFlags.nearBottomPx(_conversationSettings);

    final isNearBottom = extentAfter <= threshold;
    _isNearBottom = isNearBottom;

    if (notification is ScrollUpdateNotification) {
      final currentPixels = metrics.pixels;
      final scrolledUp = currentPixels < _lastScrollPixels;
      _lastScrollPixels = currentPixels;

      if (scrolledUp && _autoFollowEnabled) {
        _pendingAutoFollow = false;
        _pendingAutoFollowSmooth = false;
        setState(() {
          _autoFollowEnabled = false;
          _showScrollToBottom = true;
        });
      } else if (isNearBottom && !_autoFollowEnabled) {
        setState(() {
          _autoFollowEnabled = true;
          _showScrollToBottom = false;
        });
      } else if (!isNearBottom && _autoFollowEnabled) {
        setState(() {
          _showScrollToBottom = true;
        });
      } else if (isNearBottom && _autoFollowEnabled && _showScrollToBottom) {
        setState(() {
          _showScrollToBottom = false;
        });
      }
    }

    if (notification is UserScrollNotification) {
      if (notification.direction == ScrollDirection.forward &&
          _autoFollowEnabled) {
        _pendingAutoFollow = false;
        _pendingAutoFollowSmooth = false;
        setState(() {
          _autoFollowEnabled = false;
          _showScrollToBottom = true;
        });
      } else if (notification.direction == ScrollDirection.reverse &&
          isNearBottom &&
          !_autoFollowEnabled) {
        setState(() {
          _autoFollowEnabled = true;
          _showScrollToBottom = false;
        });
      }
    }

    return false;
  }
}
