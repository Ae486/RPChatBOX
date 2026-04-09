import 'package:chatboxapp/adapters/ai_provider.dart';
import 'package:chatboxapp/adapters/proxy_openai_provider.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ProxyStreamChunkParser', () {
    setUp(() {
      ProxyOpenAIProvider.debugSetPreferTypedStreamEvents(true);
    });

    test('consumes backend-normalized delta.content chunks as-is', () {
      final parser = ProxyStreamChunkParser(isGeminiModel: false);

      final outputs = <String>[
        ...parser.parse({
          'choices': [
            {
              'delta': {'content': '<think>'},
            },
          ],
        }),
        ...parser.parse({
          'choices': [
            {
              'delta': {'content': '先分析'},
            },
          ],
        }),
        ...parser.parse({
          'choices': [
            {
              'delta': {'content': '</think>'},
            },
          ],
        }),
        ...parser.parse({
          'choices': [
            {
              'delta': {'content': '最终回答'},
            },
          ],
        }),
        ...parser.flush(),
      ];

      expect(outputs, ['<think>', '先分析', '</think>', '最终回答']);
    });

    test('keeps legacy reasoning close-before-body ordering', () {
      final parser = ProxyStreamChunkParser(isGeminiModel: false);

      final outputs = <String>[
        ...parser.parse({
          'choices': [
            {
              'delta': {'reasoning_content': '先分析'},
            },
          ],
        }),
        ...parser.parse({
          'choices': [
            {
              'delta': {'content': '最终回答'},
            },
          ],
        }),
        ...parser.flush(),
      ];

      expect(outputs, ['<think>', '先分析', '</think>', '最终回答']);
    });

    test('falls back to legacy gemini candidates parsing', () {
      final parser = ProxyStreamChunkParser(isGeminiModel: true);

      final outputs = <String>[
        ...parser.parse({
          'candidates': [
            {
              'content': {
                'parts': [
                  {'text': '隐藏思考'},
                  {'text': '第一段正文'},
                  {'text': '第二段正文'},
                ],
              },
            },
          ],
        }),
        ...parser.flush(),
      ];

      expect(outputs, ['<think>', '隐藏思考', '</think>', '第一段正文', '第二段正文']);
    });

    test('extracts text from normalized content part lists', () {
      final parser = ProxyStreamChunkParser(isGeminiModel: false);

      final outputs = parser.parse({
        'choices': [
          {
            'delta': {
              'content': [
                {'text': '片段A'},
                {'content': '片段B'},
                '片段C',
              ],
            },
          },
        ],
      }).toList();

      expect(outputs, ['片段A', '片段B', '片段C']);
    });

    test('adapts typed SSE thinking/text events into current UI-compatible chunks', () {
      final parser = ProxyStreamChunkParser(isGeminiModel: false);

      final outputs = <String>[
        ...parser.parse({
          'type': 'thinking_delta',
          'delta': '先分析',
        }),
        ...parser.parse({
          'type': 'text_delta',
          'delta': '最终回答',
        }),
        ...parser.parse({
          'type': 'done',
        }),
        ...parser.flush(),
      ];

      expect(outputs, ['<think>', '先分析', '</think>', '最终回答']);
    });

    test('closes typed thinking before tool_call event', () {
      final parser = ProxyStreamChunkParser(isGeminiModel: false);

      final outputs = <String>[
        ...parser.parse({
          'type': 'thinking_delta',
          'delta': '先分析',
        }),
        ...parser.parse({
          'type': 'tool_call',
          'tool_calls': [
            {
              'id': 'call_123',
              'type': 'function',
              'function': {'name': 'web_search', 'arguments': '{}'},
            },
          ],
        }),
        ...parser.parse({
          'type': 'text_delta',
          'delta': '最终回答',
        }),
        ...parser.flush(),
      ];

      expect(outputs, ['<think>', '先分析', '</think>', '最终回答']);
    });

    test('emits structured typed events from typed SSE payloads', () {
      final parser = ProxyStreamChunkParser(isGeminiModel: false);

      final events = <AIStreamEvent>[
        ...parser.parseEvents({
          'type': 'thinking_delta',
          'delta': '先分析',
        }),
        ...parser.parseEvents({
          'type': 'text_delta',
          'delta': '最终回答',
        }),
        ...parser.parseEvents({
          'type': 'tool_call',
          'tool_calls': [
            {
              'id': 'call_1',
              'type': 'function',
              'function': {'name': 'web_search', 'arguments': '{}'},
            },
          ],
        }),
      ];

      expect(events[0].type, AIStreamEventType.thinking);
      expect(events[0].text, '先分析');
      expect(events[0].isTypedSemantic, isTrue);

      expect(events[1].type, AIStreamEventType.text);
      expect(events[1].text, '最终回答');
      expect(events[1].isTypedSemantic, isTrue);

      expect(events[2].type, AIStreamEventType.toolCall);
      expect(events[2].toolCalls, hasLength(1));
      expect(events[2].isTypedSemantic, isTrue);
    });

    test('emits structured typed tool lifecycle events', () {
      final parser = ProxyStreamChunkParser(isGeminiModel: false);

      final events = <AIStreamEvent>[
        ...parser.parseEvents({
          'type': 'tool_started',
          'call_id': 'call_1',
          'tool_name': 'web_search',
        }),
        ...parser.parseEvents({
          'type': 'tool_result',
          'call_id': 'call_1',
          'tool_name': 'web_search',
          'result': '搜索完成',
        }),
        ...parser.parseEvents({
          'type': 'tool_error',
          'call_id': 'call_2',
          'tool_name': 'read_file',
          'error': 'permission denied',
        }),
      ];

      expect(events[0].type, AIStreamEventType.toolStarted);
      expect(events[0].callId, 'call_1');
      expect(events[0].toolName, 'web_search');
      expect(events[0].isTypedSemantic, isTrue);

      expect(events[1].type, AIStreamEventType.toolResult);
      expect(events[1].callId, 'call_1');
      expect(events[1].result, '搜索完成');
      expect(events[1].isTypedSemantic, isTrue);

      expect(events[2].type, AIStreamEventType.toolError);
      expect(events[2].callId, 'call_2');
      expect(events[2].errorMessage, 'permission denied');
      expect(events[2].isTypedSemantic, isTrue);
    });
  });
}
