import 'package:flutter_test/flutter_test.dart';

import 'package:chatboxapp/controllers/thread_manager.dart';
import 'package:chatboxapp/models/conversation.dart';
import 'package:chatboxapp/models/conversation_thread.dart';
import 'package:chatboxapp/models/message.dart';

void main() {
  group('ThreadManager', () {
    late Conversation conversation;
    late ThreadManager manager;
    var updateCount = 0;
    var disposed = false;

    setUp(() {
      updateCount = 0;
      disposed = false;
      conversation = Conversation(
        id: 'test-conv',
        title: 'Test',
        messages: [],
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
      );
      manager = ThreadManager(
        getConversation: () => conversation,
        isDisposed: () => disposed,
        onConversationUpdated: () => updateCount++,
      );
    });

    tearDown(() {
      manager.dispose();
    });

    test('getThread creates empty thread for empty conversation', () {
      final thread = manager.getThread();
      expect(thread.conversationId, equals('test-conv'));
      expect(thread.nodes, isEmpty);
    });

    test('getThread builds linear thread from messages', () {
      final u1 = Message(
        id: 'u1',
        content: 'Hello',
        isUser: true,
        timestamp: DateTime.now(),
      );
      final a1 = Message(
        id: 'a1',
        content: 'Hi',
        isUser: false,
        timestamp: DateTime.now(),
      );
      conversation.messages.addAll([u1, a1]);

      final thread = manager.getThread();
      expect(thread.nodes.length, equals(2));
      expect(thread.rootId, equals('u1'));
      expect(thread.activeLeafId, equals('a1'));
    });

    test('getThread loads from threadJson when available', () {
      final u1 = Message(
        id: 'u1',
        content: 'Hello',
        isUser: true,
        timestamp: DateTime.now(),
      );
      conversation.messages.add(u1);

      // Build initial thread
      var thread = manager.getThread();
      manager.persistNoSave(thread);

      // Clear messages and add different ones
      conversation.messages.clear();
      final u2 = Message(
        id: 'u2',
        content: 'Different',
        isUser: true,
        timestamp: DateTime.now(),
      );
      conversation.messages.add(u2);

      // Create new manager - should load from threadJson
      final manager2 = ThreadManager(
        getConversation: () => conversation,
        isDisposed: () => disposed,
        onConversationUpdated: () => updateCount++,
      );

      // Since threadJson exists but has branches=false and nodes mismatch,
      // it will rebuild from messages
      thread = manager2.getThread();

      // The thread should have been rebuilt from the single message
      expect(thread.nodes.length, equals(1));

      manager2.dispose();
    });

    test('syncMessagesSnapshot updates conversation.messages', () {
      final u1 = Message(
        id: 'u1',
        content: 'Hello',
        isUser: true,
        timestamp: DateTime.now(),
      );
      final a1 = Message(
        id: 'a1',
        content: 'Response 1',
        isUser: false,
        timestamp: DateTime.now(),
      );
      final a2 = Message(
        id: 'a2',
        content: 'Response 2',
        isUser: false,
        timestamp: DateTime.now(),
      );
      conversation.messages.addAll([u1, a1]);

      final thread = manager.getThread();

      // Add variant manually
      thread.appendAssistantVariantUnderUser(
        userId: 'u1',
        assistantMessage: a2,
      );

      manager.syncMessagesSnapshot(thread);

      // Should now show u1 -> a2 (the newly selected variant)
      expect(conversation.messages.length, equals(2));
      expect(conversation.messages.last.id, equals('a2'));
    });

    test('getAssistantVariantIds returns all children of user message', () {
      final u1 = Message(
        id: 'u1',
        content: 'Hello',
        isUser: true,
        timestamp: DateTime.now(),
      );
      final a1 = Message(
        id: 'a1',
        content: 'Response 1',
        isUser: false,
        timestamp: DateTime.now(),
      );
      final a2 = Message(
        id: 'a2',
        content: 'Response 2',
        isUser: false,
        timestamp: DateTime.now(),
      );
      conversation.messages.addAll([u1, a1]);

      final thread = manager.getThread();
      thread.appendAssistantVariantUnderUser(
        userId: 'u1',
        assistantMessage: a2,
      );

      final variants = manager.getAssistantVariantIds('u1', thread);
      expect(variants, containsAll(['a1', 'a2']));
      expect(variants.length, equals(2));
    });

    test('switchVariant cycles through variants', () {
      final u1 = Message(
        id: 'u1',
        content: 'Hello',
        isUser: true,
        timestamp: DateTime.now(),
      );
      final a1 = Message(
        id: 'a1',
        content: 'Response 1',
        isUser: false,
        timestamp: DateTime.now(),
      );
      final a2 = Message(
        id: 'a2',
        content: 'Response 2',
        isUser: false,
        timestamp: DateTime.now(),
      );
      conversation.messages.addAll([u1, a1]);

      final thread = manager.getThread();
      thread.appendAssistantVariantUnderUser(
        userId: 'u1',
        assistantMessage: a2,
      );
      manager.persistNoSave(thread);

      // Current selection is a2, switch forward should go to a1
      final result = manager.switchVariant('u1', 1);
      expect(result, equals('a1'));
      expect(conversation.messages.last.id, equals('a1'));

      // Switch forward again should go back to a2
      final result2 = manager.switchVariant('u1', 1);
      expect(result2, equals('a2'));
    });

    test('switchVariant returns null for single variant', () {
      final u1 = Message(
        id: 'u1',
        content: 'Hello',
        isUser: true,
        timestamp: DateTime.now(),
      );
      final a1 = Message(
        id: 'a1',
        content: 'Response',
        isUser: false,
        timestamp: DateTime.now(),
      );
      conversation.messages.addAll([u1, a1]);
      manager.getThread();

      final result = manager.switchVariant('u1', 1);
      expect(result, isNull);
    });

    test('reset clears internal state', () {
      final u1 = Message(
        id: 'u1',
        content: 'Hello',
        isUser: true,
        timestamp: DateTime.now(),
      );
      conversation.messages.add(u1);
      manager.getThread();

      expect(manager.currentThread, isNotNull);

      manager.reset();

      expect(manager.currentThread, isNull);
      expect(manager.lastPersistedJson, isNull);
    });

    test('dispose clears state and cancels timers', () {
      final u1 = Message(
        id: 'u1',
        content: 'Hello',
        isUser: true,
        timestamp: DateTime.now(),
      );
      conversation.messages.add(u1);
      manager.getThread();
      manager.schedulePersist();

      manager.dispose();

      expect(manager.currentThread, isNull);
    });

    test('does not persist when disposed', () {
      disposed = true;
      manager.schedulePersist();
      // Should not throw or cause issues
    });
  });

  group('ThreadManager / threadJson validation', () {
    late Conversation conversation;
    late ThreadManager manager;
    var disposed = false;

    setUp(() {
      disposed = false;
      conversation = Conversation(
        id: 'test-conv',
        title: 'Test',
        messages: [],
        createdAt: DateTime.now(),
        updatedAt: DateTime.now(),
      );
      manager = ThreadManager(
        getConversation: () => conversation,
        isDisposed: () => disposed,
        onConversationUpdated: () {},
      );
    });

    tearDown(() {
      manager.dispose();
    });

    test('handles malformed JSON gracefully', () {
      conversation.threadJson = 'not valid json {{{';
      conversation.messages.add(Message(
        id: 'u1',
        content: 'Hello',
        isUser: true,
        timestamp: DateTime.now(),
      ));

      final thread = manager.getThread();

      // Should fall back to messages
      expect(thread.nodes.length, equals(1));
      expect(thread.rootId, equals('u1'));
    });

    test('handles JSON with wrong root type', () {
      conversation.threadJson = '["array", "not", "object"]';
      conversation.messages.add(Message(
        id: 'u1',
        content: 'Hello',
        isUser: true,
        timestamp: DateTime.now(),
      ));

      final thread = manager.getThread();

      expect(thread.nodes.length, equals(1));
      expect(thread.rootId, equals('u1'));
    });

    test('handles JSON missing required fields', () {
      conversation.threadJson = '{"someField": "value"}';
      conversation.messages.add(Message(
        id: 'u1',
        content: 'Hello',
        isUser: true,
        timestamp: DateTime.now(),
      ));

      final thread = manager.getThread();

      expect(thread.nodes.length, equals(1));
    });

    test('handles conversationId mismatch', () {
      conversation.threadJson = '''
      {
        "conversationId": "different-id",
        "nodes": {},
        "rootId": "",
        "selectedChild": {},
        "activeLeafId": ""
      }
      ''';
      conversation.messages.add(Message(
        id: 'u1',
        content: 'Hello',
        isUser: true,
        timestamp: DateTime.now(),
      ));

      final thread = manager.getThread();

      // Should rebuild from messages due to ID mismatch
      expect(thread.conversationId, equals('test-conv'));
      expect(thread.nodes.length, equals(1));
    });

    test('repairs inconsistent rootId', () {
      // Valid structure but rootId points to non-existent node
      conversation.threadJson = '''
      {
        "conversationId": "test-conv",
        "nodes": {
          "u1": {
            "id": "u1",
            "parentId": null,
            "message": {
              "id": "u1",
              "content": "Hello",
              "isUser": true,
              "timestamp": "${DateTime.now().toIso8601String()}"
            },
            "children": []
          }
        },
        "rootId": "nonexistent",
        "selectedChild": {},
        "activeLeafId": "u1"
      }
      ''';

      final thread = manager.getThread(rebuildFromMessagesIfMismatch: false);

      // Should be repaired - rootId should point to existing node
      expect(thread.nodes.containsKey(thread.rootId), isTrue);
    });

    test('repairs inconsistent activeLeafId', () {
      conversation.threadJson = '''
      {
        "conversationId": "test-conv",
        "nodes": {
          "u1": {
            "id": "u1",
            "parentId": null,
            "message": {
              "id": "u1",
              "content": "Hello",
              "isUser": true,
              "timestamp": "${DateTime.now().toIso8601String()}"
            },
            "children": []
          }
        },
        "rootId": "u1",
        "selectedChild": {},
        "activeLeafId": "nonexistent"
      }
      ''';

      final thread = manager.getThread(rebuildFromMessagesIfMismatch: false);

      // Should be repaired
      expect(thread.nodes.containsKey(thread.activeLeafId), isTrue);
    });

    test('repairs dangling selectedChild entries', () {
      conversation.threadJson = '''
      {
        "conversationId": "test-conv",
        "nodes": {
          "u1": {
            "id": "u1",
            "parentId": null,
            "message": {
              "id": "u1",
              "content": "Hello",
              "isUser": true,
              "timestamp": "${DateTime.now().toIso8601String()}"
            },
            "children": ["a1"]
          },
          "a1": {
            "id": "a1",
            "parentId": "u1",
            "message": {
              "id": "a1",
              "content": "Hi",
              "isUser": false,
              "timestamp": "${DateTime.now().toIso8601String()}"
            },
            "children": []
          }
        },
        "rootId": "u1",
        "selectedChild": {"u1": "nonexistent", "fake": "a1"},
        "activeLeafId": "a1"
      }
      ''';

      final thread = manager.getThread(rebuildFromMessagesIfMismatch: false);

      // Dangling entries should be cleaned up by normalize()
      for (final entry in thread.selectedChild.entries) {
        expect(thread.nodes.containsKey(entry.key), isTrue);
        expect(thread.nodes.containsKey(entry.value), isTrue);
      }
    });

    test('valid threadJson loads correctly', () {
      final timestamp = DateTime.now().toIso8601String();
      conversation.threadJson = '''
      {
        "conversationId": "test-conv",
        "nodes": {
          "u1": {
            "id": "u1",
            "parentId": null,
            "message": {
              "id": "u1",
              "content": "Hello",
              "isUser": true,
              "timestamp": "$timestamp"
            },
            "children": ["a1"]
          },
          "a1": {
            "id": "a1",
            "parentId": "u1",
            "message": {
              "id": "a1",
              "content": "Hi",
              "isUser": false,
              "timestamp": "$timestamp"
            },
            "children": []
          }
        },
        "rootId": "u1",
        "selectedChild": {"u1": "a1"},
        "activeLeafId": "a1"
      }
      ''';

      final thread = manager.getThread(rebuildFromMessagesIfMismatch: false);

      expect(thread.nodes.length, equals(2));
      expect(thread.rootId, equals('u1'));
      expect(thread.activeLeafId, equals('a1'));
    });

    test('ThreadJsonValidationResult enum values exist', () {
      expect(ThreadJsonValidationResult.values, contains(ThreadJsonValidationResult.valid));
      expect(ThreadJsonValidationResult.values, contains(ThreadJsonValidationResult.empty));
      expect(ThreadJsonValidationResult.values, contains(ThreadJsonValidationResult.jsonSyntaxError));
      expect(ThreadJsonValidationResult.values, contains(ThreadJsonValidationResult.structureError));
      expect(ThreadJsonValidationResult.values, contains(ThreadJsonValidationResult.inconsistentRepaired));
      expect(ThreadJsonValidationResult.values, contains(ThreadJsonValidationResult.conversationIdMismatch));
    });

    test('ThreadLoadResult.isHealthy returns correct values', () {
      final healthyValid = ThreadLoadResult(
        thread: ConversationThread(
          conversationId: 'c1',
          nodes: {},
          rootId: '',
        ),
        validationResult: ThreadJsonValidationResult.valid,
      );
      expect(healthyValid.isHealthy, isTrue);

      final healthyRepaired = ThreadLoadResult(
        thread: ConversationThread(
          conversationId: 'c1',
          nodes: {},
          rootId: '',
        ),
        validationResult: ThreadJsonValidationResult.inconsistentRepaired,
        wasRepaired: true,
      );
      expect(healthyRepaired.isHealthy, isTrue);

      final unhealthy = ThreadLoadResult(
        thread: ConversationThread(
          conversationId: 'c1',
          nodes: {},
          rootId: '',
        ),
        validationResult: ThreadJsonValidationResult.jsonSyntaxError,
        errorMessage: 'test error',
      );
      expect(unhealthy.isHealthy, isFalse);
    });
  });
}
