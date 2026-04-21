/// INPUT: Conversation (via getter) + persistence callbacks
/// OUTPUT: ThreadManager - thread lifecycle management (load/persist/sync/variant)
/// POS: Controllers / Chat / Thread Management (extracted from conversation_view_v2)

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';

import '../models/conversation.dart';
import '../models/conversation_thread.dart';
import '../models/message.dart';

/// Result of threadJson validation.
enum ThreadJsonValidationResult {
  /// Valid JSON, successfully parsed to ConversationThread.
  valid,

  /// Empty or null threadJson - not an error, just needs rebuild.
  empty,

  /// JSON syntax error (malformed JSON).
  jsonSyntaxError,

  /// JSON structure error (missing required fields, wrong types).
  structureError,

  /// Inconsistent state (orphan nodes, missing root, etc.) - auto-repaired.
  inconsistentRepaired,

  /// Conversation ID mismatch.
  conversationIdMismatch,
}

/// Details about thread loading/validation.
class ThreadLoadResult {
  final ConversationThread thread;
  final ThreadJsonValidationResult validationResult;
  final String? errorMessage;
  final bool wasRepaired;

  const ThreadLoadResult({
    required this.thread,
    required this.validationResult,
    this.errorMessage,
    this.wasRepaired = false,
  });

  bool get isHealthy =>
      validationResult == ThreadJsonValidationResult.valid ||
      validationResult == ThreadJsonValidationResult.inconsistentRepaired;
}

/// Manages ConversationThread lifecycle: loading, mutation, persistence.
///
/// Extracted from ConversationViewV2 to reduce complexity and improve testability.
/// This class handles:
/// - Lazy-load thread from Conversation.threadJson
/// - Maintain thread <-> messages snapshot sync
/// - Debounced persistence (350ms default)
/// - Variant ID retrieval for branch switching
class ThreadManager {
  /// Gets the current Conversation instance.
  final Conversation Function() getConversation;

  /// Checks if the owner widget is disposed.
  final bool Function() isDisposed;

  /// Called when conversation needs to be saved.
  final void Function() onConversationUpdated;

  /// Optional: looks up a message by ID from persistent storage.
  /// Used to resolve messages for non-active branches in threadJson.
  /// If not provided, falls back to conversation.messages only.
  /// Can be set/updated after construction.
  ///
  /// NOTE(tech-debt): 这是一个穿透链路，用于解决 conversation.messages 只包含
  /// 活动分支消息的问题。理想情况下应该在 HiveConversationService 加载时一次性
  /// 填充所有消息到 thread 节点，而不是运行时再查找。
  /// 详见：docs/debug/thread-message-lookup-debt.md
  Message? Function(String id)? getMessageById;

  ConversationThread? _thread;
  Timer? _persistTimer;
  String? _lastPersistedJson;

  ThreadManager({
    required this.getConversation,
    required this.isDisposed,
    required this.onConversationUpdated,
    this.getMessageById,
  });

  /// Current thread instance (may be null before first access).
  ConversationThread? get currentThread => _thread;

  /// Last persisted JSON (for change detection).
  String? get lastPersistedJson => _lastPersistedJson;

  /// Gets or lazily loads the thread for the current conversation.
  ///
  /// If [rebuildFromMessagesIfMismatch] is true (default), will rebuild
  /// from linear messages when:
  /// - No usable threadJson exists
  /// - Thread is linear (no branches) and out of sync with messages
  ///
  /// If [checkLimits] is true, will check soft limits and log warnings
  /// if exceeded (default: false to avoid overhead on frequent calls).
  ConversationThread getThread({
    bool rebuildFromMessagesIfMismatch = true,
    bool checkLimits = false,
  }) {
    final conversation = getConversation();

    if (_thread == null || _thread!.conversationId != conversation.id) {
      _thread = _loadFromConversation(conversation);
      // Check limits on initial load
      _thread!.checkLimits();
    }

    if (rebuildFromMessagesIfMismatch) {
      final raw = (conversation.threadJson ?? '').trim();
      final hasUsableThreadJson = raw.isNotEmpty && _thread!.nodes.isNotEmpty;

      final hasBranches = _thread!.nodes.values.any((n) => n.children.length > 1);
      final messages = conversation.messages;
      final messagesLastId = messages.isEmpty ? '' : messages.last.id;

      // Phase 1 (tree as source-of-truth):
      // - If there is NO usable threadJson yet, build a linear thread from messages.
      // - If the current thread is still linear (no branches), keep it synced with
      //   the legacy linear list to avoid breaking existing delete/truncate paths.
      // - Once branches exist, never rebuild from `conversation.messages`.
      final shouldRebuildFromMessages = !hasUsableThreadJson ||
          (!hasBranches &&
              (_thread!.nodes.length != messages.length ||
                  _thread!.activeLeafId != messagesLastId));

      if (shouldRebuildFromMessages) {
        _thread = ConversationThread.fromLinearMessages(conversation.id, messages);
        persistNoSave(_thread!);
      }
    }

    if (checkLimits) {
      _thread!.checkLimits();
    }

    return _thread!;
  }

