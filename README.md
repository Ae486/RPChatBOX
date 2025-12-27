# 架构速查（ChatBoxApp）

## 核心依赖链（建议遵循）
UI（`lib/pages`/`lib/widgets`） → 控制器（`lib/controllers`） → 业务服务（`lib/services`） → Provider/Adapter（`lib/adapters`） → 模型与存储（`lib/models`/Hive）

## 危险区域（改动需特别小心）
- `lib/widgets/conversation_view_v2.dart` + `lib/widgets/conversation_view_v2/*`：V2 主聊天视图（flutter_chat_ui 集成 + 流式输出 + 导出/重生成等）
- `lib/widgets/conversation_view.dart`：V1 聊天（历史逻辑，迁移对照）
- `lib/controllers/stream_output_controller.dart`：流式输出控制（时序/取消/异常收敛）
- `lib/adapters/*_provider.dart`：各家 API 兼容与 SSE 解析（最易出边界 bug）
- `lib/services/storage_service.dart` / Hive 相关：持久化与数据迁移

## 维护铁律（强制）
改文件 → 改文件头（INPUT/OUTPUT/POS） → 改目录 `INDEX.md` → 改根 README（如果跨模块）

更多规范见：`docs/FILE_ORGANIZATION_GUIDE.md`

