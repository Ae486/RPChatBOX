import 'package:chatboxapp/models/attached_file.dart';
import 'package:chatboxapp/models/conversation.dart';
import 'package:chatboxapp/models/message.dart';
import 'package:chatboxapp/services/backend_conversation_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('BackendConversationSummary', () {
    test('toConversation creates a mutable message list', () {
      final summary = BackendConversationSummary(
        id: 'conv-1',
        title: 'Conversation',
        systemPrompt: null,
        roleId: null,
        roleType: null,
        latestCheckpointId: 'checkpoint-latest',
        selectedCheckpointId: 'checkpoint-selected',
        isPinned: false,
        isArchived: false,
        createdAt: DateTime.parse('2026-04-09T00:00:00Z'),
        updatedAt: DateTime.parse('2026-04-09T00:00:00Z'),
        lastActivityAt: DateTime.parse('2026-04-09T00:00:00Z'),
      );

      final conversation = summary.toConversation();

      expect(conversation.messages, isEmpty);
      expect(conversation.activeLeafId, isNull);

      conversation.messages.add(
        Message(
          id: 'msg-1',
          content: 'hello',
          isUser: true,
          timestamp: DateTime.now(),
        ),
      );

      expect(conversation.messages, hasLength(1));
    });
  });

  group('BackendConversationCompactSummary', () {
    test('applyToConversation hydrates compact summary fields', () {
      final conversation = Conversation(id: 'conv-1', title: 'Conversation');
      final summary = BackendConversationCompactSummary(
        conversationId: 'conv-1',
        summary: '{"intent":["continue"]}',
        rangeStartMessageId: 'msg-10',
        rangeEndMessageId: 'msg-19',
        createdAt: DateTime.parse('2026-04-10T00:00:00Z'),
        updatedAt: DateTime.parse('2026-04-10T01:00:00Z'),
      );

      summary.applyToConversation(conversation);

      expect(conversation.summary, '{"intent":["continue"]}');
      expect(conversation.summaryRangeStartId, 'msg-10');
      expect(conversation.summaryRangeEndId, 'msg-19');
      expect(conversation.summaryUpdatedAt, isNotNull);
    });
  });

  group('BackendConversationAttachmentSummary', () {
    test('toAttachedFile preserves backend-owned attachment metadata', () {
      final attachment = BackendConversationAttachmentSummary(
        id: 'file-1',
        conversationId: 'conv-1',
        storageKey: 'attachments/conv-1/file-1_doc.txt',
        localPath: r'C:\tmp\doc.txt',
        originalName: 'doc.txt',
        mimeType: 'text/plain',
        sizeBytes: 128,
        kind: 'document',
        metadata: const {'source': 'backend'},
        createdAt: DateTime.parse('2026-04-10T00:00:00Z'),
      );

      final file = attachment.toAttachedFile();
      final snapshot = attachment.toAttachedFileSnapshot();

      expect(file.type, FileType.document);
      expect(file.path, r'C:\tmp\doc.txt');
      expect(file.metadata['storageKey'], 'attachments/conv-1/file-1_doc.txt');
      expect(snapshot.name, 'doc.txt');
      expect(snapshot.type, FileType.document);
    });
  });
}
