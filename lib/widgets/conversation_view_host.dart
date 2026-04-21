/// INPUT: Conversation + ChatSettings + 回调（更新会话/Token 使用）
/// OUTPUT: ConversationViewHost - 统一承载聊天视图（当前固定委派到 V2）
/// POS: UI 层 / Widgets - ChatPage 中的 per-conversation 视图宿主（保活 keep-alive）

import 'package:flutter/material.dart';

import '../models/chat_settings.dart';
import '../models/conversation.dart';
import 'conversation_view_v2.dart';

class ConversationViewHost extends StatefulWidget {
  final Conversation conversation;
  final ChatSettings settings;
  final VoidCallback onConversationUpdated;
  final Function(Conversation) onTokenUsageUpdated;

  const ConversationViewHost({
    super.key,
    required this.conversation,
    required this.settings,
    required this.onConversationUpdated,
    required this.onTokenUsageUpdated,
  });

  @override
  State<ConversationViewHost> createState() => ConversationViewHostState();
}

class ConversationViewHostState extends State<ConversationViewHost>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  final GlobalKey<ConversationViewV2State> _v2Key = GlobalKey<ConversationViewV2State>();

  void scrollToMessage(String messageId) {
    _v2Key.currentState?.scrollToMessage(messageId);
  }

  void enterExportMode() {
    _v2Key.currentState?.enterExportMode();
  }

  /// 显示流式渲染参数调试面板（仅 V2）
  void showTuningPanel() {
    _v2Key.currentState?.showTuningPanel();
  }

  Future<void> refreshFromBackend() async {
    await _v2Key.currentState?.refreshFromBackend();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    return ConversationViewV2(
      key: _v2Key,
      conversation: widget.conversation,
      settings: widget.settings,
      onConversationUpdated: widget.onConversationUpdated,
      onTokenUsageUpdated: widget.onTokenUsageUpdated,
    );
  }
}
