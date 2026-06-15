/// INPUT: Markdown 文本 + 主题深浅 + 流式标记
/// OUTPUT: OwuiMarkdown - Markdown 渲染（表格/代码/LaTeX/图片/Mermaid/error 块）
/// POS: UI 层 / Markdown / Owui - 主 Markdown 渲染入口
///
/// 渲染委托给共享模块 OwuiSmoothMarkdown(基于 flutter_smooth_markdown)；本类只负责
/// 生产侧预处理(think 剥离安全网 / 缩进码块归一)与 UI 缩放，并保持对外契约不变。
/// think 已在上游 StreamManager 剥离，此处剥离仅作安全网；`<error>` 协议块由共享模块解析渲染。
library;

import 'package:flutter/material.dart';

import 'owui_tokens_ext.dart';
import 'smooth/owui_smooth_markdown.dart';

class OwuiMarkdown extends StatelessWidget {
  final String text;
  final bool isDark;
  final bool isStreaming;

  const OwuiMarkdown({
    super.key,
    required this.text,
    required this.isDark,
    required this.isStreaming,
  });

  @visibleForTesting
  static String debugStripInternalThinkBlocks(String source) {
    var sanitized = source;

    for (final tagName in const ['thinking', 'think', 'thought', 'thoughts']) {
      sanitized = sanitized.replaceAll(
        RegExp('<$tagName>[\\s\\S]*?</$tagName>', dotAll: true),
        '',
      );
      sanitized = sanitized.replaceAll('<$tagName>', '');
      sanitized = sanitized.replaceAll('</$tagName>', '');
    }

    return sanitized;
  }

  String _stripInternalThinkBlocks(String source) =>
      debugStripInternalThinkBlocks(source);

  /// flutter_smooth_markdown 不识别 4 空格缩进代码块（会当普通段落）。沿用旧逻辑把
  /// 缩进块转换为带 `plain` 语言的围栏块，保持既有的缩进代码渲染能力。
  String _normalizeIndentedCodeBlocks(String markdown) {
    final lines = markdown.split('\n');
    final out = <String>[];

    var inFence = false;
    var fenceChar = '';
    var fenceLen = 0;
    var prevBlank = true;

    bool isIndented(String line) =>
        line.startsWith('\t') || line.startsWith('    ');
    String leadingIndent(String line) =>
        RegExp(r'^[ \t]+').firstMatch(line)?.group(0) ?? '';

    final fenceRe = RegExp(r'^(\s*)(```+|~~~+)(.*)$');

    var i = 0;
    while (i < lines.length) {
      final line = lines[i];
      final trimmed = line.trimRight();

      final m = fenceRe.firstMatch(line);
      if (m != null) {
        final fence = m.group(2)!;
        final rest = (m.group(3) ?? '').trim();
        if (!inFence) {
          inFence = true;
          fenceChar = fence[0];
          fenceLen = fence.length;
        } else {
          final isClosing =
              fence[0] == fenceChar && fence.length >= fenceLen && rest.isEmpty;
          if (isClosing) {
            inFence = false;
            fenceChar = '';
            fenceLen = 0;
          }
        }
        out.add(line);
        prevBlank = trimmed.isEmpty;
        i++;
        continue;
      }

      if (!inFence && prevBlank && isIndented(line)) {
        final indent = leadingIndent(line);
        out.add('$indent```plain');
        while (i < lines.length) {
          final l = lines[i];
          if (l.trim().isEmpty) {
            out.add('');
            i++;
            continue;
          }
          if (!l.startsWith(indent)) break;
          out.add(l.substring(indent.length));
          i++;
        }
        out.add('$indent```');
        prevBlank = true;
        continue;
      }

      out.add(line);
      prevBlank = trimmed.isEmpty;
      i++;
    }

    return out.join('\n');
  }

  @override
  Widget build(BuildContext context) {
    final processed =
        _normalizeIndentedCodeBlocks(_stripInternalThinkBlocks(text));

    Widget md = OwuiSmoothMarkdown(
      text: processed,
      isDark: isDark,
      isStreaming: isStreaming,
      selectable: !isStreaming, // 流式禁选，规避 SelectionArea 布局错误
    );

    // 保留 UI 缩放：owui 设计体系以 uiScale 统一缩放，默认 1.0(与 lab 一致，无副作用)。
    final uiScale = context.owui.uiScale;
    if (uiScale != 1.0) {
      final mq = MediaQuery.of(context);
      md = MediaQuery(
        data: mq.copyWith(textScaler: TextScaler.linear(uiScale)),
        child: md,
      );
    }
    return md;
  }
}
