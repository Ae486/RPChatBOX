part of '../conversation_view_v2.dart';

List<app.Message> buildActiveMessageChain(ConversationThread thread) {
  if (thread.nodes.isEmpty || thread.rootId.isEmpty) {
    return const <app.Message>[];
  }

  final chain = <app.Message>[];
  var currentId = thread.rootId;
  final visited = <String>{};

  while (currentId.isNotEmpty) {
    if (!visited.add(currentId)) break;

    final node = thread.nodes[currentId];
    if (node == null) break;
    chain.add(node.message);

    if (node.children.isEmpty) break;

    final selected = thread.selectedChild[currentId];
    final nextId = (selected != null && node.children.contains(selected))
        ? selected
        : node.children.last;

    currentId = nextId;
  }

  return chain;
}
