# 架构审查与改进方案（Draft）

> 目标：基于 07-18 系列文档的设计，进行专业架构审查，识别问题并给出改进方案。
>
> 本文档为 Claude + Codex 迭代讨论的结果汇总。
>
> 最后更新：2026-01-07

---

## 0. 审查背景

### 0.1 原始设计概览

原设计包含：
- **9 个模块**：Character、World、Scene、Timeline、Goals、Foreshadow_Hooks、State、Style、Mechanics
- **3 层数据模型**：foundation（基底）→ canon_story（随剧情演进）→ draft（草稿）
- **13 种 Proposal 类型**：Canon-Write（4 类）+ Draft-Only（9 类）
- **软依赖模块系统**：只使用 `suggests`，不使用 `requires`

### 0.2 识别的问题

| 风险级别 | 问题 | 影响 |
|---------|------|------|
| 🔴 高 | 循环依赖（foreshadow↔goals、Scene↔Timeline↔Foreshadow） | 数据流不清晰，难以维护 |
| 🔴 高 | 派生数据失效范围不明确 | 编辑旧消息后可能导致级联错误 |
| 🔴 高 | 一致性闸门未定义 | 无法拦截外观/状态/时间线错误 |
| 🟡 中 | Canon 层级过度细分 | 心智负担重，概念混淆 |
| 🟡 中 | Proposal 类型冗余（13 类） | 实现复杂度高 |
| 🟡 中 | View 缺乏全局 token 分配 | 模块间争抢预算 |
| 🟡 中 | 后台任务"一刀切丢弃" | 可能浪费有效计算 |

---

## 1. 依赖流重构：单向脊柱模型

### 1.1 问题根因

原设计中存在双向依赖：
- `foreshadow_hooks` ↔ `goals`：目标完成触发伏笔回收；伏笔可能产生新目标
- `Scene` ↔ `Timeline` ↔ `Foreshadow`：场景切换触发关键事件；关键事件影响伏笔进度；伏笔紧迫度可能促使场景切换

**根本原因**：混淆了"数据所有权"（谁写入真相）和"行为影响"（谁建议下一步）。

### 1.2 解决方案：Timeline 作为数据模型脊柱（非运行时阻塞）

建立单向数据流，以 **Timeline（Key Events）** 作为剧情推进的权威账本：

> **重要澄清**：Timeline 是"数据模型原则"，不是"运行时阻塞原则"。不要求每轮都等待 KeyEventExtractor 完成。

```
Source (active chain)
    ↓
SceneDetector → Scene Proposal
    ↓
KeyEventExtractor → Timeline (Key Events)
    ↓
    ├── StateUpdater → State/Flags
    ├── GoalsUpdater → Goals
    ├── ForeshadowLinker → Foreshadow Trackers
    └── CharacterMemoryUpdater → Character Memory
    ↓
Proposals → Tier Policy → Commit
```

**核心规则**：
1. **Scene 不依赖 Foreshadow**：场景切换由对话+前一场景推断，伏笔紧迫度只产生"叙事提示"（注入建议），不自动触发场景变更
2. **Goals 和 Foreshadow 不直接互写**：目标完成/伏笔回收都变成 Key Event，各模块从 Timeline 流中读取更新
3. **每轮固定顺序**：避免同轮乒乓

### 1.3 实用的放宽模型

完全的"单一脊柱"会造成延迟瓶颈。实际采用放宽模型：

**快速路径（低延迟直接更新）**：
- State 可直接从用户轮次提议更新（例如"我拿起钥匙"）
- Goals 可直接从用户意图提议更新
- SceneDetector 可直接提议场景切换

**机会性 Timeline 提取**：
- 仅在信号表明重要时运行 KeyEventExtractor：
  - 场景切换确认
  - 用户编辑旧消息
  - 明显的"状态转换"模式（伤害、物品获得/丢失、揭示）
  - token 压力 / 摘要器运行
  - 每 N 轮作为维护扫描
- 否则跳过（或用低成本分类器判断"是否关键事件？"）

**降级路径**：
- ForeshadowLinker 在 Timeline 缺失时可退化为使用 **消息片段** 作为证据
- 当 Timeline 后续补全时，可"升级"消息片段证据为事件引用

### 1.4 依赖关系图（单向）

