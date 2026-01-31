/// INPUT: Assistant 消息元信息 + Markdown 内容 + StreamManager 流式状态 + 会话设置
/// OUTPUT: OwuiAssistantMessage - 助手消息渲染（Markdown/Thinking/Meta/图片）
/// POS: UI 层 / Chat / Owui - V2 助手消息组件（由 ConversationViewV2 组装）

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_chat_ui/flutter_chat_ui.dart' show IsTypingIndicator;
import 'package:provider/provider.dart';

import '../../models/conversation_settings.dart';
import '../../widgets/conversation_view_v2.dart';
import '../../widgets/stream_manager.dart';
import 'chat_theme.dart';
import 'markdown.dart';
import 'owui_icons.dart';
import 'owui_tokens_ext.dart';
import 'palette.dart';

/// 生成的图片数据
class GeneratedImage {
  /// 图片来源：URL 或 base64 data URL
  final String source;
  /// DALL-E 等模型返回的修改后提示词
  final String? revisedPrompt;

  const GeneratedImage({required this.source, this.revisedPrompt});

  /// 是否为 base64 数据
  bool get isBase64 => source.startsWith('data:image');

  /// 是否为网络 URL
  bool get isNetworkUrl => source.startsWith('http://') || source.startsWith('https://');

  /// 是否为本地文件路径
  bool get isLocalFile => !isBase64 && !isNetworkUrl;

  /// 获取本地文件路径（处理 file:// URI）
  String get localFilePath {
    if (!isLocalFile) return source;
    final uri = Uri.tryParse(source);
    if (uri != null && uri.scheme == 'file') {
      return uri.toFilePath();
    }
    return source;
  }

