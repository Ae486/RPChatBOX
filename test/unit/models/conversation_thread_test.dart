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

/// Helper: build a branched thread for removeNode tests.
///
/// Structure:
///   u1 → a1 → u2 → a3
///       → a2
ConversationThread _buildBranchedThread() {
  final t = DateTime(2024, 1, 1, 12);
  final messages = <Message>[
    _msg(id: 'u1', isUser: true, timestamp: t),
    _msg(id: 'a1', isUser: false, timestamp: t.add(const Duration(minutes: 1))),
    _msg(id: 'u2', isUser: true, timestamp: t.add(const Duration(minutes: 2))),
    _msg(id: 'a3', isUser: false, timestamp: t.add(const Duration(minutes: 3))),
  ];
  final thread = ConversationThread.fromLinearMessages('c1', messages);

  // Add a2 as sibling of a1 under u1
  final a2 = _msg(id: 'a2', isUser: false, timestamp: t.add(const Duration(minutes: 4)));
  thread.appendAssistantVariantUnderUser(userId: 'u1', assistantMessage: a2);
  // Select a1 branch to keep u2→a3 on the active chain
  thread.selectedChild['u1'] = 'a1';
  thread.normalize();
  return thread;
}

List<String> _chainIds(ConversationThread thread) {
  return thread.buildActiveChain().map((m) => m.id).toList();
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

  group('ConversationThread / removeNode', () {
    test('removeNode on non-existent node is a no-op', () {
      final thread = _buildBranchedThread();
      final nodeCountBefore = thread.nodes.length;

      thread.removeNode('does-not-exist');

      expect(thread.nodes.length, equals(nodeCountBefore));
    });

    test('removeNode on empty thread is a no-op', () {
      final thread = ConversationThread(
        conversationId: 'c1',
        nodes: <String, ThreadNode>{},
        rootId: '',
      );

      thread.removeNode('anything');

      expect(thread.nodes, isEmpty);
      expect(thread.rootId, isEmpty);
    });

    test('delete sole node results in empty tree', () {
      final t = DateTime(2024, 1, 1, 12);
      final thread = ConversationThread.fromLinearMessages(
        'c1',
        [_msg(id: 'u1', isUser: true, timestamp: t)],
      );

      thread.removeNode('u1');

      expect(thread.nodes, isEmpty);
      expect(thread.rootId, isEmpty);
      expect(thread.activeLeafId, isEmpty);
      expect(thread.buildActiveChain(), isEmpty);
    });

    test('delete leaf node without siblings', () {
      // u1 → a1 → u2 → a3, also a2 under u1
      // Delete a3 (leaf, no siblings under u2)
      final thread = _buildBranchedThread();
      thread.removeNode('a3');

      expect(thread.nodes.containsKey('a3'), isFalse);
      expect(thread.nodes['u2']!.children, isEmpty);
      // Active chain: u1 → a1 → u2
      expect(_chainIds(thread), equals(['u1', 'a1', 'u2']));
    });

    test('delete leaf node with siblings keeps sibling', () {
      // u1 has children [a1, a2], a1 selected
      // Delete a2 (leaf with sibling a1)
      final thread = _buildBranchedThread();
      thread.removeNode('a2');

      expect(thread.nodes.containsKey('a2'), isFalse);
      expect(thread.nodes['u1']!.children, equals(['a1']));
      // Active chain unchanged: u1 → a1 → u2 → a3
      expect(_chainIds(thread), equals(['u1', 'a1', 'u2', 'a3']));
    });

    test('delete selected leaf with siblings switches to remaining', () {
      // u1 has children [a1, a2], select a2
      final thread = _buildBranchedThread();
      thread.selectedChild['u1'] = 'a2';
      thread.normalize();
      expect(thread.activeLeafId, equals('a2'));

      thread.removeNode('a2');

      expect(thread.nodes.containsKey('a2'), isFalse);
      // Should select remaining a1
      expect(thread.nodes['u1']!.children, equals(['a1']));
      expect(_chainIds(thread), equals(['u1', 'a1', 'u2', 'a3']));
    });

    test('delete middle node promotes children to parent', () {
      // u1 → a1 → u2 → a3
      // Delete a1 → u2 should be promoted to u1's child
      final thread = _buildBranchedThread();
      // Remove a2 first to simplify (avoid multi-child root scenario)
      thread.removeNode('a2');
      // Now: u1 → a1 → u2 → a3
      thread.removeNode('a1');

      expect(thread.nodes.containsKey('a1'), isFalse);
      expect(thread.nodes['u1']!.children, contains('u2'));
      expect(thread.nodes['u2']!.parentId, equals('u1'));
      expect(thread.nodes['u2']!.message.parentId, equals('u1'));
      // Active chain: u1 → u2 → a3
      expect(_chainIds(thread), equals(['u1', 'u2', 'a3']));
    });

    test('delete middle node with multiple children promotes all', () {
      // Build: u1 → a1 → u2a
      //                  → u2b
      final t = DateTime(2024, 1, 1, 12);
      final messages = [
        _msg(id: 'u1', isUser: true, timestamp: t),
        _msg(id: 'a1', isUser: false, timestamp: t.add(const Duration(minutes: 1))),
        _msg(id: 'u2a', isUser: true, timestamp: t.add(const Duration(minutes: 2))),
      ];
      final thread = ConversationThread.fromLinearMessages('c1', messages);

      // Add u2b under a1
      final u2b = _msg(id: 'u2b', isUser: true, timestamp: t.add(const Duration(minutes: 3)));
      u2b.parentId = 'a1';
      thread.appendToActiveLeaf(u2b);
      // Fix: manually set u2b as child of a1
      thread.selectedChild['a1'] = 'u2a';
      thread.normalize();

      // Delete a1 → u2a and u2b should be promoted to u1
      thread.removeNode('a1');

      expect(thread.nodes.containsKey('a1'), isFalse);
      expect(thread.nodes['u1']!.children, containsAll(['u2a']));
      // u2a's parent should be u1
      expect(thread.nodes['u2a']!.parentId, equals('u1'));
    });

    test('delete root with single child promotes child to root', () {
      final t = DateTime(2024, 1, 1, 12);
      final messages = [
        _msg(id: 'u1', isUser: true, timestamp: t),
        _msg(id: 'a1', isUser: false, timestamp: t.add(const Duration(minutes: 1))),
      ];
      final thread = ConversationThread.fromLinearMessages('c1', messages);

      thread.removeNode('u1');

      expect(thread.nodes.containsKey('u1'), isFalse);
      expect(thread.rootId, equals('a1'));
      expect(_chainIds(thread), equals(['a1']));
    });

    test('delete root with multiple children cascade-deletes non-selected', () {
      // u1 → a1 (selected, has u2 → a3)
      //     → a2
      final thread = _buildBranchedThread();
      expect(thread.selectedChild['u1'], equals('a1'));

      thread.removeNode('u1');

      // a2 should be cascade-deleted
      expect(thread.nodes.containsKey('u1'), isFalse);
      expect(thread.nodes.containsKey('a2'), isFalse);
      // a1 becomes new root
      expect(thread.rootId, equals('a1'));
      // Chain: a1 → u2 → a3
      expect(_chainIds(thread), equals(['a1', 'u2', 'a3']));
    });

    test('delete root with multiple children uses first child when none selected', () {
      final t = DateTime(2024, 1, 1, 12);
      final u1 = _msg(id: 'u1', isUser: true, timestamp: t);
      final a1 = _msg(id: 'a1', isUser: false, timestamp: t.add(const Duration(minutes: 1)));
      final a2 = _msg(id: 'a2', isUser: false, timestamp: t.add(const Duration(minutes: 2)));

      final thread = ConversationThread.fromLinearMessages('c1', [u1, a1]);
      thread.appendAssistantVariantUnderUser(userId: 'u1', assistantMessage: a2);

      // Clear selectedChild to test fallback
      thread.selectedChild.remove('u1');

      thread.removeNode('u1');

      // Should use first child (a1) as fallback
      expect(thread.rootId, equals('a1'));
      expect(thread.nodes.containsKey('a2'), isFalse);
    });

    test('delete preserves selectedChild for surviving branches', () {
      // u1 → a1 (selected) → u2 → a3
      //     → a2
      final thread = _buildBranchedThread();

      // Delete a3 (leaf)
      thread.removeNode('a3');

      // selectedChild for u1 should still be a1
      expect(thread.selectedChild['u1'], equals('a1'));
      // u2 is now a leaf, so no selectedChild for u2
      expect(thread.selectedChild.containsKey('u2'), isFalse);
    });

    test('delete middle node updates selectedChild when it was selected', () {
      // u1 → a1 (selected) → u2 → a3
      //     → a2
      final thread = _buildBranchedThread();

      // Delete a1 → u2 promoted to u1, a2 still sibling
      thread.removeNode('a1');

      expect(thread.nodes.containsKey('a1'), isFalse);
      // u2 should be promoted and selected (first promoted child)
      expect(thread.nodes['u1']!.children, containsAll(['u2', 'a2']));
      expect(thread.selectedChild['u1'], isNotNull);
    });

    test('active chain consistency after multiple deletions', () {
      final thread = _buildBranchedThread();
      // Initial chain: u1 → a1 → u2 → a3

      // Delete a3
      thread.removeNode('a3');
      expect(_chainIds(thread), equals(['u1', 'a1', 'u2']));

      // Delete u2
      thread.removeNode('u2');
      expect(_chainIds(thread), equals(['u1', 'a1']));

      // Delete a1 (has sibling a2)
      thread.removeNode('a1');
      expect(thread.nodes.containsKey('a1'), isFalse);
      // Only a2 remains under u1
      expect(_chainIds(thread), equals(['u1', 'a2']));
    });

    test('normalize repairs dangling activeLeafId after deletion', () {
      final thread = _buildBranchedThread();

      // Manually corrupt activeLeafId
      thread.activeLeafId = 'nonexistent';
      thread.normalize();

      // Should recover to a valid leaf
      expect(thread.nodes.containsKey(thread.activeLeafId), isTrue);
      expect(thread.buildActiveChain(), isNotEmpty);
    });

    test('normalize repairs dangling rootId', () {
      final thread = _buildBranchedThread();

      // Manually corrupt rootId
      thread.rootId = 'nonexistent';
      thread.normalize();

      // Should recover to first available node
      expect(thread.nodes.containsKey(thread.rootId), isTrue);
    });

    test('normalize cleans up invalid selectedChild entries', () {
      final thread = _buildBranchedThread();

      // Add invalid selectedChild entries
      thread.selectedChild['nonexistent_parent'] = 'a1';
      thread.selectedChild['u1'] = 'nonexistent_child';

      thread.normalize();

      expect(thread.selectedChild.containsKey('nonexistent_parent'), isFalse);
      // u1's selectedChild should be repaired to a valid child
      final selectedForU1 = thread.selectedChild['u1'];
      expect(selectedForU1, isNotNull);
      expect(thread.nodes['u1']!.children, contains(selectedForU1));
    });

    test('JSON round-trip preserves tree structure after deletion', () {
      final thread = _buildBranchedThread();
      thread.removeNode('a3');

      final json = thread.toJson();
      // Build lookup from existing nodes for compact format
      final messageMap = <String, Message>{};
      for (final node in thread.nodes.values) {
        messageMap[node.message.id] = node.message;
      }
      final restored = ConversationThread.fromJson(
        json,
        messageLookup: (id) => messageMap[id],
      );

      expect(restored.rootId, equals(thread.rootId));
      expect(restored.activeLeafId, equals(thread.activeLeafId));
      expect(restored.nodes.length, equals(thread.nodes.length));
      expect(_chainIds(restored), equals(_chainIds(thread)));
    });
  });

  group('ConversationThread / soft limits', () {
    test('calculateDepth returns 0 for empty tree', () {
      final thread = ConversationThread(
        conversationId: 'c1',
        nodes: <String, ThreadNode>{},
        rootId: '',
      );

      expect(thread.calculateDepth(), equals(0));
    });

    test('calculateDepth returns 1 for single node', () {
      final t = DateTime(2024, 1, 1, 12);
      final thread = ConversationThread.fromLinearMessages(
        'c1',
        [_msg(id: 'u1', isUser: true, timestamp: t)],
      );

      expect(thread.calculateDepth(), equals(1));
    });

    test('calculateDepth returns correct depth for linear chain', () {
      final t = DateTime(2024, 1, 1, 12);
      final messages = [
        _msg(id: 'u1', isUser: true, timestamp: t),
        _msg(id: 'a1', isUser: false, timestamp: t.add(const Duration(minutes: 1))),
        _msg(id: 'u2', isUser: true, timestamp: t.add(const Duration(minutes: 2))),
        _msg(id: 'a2', isUser: false, timestamp: t.add(const Duration(minutes: 3))),
      ];
      final thread = ConversationThread.fromLinearMessages('c1', messages);

      expect(thread.calculateDepth(), equals(4));
    });

    test('calculateDepth returns max depth for branched tree', () {
      // u1 → a1 (depth 2) → u2 (depth 3) → a3 (depth 4)
      //     → a2 (depth 2)
      final thread = _buildBranchedThread();

      expect(thread.calculateDepth(), equals(4));
    });

    test('calculateMaxChildren returns 0 for empty tree', () {
      final thread = ConversationThread(
        conversationId: 'c1',
        nodes: <String, ThreadNode>{},
        rootId: '',
      );

      expect(thread.calculateMaxChildren(), equals(0));
    });

    test('calculateMaxChildren returns correct value for branched tree', () {
      // u1 has 2 children (a1, a2)
      final thread = _buildBranchedThread();

      expect(thread.calculateMaxChildren(), equals(2));
    });

    test('checkLimits returns status with no exceeded limits for small tree', () {
      final thread = _buildBranchedThread();

      final status = thread.checkLimits();

      expect(status.nodeCount, equals(5));
      expect(status.depth, equals(4));
      expect(status.maxChildren, equals(2));
      expect(status.nodeCountExceeded, isFalse);
      expect(status.depthExceeded, isFalse);
      expect(status.childrenExceeded, isFalse);
      expect(status.anyExceeded, isFalse);
    });

    test('ThreadLimits constants are accessible', () {
      expect(ThreadLimits.maxNodes, isPositive);
      expect(ThreadLimits.maxDepth, isPositive);
      expect(ThreadLimits.maxChildrenPerNode, isPositive);
    });
  });

  group('ConversationThread / compact serialization', () {
    test('toJson outputs messageId instead of full message', () {
      final t = DateTime(2024, 1, 1, 12);
      final thread = ConversationThread.fromLinearMessages('c1', [
        _msg(id: 'u1', isUser: true, timestamp: t),
        _msg(id: 'a1', isUser: false, timestamp: t.add(const Duration(minutes: 1))),
      ]);

      final json = thread.toJson();
      final nodesJson = json['nodes'] as Map<String, dynamic>;

      // Check that nodes have messageId, not full message
      final u1Node = nodesJson['u1'] as Map<String, dynamic>;
      expect(u1Node['messageId'], equals('u1'));
      expect(u1Node.containsKey('message'), isFalse);

      final a1Node = nodesJson['a1'] as Map<String, dynamic>;
      expect(a1Node['messageId'], equals('a1'));
      expect(a1Node.containsKey('message'), isFalse);
    });

    test('fromJson with messageLookup restores full messages', () {
      final t = DateTime(2024, 1, 1, 12);
      final u1 = _msg(id: 'u1', isUser: true, timestamp: t);
      final a1 = _msg(id: 'a1', isUser: false, timestamp: t.add(const Duration(minutes: 1)));

      final thread = ConversationThread.fromLinearMessages('c1', [u1, a1]);
      final json = thread.toJson();

      // Restore with lookup
      final messageMap = {'u1': u1, 'a1': a1};
      final restored = ConversationThread.fromJson(
        json,
        messageLookup: (id) => messageMap[id],
      );

      expect(restored.nodes['u1']!.message.content, equals('content:u1'));
      expect(restored.nodes['a1']!.message.content, equals('content:a1'));
      expect(restored.nodes['u1']!.message.isUser, isTrue);
      expect(restored.nodes['a1']!.message.isUser, isFalse);
    });

    test('fromJson without messageLookup falls back to legacy format', () {
      // Simulate legacy JSON with inline message
      final legacyJson = {
        'conversationId': 'c1',
        'nodes': {
          'u1': {
            'id': 'u1',
            'parentId': null,
            'message': {
              'id': 'u1',
              'content': 'Hello',
              'isUser': true,
              'timestamp': '2024-01-01T12:00:00.000',
            },
            'children': ['a1'],
          },
          'a1': {
            'id': 'a1',
            'parentId': 'u1',
            'message': {
              'id': 'a1',
              'content': 'Hi there',
              'isUser': false,
              'timestamp': '2024-01-01T12:01:00.000',
            },
            'children': <String>[],
          },
        },
        'rootId': 'u1',
        'selectedChild': <String, String>{},
        'activeLeafId': 'a1',
      };

      // No messageLookup - should use inline message
      final restored = ConversationThread.fromJson(legacyJson);

      expect(restored.nodes['u1']!.message.content, equals('Hello'));
      expect(restored.nodes['a1']!.message.content, equals('Hi there'));
    });

    test('fromJson creates placeholder when message not found', () {
      // Compact JSON without lookup and without inline message
      final compactJson = {
        'conversationId': 'c1',
        'nodes': {
          'u1': {
            'id': 'u1',
            'parentId': null,
            'messageId': 'u1',
            'children': <String>[],
          },
        },
        'rootId': 'u1',
        'selectedChild': <String, String>{},
        'activeLeafId': 'u1',
      };

      // No lookup provided - should create placeholder
      final restored = ConversationThread.fromJson(compactJson);

      expect(restored.nodes['u1']!.message.id, equals('u1'));
      expect(restored.nodes['u1']!.message.content, equals(''));
    });

    test('compact format significantly reduces JSON size', () {
      final t = DateTime(2024, 1, 1, 12);
      final messages = List.generate(10, (i) {
        final isUser = i.isEven;
        return Message(
          id: 'msg_$i',
          content: 'A' * 500, // 500 chars per message
          isUser: isUser,
          timestamp: t.add(Duration(minutes: i)),
        );
      });

      final thread = ConversationThread.fromLinearMessages('c1', messages);
      final compactJson = thread.toJson();

      // Build legacy format for comparison
      final legacyNodes = <String, dynamic>{};
      for (final node in thread.nodes.values) {
        legacyNodes[node.id] = {
          'id': node.id,
          'parentId': node.parentId,
          'message': node.message.toJson(), // Full message
          'children': node.children,
        };
      }

      final compactSize = compactJson.toString().length;
      final legacySize = legacyNodes.toString().length;

      // Compact should be at least 50% smaller
      expect(compactSize, lessThan(legacySize * 0.5));
    });
  });
}
