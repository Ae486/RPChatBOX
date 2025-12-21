import 'package:flutter/material.dart';

import 'stable_markdown_splitter.dart';

typedef StreamingCodeBlockBuilder = Widget Function({required String language, required String code});

class StreamingMarkdownBody extends StatelessWidget {
  final String text;
  final StableMarkdownSplitResult Function(String source) splitStableMarkdown;
  final Widget Function(String markdownText) markdown;
  final TextStyle plainTextStyle;
  final StreamingCodeBlockBuilder? streamingCodeBlock;

  const StreamingMarkdownBody({
    super.key,
    required this.text,
    required this.markdown,
    required this.plainTextStyle,
    this.splitStableMarkdown = StableMarkdownSplitter.split,
    this.streamingCodeBlock,
  });

  static ({String language, String code, String rest})? _extractLeadingFence(String input) {
    final match = RegExp(r'^\s*(```|~~~)([^\n\r]*)\r?\n?').firstMatch(input);
    if (match == null) return null;

    final marker = match.group(1)!;
    final lang = (match.group(2) ?? '').trim();
    final after = input.substring(match.end);

    final close = RegExp('(^|\\r?\\n)${RegExp.escape(marker)}', multiLine: true).firstMatch(after);
    if (close == null) {
      return (language: lang, code: after, rest: '');
    }

    final code = after.substring(0, close.start);
    final rest = after.substring(close.end);
    return (language: lang, code: code, rest: rest);
  }

  @override
  Widget build(BuildContext context) {
    final parts = splitStableMarkdown(text);

    final fence = streamingCodeBlock == null ? null : _extractLeadingFence(parts.tail);

    if (parts.stable.isEmpty) {
      if (fence != null) {
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            streamingCodeBlock!(language: fence.language, code: fence.code),
            if (fence.rest.isNotEmpty)
              Text(
                fence.rest,
                style: plainTextStyle,
              ),
          ],
        );
      }

      return Text(
        parts.tail,
        style: plainTextStyle,
      );
    }

    if (parts.tail.isEmpty) {
      return markdown(parts.stable);
    }

    if (fence != null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          markdown(parts.stable),
          streamingCodeBlock!(language: fence.language, code: fence.code),
          if (fence.rest.isNotEmpty)
            Text(
              fence.rest,
              style: plainTextStyle,
            ),
        ],
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        markdown(parts.stable),
        Text(
          parts.tail,
          style: plainTextStyle,
        ),
      ],
    );
  }
}
