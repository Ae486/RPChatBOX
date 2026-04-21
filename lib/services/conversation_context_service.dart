/// INPUT: Conversation + ConversationSettings (+ optional live history override)
/// OUTPUT: Effective context window / compact window / token breakdown
/// POS: Services / Base Chat / Context Window
import 'dart:convert';

import '../models/conversation.dart';
import '../models/conversation_settings.dart';
import '../models/conversation_thread.dart';
import '../models/message.dart';
import '../utils/token_counter.dart';

const String kCompactSummaryPromptPrefix = '[Previous conversation summary]\n';

class ConversationContextWindow {
  final List<Message> activeHistory;
  final List<Message> effectiveHistory;
  final List<Message> windowMessages;
  final String summary;
  final bool summaryApplied;
  final int summaryTokens;
  final int windowTokens;

  const ConversationContextWindow({
    required this.activeHistory,
    required this.effectiveHistory,
    required this.windowMessages,
    required this.summary,
    required this.summaryApplied,
    required this.summaryTokens,
    required this.windowTokens,
  });

  String? get rangeStartId =>
      windowMessages.isNotEmpty ? windowMessages.first.id : null;

  String? get rangeEndId =>
      windowMessages.isNotEmpty ? windowMessages.last.id : null;

  int get totalContextTokens => summaryTokens + windowTokens;
}

class ConversationContextService {
  const ConversationContextService();

  ConversationContextWindow buildContextWindow({
    required Conversation conversation,
    required ConversationSettings settings,
    List<Message>? historyOverride,
    int? contextLengthOverride,
  }) {
    final rawHistory = historyOverride ?? _loadActiveHistory(conversation);
    final activeHistory = _stripTrailingEmptyAssistant(rawHistory);

    var effectiveHistory = activeHistory;
    var summaryApplied = false;

    final summary = (conversation.summary ?? '').trim();
    final summaryRangeEndId = conversation.summaryRangeEndId;
    if (summary.isNotEmpty && summaryRangeEndId != null) {
      final summaryEndIndex = activeHistory.indexWhere(
        (message) => message.id == summaryRangeEndId,
      );
      if (summaryEndIndex >= 0) {
        effectiveHistory = activeHistory.sublist(summaryEndIndex + 1);
        summaryApplied = true;
      }
    }

    final contextLength = contextLengthOverride ?? settings.contextLength;
    final startIndex =
        (contextLength <= 0 ||
            contextLength == -1 ||
            effectiveHistory.length <= contextLength)
        ? 0
        : effectiveHistory.length - contextLength;

    final windowMessages = effectiveHistory
        .skip(startIndex)
        .toList(growable: false);
    final summaryTokens = summaryApplied
        ? TokenCounter.estimateTokens(formatSummaryForPrompt(summary))
        : 0;
    final windowTokens = windowMessages.fold<int>(
      0,
      (sum, message) => sum + estimateMessageTokens(message),
    );

    return ConversationContextWindow(
      activeHistory: activeHistory,
      effectiveHistory: effectiveHistory,
      windowMessages: windowMessages,
      summary: summary,
      summaryApplied: summaryApplied,
      summaryTokens: summaryTokens,
      windowTokens: windowTokens,
    );
  }

  int estimateMessageTokens(Message message) {
    if (message.isUser) {
      final inputTokens = message.inputTokens;
      if (inputTokens != null && inputTokens > 0) {
        return inputTokens;
      }
      return TokenCounter.estimateTokens(message.content);
    }

    final outputTokens = message.outputTokens;
    if (outputTokens != null && outputTokens > 0) {
      return outputTokens;
    }
    return TokenCounter.estimateTokens(message.content);
  }

  static String formatSummaryForPrompt(String summaryJson) {
    return '$kCompactSummaryPromptPrefix$summaryJson';
  }

  List<Message> _loadActiveHistory(Conversation conversation) {
    final thread = _loadThread(conversation);
    return thread?.buildActiveChain() ?? conversation.messages;
  }

  ConversationThread? _loadThread(Conversation conversation) {
    final raw = (conversation.threadJson ?? '').trim();
    if (raw.isEmpty) return null;
    try {
      final messageMap = <String, Message>{
        for (final message in conversation.messages) message.id: message,
      };
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

  List<Message> _stripTrailingEmptyAssistant(List<Message> history) {
    if (history.isEmpty) return const <Message>[];
    final last = history.last;
    if (!last.isUser && last.content.trim().isEmpty) {
      return history.sublist(0, history.length - 1);
    }
    return history.toList(growable: false);
  }
}
