import 'dart:ui';
import 'package:flutter/material.dart';
import '../models/conversation.dart';
import '../models/role_preset.dart';
import '../models/custom_role.dart';
import '../design_system/design_tokens.dart';
import '../design_system/apple_tokens.dart';
import '../design_system/apple_icons.dart';

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
    final isDark = Theme.of(context).brightness == Brightness.dark;

    // 按角色分组会话
    final groupedConversations = _groupByRole(conversations);
    
    // 计算实际显示的会话数（排除被删除角色的对话）
    final displayedConversationsCount = groupedConversations.values
        .fold<int>(0, (sum, group) => sum + group.conversations.length);

    return Drawer(
      backgroundColor: Colors.transparent, // 关键：Drawer背景透明
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 30, sigmaY: 30), // 增强模糊效果
        child: Container(
          decoration: BoxDecoration(
            color: isDark
                ? Colors.black.withValues(alpha: 0.75) // 暗模式75%透明
                : Colors.white.withValues(alpha: 0.8), // 亮模式80%透明
            border: Border(
              right: BorderSide(
                color: AppleColors.separator(context),
                width: 0.5,
              ),
            ),
          ),
          child: Column(
            children: [
              // 头部 - Apple风格简洁设计（移除新建按钮）
              Container(
                padding: EdgeInsets.fromLTRB(
                  ChatBoxTokens.spacing.lg,
                  MediaQuery.of(context).padding.top + ChatBoxTokens.spacing.lg,
                  ChatBoxTokens.spacing.lg,
                  ChatBoxTokens.spacing.lg,
                ),
                decoration: BoxDecoration(
                  border: Border(
                    bottom: BorderSide(
                      color: AppleColors.separator(context),
                      width: 0.5,
                    ),
                  ),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '对话',
                      style: AppleTokens.typography.largeTitle.copyWith(
                        color: isDark ? Colors.white : Colors.black,
                      ),
                    ),
                    SizedBox(height: ChatBoxTokens.spacing.xs),
                    Text(
                      '$displayedConversationsCount 个会话',
                      style: AppleTokens.typography.footnote.copyWith(
                        color: AppleColors.secondaryLabel(context),
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
              Container(
                decoration: BoxDecoration(
                  border: Border(
                    top: BorderSide(
                      color: AppleColors.separator(context),
                      width: 0.5,
                    ),
                  ),
                ),
                child: ListTile(
                  leading: Icon(AppleIcons.personAdd, color: AppleColors.blue),
                  title: Text(
                    '自定义助手',
                    style: AppleTokens.typography.body,
                  ),
                  onTap: () {
                    Navigator.pop(context);
                    onManageCustomRoles();
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  /// 构建角色分组 - Apple风格卡片
  Widget _buildRoleGroup(
    BuildContext context, {
    required String roleName,
    required String roleIcon,
    required List<Conversation> conversations,
    RolePreset? onNewWithRole,
    CustomRole? onNewWithCustomRole,
  }) {
    return Container(
      margin: EdgeInsets.symmetric(
        horizontal: ChatBoxTokens.spacing.md,
        vertical: ChatBoxTokens.spacing.xs,
      ),
      decoration: BoxDecoration(
        color: Theme.of(context).cardColor,
        borderRadius: BorderRadius.circular(12), // Apple圆角
        boxShadow: AppleTokens.shadows.card, // 轻微阴影
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: ExpansionTile(
          leading: Text(roleIcon, style: const TextStyle(fontSize: 24)),
          title: Text(
            roleName,
            style: AppleTokens.typography.body.copyWith(
              fontWeight: FontWeight.w600,
            ),
          ),
          subtitle: Text(
            '${conversations.length} 个对话',
            style: AppleTokens.typography.footnote.copyWith(
              color: AppleColors.secondaryLabel(context),
            ),
          ),
          tilePadding: EdgeInsets.symmetric(
            horizontal: ChatBoxTokens.spacing.md,
            vertical: ChatBoxTokens.spacing.xs,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          collapsedShape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          initiallyExpanded: conversations.any((c) => c.id == currentConversationId),
          children: [
            // 新建对话按钮 - Apple蓝色风格
            Padding(
              padding: EdgeInsets.fromLTRB(
                ChatBoxTokens.spacing.md,
                ChatBoxTokens.spacing.xs,
                ChatBoxTokens.spacing.md,
                ChatBoxTokens.spacing.sm,
              ),
              child: ElevatedButton.icon(
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
                icon: const Icon(AppleIcons.addCircle, size: 20),
                label: Text(
                  '新建对话',
                  style: AppleTokens.typography.body.copyWith(
                    fontWeight: FontWeight.w500,
                  ),
                ),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppleColors.blue,
                  foregroundColor: Colors.white,
                  elevation: 0,
                  shadowColor: Colors.transparent,
                  padding: EdgeInsets.symmetric(
                    vertical: ChatBoxTokens.spacing.sm,
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10),
                  ),
                  minimumSize: const Size(double.infinity, 44),
                ),
              ),
            ),
            // 该角色下的所有会话
            ...conversations.map((conv) => _buildConversationTile(context, conv)),
          ],
        ),
      ),
    );
  }

  /// 构建会话磁贴 - Apple风格选中高亮
  Widget _buildConversationTile(BuildContext context, Conversation conv) {
    final isSelected = conv.id == currentConversationId;

    return Container(
      margin: EdgeInsets.symmetric(
        horizontal: ChatBoxTokens.spacing.sm,
        vertical: 2,
      ),
      decoration: BoxDecoration(
        color: isSelected
            ? AppleColors.blue.withValues(alpha: 0.15) // Apple蓝半透明背景
            : Colors.transparent,
        borderRadius: BorderRadius.circular(8),
      ),
      child: ListTile(
        selected: isSelected,
        contentPadding: EdgeInsets.only(
          left: ChatBoxTokens.spacing.lg,
          right: ChatBoxTokens.spacing.md,
        ),
        title: Text(
          conv.title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: AppleTokens.typography.body.copyWith(
            fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
          ),
        ),
        subtitle: Text(
          conv.lastMessagePreview,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: AppleTokens.typography.footnote.copyWith(
            color: AppleColors.secondaryLabel(context),
          ),
        ),
        trailing: PopupMenuButton<String>(
          icon: const Icon(AppleIcons.moreVert, size: 20),
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
          PopupMenuItem(
            value: 'rename',
            child: Row(
              children: [
                Icon(AppleIcons.edit, size: 18),
                SizedBox(width: ChatBoxTokens.spacing.sm),
                Text('重命名'),
              ],
            ),
          ),
          PopupMenuItem(
            value: 'delete',
            child: Row(
              children: [
                Icon(AppleIcons.delete, size: 18),
                SizedBox(width: ChatBoxTokens.spacing.sm),
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
      ),
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
