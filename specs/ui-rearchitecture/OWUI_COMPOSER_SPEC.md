# 输入区重构（OwuiComposer）实施规范
> `/specs/ui-rearchitecture` - V2 输入区重构与 OpenWebUI 风格适配  
> 创建时间: 2025-12-23  

---

## 1. 背景与目标

### 1.1 背景
- 当前 V2 通过 `flutter_chat_ui.Chat` 的 `composerBuilder` 注入自研 `EnhancedInputArea`（`lib/widgets/conversation_view_v2/build.dart`），并使用 `_ComposerHeightReporter` 手动上报高度。
- `EnhancedInputArea` 偏 Apple 风格、结构相对固化；未来引入更多动作按钮（语音、联网、工具、变量面板等）会导致多次返工。

### 1.2 目标
- **框架整合**：保留 `flutter_chat_ui` 作为 Chat 骨架，输入区与其 `ComposerHeightNotifier` 深度对齐（不再依赖外部高度 reporter）。
- **OpenWebUI 风格**：采用 `OwuiPalette` 灰阶体系，输入区与消息卡片一致的底色/边框/圆角；交互状态切换不抖动。
- **可扩展性**：输入区内置“动作栏 + 附件预览 + 模型选择 + 发送/停止”结构，后续新增按钮不影响主布局。
- **功能不回退**：V2 输入区必须覆盖当前 `EnhancedInputArea` 在 V2 中提供的能力（文件上传、联网开关、模型参数配置入口、模型选择、停止流式）。

---

## 2. 范围定义

### 2.1 本期范围（Phase 1）
- 输入区组件：`OwuiComposer`（项目内实现，基于 `flutter_chat_ui` 的 `Composer` 结构改造）
- 功能点：
  - 文件上传（沿用现有 `file_picker` 逻辑与 `AttachedFile.fromFile`）
  - 附件预览与移除
  - 联网开关（映射到 `ConversationSettings.enableNetwork`）
  - “对话配置”入口（复用 `ConversationConfigDialog`）
  - 模型选择（复用现有 bottom sheet 逻辑）
  - 发送 / 停止流式（按钮占位固定，切换图标不引发布局抖动）
  - 多行输入（最多 5 行；桌面 Enter 发送、Shift+Enter 换行）
- 集成点：
  - 替换 V2 的 `composerBuilder` 注入
  - Composer 高度上报使用 `ComposerHeightNotifier`（去掉 `_ComposerHeightReporter`）

### 2.2 非本期范围（Phase 2+）
- 语音输入（Mic/录音/转写）  
- “+”多入口菜单（拍照/相册/链接附件）  
- 桌面拖拽上传（desktop_drop / super_drag_and_drop）  
- 输入区 rich text / markdown 工具条  

---

## 3. 设计方案

### 3.1 布局结构（自上而下）
1) 附件预览条（仅有附件时显示；可横向滚动；可删除）
2) 主输入行（一体化圆角输入条；固定高度区间，可随文本增长）：
   - 左侧：动作按钮组（附件、联网、配置）
   - 中间：多行 TextField（无边框/无内置 padding；由容器提供底色/边框/圆角；最多 5 行）
   - 右侧：模型选择 pill + 发送/停止按钮

### 3.2 状态机（最小集合）
- `hasText`（输入是否为空）
- `isStreaming`（流式中：发送按钮变 Stop 且可在空输入时点击）
- `hasAttachments`（是否存在附件，控制预览条显示）

### 3.3 样式规范（OpenWebUI）
- 颜色：
  - 页面/输入容器：`OwuiPalette.pageBackground(context)`
  - 输入框底色：`OwuiPalette.surfaceCard(context)`
  - 边框：`OwuiPalette.borderSubtle(context)`
  - 文字：`OwuiPalette.textPrimary/Secondary(context)`
  - TextField：`InputBorder.none` + `contentPadding=EdgeInsets.zero`（由外层容器控制内边距）
- 圆角：
  - 输入框：12~16
  - 按钮容器：10~12
- 动效：
  - 仅保留必要的 `AnimatedContainer`（focus 边框），避免高度变化动效引起滚动抖动

---

## 4. 实施计划（按最小返工设计）

### 4.1 Phase 1（本次实施）
| 任务 | 变更 | 验收 |
|---|---|---|
| 1. 新增 OwuiComposer | 把 `flutter_chat_ui` Composer 复制到项目内并扩展：动作栏/附件预览/模型 pill/stop | 编译通过；高度上报正确；布局稳定 |
| 2. V2 接入 | `ConversationViewV2` 的 `composerBuilder` 替换为 OwuiComposer | V2 聊天可正常发送、停止、选模型、上传文件 |
| 3. 清理高度 reporter | 删除 `_ComposerHeightReporter` 及相关引用 | 消息列表不被输入区遮挡 |
| 4. 文档与索引更新 | 更新本 spec 的“完成情况”与目录 INDEX | CR 可追溯、可维护 |

### 4.2 Phase 2（后续）
- 接入语音输入：`speech_to_text`（本地）或 `record` + 后端 STT（云端）
- 统一附件入口：拍照/相册/文件/链接；桌面拖拽（优先 `desktop_drop`）

---

## 5. 文件清单（计划）

### 5.1 新增
- `lib/chat_ui/owui/composer/owui_composer.dart` - OwuiComposer 主体（含高度上报）
- `lib/chat_ui/owui/composer/owui_model_selector_sheet.dart` - 模型选择 bottom sheet（从 EnhancedInputArea 迁移/复用）
- `lib/chat_ui/owui/INDEX.md` - owui 目录索引（新增/更新）

### 5.2 修改
- `lib/widgets/conversation_view_v2/build.dart` - composerBuilder 替换为 OwuiComposer
- `lib/widgets/conversation_view_v2.dart` - 移除旧 composer part（如不再需要）
- `lib/widgets/conversation_view_v2/INDEX.md` - 更新输入区实现说明
- （可选）`test/widgets/owui_composer_test.dart` - 输入区基础交互测试（send/stop）

---

## 6. 测试与验收

### 6.1 自动化
- `flutter test`
- （如新增）widget test：验证
  - 输入非空点击发送触发回调
  - `isStreaming=true` 时按钮触发 stop 回调（即使输入为空）

### 6.2 手测清单（必须）
- 发送文本、发送附件、发送文本+附件
- 流式中点击 Stop 可停止且不导致输入区/列表错位
- 切换模型后发送正常
- 联网 toggle 状态可持久化到 `ConversationSettings`
- 输入区高度变化时消息列表不遮挡、不跳动

---

## 7. 进度记录
- [x] Phase 1 / 任务 1：新增 OwuiComposer
- [x] Phase 1 / 任务 2：V2 接入
- [x] Phase 1 / 任务 3：清理高度 reporter
- [x] Phase 1 / 任务 4：文档与索引更新

补充：
- `flutter test`：通过（仅存在上游 `file_picker` 平台声明警告）
