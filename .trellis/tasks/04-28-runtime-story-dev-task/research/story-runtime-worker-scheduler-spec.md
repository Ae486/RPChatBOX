# Story Runtime Worker / Scheduler Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Worker Registry / Scheduler / Orchestrator
>
> Status: draft-v1

## 1. 范围

本规格书负责冻结：

- `WorkerDescriptor`
- `WorkerExecutionPolicy`
- `WorkerExecutionRequest`
- `WorkerExecutionPlan`
- `WorkerContextPacket`
- `WorkerResult`
- Scheduler validate / select / dispatch 规则
- Orchestrator structured plan contract

这份文档不负责：

- writer packet 的具体上下文内容
- retrieval card 结构
- post-write 业务治理细节
- Runtime Workspace child material 模型本体

## 2. 设计目标

这一层要解决 6 个问题：

1. LLM 只提案，程序如何裁决
2. worker 如何以统一合同接入，而不是每个 worker 一条独立链
3. mode/profile/permission 如何真正作用到 worker 执行
4. same worker 在不同 phase 下如何做不同工作，而不是拆两套身份
5. scheduler 如何在不硬编码 worker 名称的情况下执行
6. 怎么让后续 dev session 按统一 contract 并行开发 worker

## 3. 当前实现判断

当前后端里：

- `longform_orchestrator_service.py`
  - 只能输出 MVP `OrchestratorPlan`
  - 主要还是围绕 writer 指令和 retrieval queries

- `longform_specialist_service.py`
  - 本质上承担了单 worker memory 分析职责

- `story_turn_domain_service.py`
  - 当前把 orchestrator/specialist/writer 串成固定顺序

这套链路可作为参考，但不能继续当新 runtime 的主合同。

W5-A 要求：

- 新 runtime 主链消费 `WorkerDescriptor / WorkerExecutionPlan / WorkerContextPacket / WorkerResult`
- 旧 `LongformOrchestratorService` 与 `LongformSpecialistService` 只允许以 adapter 身份挂在新合同后面

本文中的 W5-A / 初始里程碑不是永久 MVP。当前明确演进规划：

- W5-A：冻结 scheduler / worker 合同，使用异步 job 语义，提供轻量
  in-process runner / test drain path，打通真实 job/item/receipt/failure 链路；
- W5-B：补 recoverable background execution，包括进程重启恢复、stale
  running job 检测、并发保护、可替换 queue adapter；
- W5-C：补 operational retry，包括分类瞬时错误的窄自动重试、retry budget、
  cancellation、admin/debug 控制和 metrics。

W5-A 的轻量 runner 只是执行载体，不是长期架构上限。调度合同必须从一开始
避免同步请求假设、brainstorm 私有耦合和 runner 私有状态泄漏。

后续讨论任何“首个实现”“第一版”“W5-A”时，必须先说明总体目标能力族，再从
总体目标中选择当前实现子集，并明确哪些能力延后到 W5-B/W5-C。不能只讨论
初版切片，导致模块最终停滞在初版而和其他模块进度错位。

需求翻译纪律：

- 用户讨论中的表述可能是功能需求说明，不直接等于服务名、DTO 名或存储边界；
- 实现前必须把“proposal”“确认”“版本对比”“worker 修改 memory”等产品说法
  翻译成 scheduler / governance / Core apply 工程合同；
- 调度层负责 durable job / worker item / receipt；
- proposal review 负责用户 accept / reject / edit；
- Core apply 负责正式 memory revision 采用。

当用户功能表述和工程边界存在差异时，以本文档中的工程合同为实现依据。

## 4. 文件落位建议

## 4.1 复用现有文件

- `backend/rp/models/memory_contract_registry.py`
  - 当前已有 `MemoryWorkerDescriptor`
  - 可继续作为 registry descriptor 的基础来源

- `backend/rp/services/memory_contract_registry.py`
  - 继续承载 registry 读取

