import 'package:flutter/material.dart';
import '../design_system/apple_icons.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';
import '../models/chat_settings.dart';
import '../models/conversation.dart';
import '../models/role_preset.dart';
import '../models/custom_role.dart';
import '../services/storage_service.dart';
import '../services/hive_conversation_service.dart';
import '../services/custom_role_service.dart';
import '../utils/token_counter.dart';
import '../widgets/conversation_drawer.dart';
import '../widgets/conversation_view.dart';
import '../widgets/apple_toast.dart';
import '../main.dart';
import 'settings_page.dart';
import 'search_page.dart';
import 'custom_roles_page.dart';

/// 对话页面（使用 IndexedStack 优化）
class ChatPage extends StatefulWidget {
  const ChatPage({super.key});

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final _storageService = StorageService();
  late HiveConversationService _conversationService;
  final _customRoleService = CustomRoleService();

  List<Conversation> _conversations = [];
  List<CustomRole> _customRoles = [];
  late List<GlobalKey<ConversationViewState>> _conversationKeys; // GlobalKey 列表
  int _currentIndex = 0;
  ChatSettings _settings = ChatSettings();
  TokenUsage _tokenUsage = TokenUsage();

  @override
  void initState() {
    super.initState();
    _initServices();
  }
  
  /// 初始化服务
  Future<void> _initServices() async {
    _conversationService = HiveConversationService();
    await _conversationService.initialize();
    await _loadData();
  }

  @override
  void dispose() {
    // ScrollController 已移除，无需释放
    super.dispose();
  }

  /// 加载数据
  Future<void> _loadData() async {
    final settings = await _storageService.loadSettings();
    final conversations = await _conversationService.loadConversations();
    final currentId = await _conversationService.loadCurrentConversationId();
    final tokenUsage = await _storageService.loadTokenUsage();
    final customRoles = await _customRoleService.loadCustomRoles();

    setState(() {
      _settings = settings;
      _conversations = conversations;
      _tokenUsage = tokenUsage;
      _customRoles = customRoles;
      
      // 为每个会话创建独立的 GlobalKey
      _conversationKeys = List.generate(
        conversations.length,
        (_) => GlobalKey<ConversationViewState>(),
      );
      
      // 恢复当前会话索引
      if (currentId != null) {
        _currentIndex = conversations.indexWhere((c) => c.id == currentId);
        if (_currentIndex < 0) _currentIndex = 0;
      }
    });

    await _conversationService.saveCurrentConversationId(_conversations[_currentIndex].id);
  }

  /// 切换会话
  Future<void> _switchConversation(String conversationId) async {
    final index = _conversations.indexWhere((c) => c.id == conversationId);
    if (index < 0) return;
    
    setState(() {
      _currentIndex = index;
    });

    await _conversationService.saveCurrentConversationId(conversationId);
  }

  /// 新建会话
  Future<void> _createNewConversation({RolePreset? rolePreset, CustomRole? customRole}) async {
    String? title;
    String? systemPrompt;
    String? roleId;
    String? roleType;

    if (rolePreset != null) {
      title = rolePreset.name;
      systemPrompt = rolePreset.systemPrompt;
      roleId = rolePreset.id;
      roleType = 'preset';
    } else if (customRole != null) {
      title = customRole.name;
      systemPrompt = customRole.systemPrompt;
      roleId = customRole.id;
      roleType = 'custom';
    }

    final newConv = _conversationService.createConversation(
      title: title,
      systemPrompt: systemPrompt,
      roleId: roleId,
      roleType: roleType,
    );

    setState(() {
      _conversations.add(newConv);
      _conversationKeys.add(GlobalKey<ConversationViewState>());
      _currentIndex = _conversations.length - 1;
    });

    await _conversationService.saveConversations(_conversations);
    await _conversationService.saveCurrentConversationId(newConv.id);
  }

  /// 删除会话
  Future<void> _deleteConversation(Conversation conversation) async {
    if (_conversations.length == 1) {
      AppleToast.warning(context, message: '至少需要保留一个会话');
      return;
    }

    final index = _conversations.indexOf(conversation);
    if (index < 0) return;

    setState(() {
      _conversations.removeAt(index);
      _conversationKeys.removeAt(index);
      
      if (_currentIndex >= _conversations.length) {
        _currentIndex = _conversations.length - 1;
      }
    });

    await _conversationService.saveConversations(_conversations);
    await _conversationService.saveCurrentConversationId(_conversations[_currentIndex].id);
  }

  /// 重命名会话
  Future<void> _renameConversation(Conversation conversation) async {
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

    if (newTitle != null && newTitle.isNotEmpty) {
      setState(() {
        conversation.title = newTitle;
      });
      await _conversationService.saveConversations(_conversations);
    }
  }

