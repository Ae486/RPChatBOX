import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:scrollable_positioned_list/scrollable_positioned_list.dart';
import 'package:photo_view/photo_view.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';
import 'cached_image_widget.dart';
import '../models/message.dart';
import '../models/conversation.dart';
import '../models/chat_settings.dart';
import '../models/attached_file.dart';
import '../services/export_service.dart';
import '../utils/token_counter.dart';
import 'message_actions.dart';
import 'enhanced_content_renderer.dart';
import '../models/conversation_settings.dart';
import 'enhanced_input_area.dart';
import 'apple_toast.dart';
import '../design_system/apple_icons.dart';
import '../main.dart' show globalModelServiceManager;
import '../controllers/stream_output_controller.dart';
import '../adapters/ai_provider.dart';
import '../utils/chunk_buffer.dart';
import '../utils/smart_scroll_controller.dart';
import '../design_system/design_tokens.dart';
import '../design_system/apple_tokens.dart';
import '../themes/chatbox_chat_theme.dart';
import '../rendering/markdown/experimental_streaming_markdown_renderer.dart';

/// 单个会话视图（保持存活状态）
class ConversationView extends StatefulWidget {
  final Conversation conversation;
  final ChatSettings settings;
  final VoidCallback onConversationUpdated;
  final Function(Conversation) onTokenUsageUpdated;

  const ConversationView({
    super.key,
    required this.conversation,
    required this.settings,
    required this.onConversationUpdated,
    required this.onTokenUsageUpdated,
  });

  @override
  State<ConversationView> createState() => ConversationViewState();
}

