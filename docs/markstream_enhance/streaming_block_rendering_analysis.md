# 流式 Markdown 渲染问题分析文档

## 1. 核心需求

**用户要求**：流式渲染时不展示 markdown 原始语法文本，注重视觉体验。

**关键原则**：当检测到块级信号（代码块、mermaid、latex、think 等）时：
1. **立即渲染该块的 UI 容器/包裹器**
2. **在容器内部输出内容**
3. **用户永远不会看到 `\`\`\``、`$$`、`<think>` 等原始语法标记**

**参考实现**：`lib/pages/flyer_chat_demo/streaming_markdown_body.dart`

---

## 2. 当前实现架构分析

### 2.1 核心文件关系

```
ConversationViewV2
    └── _handleStreamFlush() [streaming.dart:270]
            │
            └── OwuiMarkdown [markdown.dart:234]
                    │
                    ├── StablePrefixParser.split() [stable_prefix_parser.dart:26]
                    │       → 返回 (stable, tail)
                    │
                    └── OwuiStableBody [stable_body.dart:7]
                            │
                            ├── extractLeadingFence() [stable_body.dart:32]
                            │       → 仅检测代码块 ``` 或 ~~~
                            │
                            └── build() [stable_body.dart:99]
                                    ├── stable → _buildMarkdownWidget()
                                    └── tail → 代码块容器 OR 纯文本
```

### 2.2 当前流程

1. **流式数据到达** → `_handleStreamFlush()` 被调用
2. **稳定前缀解析** → `StablePrefixParser.split(text)` 将文本分为 stable 和 tail
3. **stable 部分** → 完整的 Markdown 渲染
4. **tail 部分处理**：
   - 如果以 `\`\`\`` 开头 → 调用 `extractLeadingFence()` → 渲染 `OwuiCodeBlock` 容器
   - **否则 → 作为纯文本 (`Text` widget) 显示**

---

## 3. 问题诊断

### 3.1 核心问题：只有代码块实现了容器优先渲染

| 块类型 | 信号标记 | 当前处理方式 | 问题 |
|--------|----------|--------------|------|
| 代码块 | ` ``` ` | ✅ 容器渲染 | 正常 |
| Mermaid | ` ```mermaid ` | ✅ 在代码块内处理 | 正常 |
| **LaTeX 块** | `$$` | ❌ 纯文本显示 | **会暴露 `$$ x^2 $$`** |
| **Think 块** | `<think>` | ❌ 纯文本显示 | **会暴露 `<think>...`** |
| **HTML 块** | `<div>` 等 | ❌ 纯文本显示 | **会暴露原始 HTML** |
| **表格** | `\|...\|` | ❌ 纯文本显示 | **会暴露管道符号** |

### 3.2 问题代码位置

**`stable_body.dart:99-152` - build() 方法**

```dart
@override
Widget build(BuildContext context) {
  final parts = _parts;

  // 仅检测代码块
  final fence = widget.streamingCodeBlock == null
      ? null
      : OwuiStableBody.extractLeadingFence(parts.tail);  // ← 只检测 ```

  // 当 stable 为空且无代码块时
  if (parts.stable.isEmpty) {
    if (fence != null) {
      // 代码块容器渲染 ✅
      return Column(...);
    }

    // ❌ 问题：直接显示原始 tail 文本
    return Text(parts.tail, style: widget.plainTextStyle);
  }

  // ...同样的问题在其他分支
}
```

### 3.3 `extractLeadingFence` 只检测代码块

**`stable_body.dart:32-53`**

```dart
static ({String language, String code, String rest, bool isClosed})? extractLeadingFence(
  String input,
) {
  // 只匹配 ``` 或 ~~~
  final match = RegExp(r'^\s*(```|~~~)([^\n\r]*)\r?\n?').firstMatch(input);
  if (match == null) return null;  // ← LaTeX、think 等返回 null

  // ...
}
```

### 3.4 StablePrefixParser 检测但不渲染

`StablePrefixParser` 正确检测了所有块类型：
- 围栏代码块 (`\`\`\``)
- 数学块 (`$$`)
- Think 标签 (`<think>`)
- HTML 块 (`<div>` 等)
- 表格 (`|...|`)

**但它只负责分割**，不负责渲染容器。当这些块进入 tail 时，`OwuiStableBody.build()` 只会将其作为纯文本显示。

---

## 4. 对比：flyer_chat_demo 的实现

### 4.1 Demo 的 `_StreamingMarkdownBody`

**`streaming_markdown_body.dart:120-143`**