  factory GeneratedImage.fromJson(Map<String, dynamic> json) {
    return GeneratedImage(
      source: json['source'] as String? ?? json['url'] as String? ?? json['b64_json'] as String? ?? '',
      revisedPrompt: json['revised_prompt'] as String? ?? json['revisedPrompt'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
    'source': source,
    if (revisedPrompt != null) 'revisedPrompt': revisedPrompt,
  };
}

class OwuiAssistantMessage extends StatelessWidget {
  final String messageId;
  final DateTime createdAt;
  final String bodyMarkdown;
  final bool isStreaming;
  final String? modelName;
  final String? providerName;
  final StreamData? streamData;
  /// 生成的图片列表
  final List<GeneratedImage> images;

  const OwuiAssistantMessage({
    super.key,
    required this.messageId,
    required this.createdAt,
    required this.bodyMarkdown,
    required this.isStreaming,
    required this.modelName,
    required this.providerName,
    required this.streamData,
    this.images = const [],
  });

  @override
  Widget build(BuildContext context) {
    final uiScale = context.owui.uiScale;
    final isDark = OwuiPalette.isDark(context);
    final thinking = streamData?.thinkingContent ?? '';
    final thinkingOpen = streamData?.isThinkingOpen ?? false;

    // P0-3/P0-4: 获取 ConversationSettings 以判断是否启用平滑流式
    final settings = context.watch<ConversationSettings?>();
    final enableSmoothCode = settings != null &&
        MarkstreamV2StreamingFlags.codeBlockPreviewDuringStreaming(settings);
    final enableSmoothMermaid = settings != null &&
        MarkstreamV2StreamingFlags.mermaidStablePlaceholderDuringStreaming(settings);
    final enableFadeIn = settings != null &&
        isStreaming &&
        settings.enableExperimentalStreamingMarkdown;
    final fadeInDurationMs = settings != null
        ? MarkstreamV2StreamingFlags.fadeInDurationMs(settings)
        : 150;
    final fadeInStartOpacity = settings != null
        ? MarkstreamV2StreamingFlags.fadeInStartOpacity(settings)
        : 0.3;

    final name = modelName?.trim();
    final headerText = (name == null || name.isEmpty) ? 'Assistant' : name;
    final sub = (providerName ?? '').trim();

    final children = <Widget>[
      Row(
        children: [
          Expanded(
            child: Text(
              sub.isEmpty ? headerText : '$headerText · $sub',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 13 * uiScale,
                fontWeight: FontWeight.w600,
                color: OwuiPalette.textPrimary(context),
              ),
            ),
          ),
          Text(
            '${createdAt.toLocal().hour.toString().padLeft(2, '0')}:${createdAt.toLocal().minute.toString().padLeft(2, '0')}',
            style: TextStyle(
              fontSize: 12 * uiScale,
              color: OwuiPalette.textSecondary(context),
            ),
          ),
        ],
      ),
      SizedBox(height: 8 * uiScale),
    ];

    // 判断思考是否完成：必须有结束时间才算完成
    final hasThinking = thinking.trim().isNotEmpty || thinkingOpen;
    final thinkingCompleted = streamData?.thinkingEndTime != null && thinking.trim().isNotEmpty;

    if (hasThinking) {
      children.add(
        Padding(
          padding: EdgeInsets.only(bottom: 10 * uiScale),
          child: OwuiThinkBubble(
            thinkingContent: thinking,
            isThinkingOpen: thinkingOpen,
            isCompleted: thinkingCompleted,
            thinkingStartTime: streamData?.thinkingStartTime,
            thinkingEndTime: streamData?.thinkingEndTime,
            uiScale: uiScale,
          ),
        ),
      );
    }

    // 加载指示器：流式输出中但还没有任何内容
    if (isStreaming && bodyMarkdown.trim().isEmpty && thinking.trim().isEmpty && !thinkingOpen) {
      children.add(
        Padding(
          padding: EdgeInsets.only(bottom: 8 * uiScale),
          child: IsTypingIndicator(
            size: 5 * uiScale,
            color: OwuiPalette.textSecondary(context),
            spacing: 3 * uiScale,
          ),
        ),
      );
    }

    if (bodyMarkdown.trim().isNotEmpty) {
      children.add(
        OwuiMarkdown(
          text: bodyMarkdown,
          isDark: isDark,
          isStreaming: isStreaming,
          stableCacheKey: Object.hash(isDark, messageId, 'body'),
          enableSmoothCodeBlock: enableSmoothCode,
          enableSmoothMermaid: enableSmoothMermaid,
          enableFadeIn: enableFadeIn,
          fadeInDuration: Duration(milliseconds: fadeInDurationMs),
          fadeInStartOpacity: fadeInStartOpacity,
        ),
      );
    }

    // 图片网格显示
    if (images.isNotEmpty) {
      children.add(
        Padding(
          padding: EdgeInsets.only(top: bodyMarkdown.trim().isNotEmpty ? 12 * uiScale : 0),
          child: _ImageGrid(images: images, uiScale: uiScale),
        ),
      );
    }

    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(12 * uiScale, 10 * uiScale, 12 * uiScale, 10 * uiScale),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: children,
      ),
    );
  }
}

/// 图片网格组件
class _ImageGrid extends StatelessWidget {
  final List<GeneratedImage> images;
  final double uiScale;

  const _ImageGrid({required this.images, required this.uiScale});

  @override
  Widget build(BuildContext context) {
    if (images.isEmpty) return const SizedBox.shrink();

    // 单张图片：较大显示
    if (images.length == 1) {
      return _ImageItem(image: images.first, uiScale: uiScale, maxSize: 320);
    }

    // 多张图片：网格显示
    return Wrap(
      spacing: 8 * uiScale,
      runSpacing: 8 * uiScale,
      children: images.map((img) => _ImageItem(image: img, uiScale: uiScale, maxSize: 200)).toList(),
    );
  }
}

/// 单个图片项
class _ImageItem extends StatelessWidget {
  final GeneratedImage image;
  final double uiScale;
  final double maxSize;

