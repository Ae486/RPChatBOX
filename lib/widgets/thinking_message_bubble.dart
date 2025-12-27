import 'dart:async';
import 'package:flutter/material.dart';
import '../themes/chatbox_chat_theme.dart';
import '../chat_ui/owui/owui_icons.dart';
import 'enhanced_content_renderer.dart';

/// 思考消息气泡组件
///
/// 显示 AI 的思考过程，支持：
/// - 折叠/展开交互
/// - 实时计时显示
/// - 呼吸灯动画效果
/// - 思考内容滚动
class ThinkingMessageBubble extends StatefulWidget {
  /// 思考内容
  final String thinking;

  /// 正文内容
  final String body;

  /// 模型名称
  final String? modelName;

  /// 提供商名称
  final String? providerName;

  /// 输出 Token 数
  final int? outputTokens;

  /// 输入 Token 数
  final int? inputTokens;

  /// 是否正在思考（流式输出中）
  final bool isThinking;

  /// 思考时长（秒），用于已保存的消息
  final int? thinkingDurationSeconds;

  /// 消息时间戳
  final DateTime? timestamp;

  const ThinkingMessageBubble({
    super.key,
    required this.thinking,
    required this.body,
    this.modelName,
    this.providerName,
    this.outputTokens,
    this.inputTokens,
    this.isThinking = false,
    this.thinkingDurationSeconds,
    this.timestamp,
  });

  @override
  State<ThinkingMessageBubble> createState() => _ThinkingMessageBubbleState();
}

