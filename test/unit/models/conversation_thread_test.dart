import 'package:chatboxapp/models/conversation_thread.dart';
import 'package:chatboxapp/models/message.dart';
import 'package:chatboxapp/widgets/conversation_view_v2.dart' as v2;
import 'package:flutter_test/flutter_test.dart';

Message _msg({
  required String id,
  required bool isUser,
  required DateTime timestamp,
}) {
  return Message(
    id: id,
    content: 'content:$id',
    isUser: isUser,
    timestamp: timestamp,
  );
}

void main() {
  group('ConversationThread / active-chain projection', () {
    test('fromLinearMessages produces a single chain', () {
      final messages = <Message>[
        _msg(
          id: 'u1',
          isUser: true,
          timestamp: DateTime(2024, 1, 1, 12, 0, 0),
        ),
        _msg(
          id: 'a1',
          isUser: false,
          timestamp: DateTime(2024, 1, 1, 12, 1, 0),
        ),
        _msg(
          id: 'u2',
          isUser: true,
          timestamp: DateTime(2024, 1, 1, 12, 2, 0),
        ),
      ];

      final thread = ConversationThread.fromLinearMessages('c1', messages);

      expect(thread.rootId, equals('u1'));
      expect(thread.activeLeafId, equals('u2'));

      expect(thread.nodes['u1']!.children, equals(['a1']));
      expect(thread.nodes['a1']!.children, equals(['u2']));
      expect(thread.nodes['u2']!.children, isEmpty);

      final chainIds = v2.buildActiveMessageChain(thread).map((m) => m.id).toList();
      expect(chainIds, equals(['u1', 'a1', 'u2']));
    });

    test('normalize selects last child by default', () {
      final user = _msg(
        id: 'u1',
        isUser: true,
        timestamp: DateTime(2024, 1, 1, 12, 0, 0),
      );
      final assistant1 = _msg(
        id: 'a1',
        isUser: false,
        timestamp: DateTime(2024, 1, 1, 12, 1, 0),
      );
      final assistant2 = _msg(
        id: 'a2',
        isUser: false,
        timestamp: DateTime(2024, 1, 1, 12, 2, 0),
      );

      final nodes = <String, ThreadNode>{
        'u1': ThreadNode(
          id: 'u1',
          parentId: null,
          message: user,
          children: const ['a1', 'a2'],
        ),
        'a1': ThreadNode(
          id: 'a1',
          parentId: 'u1',
          message: assistant1,
          children: const [],
        ),
        'a2': ThreadNode(
          id: 'a2',
          parentId: 'u1',
          message: assistant2,
          children: const [],
        ),
      };

      final thread = ConversationThread(
        conversationId: 'c1',
        nodes: nodes,
        rootId: 'u1',
      );

      thread.normalize();

      expect(thread.selectedChild['u1'], equals('a2'));
      expect(thread.activeLeafId, equals('a2'));

      final chainIds = v2.buildActiveMessageChain(thread).map((m) => m.id).toList();
      expect(chainIds, equals(['u1', 'a2']));
    });

    test('appendAssistantVariantUnderUser appends and selects new variant', () {
      final user = _msg(
        id: 'u1',
        isUser: true,
        timestamp: DateTime(2024, 1, 1, 12, 0, 0),
      );
      final assistant1 = _msg(
        id: 'a1',
        isUser: false,
        timestamp: DateTime(2024, 1, 1, 12, 1, 0),
      );

      final thread = ConversationThread.fromLinearMessages('c1', [user, assistant1]);

      final assistant2 = _msg(
        id: 'a2',
        isUser: false,
        timestamp: DateTime(2024, 1, 1, 12, 2, 0),
      );

      thread.appendAssistantVariantUnderUser(
        userId: 'u1',
        assistantMessage: assistant2,
      );

      expect(thread.nodes['u1']!.children, equals(['a1', 'a2']));
      expect(thread.selectedChild['u1'], equals('a2'));
      expect(thread.activeLeafId, equals('a2'));

      final chainIds = v2.buildActiveMessageChain(thread).map((m) => m.id).toList();
      expect(chainIds, equals(['u1', 'a2']));
    });

    test('appendAssistantVariantUnderUser throws if parent not user', () {
      final rootAssistant = _msg(
        id: 'a1',
        isUser: false,
        timestamp: DateTime(2024, 1, 1, 12, 0, 0),
      );
      final thread = ConversationThread.fromLinearMessages('c1', [rootAssistant]);

      expect(
        () => thread.appendAssistantVariantUnderUser(
          userId: 'a1',
          assistantMessage: _msg(
            id: 'a2',
            isUser: false,
            timestamp: DateTime(2024, 1, 1, 12, 1, 0),
          ),
        ),
        throwsA(isA<ArgumentError>()),
      );
    });
  });
}