- `backend/rp/services/runtime_profile_snapshot_service.py`
  - 继续输出 worker activation / permission profile

- `backend/rp/services/longform_orchestrator_service.py`
  - 仅作为旧 orchestrator adapter 候选

- `backend/rp/services/longform_specialist_service.py`
  - 仅作为 `LongformMemoryWorker` adapter 候选

## 4.2 新增文件建议

- `backend/rp/models/worker_runtime_contracts.py`
- `backend/rp/models/scheduler_runtime_contracts.py`
- `backend/rp/services/scheduler_trigger_intake_service.py`
- `backend/rp/services/scheduler_decision_service.py`
- `backend/rp/services/orchestrator_execution_service.py`
- `backend/rp/services/worker_context_builder_service.py`
- `backend/rp/services/worker_registry_service.py`
- `backend/rp/services/worker_scheduler_service.py`
- `backend/rp/services/worker_execution_service.py`
- `backend/rp/services/worker_result_ingestion_service.py`
- `backend/rp/services/scheduler_job_store_service.py`
- `backend/rp/services/scheduler_runner_service.py`
- `backend/rp/services/scheduler_receipt_service.py`
- `backend/rp/services/orchestrator_plan_adapter_service.py`

说明：

- 不建议把新 worker/scheduler 合同继续塞回 `story_runtime.py`
- 旧 `OrchestratorPlan` 保留作 MVP adapter，不再作为新真相模型
- `worker_scheduler_service.py` 如果保留，只能作为 facade / coordinator；
  不得同时承载 trigger intake、source mapping、orchestrator execution、
  scheduler decision、worker packet build、worker execution、result ingestion
  和 receipt persistence。

## 5. 核心对象

## 5.1 WorkerDescriptor

用途：

- registry 中一条 worker 的声明式描述
- 用于 snapshot compile、scheduler validate、worker enable/disable、permission resolve

建议字段：

- `worker_id: str`
- `display_name: str`
- `owned_domains: list[str]`
- `read_domains: list[str]`
- `allowed_layers: list[str]`
- `tool_allowlist: list[str]`
- `default_execution_policy: str`
- `supported_phases: list[str]`
- `permission_profile_ref: str | None`
- `provider_defaults: dict`
- `model_defaults: dict`
- `context_slot_policy: dict`
- `output_schema_version: str`
- `metadata_json: dict`

工程语义：

- `owned_domains` 是主责领域，不等于无条件写权限
- `supported_phases` 用于区分同一 worker 在不同 phase 的执行方式
- `context_slot_policy` 约束 scheduler/context orchestration 能给它哪些材料

## 5.2 WorkerExecutionPolicy

用途：

- 定义 worker 的执行类型和默认行为

建议字段：

- `policy_id: str`
- `execution_class: str`
  - `always_run`
  - `scheduled`
  - `post_write_observer`
  - `maintenance`

- `blocking_default: bool`
- `allow_async: bool`
- `allow_degrade: bool`
- `must_record_trace: bool`
- `requires_runtime_workspace: bool`
- `requires_post_write_job: bool`
- `metadata_json: dict`

关键约束：

- `always_run` 是 workflow 级必经能力，不代表每轮都要跑重 worker
- 具体是否重跑仍由 scheduler 按 dirty/budget/trigger 决定

## 5.3 WorkerExecutionRequest

用途：

- scheduler 派发给具体 worker executor 的请求

建议字段：

- `request_id: str`
- `identity: MemoryRuntimeIdentity`
- `worker_id: str`
- `phase: str`
- `mode: str`
- `turn_id: str`
- `context_packet_ref: str | None`
- `context_packet: dict | None`
- `execution_policy: dict`
- `budget_class: str | None`
- `reason_codes: list[str]`
- `scheduler_constraints: dict`
- `metadata_json: dict`

## 5.4 WorkerExecutionPlan

用途：

- scheduler 裁决后的最终执行清单

建议字段：

