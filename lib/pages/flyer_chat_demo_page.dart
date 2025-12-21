import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollDirection;
import 'package:flutter/services.dart';
import 'package:flutter_chat_core/flutter_chat_core.dart';
import 'package:flutter_chat_ui/flutter_chat_ui.dart';
import 'package:flutter_highlight/themes/github.dart';
import 'package:flutter_highlight/themes/monokai-sublime.dart';
import 'package:flutter_highlight/themes/vs2015.dart';
import 'package:highlight/highlight.dart' show highlight, Node, Result;
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flyer_chat_text_message/flyer_chat_text_message.dart';
import 'package:flyer_chat_text_stream_message/flyer_chat_text_stream_message.dart';
import 'package:markdown/markdown.dart' as m;
import 'package:markdown_widget/markdown_widget.dart';
import 'package:path_provider/path_provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:uuid/uuid.dart';

import '../rendering/markdown_stream/markdown_stream.dart';
import '../widgets/mermaid_renderer.dart';

part 'flyer_chat_demo/latex.dart';
part 'flyer_chat_demo/markdown_nodes.dart';
part 'flyer_chat_demo/streaming_code_block_preview.dart';
part 'flyer_chat_demo/streaming_markdown_body.dart';
part 'flyer_chat_demo/streaming_state.dart';
part 'flyer_chat_demo/demo_data.dart';
part 'flyer_chat_demo/admonition_node.dart';
part 'flyer_chat_demo/highlight_syntax.dart';
part 'flyer_chat_demo/sub_sup_syntax.dart';
part 'flyer_chat_demo/insert_syntax.dart';
part 'flyer_chat_demo/performance_monitor.dart';
part 'flyer_chat_demo/mermaid_block.dart';
part 'flyer_chat_demo/enhanced_code_block.dart';

class FlyerChatDemoPage extends StatefulWidget {
  const FlyerChatDemoPage({super.key});

  @override
  State<FlyerChatDemoPage> createState() => _FlyerChatDemoPageState();
}

class _FlyerChatDemoPageState extends State<FlyerChatDemoPage> {
  static const String _currentUserId = 'user';
  static const String _assistantUserId = 'assistant';
  static const Duration _chunkAnimationDuration = Duration(milliseconds: 250);

  _RenderSpeedConfig _speedConfig = _RenderSpeedConfig.normal;

  Duration get _markdownStreamUpdateThrottle => _speedConfig.streamThrottle;
  Duration get _chunkDelay => _speedConfig.chunkDelay;

  String get _renderSpeedLabel => '${_speedConfig.streamThrottleMs}/${_speedConfig.chunkDelayMs}ms';

  void _showSpeedConfigDialog() {
    showDialog(
      context: context,
      builder: (context) => _SpeedConfigDialog(
        config: _speedConfig,
        onChanged: (config) {
          setState(() => _speedConfig = config);
        },
      ),
    );
  }

  late final InMemoryChatController _chatController;
  late final _DemoStreamManager _streamManager;
  final Uuid _uuid = const Uuid();
  final _PerformanceMonitor _perfMonitor = _PerformanceMonitor();
  bool _showPerfPanel = false;

  bool _autoFollowEnabled = true;
  double _lastScrollPixels = 0;
  bool _showScrollToBottom = false;
  DateTime _lastAutoFollowRequest = DateTime.fromMillisecondsSinceEpoch(0);

  _StreamingRenderMode _streamingRenderMode = _StreamingRenderMode.markdownStablePrefix;

