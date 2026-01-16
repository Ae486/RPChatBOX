/// INPUT: ConversationThread（树）+ Message 节点集合
/// OUTPUT: buildActiveMessageChain() - 选中分支投影为线性消息列表（供 Chat 渲染）
/// POS: UI 层 / Chat / V2 - Thread → Linear 投影（part of ConversationViewV2）

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
