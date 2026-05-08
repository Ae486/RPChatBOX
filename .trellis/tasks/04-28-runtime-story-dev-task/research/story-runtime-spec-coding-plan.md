# Story Runtime Spec Coding Plan

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Date: 2026-05-05
>
> Status: spec-first, no code implementation in this document

## 1. Purpose

这份文档不是设计回顾，而是后续真正进入开发时要执行的 `spec coding` 主方案。

目标是把当前已经讨论清楚的口径，整理成一套可以直接拆切片、分配开发、做 check、做回滚的工程方案。

本方案遵守以下硬边界：

- 当前只整理 spec，不改代码。
- task 级讨论结论高于旧设计文档。
- 第一阶段以 longform 可运行落地为主，但底层合同必须面向所有 mode，而不是长文专用硬编码。
- 当前 longform MVP 只作为参考，不作为必须兼容的后端链路、API、SSE、数据模型或用户可见行为约束。
- 若旧实现阻碍新 runtime 合同，允许按新设计重写 runtime；复用必须服务于新合同，而不是让新合同迁就旧实现。
- story runtime 采用“重 workflow，轻 agent”。
- Deterministic Scheduler 掌握执行权；LLM 只负责提出结构化提案。
- worker 先是 Memory OS 和 runtime context 的管理者，其次才是技能载体。

## 2. 本次冻结的最终目标

第一阶段实施完成后，story runtime 应达到下面这个状态：

1. 新 longform runtime 不再只是 `orchestrator -> single specialist -> writer` 的固定链，而是具备真正的：
   - runtime identity
   - runtime profile snapshot
   - worker registry
   - deterministic scheduler
   - worker context packet
   - Runtime Workspace turn material
   - post-write 主链

2. 第一版可以只有一个真实 memory worker，但它必须通过 `WorkerDescriptor / WorkerExecutor / WorkerContextPacket / WorkerResult` 接入新合同。这个 worker 可以复用 `LongformSpecialistService`，也可以按新合同重写；不允许继续以“写死固定 specialist”方式存在。

3. writer 可以在受控边界内自行判断“知识不足”，并调用 retrieval 工具获取卡片、展开卡片、记录使用情况；这些材料先进入 Runtime Workspace，写完后再交由 post-write 调度和 worker 整理。

4. longform 的讨论、修订、重写、接受继续、完成本章，都要纳入统一 runtime 合同，而不是分别走几套临时逻辑。

5. roleplay / trpg 这一阶段不要求完整做完，但 runtime contract、domain registry、worker catalog、packet policy、Runtime Workspace material type 必须已经能表达它们。

## 2.1 第一版最小可运行闭环

第一版 runtime 的最小可运行闭环只证明一条主链：

```text
用户发起一次 longform writing turn
  -> Runtime Identity 创建并绑定 active BranchHead / Turn / RuntimeProfileSnapshot
  -> Context Orchestration 组装 writer packet
  -> WritingWorker 产出用户可见文本
  -> Runtime Workspace 记录 writer input/output、packet refs、token usage、trace
  -> post-write 根据触发条件运行 Scheduler / Worker
  -> Worker 处理本轮材料并产出结构化结果
  -> 优先刷新下一轮 writer 需要的 Core State 当前视图 / projection block views
  -> 下一轮 writer packet 能读取新视图 + 近几轮原文窗口
```

这一闭环的目标不是做完所有 longform 产品行为，而是证明新架构主链成立。第一版必须实现的能力是：

- `StorySession / BranchHead / Turn / RuntimeProfileSnapshot` 作为运行时身份锚点。
- `Worker Registry` 能注册、启用、禁用 worker，Scheduler 不硬编码 worker 名称。
- `Context Orchestration` 能确定性组装 writer packet，包含 Core State 当前视图 / projection block views 与近几轮原文窗口。
- `WritingWorker` 能完成一次正文输出，并能记录 packet / output / token usage。
- `Runtime Workspace` 能持久化本 turn 材料，至少覆盖 writer input/output、packet refs、token usage、post-write trace。
- `Post-write` 能在 writer 输出后进入 Scheduler / Worker 主链，完成一次 worker 分析和下一轮视图刷新。

第一版可以先不完整实现：

- longform 讨论 / brainstorm 的完整 UI 和全部 apply 体验。
- 修订 overlay 的完整产品体验。
- 完整章节生命周期优化和 chapter compact。
- roleplay / TRPG 的完整运行行为。
- 完整分支 UI、物理删除和跨分支 Evolution 管理。
- RP/TRPG 的重树形消息流可视化。第一版只需要 branch 入口和最小 branch 面板，不要求在主聊天流直接渲染复杂树杈。点击 `从这里分支` 后默认立即切到新 branch，主聊天流按当前 active branch 线性重建，fork 点之后旧分支的后续消息从主视图消失；顶部 branch badge、fork 点提示条和 branch 面板 origin 信息作为第一版最小 UX 约束。

但这些未完成能力必须已经能被合同表达，不能用 longform-only 字段或临时 if/else 把主链写死。

## 3. 第一阶段架构总图

```text
StorySession + BranchHead + Turn + RuntimeProfileSnapshot
  -> StoryGraphRunner / Graph Nodes
  -> Deterministic Scheduler
       -> ask Orchestrator Worker for structured plan
       -> validate against worker registry / policy / permission / budget
       -> build WorkerContextPacket
       -> run selected worker executors
  -> Context Orchestration Layer
       -> assemble writer packet from view + recent turns + sidecars + retrieval cards
  -> WritingWorker
       -> optional bounded retrieval loop
       -> produce visible output
  -> Post-write processing
       -> write Runtime Workspace materials / usage / trace
       -> when triggered, run scheduler again for maintenance
       -> worker analyzes turn materials
       -> refresh next-turn Core projection view first
       -> then proposal / apply / recall / archival maintenance
```

### 3.1 关键模块职责

| 模块 | 责任 | 不负责 |
|---|---|---|
| `StorySession / BranchHead / Turn` | 运行时身份、生命周期锚点、版本追溯 | 不负责业务分析 |
| `RuntimeProfileSnapshot` | 冻结本轮 worker/policy/model/permission 配置 | 不直接存草稿配置 |
| `Orchestrator Worker` | 输出结构化调度提案 | 不直接执行 worker，不直接改 memory |
| `Deterministic Scheduler` | 校验提案、选择 worker、决定 phase、降级、跳过、并行/串行 | 不做自由文本理解 |
| `Worker Registry` | 描述 worker、domain 绑定、权限、输入输出合同 | 不承载 workflow 主链 |
| `Context Orchestration Layer` | 确定性组包、裁剪、refs、budget、短编号映射 | 不负责判断是否检索，不做主路径智能决策 |
| `Runtime Workspace` | 暂存当前 turn 材料、检索卡片、review overlay、usage record、worker candidate、trace | 不是 story truth |
| `WritingWorker` | 唯一可见输出；支持 `brainstorm/discussion` 与 `writing/rewrite` 两种 operation mode | 不直接写 Core truth |
| `Post-write processing` | writer 输出后的主维护链，准备下一轮 view，并治理后续沉淀 | 不是可有可无的附属任务 |