```dart
@override
Widget build(BuildContext context) {
  final parts = _parts;

  final fence = widget.streamingCodeBlock == null
      ? null
      : _StreamingMarkdownBody._extractLeadingFence(parts.tail);

  if (parts.stable.isEmpty) {
    if (fence != null) {
      return Column(
        children: [
          widget.streamingCodeBlock!(
            language: inferCodeLanguage(declaredLanguage: fence.language, code: fence.code),
            code: fence.code,
            isClosed: fence.isClosed,
          ),
          if (fence.rest.isNotEmpty) Text(fence.rest, style: widget.plainTextStyle),
        ],
      );
    }

    // Demo 也有同样的问题 - 但 Demo 只是演示代码块
    return Text(parts.tail, style: widget.plainTextStyle);
  }
  // ...
}
```

### 4.2 Demo 的限制

Demo (`flyer_chat_demo`) 同样只实现了代码块的容器优先渲染，这是因为 Demo 的目标是演示代码块流式预览功能，而非完整的块级信号处理。

**生产环境需要扩展这个模式到所有块类型。**

---

## 5. 需要扩展的块类型

### 5.1 LaTeX 数学块

**信号**：以 `$$` 开头（块级）或 `$` 开头（行内）

**期望行为**：
1. 检测到 `$$` → 立即渲染 LaTeX 容器（可以是占位框）
2. 在容器内显示正在解析的内容
3. 闭合后渲染完整公式

**当前问题**：
```
流式输入: "这是一个公式：\n$$\nx^2 + y^2"
显示结果: "这是一个公式：\n$$\nx^2 + y^2" ← 暴露原始语法
期望结果: "这是一个公式：\n[LaTeX 容器: x^2 + y^2 渲染中...]"
```

### 5.2 Think 块

**信号**：`<think>`、`<thinking>`、`<thought>`、`<thoughts>`

**期望行为**：
1. 检测到 `<think>` → 立即渲染 Think 容器
2. 在容器内显示思考过程（可折叠）
3. 闭合后完成渲染

**当前问题**：
```
流式输入: "<think>\n让我思考一下..."
显示结果: "<think>\n让我思考一下..." ← 暴露原始标签
期望结果: "[思考中容器: 让我思考一下...]"
```

### 5.3 表格

**信号**：以 `|` 开始的行

**期望行为**：
1. 检测到表格头 → 渲染表格容器
2. 等待分隔行确认表格
3. 流式填充单元格

**当前问题**：
```
流式输入: "| Name | Age |\n| --- | --- |"
显示结果: "| Name | Age |\n| --- | --- |" ← 暴露管道符号
期望结果: [表格容器: Name | Age]
```

---

## 6. 解决方案设计

### 6.1 扩展 extractLeadingFence → extractLeadingBlock

创建一个统一的块信号提取器，返回块类型和内容：

```dart
enum StreamingBlockType {
  code,      // ```
  mermaid,   // ```mermaid
  latex,     // $$
  think,     // <think>
  table,     // |...|
  html,      // <div> 等
}

typedef StreamingBlockMatch = ({
  StreamingBlockType type,
  String? language,  // 仅代码块使用
  String content,
  String rest,
  bool isClosed,
});

static StreamingBlockMatch? extractLeadingBlock(String input) {
  // 1. 检测代码块 (优先级最高)
  final fence = extractLeadingFence(input);
  if (fence != null) {
    final lang = inferCodeLanguage(...);
    return (
      type: lang == 'mermaid' ? StreamingBlockType.mermaid : StreamingBlockType.code,
      language: lang,
      content: fence.code,
      rest: fence.rest,
      isClosed: fence.isClosed,
    );
  }

  // 2. 检测 LaTeX 块
  final latex = extractLeadingLatex(input);
  if (latex != null) {
    return (type: StreamingBlockType.latex, ...);
  }

  // 3. 检测 Think 块
  final think = extractLeadingThink(input);
  if (think != null) {
    return (type: StreamingBlockType.think, ...);
  }

  // 4. 其他块类型...

  return null;
}
```

### 6.2 扩展 OwuiStableBody 回调

```dart
class OwuiStableBody extends StatefulWidget {
  // 现有
  final Widget Function({...})? streamingCodeBlock;

