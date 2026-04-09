import 'package:chatboxapp/widgets/stream_manager.dart';
import 'package:chatboxapp/models/mcp/mcp_tool_call.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('StreamManager thinking parsing', () {
    late StreamManager manager;
    const streamId = 'stream-1';

    setUp(() {
      manager = StreamManager();
      manager.createStream(streamId);
    });

    tearDown(() {
      manager.dispose();
    });

    test('separates thinking content from body when tags are complete', () {
      manager.append(streamId, '正文前<think>思考内容</think>正文后');

      final data = manager.getData(streamId)!;
      expect(data.content, '正文前正文后');
      expect(data.thinkingContent, '思考内容');
      expect(data.isThinkingOpen, isFalse);
      expect(data.thinkingEndTime, isNotNull);
    });

    test('keeps thinking state open across chunks until closing tag arrives', () {
      manager.append(streamId, '开头<think>第一段');

      var data = manager.getData(streamId)!;
      expect(data.content, '开头');
      expect(data.thinkingContent, '第一段');
      expect(data.isThinkingOpen, isTrue);

      manager.append(streamId, '第二段</think>结尾');

      data = manager.getData(streamId)!;
      expect(data.content, '开头结尾');
      expect(data.thinkingContent, '第一段第二段');
      expect(data.isThinkingOpen, isFalse);
      expect(data.thinkingEndTime, isNotNull);
    });

    test('forces unfinished thinking block to close when stream ends', () {
      manager.append(streamId, '<think>未完成思考');
      manager.end(streamId);

      final data = manager.getData(streamId)!;
      expect(data.thinkingContent, '未完成思考');
      expect(data.isThinkingOpen, isFalse);
      expect(data.thinkingEndTime, isNotNull);
      expect(data.status, StreamStatus.completed);
    });

    test('supports typed thinking deltas without string tags', () {
      manager.appendThinking(streamId, '第一段');
      manager.appendThinking(streamId, '第二段');
      manager.closeThinking(streamId);

      final data = manager.getData(streamId)!;
      expect(data.content, '');
      expect(data.thinkingContent, '第一段第二段');
      expect(data.isThinkingOpen, isFalse);
      expect(data.thinkingStartTime, isNotNull);
      expect(data.thinkingEndTime, isNotNull);
    });

    test('supports typed text deltas without thinking parsing', () {
      manager.appendThinking(streamId, '思考');
      manager.closeThinking(streamId);
      manager.appendText(streamId, '正文A');
      manager.appendText(streamId, '正文B');

      final data = manager.getData(streamId)!;
      expect(data.thinkingContent, '思考');
      expect(data.content, '正文A正文B');
    });

    test('supports tool lifecycle state transitions', () {
      manager.addToolCall(
        streamId,
        ToolCallData(
          callId: 'call_1',
          toolName: 'web_search',
          status: ToolCallStatus.pending,
        ),
      );

      manager.startToolCall(streamId, 'call_1');
      manager.completeToolCall(
        streamId,
        'call_1',
        success: true,
        result: '搜索完成',
      );

      final toolCalls = manager.getToolCalls(streamId);
      expect(toolCalls, hasLength(1));
      expect(toolCalls.first.status, ToolCallStatus.success);
      expect(toolCalls.first.result, '搜索完成');
      expect(toolCalls.first.startTime, isNotNull);
      expect(toolCalls.first.endTime, isNotNull);
    });
  });
}