  const _ImageItem({
    required this.image,
    required this.uiScale,
    this.maxSize = 200,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = OwuiPalette.isDark(context);
    final size = maxSize * uiScale;

    return GestureDetector(
      onTap: () => _showImagePreview(context),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(8 * uiScale),
        child: Container(
          constraints: BoxConstraints(maxWidth: size, maxHeight: size),
          color: isDark
              ? Colors.white.withValues(alpha: 0.05)
              : Colors.black.withValues(alpha: 0.03),
          child: _buildImage(context, size),
        ),
      ),
    );
  }

  Widget _buildImage(BuildContext context, double size) {
    final errorWidget = Container(
      width: size,
      height: size * 0.6,
      color: OwuiPalette.isDark(context)
          ? Colors.white.withValues(alpha: 0.1)
          : Colors.black.withValues(alpha: 0.05),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(OwuiIcons.brokenImage, size: 32, color: OwuiPalette.textSecondary(context)),
          const SizedBox(height: 4),
          Text('加载失败', style: TextStyle(fontSize: 12, color: OwuiPalette.textSecondary(context))),
        ],
      ),
    );

    final loadingWidget = Container(
      width: size,
      height: size * 0.6,
      color: OwuiPalette.isDark(context)
          ? Colors.white.withValues(alpha: 0.05)
          : Colors.black.withValues(alpha: 0.03),
      child: Center(
        child: SizedBox(
          width: 24,
          height: 24,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: OwuiPalette.textSecondary(context),
          ),
        ),
      ),
    );

    if (image.isBase64) {
      // Base64 图片
      try {
        final base64Str = image.source.split(',').last;
        final bytes = base64Decode(base64Str);
        return Image.memory(
          bytes,
          fit: BoxFit.cover,
          errorBuilder: (_, __, ___) => errorWidget,
        );
      } catch (_) {
        return errorWidget;
      }
    } else if (image.isNetworkUrl) {
      // 网络图片
      return CachedNetworkImage(
        imageUrl: image.source,
        fit: BoxFit.cover,
        placeholder: (_, __) => loadingWidget,
        errorWidget: (_, __, ___) => errorWidget,
      );
    } else if (image.isLocalFile) {
      // 本地文件
      final file = File(image.localFilePath);
      return FutureBuilder<bool>(
        future: file.exists(),
        builder: (context, snapshot) {
          if (snapshot.data != true) return errorWidget;
          return Image.file(file, fit: BoxFit.cover, errorBuilder: (_, __, ___) => errorWidget);
        },
      );
    }

    return errorWidget;
  }

  void _showImagePreview(BuildContext context) {
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        backgroundColor: Colors.transparent,
        insetPadding: const EdgeInsets.all(16),
        child: Stack(
          alignment: Alignment.center,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: InteractiveViewer(
                minScale: 0.5,
                maxScale: 4.0,
                child: _buildFullImage(ctx),
              ),
            ),
            // 关闭按钮
            Positioned(
              top: 0,
              right: 0,
              child: IconButton(
                onPressed: () => Navigator.of(ctx).pop(),
                icon: Container(
                  padding: const EdgeInsets.all(4),
                  decoration: BoxDecoration(
                    color: Colors.black54,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Icon(OwuiIcons.close, color: Colors.white, size: 20),
                ),
              ),
            ),
            // 修改后的提示词（如果有）
            if (image.revisedPrompt != null && image.revisedPrompt!.isNotEmpty)
              Positioned(
                bottom: 0,
                left: 0,
                right: 0,
                child: Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: Colors.black.withValues(alpha: 0.7),
                    borderRadius: const BorderRadius.vertical(bottom: Radius.circular(12)),
                  ),
                  child: Text(
                    image.revisedPrompt!,
                    style: const TextStyle(color: Colors.white, fontSize: 12),
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildFullImage(BuildContext context) {
    final errorWidget = Container(
      padding: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(OwuiIcons.brokenImage, size: 48, color: OwuiPalette.textSecondary(context)),
          const SizedBox(height: 8),
          Text('无法加载图片', style: TextStyle(color: OwuiPalette.textSecondary(context))),
        ],
      ),
    );

    if (image.isBase64) {
      try {
        final base64Str = image.source.split(',').last;
        final bytes = base64Decode(base64Str);
        return Image.memory(bytes, fit: BoxFit.contain, errorBuilder: (_, __, ___) => errorWidget);
      } catch (_) {
        return errorWidget;
      }
    } else if (image.isNetworkUrl) {
      return CachedNetworkImage(
        imageUrl: image.source,
        fit: BoxFit.contain,
        errorWidget: (_, __, ___) => errorWidget,
      );
    } else if (image.isLocalFile) {
      return Image.file(File(image.localFilePath), fit: BoxFit.contain, errorBuilder: (_, __, ___) => errorWidget);
    }

    return errorWidget;
  }
}

