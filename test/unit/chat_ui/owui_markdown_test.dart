import 'package:chatboxapp/chat_ui/owui/markdown.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('debugStripInternalThinkBlocks removes internal think protocol tags', () {
    final sanitized = OwuiMarkdown.debugStripInternalThinkBlocks(
      '<think>思考内容</think>正文',
    );

    expect(sanitized, '正文');
  });

  test('debugStripInternalThinkBlocks removes dangling think tags without swallowing body', () {
    final sanitized = OwuiMarkdown.debugStripInternalThinkBlocks(
      '<think>思考内容正文',
    );

    expect(sanitized, '思考内容正文');
  });
}
