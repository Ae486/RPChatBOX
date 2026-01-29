/// INPUT: ConversationThread tree + Message nodes
/// OUTPUT: Active-chain projection + branch selection state
/// POS: Models / Base Chat / Thread
import 'message.dart';

class ConversationThread {
  final String conversationId;
  final Map<String, ThreadNode> nodes;
  String rootId;
  final Map<String, String> selectedChild;
  String activeLeafId;

  ConversationThread({
    required this.conversationId,
    required this.nodes,
    required this.rootId,
    Map<String, String>? selectedChild,
    String? activeLeafId,
  })  : selectedChild = selectedChild ?? {},
        activeLeafId = activeLeafId ?? rootId;

  Map<String, dynamic> toJson() {
    return {
      'conversationId': conversationId,
      'nodes': nodes.map((id, node) => MapEntry(id, node.toJson())),
      'rootId': rootId,
      'selectedChild': selectedChild,
      'activeLeafId': activeLeafId,
    };
  }

  factory ConversationThread.fromJson(Map<String, dynamic> json) {
    final nodesJson = (json['nodes'] as Map?)?.cast<String, dynamic>() ?? {};
    final nodes = <String, ThreadNode>{
      for (final entry in nodesJson.entries)
        entry.key: ThreadNode.fromJson(entry.value as Map<String, dynamic>),
    };

    return ConversationThread(
      conversationId: json['conversationId'] as String,
      nodes: nodes,
      rootId: (json['rootId'] as String?) ?? '',
      selectedChild:
          (json['selectedChild'] as Map?)?.cast<String, String>() ?? {},
      activeLeafId: json['activeLeafId'] as String?,
    )
      ..rebuildFromParentIds()
      ..normalize();
  }

  static ConversationThread fromLinearMessages(
    String conversationId,
    List<Message> messages,
  ) {
    if (messages.isEmpty) {
      return ConversationThread(
        conversationId: conversationId,
        nodes: <String, ThreadNode>{},
        rootId: '',
        selectedChild: <String, String>{},
        activeLeafId: '',
      );
    }

    final nodes = <String, ThreadNode>{};
    String? previousId;
    for (final message in messages) {
      final parentId =
          (message.parentId != null && message.parentId!.isNotEmpty)
              ? message.parentId
              : previousId;
      if (message.parentId == null || message.parentId!.isEmpty) {
        message.parentId = parentId;
      }
      final node = ThreadNode(
        id: message.id,
        parentId: parentId,
        message: message,
        children: const [],
      );
      nodes[node.id] = node;
      if (parentId != null) {
        final parent = nodes[parentId];
        if (parent != null) {
          nodes[parentId] = parent.copyWith(
            children: [...parent.children, node.id],
          );
        }
      }
      previousId = node.id;
    }

    final rootId = messages.first.id;
    final activeLeafId = messages.last.id;
    return ConversationThread(
      conversationId: conversationId,
      nodes: nodes,
      rootId: rootId,
      selectedChild: <String, String>{},
      activeLeafId: activeLeafId,
    )..normalize();
  }

  void normalize() {
    if (nodes.isEmpty) {
      rootId = '';
      activeLeafId = '';
      selectedChild.clear();
      return;
    }

    if (rootId.isEmpty || !nodes.containsKey(rootId)) {
      rootId = nodes.keys.first;
    }

    if (activeLeafId.isEmpty || !nodes.containsKey(activeLeafId)) {
      activeLeafId = rootId;
    }

    selectedChild.removeWhere(
      (parentId, childId) =>
          !nodes.containsKey(parentId) ||
          !nodes.containsKey(childId) ||
          !nodes[parentId]!.children.contains(childId),
    );

    final nodeIds = nodes.keys.toList(growable: false);
    for (final nodeId in nodeIds) {
      final node = nodes[nodeId];
      if (node == null || node.children.isEmpty) continue;
      _syncMessageParentId(nodeId);

      final validChildren = node.children
          .where(nodes.containsKey)
          .toList(growable: false);
      if (validChildren.length != node.children.length) {
        nodes[nodeId] = node.copyWith(children: validChildren);
      }
    }

    // Ensure message.parentId is aligned for any remaining nodes.
    for (final nodeId in nodes.keys) {
      _syncMessageParentId(nodeId);
    }

    var currentId = rootId;
    while (currentId.isNotEmpty) {
      final node = nodes[currentId];
      if (node == null || node.children.isEmpty) break;

      final selected = selectedChild[currentId];
      final nextId =
          (selected != null && node.children.contains(selected))
              ? selected
              : node.children.last;

      selectedChild[currentId] = nextId;
      currentId = nextId;
    }

    activeLeafId = currentId;
  }

