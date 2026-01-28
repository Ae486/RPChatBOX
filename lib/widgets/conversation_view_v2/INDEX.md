# /lib/widgets/conversation_view_v2

一句话：V2 聊天视图拆分（基于 `flutter_chat_ui`），承载流式渲染、自动滚动、搜索定位、导出、编辑/重发、重生成等功能。

## 依赖规则（建议）
- 允许依赖：`models/*`、`services/*`、`controllers/*`、`adapters/*`、`chat_ui/*`、`utils/*`
- 禁止依赖：跨页面逻辑（不要直接 import `chat_page.dart`）；UI 组件尽量通过回调与 host 协作

## 文件清单
- `build.dart` - 核心 - Chat 组件组装（builders / composer / scroll button）
- `streaming.dart` - 核心 - 发送与流式输出、占位消息、落盘 finalize、取消
- `thread_projection.dart` - 核心 - 活动链投影（active chain），与 threadJson/activeLeafId 对齐
- `message_actions_sheet.dart` - 核心 - 长按/右键菜单（复制/编辑/重发/重生成/删除/导出）；重发/重生成不新增用户气泡，只裁剪并重新生成助手回复
- `scroll_and_highlight.dart` - 核心 - 搜索定位滚动、消息高亮、auto-follow 自动滚动
- `export_mode.dart` - 功能 - 批量导出模式（选择/全选/导出）
- `tokens_and_ids.dart` - 功能 - Token 统计与消息 ID 生成（避免 duplicate id）
- `user_bubble.dart` - UI - 用户气泡与附件预览（含 SelectionArea）
- 输入区：`lib/chat_ui/owui/composer/owui_composer.dart`（在 `build.dart` 注入；导出模式下置 0 高度）

---
⚠️ 改架构 / 加文件前，要先更新我
