# Story Runtime Module Architecture

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Date: 2026-05-05
>
> Purpose: 根据现有 spec / 需求文档，对 story runtime 进行总体架构设计与模块拆分。

## 1. 总体设计目标

story runtime 的设计目标不是“再造一个大 agent”，而是：

> 用稳定的 workflow 骨架，把 Memory OS、worker、writer、retrieval、post-write 维护链组织成一个可扩展的运行时系统。

核心原则：

- 重 workflow，轻 agent
- mode 差异主要落在 worker / policy，不再额外增加新的总抽象层
- writer 只负责写作与受控检索，不负责 memory 治理
- worker 负责 memory 管理与上下文治理
- scheduler 掌握执行权

---

## 2. 顶层模块图

```text
Story Runtime
├─ A. Runtime Identity Module
├─ B. Runtime Profile / ModeProfile Compiler
├─ C. Turn Intake / Command Surface
├─ D. Scheduler / Orchestrator Module
├─ E. Worker Registry / Worker Executor
├─ F. Context Orchestration Module
├─ G. Writer Runtime Module
├─ H. Runtime Workspace Module
├─ I. Memory Integration Module
├─ J. Post-write Maintenance Module
├─ K. Longform Experience Module
├─ L. Observability / Debug Module
└─ M. Branch / Rollback Adapter Module
```

---

## 3. 模块拆分

## A. Runtime Identity Module

### 责任

- 定义并分配本轮 runtime 身份：
  - `StorySession`
  - `BranchHead`
  - `Turn`
  - `RuntimeProfileSnapshot`
- 作为 memory / retrieval / workspace / proposal / trace 的统一锚点

### 输入

- story session
- active branch
- 当前命令

### 输出

- `MemoryRuntimeIdentity`
- pinned snapshot ref

### 为什么必须独立

如果这一层不先独立，后面任何 branch、rollback、pending、worker candidate、usage trace 都会混线。

---

## B. Runtime Profile / ModeProfile Compiler

### 责任

- 把 `ModeProfile + worker config + runtime config` 编译成不可变 `RuntimeProfileSnapshot`
- 输出：
  - worker enablement
  - per-worker permission
  - writer policy
  - retrieval policy
  - packet policy
  - post-write policy
  - latency/budget policy

### 输入

- setup profile defaults
- runtime panel patch
- worker config stage 产物

### 输出

- immutable snapshot

### 与 A 的关系

`A` 负责“本轮用哪个 snapshot”；`B` 负责“怎么生成 snapshot”。

---

## C. Turn Intake / Command Surface

### 责任

- 接住前端动作
- 归一化为 runtime 可理解的 turn command
- 决定进入哪条 workflow 路线

### 典型动作

- longform:
  - `brainstorm/discussion`
  - `rewrite`
  - `accept_and_continue`
  - `complete_chapter`
- roleplay/trpg:
  - `user_input`
  - `rule_card_submit`
  - `manual_refresh`

### 当前判断

旧 API / command surface 只作为产品语义参考，不是必须兼容的后端约束。若保留薄 adapter 能降低前端同步成本，可以保留；若旧入口阻碍新 `Turn / Scheduler / Worker / Runtime Workspace` 合同，应按新 command surface 重建。

---

## D. Scheduler / Orchestrator Module

### 责任

- 让 LLM 只负责提案
- 让程序负责裁决
- 管理本轮 worker 执行计划

### 子职责

1. 向 `Orchestrator Worker` 请求结构化 plan
2. 根据 registry / permission / budget / phase 验证
3. 输出最终 `WorkerExecutionPlan`
4. 决定：
   - 哪些 worker 执行
   - 哪些跳过
   - 哪些降级
   - 哪些允许 async / pending

### 为什么单独成模块

因为这是 story runtime 的真正“总控器”，不能继续埋在 longform orchestrator service 里。

---

## E. Worker Registry / Worker Executor

### 责任

- 统一描述 worker
- 根据 `RuntimeProfileSnapshot` 启停 worker
- 以统一合同执行 worker

### worker 划分原则

- 责任按 `domain` 登记
- 执行 worker 可聚合多个强相关 domain
- phase 不拆成不同 worker 身份

### 第一阶段 bootstrap worker

- `LongformMemoryWorker`
- `WritingWorker`
- 预留：
  - `CharacterMemoryWorker`
  - `SceneInteractionWorker`
  - `RuleStateWorker`
  - `MaintenanceWorker`

### 关键约束

- 共享统一 contract
- registry-driven
- pluggable

---

## F. Context Orchestration Module

### 责任

- 确定性上下文编排
- 负责 packet 组装，不负责智能决策

### 对 worker

输出 `WorkerContextPacket`：

- recent refs
- projection refs
- retrieval refs
- sidecar refs
- forbidden context
- budget

### 对 writer

输出 `WritingPacket`：

- core view
- recent raw turns
- mode sidecars
- retrieval cards
- review overlay
- system prompt / writer contract

### 为什么不能混到 scheduler