  void upsertMessage(Message message) {
    final existing = nodes[message.id];
    if (existing == null) return;
    if (message.parentId == null || message.parentId!.isEmpty) {
      message.parentId = existing.parentId;
    }
    nodes[message.id] = existing.copyWith(message: message);
  }

  /// 级联删除节点及其所有子孙节点
  void _cascadeDelete(String nodeId) {
    final node = nodes[nodeId];
    if (node == null) return;

    // 递归删除所有子节点
    for (final childId in List.from(node.children)) {
      _cascadeDelete(childId);
    }

    // 删除节点本身
    nodes.remove(nodeId);
    selectedChild.remove(nodeId);
  }

  /// 删除单条消息，将其子节点提升到父节点
  void removeNode(String nodeId) {
    final node = nodes[nodeId];
    if (node == null) return;

    final parentId = node.parentId;
    final childrenToPromote = List<String>.from(node.children);

    // 场景6：删除根节点且有多个子节点 - 只保留当前链路的子节点
    if ((parentId == null || parentId.isEmpty) && childrenToPromote.length > 1) {
      // 确定当前选中的子节点
      String? currentChild = selectedChild[nodeId];

      // 如果没有选中的子节点，选择第一个子节点
      if (currentChild == null || !childrenToPromote.contains(currentChild)) {
        currentChild = childrenToPromote.first;
      }

      // 删除其他子节点（级联删除）
      for (final childId in childrenToPromote) {
        if (childId != currentChild) {
          _cascadeDelete(childId);
        }
      }

      // 当前子节点成为新根
      rootId = currentChild!;
      final newRoot = nodes[currentChild];
      if (newRoot != null) {
        newRoot.message.parentId = null;
        nodes[currentChild] = newRoot.copyWith(parentId: null);
      }

      // 删除旧根节点
      nodes.remove(nodeId);
      selectedChild.remove(nodeId);
      normalize();
      return;
    }

    // 其他场景：提升所有子节点到父节点
    // 更新被提升子节点的 parentId
    for (final childId in childrenToPromote) {
      final child = nodes[childId];
      if (child != null) {
        child.message.parentId = parentId;
        nodes[childId] = child.copyWith(parentId: parentId);
      }
    }

    if (parentId != null && parentId.isNotEmpty && nodes.containsKey(parentId)) {
      // 有父节点：将子节点插入到被删除节点原来的位置
      final parent = nodes[parentId]!;
      final parentChildren = List<String>.from(parent.children);
      final nodeIndex = parentChildren.indexOf(nodeId);

      if (nodeIndex >= 0) {
        parentChildren.removeAt(nodeIndex);
        parentChildren.insertAll(nodeIndex, childrenToPromote);
      } else {
        parentChildren.addAll(childrenToPromote);
      }

      nodes[parentId] = parent.copyWith(children: parentChildren);

      // 清理 selectedChild：如果父节点选中的是被删除节点，改选第一个提升的子节点
      if (selectedChild[parentId] == nodeId) {
        // 优先选择被删除节点的第一个子节点，保持原分支连续性
        if (childrenToPromote.isNotEmpty) {
          selectedChild[parentId] = childrenToPromote.first;
        } else {
          selectedChild.remove(parentId);
        }
      }
    } else {
      // 删除的是根节点（只有一个或零个子节点）
      if (childrenToPromote.isEmpty) {
        rootId = '';
      } else {
        // 只有一个子节点：直接成为新根
        rootId = childrenToPromote.first;
        final newRoot = nodes[rootId];
        if (newRoot != null) {
          newRoot.message.parentId = null;
          nodes[rootId] = newRoot.copyWith(parentId: null);
        }
      }
    }

    // 删除节点本身
    nodes.remove(nodeId);
    selectedChild.remove(nodeId);

    // 重新规范化
    normalize();
  }

