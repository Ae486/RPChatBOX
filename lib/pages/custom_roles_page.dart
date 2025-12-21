import 'package:flutter/material.dart';
import '../design_system/apple_icons.dart';
import '../widgets/apple_toast.dart';
import '../models/custom_role.dart';
import '../services/custom_role_service.dart';
import '../services/hive_conversation_service.dart';
import '../models/conversation.dart';

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
        AppleToast.error(context, message: '初始化失败: $e');
      }
    }
  }

  Future<void> _loadRoles() async {
    final roles = await _service.loadCustomRoles();
    setState(() {
      _customRoles = roles;
    });
  }

  /// 创建或编辑角色
  Future<void> _showRoleDialog({CustomRole? editRole}) async {
    final nameController = TextEditingController(text: editRole?.name ?? '');
    final descController = TextEditingController(text: editRole?.description ?? '');
    final promptController = TextEditingController(text: editRole?.systemPrompt ?? '');
    String selectedIcon = editRole?.icon ?? '✨';

    final result = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setState) => AlertDialog(
          title: Text(editRole == null ? '创建自定义角色' : '编辑角色'),
          content: SizedBox(
            width: 400,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                // 图标和名称一行
                Row(
                  children: [
                    // 图标选择框
                    InkWell(
                      onTap: () async {
                        final icon = await _showEmojiPicker(context, selectedIcon);
                        if (icon != null) {
                          setState(() {
                            selectedIcon = icon;
                          });
                        }
                      },
                      child: Container(
                        width: 60,
                        height: 60,
                        decoration: BoxDecoration(
                          border: Border.all(color: Colors.grey),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Center(
                          child: Text(
                            selectedIcon,
                            style: const TextStyle(fontSize: 32),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    // 角色名称
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
                const SizedBox(height: 16),
                // 角色描述
                SizedBox(
                  height: 80,
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
                const SizedBox(height: 16),
                // System Prompt
                SizedBox(
                  height: 150,
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
              onPressed: () => Navigator.pop(context, false),
              child: const Text('取消'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('保存'),
            ),
          ],
        ),
      ),
    );

    if (result == true) {
      final name = nameController.text.trim();
      final description = descController.text.trim();
      final prompt = promptController.text.trim();
      
      // 验证：角色名称不能为空
      if (name.isEmpty) {
        if (mounted) {
          AppleToast.warning(context, message: '角色名称不能为空');
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
      builder: (context) => AlertDialog(
        title: const Text('选择图标'),
        content: SizedBox(
          width: 300,
          height: 300,
          child: GridView.builder(
            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 4,
              mainAxisSpacing: 8,
              crossAxisSpacing: 8,
            ),
            itemCount: emojis.length,
            itemBuilder: (context, index) {
              final emoji = emojis[index];
              final isSelected = emoji == currentIcon;
              
              return InkWell(
                onTap: () => Navigator.pop(context, emoji),
                child: Container(
                  decoration: BoxDecoration(
                    border: Border.all(
                      color: isSelected ? Colors.blue : Colors.grey.shade300,
                      width: isSelected ? 2 : 1,
                    ),
                    borderRadius: BorderRadius.circular(8),
                    color: isSelected ? Colors.blue.shade50 : null,
                  ),
                  child: Center(
                    child: Text(emoji, style: const TextStyle(fontSize: 32)),
                  ),
                ),
              );
            },
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('取消'),
          ),
        ],
      ),
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
      builder: (context) => AlertDialog(
        title: const Text('删除角色'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('确定要删除「${role.name}」吗？'),
            if (hasRelatedConversations)
              const SizedBox(height: 16),
            if (hasRelatedConversations)
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.orange.shade50,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.orange.shade200),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Icon(AppleIcons.warning, color: Colors.orange.shade700, size: 20),
                        const SizedBox(width: 8),
                        Text(
                          '关联对话警告',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: Colors.orange.shade900,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '此角色有 $conversationCount 个关联对话，删除后这些对话也会被删除！',
                      style: TextStyle(color: Colors.orange.shade900),
                    ),
                  ],
                ),
              ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('取消'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: Text(hasRelatedConversations ? '确认删除' : '删除'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      // 删除关联的对话
      if (hasRelatedConversations) {
        try {
          for (final conv in relatedConversations) {
            await _conversationService.deleteConversation(allConversations, conv.id);
          }
          debugPrint('✅ 已删除 $conversationCount 个关联对话');
        } catch (e) {
          debugPrint('⚠️ 删除关联对话失败: $e');
          if (mounted) {
            AppleToast.error(context, message: '删除关联对话失败: $e');
          }
          return;
        }
      }
      
      // 删除角色
      await _service.deleteCustomRole(role.id);
      await _loadRoles();
      
      // 显示成功提示
      if (mounted) {
        AppleToast.success(
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
    return Scaffold(
      appBar: AppBar(
        title: const Text('自定义角色'),
      ),
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
                        icon: const Icon(AppleIcons.edit),
                        onPressed: () => _showRoleDialog(editRole: role),
                      ),
                      IconButton(
                        icon: const Icon(AppleIcons.delete, color: Colors.red),
                        onPressed: () => _deleteRole(role),
                      ),
                    ],
                  ),
                );
              },
            ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showRoleDialog(),
        child: const Icon(AppleIcons.add),
      ),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(AppleIcons.personAdd, size: 80, color: Colors.grey.shade300),
          const SizedBox(height: 16),
          Text(
            '还没有自定义角色',
            style: TextStyle(fontSize: 18, color: Colors.grey.shade600),
          ),
          const SizedBox(height: 8),
          TextButton.icon(
            onPressed: () => _showRoleDialog(),
            icon: const Icon(AppleIcons.add),
            label: const Text('创建第一个角色'),
          ),
        ],
      ),
    );
  }
}

