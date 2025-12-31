import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../models/conversation_settings.dart';
import '../../widgets/conversation_view_v2.dart';
import '../../widgets/stream_manager.dart';
import 'chat_theme.dart';
import 'markdown.dart';
import 'owui_tokens_ext.dart';
import 'palette.dart';

class OwuiAssistantMessage extends StatelessWidget {
  final String messageId;
  final DateTime createdAt;
  final String bodyMarkdown;
  final bool isStreaming;
  final String? modelName;
  final String? providerName;
  final StreamData? streamData;

  const OwuiAssistantMessage({
    super.key,
    required this.messageId,
    required this.createdAt,
    required this.bodyMarkdown,
    required this.isStreaming,
    required this.modelName,
    required this.providerName,
    required this.streamData,
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

    if (thinking.trim().isNotEmpty || thinkingOpen) {
      children.add(
        Container(
          width: double.infinity,
          margin: EdgeInsets.only(bottom: 10 * uiScale),
          padding: EdgeInsets.all(12 * uiScale),
          decoration: OwuiChatTheme.thinkingDecoration(context),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Text(
                    'Thinking',
                    style: TextStyle(
                      fontSize: 12 * uiScale,
                      fontWeight: FontWeight.w700,
                      color: isDark ? const Color(0xFFBFDBFE) : const Color(0xFF1D4ED8),
                      letterSpacing: 0.2,
                    ),
                  ),
                  if (thinkingOpen) ...[
                    SizedBox(width: 8 * uiScale),
                    _ThinkingDots(uiScale: uiScale),
                  ],
                ],
              ),
              SizedBox(height: 8 * uiScale),
              ConstrainedBox(
                constraints: BoxConstraints(maxHeight: 160 * uiScale, minHeight: 44 * uiScale),
                child: ScrollConfiguration(
                  behavior: ScrollConfiguration.of(context).copyWith(scrollbars: false),
                  child: SingleChildScrollView(
                    physics: const ClampingScrollPhysics(),
                    child: thinking.trim().isEmpty && thinkingOpen
                        ? Text('...', style: TextStyle(color: OwuiPalette.textSecondary(context)))
                        : OwuiMarkdown(
                            text: thinking,
                            isDark: isDark,
                            isStreaming: isStreaming,
                            stableCacheKey: Object.hash(isDark, messageId, 'thinking'),
                            enableSmoothCodeBlock: enableSmoothCode,
                            enableSmoothMermaid: enableSmoothMermaid,
                            enableFadeIn: enableFadeIn,
                            fadeInDuration: Duration(milliseconds: fadeInDurationMs),
                            fadeInStartOpacity: fadeInStartOpacity,
                          ),
                  ),
                ),
              ),
            ],
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

class _ThinkingDots extends StatefulWidget {
  final double uiScale;

  const _ThinkingDots({required this.uiScale});

  @override
  State<_ThinkingDots> createState() => _ThinkingDotsState();
}

class _ThinkingDotsState extends State<_ThinkingDots> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 900),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final t = _controller.value;
        final count = (t * 3).floor() + 1;
        return Text(
          '.' * count,
          style: TextStyle(
            fontSize: 12 * widget.uiScale,
            fontWeight: FontWeight.w700,
            color: OwuiPalette.textSecondary(context),
          ),
        );
      },
    );
  }
}
