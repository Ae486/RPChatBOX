# markstream-flutter 编码规范

> 供 AI 助手参考的编码规范
> 基于项目实践总结
> 最后更新: 2025-12-19

---

## 1. 文件组织

### 1.1 Part 文件模式

Demo 组件使用 `part` 文件模式，所有 `part` 文件共享主文件的 import：

```dart
// 主文件: flyer_chat_demo_page.dart
import 'package:flutter/material.dart';
import 'package:flutter_highlight/flutter_highlight.dart';
// ... 其他 import

part 'flyer_chat_demo/enhanced_code_block.dart';
part 'flyer_chat_demo/mermaid_block.dart';
// ... 其他 part
```

```dart
// Part 文件: enhanced_code_block.dart
part of '../flyer_chat_demo_page.dart';

// ⚠️ 禁止在 part 文件中使用 import 语句
// 所有依赖必须在主文件中导入
```

### 1.2 命名约定

| 类型 | 约定 | 示例 |
|-----|------|------|
| 私有类 | 下划线前缀 | `_EnhancedCodeBlock` |
| 私有方法 | 下划线前缀 | `_buildHeader()` |
| 私有枚举 | 下划线前缀 | `_MermaidTab` |
| 工具函数 | 下划线前缀 | `_getCodeTheme()` |
| 公共类 | PascalCase | `EnhancedCodeBlock` |

### 1.3 文件结构

```
lib/pages/flyer_chat_demo/
├── enhanced_code_block.dart    # 代码块组件
├── mermaid_block.dart          # Mermaid 组件
├── latex.dart                  # LaTeX 组件
├── admonition_node.dart        # Admonition 组件
├── highlight_syntax.dart       # 高亮语法
├── insert_syntax.dart          # 插入语法
├── sub_sup_syntax.dart         # 上下标语法
├── markdown_nodes.dart         # Markdown 节点
├── streaming_markdown_body.dart # 流式渲染
├── streaming_code_block_preview.dart # 流式代码块
├── streaming_state.dart        # 流式状态
├── demo_data.dart              # 测试数据
└── performance_monitor.dart    # 性能监控
```

---

## 2. 组件设计

### 2.1 StatefulWidget 模式

```dart
class _EnhancedCodeBlock extends StatefulWidget {
  // 1. 必需参数优先
  final String code;
  final String language;
  final bool isDark;
  
  // 2. 可选参数带默认值
  final bool isStreaming;
  final bool showHeader;

  const _EnhancedCodeBlock({
    required this.code,
    required this.language,
    required this.isDark,
    this.isStreaming = false,
    this.showHeader = true,
  });

  @override
  State<_EnhancedCodeBlock> createState() => _EnhancedCodeBlockState();
}

class _EnhancedCodeBlockState extends State<_EnhancedCodeBlock> {
  // 3. 状态变量
  bool _isCollapsed = false;
  final ScrollController _scrollController = ScrollController();

  // 4. 生命周期方法
  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  // 5. 业务方法
  Future<void> _copyCode() async { ... }

  // 6. 构建方法
  Widget _buildHeader() { ... }
  Widget _buildCodeContent() { ... }

  // 7. build 方法
  @override
  Widget build(BuildContext context) { ... }
}
```

### 2.2 主题适配

```dart
// 使用 isDark 参数而非 Theme.of(context)
// 避免重复计算，提升性能

Widget build(BuildContext context) {
  // ✅ 推荐
  final bgColor = widget.isDark 
      ? const Color(0xFF14161A) 
      : const Color(0xFFF6F8FA);
  
  // ❌ 避免
  final isDark = Theme.of(context).brightness == Brightness.dark;
}
```

### 2.3 颜色定义

```dart
// 使用 const Color 定义颜色，避免运行时计算
const _darkBg = Color(0xFF14161A);
const _lightBg = Color(0xFFF6F8FA);

// 透明度使用 withValues
color.withValues(alpha: 0.5);  // ✅ 新 API
color.withOpacity(0.5);        // ⚠️ 旧 API（已弃用）
```

---

## 3. Markdown 扩展

### 3.1 自定义语法

```dart
/// 自定义语法类
class _HighlightSyntax extends m.InlineSyntax {
  _HighlightSyntax() : super(r'==((?:[^=]|(?<!=)=(?!=))+)==');

  @override
  bool onMatch(m.InlineParser parser, Match match) {
    final el = m.Element.text('highlight', match[1]!);
    parser.addNode(el);
    return true;
  }
}
```

### 3.2 自定义节点

```dart
/// 自定义节点类
class _HighlightNode extends ElementNode {
  final MarkdownConfig config;
  final bool isDark;

  _HighlightNode({
    required this.config,
    required this.isDark,
  });

  @override
  InlineSpan build() {
    return WidgetSpan(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 4),
        decoration: BoxDecoration(
          color: isDark 
              ? Colors.yellow.withValues(alpha: 0.3)
              : Colors.yellow.withValues(alpha: 0.5),
          borderRadius: BorderRadius.circular(3),
        ),
        child: Text.rich(childrenSpan),
      ),
    );
  }
}
```

### 3.3 Generator 注册

