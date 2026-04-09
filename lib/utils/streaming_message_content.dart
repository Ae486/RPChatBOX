/// 组装 finalize 后的 assistant 消息内容。
String buildStreamingFinalContent({
  required String thinking,
  required String body,
  String? errorTag,
}) {
  var finalContent = thinking.trim().isNotEmpty
      ? '<think>$thinking</think>$body'
      : body;

  if (errorTag != null) {
    finalContent = finalContent.isEmpty
        ? errorTag
        : '$finalContent\n$errorTag';
  }

  return finalContent;
}

/// 判断 finalize 后是否应保留占位消息并落盘。
bool shouldPersistFinalizedStreamingMessage(String finalContent) {
  return finalContent.trim().isNotEmpty;
}
