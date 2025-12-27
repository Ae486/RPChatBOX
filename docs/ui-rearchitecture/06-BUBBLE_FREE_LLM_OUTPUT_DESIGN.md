# 无气泡 LLM 输出设计规范

> 用户明确要求：大模型输出内容不使用气泡包裹，直接流淌在背景上
> 最后更新: 2024-12-21

---

## 1. 设计目标

### 1.1 视觉参考

参考 MateChat 风格的聊天界面设计：

```
┌─────────────────────────────────────────────┐
│                                             │
│  ┌─────────────────────────────────────┐    │
│  │ 用户消息在气泡内                      │ ←─ 用户气泡
│  │ 背景色区分，有圆角边框                │    │
│  └─────────────────────────────────────┘    │
│                                             │
│  如果立希知道这段对话，她大概会：           │ ←─ LLM 直接输出
│                                             │     无气泡/边框
│  "......所以你们刚才一直在讨论我？"        │     全宽度内容
│                                             │     流淌在背景上
│  她皱起眉头                                 │
│  "......感觉好奇怪。"                      │
│                                             │
│  关于"出戏":                                │ ←─ 分隔线（可选）
│  ───────────────────────────────────        │
│  我懂你的意思。就像演员在台上演戏...        │
│                                             │
└─────────────────────────────────────────────┘
```

### 1.2 核心原则

| 元素 | 样式 | 说明 |
|------|------|------|
| **用户消息** | 气泡包裹 | 使用 `primaryContainer` 背景色，圆角边框 |
| **LLM 输出** | 无气泡 | 直接渲染，无背景色，无边框，全宽度 |
| **思考气泡** | 轻量容器 | 半透明蓝色背景，与正文区分 |
| **代码块** | 自带容器 | 保持现有增强代码块样式 |

---

## 2. 技术实现

### 2.1 flutter_chat_ui Builder 适配

**textMessageBuilder** 修改：

```dart
textMessageBuilder: (context, message, index, {required isSentByMe, groupStatus}) {
  final isDark = Theme.of(context).brightness == Brightness.dark;
  
  // 用户消息：保持气泡
  if (isSentByMe) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.primaryContainer,
        borderRadius: BorderRadius.circular(16),
      ),
      child: _buildUserContent(message),
    );
  }
  
  // LLM 消息：无气泡，直接渲染
  return Padding(
    padding: const EdgeInsets.symmetric(vertical: 8),
    child: _buildAssistantContent(message, isDark),
  );
}
```

### 2.2 LLM 消息布局

```dart
Widget _buildAssistantContent(TextMessage message, bool isDark) {
  final segments = _splitByThinkingBlocks(message.text);
  
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      // 消息头部（模型名称、时间）
      _AssistantMessageHeader(
        modelName: message.metadata?['modelName'],
        providerName: message.metadata?['providerName'],
        timestamp: message.createdAt,
      ),
      
      const SizedBox(height: 8),
      
      // 内容区域：无气泡包裹
      for (final seg in segments) ...[
        if (seg.kind == 'thinking')
          _ThinkingSection(content: seg.text, isOpen: seg.open)
        else
          // 直接渲染 Markdown，无包裹容器
          _MarkdownContent(text: seg.text, isDark: isDark),
      ],
      
      // 操作按钮行
      _MessageActionsRow(message: message),
    ],
  );
}
```

### 2.3 用户消息布局

```dart
Widget _buildUserContent(TextMessage message) {
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      // 附件预览（如有）
      if (message.metadata?['attachedFiles'] != null)
        _AttachmentsPreview(files: message.metadata!['attachedFiles']),
      
      // 消息内容
      Text(
        message.text,
        style: TextStyle(fontSize: 15),
      ),
    ],
  );
}
```

---

## 3. 样式规范

### 3.1 用户消息样式

```dart
// 用户消息容器
Container(
  padding: EdgeInsets.symmetric(
    horizontal: ChatBoxTokens.spacing.lg,  // 16px
    vertical: ChatBoxTokens.spacing.md,     // 12px
  ),
  decoration: BoxDecoration(
    color: Theme.of(context).colorScheme.primaryContainer,
    borderRadius: BorderRadius.circular(AppleTokens.corners.bubble), // 20px
    boxShadow: AppleTokens.shadows.bubble,
  ),
)
```

### 3.2 LLM 消息样式

```dart
// LLM 消息：无容器，仅有间距
Padding(
  padding: EdgeInsets.symmetric(
    horizontal: ChatBoxTokens.spacing.lg,  // 16px
    vertical: ChatBoxTokens.spacing.sm,     // 8px
  ),
  child: Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      // 头部：模型名称 + 时间
      Row(
        children: [
          CircleAvatar(
            radius: 16,
            backgroundColor: Theme.of(context).colorScheme.secondary,
            child: Icon(AppleIcons.chatbot, size: 18, color: Colors.white),
          ),
          SizedBox(width: 8),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(modelName, style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
              Text(timeAgo, style: TextStyle(fontSize: 11, color: Colors.grey)),
            ],
          ),
        ],
      ),
      
      SizedBox(height: 12),
      
      // 内容：直接渲染，无背景
      MarkdownWidget(
        data: content,
        // ... 配置
      ),
    ],
  ),
)
```

