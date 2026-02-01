# Roleplay Feature - 开发指导文档

> 供 Claude / Codex 协作开发使用
>
> 最后更新：2026-01-15

---

## 0. 核心开发准则 ⭐

### 0.1 胶水编程原则 (Glue Programming)

```
┌─────────────────────────────────────────────────────────────┐
│                      业务需求                                │
├─────────────────────────────────────────────────────────────┤
│                  AI 胶水层 (Glue Layer)                      │
│          "理解需求，把成熟模块连接起来"                        │
├─────────────────────────────────────────────────────────────┤
│    成熟模块 A     │    成熟模块 B    │    成熟模块 C          │
│   (10万+ ⭐)      │   (生产验证)     │   (官方 SDK)          │
└─────────────────────────────────────────────────────────────┘
```

**核心理念**：
- **优先复用**：使用成熟的开源项目、官方 SDK、久经考验的库
- **胶水代码**：AI 生成的代码负责数据流转和接口适配
- **避免重复造轮子**：搜索现有解决方案，而非从零实现

### 0.2 文档优先原则

**开发前必读**：
1. `docs/roleplay-feature/*.md` - 需求和技术讨论文档
2. `docs/roleplay-feature/specs/*.md` - 技术规格文档
3. `docs/research/*` - 参考项目实现（精华提取源）

**关键参考项目**：
| 项目 | 路径 | 参考价值 |
|------|------|----------|
| letta-main | `docs/research/letta-main/` | Memory 系统、Agent 编排 |
| MuMuAINovel-main | `docs/research/MuMuAINovel-main/` | Prompt 组装、记忆上下文 |
| open-webui-main | `docs/research/open-webui-main/` | UI 模式、任务管理 |

### 0.3 迭代适配原则

**当基础功能/框架不足时**：
1. ✅ 允许在不影响原有功能的基础上进行扩展
2. ✅ 允许引入新的成熟框架
3. ✅ 使用 MCP 工具搜索优秀架构和实现
4. ⚠️ 新增代码应保持最小侵入性
5. ⚠️ 扩展点使用条件判断隔离

**搜索策略**：
```
# 使用 MCP 工具搜索
- mcp__tavily-remote__tavily_search: 搜索最新技术方案
- mcp__exa__get_code_context_exa: 搜索代码实现参考
- mcp__augment-context-engine__codebase-retrieval: 搜索本地代码库
```



### 0.5  开发工具

1.使用mcp工具帮助进行网络搜索（tavily）与代码检索定位（augment）

2.开发期间随时使用合适的skills

3.遵照skill与sessionID进行协作交流开发：
  - **Codex**: `019b8e40-021b-7563-b300-cf99e87f76ec` (后端逻辑、算法、调试)
  - **Gemini**: `29ea2ac3-7e60-4c04-9ca1-ecc144d1bfc6` (前端UI、样式、交互)

### 0.6 Mx 实现状态

在开放前编写specs下对应文档，开发期间和开发完成后实时更新

| 里程碑 | 状态 | 完成日期 |
|--------|------|----------|
| M0 Foundation | ✅ 已完成 | 2026-01-15 |
| M1 Context Compiler | ✅ 已完成 | 2026-01-18 |
| M2 Consistency Gate | ✅ 已完成 | 2026-01-19 |
| M3 Worker Isolate | ✅ 已完成 | 2026-01-20 |
| M4 Agent Integration | ✅ 已完成 | 2026-02-01 |
| M4.5 Performance & UX | ✅ 已完成 | 2026-02-01 |

---

## 1. 项目定位

**Roleplay Feature** 是 ChatBoxApp 的**可选功能模块**（Feature Layer），用户进入专属页面后才激活。