  @override
  void initState() {
    super.initState();

    _chatController = InMemoryChatController();
    _streamManager = _DemoStreamManager(
      chatController: _chatController,
      chunkAnimationDuration: _chunkAnimationDuration,
    );

    _streamManager.addListener(_handleStreamTick);

    _chatController.setMessages([
      TextMessage(
        id: 'demo_1',
        authorId: _assistantUserId,
        createdAt: DateTime.now().toUtc().subtract(const Duration(minutes: 2)),
        text: '这是一个 Flyer Chat UI 流式 + Markdown 渲染测试页。\n\n发送一条消息后：\n- 可切换两种模式：\n  - Streaming: Markdown（稳定前缀）：边输出边渲染（对标 markstream-vue 观感）\n  - Streaming: 纯文本（结束后再渲染）：Strategy A\n\n当前渲染引擎：\n- markdown_widget（代码块/表格/链接）\n- LaTeX：flutter_math_fork\n- Mermaid：移动端 WebView\n\n建议你发送任意消息，然后观察：\n- 代码块何时从“尾巴纯文本”升级成高亮组件\n- 表格/公式/mermaid 在闭合结构后出现的时机',
      ),
    ]);
  }

  @override
  void dispose() {
    _streamManager.removeListener(_handleStreamTick);
    _streamManager.dispose();
    _chatController.dispose();
    super.dispose();
  }

  void _handleStreamTick() {
    if (_streamingRenderMode != _StreamingRenderMode.strategyA) return;
    _requestAutoFollow(smooth: false);
  }