  void appendToActiveLeaf(Message message) {
    // If the node already exists, treat this as an update and move the active leaf.
    if (nodes.containsKey(message.id)) {
      upsertMessage(message);
      activeLeafId = message.id;
      return;
    }

    // Empty thread: initialize root.
    if (nodes.isEmpty || rootId.isEmpty) {
      message.parentId ??= null;
      nodes[message.id] = ThreadNode(
        id: message.id,
        parentId: null,
        message: message,
        children: const [],
      );
      rootId = message.id;
      activeLeafId = message.id;
      selectedChild.clear();
      return;
    }

    final parentId = activeLeafId;
    final parent = nodes[parentId];
    if (parent == null) {
      // Corrupted state; fall back to re-initialize as a single-chain.
      nodes
        ..clear()
        ..[message.id] = ThreadNode(
          id: message.id,
          parentId: null,
          message: message,
          children: const [],
        );
      rootId = message.id;
      activeLeafId = message.id;
      selectedChild.clear();
      return;
    }

    if (message.parentId == null || message.parentId!.isEmpty) {
      message.parentId = parentId;
    }
    nodes[message.id] = ThreadNode(
      id: message.id,
      parentId: parentId,
      message: message,
      children: const [],
    );
    nodes[parentId] = parent.copyWith(children: [...parent.children, message.id]);
    selectedChild[parentId] = message.id;
    activeLeafId = message.id;
  }

  void appendAssistantChildUnderUserAndSelect({
    required String userId,
    required String childId,
    Message? assistantMessage,
  }) {
    final userNode = nodes[userId];
    if (userNode == null) {
      throw ArgumentError.value(userId, 'userId', 'Parent node not found');
    }
    if (!userNode.message.isUser) {
      throw ArgumentError.value(userId, 'userId', 'Parent must be a user node');
    }

    if (assistantMessage != null) {
      if (assistantMessage.id != childId) {
        throw ArgumentError.value(
          assistantMessage.id,
          'assistantMessage',
          'assistantMessage.id must equal childId',
        );
      }
      if (assistantMessage.parentId == null || assistantMessage.parentId!.isEmpty) {
        assistantMessage.parentId = userId;
      }
      if (assistantMessage.isUser) {
        throw ArgumentError.value(
          assistantMessage.id,
          'assistantMessage',
          'Child must be an assistant message',
        );
      }
    }

    final existingChild = nodes[childId];
    if (existingChild != null) {
      if (existingChild.message.isUser) {
        throw ArgumentError.value(childId, 'childId', 'Child must be assistant');
      }
      if (existingChild.parentId != userId) {
        throw ArgumentError.value(
          childId,
          'childId',
          'Child already exists under a different parent',
        );
      }
      if (assistantMessage != null) {
        if (assistantMessage.parentId == null || assistantMessage.parentId!.isEmpty) {
          assistantMessage.parentId = userId;
        }
        upsertMessage(assistantMessage);
      }
    } else {
      if (assistantMessage == null) {
        throw ArgumentError.value(
          childId,
          'childId',
          'assistantMessage is required when creating a new child node',
        );
      }
      if (assistantMessage.parentId == null || assistantMessage.parentId!.isEmpty) {
        assistantMessage.parentId = userId;
      }
      nodes[childId] = ThreadNode(
        id: childId,
        parentId: userId,
        message: assistantMessage,
        children: const [],
      );
    }

    if (!userNode.children.contains(childId)) {
      nodes[userId] = userNode.copyWith(children: [...userNode.children, childId]);
    }

    _selectPathToNode(userId);
    selectedChild[userId] = childId;
    activeLeafId = childId;

    normalize();
    selectedChild[userId] = childId;
    activeLeafId = childId;
  }

  void appendAssistantVariantUnderUser({
    required String userId,
    required Message assistantMessage,
  }) {
    appendAssistantChildUnderUserAndSelect(
      userId: userId,
      childId: assistantMessage.id,
      assistantMessage: assistantMessage,
    );
  }

  void _selectPathToNode(String nodeId) {
    if (nodes.isEmpty) return;

    final path = <String>[];
    var currentId = nodeId;
    while (currentId.isNotEmpty) {
      path.add(currentId);
      final parentId = nodes[currentId]?.parentId;
      if (parentId == null || parentId.isEmpty) break;
      currentId = parentId;
    }

    // path: nodeId -> ... -> root
    for (var i = path.length - 1; i >= 1; i--) {
      final parentId = path[i];
      final childId = path[i - 1];
      final parent = nodes[parentId];
      if (parent == null) continue;
      if (!parent.children.contains(childId)) continue;
      selectedChild[parentId] = childId;
    }
  }