```
┌─────────────────────────────────────────────────────────────────┐
│  Feature Layer: Roleplay/Writing Mode (Optional)                │
│  ├─ 独立路由入口                                                 │
│  ├─ 独立状态管理                                                 │
│  ├─ 独立存储命名空间 (Hive Box: rp_*)                            │
│  └─ 专属 UI 上下文                                               │
├─────────────────────────────────────────────────────────────────┤
│  Base Layer: Core Chat Functionality (不修改)                    │
│  ├─ ChatPage / ConversationViewV2                               │
│  ├─ Conversation / Message 模型                                  │
│  ├─ AIProvider 抽象层                                            │
│  └─ StreamOutputController                                      │
└─────────────────────────────────────────────────────────────────┘
```

**核心原则**：
- **隔离性**：不污染 Base Layer
- **可选性**：不进入页面时完全不加载
- **组合性**：复用 Base Layer 基础设施

---

## 1. 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| 框架 | Flutter (Dart) | >= 3.0 |
| 持久化 | Hive | >= 2.0 |
| 并发 | Isolate | Flutter 内置 |
| AI 集成 | Provider 抽象层 | 现有 |
| ID 生成 | ULID | 待引入 |

---

## 2. 目录结构

### 2.1 新增目录

```
lib/
├── models/roleplay/              # Hive 数据模型 (TypeId 50-59)
│   ├── rp_story_meta.dart        # StoryMeta + Head + ModuleState
│   ├── rp_entry_blob.dart        # EntryBlob + EvidenceRef
│   ├── rp_operation.dart         # Operation + EntryChange
│   ├── rp_snapshot.dart          # Snapshot
│   ├── rp_proposal.dart          # Proposal + Target
│   └── rp_enums.dart             # 枚举定义
│
├── services/roleplay/            # 业务服务
│   ├── roleplay_memory_repository.dart  # Hive CRUD
│   ├── context_compiler.dart            # Budget Broker
│   ├── proposal_applier.dart            # Proposal → Op
│   ├── agent_worker_host.dart           # Isolate 管理
│   ├── orchestrator.dart                # 调度逻辑
│   ├── consistency_gate.dart            # 一致性检测
│   └── modules/                         # 记忆模块
│       ├── rp_module.dart               # 接口定义
│       ├── scene_module.dart
│       ├── character_module.dart
│       └── ...
│
├── services/roleplay/skills/     # Skill 化 Agent 系统
│   ├── config/                   # 配置数据结构
│   ├── registry/                 # 注册表
│   ├── scheduler/                # 调度器
│   ├── adapter/                  # 模型适配
│   ├── executor/                 # Agent 执行器
│   └── hooks/                    # 生命周期钩子
│
└── widgets/roleplay/             # UI 组件
    ├── roleplay_page.dart        # 主页面
    ├── memory_panel.dart         # Memory 面板
    └── proposal_review_dialog.dart
```

### 2.2 Hive TypeId 分配

| TypeId | 类型 | 文件 |
|--------|------|------|
| 0-3 | 现有 (Conversation/Message/File) | 已占用 |
| 50 | RpStoryMeta | rp_story_meta.dart |
| 51 | RpHead | rp_story_meta.dart |
| 52 | RpModuleState | rp_story_meta.dart |
| 53 | RpEntryBlob | rp_entry_blob.dart |
| 54 | RpEvidenceRef | rp_entry_blob.dart |
| 55 | RpOperation | rp_operation.dart |
| 56 | RpEntryChange | rp_operation.dart |
| 57 | RpSnapshot | rp_snapshot.dart |
| 58 | RpProposal | rp_proposal.dart |
| 59 | RpProposalTarget | rp_proposal.dart |

### 2.3 Hive Box 结构

```
rp_story_meta     - StoryMeta (key=storyId)
rp_entry_blobs    - EntryBlob (key=blobId)
rp_ops            - Operation (key=$storyId|$scope|$branchId|$rev)
rp_snapshots      - Snapshot (key=$storyId|$scope|$branchId|$rev)
rp_proposals      - Proposal (key=proposalId)
rp_logs           - 审计日志 (key=logId)
```