/// 思考气泡组件
///
/// 支持收起/展开。
/// - 思考中：两行布局（第一行：灯泡+文字+秒数，第二行：摘要），灯泡较大并居中
/// - 思考完成：单行布局（灯泡+完成文字），灯泡较小
class OwuiThinkBubble extends StatefulWidget {
  final String thinkingContent;
  final bool isThinkingOpen;
  final bool isCompleted;
  final DateTime? thinkingStartTime;
  final DateTime? thinkingEndTime;
  final double uiScale;

  const OwuiThinkBubble({
    super.key,
    required this.thinkingContent,
    required this.isThinkingOpen,
    required this.isCompleted,
    this.thinkingStartTime,
    this.thinkingEndTime,
    required this.uiScale,
  });

  /// 提取最新的 **粗体** 摘要
  static String? extractLatestBoldSummary(String content) {
    final matches = RegExp(r'\*\*([^*]+)\*\*').allMatches(content);
    if (matches.isEmpty) return null;
    final raw = matches.last.group(1)!.trim();
    return raw.length > 40 ? '${raw.substring(0, 40)}...' : raw;
  }

  @override
  State<OwuiThinkBubble> createState() => _OwuiThinkBubbleState();
}

class _OwuiThinkBubbleState extends State<OwuiThinkBubble>
    with SingleTickerProviderStateMixin {
  bool _expanded = false;

  // 使用 ValueNotifier 实现局部更新
  final ValueNotifier<int> _secondsNotifier = ValueNotifier(0);
  final ValueNotifier<String?> _summaryNotifier = ValueNotifier(null);
  Timer? _secondsTimer;

  late AnimationController _breatheController;
  late Animation<double> _breatheAnimation;

  final ScrollController _scrollController = ScrollController();
  bool _userScrolledAway = false;

  @override
  void initState() {
    super.initState();
    _breatheController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    );
    _breatheAnimation = Tween<double>(begin: 0.4, end: 1.0).animate(
      CurvedAnimation(parent: _breatheController, curve: Curves.easeInOut),
    );

    _scrollController.addListener(_onScroll);
    _syncState();
    _updateSummary();
  }

  @override
  void didUpdateWidget(covariant OwuiThinkBubble oldWidget) {
    super.didUpdateWidget(oldWidget);

    // 状态变化时同步 timer 和动画
    if (widget.isCompleted != oldWidget.isCompleted ||
        widget.isThinkingOpen != oldWidget.isThinkingOpen ||
        widget.thinkingStartTime != oldWidget.thinkingStartTime ||
        widget.thinkingEndTime != oldWidget.thinkingEndTime) {
      _syncState();
    }

    // 内容变化时更新摘要和自动滚动
    if (widget.thinkingContent != oldWidget.thinkingContent) {
      _updateSummary();
      _autoFollowScroll();
    }
  }

  void _syncState() {
    _updateSeconds();

    // 正在思考的判断：标签打开 OR (有开始时间但没有结束时间)
    final isThinking = widget.isThinkingOpen ||
        (widget.thinkingStartTime != null && widget.thinkingEndTime == null);
    if (isThinking) {
      if (!_breatheController.isAnimating) {
        _breatheController.repeat(reverse: true);
      }
      _startTimer();
    } else {
      _breatheController.stop();
      _breatheController.value = 1.0;
      _stopTimer();
      // 完成时最后更新一次秒数
      _updateSeconds();
    }
  }

  void _startTimer() {
    if (_secondsTimer != null) return;
    // 100ms 轮询检测秒数变化，只在变化时更新 notifier（不造成额外重建）
    _secondsTimer = Timer.periodic(const Duration(milliseconds: 100), (_) {
      if (!mounted) return;
      final start = widget.thinkingStartTime;
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
    final start = widget.thinkingStartTime;
    if (start == null) {
      _secondsNotifier.value = 0;
      return;
    }
    final end = widget.thinkingEndTime ?? DateTime.now();
    _secondsNotifier.value = end.difference(start).inSeconds;
  }

  void _updateSummary() {
    // 正在思考的判断：标签打开 OR (有开始时间但没有结束时间)
    final isThinking = widget.isThinkingOpen ||
        (widget.thinkingStartTime != null && widget.thinkingEndTime == null);
    if (isThinking) {
      _summaryNotifier.value =
          OwuiThinkBubble.extractLatestBoldSummary(widget.thinkingContent);
    } else {
      _summaryNotifier.value = null;
    }
  }

  void _onScroll() {
    if (!_scrollController.hasClients) return;
    final pos = _scrollController.position;
    final atBottom = pos.pixels >= pos.maxScrollExtent - 20;
    if (atBottom) {
      _userScrolledAway = false;
    } else if (pos.userScrollDirection != ScrollDirection.idle) {
      _userScrolledAway = true;
    }
  }

  void _autoFollowScroll() {
    if (!_expanded || _userScrolledAway) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scrollController.hasClients) return;
      _scrollController.jumpTo(_scrollController.position.maxScrollExtent);
    });
  }

  @override
  void dispose() {
    _secondsTimer?.cancel();
    _secondsNotifier.dispose();
    _summaryNotifier.dispose();
    _breatheController.dispose();
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isDark = OwuiPalette.isDark(context);
    final us = widget.uiScale;
    // 正在思考的判断：标签打开 OR (有开始时间但没有结束时间)
    final isThinking = widget.isThinkingOpen ||
        (widget.thinkingStartTime != null && widget.thinkingEndTime == null);

    final activeIconColor = isDark ? Colors.amber[400]! : Colors.amber[600]!;
    final inactiveIconColor = OwuiPalette.textSecondary(context);
    final textColor = OwuiPalette.textSecondary(context);
    final borderColor = isDark
        ? Colors.white.withValues(alpha: 0.1)
        : Colors.black.withValues(alpha: 0.06);

    return GestureDetector(
      onTap: () => setState(() => _expanded = !_expanded),
      child: Container(
        width: double.infinity,
        decoration: OwuiChatTheme.thinkingDecoration(context),
        clipBehavior: Clip.hardEdge,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Header area
            Padding(
              padding: EdgeInsets.symmetric(
                horizontal: 12 * us,
                vertical: 10 * us,
              ),
              child: isThinking
                  ? _buildThinkingHeader(
                      us: us,
                      activeIconColor: activeIconColor,
                      textColor: textColor,
                      borderColor: borderColor,
                    )
                  : _buildCompletedHeader(
                      us: us,
                      inactiveIconColor: inactiveIconColor,
                      textColor: textColor,
                    ),
            ),

            // Expanded content area
            AnimatedSize(
              duration: const Duration(milliseconds: 250),
              curve: Curves.fastOutSlowIn,
              alignment: Alignment.topCenter,
              clipBehavior: Clip.hardEdge,
              child: _expanded
                  ? Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Divider(height: 1, color: borderColor),
                        ConstrainedBox(
                          constraints: BoxConstraints(maxHeight: 160 * us),
                          child: ScrollConfiguration(
                            behavior: ScrollConfiguration.of(context)
                                .copyWith(scrollbars: false),
                            child: SingleChildScrollView(
                              controller: _scrollController,
                              physics: const ClampingScrollPhysics(),
                              padding: EdgeInsets.all(12 * us),
                              child: OwuiMarkdown(
                                text: widget.thinkingContent,
                                isDark: isDark,
                                isStreaming: isThinking,
                                stableCacheKey: null,
                              ),
                            ),
                          ),
                        ),
                      ],
                    )
                  : const SizedBox.shrink(),
            ),
          ],
        ),
      ),
    );
  }

  /// 思考中：两行布局
  /// 第一行：灯泡（大，居中两行）| 正在思考 xx秒 | 箭头
  /// 第二行：摘要
  Widget _buildThinkingHeader({
    required double us,
    required Color activeIconColor,
    required Color textColor,
    required Color borderColor,
  }) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        // 灯泡 - 较大，呼吸动画
        AnimatedBuilder(
          animation: _breatheAnimation,
          builder: (context, child) => Opacity(
            opacity: _breatheAnimation.value,
            child: child,
          ),
          child: Icon(
            OwuiIcons.lightbulb,
            size: 20 * us,
            color: activeIconColor,
          ),
        ),

        SizedBox(width: 10 * us),

        // 右侧内容：两行
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              // 第一行：正在思考 + 秒数
              Row(
                children: [
                  Text(
                    '正在思考 ',
                    style: TextStyle(
                      fontSize: 12 * us,
                      color: textColor,
                    ),
                  ),
                  // 秒数：局部更新
                  ValueListenableBuilder<int>(
                    valueListenable: _secondsNotifier,
                    builder: (context, seconds, _) => Text(
                      '$seconds秒',
                      style: TextStyle(
                        fontSize: 12 * us,
                        fontWeight: FontWeight.w600,
                        color: textColor,
                        fontFeatures: const [FontFeature.tabularFigures()],
                      ),
                    ),
                  ),
                ],
              ),

              SizedBox(height: 4 * us),

              // 第二行：摘要（局部更新）
              ValueListenableBuilder<String?>(
                valueListenable: _summaryNotifier,
                builder: (context, summary, _) => AnimatedSwitcher(
                  duration: const Duration(milliseconds: 200),
                  child: Text(
                    summary ?? '...',
                    key: ValueKey(summary),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 12 * us,
                      fontStyle: FontStyle.italic,
                      color: textColor.withValues(alpha: 0.8),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),

        SizedBox(width: 4 * us),

        // 箭头
        AnimatedRotation(
          turns: _expanded ? 0.5 : 0.0,
          duration: const Duration(milliseconds: 250),
          curve: Curves.fastOutSlowIn,
          child: Icon(OwuiIcons.chevronDown, size: 14 * us, color: textColor),
        ),
      ],
    );
  }

  /// 思考完成：单行布局
  /// 灯泡（小）| 已完成思考（用时xx秒）| 箭头
  Widget _buildCompletedHeader({
    required double us,
    required Color inactiveIconColor,
    required Color textColor,
  }) {
    return Row(
      children: [
        // 灯泡 - 较小，静止
        Icon(
          OwuiIcons.lightbulb,
          size: 14 * us,
          color: inactiveIconColor,
        ),

        SizedBox(width: 6 * us),

        // 完成文字 + 秒数
        Expanded(
          child: ValueListenableBuilder<int>(
            valueListenable: _secondsNotifier,
            builder: (context, seconds, _) => Text(
              '已完成思考（用时$seconds秒）',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 12 * us,
                color: textColor,
                fontFeatures: const [FontFeature.tabularFigures()],
              ),
            ),
          ),
        ),

        SizedBox(width: 4 * us),

        // 箭头
        AnimatedRotation(
          turns: _expanded ? 0.5 : 0.0,
          duration: const Duration(milliseconds: 250),
          curve: Curves.fastOutSlowIn,
          child: Icon(OwuiIcons.chevronDown, size: 14 * us, color: textColor),
        ),
      ],
    );
  }
}