  /// Loads thread from conversation's threadJson or builds from linear messages.
  /// Includes validation and auto-repair for corrupted data.
  ConversationThread _loadFromConversation(Conversation conversation) {
    final result = _loadAndValidate(conversation);

    // Log validation issues for debugging
    if (result.validationResult != ThreadJsonValidationResult.valid &&
        result.validationResult != ThreadJsonValidationResult.empty) {
      debugPrint(
        '[ThreadManager] threadJson validation: ${result.validationResult.name}'
        '${result.errorMessage != null ? " - ${result.errorMessage}" : ""}'
        '${result.wasRepaired ? " (auto-repaired)" : ""}',
      );
    }

    return result.thread;
  }

  /// Loads and validates threadJson with detailed diagnostics.
  ThreadLoadResult _loadAndValidate(Conversation conversation) {
    final raw = (conversation.threadJson ?? '').trim();

    // Case 1: Empty threadJson - rebuild from messages
    if (raw.isEmpty) {
      return ThreadLoadResult(
        thread: ConversationThread.fromLinearMessages(
          conversation.id,
          conversation.messages,
        ),
        validationResult: ThreadJsonValidationResult.empty,
      );
    }

    // Case 2: Try to parse JSON
    dynamic decoded;
    try {
      decoded = jsonDecode(raw);
    } catch (e) {
      debugPrint('[ThreadManager] JSON syntax error: $e');
      return ThreadLoadResult(
        thread: ConversationThread.fromLinearMessages(
          conversation.id,
          conversation.messages,
        ),
        validationResult: ThreadJsonValidationResult.jsonSyntaxError,
        errorMessage: e.toString(),
      );
    }

    // Case 3: Validate JSON structure
    if (decoded is! Map) {
      return ThreadLoadResult(
        thread: ConversationThread.fromLinearMessages(
          conversation.id,
          conversation.messages,
        ),
        validationResult: ThreadJsonValidationResult.structureError,
        errorMessage: 'Root is not a Map',
      );
    }

    final json = decoded is Map<String, dynamic>
        ? decoded
        : decoded.cast<String, dynamic>();

    // Validate required fields
    final structureError = _validateJsonStructure(json);
    if (structureError != null) {
      return ThreadLoadResult(
        thread: ConversationThread.fromLinearMessages(
          conversation.id,
          conversation.messages,
        ),
        validationResult: ThreadJsonValidationResult.structureError,
        errorMessage: structureError,
      );
    }

    // Case 4: Check conversation ID match
    final jsonConversationId = json['conversationId'] as String?;
    if (jsonConversationId != null && jsonConversationId != conversation.id) {
      debugPrint(
        '[ThreadManager] conversationId mismatch: '
        'expected=${conversation.id}, got=$jsonConversationId',
      );
      return ThreadLoadResult(
        thread: ConversationThread.fromLinearMessages(
          conversation.id,
          conversation.messages,
        ),
        validationResult: ThreadJsonValidationResult.conversationIdMismatch,
        errorMessage: 'ID mismatch: expected ${conversation.id}',
      );
    }

    // Case 5: Parse and validate internal consistency
    // NOTE(tech-debt): 这里可能是 thread 的二次加载。HiveConversationService.loadConversations()
    // 已经用 messageBox 加载过一次 thread，但 ThreadManager 会重新从 threadJson 解析。
    // 两次加载使用不同的 messageLookup，可能导致不一致。
    // 详见：docs/debug/thread-message-lookup-debt.md
    ConversationThread thread;
    try {
      // Build message lookup: first try memory (conversation.messages),
      // then fall back to persistent storage (getMessageById) for non-active branches.
      // NOTE(tech-debt): conversation.messages 只包含活动分支的消息快照，
      // 非活动分支的消息需要通过 getMessageById 从 messageBox 获取。
      final memoryMap = <String, Message>{};
      for (final msg in conversation.messages) {
        memoryMap[msg.id] = msg;
      }
      Message? combinedLookup(String id) {
        return memoryMap[id] ?? getMessageById?.call(id);
      }
      thread = ConversationThread.fromJson(
        json,
        messageLookup: combinedLookup,
      );
    } catch (e) {
      debugPrint('[ThreadManager] ConversationThread.fromJson failed: $e');
      return ThreadLoadResult(
        thread: ConversationThread.fromLinearMessages(
          conversation.id,
          conversation.messages,
        ),
        validationResult: ThreadJsonValidationResult.structureError,
        errorMessage: 'fromJson failed: $e',
      );
    }

    // Case 6: Check for inconsistencies and repair
    final inconsistencies = _detectInconsistencies(thread);
    if (inconsistencies.isNotEmpty) {
      debugPrint(
        '[ThreadManager] Detected inconsistencies: ${inconsistencies.join(", ")}',
      );

      // normalize() already called in fromJson, but call again to be safe
      thread.normalize();

      // Verify repair was successful
      final postRepairIssues = _detectInconsistencies(thread);
      if (postRepairIssues.isNotEmpty) {
        debugPrint(
          '[ThreadManager] Repair incomplete, remaining issues: '
          '${postRepairIssues.join(", ")}. Rebuilding from messages.',
        );
        return ThreadLoadResult(
          thread: ConversationThread.fromLinearMessages(
            conversation.id,
            conversation.messages,
          ),
          validationResult: ThreadJsonValidationResult.structureError,
          errorMessage: 'Unrepairable: ${postRepairIssues.join(", ")}',
        );
      }

      _lastPersistedJson = raw;
      return ThreadLoadResult(
        thread: thread,
        validationResult: ThreadJsonValidationResult.inconsistentRepaired,
        errorMessage: inconsistencies.join(', '),
        wasRepaired: true,
      );
    }

    // Case 7: All good
    _lastPersistedJson = raw;
    return ThreadLoadResult(
      thread: thread,
      validationResult: ThreadJsonValidationResult.valid,
    );
  }

