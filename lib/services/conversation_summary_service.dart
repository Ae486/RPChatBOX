/// INPUT: Conversation + ConversationSettings + AIProvider
/// OUTPUT: Summary string + range metadata (no UI)
/// POS: Services / Base Chat / Summary
import 'dart:convert';

import '../adapters/ai_provider.dart' as ai;
import '../models/conversation.dart';
import '../models/conversation_settings.dart';
import '../models/conversation_thread.dart';
import '../models/message.dart';
import '../models/model_config.dart';

class ConversationSummaryContext {
  final List<Message> messages;
  final String? rangeStartId;
  final String? rangeEndId;

  const ConversationSummaryContext({
    required this.messages,
    required this.rangeStartId,
    required this.rangeEndId,
  });
}

class ConversationSummaryResult {
  final String summary;
  final String? rangeStartId;
  final String? rangeEndId;
  final DateTime updatedAt;

  const ConversationSummaryResult({
    required this.summary,
    required this.rangeStartId,
    required this.rangeEndId,
    required this.updatedAt,
  });
}

class ConversationSummaryService {
  static const String _systemPrompt =
      'You are a structured summarizer. Output JSON only. '
      'Summarize the conversation for future continuation. '
      'Focus on facts, decisions, constraints, and open items. Do not invent details.';

  static const String _schemaHint = '''
Output JSON with this exact structure:
{
  "intent": ["main goals or objectives discussed"],
  "decisions": ["decisions made during conversation"],
  "artifacts": ["code snippets, file paths, or concrete outputs mentioned"],
  "next_steps": ["planned or suggested actions"],
  "open_questions": ["unresolved questions or uncertainties"],
  "constraints": ["limitations, requirements, or rules established"]
}
''';

  ConversationSummaryContext buildSummaryContext({
    required Conversation conversation,
    required ConversationSettings settings,
  }) {
    final thread = _loadThread(conversation);
    final history = thread?.buildActiveChain() ?? conversation.messages;

    final contextLength = settings.contextLength;
    // Range 语义：[0, startIndex) 是已压缩消息，[startIndex, end] 是当前窗口
    final startIndex = (contextLength <= 0 ||
            contextLength == -1 ||
            history.length <= contextLength)
        ? 0
        : history.length - contextLength;

    // 需要压缩的消息：[0, startIndex)
    final toCompress = startIndex > 0
        ? history.take(startIndex).toList(growable: false)
        : <Message>[];
    final rangeStartId = toCompress.isNotEmpty ? toCompress.first.id : null;
    final rangeEndId = toCompress.isNotEmpty ? toCompress.last.id : null;

    return ConversationSummaryContext(
      messages: toCompress,
      rangeStartId: rangeStartId,
      rangeEndId: rangeEndId,
    );
  }

  Future<ConversationSummaryResult> summarize({
    required Conversation conversation,
    required ConversationSettings settings,
    required ai.AIProvider provider,
    required String modelName,
    ModelParameters? parameters,
  }) async {
    final context = buildSummaryContext(
      conversation: conversation,
      settings: settings,
    );

    if (context.messages.isEmpty) {
      return ConversationSummaryResult(
        summary: conversation.summary ?? '',
        rangeStartId: conversation.summaryRangeStartId,
        rangeEndId: conversation.summaryRangeEndId,
        updatedAt: conversation.summaryUpdatedAt ?? DateTime.now(),
      );
    }

    final existingSummary = conversation.summary ?? '';
    final prompt = existingSummary.isNotEmpty
        ? _buildMergePrompt(existingSummary, context.messages)
        : _buildSummaryPrompt(context.messages);

    final summary = await provider.sendMessage(
      model: modelName,
      messages: [
        ai.ChatMessage(role: 'system', content: _systemPrompt),
        ai.ChatMessage(role: 'user', content: prompt),
      ],
      parameters: parameters ?? settings.parameters,
    );

    final cleaned = _cleanJsonResponse(summary);
    final validated = _validateAndNormalizeJson(cleaned);
    final result = ConversationSummaryResult(
      summary: validated,
      rangeStartId: context.rangeStartId,
      rangeEndId: context.rangeEndId,
      updatedAt: DateTime.now(),
    );

    applySummary(conversation, result);
    return result;
  }

  void applySummary(
    Conversation conversation,
    ConversationSummaryResult result,
  ) {
    conversation
      ..summary = result.summary
      ..summaryRangeStartId = result.rangeStartId
      ..summaryRangeEndId = result.rangeEndId
      ..summaryUpdatedAt = result.updatedAt
      ..updatedAt = DateTime.now();
  }

  ConversationThread? _loadThread(Conversation conversation) {
    final raw = (conversation.threadJson ?? '').trim();
    if (raw.isEmpty) return null;
    try {
      // Build lookup from conversation.messages for compact format
      final messageMap = <String, Message>{};
      for (final msg in conversation.messages) {
        messageMap[msg.id] = msg;
      }
      final decoded = jsonDecode(raw);
      if (decoded is Map<String, dynamic>) {
        return ConversationThread.fromJson(
          decoded,
          messageLookup: (id) => messageMap[id],
        );
      }
      if (decoded is Map) {
        return ConversationThread.fromJson(
          decoded.cast<String, dynamic>(),
          messageLookup: (id) => messageMap[id],
        );
      }
    } catch (_) {
      // Fall back to linear messages.
    }
    return null;
  }

  String _buildSummaryPrompt(List<Message> messages) {
    if (messages.isEmpty) {
      return 'There is no conversation history to summarize.';
    }

    final buffer = StringBuffer();
    buffer.writeln('Summarize the following conversation into structured JSON.');
    buffer.writeln(_schemaHint);
    buffer.writeln('');
    buffer.writeln('Conversation:');
    for (final msg in messages) {
      final role = msg.isUser ? 'User' : 'Assistant';
      buffer.writeln('$role: ${msg.content}');
    }
    return buffer.toString();
  }

  String _buildMergePrompt(String existingSummary, List<Message> newMessages) {
    final buffer = StringBuffer();
    buffer.writeln('Merge the existing summary with new messages into updated structured JSON.');
    buffer.writeln(_schemaHint);
    buffer.writeln('');
    buffer.writeln('Existing Summary:');
    buffer.writeln(existingSummary);
    buffer.writeln('');
    buffer.writeln('New Messages to incorporate:');
    for (final msg in newMessages) {
      final role = msg.isUser ? 'User' : 'Assistant';
      buffer.writeln('$role: ${msg.content}');
    }
    buffer.writeln('');
    buffer.writeln('Produce updated JSON summary:');
    return buffer.toString();
  }

  String _cleanJsonResponse(String response) {
    var cleaned = response.trim();
    if (cleaned.startsWith('```json')) {
      cleaned = cleaned.substring(7);
    } else if (cleaned.startsWith('```')) {
      cleaned = cleaned.substring(3);
    }
    if (cleaned.endsWith('```')) {
      cleaned = cleaned.substring(0, cleaned.length - 3);
    }
    return cleaned.trim();
  }

  String _validateAndNormalizeJson(String input) {
    try {
      final decoded = jsonDecode(input);
      if (decoded is Map<String, dynamic>) {
        return jsonEncode(decoded);
      }
    } catch (_) {
      // JSON 解析失败，构建 fallback 结构
    }
    return jsonEncode({
      'intent': [],
      'decisions': [],
      'artifacts': [],
      'next_steps': [],
      'open_questions': [],
      'constraints': [],
      '_raw': input,
    });
  }
}