---

## 3. 实现路线图（MVP 策略 C）

### 3.1 里程碑依赖

```
M0 (Foundation) ──┬── M1 (Context Compiler) ── M2 (Consistency Gate)
                  │
                  └── M3 (Worker Isolate) ── M4 (Agent Integration) ── M5 (Advanced)
                                                                            │
                                                                            ▼
                                                                       M6 (Polish)
```

### 3.2 MVP 优先任务

**Phase 1: 后端核心逻辑**
1. M0: Hive 数据模型定义 + CRUD
2. M1: RpModule 接口 + RpBudgetBroker + 核心模块 (Scene, Character, State)
3. 与现有 systemPrompt 集成

**Phase 2: 最小可用 UI**
- 复用 ConversationViewV2 作为聊天容器
- 复用 CustomRole 选择器作为角色入口
- 简单配置面板（现有 Form 组件）

**Phase 3: 迭代优化**
- M3-M5 完整实现
- 专属 UI/UX 设计

---

## 4. 关键设计文档索引

| 文档 | 内容 | 优先级 |
|------|------|--------|
| `22-FINAL-SUMMARY.md` | 设计总结、M0-M6 详细任务、ADR | **必读** |
| `23-SKILL-BASED-AGENT-DESIGN.md` | Skill 化 Agent 架构、配置格式、执行器设计 | **必读** |
| `21-TECHNICAL-IMPLEMENTATION-MAPPING.md` | Hive 模型、Worker Isolate、Context Compiler | **必读** |
| `24-PROJECT-CODEBASE-REFERENCE.md` | 现有代码结构、集成点 | **必读** |
| `20-AGENT-ORCHESTRATION-DESIGN.md` | Agent 编排、调度逻辑 | 参考 |
| `19-ARCHITECTURE-REVIEW.md` | 架构审查、改进方案 | 参考 |
| `03-DATA-MODELS.md` | 早期数据模型设计 | 背景 |

---

## 5. 核心概念速查

### 5.1 9 大 Memory 模块

| 模块 | 作用 | 优先级 |
|------|------|--------|
| Scene | 当前场景状态 | P0 |
| Character | 角色卡 + Quick Facts | P0 |
| State | 状态/物品/伤势 | P0 |
| Goals | 目标追踪 | P1 |
| Foreshadow | 伏笔追踪 | P1 |
| World | 世界书条目 | P1 |
| Timeline | 关键事件 | P2 |
| Style | 文风约束 | P2 |
| Mechanics | 机制规则 | P2 |

### 5.2 Proposal 类型 (7 种)

| 类型 | 作用 |
|------|------|
| CONFIRMED_WRITE | 写入 confirmed 条目 |
| DRAFT_UPDATE | 写入 draft 条目 |
| LINK_UPDATE | 伏笔链接更新 |
| SCENE_TRANSITION | 场景切换 |
| COMPRESSION_UPDATE | 摘要压缩 |
| OUTPUT_FIX | 一致性修复建议 |
| USER_EDIT_INTERPRETATION | 用户编辑解释 |

### 5.3 Entry 两维度模型

| 维度 | 值 | 说明 |
|------|-----|------|
| scope | foundation | 基底（跨分支共享） |
| scope | story | 剧情（分支隔离） |
| status | confirmed | 已确认（权威） |
| status | draft | 草稿（待审核） |

### 5.4 logicalId 命名规范

```
rp:v1:<domainCode>:<entityKey>:<entryType>[:<subKey>]

示例：
rp:v1:ch:ent_01j2k...:card.base      # 角色基础卡
rp:v1:sc:current:state               # 当前场景状态
rp:v1:tl:ev_01j3b...:event          # 关键事件
```

---

## 6. Codex 协作规范

### 6.1 Session 信息

```
SESSION_ID: 019b8e40-021b-7563-b300-cf99e87f76ec
```

### 6.2 协作时机

