# 流式输出集成指导文档

> 将 markstream-flutter Demo 组件集成到生产 ConversationView
> 最后更新: 2025-12-21

---

## 1. 当前架构对比

### 1.1 Demo 页面 (flyer_chat_demo_page.dart)

```dart
// 使用 flutter_chat_ui 的 Chat 组件
Chat(
  chatController: _chatController,
  builders: Builders(
    textMessageBuilder: (context, message, index, {...}) {
      // 自定义 Markdown 渲染
      return MarkdownWidget(data: message.text, ...);
    },
    textStreamMessageBuilder: (context, message, index, {...}) {
      // 流式消息渲染
      return FlyerChatTextStreamMessage(...);
    },
  ),
)
```

**关键组件**:
- `_DemoStreamManager`: 管理流式状态
- `_StreamingMarkdownBody`: 流式 Markdown 渲染
- `_EnhancedCodeBlock`: 增强代码块
- `_EnhancedMermaidBlock`: 增强 Mermaid 图表

### 1.2 生产页面 (ConversationView)

```dart
// 使用 ScrollablePositionedList 手动构建
ScrollablePositionedList.builder(
  itemScrollController: _itemScrollController,
  itemBuilder: (context, index) {
    return _buildMessageBubble(
      content: message.content,
      isUser: message.isUser,
    );
  },
)
```

**关键组件**:
- `EnhancedStreamController`: 流式输出控制
- `ChunkBuffer`: 批量处理 chunk
- `SmartScrollController`: 智能滚动
- `EnhancedContentRenderer`: Markdown 渲染

---

## 2. 集成方案

### 2.1 方案 A：渐进式替换（推荐）

**步骤**:

1. **替换 Markdown 渲染器**
   ```dart
   // 在 _buildMessageBubble 中替换 EnhancedContentRenderer
   // 改为使用 Demo 的 MarkdownWidget 配置
   
   Widget buildMarkdown(String text) {
     return MarkdownWidget(
       data: text,
       config: config.copy(configs: [
         PreConfig(
           theme: isDark ? monokaiSublimeTheme : githubTheme,
           wrapper: (child, code, language) {
             return _EnhancedCodeBlock(
               code: code,
               language: language,
               isDark: isDark,
             );
           },
         ),
         // ... 其他配置
       ]),
       markdownGenerator: MarkdownGenerator(
         generators: [
           _latexGenerator,
           _interactiveLinkGenerator(),
           // ... 其他生成器
         ],
       ),
     );
   }
   ```

2. **集成代码块组件**
   ```dart
   // 复制 enhanced_code_block.dart 到 lib/rendering/widgets/
   // 调整导入路径
   
   import '../rendering/widgets/enhanced_code_block.dart';
   ```

3. **集成 Mermaid 组件**
   ```dart
   // 复制 mermaid_block.dart 到 lib/rendering/widgets/
   // 确保 WebView 依赖正确配置
   ```

4. **保留现有流式输出逻辑**
   ```dart
   // 继续使用 ChunkBuffer + SmartScrollController
   // 仅替换渲染组件
   ```

### 2.2 方案 B：完整替换为 flutter_chat_ui

详见 [FLUTTER_CHAT_UI_MIGRATION_GUIDE.md](./FLUTTER_CHAT_UI_MIGRATION_GUIDE.md)

---

## 3. 关键代码迁移

### 3.1 代码块渲染迁移

**当前生产代码** (EnhancedContentRenderer):
```dart
// 使用 markdown_widget 的默认代码块
PreConfig(
  theme: isDark ? vs2015Theme : githubTheme,
)
```

**目标代码** (使用 _EnhancedCodeBlock):
```dart
PreConfig(
  theme: isDark ? vs2015Theme : githubTheme,
  wrapper: (child, code, language) {
    final lang = language.trim().toLowerCase();
    if (lang == 'mermaid') {
      return _EnhancedMermaidBlock(
        mermaidCode: code,
        isDark: isDark,
      );
    }
    return _EnhancedCodeBlock(
      code: code,
      language: lang,
      isDark: isDark,
      isStreaming: false,
    );
  },
)
```

### 3.2 流式代码块处理

**关键点**: 流式输出时使用 `isStreaming: true`

```dart
// 在流式消息渲染中
_EnhancedCodeBlock(
  code: code,
  language: language,
  isDark: isDark,
  isStreaming: true, // 流式模式：纯文本渲染，避免高亮闪烁
)
```

### 3.3 思考气泡兼容

**Demo 实现**:
```dart
// 使用 _splitByThinkingBlocks 分割
final segments = _splitByThinkingBlocks(message.text);
for (final seg in segments) {
  if (seg.kind == 'thinking') {
    // 渲染思考气泡
  } else {
    // 渲染正文
  }
}
```

**生产代码已有实现**:
```dart
// ConversationView._buildInlineThinkingSection
// 可以复用现有逻辑
```

---

## 4. 文件迁移清单

| Demo 文件 | 目标位置 | 说明 |
|----------|---------|------|
| `enhanced_code_block.dart` | `lib/rendering/widgets/` | 增强代码块 |
| `mermaid_block.dart` | `lib/rendering/widgets/` | Mermaid 图表 |
| `latex.dart` | `lib/rendering/widgets/` | LaTeX 公式 |
| `highlight_syntax.dart` | `lib/rendering/markdown/` | 高亮语法 |
| `insert_syntax.dart` | `lib/rendering/markdown/` | 插入语法 |
| `sub_sup_syntax.dart` | `lib/rendering/markdown/` | 上下标 |
| `admonition_node.dart` | `lib/rendering/widgets/` | 提示框 |

---

## 5. 依赖检查

### 5.1 必需依赖

```yaml
dependencies:
  markdown_widget: ^2.x.x
  flutter_highlight: ^0.7.0
  highlight: ^0.7.0  # 需要添加为直接依赖
  flutter_math_fork: ^0.7.x
  webview_flutter: ^4.x.x  # Mermaid 渲染
  webview_windows: ^0.4.x  # Windows Mermaid
```

### 5.2 平台配置

**Android**: 已配置 WebView  
**iOS**: 已配置 WKWebView  
**Windows**: 需要 WebView2 Runtime

---

## 6. 测试验证

### 6.1 功能测试

- [ ] 代码块语法高亮
- [ ] 代码块框选复制（保留换行）
- [ ] 代码块展开/收缩动画
- [ ] Mermaid 图表渲染
- [ ] LaTeX 公式渲染
- [ ] 流式输出无抖动
- [ ] 自动滚动跟随

### 6.2 性能测试

- [ ] 大代码块渲染性能
- [ ] 长对话滚动性能
- [ ] 流式输出 FPS

---

## 7. 风险与缓解

| 风险 | 等级 | 缓解措施 |
|-----|------|---------|
| WebView 兼容性 | 中 | 保留外部预览降级方案 |
| 性能回退 | 低 | 保留现有 ChunkBuffer 优化 |
| 样式不一致 | 低 | 统一使用 ChatBoxChatTheme |

---

*本文档基于生产代码审查生成*