- `plan_id: str`
- `identity: MemoryRuntimeIdentity`
- `plan_source: str`
  - `orchestrator`
  - `deterministic_fallback`
  - `post_write_required`

- `phase: str`
- `selected_workers: list[WorkerExecutionItem]`
- `skipped_workers: list[WorkerSkipItem]`
- `degraded_workers: list[WorkerDegradeItem]`
- `trace_summary: dict`
- `metadata_json: dict`

### WorkerExecutionItem

建议字段：

- `worker_id: str`
- `must_run: bool`
- `allow_degrade: bool`
- `blocking: bool`
- `async_allowed: bool`
- `budget_class: str | None`
- `context_requirements: dict`
- `reason_codes: list[str]`
- `scheduler_constraints: dict`
- `status: str`
- `attempt: int`
- `last_receipt_id: str | None`

### WorkerSkipItem

建议字段：

- `worker_id: str`
- `skip_reason: str`
- `reason_codes: list[str]`

### WorkerDegradeItem

建议字段：

- `worker_id: str`
- `from_execution_class: str`
- `to_execution_class: str`
- `degrade_reason: str`

## 5.5 WorkerContextPacket

该对象是 worker 侧输入合同，writer packet 不是它的子集。

如果与 `story-runtime-context-packet-spec.md` 的字段列举冲突，以后者为 canonical contract。

建议字段：

- `packet_id: str`
- `identity: MemoryRuntimeIdentity`
- `worker_id: str`
- `phase: str`
- `mode: str`
- `session_refs: list[str]`
- `recent_turn_refs: list[str]`
- `core_projection_refs: list[str]`
- `sidecar_refs: list[str]`
- `retrieval_refs: list[str]`
- `workspace_refs: list[str]`
- `forbidden_context: list[str]`
- `token_budget: dict`
- `packet_metadata: dict`
- `trace_refs: list[str]`

关键约束：

- worker packet 可以引用 Runtime Workspace
- writer packet 默认不吃 Runtime Workspace 日志

## 5.6 WorkerResult

建议字段：

- `worker_id: str`
- `phase: str`
- `result_status: str`
  - `completed`
  - `failed`
  - `degraded`
  - `skipped`

- `writer_hints: list[dict]`
- `projection_refresh_requests: list[dict]`
- `proposal_candidates: list[dict]`
- `recall_candidates: list[dict]`
- `archival_candidates: list[dict]`
- `validation_findings: list[dict]`
- `evidence_refs: list[str]`
- `trace_summary: dict`
- `metadata_json: dict`

关键约束：

- `WorkerResult` 必须结构化
- 不允许让 scheduler 再去读自由文本猜 worker 结果
- `WorkerResult` 不是 Core mutation receipt；它只表示 worker 产出了结构化候选
  / finding / refresh request
- worker 必须产出结构化 candidate new version 或明确 no-op finding；不能用自由
  文本表达“我要改什么”
- proposal 不是 worker 私有工具；权限不足时，proposal 是固定治理逻辑把 old
  block revision 和 worker-produced new block revision 交给用户确认的过程
- W5-A worker 输出以 block-level candidate new version 为主；字段级 diff /
  patch 只作为派生展示或后续优化，不作为主合同

建议 block-level candidate 字段：

- `target_block_ref: str`
- `base_block_revision_id: str`
- `candidate_revision_id: str`
- `candidate_content: dict`
- `source_refs: list[str]`
- `evidence_refs: list[str]`
- `change_summary: str`
- `no_op_reason: str | None`

约束：

- `base_block_revision_id` 必须等于当前 branch-visible block revision 才能
  accept / apply；
- base revision 变化时，candidate 进入 stale/conflict，不能直接应用；
- 一个 worker result 可以包含多个 block candidates；
- worker 只能为自己拥有或被授权的 block 产出 candidate；
- 前端红绿 diff / 并排对比由 old/current content 和 candidate content 派生；
- 用户在 review surface 中编辑后，用户编辑版本优先于 worker candidate。

