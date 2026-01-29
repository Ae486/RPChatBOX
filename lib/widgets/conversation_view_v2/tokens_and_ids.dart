/// INPUT: TokenCounter, ConversationViewV2State.message/metadata
/// OUTPUT: _newMessageId(), _estimatePromptTokens(), _buildTokenFooter() - 被 streaming/build 调用
/// POS: UI 层 / Chat / V2 - Token/ID 子模块（影响稳定性与统计口径）

part of '../conversation_view_v2.dart';

mixin _ConversationViewV2TokensMixin on _ConversationViewV2StateBase {
  int _estimatePromptTokens(List<ai.ChatMessage> messages) {
    // Best-effort estimate: message content + small per-message overhead.
    var total = 0;
    for (final m in messages) {
      final json = m.toJson();
      final content = json['content'];
      if (content is String) {
        total += TokenCounter.estimateTokens(content);
      } else if (content is List) {
        for (final item in content) {
          if (item is Map && item['type'] == 'text') {
            total += TokenCounter.estimateTokens(
              (item['text'] ?? '').toString(),
            );
          }
        }
      }
      total += 4; // role/format overhead (rough)
    }
    return total + 2; // assistant priming (rough)
  }

  String _newMessageId() {
    // Avoid collisions between user message id and assistant placeholder id.
    // `millisecondsSinceEpoch` is not enough when both are created in the same tick.
    return '${DateTime.now().microsecondsSinceEpoch}_${_v2MessageIdSeq++}';
  }

  Widget _buildTokenFooter(chat.Message message, {required bool isSentByMe}) {
    final meta = message.metadata ?? const <String, dynamic>{};
    if (meta['streaming'] == true) return const SizedBox.shrink();
    final input = meta['inputTokens'];
    final output = meta['outputTokens'];

    final inputTokens = input is int ? input : 0;
    final outputTokens = output is int ? output : 0;
    if (inputTokens == 0 && outputTokens == 0) return const SizedBox.shrink();

    final total = inputTokens + outputTokens;
    final uiScale = context.owui.uiScale;
    // 统一左对齐，与消息内容左侧对齐
    // 对于助手消息：与 OwuiAssistantMessage 内部 padding 对齐（12 * uiScale）
    // 对于用户消息：右对齐，与用户气泡对齐
    return Padding(
      padding: EdgeInsets.only(top: 8 * uiScale, left: isSentByMe ? 0 : 12 * uiScale),
      child: Align(
        alignment: isSentByMe ? Alignment.centerRight : Alignment.centerLeft,
        child: Text(
          'Tokens:$total ↑$inputTokens ↓$outputTokens',
          style: TextStyle(
            fontSize: 11 * uiScale,
            height: 1.2,
            color: OwuiPalette.textSecondary(context).withValues(alpha: 0.85),
          ),
        ),
      ),
    );
  }
}
