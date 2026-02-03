# Thread Message Lookup 技术债务

> 创建时间：2026-02-03
> 状态：已标记，待重构
> 影响范围：消息树加载、分支切换、错误持久化

## 问题背景

在实现错误消息持久化功能时，发现消息树结构在重启后出现问题：非活动分支显示空白 assistant header 占位。

## 根本原因

### 1. `conversation.messages` 语义不清

`conversation.messages` 实际上只存储**活动分支的消息快照**，而不是所有消息。这个语义不清晰，容易被误用。

```
数据存储结构：
├── messageBox (Hive)     → 所有消息（按 ID 索引）
├── conversation.messageIds → 所有消息 ID 列表
├── conversation.messages   → 活动分支消息快照 ⚠️ 容易被误认为是所有消息
└── conversation.threadJson → 树结构（节点只存 messageId 引用）
```

### 2. Thread 二次加载问题

Thread 可能被加载两次，使用不同的 messageLookup：

```
第一次加载（正确）：
HiveConversationService.loadConversations()
  → _loadThread(messageBox: messageBox)
  → messageLookup = messageBox.get(id)  ✅ 能找到所有消息

第二次加载（有问题）：
ThreadManager.getThread()
  → _loadAndValidate()
  → messageLookup = conversation.messages + getMessageById
  → 如果 getMessageById 未设置，非活动分支找不到消息 ⚠️
```

### 3. 穿透链路

为解决二次加载问题，引入了 `getMessageById` 回调穿透链路：

```
ConversationViewV2.didChangeDependencies()
  → context.read<ChatSessionProvider>()
    → ChatSessionProvider.getMessageById()
      → HiveConversationService.getMessageById()
        → messageBox.get(id)
```

这个设计虽然能工作，但增加了架构复杂度。

## 受影响的文件

| 文件 | 标记位置 | 说明 |
|------|----------|------|
| `lib/controllers/thread_manager.dart` | `getMessageById` 字段 | 穿透回调定义 |
| `lib/controllers/thread_manager.dart` | `_loadAndValidate()` | 二次加载逻辑 |
| `lib/services/hive_conversation_service.dart` | `loadConversations()` | 第一次加载 + messages 语义 |
| `lib/widgets/conversation_view_v2.dart` | `didChangeDependencies()` | 穿透链路设置 |
| `lib/providers/chat_session_provider.dart` | `getMessageById()` | 穿透中间层 |

## 当前状态

- **性能**：可接受。`messageBox.get()` 是 O(1)，只在首次加载时调用
- **功能**：正常工作。错误持久化和消息树加载都能正常运行
- **风险**：中等。`conversation.messages` 语义不清可能导致未来误用

## 建议的重构方案

### 方案 A：消除二次加载（推荐）

让 `HiveConversationService.loadConversations()` 返回时，thread 节点中已经包含完整的 message 对象。`ThreadManager` 检测到节点消息有效时，直接复用而不重新解析 threadJson。

```dart
// ThreadManager.getThread()
if (_thread == null || _thread!.conversationId != conversation.id) {
  // 检查是否已经有有效的 thread（从 Service 层传递）
  final existingThread = _tryGetPreloadedThread(conversation);
  if (existingThread != null && _isThreadValid(existingThread)) {
    _thread = existingThread;
  } else {
    _thread = _loadFromConversation(conversation);
  }
}
```

### 方案 B：明确 `conversation.messages` 语义

重命名为 `conversation.activeChainSnapshot` 或添加详细文档说明其语义。

### 方案 C：统一数据源

让 `ConversationThread` 成为消息的唯一数据源，`conversation.messages` 完全成为派生数据。

## 何时重构

- **短期**：不需要。当前方案能工作，风险可控
- **触发条件**：当需要开发以下功能时考虑重构
  - 分支合并
  - 分支导出
  - 消息搜索（跨分支）
  - 性能优化（大量分支场景）

## 相关 Issue / PR

- 无（内部技术债务记录）

## 变更历史

| 日期 | 变更 | 原因 |
|------|------|------|
| 2026-02-03 | 初始记录 | 错误持久化功能引发消息树加载问题，添加 getMessageById 穿透链路 |
