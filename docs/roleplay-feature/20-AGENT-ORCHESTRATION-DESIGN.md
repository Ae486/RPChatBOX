# Agent 体系与编排设计（Draft）

> 目标：定义"写作/跑团式角色扮演"系统的 Agent 清单、职责边界、通信模式、提示词设计、失败处理策略。
>
> 本文档为 Claude + Codex 迭代讨论的结果汇总。
>
> 最后更新：2026-01-07

---

## 0. 设计原则

1. **Orchestrator 确定性**：调度器必须可预测、可审计，不使用 LLM 决策调度
2. **Agent 混合化**：大多数 Agent 为 Hybrid（LLM 语义理解 + 确定性验证）
3. **单一写入者**：所有状态更新通过 Proposals → Tier Policy → Commit 路径
4. **版本闸门**：后台任务必须带版本快照，过期结果丢弃
5. **优雅降级**：任何 Agent 失败不应阻塞用户回复

---

## 1. Agent 分类与清单

### 1.1 分类标准

| 类型 | 定义 | 特点 |
|------|------|------|
| **Deterministic** | 纯规则/状态机，不涉及 LLM | 可预测、无成本、快速 |
| **Hybrid** | LLM 语义理解 + 确定性验证/约束 | 需要 schema 验证、结构化输出 |
| **Full Agent** | 纯 LLM 驱动 | 成本高、输出不确定，需严格限制 |

### 1.2 Agent 清单

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ORCHESTRATOR                                   │
│                         (Deterministic State Machine)                       │
│  职责: 调度、预算分配、版本管理、提议路由、日志记录                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  内置组件:                                                                   │
│  ├── Budget Broker (RTCO 分配)                                              │
│  ├── Tier Policy Router (权限分发)                                          │
│  ├── Job Scheduler (后台任务调度)                                            │
│  └── Version Gate (过期检测)                                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SPECIALIST AGENTS                                 │
├──────────────────┬──────────────────────────────────────────────────────────┤
│ Agent            │ Type        │ 职责                                       │
├──────────────────┼─────────────┼────────────────────────────────────────────┤
│ SceneDetector    │ Hybrid      │ 检测场景转换，输出 SCENE_TRANSITION 提议     │
│ KeyEventExtractor│ Hybrid      │ 从对话中提取关键事件，输出 DRAFT/CONFIRMED   │
│ StateUpdater     │ Hybrid      │ 检测状态变化（物品/伤势/关系），输出更新提议  │
│ GoalsUpdater     │ Hybrid      │ 检测用户意图/目标变化，输出 DRAFT_UPDATE     │
│ ForeshadowLinker │ Hybrid      │ 链接事件到伏笔，更新 Tracker，输出 LINK_UPDATE│
│ CharMemoryUpdater│ Hybrid      │ 更新角色主观记忆/认知，输出 DRAFT_UPDATE     │
│ ConsistencyGate  │ Hybrid      │ 检测违规，可选重写，输出 OUTPUT_FIX          │
│ Summarizer       │ Full Agent  │ 压缩/摘要，输出 COMPRESSION_UPDATE          │
│ EditInterpreter  │ Hybrid      │ 解释用户编辑，分类为纠错/剧情变化/其他        │
└──────────────────┴─────────────┴────────────────────────────────────────────┘
```

### 1.3 层级关系图

```
                    ┌─────────────────────┐
                    │    Orchestrator     │
                    │   (Deterministic)   │
                    └─────────┬───────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
          ▼                   ▼                   ▼
    ┌───────────┐       ┌───────────┐       ┌───────────┐
    │ Sync Path │       │Async Path │       │ On-Demand │
    │(per turn) │       │(background)│       │  (manual) │
    └─────┬─────┘       └─────┬─────┘       └─────┬─────┘
          │                   │                   │
    ┌─────┴─────┐       ┌─────┴─────┐       ┌─────┴─────┐
    │Consistency│       │SceneDetect│       │ Summarizer│
    │   Gate    │       │KeyEventExt│       │(Sleeptime)│
    └───────────┘       │StateUpdate│       └───────────┘
                        │GoalsUpdate│
                        │ForeshadowL│
                        │CharMemory │
                        │EditInterp │
                        └───────────┘
