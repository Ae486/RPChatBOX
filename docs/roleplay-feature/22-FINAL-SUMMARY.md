# 设计总结与实现路线图

> 目标：汇总 Phase 1-4 的设计成果，输出可执行的实现计划。
>
> 本文档为"写作/跑团式角色扮演"系统设计的最终总结。
>
> 最后更新：2026-01-07

---

## 0. 文档索引

| 文档 | 内容 | 状态 |
|------|------|------|
| `19-ARCHITECTURE-REVIEW.md` | 架构问题诊断与改进方案 | ✅ 完成 |
| `20-AGENT-ORCHESTRATION-DESIGN.md` | Agent 体系与编排设计 | ✅ 完成 |
| `21-TECHNICAL-IMPLEMENTATION-MAPPING.md` | 技术实现映射 | ✅ 完成 |
| `22-FINAL-SUMMARY.md` | 本文档 | ✅ 完成 |

---

## 1. 需求确认清单

### 1.1 核心功能需求

| ID | 需求 | 优先级 | 状态 |
|----|------|--------|------|
| F-01 | 结构化记忆存储（9 模块） | P0 | ✅ 设计完成 |
| F-02 | 版本控制与回滚 | P0 | ✅ 设计完成 |
| F-03 | 上下文智能编译（Budget Broker） | P0 | ✅ 设计完成 |
| F-04 | 一致性闸门（外观/状态/时间线） | P0 | ✅ 设计完成 |
| F-05 | 后台 Agent 任务处理 | P1 | ✅ 设计完成 |
| F-06 | 用户编辑解释与传播 | P1 | ✅ 设计完成 |
| F-07 | 伏笔追踪与链接 | P1 | ✅ 设计完成 |
| F-08 | 场景检测与切换 | P1 | ✅ 设计完成 |
| F-09 | 关键事件提取 | P2 | ✅ 设计完成 |
| F-10 | 摘要/压缩（Sleeptime 维护） | P2 | ✅ 设计完成 |

### 1.2 非功能需求

| ID | 需求 | 目标 | 状态 |
|----|------|------|------|
| NF-01 | 流式输出延迟 | 不阻塞首 token | ✅ 设计完成 |
| NF-02 | Proposal 弹窗延迟 | < 3s（目标）/ < 10s（最坏） | ✅ 设计完成 |
| NF-03 | 后台任务 token 预算 | ≤ 18% 输入 / ≤ 10% 输出 | ✅ 设计完成 |
| NF-04 | 崩溃恢复 | 不丢失已确认数据 | ✅ 设计完成 |
| NF-05 | 兼容现有代码 | 最小侵入 | ✅ 设计完成 |

---

## 2. 架构决策记录（ADR）

### ADR-001: 单向数据流（Timeline 脊柱）

**背景**：原设计存在循环依赖（foreshadow↔goals、Scene↔Timeline↔Foreshadow）

**决策**：
- Timeline（Key Events）作为剧情推进的权威账本
- 所有派生模块从 Timeline 单向读取
- Scene 不依赖 Foreshadow；Goals 和 Foreshadow 不直接互写

**后果**：
- ✅ 数据流清晰，易于调试
- ✅ 减少级联更新风险
- ⚠️ 需要放宽模型允许快速路径直接更新

### ADR-002: 两维度 Entry 模型

**背景**：原 3 层 + 每模块 Canon 造成概念混淆

**决策**：
- `scope`: foundation（基底）| story（剧情）
- `status`: confirmed（已确认）| draft（草稿）
- 组合代替原来的三层

**后果**：
- ✅ 概念清晰：scope 控制回滚范围，status 控制权威性
- ✅ 简化 UI 展示逻辑

### ADR-003: Proposal 类型精简（13 → 7）

**背景**：原 13 种类型功能重叠

**决策**：保留 7 种核心类型
1. CONFIRMED_WRITE（写入 confirmed）
2. DRAFT_UPDATE（写入 draft）
3. LINK_UPDATE（伏笔链接）
4. SCENE_TRANSITION（场景切换）
5. COMPRESSION_UPDATE（摘要压缩）
6. OUTPUT_FIX（一致性修复）
7. USER_EDIT_INTERPRETATION（编辑解释）

**后果**：
- ✅ 实现复杂度降低
- ✅ UI 路由逻辑简化
- ⚠️ 需要 `domain` 字段进行细分

### ADR-004: Budget Broker 统一分配

**背景**：各 View 各自为政，预算争抢

**决策**：
- 单一 Budget Broker 管理所有 token 分配
- 三优先级：P0（必须）/ P1（重要）/ P2（可选）
- 评分公式：`utility / costTokens`