  /// Validates JSON structure has required fields with correct types.
  /// Returns error message if invalid, null if valid.
  String? _validateJsonStructure(Map<String, dynamic> json) {
    // conversationId: required string
    if (!json.containsKey('conversationId')) {
      return 'Missing conversationId';
    }
    if (json['conversationId'] is! String) {
      return 'conversationId is not a String';
    }

    // nodes: required map
    if (!json.containsKey('nodes')) {
      return 'Missing nodes';
    }
    if (json['nodes'] is! Map) {
      return 'nodes is not a Map';
    }

    // rootId: required string (can be empty for empty thread)
    if (!json.containsKey('rootId')) {
      return 'Missing rootId';
    }
    if (json['rootId'] is! String) {
      return 'rootId is not a String';
    }

    // selectedChild: optional map
    if (json.containsKey('selectedChild') && json['selectedChild'] is! Map) {
      return 'selectedChild is not a Map';
    }

    // activeLeafId: optional string
    if (json.containsKey('activeLeafId') &&
        json['activeLeafId'] != null &&
        json['activeLeafId'] is! String) {
      return 'activeLeafId is not a String';
    }

    // Validate nodes structure
    final nodes = json['nodes'] as Map;
    for (final entry in nodes.entries) {
      if (entry.key is! String) {
        return 'Node key is not a String';
      }
      if (entry.value is! Map) {
        return 'Node value is not a Map';
      }
      final node = entry.value as Map;
      if (!node.containsKey('id')) {
        return 'Node missing id';
      }
      // 支持两种格式：inline message 或 messageId 引用
      if (!node.containsKey('message') && !node.containsKey('messageId')) {
        return 'Node missing message or messageId';
      }
    }

    return null;
  }

  /// Detects inconsistencies in the thread that can be repaired.
  /// Returns list of issue descriptions.
  List<String> _detectInconsistencies(ConversationThread thread) {
    final issues = <String>[];

    // Empty thread is valid
    if (thread.nodes.isEmpty) {
      if (thread.rootId.isNotEmpty) {
        issues.add('Empty nodes but non-empty rootId');
      }
      return issues;
    }

    // Check rootId points to existing node
    if (thread.rootId.isEmpty) {
      issues.add('Empty rootId with non-empty nodes');
    } else if (!thread.nodes.containsKey(thread.rootId)) {
      issues.add('rootId points to non-existent node');
    }

    // Check activeLeafId points to existing node
    if (thread.activeLeafId.isNotEmpty &&
        !thread.nodes.containsKey(thread.activeLeafId)) {
      issues.add('activeLeafId points to non-existent node');
    }

    // Check for orphan nodes (no parent and not root)
    for (final node in thread.nodes.values) {
      if (node.id != thread.rootId) {
        final parentId = node.parentId;
        if (parentId == null || parentId.isEmpty) {
          issues.add('Orphan node without parent: ${node.id}');
        } else if (!thread.nodes.containsKey(parentId)) {
          issues.add('Node ${node.id} has non-existent parent: $parentId');
        }
      }
    }

    // Check children references
    for (final node in thread.nodes.values) {
      for (final childId in node.children) {
        if (!thread.nodes.containsKey(childId)) {
          issues.add('Node ${node.id} has non-existent child: $childId');
        }
      }
    }

    // Check selectedChild references
    for (final entry in thread.selectedChild.entries) {
      if (!thread.nodes.containsKey(entry.key)) {
        issues.add('selectedChild has non-existent parent: ${entry.key}');
      }
      if (!thread.nodes.containsKey(entry.value)) {
        issues.add('selectedChild has non-existent child: ${entry.value}');
      }
    }

    return issues;
  }