class _ThinkingMessageBubbleState extends State<ThinkingMessageBubble>
    with SingleTickerProviderStateMixin {
  bool _isExpanded = false;
  late AnimationController _breatheController;
  Timer? _timer;
  int _elapsedSeconds = 0;
  final ScrollController _scrollController = ScrollController();

  /// 用户是否手动滚动过（用于禁止自动滚动）
  bool _userHasScrolled = false;

  @override
  void initState() {
    super.initState();

    // 呼吸灯动画
    _breatheController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
      lowerBound: 0.92,
      upperBound: 1.08,
    );

    // 初始化计时器：使用传入的已有时长
    _elapsedSeconds = widget.thinkingDurationSeconds ?? 0;

    if (widget.isThinking) {
      _breatheController.repeat(reverse: true);
      _startTimer();
    }

    // 监听用户滚动行为
    _scrollController.addListener(_onScrollChanged);
  }

  @override
  void didUpdateWidget(ThinkingMessageBubble oldWidget) {
    super.didUpdateWidget(oldWidget);

    if (widget.isThinking && !oldWidget.isThinking) {
      _breatheController.repeat(reverse: true);
      // 从传入的时长开始计时
      _elapsedSeconds = widget.thinkingDurationSeconds ?? 0;
      _userHasScrolled = false;
      _startTimer();
    } else if (!widget.isThinking && oldWidget.isThinking) {
      _breatheController.stop();
      _breatheController.value = 1.0;
      _stopTimer();
    }
  }

  void _onScrollChanged() {
    // 如果用户向上滚动，禁止自动滚动
    if (_scrollController.hasClients) {
      final maxScroll = _scrollController.position.maxScrollExtent;
      final currentScroll = _scrollController.position.pixels;
      // 如果不在底部（允许 10px 容差），标记用户已手动滚动
      if (maxScroll - currentScroll > 10) {
        _userHasScrolled = true;
      } else {
        // 如果用户滚动到底部，重置标记
        _userHasScrolled = false;
      }
    }
  }

  void _startTimer() {
    _timer?.cancel();
    // 不重置 _elapsedSeconds，保留传入的初始值
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) {
        setState(() {
          _elapsedSeconds++;
        });
        _autoScrollToBottom();
      }
    });
  }

  void _stopTimer() {
    _timer?.cancel();
    _timer = null;
  }

  void _autoScrollToBottom() {
    // 如果用户手动滚动过，不自动滚动
    if (_userHasScrolled) return;

    if (_scrollController.hasClients && _isExpanded) {
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 120),
        curve: Curves.easeOut,
      );
    }
  }

  @override
  void dispose() {
    _breatheController.dispose();
    _timer?.cancel();
    _scrollController.removeListener(_onScrollChanged);
    _scrollController.dispose();
    super.dispose();
  }

  String _formatDuration(int seconds) {
    final m = (seconds ~/ 60).toString().padLeft(2, '0');
    final s = (seconds % 60).toString().padLeft(2, '0');
    return '$m:$s';
  }

  String _formatTimestamp(DateTime timestamp) {
    return '${timestamp.year}-${timestamp.month.toString().padLeft(2, '0')}-${timestamp.day.toString().padLeft(2, '0')} '
        '${timestamp.hour.toString().padLeft(2, '0')}:${timestamp.minute.toString().padLeft(2, '0')}:${timestamp.second.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final authorName = _getAuthorName();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // 头部：作者信息和时间
        _buildHeader(authorName),
        const SizedBox(height: 8),

        // 思考气泡
        if (widget.thinking.isNotEmpty) ...[
          _buildThinkingBubble(),
          const SizedBox(height: 12),
        ],

        // 正文气泡
        if (widget.body.isNotEmpty) _buildBodyBubble(),

        // Token 信息
        if (widget.outputTokens != null || widget.inputTokens != null)
          _buildTokenInfo(),
      ],
    );
  }

  String _getAuthorName() {
    if (widget.modelName != null && widget.providerName != null) {
      return '${widget.modelName}|${widget.providerName}';
    } else if (widget.modelName != null) {
      return widget.modelName!;
    }
    return 'AI助手';
  }

  Widget _buildHeader(String authorName) {
    return Row(
      children: [
        CircleAvatar(
          radius: 20,
          backgroundColor: Theme.of(context).colorScheme.secondary,
          child: const Icon(
            OwuiIcons.chatbot,
            color: Colors.white,
            size: 24,
          ),
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                authorName,
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  fontSize: 14,
                  color: ChatBoxChatTheme.onSurfaceColor(context),
                ),
              ),
              if (widget.timestamp != null)
                Text(
                  _formatTimestamp(widget.timestamp!),
                  style: TextStyle(
                    fontSize: 11,
                    color: ChatBoxChatTheme.secondaryTextColor(context),
                  ),
                ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildThinkingBubble() {
    final showContent = widget.isThinking || _isExpanded;

    return Container(
      width: double.infinity,
      decoration: ChatBoxChatTheme.thinkingBubbleDecoration(context),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: widget.isThinking ? null : () => setState(() => _isExpanded = !_isExpanded),
          borderRadius: BorderRadius.circular(16),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // 思考头部
                Row(
                  children: [
                    ScaleTransition(
                      scale: _breatheController,
                      child: Icon(
                        OwuiIcons.lightbulb,
                        size: 16,
                        color: ChatBoxChatTheme.onSurfaceColor(context),
                      ),
                    ),
                    const SizedBox(width: 6),
                    Text(
                      widget.isThinking
                          ? '思考中 ${_formatDuration(_elapsedSeconds)}'
                          : '已思考 ${_elapsedSeconds}s',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: ChatBoxChatTheme.onSurfaceColor(context),
                      ),
                    ),
                    const Spacer(),
                    if (!widget.isThinking)
                      AnimatedRotation(
                        turns: _isExpanded ? 0.5 : 0,
                        duration: const Duration(milliseconds: 200),
                        child: Icon(
                          OwuiIcons.arrowDown,
                          size: 18,
                          color: ChatBoxChatTheme.secondaryTextColor(context),
                        ),
                      ),
                  ],
                ),

                // 思考内容
                AnimatedSize(
                  duration: const Duration(milliseconds: 200),
                  curve: Curves.easeInOut,
                  child: showContent
                      ? Container(
                          margin: const EdgeInsets.only(top: 8),
                          constraints: const BoxConstraints(
                            maxHeight: 160,
                            minHeight: 44,
                          ),
                          child: SingleChildScrollView(
                            controller: _scrollController,
                            child: Text(
                              widget.thinking.isEmpty ? '...' : widget.thinking,
                              style: TextStyle(
                                fontSize: 14,
                                color: ChatBoxChatTheme.onSurfaceColor(context),
                                height: 1.5,
                              ),
                            ),
                          ),
                        )
                      : const SizedBox.shrink(),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildBodyBubble() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: ChatBoxChatTheme.assistantBubbleDecoration(context),
      child: EnhancedContentRenderer(
        content: widget.body,
        textStyle: TextStyle(
          fontSize: 15,
          color: ChatBoxChatTheme.onSurfaceColor(context),
        ),
        backgroundColor: Theme.of(context).colorScheme.surface,
        isUser: false,
      ),
    );
  }

  Widget _buildTokenInfo() {
    final inputTokens = widget.inputTokens ?? 0;
    final outputTokens = widget.outputTokens ?? 0;
    final totalTokens = inputTokens + outputTokens;

    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Text(
        'Tokens:$totalTokens ↑$inputTokens ↓$outputTokens',
        style: TextStyle(
          fontSize: 10,
          color: ChatBoxChatTheme.secondaryTextColor(context),
          fontStyle: FontStyle.italic,
        ),
      ),
    );
  }
}
