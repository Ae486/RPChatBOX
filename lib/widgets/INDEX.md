# /lib/widgets

一句话：可复用 UI 组件（非路由级），包含对话抽屉、对话配置对话框、V2 聊天视图与其配套的渲染/状态组件。

## 依赖规则（建议）
- 允许依赖：`models/*`、`services/*`、`utils/*`、`chat_ui/*`
- 禁止依赖：`pages/*`（避免组件反向依赖路由）

## 文件清单
- `conversation_view_host.dart` - 聊天视图宿主（当前固定委派 V2，暴露 scroll/export/tuning 等 state API）
- `conversation_view_v2.dart` - V2 主聊天视图入口（`flutter_chat_ui` 集成）
- `conversation_view_v2/` - V2 子模块拆分（见该目录 `INDEX.md`）
- `conversation_drawer.dart` - 会话列表 Drawer（分组/重命名/删除/角色入口）
- `conversation_config_dialog.dart` - 单会话配置对话框（参数/上下文/实验开关）
- `add_model_dialog.dart` - 添加模型对话框（检测/批量选择）
- `provider_card.dart` - Provider 管理卡片（ModelServicesPage 使用）
- `stream_manager.dart` - 流式状态管理（thinking/streaming 生命周期）
- `mermaid_renderer.dart` - Mermaid 渲染底层（WebView/外部预览）

---
⚠️ 组件改动建议以“页面冒烟 + flutter test”验证，避免破坏导航/回调链
