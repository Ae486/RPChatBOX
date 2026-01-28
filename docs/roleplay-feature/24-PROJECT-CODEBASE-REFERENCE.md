# ChatBoxApp 项目代码库参考文档

> 创建时间: 2026-01-15
> 目的: 为 roleplay-feature 开发提供项目基础实现参考，供 Claude 和 Codex 协作时使用

---

## 1. 项目概述

### 1.1 技术栈
- **框架**: Flutter (Dart)
- **平台**: Windows / Android / macOS / Linux / Web
- **存储**: Hive (本地数据库) + SharedPreferences (轻量配置)
- **网络**: Dio (HTTP 客户端)
- **UI**: flutter_chat_ui 生态系统

### 1.2 核心依赖链
```
UI (lib/pages, lib/widgets)
    ↓
控制器 (lib/controllers)
    ↓
业务服务 (lib/services)
    ↓
Provider/Adapter (lib/adapters)
    ↓
模型与存储 (lib/models / Hive)
```

### 1.3 关键目录结构
```
lib/
├── main.dart                    # 应用入口
├── models/                      # 数据模型
│   ├── conversation.dart        # 会话模型 (Hive TypeId: 0)
│   ├── message.dart             # 消息模型 (Hive TypeId: 1)
│   ├── attached_file.dart       # 附件模型 (Hive TypeId: 2, 3)
│   ├── custom_role.dart         # 自定义角色模型
│   ├── provider_config.dart     # Provider配置
│   └── model_config.dart        # 模型配置
├── services/
│   ├── hive_conversation_service.dart  # Hive会话存储
│   ├── custom_role_service.dart        # 角色管理
│   ├── model_service_manager.dart      # 模型服务管理
│   └── storage_service.dart            # 通用存储
├── adapters/
│   ├── ai_provider.dart         # Provider抽象接口
│   └── openai_provider.dart     # OpenAI格式实现
├── controllers/
│   └── stream_output_controller.dart  # 流式输出控制
├── widgets/
│   ├── conversation_view_v2.dart      # V2主聊天视图
│   └── conversation_view_v2/          # V2子模块
│       ├── streaming.dart             # 流式输出核心
│       ├── thread_projection.dart     # 树状消息链投影
│       └── ...
└── pages/
    └── chat_page.dart           # 主聊天页面
```

---

## 2. 数据模型

### 2.1 Conversation (会话)
**文件**: `lib/models/conversation.dart`
**Hive TypeId**: 0

```dart
@HiveType(typeId: 0)
class Conversation {
  @HiveField(0)  final String id;
  @HiveField(1)  String title;
  @HiveField(2)  final List<Message> messages;
  @HiveField(3)  final DateTime createdAt;
  @HiveField(4)  DateTime updatedAt;
  @HiveField(5)  String? systemPrompt;     // 系统提示词（角色设定）
  @HiveField(6)  int? scrollIndex;         // 滚动位置
  @HiveField(7)  String? roleId;           // 角色ID
  @HiveField(8)  String? roleType;         // 'preset' | 'custom'
  @HiveField(9)  String? threadJson;       // 树状消息链 JSON
  @HiveField(10) String? activeLeafId;     // 活动叶子节点
  @HiveField(11) String? summary;          // 会话摘要
  @HiveField(12) String? summaryRangeStartId;
  @HiveField(13) String? summaryRangeEndId;
  @HiveField(14) DateTime? summaryUpdatedAt;
  @HiveField(15) List<String> messageIds;  // 消息ID索引
}
```

**关键方法**:
- `addMessage(Message)` - 添加消息
- `removeMessage(String)` - 删除消息
- `clearMessages()` - 清空消息
- `copyWith(...)` - 创建副本

### 2.2 Message (消息)
**文件**: `lib/models/message.dart`
**Hive TypeId**: 1

