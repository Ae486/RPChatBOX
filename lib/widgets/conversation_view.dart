import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:file_picker/file_picker.dart' as picker;
import 'package:url_launcher/url_launcher.dart';
import 'package:scrollable_positioned_list/scrollable_positioned_list.dart';
import 'package:photo_view/photo_view.dart';
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
import '../utils/global_toast.dart';
import 'enhanced_input_area.dart';
import '../main.dart' show globalModelServiceManager;
import '../controllers/stream_output_controller.dart';
import '../adapters/ai_provider.dart';

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
  bool _attachmentBarVisible = true; // 附件栏可见性控制
  AIProvider? _currentProvider; // 🔥 当前流式输出的 Provider，用于取消请求
  
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
    final hasFiles = _conversationSettings.hasAttachedFiles;

    // 允许：有文本 或 有附件
    if (text.isEmpty && !hasFiles) return;

    // 获取选择的Provider和Model
    final modelId = _conversationSettings.selectedModelId;
    if (modelId == null) {
      // 🆕 使用全局提示框
      GlobalToast.showInfo(
        context,
        '⚠️ 请先选择一个模型',
      );
      return;
    }

    final modelWithProvider = globalModelServiceManager.getModelWithProvider(modelId);
    if (modelWithProvider == null) {
      // 🆕 使用全局提示框
      GlobalToast.showError(
        context,
        '❌ 无法找到指定的模型',
      );
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
    });

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
              modelName: modelWithProvider.model.displayName,
              providerName: modelWithProvider.provider.name,
            );

            setState(() {
              widget.conversation.addMessage(assistantMessage);
              _currentAssistantMessage = '';
              _isLoading = false;
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

          if (mounted) {
            // 🆕 使用全局提示框
            GlobalToast.showError(
              context,
              '❌ 消息发送失败\n${error.toString()}',
            );
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
        GlobalToast.showError(
          context,
          '❌ 消息发送失败\n${e.toString()}',
        );
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
      });
    }
  }

  /// 复制消息内容
  void _copyMessage(String content) {
    Clipboard.setData(ClipboardData(text: content));
    // 🆕 使用全局提示框
    GlobalToast.showSuccess(
      context,
      '✅ 已复制到剪贴板',
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
                const SizedBox(height: 8),
                ...missingFiles.map((name) => Padding(
                  padding: const EdgeInsets.only(left: 16, top: 4),
                  child: Text('• $name', style: const TextStyle(fontSize: 13)),
                )),
                const SizedBox(height: 16),
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

    // AI名称：使用消息保存的模型信息
    String senderName;
    if (isUser) {
      senderName = '用户';
    } else if (message != null && message.modelName != null && message.providerName != null) {
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
                        // 用户消息：显示附件
                        if (isUser && message != null && message.attachedFiles != null && message.attachedFiles!.isNotEmpty)
                          _buildAttachmentsPreview(message.attachedFiles!),

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
                  padding: const EdgeInsets.only(bottom: 8),
                  child: fileExists
                      ? GestureDetector(
                          onTap: () => _showImageViewer(file.path, file.name),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(8),
                            child: CachedImageWidget(
                              path: file.path,
                              fit: BoxFit.cover,
                              errorBuilder: (context, error, stackTrace) {
                                return _buildFilePlaceholder(
                                  file.name,
                                  '图片加载失败',
                                  Icons.broken_image,
                                );
                              },
                            ),
                          ),
                        )
                      : _buildFilePlaceholder(
                          file.name,
                          '图片已不存在',
                          Icons.image_not_supported,
                        ),
                );
              } else {
                // 文档/代码文件：显示可点击的卡片
                return Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: fileExists
                      ? InkWell(
                          onTap: () => _openFile(file.path),
                          child: Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: Theme.of(context).colorScheme.surface,
                              borderRadius: BorderRadius.circular(8),
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
                                const SizedBox(width: 12),
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
                                      const SizedBox(height: 2),
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
                                const SizedBox(width: 8),
                                Icon(
                                  Icons.open_in_new,
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
                          Icons.insert_drive_file_outlined,
                        ),
                );
              }
            },
          );
        }),
        const SizedBox(height: 8),
        const Divider(height: 1),
        const SizedBox(height: 8),
      ],
    );
  }

  /// 构建文件占位符（文件不存在时显示）
  Widget _buildFilePlaceholder(String fileName, String message, IconData icon) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.grey.shade200,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.grey.shade400),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: Colors.grey),
          const SizedBox(width: 8),
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
                const SizedBox(height: 2),
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
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('无法打开文件: $path'),
              behavior: SnackBarBehavior.floating,
              margin: const EdgeInsets.only(top: 80, left: 20, right: 20),
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('打开文件失败: ${e.toString()}'),
            behavior: SnackBarBehavior.floating,
            margin: const EdgeInsets.only(top: 80, left: 20, right: 20),
          ),
        );
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
                icon: const Icon(Icons.close),
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
              child: CircularProgressIndicator(
                value: event == null
                    ? 0
                    : event.cumulativeBytesLoaded / (event.expectedTotalBytes ?? 1),
              ),
            ),
            errorBuilder: (context, error, stackTrace) => Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.broken_image, size: 64, color: Colors.white54),
                  const SizedBox(height: 16),
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
        return Icons.image;
      case FileType.video:
        return Icons.videocam;
      case FileType.audio:
        return Icons.audiotrack;
      case FileType.document:
        return Icons.description;
      case FileType.code:
        return Icons.code;
      case FileType.other:
        return Icons.insert_drive_file;
    }
  }
}

