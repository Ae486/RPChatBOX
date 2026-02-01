# 代码质量审查执行计划

> 创建时间: 2026-02-01
> 排除范围: `lib/services/roleplay/`、`lib/models/roleplay/`

---

## 执行阶段

### Phase 1: 核心层 (P0) - 预计 4 个文件夹

| 序号 | 目录 | 预估文件数 | 检查重点 | 输出 |
|------|------|-----------|----------|------|
| 01 | `lib/models/` | ~15 | Hive 模型、序列化、TypeId 冲突 | `01-models.md` |
| 02 | `lib/services/` | ~10 | 业务逻辑、依赖方向、错误处理 | `02-services.md` |
| 03 | `lib/adapters/` | ~6 | Provider 实现、API 一致性、异常处理 | `03-adapters.md` |
| 04 | `lib/controllers/` | ~2 | 状态管理、并发安全、资源释放 | `04-controllers.md` |

### Phase 2: 状态与 UI 层 (P1) - 预计 4 个文件夹

| 序号 | 目录 | 预估文件数 | 检查重点 | 输出 |
|------|------|-----------|----------|------|
| 05 | `lib/providers/` | ~2 | 状态管理、通知机制、内存泄漏 | `05-providers.md` |
| 06 | `lib/pages/` | ~8 | 页面复杂度、状态提升、导航逻辑 | `06-pages.md` |
| 07 | `lib/widgets/` | ~15 | 组件职责、rebuild 优化、key 使用 | `07-widgets.md` |
| 08 | `lib/chat_ui/` | ~12 | 自定义组件、主题一致性、扩展性 | `08-chat-ui.md` |

### Phase 3: 工具与支撑层 (P2) - 预计 7 个文件夹

| 序号 | 目录 | 预估文件数 | 检查重点 | 输出 |
|------|------|-----------|----------|------|
| 09 | `lib/utils/` | ~5 | 工具函数纯度、重复逻辑 | `09-utils.md` |
| 10 | `lib/rendering/` | ~3 | 渲染逻辑、性能问题 | `10-rendering.md` |
| 11 | `lib/data/` | ~2 | 静态数据、常量管理 | `11-data.md` |
| 12 | `lib/design_system/` | ~2 | 设计系统一致性 | `12-design-system.md` |
| 13 | `packages/flutter_chat_ui/` | ~20 | Fork 改动合理性、上游同步风险 | `13-flutter-chat-ui-fork.md` |
| 14 | `test/` | ~10 | 测试覆盖、测试质量 | `14-tests.md` |
| 15 | 根目录 (`main.dart`) | ~1 | 初始化逻辑、全局配置 | `15-root-files.md` |

---

## 单文件夹检查流程

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: 文件清单                                             │
│   - 列出所有 .dart 文件                                      │
│   - 统计行数                                                 │
│   - 识别入口/核心文件                                        │
├─────────────────────────────────────────────────────────────┤
│ Step 2: 静态检查                                             │
│   - 文件行数 > 500                                          │
│   - 函数行数 > 50                                           │
│   - dynamic 使用                                            │
│   - TODO/FIXME 统计                                         │
├─────────────────────────────────────────────────────────────┤
│ Step 3: 代码阅读                                             │
│   - 依赖关系分析                                             │
│   - 错误处理模式                                             │
│   - 重复代码识别                                             │
│   - 架构问题识别                                             │
├─────────────────────────────────────────────────────────────┤
│ Step 4: 问题分类                                             │
│   - Critical: 必须修复（崩溃、数据丢失、安全漏洞）            │
│   - Warning: 应该修复（技术债务、可维护性）                   │
│   - Info: 建议改进（风格、最佳实践）                          │
├─────────────────────────────────────────────────────────────┤
│ Step 5: 输出文档                                             │
│   - 按模板格式输出                                           │
│   - 记录模型讨论（如有）                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 多模型协作时机

| 场景 | 触发条件 | 协作模型 |
|------|----------|----------|
| 后端逻辑疑难 | services/adapters 中复杂逻辑 | Codex |
| UI/交互问题 | pages/widgets 中设计问题 | Gemini |
| 架构决策 | 跨层级依赖问题 | Codex + Gemini 并行 |

**协作原则**:
- 英文交流
- 禁止修改代码
- 记录 SESSION_ID

---

## 进度追踪