如果一个 proposal review 包含多个 block candidates，底层语义按 block 独立
accept / reject。`Accept All` / `Reject All` 只能是 UI 便利操作，持久化状态
仍然逐 block 记录。

推荐 per-block review statuses：

```text
pending_review
accepted
rejected
edited
stale
applied
```

推荐 proposal review aggregate statuses：

```text
pending_review
partially_accepted
accepted
rejected
partially_stale
```

单个 block stale/conflict 只阻塞该 block candidate，不阻塞同一 proposal
review 下其他未冲突 block candidate。

worker 产出的 candidate new version 存在 Runtime Workspace，不直接进入 active
Core，也不能只存在前端内存。

W5-A 存储合同：

```text
RuntimeWorkspaceMaterial.kind = WORKER_CANDIDATE
visibility = review_visible 或 worker_visible
metadata.source_of_truth = false
metadata.authoritative_mutation = false
```

candidate material payload 保存 block-level candidate 字段，例如
`target_block_ref`、`base_block_revision_id`、`candidate_content`、`source_refs`、
`evidence_refs`、`change_summary`。

`ProposalReview` 只保存 old/current Core block refs 和 candidate material refs；
它不复制 Core truth，也不拥有 candidate payload truth。

Lifecycle 映射：

- accept / apply 后，candidate material lifecycle 标记为 `promoted`；
- reject 后标记为 `discarded`；
- stale / conflict 后标记为 `invalidated`。

worker candidate 使用 repository-backed、identity-scoped Runtime Workspace
material store。W5-A 不能把 candidate 只存在进程内缓存中，因为 proposal review
必须能跨刷新和后续请求读取。

用户 accept proposal 后，proposal UI 不直接写 Core。accept 的含义是把用户
确认的 candidate 版本交给统一 governed Core mutation / apply 路径正式采用。

由于 worker 已经投机执行并产出完整 candidate new version，accept 不重新运行
worker，也不要求 worker 再生成第二个 patch。剩余工作只是正式采用版本：

- 重新校验 `base_block_revision_id` 是否仍等于当前 branch-visible revision；
- 用 accepted candidate 或用户编辑版本创建正式 Core block revision；
- 更新 branch-visible manifest / pointer；
- 记录 MemoryChangeEvent / apply receipt / audit refs；
- 按需标记 projection dirty 或请求 projection refresh。

Scheduler、proposal review、Core apply 是三个独立生命周期：

- `SchedulerJob` / `SchedulerWorkerItem`：worker 执行和 candidate 产出；
- `ProposalReview`：用户查看、accept、reject、edit；
- `CoreApplyReceipt`：正式 Core 采用。

用户 accept / reject 不反向改写已经 completed 的 scheduler job 状态。三者通过
id 关联展示，但各自拥有自己的状态字段。

## 5.7 SchedulerJob completion boundary

`SchedulerJob.status=completed` 不等于 Core memory 一定发生变更。

它只表示：

- 被选中的 worker item 已经达到 terminal success 或 accepted skip/degrade；
- completed worker result 已通过结构化 schema 校验；
- `WorkerResultIngestion` 已经接受结果，并把 proposal candidate、Core
  change candidate、projection refresh request、finding 或 governance receipt
  交给下游；
- scheduler receipt 记录了交付给治理 / proposal / apply 的内容。

真正的 Core mutation 仍由 deterministic governance / proposal / apply /
projection services 决定。一个 completed scheduler job 可以对应：

- Core changes applied；
- proposal pending review；
- governance rejected；
- no-op finding；
- projection refresh only。

如果 worker 执行成功但 result ingestion 失败，job 不能标记为 `completed`，
必须进入 `failed` 或 `partial_failed`，并记录具体 failure category / reason。

`WorkerResultIngestion` 不写死 direct apply / proposal / review 策略。它必须读取
setup 阶段配置出的 worker 权限、active `RuntimeProfileSnapshot`、domain policy
和治理规则，然后把结构化候选路由为：