**后果**：
- ✅ 全局最优分配
- ✅ 可观测性（日志 dropped fragments）
- ⚠️ 初期调参需迭代

### ADR-005: 单一 Worker Isolate

**背景**：后台任务可能阻塞 UI

**决策**：
- Main Isolate：UI + Streaming + Hive 写入（单一写入者）
- Worker Isolate：LLM Agents + 重计算（只读，返回 Proposals）

**后果**：
- ✅ UI 不卡顿
- ✅ 写入冲突消除
- ⚠️ Isolate 通信序列化成本

### ADR-006: COW 版本控制

**背景**：需要支持回滚和审计

**决策**：
- 不可变 EntryBlob（每次修改创建新 blob）
- Append-only Operation 日志
- 周期性 Snapshot（pointer map）

**后果**：
- ✅ 任意版本可重建
- ✅ 崩溃容错（ops 是权威）
- ⚠️ 需要 GC 清理旧 blob

### ADR-007: 一致性闸门两阶段

**背景**：流式输出场景下的一致性检测

**决策**：
- 轻量闸门（始终运行）：外观不变量、状态约束、在场角色
- 重量闸门（触发式）：时间线顺序、知识泄露、上下文压力时

**后果**：
- ✅ 默认低延迟
- ✅ 高风险场景有保障
- ⚠️ 永不阻塞已流式文本

---

## 3. 实现路线图

### 3.1 里程碑定义

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              实现路线图                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  M0: Foundation (基础设施)                                                  │
│  ├── Hive 数据模型定义 (typeId 50-59)                                       │
│  ├── RpMemoryRepository CRUD                                                │
│  ├── Operation/Snapshot 版本控制                                            │
│  └── 单元测试覆盖                                                           │
│                                                                             │
│  M1: Context Compiler (上下文编译)                                          │
│  ├── RpModule 接口定义                                                      │
│  ├── RpBudgetBroker 实现                                                    │
│  ├── 核心模块注册 (Scene, Character, State)                                 │
│  └── 与现有 systemPrompt 集成                                               │
│                                                                             │
│  M2: Consistency Gate (一致性闸门)                                          │
│  ├── 轻量闸门实现                                                           │
│  ├── 外观不变量检测                                                         │
│  ├── 状态约束检测                                                           │
│  └── 与流式输出集成                                                         │
│                                                                             │
│  M3: Worker Isolate (后台任务)                                              │
│  ├── Isolate 通信协议                                                       │
│  ├── 任务调度器                                                             │
│  ├── 版本闸门 (过期检测)                                                    │
│  └── 崩溃恢复                                                               │
│                                                                             │
│  M4: Agent Integration (Agent 集成)                                         │
│  ├── SceneDetector                                                          │
│  ├── StateUpdater                                                           │
│  ├── KeyEventExtractor                                                      │
│  └── ConsistencyGate (重量闸门)                                             │
│                                                                             │
│  M5: Advanced Features (高级功能)                                           │
│  ├── ForeshadowLinker                                                       │
│  ├── GoalsUpdater                                                           │
│  ├── Summarizer                                                             │
│  ├── EditInterpreter                                                        │
│  └── Sleeptime 维护                                                         │
│                                                                             │
│  M6: Polish & Optimization (优化)                                           │
│  ├── UI 集成完善                                                            │
│  ├── 性能优化                                                               │
│  ├── 用户测试反馈                                                           │
│  └── 文档完善                                                               │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 里程碑依赖关系

```
M0 ─────┬────────────────────────────────────────────────────────▶ M6
        │
        ├── M1 ──┬────────────────────────────────────────────────▶ M6
        │        │
        │        └── M2 ──────────────────────────────────────────▶ M6
        │
        └── M3 ──┬── M4 ──┬── M5 ─────────────────────────────────▶ M6
                 │        │
                 │        └──────────────────────────────────────▶ M6
                 │
                 └───────────────────────────────────────────────▶ M6

依赖说明：
- M0 是所有里程碑的前置
- M1 依赖 M0（需要数据模型）
- M2 依赖 M1（需要上下文编译）
- M3 依赖 M0（需要数据模型）
- M4 依赖 M3（需要 Worker Isolate）
- M5 依赖 M4（需要基础 Agent）
- M6 依赖所有前置里程碑
```

### 3.3 各里程碑详细任务

#### M0: Foundation

