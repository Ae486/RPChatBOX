# 文件整理与索引规范（3 层分形索引）

目标：让文档成为代码的一部分，而不是代码的附件；降低新人上手成本、减少“只有作者懂”的风险，并让大型模块可持续演进。

## 0. 适用范围（建议）
- **强制**：核心模块/危险区域/被多处引用的公共模块（例如：聊天主视图、流式输出、存储、Provider 适配器等）。
- **可选**：一次性实验文件、小型纯 UI 组件、短小工具函数（避免过度文档化）。

## 1) 文件级：3 行文件头（INPUT / OUTPUT / POS）
在“核心/危险”文件顶部写 3 行（Dart 推荐用 `///`）：

```dart
/// INPUT: lib/models/Conversation (强依赖), lib/main.dart:globalModelServiceManager (强依赖)
/// OUTPUT: ConversationViewV2(), ConversationViewV2State.scrollToMessage() - 被 ConversationViewHost 调用
/// POS: UI 层 / Chat / V2（flutter_chat_ui 集成）- 核心模块（改动需全量回归）
```

约定：
- `INPUT`：列出强依赖（不可替换/会牵一发动全身）与可替换依赖（可用接口替换实现）。
- `OUTPUT`：列出对外暴露的类/函数/Widget，以及**被谁调用**（关键依赖链）。
- `POS`：明确模块在架构中的位置 + 风险级别（是否需要全量回归/重点手测）。

## 2) 文件夹级：`INDEX.md`（目录职责 + 依赖规则 + 文件清单）
在一个目录里文件开始增多、或目录承载“明确职责”时，添加 `INDEX.md`：

模板：
```md
# /lib/services

一句话：业务逻辑层，只调用 models/utils/adapters，禁止跨 service 互相调用（避免环依赖）。

## 文件清单
- `token_usage_service.dart` - 核心 - Token 汇总/落盘
- `export_service.dart` - 工具 - 导出 Markdown/TXT

---
⚠️ 改架构 / 加文件前，要先更新我
```

建议写清楚：
- “这一层允许依赖谁 / 禁止依赖谁”
- 哪些文件是“核心/危险区域”
- 新文件加入时必须更新清单（否则 Review 直接打回）

## 3) 项目级：根 `README.md`（架构速查）
根 README 的目标不是“介绍产品”，而是**让维护者 30 秒看懂依赖链和危险区域**：

建议包含：
- 核心依赖链（示例）：`UI(Pages/Widgets) → Controllers → Services → Adapters → Models/Storage`
- 危险区域（改动需特别小心）：例如流式输出、Provider 适配、存储、迁移主开关
- 维护铁律：改文件 → 改文件头 → 改 INDEX.md → 改 README（如果跨模块）

## 4) 落地规则（本项目建议）
- 目录新增/拆分：必须先写 `INDEX.md`（说明职责与依赖规则）。
- 核心模块改动：必须更新文件头 `POS` 风险级别，并补充手测清单（写在相关 `INDEX.md` 或 docs 中）。
- 文档保持“短而强约束”：优先写规则与索引，不写长篇散文。