## 4. 当前实现到目标实现的迁移判断

## 4.1 可参考 / 可复用 / 可替换的旧实现

- `backend/rp/graphs/story_graph_runner.py`
- `backend/rp/graphs/story_graph_nodes.py`
- `backend/rp/services/story_turn_domain_service.py`
- `backend/rp/services/longform_orchestrator_service.py`
- `backend/rp/services/longform_specialist_service.py`
- `backend/rp/services/writing_packet_builder.py`
- `backend/rp/services/writing_worker_execution_service.py`
- `backend/rp/services/longform_regression_service.py`
- `backend/rp/models/story_runtime.py`
- `backend/rp/models/writing_runtime.py`
- `backend/rp/models/runtime_workspace_material.py`
- `backend/rp/services/runtime_workspace_material_service.py`
- `backend/rp/models/memory_contract_registry.py`
- `backend/rp/services/proposal_apply_service.py`
- `backend/rp/services/proposal_workflow_service.py`

这些部分是第一阶段的主要参考和可复用来源，但不是必须保留的架构承载物。若某段旧 longform MVP 链路阻碍新 runtime 合同，或继续包旧链路的收益低于按新设计重写，可以删除或替换旧链路，以新版本设计链路为准。

旧数据模型也不是硬约束。若旧 `StorySession / ChapterWorkspace / StoryArtifact / StoryDiscussionEntry` 等 longform MVP 结构与新 `Turn / BranchHead / RuntimeProfileSnapshot / Runtime Workspace` 主模型差距较大，或强行兼容会造成硬编码、longform-only、非模块化实现，允许删除或替换旧模型，按当前 runtime 设计重建。实施时只需保留必要的迁移判断、前端入口调整、测试入口调整和回退说明。

旧后端 API / command surface / SSE 字段也不是硬约束。新 runtime 可以当旧链路不存在来设计；前端现有布局、按钮分区和交互入口只作为产品参考。若旧 API 形状或旧状态模型阻碍新 `Turn / Scheduler / Worker / Runtime Workspace` 合同，应优先按新设计重建调用面。

## 4.2 必须重构或扩展的部分

| 当前实现 | 问题 | 目标改法 |
|---|---|---|
| `OrchestratorPlan` 只有 query/focus/instruction | 不能表达真实 worker 调度 | 扩成可校验的 worker plan；若旧 plan adapter 扭曲新合同，应重写 |
| graph 固定调用 `LongformSpecialistService` | 没有 registry/scheduler 概念 | 引入 worker registry + scheduler；旧 specialist 只在不污染新合同时作为 adapter，否则重写 executor |
| writer packet 只吃 projection + hints | 缺少 sidecar/retrieval/review/runtime identity | 扩成正式 writer packet contract |
| `Runtime Workspace` 只算细窄 scratch | 不足以承载 turn material | 扩成 turn material 标准层 |
| `LongformTurnCommandKind` 只覆盖旧 MVP | 不能完整表达讨论/修订/接受继续语义 | 作为产品语义参考；必要时重建新 command surface |
| current story runtime 只有 longform thinking | 底层容易写死成长文专用 | 所有新合同必须经 ModeProfile / registry / snapshot 驱动 |

## 5. 合同清单

本节是实施时必须先冻结的合同 inventory。

## 5.1 身份与配置合同

### 必须存在

- `StorySession`
- `BranchHead`
- `Turn`
- `RuntimeProfileSnapshot`
- `MemoryRuntimeIdentity`

### 现状与目标

| 合同 | 现状 | 目标 |
|---|---|---|
| `StorySession` | 已有 | 保留为 story/session anchor；对外入口可按新 runtime 需要调整 |
| `BranchHead` | 还未正式落到 story runtime 模型 | 第一阶段至少要有内部合同和默认主分支语义 |
| `Turn` | graph 内部隐式存在 | 第一阶段提升为正式 runtime identity 单位 |
| `RuntimeProfileSnapshot` | 只有概念，没有正式 story runtime 合同 | 必须落模型与读取链 |
| `MemoryRuntimeIdentity` | 已有模型 | 作为 runtime / workspace / worker / proposal / trace 统一锚点 |

### 推荐落位

- 扩展 [story_runtime.py](H:/chatboxapp/backend/rp/models/story_runtime.py)
- 复用 [memory_contract_registry.py](H:/chatboxapp/backend/rp/models/memory_contract_registry.py)
- 新增 `story runtime profile` 专用模型文件，避免直接混用 setup agent 的 `RuntimeProfile`

推荐新增文件：

- `backend/rp/models/story_runtime_profile.py`
- `backend/rp/models/story_worker_runtime.py`

## 5.2 worker 合同

第一阶段至少冻结以下模型：

- `WorkerDescriptor`
- `WorkerExecutionPolicy`
- `WorkerExecutionRequest`
- `WorkerExecutionPlan`
- `WorkerContextPacket`
- `WorkerResult`
- `WorkerEvidenceRef`
- `WorkerProposalRef`

### `WorkerDescriptor` 至少包含

- `worker_id`
- `display_name`
- `owned_domains`
- `read_domains`
- `allowed_layers`
- `tool_allowlist`
- `default_execution_policy`
- `supported_phases`
- `permission_profile_ref`
- `provider/model defaults`
- `context_slot_policy`
- `output_schema_version`

### `WorkerExecutionPlan` 至少包含

- `plan_id`
- `phase`
- `worker_id`
- `must_run`
- `allow_degrade`
- `budget_class`
- `context_requirements`
- `reason_codes`
- `scheduler_constraints`

### `WorkerContextPacket` 至少包含

- `identity`
- `worker_id`
- `phase`
- `mode`
- `session refs`
- `recent turn refs`
- `core projection refs`
- `sidecar refs`
- `retrieval refs`
- `forbidden_context`
- `token_budget`
- `packet metadata`

### `WorkerResult` 至少包含

- `worker_id`
- `phase`
- `result_status`
- `writer_hints`
- `projection_refresh_requests`
- `proposal_candidates`
- `recall_candidates`
- `archival_candidates`
- `validation_findings`
- `evidence_refs`
- `trace_summary`

## 5.3 writer packet 合同

`WritingPacket` 需要从“长文 MVP 输入包”升级为“story runtime writer 输入包”。

第一阶段 writer packet 必须明确区分：

- `system sections`
- `core view sections`
- `recent raw turns`
- `mode sidecars`
- `retrieval cards`
- `review overlay`
- `writer contract`
- `operation mode`
- `packet summary metadata`

### writer packet 允许进入的内容

