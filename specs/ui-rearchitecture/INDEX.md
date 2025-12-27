# /specs/ui-rearchitecture

一句话：V2（`flutter_chat_ui`）迁移与 OpenWebUI（OWUI）风格适配的实施规范文档集合。

## 文件清单
- `OWUI_COMPOSER_SPEC.md` - 核心 - 输入区重构（OwuiComposer）实施规范
- `OWUI_MARKDOWN_SPEC.md` - 核心 - Markdown 渲染规范（含表格窄屏横向滚动）
- `OWUI_MESSAGE_BRANCHING_SPEC.md` - 规划 - 树状消息链（多版本回复、1/2 切换）设计与落地步骤
- `OWUI_PAGES_STYLE_UNIFICATION_PLAN.md` - 规划 - Pages + overlays 的 OWUI 风格统一计划（组件壳 + 分批迁移）
- `OWUI_DISPLAY_SETTINGS_SPEC.md` - 核心 - 显示设置（UI scale / 字体）规格

---
⚠️ 新增/调整实现前先更新对应 spec，再开始编码
