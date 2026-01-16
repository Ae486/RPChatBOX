# /lib/pages

一句话：路由级页面（Page / Route），负责承载业务流转与页面布局；内部使用 `lib/widgets/*` 与 `lib/chat_ui/owui/*` 组件组合 UI。

## 依赖规则（建议）
- 允许依赖：`widgets/*`、`chat_ui/*`、`services/*`、`models/*`、`utils/*`
- 禁止被依赖：页面不应被底层组件反向 import（避免 UI 组件耦合路由与业务）

## 文件清单
- `chat_page.dart` - 主页面（home）：会话列表/抽屉/聊天视图/搜索/设置入口
- `settings_page.dart` - 设置入口：外观/模型管理/缓存清理/调试入口
- `display_settings_page.dart` - 显示设置（缩放/字体/主题）
- `model_services_page.dart` - Provider/Model 管理入口
- `provider_detail_page.dart` - Provider 详情（API 配置 + 模型列表/编辑/添加）
- `model_edit_page.dart` - 模型能力编辑（capabilities presets）
- `search_page.dart` - 搜索并跳转到指定会话/消息
- `custom_roles_page.dart` - 自定义角色管理（含关联会话处理）

---
⚠️ 页面改动建议以“手动冒烟 + flutter test”双保险验证（尤其是导航/回调与跨页状态）
