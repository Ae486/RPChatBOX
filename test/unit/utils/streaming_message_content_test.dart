import 'package:chatboxapp/utils/streaming_message_content.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('preserves aborted error block when there is no streamed body yet', () {
    const errorTag =
        '<error type="unknown" brief="Request was aborted">Request was aborted</error>';

    final finalContent = buildStreamingFinalContent(
      thinking: '',
      body: '',
      errorTag: errorTag,
    );

    expect(finalContent, errorTag);
    expect(shouldPersistFinalizedStreamingMessage(finalContent), isTrue);
  });

  test('appends aborted error block after rendered body content', () {
    const errorTag =
        '<error type="unknown" brief="Request was aborted">Request was aborted</error>';

    final finalContent = buildStreamingFinalContent(
      thinking: '',
      body: '已生成的正文',
      errorTag: errorTag,
    );

    expect(finalContent, '已生成的正文\n$errorTag');
    expect(shouldPersistFinalizedStreamingMessage(finalContent), isTrue);
  });

  test('combines thinking body and error in the expected order', () {
    const errorTag =
        '<error type="unknown" brief="Request was aborted">Request was aborted</error>';

    final finalContent = buildStreamingFinalContent(
      thinking: '思考内容',
      body: '正文内容',
      errorTag: errorTag,
    );

    expect(
      finalContent,
      '<think>思考内容</think>正文内容\n$errorTag',
    );
  });
}