class ConversationViewState extends State<ConversationView>
    with AutomaticKeepAliveClientMixin, SingleTickerProviderStateMixin {
  
  final _messageController = TextEditingController();
  final _editController = TextEditingController();
  
  // 🔥 关键：使用 ItemScrollController 替代 ScrollController
  final ItemScrollController _itemScrollController = ItemScrollController();
  final ItemPositionsListener _itemPositionsListener = ItemPositionsListener.create();
  
  bool _isLoading = false;
  String _currentAssistantMessage = '';
  String? _editingMessageId;
  String? _highlightedMessageId; // 高亮的消息 ID

  // 导出模式相关
  bool _isExportMode = false;
  final Set<String> _selectedMessageIds = {};

  // 🔥 智能滚动相关
  bool _isUserNearBottom = true; // 用户是否在底部附近
  bool _showNewMessageButton = false; // 是否显示"新消息"按钮
  bool _isUserScrolling = false; // 用户是否正在主动滚动
  bool _autoScrollEnabled = true; // 自动滚动是否启用
  DateTime? _lastUserScrollTime; // 用户最后一次滚动时间
  Timer? _scrollDebounceTimer; // 滚动防抖定时器
  Timer? _autoScrollTimer; // 自动滚动定时器
  int _lastScrollIndex = -1; // 上次滚动的索引，用于检测变化

  // 🆕 新功能相关
  late ConversationSettings _conversationSettings;
  late EnhancedStreamController _streamController;
  bool _attachmentBarVisible = true; // 附件栏可见性控制
  AIProvider? _currentProvider; // 🔥 当前流式输出的 Provider，用于取消请求
  bool _isInitializing = true; // 初始化加载状态
  
  // 🆕 流式输出优化组件
  ChunkBuffer? _chunkBuffer;
  SmartScrollController? _smartScrollController;
  
  // 🧠 思考气泡状态
  bool _thinkingVisible = false;
  bool _thinkingExpanded = false;
  bool _isThinkingOpen = false;
  String _thinkingContent = '';
  String? _currentThinkingEndTag; // 当前使用的结束标签（用于跨chunk匹配）
  DateTime? _thinkingStartTime;
  Timer? _thinkingTimer;
  AnimationController? _bulbController; // 呼吸动画（可为空，热重载下更安全）
  final AlwaysStoppedAnimation<double> _staticScale = AlwaysStoppedAnimation<double>(1.0);
  final ScrollController _thinkingScrollController = ScrollController();
  final Map<String, bool> _savedThinkingExpanded = {}; // 已保存消息折叠状态
  DateTime? _currentUserSendTime; // 当前轮用户消息时间（用于冻结流式气泡头部时间）
  final ValueNotifier<int> _thinkingSeconds = ValueNotifier<int>(0);
  final Map<String, int> _savedThinkingDurations = {}; // 保存消息的思考时长（秒）
  String _pendingBodyBuffer = '';
  bool _holdBodyUntilThinkEnd = false;
  DateTime? _thinkingEndTime;
  bool _hasBodyStartedAfterThink = false; // 正文是否已在思考之后开始输出
  
  // 🔥 关键：保持页面存活，不销毁
  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();

    // 呼吸灯动画控制器
    _bulbController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
      lowerBound: 0.92,
      upperBound: 1.08,
    )..value = 1.0;

    // 初始化自动滚动状态
    _autoScrollEnabled = true;
    _isUserNearBottom = true;

    // 初始化对话配置
    _conversationSettings = globalModelServiceManager.getConversationSettings(widget.conversation.id);

    // 初始化流式控制器
    _streamController = EnhancedStreamController();

    // 初始化 Chunk 缓冲器
    _chunkBuffer = ChunkBuffer(
      onFlush: (content) {
        setState(() {
          _handleStreamContent(content);
        });
        if (_smartScrollController != null) {
          final messagesCount = widget.conversation.messages.length;
          final hasGenerating = _isLoading || _currentAssistantMessage.isNotEmpty;
          final totalItems = messagesCount + (hasGenerating ? 1 : 0) + 1;
          _smartScrollController!.autoScrollToBottom(
            messageCount: totalItems,
            smooth: false,
          );
        }
      },
      flushInterval: const Duration(milliseconds: 50),
      flushThreshold: 30,
      enableDebugLog: true,
    );

    // 初始化智能滚动控制器
    _smartScrollController = SmartScrollController(
      scrollController: _itemScrollController,
      positionsListener: _itemPositionsListener,
      lockThreshold: 10.0,
      unlockThreshold: 50.0,
      enableDebugLog: true,
    );

    // 监听滚动位置变化
    _itemPositionsListener.itemPositions.addListener(_onScrollPositionChanged);

    // 初始化时滚动到底部
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (_itemScrollController.isAttached && widget.conversation.messages.isNotEmpty) {
        final messagesCount = widget.conversation.messages.length;
        final hasGenerating = _isLoading || _currentAssistantMessage.isNotEmpty;
        final totalItems = messagesCount + (hasGenerating ? 1 : 0) + 1;
        final spacerIndex = totalItems - 1;
        _itemScrollController.jumpTo(index: spacerIndex);
        debugPrint('✅ 初始化滚动到底部占位符，索引: $spacerIndex (messagesCount: $messagesCount)');
      }

      await Future.delayed(const Duration(milliseconds: 100));
      if (mounted) {
        setState(() {
          _isInitializing = false;
        });
      }
    });
  }

  void _ensureThinkingTimerStarted() {
    if (_thinkingStartTime == null) {
      _thinkingStartTime = DateTime.now();
    }
    // 立即同步一次
    if (_thinkingStartTime != null) {
      _thinkingSeconds.value = DateTime.now().difference(_thinkingStartTime!).inSeconds;
    }
    _thinkingTimer ??= Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      if (_thinkingStartTime != null) {
        _thinkingSeconds.value = DateTime.now().difference(_thinkingStartTime!).inSeconds;
      }
      _autoScrollThinking();
    });
    if (!(_bulbController?.isAnimating ?? false)) {
      _bulbController?.repeat(reverse: true);
    }
  }

  void _stopThinkingTimer() {
    _thinkingTimer?.cancel();
    _thinkingTimer = null;
    if (_bulbController?.isAnimating ?? false) {
      _bulbController?.stop();
      _bulbController?.value = 1.0;
    }
  }
  
  void _handleStreamContent(String chunk) {
    // 🐛 调试：打印进入的原始 chunk（截断显示）
    final preview = chunk.length > 200 ? '${chunk.substring(0, 200)}…' : chunk;
    debugPrint('🧩 [flush->handle] len=${chunk.length} preview="$preview"');
    
    // 🧠 支持多种思考标签变体（按优先级）
    const thinkingTags = [
      ('<thinking>', '</thinking>'),
      ('<think>', '</think>'),
      ('<thought>', '</thought>'),
      ('<thoughts>', '</thoughts>'),
    ];
    
    var remaining = chunk;
    // 如果之前有未结束的思考段，优先补齐
    if (_isThinkingOpen) {
      // 使用之前检测到的标签类型
      final endTag = _currentThinkingEndTag ?? '</think>';
      final endIdx = remaining.indexOf(endTag);
      if (endIdx != -1) {
        _thinkingContent += remaining.substring(0, endIdx);
        remaining = remaining.substring(endIdx + endTag.length);
        _isThinkingOpen = false;
        _currentThinkingEndTag = null; // 标签已闭合，清空
        _thinkingEndTime = DateTime.now();
        _stopThinkingTimer();
        if (_pendingBodyBuffer.isNotEmpty) {
          final pending = _pendingBodyBuffer;
          _currentAssistantMessage += pending;
          _pendingBodyBuffer = '';
          if (!_hasBodyStartedAfterThink && pending.trim().isNotEmpty) {
            _hasBodyStartedAfterThink = true; // 首次正文出现
            _thinkingExpanded = false; // 仅首次强制折叠
          }
        }
        _holdBodyUntilThinkEnd = false;
        debugPrint('💡 [think] closed pending block, thinkLen=${_thinkingContent.length}');
      } else {
        _thinkingContent += remaining;
        remaining = '';
        debugPrint('💡 [think] appended to pending, thinkLen=${_thinkingContent.length}');
      }
    }

    // 解析本段中的思考标签
    while (true) {
      // 查找最早出现的思考标签
      int earliestIndex = -1;
      String? detectedStartTag;
      String? detectedEndTag;
      
      for (final (startTag, endTag) in thinkingTags) {
        final idx = remaining.indexOf(startTag);
        if (idx != -1 && (earliestIndex == -1 || idx < earliestIndex)) {
          earliestIndex = idx;
          detectedStartTag = startTag;
          detectedEndTag = endTag;
        }
      }
      
      if (earliestIndex == -1) break; // 没有找到任何思考标签
      
      final s = earliestIndex;
      final startTag = detectedStartTag!;
      final endTag = detectedEndTag!;
      final before = remaining.substring(0, s);
      final afterStart = s + startTag.length;
      if (before.isNotEmpty) {
        if (_holdBodyUntilThinkEnd || _thinkingVisible || _isThinkingOpen) {
          _pendingBodyBuffer += before;
        } else {
          _currentAssistantMessage += before;
        }
        debugPrint('✍️  [content] appended ${before.length} chars, contentLen=${_currentAssistantMessage.length} pendingLen=${_pendingBodyBuffer.length}');
      }
      final endIdx = remaining.indexOf(endTag, afterStart);
      _thinkingVisible = true;
      _ensureThinkingTimerStarted();
      _holdBodyUntilThinkEnd = true;
      if (endIdx != -1) {
        _thinkingContent += remaining.substring(afterStart, endIdx);
        remaining = remaining.substring(endIdx + endTag.length);
        _isThinkingOpen = false;
        _currentThinkingEndTag = null; // 标签已闭合，清空
        _thinkingEndTime = DateTime.now();
        _stopThinkingTimer();
        // 正文开始，折叠思考框为 header-only
        _thinkingExpanded = false;
        if (_pendingBodyBuffer.isNotEmpty) {
          _currentAssistantMessage += _pendingBodyBuffer;
          _pendingBodyBuffer = '';
          _hasBodyStartedAfterThink = true;
        }
        _holdBodyUntilThinkEnd = false;
        debugPrint('💡 [think] inline block closed, tag=$startTag, thinkLen=${_thinkingContent.length}');
        _autoScrollThinking();
      } else {
        _thinkingContent += remaining.substring(afterStart);
        _isThinkingOpen = true;
        _currentThinkingEndTag = endTag; // 保存结束标签以便下次chunk使用
        remaining = '';
        debugPrint('💡 [think] open block started, tag=$startTag, thinkLen=${_thinkingContent.length}');
        _autoScrollThinking();
        break;
      }
    }

    if (remaining.isNotEmpty) {
      if (_holdBodyUntilThinkEnd || _isThinkingOpen) {
        _pendingBodyBuffer += remaining;
        debugPrint('✍️  [content] tail buffered ${remaining.length} chars, pendingLen=${_pendingBodyBuffer.length}');
      } else {
        _currentAssistantMessage += remaining;
        if (_thinkingContent.isNotEmpty && !_isThinkingOpen) {
          // 仅在首次检测到非空正文 token 时，设置 body started 并折叠
          if (!_hasBodyStartedAfterThink && remaining.trim().isNotEmpty) {
            _hasBodyStartedAfterThink = true;
            _thinkingExpanded = false;
          }
        }
        debugPrint('✍️  [content] tail appended ${remaining.length} chars, contentLen=${_currentAssistantMessage.length}');
      }
    }
  }

  void _autoScrollThinking() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_thinkingScrollController.hasClients) return;
      final max = _thinkingScrollController.position.maxScrollExtent;
      // 强制跟随到底部（思考框内的内容取消限制）
      _thinkingScrollController.animateTo(
        max,
        duration: const Duration(milliseconds: 120),
        curve: Curves.easeOut,
      );
    });
  }
  
  @override
  void dispose() {
    _messageController.dispose();
    _editController.dispose();
    _itemPositionsListener.itemPositions.removeListener(_onScrollPositionChanged);
    _scrollDebounceTimer?.cancel();
    _autoScrollTimer?.cancel();
    _streamController.dispose(); // 🆕 清理流式控制器
    
    // 🆕 清理优化组件
    _chunkBuffer?.dispose();
    _smartScrollController?.dispose();
    _thinkingTimer?.cancel();
    _bulbController?.dispose();
    _thinkingScrollController.dispose();
    
    super.dispose();
  }

  /// 滚动位置变化时自动保存
  void _onScrollPositionChanged() {
    final positions = _itemPositionsListener.itemPositions.value;
    if (positions.isNotEmpty) {
      // 保存第一个可见消息的索引
      final firstVisibleIndex = positions
          .where((position) => position.itemTrailingEdge > 0)
          .reduce((a, b) => a.index < b.index ? a : b)
          .index;

      // 检测用户是否在主动滚动
      final currentTime = DateTime.now();
      final isUserInitiatedScroll = _lastScrollIndex != firstVisibleIndex &&
          _lastScrollIndex != -1 &&
          (_lastUserScrollTime == null ||
           currentTime.difference(_lastUserScrollTime!).inMilliseconds < 1000);

      if (isUserInitiatedScroll) {
        _markUserScrolling();
      }

      // 更新用户是否在底部的状态（需要context获取屏幕高度）
      if (mounted && context.mounted) {
        _updateUserNearBottomStatus(positions, context);
      }

      _lastScrollIndex = firstVisibleIndex;

      // 🔴 已禁用：只在位置真正改变时保存（防止频繁写入）
      // if (widget.conversation.scrollIndex != firstVisibleIndex) {
      //   widget.conversation.scrollIndex = firstVisibleIndex;
      //   // 延迟保存，避免滚动时频繁触发
      //   Future.delayed(const Duration(milliseconds: 500), () {
      //     widget.onConversationUpdated();
      //   });
      // }
    }
  }

  /// 标记用户正在滚动
  void _markUserScrolling() {
    setState(() {
      _isUserScrolling = true;
      _lastUserScrollTime = DateTime.now();
      // 用户主动滚动时，暂时禁用自动滚动
      _autoScrollEnabled = false;
    });

    // 取消之前的防抖定时器
    _scrollDebounceTimer?.cancel();

    // 设置新的防抖定时器，1秒后恢复自动滚动
    _scrollDebounceTimer = Timer(const Duration(seconds: 1), () {
      if (mounted) {
        setState(() {
          _isUserScrolling = false;
          // 只有在用户接近底部时才恢复自动滚动
          _autoScrollEnabled = _isUserNearBottom;
        });
      }
    });
  }

  /// 更新用户是否在底部的状态
  /// 优化：使用绝对像素距离（150px）而非相对位置阈值
  /// 
  /// [positions] 当前可见的item位置列表
  /// [context] BuildContext用于获取屏幕高度
  void _updateUserNearBottomStatus(Iterable<ItemPosition> positions, BuildContext context) {
    if (positions.isEmpty) return;

    final totalMessages = widget.conversation.messages.length + (_currentAssistantMessage.isEmpty ? 0 : 1);
    if (totalMessages == 0) return;

    // 获取viewport高度
    final viewportHeight = MediaQuery.of(context).size.height;
    
    // 获取最后一条消息的位置
    final lastMessageIndex = totalMessages - 1;
    
    // 查找最后一条消息是否可见
    final lastMessagePosition = positions.firstWhere(
      (pos) => pos.index == lastMessageIndex,
      orElse: () => ItemPosition(
        index: -1,
        itemLeadingEdge: 2.0,  // 设置为屏幕外（>1）
        itemTrailingEdge: 2.0,
      ),
    );

    // 计算距离底部的绝对像素距离
    // itemTrailingEdge: 0表示item底部在屏幕顶部，1表示item底部在屏幕底部
    // distanceFromBottom = (1.0 - itemTrailingEdge) * viewportHeight
    final distanceFromBottomPx = (1.0 - lastMessagePosition.itemTrailingEdge) * viewportHeight;
    
    // 判断：距离底部小于150px视为"在底部附近"
    const bottomThresholdPx = 150.0;
    final isNearBottom = lastMessagePosition.index == lastMessageIndex && 
                        distanceFromBottomPx < bottomThresholdPx;

    if (_isUserNearBottom != isNearBottom) {
      setState(() {
        _isUserNearBottom = isNearBottom;
        // 用户回到底部时，重新启用自动滚动
        if (isNearBottom) {
          _autoScrollEnabled = true;
        }
      });
    }
  }

  /// 恢复滚动位置
  /// 🔴 已禁用：该功能在切换对话时会导致频繁IO和性能问题
  /// 保留代码以便未来需要时重新启用
  void _restoreScrollPosition() {
    // if (widget.conversation.scrollIndex != null && 
    //     _itemScrollController.isAttached) {
    //   final targetIndex = widget.conversation.scrollIndex!;
    //   final maxIndex = widget.conversation.messages.length - 1;
    //   
    //   // 确保索引有效
    //   if (targetIndex >= 0 && targetIndex <= maxIndex) {
    //     _itemScrollController.jumpTo(index: targetIndex);
    //     debugPrint('✅ 恢复滚动位置到索引: $targetIndex');
    //   }
    // }
  }

  /// 公开方法：滚动到指定消息（使用 ItemScrollController - 100% 可靠）
  void scrollToMessage(String messageId) {
    final index = widget.conversation.messages.indexWhere((m) => m.id == messageId);
    
    if (index < 0) {
      debugPrint(' 未找到消息: $messageId');
      return;
    }
    
    debugPrint(' 滚动到消息索引: $index');
    
    // 设置高亮
    setState(() {
      _highlightedMessageId = messageId;
    });
    
    // 2 秒后取消高亮
    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) {
        setState(() {
          _highlightedMessageId = null;
        });
      }
    });
    
    // 🔥 核心：使用 ItemScrollController 直接跳转到索引
    // 这个方法 100% 可靠，不依赖任何估算或 GlobalKey
    if (_itemScrollController.isAttached) {
      _itemScrollController.scrollTo(
        index: index,
        duration: const Duration(milliseconds: 500),
        curve: Curves.easeInOut,
        alignment: 0.2, // 消息显示在屏幕 20% 位置
      );
      debugPrint('✅ 滚动成功（索引: $index）');
    } else {
      debugPrint('⚠️ ItemScrollController 未附加');
    }
  }

  /// 智能滚动到底部（优化版）
  /// 用于自动追随 AI 回复，跳转到最后一条消息的顶部
  void _scrollToBottom({bool smooth = false}) {
    // 只有在自动滚动启用且用户不在主动滚动时才执行
    if (!_autoScrollEnabled || _isUserScrolling) {
      return;
    }

    // 如果用户不在底部附近，不自动滚动
    if (!_isUserNearBottom) {
      return;
    }

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_itemScrollController.isAttached) {
        final totalItems = widget.conversation.messages.length + (_currentAssistantMessage.isEmpty ? 0 : 1);
        final lastIndex = totalItems - 1;

        if (lastIndex >= 0) {
          if (smooth) {
            // 使用平滑滚动动画
            _itemScrollController.scrollTo(
              index: lastIndex,
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeOutCubic,
            );
          } else {
            // 直接跳转（用于流式输出时的频繁更新）
            _itemScrollController.jumpTo(index: lastIndex);
          }
        }
      }
    });
  }

  /// 滚动到真正的底部（最后一条消息的底部）
  /// 专门用于"回到底部"按钮，与消息搜索定位功能无关
  void _scrollToActualBottom() {
    // 🔥 修复：计算最新的消息数量（包括正在生成的消息和底部占位符）
    final messagesCount = widget.conversation.messages.length;
    final hasCurrentMessage = _currentAssistantMessage.isNotEmpty;
    final totalItems = messagesCount + (hasCurrentMessage ? 1 : 0) + 1; // +1 为底部占位符
    
    // ✅ 使用智能滚动控制器，并传入最新的消息数量
    if (_smartScrollController != null) {
      _smartScrollController!.scrollToBottom(
        smooth: true,
        messageCount: totalItems, // 🔥 关键修复：传入最新的总项数
      );
    } else {
      // 降级处理（如果控制器未初始化）
      if (!_itemScrollController.isAttached) {
        debugPrint('⚠️ _scrollToActualBottom: ItemScrollController 未附加');
        return;
      }

      if (messagesCount == 0) {
        debugPrint('⚠️ _scrollToActualBottom: 没有消息');
        return;
      }

      final spacerIndex = totalItems - 1;
      _itemScrollController.scrollTo(
        index: spacerIndex,
        duration: const Duration(milliseconds: 500),
        curve: Curves.easeInOutCubic,
      );
      
      debugPrint('✅ _scrollToActualBottom: 已滚动到底部占位符索引 $spacerIndex');
    }
  }

  /// 节流滚动：用于流式输出
  void _throttledScrollToBottom() {
    // 取消之前的定时器
    _autoScrollTimer?.cancel();

    // 设置新的定时器，500ms后执行滚动
    _autoScrollTimer = Timer(const Duration(milliseconds: 500), () {
      if (mounted && _isLoading) {
        _scrollToBottom(smooth: true);
      }
    });
  }

  /// 发送消息（使用新的流式控制器）
  Future<void> _sendMessage() async {
    final text = _messageController.text.trim();
    final hasFiles = _conversationSettings.hasAttachedFiles;

    // 允许：有文本 或 有附件
    if (text.isEmpty && !hasFiles) return;

    // 获取选择的Provider和Model
    final modelId = _conversationSettings.selectedModelId;
    if (modelId == null) {
      // 🆕 使用全局提示框
      AppleToast.warning(context, message: '请先选择一个模型');
      return;
    }

    final modelWithProvider = globalModelServiceManager.getModelWithProvider(modelId);
    if (modelWithProvider == null) {
      // 🆕 使用全局提示框
      AppleToast.error(context, message: '无法找到指定的模型');
      return;
    }

    // 🔥 关键：立即隐藏附件栏（优雅体验）
    if (hasFiles) {
      setState(() {
        _attachmentBarVisible = false;
      });
    }

    // 计算用户消息的 token
    final userInputTokens = TokenCounter.estimateTokens(text);

    // 添加用户消息
    final userMessage = Message(
      id: DateTime.now().millisecondsSinceEpoch.toString(),
      content: text,
      isUser: true,
      timestamp: DateTime.now(),
      inputTokens: userInputTokens,
      attachedFiles: _conversationSettings.attachedFiles
          .map((f) => AttachedFileSnapshot.fromAttachedFile(f))
          .toList(),
    );

    setState(() {
      widget.conversation.addMessage(userMessage);
      _messageController.clear();
      _isLoading = true;
      _currentAssistantMessage = '';
      _currentUserSendTime = userMessage.timestamp;
      // 重置思考状态
      _thinkingVisible = false;
      _thinkingExpanded = false;
      _isThinkingOpen = false;
      _thinkingContent = '';
      _currentThinkingEndTag = null;
      _thinkingStartTime = null;
      _thinkingEndTime = null;
      _pendingBodyBuffer = '';
      _holdBodyUntilThinkEnd = false;
      _hasBodyStartedAfterThink = false;
    });
    _stopThinkingTimer();

    _scrollToBottom();
    widget.onConversationUpdated();

    try {
      // 创建 Provider 实例
      final provider = globalModelServiceManager.createProviderInstance(
        modelWithProvider.provider.id,
      );
      
      // 🔥 保存 Provider 实例以便取消请求
      _currentProvider = provider;

      // 准备消息列表
      final chatMessages = <ChatMessage>[];

      // 添加系统提示词
      if (widget.conversation.systemPrompt != null) {
        chatMessages.add(ChatMessage(
          role: 'system',
          content: widget.conversation.systemPrompt!,
        ));
      }

      // 添加对话历史
      for (var msg in widget.conversation.messages) {
        chatMessages.add(ChatMessage(
          role: msg.isUser ? 'user' : 'assistant',
          content: msg.content,
        ));
      }

      // 准备附件
      final files = _conversationSettings.attachedFiles
          .map((f) => AttachedFileData(
                path: f.path,
                mimeType: f.mimeType,
                name: f.name,
              ))
          .toList();

      // 开始流式输出
      debugPrint('🚀 [startStreaming] provider=${provider.displayName} type=${provider.type.name} model=${modelWithProvider.model.modelName} apiUrl=${modelWithProvider.provider.apiUrl}');
      await _streamController.startStreaming(
        provider: provider,
        modelName: modelWithProvider.model.modelName,
        messages: chatMessages,
        parameters: _conversationSettings.parameters,
        files: files.isNotEmpty ? files : null,
        onChunk: (chunk) {
          final cPrev = chunk.length > 200 ? '${chunk.substring(0, 200)}…' : chunk;
          debugPrint('📨 [onChunk] len=${chunk.length} preview="$cPrev"');
          // ✅ 使用 ChunkBuffer 批量处理
          _chunkBuffer?.add(chunk);
        },
        onDone: () {
          debugPrint('✅ 流式输出完成');
          
          // 🆕 确保最后的内容被刷新
          _chunkBuffer?.flush();
          _stopThinkingTimer();
          // 如仍有缓冲的正文，合并到显示内容
          if (_pendingBodyBuffer.isNotEmpty) {
            _currentAssistantMessage += _pendingBodyBuffer;
            _pendingBodyBuffer = '';
          }
          _holdBodyUntilThinkEnd = false;
          if (_thinkingStartTime != null && _thinkingEndTime == null) {
            _thinkingEndTime = DateTime.now();
          }
          
          // 保存助手消息
          if (_currentAssistantMessage.isNotEmpty || _thinkingContent.isNotEmpty) {
            final finalContent = _thinkingContent.isNotEmpty
                ? '<think>' + _thinkingContent + '</think>' + _currentAssistantMessage
                : _currentAssistantMessage;
            final inputTokens = TokenCounter.estimateTokens(text);
            final outputTokens = TokenCounter.estimateTokens(finalContent);

            final assistantMessage = Message(
              id: DateTime.now().millisecondsSinceEpoch.toString(),
              content: finalContent,
              isUser: false,
              timestamp: DateTime.now(),
              inputTokens: inputTokens,
              outputTokens: outputTokens,
              modelName: modelWithProvider.model.displayName,
              providerName: modelWithProvider.provider.name,
            );

            setState(() {
              widget.conversation.addMessage(assistantMessage);
              _currentAssistantMessage = '';
              _isLoading = false;
              _thinkingVisible = false;
              _thinkingExpanded = false;
              _isThinkingOpen = false;
              _thinkingContent = '';
              _currentThinkingEndTag = null;
              _pendingBodyBuffer = '';
              _holdBodyUntilThinkEnd = false;
              _thinkingStartTime = null;
              _thinkingEndTime = null;
              // 保存思考时长
              final dur = _thinkingSeconds.value;
              _savedThinkingDurations[assistantMessage.id] = dur;
              _thinkingSeconds.value = 0;
            });

            // 🔥 成功后：清空附件数据并恢复可见性状态
            _conversationSettings = _conversationSettings.clearFiles();
            globalModelServiceManager.updateConversationSettings(_conversationSettings);
            setState(() {
              _attachmentBarVisible = true; // 恢复状态，等待下次使用
            });

            widget.onConversationUpdated();
            widget.onTokenUsageUpdated(widget.conversation);
            _scrollToBottom();
          }
        },
        onError: (error) {
          // 🔥 失败时：恢复附件栏显示（让用户可以重试）
          setState(() {
            _isLoading = false;
            _attachmentBarVisible = true;
          });
          _stopThinkingTimer();

          if (mounted) {
            // 🆕 使用全局提示框
            AppleToast.error(context, message: '消息发送失败\n${error.toString()}');
          }
        },
      );
    } catch (e) {
      // 🔥 异常时：恢复附件栏显示
      setState(() {
        _isLoading = false;
        _attachmentBarVisible = true;
      });

      if (mounted) {
        // 🆕 使用全局提示框
        AppleToast.error(context, message: '消息发送失败\n${e.toString()}');
      }
    }
  }

  /// 停止流式输出
  Future<void> _stopStreaming() async {
    debugPrint('🛡️ [Stop] 开始停止，当前内容长度: ${_currentAssistantMessage.length}');
    debugPrint('🛡️ [Stop] _isLoading: $_isLoading, isStreaming: ${_streamController.isStreaming}');
    
    // 🔥 关键：先取消 Provider 的网络请求
    if (_currentProvider != null) {
      debugPrint('🛡️ [Stop] 调用 Provider.cancelRequest()');
      try {
        // 尝试调用 cancelRequest 方法（如果 Provider 支持）
        final providerType = _currentProvider.runtimeType.toString();
        debugPrint('🛡️ [Stop] Provider 类型: $providerType');
        
        // OpenAIProvider 有 cancelRequest 方法
        if (_currentProvider.runtimeType.toString().contains('OpenAI')) {
          (_currentProvider as dynamic).cancelRequest();
          debugPrint('🛡️ [Stop] OpenAIProvider.cancelRequest() 已调用');
        }
      } catch (e) {
        debugPrint('⚠️ [Stop] cancelRequest 失败: $e');
      }
      _currentProvider = null;
    }
    
    // 停止流控制器（不要 await，因为请求已经被取消）
    debugPrint('🛡️ [Stop] 调用 _streamController.stop()');
    _streamController.stop().then((_) {
      debugPrint('🛡️ [Stop] 流已停止， isStreaming: ${_streamController.isStreaming}');
    }).catchError((e) {
      debugPrint('⚠️ [Stop] 流停止时出错: $e');
    });

    // 使用 _currentAssistantMessage，因为它包含所有已显示的内容
    if (_currentAssistantMessage.isNotEmpty) {
      // 合并未刷新的正文缓冲
      if (_pendingBodyBuffer.isNotEmpty) {
        _currentAssistantMessage += _pendingBodyBuffer;
        _pendingBodyBuffer = '';
      }
      _holdBodyUntilThinkEnd = false;
      if (_thinkingStartTime != null && _thinkingEndTime == null) {
        _thinkingEndTime = DateTime.now();
      }
      debugPrint('🛡️ [Stop] 准备保存消息，内容: ${_currentAssistantMessage.substring(0, _currentAssistantMessage.length > 50 ? 50 : _currentAssistantMessage.length)}...');
      // 获取当前模型信息
      final modelId = _conversationSettings.selectedModelId;
      String? modelName;
      String? providerName;

      if (modelId != null) {
        final modelWithProvider = globalModelServiceManager.getModelWithProvider(modelId);
        if (modelWithProvider != null) {
          modelName = modelWithProvider.model.displayName;
          providerName = modelWithProvider.provider.name;
        }
      }

      // 保存被截断的部分内容
      final assistantMessage = Message(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        content: _currentAssistantMessage,
        isUser: false,
        timestamp: DateTime.now(),
        outputTokens: TokenCounter.estimateTokens(_currentAssistantMessage),
        modelName: modelName,
        providerName: providerName,
      );

      // 🔥 关键：先添加消息，但不立即清空 _currentAssistantMessage
      setState(() {
        widget.conversation.addMessage(assistantMessage);
        _isLoading = false;
        // 不要立即清空，避免渲染竞争
        _thinkingVisible = false;
        _thinkingExpanded = false;
        _isThinkingOpen = false;
        _thinkingContent = '';
        _currentThinkingEndTag = null;
        _pendingBodyBuffer = '';
        _holdBodyUntilThinkEnd = false;
        _thinkingStartTime = null;
        _thinkingEndTime = null;
        // 保存思考时长
        final dur = _thinkingSeconds.value;
        _savedThinkingDurations[assistantMessage.id] = dur;
        _thinkingSeconds.value = 0;
      });
      debugPrint('🛡️ [Stop] 消息已添加，总消息数: ${widget.conversation.messages.length}');
      debugPrint('🛡️ [Stop] _currentAssistantMessage 还未清空，长度: ${_currentAssistantMessage.length}');

      // 下一帧再清空临时消息，确保正式消息已渲染
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          debugPrint('🛡️ [Stop] postFrameCallback: 清空 _currentAssistantMessage');
          setState(() {
            _currentAssistantMessage = '';
          });
          debugPrint('🛡️ [Stop] postFrameCallback: 已清空，总消息数: ${widget.conversation.messages.length}');
        }
      });

      // 🔥 手动停止后：清空附件数据并恢复可见性状态
      _conversationSettings = _conversationSettings.clearFiles();
      globalModelServiceManager.updateConversationSettings(_conversationSettings);
      setState(() {
        _attachmentBarVisible = true; // 恢复状态，等待下次使用
      });

      widget.onConversationUpdated();
      widget.onTokenUsageUpdated(widget.conversation);
    } else {
      // 没有内容，但仍需清空附件
      _conversationSettings = _conversationSettings.clearFiles();
      globalModelServiceManager.updateConversationSettings(_conversationSettings);
      
      setState(() {
        _currentAssistantMessage = '';
        _isLoading = false;
        _attachmentBarVisible = true;
        _thinkingVisible = false;
        _thinkingExpanded = false;
        _isThinkingOpen = false;
        _thinkingContent = '';
        _currentThinkingEndTag = null;
        _pendingBodyBuffer = '';
        _holdBodyUntilThinkEnd = false;
        _thinkingStartTime = null;
        _thinkingEndTime = null;
      });
    }
  }

  /// 复制消息内容
  void _copyMessage(String content) {
    Clipboard.setData(ClipboardData(text: content));
    // 🆕 使用全局提示框
    AppleToast.success(context, message: '已复制到剪贴板');
  }

  /// 导出消息（进入批量导出模式）
  void _exportMessage(Message message) {
    // 进入导出模式并自动选中当前消息
    setState(() {
      _isExportMode = true;
      _selectedMessageIds.clear();
      _selectedMessageIds.add(message.id);
    });
  }

  /// 删除单条消息
  Future<void> _deleteMessage(Message message) async {
    setState(() {
      widget.conversation.removeMessage(message.id);
    });
    widget.onConversationUpdated();
  }

  /// 进入导出模式（公开方法，供外部调用）
  void enterExportMode() {
    setState(() {
      _isExportMode = true;
      _selectedMessageIds.clear();
    });
  }

  /// 退出导出模式
  void _exitExportMode() {
    setState(() {
      _isExportMode = false;
      _selectedMessageIds.clear();
    });
  }

  /// 切换消息选中状态
  void _toggleMessageSelection(String messageId) {
    setState(() {
      if (_selectedMessageIds.contains(messageId)) {
        _selectedMessageIds.remove(messageId);
      } else {
        _selectedMessageIds.add(messageId);
      }
    });
  }

  /// 全选消息
  void _selectAllMessages() {
    setState(() {
      _selectedMessageIds.clear();
      for (var message in widget.conversation.messages) {
        _selectedMessageIds.add(message.id);
      }
    });
  }

  /// 取消全选
  void _deselectAllMessages() {
    setState(() {
      _selectedMessageIds.clear();
    });
  }

  /// 导出选中的消息
  Future<void> _exportSelectedMessages() async {
    if (_selectedMessageIds.isEmpty) {
      AppleToast.warning(context, message: '请先选择要导出的消息');
      return;
    }

    // 按时间顺序获取选中的消息
    final selectedMessages = widget.conversation.messages
        .where((m) => _selectedMessageIds.contains(m.id))
        .toList();

    // 显示格式选择对话框
    final format = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('选择导出格式'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(AppleIcons.document),
              title: const Text('Markdown'),
              subtitle: Text('${selectedMessages.length} 条消息'),
              onTap: () => Navigator.pop(context, 'md'),
            ),
            ListTile(
              leading: const Icon(AppleIcons.document),
              title: const Text('纯文本'),
              subtitle: Text('${selectedMessages.length} 条消息'),
              onTap: () => Navigator.pop(context, 'txt'),
            ),
          ],
        ),
      ),
    );

    if (format == null) return;

    try {
      String filePath;
      
      if (format == 'md') {
        // 导出为 Markdown
        final content = ExportService.exportMessagesToMarkdown(
          selectedMessages,
          widget.conversation.title,
        );
        final fileName = ExportService.generateMultiMessageFileName(
          widget.conversation.title,
          selectedMessages.length,
          'md',
        );
        filePath = await ExportService.saveToFile(content, fileName);
      } else {
        // 导出为纯文本
        final content = ExportService.exportMessagesToText(
          selectedMessages,
          widget.conversation.title,
        );
        final fileName = ExportService.generateMultiMessageFileName(
          widget.conversation.title,
          selectedMessages.length,
          'txt',
        );
        filePath = await ExportService.saveToFile(content, fileName);
      }

      if (mounted) {
        Clipboard.setData(ClipboardData(text: filePath));
        AppleToast.success(
          context,
          message: '已导出 ${selectedMessages.length} 条消息\n路径已复制到剪贴板',
        );
        
        // 退出导出模式
        _exitExportMode();
      }
    } catch (e) {
      if (mounted) {
        AppleToast.error(context, message: '导出失败: $e');
      }
    }
  }

  /// 开始编辑消息
  void _startEditMessage(Message message) {
    setState(() {
      _editingMessageId = message.id;
      _editController.text = message.content;
    });
  }

  /// 取消编辑
  void _cancelEdit() {
    setState(() {
      _editingMessageId = null;
      _editController.clear();
    });
  }

  /// 保存编辑
  Future<void> _saveEdit(Message message) async {
    final newContent = _editController.text.trim();
    if (newContent.isEmpty) return;

    setState(() {
      message.content = newContent;
      _editingMessageId = null;
      _editController.clear();
    });

    widget.onConversationUpdated();
  }

  /// 保存并重新发送（仅用户消息）
  Future<void> _saveAndResend(Message message) async {
    final newContent = _editController.text.trim();
    if (newContent.isEmpty) return;

    // 保存修改
    setState(() {
      message.content = newContent;
      _editingMessageId = null;
      _editController.clear();
    });

    widget.onConversationUpdated();

    // 🔥 删除该消息及之后的所有消息（包括当前消息）
    final messageIndex = widget.conversation.messages.indexOf(message);
    if (messageIndex >= 0) {
      setState(() {
        widget.conversation.messages.removeRange(
          messageIndex,  // 🔥 从当前消息开始删除，而不是 messageIndex + 1
          widget.conversation.messages.length,
        );
      });
      widget.onConversationUpdated();
    }

    // 重新发送
    _messageController.text = newContent;
    await _sendMessage();
  }

  /// 从指定消息重新生成
  Future<void> _regenerateFromMessage(Message message) async {
    final messageIndex = widget.conversation.messages.indexOf(message);
    if (messageIndex < 0) return;

    // 🆕 步骤 1: 检查附件是否存在
    if (message.attachedFiles != null && message.attachedFiles!.isNotEmpty) {
      final existingFiles = <AttachedFileSnapshot>[];
      final missingFiles = <String>[];

      for (var fileSnapshot in message.attachedFiles!) {
        if (await fileSnapshot.exists()) {
          existingFiles.add(fileSnapshot);
        } else {
          missingFiles.add(fileSnapshot.name);
        }
      }

      // 🆕 步骤 2: 有文件缺失，询问用户是否继续
      if (missingFiles.isNotEmpty) {
        final shouldContinue = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('⚠️ 部分文件已不存在'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('以下文件无法重新发送：'),
                SizedBox(height: ChatBoxTokens.spacing.sm),
                ...missingFiles.map((name) => Padding(
                  padding: EdgeInsets.only(
                    left: ChatBoxTokens.spacing.lg,
                    top: ChatBoxTokens.spacing.xs,
                  ),
                  child: Text('• $name', style: const TextStyle(fontSize: 13)),
                )),
                SizedBox(height: ChatBoxTokens.spacing.lg),
                const Text('是否继续发送其他内容？'),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('取消'),
              ),
              TextButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('继续发送'),
              ),
            ],
          ),
        );

        if (shouldContinue != true) return;
      }

      // 🆕 步骤 3: 恢复存在的附件到输入框
      if (existingFiles.isNotEmpty) {
        final attachedFiles = <AttachedFile>[];

        for (var snapshot in existingFiles) {
          try {
            // 将快照转换回 AttachedFile 对象
            final file = await AttachedFile.fromFile(
              File(snapshot.path),
              snapshot.id,
            );
            attachedFiles.add(file);
          } catch (e) {
            debugPrint('恢复附件失败: ${snapshot.name}, 错误: $e');
          }
        }

        if (attachedFiles.isNotEmpty) {
          // 恢复到输入框状态
          _conversationSettings = _conversationSettings.copyWith(
            attachedFiles: attachedFiles,
          );
          globalModelServiceManager.updateConversationSettings(_conversationSettings);

          // 确保附件栏可见
          setState(() {
            _attachmentBarVisible = true;
          });
        }
      }
    }

    // 🆕 步骤 4: 处理消息内容和重新发送
    if (message.isUser) {
      // 用户消息：删除该消息及之后的所有消息，然后重新发送
      final userContent = message.content;

      setState(() {
        widget.conversation.messages.removeRange(
          messageIndex,
          widget.conversation.messages.length,
        );
      });
      widget.onConversationUpdated();

      _scrollToBottom();
      

      // 🔥 关键修改：即使 content 为空，只要有附件也要发送
      _messageController.text = userContent;
      await _sendMessage();
    } else {
      // AI 消息：找到上一条用户消息重新发送
      Message? previousUserMessage;
      for (var i = messageIndex - 1; i >= 0; i--) {
        if (widget.conversation.messages[i].isUser) {
          previousUserMessage = widget.conversation.messages[i];
          break;
        }
      }

      if (previousUserMessage != null) {
        // 递归调用，处理用户消息的重新生成（会自动处理附件）
        await _regenerateFromMessage(previousUserMessage);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context); // 必须调用以启用 KeepAlive

    return Stack(
      children: [
        // 底层：主内容（始终渲染，但初始化时被遮罩覆盖）
        Column(
          children: [
            // 导出模式工具栏
            if (_isExportMode) _buildExportModeToolbar(),

            // 消息列表
            Expanded(
              child: widget.conversation.messages.isEmpty && _currentAssistantMessage.isEmpty
                  ? _buildEmptyState()
                  : _buildMessageList(),
            ),

            // 输入区域
            if (!_isExportMode) _buildInputArea(),
          ],
        ),

        // 回到底部浮动按钮
        if (!_isExportMode && !_isUserNearBottom && !_isLoading)
          _buildScrollToBottomButton(),
        
        // 顶层：初始化加载遮罩（完全覆盖底层内容）
        if (_isInitializing)
          Container(
            color: Theme.of(context).scaffoldBackgroundColor,
            child: Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  SpinKitFadingCircle(
                    color: Theme.of(context).colorScheme.primary,
                    size: 60,
                  ),
                  SizedBox(height: ChatBoxTokens.spacing.xl),
                  Text(
                    '加载中...',
                    style: TextStyle(
                      fontSize: 16,
                      color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.6),
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  /// 导出模式工具栏
  Widget _buildExportModeToolbar() {
    final selectedCount = _selectedMessageIds.length;
    final totalCount = widget.conversation.messages.length;
    
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: ChatBoxTokens.spacing.lg,
        vertical: ChatBoxTokens.spacing.md,
      ),
      decoration: BoxDecoration(
        color: Theme.of(context).primaryColor.withOpacity(0.1),
        border: Border(
          bottom: BorderSide(
            color: Theme.of(context).dividerColor,
          ),
        ),
      ),
      child: Row(
        children: [
          // 关闭按钮
          IconButton(
            icon: const Icon(AppleIcons.close),
            onPressed: _exitExportMode,
            tooltip: '退出导出模式',
          ),
          SizedBox(width: ChatBoxTokens.spacing.sm),
          
          // 选中计数
          Text(
            '已选 $selectedCount / $totalCount',
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
          
          const Spacer(),
          
          // 全选按钮
          TextButton.icon(
            onPressed: selectedCount == totalCount ? _deselectAllMessages : _selectAllMessages,
            icon: Icon(selectedCount == totalCount ? AppleIcons.close : AppleIcons.selectAll),
            label: Text(selectedCount == totalCount ? '取消全选' : '全选'),
          ),
          
          SizedBox(width: ChatBoxTokens.spacing.sm),
          
          // 导出按钮
          FilledButton.icon(
            onPressed: selectedCount > 0 ? _exportSelectedMessages : null,
            icon: const Icon(AppleIcons.download),
            label: const Text('导出'),
          ),
        ],
      ),
    );
  }

  /// 空状态
  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text(
            '💬',
            style: const TextStyle(fontSize: 80),
          ),
          SizedBox(height: ChatBoxTokens.spacing.lg),
          Text(
            '开始对话吧！',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: Colors.grey.shade600,
            ),
          ),
        ],
      ),
    );
  }

  /// 消息列表
  Widget _buildMessageList() {
    // 计算总项数：消息 + 生成中的消息 + 底部占位符
    final messagesCount = widget.conversation.messages.length;
    final hasGenerating = _isLoading || _currentAssistantMessage.isNotEmpty;
    final totalItems = messagesCount + (hasGenerating ? 1 : 0) + 1; // +1 为底部占位符
    
    return ScrollablePositionedList.builder(
      itemScrollController: _itemScrollController,
      itemPositionsListener: _itemPositionsListener,
      padding: EdgeInsets.all(ChatBoxTokens.spacing.lg),
      itemCount: totalItems,
      itemBuilder: (context, index) {
        // 底部占位符：最后一项，透明的空间
        if (index == totalItems - 1) {
          return const SizedBox(height: 1); // 极小的占位符
        }

        // 普通历史消息区域
        if (index < messagesCount) {
          final msg = widget.conversation.messages[index];
          return _buildMessageBubble(
            content: msg.content,
            isUser: msg.isUser,
            timestamp: msg.timestamp,
            message: msg,
          );
        }

        // 追加生成中的消息
        var next = messagesCount;
        if (hasGenerating && index == next) {
          return _buildMessageBubble(
            content: _currentAssistantMessage,
            isUser: false,
            timestamp: _currentUserSendTime ?? DateTime.now(),
            message: null,
          );
        }

        // 兜底（不应触达）
        return const SizedBox.shrink();
      },
    );
  }

  /// 思考内联片段
  Widget _buildInlineThinkingSection() {
    // 是否显示正文区域（思考中始终展开；正文开始后默认折叠，用户可手动展开）
    final showContent = _isThinkingOpen || !_hasBodyStartedAfterThink || _thinkingExpanded;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () {
            if (!_isThinkingOpen) {
              setState(() => _thinkingExpanded = !_thinkingExpanded);
              if (_thinkingExpanded) _autoScrollThinking();
            }
          },
          borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
          child: Row(
            children: [
              ScaleTransition(
                scale: _bulbController ?? _staticScale,
                child: const Icon(AppleIcons.lightbulb, size: 16),
              ),
              SizedBox(width: ChatBoxTokens.spacing.xs + 2),
              ValueListenableBuilder<int>(
                valueListenable: _thinkingSeconds,
                builder: (_, v, __) {
                  if (_isThinkingOpen) {
                    final m = (v ~/ 60).toString().padLeft(2, '0');
                    final s = (v % 60).toString().padLeft(2, '0');
                    return Text(
                      '思考中 $m:$s',
                      style: TextStyle(
                        fontSize: 12,
                        color: Theme.of(context).colorScheme.onSurface,
                        fontWeight: FontWeight.w500,
                      ),
                    );
                  } else {
                    return Text(
                      '已思考 ${v}s',
                      style: TextStyle(
                        fontSize: 12,
                        color: Theme.of(context).colorScheme.onSurface,
                        fontWeight: FontWeight.w500,
                      ),
                    );
                  }
                },
              ),
              const Spacer(),
              // 展开指示（仅在思考结束后显示）
              if (!_isThinkingOpen)
                AnimatedCrossFade(
                  duration: const Duration(milliseconds: 150),
                  firstChild: const Icon(AppleIcons.arrowDown, size: 18),
                  secondChild: const Icon(AppleIcons.arrowUp, size: 18),
                  crossFadeState: _thinkingExpanded
                      ? CrossFadeState.showSecond
                      : CrossFadeState.showFirst,
                ),
            ],
          ),
        ),
        SizedBox(height: ChatBoxTokens.spacing.sm),
        AnimatedSize(
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeInOut,
          child: showContent
              ? Container(
                  width: double.infinity,
                  constraints: const BoxConstraints(
                    maxHeight: 160,
                    minHeight: 44,
                  ),
                  padding: EdgeInsets.all(ChatBoxTokens.spacing.md),
                  decoration: BoxDecoration(
                    color: Theme.of(context).colorScheme.surfaceContainerHigh,
                    borderRadius: BorderRadius.circular(ChatBoxTokens.radius.medium),
                  ),
                  child: SingleChildScrollView(
                    controller: _thinkingScrollController,
                    child: Text(
                      _thinkingContent.isEmpty ? '...' : _thinkingContent,
                      style: TextStyle(
                        fontSize: 14,
                        color: Theme.of(context).colorScheme.onSurface,
                        height: 1.5,
                      ),
                    ),
                  ),
                )
              : const SizedBox.shrink(),
        ),
        SizedBox(height: ChatBoxTokens.spacing.md),
      ],
    );
  }

  String _formatThinkingElapsed() {
    final start = _thinkingStartTime;
    if (start == null) return '00:00';
    final end = _thinkingEndTime;
    final diff = (end ?? DateTime.now()).difference(start);
    final m = diff.inMinutes;
    final s = diff.inSeconds % 60;
    return '${m.toString().padLeft(2, '0')}:${s.toString().padLeft(2, '0')}';
  }

  /// 解析保存内容中的思考段，返回思考和正文（支持多种标签）
  ({String think, String body}) _splitThinkSegments(String full) {
    // 🧠 支持多种思考标签变体（按优先级）
    const thinkingTags = [
      ('<thinking>', '</thinking>'),
      ('<think>', '</think>'),
      ('<thought>', '</thought>'),
      ('<thoughts>', '</thoughts>'),
    ];
    
    // 查找最早出现的思考标签
    int earliestStart = -1;
    String? detectedStartTag;
    String? detectedEndTag;
    
    for (final (startTag, endTag) in thinkingTags) {
      final idx = full.indexOf(startTag);
      if (idx != -1 && (earliestStart == -1 || idx < earliestStart)) {
        earliestStart = idx;
        detectedStartTag = startTag;
        detectedEndTag = endTag;
      }
    }
    
    if (earliestStart == -1) return (think: '', body: full);
    
    final startTag = detectedStartTag!;
    final endTag = detectedEndTag!;
    final afterStart = earliestStart + startTag.length;
    final e = full.indexOf(endTag, afterStart);
    
    if (e == -1) {
      // 没有闭合，视为全部正文
      return (think: '', body: full);
    }
    
    final think = full.substring(afterStart, e);
    final body = full.substring(0, earliestStart) + full.substring(e + endTag.length);
    return (think: think, body: body);
  }

  /// 已保存消息的思考气泡（沿用流式正文阶段的单行 header 样式，默认折叠，可点击展开内容）
  Widget _buildSavedThinkingSection({
    required String messageId,
    required String thinkText,
  }) {
    final expanded = _savedThinkingExpanded[messageId] ?? false;
    final durSec = _savedThinkingDurations[messageId] ?? 0;
    return InkWell(
      onTap: () => setState(() => _savedThinkingExpanded[messageId] = !expanded),
      borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(AppleIcons.lightbulb, size: 16),
              SizedBox(width: ChatBoxTokens.spacing.xs + 2),
              Text(
                '已思考 ${durSec}s',
                style: TextStyle(
                  fontSize: 12,
                  color: Theme.of(context).colorScheme.onSurface,
                  fontWeight: FontWeight.w500,
                ),
              ),
              const Spacer(),
              AnimatedCrossFade(
                duration: const Duration(milliseconds: 150),
                firstChild: const Icon(AppleIcons.arrowDown, size: 18),
                secondChild: const Icon(AppleIcons.arrowUp, size: 18),
                crossFadeState: expanded
                    ? CrossFadeState.showSecond
                    : CrossFadeState.showFirst,
              ),
            ],
          ),
          if (expanded) SizedBox(height: ChatBoxTokens.spacing.sm),
          AnimatedSize(
            duration: const Duration(milliseconds: 200),
            curve: Curves.easeInOut,
            child: expanded
                ? Container(
                    width: double.infinity,
                    constraints: const BoxConstraints(
                      maxHeight: 160,
                      minHeight: 44,
                    ),
                    padding: EdgeInsets.all(ChatBoxTokens.spacing.md),
                    decoration: BoxDecoration(
                      color: Theme.of(context).colorScheme.surfaceContainerHigh,
                      borderRadius: BorderRadius.circular(ChatBoxTokens.radius.medium),
                    ),
                    child: SingleChildScrollView(
                      child: Text(
                        thinkText.isEmpty ? '...' : thinkText,
                        style: TextStyle(
                          fontSize: 14,
                          color: Theme.of(context).colorScheme.onSurface,
                          height: 1.5,
                        ),
                      ),
                    ),
                  )
                : const SizedBox.shrink(),
          ),
          SizedBox(height: ChatBoxTokens.spacing.md),
        ],
      ),
    );
  }

  /// 消息气泡
  Widget _buildMessageBubble({
    required String content,
    required bool isUser,
    required DateTime timestamp,
    Message? message,
  }) {
    final isEditing = message != null && _editingMessageId == message.id;
    final isHighlighted = message != null && _highlightedMessageId == message.id;

    // AI名称：使用消息保存的模型信息
    String senderName;
    if (isUser) {
      senderName = '用户';
    } else if (message == null) {
      // 流式进行中的消息，名称使用当前选择的模型
      final modelId = _conversationSettings.selectedModelId;
      if (modelId != null) {
        final mp = globalModelServiceManager.getModelWithProvider(modelId);
        if (mp != null) {
          senderName = '${mp.model.displayName}|${mp.provider.name}';
        } else {
          senderName = 'AI助手';
        }
      } else {
        senderName = 'AI助手';
      }
    } else if (message.modelName != null && message.providerName != null) {
      senderName = '${message.modelName}|${message.providerName}';
    } else {
      senderName = 'AI助手';
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 导出模式：复选框
            if (_isExportMode && message != null)
              Padding(
                padding: EdgeInsets.only(
                  top: ChatBoxTokens.spacing.xs,
                  right: ChatBoxTokens.spacing.sm,
                ),
                child: Checkbox(
                  value: _selectedMessageIds.contains(message.id),
                  onChanged: (_) => _toggleMessageSelection(message.id),
                ),
              ),
            
            // 头像
            Padding(
              padding: EdgeInsets.only(
                top: ChatBoxTokens.spacing.xs,
                right: ChatBoxTokens.spacing.sm,
              ),
              child: CircleAvatar(
                radius: 20,
                backgroundColor: isUser
                    ? Theme.of(context).colorScheme.primary
                    : Theme.of(context).colorScheme.secondary,
                child: Icon(
                  isUser ? AppleIcons.person : AppleIcons.chatbot,
                  color: Colors.white,
                  size: 24,
                ),
              ),
            ),

            // 消息主体
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // 头部：名称
                  Text(
                    senderName,
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 14,
                      color: Theme.of(context).colorScheme.onSurface,
                    ),
                  ),
                  SizedBox(height: 2),
                  // 时间
                  Text(
                    _formatFullTimestamp(timestamp),
                    style: TextStyle(
                      fontSize: 11,
                      color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
                  ),
                  SizedBox(height: ChatBoxTokens.spacing.sm),

                  // 消息内容容器：分开渲染思考气泡与正文气泡
                  ...(() {
                    final bubbles = <Widget>[];

                    // 用户消息：单一气泡（包含附件或编辑框或正文）
                    if (isUser) {
                      bubbles.add(
                        AnimatedContainer(
                          duration: const Duration(milliseconds: 300),
                          width: double.infinity,
                          padding: EdgeInsets.symmetric(
                            horizontal: ChatBoxTokens.spacing.lg, // 16px
                            vertical: ChatBoxTokens.spacing.md,    // 12px
                          ),
                          decoration: BoxDecoration(
                            color: Theme.of(context).colorScheme.primaryContainer,
                            borderRadius: BorderRadius.circular(AppleTokens.corners.bubble), // 20px Apple风格
                            border: isHighlighted
                                ? Border.all(
                                    color: Theme.of(context).colorScheme.primary,
                                    width: 3,
                                  )
                                : null,
                            boxShadow: isHighlighted
                                ? AppleTokens.shadows.highlight(Theme.of(context).colorScheme.primary)
                                : AppleTokens.shadows.bubble, // Apple双层阴影
                          ),
                          child: isEditing
                              ? TextField(
                                  controller: _editController,
                                  maxLines: null,
                                  autofocus: true,
                                  decoration: InputDecoration(
                                    border: OutlineInputBorder(),
                                    contentPadding: EdgeInsets.all(ChatBoxTokens.spacing.sm),
                                  ),
                                )
                              : Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    if (message != null && message.attachedFiles != null && message.attachedFiles!.isNotEmpty)
                                      _buildAttachmentsPreview(message.attachedFiles!),
                                    EnhancedContentRenderer(
                                      content: content,
                                      textStyle: TextStyle(
                                        fontSize: 15,
                                        color: Theme.of(context).colorScheme.onSurface,
                                      ),
                                      backgroundColor: Theme.of(context).colorScheme.surface,
                                      isUser: true,
                                    ),
                                  ],
                                ),
                        ),
                      );
                      if (!isEditing && message != null) {
                        bubbles.add(_buildTokenInfo(message, isUser));
                      }
                      return bubbles;
                    }

                    // 助手消息：分离思考与正文
                    if (message == null) {
                      // 流式
                      if (_thinkingVisible || _isThinkingOpen || _thinkingContent.isNotEmpty) {
                        bubbles.add(
                          AnimatedContainer(
                            duration: const Duration(milliseconds: 200),
                            width: double.infinity,
                            padding: EdgeInsets.symmetric(
                              horizontal: ChatBoxTokens.spacing.lg,
                              vertical: ChatBoxTokens.spacing.md,
                            ),
                            decoration: ChatBoxChatTheme.thinkingBubbleDecoration(context),
                            child: _buildInlineThinkingSection(),
                          ),
                        );
                        bubbles.add(SizedBox(height: ChatBoxTokens.spacing.md));
                      }

                      if (content.isNotEmpty) {
                        bubbles.add(
                          AnimatedContainer(
                            duration: const Duration(milliseconds: 200),
                            width: double.infinity,
                            padding: EdgeInsets.symmetric(
                              horizontal: ChatBoxTokens.spacing.lg, // 16px
                              vertical: ChatBoxTokens.spacing.md,    // 12px
                            ),
                            decoration: ChatBoxChatTheme.assistantBubbleDecoration(context),
                            child: _conversationSettings.enableExperimentalStreamingMarkdown
                                ? ExperimentalStreamingMarkdownRenderer(
                                    text: content,
                                    textStyle: TextStyle(
                                      fontSize: 15,
                                      color: ChatBoxChatTheme.onSurfaceColor(context),
                                    ),
                                    backgroundColor: ChatBoxChatTheme.assistantBubbleColor(context),
                                    isUser: false,
                                  )
                                : EnhancedContentRenderer(
                                    content: content,
                                    textStyle: TextStyle(
                                      fontSize: 15,
                                      color: ChatBoxChatTheme.onSurfaceColor(context),
                                    ),
                                    backgroundColor: ChatBoxChatTheme.assistantBubbleColor(context),
                                    isUser: false,
                                  ),
                          ),
                        );
                      } else if (!(_thinkingVisible || _isThinkingOpen || _thinkingContent.isNotEmpty)) {
                        bubbles.add(
                          Padding(
                            padding: EdgeInsets.symmetric(vertical: ChatBoxTokens.spacing.xs),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                SpinKitThreeBounce(
                                  color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.6),
                                  size: 14,
                                ),
                                SizedBox(width: ChatBoxTokens.spacing.sm),
                                Text(
                                  '正在输入...',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.6),
                                  ),
                                )
                              ],
                            ),
                          ),
                        );
                      }
                    } else {
                      // 已保存
                      final split = _splitThinkSegments(content);
                      if (split.think.isNotEmpty) {
                        bubbles.add(
                          AnimatedContainer(
                            duration: const Duration(milliseconds: 200),
                            width: double.infinity,
                            padding: EdgeInsets.symmetric(
                              horizontal: ChatBoxTokens.spacing.lg,
                              vertical: ChatBoxTokens.spacing.md,
                            ),
                            decoration: ChatBoxChatTheme.thinkingBubbleDecoration(context),
                            child: _buildSavedThinkingSection(
                              messageId: message.id,
                              thinkText: split.think,
                            ),
                          ),
                        );
                        bubbles.add(SizedBox(height: ChatBoxTokens.spacing.md));
                      }
                      if (split.body.trim().isNotEmpty || isEditing) {
                        bubbles.add(
                          AnimatedContainer(
                            duration: const Duration(milliseconds: 200),
                            width: double.infinity,
                            padding: EdgeInsets.symmetric(
                              horizontal: ChatBoxTokens.spacing.lg, // 16px
                              vertical: ChatBoxTokens.spacing.md,    // 12px
                            ),
                            decoration: ChatBoxChatTheme.assistantBubbleDecoration(context),
                            child: isEditing
                                ? TextField(
                                    controller: _editController,
                                    maxLines: null,
                                    autofocus: true,
                                    decoration: InputDecoration(
                                      border: OutlineInputBorder(),
                                      contentPadding: EdgeInsets.all(ChatBoxTokens.spacing.sm),
                                    ),
                                  )
                                : EnhancedContentRenderer(
                                    content: split.body,
                                    textStyle: TextStyle(
                                      fontSize: 15,
                                      color: ChatBoxChatTheme.onSurfaceColor(context),
                                    ),
                                    backgroundColor: ChatBoxChatTheme.assistantBubbleColor(context),
                                    isUser: false,
                                  ),
                          ),
                        );
                      }
                      if (!isEditing) {
                        bubbles.add(_buildTokenInfo(message, isUser));
                      }
                    }

                    return bubbles;
                  }()),

                  // 操作按钮
                  if (message != null)
                    isEditing
                        ? EditModeActions(
                            onCancel: _cancelEdit,
                            onSave: () => _saveEdit(message),
                            onResend: isUser ? () => _saveAndResend(message) : null,
                          )
                        : MessageActions(
                            isUser: isUser,
                            onCopy: () => _copyMessage(content),
                            onRegenerate: () => _regenerateFromMessage(message),
                            onEdit: () => _startEditMessage(message),
                            onExport: !isUser ? () => _exportMessage(message) : null,
                            onDelete: () => _deleteMessage(message),
                          ),
                ],
              ),
            ),
          ],
        ),

        SizedBox(height: ChatBoxTokens.spacing.md),
      ],
    );
  }

  /// 构建 Token 信息显示
  Widget _buildTokenInfo(Message message, bool isUser) {
    String tokenText;
    
    if (message.isUser) {
      final tokens = message.inputTokens ?? TokenCounter.estimateTokens(message.content);
      tokenText = 'Tokens:$tokens ↑$tokens';
    } else {
      final inputTokens = message.inputTokens ?? 0;
      final outputTokens = message.outputTokens ?? TokenCounter.estimateTokens(message.content);
      final totalTokens = inputTokens + outputTokens;
      
      tokenText = 'Tokens:$totalTokens ↑$inputTokens ↓$outputTokens';
    }

    return Padding(
      padding: EdgeInsets.only(top: ChatBoxTokens.spacing.sm),
      child: Text(
        tokenText,
        style: TextStyle(
          fontSize: 10,
          color: isUser
              ? Theme.of(context).colorScheme.onPrimaryContainer.withValues(alpha: 0.5)
              : Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.5),
          fontStyle: FontStyle.italic,
        ),
      ),
    );
  }

  /// 格式化完整时间戳
  String _formatFullTimestamp(DateTime timestamp) {
    return '${timestamp.year}-${_pad(timestamp.month)}-${_pad(timestamp.day)} '
        '${_pad(timestamp.hour)}:${_pad(timestamp.minute)}:${_pad(timestamp.second)}';
  }

  /// 补零
  String _pad(int n) => n.toString().padLeft(2, '0');

  /// 回到底部浮动按钮
  Widget _buildScrollToBottomButton() {
    return Positioned(
      right: 16,
      bottom: 100, // 输入区域上方
      child: FloatingActionButton.small(
        heroTag: 'scrollToBottom_${widget.conversation.id}',
        onPressed: () {
          // 重置状态
          setState(() {
            _autoScrollEnabled = true;
            _isUserNearBottom = true;
          });
          // 使用专门的方法滚动到真正的底部
          _scrollToActualBottom();
        },
        backgroundColor: Theme.of(context).colorScheme.primary,
        foregroundColor: Theme.of(context).colorScheme.onPrimary,
        child: const Icon(AppleIcons.arrowDown),
      ),
    );
  }

  /// 输入区域（使用增强输入框）
  Widget _buildInputArea() {
    return EnhancedInputArea(
      textController: _messageController,
      onSend: _sendMessage,
      onStop: _stopStreaming,
      isStreaming: _streamController.isStreaming,
      serviceManager: globalModelServiceManager,
      conversationSettings: _conversationSettings,
      attachmentBarVisible: _attachmentBarVisible, // 🔥 传递附件栏可见性
      onSettingsChanged: (settings) {
        setState(() {
          _conversationSettings = settings;
        });
        globalModelServiceManager.updateConversationSettings(settings);
      },
    );
  }

  /// 构建附件预览（在用户气泡中显示）
  Widget _buildAttachmentsPreview(List<AttachedFileSnapshot> files) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ...files.map((file) {
          return FutureBuilder<bool>(
            future: file.exists(),
            builder: (context, snapshot) {
              final fileExists = snapshot.data ?? false;

              if (file.isImage) {
                // 图片文件：显示缩略图，可点击查看原图
                return Padding(
                  padding: EdgeInsets.only(bottom: ChatBoxTokens.spacing.sm),
                  child: fileExists
                      ? GestureDetector(
                          onTap: () => _showImageViewer(file.path, file.name),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
                            child: CachedImageWidget(
                              path: file.path,
                              fit: BoxFit.cover,
                              errorBuilder: (context, error, stackTrace) {
                                return _buildFilePlaceholder(
                                  file.name,
                                  '图片加载失败',
                                  AppleIcons.imageOff,
                                );
                              },
                            ),
                          ),
                        )
                      : _buildFilePlaceholder(
                          file.name,
                          '图片已不存在',
                          AppleIcons.imageOff,
                        ),
                );
              } else {
                // 文档/代码文件：显示可点击的卡片
                return Padding(
                  padding: EdgeInsets.only(bottom: ChatBoxTokens.spacing.sm),
                  child: fileExists
                      ? InkWell(
                          onTap: () => _openFile(file.path),
                          child: Container(
                            padding: EdgeInsets.all(ChatBoxTokens.spacing.md),
                            decoration: BoxDecoration(
                              color: Theme.of(context).colorScheme.surface,
                              borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
                              border: Border.all(
                                color: Theme.of(context)
                                    .colorScheme
                                    .outline
                                    .withOpacity(0.5),
                              ),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(
                                  _getFileIconData(file.type),
                                  color: Theme.of(context).colorScheme.primary,
                                ),
                                SizedBox(width: ChatBoxTokens.spacing.md),
                                Flexible(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        file.name,
                                        style: TextStyle(
                                          color: Theme.of(context).colorScheme.primary,
                                          decoration: TextDecoration.underline,
                                          fontWeight: FontWeight.w500,
                                        ),
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                      SizedBox(height: 2),
                                      Text(
                                        file.mimeType,
                                        style: TextStyle(
                                          fontSize: 11,
                                          color: Theme.of(context)
                                              .colorScheme
                                              .onSurface
                                              .withOpacity(0.6),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                SizedBox(width: ChatBoxTokens.spacing.sm),
                                Icon(
                                  AppleIcons.externalLink,
                                  size: 16,
                                  color: Theme.of(context)
                                      .colorScheme
                                      .onSurface
                                      .withOpacity(0.5),
                                ),
                              ],
                            ),
                          ),
                        )
                      : _buildFilePlaceholder(
                          file.name,
                          '文件已不存在',
                          AppleIcons.file,
                        ),
                );
              }
            },
          );
        }),
        SizedBox(height: ChatBoxTokens.spacing.sm),
        const Divider(height: 1),
        SizedBox(height: ChatBoxTokens.spacing.sm),
      ],
    );
  }

  /// 构建文件占位符（文件不存在时显示）
  Widget _buildFilePlaceholder(String fileName, String message, IconData icon) {
    return Container(
      padding: EdgeInsets.all(ChatBoxTokens.spacing.md),
      decoration: BoxDecoration(
        color: Colors.grey.shade200,
        borderRadius: BorderRadius.circular(ChatBoxTokens.radius.small),
        border: Border.all(color: Colors.grey.shade400),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: Colors.grey),
          SizedBox(width: ChatBoxTokens.spacing.sm),
          Flexible(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  fileName,
                  style: const TextStyle(
                    color: Colors.grey,
                    decoration: TextDecoration.lineThrough,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
                SizedBox(height: 2),
                Text(
                  message,
                  style: TextStyle(
                    fontSize: 11,
                    color: Colors.grey.shade600,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// 打开文件
  Future<void> _openFile(String path) async {
    try {
      final uri = Uri.file(path);
      if (await canLaunchUrl(uri)) {
        await launchUrl(uri);
      } else {
        if (mounted) {
          AppleToast.error(context, message: '无法打开文件: $path');
        }
      }
    } catch (e) {
      if (mounted) {
        AppleToast.error(context, message: '打开文件失败: ${e.toString()}');
      }
    }
  }

  /// 显示图片查看器（全屏，支持缩放）
  void _showImageViewer(String imagePath, String imageName) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => Scaffold(
          backgroundColor: Colors.black,
          appBar: AppBar(
            backgroundColor: Colors.black,
            foregroundColor: Colors.white,
            title: Text(imageName),
            actions: [
              IconButton(
                icon: const Icon(AppleIcons.close),
                onPressed: () => Navigator.pop(context),
              ),
            ],
          ),
          body: PhotoView(
            imageProvider: FileImage(File(imagePath)),
            minScale: PhotoViewComputedScale.contained,
            maxScale: PhotoViewComputedScale.covered * 3,
            initialScale: PhotoViewComputedScale.contained,
            backgroundDecoration: const BoxDecoration(
              color: Colors.black,
            ),
            loadingBuilder: (context, event) => Center(
              child: SpinKitFadingCircle(
                color: Colors.white,
                size: 50.0,
              ),
            ),
            errorBuilder: (context, error, stackTrace) => Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(AppleIcons.imageOff, size: 64, color: Colors.white54),
                  SizedBox(height: ChatBoxTokens.spacing.lg),
                  Text(
                    '图片加载失败',
                    style: TextStyle(color: Colors.white54),
                  ),
                ],
              ),
            ),
          ),
        ),
        fullscreenDialog: true,
      ),
    );
  }

  /// 获取文件图标
  IconData _getFileIconData(FileType type) {
    switch (type) {
      case FileType.image:
        return AppleIcons.image;
      case FileType.video:
        return AppleIcons.video;
      case FileType.audio:
        return AppleIcons.audio;
      case FileType.document:
        return AppleIcons.document;
      case FileType.code:
        return AppleIcons.code;
      case FileType.other:
        return AppleIcons.file;
    }
  }
}