```
┌─────────────────────────────────────────────────────────────────┐
│                     Source (active chain + edits)               │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SceneDetector (Hybrid)                     │
│                      → Scene Proposal                           │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  KeyEventExtractor (Hybrid)                     │
│                  → Timeline: Key Events                         │
│                  (branch-scoped, canon_story)                   │
└─────────────────────────────────────────────────────────────────┘
                                │
        ┌───────────┬───────────┼───────────┬───────────┐
        ▼           ▼           ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │  State  │ │  Goals  │ │Foreshadow│ │Character│ │Summarizer│
   │ Updater │ │ Updater │ │ Linker  │ │ Memory  │ │         │
   └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘
        │           │           │           │           │
        └───────────┴───────────┴───────────┴───────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              Proposals → Tier Policy → Commit                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 层级简化：两个作用域 + 一个状态

### 2.1 问题根因

原设计"3 层 + 每模块各自 Canon"造成混淆：
- 层级命名暗示"Canon 是多个东西"
- 实际上存在两个正交维度：**作用域/回滚** 和 **认知权威/确认状态**

### 2.2 解决方案：统一的 Entry 模型

将原来的三层重构为两个维度：

```
Entry {
  module_id: string
  entry_type: string

  scope: "foundation" | "story"     // 作用域
  status: "confirmed" | "draft"     // 确认状态
  branch_id: string                 // scope=story 时必须

  evidence: Evidence[]
  content: any
  revision: string
}
```

**映射关系**：
| 原概念 | 新模型 |
|--------|--------|
| foundation（基底） | `scope=foundation, status=confirmed` |
| canon_story（随剧情演进的已确认事实） | `scope=story, status=confirmed` |
| draft（工作记忆） | `scope=story, status=draft` |

**语义澄清**：
- **硬约束**：`status=confirmed`（无论 foundation 还是 story）
- **剧情回滚**：回滚所有 `scope=story` 的条目（confirmed + draft）
- **基底编辑**：有独立的撤销/审计线，不随剧情回滚

### 2.3 Foundation vs Story 边界规则

| 场景 | 处理方式 |
|------|----------|
| **提升 Delta 到基底**（story→foundation） | 显式"提升操作"，用户确认，创建新 foundation_rev |
| **基底编辑中途**（foundation 改了） | 触发"故事一致性审查"，生成冲突集，不自动失效 canon_story |
| **冲突时优先级** | 默认 canon_story 在该故事/分支内覆盖 foundation |

---

## 3. Proposal 类型精简：13 → 7

### 3.1 问题根因

原 13 种 Proposal 类型存在功能重叠，本质是同一变更类的领域变体。

### 3.2 解决方案：7 种最小分类 + domain 分发

保留 7 种主类型，添加必要的 `domain` 字段用于 UI 路由和验证规则分发：

```typescript
interface Proposal {
  proposal_kind: ProposalKind;  // 7 种之一（驱动权限层级）
  domain: Domain;               // 必须（驱动 UI 路由 + 验证规则）
  subtype?: string;             // 可选（领域内细分）
  // ... 其他字段
}

type ProposalKind =
  | "CONFIRMED_WRITE"
  | "DRAFT_UPDATE"
  | "LINK_UPDATE"
  | "SCENE_TRANSITION"
  | "COMPRESSION_UPDATE"
  | "OUTPUT_FIX"
  | "USER_EDIT_INTERPRETATION";

type Domain =
  | "character" | "world" | "scene" | "timeline"
  | "goals" | "foreshadow_hooks" | "state" | "style" | "mechanics";
```

| 新类型 | 描述 | 原类型映射 |
|--------|------|-----------|
| **CONFIRMED_WRITE** | 写入 `status=confirmed` 的任何条目 | World/Character/KeyEvent/State Canon-Write |
| **DRAFT_UPDATE** | 写入 `status=draft` 的任何条目 | Goals Update, Tracker Update, Character Memory |
| **LINK_UPDATE** | 创建/更新链接条目 | Foreshadow Link |
| **SCENE_TRANSITION** | 场景切换提议 | Scene Change |
| **COMPRESSION_UPDATE** | 摘要/压缩提议 | Summarize/Compress |
| **OUTPUT_FIX** | 一致性闸门重写回复 | Consistency Gate Fix |
| **USER_EDIT_INTERPRETATION** | 用户编辑差异分类 | User Edit Correction |

### 3.3 权限层级保持不变

```
silent          → 静默更新，只写日志
notify_apply    → 提醒后直接更新
review_required → 必须用户确认（CONFIRMED_WRITE 默认）
```

---

## 4. Token 预算协调：Budget Broker

### 4.1 问题根因

各 View 各自为政，缺乏全局分配策略，导致预算争抢或静默丢弃。

### 4.2 解决方案：单一 Budget Broker

由 Orchestrator 内置的 Budget Broker 统一管理：

```
┌─────────────────────────────────────────────────────────────┐
│                     Budget Broker (RTCO)                    │
├─────────────────────────────────────────────────────────────┤
│  P0 (必须): 硬预留，严格上限                                  │
│  - System Rules                                             │
│  - Scene State (当前)                                       │
│  - Character Quick Facts (硬约束字段)                        │
├─────────────────────────────────────────────────────────────┤
│  P1 (重要): 按 score/cost 贪婪分配                           │
│  - Active State Constraints                                 │
│  - Current Goals (top-N)                                    │
│  - Due Foreshadows (top-N)                                  │
│  - World Keyword Hits (top-N)                               │
│  - Style Card (按频率)                                      │
├─────────────────────────────────────────────────────────────┤
│  P2 (可选): 机会性填充，优先丢弃                              │
│  - Timeline Key Events (top-N)                              │
│  - Extra Lore / Summaries                                   │
│  - Mechanics                                                │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 优先级矩阵（默认值）