  void _requestAutoFollow({required bool smooth}) {
    if (!_autoFollowEnabled) return;
    final messageCount = _chatController.messages.length;
    if (messageCount <= 0) return;

    final now = DateTime.now();
    if (now.difference(_lastAutoFollowRequest) < const Duration(milliseconds: 80)) return;
    _lastAutoFollowRequest = now;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final lastIndex = _chatController.messages.length - 1;
      _chatController.scrollToIndex(
        lastIndex,
        duration: smooth ? const Duration(milliseconds: 160) : Duration.zero,
        curve: Curves.easeOutCubic,
        alignment: 1.0,
        offset: 0,
      );
    });
  }

  bool _handleChatScrollNotification(ScrollNotification notification) {
    if (notification.depth != 0) return false;
    final metrics = notification.metrics;
    final extentAfter = metrics.extentAfter;
    const threshold = 80.0;

    final isNearBottom = extentAfter <= threshold;

    if (notification is ScrollUpdateNotification) {
      final currentPixels = metrics.pixels;
      final scrolledUp = currentPixels < _lastScrollPixels;
      _lastScrollPixels = currentPixels;

      if (scrolledUp && _autoFollowEnabled) {
        setState(() {
          _autoFollowEnabled = false;
          _showScrollToBottom = true;
        });
      } else if (isNearBottom && !_autoFollowEnabled) {
        setState(() {
          _autoFollowEnabled = true;
          _showScrollToBottom = false;
        });
      } else if (!isNearBottom && _autoFollowEnabled) {
        setState(() {
          _showScrollToBottom = true;
        });
      } else if (isNearBottom && _autoFollowEnabled && _showScrollToBottom) {
        setState(() {
          _showScrollToBottom = false;
        });
      }
    }

    if (notification is UserScrollNotification) {
      if (notification.direction == ScrollDirection.forward && _autoFollowEnabled) {
        setState(() {
          _autoFollowEnabled = false;
          _showScrollToBottom = true;
        });
      } else if (notification.direction == ScrollDirection.reverse && isNearBottom && !_autoFollowEnabled) {
        setState(() {
          _autoFollowEnabled = true;
          _showScrollToBottom = false;
        });
      }
    }

    return false;
  }

  Future<void> _handleMessageSend(String text) async {
    final trimmed = text.trim();
    if (trimmed.isEmpty) return;

    final userMessage = TextMessage(
      id: _uuid.v4(),
      authorId: _currentUserId,
      createdAt: DateTime.now().toUtc(),
      text: trimmed,
    );

    await _chatController.insertMessage(userMessage);
    await _simulateAssistantStream(trimmed);
  }

  Future<void> _simulateAssistantStream(String prompt) async {
    final full = _buildMarkdownResponse(prompt);

    switch (_streamingRenderMode) {
      case _StreamingRenderMode.strategyA:
        await _simulateAssistantStreamStrategyA(full);
        break;
      case _StreamingRenderMode.markdownStablePrefix:
        await _simulateAssistantStreamMarkdownStablePrefix(full);
        break;
    }
  }

  Future<void> _simulateAssistantStreamStrategyA(String full) async {
    final streamId = _uuid.v4();
    final messageId = _uuid.v4();
    final createdAt = DateTime.now().toUtc();

    final streamMessage = TextStreamMessage(
      id: messageId,
      authorId: _assistantUserId,
      createdAt: createdAt,
      streamId: streamId,
    );

    await _chatController.insertMessage(streamMessage);

    _streamManager.startStream(streamId, streamMessage);

    for (final chunk in _chunkify(full)) {
      if (!mounted) return;
      _streamManager.addChunk(streamId, chunk);
      await Future.delayed(_chunkDelay);
    }

    await _streamManager.completeStream(streamId);
  }

  Future<void> _simulateAssistantStreamMarkdownStablePrefix(String full) async {
    final messageId = _uuid.v4();
    final createdAt = DateTime.now().toUtc();

    var buffer = '';

    TextMessage current = TextMessage(
      id: messageId,
      authorId: _assistantUserId,
      createdAt: createdAt,
      text: buffer,
      metadata: const {'streaming': true},
    );
    await _chatController.insertMessage(current);

    DateTime lastUiUpdate = DateTime.fromMillisecondsSinceEpoch(0);

    Future<void> flush({required bool isFinal}) async {
      final newMsg = TextMessage(
        id: messageId,
        authorId: _assistantUserId,
        createdAt: createdAt,
        text: buffer,
        metadata: {'streaming': !isFinal},
      );

      final oldMsg = current;

      await WidgetsBinding.instance.endOfFrame;
      if (!mounted) return;
      await _chatController.updateMessage(oldMsg, newMsg);
      current = newMsg;

      _requestAutoFollow(smooth: isFinal);
    }

    for (final chunk in _chunkify(full)) {
      if (!mounted) return;
      buffer += chunk;

      final now = DateTime.now();
      if (now.difference(lastUiUpdate) >= _markdownStreamUpdateThrottle) {
        lastUiUpdate = now;
        await flush(isFinal: false);
      }

      await Future.delayed(_chunkDelay);
    }

    await flush(isFinal: true);
  }

  // 使用提取的 StablePrefixParser
  static const _stablePrefixParser = StablePrefixParser();

  StablePrefixResult _splitStableMarkdown(String source) {
    return _stablePrefixParser.split(source);
  }

  String _preprocessMarkdownForMarkdownWidget(String markdown) {
    var safe = markdown;

    if (safe.endsWith('- *')) {
      safe = safe.replaceFirst(RegExp(r'- \*$'), r'- \\*');
    }

    safe = safe.replaceFirst(RegExp(r'\n\s*[-*+]\s*$'), '\n');
    safe = safe.replaceFirst(RegExp(r'\n\s*-\s*$'), '\n');
    safe = safe.replaceFirst(RegExp(r'\n\s*>\s*$'), '\n');

    return safe;
  }

  List<({String kind, String text, bool open})> _splitByThinkingBlocks(String full) {
    const tags = <({String start, String end})>[
      (start: '<thinking>', end: '</thinking>'),
      (start: '<think>', end: '</think>'),
      (start: '<thought>', end: '</thought>'),
      (start: '<thoughts>', end: '</thoughts>'),
    ];

    final parts = <({String kind, String text, bool open})>[];
    var cursor = 0;

    while (cursor < full.length) {
      var earliest = -1;
      String? startTag;
      String? endTag;
      for (final tag in tags) {
        final idx = full.indexOf(tag.start, cursor);
        if (idx != -1 && (earliest == -1 || idx < earliest)) {
          earliest = idx;
          startTag = tag.start;
          endTag = tag.end;
        }
      }

      if (earliest == -1 || startTag == null || endTag == null) {
        final tail = full.substring(cursor);
        if (tail.isNotEmpty) parts.add((kind: 'markdown', text: tail, open: false));
        break;
      }

      final before = full.substring(cursor, earliest);
      if (before.isNotEmpty) parts.add((kind: 'markdown', text: before, open: false));

      final contentStart = earliest + startTag.length;
      final endIdx = full.indexOf(endTag, contentStart);
      if (endIdx == -1) {
        final thinking = full.substring(contentStart);
        parts.add((kind: 'thinking', text: thinking, open: true));
        break;
      }

      final thinking = full.substring(contentStart, endIdx);
      parts.add((kind: 'thinking', text: thinking, open: false));
      cursor = endIdx + endTag.length;
    }

    return parts;
  }

  Widget _buildThinkingSection({
    required BuildContext context,
    required bool isDark,
    required bool isStreaming,
    required String thinking,
    required bool thinkingOpen,
    required Widget Function(String text) buildMarkdown,
    required Color bubbleColor,
    required MarkdownConfig config,
  }) {
    final headerTextStyle = TextStyle(
      fontSize: 12,
      fontWeight: FontWeight.w700,
      color: isDark ? const Color(0xFFBFDBFE) : const Color(0xFF1D4ED8),
      letterSpacing: 0.2,
    );

    final content = isStreaming
        ? _StreamingMarkdownBody(
            text: thinking,
            splitStableMarkdown: _splitStableMarkdown,
            stableCacheKey: Object.hash(isDark, bubbleColor, config.hashCode, 'thinking'),
            markdown: buildMarkdown,
            plainTextStyle: config.p.textStyle,
            streamingCodeBlock: ({required language, required code, required isClosed}) {
              final inferred = inferCodeLanguage(declaredLanguage: language, code: code);
              if (inferred == 'mermaid') {
                return _EnhancedMermaidBlock(
                  mermaidCode: code,
                  isDark: isDark,
                  isStreaming: !isClosed,
                );
              }
              return _EnhancedCodeBlock(
                code: code,
                language: inferred,
                isDark: isDark,
                isStreaming: !isClosed,
              );
            },
          )
        : buildMarkdown(thinking);

    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: isDark ? const Color(0x331D4ED8) : const Color(0x1A3B82F6),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isDark ? const Color(0x33493BFF) : const Color(0x33493BFF),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text('Thinking', style: headerTextStyle),
              const SizedBox(width: 8),
              if (thinkingOpen) const _ThinkingDots(),
            ],
          ),
          const SizedBox(height: 8),
          ConstrainedBox(
            constraints: const BoxConstraints(maxHeight: 160, minHeight: 44),
            child: ScrollConfiguration(
              behavior: ScrollConfiguration.of(context).copyWith(scrollbars: false),
              child: SingleChildScrollView(
                physics: const ClampingScrollPhysics(),
                child: thinking.trim().isEmpty && thinkingOpen
                    ? Text('...', style: config.p.textStyle)
                    : content,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Iterable<String> _chunkify(String text) sync* {
    const int step = 4;
    var i = 0;
    while (i < text.length) {
      final end = (i + step) > text.length ? text.length : (i + step);
      yield text.substring(i, end);
      i = end;
    }
  }

  @override
  Widget build(BuildContext context) {
    final chatTheme = ChatTheme.fromThemeData(Theme.of(context));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Flyer Chat Demo'),
        actions: [
          IconButton(
            icon: const Icon(Icons.speed_rounded),
            tooltip: '渲染速度（当前：$_renderSpeedLabel）',
            onPressed: _showSpeedConfigDialog,
          ),
          PopupMenuButton<_StreamingRenderMode>(
            initialValue: _streamingRenderMode,
            onSelected: (mode) {
              setState(() {
                _streamingRenderMode = mode;
              });
            },
            itemBuilder: (context) => const [
              PopupMenuItem(
                value: _StreamingRenderMode.markdownStablePrefix,
                child: Text('Streaming: Markdown（稳定前缀）'),
              ),
              PopupMenuItem(
                value: _StreamingRenderMode.strategyA,
                child: Text('Streaming: 纯文本（结束后再渲染）'),
              ),
            ],
          ),
          IconButton(
            icon: Icon(
              Icons.analytics_outlined,
              color: _showPerfPanel ? Colors.blue : null,
            ),
            tooltip: '性能监控',
            onPressed: () => setState(() => _showPerfPanel = !_showPerfPanel),
          ),
        ],
      ),
      body: Stack(
        children: [
          NotificationListener<ScrollNotification>(
            onNotification: _handleChatScrollNotification,
            child: ScrollConfiguration(
              behavior: ScrollConfiguration.of(context).copyWith(scrollbars: false),
              child: Chat(
                chatController: _chatController,
                currentUserId: _currentUserId,
                theme: chatTheme,
                backgroundColor: chatTheme.colors.surface,
                builders: Builders(
                  textStreamMessageBuilder: (context, message, index, {required isSentByMe, groupStatus}) {
                    return AnimatedBuilder(
                      animation: _streamManager,
                      builder: (context, _) {
                        final streamState = _streamManager.getState(message.streamId);
                        return FlyerChatTextStreamMessage(
                          message: message,
                          index: index,
                          streamState: streamState,
                          chunkAnimationDuration: _chunkAnimationDuration,
                        );
                      },
                    );
                  },
                  textMessageBuilder: (context, message, index, {required isSentByMe, groupStatus}) {
              if (message.authorId != _assistantUserId) {
                return FlyerChatTextMessage(
                  message: message,
                  index: index,
                );
              }

              final bubbleColor = chatTheme.colors.surfaceContainerHigh;
              final isDark = Theme.of(context).brightness == Brightness.dark;
              final config = isDark ? MarkdownConfig.darkConfig : MarkdownConfig.defaultConfig;

              final isStreamingMarkdown = message.metadata?['streaming'] == true;

              final segments = _splitByThinkingBlocks(message.text);

              Widget codeWrapper(Widget child, String text, String language) {
                final lang = language.trim().toLowerCase();
                if (lang == 'mermaid') {
                  return MermaidRenderer(
                    mermaidCode: text,
                    isDark: isDark,
                  );
                }

                return _MarkdownCodeWrapper(
                  code: text,
                  language: lang.isEmpty ? 'plaintext' : lang,
                  isDark: isDark,
                  child: child,
                );
              }

              Widget buildMarkdown(String text) {
                final safeText = _preprocessMarkdownForMarkdownWidget(text);

                final blockquoteConfig = BlockquoteConfig(
                  sideColor: isDark ? const Color(0xFF60A5FA) : const Color(0xFF1A73E8),
                  textColor: isDark ? const Color(0xFFD1D5DB) : const Color(0xFF374151),
                  sideWith: 4,
                  padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
                  margin: const EdgeInsets.fromLTRB(0, 10, 0, 10),
                );

                final tableConfig = TableConfig(
                  headerRowDecoration: BoxDecoration(
                    color: isDark ? const Color(0xFF141821) : const Color(0xFFF3F4F6),
                  ),
                  headerStyle: TextStyle(
                    fontWeight: FontWeight.w700,
                    color: isDark ? const Color(0xFFE5E7EB) : const Color(0xFF111827),
                  ),
                  bodyStyle: TextStyle(
                    color: isDark ? const Color(0xFFD1D5DB) : const Color(0xFF111827),
                  ),
                  headPadding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
                  bodyPadding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
                  wrapper: (child) => _MarkdownTableWrapper(
                    isDark: isDark,
                    child: child,
                  ),
                );

                return MarkdownWidget(
                  data: safeText,
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  padding: EdgeInsets.zero,
                  config: config.copy(configs: [
                    LinkConfig(
                      style: TextStyle(
                        color: isDark ? const Color(0xFF8AB4F8) : const Color(0xFF1A73E8),
                        decoration: TextDecoration.underline,
                      ),
                      onTap: (url) async {
                        final uri = Uri.tryParse(url);
                        if (uri == null) return;
                        await launchUrl(uri, mode: LaunchMode.externalApplication);
                      },
                    ),
                    PreConfig(
                      theme: isDark ? monokaiSublimeTheme : githubTheme,
                      wrapper: codeWrapper,
                    ),
                    blockquoteConfig,
                    tableConfig,
                  ]),
                  markdownGenerator: MarkdownGenerator(
                    generators: [
                      _latexGenerator,
                      _interactiveLinkGenerator(),
                      _styledListItemGenerator(isDark: isDark),
                      _interactiveTableGenerator(isDark: isDark),
                      _zebraTbodyGenerator(isDark: isDark),
                      _styledBlockquoteGenerator(isDark: isDark),
                      _highlightGenerator(isDark: isDark),
                      _superscriptGenerator(),
                      _subscriptGenerator(),
                      _insertGenerator(isDark: isDark),
                    ],
                    inlineSyntaxList: [
                      _LatexSyntax(),
                      _HighlightSyntax(),
                      _SuperscriptSyntax(),
                      _SubscriptSyntax(),
                      _InsertSyntax(),
                    ],
                  ),
                );
              }

              final children = <Widget>[];
              for (var i = 0; i < segments.length; i++) {
                final seg = segments[i];

                if (seg.kind == 'thinking') {
                  if (seg.text.trim().isNotEmpty || seg.open) {
                    children.add(
                      _buildThinkingSection(
                        context: context,
                        isDark: isDark,
                        isStreaming: isStreamingMarkdown,
                        thinking: seg.text,
                        thinkingOpen: seg.open,
                        buildMarkdown: buildMarkdown,
                        bubbleColor: bubbleColor,
                        config: config,
                      ),
                    );
                  }
                  continue;
                }

                if (seg.text.isEmpty) continue;

                children.add(
                  isStreamingMarkdown
                      ? _StreamingMarkdownBody(
                          text: seg.text,
                          splitStableMarkdown: _splitStableMarkdown,
                          stableCacheKey: Object.hash(isDark, bubbleColor, config.hashCode, i),
                          markdown: buildMarkdown,
                          plainTextStyle: config.p.textStyle,
                          streamingCodeBlock: ({required language, required code, required isClosed}) {
                            final inferred = inferCodeLanguage(declaredLanguage: language, code: code);
                            if (inferred == 'mermaid') {
                              return _EnhancedMermaidBlock(
                                mermaidCode: code,
                                isDark: isDark,
                                isStreaming: !isClosed,
                              );
                            }
                            return _EnhancedCodeBlock(
                              code: code,
                              language: inferred,
                              isDark: isDark,
                              isStreaming: !isClosed,
                            );
                          },
                        )
                      : buildMarkdown(seg.text),
                );
              }

              final Widget content = children.length == 1
                  ? children.first
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: children,
                    );

                    return Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: bubbleColor,
                        borderRadius: chatTheme.shape,
                      ),
                      child: content,
                    );
                  },
                ),
                onMessageSend: _handleMessageSend,
                resolveUser: (userId) async {
                  if (userId == _currentUserId) {
                    return const User(id: _currentUserId, name: 'You');
                  }
                  return User(id: userId, name: userId);
                },
              ),
            ),
          ),
          if (_showPerfPanel)
            Positioned(
              right: 0,
              bottom: 80,
              child: _PerformancePanel(
                monitor: _perfMonitor,
                onClose: () => setState(() => _showPerfPanel = false),
              ),
            ),
        ],
      ),
    );
  }

}