- `Core State` 当前视图
- 近 X 轮 user / writer 原文窗口
- longform 的 review overlay
- longform 的 accepted outline / chapter goal / chapter bridge material
- roleplay 的角色相关 sidecar
- trpg 的 rule card / state card
- retrieval 卡片摘要与展开卡片

### writer packet 禁止进入的内容

- raw authoritative JSON
- raw retrieval hit 原文全集
- Runtime Workspace 日志
- worker 中间推理
- tool call trace
- token usage trace
- proposal/apply 内部日志

### longform 可见版本约束

- longform rewrite 的旧版本不删除，允许用户回看和比较。
- 但续写、post-write 治理、next-turn writer packet、rollback 可见文本恢复，只能认一个显式“确定版本”。
- 底层应保留类似 `selected / canonical draft revision` 的单一引用。
- 对 longform 来说，存在 rewrite 候选版本时，用户必须显式采用某一版；不能通过“点击续写”自动晋升当前页面版本。
- roleplay / TRPG 不采用“同一 Turn 下保留多个可切换候选”的设计。对用户来说，单个 `Turn` 只有当前一版正式可见结果；若用户不满意，应通过显式分支从历史 turn 改写未来，而不是在同一 turn 内保留候选树。
- 因此 RP/TRPG 侧真正重要的不是 chat 样式候选树，而是更重的 story-runtime 可回溯/分支消息树。正式实现必须与 `Turn`、`BranchHead`、memory 可见状态、Runtime Workspace、post-write 状态一起对齐。
- 还应保留一条轻量 `selection receipt`，至少包含：
  - `turn_id`
  - `candidate_output_refs`
  - `selected_output_ref`
  - `selected_at`
  - `selection_source = user_explicit_select`

## 5.3.1 修订模块补充规格

longform 的 review overlay / revision / rewrite 不再只散落在 PRD 段落中，后续实现应以：

- [story-runtime-revision-overlay-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-revision-overlay-spec.md)
- [story-runtime-revision-overlay-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-revision-overlay-development-spec.md)

作为专门补充规格。

其中 `story-runtime-revision-overlay-spec.md` 负责需求语义，`story-runtime-revision-overlay-development-spec.md` 负责可派发实现合同。

需求语义规格负责：

- `viewing / editing / suggesting` 三态
- review overlay / comment / tracked change 的 runtime 语义
- `full rewrite / paragraph rewrite` 的输入输出合同
- SuperDoc adapter 与 runtime boundary
- selection receipt / adoption receipt / comment lifecycle

开发规格负责：

- draft materialization / block anchor contract
- backend DTO / service signatures
- rewrite request / paragraph patch contract
- selection / adoption validation matrix
- implementation slices `R1-R6`
- backend / frontend / integration tests required

实现时约束：

- 不重复定义 `WritingPacket / PacketSection / Turn / RuntimeWorkspaceMaterial` 的 canonical 字段
- 只在修订模块 spec 中定义修订特有 sidecar、rewrite packet shape、comment lifecycle 和 adoption 规则
- SuperDoc 只作为 document/revision substrate；runtime truth 仍由 `Turn / Runtime Workspace / adoption receipt` 持有

## 5.4 Runtime Workspace 材料合同

当前 [runtime_workspace_material.py](H:/chatboxapp/backend/rp/models/runtime_workspace_material.py) 已有不错的基础，第一阶段直接沿用并扩展。

必须正式承载的材料类型：

- `WRITER_INPUT_REF`
- `WRITER_OUTPUT_REF`
- `RETRIEVAL_CARD`
- `RETRIEVAL_EXPANDED_CHUNK`
- `RETRIEVAL_MISS`
- `RETRIEVAL_USAGE_RECORD`
- `RULE_CARD`
- `RULE_STATE_CARD`
- `REVIEW_OVERLAY`
- `WORKER_CANDIDATE`
- `WORKER_EVIDENCE_BUNDLE`
- `POST_WRITE_TRACE`
- `PACKET_REF`
- `TOKEN_USAGE_METADATA`

第一阶段必须打通：

- material record
- short id 映射
- lifecycle update
- identity-scoped list/read
- trace event emission
- writer retrieval usage hook

## 5.5 Turn Lifecycle And Post-write Status Contract

第一版必须把 `Turn` 和 post-write 的状态收成显式合同，不能只散落在 graph state 或局部 service 里。

### `Turn` 最小状态

- `received`
- `packet_built`
- `writer_running`
- `writer_completed`
- `post_write_pending`
- `post_write_running`
- `post_write_deferred`
- `settled`
- `failed`

### `Turn` 轻量终态解释字段

第一版建议在 `StoryTurnRecord` 上增加两个轻量字段：

- `settlement_reason`
- `failure_reason`

约束：

- `settlement_reason` 只在 `status = settled` 时填写。
- `failure_reason` 只在 `status = failed` 时填写。
- 二者都不是自由文本主字段，应优先使用稳定枚举值；必要细节进入 `metadata_json` 或关联 trace/job/error 记录。
- 不把成功和失败混进一个 `completion_reason` 字段，避免状态机语义混乱。

### 建议最小枚举

`settlement_reason`

- `all_required_jobs_completed`
- `required_jobs_deferred_by_policy`
- `user_override_continue`
- `system_recovered_after_retry`

`failure_reason`

- `writer_generation_failed`
- `worker_schema_validation_failed`
- `required_post_write_job_failed`
- `projection_refresh_failed`
- `runtime_workspace_persist_failed`
- `storage_persist_failed`
- `manual_intervention_required`

### 语义

- `writer_completed`：writer 已产出本轮用户可见文本，前台可以返回。
- `post_write_pending`：writer 已完成，但本轮仍有必需 post-write 尚未开始或尚未完成。
- `post_write_running`：Scheduler / Worker 正在处理本轮材料。
- `post_write_deferred`：本轮允许把完整 post-write 延后，但该状态只作为短暂中间态存在；若该 turn 最终可以成为正式回退点，必须推进到 `settled`，并通过 `settlement_reason = required_jobs_deferred_by_policy` 表达。
- `settled`：该 turn 的 acceptance 条件满足，且该 turn 的必需 post-write 已完成、被跳过，或其必需 jobs 被 policy 合法标记为 `deferred`。
- `failed`：writer 或必需 post-write 失败，不能被当作 settled truth 使用。

### 下一轮 gating 规则

- 新 turn 创建前，系统必须读取上一轮 `Turn` 状态和相关 Runtime Workspace / trace。
- 若上一轮已 `settled`，直接进入下一轮。
- 若上一轮处于 `post_write_pending` 或 `post_write_running`，系统必须根据 mode policy 和本轮请求决定：等待、提示 pending，或在允许时使用上一版稳定视图 + 近几轮原文窗口继续。
- 若上一轮处于 `failed`，系统不能静默当作已整理完成，必须走 repair、retry、rewrite 或显式用户决策。

### 分支 / 回退约束

