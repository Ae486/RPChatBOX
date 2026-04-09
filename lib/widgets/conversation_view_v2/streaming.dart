/// INPUT: AIProvider/StreamController/ChunkBuffer + ConversationSettings/contextLength
/// OUTPUT: _sendMessage(), _finalizeStreamingMessage(), _stopStreaming()
/// POS: UI 层 / Chat / V2 - 流式输出核心（改动需全量回归）

part of '../conversation_view_v2.dart';

mixin _ConversationViewV2StreamingMixin on _ConversationViewV2StateBase {
  @override
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
        _toFlutterChatMessage(userMsg),
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
      GlobalToast.warning(context, message: '请先停止输出');
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

    _resetStableFlowRevealForNewStream();

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
        final safeChainForUi =
            chain.isNotEmpty &&
                !chain.last.isUser &&
                chain.last.content.trim().isEmpty
            ? chain.sublist(0, chain.length - 1)
            : chain;
        final msgs = safeChainForUi.map(_toFlutterChatMessage).toList();
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
        GlobalToast.error(context, message: '消息插入失败\n$e');
      }
      return;
    }
    _requestAutoFollow(smooth: true);

    // Build prompt messages after placeholder update so regeneration clears the UI
    // immediately even for long histories.
    final chatMessages = <ai.ChatMessage>[];
    final systemPrompt = widget.conversation.systemPrompt;
    if (systemPrompt != null && systemPrompt.trim().isNotEmpty) {
      chatMessages.add(ai.ChatMessage(role: 'system', content: systemPrompt));
    }

    // Roleplay context injection (M1 Context Compiler)
    if (_isRoleplaySession(widget.conversation)) {
      try {
        final rpContext = await _compileRoleplayContext(widget.conversation);
        if (rpContext.isNotEmpty) {
          chatMessages.add(ai.ChatMessage(role: 'system', content: rpContext));
        }
      } catch (e) {
        debugPrint('[streaming] Roleplay context compilation failed: $e');
      }
    }

    final thread = _getThread();
    final history = buildActiveMessageChain(thread);
    final safeHistory =
        history.isNotEmpty &&
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

    // 注入 summary：如果存在已压缩消息的摘要，在 systemPrompt 后注入
    final summary = widget.conversation.summary ?? '';
    final summaryRangeEndId = widget.conversation.summaryRangeEndId;
    if (summary.isNotEmpty && summaryRangeEndId != null) {
      final summaryEndIndex = safeHistory.indexWhere(
        (msg) => msg.id == summaryRangeEndId,
      );
      if (summaryEndIndex == -1) {
        debugPrint(
          '[streaming] summaryRangeEndId=$summaryRangeEndId not found in history, skipping injection',
        );
      } else if (summaryEndIndex < startIndex) {
        // 只有当 summaryRangeEndId 在当前窗口之前时才注入（表示有被压缩的消息）
        chatMessages.add(
          ai.ChatMessage(
            role: 'system',
            content: _formatSummaryForPrompt(summary),
          ),
        );
      }
    }

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
      final files = _conversationSettings.attachedFiles
          .map(
            (f) => ai.AttachedFileData(
              path: f.path,
              mimeType: f.mimeType,
              name: f.name,
              bytes: File(f.path).existsSync()
                  ? File(f.path).readAsBytesSync()
                  : null,
            ),
          )
          .toList();

      final provider = globalModelServiceManager.createProviderInstance(
        modelWithProvider.provider.id,
      );
      _currentProvider = provider;

      // MCP 工具集成：如果模型支持工具且有已连接的 MCP 服务器
      if (provider is HybridLangChainProvider &&
          globalMcpClientService.hasConnectedServer) {
        final supportsTools = modelWithProvider.model.hasCapability(
          ModelCapability.tool,
        );
        if (supportsTools) {
          final mcpAdapter = McpToolAdapter(globalMcpClientService);
          provider.setMcpAdapter(mcpAdapter, supportsTools: true);
        }
      }

      await _streamController.startStreaming(
        provider: provider,
        modelName: modelWithProvider.model.modelName,
        modelId: modelWithProvider.model.id,
        messages: chatMessages,
        parameters: _conversationSettings.parameters,
        files: files.isNotEmpty ? files : null,
        onChunk: (chunk) {
          if (_isDisposed) return;
          _chunkBuffer?.add(chunk);
        },
        onEvent: (event) {
          if (_isDisposed) return;
          _handleStreamEvent(event);
        },
        onDone: () async {
          if (_isDisposed) return;
          _chunkBuffer?.flush();
          // 设置待 finalize 状态，保存快照以避免 active 状态被清空
          _pendingFinalize = (
            modelName: modelWithProvider.model.displayName,
            providerName: modelWithProvider.provider.name,
            error: null,
            streamId: _activeStreamId,
            placeholder: _activeAssistantPlaceholder,
            promptTokens: _activePromptTokensEstimate,
          );
          // 确保 Timer 继续运行以完成剩余渲染
          _scheduleNextRevealTick();
        },
        onError: (error) async {
          if (_isDisposed) return;
          // 错误情况：设置待 finalize 状态，保存快照
          _pendingFinalize = (
            modelName: modelWithProvider.model.displayName,
            providerName: modelWithProvider.provider.name,
            error: error,
            streamId: _activeStreamId,
            placeholder: _activeAssistantPlaceholder,
            promptTokens: _activePromptTokensEstimate,
          );
          _scheduleNextRevealTick();
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

  void _handleStreamEvent(ai.AIStreamEvent event) {
    if (!event.isTypedSemantic) return;
    _activeStreamUsesTypedEvents = true;

    final streamId = _activeStreamId;
    if (streamId == null) return;

    switch (event.type) {
      case ai.AIStreamEventType.thinking:
        final text = event.text ?? '';
        if (text.isEmpty) return;
        _streamManager.appendThinking(streamId, text);
        _refreshStreamingPlaceholderForState(bumpThinking: true);
        return;
      case ai.AIStreamEventType.text:
        final wasOpen =
            _streamManager.getData(streamId)?.isThinkingOpen ?? false;
        _streamManager.closeThinking(streamId);
        if (wasOpen) {
          _refreshStreamingPlaceholderForState(bumpThinking: true);
        }
        return;
      case ai.AIStreamEventType.toolCall:
        final toolCalls = event.toolCalls ?? const <Map<String, dynamic>>[];
        if (toolCalls.isEmpty) return;
        _streamManager.closeThinking(streamId);
        _applyTypedToolCalls(streamId, toolCalls);
        _refreshStreamingPlaceholderForState(bumpToolCalls: true);
        return;
      case ai.AIStreamEventType.toolStarted:
        final callId = event.callId ?? '';
        if (callId.isEmpty) return;
        _streamManager.closeThinking(streamId);
        _ensureTypedToolCallExists(
          streamId,
          callId: callId,
          toolName: event.toolName,
        );
        _streamManager.startToolCall(streamId, callId);
        _refreshStreamingPlaceholderForState(bumpToolCalls: true);
        return;
      case ai.AIStreamEventType.toolResult:
        final callId = event.callId ?? '';
        if (callId.isEmpty) return;
        _streamManager.closeThinking(streamId);
        _ensureTypedToolCallExists(
          streamId,
          callId: callId,
          toolName: event.toolName,
        );
        _streamManager.completeToolCall(
          streamId,
          callId,
          success: true,
          result: event.result,
        );
        _refreshStreamingPlaceholderForState(bumpToolCalls: true);
        return;
      case ai.AIStreamEventType.toolError:
        final callId = event.callId ?? '';
        if (callId.isEmpty) return;
        _streamManager.closeThinking(streamId);
        _ensureTypedToolCallExists(
          streamId,
          callId: callId,
          toolName: event.toolName,
        );
        _streamManager.completeToolCall(
          streamId,
          callId,
          success: false,
          errorMessage: event.errorMessage,
        );
        _refreshStreamingPlaceholderForState(bumpToolCalls: true);
        return;
    }
  }

  void _applyTypedToolCalls(
    String streamId,
    List<Map<String, dynamic>> toolCalls,
  ) {
    for (final toolCall in toolCalls) {
      final callId = (toolCall['id'] ?? '').toString();
      final function = toolCall['function'];
      if (callId.isEmpty || function is! Map<String, dynamic>) {
        continue;
      }

      final toolName = (function['name'] ?? '').toString();
      if (toolName.isEmpty) {
        continue;
      }

      Map<String, dynamic>? arguments;
      final rawArguments = function['arguments'];
      if (rawArguments is Map<String, dynamic>) {
        arguments = rawArguments;
      } else if (rawArguments is String && rawArguments.isNotEmpty) {
        try {
          final decoded = jsonDecode(rawArguments);
          if (decoded is Map<String, dynamic>) {
            arguments = decoded;
          }
        } catch (_) {
          arguments = {'raw': rawArguments};
        }
      }

      _streamManager.addToolCall(
        streamId,
        ToolCallData(
          callId: callId,
          toolName: toolName,
          status: ToolCallStatus.pending,
          arguments: arguments,
        ),
      );
    }
  }

  void _ensureTypedToolCallExists(
    String streamId, {
    required String callId,
    String? toolName,
  }) {
    final existing = _streamManager.getToolCalls(streamId);
    final found = existing.any((toolCall) => toolCall.callId == callId);
    if (found) {
      return;
    }

    _streamManager.addToolCall(
      streamId,
      ToolCallData(
        callId: callId,
        toolName: (toolName != null && toolName.isNotEmpty)
            ? toolName
            : 'unknown_tool',
        status: ToolCallStatus.pending,
      ),
    );
  }

  void _refreshStreamingPlaceholderForState({
    bool bumpThinking = false,
    bool bumpToolCalls = false,
  }) {
    if (_isDisposed) return;

    final streamId = _activeStreamId;
    final oldPlaceholder = _activeAssistantPlaceholder;
    if (streamId == null || oldPlaceholder == null) return;

    final oldMeta = oldPlaceholder.metadata ?? const <String, dynamic>{};
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final oldText = oldPlaceholder is chat.TextMessage
        ? oldPlaceholder.text
        : '';
    final newMeta = <String, dynamic>{
      ...oldMeta,
      'streaming': true,
      'streamStateBumpTs': nowMs,
    };

    if (bumpThinking) {
      final revRaw = oldMeta['thinkingRev'];
      final rev = (revRaw is int) ? revRaw : int.tryParse('$revRaw') ?? 0;
      newMeta['thinkingRev'] = rev + 1;
      newMeta['thinkingBumpTs'] = nowMs;
    }

    if (bumpToolCalls) {
      final revRaw = oldMeta['toolCallsRev'];
      final rev = (revRaw is int) ? revRaw : int.tryParse('$revRaw') ?? 0;
      newMeta['toolCallsRev'] = rev + 1;
      newMeta['toolCallsBumpTs'] = nowMs;
    }

    final newMsg = chat.TextMessage(
      id: oldPlaceholder.id,
      authorId: oldPlaceholder.authorId,
      createdAt: oldPlaceholder.createdAt,
      text: oldText,
      metadata: newMeta,
    );

    _chatController.updateMessage(oldPlaceholder, newMsg);
    _activeAssistantPlaceholder = newMsg;
    _requestAutoFollow(smooth: true);
  }

  @override
  void _handleStreamFlush(String content) {
    if (_isDisposed) return;

    final streamId = _activeStreamId;
    final oldPlaceholder = _activeAssistantPlaceholder;
    if (streamId == null || oldPlaceholder == null) return;

    final beforeData = _streamManager.getData(streamId);
    final beforeThinkingLen = beforeData?.thinkingContent.length ?? 0;
    final beforeThinkingOpen = beforeData?.isThinkingOpen ?? false;

    if (_activeStreamUsesTypedEvents) {
      _streamManager.appendText(streamId, content);
    } else {
      _streamManager.append(streamId, content);
    }

    _scheduleStreamingImagePrefetch(streamId);

    final useStableFlow = MarkstreamV2StreamingFlags.stableFlowReveal(
      _conversationSettings,
    );

    if (useStableFlow) {
      final afterData = _streamManager.getData(streamId);
      final afterThinkingLen = afterData?.thinkingContent.length ?? 0;
      final afterThinkingOpen = afterData?.isThinkingOpen ?? false;
      final thinkingChanged =
          afterThinkingLen != beforeThinkingLen ||
          afterThinkingOpen != beforeThinkingOpen;

      // FIX: 移除 content.isEmpty 门控，thinking 变化时始终触发 thinkingBump
      // 根因：<think> 和 </think> 经常在同一 flush 中到达，如果 body 也在同一 chunk，
      // content.isEmpty 为 false 会跳过 thinkingBump，导致 UI 从未显示 thinking 状态
      if (thinkingChanged) {
        final oldMeta = oldPlaceholder.metadata ?? const <String, dynamic>{};
        final nowMs = DateTime.now().millisecondsSinceEpoch;
        final lastBump = oldMeta['thinkingBumpTs'] as int?;
        const bumpThrottleMs = 120;

        if (lastBump == null || (nowMs - lastBump) >= bumpThrottleMs) {
          final revRaw = oldMeta['thinkingRev'];
          final rev = (revRaw is int) ? revRaw : int.tryParse('$revRaw') ?? 0;
          final oldText = (oldPlaceholder is chat.TextMessage)
              ? oldPlaceholder.text
              : '';

          final newMsg = chat.TextMessage(
            id: oldPlaceholder.id,
            authorId: oldPlaceholder.authorId,
            createdAt: oldPlaceholder.createdAt,
            text: oldText,
            metadata: {
              ...oldMeta,
              'streaming': true,
              'thinkingRev': rev + 1,
              'thinkingBumpTs': nowMs,
            },
          );

          _chatController.updateMessage(oldPlaceholder, newMsg);
          _activeAssistantPlaceholder = newMsg;
          // 思考气泡出现/更新时也需要自动跟随到底部
          _requestAutoFollow(smooth: true);
        }
      }
    }

    if (!useStableFlow) {
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

      MarkstreamV2StreamingMetrics.onUpdateMessage();
      _chatController.updateMessage(oldPlaceholder, newMsg);
      _activeAssistantPlaceholder = newMsg;
      _requestAutoFollow(smooth: true);
      return;
    }

    _ensureStableFlowRevealTimer();

    // FIX-1 + FIX-2: 解耦生产者与消费者
    // 删除直接调用 _stableFlowRevealTick()，让 timer 控制渲染节奏
    // 仅在首次 flush 时立即触发一次，避免用户感知延迟
    if (!_stableRevealKickstarted) {
      _stableRevealKickstarted = true;
      _stableFlowRevealTick();
    }
  }

  void _resetStableFlowRevealForNewStream() {
    _stableRevealTimer?.cancel();
    _stableRevealTimer = null;

    _streamImagePrefetchTimer?.cancel();
    _streamImagePrefetchTimer = null;
    _streamPrefetchedImageUrls.clear();

    _stableRevealTicking = false;
    _stableRevealDisplayedLen = 0;
    _stableRevealKickstarted = false; // FIX-2 改进：使用一次性标志
    _activeStreamUsesTypedEvents = false;
    _pendingFinalize = null;
  }

  void _scheduleStreamingImagePrefetch(String streamId) {
    _streamImagePrefetchTimer?.cancel();
    _streamImagePrefetchTimer = Timer(const Duration(milliseconds: 280), () {
      if (_isDisposed) return;
      if (_activeStreamId != streamId) return;

      final fullText = _streamManager.getState(streamId).text;
      for (final url
          in ImagePersistenceService.extractNetworkImageUrlsFromMarkdown(
            fullText,
          )) {
        if (_streamPrefetchedImageUrls.add(url)) {
          unawaited(ImagePersistenceService().persistNetworkImage(url));
        }
      }
    });
  }

  void _ensureStableFlowRevealTimer() {
    if (_stableRevealTimer != null) return;
    _scheduleNextRevealTick();
  }

  /// 调度下一次 reveal tick（使用单次 Timer，每次读取最新的 tickMs）
  void _scheduleNextRevealTick() {
    if (_isDisposed || _stableRevealTimer != null) return;
    final tickMs = MarkstreamV2StreamingFlags.revealTickMs(
      _conversationSettings,
    );
    _stableRevealTimer = Timer(Duration(milliseconds: tickMs), () {
      _stableRevealTimer = null;
      _stableFlowRevealTick();
    });
  }

  void _stopStableFlowRevealTimer() {
    _stableRevealTimer?.cancel();
    _stableRevealTimer = null;
    _stableRevealTicking = false;
  }

  void _stableFlowRevealTick() {
    if (_isDisposed) {
      _stopStableFlowRevealTimer();
      return;
    }

    if (_stableRevealTicking) return;

    if (!MarkstreamV2StreamingFlags.stableFlowReveal(_conversationSettings)) {
      _stopStableFlowRevealTimer();
      return;
    }

    final streamId = _activeStreamId;
    final oldPlaceholder = _activeAssistantPlaceholder;
    if (streamId == null || oldPlaceholder == null) {
      // 流已结束或被清理，使用快照进行 finalize
      final pending = _pendingFinalize;
      if (pending != null) {
        _pendingFinalize = null;
        unawaited(
          _finalizeStreamingMessage(
            modelName: pending.modelName,
            providerName: pending.providerName,
            error: pending.error,
            streamIdOverride: pending.streamId,
            placeholderOverride: pending.placeholder,
            promptTokensOverride: pending.promptTokens,
          ),
        );
      }
      _stopStableFlowRevealTimer();
      return;
    }

    final fullText = _streamManager.getState(streamId).text;
    final fullLen = fullText.length;
    if (fullLen <= 0) {
      // 无内容，如果有待 finalize 则使用快照执行
      final pending = _pendingFinalize;
      if (pending != null) {
        _pendingFinalize = null;
        _stopStableFlowRevealTimer();
        unawaited(
          _finalizeStreamingMessage(
            modelName: pending.modelName,
            providerName: pending.providerName,
            error: pending.error,
            streamIdOverride: pending.streamId,
            placeholderOverride: pending.placeholder,
            promptTokensOverride: pending.promptTokens,
          ),
        );
        return;
      }
      _scheduleNextRevealTick();
      return;
    }

    var displayedLen = _stableRevealDisplayedLen;
    if (displayedLen < 0) displayedLen = 0;
    if (displayedLen > fullLen) displayedLen = fullLen;

    final backlog = fullLen - displayedLen;
    if (backlog <= 0) {
      // 已显示完所有内容，使用快照进行 finalize
      final pending = _pendingFinalize;
      if (pending != null) {
        _pendingFinalize = null;
        _stopStableFlowRevealTimer();
        unawaited(
          _finalizeStreamingMessage(
            modelName: pending.modelName,
            providerName: pending.providerName,
            error: pending.error,
            streamIdOverride: pending.streamId,
            placeholderOverride: pending.placeholder,
            promptTokensOverride: pending.promptTokens,
          ),
        );
        return;
      }
      _scheduleNextRevealTick();
      return;
    }

    final maxCharsPerTick = MarkstreamV2StreamingFlags.revealMaxCharsPerTick(
      _conversationSettings,
    );
    final minBufferChars = MarkstreamV2StreamingFlags.revealMinBufferChars(
      _conversationSettings,
    );
    final maxLagChars = MarkstreamV2StreamingFlags.revealMaxLagChars(
      _conversationSettings,
    );

    final needCatchUpNow = maxLagChars > 0 && backlog > maxLagChars;
    var desiredMin = displayedLen;
    if (needCatchUpNow) {
      desiredMin = fullLen - maxLagChars;
      if (desiredMin < displayedLen) desiredMin = displayedLen;
    }

    // FIX-3 改进: 流结束时绕过 minBufferChars 限制
    final isFinishing = _pendingFinalize != null;
    final keepBuffer = !isFinishing && backlog > minBufferChars;
    var desiredMax = keepBuffer ? fullLen - minBufferChars : fullLen;
    if (desiredMax < desiredMin) desiredMax = desiredMin;

    var proposed = displayedLen + maxCharsPerTick;

    // FIX-3: 流结束时快进，消除完成延迟
    // 如果流已结束且 backlog 较小（≤ 3 倍 maxCharsPerTick），一次性显示完
    if (isFinishing && backlog > 0 && backlog <= maxCharsPerTick * 3) {
      proposed = fullLen;
    }

    if (proposed < desiredMin) proposed = desiredMin;
    if (proposed > desiredMax) proposed = desiredMax;

    // FIX-4: 流结束时直接绕过稳定性检查，避免死锁
    // 根因：StablePrefixParser 对未闭合结构返回 stable=""，导致渲染无法前进
    // 流结束后不会有更多内容来闭合这些结构，继续等待是无意义的
    final bypassStableCheck = isFinishing;

    final safeEnd = _clampStableRevealEnd(
      fullText,
      proposed,
      floor: displayedLen,
      bypassStableCheck: bypassStableCheck,
    );

    if (safeEnd <= displayedLen) {
      _scheduleNextRevealTick();
      return;
    }

    _stableRevealTicking = true;
    try {
      final actualChars = safeEnd - displayedLen;
      _stableRevealDisplayedLen = safeEnd;

      // 调试日志：显示实际输出的字符数（仅在 MS_STREAM_METRICS 启用时）
      if (const bool.fromEnvironment(
        'MS_STREAM_METRICS',
        defaultValue: false,
      )) {
        final tickMs = MarkstreamV2StreamingFlags.revealTickMs(
          _conversationSettings,
        );
        debugPrint(
          '[tick] +$actualChars chars (max=$maxCharsPerTick, tick=${tickMs}ms, displayed=$safeEnd/$fullLen)',
        );
      }

      final newText = fullText.substring(0, safeEnd);
      final newMsg = chat.TextMessage(
        id: oldPlaceholder.id,
        authorId: oldPlaceholder.authorId,
        createdAt: oldPlaceholder.createdAt,
        text: newText,
        metadata: {
          ...(oldPlaceholder.metadata ?? const <String, dynamic>{}),
          'streaming': true,
        },
      );

      MarkstreamV2StreamingMetrics.onUpdateMessage();
      _chatController.updateMessage(oldPlaceholder, newMsg);
      _activeAssistantPlaceholder = newMsg;
      _requestAutoFollow(smooth: true);
    } finally {
      _stableRevealTicking = false;
      _scheduleNextRevealTick();
    }
  }

  int _clampStableRevealEnd(
    String text,
    int desiredEnd, {
    required int floor,
    bool bypassStableCheck = false, // FIX-4: 流结束时绕过稳定性检查
  }) {
    var end = desiredEnd;
    if (end > text.length) end = text.length;
    if (end <= floor) return floor;

    // Avoid splitting surrogate pairs (always keep this check for safety).
    if (end > floor) {
      final cu = text.codeUnitAt(end - 1);
      if (cu >= 0xD800 && cu <= 0xDBFF) {
        end -= 1;
        if (end <= floor) return floor;
      }
    }

    // FIX-4: 流结束时绕过其他稳定性检查，避免死锁
    if (bypassStableCheck) {
      return end;
    }

    // Avoid ending on a dangling CR in "\r\n".
    if (end > floor && text.codeUnitAt(end - 1) == 0x0D) {
      end -= 1;
      if (end <= floor) return floor;
    }

    end = _stripPartialRun(text, end, floor: floor, charCode: 0x60); // `
    end = _stripPartialRun(text, end, floor: floor, charCode: 0x7E); // ~

    // Prevent leaking half of a "$"/"$$" across chunk boundaries.
    final dollarRun = _countTrailingRun(
      text,
      end,
      floor: floor,
      charCode: 0x24,
    );
    if (dollarRun == 1) {
      end -= 1;
      if (end <= floor) return floor;
    }

    // Avoid ending on a dangling escape.
    if (end > floor && text.codeUnitAt(end - 1) == 0x5C) {
      end -= 1;
      if (end <= floor) return floor;
    }

    end = _stripDanglingHtmlTagStart(text, end, floor: floor);
    if (end <= floor) return floor;

    // Reuse `StablePrefixParser` to avoid revealing unstable blocks (e.g. $$
    // blocks, HTML blocks, tables) before they are safely closed.
    //
    // IMPORTANT: code fences are explicitly allowed, because `OwuiStableBody`
    // will render them via the streaming code block shell (no raw backticks
    // shown).
    final windowStart = (end - 768) > floor ? (end - 768) : floor;
    final window = text.substring(windowStart, end);
    final maybeSensitive =
        window.contains(r'$$') || window.contains('<') || window.contains('|');

    if (maybeSensitive) {
      final parts = const StablePrefixParser().split(text.substring(0, end));
      if (parts.tail.isNotEmpty) {
        final tailHasLeadingFence = RegExp(
          r'^\s*(```|~~~)',
        ).hasMatch(parts.tail);
        if (!tailHasLeadingFence) {
          final stableLen = parts.stable.length;
          if (stableLen <= floor) return floor;
          return stableLen;
        }
      }
    }

    return end;
  }

  int _stripDanglingHtmlTagStart(String text, int end, {required int floor}) {
    final windowStart = (end - 256) > floor ? (end - 256) : floor;
    var searchFrom = end - 1;
    while (true) {
      final idx = text.lastIndexOf('<', searchFrom);
      if (idx < windowStart) return end;
      if (idx + 1 >= end) return idx <= floor ? floor : idx;

      final first = text.codeUnitAt(idx + 1);
      final looksLikeTag =
          first == 47 || first == 33 || first == 63 || _isAsciiLetter(first);
      if (!looksLikeTag) {
        searchFrom = idx - 1;
        continue;
      }

      final closeIdx = text.indexOf('>', idx + 2);
      if (closeIdx == -1 || closeIdx >= end) {
        end = idx;
        if (end <= floor) return floor;
      }

      searchFrom = idx - 1;
    }
  }

  bool _isAsciiLetter(int codeUnit) {
    return (codeUnit >= 65 && codeUnit <= 90) ||
        (codeUnit >= 97 && codeUnit <= 122);
  }

  String _formatSummaryForPrompt(String summaryJson) {
    return '[Previous conversation summary]\n$summaryJson';
  }

  int _stripPartialRun(
    String text,
    int end, {
    required int floor,
    required int charCode,
  }) {
    final run = _countTrailingRun(text, end, floor: floor, charCode: charCode);
    if (run > 0 && run < 3) {
      return end - run;
    }
    return end;
  }

  int _countTrailingRun(
    String text,
    int end, {
    required int floor,
    required int charCode,
  }) {
    var count = 0;
    var i = end - 1;
    while (i >= floor && text.codeUnitAt(i) == charCode) {
      count++;
      i--;
    }
    return count;
  }

  Future<void> _finalizeStreamingMessage({
    required String modelName,
    required String providerName,
    Object? error,
    // Override 参数：使用快照而非 active 状态
    String? streamIdOverride,
    chat.Message? placeholderOverride,
    int? promptTokensOverride,
  }) async {
    if (_isDisposed) return;

    // 优先使用 override 快照，否则使用当前 active 状态
    final streamId = streamIdOverride ?? _activeStreamId;
    final placeholder = placeholderOverride ?? _activeAssistantPlaceholder;
    final promptTokens = promptTokensOverride ?? _activePromptTokensEstimate;

    _stopStableFlowRevealTimer();

    _streamImagePrefetchTimer?.cancel();
    _streamImagePrefetchTimer = null;
    _streamPrefetchedImageUrls.clear();

    // 无条件清空 active 状态（恢复原逻辑）
    _activeStreamId = null;
    _activeAssistantPlaceholder = null;
    _currentProvider = null;
    _activePromptTokensEstimate = null;

    if (streamId != null) {
      _streamManager.end(streamId);
    }

    // 格式化错误为 <error> 标签（不再使用 toast）
    String? errorTag;
    if (error != null) {
      final errorInfo = error is ErrorInfo
          ? error
          : ErrorFormatter.parse(error);
      errorTag = errorInfo.toErrorTag();
    }

    if (placeholder != null && streamId != null) {
      final data = _streamManager.getData(streamId);
      final body = data?.content ?? '';
      final thinking = data?.thinkingContent ?? '';

      final finalContent = buildStreamingFinalContent(
        thinking: thinking,
        body: body,
        errorTag: errorTag,
      );

      if (shouldPersistFinalizedStreamingMessage(finalContent)) {
        final outputTokens = TokenCounter.estimateTokens(finalContent);
        final thinkingDuration = data?.thinkingDurationSeconds ?? 0;
        final assistantMessage = app.Message(
          id: placeholder.id,
          content: finalContent,
          isUser: false,
          timestamp: DateTime.now(),
          inputTokens: promptTokens,
          outputTokens: outputTokens,
          modelName: modelName,
          providerName: providerName,
          thinkingDurationSeconds: thinkingDuration > 0
              ? thinkingDuration
              : null,
        );

        final thread = _getThread(rebuildFromMessagesIfMismatch: false);
        final nodeAlreadyInThread = thread.nodes.containsKey(
          assistantMessage.id,
        );

        if (!nodeAlreadyInThread) {
          widget.conversation.addMessage(assistantMessage);
        }

        thread.appendToActiveLeaf(assistantMessage);
        _syncConversationMessagesSnapshotFromThread(thread);
        _persistThreadNoSave(thread);
        _schedulePersistThread();

        widget.onConversationUpdated();
        widget.onTokenUsageUpdated(widget.conversation);

        final converted = _toFlutterChatMessage(assistantMessage);
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
        // FIX-5: 不强制跳转底部，尊重用户的滚动位置
        _syncConversationToChatController(autoFollow: false);
        _requestAutoFollow(smooth: true);

        // 将过期的网络图片 URL 替换为持久化的本地文件 URI
        unawaited(_persistMarkdownImagesForMessageId(assistantMessage.id));
      } else {
        // 只有在既没有正文/思考，也没有错误块时才移除占位消息。
        // 手动截断会附加 <error> 块，从而保留 header 并显示提示。
        try {
          await _chatController.removeMessage(placeholder, animated: false);
        } catch (_) {
          // ignore
        }
        _syncConversationToChatController();
      }
      // 保存思考秒数到缓存，防止 removeStream 后丢失
      final thinkingDuration = data?.thinkingDurationSeconds ?? 0;
      if (thinkingDuration > 0) {
        _thinkingDurationCache[streamId] = thinkingDuration;
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

  @override
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
    _currentProvider = null;

    var modelName = 'Unknown';
    var providerName = 'Unknown';
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

    // FIX-6: 截断基于渲染器当前进度，而非 chunk 完整内容
    // 避免点击截断后瞬间释放大量未渲染内容
    final streamId = _activeStreamId;
    if (streamId != null && _stableRevealDisplayedLen > 0) {
      final fullText = _streamManager.getState(streamId).text;
      if (_stableRevealDisplayedLen < fullText.length) {
        // 截断到当前渲染位置
        _streamManager.truncate(streamId, _stableRevealDisplayedLen);
      }
    }

    // 清空待 finalize 状态，避免重复执行
    _pendingFinalize = null;

    await _finalizeStreamingMessage(
      modelName: modelName,
      providerName: providerName,
      error: ErrorFormatter.requestAborted(),
    );
  }

  @override
  bool _isProbablyNetworkUrl(String source) {
    final uri = Uri.tryParse(source);
    if (uri == null || !uri.hasScheme) return false;
    return uri.scheme == 'http' || uri.scheme == 'https';
  }

  @override
  String _toFilePathIfNeeded(String source) {
    final uri = Uri.tryParse(source);
    if (uri == null) return source;
    if (uri.scheme == 'file') return uri.toFilePath();
    return source;
  }

  /// Check if conversation is a roleplay session
  bool _isRoleplaySession(Conversation conversation) {
    return conversation.roleType == 'roleplay';
  }

  /// Lazy-initialized roleplay context compiler
  RpMemoryRepository? _rpRepository;
  RpContextCompiler? _rpContextCompiler;

  /// Ensure roleplay compiler is initialized
  Future<RpContextCompiler> _ensureRpCompiler() async {
    if (_rpContextCompiler != null) return _rpContextCompiler!;

    _rpRepository = RpMemoryRepository();
    await _rpRepository!.initialize();
    _rpContextCompiler = RpContextCompiler(repository: _rpRepository!);
    return _rpContextCompiler!;
  }

  /// Compile roleplay context for injection
  Future<String> _compileRoleplayContext(Conversation conversation) async {
    const defaultRpBudget = 2000;

    final compiler = await _ensureRpCompiler();

    final result = await compiler.compile(
      storyId: conversation.id,
      branchId: 'main',
      maxTokensTotal: defaultRpBudget,
    );

    if (result.hasP0Overflow) {
      debugPrint(
        '[streaming] Roleplay context P0 overflow - some required content dropped',
      );
    }

    return result.renderedText;
  }
}