  // 新增
  final Widget Function({required String content, required bool isClosed})? streamingLatexBlock;
  final Widget Function({required String content, required bool isClosed})? streamingThinkBlock;
  final Widget Function({required String content, required bool isClosed})? streamingTableBlock;
}
```

### 6.3 修改 build() 方法

```dart
@override
Widget build(BuildContext context) {
  final parts = _parts;

  // 使用统一的块信号提取器
  final block = extractLeadingBlock(parts.tail);

  if (block != null) {
    final blockWidget = switch (block.type) {
      StreamingBlockType.code => widget.streamingCodeBlock!(...),
      StreamingBlockType.mermaid => widget.streamingMermaidBlock!(...),
      StreamingBlockType.latex => widget.streamingLatexBlock!(...),
      StreamingBlockType.think => widget.streamingThinkBlock!(...),
      _ => null,
    };

    if (blockWidget != null) {
      return Column(
        children: [
          if (_cachedStableWidget != null) _cachedStableWidget!,
          blockWidget,
          if (block.rest.isNotEmpty) Text(block.rest, ...),
        ],
      );
    }
  }

  // 无块信号时的处理...
}
```

---

## 7. 实施优先级

### P0 - 必须修复（视觉体验核心）

1. **LaTeX 块容器** - 用户经常使用数学公式
2. **Think 块容器** - AI 思考过程暴露标签很不专业

### P1 - 重要改进

3. **表格容器** - 表格流式渲染体验
4. **HTML 块容器** - 通用 HTML 支持

### P2 - 增强

5. **块引用容器** - `>` 引用块
6. **列表容器** - 有序/无序列表

---

## 8. 相关文件清单

| 文件 | 作用 | 需要修改 |
|------|------|----------|
| `lib/chat_ui/owui/stable_body.dart` | 流式渲染核心 | ✅ 扩展块检测和渲染 |
| `lib/chat_ui/owui/markdown.dart` | Markdown 渲染入口 | ✅ 添加新回调 |
| `lib/rendering/markdown_stream/stable_prefix_parser.dart` | 稳定前缀解析 | 可能需要优化 |
| `lib/widgets/conversation_view_v2/streaming.dart` | 流式控制 | 可能无需修改 |
| `lib/chat_ui/owui/code_block.dart` | 代码块 UI | 参考实现 |
| `lib/chat_ui/owui/mermaid_block.dart` | Mermaid UI | 参考实现 |
| **新增** `lib/chat_ui/owui/latex_block.dart` | LaTeX 流式容器 | 新建 |
| **新增** `lib/chat_ui/owui/think_block.dart` | Think 流式容器 | 新建 |

---

## 9. 技术风险与注意事项

### 9.1 性能考量

- 块信号检测在每次流式更新时都会执行
- 需要确保正则匹配的效率
- 建议使用预编译的正则表达式

### 9.2 边界情况

- 嵌套块：代码块内的 `$$` 不应触发 LaTeX 检测
- 转义字符：`\$$` 应被视为普通文本
- 不完整的块：`$$x^2` 没有闭合时的处理

### 9.3 回退策略

- 如果块检测失败，应该有合理的 fallback
- 不应因为检测错误而崩溃

---

## 10. 下一步行动

1. **确认优先级** - 与用户确认 P0 项目是否正确
2. **实现 extractLeadingLatex** - 基于 `_extractLeadingFence` 模式
3. **实现 extractLeadingThink** - 基于 `_extractLeadingFence` 模式
4. **创建流式 LaTeX 容器组件** - 参考 `OwuiCodeBlock`
5. **创建流式 Think 容器组件** - 参考 `OwuiCodeBlock`
6. **集成到 OwuiStableBody** - 修改 build 方法
7. **测试验证** - 各种边界情况测试

---

## 附录 A：当前代码块流式渲染的完整流程

```
1. 流式 chunk 到达
   ↓
2. _handleStreamFlush() 调用 _chatController.updateMessage()
   ↓
3. OwuiMarkdown.build() 被触发
   ↓
4. StablePrefixParser.split() 返回 (stable, tail)
   ↓
5. OwuiStableBody.build() 执行：
   ├── stable → _buildMarkdownWidget() → 完整 MD 渲染
   └── tail → extractLeadingFence() 检测
               ├── 有代码块 → OwuiCodeBlock 容器渲染
               └── 无代码块 → Text(tail) 纯文本 ❌
   ↓
6. 代码块内部：
   ├── isStreaming=true → 显示 "Streaming..." + 实时代码
   └── isClosed=true → 完整高亮渲染
```

## 附录 B：期望的完整块级渲染流程

```
1. 流式 chunk 到达
   ↓
2. _handleStreamFlush() 调用 _chatController.updateMessage()
   ↓
3. OwuiMarkdown.build() 被触发
   ↓
4. StablePrefixParser.split() 返回 (stable, tail)
   ↓
5. OwuiStableBody.build() 执行：
   ├── stable → _buildMarkdownWidget() → 完整 MD 渲染
   └── tail → extractLeadingBlock() 统一检测
               ├── 代码块 → OwuiCodeBlock 容器
               ├── Mermaid → OwuiMermaidBlock 容器
               ├── LaTeX → OwuiLatexBlock 容器 ← 新增
               ├── Think → OwuiThinkBlock 容器 ← 新增
               ├── Table → OwuiTableBlock 容器 ← 新增
               └── 无块信号 → Text(tail) 纯文本
   ↓
6. 用户永远不会看到原始语法标记
```