| 任务 | 输出 | 验收标准 |
|------|------|----------|
| 定义 Hive 数据模型 | `lib/models/roleplay/*.dart` | 编译通过，typeId 无冲突 |
| 实现 RpMemoryRepository | `lib/services/roleplay/roleplay_memory_repository.dart` | CRUD 操作正确 |
| 实现 Operation 日志 | 写入顺序正确 | 崩溃恢复测试通过 |
| 实现 Snapshot | 周期性快照 | 冷启动重建测试通过 |
| 单元测试 | `test/services/roleplay/*_test.dart` | 覆盖率 > 80% |

#### M1: Context Compiler

| 任务 | 输出 | 验收标准 |
|------|------|----------|
| 定义 RpModule 接口 | `lib/services/roleplay/modules/rp_module.dart` | 接口清晰 |
| 实现 RpBudgetBroker | `lib/services/roleplay/context_compiler.dart` | 评分公式正确 |
| 实现 Scene 模块 | `lib/services/roleplay/modules/scene_module.dart` | P0 优先级 |
| 实现 Character 模块 | `lib/services/roleplay/modules/character_module.dart` | Quick Facts 提取 |
| 集成到 systemPrompt | 修改 `lib/widgets/conversation_view_v2/` | 编译后上下文注入 |

#### M2: Consistency Gate

| 任务 | 输出 | 验收标准 |
|------|------|----------|
| 实现轻量闸门 | `lib/services/roleplay/consistency_gate.dart` | 外观/状态检测 |
| 与流式输出集成 | 修改 streaming 管线 | 不阻塞首 token |
| 实现 OUTPUT_FIX 提议 | Proposal 生成正确 | UI 可显示修复建议 |

#### M3: Worker Isolate

| 任务 | 输出 | 验收标准 |
|------|------|----------|
| 实现 Isolate 通信 | `lib/services/roleplay/agent_worker_host.dart` | SendPort/ReceivePort 正确 |
| 实现任务调度器 | 优先队列 + 去重 | 背压处理正确 |
| 实现版本闸门 | 过期检测 + 锚点验证 | 过期任务正确丢弃 |
| 崩溃恢复 | 错误处理 | Worker 崩溃后可恢复 |

#### M4: Agent Integration

| 任务 | 输出 | 验收标准 |
|------|------|----------|
| 实现 SceneDetector | Agent 提示词 + 输出解析 | SCENE_TRANSITION 提议正确 |
| 实现 StateUpdater | Agent 提示词 + 输出解析 | DRAFT_UPDATE 提议正确 |
| 实现 KeyEventExtractor | Agent 提示词 + 输出解析 | Timeline 条目正确 |
| 实现重量闸门 | 触发条件 + 检测逻辑 | 时间线/知识泄露检测 |

#### M5: Advanced Features

| 任务 | 输出 | 验收标准 |
|------|------|----------|
| 实现 ForeshadowLinker | Agent + Tracker 更新 | LINK_UPDATE 提议正确 |
| 实现 GoalsUpdater | Agent + 目标生命周期 | 目标状态机正确 |
| 实现 Summarizer | Agent + 压缩逻辑 | token 上限遵守 |
| 实现 EditInterpreter | diff 分类 + 影响分析 | 分类准确 |
| 实现 Sleeptime 维护 | 空闲触发 + 任务队列 | 不影响前台 |

#### M6: Polish & Optimization

| 任务 | 输出 | 验收标准 |
|------|------|----------|
| UI 集成完善 | Memory 面板 + 提议审批 | 交互流畅 |
| 性能优化 | 缓存 + 延迟加载 | 指标达标 |
| 用户测试 | 反馈收集 + 修复 | 关键问题解决 |
| 文档完善 | 用户指南 + API 文档 | 完整可用 |

---

## 4. 风险清单与缓解措施

### 4.1 风险矩阵

```
                        影响 (Impact)
                 低 (Low)    中 (Medium)    高 (High)
            ┌─────────────┬─────────────┬─────────────┐
    高      │             │             │             │
   (High)   │             │    R-03     │    R-01     │
            │             │             │    R-02     │
 概         ├─────────────┼─────────────┼─────────────┤
 率         │             │             │             │
   中       │             │    R-04     │    R-05     │
  (Med)     │             │    R-06     │             │
            ├─────────────┼─────────────┼─────────────┤
   低       │    R-08     │    R-07     │             │
   (Low)    │             │             │             │
            └─────────────┴─────────────┴─────────────┘

图例：
- 红色区域（高概率 × 高影响）：需要主动缓解
- 黄色区域（中等）：需要监控
- 绿色区域（低）：可接受
```

### 4.2 风险详情