```

---

## 2. Orchestrator 设计

### 2.1 状态机（每轮流程）

```
[TurnStart] ──▶ LoadContext ──▶ BuildCandidates ──▶ PackRTCO
                                                        │
                                                        ▼
                                                  StartStream
                                                        │
                            ┌───────────────────────────┤
                            │                           ▼
                            │                    StreamDrafting
                            │                           │
                      ┌─────┴─────┐              ┌──────┴──────┐
                      │AbortRetry │◀─────────────│OnlineLightGate│
                      │(once max) │  violation   │  (optional)  │
                      └───────────┘              └──────┬──────┘
                                                        │ no violation
                                                        ▼
                                                 FinalizeDraft
                                                        │
                                                        ▼
                                                   PostGate
                                                (light/heavy)
                                                        │
                                                        ▼
                                                FinalizeReply
                                                        │
                                                        ▼
                                                  EmitReply
                                                        │
                                                        ▼
                                                ScheduleJobs
                                             (enqueue async agents)
                                                        │
                                                        ▼
                                            ApplyOrQueueProposals
                                                        │
                                                        ▼
                                                  CommitOps
                                              (single-writer)
                                                        │
                                                        ▼
                                                   LogTurn
                                                        │
                                                        ▼
                                                  [TurnEnd]
```

### 2.2 Orchestrator 维护的状态

**持久化状态（存储，跨会话保留）**：
```typescript
interface OrchestratorPersistentState {
  // 模块配置
  enabled_modules: ModuleId[];
  budget_profile: BudgetProfile;
  per_view_caps: Map<ViewId, number>;

  // 版本追踪
  revisions: {
    foundation_rev: string;
    source_rev: Map<BranchId, string>;
    story_rev: Map<BranchId, string>;
  };

  // 队列
  pending_proposals: Proposal[];
  operation_log: Operation[];
  snapshot_index: SnapshotPointer[];

  // 脏标记
  dirty_flags: Map<ModuleId, DirtyWindow[]>;

  // 可观测性聚合
  recent_injection_stats: InjectionStats[];
}
```

**临时状态（内存，每会话）**：
```typescript
interface OrchestratorEphemeralState {
  turn_id: string;
  last_stream_abort_count: number;
  recent_signals: Signal[];  // ring buffer
  job_registry: Map<JobId, JobHandle>;
}
```

### 2.3 调度决策逻辑

Orchestrator 根据信号决定本轮运行哪些 Agent：

```typescript
function decideAgentsToRun(signals: TurnSignals): AgentTask[] {
  const tasks: AgentTask[] = [];

  // Always consider
  if (signals.scene_uncertainty > THRESHOLD || signals.has_location_cue) {
    tasks.push({ agent: 'SceneDetector', priority: 1 });
  }

  if (signals.has_state_change_keywords || signals.consistency_gate_tension) {
    tasks.push({ agent: 'StateUpdater', priority: 2 });
  }

  if (signals.has_directive_intent || signals.turns_since_goals_check > M) {
    tasks.push({ agent: 'GoalsUpdater', priority: 3 });
  }

  // Trigger-based
  if (signals.has_state_transition_pattern ||
      signals.user_edited_old_message ||
      signals.turns_since_keyevent_check > N) {
    tasks.push({ agent: 'KeyEventExtractor', priority: 2 });
  }

  if (signals.token_pressure_high || signals.scene_changed) {
    tasks.push({ agent: 'Summarizer', priority: 4 });
  }

  if (signals.new_key_events_extracted) {
    tasks.push({ agent: 'ForeshadowLinker', priority: 3 });
  }

  if (signals.has_pov_knowledge_cue || signals.user_edited_old_message) {
    tasks.push({ agent: 'CharMemoryUpdater', priority: 4 });
  }

  // Apply hard caps
  return tasks
    .sort((a, b) => a.priority - b.priority)
    .slice(0, MAX_ASYNC_JOBS_PER_TURN);
}
```

---

## 3. 通信模式（Flutter 实现）

### 3.1 架构选择

**推荐方案：(B) 单一 Worker Isolate**

```
┌─────────────────────────────────────────────────────────────────┐
│                        Main Isolate                             │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ UI + Streaming + Persistence Orchestration              │   │
│  │ (Single-writer commit to Hive)                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                    SendPort/ReceivePort                         │
│                              │                                  │
└──────────────────────────────┼──────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────┐
│                        Worker Isolate                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ LLM Agents + Heavy Parsing/Scoring                      │   │
│  │ (Read-only, returns Proposals)                          │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**为什么不选 (A) 全部主线程**：JSON 解析 + 排序 + 验证会卡 UI
**为什么不选 (C) 每 Agent 一个 Isolate**：协调开销太大

