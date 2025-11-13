# 代码渲染修复说明

## 问题诊断

用户发现修改 `enhanced_code_block.dart` 的颜色会同时影响单反引号和三反引号的显示，说明它们都在使用同一个组件。

## 根本原因

**flutter_markdown 的行为**：
- `CodeBlockBuilder` 处理所有 `<code>` 元素
- 无论是单反引号还是三反引号，都会触发 `CodeBlockBuilder`
- `CodespanBuilder` 在某些情况下不会被调用

## 解决方案

### 修改 `CodeBlockBuilder` 以区分两种代码

**文件**: `lib/widgets/optimized_latex_renderer.dart`

在 `CodeBlockBuilder.visitElementAfter()` 中添加判断逻辑：

```dart
// 检查是否有language class属性，这是三反引号代码块的特征
final className = element.attributes['class'];
final hasLanguageClass = className != null && className.startsWith('language-');

// 如果没有language class，这可能是单反引号行内代码
final isLikelyInlineCode = !hasLanguageClass && 
                            code.length < 100 && 
                            !code.contains('\n');

if (isLikelyInlineCode) {
  // 返回简单的行内代码样式
  return Container(...);
}

// 否则返回完整的代码块
return _CodeBlockWithCopy(...);
```

### 判断依据

1. **有 `language-xxx` class** → 三反引号代码块
2. **无 class + 短文本 + 无换行** → 单反引号行内代码
3. **其他情况** → 三反引号代码块

## 渲染路径

### 单反引号 `` `code` ``
```
MarkdownBody
  → CodeBlockBuilder.visitElementAfter()
    → 检测到：无language class + 短文本
      → 返回简单 Container（灰色背景 + 红色文字）
```

### 三反引号 ` ```code``` `
```
MarkdownBody
  → CodeBlockBuilder.visitElementAfter()
    → 检测到：有language class 或 长文本/多行
      → _CodeBlockWithCopy
        → EnhancedCodeBlock（完整代码块组件）
```

## 样式对比

| 特性 | 单反引号 | 三反引号 |
|------|---------|---------|
| 背景色 | 浅灰 `#F0F0F0` | 浅灰 `#ECECEC` |
| 边框 | 无 | 圆角容器 |
| 语言标签 | 无 | 有 |
| 复制按钮 | 无 | 有 |
| 语法高亮 | 无 | 有 |
| 横向滚动 | 无需 | 支持 |
| Padding | `(3, 1)` | `(16, 16)` |

## 测试验证

1. **单反引号**: `` `cout` `` → 应显示为紧凑的灰色背景文字
2. **三反引号**: 
   ````
   ```cpp
   int main() { return 0; }
   ```
   ````
   → 应显示为完整代码块（带header和滚动）

3. **修改颜色测试**:
   - 修改 `enhanced_code_block.dart` 第56行的颜色 → 只影响三反引号
   - 修改 `optimized_latex_renderer.dart` 第506行的颜色 → 只影响单反引号
