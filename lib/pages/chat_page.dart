/// INPUT: ChatSessionProvider + IndexedStack 状态保持
/// OUTPUT: ChatPage - 应用主页面（Drawer + Chat 视图 + 搜索/设置等入口）
/// POS: UI 层 / Pages - Home（路由入口）

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';

import '../chat_ui/owui/components/owui_dialog.dart';
import '../chat_ui/owui/components/owui_menu.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../models/conversation.dart';
import '../providers/chat_session_provider.dart';
import '../utils/token_counter.dart';
import '../widgets/conversation_drawer.dart';
import '../widgets/conversation_view_host.dart';
import '../utils/global_toast.dart';
import '../main.dart';
import 'settings_page.dart';
import 'search_page.dart';
import 'custom_roles_page.dart';

/// 对话页面（使用 IndexedStack 保持会话状态）
class ChatPage extends StatefulWidget {
  const ChatPage({super.key});

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  /// 为每个会话维护独立的 GlobalKey，确保 IndexedStack 中的 widget 状态保持
  final Map<String, GlobalKey<ConversationViewHostState>> _conversationKeys = {};

  @override
  void initState() {
    super.initState();
    _initSystemUiMode();
  }

  Future<void> _initSystemUiMode() async {
    await SystemChrome.setEnabledSystemUIMode(
      SystemUiMode.manual,
      overlays: SystemUiOverlay.values,
    );
    await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  }

  /// 获取或创建会话的 GlobalKey
  GlobalKey<ConversationViewHostState> _getKeyForConversation(String conversationId) {
    return _conversationKeys.putIfAbsent(
      conversationId,
      () => GlobalKey<ConversationViewHostState>(),
    );
  }

  /// 清理已删除会话的 keys
  void _cleanupKeys(List<Conversation> conversations) {
    final activeIds = conversations.map((c) => c.id).toSet();
    _conversationKeys.removeWhere((id, _) => !activeIds.contains(id));
  }

  /// 获取当前会话的 key（用于外部调用如搜索跳转）
  GlobalKey<ConversationViewHostState>? _getCurrentKey(String? conversationId) {
    if (conversationId == null) return null;
    return _conversationKeys[conversationId];
  }

