/// INPUT: ConversationThread（树）+ Message 节点集合
/// OUTPUT: buildActiveMessageChain() - 选中分支投影为线性消息列表（供 Chat 渲染）
/// POS: UI 层 / Chat / V2 - Thread → Linear 投影（part of ConversationViewV2）

part of '../conversation_view_v2.dart';

List<app.Message> buildActiveMessageChain(ConversationThread thread) {
  return thread.buildActiveChain();
}
