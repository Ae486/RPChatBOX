/// INPUT: Conversation/ChatSettings + threadJson/activeLeafId + globalModelServiceManager + flutter_chat_ui
/// OUTPUT: ConversationViewV2() - 被 ConversationViewHost 使用；State API: scrollToMessage()/enterExportMode()
/// POS: UI 层 / Chat / V2（flutter_chat_ui 集成）核心模块（改动需全量回归）

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_chat_core/flutter_chat_core.dart' as chat;
import 'package:flutter_chat_ui/flutter_chat_ui.dart' hide ChatMessage;
import 'package:flyer_chat_file_message/flyer_chat_file_message.dart';
import 'package:flyer_chat_image_message/flyer_chat_image_message.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../adapters/ai_provider.dart' as ai;
import '../adapters/chat_message_adapter.dart';
import '../chat_ui/owui/assistant_message.dart';
import '../chat_ui/owui/chat_theme.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../chat_ui/owui/composer/owui_composer.dart';
import '../chat_ui/owui/message_highlight_sweep.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../chat_ui/owui/palette.dart';

import '../controllers/stream_output_controller.dart';
import '../main.dart' show globalModelServiceManager;
import '../models/attached_file.dart';
import '../models/chat_settings.dart';
import '../models/conversation.dart';
import '../models/conversation_settings.dart';
import '../models/conversation_thread.dart';
import '../models/model_config.dart';
import '../models/message.dart' as app;
import '../models/provider_config.dart';
import '../services/export_service.dart';
import '../services/image_persistence_service.dart';
import '../services/roleplay/context_compiler/rp_context_compiler.dart';
import '../services/roleplay/rp_memory_repository.dart';
import '../utils/chunk_buffer.dart';
import '../utils/token_counter.dart';
import '../utils/global_toast.dart';
import '../rendering/markdown_stream/stable_prefix_parser.dart';
import 'stream_manager.dart';

part 'conversation_view_v2/build.dart';
part 'conversation_view_v2/export_mode.dart';
part 'conversation_view_v2/message_actions_sheet.dart';
part 'conversation_view_v2/scroll_and_highlight.dart';
part 'conversation_view_v2/streaming.dart';
part 'conversation_view_v2/streaming_feature_flags.dart';
part 'conversation_view_v2/tokens_and_ids.dart';
part 'conversation_view_v2/user_bubble.dart';
part 'conversation_view_v2/thread_projection.dart';

const String _v2CurrentUserId = 'user';
const String _v2AssistantUserId = 'assistant';
int _v2MessageIdSeq = 0;

class ConversationViewV2 extends StatefulWidget {
  final Conversation conversation;
  final ChatSettings settings;
  final VoidCallback onConversationUpdated;
  final Function(Conversation) onTokenUsageUpdated;

  const ConversationViewV2({
    super.key,
    required this.conversation,
    required this.settings,
    required this.onConversationUpdated,
    required this.onTokenUsageUpdated,
  });

  @override
  State<ConversationViewV2> createState() => ConversationViewV2State();
}