  void _syncMessageParentId(String nodeId) {
    final node = nodes[nodeId];
    if (node == null) return;
    if (node.message.parentId != node.parentId) {
      node.message.parentId = node.parentId;
    }
  }

  List<Message> buildActiveChain() {
    if (nodes.isEmpty || rootId.isEmpty) {
      return const <Message>[];
    }

    final chain = <Message>[];
    var currentId = rootId;
    final visited = <String>{};

    while (currentId.isNotEmpty) {
      if (!visited.add(currentId)) break;

      final node = nodes[currentId];
      if (node == null) break;
      chain.add(node.message);

      if (node.children.isEmpty) break;

      final selected = selectedChild[currentId];
      final nextId =
          (selected != null && node.children.contains(selected))
              ? selected
              : node.children.last;

      currentId = nextId;
    }

    return chain;
  }

  void rebuildFromParentIds() {
    if (nodes.isEmpty) return;

    final nodeIds = nodes.keys.toList(growable: false);
    final parentMap = <String, String?>{};
    for (final nodeId in nodeIds) {
      final node = nodes[nodeId];
      if (node == null) continue;
      final parentId = (node.message.parentId != null &&
              node.message.parentId!.isNotEmpty)
          ? node.message.parentId
          : node.parentId;
      parentMap[nodeId] = parentId;
      if (parentId != node.parentId) {
        nodes[nodeId] = node.copyWith(parentId: parentId);
      }
    }

    for (final nodeId in nodeIds) {
      final node = nodes[nodeId];
      if (node == null) continue;
      if (node.children.isNotEmpty) {
        nodes[nodeId] = node.copyWith(children: const []);
      }
    }

    final childrenMap = <String, List<String>>{};
    for (final entry in parentMap.entries) {
      final childId = entry.key;
      final parentId = entry.value;
      if (parentId == null || parentId.isEmpty) continue;
      if (!nodes.containsKey(parentId)) continue;
      childrenMap.putIfAbsent(parentId, () => []).add(childId);
    }

    for (final entry in childrenMap.entries) {
      final parentId = entry.key;
      final desired = entry.value;
      final parent = nodes[parentId];
      if (parent == null) continue;

      final existing = parent.children;
      final ordered = <String>[];
      for (final childId in existing) {
        if (desired.contains(childId)) ordered.add(childId);
      }
      final remaining = desired.where((id) => !ordered.contains(id)).toList();
      remaining.sort((a, b) => nodes[a]!.message.timestamp
          .compareTo(nodes[b]!.message.timestamp));
      ordered.addAll(remaining);

      nodes[parentId] = parent.copyWith(children: ordered);
    }

    final roots = nodeIds.where((nodeId) {
      final parentId = parentMap[nodeId];
      return parentId == null || parentId.isEmpty || !nodes.containsKey(parentId);
    }).toList();
    if (roots.isNotEmpty) {
      roots.sort((a, b) => nodes[a]!.message.timestamp
          .compareTo(nodes[b]!.message.timestamp));
      rootId = roots.first;
    }
  }
}


class ThreadNode {
  final String id;
  final String? parentId;
  final Message message;
  final List<String> children;

  const ThreadNode({
    required this.id,
    required this.parentId,
    required this.message,
    required this.children,
  });

  ThreadNode copyWith({
    String? id,
    String? parentId,
    Message? message,
    List<String>? children,
  }) {
    return ThreadNode(
      id: id ?? this.id,
      parentId: parentId ?? this.parentId,
      message: message ?? this.message,
      children: children ?? this.children,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'parentId': parentId,
      'message': message.toJson(),
      'children': children,
    };
  }

  factory ThreadNode.fromJson(Map<String, dynamic> json) {
    return ThreadNode(
      id: json['id'] as String,
      parentId: json['parentId'] as String?,
      message: Message.fromJson(json['message'] as Map<String, dynamic>),
      children: (json['children'] as List?)?.cast<String>() ?? const [],
    );
  }
}
