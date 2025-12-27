import 'package:flutter/material.dart';

import '../chat_ui/owui/components/owui_card.dart';
import '../chat_ui/owui/components/owui_dialog.dart';
import '../chat_ui/owui/components/owui_menu.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../models/conversation.dart';
import '../models/custom_role.dart';
import '../models/role_preset.dart';

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
    final colors = context.owuiColors;
    final spacing = context.owuiSpacing;

    final groupedConversations = _groupByRole(conversations);

    final displayedConversationsCount = groupedConversations.values.fold<int>(
      0,
      (sum, group) => sum + group.conversations.length,
    );

    return Drawer(
      backgroundColor: colors.pageBg,
      child: Container(
        decoration: BoxDecoration(
          color: colors.pageBg,
          border: Border(right: BorderSide(color: colors.borderSubtle)),
        ),
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(
                spacing.lg,
                MediaQuery.paddingOf(context).top + spacing.lg,
                spacing.lg,
                spacing.lg,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('对话', style: Theme.of(context).textTheme.titleLarge),
                  SizedBox(height: spacing.xs),
                  Text(
                    '$displayedConversationsCount 个会话',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: colors.textSecondary,
                        ),
                  ),
                ],
              ),
            ),
            Divider(height: 1, color: colors.borderSubtle),
            Expanded(
              child: ListView(
                padding: EdgeInsets.symmetric(vertical: spacing.sm),
                children: [
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
                  ..._buildEmptyCustomRoles(context, groupedConversations),
                ],
              ),
            ),
            Divider(height: 1, color: colors.borderSubtle),
            ListTile(
              leading: Icon(
                OwuiIcons.personAdd,
                color: Theme.of(context).colorScheme.primary,
              ),
              title: const Text('自定义助手'),
              trailing: const Icon(OwuiIcons.chevronRight),
              onTap: () {
                Navigator.pop(context);
                onManageCustomRoles();
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRoleGroup(
    BuildContext context, {
    required String roleName,
    required String roleIcon,
    required List<Conversation> conversations,
    RolePreset? onNewWithRole,
    CustomRole? onNewWithCustomRole,
  }) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;
    final scale = context.owuiTokens.uiScale;

    return OwuiCard(
      margin: EdgeInsets.symmetric(horizontal: spacing.md, vertical: spacing.xs),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          leading: Text(roleIcon, style: TextStyle(fontSize: 22 * scale)),
          title: Text(
            roleName,
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
          subtitle: Text(
            '${conversations.length} 个会话',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: colors.textSecondary,
                ),
          ),
          tilePadding: EdgeInsets.symmetric(
            horizontal: spacing.lg,
            vertical: spacing.xs,
          ),
          initiallyExpanded:
              conversations.any((c) => c.id == currentConversationId),
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(
                spacing.lg,
                spacing.xs,
                spacing.lg,
                spacing.sm,
              ),
              child: SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
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
                  icon: const Icon(OwuiIcons.addCircle, size: 18),
                  label: const Text('新建对话'),
                ),
              ),
            ),
            ...conversations.map((conv) => _buildConversationTile(context, conv)),
          ],
        ),
      ),
    );
  }

  Widget _buildConversationTile(BuildContext context, Conversation conv) {
    final spacing = context.owuiSpacing;
    final colors = context.owuiColors;

    final isSelected = conv.id == currentConversationId;
    final selectedBg = Theme.of(context).colorScheme.primary.withValues(alpha: 0.10);

    return Container(
      margin: EdgeInsets.symmetric(horizontal: spacing.sm, vertical: 2),
      decoration: BoxDecoration(
        color: isSelected ? selectedBg : Colors.transparent,
        borderRadius: BorderRadius.circular(context.owuiRadius.rLg),
      ),
      child: ListTile(
        dense: true,
        contentPadding: EdgeInsets.only(left: spacing.lg, right: spacing.sm),
        title: Text(
          conv.title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
              ),
        ),
        subtitle: Text(
          conv.lastMessagePreview,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: colors.textSecondary,
              ),
        ),
        trailing: OwuiMenuButton<String>(
          icon: const Icon(OwuiIcons.moreVert, size: 18),
          itemBuilder: (context) => [
            PopupMenuItem(
              value: 'rename',
              child: Row(
                children: [
                  const Icon(OwuiIcons.edit, size: 18),
                  SizedBox(width: spacing.sm),
                  const Text('重命名'),
                ],
              ),
            ),
            PopupMenuItem(
              value: 'delete',
              child: Row(
                children: [
                  const Icon(OwuiIcons.delete, size: 18),
                  SizedBox(width: spacing.sm),
                  const Text('删除'),
                ],
              ),
            ),
          ],
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
        ),
        onTap: () {
          onConversationSelected(conv.id);
          Navigator.pop(context);
        },
      ),
    );
  }

  List<Widget> _buildEmptyCustomRoles(
    BuildContext context,
    Map<String, _RoleGroup> existingGroups,
  ) {
    final emptyRoles = <Widget>[];
    for (final customRole in customRoles) {
      if (!existingGroups.containsKey(customRole.name)) {
        emptyRoles.add(
          _buildRoleGroup(
            context,
            roleName: customRole.name,
            roleIcon: customRole.icon,
            conversations: const [],
            onNewWithCustomRole: customRole,
          ),
        );
      }
    }
    return emptyRoles;
  }

  Map<String, _RoleGroup> _groupByRole(List<Conversation> conversations) {
    final groups = <String, _RoleGroup>{};

    for (final conv in conversations) {
      String roleName;
      String roleIcon;
      RolePreset? preset;
      CustomRole? customRole;

      if (conv.roleId != null && conv.roleType != null) {
        if (conv.roleType == 'preset') {
          final matchedPreset = RolePresets.presets.firstWhere(
            (p) => p.id == conv.roleId,
            orElse: () => RolePresets.presets.first,
          );

          if (matchedPreset.id == conv.roleId) {
            roleName = matchedPreset.name;
            roleIcon = matchedPreset.icon;
            preset = matchedPreset;
          } else {
            roleName = '默认助手';
            roleIcon = '🤖';
            preset = RolePresets.presets.first;
          }
        } else if (conv.roleType == 'custom') {
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
            // 自定义角色已被删除：不显示该对话
            continue;
          }
        } else {
          roleName = '默认助手';
          roleIcon = '🤖';
          preset = RolePresets.presets.first;
        }
      } else {
        // 兼容旧数据：使用 systemPrompt 匹配
        if (conv.systemPrompt != null && conv.systemPrompt!.isNotEmpty) {
          final matchedPreset = RolePresets.presets.firstWhere(
            (p) => p.systemPrompt == conv.systemPrompt,
            orElse: () => RolePresets.presets.first,
          );

          if (matchedPreset.systemPrompt == conv.systemPrompt) {
            roleName = matchedPreset.name;
            roleIcon = matchedPreset.icon;
            preset = matchedPreset;
          } else {
            final matchedCustom = customRoles.firstWhere(
              (r) => r.systemPrompt == conv.systemPrompt,
              orElse: () => CustomRole(
                id: '',
                name: '',
                description: '',
                systemPrompt: '',
                icon: '',
              ),
            );

            if (matchedCustom.systemPrompt == conv.systemPrompt) {
              roleName = matchedCustom.name;
              roleIcon = matchedCustom.icon;
              customRole = matchedCustom;
            } else {
              roleName = '默认助手';
              roleIcon = '🤖';
              preset = RolePresets.presets.first;
            }
          }
        } else {
          roleName = '默认助手';
          roleIcon = '🤖';
          preset = RolePresets.presets.first;
        }
      }

      groups.putIfAbsent(
        roleName,
        () => _RoleGroup(
          icon: roleIcon,
          conversations: [],
          preset: preset,
          customRole: customRole,
        ),
      );

      groups[roleName]!.conversations.add(conv);
    }

    return groups;
  }

  void _confirmDelete(BuildContext context, Conversation conv) {
    showDialog<void>(
      context: context,
      builder: (context) => OwuiDialog(
        title: const Text('删除会话'),
        content: Text('确定要删除“${conv.title}”吗？此操作无法撤销。'),
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
            style: TextButton.styleFrom(
              foregroundColor: Theme.of(context).colorScheme.error,
            ),
            child: const Text('删除'),
          ),
        ],
      ),
    );
  }
}

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

