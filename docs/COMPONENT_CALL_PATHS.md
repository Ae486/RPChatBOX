# 组件调用路径文档

> 记录关键UI组件的调用关系，确保修改时不破坏功能

---

## ConversationDrawer 调用路径

### 定义位置
**文件**: `lib/widgets/conversation_drawer.dart` (第7-31行)

### 使用位置
**文件**: `lib/pages/chat_page.dart` (第625-636行)

```dart
Scaffold(
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
)
```

### 组件结构
```
ConversationDrawer (StatelessWidget)
└── Drawer
     └── Column
          ├── DrawerHeader (渐变背景)
          │    └── Column
          │         ├── Text("AI ChatBox")
          │         └── Text("X个会话")
          ├── Expanded(ListView) - 角色分组列表
          │    └── _buildRoleGroup() × N
          │         ├── ExpansionTile
          │         │    ├── Leading (roleIcon)
          │         │    ├── Title (roleName)
          │         │    ├── Subtitle (count)
          │         │    └── Children
          │         │         ├── OutlinedButton (新建对话)
          │         │         └── ListTile × N (会话列表)
          │         │              ├── Leading (Icon)
          │         │              ├── Title (conversation.title)
          │         │              ├── Subtitle (时间)
          │         │              └── Trailing (PopupMenuButton)
          │         └── _buildEmptyCustomRoleCard() (未使用的自定义角色)
          └── Container (底部固定按钮)
               └── ListTile (自定义助手管理)
```

### 关键回调函数
1. `onConversationSelected(String id)` - 切换会话
2. `onNewConversation()` - 创建空白会话
3. `onNewConversationWithRole(RolePreset)` - 基于预设角色创建
4. `onNewConversationWithCustomRole(CustomRole)` - 基于自定义角色创建
5. `onDeleteConversation(Conversation)` - 删除会话
6. `onRenameConversation(Conversation)` - 重命名会话
7. `onManageCustomRoles()` - 打开自定义角色管理页

### 依赖的模型
- `Conversation` - 会话模型
- `CustomRole` - 自定义角色模型
- `RolePreset` - 预设角色模型

---

## 验证状态
- ✅ 调用路径已确认
- ✅ 所有回调函数已记录
- ✅ 组件结构已分析
- ✅ 无多级override覆盖

**验证日期**: 2025-01-17
