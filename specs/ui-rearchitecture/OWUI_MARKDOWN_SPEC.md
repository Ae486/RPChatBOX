# OWUI Markdown 渲染规范（OwuiMarkdown）
> `/specs/ui-rearchitecture` - V2（`flutter_chat_ui`）下的 OpenWebUI 风格 Markdown 渲染与交互约定  
> 创建时间: 2025-12-24  

---

## 1. 背景与目标
- `OwuiMarkdown` 是 V2 助手消息的核心渲染器：负责 Markdown/代码块/Mermaid/LaTeX/表格等内容展示。
- 目标：以 `flyer_chat_demo` 为准，迁移其“可读性 + 可交互性 + 流式稳定渲染”策略到生产 V2。

---

## 2. 关键能力（必须）
### 2.1 流式稳定渲染
- 流式输出时使用稳定前缀切分策略（`StablePrefixParser`），避免频繁重排导致抖动。

### 2.2 代码块 / Mermaid / LaTeX
- 代码块：语法高亮 + 复制等增强能力（沿用 OWUI 现有实现）。
- Mermaid：基于 WebView 渲染（Windows 依赖 WebView2 runtime）。
- LaTeX：支持 `$...$` 与 `$$...$$`。

### 2.3 表格：窄屏横向滚动（本次新增）
- 要求：当页面宽度不足时，表格可横向滚动，避免溢出/挤压导致不可读。
- 实现：通过 `markdown_widget.TableConfig.wrapper` 包裹 table：
  - 外层：`SingleChildScrollView(scrollDirection: Axis.horizontal)`
  - 保底宽度：`ConstrainedBox(minWidth: constraints.maxWidth)`
  - 桌面端：展示可交互 `Scrollbar`（移动端不强制显示）
- 参考来源：`lib/pages/flyer_chat_demo/markdown_nodes.dart` 的 `_MarkdownTableWrapper`。

---

## 3. 代码入口
- 渲染器：`lib/chat_ui/owui/markdown.dart`
- 表格 wrapper：`_OwuiMarkdownTableWrapper`（同文件内）

---

## 4. 手测清单
- 窄屏（手机竖屏）含表格消息：表格可左右拖动查看完整列
- 桌面端：表格出现横向滚动条，且可拖动
- 流式输出过程中出现表格：不崩溃、不抖动、不卡死

