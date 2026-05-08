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

第一阶段要求：

- 新 runtime 主链消费 `WorkerDescriptor / WorkerExecutionPlan / WorkerContextPacket / WorkerResult`
- 旧 `LongformOrchestratorService` 与 `LongformSpecialistService` 只允许以 adapter 身份挂在新合同后面

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
- `backend/rp/services/worker_registry_service.py`
- `backend/rp/services/worker_scheduler_service.py`
- `backend/rp/services/worker_execution_service.py`
- `backend/rp/services/orchestrator_plan_adapter_service.py`

说明：

- 不建议把新 worker/scheduler 合同继续塞回 `story_runtime.py`
- 旧 `OrchestratorPlan` 保留作 MVP adapter，不再作为新真相模型

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

## 6. Registry 规则

## 6.1 Registry 真相来源

第一阶段 registry 真相优先来自：

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

## 6.3 第一阶段 bootstrap set

冻结的 bootstrap set：

- `LongformMemoryWorker`
- `WritingWorker`

预留：

- `CharacterMemoryWorker`
- `SceneInteractionWorker`
- `RuleStateWorker`
- `MaintenanceWorker`

说明：

- 第一阶段只要求 `LongformMemoryWorker` 真正可执行
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

Scheduler 负责：

- 验证 worker 是否 active
- 验证 phase 是否支持
- 验证 permission / budget / constraints
- 决定执行 / 跳过 / 降级 / async

## 7.3 Deterministic fallback

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

## 7.4 Phase 规则

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