- `branch/fork` 只允许从 `settled` turn 派生。
- `fork created`、`branch switched`、`branch deleted` 属于 branch control actions，不创建新的 `Turn`，只写 branch/control receipts 与必要 trace。
- `post_write_pending`、`post_write_running`、`post_write_deferred` 状态都必须能通过 `StorySession / BranchHead / Turn` 精确追溯。
- 分支切换时，不携带其他分支未 settled 的 Runtime Workspace / worker candidate / pending 结果。

## 5.6 Rollback Anchor Contract

第一版必须冻结统一回溯锚点：**回退只认 `Turn`，不认各层各自的独立版本号。**

### 合同

- 当前主线上的回退目标是某个 `BranchHead` 下的目标 `Turn`。
- `Turn` 是产品语义上的统一回溯锚点。
- `Core State revision`、`projection block view revision`、`Recall / Archival materialization revision`、writer output revision、Runtime Workspace material lifecycle 都是附属于该 `Turn` 的内部版本，不单独作为用户可选的回退锚点。

### 回退语义

- 回退到 `Turn N` 时，应恢复 `Turn N` 完成后的最终可见状态。
- 同一 `Turn` 内如果发生多次 memory 更新、视图刷新、用户手动 `Core State` 修改，回退时取该 `Turn` 内最终有效的一版，而不是中间某个半完成版本。
- `Turn N+1` 及之后产生的 writer 输出、Runtime Workspace 材料、Core State 更新、Recall materialization、packet/window metadata 都对当前主线隐藏 / 失效。
- 如果之后要保留 `Turn N+1` 的未来，那属于 `branch/fork`，不是 rollback。

### 例子

```text
Turn 1
  -> user + writer 完成一轮

Turn 2
  -> user + writer 完成一轮
  -> post-write 调度完成
  -> Core State 更新一版
  -> 用户手动修改 Core State 一版

Turn 3
  -> user + writer 完成一轮
  -> writer 发起 retrieval
  -> post-write 调度完成
  -> Core State 再更新一版
```

此时：

- 回退到 `Turn 2`，应恢复到“Turn 2 完成后的最终状态”，包含该轮用户手动修改后的 `Core State`。
- 回退到 `Turn 1`，应恢复到“Turn 1 完成后的最终状态”。
- `Turn 3` 的所有内容都不再对当前主线可见。

### 对实现的约束

- `StoryTurnRecord` 必须能作为其他版本化对象的统一归属锚点。
- 各类 revision / materialization / packet metadata 必须能回答：“它最终属于哪个 Turn 的完成状态？”
- 回退恢复逻辑应优先依据 `Turn` 解析可见状态，而不是要求每一层各自独立选择回退版本。

## 5.7 Turn-scoped Workflow Job Ledger

第一版需要一个明确的后台任务账本，用来判断“某个 Turn 是否已经完全完成，可以作为正式回退点”。

### 核心口径

- 每个属于某一可视对话轮次后处理链的后台任务，都必须带 `turn_id`。
- 这些任务不是独立的产品回退锚点，它们只是“归属于某个 Turn 的后台工作项”。
- 当某个 `Turn` 下所有**必需完成**的后台任务都达到终态后，该 `Turn` 才能被标记为“该轮完全完成”。
- 如果某些任务被 mode policy 明确允许延后，则这些任务需要被标记为 `deferred`，并且该状态必须进入 turn 完成判定。

### 推荐模型

建议显式引入一类持久化记录，例如：

- `RuntimeWorkflowJobRecord`

最小字段建议：

- `job_id`
- `story_id`
- `session_id`
- `branch_head_id`
- `turn_id`
- `runtime_profile_snapshot_id`
- `job_kind`
- `status`
- `required_for_turn_completion`
- `attempt_count`
- `idempotency_key`
- `started_at`
- `completed_at`
- `last_error`
- `result_refs_json`
- `metadata_json`
- `completion_reason`
- `failure_reason`

### `job_kind` 全局口径

第一版不要只定义最小集合，必须先冻结全局分类。推荐按职责分四类：

1. `turn-finalization jobs`
   直接决定某个可视对话轮次是否已经达到“该轮完全完成”的后台任务。

2. `state-governance jobs`
   负责把本轮材料治理进 `Core State` / 当前视图 / proposal / apply 的后台任务。

3. `memory-materialization jobs`
   负责把本轮材料沉淀到 `Recall Memory` / `Archival Knowledge` 或触发对应再处理的后台任务。

4. `maintenance-and-repair jobs`
   负责 repair、retry、rebuild、cleanup、reindex、supplementary refresh 的后台任务。

### 推荐全局 `job_kind` 候选集合

- `required_post_write_analysis`
- `projection_refresh`
- `proposal_submit`
- `proposal_apply`
- `retrieval_usage_persist`
- `runtime_workspace_finalize`
- `recall_materialization`
- `archival_materialization`
- `archival_reindex`
- `repair_retry`
- `repair_recompute`
- `cleanup_expire_workspace`
- `cleanup_invalidate_candidates`

这些是**全局候选集合**，不是第一版必须全部实现。

### 推荐状态

- `pending`
- `running`
- `completed`
- `failed`
- `cancelled`
- `deferred`

### Job 轻量解释字段

- `completion_reason` 只在 `status = completed / deferred / cancelled` 等终态时填写。
- `failure_reason` 只在 `status = failed` 时填写。
- reason 字段保持轻量、枚举化、稳定，不承载大段报错文本；详细错误进入 `last_error` 和关联 trace。

### 失败恢复与职责分层

第一版必须区分两类失败：

1. `deterministic failure`
   代码逻辑、存储、约束校验、持久化、状态机推进失败。

2. `LLM / worker failure`
   结构化输出不合法、tool/use 失败、worker 产出无法通过校验、需要补跑或轻量自恢复的失败。

### 恢复原则

- 若 writer 文本已经成功返回给用户，则该文本不自动撤回。
- 但只要必需 post-write 失败，该 `Turn` 就不能进入 `settled`。
- 下一轮必须经过显式 gating，不能静默当作该轮已经整理完成。
- 前台必须有错误提示；后台必须支持 `retry`、`repair`、必要时的 worker 轻量自恢复。

### 建议恢复路径

- `deterministic failure`
  - 优先记录失败 job 和错误原因。
  - 不做复杂自愈；由 retry、人工修复或明确用户决策恢复。

- `LLM / worker failure`
  - 允许走轻量 `repair` / bounded retry。
  - worker 可参考 setup agent 的思路，对结构化输出错误、缺字段、轻量 schema 偏差做一次受控自恢复。
  - 超过受控次数后，进入 `failed` 并要求 user decision / rewrite / later retry。

### mode-specific gating

- `longform`
  - 默认更严格。writer 文本可保留，但下一轮正文写作默认等待 repair/retry 成功，或由用户显式决定继续 / 重写。