```dart
@HiveType(typeId: 1)
class Message {
  @HiveField(0)  final String id;
  @HiveField(1)  String content;           // 可变，支持编辑
  @HiveField(2)  final bool isUser;
  @HiveField(3)  final DateTime timestamp;
  @HiveField(4)  int? inputTokens;         // 输入 token
  @HiveField(5)  int? outputTokens;        // 输出 token
  @HiveField(6)  String? modelName;        // AI消息的模型名
  @HiveField(7)  String? providerName;     // AI消息的供应商名
  @HiveField(8)  List<AttachedFileSnapshot>? attachedFiles;  // 附件快照
  @HiveField(9)  String? parentId;         // 父消息ID
  @HiveField(10) DateTime? editedAt;       // 编辑时间
}
```

### 2.3 CustomRole (自定义角色)
**文件**: `lib/models/custom_role.dart`
**存储**: SharedPreferences (JSON)

```dart
class CustomRole {
  final String id;
  String name;
  String description;
  String systemPrompt;
  String icon;  // 默认 '✨'
}
```

### 2.4 Hive TypeId 分配表
| TypeId | 类型 | 文件 |
|--------|------|------|
| 0 | Conversation | conversation.dart |
| 1 | Message | message.dart |
| 2 | FileType | attached_file.dart |
| 3 | AttachedFileSnapshot | attached_file.dart |

> **roleplay-feature 注意**: 新增 Hive 类型需从 TypeId 4 开始

---

## 3. 服务层

### 3.1 HiveConversationService
**文件**: `lib/services/hive_conversation_service.dart`

```dart
class HiveConversationService {
  // Box 名称
  static const String _conversationsBoxName = 'conversations';
  static const String _messagesBoxName = 'messages';
  static const String _currentConversationKey = 'current_conversation_id';

  // 核心方法
  Future<void> initialize();                        // 初始化 Hive
  Future<void> saveConversations(List<Conversation>);  // 保存所有会话
  Future<List<Conversation>> loadConversations();   // 加载所有会话
  Future<void> saveCurrentConversationId(String);   // 保存当前会话ID
  Future<String?> loadCurrentConversationId();      // 加载当前会话ID
  Conversation createConversation({                 // 创建新会话
    String? title,
    String? systemPrompt,
    String? roleId,
    String? roleType,
  });
  Future<void> deleteConversation(...);
  Future<void> clearAllConversations();
  Future<void> close();
}
```

**适配器注册顺序**:
```dart
Hive.registerAdapter(ConversationAdapter());      // TypeId 0
Hive.registerAdapter(MessageAdapter());           // TypeId 1
Hive.registerAdapter(FileTypeAdapter());          // TypeId 2
Hive.registerAdapter(AttachedFileSnapshotAdapter()); // TypeId 3
```

### 3.2 CustomRoleService
**文件**: `lib/services/custom_role_service.dart`

```dart
class CustomRoleService {
  static const String _customRolesKey = 'custom_roles';

  Future<void> saveCustomRoles(List<CustomRole>);
  Future<List<CustomRole>> loadCustomRoles();
  Future<void> addCustomRole(CustomRole);
  Future<void> deleteCustomRole(String roleId);
  Future<void> updateCustomRole(CustomRole);
}
```

### 3.3 ModelServiceManager
**文件**: `lib/services/model_service_manager.dart`
**全局实例**: `globalModelServiceManager`

- 管理 Provider 和 Model 配置
- 创建 Provider 实例
- 管理对话设置 (ConversationSettings)

---

## 4. API Provider 架构

### 4.1 AIProvider 抽象接口
**文件**: `lib/adapters/ai_provider.dart`

```dart
abstract class AIProvider {
  final ProviderConfig config;

  Future<ProviderTestResult> testConnection();
  Future<List<String>> listAvailableModels();

  // 流式发送
  Stream<String> sendMessageStream({
    required String model,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
  });

  // 非流式发送
  Future<String> sendMessage({...});
}
```

### 4.2 ChatMessage (API消息格式)
```dart
class ChatMessage {
  final String role;     // 'system', 'user', 'assistant'
  final String content;
  final List<MessageContent>? multimodalContent;
}
```

### 4.3 ProviderType 枚举
```dart
enum ProviderType {
  openai('OpenAI格式', 'https://api.openai.com/v1'),
  gemini('Gemini格式', 'https://generativelanguage.googleapis.com/v1'),
  deepseek('DeepSeek格式', 'https://api.deepseek.com/v1'),
  claude('Claude格式', 'https://api.anthropic.com/v1');
}
```