| View / Fragment | Tier | 必须? | Min | Max | 冲突处理 |
|-----------------|------|-------|-----|-----|----------|
| System/Tool rules | P0 | ✅ | fixed | fixed | 永不丢弃 |
| Scene State | P0 | ✅ | short | short | 截断字段，不丢弃 |
| Character Quick Facts | P0 | ✅* | tiny | small | 降级为"仅易错字段" |
| State Constraints | P1 | ❌ | 0 | small | 先丢低严重度 |
| Current Goals | P1 | ❌ | 0 | small | 降为 top-1 |
| Due Foreshadows | P1 | ❌ | 0 | small | 降为 top-1 |
| World Keyword Hits | P1 | ❌ | 0 | medium | 先丢低优先级 |
| Style Card | P1 | ❌ | 0 | small | 本轮跳过 |
| Timeline Events | P2 | ❌ | 0 | medium | 紧张时降为 0 |
| Mechanics | P2 | ❌ | 0 | small | 通常为 0 |

### 4.4 分配算法

```
score = (wR × relevance + wU × urgency + wK × risk + wP × base_priority + wN × novelty)
        / (tokens_est ^ α)

推荐权重：wR=0.40, wU=0.25, wK=0.25, wP=0.10, wN=0.05, α=1.0
```

---

## 5. 一致性闸门 v0 契约

### 5.1 设计原则

- **两阶段**：预生成（约束注入）+ 后生成（违规检测）
- **两层级**：轻量闸门（始终运行）+ 重量闸门（触发式运行）
- **不阻塞**：本地可修正则自动重写，全局/模糊则警告+队列提议

### 5.2 检查清单（v0 最小集）

| 类别 | 检查内容 | 硬/软 |
|------|----------|-------|
| **外观不变量** | hair_color, eye_color, species, name, pronouns | 硬 |
| **状态约束** | 物品持有、伤势、关系、位置锁 | 硬 |
| **时间线顺序** | 事件是否已发生、当前时间标记 | 硬 |
| **场景约束** | 位置、在场角色、时间 | 硬 |

### 5.3 执行计划

**Tier 1 — 轻量闸门（始终运行）**
- 输入：draft_reply + Quick Facts（硬）+ State Constraints（硬）+ present_characters
- 检查：外观不变量、状态矛盾、在场角色不匹配
- 行为：minor→warn+log；major+local→单次自动重写；永不弹窗

**Tier 2 — 重量闸门（触发式）**
- 触发条件：用户编辑旧消息、场景切换、新 canon_story 确认、上下文压力
- 额外输入：timeline.key_events_topn、软约束、POV 提示
- 额外检查：时间线顺序冲突、知识泄露检测
- 行为：可能 retcon 则 warn+创建 review-required 提议；不阻塞

### 5.4 流式场景处理

在 SSE 流式输出场景下，一致性闸门需要特殊处理：

**混合模式（推荐）**：
1. **预流式**：将最紧约束注入 P0（场景 + Quick Facts + 硬状态约束）→ 减少漂移
2. **流式中**：可选的轻量在线检测（高置信度、易检测的违规）
   - 检测到时可 **中止生成并重试**（调整提示词）
3. **流式后**：完整闸门验证
   - minor 问题：仅日志
   - 严重但局部问题：创建 `OUTPUT_FIX` 提议
     - Standard 模式：提供"应用修正"按钮
     - Immersive 模式：日志 + 可选的一键修正

**不推荐的方案**：
- ❌ 完全缓冲后再流式（延迟太高）
- ❌ 仅非流式场景运行闸门（正好在最需要时缺失）

### 5.5 输入输出契约