### 3.2 消息协议

**Main → Worker**：
```dart
sealed class WorkerCommand {
  case RunJob({
    required String jobId,
    required String jobType,
    required InputSnapshot inputSnapshot,
    required Map<String, dynamic> payload,
  });

  case CancelJob({required String jobId});

  case Warmup({required ModelCapabilities capabilities});
}
```

**Worker → Main**：
```dart
sealed class WorkerResult {
  case JobResult({
    required String jobId,
    required JobStatus status,
    required List<Proposal> proposals,
    required Diagnostics diagnostics,
    required int tokenEstimate,
  });

  case JobError({
    required String jobId,
    required ErrorType errorType,
    required bool retryable,
  });

  case JobLog({
    required String jobId,
    required LogEvent event,
  });
}
```

### 3.3 黑板快照模式

Worker 不直接读写 Hive。Orchestrator 构建只读快照发送：

```dart
class InputSnapshot {
  final String foundationRev;
  final String storyRev;
  final String sourceRev;

  // 预选的视图数据（已预算裁剪）
  final List<ViewFragment> selectedViews;
  final List<Constraint> relevantConstraints;
  final JobConfig jobConfig;
}
```

Worker 返回 Proposals，Main Isolate 是唯一写入者：
- 应用 Tier Policy
- Commit Operations 到 Hive
- Bump revisions
- 清理/扩展 dirty windows

---

## 4. 提示词设计

### 4.1 通用原则

1. **System Prompt 固定**：角色定义 + 硬规则 + "必须输出有效 JSON"
2. **Injected Context 动态**：仅任务所需的预算视图
3. **结构化输出强制**：JSON schema 在 prompt 中定义，验证后重试一次
4. **证据必须**：任何事实断言必须附带 evidence refs

### 4.2 模板示例：KeyEventExtractor

**System Prompt**：
```
You are KeyEventExtractor for an interactive fiction system.

Task: Extract high-value, objectively occurred events from the provided
conversation window, and output ONLY structured JSON proposals.

Hard rules:
- Do NOT invent facts. Every event must cite evidence spans from messages.
- If uncertain, output a draft proposal with low confidence, or nothing.
- Key Events are "what happened" (objective), not interpretations.
- Do not merge across branches. Use the provided branch_id.
- Output must match the JSON schema exactly. No extra keys, no prose.

Key Event criteria (v0):
- state change (injury/heal, item gained/lost, relationship change)
- location/time transition
- revelation/identity disclosure
- conflict phase change (escalation/de-escalation)
- irreversible action (death, destruction, pact, betrayal)

If no key event exists, output proposals=[].
```

**Output Schema**：
```json
{
  "agent": "KeyEventExtractor",
  "version": "0.1",
  "story_id": "string",
  "branch_id": "string",
  "input_snapshot": {
    "foundation_rev": "string",
    "story_rev": "string",
    "source_rev": "string"
  },
  "proposals": [
    {
      "proposal_kind": "DRAFT_UPDATE|CONFIRMED_WRITE",
      "domain": "timeline",
      "subtype": "key_event_create",
      "risk": "low|medium|high",
      "confidence": 0.0-1.0,
      "target": {
        "scope": "story",
        "status": "draft|confirmed",
        "module": "timeline",
        "entry_id": "needs_new_id"
      },
      "patch": {
        "operation": "create",
        "entry": {
          "event_type": "string",
          "summary": "string",
          "order_hint": "optional",
          "participants": ["character_id"],
          "location_hint": "optional",
          "time_hint": "optional"
        }
      },
      "evidence": [
        {
          "type": "message_span",
          "message_id": "string",
          "start": 0,
          "end": 0,
          "quote": "string"
        }
      ],
      "reason": "string"
    }
  ],
  "diagnostics": {
    "events_found": 0
  }
}
```

### 4.3 其他 Agent 模板摘要

