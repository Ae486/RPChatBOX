import 'package:flutter/material.dart';

import '../models/chat_settings.dart';
import '../models/conversation.dart';
import 'conversation_view.dart';
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

  final GlobalKey<ConversationViewState> _v1Key = GlobalKey<ConversationViewState>();
  final GlobalKey<ConversationViewV2State> _v2Key = GlobalKey<ConversationViewV2State>();

  void scrollToMessage(String messageId) {
    if (widget.settings.enableChatUiV2) {
      _v2Key.currentState?.scrollToMessage(messageId);
    } else {
      _v1Key.currentState?.scrollToMessage(messageId);
    }
  }

  void enterExportMode() {
    if (widget.settings.enableChatUiV2) {
      _v2Key.currentState?.enterExportMode();
    } else {
      _v1Key.currentState?.enterExportMode();
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    if (widget.settings.enableChatUiV2) {
      return ConversationViewV2(
        key: _v2Key,
        conversation: widget.conversation,
        settings: widget.settings,
        onConversationUpdated: widget.onConversationUpdated,
        onTokenUsageUpdated: widget.onTokenUsageUpdated,
      );
    }

    return ConversationView(
      key: _v1Key,
      conversation: widget.conversation,
      settings: widget.settings,
      onConversationUpdated: widget.onConversationUpdated,
      onTokenUsageUpdated: widget.onTokenUsageUpdated,
    );
  }
}
