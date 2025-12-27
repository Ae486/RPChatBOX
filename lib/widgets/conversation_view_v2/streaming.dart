/// INPUT: AIProvider/StreamController/ChunkBuffer + ConversationSettings/contextLength
/// OUTPUT: _sendMessage(), _finalizeStreamingMessage(), _stopStreaming()
/// POS: UI 层 / Chat / V2 - 流式输出核心（改动需全量回归）

part of '../conversation_view_v2.dart';

mixin _ConversationViewV2StreamingMixin on _ConversationViewV2StateBase {
  Future<void> _sendMessage() async {
    if (_isDisposed) return;
    final text = _messageController.text.trim();
    final hasFiles = _conversationSettings.hasAttachedFiles;

    if (text.isEmpty && !hasFiles) return;

    final modelId = _conversationSettings.selectedModelId;
    if (modelId == null) {
      GlobalToast.warning(context, message: '请先选择一个模型');
      return;
    }

    final modelWithProvider = globalModelServiceManager.getModelWithProvider(
      modelId,
    );
    if (modelWithProvider == null) {
      GlobalToast.error(context, message: '无法找到指定的模型');
      return;
    }

    if (hasFiles) {
      setState(() {
        _attachmentBarVisible = false;
      });
    }

    final userInputTokens = TokenCounter.estimateTokens(text);
    final userMsg = app.Message(
      id: _newMessageId(),
      content: text,
      isUser: true,
      timestamp: DateTime.now(),
      inputTokens: userInputTokens,
      attachedFiles: _conversationSettings.attachedFiles
          .map((f) => AttachedFileSnapshot.fromAttachedFile(f))
          .toList(),
    );

    widget.conversation.addMessage(userMsg);

    final thread = _getThread();
    thread.appendToActiveLeaf(userMsg);
    _syncConversationMessagesSnapshotFromThread(thread);
    _persistThreadNoSave(thread);
    _schedulePersistThread();

    widget.onConversationUpdated();
    _messageController.clear();

    try {
      await _chatController.insertMessage(
        ChatMessageAdapter.toFlutterChatMessage(userMsg),
        animated: true,
      );
    } catch (_) {
      // Best-effort: keep UI consistent if chat controller rejects insertion.
      _syncConversationToChatController();
    }
    _requestAutoFollow(smooth: true);

    await _startAssistantResponse(
      modelWithProvider: modelWithProvider,
      animateInsert: true,
    );
  }

  @override
  Future<void> _startAssistantResponse({
    required ({ProviderConfig provider, ModelConfig model}) modelWithProvider,
    String? parentUserMessageId,
    bool animateInsert = true,
    bool useAtomicSetMessages = false,
  }) async {
    if (_isDisposed) return;
    if (_isLoading || _streamController.isStreaming) {
      GlobalToast.warning(context, message: '璇峰厛鍋滄杈撳嚭');
      return;
    }

    if (_conversationSettings.hasAttachedFiles) {
      setState(() {
        _attachmentBarVisible = false;
      });
    }

    setState(() {
      _isLoading = true;
    });

    final assistantId = _newMessageId();
    final createdAt = DateTime.now().toUtc();

    final placeholder = chat.TextMessage(
      id: assistantId,
      authorId: _v2AssistantUserId,
      createdAt: createdAt,
      text: '',
      metadata: {
        'streaming': true,
        'modelName': modelWithProvider.model.displayName,
        'providerName': modelWithProvider.provider.name,
      },
    );

    _activeAssistantPlaceholder = placeholder;
    _activeStreamId = assistantId;
    _streamManager.createStream(_activeStreamId!);

    try {
      if (parentUserMessageId != null) {
        final thread = _getThread(rebuildFromMessagesIfMismatch: false);
        final appPlaceholder = app.Message(
          id: assistantId,
          content: '',
          isUser: false,
          timestamp: DateTime.now(),
          modelName: modelWithProvider.model.displayName,
          providerName: modelWithProvider.provider.name,
        );
        thread.appendAssistantVariantUnderUser(
          userId: parentUserMessageId,
          assistantMessage: appPlaceholder,
        );
        _syncConversationMessagesSnapshotFromThread(thread);
        _persistThreadNoSave(thread);
        _schedulePersistThread();
      }

      if (useAtomicSetMessages) {
        // Route A (regenerate/resend): atomically replace the full list after the
        // thread has been updated to select the new assistant version, then
        // append a header-only streaming placeholder. This avoids transient
        // duplicate/ghost bubbles caused by mixing set/insert/update in
        // flutter_chat_ui.
        final thread = _getThread(rebuildFromMessagesIfMismatch: false);
        final chain = buildActiveMessageChain(thread);
        final safeChainForUi = chain.isNotEmpty &&
                !chain.last.isUser &&
                chain.last.content.trim().isEmpty
            ? chain.sublist(0, chain.length - 1)
            : chain;
        final msgs =
            safeChainForUi.map(ChatMessageAdapter.toFlutterChatMessage).toList();
        msgs.add(placeholder);
        await _chatController.setMessages(msgs, animated: false);
      } else {
        // Normal send: keep the lightweight incremental insert path for better UX.
        await _chatController.insertMessage(
          placeholder,
          animated: animateInsert,
        );
      }
    } catch (e) {
      _activeStreamId = null;
      _activeAssistantPlaceholder = null;
      _currentProvider = null;
      _activePromptTokensEstimate = null;
      _streamManager.end(assistantId);

      globalModelServiceManager.updateConversationSettings(
        _conversationSettings,
      );
      if (mounted && !_isDisposed) {
        setState(() {
          _isLoading = false;
          _attachmentBarVisible = true;
        });
        GlobalToast.error(context, message: '娑堟伅鎻掑叆澶辫触\n$e');
      }
      return;
    }
    _requestAutoFollow(smooth: false);

    // Build prompt messages after placeholder update so regeneration clears the UI
    // immediately even for long histories.
    final chatMessages = <ai.ChatMessage>[];
    final systemPrompt = widget.conversation.systemPrompt;
    if (systemPrompt != null && systemPrompt.trim().isNotEmpty) {
      chatMessages.add(ai.ChatMessage(role: 'system', content: systemPrompt));
    }

    final thread = _getThread();
    final history = buildActiveMessageChain(thread);
    final safeHistory = history.isNotEmpty &&
            !history.last.isUser &&
            history.last.content.trim().isEmpty
        ? history.sublist(0, history.length - 1)
        : history;
    final contextLength = _conversationSettings.contextLength;

    final startIndex =
        (contextLength <= 0 ||
                contextLength == -1 ||
                safeHistory.length <= contextLength)
            ? 0
            : safeHistory.length - contextLength;
    for (final msg in safeHistory.skip(startIndex)) {
      chatMessages.add(
        ai.ChatMessage(
          role: msg.isUser ? 'user' : 'assistant',
          content: msg.content,
        ),
      );
    }

    _activePromptTokensEstimate = _estimatePromptTokens(chatMessages);

    try {
      final provider = globalModelServiceManager.createProviderInstance(
        modelWithProvider.provider.id,
      );
      _currentProvider = provider;

      final files = _conversationSettings.attachedFiles
          .map(
            (f) => ai.AttachedFileData(
              path: f.path,
              mimeType: f.mimeType,
              name: f.name,
            ),
          )
          .toList();

      await _streamController.startStreaming(
        provider: provider,
        modelName: modelWithProvider.model.modelName,
        messages: chatMessages,
        parameters: _conversationSettings.parameters,
        files: files.isNotEmpty ? files : null,
        onChunk: (chunk) {
          if (_isDisposed) return;
          _chunkBuffer?.add(chunk);
        },
        onDone: () async {
          if (_isDisposed) return;
          _chunkBuffer?.flush();
          await _finalizeStreamingMessage(
            modelName: modelWithProvider.model.displayName,
            providerName: modelWithProvider.provider.name,
          );
        },
        onError: (error) async {
          if (_isDisposed) return;
          await _finalizeStreamingMessage(
            modelName: modelWithProvider.model.displayName,
            providerName: modelWithProvider.provider.name,
            error: error,
          );
        },
      );
    } catch (e) {
      await _finalizeStreamingMessage(
        modelName: modelWithProvider.model.displayName,
        providerName: modelWithProvider.provider.name,
        error: e,
      );
    }
  }

  void _handleStreamFlush(String content) {
    if (_isDisposed) return;
    final streamId = _activeStreamId;
    final oldPlaceholder = _activeAssistantPlaceholder;
    if (streamId == null || oldPlaceholder == null) return;

    _streamManager.append(streamId, content);
    final state = _streamManager.getState(streamId);

    final newMsg = chat.TextMessage(
      id: oldPlaceholder.id,
      authorId: oldPlaceholder.authorId,
      createdAt: oldPlaceholder.createdAt,
      text: state.text,
      metadata: {
        ...(oldPlaceholder.metadata ?? const <String, dynamic>{}),
        'streaming': !state.isComplete,
      },
    );

    _chatController.updateMessage(oldPlaceholder, newMsg);
    _activeAssistantPlaceholder = newMsg;
    _requestAutoFollow(smooth: false);
  }

  Future<void> _finalizeStreamingMessage({
    required String modelName,
    required String providerName,
    Object? error,
  }) async {
    if (_isDisposed) return;
    final streamId = _activeStreamId;
    final placeholder = _activeAssistantPlaceholder;

    _activeStreamId = null;
    _activeAssistantPlaceholder = null;
    _currentProvider = null;
    final promptTokens = _activePromptTokensEstimate;
    _activePromptTokensEstimate = null;

    if (streamId != null) {
      _streamManager.end(streamId);
    }

    if (error != null && mounted && !_isDisposed) {
      GlobalToast.error(context, message: '娑堟伅鍙戦€佸け璐n${error.toString()}');
    }

    if (placeholder != null && streamId != null) {
      final data = _streamManager.getData(streamId);
      final body = data?.content ?? '';
      final thinking = data?.thinkingContent ?? '';

      final finalContent = thinking.trim().isNotEmpty
          ? '<think>$thinking</think>$body'
          : body;

      if (finalContent.trim().isNotEmpty) {
        final outputTokens = TokenCounter.estimateTokens(finalContent);
        final assistantMessage = app.Message(
          id: placeholder.id,
          content: finalContent,
          isUser: false,
          timestamp: DateTime.now(),
          inputTokens: promptTokens,
          outputTokens: outputTokens,
          modelName: modelName,
          providerName: providerName,
        );

        final thread = _getThread(rebuildFromMessagesIfMismatch: false);
        final nodeAlreadyInThread = thread.nodes.containsKey(assistantMessage.id);

        if (!nodeAlreadyInThread) {
          widget.conversation.addMessage(assistantMessage);
        }

        thread.appendToActiveLeaf(assistantMessage);
        _syncConversationMessagesSnapshotFromThread(thread);
        _persistThreadNoSave(thread);
        _schedulePersistThread();

        widget.onConversationUpdated();
        widget.onTokenUsageUpdated(widget.conversation);

        final converted = ChatMessageAdapter.toFlutterChatMessage(
          assistantMessage,
        );
        // NOTE: `flutter_chat_ui` may not reliably repaint when a message's
        // runtime type changes (e.g. streaming `TextMessage` -> finalized
        // `CustomMessage` for <think> content). To prevent "duplicate/ghost"
        // messages that disappear after restart, always re-sync from the
        // persisted conversation after finalize.
        try {
          await _chatController.updateMessage(placeholder, converted);
        } catch (_) {
          // ignore: full sync below is the source of truth
        }
        _syncConversationToChatController();
        _requestAutoFollow(smooth: true);
      } else {
        // No content (e.g. request failed before any chunk or user stopped immediately).
        // Remove the placeholder to avoid a stuck "未落盘" item.
        try {
          await _chatController.removeMessage(placeholder, animated: false);
        } catch (_) {
          // ignore
        }
        _syncConversationToChatController();
      }
      _streamManager.removeStream(streamId);
    }

    // 成功/失败都清空附件并恢复附件栏
    _conversationSettings = _conversationSettings.clearFiles();
    globalModelServiceManager.updateConversationSettings(_conversationSettings);

    if (!mounted || _isDisposed) return;
    setState(() {
      _isLoading = false;
      _attachmentBarVisible = true;
    });
  }

  Future<void> _stopStreaming() async {
    if (_isDisposed) return;
    final provider = _currentProvider;
    if (provider != null) {
      try {
        if (provider.runtimeType.toString().contains('OpenAI')) {
          (provider as dynamic).cancelRequest();
        }
      } catch (_) {
        // ignore
      }
    }

    String modelName = 'Unknown';
    String providerName = 'Unknown';
    final modelId = _conversationSettings.selectedModelId;
    if (modelId != null) {
      final modelWithProvider = globalModelServiceManager.getModelWithProvider(
        modelId,
      );
      if (modelWithProvider != null) {
        modelName = modelWithProvider.model.displayName;
        providerName = modelWithProvider.provider.name;
      }
    }

    try {
      _chunkBuffer?.flush();
      await _streamController.stop();
    } catch (_) {
      // ignore
    }

    await _finalizeStreamingMessage(
      modelName: modelName,
      providerName: providerName,
    );
  }

  bool _isProbablyNetworkUrl(String source) {
    final uri = Uri.tryParse(source);
    if (uri == null || !uri.hasScheme) return false;
    return uri.scheme == 'http' || uri.scheme == 'https';
  }

  String _toFilePathIfNeeded(String source) {
    final uri = Uri.tryParse(source);
    if (uri == null) return source;
    if (uri.scheme == 'file') return uri.toFilePath();
    return source;
  }
}