- `roleplay`
  - 可在 failure 被显式标记的前提下继续，优先使用上一版稳定视图 + 近几轮原文窗口。

- `trpg`
  - 若失败涉及规则判定、数值结算、状态推进，默认不能静默继续。

### 第一版最小实现集合

在全局口径冻结后，第一版最小实现建议只要求以下 `job_kind` 真正落地：

- `required_post_write_analysis`
- `projection_refresh`
- `retrieval_usage_persist`
- `runtime_workspace_finalize`

第一版可以先不要求完整实现、但必须预留合同的 `job_kind`：

- `proposal_submit`
- `proposal_apply`
- `recall_materialization`
- `archival_materialization`
- `archival_reindex`
- `repair_retry`
- `repair_recompute`
- `cleanup_expire_workspace`
- `cleanup_invalidate_candidates`

### 创建时 obligation 与后置派发

job ledger 不应把所有 job 都在 turn 创建时一次性建好。第一版冻结为两层：

1. `creation-time obligations`
   在该可视对话轮次一旦成立、且 writer 文本一旦允许返回时，就必须与 `Turn` 同事务登记的最小后台责任。

2. `derived jobs`
   在 post-write 分析结果出来后，根据真实需要再派发的后台任务。

### 第一版 creation-time obligations

建议至少包括：

- `required_post_write_analysis`
- `runtime_workspace_finalize`

理由：

- 它们代表“这一轮已经产生，且一定存在的后台责任”。
- 即使 writer 文本已经返回后服务立刻崩溃，系统重启后也必须知道该 `Turn` 仍有后处理未完成。
- 这两类 obligation 不依赖后续分析结果才能知道自己是否存在。
- 第一阶段要冻结唯一 owner：由 turn-domain finalize 边界（例如 `StoryTurnDomainService.finalize_writer_output(...)`）与 writer output / usage metadata / turn 状态推进一起同事务登记；`run_post_write()` 只负责幂等校验或补齐，不应成为首次创建 owner。

### 第一版 derived jobs

建议默认作为后置派发：

- `projection_refresh`
- `proposal_submit`
- `proposal_apply`
- `recall_materialization`
- `archival_materialization`
- `archival_reindex`
- `repair_retry`
- `repair_recompute`
- `cleanup_expire_workspace`
- `cleanup_invalidate_candidates`

理由：

- 这些 job 往往依赖 post-write 分析结果，或并非每轮都需要。
- 若在 turn 创建时全部预建，会制造大量实际上不会运行的空任务，增加恢复和判定噪音。

### Turn 完成判定

- `StoryTurnRecord` 是否可被标记为“该轮完全完成”，不直接看某个单独 service 是否跑完。
- 应由一个确定性判定逻辑读取该 `turn_id` 下所有 job：
  - 所有 `required_for_turn_completion = true` 的 job 都为 `completed`
  - 或被 mode policy 允许进入 `deferred`
  - 且没有 `failed` 的必需 job 未被 repair / retry / user decision 处理
- 只有满足以上条件，`Turn` 才能进入正式可回退状态。

### 工程约束

- job ledger 是 **durable workflow/job ledger**，不是数据库底层 WAL/binlog 的替代品。
- job ledger 负责失败重试、恢复、补跑、可观察性和 turn 完成判定。
- `MemoryChangeEvent`、proposal/apply receipts、Runtime Workspace materials、projection refresh 结果等，作为 job 的结果引用或副产物存在，而不是反过来替代 job ledger。
- 第一版如果未来发现某个 `job_kind` 不应阻塞“该轮完全完成”，应调整 `required_for_turn_completion` 和 mode policy，而不是删除全局 `job_kind` 口径。
- `Turn` 创建事务中至少要持久化最小 `creation-time obligations`；系统不能在 writer 文本已返回后，仍依赖内存态去记住“这轮还有哪些后处理责任”。

## 6. 模块级实施方案

## 6.1 Slice A: Runtime Identity + Profile Snapshot

### 目标

把“session 入口 + 隐式 turn”升级成真正可追溯的 runtime identity。

### 交付

- story runtime 正式引入 `BranchHead` / `Turn` / `RuntimeProfileSnapshot`
- 每轮执行前分配或解析 `MemoryRuntimeIdentity`
- graph / worker / workspace / proposal / trace 全链带 identity
- `RuntimeProfileSnapshot` 支持 turn-start pin

### 主要改动文件

- [backend/rp/models/story_runtime.py](H:/chatboxapp/backend/rp/models/story_runtime.py)
- `backend/rp/models/story_runtime_profile.py`（新增）
- [backend/rp/models/memory_contract_registry.py](H:/chatboxapp/backend/rp/models/memory_contract_registry.py)
- [backend/rp/graphs/story_graph_runner.py](H:/chatboxapp/backend/rp/graphs/story_graph_runner.py)
- [backend/rp/graphs/story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py)
- [backend/rp/services/story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py)

### 测试

- identity 在单轮执行中固定
- runtime panel 热更新不影响进行中的 turn
- proposal / workspace / trace 都拿到相同 identity

## 6.2 Slice B: Worker Registry + Scheduler Skeleton

### 目标

把“固定 specialist 调用链”升级成“可注册 worker + 确定性调度”。

### 交付

- worker registry
- `OrchestratorWorker -> structured plan`
- scheduler validate / select / degrade / dispatch
- registered `LongformMemoryWorker` executor。它可以复用 `LongformSpecialistService` adapter，也可以按新合同重写。

### 主要改动文件

- `backend/rp/models/story_worker_runtime.py`（新增）
- `backend/rp/services/story_worker_registry_service.py`（新增）
- `backend/rp/services/story_runtime_scheduler_service.py`（新增）
- [backend/rp/services/longform_orchestrator_service.py](H:/chatboxapp/backend/rp/services/longform_orchestrator_service.py)
- [backend/rp/services/longform_specialist_service.py](H:/chatboxapp/backend/rp/services/longform_specialist_service.py)
- [backend/rp/services/story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py)
- [backend/rp/graphs/story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py)

### 第一阶段 worker bootstrap set

- `LongformMemoryWorker`
- `WritingWorker`
- 预留但不强制实现：
  - `CharacterMemoryWorker`
  - `SceneInteractionWorker`
  - `RuleStateWorker`
  - `MaintenanceWorker`

### 测试

- registry 可启停 worker 而不改 scheduler 主逻辑
- scheduler 对非法 worker plan 会拒绝或降级
- registered `LongformMemoryWorker` 能跑通；其 executor 可来自旧 specialist adapter，也可来自新实现

## 6.3 Slice C: Context Orchestration Layer + WorkerContextPacket

### 目标

把散落在 orchestrator/specialist/builder 内部的上下文拼接，收拢成确定性上下文编排层。

### 交付

- `WorkerContextPacketBuilder`
- writer packet slot policy
- retrieval card 短编号映射
- context budget / trim policy
- forbidden context policy

### 主要改动文件

