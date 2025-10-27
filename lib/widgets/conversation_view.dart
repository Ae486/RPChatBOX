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
  
  // 🔥 关键：保持页面存活，不销毁
  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    
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

  /// 滚动到底部
  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_itemScrollController.isAttached) {
        final lastIndex = widget.conversation.messages.length - 1;
        if (lastIndex >= 0) {
          _itemScrollController.jumpTo(index: lastIndex);
        }
      }
    });
  }

  /// 发送消息
  Future<void> _sendMessage() async {
    final text = _messageController.text.trim();
    if (text.isEmpty) return;

    // 检查设置
    if (widget.settings.apiKey.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('⚠️ 请先在设置中配置 API Key')),
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
      // 构建消息列表（包含系统提示词）
      final messages = <Message>[];
      
      // 如果有系统提示词，添加到开头
      if (widget.conversation.systemPrompt != null) {
        messages.add(Message(
          id: 'system',
          content: widget.conversation.systemPrompt!,
          isUser: false,
          timestamp: DateTime.now(),
        ));
      }
      
      // 添加会话历史
      messages.addAll(widget.conversation.messages);

      // 调用 API
      final service = OpenAIService(widget.settings);
      final stream = service.sendMessage(messages);

      // 接收流式响应
      await for (var chunk in stream) {
        setState(() {
          _currentAssistantMessage += chunk;
        });
        _scrollToBottom();
      }

      // 保存 AI 回复
      if (_currentAssistantMessage.isNotEmpty) {
        // 计算 Token 使用量
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
        });

        widget.onConversationUpdated();
        widget.onTokenUsageUpdated(widget.conversation);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('❌ 发送失败: $e')),
        );
      }
    } finally {
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

    return Column(
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

  /// 输入区域
  Widget _buildInputArea() {
    return Container(
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.05),
            blurRadius: 10,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      padding: const EdgeInsets.all(12),
      child: SafeArea(
        child: Row(
          children: [
            Expanded(
              child: ConstrainedBox(
                constraints: const BoxConstraints(
                  maxHeight: 150, // 限制输入框最大高度
                ),
                child: TextField(
                  controller: _messageController,
                  decoration: InputDecoration(
                    hintText: '输入消息...',
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(24),
                    ),
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 16,
                      vertical: 12,
                    ),
                  ),
                  minLines: 1,
                  maxLines: 6, // 最多显示6行
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _sendMessage(),
                  enabled: !_isLoading,
                ),
              ),
            ),
            const SizedBox(width: 8),
            FloatingActionButton(
              heroTag: 'send_${widget.conversation.id}', // 唯一的 Hero tag
              onPressed: _isLoading ? null : _sendMessage,
              child: _isLoading
                  ? const SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Icon(Icons.send),
            ),
          ],
        ),
      ),
    );
  }
}