| Phase | 文件夹数 | 完成数 | 状态 |
|-------|---------|--------|------|
| Phase 1 (P0) | 4 | 4 | ✅ 完成 + Codex复核 |
| Phase 2 (P1) | 4 | 4 | ✅ 完成 + Codex复核 |
| Phase 3 (P2) | 7 | 6 | 🔄 进行中 (09-utils ✅, 10-rendering ✅ Codex, 11-12 Codex in progress, 13-14-15 Codex in progress) |
| **总计** | **15** | **14** | **93%** (待 Codex 反馈) |

### 完成详情
- ✅ **Phase 1**: 01-models, 02-services, 03-adapters, 04-controllers (都已 Codex 复核)
- ✅ **Phase 2**: 05-providers, 06-pages, 07-widgets, 08-chat-ui (都已 Codex 复核)
- ✅ **Phase 3 进行中**:
  - 09-utils: ✅ 完成 + Codex复核
  - 10-rendering: ✅ 初步审计 + ✅ Codex 深度补充 (SESSION_ID: 019c1590-91b9-7140-90f4-b639690bc358)
  - 11-data: ✅ 初步审计 + 🔄 Codex 深度审查中 (任务 ba3a28d)
  - 12-design-system: ✅ 初步审计 + 🔄 Codex 深度审查中 (任务 ba3a28d)
  - 13-flutter-chat-ui-fork: ✅ 初步分析框架 + 🔄 Codex 战略评估中 (任务 b167d02)
  - 14-tests: ✅ 初步统计 + 🔄 Codex 覆盖分析中 (任务 b167d02)
  - 15-root-files: ✅ 初步审计 + 🔄 Codex 启动安全分析中 (任务 b167d02)

### 输出物清单

```
docs/analyze/
├── CHECKLIST.md           # ✅ 主检查清单
├── PLAN.md                # ✅ 审计计划
├── TEMPLATE.md            # ✅ 标准模板
├── SUMMARY.md             # ✅ 总结报告（Phase 1-2 完整 + Phase 3 部分）
├── 01-models.md           # ✅ 完成 + Codex复核
├── 02-services.md         # ✅ 完成 + Codex复核
├── 03-adapters.md         # ✅ 完成 + Codex复核
├── 04-controllers.md      # ✅ 完成 + Codex复核
├── 05-providers.md        # ✅ 完成 + Codex复核
├── 06-pages.md            # ✅ 完成 + Codex复核
├── 07-widgets.md          # ✅ 完成 + Codex复核
├── 08-chat-ui.md          # ✅ 完成 + Codex复核
├── 09-utils.md            # ✅ 完成 + Codex复核
├── 10-rendering.md        # ⏳ 框架就绪
├── 11-data.md             # ⏳ 框架就绪
├── 12-design-system.md    # ⏳ 框架就绪
├── 13-flutter-chat-ui-fork.md  # ⏳ 框架就绪
├── 14-tests.md            # ⏳ 框架就绪
└── 15-root-files.md       # ⏳ 框架就绪
```

---

## 输出物清单

完成后将产生：

```
docs/analyze/
├── CHECKLIST.md           # 主检查清单 ✅
├── PLAN.md                # 本计划文件 ✅
├── TEMPLATE.md            # 标准模板 ✅
├── 01-models.md           # ✅ 完成 + Codex复核
├── 02-services.md         # ✅ 完成 + Codex复核
├── 03-adapters.md         # ✅ 完成 + Codex复核
├── 04-controllers.md      # ✅ 完成 + Codex复核
├── 05-providers.md        # ✅ 完成 + Codex复核
├── 06-pages.md            # ✅ 完成 + Codex复核 + 文档迭代
├── 07-widgets.md          # 🔄 Codex审核中 (bd3c850)
├── 08-chat-ui.md          # 🔄 Codex审核中 (b91ce2d)
├── 09-utils.md            # ⏳ 框架就绪
├── 10-rendering.md        # ⏳ 框架就绪
├── 11-data.md             # ⏳ 框架就绪
├── 12-design-system.md    # ⏳ 框架就绪
├── 13-flutter-chat-ui-fork.md  # ⏳ 框架就绪
├── 14-tests.md            # ⏳ 框架就绪
├── 15-root-files.md       # ⏳ 框架就绪
└── SUMMARY.md             # ⏳ 最后生成
```

---

## 启动确认

准备就绪，从 **Phase 1 → 01-models** 开始？