- `backend/rp/services/worker_context_packet_builder.py`（新增）
- `backend/rp/services/story_writer_packet_policy_service.py`（新增）
- [backend/rp/services/writing_packet_builder.py](H:/chatboxapp/backend/rp/services/writing_packet_builder.py)
- [backend/rp/services/story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py)

### 测试

- writer packet 不泄露 raw retrieval / raw truth / logs
- recent raw turns 与 core view 同时存在
- 不同 mode 下 sidecar slot 可插拔

## 6.4 Slice D: Runtime Workspace Turn Material

### 目标

让 Runtime Workspace 真正成为 turn material store，而不是狭窄 scratch。

### 交付

- retrieval cards / expanded chunks / usage records
- review overlay
- worker candidates / evidence bundles
- brainstorm summary apply receipts
- packet refs / token usage
- lifecycle 管理和 trace 事件

### 主要改动文件

- [backend/rp/models/runtime_workspace_material.py](H:/chatboxapp/backend/rp/models/runtime_workspace_material.py)
- [backend/rp/services/runtime_workspace_material_service.py](H:/chatboxapp/backend/rp/services/runtime_workspace_material_service.py)
- `backend/rp/services/story_runtime_workspace_facade.py`（新增）

### 测试

- short id 冲突校验
- lifecycle 更新
- branch/turn identity 隔离
- usage hook 必写

## 6.4.1 Unified Trace And Audit Spine

第一版不应把“日志/留痕”分散成各模块各写一套，也不应把 eval 变成主留痕模块。成熟做法应是：

- **统一基础设施，分散产出语义**
  - 各功能模块继续拥有自己的业务语义和状态推进权。
  - 但所有留痕都通过统一的持久化合同和仓储层落到同一片 runtime trace/audit 区域。

- **eval 只消费，不拥有**
  - eval 模块读取这些记录做分析、评分、诊断。
  - eval 不应成为业务模块写日志的入口，也不应反向定义业务主记录。

### 推荐统一留痕对象

第一版建议统一在 runtime trace/audit 范围内管理下列对象：

- `StoryTurnRecord`
- `RuntimeWorkflowJobRecord`
- `RuntimeWorkspaceMaterialRecord`
- `MemoryChangeEventRecord`
- proposal/apply receipts
- read manifest / packet summary
- brainstorm summary apply receipt

### `Turn` 主锚点约束

- `StoryTurnRecord` 是唯一的主锚点。
- 下列对象都不再长成平行主记录系统，而应作为 `Turn` 的子材料或关联记录存在：
  - `review overlay`
  - `brainstorm change summary`
  - `brainstorm summary apply receipt`
  - rewrite 候选版本与确定版本选择结果
  - retrieval cards / expanded chunks / usage
  - worker trace / evidence bundle
  - proposal/apply receipts
- 也就是说，业务上允许这些对象有各自的表或记录类型，但它们的数据归属、查询入口、回退语义和 debug/eval 追溯都继续从 `Turn` 出发，而不是形成多套平行时间线。

### 轻量统一引用规范

成熟工程里，不应让各模块随意在 `metadata_json` 里拼接关系字符串，也不必一上来引入重型 tracing 平台。第一版建议冻结一套轻量统一引用规范：

- 每类主记录保留自己的主键：
  - `turn_id`
  - `job_id`
  - `material_id`
  - `event_id`
  - `proposal_id`
  - `apply_id`
  - `summary_item_id`

- 再统一补少量标准关联字段：
  - `turn_id`
  - `job_id`
  - `parent_job_id`
  - `source_ref_ids`
  - `result_ref_ids`
  - `trace_refs`

- `trace_refs` 应使用稳定结构，而不是自由文本。建议统一前缀式 ref：
  - `turn:<id>`
  - `job:<id>`
  - `material:<id>`
  - `event:<id>`
  - `proposal:<id>`
  - `apply:<id>`
  - `summary_item:<id>`

### 约束

- 业务主关系优先使用显式字段，不依赖 `metadata_json` 猜。
- `metadata_json` 只承载补充细节，不承担主关联职责。
- debug/eval/recovery 查询面优先依赖这些统一关联字段和 `trace_refs`。
- 这套规范的目标是稳定追溯，不是实现完整分布式 tracing 平台。

### 基础设施边界

- 不让 `eval` 成为统一日志主模块。
- 不做一个“超大日志模块”统一理解所有业务语义。
- 做一个共享的 `trace/audit` 基础设施层：统一 DTO、统一 repository、统一 identity、统一 reason/status 字段、统一查询面。
- 各功能模块继续拥有自己的业务语义和状态推进权，只负责把自己的留痕写入这套基础设施。
- debug 页面与 eval 都从这套统一区域读取；`eval` 只消费，不拥有业务主记录。

### 产出原则

- `Turn` 负责可视对话轮次锚点。
- job ledger 负责后台任务状态、retry/repair/recovery。
- Runtime Workspace 负责当前轮临时材料和工具使用留痕。
- MemoryChangeEvent 负责 memory 变化、dirty target、trace。
- proposal/apply receipt 负责受治理写入证明。
- brainstorm apply receipt 负责“哪条讨论结果最终作用到了哪些 block”。

### 工程建议

- 不做一个“超大日志模块”统一理解所有业务语义。
- 做一个共享 `trace/audit` 基础设施层：统一 DTO、统一 repository、统一 id/identity、统一 reason/status 字段、统一查询面。
- 各功能模块自行产出到这套基础设施中。
- debug 页面与 eval 都从这套统一区域读取，而不是各模块各拼一份读模型。

## 6.5 Slice E: Longform Action Surface And Writing Modes

### 目标

把 longform 的讨论、修订、重写、接受继续、完成本章，整理进统一 runtime 面。

### 交付

- `WritingWorker` operation mode：
  - `brainstorm/discussion`
  - `writing/rewrite`
- output area action 口径冻结为：
  - `重写`
  - `接受并继续`
  - `完成本章`
- discussion area 输入触发 brainstorm
- review overlay 作为 sidecar 进入 rewrite packet

### 旧入口参考策略

旧后端命令枚举可以作为产品动作参考，但不是硬约束。若保留旧入口能降低前端同步成本，允许做薄 adapter；若旧命令面阻碍新 runtime 合同，应按新 command surface 重建。

| 产品动作 | 第一阶段可参考旧命令 |
|---|---|
| 讨论/头脑风暴 | `DISCUSS_OUTLINE` 可作为语义参考；新实现可改为通用 `brainstorm/discussion` command |
| 重写当前段 | `REWRITE_PENDING_SEGMENT` |
| 接受并继续 | `ACCEPT_PENDING_SEGMENT` |
| 完成本章 | `COMPLETE_CHAPTER` |

### 主要改动文件