```text
direct_apply_allowed
proposal_required
review_required
blocked
```

brainstorm item、accepted prose K-window、manual flush、chapter close flush 都走
同一套 worker permission / governance 路径；brainstorm 不能拥有私有直写通道。

如果权限要求 review / proposal，固定逻辑创建版本对比记录：

- old version 指向当前 branch-visible Core block revision；
- new version 指向 worker 产出的 candidate block revision；
- 前端可以渲染为 diff 风格红/绿对比，或 block 级新旧并排对比；
- W5-A 只要求 accept / reject；
- reject 不改变 active Core；
- accept 应用 candidate；如果用户在单个 block 的 review surface 中编辑过，则
  用户编辑版本优先于 worker candidate。
- 多 block proposal review 按 block 独立 accept / reject；批量按钮只是 UI
  便利，不改变底层逐 block 状态。
- proposal accept 走统一 governed Core apply 路径；proposal UI 不拥有 Core
  写入逻辑。
- SchedulerJob、ProposalReview、CoreApplyReceipt 生命周期分离；accept / reject
  不回写 scheduler job 状态。
- worker candidate new version 存为 RuntimeWorkspaceMaterial(kind=WORKER_CANDIDATE)，
  accept/reject/stale 分别映射为 promoted/discarded/invalidated。

如果 worker 本轮判断 no-op，不创建 proposal review 记录。

## 6. Registry 规则

## 6.1 Registry 真相来源

W5-A registry 真相优先来自：

- `MemoryDomainContract`
- `MemoryWorkerDescriptor`
- `RuntimeProfileSnapshotCompiledProfile.worker_activation`

## 6.2 Scheduler 不允许硬编码

禁止：

- 直接 if/else 写死 `LongformMemoryWorker`、`WritingWorker`
- 直接在 scheduler 里散落 mode -> worker 名称映射

必须：

- 通过 registry 发现 worker
- 通过 snapshot 判断是否 active
- 通过 descriptor 判断 phase/permission/tool allowlist
- 通过 runtime profile / domain policy 判断 worker 输出是 direct apply、
  proposal、review 还是 blocked

## 6.3 W5-A bootstrap set

冻结的 bootstrap set：

- `LongformMemoryWorker`
- `WritingWorker`

预留：

- `CharacterMemoryWorker`
- `SceneInteractionWorker`
- `RuleStateWorker`
- `MaintenanceWorker`

说明：

- W5-A 只要求 `LongformMemoryWorker` 真正可执行；后续 worker 扩展属于
  W5-B/W5-C 的规划范围，不得通过硬编码绕开 registry
- `WritingWorker` 虽然也是 worker，但它是用户可见输出 worker，运行位置由 writer runtime 规格书进一步说明

## 7. Scheduler 运行规则

## 7.1 基本流程

1. 读取 `MemoryRuntimeIdentity`
2. 读取 `RuntimeProfileSnapshot`
3. 读取 active worker descriptors
4. 读取 phase / mode / trigger
5. 请求 orchestrator plan（若该 phase 需要）
6. 校验 orchestrator plan
7. 生成 `WorkerExecutionPlan`
8. 派发 worker requests
9. 汇总 worker results

## 7.2 Orchestrator 与 Scheduler 边界

Orchestrator 只负责：

- 提案
- 给出建议 worker
- 给出 context 需求
- 给出建议原因
- 通过结构化工具 / 严格结构化输出选择 source refs 或窗口内短编号

Scheduler 负责：

- 验证 worker 是否 active
- 验证 phase 是否支持
- 验证 permission / budget / constraints
- 决定执行 / 跳过 / 降级 / async
- 把 orchestrator 的 source 选择解析成稳定 source refs
- 生成最终 `WorkerExecutionPlan` 和可追溯 receipt

当前确认口径：

