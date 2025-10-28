import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:scrollable_positioned_list/scrollable_positioned_list.dart';
import '../models/message.dart';
import '../models/conversation.dart';
import '../models/chat_settings.dart';
import '../services/openai_service.dart';
import '../services/export_service.dart';
import '../utils/token_counter.dart';
import 'message_actions.dart';
import 'smart_content_renderer.dart';
import 'enhanced_content_renderer.dart';
import '../models/conversation_settings.dart';
import '../controllers/stream_output_controller.dart';
import '../adapters/ai_provider.dart';
import 'enhanced_input_area.dart';
import '../main.dart' show globalModelServiceManager;

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
    with AutomaticKeepAliveClientMixin {
  
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
  
  // 🔥 关键：保持页面存活，不销毁
  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();

    // 初始化自动滚动状态
    _autoScrollEnabled = true;
    _isUserNearBottom = true;

    // 🆕 初始化对话配置
    _conversationSettings = globalModelServiceManager
        .getConversationSettings(widget.conversation.id);

    // 🆕 初始化流式控制器
    _streamController = EnhancedStreamController();

    // 监听滚动位置变化，自动保存
    _itemPositionsListener.itemPositions.addListener(_onScrollPositionChanged);

    // 恢复之前保存的滚动位置
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _restoreScrollPosition();
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

      // 更新用户是否在底部的状态
      _updateUserNearBottomStatus(positions);

      _lastScrollIndex = firstVisibleIndex;

      // 只在位置真正改变时保存（防止频繁写入）
      if (widget.conversation.scrollIndex != firstVisibleIndex) {
        widget.conversation.scrollIndex = firstVisibleIndex;
        // 延迟保存，避免滚动时频繁触发
        Future.delayed(const Duration(milliseconds: 500), () {
          widget.onConversationUpdated();
        });
      }
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
  void _updateUserNearBottomStatus(Iterable<ItemPosition> positions) {
    if (positions.isEmpty) return;

    final totalMessages = widget.conversation.messages.length + (_currentAssistantMessage.isEmpty ? 0 : 1);
    final lastVisibleIndex = positions
        .where((position) => position.itemLeadingEdge < 1)
        .reduce((a, b) => a.index > b.index ? a : b)
        .index;

    // 如果最后可见的消息距离底部2条消息以内，认为用户在底部附近
    final isNearBottom = totalMessages - lastVisibleIndex <= 2;

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
  void _restoreScrollPosition() {
    if (widget.conversation.scrollIndex != null && 
        _itemScrollController.isAttached) {
      final targetIndex = widget.conversation.scrollIndex!;
      final maxIndex = widget.conversation.messages.length - 1;
      
      // 确保索引有效
      if (targetIndex >= 0 && targetIndex <= maxIndex) {
        _itemScrollController.jumpTo(index: targetIndex);
        debugPrint('✅ 恢复滚动位置到索引: $targetIndex');
      }
    }
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
    if (text.isEmpty) return;

    // 获取选择的Provider和Model
    final modelId = _conversationSettings.selectedModelId;
    if (modelId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('⚠️ 请先选择模型')),
      );
      return;
    }

    final modelWithProvider = globalModelServiceManager.getModelWithProvider(modelId);
    if (modelWithProvider == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('⚠️ 模型配置错误')),
      );
      return;
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
    );

    setState(() {
      widget.conversation.addMessage(userMessage);
      _messageController.clear();
      _isLoading = true;
      _currentAssistantMessage = '';
    });

    _scrollToBottom();
    widget.onConversationUpdated();

    try {
      // 创建Provider实例
      final provider = globalModelServiceManager.createProviderInstance(
        modelWithProvider.provider.id,
      );

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
      await _streamController.startStreaming(
        provider: provider,
        modelName: modelWithProvider.model.modelName,
        messages: chatMessages,
        parameters: _conversationSettings.parameters,
        files: files.isNotEmpty ? files : null,
        onChunk: (chunk) {
          setState(() {
            _currentAssistantMessage += chunk;
          });
          _throttledScrollToBottom();
        },
        onDone: () {
          // 保存助手消息
          if (_currentAssistantMessage.isNotEmpty) {
            final inputTokens = TokenCounter.estimateTokens(text);
            final outputTokens = TokenCounter.estimateTokens(_currentAssistantMessage);

            final assistantMessage = Message(
              id: DateTime.now().millisecondsSinceEpoch.toString(),
              content: _currentAssistantMessage,
              isUser: false,
              timestamp: DateTime.now(),
              inputTokens: inputTokens,
              outputTokens: outputTokens,
            );

            setState(() {
              widget.conversation.addMessage(assistantMessage);
              _currentAssistantMessage = '';
              _isLoading = false;
            });

            // 清空附件
            _conversationSettings = _conversationSettings.clearFiles();
            globalModelServiceManager.updateConversationSettings(_conversationSettings);

            widget.onConversationUpdated();
            widget.onTokenUsageUpdated(widget.conversation);
            _scrollToBottom();
          }
        },
        onError: (error) {
          setState(() {
            _isLoading = false;
          });

          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text('❌ 错误: ${error.toString()}')),
            );
          }
        },
      );
    } catch (e) {
      setState(() {
        _isLoading = false;
      });

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('❌ 发送失败: $e')),
        );
      }
    }
  }

  /// 停止流式输出
  Future<void> _stopStreaming() async {
    final content = await _streamController.stop();

    if (content.isNotEmpty) {
      // 保存部分内容
      final assistantMessage = Message(
        id: DateTime.now().millisecondsSinceEpoch.toString(),
        content: content,
        isUser: false,
        timestamp: DateTime.now(),
        outputTokens: TokenCounter.estimateTokens(content),
      );

      setState(() {
        widget.conversation.addMessage(assistantMessage);
        _currentAssistantMessage = '';
        _isLoading = false;
      });

      widget.onConversationUpdated();
      widget.onTokenUsageUpdated(widget.conversation);
    } else {
      setState(() {
        _isLoading = false;
      });
    }
  }

  /// 复制消息内容
  void _copyMessage(String content) {
    Clipboard.setData(ClipboardData(text: content));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('✅ 已复制到剪贴板')),
    );
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
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('⚠️ 请先选择要导出的消息')),
      );
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
              leading: const Icon(Icons.text_snippet),
              title: const Text('Markdown'),
              subtitle: Text('${selectedMessages.length} 条消息'),
              onTap: () => Navigator.pop(context, 'md'),
            ),
            ListTile(
              leading: const Icon(Icons.description),
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
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(' 已导出 ${selectedMessages.length} 条消息到:\n$filePath'),
            duration: const Duration(seconds: 3),
            action: SnackBarAction(
              label: '复制路径',
              onPressed: () {
                Clipboard.setData(ClipboardData(text: filePath));
              },
            ),
          ),
        );
        
        // 退出导出模式
        _exitExportMode();
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(' 导出失败: $e')),
        );
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

    // 删除该消息之后的所有消息
    final messageIndex = widget.conversation.messages.indexOf(message);
    if (messageIndex >= 0) {
      setState(() {
        widget.conversation.messages.removeRange(
          messageIndex + 1,
          widget.conversation.messages.length,
        );
      });
    }

    // 重新发送
    _messageController.text = newContent;
    await _sendMessage();
  }

  /// 从指定消息重新生成
  Future<void> _regenerateFromMessage(Message message) async {
    final messageIndex = widget.conversation.messages.indexOf(message);
    if (messageIndex < 0) return;

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

      // 重新发送
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
        final userContent = previousUserMessage.content;
        
        setState(() {
          final userIndex = widget.conversation.messages.indexOf(previousUserMessage!);
          widget.conversation.messages.removeRange(
            userIndex,
            widget.conversation.messages.length,
          );
        });
        widget.onConversationUpdated();

        // 重新发送用户消息
        _messageController.text = userContent;
        await _sendMessage();
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context); // 必须调用以启用 KeepAlive

    return Stack(
      children: [
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
      ],
    );
  }

  /// 导出模式工具栏
  Widget _buildExportModeToolbar() {
    final selectedCount = _selectedMessageIds.length;
    final totalCount = widget.conversation.messages.length;
    
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
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
            icon: const Icon(Icons.close),
            onPressed: _exitExportMode,
            tooltip: '退出导出模式',
          ),
          const SizedBox(width: 8),
          
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
            icon: Icon(selectedCount == totalCount ? Icons.deselect : Icons.select_all),
            label: Text(selectedCount == totalCount ? '取消全选' : '全选'),
          ),
          
          const SizedBox(width: 8),
          
          // 导出按钮
          FilledButton.icon(
            onPressed: selectedCount > 0 ? _exportSelectedMessages : null,
            icon: const Icon(Icons.file_download),
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
          const SizedBox(height: 16),
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
    return ScrollablePositionedList.builder(
      itemScrollController: _itemScrollController,
      itemPositionsListener: _itemPositionsListener,
      padding: const EdgeInsets.all(16),
      itemCount: widget.conversation.messages.length + (_currentAssistantMessage.isEmpty ? 0 : 1),
      itemBuilder: (context, index) {
        // 显示正在生成的消息
        if (index == widget.conversation.messages.length) {
          return _buildMessageBubble(
            content: _currentAssistantMessage,
            isUser: false,
            timestamp: DateTime.now(),
            message: null,
          );
        }

        final message = widget.conversation.messages[index];
        
        return _buildMessageBubble(
          content: message.content,
          isUser: message.isUser,
          timestamp: message.timestamp,
          message: message,
        );
      },
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
    final senderName = isUser ? '用户' : widget.settings.model;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 导出模式：复选框
            if (_isExportMode && message != null)
              Padding(
                padding: const EdgeInsets.only(top: 4, right: 8),
                child: Checkbox(
                  value: _selectedMessageIds.contains(message.id),
                  onChanged: (_) => _toggleMessageSelection(message.id),
                ),
              ),
            
            // 头像
            Padding(
              padding: const EdgeInsets.only(top: 4, right: 8),
              child: CircleAvatar(
                radius: 20,
                backgroundColor: isUser
                    ? Theme.of(context).colorScheme.primary
                    : Theme.of(context).colorScheme.secondary,
                child: Icon(
                  isUser ? Icons.person_rounded : Icons.smart_toy,
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
                  const SizedBox(height: 2),
                  // 时间
                  Text(
                    _formatFullTimestamp(timestamp),
                    style: TextStyle(
                      fontSize: 11,
                      color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.5),
                    ),
                  ),
                  const SizedBox(height: 8),

                  // 消息内容容器
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 300),
                    width: double.infinity,
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: isUser
                          ? Theme.of(context).colorScheme.primaryContainer
                          : Theme.of(context).colorScheme.surfaceContainerHighest,
                      borderRadius: BorderRadius.circular(12),
                      border: isHighlighted
                          ? Border.all(
                              color: Theme.of(context).colorScheme.primary,
                              width: 3,
                            )
                          : null,
                      boxShadow: isHighlighted
                          ? [
                              BoxShadow(
                                color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.3),
                                blurRadius: 12,
                                spreadRadius: 2,
                              ),
                            ]
                          : null,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // 编辑模式：文本框
                        if (isEditing)
                          TextField(
                            controller: _editController,
                            maxLines: null,
                            autofocus: true,
                            decoration: const InputDecoration(
                              border: OutlineInputBorder(),
                              contentPadding: EdgeInsets.all(8),
                            ),
                          )
                        // 正常模式：增强渲染（支持 Markdown + LaTeX + Mermaid）
                        else
                          EnhancedContentRenderer(
                            content: content,
                            textStyle: TextStyle(
                              fontSize: 15,
                              color: isUser
                                  ? Theme.of(context).colorScheme.onPrimaryContainer
                                  : Theme.of(context).colorScheme.onSurface,
                            ),
                            backgroundColor: isUser
                                ? Theme.of(context).colorScheme.primary.withValues(alpha: 0.1)
                                : Theme.of(context).colorScheme.surface,
                            isUser: isUser,
                          ),
                        
                        // Token 统计
                        if (message != null && !isEditing)
                          _buildTokenInfo(message, isUser),
                      ],
                    ),
                  ),

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

        const SizedBox(height: 12),
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
      padding: const EdgeInsets.only(top: 8),
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
          setState(() {
            _autoScrollEnabled = true;
            _isUserNearBottom = true;
          });
          _scrollToBottom(smooth: true);
        },
        backgroundColor: Theme.of(context).colorScheme.primary,
        foregroundColor: Theme.of(context).colorScheme.onPrimary,
        child: const Icon(Icons.keyboard_arrow_down),
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
      onSettingsChanged: (settings) {
        setState(() {
          _conversationSettings = settings;
        });
        globalModelServiceManager.updateConversationSettings(settings);
      },
    );
  }
}

