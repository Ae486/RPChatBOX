/// INPUT: Conversation/history/settings + current model/provider
/// OUTPUT: Compact action + context token summaries for UI
/// POS: UI 层 / Chat / V2 - Compact

part of '../conversation_view_v2.dart';

mixin _ConversationViewV2CompactMixin on _ConversationViewV2StateBase {
  ConversationContextWindow _buildCurrentContextWindow({
    int? contextLengthOverride,
  }) {
    final history = ai.ProviderFactory.pythonBackendEnabled
        ? widget.conversation.messages
        : buildActiveMessageChain(_getThread());
    return _conversationContextService.buildContextWindow(
      conversation: widget.conversation,
      settings: _conversationSettings,
      historyOverride: history,
      contextLengthOverride: contextLengthOverride,
    );
  }

  String _compactButtonLabel() {
    final window = _buildCurrentContextWindow();
    return 'Compact ${TokenCounter.formatTokens(window.windowTokens)}';
  }

  String _compactButtonTooltip() {
    final window = _buildCurrentContextWindow();
    if (window.summaryApplied && window.summaryTokens > 0) {
      return '压缩当前窗口 ${window.windowMessages.length} 条消息\n'
          '窗口 ${TokenCounter.formatTokens(window.windowTokens)} tokens，'
          '摘要 ${TokenCounter.formatTokens(window.summaryTokens)} tokens';
    }
    return '压缩当前窗口 ${window.windowMessages.length} 条消息\n'
        '窗口 ${TokenCounter.formatTokens(window.windowTokens)} tokens';
  }

  String _contextTokenSummaryForLength(int contextLength) {
    final window = _buildCurrentContextWindow(
      contextLengthOverride: contextLength,
    );
    final windowText =
        '当前窗口 ${window.windowMessages.length} 条，'
        '${TokenCounter.formatTokens(window.windowTokens)} tokens';
    if (!window.summaryApplied || window.summaryTokens <= 0) {
      return windowText;
    }
    return '$windowText；已注入摘要 ${TokenCounter.formatTokens(window.summaryTokens)} tokens，'
        '总计 ${TokenCounter.formatTokens(window.totalContextTokens)} tokens';
  }

  bool _canRunCompact(ConversationContextWindow window) {
    if (_isCompacting || _isLoading || _streamController.isStreaming) {
      return false;
    }
    if (window.windowMessages.isEmpty) {
      return false;
    }
    return _conversationSettings.selectedModelId != null;
  }

  @override
  Future<void> _runCompact() async {
    if (_isDisposed) return;
    if (_isCompacting) return;
    if (_isLoading || _streamController.isStreaming) {
      GlobalToast.warning(context, message: '请先停止输出再执行 Compact');
      return;
    }

    final window = _buildCurrentContextWindow();
    if (window.windowMessages.isEmpty) {
      GlobalToast.warning(context, message: '当前没有可压缩的上下文窗口');
      return;
    }

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

    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Compact'),
        content: Text(
          window.summaryApplied && window.summaryTokens > 0
              ? '将压缩当前窗口 ${window.windowMessages.length} 条消息。\n\n'
                    '当前窗口: ${TokenCounter.formatTokens(window.windowTokens)} tokens\n'
                    '已有摘要: ${TokenCounter.formatTokens(window.summaryTokens)} tokens\n'
                    '模型当前可见上下文总计: ${TokenCounter.formatTokens(window.totalContextTokens)} tokens'
              : '将压缩当前窗口 ${window.windowMessages.length} 条消息。\n\n'
                    '当前窗口: ${TokenCounter.formatTokens(window.windowTokens)} tokens',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('取消'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('继续'),
          ),
        ],
      ),
    );
    if (confirm != true || !mounted || _isDisposed) return;

    setState(() {
      _isCompacting = true;
    });

    try {
      final provider = globalModelServiceManager.createProviderInstance(
        modelWithProvider.provider.id,
      );
      final result = await _conversationSummaryService.summarize(
        conversation: widget.conversation,
        settings: _conversationSettings,
        provider: provider,
        modelName: modelWithProvider.model.modelName,
        parameters: _conversationSettings.parameters,
        historyOverride: window.activeHistory,
      );

      await context.read<ChatSessionProvider>().saveCurrentConversation();
      if (!mounted || _isDisposed) return;

      setState(() {});
      GlobalToast.success(
        context,
        message:
            'Compact 完成，已压缩到 ${TokenCounter.formatTokens(window.windowTokens)} tokens 窗口',
      );
      debugPrint(
        '[compact] range=${result.rangeStartId}..${result.rangeEndId} updatedAt=${result.updatedAt.toIso8601String()}',
      );
    } catch (e) {
      if (!mounted || _isDisposed) return;
      GlobalToast.error(context, message: 'Compact 失败\n$e');
    } finally {
      if (mounted && !_isDisposed) {
        setState(() {
          _isCompacting = false;
        });
      }
    }
  }
}
