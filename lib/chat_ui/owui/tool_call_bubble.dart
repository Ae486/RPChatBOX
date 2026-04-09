/// INPUT: ToolCallData（工具调用状态）+ uiScale
/// OUTPUT: OwuiToolCallBubble - 工具调用气泡组件
/// POS: UI 层 / Chat / Owui - MCP 工具调用状态展示

import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';

import '../../models/mcp/mcp_tool_call.dart';
import 'owui_icons.dart';
import 'palette.dart';

/// 工具调用气泡组件
///
/// 状态设计：
/// - pending: 灰色，等待执行
/// - running: 琥珀色，脉冲动画，双行（工具名+秒数 / 参数摘要）
/// - success: 绿色，单行（工具名+耗时），可展开
/// - error: 红色，单行（工具名+错误），可展开
class OwuiToolCallBubble extends StatefulWidget {
  final ToolCallData toolCall;
  final double uiScale;

  const OwuiToolCallBubble({
    super.key,
    required this.toolCall,
    required this.uiScale,
  });

  @override
  State<OwuiToolCallBubble> createState() => _OwuiToolCallBubbleState();
}

class _OwuiToolCallBubbleState extends State<OwuiToolCallBubble>
    with SingleTickerProviderStateMixin {
  bool _expanded = false;

  final ValueNotifier<int> _secondsNotifier = ValueNotifier(0);
  Timer? _secondsTimer;

  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );
    _pulseAnimation = Tween<double>(begin: 0.6, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

    _scrollController.addListener(_onScroll);
    _syncState();
  }

  @override
  void didUpdateWidget(covariant OwuiToolCallBubble oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.toolCall.status != oldWidget.toolCall.status ||
        widget.toolCall.startTime != oldWidget.toolCall.startTime ||
        widget.toolCall.endTime != oldWidget.toolCall.endTime) {
      _syncState();
    }
  }

  void _syncState() {
    _updateSeconds();

    if (_isRunning) {
      if (!_pulseController.isAnimating) {
        _pulseController.repeat(reverse: true);
      }
      _startTimer();
    } else {
      _pulseController.stop();
      _pulseController.value = 1.0;
      _stopTimer();
      _updateSeconds();
    }
  }

  bool get _isRunning => widget.toolCall.status == ToolCallStatus.running;
  bool get _isPending => widget.toolCall.status == ToolCallStatus.pending;
  bool get _isSuccess => widget.toolCall.status == ToolCallStatus.success;
  bool get _isError => widget.toolCall.status == ToolCallStatus.error;
  bool get _isCompleted => _isSuccess || _isError;

  void _startTimer() {
    if (_secondsTimer != null) return;
    _secondsTimer = Timer.periodic(const Duration(milliseconds: 100), (_) {
      if (!mounted) return;
      final start = widget.toolCall.startTime;
      if (start == null) return;
      final newSeconds = DateTime.now().difference(start).inSeconds;
      if (_secondsNotifier.value != newSeconds) {
        _secondsNotifier.value = newSeconds;
      }
    });
  }

  void _stopTimer() {
    _secondsTimer?.cancel();
    _secondsTimer = null;
  }

  void _updateSeconds() {
    final start = widget.toolCall.startTime;
    if (start == null) {
      _secondsNotifier.value = 0;
      return;
    }
    final end = widget.toolCall.endTime ?? DateTime.now();
    _secondsNotifier.value = end.difference(start).inSeconds;
  }

  void _onScroll() {
    // Reserved for future auto-scroll feature
  }

  @override
  void dispose() {
    _secondsTimer?.cancel();
    _secondsNotifier.dispose();
    _pulseController.dispose();
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = OwuiPalette.isDark(context);
    final us = widget.uiScale;

    final borderColor = isDark
        ? Colors.white.withValues(alpha: 0.1)
        : Colors.black.withValues(alpha: 0.06);

    return GestureDetector(
      onTap: () => setState(() => _expanded = !_expanded),
      child: Container(
        width: double.infinity,
        decoration: _buildDecoration(context),
        clipBehavior: Clip.hardEdge,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: EdgeInsets.symmetric(
                horizontal: 12 * us,
                vertical: 10 * us,
              ),
              child: _isRunning || _isPending
                  ? _buildRunningHeader(us: us, isDark: isDark)
                  : _buildCompletedHeader(us: us, isDark: isDark),
            ),
            AnimatedSize(
              duration: const Duration(milliseconds: 250),
              curve: Curves.fastOutSlowIn,
              alignment: Alignment.topCenter,
              clipBehavior: Clip.hardEdge,
              child: _expanded && _isCompleted
                  ? Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Divider(height: 1, color: borderColor),
                        _buildExpandedContent(us: us, isDark: isDark),
                      ],
                    )
                  : const SizedBox.shrink(),
            ),
          ],
        ),
      ),
    );
  }

  BoxDecoration _buildDecoration(BuildContext context) {
    final isDark = OwuiPalette.isDark(context);

    Color bgColor;
    Color borderColor;

    switch (widget.toolCall.status) {
      case ToolCallStatus.pending:
        bgColor = isDark ? const Color(0xFF1A1A1A) : const Color(0xFFF5F5F5);
        borderColor = isDark
            ? Colors.white.withValues(alpha: 0.08)
            : Colors.black.withValues(alpha: 0.05);
      case ToolCallStatus.running:
        bgColor = isDark ? const Color(0xFF1C1A17) : const Color(0xFFFFFBEB);
        borderColor = isDark
            ? Colors.amber.withValues(alpha: 0.2)
            : Colors.amber.withValues(alpha: 0.3);
      case ToolCallStatus.success:
        bgColor = isDark ? const Color(0xFF171917) : const Color(0xFFF0FDF4);
        borderColor = isDark
            ? Colors.green.withValues(alpha: 0.15)
            : Colors.green.withValues(alpha: 0.2);
      case ToolCallStatus.error:
        bgColor = isDark ? const Color(0xFF1A1717) : const Color(0xFFFEF2F2);
        borderColor = isDark
            ? Colors.red.withValues(alpha: 0.15)
            : Colors.red.withValues(alpha: 0.2);
    }

    return BoxDecoration(
      color: bgColor,
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: borderColor),
    );
  }

  Color _getIconColor(bool isDark) {
    switch (widget.toolCall.status) {
      case ToolCallStatus.pending:
        return isDark ? OwuiPalette.gray500 : OwuiPalette.gray400;
      case ToolCallStatus.running:
        return isDark ? Colors.amber[400]! : Colors.amber[600]!;
      case ToolCallStatus.success:
        return isDark ? Colors.green[400]! : Colors.green[600]!;
      case ToolCallStatus.error:
        return isDark ? Colors.red[400]! : Colors.red[600]!;
    }
  }

  /// 运行中/等待中：双行布局
  Widget _buildRunningHeader({
    required double us,
    required bool isDark,
  }) {
    final iconColor = _getIconColor(isDark);
    final textColor = OwuiPalette.textSecondary(context);
    final toolName = _extractToolName(widget.toolCall.toolName);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        // 扳手图标 - 脉冲动画
        _isRunning
            ? AnimatedBuilder(
                animation: _pulseAnimation,
                builder: (context, child) => Opacity(
                  opacity: _pulseAnimation.value,
                  child: child,
                ),
                child: Icon(OwuiIcons.wrench, size: 18 * us, color: iconColor),
              )
            : Icon(OwuiIcons.wrench, size: 18 * us, color: iconColor),

        SizedBox(width: 10 * us),

        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              // 第一行：工具名 + 状态 + 秒数
              Row(
                children: [
                  Flexible(
                    child: Text(
                      toolName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 12 * us,
                        fontWeight: FontWeight.w600,
                        color: textColor,
                      ),
                    ),
                  ),
                  Text(
                    _isPending ? ' · 等待中' : ' · 执行中 ',
                    style: TextStyle(fontSize: 12 * us, color: textColor),
                  ),
                  if (_isRunning)
                    ValueListenableBuilder<int>(
                      valueListenable: _secondsNotifier,
                      builder: (context, seconds, _) => Text(
                        '${seconds}s',
                        style: TextStyle(
                          fontSize: 12 * us,
                          color: textColor,
                          fontFeatures: const [FontFeature.tabularFigures()],
                        ),
                      ),
                    ),
                ],
              ),

              SizedBox(height: 3 * us),

              // 第二行：参数摘要
              Text(
                widget.toolCall.argumentsSummary,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 11 * us,
                  color: textColor.withValues(alpha: 0.7),
                  fontFamily: 'monospace',
                ),
              ),
            ],
          ),
        ),

        SizedBox(width: 4 * us),

        // 箭头（运行中不可展开，灰色）
        Icon(
          OwuiIcons.chevronDown,
          size: 14 * us,
          color: textColor.withValues(alpha: 0.3),
        ),
      ],
    );
  }

  /// 完成：单行布局
  Widget _buildCompletedHeader({
    required double us,
    required bool isDark,
  }) {
    final iconColor = _getIconColor(isDark);
    final textColor = OwuiPalette.textSecondary(context);
    final toolName = _extractToolName(widget.toolCall.toolName);

    final statusText = _isSuccess
        ? '已完成（${widget.toolCall.durationDisplay}）'
        : '执行失败';

    return Row(
      children: [
        Icon(OwuiIcons.wrench, size: 14 * us, color: iconColor),

        SizedBox(width: 6 * us),

        Expanded(
          child: Text(
            '$toolName · $statusText',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 12 * us,
              color: textColor,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
        ),

        SizedBox(width: 4 * us),

        AnimatedRotation(
          turns: _expanded ? 0.5 : 0.0,
          duration: const Duration(milliseconds: 250),
          curve: Curves.fastOutSlowIn,
          child: Icon(OwuiIcons.chevronDown, size: 14 * us, color: textColor),
        ),
      ],
    );
  }

  /// 展开内容：输入参数 + 输出结果
  Widget _buildExpandedContent({
    required double us,
    required bool isDark,
  }) {
    final sections = <Widget>[];

    // 输入参数
    if (widget.toolCall.arguments != null &&
        widget.toolCall.arguments!.isNotEmpty) {
      sections.add(_buildSection(
        title: '输入',
        content: _formatJson(widget.toolCall.arguments!),
        us: us,
        isDark: isDark,
      ));
    }

    // 输出结果
    if (widget.toolCall.result != null &&
        widget.toolCall.result!.isNotEmpty) {
      sections.add(_buildSection(
        title: '输出',
        content: widget.toolCall.result!,
        us: us,
        isDark: isDark,
      ));
    }

    // 错误信息
    if (widget.toolCall.errorMessage != null &&
        widget.toolCall.errorMessage!.isNotEmpty) {
      sections.add(_buildSection(
        title: '错误',
        content: widget.toolCall.errorMessage!,
        us: us,
        isDark: isDark,
        isError: true,
      ));
    }

    if (sections.isEmpty) {
      sections.add(Padding(
        padding: EdgeInsets.all(12 * us),
        child: Text(
          '无详细信息',
          style: TextStyle(
            fontSize: 12 * us,
            color: OwuiPalette.textSecondary(context),
          ),
        ),
      ));
    }

    return ConstrainedBox(
      constraints: BoxConstraints(maxHeight: 200 * us),
      child: ScrollConfiguration(
        behavior: ScrollConfiguration.of(context).copyWith(scrollbars: false),
        child: SingleChildScrollView(
          controller: _scrollController,
          physics: const ClampingScrollPhysics(),
          padding: EdgeInsets.all(12 * us),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: sections,
          ),
        ),
      ),
    );
  }

  Widget _buildSection({
    required String title,
    required String content,
    required double us,
    required bool isDark,
    bool isError = false,
  }) {
    final titleColor = isError
        ? (isDark ? Colors.red[400]! : Colors.red[600]!)
        : OwuiPalette.textSecondary(context);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: TextStyle(
            fontSize: 11 * us,
            fontWeight: FontWeight.w600,
            color: titleColor,
          ),
        ),
        SizedBox(height: 4 * us),
        Container(
          width: double.infinity,
          padding: EdgeInsets.all(8 * us),
          decoration: BoxDecoration(
            color: isDark
                ? Colors.white.withValues(alpha: 0.03)
                : Colors.black.withValues(alpha: 0.02),
            borderRadius: BorderRadius.circular(6),
          ),
          child: SelectableText(
            content,
            style: TextStyle(
              fontSize: 11 * us,
              fontFamily: 'monospace',
              color: OwuiPalette.textPrimary(context).withValues(alpha: 0.9),
            ),
          ),
        ),
        SizedBox(height: 8 * us),
      ],
    );
  }

  /// 提取工具名称（去除 serverId__ 前缀）
  String _extractToolName(String fullName) {
    final idx = fullName.indexOf('__');
    if (idx != -1 && idx < fullName.length - 2) {
      return fullName.substring(idx + 2);
    }
    return fullName;
  }

  /// 格式化 JSON
  String _formatJson(Map<String, dynamic> json) {
    try {
      const encoder = JsonEncoder.withIndent('  ');
      return encoder.convert(json);
    } catch (_) {
      return json.toString();
    }
  }
}