```dart
/// 在 MarkdownGenerator 中注册
markdownGenerator: MarkdownGenerator(
  generators: [
    _highlightGenerator(isDark: isDark),
    _insertGenerator(isDark: isDark),
  ],
  inlineSyntaxList: [
    _HighlightSyntax(),
    _InsertSyntax(),
  ],
),
```

---

## 4. 流式渲染

### 4.1 稳定前缀模式

```dart
/// 分割稳定部分和尾部
({String stable, String tail}) _splitStableMarkdown(String source) {
  // 查找最后一个稳定边界
  // 返回已完成的稳定部分和正在输入的尾部
}
```

### 4.2 缓存策略

```dart
class _StreamingMarkdownBodyState extends State<_StreamingMarkdownBody> {
  String _cachedStable = '';
  Widget? _cachedStableWidget;
  
  void _ensureStableCache() {
    if (_parts.stable != _cachedStable) {
      _cachedStable = _parts.stable;
      _cachedStableWidget = RepaintBoundary(
        child: widget.markdown(_cachedStable),
      );
    }
  }
}
```

### 4.3 代码块检测

```dart
/// 检测正在输入的代码块
static ({String language, String code, String rest, bool isClosed})? 
    _extractLeadingFence(String input) {
  final match = RegExp(r'^\s*(```|~~~)([^\n\r]*)\r?\n?').firstMatch(input);
  if (match == null) return null;
  // ...
}
```

---

## 5. 性能优化

### 5.1 RepaintBoundary

```dart
// 对稳定内容使用 RepaintBoundary
_cachedStableWidget = RepaintBoundary(
  child: widget.markdown(_cachedStable),
);
```

### 5.2 const 构造

```dart
// 尽可能使用 const
const SizedBox(width: 8);
const EdgeInsets.all(12);
const BorderRadius.all(Radius.circular(12));
```

### 5.3 避免不必要的重建

```dart
// 使用 ValueKey 避免不必要的重建
AnimatedSwitcher(
  child: KeyedSubtree(
    key: ValueKey(_tab == _MermaidTab.preview ? 'preview' : 'source'),
    child: body,
  ),
)
```

---

## 6. 测试数据

### 6.1 压力测试命令

```dart
// 支持的命令
'/stress'        // 完整压力测试
'/stress code'   // 代码块测试
'/stress math'   // 数学公式测试
'/stress mermaid' // Mermaid 测试
'/stress table'  // 表格测试
```

### 6.2 测试数据生成

```dart
class _StressTestData {
  static String generateCodeHeavy() { ... }
  static String generateMathHeavy() { ... }
  static String generateMermaidCharts() { ... }
  static String generateTableHeavy() { ... }
}
```

---

## 7. 文档注释

### 7.1 类注释

```dart
/// 增强版代码块组件
/// 
/// 参考 markstream-vue: src/components/CodeBlockNode/CodeBlockNode.vue
/// 功能：
/// - 默认完全展开，收起后只显示 header
/// - 默认自动换行
/// - 行号对应原始行
/// - 语法高亮（支持多种主题）
class _EnhancedCodeBlock extends StatefulWidget {
```

### 7.2 方法注释

```dart
/// 计算每行的显示行数（考虑自动换行）
/// 
/// [code] 代码内容
/// [maxWidth] 最大宽度
/// [style] 文本样式
/// 
/// 返回每行的行号列表，-1 表示续行
List<int> _calculateWrappedLineNumbers(
  String code, 
  double maxWidth, 
  TextStyle style,
) { ... }
```

---

## 8. 错误处理

### 8.1 安全的异步操作

```dart
Future<void> _copyCode() async {
  await Clipboard.setData(ClipboardData(text: widget.code));
  if (!mounted) return; // 检查组件是否仍然挂载
  ScaffoldMessenger.of(context).showSnackBar(...);
}
```

### 8.2 错误回退

```dart
// LaTeX 渲染错误回退
Math.tex(
  content,
  onErrorFallback: (error) {
    return Text(
      textContent,
      style: style.copyWith(color: Colors.red),
    );
  },
);
```

---

## 9. 平台适配

### 9.1 平台检测

```dart
bool get _isDesktop => 
    Platform.isWindows || Platform.isLinux || Platform.isMacOS;

bool get _isMobile => 
    Platform.isAndroid || Platform.isIOS;
```

### 9.2 平台特定实现

```dart
// Mermaid 渲染的平台适配
if (Platform.isWindows) {
  // 使用 webview_windows
} else if (Platform.isAndroid || Platform.isIOS) {
  // 使用 webview_flutter
} else {
  // 降级到外部预览
}
```

---

## 10. 代码审查清单

- [ ] 是否使用了 const 构造函数
- [ ] 是否在异步操作后检查 mounted
- [ ] 是否正确处理了 dispose
- [ ] 是否避免了在 part 文件中使用 import
- [ ] 是否使用了 RepaintBoundary 优化性能
- [ ] 是否添加了必要的文档注释
- [ ] 是否处理了平台差异
- [ ] 是否使用了新的 Color API (withValues)

---

*本规范基于项目实践总结，持续更新*
