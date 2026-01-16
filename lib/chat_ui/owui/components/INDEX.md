# /lib/chat_ui/owui/components

一句话：OpenWebUI 风格基础组件壳（AppBar/Scaffold/Card/Dialog/Menu/SnackBar/TextField），供 `pages/*` 与复用组件使用，避免样式逻辑散落。

## 依赖规则（建议）
- 允许依赖：`../owui_tokens_ext.dart`（只读）、`Theme.of(context)`（只读）
- 禁止依赖：`services/*`、`controllers/*`、具体业务流程（保持纯 UI）

## 文件清单
- `owui_app_bar.dart` - AppBar 壳（pageBg + 底部分割线）
- `owui_scaffold.dart` - Scaffold 壳（统一 pageBg）
- `owui_card.dart` - Card 壳（surfaceCard + subtle border）
- `owui_dialog.dart` - Dialog 壳（surfaceCard + subtle border）
- `owui_menu.dart` - PopupMenu 壳（surfaceCard + subtle border）
- `owui_snack_bar.dart` - SnackBar 统一封装（floating + OWUI 样式）
- `owui_text_field.dart` - TextField/SearchField 封装（rounded + subtle border）

---
⚠️ 这里的组件只做“样式壳/行为微封装”，不要在此引入业务逻辑与状态流转