- LLM 可以存在于 Orchestrator Worker 和 Specialist Worker；
- Scheduler Decision 是 deterministic 裁决层，不由 LLM 拥有最终执行主权；
- Orchestrator 传给 worker 的内容是 evidence selection，不是权威事实判断；
- worker 必须读取真实 source text 和 memory snapshot，自行维护自己负责的
  Core memory blocks。

## 7.3 Async job semantics

Scheduler 从 W5-A 开始采用异步 job 语义。

trigger submit 负责创建或复用 `SchedulerJob`，返回 job / receipt 状态；它
不应该要求 HTTP/API 调用方等待所有 orchestrator / worker 执行完成。

W5-A 可以使用轻量执行载体：

- in-process background runner；
- 显式 `run_pending_once()`；
- 测试中的 drain pending jobs 路径。

但这只是 runner 实现，不是同步合同。合同必须已经支持：

- `pending` / `running` / terminal job status；
- worker item attempt；
- 按 `window_fingerprint` 幂等 re-entry；
- failed worker item 手动重试；
- job / receipt 查询。

W5-B 必须将 runner 演进为 recoverable background execution：

- 进程重启后恢复 pending / running-recoverable job；
- stale running job 检测；
- 并发抢占保护；
- queue adapter 可替换。

外部队列属于 W5-B/W5-C 的执行实现细节，不能改变 scheduler trigger /
job / worker item / failure / receipt 合同。

## 7.4 Job idempotency and retry

Scheduler 必须从 W5-A 开始支持幂等与 worker 级重试。

核心判断不是“这个 trigger 又来了一次”，而是“这次 trigger 指向的 source
window 是否已经处理过”。因此调度前必须计算 `window_fingerprint`。

推荐 fingerprint 输入：

- `story_id`
- `branch_id`
- `trigger_type`
- stable source refs
- source text hashes
- scheduler profile / policy version
- `maintenance_window_index`

语义：

- fingerprint 不存在：创建新的 `SchedulerJob`；
- fingerprint 已存在且 job `completed`：返回已有 receipt 或 linked no-op
  receipt，不重新执行 worker；
- fingerprint 已存在且 job `running`：返回 existing in-flight job；
- fingerprint 已存在且 job `failed` / `partial_failed`：只重试 failed
  `SchedulerWorkerItem`；
- successful worker item 在 retry 时不得重复执行；
- manual flush 与 K-window trigger 如果解析到同一 source window，应通过
  fingerprint dedupe，而不是产生两次 worker dispatch。

最小状态：

```text
SchedulerJob.status:
pending / running / completed / partial_failed / failed / skipped

SchedulerWorkerItem.status:
pending / running / completed / failed / skipped
```

如果部分 worker 成功、部分 worker 失败，整体 job 是 `partial_failed`。
worker 问题必须允许重试任务，但重试应绑定原 job / receipt，并只针对失败
item 建立新的 attempt。

W5-A retry 以手动触发为主。开发期间遇到 worker 错误时，系统应先保留
failure reason / receipt / trace，方便定位原因并修复问题；不得用盲目自动重试
掩盖 schema 错误、权限错误、source ref 缺失、worker 输出不合规或治理拒绝。
W5-C 必须补 operational retry 策略，但只覆盖明确可恢复的分类瞬时错误。

错误码策略采用“小集合起步，开发中逐步收敛 unknown”的方式。W5-A 先冻结
肯定会出现的 failure categories：

```text
validation_error
permission_error
source_error
orchestrator_error
worker_error
retrieval_error
governance_error
persistence_error
upstream_error
unknown_error
```

W5-A reason codes 至少覆盖：

```text
window_fingerprint_conflict
source_window_empty
source_ref_not_found
paragraph_number_out_of_range
worker_not_active
worker_permission_denied
orchestrator_schema_invalid
orchestrator_provider_error
worker_output_schema_invalid
worker_provider_error
retrieval_query_failed
governance_rejected
receipt_write_failed
unknown_error
```

