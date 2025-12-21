part of '../flyer_chat_demo_page.dart';

/// 插入标记语法 (++text++)
/// 
/// 参考 markstream-vue: src/components/InsertNode/InsertNode.vue
/// 渲染为下划线文本
class _InsertSyntax extends m.InlineSyntax {
  _InsertSyntax() : super(r'\+\+([^\+]+)\+\+');

  @override
  bool onMatch(m.InlineParser parser, Match match) {
    final text = match[1]!;
    final el = m.Element.text('insert', text);
    parser.addNode(el);
    return true;
  }
}

/// 插入节点
class _InsertNode extends SpanNode {
  final String text;
  final bool isDark;

  _InsertNode(this.text, {required this.isDark});

  @override
  InlineSpan build() {
    return TextSpan(
      text: text,
      style: TextStyle(
        decoration: TextDecoration.underline,
        decorationColor: isDark ? Colors.green.shade300 : Colors.green.shade700,
        color: isDark ? Colors.green.shade200 : Colors.green.shade800,
      ),
    );
  }
}

/// 插入节点生成器
SpanNodeGeneratorWithTag _insertGenerator({required bool isDark}) {
  return SpanNodeGeneratorWithTag(
    tag: 'insert',
    generator: (e, config, visitor) => _InsertNode(
      e.textContent,
      isDark: isDark,
    ),
  );
}