abstract class _ConversationViewV2StateBase extends State<ConversationViewV2>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  late final chat.InMemoryChatController _chatController;
  final _messageController = TextEditingController();

  late ConversationSettings _conversationSettings;
  late EnhancedStreamController _streamController;
  ChunkBuffer? _chunkBuffer;
  final StreamManager _streamManager = StreamManager();

  bool _isLoading = false;
  bool _attachmentBarVisible = true;
  ai.AIProvider? _currentProvider;
  bool _isDisposed = false;

  bool _isExportMode = false;
  final Set<String> _selectedMessageIds = <String>{};

  String? _pendingScrollToMessageId;
  int _pendingScrollToMessageAttempts = 0;
  String? _highlightedMessageId;
  int _highlightNonce = 0;
  Timer? _clearHighlightTimer;

  String? _activeStreamId;
  chat.Message? _activeAssistantPlaceholder;
  int? _activePromptTokensEstimate;
  ConversationThread? _thread;
  Timer? _persistThreadTimer;
  String? _lastPersistedThreadJson;

  final Map<String, chat.Message> _chatMessageCache = <String, chat.Message>{};
  final Map<String, int> _chatMessageCacheFingerprints = <String, int>{};

  bool _autoFollowEnabled = true;
  bool _isNearBottom = true;

  bool _pendingAutoFollow = false;
  bool _pendingAutoFollowSmooth = false;
  bool _autoFollowScheduled = false;

  bool _showScrollToBottom = false;
  double _lastScrollPixels = 0;
  DateTime _lastAutoFollowRequest = DateTime.fromMillisecondsSinceEpoch(0);

  // 调试面板状态
  bool _showTuningPanel = false;

  // Composer height excluding bottom safe area (used for overlay positioning).
  double _composerHeight = 0.0;

  // Phase 1 (P0): stable flow reveal (display/full separation).
  Timer? _stableRevealTimer;
  bool _stableRevealTicking = false;
  int _stableRevealDisplayedLen = 0;

  // 待 finalize 状态（流结束后等待渐进式渲染完成）
  ({String modelName, String providerName, Object? error})? _pendingFinalize;

  // 图片持久化：将过期的网络图片保存到本地
  String? _imagePersistenceSweptConversationId;
  int _imagePersistenceSweepEpoch = 0;
  bool _imagePersistenceSweepRunning = false;
  final Set<String> _persistingMarkdownMessageIds = <String>{};

  // 流式输出期间预取图片（抢在 URL 过期前）
  Timer? _streamImagePrefetchTimer;
  final Set<String> _streamPrefetchedImageUrls = <String>{};


  @override
  void initState() {
    super.initState();

    _chatController = chat.InMemoryChatController();

    // Start loading persisted tuning params as early as possible.
    unawaited(StreamingTuningParams.instance.ensureLoaded());

    _conversationSettings = globalModelServiceManager.getConversationSettings(
      widget.conversation.id,
    );
    _streamController = EnhancedStreamController();

    _chunkBuffer = ChunkBuffer(
      onFlush: (content) {
        if (!mounted || _isDisposed) return;
        _handleStreamFlush(content);
      },
      flushInterval: const Duration(milliseconds: 50),
      flushThreshold: 30,
      enableDebugLog: false,
    );

    // 初始化同步对话消息到 chatController
    scheduleMicrotask(() {
      if (!mounted) return;
      _syncConversationToChatController();
      _scheduleImagePersistenceSweep();
    });
  }

  void _handleComposerHeightChanged(double heightWithoutSafeArea) {
    if (!mounted || _isDisposed) return;
    if ((_composerHeight - heightWithoutSafeArea).abs() < 0.5) return;
    setState(() {
      _composerHeight = heightWithoutSafeArea;
    });
  }

  @override
  void dispose() {
    _isDisposed = true;
    // Best-effort: stop streaming to prevent late callbacks touching a deactivated tree.
    _streamController.stop();
    _chunkBuffer?.dispose();
    _stableRevealTimer?.cancel();
    _stableRevealTimer = null;
    _streamImagePrefetchTimer?.cancel();
    _streamImagePrefetchTimer = null;
    _pendingFinalize = null;
    _clearHighlightTimer?.cancel();
    _persistThreadTimer?.cancel();
    _persistThreadTimer = null;
    _streamController.dispose();
    _messageController.dispose();
    _chatController.dispose();
    _streamManager.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant ConversationViewV2 oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.conversation.id != widget.conversation.id) {
      _stableRevealTimer?.cancel();
      _stableRevealTimer = null;
      _stableRevealTicking = false;
      _stableRevealDisplayedLen = 0;
      _pendingFinalize = null;

      _streamImagePrefetchTimer?.cancel();
      _streamImagePrefetchTimer = null;
      _streamPrefetchedImageUrls.clear();

      _imagePersistenceSweepEpoch++;
      _imagePersistenceSweepRunning = false;
      _imagePersistenceSweptConversationId = null;
      _persistingMarkdownMessageIds.clear();

      _flushPersistThreadNow();
      _conversationSettings = globalModelServiceManager.getConversationSettings(
        widget.conversation.id,
      );
      _thread = null;

      _chatMessageCache.clear();
      _chatMessageCacheFingerprints.clear();
      scheduleMicrotask(() {
        if (!mounted) return;
        _syncConversationToChatController();
        _scheduleImagePersistenceSweep();
      });
    }
  }

  ConversationThread _getThread({bool rebuildFromMessagesIfMismatch = true}) {
    final conversation = widget.conversation;

    if (_thread == null || _thread!.conversationId != conversation.id) {
      _thread = _loadThreadFromConversation(conversation);
    }

    if (rebuildFromMessagesIfMismatch) {
      final raw = (conversation.threadJson ?? '').trim();
      final hasUsableThreadJson = raw.isNotEmpty && _thread!.nodes.isNotEmpty;

      final hasBranches = _thread!.nodes.values.any((n) => n.children.length > 1);
      final messages = conversation.messages;
      final messagesLastId = messages.isEmpty ? '' : messages.last.id;

      // Phase 1 (tree as source-of-truth):
      // - If there is NO usable threadJson yet, build a linear thread from messages.
      // - If the current thread is still linear (no branches), keep it synced with
      //   the legacy linear list to avoid breaking existing delete/truncate paths.
      // - Once branches exist, never rebuild from `conversation.messages`.
      final shouldRebuildFromMessages = !hasUsableThreadJson ||
          (!hasBranches &&
              (_thread!.nodes.length != messages.length ||
                  _thread!.activeLeafId != messagesLastId));

      if (shouldRebuildFromMessages) {
        _thread = ConversationThread.fromLinearMessages(conversation.id, messages);
        _persistThreadNoSave(_thread!);
      }
    }

    return _thread!;
  }

  ConversationThread _loadThreadFromConversation(Conversation conversation) {
    final raw = (conversation.threadJson ?? '').trim();
    if (raw.isNotEmpty) {
      try {
        final decoded = jsonDecode(raw);
        if (decoded is Map<String, dynamic>) {
          _lastPersistedThreadJson = raw;
          return ConversationThread.fromJson(decoded);
        }
        if (decoded is Map) {
          _lastPersistedThreadJson = raw;
          return ConversationThread.fromJson(decoded.cast<String, dynamic>());
        }
      } catch (_) {
        // Fall back to linear messages.
      }
    }

    return ConversationThread.fromLinearMessages(
      conversation.id,
      conversation.messages,
    );
  }

  void _persistThreadNoSave(ConversationThread thread) {
    final encoded = jsonEncode(thread.toJson());
    _lastPersistedThreadJson = encoded;
    widget.conversation.threadJson = encoded;
    widget.conversation.activeLeafId = thread.activeLeafId;
  }

  void _schedulePersistThread({
    Duration delay = const Duration(milliseconds: 350),
  }) {
    if (_isDisposed) return;
    _persistThreadTimer?.cancel();
    _persistThreadTimer = Timer(delay, () {
      if (_isDisposed) return;
      final thread = _thread;
      if (thread == null) return;

      final encoded = jsonEncode(thread.toJson());
      if (encoded == _lastPersistedThreadJson) return;

      _lastPersistedThreadJson = encoded;
      widget.conversation.threadJson = encoded;
      widget.conversation.activeLeafId = thread.activeLeafId;
      widget.onConversationUpdated();
    });
  }

  void _flushPersistThreadNow() {
    if (_isDisposed) return;

    _persistThreadTimer?.cancel();
    _persistThreadTimer = null;

    final thread = _thread;
    if (thread == null) return;

    final encoded = jsonEncode(thread.toJson());
    if (encoded == _lastPersistedThreadJson) return;

    _lastPersistedThreadJson = encoded;
    widget.conversation.threadJson = encoded;
    widget.conversation.activeLeafId = thread.activeLeafId;
    if (mounted && !_isDisposed) {
      widget.onConversationUpdated();
    }
  }

  void _syncConversationMessagesSnapshotFromThread(ConversationThread thread) {
    final chain = buildActiveMessageChain(thread);
    final messages = widget.conversation.messages;
    messages
      ..clear()
      ..addAll(chain);
  }

  void _scheduleImagePersistenceSweep({
    Duration delay = const Duration(milliseconds: 650),
  }) {
    if (_isDisposed) return;

    final conversationId = widget.conversation.id;
    if (_imagePersistenceSweptConversationId == conversationId) return;

    final epoch = ++_imagePersistenceSweepEpoch;
    unawaited(() async {
      await Future<void>.delayed(delay);
      if (_isDisposed || !mounted) return;
      if (epoch != _imagePersistenceSweepEpoch) return;
      if (widget.conversation.id != conversationId) return;
      if (_imagePersistenceSweptConversationId == conversationId) return;
      if (_imagePersistenceSweepRunning) return;

      _imagePersistenceSweepRunning = true;
      try {
        await _runImagePersistenceSweep(
          epoch: epoch,
          conversationId: conversationId,
        );
        if (_isDisposed || !mounted) return;
        if (epoch != _imagePersistenceSweepEpoch) return;
        if (widget.conversation.id != conversationId) return;
        _imagePersistenceSweptConversationId = conversationId;
      } finally {
        if (epoch == _imagePersistenceSweepEpoch) {
          _imagePersistenceSweepRunning = false;
        }
      }
    }());
  }

  Future<void> _runImagePersistenceSweep({
    required int epoch,
    required String conversationId,
  }) async {
    if (_isDisposed) return;
    if (epoch != _imagePersistenceSweepEpoch) return;
    if (widget.conversation.id != conversationId) return;

    final thread = _getThread(rebuildFromMessagesIfMismatch: false);
    final chain = buildActiveMessageChain(thread);

    var changed = false;
    for (final msg in chain) {
      if (_isDisposed) return;
      if (epoch != _imagePersistenceSweepEpoch) return;
      if (widget.conversation.id != conversationId) return;
      if (msg.isUser) continue;

      final result = await ImagePersistenceService()
          .persistMarkdownImagesToLocalFiles(msg.content);
      if (!result.changed) continue;

      msg.content = result.markdown;
      _chatMessageCache.remove(msg.id);
      _chatMessageCacheFingerprints.remove(msg.id);
      changed = true;
    }

    if (!changed) return;

    _syncConversationMessagesSnapshotFromThread(thread);
    _persistThreadNoSave(thread);
    _schedulePersistThread(delay: Duration.zero);
    _syncConversationToChatController();
  }

  Future<void> _persistMarkdownImagesForMessageId(String messageId) async {
    if (_isDisposed) return;
    if (_persistingMarkdownMessageIds.contains(messageId)) return;

    _persistingMarkdownMessageIds.add(messageId);
    try {
      final thread = _getThread(rebuildFromMessagesIfMismatch: false);
      final node = thread.nodes[messageId];
      if (node == null || node.message.isUser) return;

      final msg = node.message;
      final result = await ImagePersistenceService()
          .persistMarkdownImagesToLocalFiles(msg.content);
      if (_isDisposed) return;
      if (!result.changed) return;

      msg.content = result.markdown;
      _chatMessageCache.remove(messageId);
      _chatMessageCacheFingerprints.remove(messageId);

      _syncConversationMessagesSnapshotFromThread(thread);
      _persistThreadNoSave(thread);
      _schedulePersistThread(delay: Duration.zero);
      _syncConversationToChatController();
    } finally {
      _persistingMarkdownMessageIds.remove(messageId);
    }
  }

  int _fingerprintAppMessage(app.Message message) {
    final attachments = message.attachedFiles;
    final attachmentsKey = attachments == null || attachments.isEmpty
        ? 0
        : Object.hashAll(
            attachments.map(
              (f) => Object.hash(f.id, f.path, f.mimeType, f.name),
            ),
          );

    return Object.hash(
      message.isUser,
      message.content,
      message.timestamp.millisecondsSinceEpoch,
      message.inputTokens ?? -1,
      message.outputTokens ?? -1,
      message.modelName ?? '',
      message.providerName ?? '',
      attachmentsKey,
    );
  }

  chat.Message _toFlutterChatMessageCached(app.Message message) {
    final fp = _fingerprintAppMessage(message);
    final cachedFp = _chatMessageCacheFingerprints[message.id];
    final cached = _chatMessageCache[message.id];

    if (cached != null && cachedFp == fp) return cached;

    final converted = ChatMessageAdapter.toFlutterChatMessage(message);
    _chatMessageCache[message.id] = converted;
    _chatMessageCacheFingerprints[message.id] = fp;
    return converted;
  }

  chat.Message _toFlutterChatMessage(app.Message message) {
    return _toFlutterChatMessageCached(message);
  }

  List<String> _assistantVariantIdsForUser(
    String userMessageId,
    ConversationThread thread,
  ) {
    final node = thread.nodes[userMessageId];
    if (node == null) return const <String>[];
    if (!node.message.isUser) return const <String>[];

    final result = <String>[];
    for (final childId in node.children) {
      final child = thread.nodes[childId];
      if (child == null) continue;
      if (child.message.isUser) continue;
      result.add(childId);
    }
    return result;
  }

  Future<void> _switchAssistantVariant(String userMessageId, int delta) async {
    if (_isDisposed) return;
    if (_isLoading || _streamController.isStreaming) {
      GlobalToast.warning(context, message: '请先停止输出再切换版本');
      return;
    }

    final thread = _getThread(rebuildFromMessagesIfMismatch: false);
    final variants = _assistantVariantIdsForUser(userMessageId, thread);
    if (variants.length <= 1) return;

    final selected = thread.selectedChild[userMessageId];
    var index = selected == null ? -1 : variants.indexOf(selected);
    if (index < 0) index = variants.length - 1;

    final rawNext = index + delta;
    final nextIndex = ((rawNext % variants.length) + variants.length) % variants.length;

    thread.selectedChild[userMessageId] = variants[nextIndex];
    thread.normalize();

    _syncConversationMessagesSnapshotFromThread(thread);
    _persistThreadNoSave(thread);
    _schedulePersistThread(delay: const Duration(milliseconds: 220));

    _syncConversationToChatController();
    scrollToMessage(userMessageId);
  }

  void scrollToMessage(String messageId);

  /// 显示流式渲染参数调试面板
  void showTuningPanel() {
    setState(() => _showTuningPanel = true);
  }

  void _syncConversationToChatController();

  void _handleStreamFlush(String content);

  bool _handleChatScrollNotification(ScrollNotification notification);


  void _requestAutoFollow({required bool smooth, bool force = false});
  Widget _wrapHighlighted({required String messageId, required Widget child});
  Widget _wrapExportSelectable({
    required chat.Message message,
    required Widget child,
  });

  Widget _buildExportModeToolbar();
  Widget _buildTokenFooter(chat.Message message, {required bool isSentByMe});
  Widget _buildUserBubble({required chat.TextMessage message});

  Future<void> _sendMessage();
  Future<void> _startAssistantResponse({
    required ({ProviderConfig provider, ModelConfig model}) modelWithProvider,
    String? parentUserMessageId,
    bool animateInsert = true,
    bool useAtomicSetMessages = false,
  });
  Future<void> _stopStreaming();
  Future<void> _showMessageActionsSheet(chat.Message message);

  bool _isProbablyNetworkUrl(String source);
  String _toFilePathIfNeeded(String source);

  int _estimatePromptTokens(List<ai.ChatMessage> messages);
  String _newMessageId();
}

class ConversationViewV2State extends _ConversationViewV2StateBase
    with
        _ConversationViewV2ScrollMixin,
        _ConversationViewV2ExportMixin,
        _ConversationViewV2TokensMixin,
        _ConversationViewV2StreamingMixin,
        _ConversationViewV2MessageActionsMixin,
        _ConversationViewV2UserBubbleMixin,
        _ConversationViewV2BuildMixin {}