  /// 清空当前对话
  Future<void> _clearCurrentChat() async {
    final conversation = _conversations[_currentIndex];

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

    if (confirmed == true) {
      setState(() {
        conversation.clearMessages();
      });
      await _conversationService.saveConversations(_conversations);
    }
  }

  /// 保存会话
  Future<void> _saveConversations() async {
    await _conversationService.saveConversations(_conversations);
  }

  /// 更新 Token 使用量
  void _updateTokenUsage(Conversation conversation) {
    if (conversation.messages.isNotEmpty) {
      final lastMessage = conversation.messages.last;
      if (!lastMessage.isUser) {
        final inputTokens = lastMessage.inputTokens ?? 0;
        final outputTokens = lastMessage.outputTokens ?? 0;
        final cost = TokenCounter.estimateCost(inputTokens, _settings.model, isOutput: false) +
                     TokenCounter.estimateCost(outputTokens, _settings.model, isOutput: true);
        
    setState(() {
          _tokenUsage.addUsage(inputTokens, outputTokens, cost);
        });
        _storageService.saveTokenUsage(_tokenUsage);
      }
    }
  }

  /// 显示 Token 统计
  void _showTokenStats() {
    // 计算当前会话的 token
    int currentConvTokens = 0;
    final conversation = _conversations[_currentIndex];
    for (var msg in conversation.messages) {
        currentConvTokens += TokenCounter.estimateTokens(msg.content);
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
              _buildStatRow('当前会话', TokenCounter.formatTokens(currentConvTokens)),
              const Divider(),
              _buildStatRow('总输入', TokenCounter.formatTokens(_tokenUsage.inputTokens)),
              _buildStatRow('总输出', TokenCounter.formatTokens(_tokenUsage.outputTokens)),
              _buildStatRow(
                '总计',
                TokenCounter.formatTokens(_tokenUsage.totalTokens),
                isBold: true,
              ),
              const Divider(),
              _buildStatRow(
                '费用估算 (USD)',
                TokenCounter.formatCost(_tokenUsage.totalCost),
              ),
              _buildStatRow(
                '费用估算 (CNY)',
                TokenCounter.formatCostCNY(_tokenUsage.totalCost),
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
            onPressed: () => _resetTokenStats(context),
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

  /// 重置 Token 统计
  Future<void> _resetTokenStats(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('重置统计'),
        content: const Text('确定要清空所有 Token 统计数据吗？'),
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
      setState(() {
        _tokenUsage.reset();
      });
      await _storageService.saveTokenUsage(_tokenUsage);
      
      if (mounted) {
        Navigator.pop(context);
        AppleToast.success(context, message: '统计已重置');
      }
    }
  }

  /// 构建统计行
  Widget _buildStatRow(String label, String value, {bool isBold = false}) {
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

  /// 打开搜索页面
  Future<void> _openSearch() async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => SearchPage(
          conversations: _conversations,
          onResultTap: (conversationId, messageId) async {
            debugPrint('🔍 搜索跳转: conversationId=$conversationId, messageId=$messageId');
            
            // 步骤 1: 切换到目标会话
            await _switchConversation(conversationId);
            debugPrint('✅ 会话已切换到索引: $_currentIndex');
            
            // 步骤 2: 如果有 messageId，滚动到该消息
            if (messageId != null) {
              // 🔥 使用 ItemScrollController 后，只需简单延迟即可
              await Future.delayed(const Duration(milliseconds: 300));
              
              // 调用滚动方法（100% 可靠）
              _conversationKeys[_currentIndex].currentState?.scrollToMessage(messageId);
            }
          },
        ),
      ),
    );
  }

  /// 进入导出模式
  void _enterExportMode() {
    _conversationKeys[_currentIndex].currentState?.enterExportMode();
  }