`unknown_error` 不是失败分类设计失败，而是兜底状态。它必须保留 raw exception
type / raw message / provider / upstream status / request id / job id / worker
item id / source refs，方便测试和开发期间把高频 unknown 提升为明确 reason
code 并补测试。

## 7.5 Deterministic fallback

若 orchestrator 输出：

- schema 不合法
- worker_id 不存在
- phase 不支持
- budget 超限
- 必需 worker 未被选择

scheduler 必须：

- 进入 deterministic fallback
- 最少保证必需 worker 能被选中
- 同时写 trace 说明 fallback 原因

## 7.6 Phase 规则

建议 phase 最小集合：

- `pre_write_context`
- `writer_generation`
- `post_write_maintenance`
- `manual_refresh`
- `story_evolution`

约束：

- 同一 worker 不按 phase 拆身份
- phase 改变的是输入、工具、权限、输出合同

## 8. Orchestrator structured plan contract

旧 `OrchestratorPlan` 目前只够 MVP。

新 orchestrator 输出至少要包含：

- `phase`
- `candidate_workers`
- `must_run_workers`
- `context_requests`
- `budget_hints`
- `reason_codes`
- `allow_degrade`
- `notes`

### CandidateWorkerPlan

建议字段：

- `worker_id: str`
- `must_run: bool`
- `context_requirements: dict`
- `reason_codes: list[str]`
- `budget_class: str | None`
- `allow_degrade: bool`

### OrchestratorPlanEnvelope

建议字段：

- `plan_version: str`
- `identity_ref: str`
- `phase: str`
- `candidate_workers: list[CandidateWorkerPlan]`
- `plan_notes: list[str]`

### Source-selection tool contract

调度层不应为 brainstorm 和正文 K-window 分别维护两套 source mapping。
Trigger intake 应先把不同来源统一规范化为 `SchedulerSourceUnit[]`：

- `accepted_story_paragraph`：确认采纳正文段落；
- `brainstorm_item`：用户审查后上传的 brainstorm 条目；
- future kinds：后续 manual flush / chapter close / repair/debug 等入口可扩展。

`SchedulerSourceUnit` 是调度层内部模型，不应泄漏到 writer、brainstorm UI 或
proposal UI。它的价值只在于减少重复逻辑，并让 orchestrator 始终面对简单的
`1..N` 编号。

对于 accepted prose K-window 维护，orchestrator 不应复制原文或复杂 source
ref。Trigger intake 先为当前窗口生成 `1..N` 的 source unit 短编号映射。
Orchestrator 看到短编号和 source unit 内容后，只通过结构化工具选择 worker
和编号：

```python
class OrchestratorDispatchSelection(BaseModel):
    worker_id: str
    source_unit_numbers: list[int]
    focus_hint: str | None = None
    reason_codes: list[str] = Field(default_factory=list)


class OrchestratorDispatchToolInput(BaseModel):
    selections: list[OrchestratorDispatchSelection]
```

规则：

- `source_unit_numbers` 只在当前 scheduler window 内有效；
- 持久化 trace / worker result / proposal / receipt 必须使用真实 source refs；
- `focus_hint` 是非权威提示，不能作为 memory fact；
- orchestrator 不能输出 memory 更新内容、改写后的 source 内容、Core patch 或
  worker candidate 内容；
- Scheduler Decision 必须校验编号范围、去重、worker active 状态、phase 和
  permission，再生成 worker packet。

W5-A 验收必须同时覆盖两条真实产品入口：

- `brainstorm_batch_submitted`
- `accepted_prose_k_window`

这用于证明 scheduler 是通用 runtime 基础设施，而不是 brainstorm 私有
consumer。

### Accepted prose K-window contract

`K` 只统计当前 branch canonical story body 中已确认采纳的 story segment：

- 不包括章节起始大纲；
- 不包括 draft；
- 不包括未确认的 rewrite candidate；
- 第三段多次 rewrite 但未确认时 count 仍是 2，确认后才是 3；
- 分支 / 回退以后，以 active branch 可见的 accepted segment index 为准。

