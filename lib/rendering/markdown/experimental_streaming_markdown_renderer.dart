import 'package:flutter/material.dart';

import '../../widgets/enhanced_content_renderer.dart';
import 'streaming_markdown_body.dart';

class ExperimentalStreamingMarkdownRenderer extends StatelessWidget {
  final String text;
  final TextStyle textStyle;
  final Color? backgroundColor;
  final bool isUser;

  const ExperimentalStreamingMarkdownRenderer({
    super.key,
    required this.text,
    required this.textStyle,
    required this.backgroundColor,
    required this.isUser,
  });

  @override
  Widget build(BuildContext context) {
    return StreamingMarkdownBody(
      text: text,
      markdown: (markdownText) {
        return EnhancedContentRenderer(
          content: markdownText,
          textStyle: textStyle,
          backgroundColor: backgroundColor,
          isUser: isUser,
        );
      },
      plainTextStyle: textStyle,
    );
  }
}