### 4.4 ProviderFactory
```dart
class ProviderFactory {
  static AIProvider createProvider(ProviderConfig config) {
    switch (config.type) {
      case ProviderType.openai:   return OpenAIProvider(config);
      case ProviderType.gemini:   return OpenAIProvider(config); // 临时
      case ProviderType.deepseek: return DeepSeekProvider(config);
      case ProviderType.claude:   return ClaudeProvider(config);
    }
  }
}
```

---

## 5. 流式输出系统

### 5.1 StreamOutputController
**文件**: `lib/controllers/stream_output_controller.dart`

```dart
class StreamOutputController {
  bool get isStreaming;
  bool get isCancelled;
  String get accumulatedContent;

  Future<void> startStreaming({
    required AIProvider provider,
    required String modelName,
    required List<ChatMessage> messages,
    required ModelParameters parameters,
    List<AttachedFileData>? files,
    required void Function(String chunk) onChunk,
    required void Function() onDone,
    required void Function(dynamic error) onError,
  });

  Future<String> stop();
  void pause();
  void resume();
  void dispose();
}
```

### 5.2 EnhancedStreamController
扩展版，提供详细的状态管理和性能统计:
- `StreamState`: idle, streaming, paused, stopped, error
- `stateStream`: 状态变化流
- `getStats()`: 性能统计

---

## 6. System Prompt 组装流程

**位置**: `lib/widgets/conversation_view_v2/streaming.dart` - `_startAssistantResponse()`

```dart
// 1. 构建消息列表
final chatMessages = <ai.ChatMessage>[];

// 2. 添加 System Prompt (如果存在)
final systemPrompt = widget.conversation.systemPrompt;
if (systemPrompt != null && systemPrompt.trim().isNotEmpty) {
  chatMessages.add(ai.ChatMessage(role: 'system', content: systemPrompt));
}

// 3. 获取活动消息链
final thread = _getThread();
final history = buildActiveMessageChain(thread);

// 4. 应用上下文长度限制
final contextLength = _conversationSettings.contextLength;
final startIndex = (contextLength <= 0 || history.length <= contextLength)
    ? 0
    : history.length - contextLength;

// 5. 添加历史消息
for (final msg in history.skip(startIndex)) {
  chatMessages.add(ai.ChatMessage(
    role: msg.isUser ? 'user' : 'assistant',
    content: msg.content,
  ));
}

// 6. 发送请求
await _streamController.startStreaming(
  provider: provider,
  modelName: modelWithProvider.model.modelName,
  messages: chatMessages,
  parameters: _conversationSettings.parameters,
  ...
);
```

**关键注入点** (roleplay-feature):
- System Prompt 在步骤 2 注入
- 历史消息在步骤 5 构建
- 可在步骤 2 后、步骤 5 前插入 roleplay 上下文

---

## 7. 树状消息链 (Message Branching)

### 7.1 ConversationThread
**文件**: `lib/models/conversation_thread.dart`

```dart
class ConversationThread {
  final String conversationId;
  final Map<String, ThreadNode> nodes;  // key = messageId
  final String? rootId;
  final Map<String, String> selectedChild;  // parentId -> selectedChildId
  String? activeLeafId;

  // 从线性消息构建
  factory ConversationThread.fromLinearMessages(
    String conversationId,
    List<Message> messages,
  );

  // 获取活动消息链
  void normalize();
  void appendToActiveLeaf(Message);
  void appendAssistantVariantUnderUser({...});
}
```

### 7.2 ThreadNode
```dart
class ThreadNode {
  final String id;
  final String? parentId;
  final Message message;
  final List<String> children;  // 按创建时间排序
}
```

### 7.3 线性投影
**文件**: `lib/widgets/conversation_view_v2/thread_projection.dart`

```dart
List<Message> buildActiveMessageChain(ConversationThread thread);
```

---

## 8. 应用入口