```typescript
// 输入
interface GateInput {
  gate_version: string;
  story_id: string;
  branch_id: string;
  turn_id: string;
  mode: "standard" | "immersive" | "god";

  revisions: {
    foundation_rev: string;
    canon_story_rev: string;
    draft_rev: string;
    source_rev: string;
  };

  draft_reply: {
    assistant_text: string;
    speaker_pov: "user_role" | "narrator" | "character:<id>" | "unknown";
  };

  scene: {
    scene_id: string;
    location?: string;
    present_characters: string[];
    current_goal_or_conflict?: string;
  };

  constraints: {
    character_quick_facts: QuickFact[];
    state_constraints: StateConstraint[];
    timeline_constraints: TimelineConstraint;
  };

  policies: {
    autofix_allowed: boolean;
    block_on_major: boolean;
    max_fix_attempts: number;
  };
}

// 输出
interface GateOutput {
  status: "pass" | "fixed" | "warn" | "fail";
  violations: Violation[];
  fix?: {
    attempted: boolean;
    method: "rewrite" | "soften" | "none";
    after_text?: string;
  };
  followups: {
    proposals_to_create: ProposalCandidate[];
    log_events: LogEvent[];
  };
}
```

---

## 6. 已确认决策（Phase 4 结论）

### 6.1 一致性闸门触发策略

**Q: 轻量闸门是否对所有模型都足够？**
- ✅ **决策：YES，默认始终开启**
- 轻量闸门主要是确定性验证，不依赖函数调用
- 配置：允许 per-story 开关 `gate.light.enabled`（高级选项），但默认启用

**Q: 重量闸门的触发阈值（"上下文压力"指标）？**
- ✅ **决策：基于以下指标触发**

| 指标 | 阈值 |
|------|------|
| `prompt_utilization` | >= 0.85 |
| `headroom_tokens` | < 800 |
| `rtco_drop_ratio` | >= 0.50 |
| `summary_debt_events` | >= 25 |
| `recent_edit_risk` | true（最近 2 轮内编辑） |
| `recent_gate_warn_or_error` | true（最近 3 轮有违规） |

**Q: 流式场景下 autofix 失败处理？**
- ✅ **决策：永不阻塞或重写已流式文本，优雅降级**
- 保留已流式输出
- 生成 `OUTPUT_FIX` 提议（含推荐动作）
- 隔离该轮的自动写入（需 review）
- UI 显示非阻塞徽章

### 6.2 Foundation 动态更新

**Q: "提升 Delta 到基底"的 UI 入口？**
- ✅ **决策：Standard 模式显示，Immersive 隐藏但可访问**
- Standard：条目详情页 "Promote to Foundation"
- Immersive：Memory 面板（侧边抽屉/专用页面）

**Q: 故事一致性审查触发方式？**
- ✅ **决策：自动轻量 + 可选手动重量**
- Foundation 编辑后自动标记相关模块 dirty，入队轻量审查
- 提供手动按钮 "Run full story consistency review"

**Q: 现有 canon_story 条目处理？**
- ✅ **决策：保留，overlay 优先级不变，标记潜在冲突**
- 不删除/失效现有 `story/confirmed` 条目
- story delta 覆盖 foundation base（同字段时）
- 运行审查生成调整提议

### 6.3 分支合并

**Q: v0 是否支持分支合并/cherry-pick？**
- ✅ **决策：DEFER 完整合并，YES 支持 "复制分支" + "cherry-pick 条目"**
- v0 支持：从修订创建分支、cherry-pick 选定条目
- v0 不支持：自动多分支时间线合并

**Q: Key Events 冲突处理？**
- ✅ **决策：导入为新事件，不尝试语义合并**
- Cherry-pick 时分配新 eventId，保留来源 "imported from branch X"
- 疑似重复标记 `needs_review`

**Q: Foreshadow tracker 冲突？**
- ✅ **决策：tracker 视为派生数据，尽可能重算**
- 默认：导入 setup 文本 + 重置 tracker 为 0/"open"
- 可选：高级用户可选择 "import with current tracker"

### 6.4 过期任务恢复

**Q: 增量重算 vs 丢弃+重跑？**
- ✅ **决策：v0 = 丢弃 + 重跑，但实现最小锚点挽救**

**Q: 锚点验证成本/收益？**
- ✅ **决策：YES 实现，成本低且节省 LLM 调用**
- 锚点集：`requiredSourceRev` + `messageIdsUsed[]` + `memoryPointerDigest`
- 接受条件：rev 匹配 OR 锚点匹配

**Q: 部分有效结果处理？**
- ✅ **决策：按 proposal 逐个挽救，拒绝其余**
- 验证每个 proposal 的 staleness guards + anchors
- 通过的应用，失败的标记 `rejected` + `reason="stale_conflict"`

---

## 7. 相关文档

- **Phase 2**：Agent 体系设计 → `20-AGENT-ORCHESTRATION-DESIGN.md`
- **Phase 3**：技术实现映射 → `21-TECHNICAL-IMPLEMENTATION-MAPPING.md`
- **Phase 5**：总结文档 → `22-FINAL-SUMMARY.md`