建议在 accepted/adoption turn 或 adoption receipt 上记录：

- `canonical_segment_index` 或 `accepted_story_segment_index`；
- `maintenance_window_index`；
- `maintenance_window_position`；
- `maintenance_window_size`。

触发规则：

- 满 `K` 个 confirmed story segment 正常触发；
- chapter close 可以 flush 不足 K 的尾部窗口；
- manual flush 允许，W5-A 可只做 internal/debug trigger，W5-B/W5-C 再补产品
  UI 入口；
- scene close 不触发，也不切断窗口；窗口允许跨 scene。

## 9. 伪代码

## 9.1 Scheduler validate and dispatch

```python
def build_worker_execution_plan(identity, phase, mode, orchestrator_plan=None):
    snapshot = load_snapshot(identity.runtime_profile_snapshot_id)
    registry = load_active_worker_descriptors(snapshot)
    required_workers = resolve_required_workers(snapshot, phase, mode)

    if orchestrator_plan is None:
        candidate_workers = []
    else:
        candidate_workers = orchestrator_plan.candidate_workers

    selected = []
    skipped = []
    degraded = []

    for required in required_workers:
        if required.worker_id not in [item.worker_id for item in candidate_workers]:
            candidate_workers.append(
                CandidateWorkerPlan(
                    worker_id=required.worker_id,
                    must_run=True,
                    context_requirements={},
                    reason_codes=["required_by_policy"],
                    allow_degrade=False,
                )
            )

    for item in candidate_workers:
        descriptor = registry.get(item.worker_id)
        if descriptor is None:
            skipped.append({"worker_id": item.worker_id, "skip_reason": "unknown_worker"})
            continue
        if phase not in descriptor.supported_phases:
            skipped.append({"worker_id": item.worker_id, "skip_reason": "phase_not_supported"})
            continue
        if not is_worker_active(snapshot, item.worker_id):
            skipped.append({"worker_id": item.worker_id, "skip_reason": "inactive_in_snapshot"})
            continue
        decision = apply_scheduler_constraints(snapshot, descriptor, item)
        if decision.kind == "skip":
            skipped.append({"worker_id": item.worker_id, "skip_reason": decision.reason})
            continue
        if decision.kind == "degrade":
            degraded.append({"worker_id": item.worker_id, "degrade_reason": decision.reason})
        selected.append(build_execution_item(descriptor, item, decision))

    return WorkerExecutionPlan(
        plan_id=new_id(),
        identity=identity,
        phase=phase,
        selected_workers=selected,
        skipped_workers=skipped,
        degraded_workers=degraded,
    )
```

## 9.2 Execute one worker

```python
def execute_worker(request: WorkerExecutionRequest) -> WorkerResult:
    executor = resolve_worker_executor(request.worker_id)
    packet = load_or_build_worker_context_packet(request)
    return executor.run(packet=packet, request=request)
```

## 10. 测试点

1. registry 中关闭某个 worker 后，scheduler 不再选它
2. required worker 即使 orchestrator 漏掉，也会被 fallback 补上
3. phase 不支持时 worker 被跳过
4. 同一 worker 在 `pre_write_context` 和 `post_write_maintenance` 能走不同执行策略
5. `WorkerResult` 不依赖自由文本就能驱动下游
6. scheduler 不写死 worker 名称仍可完成 longform bootstrap

## 11. 已知风险

1. 当前 `MemoryWorkerDescriptor` 在 `memory_contract_registry.py` 中还偏 registry 视角，后续实现时可能需要一个更 runtime-centric 的 wrapper，但不能把两个 descriptor 语义写散
2. 如果 dev 直接沿用旧 `OrchestratorPlan` 不升级结构化 plan，scheduler 会退化回 writer-first 固定链
3. `WritingWorker` 同时是用户可见输出 worker 和 registry worker，后续实现要注意它和 `LongformMemoryWorker` 的职责边界
