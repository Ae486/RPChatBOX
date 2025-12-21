part of '../flyer_chat_demo_page.dart';

/// 高亮标记语法 (==text==)
/// 
/// 参考 markstream-vue: src/components/HighlightNode/HighlightNode.vue
class _HighlightSyntax extends m.InlineSyntax {
  _HighlightSyntax() : super(r'==([^=]+)==');

  @override
  bool onMatch(m.InlineParser parser, Match match) {
    final text = match[1]!;
    final el = m.Element.text('highlight', text);
    parser.addNode(el);
    return true;
  }
}

/// 高亮节点
class _HighlightNode extends SpanNode {
  final String text;
  final bool isDark;

  _HighlightNode(this.text, {required this.isDark});

  @override
  InlineSpan build() {
    return WidgetSpan(
      alignment: PlaceholderAlignment.baseline,
      baseline: TextBaseline.alphabetic,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 3),
        decoration: BoxDecoration(
          color: isDark 
              ? const Color(0xFFFFFF00).withValues(alpha: 0.3)
              : const Color(0xFFFFFF00).withValues(alpha: 0.5),
          borderRadius: BorderRadius.circular(2),
        ),
        child: Text(
          text,
          style: TextStyle(
            color: isDark ? Colors.white : Colors.black87,
          ),
        ),
      ),
    );
  }
}

/// 高亮节点生成器
SpanNodeGeneratorWithTag _highlightGenerator({required bool isDark}) {
  return SpanNodeGeneratorWithTag(
    tag: 'highlight',
    generator: (e, config, visitor) => _HighlightNode(
      e.textContent,
      isDark: isDark,
    ),
  );
}