enum _MermaidBlockTab {
  preview,
  source,
}

class _MermaidBlockFrame extends StatefulWidget {
  final String mermaidCode;
  final bool isDark;
  final bool isStreaming;

  const _MermaidBlockFrame({
    required this.mermaidCode,
    required this.isDark,
    required this.isStreaming,
  });

  @override
  State<_MermaidBlockFrame> createState() => _MermaidBlockFrameState();
}

class _MermaidBlockFrameState extends State<_MermaidBlockFrame> {
  _MermaidBlockTab _tab = _MermaidBlockTab.preview;

  bool get _isDesktop => Platform.isWindows || Platform.isLinux;

  Future<void> _copySource() async {
    await Clipboard.setData(ClipboardData(text: widget.mermaidCode));
    if (!mounted) return;
    final messenger = ScaffoldMessenger.maybeOf(context);
    messenger?.hideCurrentSnackBar();
    messenger?.showSnackBar(
      const SnackBar(
        content: Text('已复制'),
        duration: Duration(milliseconds: 900),
      ),
    );
  }

  String _escapeMermaidCode(String code) {
    return code
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;');
  }

  Future<void> _openExternalPreview() async {
    try {
      final template = await rootBundle.loadString('assets/web/mermaid_template.html');
      final html = template
          .replaceAll('{{MERMAID_CODE}}', _escapeMermaidCode(widget.mermaidCode))
          .replaceAll('{{THEME}}', widget.isDark ? 'dark' : 'default');

      final dir = await getTemporaryDirectory();
      final file = File(
        '${dir.path}${Platform.pathSeparator}mermaid_preview_${DateTime.now().millisecondsSinceEpoch}.html',
      );
      await file.writeAsString(html);

      await launchUrl(
        Uri.file(file.path),
        mode: LaunchMode.externalApplication,
      );
    } catch (_) {
      if (!mounted) return;
      final messenger = ScaffoldMessenger.maybeOf(context);
      messenger?.hideCurrentSnackBar();
      messenger?.showSnackBar(
        const SnackBar(
          content: Text('外部预览打开失败'),
          duration: Duration(milliseconds: 900),
        ),
      );
    }
  }