| ID | 风险 | 概率 | 影响 | 缓解措施 |
|----|------|------|------|----------|
| R-01 | **LLM 输出不稳定** | 高 | 高 | JSON 修复重试、schema 验证、降级为 draft、失败关闭 |
| R-02 | **Token 预算超支** | 高 | 高 | Budget Broker 硬上限、P2 优先丢弃、动态调整 |
| R-03 | **后台任务延迟** | 高 | 中 | 版本闸门丢弃过期结果、优先级队列、背压处理 |
| R-04 | **Hive 性能瓶颈** | 中 | 中 | COW + 周期快照、GC 清理、延迟写入 |
| R-05 | **一致性检测误报** | 中 | 高 | 轻量闸门仅检测高置信度违规、用户可覆盖、日志审计 |
| R-06 | **用户编辑传播复杂** | 中 | 中 | dirty window 追踪、增量重算、版本闸门 |
| R-07 | **分支合并冲突** | 低 | 中 | v0 不支持自动合并、cherry-pick 导入为新条目、标记 needs_review |
| R-08 | **Worker Isolate 崩溃** | 低 | 低 | 错误处理 + 懒重启、本轮降级跳过后台任务 |

### 4.3 关键风险缓解策略

#### R-01: LLM 输出不稳定

```
┌─────────────────────────────────────────────────────────────┐
│                    LLM 输出验证流水线                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  LLM Output                                                 │
│      │                                                      │
│      ▼                                                      │
│  ┌─────────────┐   失败   ┌─────────────┐                  │
│  │ JSON Parse  │─────────▶│ Repair Retry │─────┐           │
│  └─────────────┘          │ (1次 max)    │     │           │
│      │ 成功               └─────────────┘     │           │
│      ▼                          │ 成功        │ 仍失败     │
│  ┌─────────────┐               ▼              │           │
│  │Schema Valid │◀──────────────┘              │           │
│  └─────────────┘                              │           │
│      │ 失败                                    │           │
│      ▼                                         │           │
│    [丢弃 + 日志]◀──────────────────────────────┘           │
│      │ 成功                                                │
│      ▼                                                      │
│  ┌─────────────┐                                           │
│  │Semantic Valid│                                           │
│  │- evidence 存在│                                          │
│  │- ID 有效     │                                           │
│  └─────────────┘                                           │
│      │ 失败                                                │
│      ▼                                                      │
│  ┌─────────────┐                                           │
│  │ 降级处理    │                                           │
│  │- 降为 draft │                                           │
│  │- 降低 conf  │                                           │
│  └─────────────┘                                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### R-02: Token 预算超支

```
预算分配策略：

1. P0 硬预留（始终保证）
   - System Rules: fixed
   - Scene State: fixed
   - Character Quick Facts (硬约束): fixed

2. P1 贪婪分配（score/cost 排序）
   - 达到 cap 时停止
   - 模块内 cap 限制

3. P2 机会填充（有空间才加）
   - 紧张时完全跳过

4. 应急处理
   - prompt_utilization >= 0.85: 跳过后台 LLM
   - headroom < 800: 只保留 P0
```

---

## 5. 技术栈确认

### 5.1 核心技术

| 组件 | 技术 | 版本要求 |
|------|------|----------|
| 框架 | Flutter | >= 3.0 |
| 持久化 | Hive | >= 2.0 |
| 并发 | Isolate | Flutter 内置 |
| AI 集成 | Provider 抽象层 | 现有 |

### 5.2 新增依赖

| 依赖 | 用途 | 必须/可选 |
|------|------|----------|
| `ulid` | logicalId 生成 | 必须 |
| `json_annotation` | JSON 序列化 | 必须 |
| `freezed` | 不可变数据类 | 可选（推荐） |

### 5.3 文件结构

```
lib/
├── models/
│   └── roleplay/
│       ├── rp_story_meta.dart          # typeId 50-52
│       ├── rp_entry_blob.dart          # typeId 53-54
│       ├── rp_operation.dart           # typeId 55-56
│       ├── rp_snapshot.dart            # typeId 57
│       ├── rp_proposal.dart            # typeId 58-59
│       └── rp_enums.dart               # 枚举定义
│
├── services/
│   └── roleplay/
│       ├── roleplay_memory_repository.dart  # Hive CRUD
│       ├── context_compiler.dart            # Budget Broker
│       ├── proposal_applier.dart            # Proposal → Op
│       ├── agent_worker_host.dart           # Isolate 管理
│       ├── orchestrator.dart                # 调度逻辑
│       ├── consistency_gate.dart            # 一致性检测
│       └── modules/
│           ├── rp_module.dart               # 接口定义
│           ├── scene_module.dart
│           ├── character_module.dart
│           ├── state_module.dart
│           ├── goals_module.dart
│           ├── foreshadow_module.dart
│           ├── world_module.dart
│           ├── style_module.dart
│           └── mechanics_module.dart
│
└── widgets/
    └── roleplay/
        ├── memory_panel.dart                # Memory 面板
        ├── proposal_review_dialog.dart      # 提议审批
        └── consistency_badge.dart           # 一致性徽章
