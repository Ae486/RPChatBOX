/// INPUT: CustomRoleService + HiveConversationService
/// OUTPUT: CustomRolesPage - 自定义角色增删改查（含关联会话处理）
/// POS: UI 层 / Pages - 角色管理页

import 'package:flutter/material.dart';

import '../chat_ui/owui/components/owui_app_bar.dart';
import '../chat_ui/owui/components/owui_dialog.dart';
import '../chat_ui/owui/components/owui_scaffold.dart';
import '../chat_ui/owui/components/owui_snack_bar.dart';
import '../chat_ui/owui/owui_icons.dart';
import '../chat_ui/owui/owui_tokens_ext.dart';
import '../models/conversation.dart';
import '../models/custom_role.dart';
import '../services/custom_role_service.dart';
import '../services/hive_conversation_service.dart';

/// 自定义角色管理页面
class CustomRolesPage extends StatefulWidget {
  const CustomRolesPage({super.key});

  @override
  State<CustomRolesPage> createState() => _CustomRolesPageState();
}

class _CustomRolesPageState extends State<CustomRolesPage> {
  final _service = CustomRoleService();
  late final HiveConversationService _conversationService;
  List<CustomRole> _customRoles = [];
  bool _isInitialized = false;

  @override
  void initState() {
    super.initState();
    _conversationService = HiveConversationService();
    _initialize();
  }
  
  @override
  void dispose() {
    // 确保清理资源
    super.dispose();
  }
  
  /// 初始化 Hive 和加载角色
  Future<void> _initialize() async {
    try {
      await _conversationService.initialize();
      _isInitialized = true;
      await _loadRoles();
    } catch (e) {
      debugPrint('⚠️ 初始化失败: $e');
      if (mounted) {
        OwuiSnackBars.error(context, message: '初始化失败: $e');
      }
    }
  }


  Future<void> _loadRoles() async {
    final roles = await _service.loadCustomRoles();
    if (!mounted) return;
    setState(() {
      _customRoles = roles;
    });
  }

  /// 创建或编辑角色
  Future<void> _showRoleDialog({CustomRole? editRole}) async {
    final nameController = TextEditingController(text: editRole?.name ?? '');
    final descController = TextEditingController(text: editRole?.description ?? '');
    final promptController = TextEditingController(
      text: editRole?.systemPrompt ?? '',
    );
    String selectedIcon = editRole?.icon ?? '✨';

    final result = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (dialogContext, setState) {
          final spacing = dialogContext.owuiSpacing;
          final colors = dialogContext.owuiColors;
          final radius = dialogContext.owuiRadius;
          final uiScale = dialogContext.owui.uiScale;

          return OwuiDialog(
            title: Text(editRole == null ? '创建自定义角色' : '编辑角色'),
            content: SizedBox(
              width: 400 * uiScale,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      InkWell(
                        onTap: () async {
                          final icon = await _showEmojiPicker(
                            dialogContext,
                            selectedIcon,
                          );
                          if (icon != null) {
                            setState(() {
                              selectedIcon = icon;
                            });
                          }
                        },
                        borderRadius: BorderRadius.circular(radius.rLg),
                        child: Container(
                          width: 60 * uiScale,
                          height: 60 * uiScale,
                          decoration: BoxDecoration(
                            border: Border.all(color: colors.borderSubtle),
                            borderRadius: BorderRadius.circular(radius.rLg),
                          ),
                          child: Center(
                            child: Text(
                              selectedIcon,
                              style: TextStyle(fontSize: 32 * uiScale),
                            ),
                          ),
                        ),
                      ),
                      SizedBox(width: spacing.md),
                      Expanded(
                        child: TextField(
                          controller: nameController,
                          decoration: const InputDecoration(
                            labelText: '角色名称',
                            hintText: '例如：Python 专家',
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: spacing.lg),
                  SizedBox(
                    height: 80 * uiScale,
                    child: TextField(
                      controller: descController,
                      decoration: const InputDecoration(
                        labelText: '角色描述',
                        hintText: '简短描述角色特点',
                        border: OutlineInputBorder(),
                        alignLabelWithHint: true,
                      ),
                      maxLines: 3,
                    ),
                  ),
                  SizedBox(height: spacing.lg),
                  SizedBox(
                    height: 150 * uiScale,
                    child: TextField(
                      controller: promptController,
                      decoration: const InputDecoration(
                        labelText: 'System Prompt',
                        hintText: 'You are a...',
                        border: OutlineInputBorder(),
                        alignLabelWithHint: true,
                      ),
                      maxLines: null,
                      expands: true,
                      textAlignVertical: TextAlignVertical.top,
                    ),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogContext, false),
                child: const Text('取消'),
              ),
              TextButton(
                onPressed: () => Navigator.pop(dialogContext, true),
                child: const Text('保存'),
              ),
            ],
          );
        },
      ),
    );