### 8.1 main.dart 初始化流程
```dart
void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  final prefs = await SharedPreferences.getInstance();

  // 1. 数据迁移
  final migrationService = DataMigrationService();
  if (await migrationService.needsMigration()) {
    await migrationService.migrate();
  }

  // 2. 初始化 ModelServiceManager
  globalModelServiceManager = ModelServiceManager(prefs);
  await globalModelServiceManager.initialize();

  // 3. 加载主题设置
  final themeMode = prefs.getString('theme_mode') ?? 'system';
  final uiScale = prefs.getDouble('ui_scale') ?? 1.0;
  // ...

  // 4. 启动应用
  runApp(MyApp(...));
}
```

### 8.2 MyApp 状态
```dart
class MyAppState extends State<MyApp> {
  late ThemeMode _themeMode;
  late double _uiScale;
  late String _uiFontFamily;
  late String _uiCodeFontFamily;

  Future<void> setThemeMode(ThemeMode);
  Future<void> setDisplaySettings({...});
}
```

---

## 9. roleplay-feature 集成点

### 9.1 数据存储扩展
- **推荐**: 新建 Hive Box (如 `roleplay_data`)
- **TypeId**: 从 4 开始分配
- **JSON 字段**: 可利用 `Conversation.threadJson` 模式

### 9.2 System Prompt 注入
**位置**: `streaming.dart:_startAssistantResponse()`
**方式**: 在 systemPrompt 添加后、历史消息前插入 roleplay 上下文

```dart
// 现有代码
if (systemPrompt != null && systemPrompt.trim().isNotEmpty) {
  chatMessages.add(ai.ChatMessage(role: 'system', content: systemPrompt));
}

// roleplay 注入点 (建议)
// final roleplayContext = await roleplayService.compileContext(...);
// chatMessages.add(ai.ChatMessage(role: 'system', content: roleplayContext));
```

### 9.3 流式输出处理
**位置**: `streaming.dart:_handleStreamFlush()`
**用途**: 可在此处理 roleplay 相关的输出解析 (如 Proposal 检测)

### 9.4 会话创建扩展
**位置**: `HiveConversationService.createConversation()`
**方式**: 添加 roleplay 相关参数

---

## 10. 危险区域 (改动需小心)

| 文件/目录 | 风险描述 |
|-----------|----------|
| `conversation_view_v2.dart` + `conversation_view_v2/*` | V2 主聊天视图，核心流式输出 |
| `conversation_view_host.dart` | 聊天视图宿主 |
| `stream_output_controller.dart` | 流式输出时序/取消/异常 |
| `adapters/*_provider.dart` | API 兼容与 SSE 解析 |
| `storage_service.dart` / Hive 相关 | 持久化与数据迁移 |

---

## 11. 测试基础设施

### 11.1 测试目录结构
```
test/
├── helpers/
│   ├── test_data.dart      # 测试数据工厂
│   ├── test_setup.dart     # 测试环境配置
│   └── pump_app.dart       # Widget测试辅助
├── mocks/
│   └── mocks.dart          # Mockito Mock定义
├── unit/
│   ├── models/             # 模型单元测试
│   └── services/           # 服务单元测试
├── widget/                 # Widget测试
└── golden/                 # Golden测试
```

### 11.2 TestData 工厂
```dart
class TestData {
  static Conversation createTestConversation({...});
  static Message createUserMessage({...});
  static Message createAiMessage({...});
  static Conversation createConversationWithMessages({...});
}
```

---

## 12. 版本信息

- **Flutter**: 3.x
- **Hive**: 2.2.3
- **flutter_chat_ui**: 2.0.0
- **Dio**: 5.4.0

---

## 附录: 快速参考

### A. 新增 Hive 类型步骤
1. 定义类并添加 `@HiveType(typeId: N)` 注解
2. 运行 `flutter pub run build_runner build`
3. 在 `HiveConversationService.initialize()` 中注册适配器
4. 更新本文档的 TypeId 分配表

### B. 新增 Service 步骤
1. 在 `lib/services/` 创建服务类
2. 如需初始化，在 `main.dart` 中添加
3. 更新 README 核心依赖链

### C. 扩展 Conversation 模型
1. 添加新的 `@HiveField(N)` 字段
2. 更新 `toJson()` / `fromJson()` / `copyWith()`
3. 运行 `flutter pub run build_runner build`
4. 考虑数据迁移 (DataMigrationService)