  /// Rename Conversation Dialog
  Future<void> _renameConversation(BuildContext context, Conversation conversation) async {
    final controller = TextEditingController(text: conversation.title);
    
    final newTitle = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('重命名会话'),
        content: TextField(
          controller: controller,
          decoration: const InputDecoration(
            labelText: '会话名称',
            border: OutlineInputBorder(),
          ),
          autofocus: true,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('确定'),
          ),
        ],
      ),
    );

    if (newTitle != null && newTitle.isNotEmpty && mounted) {
      final provider = context.read<ChatSessionProvider>();
      await provider.renameConversation(conversation.id, newTitle);
    }
  }

  /// Clear Chat Dialog
  Future<void> _clearCurrentChat(BuildContext context) async {
    final provider = context.read<ChatSessionProvider>();
    final conversation = provider.currentConversation;
    if (conversation == null) return;
    final currentKey = _getCurrentKey(conversation.id);

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('清空对话'),
        content: Text('确定要清空"${conversation.title}"的所有消息吗？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('确定'),
          ),
        ],
      ),
    );

    if (confirmed == true && mounted) {
      await provider.clearCurrentMessages();
      await currentKey?.currentState?.refreshFromBackend();
    }
  }

  /// Delete Conversation Dialog
  Future<void> _deleteConversation(BuildContext context, Conversation conversation) async {
    final provider = context.read<ChatSessionProvider>();
    // If only one left, warn
    if (provider.conversations.length <= 1) {
      GlobalToast.warning(context, message: '至少需要保留一个会话');
      return;
    }

    // The confirmation dialog is already handled in ConversationDrawer's _confirmDelete usually, 
    // but the callback passed to Drawer expects to just do the action.
    await provider.deleteConversation(conversation.id);
  }

  /// Show Token Stats
  void _showTokenStats(BuildContext context) {
    final provider = context.read<ChatSessionProvider>();
    final tokenUsage = provider.tokenUsage;
    final conversation = provider.currentConversation;

    // Calculate current conversation tokens (approx)
    int currentConvTokens = 0;
    if (conversation != null) {
      for (var msg in conversation.messages) {
          currentConvTokens += TokenCounter.estimateTokens(msg.content);
      }
    }

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.analytics),
            SizedBox(width: 8),
            Text('Token 统计'),
          ],
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _buildStatRow(context, '当前会话', TokenCounter.formatTokens(currentConvTokens)),
              const Divider(),
              _buildStatRow(context, '总输入', TokenCounter.formatTokens(tokenUsage.inputTokens)),
              _buildStatRow(context, '总输出', TokenCounter.formatTokens(tokenUsage.outputTokens)),
              _buildStatRow(
                context,
                '总计',
                TokenCounter.formatTokens(tokenUsage.totalTokens),
                isBold: true,
              ),
              const Divider(),
              _buildStatRow(
                context,
                '费用估算 (USD)',
                TokenCounter.formatCost(tokenUsage.totalCost),
              ),
              _buildStatRow(
                context,
                '费用估算 (CNY)',
                TokenCounter.formatCostCNY(tokenUsage.totalCost),
              ),
              const SizedBox(height: 16),
              Text(
                '💡 注意：Token 统计为估算值，实际消耗以 API 账单为准',
                style: TextStyle(
                  fontSize: 12,
                  color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.6),
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () {
              provider.resetTokenStats();
              Navigator.pop(context);
              GlobalToast.success(context, message: '统计已重置');
            },
            child: const Text('重置'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('关闭'),
          ),
        ],
      ),
    );
  }

  Widget _buildStatRow(BuildContext context, String label, String value, {bool isBold = false}) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: TextStyle(
              fontSize: isBold ? 16 : 14,
              fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
            ),
          ),
          Text(
            value,
            style: TextStyle(
              fontSize: isBold ? 18 : 15,
              fontWeight: isBold ? FontWeight.bold : FontWeight.normal,
              color: Theme.of(context).colorScheme.primary,
            ),
          ),
        ],
      ),
    );
  }

  /// Theme Dialog
  void _showThemeDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => OwuiDialog(
        title: const Text('选择主题'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            RadioListTile<ThemeMode>(
              title: const Text('浅色模式'),
              value: ThemeMode.light,
              groupValue: Theme.of(context).brightness == Brightness.light 
                  ? ThemeMode.light 
                  : ThemeMode.dark,
              onChanged: (value) {
                Navigator.pop(context);
                if (value != null) {
                  MyApp.of(context)?.setThemeMode(value);
                }
              },
            ),
            RadioListTile<ThemeMode>(
              title: const Text('深色模式'),
              value: ThemeMode.dark,
              groupValue: Theme.of(context).brightness == Brightness.dark 
                  ? ThemeMode.dark 
                  : ThemeMode.light,
              onChanged: (value) {
                Navigator.pop(context);
                if (value != null) {
                  MyApp.of(context)?.setThemeMode(value);
                }
              },
            ),
            RadioListTile<ThemeMode>(
              title: const Text('跟随系统'),
              value: ThemeMode.system,
              groupValue: ThemeMode.system,
              onChanged: (value) {
                Navigator.pop(context);
                if (value != null) {
                  MyApp.of(context)?.setThemeMode(value);
                }
              },
            ),
          ],
        ),
      ),
    );
  }

  /// Open Search
  Future<void> _openSearch(BuildContext context) async {
    final provider = context.read<ChatSessionProvider>();
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => SearchPage(
          conversations: provider.conversations,
          onResultTap: (conversationId, messageId) async {
            await provider.switchConversation(conversationId);

            if (messageId != null) {
               // Wait for the view to build
               await Future.delayed(const Duration(milliseconds: 300));
               _getCurrentKey(conversationId)?.currentState?.scrollToMessage(messageId);
            }
          },
        ),
      ),
    );
  }

  /// Open Custom Roles
  Future<void> _openCustomRoles(BuildContext context) async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => const CustomRolesPage(),
      ),
    );
    if (mounted) {
      context.read<ChatSessionProvider>().reloadCustomRoles();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<ChatSessionProvider>(
      builder: (context, provider, child) {
        if (provider.isLoading) {
           return Scaffold(
            body: Center(
              child: SpinKitFadingCircle(
                color: Theme.of(context).colorScheme.primary,
                size: 50.0,
              ),
            ),
          );
        }

        final conversations = provider.conversations;
        final currentConversation = provider.currentConversation;

        // 清理已删除会话的 keys
        _cleanupKeys(conversations);

        // 计算当前会话在列表中的索引
        final currentIndex = currentConversation != null
            ? conversations.indexWhere((c) => c.id == currentConversation.id)
            : 0;
        final safeIndex = currentIndex >= 0 ? currentIndex : 0;

        // 获取当前会话的 key（用于菜单操作）
        final currentKey = currentConversation != null
            ? _getKeyForConversation(currentConversation.id)
            : null;

        return Scaffold(
          appBar: AppBar(
            title: Text(currentConversation?.title ?? 'ChatBox'),
            actions: [
              IconButton(
                icon: const Icon(OwuiIcons.search),
                onPressed: () => _openSearch(context),
                tooltip: '搜索',
              ),
              OwuiMenuButton<String>(
                icon: const Icon(OwuiIcons.moreVert),
                onSelected: (value) {
                  switch (value) {
                    case 'token_stats':
                      _showTokenStats(context);
                      break;
                    case 'theme':
                      _showThemeDialog(context);
                      break;
                    case 'clear':
                      _clearCurrentChat(context);
                      break;
                    case 'settings':
                      Navigator.push(context, MaterialPageRoute(builder: (_) => const SettingsPage()));
                      break;
                    case 'streaming_tuning':
                      currentKey?.currentState?.showTuningPanel();
                      break;
                  }
                },
                itemBuilder: (context) => [
                  const PopupMenuItem(
                    value: 'token_stats',
                    child: Row(
                      children: [
                        Icon(OwuiIcons.analytics, size: 20),
                        SizedBox(width: 8),
                        Text('Token 统计'),
                      ],
                    ),
                  ),
                  const PopupMenuItem(
                    value: 'theme',
                    child: Row(
                      children: [
                        Icon(OwuiIcons.palette, size: 20),
                        SizedBox(width: 8),
                        Text('主题切换'),
                      ],
                    ),
                  ),
                  const PopupMenuItem(
                    value: 'clear',
                    child: Row(
                      children: [
                        Icon(OwuiIcons.delete, size: 20),
                        SizedBox(width: 8),
                        Text('清空对话'),
                      ],
                    ),
                  ),
                  const PopupMenuItem(
                    value: 'settings',
                    child: Row(
                      children: [
                        Icon(OwuiIcons.settings, size: 20),
                        SizedBox(width: 8),
                        Text('设置'),
                      ],
                    ),
                  ),
                  const PopupMenuItem(
                    value: 'streaming_tuning',
                    child: Row(
                      children: [
                        Icon(OwuiIcons.tune, size: 20),
                        SizedBox(width: 8),
                        Text('流式调试'),
                      ],
                    ),
                  ),
                ],
              ),
            ],
          ),
          drawer: ConversationDrawer(
            conversations: conversations,
            customRoles: provider.customRoles,
            currentConversationId: currentConversation?.id,
            onConversationSelected: (id) {
               provider.switchConversation(id);
            },
            onNewConversation: () {
               provider.createNewConversation();
            },
            onNewConversationWithRole: (role) {
               provider.createNewConversation(rolePreset: role);
            },
            onNewConversationWithCustomRole: (role) {
               provider.createNewConversation(customRole: role);
            },
            onDeleteConversation: (c) => _deleteConversation(context, c),
            onRenameConversation: (c) => _renameConversation(context, c),
            onManageCustomRoles: () => _openCustomRoles(context),
          ),
          // 使用 IndexedStack 保持所有会话的 widget 状态
          body: conversations.isEmpty
              ? const Center(child: Text("No Conversation"))
              : IndexedStack(
                  index: safeIndex,
                  children: conversations.map((conversation) {
                    return ConversationViewHost(
                      key: _getKeyForConversation(conversation.id),
                      conversation: conversation,
                      settings: provider.settings,
                      onConversationUpdated: () => provider.saveCurrentConversation(),
                      onTokenUsageUpdated: (conv) {
                        if (conv.messages.isNotEmpty) {
                          final lastMessage = conv.messages.last;
                          if (!lastMessage.isUser) {
                            final input = lastMessage.inputTokens ?? 0;
                            final output = lastMessage.outputTokens ?? 0;
                            provider.updateTokenUsage(input, output);
                          }
                        }
                      },
                    );
                  }).toList(),
                ),
        );
      },
    );
  }
}
