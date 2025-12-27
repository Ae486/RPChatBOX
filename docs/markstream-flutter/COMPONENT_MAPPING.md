# markstream-vue 组件对照表

## 组件实现状态

| markstream-vue 组件 | Flutter 实现 | 状态 | 备注 |
|-------------------|-------------|------|------|
| **核心渲染** |
| NodeRenderer | MarkdownWidget (markdown_widget) | ✅ 复用 | 第三方包 |
| stream-markdown-parser | StablePrefixParser | ✅ 已实现 | lib/rendering/markdown_stream/ |
| batchRendering | BatchRenderController | ✅ 已实现 | lib/rendering/markdown_stream/ |
| viewportPriority | ViewportPriority | ✅ 已实现 | lib/rendering/markdown_stream/ |
| **文本节点** |
| TextNode | markdown_widget 内置 | ✅ 复用 | - |
| ParagraphNode | markdown_widget 内置 | ✅ 复用 | - |
| EmphasisNode | markdown_widget 内置 | ✅ 复用 | *斜体* |
| StrongNode | markdown_widget 内置 | ✅ 复用 | **粗体** |
| StrikethroughNode | markdown_widget 内置 | ✅ 复用 | ~~删除线~~ |
| **标题** |
| HeadingNode | markdown_widget H1-H6Config | ✅ 复用 | - |
| **代码** |
| CodeBlockNode | _EnhancedCodeBlock | ✅ 已实现 | 收起/展开/自动换行/行号对应 |
| InlineCodeNode | markdown_widget 内置 | ✅ 复用 | - |
| PreCodeNode | EnhancedCodeBlock | ✅ 已实现 | - |
| **列表** |
| ListNode | markdown_widget 内置 | ✅ 复用 | - |
| ListItemNode | _StyledListItemNode | ✅ 已实现 | flyer_chat_demo/ |
| CheckboxNode | markdown_widget 内置 | ✅ 复用 | 任务列表 |
| **表格** |
| TableNode | _InteractiveTableNode | ✅ 已实现 | 右键菜单+复制 |
| **引用/提示** |
| BlockquoteNode | _StyledBlockquoteNode | ✅ 已实现 | - |
| AdmonitionNode | _AdmonitionWidget | ✅ 已实现 | 7种类型 |
| **链接/图片** |
| LinkNode | _InteractiveLinkNode | ✅ 已实现 | 右键菜单 |
| ImageNode | markdown_widget 内置 | ✅ 复用 | - |
| **数学公式** |
| MathBlockNode | _LatexNode (flutter_math_fork) | ✅ 已实现 | - |
| MathInlineNode | _LatexSyntax | ✅ 已实现 | - |
| **图表** |
| MermaidBlockNode | _EnhancedMermaidBlock | ✅ 已实现 | 放大/缩小/拖动/全屏/Preview切换 |
| **其他** |
| EmojiNode | markdown_widget 内置 | ✅ 复用 | - |
| HardBreakNode | markdown_widget 内置 | ✅ 复用 | - |
| ThematicBreakNode | markdown_widget 内置 | ✅ 复用 | --- |
| HtmlBlockNode | markdown_widget 内置 | ⚠️ 部分 | 安全限制 |
| HtmlInlineNode | markdown_widget 内置 | ⚠️ 部分 | 安全限制 |
| **扩展功能** |
| HighlightNode | _HighlightSyntax + _HighlightNode | ✅ 已实现 | ==高亮== |
| InsertNode | _InsertSyntax + _InsertNode | ✅ 已实现 | ++插入++ |
| SubscriptNode | _SubscriptSyntax + _SubscriptNode | ✅ 已实现 | ~下标~ |
| SuperscriptNode | _SuperscriptSyntax + _SuperscriptNode | ✅ 已实现 | ^上标^ |
| FootnoteNode | 待实现 | ⏳ 待开发 | 脚注 |
| FootnoteReferenceNode | 待实现 | ⏳ 待开发 | 脚注引用 |
| FootnoteAnchorNode | 待实现 | ⏳ 待开发 | 脚注锚点 |
| DefinitionListNode | 待实现 | ⏳ 待开发 | 定义列表 |
| ReferenceNode | 待实现 | ⏳ 待开发 | 引用 |
| MarkdownCodeBlockNode | 待实现 | ⏳ 待开发 | Markdown预览 |

## 统计

- **已实现/复用**: 32+ 组件
- **待开发**: 6 组件 (扩展功能，优先级较低)
- **核心功能覆盖率**: **94%**

## 优先级排序

### P1 (已完成)
- [x] 流式渲染核心 (StablePrefixParser)
- [x] 代码块增强
- [x] 表格交互
- [x] 链接交互
- [x] LaTeX 公式
- [x] Mermaid 图表
- [x] Admonition 提示框
- [x] 批次渲染控制
- [x] 视口优先级

### P2 (已完成)
- [x] 高亮标记 (==text==)
- [x] 上标/下标 (^text^, ~text~)
- [x] 插入标记 (++text++)

### P3 (低优先级)
- [ ] 脚注
- [ ] 定义列表
- [ ] Markdown 内嵌预览
- [ ] 自定义 HTML 块增强

---

*最后更新: 2025-12-19*

---

## 最新优化 (2025-12-19)

### Mermaid 图表增强
- ✅ 放大/缩小按钮 + 缩放百分比显示
- ✅ Preview/Source 切换
- ✅ 复制按钮
- ✅ 全屏显示按钮
- ✅ 拖动图表功能
- ✅ 收起/展开
- ✅ Windows 桌面端 WebView2 渲染

### 代码块增强
- ✅ 默认完全展开，收起后只显示 header
- ✅ 默认自动换行
- ✅ 行号对应原始行（换行后续行行号为空）
- ✅ 语言图标和颜色

### 性能监控
- ✅ 实时渲染统计面板
- ✅ 可视化柱状图