| Phase | 用途 | 输入 |
|-------|------|------|
| Phase 2 (分析) | 多方案分析、逻辑验证 | 原始需求 + 入口文件路径 |
| Phase 3B (原型) | 后端逻辑原型 Diff | 设计规格 + 接口签名 |
| Phase 5 (审计) | Code Review | Unified Diff + 目标文件 |

### 6.3 Prompt 模板

**分析请求**：
```
Analyze the implementation approach for [FEATURE_NAME] in ChatBoxApp roleplay-feature.

Context:
- Entry file: lib/services/roleplay/[FILE].dart
- Design doc: docs/roleplay-feature/[DOC].md (row N-M)

Requirements:
1. [Requirement 1]
2. [Requirement 2]

OUTPUT: Step-by-step implementation plan. Strictly prohibit any actual modifications.
```

**Code Review 请求**：
```
Review the following Unified Diff for [FEATURE_NAME]:

[DIFF CONTENT]

Check for:
1. Logic correctness
2. Edge cases
3. Performance concerns
4. Consistency with existing codebase patterns

OUTPUT: Review comments with specific line references. Strictly prohibit any actual modifications.
```

---

## 7. 代码风格规范

### 7.1 Dart/Flutter

- 使用 `final` 优先于 `var`
- Hive 类使用 `@HiveType` + `@HiveField` 注解
- 枚举使用 index 存储（`enumValue.index`）
- JSON 序列化使用 `Uint8List` (UTF-8) 存储大内容

### 7.2 命名规范

| 类型 | 规范 | 示例 |
|------|------|------|
| 类 | PascalCase + Rp 前缀 | `RpStoryMeta` |
| 文件 | snake_case + rp_ 前缀 | `rp_story_meta.dart` |
| Box | snake_case + rp_ 前缀 | `rp_entry_blobs` |
| logicalId | 小写 + 冒号分隔 | `rp:v1:ch:xxx:card.base` |

### 7.3 注释原则

- **非必要不注释**：代码自解释
- **公共 API**：必须有 dartdoc
- **复杂逻辑**：简要说明 why，不说明 what

---

## 8. 测试策略

### 8.1 单元测试

```
test/
├── models/roleplay/          # 模型序列化测试
├── services/roleplay/        # 服务逻辑测试
└── helpers/
    └── rp_test_data.dart     # 测试数据工厂
```

### 8.2 关键测试场景

| 场景 | 验收标准 |
|------|----------|
| Hive CRUD | 创建/读取/更新/删除正确 |
| COW 版本控制 | 崩溃恢复后数据完整 |
| Context Compiler | 预算分配正确、优先级排序正确 |
| Worker Isolate | 通信正确、崩溃可恢复 |

---

## 9. 危险区域（改动需谨慎）

| 文件/目录 | 风险描述 |
|-----------|----------|
| `conversation_view_v2.dart` | V2 主聊天视图，核心流式输出 |
| `stream_output_controller.dart` | 流式输出时序/取消/异常 |
| `adapters/*_provider.dart` | API 兼容与 SSE 解析 |
| `hive_conversation_service.dart` | 持久化与数据迁移 |

**原则**：Roleplay 功能应通过**扩展**而非**修改**现有代码实现。

---

## 10. Research 参考

| 项目 | 路径 | 参考价值 |
|------|------|----------|
| markstream-vue-main | `docs/research/markstream-vue-main/` | Markdown 流式渲染实现 |

---

## 附录 A: 快速参考命令

### A.1 生成 Hive Adapter

```bash
flutter pub run build_runner build --delete-conflicting-outputs
```

### A.2 运行测试

```bash
flutter test test/services/roleplay/
```

### A.3 检查 TypeId 冲突

```bash
grep -r "@HiveType(typeId:" lib/models/
```

---

## 附录 B: 变更历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0 | 2026-01-15 | 初版，MVP 策略 C 开发指导 |
