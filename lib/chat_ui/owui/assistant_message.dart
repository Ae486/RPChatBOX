/// INPUT: Assistant 消息元信息 + Markdown 内容 + StreamManager 流式状态 + 会话设置
/// OUTPUT: OwuiAssistantMessage - 助手消息渲染（Markdown/Thinking/Meta/图片）
/// POS: UI 层 / Chat / Owui - V2 助手消息组件（由 ConversationViewV2 组装）

import 'dart:convert';
import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
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