### 3.3 思考气泡样式

```dart
// 思考气泡：保持轻量容器
Container(
  margin: EdgeInsets.only(bottom: 10),
  padding: EdgeInsets.all(12),
  decoration: BoxDecoration(
    color: isDark ? const Color(0x331D4ED8) : const Color(0x1A3B82F6),
    borderRadius: BorderRadius.circular(12),
    border: Border.all(
      color: isDark ? const Color(0x33493BFF) : const Color(0x33493BFF),
    ),
  ),
)
```

### 3.4 代码块样式

代码块保持现有增强样式，自带完整容器：

```dart
Container(
  margin: EdgeInsets.symmetric(vertical: 8),
  clipBehavior: Clip.antiAlias,
  decoration: BoxDecoration(
    color: isDark ? const Color(0xFF14161A) : const Color(0xFFF6F8FA),
    borderRadius: BorderRadius.circular(12),
    border: Border.all(
      color: isDark ? const Color(0x26FFFFFF) : const Color(0x1A000000),
    ),
  ),
)
```

---

## 4. 消息操作按钮

### 4.1 布局变化

由于 LLM 消息无气泡，操作按钮需要调整位置：

**方案 A：底部行**

```dart
Column(
  children: [
    // ... 消息内容
    SizedBox(height: 8),
    // 操作按钮行
    Row(
      mainAxisAlignment: MainAxisAlignment.start,
      children: [
        _ActionIcon(icon: Icons.copy, onTap: _copy),
        _ActionIcon(icon: Icons.refresh, onTap: _regenerate),
        _ActionIcon(icon: Icons.edit, onTap: _edit),
        _ActionIcon(icon: Icons.delete_outline, onTap: _delete),
      ],
    ),
  ],
)
```

**方案 B：悬浮工具栏 (推荐)**

```dart
Stack(
  children: [
    // 消息内容
    _MessageContent(),
    
    // 悬浮工具栏（鼠标悬停/长按时显示）
    Positioned(
      top: 0,
      right: 0,
      child: _HoverToolbar(
        visible: _isHovered || _isLongPressed,
        actions: [copy, regenerate, edit, delete],
      ),
    ),
  ],
)
```

### 4.2 操作按钮样式

```dart
Widget _buildActionButton(IconData icon, String tooltip, VoidCallback onTap) {
  return Tooltip(
    message: tooltip,
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(6),
      child: Padding(
        padding: EdgeInsets.all(6),
        child: Icon(
          icon,
          size: 16,
          color: Theme.of(context).colorScheme.onSurface.withOpacity(0.5),
        ),
      ),
    ),
  );
}
```

---

## 5. 分隔线设计

LLM 消息中的分隔线 (`---`) 渲染：

```dart
// 使用主题色的细线
Container(
  margin: EdgeInsets.symmetric(vertical: 12),
  height: 1,
  color: isDark 
      ? Colors.white.withOpacity(0.1) 
      : Colors.black.withOpacity(0.08),
)
```

---

## 6. 与现有设计的差异

### 6.1 变更对比

| 元素 | 当前设计 | 新设计 |
|------|----------|--------|
| 用户消息 | 气泡 + 头像 | 气泡 + 头像 (保持) |
| LLM 消息 | 气泡 + 头像 | **无气泡** + 头像 |
| 思考气泡 | 嵌套在消息气泡内 | **独立容器**，与正文平级 |
| 代码块 | 在消息气泡内 | **全宽度**，自带容器 |
| 操作按钮 | 气泡下方 | **悬浮工具栏** 或 底部行 |

### 6.2 代码修改范围

| 文件 | 修改内容 |
|------|----------|
| `textMessageBuilder` | 条件渲染用户/LLM 消息 |
| `_MessageBubble` | 拆分为 `_UserMessageBubble` 和 `_AssistantMessage` |
| `ChatDesignTokens` | 添加 LLM 消息相关 token |
| `MessageActions` | 适配悬浮工具栏模式 |

---

## 7. 实现步骤

### Phase 1: 基础布局

1. 修改 `textMessageBuilder` 区分用户/LLM 消息
2. 移除 LLM 消息的容器装饰
3. 调整 Padding 和 Margin

### Phase 2: 操作按钮

1. 实现悬浮工具栏组件
2. 添加鼠标悬停/长按检测
3. 调整按钮样式

### Phase 3: 细节优化

1. 统一分隔线样式
2. 优化代码块宽度
3. 添加过渡动画

---

## 8. 验收标准

- [ ] 用户消息保持气泡样式
- [ ] LLM 消息无气泡，直接渲染在背景上
- [ ] 思考气泡独立显示
- [ ] 代码块全宽度显示
- [ ] 操作按钮可见性良好
- [ ] 明暗主题一致性
- [ ] 流式输出时样式正确

---

*文档版本: 1.0*
*创建时间: 2024-12-21*