因为 scheduler 决定“找谁做”；context orchestration 决定“给多少材料、按什么形状给”。

---

## G. Writer Runtime Module

### 责任

- 唯一用户可见输出
- 支持：
  - `brainstorm/discussion`
  - `writing/rewrite`
- 在受控边界内发起 retrieval

### 不负责

- block 路由
- proposal/apply
- authoritative truth 写入

### 内部子层

1. writer prompt rendering
2. bounded retrieval loop
3. usage hook
4. final output generation

---

## H. Runtime Workspace Module

### 责任

- 做当前 turn 的临时材料层
- 不是 memory truth
- 但要持久化

### 典型材料

- writer input/output ref
- retrieval card / expand chunk / miss / usage
- review overlay
- rule card / state card
- worker candidate / evidence bundle
- packet ref
- token usage
- post-write trace

### 为什么单独成模块

因为它是所有“当前轮临时材料”的统一容器，不能继续散落在 graph state、artifact table、service 局部变量里。

---

## I. Memory Integration Module

### 责任

- 把 runtime 接到 Memory OS
- 不直接管理 UI 和具体文案

### 对接面

- Core State authoritative read/write
- projection read/refresh
- Recall search/materialization
- Archival search/ingestion
- proposal/apply
- provenance/version read

### 关键原则

- 所有写 truth 的路径都走治理链
- retrieval hit 默认只是证据
- projection 严格来源于事实层

---

## J. Post-write Maintenance Module

### 责任

- writer 输出后的主链
- 不是附属脚本

### 子职责

1. 记录最小 turn log
2. 满足条件时触发完整调度
3. 让 worker 分析：
   - user input
   - writer output
   - sidecars
   - retrieval usage
4. 优先刷新下一轮需要的 projection view
5. 再做 proposal / apply / recall / archival maintenance

### 与 H 的关系

`H` 存材料；`J` 消费材料并推动沉淀。

---

## K. Longform Experience Module

### 责任

- 承接 longform 特有行为，不污染通用 runtime

### 负责的内容

- chapter lifecycle
- accepted outline / chapter goal provider
- review overlay
- discussion summary apply flow
- pending segment / accepted segment 行为

### 为什么单独成模块

因为 longform 确实有特殊需求，但不应该把这些特殊需求写死进 scheduler / workspace / worker core。

---

## L. Observability / Debug Module

### 责任

- 暴露 debug 页面和读接口
- 给 eval session 留 trace contract

### 典型输出

- runtime identity
- profile snapshot version
- worker plan
- worker result
- writer packet summary
- runtime workspace materials
- retrieval usage
- proposal/apply receipts
- pending status

---

## M. Branch / Rollback Adapter Module

### 责任

- 把 LangGraph checkpoint/fork 能力和外部 memory/text/workspace 状态对齐

### 第一阶段边界

- 先做合同和 preflight
- 不做完整 UI
- 不做全部产品能力

### 为什么不直接并入别的模块

因为 graph checkpoint 是 LangGraph 层，memory/text/workspace 是应用层；两者之间需要一个专门的对齐层。

---

## 4. 模块依赖顺序

```text
A Runtime Identity
  -> B Runtime Profile Compiler
  -> D Scheduler / Orchestrator
  -> E Worker Registry / Executor
  -> F Context Orchestration
  -> G Writer Runtime
  -> H Runtime Workspace
  -> J Post-write Maintenance
  -> I Memory Integration
  -> L Observability / Debug

K Longform Experience
  -> depends on A/B/C/F/G/H/J

M Branch / Rollback Adapter
  -> overlays A/H/I/J/L and LangGraph shell
```

---

## 5. 推荐的工程边界

## 应该是核心通用层的

- Runtime Identity
- Runtime Profile Snapshot
- Scheduler
- Worker Registry
- Context Orchestration
- Runtime Workspace
- Memory Integration
- Observability

## 应该是 mode-specific adapter 的

- longform chapter provider
- longform review overlay 行为
- roleplay 角色模拟 sidecar
- trpg rule card/state card

## 可选 adapter / 可替换层

- `LongformSpecialistService -> LongformMemoryWorker` adapter。仅当它不污染新 worker 合同时使用；否则按新 executor 重写。
- 当前 `LongformTurnCommandKind` 与新 command surface 的映射。仅作为过渡或前端同步成本优化，不是硬约束。
- 当前 `StorySession.current_state_json` / `builder_snapshot_json` 与正式 store 的桥接

---

## 6. 当前架构的关键落点

1. **不要再把 story runtime 当成 longform service 的增量补丁**
2. **不要新造“能力层”**
3. **不要换 retrieval 框架**
4. **不要让 writer 直接写 memory**
5. **不要让 Runtime Workspace 继续停留在进程内字典**
6. **不要把 branch/rollback 只理解成 LangGraph checkpoint**

---

## 7. 推荐的下一步

在真正进入实现前，应该按模块顺序继续推进：

1. dependency audit 已完成
2. 先确认模块级残余问题
3. 基于本模块拆分做技术调研和伪代码
4. 再冻结第一批实现切片