  Widget _buildTabButton({
    required String label,
    required bool selected,
    required VoidCallback onTap,
  }) {
    final fg = selected
        ? (widget.isDark ? const Color(0xFFE5E7EB) : const Color(0xFF111827))
        : (widget.isDark ? const Color(0xFF9CA3AF) : const Color(0xFF6B7280));

    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(6),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: selected
              ? (widget.isDark ? const Color(0xFF1F2430) : const Color(0xFFE7EAF0))
              : Colors.transparent,
          borderRadius: BorderRadius.circular(6),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: fg,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final header = Padding(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 10),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
            decoration: BoxDecoration(
              color: widget.isDark ? const Color(0x263B82F6) : const Color(0x1A1A73E8),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              'MERMAID',
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: widget.isDark ? const Color(0xFF93C5FD) : const Color(0xFF1A73E8),
                letterSpacing: 0.5,
              ),
            ),
          ),
          const Spacer(),
          Container(
            padding: const EdgeInsets.all(2),
            decoration: BoxDecoration(
              color: widget.isDark ? const Color(0xFF171A20) : const Color(0xFFF1F3F5),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: widget.isDark ? const Color(0x1AFFFFFF) : const Color(0x14000000),
              ),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                _buildTabButton(
                  label: 'Preview',
                  selected: _tab == _MermaidBlockTab.preview,
                  onTap: () => setState(() => _tab = _MermaidBlockTab.preview),
                ),
                _buildTabButton(
                  label: 'Source',
                  selected: _tab == _MermaidBlockTab.source,
                  onTap: () => setState(() => _tab = _MermaidBlockTab.source),
                ),
              ],
            ),
          ),
          const SizedBox(width: 6),
          IconButton(
            onPressed: _copySource,
            icon: Icon(
              Icons.content_copy_rounded,
              size: 18,
              color: widget.isDark ? Colors.grey.shade500 : Colors.grey.shade600,
            ),
            padding: EdgeInsets.zero,
            visualDensity: VisualDensity.compact,
            constraints: const BoxConstraints.tightFor(width: 32, height: 32),
          ),
        ],
      ),
    );

    final Widget body;
    if (_tab == _MermaidBlockTab.source) {
      body = _StreamingCodeBlockPreview(
        code: widget.mermaidCode,
        language: 'mermaid',
        isDark: widget.isDark,
        includeOuterContainer: false,
        showHeader: false,
      );
    } else {
      if (_isDesktop) {
        body = Padding(
          padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '桌面平台不支持内嵌 Mermaid 渲染。',
                style: TextStyle(
                  fontSize: 13,
                  color: widget.isDark ? const Color(0xFFD1D5DB) : const Color(0xFF374151),
                ),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: Text(
                      widget.isStreaming ? '等待闭合后可渲染。你也可以直接外部预览。' : '你可以外部预览，或切到 Source 查看源码。',
                      style: TextStyle(
                        fontSize: 12,
                        color: widget.isDark ? const Color(0xFF9CA3AF) : const Color(0xFF6B7280),
                      ),
                    ),
                  ),
                  TextButton(
                    onPressed: _openExternalPreview,
                    child: const Text('外部预览'),
                  ),
                ],
              ),
            ],
          ),
        );
      } else if (widget.isStreaming) {
        body = Padding(
          padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
          child: Row(
            children: [
              SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor: AlwaysStoppedAnimation<Color>(
                    widget.isDark ? const Color(0xFF93C5FD) : const Color(0xFF1A73E8),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Text(
                'Mermaid 渲染中…（等待闭合）',
                style: TextStyle(
                  fontSize: 13,
                  color: widget.isDark ? const Color(0xFFD1D5DB) : const Color(0xFF374151),
                ),
              ),
            ],
          ),
        );
      } else {
        body = Padding(
          padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
          child: MermaidRenderer(
            mermaidCode: widget.mermaidCode,
            isDark: widget.isDark,
            height: 320,
            includeOuterContainer: false,
            margin: EdgeInsets.zero,
          ),
        );
      }
    }

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: widget.isDark ? const Color(0xFF14161A) : const Color(0xFFF6F8FA),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: widget.isDark ? const Color(0x26FFFFFF) : const Color(0x1A000000),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          header,
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 180),
            switchInCurve: Curves.easeOut,
            switchOutCurve: Curves.easeIn,
            child: KeyedSubtree(
              key: ValueKey(_tab == _MermaidBlockTab.preview ? 'preview' : 'source'),
              child: body,
            ),
          ),
        ],
      ),
    );
  }
}

class _ThinkingDots extends StatefulWidget {
  const _ThinkingDots();

  @override
  State<_ThinkingDots> createState() => _ThinkingDotsState();
}

class _ThinkingDotsState extends State<_ThinkingDots> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    Widget dot(double start) {
      final animation = CurvedAnimation(
        parent: _controller,
        curve: Interval(start, (start + 0.6).clamp(0.0, 1.0), curve: Curves.easeInOut),
      );
      return FadeTransition(
        opacity: Tween<double>(begin: 0.25, end: 1).animate(animation),
        child: const DecoratedBox(
          decoration: BoxDecoration(
            color: Color(0xFF2563EB),
            shape: BoxShape.circle,
          ),
          child: SizedBox(width: 6, height: 6),
        ),
      );
    }

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        dot(0.0),
        const SizedBox(width: 6),
        dot(0.15),
        const SizedBox(width: 6),
        dot(0.3),
      ],
    );
  }
}