    if (result == true) {
      final name = nameController.text.trim();
      final description = descController.text.trim();
      final prompt = promptController.text.trim();

      // 验证：角色名称不能为空
      if (name.isEmpty) {
        if (mounted) {
          OwuiSnackBars.warning(context, message: '角色名称不能为空');
        }
        return;
      }

      final role = CustomRole(
        id: editRole?.id ?? DateTime.now().millisecondsSinceEpoch.toString(),
        name: name,
        description: description,
        // prompt 为空时使用默认值
        systemPrompt: prompt.isEmpty ? 'You are a helpful assistant.' : prompt,
        icon: selectedIcon,
      );

      if (editRole == null) {
        await _service.addCustomRole(role);
      } else {
        await _service.updateCustomRole(role);
      }

      await _loadRoles();
    }
  }

  /// 显示 Emoji 选择器
  Future<String?> _showEmojiPicker(BuildContext context, String currentIcon) async {
    // 常用 Emoji 列表
    final emojis = [
      '🤖', '✨', '💡', '🎯', '🚀', '📚', '🎨', '💻',
      '🔧', '⚡', '🌟', '🎓', '📝', '🔍', '💼', '🎭',
      '🏆', '🎪', '🎬', '🎮', '🎵', '🎸', '🎹', '🎺',
      '🧑‍💻', '🧑‍🔬', '🧑‍🏫', '🧑‍⚕️', '🧑‍🎨', '🧑‍✈️', '🧑‍🚀', '🧑‍🔧',
    ];

    return await showDialog<String>(
      context: context,
      builder: (dialogContext) {
        final spacing = dialogContext.owuiSpacing;
        final colors = dialogContext.owuiColors;
        final radius = dialogContext.owuiRadius;
        final scheme = Theme.of(dialogContext).colorScheme;
        final uiScale = dialogContext.owui.uiScale;

        return OwuiDialog(
          title: const Text('选择图标'),
          content: SizedBox(
            width: 300 * uiScale,
            height: 300 * uiScale,
            child: GridView.builder(
              gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                crossAxisCount: 4,
                mainAxisSpacing: spacing.md,
                crossAxisSpacing: spacing.md,
              ),
              itemCount: emojis.length,
              itemBuilder: (context, index) {
                final emoji = emojis[index];
                final isSelected = emoji == currentIcon;

                final borderColor =
                    isSelected ? scheme.primary : colors.borderSubtle;
                final bgColor = isSelected
                    ? scheme.primary.withValues(alpha: 0.08)
                    : colors.surface2;

                return Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: () => Navigator.pop(dialogContext, emoji),
                    borderRadius: BorderRadius.circular(radius.rLg),
                    child: Container(
                      decoration: BoxDecoration(
                        color: bgColor,
                        border: Border.all(
                          color: borderColor,
                          width: (isSelected ? 2 : 1) * uiScale,
                        ),
                        borderRadius: BorderRadius.circular(radius.rLg),
                      ),
                      child: Center(
                        child: Text(
                          emoji,
                          style: TextStyle(fontSize: 32 * uiScale),
                        ),
                      ),
                    ),
                  ),
                );
              },
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('取消'),
            ),
          ],
        );
      },
    );
  }

  /// 删除角色（级联删除关联的对话）
  Future<void> _deleteRole(CustomRole role) async {
    // 显示确认对话框前显示loading
    if (!mounted) return;
    
    // 查找关联的对话
    List<Conversation> allConversations = [];
    List<Conversation> relatedConversations = [];
    
    if (!_isInitialized) {
      debugPrint('⚠️ Hive 未初始化，无法查找关联对话');
    } else {
      try {
        allConversations = await _conversationService.loadConversations();
        relatedConversations = allConversations
            .where((conv) => conv.roleId == role.id && conv.roleType == 'custom')
            .toList();
      } catch (e) {
        debugPrint('⚠️ 查找关联对话失败: $e');
      }
    }
    
    if (!mounted) return;
    
    // 构建确认对话框内容
    final hasRelatedConversations = relatedConversations.isNotEmpty;
    final conversationCount = relatedConversations.length;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        final spacing = dialogContext.owuiSpacing;
        final colors = dialogContext.owuiColors;
        final radius = dialogContext.owuiRadius;
        final scheme = Theme.of(dialogContext).colorScheme;

        return OwuiDialog(
          title: const Text('删除角色'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('确定要删除「${role.name}」吗？'),
              if (hasRelatedConversations) SizedBox(height: spacing.lg),
              if (hasRelatedConversations)
                Container(
                  padding: EdgeInsets.all(spacing.md),
                  decoration: BoxDecoration(
                    color: colors.surface2,
                    borderRadius: BorderRadius.circular(radius.rLg),
                    border: Border.all(color: colors.borderSubtle),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Icon(
                            OwuiIcons.warning,
                            color: scheme.tertiary,
                            size: 20 * dialogContext.owui.uiScale,
                          ),
                          SizedBox(width: spacing.sm),
                          Text(
                            '关联对话警告',
                            style: Theme.of(dialogContext)
                                .textTheme
                                .titleSmall
                                ?.copyWith(fontWeight: FontWeight.w600),
                          ),
                        ],
                      ),
                      SizedBox(height: spacing.sm),
                      Text(
                        '此角色有 $conversationCount 个关联对话，删除后这些对话也会被删除！',
                        style: Theme.of(dialogContext).textTheme.bodySmall?.copyWith(
                              color: colors.textSecondary,
                            ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('取消'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              style: TextButton.styleFrom(foregroundColor: scheme.error),
              child: Text(hasRelatedConversations ? '确认删除' : '删除'),
            ),
          ],
        );
      },
    );

    if (confirmed == true) {

      if (hasRelatedConversations) {
        try {
          for (final conv in relatedConversations) {
            await _conversationService.deleteConversation(allConversations, conv.id);
          }
          debugPrint('✅ 已删除 $conversationCount 个关联对话');
        } catch (e) {
          debugPrint('⚠️ 删除关联对话失败: $e');
          if (mounted) {
            OwuiSnackBars.error(context, message: '删除关联对话失败: $e');
          }
          return;
        }
      }

      // 删除角色
      await _service.deleteCustomRole(role.id);
      await _loadRoles();

      // 显示成功提示
      if (mounted) {
        OwuiSnackBars.success(
          context,
          message: hasRelatedConversations
              ? '已删除角色和 $conversationCount 个关联对话'
              : '已删除角色',
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return OwuiScaffold(
      appBar: const OwuiAppBar(title: Text('自定义角色')),
      body: _customRoles.isEmpty
          ? _buildEmptyState()
          : ListView.builder(
              itemCount: _customRoles.length,
              itemBuilder: (context, index) {
                final role = _customRoles[index];
                return ListTile(
                  leading: Text(role.icon, style: const TextStyle(fontSize: 32)),
                  title: Text(role.name),
                  subtitle: Text(role.description),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        icon: const Icon(OwuiIcons.edit),
                        onPressed: () => _showRoleDialog(editRole: role),
                      ),
                      IconButton(
                        icon: Icon(OwuiIcons.delete, color: scheme.error),
                        onPressed: () => _deleteRole(role),
                      ),
                    ],
                  ),
                );
              },
            ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showRoleDialog(),
        child: const Icon(OwuiIcons.add),
      ),
    );
  }

  Widget _buildEmptyState() {
    final colors = context.owuiColors;
    final spacing = context.owuiSpacing;

    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            OwuiIcons.personAdd,
            size: 80 * context.owui.uiScale,
            color: colors.textSecondary.withValues(alpha: 0.55),
          ),
          SizedBox(height: spacing.lg),
          Text(
            '还没有自定义角色',
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(color: colors.textSecondary),
          ),
          SizedBox(height: spacing.sm),
          TextButton.icon(
            onPressed: () => _showRoleDialog(),
            icon: const Icon(OwuiIcons.add),
            label: const Text('创建第一个角色'),
          ),
        ],
      ),
    );
  }
}
