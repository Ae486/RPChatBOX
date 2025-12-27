# /lib/chat_ui/owui

一句话：OpenWebUI 风格（灰阶 + 简洁）聊天 UI 组件与主题工具集，供 V2（`flutter_chat_ui`）与后续页面复用。

## 依赖规则（建议）
- 允许依赖：`models/*`、`services/*`（只读）、`utils/*`、`design_system/*`
- 禁止依赖：具体页面（如 `chat_page.dart`）与业务流程控制（避免 UI 层反向依赖）

## 文件清单
- `palette.dart` - 核心 - OpenWebUI 灰阶色板与语义色
- `owui_tokens.dart` - 核心 - OpenWebUI tokens（ThemeExtension：颜色/圆角/间距/缩放）
- `owui_tokens_ext.dart` - 核心 - `BuildContext` 便捷访问（`context.owui*`）
- `chat_theme.dart` - 核心 - `flutter_chat_ui.ChatTheme` 映射与气泡装饰
- `assistant_message.dart` - UI - 助手消息（Markdown/Thinking/Meta）
- `markdown.dart` - UI - Markdown 渲染与扩展（代码块/mermaid/表格横向滚动 等）
- `code_block.dart` - UI - 代码块渲染
- `mermaid_block.dart` - UI - Mermaid 渲染
- `stable_body.dart` - UI - 稳定渲染容器（避免频繁重排）
- `message_highlight_sweep.dart` - UI - 消息高亮 overlay（不改布局，避免抖动）

## 子目录
- `components/` - OpenWebUI 风格基础组件壳（Scaffold/AppBar/Card/Dialog/SnackBar/Menu 等），供 pages/overlays 复用
- `composer/` - V2 输入区（OwuiComposer）：附件/联网/配置/模型/发送-停止 + 高度上报

---
⚠️ 改架构/加文件前，要先更新我