  /// 打开自定义角色页面
  Future<void> _openCustomRoles() async {
    // 🔧 修复：从 ConversationDrawer 点击时会自动关闭 Drawer（见 conversation_drawer.dart 第109行）
    // 所以这里不需要手动关闭
    
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => const CustomRolesPage(),
      ),
    );
    
    // 🔥 关键修复：重新加载自定义角色和对话列表
    // 因为删除角色时会级联删除对话，所以必须同步更新
    final customRoles = await _customRoleService.loadCustomRoles();
    final conversations = await _conversationService.loadConversations();
    
    // 检查当前对话是否被删除
    final currentConv = _conversations[_currentIndex];
    final stillExists = conversations.any((c) => c.id == currentConv.id);
    
    // 🔧 关键优化：只更新被删除的对话的 keys，保留现有的 keys
    final oldConversationIds = _conversations.map((c) => c.id).toSet();
    final newConversationIds = conversations.map((c) => c.id).toSet();
    final deletedIds = oldConversationIds.difference(newConversationIds);
    
    // 构建新的 keys 列表，保留未被删除的对话的 key
    final oldKeysMap = <String, GlobalKey<ConversationViewState>>{};
    for (var i = 0; i < _conversations.length; i++) {
      if (!deletedIds.contains(_conversations[i].id)) {
        oldKeysMap[_conversations[i].id] = _conversationKeys[i];
      }
    }
    
    final newKeys = <GlobalKey<ConversationViewState>>[];
    for (var conv in conversations) {
      if (oldKeysMap.containsKey(conv.id)) {
        // 保留现有的 key，避免重建 widget
        newKeys.add(oldKeysMap[conv.id]!);
      } else {
        // 新对话，生成新 key
        newKeys.add(GlobalKey<ConversationViewState>());
      }
    }
    
    setState(() {
      _customRoles = customRoles;
      _conversations = conversations;
      _conversationKeys = newKeys;
      
      // 如果当前对话被删除，切换到第一个对话
      if (!stillExists) {
        _currentIndex = 0;
      } else {
        // 更新当前索引（因为对话列表可能变化）
        _currentIndex = conversations.indexWhere((c) => c.id == currentConv.id);
        if (_currentIndex < 0) _currentIndex = 0;
      }
    });
    
    // 保存当前对话 ID
    if (conversations.isNotEmpty) {
      await _conversationService.saveCurrentConversationId(conversations[_currentIndex].id);
    }
  }

  /// 显示主题切换对话框
  void _showThemeDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
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

  /// 打开设置页面
  Future<void> _openSettings() async {
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => const SettingsPage(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_conversations.isEmpty) {
      return Scaffold(
        body: Center(
          child: SpinKitFadingCircle(
            color: Theme.of(context).colorScheme.primary,
            size: 50.0,
          ),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: Text(_conversations[_currentIndex].title),
              actions: [
                IconButton(
                  icon: const Icon(AppleIcons.search),
                  onPressed: _openSearch,
                  tooltip: '搜索',
                ),
                PopupMenuButton<String>(
                  icon: const Icon(AppleIcons.moreVert),
                  onSelected: (value) {
                    switch (value) {
                      case 'token_stats':
                        _showTokenStats();
                        break;
                      case 'theme':
                        _showThemeDialog();
                        break;
                      case 'clear':
                        _clearCurrentChat();
                        break;
                      case 'settings':
                        _openSettings();
                        break;
                    }
                  },
                  itemBuilder: (context) => [
                    const PopupMenuItem(
                      value: 'token_stats',
                      child: Row(
                        children: [
                          Icon(Icons.analytics, size: 20),
                          SizedBox(width: 8),
                          Text('Token 统计'),
                        ],
                      ),
                    ),
                    const PopupMenuItem(
                      value: 'theme',
                      child: Row(
                        children: [
                          Icon(Icons.palette, size: 20),
                          SizedBox(width: 8),
                          Text('主题切换'),
                        ],
                      ),
                    ),
                    const PopupMenuItem(
                      value: 'clear',
                      child: Row(
                        children: [
                          Icon(AppleIcons.delete, size: 20),
                          SizedBox(width: 8),
                          Text('清空对话'),
                        ],
                      ),
                    ),
                    const PopupMenuItem(
                      value: 'settings',
                      child: Row(
                        children: [
                          Icon(AppleIcons.settings, size: 20),
                          SizedBox(width: 8),
                          Text('设置'),
                        ],
                      ),
                    ),
                  ],
                ),
              ],
            ),
      drawer: ConversationDrawer(
        conversations: _conversations,
        customRoles: _customRoles,
        currentConversationId: _conversations[_currentIndex].id,
        onConversationSelected: _switchConversation,
        onNewConversation: () => _createNewConversation(),
        onNewConversationWithRole: (role) => _createNewConversation(rolePreset: role),
        onNewConversationWithCustomRole: (customRole) => _createNewConversation(customRole: customRole),
        onDeleteConversation: _deleteConversation,
        onRenameConversation: _renameConversation,
        onManageCustomRoles: _openCustomRoles,
      ),
      body: IndexedStack(
        index: _currentIndex,
        children: _conversations.asMap().entries.map((entry) {
          return ConversationView(
            key: _conversationKeys[entry.key], // 使用 GlobalKey
            conversation: entry.value,
            settings: _settings,
            onConversationUpdated: _saveConversations,
            onTokenUsageUpdated: _updateTokenUsage,
          );
        }).toList(),
      ),
    );
  }
}