| Agent | 关键输入 | 关键输出 | 特殊规则 |
|-------|----------|----------|----------|
| **SceneDetector** | 对话窗口 + 前一场景 | SCENE_TRANSITION | 不依赖 Foreshadow |
| **StateUpdater** | 对话 + 当前状态 | DRAFT/CONFIRMED_WRITE | 需引用消息证据 |
| **GoalsUpdater** | 对话 + 当前目标 | DRAFT_UPDATE | 目标生命周期管理 |
| **ForeshadowLinker** | Key Events + 伏笔列表 | LINK_UPDATE | 不自动生成 negative |
| **CharMemoryUpdater** | 对话 + 角色卡 | DRAFT_UPDATE | 区分"角色知道/相信/误解" |
| **ConsistencyGate** | 回复草稿 + 约束 | OUTPUT_FIX | 可选重写 |
| **Summarizer** | 对话窗口 + Scene | COMPRESSION_UPDATE | 严格 token 上限 |
| **EditInterpreter** | diff + 上下文 | USER_EDIT_INTERPRETATION | 分类：纠错/剧情变化/润色 |

---

## 5. 失败处理

### 5.1 验证策略

```
LLM Output
    │
    ▼
┌─────────────┐   失败   ┌─────────────┐
│ JSON Parse  │─────────▶│ Repair Retry │─────┐
└─────────────┘          │ (1次 max)    │     │
    │ 成功               └─────────────┘     │
    ▼                          │ 成功        │ 仍失败
┌─────────────┐               ▼              │
│Schema Valid │◀──────────────┘              │
└─────────────┘                              │
    │ 失败                                    │
    ▼                                         │
  [丢弃 + 日志]◀──────────────────────────────┘
    │ 成功
    ▼
┌─────────────┐
│Semantic Valid│
│- evidence 存在│
│- ID 有效     │
│- 规则遵守    │
└─────────────┘
    │ 失败
    ▼
┌─────────────┐
│ 降级处理    │
│- 降为 draft │
│- 降低 conf  │
│- 或丢弃     │
└─────────────┘
```

### 5.2 失败处理矩阵

| Agent | 失败类型 | 重试 | 降级方案 | 用户影响 |
|-------|----------|------|----------|----------|
| Orchestrator | 异常 | N/A | 跳过非关键任务，保持聊天运行 | 无/最小 |
| SceneDetector | 无效 JSON / 超时 | 1 | 本轮不产生场景提议 | 无 |
| KeyEventExtractor | 无效 JSON / 超时 | 1 | 推迟；标记窗口为 dirty | 无 |
| StateUpdater | 冲突 | 0-1 | 仅生成 review-required 提议 | 最小 |
| GoalsUpdater | 低置信度 | 0 | draft-only / 队列 | 无 |
| ForeshadowLinker | negative 建议 | 0 | 降级为 neutral / 要求审查 | 无 |
| Summarizer | 输出质量差 | 1 | 截断 + 简化摘要；或跳过 | 轻微 token 成本 |
| ConsistencyGate | 无法修复 | 0 | warn/log；可选"重新生成"按钮 | 最小 |

### 5.3 全局规则

**永不阻塞用户回复**，除非：
- 关键硬约束违规 **且** 无法安全重写 **且** 用户启用了严格模式

---

## 6. Sleeptime 维护模式

### 6.1 触发时机

- App 空闲时
- App 恢复时
- 充电 / 低 CPU 压力（如可检测）
- 用户手动触发"维护"

### 6.2 任务清单

| 任务 | 优先级 | 描述 |
|------|--------|------|
| **摘要整合** | 高 | 刷新场景摘要、压缩 previously_on |
| **证据升级** | 中 | 消息片段引用 → 事件引用 |
| **Linker 重算** | 中 | 仅针对 dirty 伏笔或新 Key Events |
| **提议积压处理** | 中 | 合并重复、去重、折叠低价值 draft |
| **垃圾收集** | 低 | 归档陈旧 draft（不删除） |
| **索引重建** | 低 | View 选择器的轻量索引 |

### 6.3 预算与版本

- Sleeptime 任务同样受预算约束
- 同样需要版本闸门（用户可能中途编辑）

---

## 7. 用户编辑流程（关键路径）

### 7.1 时序图

