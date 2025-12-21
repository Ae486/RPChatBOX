part of '../flyer_chat_demo_page.dart';

/// 上标语法 (^text^)
/// 
/// 参考 markstream-vue: src/components/SuperscriptNode/SuperscriptNode.vue
class _SuperscriptSyntax extends m.InlineSyntax {
  _SuperscriptSyntax() : super(r'\^([^\^]+)\^');

  @override
  bool onMatch(m.InlineParser parser, Match match) {
    final text = match[1]!;
    final el = m.Element.text('superscript', text);
    parser.addNode(el);
    return true;
  }
}

/// 下标语法 (~text~)
/// 
/// 参考 markstream-vue: src/components/SubscriptNode/SubscriptNode.vue
class _SubscriptSyntax extends m.InlineSyntax {
  _SubscriptSyntax() : super(r'~([^~]+)~');

  @override
  bool onMatch(m.InlineParser parser, Match match) {
    final text = match[1]!;
    final el = m.Element.text('subscript', text);
    parser.addNode(el);
    return true;
  }
}

/// 上标节点
class _SuperscriptNode extends SpanNode {
  final String text;
  final TextStyle? parentStyle;

  _SuperscriptNode(this.text, {this.parentStyle});

  @override
  InlineSpan build() {
    final baseSize = parentStyle?.fontSize ?? 14.0;
    return TextSpan(
      text: text,
      style: TextStyle(
        fontSize: baseSize * 0.75,
        fontFeatures: const [FontFeature.superscripts()],
      ),
    );
  }
}

/// 下标节点
class _SubscriptNode extends SpanNode {
  final String text;
  final TextStyle? parentStyle;

  _SubscriptNode(this.text, {this.parentStyle});

  @override
  InlineSpan build() {
    final baseSize = parentStyle?.fontSize ?? 14.0;
    return TextSpan(
      text: text,
      style: TextStyle(
        fontSize: baseSize * 0.75,
        fontFeatures: const [FontFeature.subscripts()],
      ),
    );
  }
}

/// 上标节点生成器
SpanNodeGeneratorWithTag _superscriptGenerator() {
  return SpanNodeGeneratorWithTag(
    tag: 'superscript',
    generator: (e, config, visitor) => _SuperscriptNode(
      e.textContent,
      parentStyle: config.p.textStyle,
    ),
  );
}

/// 下标节点生成器
SpanNodeGeneratorWithTag _subscriptGenerator() {
  return SpanNodeGeneratorWithTag(
    tag: 'subscript',
    generator: (e, config, visitor) => _SubscriptNode(
      e.textContent,
      parentStyle: config.p.textStyle,
    ),
  );
}