```

---

## 6. 验收测试场景

### 6.1 核心场景

| ID | 场景 | 验收标准 |
|----|------|----------|
| T-01 | 新建角色扮演故事 | 创建 StoryMeta + foundation 条目成功 |
| T-02 | 发送消息并接收回复 | 流式输出正常，上下文注入正确 |
| T-03 | 外观不变量检测 | 角色发色错误时触发警告 |
| T-04 | 状态约束检测 | 角色持有未拥有物品时触发警告 |
| T-05 | 后台 Agent 运行 | SceneDetector 在后台正确运行 |
| T-06 | 用户编辑旧消息 | 版本递增，dirty 标记正确 |
| T-07 | 分支创建与切换 | 分支隔离正确 |
| T-08 | 回滚到历史版本 | story 条目正确回滚 |
| T-09 | Proposal 审批 | 用户可接受/拒绝提议 |
| T-10 | 崩溃恢复 | 重启后数据完整 |

### 6.2 边界场景

| ID | 场景 | 验收标准 |
|----|------|----------|
| E-01 | Token 预算耗尽 | P2 丢弃，P0 保留 |
| E-02 | LLM 返回无效 JSON | 重试一次后降级 |
| E-03 | Worker Isolate 崩溃 | 懒重启，本轮降级 |
| E-04 | 高频编辑 | 版本闸门正确过滤过期任务 |
| E-05 | 超长上下文 | 重量闸门正确触发 |

---

## 7. 开放问题（已解决）

所有在 Phase 4 讨论的开放问题已解决，结论记录在：
- `19-ARCHITECTURE-REVIEW.md` 第 6 节
- `20-AGENT-ORCHESTRATION-DESIGN.md` 第 8 节

关键决策摘要：

| 问题 | 决策 |
|------|------|
| 轻量闸门是否始终开启？ | ✅ YES，默认启用 |
| 重量闸门触发阈值？ | prompt_utilization >= 0.85 或 headroom < 800 |
| Foundation 提升 UI？ | Standard 显示，Immersive 隐藏但可访问 |
| v0 分支合并？ | DEFER 完整合并，支持 cherry-pick |
| 过期任务恢复？ | 丢弃 + 重跑，但实现锚点挽救 |
| 后台任务数量？ | 1 个后台 LLM 调用/轮 |
| JSON 修复策略？ | 提取 → 验证 → 重试 → 失败关闭 |

---

## 8. 总结

本设计完成了"写作/跑团式角色扮演"系统的完整架构规划，包括：

1. **架构简化**：消除循环依赖、精简 Canon 层级、压缩 Proposal 类型
2. **Agent 体系**：定义 8 个 Agent、调度逻辑、提示词设计、失败处理
3. **技术实现**：Hive 数据模型、COW 版本控制、Worker Isolate、Context Compiler
4. **边界处理**：一致性闸门、用户编辑传播、分支合并、过期任务恢复

设计遵循"保守精简"原则：
- 不删除灵活性，通过合并降低复杂度
- 保留分层结构，明确边界规则
- 支持渐进式实现（M0-M6 里程碑）

下一步：按里程碑顺序实现，从 M0（Foundation）开始。

---

## 附录 A: 术语表

| 术语 | 定义 |
|------|------|
| **Block** | 记忆模块（Character, World, Scene 等） |
| **Entry** | 单个记忆条目 |
| **View** | 条目的渲染片段，用于上下文注入 |
| **Proposal** | Agent 生成的变更建议 |
| **Operation** | 已确认的变更操作 |
| **Snapshot** | 某版本的 pointer map 快照 |
| **Budget Broker** | Token 预算分配器 |
| **Consistency Gate** | 一致性闸门 |
| **Worker Isolate** | 后台任务隔离线程 |
| **RTCO** | Runtime Context Object，运行时上下文对象 |

## 附录 B: 相关文档

- `07-13`: 原始需求文档序列
- `14-18`: 初版设计文档序列
- `19-ARCHITECTURE-REVIEW.md`: 架构审查与改进
- `20-AGENT-ORCHESTRATION-DESIGN.md`: Agent 体系设计
- `21-TECHNICAL-IMPLEMENTATION-MAPPING.md`: 技术实现映射

