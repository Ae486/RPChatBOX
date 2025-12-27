# /lib/chat_ui/owui/composer

一句话：V2 输入区组件（OpenWebUI 风格），与 `flutter_chat_ui` 的 `ComposerHeightNotifier` 对齐，支持附件/联网开关/对话配置/模型选择/发送-停止流式。

## 文件清单
- `owui_composer.dart` - 核心 - 输入区主体（布局 + 高度上报 + 快捷键 Enter 发送）
- `owui_model_selector_sheet.dart` - UI - 模型选择 bottom sheet

---
⚠️ 改动输入区交互需重点手测：高度上报、发送/停止、附件预览