```
User                 UI/Main            Source        Orchestrator      Worker        Proposals
  │                    │                  │                │               │              │
  │──Edit msg N───────▶│                  │                │               │              │
  │                    │──Create Revision▶│                │               │              │
  │                    │◀──source_rev++───│                │               │              │
  │                    │──Append Operation│                │               │              │
  │                    │──Log EditEvent───│                │               │              │
  │                    │                  │                │               │              │
  │                    │──Notify(EditEvent, source_rev)───▶│               │              │
  │                    │                  │                │               │              │
  │                    │                  │                │──Mark dirty───│              │
  │                    │                  │                │  windows      │              │
  │                    │                  │                │──Invalidate───│              │
  │                    │                  │                │  caches       │              │
  │                    │                  │                │               │              │
  │                    │                  │                │──Enqueue Jobs─│──────────────│
  │                    │                  │                │  (versioned)  │              │
  │                    │                  │                │               │              │
  │                    │                  │                │◀──JobResult───│              │
  │                    │                  │                │  (proposals)  │              │
  │                    │                  │                │               │              │
  │                    │                  │                │──Stale check──│              │
  │                    │                  │                │               │              │
  │                    │                  │                │──────────────────────────────▶│
  │                    │                  │                │                              │
  │                    │                  │                │──Log proposals───────────────│
  │                    │                  │                │                              │
  │                    │                  │                │               │              │
  │◀──(Continue chat)──│                  │                │               │              │
```

### 7.2 关键行为

1. **编辑立即改变 `source_rev`**
2. **派生模块数据标记为 dirty（窗口化）**
3. **正在运行的后台任务因 rev 不匹配而过期丢弃**
4. **提议进入队列；用户可审批/回滚**
5. **ConsistencyGate 主要影响未来输出；可选重检上一条助手消息**

---

## 8. 已确认决策（Phase 4 结论）

### 8.1 Agent 粒度

**Q: CharMemoryUpdater 是否应该与 StateUpdater 合并？**
- ✅ **决策：NO，保持分离**
- 语义不同：客观状态 vs 主观信念/知识
- 优化允许：单次 LLM 调用产出多 domain 补丁，但仍按 domain 发射为独立 proposals

**Q: EditInterpreter 是否应该内置到 Orchestrator？**
- ✅ **决策：独立组件（确定性工具 + 可选 Hybrid LLM）**
- Stage 1（始终）：确定性 diff 分类 + 影响域提示
- Stage 2（条件）：仅低置信度/大 retcon 时调用 LLM 解释
- Orchestrator 触发它，保持调度器确定性和可测试

### 8.2 函数调用支持

**Q: 不支持函数调用的模型的 JSON 修复策略？**
- ✅ **决策：提取 → schema 验证 → 一次修复重试 → 失败关闭**
1. 使用哨兵或 `{...}` 扫描提取 JSON 子串
2. 严格 schema 验证 + 语义检查
3. 一次修复重试（低温度 + 显式验证错误 + "JSON only" 指令）
4. 仍无效：返回空 proposals + 日志，**不阻塞**

**Q: 是否需要按模型配置不同的 Agent 提示词模板？**
- ✅ **决策：允许但非必须**
- 默认模板适用于大多数模型
- 可选：per-provider 模板覆盖（如本地模型需更显式的 JSON 指令）

### 8.3 性能预算

**Q: 单轮最大后台 Agent 数量？**
- ✅ **决策：按网络 LLM 调用限制，非逻辑 Agent 数**
- 默认：**1 个后台 LLM 调用/轮**
- 例外：重量闸门触发或用户编辑需紧急语义解释时允许 **+1**
- 确定性任务：无限制（但保持 CPU 轻量）

**Q: 后台任务 Token 预算分配？**
- ✅ **决策：单一"维护调用"预算 + 硬上限；高压力时跳过**

| 条件 | 行为 |
|------|------|
| `prompt_utilization >= 0.85` 或 `headroom < 800` | 跳过后台 LLM 维护（紧急解释除外） |
| 否则 | `BG_IN_CAP = min(1500, 0.18 × context_window)` |
| | `BG_OUT_CAP = min(600, 0.10 × context_window)` |
| 重摘要触发 | `BG_OUT_CAP_HEAVY = min(900, 0.14 × context_window)` |

**Q: Proposal 弹窗可接受延迟？**
- ✅ **决策：proposals 永不阻塞流式；目标快速后置呈现**
- 目标：助手完成后 **<3s** 显示 review-required 弹窗
- 可接受最坏：**<10s**，显示 "Processing updates…" 指示器
- Silent proposals 异步应用，无弹窗

---

## 9. 相关文档

- **Phase 1**：架构审查 → `19-ARCHITECTURE-REVIEW.md`
- **Phase 3**：技术实现映射 → `21-TECHNICAL-IMPLEMENTATION-MAPPING.md`
- **Phase 5**：总结文档 → `22-FINAL-SUMMARY.md`