- [backend/rp/models/story_runtime.py](H:/chatboxapp/backend/rp/models/story_runtime.py)
- [backend/rp/services/story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py)
- [backend/rp/services/writing_packet_builder.py](H:/chatboxapp/backend/rp/services/writing_packet_builder.py)
- [backend/rp/services/writing_worker_execution_service.py](H:/chatboxapp/backend/rp/services/writing_worker_execution_service.py)

### 测试

- brainstorm 不直接改 block
- summary 支持编辑/拒绝/批量 apply
- 未 apply 而继续写作时 stale
- `ACCEPT_PENDING_SEGMENT` 与 `COMPLETE_CHAPTER` 语义分离

## 6.6 Slice F: Writer-Side Retrieval

### 目标

实现已确认口径：writer 自己判断是否缺信息，并通过受控 retrieval 工具拿卡片，不新增主路径写前预检层。

### 交付

- bounded retrieval loop
- retrieval card summary first
- expand chosen card on demand
- required usage hook before final output
- retrieval results first land in Runtime Workspace

### 推荐实现

不要把整个 setup agent loop 搬过来。第一阶段更合理的是：

1. `WritingWorkerExecutionService` 外挂一个窄工具循环；
2. 只开放 retrieval 相关工具；
3. 限定 attempt 次数；
4. 每次调用工具都写 Runtime Workspace；
5. writer 最终提交前必须写 usage record。

### 主要改动文件

- [backend/rp/services/writing_worker_execution_service.py](H:/chatboxapp/backend/rp/services/writing_worker_execution_service.py)
- `backend/rp/services/writing_worker_retrieval_loop_service.py`（新增）
- `backend/rp/services/runtime_retrieval_card_service.py`（新增）
- [backend/rp/services/runtime_workspace_material_service.py](H:/chatboxapp/backend/rp/services/runtime_workspace_material_service.py)

### 测试

- writer 可发起检索并拿到稳定短编号卡片
- expand 只对已返回卡片生效
- miss 有记录
- final output 前没有 usage hook 会失败

## 6.7 Slice G: Post-write 主链

### 目标

把 post-write 从“回归维护附属逻辑”升级成 runtime 主链的一部分。

### 交付

- writer output 后最小 turn material 必写
- 满足条件时进入完整 post-write 调度
- worker 完整分析后，优先递交下一轮可见的 core projection view
- 然后再做 proposal / apply / recall / archival maintenance

### 前台返回与后台执行

第一版冻结为：

- writer 产出用户可见文本后，前台响应可以先返回，不要求无条件等待完整 post-write 完成。
- post-write 作为后台主链继续执行，负责记录最小 turn material、运行 Scheduler / Worker、刷新下一轮视图、以及后续 proposal / recall / archival 治理。
- 如果用户下一轮输入到来时，上一轮仍有未完成的必需刷新，则系统必须按 `pending` / `pending-deferred` / `settled` 规则决定：等待、提示 pending，或在允许的情况下先使用上一版稳定视图加近几轮原文窗口继续。
- 不能出现后台长期未完成但前台无限盲写的情况；必需 post-write 状态必须进入 Runtime Workspace / trace，并参与下一轮 gating。

### 触发条件

- 每 N 轮完整调度
- 本轮有 retrieval 行为
- 用户编辑了 core
- rule card / state card 出现
- scene switch / chapter transition
- manual refresh
- dirty block / pending threshold

### 主要改动文件

- [backend/rp/graphs/story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py)
- [backend/rp/services/story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py)
- [backend/rp/services/longform_regression_service.py](H:/chatboxapp/backend/rp/services/longform_regression_service.py)
- `backend/rp/services/post_write_scheduler_service.py`（新增）
- `backend/rp/services/projection_refresh_dispatch_service.py`（新增）

### 测试

- 不做完整调度时，最小 turn material 仍会保留
- retrieval-triggered turn 会触发完整 post-write
- projection view 先于重沉淀结果可用
- writer 文本可先返回，但未完成的必需 post-write 会在下一轮形成 gating 或 pending 提示

## 6.8 Slice H: Longform Chapter Lifecycle

### 目标

把 longform 章节运行流程收拢成可替换 provider 的稳定骨架。

### 冻结流程

```text
章节开始
  -> 章节目标 / accepted outline / chapter bridge material
  -> 用户讨论或确认
  -> 写作 / 重写
  -> 接受并继续 或 完成本章
  -> 若完成本章，进入下一章准备
```

### 本章到下一章

第一阶段默认 provider 只返回：

- accepted outline
- chapter goal

后续如果 eval 差，再新增 `compact / chapter-bridge provider`，替换 provider，而不是改主流程。

### 主要改动文件

- [backend/rp/models/story_runtime.py](H:/chatboxapp/backend/rp/models/story_runtime.py)
- [backend/rp/services/story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py)
- `backend/rp/services/chapter_bridge_provider.py`（新增）

## 6.9 Slice I: Roleplay / TRPG Extension Slots

### 目标

先把扩展位做对，不在第一阶段硬做完整功能。

### 必须预留

- roleplay:
  - `CharacterMemoryWorker`
  - `SceneInteractionWorker`
  - 角色相关 sidecar
- trpg:
  - `RuleStateWorker`
  - `RULE_CARD`
  - `RULE_STATE_CARD`

### 不在第一阶段完成

- 完整 roleplay 角色模拟流程
- 完整 trpg 规则系统
- UI 全量配置页

## 6.10 Slice J: LangGraph Branch / Rollback Preflight

### 目标

不是直接上分支功能，而是先验证当前项目接法下到底能做多少。

### 必须调研的点

- checkpoint
- replay
- fork
- 从旧 checkpoint 继续
- graph state 与外部 memory/text/workspace 同步
- branch switch 是否能与外部 store identity 对齐

### 产物

- 可行 / 不可行矩阵
- 第一阶段支持边界
- 暂缓项列表

### 后续能力验证要求

如果 J 的下一步进入 `GraphCheckpointPointer capture / binding` 实现，测试必须证明 branch / rollback 能力成立，而不是只验证字段存在：

- settled turn 自动绑定 branch-scoped LangGraph checkpoint pointer，并与 `Turn / BranchHead / RuntimeProfileSnapshot` identity 一致。
- rollback receipt 自动携带目标 checkpoint binding；目标缺少 binding 时，receipt 写入稳定缺失原因。
- branch create / switch 只写 control receipt / trace，不创建新的 story turn。
- rollback 后，later turns、Runtime Workspace materials、pending jobs、packet/window metadata、branch-visible reads 不再污染当前主线。
- LangGraph debug / replay / fork 只能作为技术壳验证，不能替代 RP 应用层 story truth、branch visibility、workspace lifecycle 和 Memory OS truth。
- 同一 settled turn 的 checkpoint binding 一次捕获后必须幂等，不能被后续 replay/fork/debug checkpoint 覆盖。

## 7. 文件级改动清单

## 7.1 必改旧文件