  /// Encodes thread to conversation without triggering save callback.
  void persistNoSave(ConversationThread thread) {
    final encoded = jsonEncode(thread.toJson());
    _lastPersistedJson = encoded;
    final conversation = getConversation();
    conversation.threadJson = encoded;
    conversation.activeLeafId = thread.activeLeafId;
  }

  /// Replace the in-memory thread with an externally loaded projection.
  void replaceThread(ConversationThread thread) {
    _thread = thread;
    persistNoSave(thread);
  }

  /// Schedules debounced persistence.
  void schedulePersist({
    Duration delay = const Duration(milliseconds: 350),
  }) {
    if (isDisposed()) return;
    _persistTimer?.cancel();
    _persistTimer = Timer(delay, () {
      if (isDisposed()) return;
      final thread = _thread;
      if (thread == null) return;

      final encoded = jsonEncode(thread.toJson());
      if (encoded == _lastPersistedJson) return;

      _lastPersistedJson = encoded;
      final conversation = getConversation();
      conversation.threadJson = encoded;
      conversation.activeLeafId = thread.activeLeafId;
      onConversationUpdated();
    });
  }

  /// Immediately flushes any pending persistence.
  void flushPersistNow() {
    if (isDisposed()) return;

    _persistTimer?.cancel();
    _persistTimer = null;

    final thread = _thread;
    if (thread == null) return;

    final encoded = jsonEncode(thread.toJson());
    if (encoded == _lastPersistedJson) return;

    _lastPersistedJson = encoded;
    final conversation = getConversation();
    conversation.threadJson = encoded;
    conversation.activeLeafId = thread.activeLeafId;
    onConversationUpdated();
  }

  /// Syncs conversation.messages snapshot from thread's active chain.
  void syncMessagesSnapshot(ConversationThread thread) {
    final chain = thread.buildActiveChain();
    final messages = getConversation().messages;
    messages
      ..clear()
      ..addAll(chain);
  }

  /// Gets assistant variant IDs for a user message.
  ///
  /// Returns all child node IDs of the user message (for branch switching).
  List<String> getAssistantVariantIds(String userMessageId, ConversationThread thread) {
    final node = thread.nodes[userMessageId];
    if (node == null) return const <String>[];
    if (!node.message.isUser) return const <String>[];

    // Return all child nodes (allows mixed user/assistant types after deletion)
    return List<String>.from(node.children);
  }

  /// Switches to a different variant under the given user message.
  ///
  /// Returns the new selected variant ID, or null if switch failed.
  /// The caller is responsible for UI updates (toast, scroll, etc.).
  String? switchVariant(String userMessageId, int delta) {
    if (isDisposed()) return null;

    final thread = getThread(rebuildFromMessagesIfMismatch: false);
    final variants = getAssistantVariantIds(userMessageId, thread);
    if (variants.length <= 1) return null;

    final selected = thread.selectedChild[userMessageId];
    var index = selected == null ? -1 : variants.indexOf(selected);
    if (index < 0) index = variants.length - 1;

    final rawNext = index + delta;
    final nextIndex = ((rawNext % variants.length) + variants.length) % variants.length;

    final newVariantId = variants[nextIndex];
    thread.selectedChild[userMessageId] = newVariantId;
    thread.normalize();

    syncMessagesSnapshot(thread);
    persistNoSave(thread);
    schedulePersist(delay: const Duration(milliseconds: 220));

    return newVariantId;
  }

  /// Resets internal state when conversation changes.
  void reset() {
    flushPersistNow();
    _thread = null;
    _lastPersistedJson = null;
  }

  /// Disposes resources.
  void dispose() {
    flushPersistNow();
    _persistTimer?.cancel();
    _persistTimer = null;
    _thread = null;
  }
}
