/// INPUT: Conversation/messages/chatController, ExportService, AttachedFileSnapshot
/// OUTPUT: _showMessageActionsSheet() - 长按/右键入口
/// POS: UI 层 / Chat / V2 - 消息操作菜单（功能聚合）

part of '../conversation_view_v2.dart';

mixin _ConversationViewV2MessageActionsMixin on _ConversationViewV2StateBase {
  Future<void> _showMessageActionsSheet(chat.Message message) async {
    if (!mounted || _isDisposed) return;

    final isUser = message.authorId == _v2CurrentUserId;
    final isAssistant = message.authorId == _v2AssistantUserId;

    // Best-effort snapshot of current text for streaming placeholder.
    String? liveText;
    if (message is chat.TextMessage) {
      final metadata = message.metadata ?? const <String, dynamic>{};
      final streaming = metadata['streaming'] == true;
      if (streaming && _streamManager.hasStream(message.id)) {
        final data = _streamManager.getData(message.id);
        final body = data?.content ?? '';
        final thinking = data?.thinkingContent ?? '';
        liveText = thinking.trim().isNotEmpty
            ? '<think>$thinking</think>$body'
            : body;
      } else {
        liveText = message.text;
      }
    } else if (message is chat.CustomMessage) {
      final meta = message.metadata ?? const <String, dynamic>{};
      final thinking = (meta['thinking'] as String?) ?? '';
      final body = (meta['body'] as String?) ?? '';
      liveText = thinking.trim().isNotEmpty
          ? '<think>$thinking</think>$body'
          : body;
    } else if (message is chat.ImageMessage) {
      liveText = message.source;
    } else if (message is chat.FileMessage) {
      liveText = message.source;
    }

    // Find persisted message in conversation if available.
    final messageIndex = widget.conversation.messages.indexWhere(
      (m) => m.id == message.id,
    );
    final appMsg = messageIndex >= 0
        ? widget.conversation.messages[messageIndex]
        : null;

    Future<void> doCopy() async {
      final text = (liveText ?? '').trim();
      if (text.isEmpty) return;
      await Clipboard.setData(ClipboardData(text: text));
      if (!mounted || _isDisposed) return;
      GlobalToast.success(context, message: '已复制到剪贴板');
    }

    Future<void> doEditUser() async {
      if (!isUser) return;
      if (appMsg == null || messageIndex < 0) {
        GlobalToast.warning(context, message: '该消息尚未落盘，暂不支持编辑');
        return;
      }
      if (_isLoading || _streamController.isStreaming) {
        GlobalToast.warning(context, message: '请先停止输出再编辑');
        return;
      }

      final controller = TextEditingController(text: appMsg.content);
      final action = await showDialog<String>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('编辑消息'),
          content: TextField(
            controller: controller,
            autofocus: true,
            minLines: 1,
            maxLines: 10,
            decoration: const InputDecoration(
              hintText: '输入新的内容…',
              border: OutlineInputBorder(),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(null),
              child: const Text('取消'),
            ),
            TextButton(
              onPressed: () => Navigator.of(ctx).pop('save'),
              child: const Text('保存'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(ctx).pop('resend'),
              child: const Text('保存并重发'),
            ),
          ],
        ),
      );
      final newContent = controller.text.trim();
      controller.dispose();

      if (!mounted || _isDisposed) return;
      if (action == null) return;

      final hasAttachments =
          appMsg.attachedFiles != null && appMsg.attachedFiles!.isNotEmpty;
      if (newContent.isEmpty && !hasAttachments) {
        GlobalToast.warning(context, message: '内容不能为空');
        return;
      }

      if (action == 'save') {
        appMsg.content = newContent;
        appMsg.inputTokens = TokenCounter.estimateTokens(newContent);
        widget.conversation.updatedAt = DateTime.now();
        widget.onConversationUpdated();
        widget.onTokenUsageUpdated(widget.conversation);

        try {
          final converted = ChatMessageAdapter.toFlutterChatMessage(appMsg);
          await _chatController.updateMessage(message, converted);
        } catch (_) {
          _syncConversationToChatController();
        }

        if (!mounted || _isDisposed) return;
        GlobalToast.success(context, message: '已保存');
        return;
      }

      if (!mounted || _isDisposed) return;
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('保存并重发'),
          content: const Text('将保留旧版本，并创建新的助手回复版本后重新发送。继续？'),
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
      if (confirmed != true) return;
      if (!mounted || _isDisposed) return;

      // Restore attachments if any (best-effort).
      final snapshots = appMsg.attachedFiles ?? const <AttachedFileSnapshot>[];
      if (snapshots.isNotEmpty) {
        final missing = <String>[];
        final restored = <AttachedFile>[];

        for (final s in snapshots) {
          try {
            final f = File(s.path);
            if (!await f.exists()) {
              missing.add(s.name);
              continue;
            }
            restored.add(await AttachedFile.fromFile(f, s.id));
          } catch (_) {
            missing.add(s.name);
          }
        }

        if (missing.isNotEmpty) {
          if (!mounted || _isDisposed) return;
          final shouldContinue = await showDialog<bool>(
            context: context,
            builder: (ctx) => AlertDialog(
              title: const Text('部分附件已缺失'),
              content: Text(
                "以下附件无法恢复，将忽略：\n- ${missing.join('\n- ')}\n\n继续重发？",
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
          if (shouldContinue != true) return;
          if (!mounted || _isDisposed) return;
        }

        if (restored.isNotEmpty) {
          setState(() {
            _conversationSettings = _conversationSettings.copyWith(
              attachedFiles: restored,
            );
            _attachmentBarVisible = true;
          });
          globalModelServiceManager.updateConversationSettings(
            _conversationSettings,
          );
        }
      }

      // V2 tree semantics: update user message, then create a NEW assistant variant.
      appMsg.content = newContent;
      appMsg.inputTokens = TokenCounter.estimateTokens(newContent);

      final thread = _getThread(rebuildFromMessagesIfMismatch: false);
      thread.upsertMessage(appMsg);
      thread.activeLeafId = appMsg.id;
      thread.normalize();

      _syncConversationMessagesSnapshotFromThread(thread);
      _persistThreadNoSave(thread);
      _schedulePersistThread();

      widget.conversation.updatedAt = DateTime.now();
      widget.onConversationUpdated();
      widget.onTokenUsageUpdated(widget.conversation);

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

      await _startAssistantResponse(
        modelWithProvider: modelWithProvider,
        parentUserMessageId: appMsg.id,
        animateInsert: false,
        useAtomicSetMessages: true,
      );
    }

    Future<void> doEditAssistant() async {
      if (!isAssistant) return;
      if (appMsg == null || messageIndex < 0) {
        GlobalToast.warning(context, message: '该消息尚未落盘，暂不支持编辑');
        return;
      }
      if (_isLoading || _streamController.isStreaming) {
        GlobalToast.warning(context, message: '请先停止输出再编辑');
        return;
      }

      final controller = TextEditingController(text: appMsg.content);
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('编辑消息'),
          content: TextField(
            controller: controller,
            autofocus: true,
            minLines: 1,
            maxLines: 12,
            decoration: const InputDecoration(
              hintText: '输入新的内容…',
              border: OutlineInputBorder(),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('保存'),
            ),
          ],
        ),
      );
      final newContent = controller.text.trim();
      controller.dispose();

      if (!mounted || _isDisposed) return;
      if (confirmed != true) return;
      if (newContent.isEmpty) {
        GlobalToast.warning(context, message: '内容不能为空');
        return;
      }

      appMsg.content = newContent;
      appMsg.outputTokens = TokenCounter.estimateTokens(newContent);

      // Update thread structure (source of truth for persistence).
      final thread = _getThread(rebuildFromMessagesIfMismatch: false);
      thread.upsertMessage(appMsg);
      _syncConversationMessagesSnapshotFromThread(thread);
      _persistThreadNoSave(thread);
      _schedulePersistThread();

      widget.conversation.updatedAt = DateTime.now();
      widget.onConversationUpdated();
      widget.onTokenUsageUpdated(widget.conversation);

      try {
        final converted = ChatMessageAdapter.toFlutterChatMessage(appMsg);
        await _chatController.updateMessage(message, converted);
      } catch (_) {
        _syncConversationToChatController();
      }

      if (!mounted || _isDisposed) return;
      GlobalToast.success(context, message: '已保存');
    }

    Future<String?> askExportFormat({required String title}) {
      return showDialog<String>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: Text(title),
          content: const Text('选择导出格式'),
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
    }

    Future<void> doExportSingle() async {
      final format = await askExportFormat(title: '导出消息');
      if (format == null) return;
      if (!mounted || _isDisposed) return;

      final exportMsg = appMsg ??
          (liveText == null
              ? null
              : app.Message(
                  id: message.id,
                  content: liveText!,
                  isUser: isUser,
                  timestamp: (message.createdAt ?? DateTime.now()).toLocal(),
                ));
      if (exportMsg == null) {
        GlobalToast.warning(context, message: '该消息暂无可导出的内容');
        return;
      }

      try {
        final content = format == 'md'
            ? ExportService.exportSingleMessageToMarkdown(exportMsg)
            : ExportService.exportSingleMessageToText(exportMsg);
        final fileName = ExportService.generateMultiMessageFileName(
          widget.conversation.title,
          1,
          format,
        );
        final filePath = await ExportService.saveToFile(content, fileName);
        await Clipboard.setData(ClipboardData(text: filePath));
        if (!mounted || _isDisposed) return;
        GlobalToast.success(context, message: '已导出，路径已复制到剪贴板');
      } catch (e) {
        if (!mounted || _isDisposed) return;
        GlobalToast.error(context, message: '导出失败: $e');
      }
    }

    Future<void> doExportConversation() async {
      final format = await askExportFormat(title: '导出会话');
      if (format == null) return;
      if (!mounted || _isDisposed) return;

      try {
        final content = format == 'md'
            ? ExportService.exportToMarkdown(widget.conversation)
            : ExportService.exportToText(widget.conversation);
        final fileName = ExportService.generateFileName(
          widget.conversation.title,
          format,
        );
        final filePath = await ExportService.saveToFile(content, fileName);
        await Clipboard.setData(ClipboardData(text: filePath));
        if (!mounted || _isDisposed) return;
        GlobalToast.success(context, message: '已导出会话，路径已复制到剪贴板');
      } catch (e) {
        if (!mounted || _isDisposed) return;
        GlobalToast.error(context, message: '导出失败: $e');
      }
    }

    Future<void> doDelete() async {
      final confirm = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('删除消息'),
          content: const Text('确认删除这条消息？'),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text('取消'),
            ),
            FilledButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('删除'),
            ),
          ],
        ),
      );
      if (confirm != true) return;
      if (!mounted || _isDisposed) return;

      if (messageIndex >= 0) {
        // Update thread structure (source of truth for persistence).
        final thread = _getThread(rebuildFromMessagesIfMismatch: false);
        thread.removeNode(message.id);

        // Sync linear messages snapshot from thread.
        _syncConversationMessagesSnapshotFromThread(thread);
        _persistThreadNoSave(thread);
        _schedulePersistThread();

        widget.conversation.updatedAt = DateTime.now();
        widget.onConversationUpdated();
      }

      await _chatController.removeMessage(message, animated: true);
      if (!mounted || _isDisposed) return;
      GlobalToast.success(context, message: '已删除');
    }

    Future<void> doRegenerate() async {
      if (messageIndex < 0) {
        GlobalToast.warning(context, message: '该消息尚未落盘，无法重新生成');
        return;
      }
      if (_isLoading || _streamController.isStreaming) {
        GlobalToast.warning(context, message: '请先停止输出再重新生成');
        return;
      }

      // For assistant message, regenerate from previous user message.
      var targetIndex = messageIndex;
      if (isAssistant) {
        for (var i = messageIndex - 1; i >= 0; i--) {
          if (widget.conversation.messages[i].isUser) {
            targetIndex = i;
            break;
          }
        }
      }

      final target = widget.conversation.messages[targetIndex];
      if (!target.isUser) {
        GlobalToast.warning(context, message: '找不到可用于重新生成的用户消息');
        return;
      }
      final targetContent = target.content;
      final targetSnapshots =
          target.attachedFiles ?? const <AttachedFileSnapshot>[];
      if (targetContent.trim().isEmpty && targetSnapshots.isEmpty) {
        GlobalToast.warning(context, message: '内容为空，无法重新生成');
        return;
      }

      final confirmed = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('重新生成'),
          content: const Text('将保留旧版本，并创建新的助手回复版本后重新生成。继续？'),
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
      if (confirmed != true) return;
      if (!mounted || _isDisposed) return;

      // Restore attachments if any.
      if (targetSnapshots.isNotEmpty) {
        final missing = <String>[];
        final restored = <AttachedFile>[];

        for (final s in targetSnapshots) {
          try {
            final f = File(s.path);
            if (!await f.exists()) {
              missing.add(s.name);
              continue;
            }
            restored.add(await AttachedFile.fromFile(f, s.id));
          } catch (_) {
            missing.add(s.name);
          }
        }

        if (missing.isNotEmpty) {
          if (!mounted || _isDisposed) return;
          final shouldContinue = await showDialog<bool>(
            context: context,
            builder: (ctx) => AlertDialog(
              title: const Text('部分附件已缺失'),
              content: Text(
                "以下附件无法恢复，将忽略：\n- ${missing.join('\n- ')}\n\n继续重新生成？",
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
          if (shouldContinue != true) return;
          if (!mounted || _isDisposed) return;
        }

        if (restored.isNotEmpty) {
          setState(() {
            _conversationSettings = _conversationSettings.copyWith(
              attachedFiles: restored,
            );
            _attachmentBarVisible = true;
          });
          globalModelServiceManager.updateConversationSettings(
            _conversationSettings,
          );
        }
      }

      widget.conversation.updatedAt = DateTime.now();
      widget.onConversationUpdated();
      widget.onTokenUsageUpdated(widget.conversation);

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

      await _startAssistantResponse(
        modelWithProvider: modelWithProvider,
        parentUserMessageId: target.id,
        animateInsert: false,
        useAtomicSetMessages: true,
      );
    }

    // Desktop safety: avoid triggering overlays during a MouseTracker device update.
    await Future<void>.delayed(Duration.zero);
    if (!mounted || _isDisposed) return;

    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (ctx) {
        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                leading: const Icon(OwuiIcons.copy),
                title: const Text('复制'),
                onTap: () async {
                  Navigator.of(ctx).pop();
                  await doCopy();
                },
              ),
              if (isUser && appMsg != null)
                ListTile(
                  leading: const Icon(OwuiIcons.edit),
                  title: const Text('编辑'),
                  onTap: () async {
                    Navigator.of(ctx).pop();
                    await doEditUser();
                  },
                ),
              if (isAssistant && appMsg != null)
                ListTile(
                  leading: const Icon(OwuiIcons.edit),
                  title: const Text('编辑'),
                  onTap: () async {
                    Navigator.of(ctx).pop();
                    await doEditAssistant();
                  },
                ),
              if (liveText != null || appMsg != null)
                ListTile(
                  leading: const Icon(OwuiIcons.upload),
                  title: const Text('导出此消息'),
                  onTap: () async {
                    Navigator.of(ctx).pop();
                    await doExportSingle();
                  },
                ),
              ListTile(
                leading: const Icon(OwuiIcons.share),
                title: const Text('导出当前会话'),
                onTap: () async {
                  Navigator.of(ctx).pop();
                  await doExportConversation();
                },
              ),
              if ((isAssistant || isUser) && messageIndex >= 0)
                ListTile(
                  leading: const Icon(OwuiIcons.refresh),
                  title: const Text('重新生成（从此处）'),
                  onTap: () async {
                    Navigator.of(ctx).pop();
                    await doRegenerate();
                  },
                ),
              ListTile(
                leading: const Icon(OwuiIcons.trash),
                title: const Text('删除'),
                textColor: Colors.red,
                iconColor: Colors.red,
                onTap: () async {
                  Navigator.of(ctx).pop();
                  await doDelete();
                },
              ),
              const SizedBox(height: 6),
            ],
          ),
        );
      },
    );
  }
}
