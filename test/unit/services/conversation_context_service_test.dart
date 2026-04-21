import 'package:chatboxapp/models/conversation.dart';
import 'package:chatboxapp/models/conversation_settings.dart';
import 'package:chatboxapp/models/message.dart';
import 'package:chatboxapp/services/conversation_context_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('ConversationContextService', () {
    const service = ConversationContextService();

    Message userMessage(String id, String content, {int? inputTokens}) {
      return Message(
        id: id,
        content: content,
        isUser: true,
        timestamp: DateTime(2026, 4, 10),
        inputTokens: inputTokens,
      );
    }

    Message assistantMessage(String id, String content, {int? outputTokens}) {
      return Message(
        id: id,
        content: content,
        isUser: false,
        timestamp: DateTime(2026, 4, 10),
        outputTokens: outputTokens,
      );
    }

    test('builds current window from latest context length', () {
      final conversation = Conversation(
        id: 'conv-1',
        title: 'Test',
        messages: [
          userMessage('u1', 'hello', inputTokens: 3),
          assistantMessage('a1', 'world', outputTokens: 4),
          userMessage('u2', 'follow up', inputTokens: 5),
          assistantMessage('a2', 'answer', outputTokens: 6),
        ],
      );
      final settings = ConversationSettings(
        conversationId: conversation.id,
        contextLength: 2,
      );

      final window = service.buildContextWindow(
        conversation: conversation,
        settings: settings,
      );

      expect(window.windowMessages.map((message) => message.id), ['u2', 'a2']);
      expect(window.windowTokens, 11);
      expect(window.summaryApplied, isFalse);
      expect(window.totalContextTokens, 11);
    });

    test('applies compact cutoff and includes summary tokens separately', () {
      final conversation = Conversation(
        id: 'conv-2',
        title: 'Test',
        summary: '{"intent":["continue"]}',
        summaryRangeStartId: 'u1',
        summaryRangeEndId: 'a1',
        messages: [
          userMessage('u1', 'old question', inputTokens: 9),
          assistantMessage('a1', 'old answer', outputTokens: 10),
          userMessage('u2', 'new question', inputTokens: 7),
          assistantMessage('a2', 'new answer', outputTokens: 8),
        ],
      );
      final settings = ConversationSettings(
        conversationId: conversation.id,
        contextLength: 10,
      );

      final window = service.buildContextWindow(
        conversation: conversation,
        settings: settings,
      );

      expect(window.summaryApplied, isTrue);
      expect(window.windowMessages.map((message) => message.id), ['u2', 'a2']);
      expect(window.windowTokens, 15);
      expect(window.summaryTokens, greaterThan(0));
      expect(
        window.totalContextTokens,
        window.windowTokens + window.summaryTokens,
      );
    });
  });
}
