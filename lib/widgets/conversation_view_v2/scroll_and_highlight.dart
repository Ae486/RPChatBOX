/// INPUT: _chatController, StreamManager, OwuiMessageHighlightSweep
/// OUTPUT: scrollToMessage(), _requestAutoFollow(), _wrapHighlighted() - 被搜索定位/流式输出调用
/// POS: UI 层 / Chat / V2 - 滚动与高亮（体验核心）

part of '../conversation_view_v2.dart';

mixin _ConversationViewV2ScrollMixin on _ConversationViewV2StateBase {
  void scrollToMessage(String messageId) {
    _pendingScrollToMessageId = messageId;
    _pendingScrollToMessageAttempts = 0;
    _tryScrollToPendingMessage();
  }
void _syncConversationToChatController() {
    final thread = _getThread();
    final chain = buildActiveMessageChain(thread);
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

    _chatController.setMessages(msgs, animated: false);
    _tryScrollToPendingMessage();
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
        _chatController.scrollToIndex(
          idx,
          duration: const Duration(milliseconds: 260),
          curve: Curves.easeOutCubic,
          alignment: 0.2,
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
            borderRadius: BorderRadius.circular(24),
            maxOpacity: maxOpacity,
          ),
        ),
      ],
    );
  }

  void _requestAutoFollow({required bool smooth}) {
    if (_isDisposed) return;
    if (!_autoFollowEnabled) return;
    final messageCount = _chatController.messages.length;
    if (messageCount <= 0) return;

    final now = DateTime.now();
    if (now.difference(_lastAutoFollowRequest) <
        const Duration(milliseconds: 800))
      return;
    _lastAutoFollowRequest = now;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _isDisposed) return;
      final lastIndex = _chatController.messages.length - 1;
      _chatController.scrollToIndex(
        lastIndex,
        duration: smooth ? const Duration(milliseconds: 160) : Duration.zero,
        curve: Curves.easeOutCubic,
        alignment: 1.0,
        offset: 0,
      );
    });
  }

  bool _handleChatScrollNotification(ScrollNotification notification) {
    if (_isDisposed) return false;
    if (notification.depth != 0) return false;
    final metrics = notification.metrics;
    final extentAfter = metrics.extentAfter;
    const threshold = 80.0;

    final isNearBottom = extentAfter <= threshold;

    if (notification is ScrollUpdateNotification) {
      final currentPixels = metrics.pixels;
      final scrolledUp = currentPixels < _lastScrollPixels;
      _lastScrollPixels = currentPixels;

      if (scrolledUp && _autoFollowEnabled) {
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