- [backend/rp/models/story_runtime.py](H:/chatboxapp/backend/rp/models/story_runtime.py)
- [backend/rp/models/writing_runtime.py](H:/chatboxapp/backend/rp/models/writing_runtime.py)
- [backend/rp/models/runtime_workspace_material.py](H:/chatboxapp/backend/rp/models/runtime_workspace_material.py)
- [backend/rp/graphs/story_graph_runner.py](H:/chatboxapp/backend/rp/graphs/story_graph_runner.py)
- [backend/rp/graphs/story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py)
- [backend/rp/services/story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py)
- [backend/rp/services/longform_orchestrator_service.py](H:/chatboxapp/backend/rp/services/longform_orchestrator_service.py)
- [backend/rp/services/longform_specialist_service.py](H:/chatboxapp/backend/rp/services/longform_specialist_service.py)
- [backend/rp/services/writing_packet_builder.py](H:/chatboxapp/backend/rp/services/writing_packet_builder.py)
- [backend/rp/services/writing_worker_execution_service.py](H:/chatboxapp/backend/rp/services/writing_worker_execution_service.py)
- [backend/rp/services/runtime_workspace_material_service.py](H:/chatboxapp/backend/rp/services/runtime_workspace_material_service.py)
- [backend/rp/services/longform_regression_service.py](H:/chatboxapp/backend/rp/services/longform_regression_service.py)

## 7.2 推荐新增文件

- `backend/rp/models/story_runtime_profile.py`
- `backend/rp/models/story_worker_runtime.py`
- `backend/rp/services/story_worker_registry_service.py`
- `backend/rp/services/story_runtime_scheduler_service.py`
- `backend/rp/services/worker_context_packet_builder.py`
- `backend/rp/services/story_writer_packet_policy_service.py`
- `backend/rp/services/story_runtime_workspace_facade.py`
- `backend/rp/services/writing_worker_retrieval_loop_service.py`
- `backend/rp/services/runtime_retrieval_card_service.py`
- `backend/rp/services/post_write_scheduler_service.py`
- `backend/rp/services/projection_refresh_dispatch_service.py`
- `backend/rp/services/chapter_bridge_provider.py`

### 命名原则

新增文件命名要遵守：

- contract 与 executor 分开
- registry 与 runtime workflow 分开
- policy 与 service 分开
- longform adapter / mode-specific runtime 与 generic runtime 分开

不要再把所有逻辑塞回 `story_turn_domain_service.py`。

## 8. 测试与验收方案

## 8.1 合同测试

- worker registry contract tests
- scheduler validate tests
- writer packet boundary tests
- runtime workspace material contract tests
- runtime profile snapshot pinning tests

## 8.2 运行链路测试

- longform outline generate
- longform rewrite pending segment
- longform accept and continue
- longform complete chapter
- brainstorm -> summary -> apply -> next writing
- writer retrieval -> usage hook -> post-write trigger

## 8.3 Memory 治理测试

- proposal/apply governed write
- user edit 优先于 worker candidate
- projection refresh source refs
- retrieval evidence 不自动变 truth

## 8.4 回退/扩展防退化测试

- disable/add worker without scheduler hardcode change
- mode profile switch does not rewrite old session rules
- roleplay/trpg sidecar slot can be mounted without rewriting writer core

## 9. 迁移 / 重写策略

## 9.1 总体策略

采用 `runtime-first rebuild with selective reuse`。

这不是“必须推倒重写”，也不是“必须兼容旧链路”。判断标准只有一个：是否服务于新 runtime 合同。

- 如果旧实现能低成本复用，且不会污染 `Turn / Snapshot / Worker / Runtime Workspace / post-write` 主链，可以通过 adapter 接入。
- 如果旧实现把新 runtime 绑回 longform-only、固定链路、旧 API / SSE、旧数据模型或硬编码状态机，应删除或替换。
- 前端现有布局、按钮分区、产出区 / 讨论区交互可以作为产品参考；旧后端调用面不是硬约束。

### 顺序冻结

1. 先上 identity/profile/worker/scheduler/context contracts。
2. 建立第一版 longform writing turn 最小闭环。
3. 将可复用的旧 specialist / packet builder / writer gateway 通过 adapter 接入；如果 adapter 变复杂，改为按新合同重写。
4. 接 writer-side retrieval 和 Runtime Workspace usage record。
5. 做 post-write 主链完整化。
6. 再做 longform discussion/review/rewrite/chapter lifecycle 完整收口。
7. 最后再看 roleplay/trpg 扩展位和 LangGraph 分支预研结果。

## 9.2 回滚策略

每个 slice 都必须允许单独回退：

- contract-only slice: 可以只落 DTO / service boundary / fake executor，不影响产品入口。
- scheduler slice: 可以退回到 single registered worker，而不是退回旧固定链。
- retrieval slice: 可以关闭 writer retrieval loop，保留无检索写作路径。
- post-write slice: 可以降级为只记录 turn material + pending 标记，暂停长期沉淀。
- 如果旧链路已被删除，回滚策略不要求恢复旧实现；只要求新 runtime slice 能回退到上一版稳定合同。

## 10. 非目标

第一阶段明确不做：

- 完整 roleplay runtime
- 完整 trpg runtime
- 完整分支 UI
- 物理 purge 全功能
- eval runner
- retrieval core 重写
- Memory OS 全量重构
- 把 setup agent runtime 整套复制到 story runtime

## 11. 已冻结实施口径

- 旧 command / API / SSE 不必须兼容。它们可作为产品语义参考，但不能作为新 runtime 的架构约束；若阻碍 `Turn / Scheduler / Worker / Runtime Workspace` 合同，应按新设计重建调用面。
- `Runtime Workspace` 在进入真正 story runtime 开发时必须从当前 in-process store 升级到持久化存储。这不是实现偏好，而是 boot bar 级前置条件；否则会直接限制 writer retrieval 跨请求可靠性、debug 页面价值、pending / post-write 可追溯性，以及 branch / rollback 衔接。
- writer 文本允许先返回，完整 post-write 后台执行；但必需 post-write 状态必须进入下一轮 gating，不能无限制地在后台悬空。

## 12. 推荐的开工顺序

如果下一步进入真实开发，我建议按下面顺序开工：

1. memory 补强 session 先补底盘
2. story runtime Slice A/B/C
3. `LongformMemoryWorker` 接入，executor 可选择旧 specialist adapter 或新实现
4. Runtime Workspace turn material
5. writer-side retrieval
6. post-write 主链
7. longform discussion/review/rewrite surface
8. LangGraph branch/rollback preflight

这套顺序的核心理由很简单：先把 identity、registry、scheduler、workspace 这些底层合同打稳，后面无论 longform、roleplay 还是 trpg，都不会再被迫回头推翻基础层。

## 13. Related Research

- `research/story-runtime-dependency-readiness-audit.md`
- `research/story-runtime-module-architecture.md`
- `research/story-runtime-technical-research-and-pseudocode.md`
