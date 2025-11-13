import 'package:flutter/material.dart';
import '../models/conversation.dart';
import '../models/role_preset.dart';
import '../models/custom_role.dart';

/// 会话列表侧边栏（按角色分组）
class ConversationDrawer extends StatelessWidget {
  final List<Conversation> conversations;
  final List<CustomRole> customRoles;
  final String? currentConversationId;
  final Function(String) onConversationSelected;
  final Function() onNewConversation;
  final Function(Conversation) onDeleteConversation;
  final Function(Conversation) onRenameConversation;
  final Function(RolePreset) onNewConversationWithRole;
  final Function(CustomRole) onNewConversationWithCustomRole;
  final Function() onManageCustomRoles;

  const ConversationDrawer({
    super.key,
    required this.conversations,
    required this.customRoles,
    required this.currentConversationId,
    required this.onConversationSelected,
    required this.onNewConversation,
    required this.onDeleteConversation,
    required this.onRenameConversation,
    required this.onNewConversationWithRole,
    required this.onNewConversationWithCustomRole,
    required this.onManageCustomRoles,
  });

  @override
  Widget build(BuildContext context) {
    // 按角色分组会话
    final groupedConversations = _groupByRole(conversations);
    
    // 计算实际显示的会话数（排除被删除角色的对话）
    final displayedConversationsCount = groupedConversations.values
        .fold<int>(0, (sum, group) => sum + group.conversations.length);

    return Drawer(
      child: Column(
        children: [
          // 头部
          DrawerHeader(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  Theme.of(context).colorScheme.primaryContainer,
                  Theme.of(context).colorScheme.secondaryContainer,
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Text(
                  'AI ChatBox',
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                ),
                const SizedBox(height: 8),
                Text(
                  '$displayedConversationsCount 个会话',
                  style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                        color: Theme.of(context)
                            .colorScheme
                            .onPrimaryContainer
                            .withValues(alpha: 0.7),
                      ),
                ),
              ],
            ),
          ),

          // 角色分组列表
          Expanded(
            child: ListView(
              children: [
                // 遍历所有角色分组
                ...groupedConversations.entries.map((entry) {
                  final roleName = entry.key;
                  final roleIcon = entry.value.icon;
                  final convs = entry.value.conversations;

                  return _buildRoleGroup(
                    context,
                    roleName: roleName,
                    roleIcon: roleIcon,
                    conversations: convs,
                    onNewWithRole: entry.value.preset,
                    onNewWithCustomRole: entry.value.customRole,
                  );
                }),
                
                // 显示还没有会话的自定义角色
                ..._buildEmptyCustomRoles(context, groupedConversations),
              ],
            ),
          ),

          // 底部：自定义角色管理
          const Divider(height: 1),
          ListTile(
            leading: const Icon(Icons.person_add),
            title: const Text('自定义助手'),
            onTap: () {
              Navigator.pop(context);
              onManageCustomRoles();
            },
          ),
        ],
      ),
    );
  }

  /// 构建角色分组
  Widget _buildRoleGroup(
    BuildContext context, {
    required String roleName,
    required String roleIcon,
    required List<Conversation> conversations,
    RolePreset? onNewWithRole,
    CustomRole? onNewWithCustomRole,
  }) {
    return ExpansionTile(
      leading: Text(roleIcon, style: const TextStyle(fontSize: 24)),
      title: Row(
        children: [
          Expanded(
            child: Text(
              roleName,
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
      subtitle: Text('${conversations.length} 个对话'),
      initiallyExpanded: conversations.any((c) => c.id == currentConversationId),
      children: [
        // 新建对话按钮
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          child: OutlinedButton.icon(
            onPressed: () {
              Navigator.pop(context);
              if (onNewWithRole != null) {
                onNewConversationWithRole(onNewWithRole);
              } else if (onNewWithCustomRole != null) {
                onNewConversationWithCustomRole(onNewWithCustomRole);
              } else {
                onNewConversation();
              }
            },
            icon: const Icon(Icons.add, size: 16),
            label: const Text('新建对话'),
            style: OutlinedButton.styleFrom(
              minimumSize: const Size(double.infinity, 36),
            ),
          ),
        ),
        // 该角色下的所有会话
        ...conversations.map((conv) => _buildConversationTile(context, conv)),
      ],
    );
  }

  /// 构建会话磁贴
  Widget _buildConversationTile(BuildContext context, Conversation conv) {
    final isSelected = conv.id == currentConversationId;

    return ListTile(
      selected: isSelected,
      contentPadding: const EdgeInsets.only(left: 72, right: 16),
      title: Text(
        conv.title,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: Text(
        conv.lastMessagePreview,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: TextStyle(
          fontSize: 12,
          color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.6),
        ),
      ),
      trailing: PopupMenuButton<String>(
        icon: const Icon(Icons.more_vert, size: 20),
        onSelected: (value) {
          switch (value) {
            case 'rename':
              onRenameConversation(conv);
              break;
            case 'delete':
              _confirmDelete(context, conv);
              break;
          }
        },
        itemBuilder: (context) => [
          const PopupMenuItem(
            value: 'rename',
            child: Row(
              children: [
                Icon(Icons.edit, size: 18),
                SizedBox(width: 8),
                Text('重命名'),
              ],
            ),
          ),
          const PopupMenuItem(
            value: 'delete',
            child: Row(
              children: [
                Icon(Icons.delete, size: 18),
                SizedBox(width: 8),
                Text('删除'),
              ],
            ),
          ),
        ],
      ),
      onTap: () {
        onConversationSelected(conv.id);
        Navigator.pop(context);
      },
    );
  }

  /// 构建还没有会话的自定义角色
  List<Widget> _buildEmptyCustomRoles(
    BuildContext context,
    Map<String, _RoleGroup> existingGroups,
  ) {
    final emptyRoles = <Widget>[];

    for (var customRole in customRoles) {
      // 检查这个自定义角色是否已经有会话了
      if (!existingGroups.containsKey(customRole.name)) {
        emptyRoles.add(
          _buildRoleGroup(
            context,
            roleName: customRole.name,
            roleIcon: customRole.icon,
            conversations: [],
            onNewWithCustomRole: customRole,
          ),
        );
      }
    }

    return emptyRoles;
  }

  /// 按角色分组会话（优化版：使用 roleId 匹配）
  Map<String, _RoleGroup> _groupByRole(List<Conversation> conversations) {
    final groups = <String, _RoleGroup>{};

    for (var conv in conversations) {
      String roleName;
      String roleIcon;
      RolePreset? preset;
      CustomRole? customRole;

      // 🔥 新逻辑：优先使用 roleId 和 roleType 精确匹配
      if (conv.roleId != null && conv.roleType != null) {
        if (conv.roleType == 'preset') {
          // 匹配内置角色
          final matchedPreset = RolePresets.presets.firstWhere(
            (p) => p.id == conv.roleId,
            orElse: () => RolePresets.presets.first,
          );
          
          if (matchedPreset.id == conv.roleId) {
            roleName = matchedPreset.name;
            roleIcon = matchedPreset.icon;
            preset = matchedPreset;
          } else {
            // 角色已删除，使用默认
            roleName = '默认助手';
            roleIcon = '🤖';
            preset = RolePresets.presets.first;
          }
        } else if (conv.roleType == 'custom') {
          // 匹配自定义角色
          final matchedCustom = customRoles.firstWhere(
            (r) => r.id == conv.roleId,
            orElse: () => CustomRole(
              id: '',
              name: '',
              description: '',
              systemPrompt: '',
              icon: '',
            ),
          );

          if (matchedCustom.id == conv.roleId) {
            roleName = matchedCustom.name;
            roleIcon = matchedCustom.icon;
            customRole = matchedCustom;
          } else {
            // 🔴 自定义角色已被删除，跳过此对话（不显示）
            continue;
          }
        } else {
          // 未知类型，使用默认
          roleName = '默认助手';
          roleIcon = '🤖';
          preset = RolePresets.presets.first;
        }
      } else {
        // 🔥 兼容旧数据：使用 systemPrompt 匹配（向后兼容）
        if (conv.systemPrompt != null && conv.systemPrompt!.isNotEmpty) {
          // 先查找内置角色
          final matchedPreset = RolePresets.presets.firstWhere(
            (p) => p.systemPrompt == conv.systemPrompt,
            orElse: () => RolePresets.presets.first,
          );

          if (matchedPreset.systemPrompt == conv.systemPrompt) {
            // 匹配到内置角色
            roleName = matchedPreset.name;
            roleIcon = matchedPreset.icon;
            preset = matchedPreset;
          } else {
            // 查找自定义角色
            final matchedCustom = customRoles.firstWhere(
              (r) => r.systemPrompt == conv.systemPrompt,
              orElse: () => CustomRole(
                id: '',
                name: '',
                description: '',
                systemPrompt: '',
                icon: '❓',
              ),
            );

            if (matchedCustom.id.isNotEmpty) {
              roleName = matchedCustom.name;
              roleIcon = matchedCustom.icon;
              customRole = matchedCustom;
            } else {
              // 🔴 未匹配到任何角色，跳过此对话（不显示）
              continue;
            }
          }
        } else {
          // 默认角色
          roleName = '默认助手';
          roleIcon = '🤖';
          preset = RolePresets.presets.first;
        }
      }

      if (!groups.containsKey(roleName)) {
        groups[roleName] = _RoleGroup(
          icon: roleIcon,
          conversations: [],
          preset: preset,
          customRole: customRole,
        );
      }

      groups[roleName]!.conversations.add(conv);
    }

    return groups;
  }

  /// 确认删除对话框
  void _confirmDelete(BuildContext context, Conversation conv) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('删除会话'),
        content: Text('确定要删除"${conv.title}"吗？此操作无法撤销。'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(context);
              onDeleteConversation(conv);
            },
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('删除'),
          ),
        ],
      ),
    );
  }
}

/// 角色分组数据
class _RoleGroup {
  final String icon;
  final List<Conversation> conversations;
  final RolePreset? preset;
  final CustomRole? customRole;

  _RoleGroup({
    required this.icon,
    required this.conversations,
    this.preset,
    this.customRole,
  });
}
