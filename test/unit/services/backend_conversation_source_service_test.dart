import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:chatboxapp/models/attached_file.dart';
import 'package:chatboxapp/models/conversation_thread.dart';
import 'package:chatboxapp/models/message.dart';
import 'package:chatboxapp/services/backend_conversation_source_service.dart';
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('BackendConversationSourceProjection.checkpointIdForExactMessages', () {
    test('returns empty checkpoint id for empty prefix', () {
      final projection = BackendConversationSourceProjection(
        current: _snapshot(
          checkpointId: 'cp-current',
          messages: [_message('user-1', 'hello')],
        ),
        checkpoints: const [],
        thread: ConversationThread.fromLinearMessages('conv-1', const []),
        branchCheckpointByChildMessageId: const {},
        messageIndexById: const {},
      );

      expect(projection.checkpointIdForExactMessages(const []), '');
    });

    test('matches exact revision instead of same message id only', () {
      final oldUser = _message('user-1', 'old prompt');
      final newUser = _message(
        'user-1',
        'new prompt',
        editedAt: DateTime.parse('2026-04-10T00:05:00Z'),
      );
      final projection = BackendConversationSourceProjection(
        current: _snapshot(
          checkpointId: 'cp-current',
          messages: [newUser, _message('assistant-1', 'reply')],
        ),
        checkpoints: [
          _checkpoint(checkpointId: 'cp-old-user', messages: [oldUser]),
          _checkpoint(checkpointId: 'cp-new-user', messages: [newUser]),
        ],
        thread: ConversationThread.fromLinearMessages('conv-1', [newUser]),
        branchCheckpointByChildMessageId: const {},
        messageIndexById: const {},
      );

      expect(projection.checkpointIdForExactMessages([newUser]), 'cp-new-user');
    });

    test(
      'falls back to current snapshot when history is not refreshed yet',
      () {
        final user = _message(
          'user-1',
          'hello',
          attachments: [
            AttachedFileSnapshot(
              id: 'file-1',
              name: 'note.txt',
              path: '/tmp/note.txt',
              mimeType: 'text/plain',
              type: FileType.document,
            ),
          ],
        );
        final assistant = _message(
          'assistant-1',
          'world',
          outputTokens: 12,
          modelName: 'test-model',
        );
        final projection = BackendConversationSourceProjection(
          current: _snapshot(
            checkpointId: 'cp-current',
            messages: [user, assistant],
          ),
          checkpoints: [
            _checkpoint(checkpointId: 'cp-user', messages: [user]),
          ],
          thread: ConversationThread.fromLinearMessages('conv-1', [
            user,
            assistant,
          ]),
          branchCheckpointByChildMessageId: const {},
          messageIndexById: const {},
        );

        expect(
          projection.checkpointIdForExactMessages([user, assistant]),
          'cp-current',
        );
      },
    );
  });

  group('BackendConversationSourceService.deleteMessage', () {
    test(
      'throws a dedicated exception when legacy backend returns 405',
      () async {
        final dio = Dio(
          BaseOptions(validateStatus: (status) => status != null),
        );
        dio.httpClientAdapter = _StaticResponseAdapter(
          statusCode: HttpStatus.methodNotAllowed,
          jsonBody: const {'error': 'method not allowed'},
        );
        final service = BackendConversationSourceService(
          dio: dio,
          baseUrl: 'http://localhost:8765',
        );

        await expectLater(
          service.deleteMessage(
            conversationId: 'conv-1',
            messageId: 'assistant-1',
          ),
          throwsA(
            isA<BackendConversationSourceDeleteUnsupportedException>().having(
              (error) => error.statusCode,
              'statusCode',
              HttpStatus.methodNotAllowed,
            ),
          ),
        );
      },
    );
  });
}

BackendConversationSourceSnapshot _snapshot({
  required String checkpointId,
  required List<Message> messages,
}) {
  return BackendConversationSourceSnapshot(
    conversationId: 'conv-1',
    checkpointId: checkpointId,
    latestCheckpointId: checkpointId,
    selectedCheckpointId: checkpointId,
    messages: messages,
  );
}

BackendConversationSourceCheckpointDetail _checkpoint({
  required String checkpointId,
  required List<Message> messages,
}) {
  return BackendConversationSourceCheckpointDetail(
    checkpointId: checkpointId,
    parentCheckpointId: null,
    messages: messages,
  );
}

Message _message(
  String id,
  String content, {
  bool isUser = true,
  DateTime? editedAt,
  int? inputTokens,
  int? outputTokens,
  String? modelName,
  String? providerName,
  List<AttachedFileSnapshot>? attachments,
}) {
  return Message(
    id: id,
    content: content,
    isUser: isUser,
    timestamp: DateTime.parse('2026-04-10T00:00:00Z').toLocal(),
    editedAt: editedAt?.toLocal(),
    inputTokens: inputTokens,
    outputTokens: outputTokens,
    modelName: modelName,
    providerName: providerName,
    attachedFiles: attachments,
  );
}

class _StaticResponseAdapter implements HttpClientAdapter {
  final int statusCode;
  final Map<String, dynamic> jsonBody;

  _StaticResponseAdapter({required this.statusCode, required this.jsonBody});

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    return ResponseBody.fromString(
      jsonEncode(jsonBody),
      statusCode,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}
