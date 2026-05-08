# Story Runtime Post-write / Memory Governance Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Post-write / Memory Governance
>
> Status: draft-v1

## 1. 范围

本规格书负责冻结：

- post-write 主链
- post-write trigger 条件
- creation-time obligations 与 derived jobs 的关系
- projection refresh 优先级
- proposal/apply / recall / archival 治理顺序
- user direct edit 与 worker candidate 冲突规则
- failure / retry / repair 的基本恢复边界

这份文档不负责：

- retrieval-core 的召回算法
- writer packet 组包细节
- branch/rollback 的产品语义
- Runtime Workspace / Job Ledger 基础模型本体

## 2. 设计目标

这一层要解决 8 个问题：

1. 为什么 writer 输出后不能就算“这轮结束”
2. 什么情况下必须进入完整 post-write 调度
3. 为什么要先刷新下一轮可见视图，再做重沉淀
4. retrieval 命中为什么必须经过 worker 治理链，而不是直接写 truth
5. user 手改 core 后为什么 worker candidate 不能覆盖
6. 为什么 job ledger 是 turn 完成判定的依据，而不是某个 service 自己说跑完了
7. deterministic failure 和 worker/LLM failure 怎么分层
8. post-write 的设计如何兼容 longform / RP / TRPG

## 3. 当前实现判断

当前后端里：

- `longform_regression_service.py`
  - 已承担一部分 post-write / regression / recall ingestion 职责
  - 但仍是 longform MVP 视角

- `projection_refresh_service.py`
  - 已有 projection refresh 与 memory change event 雏形

- `proposal_workflow_service.py`
  - 已有 proposal submit/policy/apply 治理链

- `post_write_apply_handler.py`
  - 已有 policy decision 路由能力

结论：

- 现有这些 service 都有复用价值
- 但要放进新的 post-write 主链语义下
- `LongformRegressionService` 未来更像 longform adapter，而不是 story runtime 通用 post-write 主控器

## 4. 文件落位建议

## 4.1 复用现有文件

- `backend/rp/services/longform_regression_service.py`
- `backend/rp/services/projection_refresh_service.py`
- `backend/rp/services/proposal_workflow_service.py`
- `backend/rp/services/post_write_apply_handler.py`
- `backend/rp/services/proposal_apply_service.py`
- `backend/rp/services/memory_change_event_service.py`
- `backend/rp/services/runtime_workspace_material_service.py`

## 4.2 新增文件建议

- `backend/rp/models/postwrite_runtime_contracts.py`
- `backend/rp/services/post_write_scheduler_service.py`
- `backend/rp/services/post_write_governance_service.py`
- `backend/rp/services/post_write_repair_service.py`
- `backend/rp/services/projection_refresh_dispatch_service.py`

说明：

- `post_write_scheduler_service.py` 负责 trigger -> plan -> jobs
- `post_write_governance_service.py` 负责 worker results -> proposal / refresh / materialization
- `longform_regression_service.py` 只作为 longform 适配层保留

## 5. 核心对象

## 5.1 PostWriteTriggerContext

用途：

- 表达某轮 writer 输出后，是否需要进入完整 post-write 调度

建议字段：

- `identity: MemoryRuntimeIdentity`
- `turn_id: str`
- `mode: str`
- `turn_kind: str`
- `command_kind: str`
- `retrieval_occurred: bool`
- `manual_core_edit_occurred: bool`
- `rule_card_present: bool`
- `scene_switch_detected: bool`
- `chapter_transition_detected: bool`
- `dirty_domains: list[str]`
- `pending_threshold_reached: bool`
- `full_schedule_due_by_frequency: bool`
- `metadata_json: dict`

## 5.2 PostWriteExecutionEnvelope

用途：

- scheduler 对某轮 post-write 的整体执行结果封装

建议字段：

- `turn_id: str`
- `identity: MemoryRuntimeIdentity`
- `run_kind: str`
  - `minimal_only`
  - `full_schedule`

- `worker_plan_ref: str | None`
- `selected_worker_result_refs: list[str]`
- `projection_refresh_job_refs: list[str]`
- `proposal_job_refs: list[str]`
- `materialization_job_refs: list[str]`
- `repair_job_refs: list[str]`
- `trace_refs: list[str]`
- `metadata_json: dict`

## 5.3 ProjectionRefreshRequest

当前已有 [projection_refresh.py](H:/chatboxapp/backend/rp/models/projection_refresh.py) / `ProjectionRefreshService` 雏形。

本规格书只冻结其 post-write 语义要求：

- 必须带 `identity`
- 必须带 `source_refs`
- 必须带 `refresh_actor`
- 必须带 `base_revision`
- 必须带 `projection_dirty_state`
- 必须能记录 `refresh_reason`

## 5.4 WorkerProposalGovernanceEnvelope

建议统一一类 worker proposal 治理元数据。

建议字段：

- `worker_id: str`
- `phase: str`
- `identity: MemoryRuntimeIdentity`
- `permission_decision: str`
- `permission_reason_codes: list[str]`
- `source_refs: list[str]`
- `trace_refs: list[str]`
- `base_refs: list[dict]`
- `metadata_json: dict`

用途：

- proposal submit/apply
- user direct edit conflict 检查
- trace / audit

## 6. 运行规则

## 6.1 creation-time obligations

固定口径：

- `required_post_write_analysis`
- `runtime_workspace_finalize`

规则：

- 只要 writer 文本允许返回，这两个 job 必须与 turn 同事务登记
- 唯一 owner 是 `StoryTurnDomainService.finalize_writer_output(...)` 或等价 turn-domain finalize facade
- post-write 入口只做幂等校验/补齐，不作为首次创建 owner
- 即使服务在 writer 返回后马上崩溃，系统重启后也能知道这轮还有哪些最小责任未完成

## 6.2 derived jobs

默认在 post-write 分析后按需派发：

- `projection_refresh`
- `proposal_submit`
- `proposal_apply`
- `retrieval_usage_persist`
- `recall_materialization`
- `archival_materialization`
- `archival_reindex`
- `repair_retry`
- `repair_recompute`
- `cleanup_expire_workspace`
- `cleanup_invalidate_candidates`

## 6.3 post-write 触发条件

完整调度 trigger：

- 每 N 轮调度频率命中
- 本轮有 retrieval 行为
- 用户手动编辑了 Core State
- rule card / state card 出现
- scene switch
- chapter transition
- manual refresh
- dirty block / pending threshold

未触发完整调度时：

- 仍然必须写最小 turn materials
- 仍然必须保留 creation-time obligations
- 可以只用上一版 settled view + recent raw turns 继续下一轮

## 6.4 执行顺序

冻结顺序：

1. writer 输出已返回
2. 写最小 turn materials / usage / trace
3. 创建 creation-time obligations
4. 判断是否跑完整 post-write
5. 若完整调度：
   - 运行 scheduler / workers
   - worker 完整分析本轮材料
   - **优先递交 projection refresh**
   - 再做 proposal / apply / recall / archival materialization

关键原则：

- 视图优先不是独立流程
- 而是同一个 post-write workflow 内部的递交顺序

## 6.5 user direct edit 冲突规则

冻结口径：

- 用户显式编辑 Core State 优先级最高
- worker candidate / proposal 必须带 base revision
- apply / projection update 时若目标 block 已被用户更新到更高 revision：
  - worker candidate 失效
  - 或进入 review / 重算
  - 绝不能覆盖用户编辑

## 6.6 retrieval 治理规则

冻结口径：

- retrieval cards / expanded chunks 是 evidence
- 不是事实
- post-write 只处理 usage record 中真正用到的：
  - `used_card_material_ids`
  - `used_expanded_chunk_material_ids`
  - `knowledge_gaps`

worker 需要：

1. 追溯 provenance
2. 判断哪些内容应成为当前剧情必须遵守的事实
3. 形成 proposal / projection refresh / recall / archival candidates

## 6.7 Turn 完成判定

某个 turn 成为正式回退点，需要：

1. acceptance 条件满足
2. 必需 post-write jobs 达到终态：
   - `completed`
   - 或 `deferred`
   - 或 policy 合法跳过

因此：

- writer 文本已经返回，不代表 turn 已 settled
- post-write failure 会阻止 turn 进入 `settled`
- 若必需 jobs 以 `deferred` 结束，turn 最终仍应推进到 `settled`，并使用 `settlement_reason = required_jobs_deferred_by_policy`；`post_write_deferred` 只允许作为短暂中间状态

## 6.8 failure / repair

区分两类：

### deterministic failure

例如：

- 持久化失败
- 约束校验失败
- revision 冲突
- repository 写入失败

处理：

- 记录 failed job
- 不做复杂自愈
- 走 retry / repair / 用户决策

### worker / LLM failure

例如：

- 结构化输出非法
- 工具调用链未收口
- worker 结果无法通过校验

处理：

- 允许一次轻量 repair / bounded retry
- 超出上限后进入失败

## 7. mode-specific 规则

## 7.1 longform

- post-write 更严格
- 下一轮正文通常等待恢复成功或用户明确决策
- review overlay / rewrite / discussion 走独立产品动作

## 7.2 roleplay

- writer 输出先作为 tentative material
- 若上一轮 post-write 未完成，允许在显式 pending 前提下继续
- 优先使用上一版 settled view + recent raw turns

## 7.3 trpg

- 若 failure 涉及规则判定或状态推进
- 默认不能静默继续
- 应优先等待恢复或要求补规则

## 8. 伪代码

## 8.1 Post-write main entry

```python
def run_post_write(identity, trigger_context):
    ensure_creation_time_obligations(identity.turn_id)
    write_minimal_trace(identity)

    if not should_run_full_schedule(trigger_context):
        mark_turn_post_write_deferred_if_allowed(identity.turn_id)
        try_settle_turn(identity.turn_id)
        return build_post_write_envelope(run_kind="minimal_only")

    worker_plan = scheduler.build_worker_execution_plan(
        identity=identity,
        phase="post_write_maintenance",
        mode=resolve_mode(identity),
    )
    worker_results = execute_selected_workers(worker_plan)

    projection_jobs = dispatch_projection_refresh_first(identity, worker_results)
    governance_jobs = dispatch_governance_jobs(identity, worker_results)
    materialization_jobs = dispatch_materialization_jobs(identity, worker_results)

    return build_post_write_envelope(
        run_kind="full_schedule",
        worker_plan_ref=worker_plan.plan_id,
        selected_worker_result_refs=[result.ref for result in worker_results],
        projection_refresh_job_refs=projection_jobs,
        proposal_job_refs=governance_jobs.proposal_jobs,
        materialization_job_refs=materialization_jobs,
    )
```

## 8.2 projection refresh first

```python
def dispatch_projection_refresh_first(identity, worker_results):
    requests = collect_projection_refresh_requests(worker_results)
    job_refs = []
    for request in requests:
        validate_projection_refresh_request(identity, request)
        job = create_job(
            turn_id=identity.turn_id,
            job_kind="projection_refresh",
            creation_mode="derived",
        required_for_turn_completion=request.required,
        )
        projection_refresh_service.refresh_from_bundle(
            chapter=resolve_chapter(identity),
            bundle=request.bundle,
            refresh_request=request,
        )
        complete_job(job.job_id)
        job_refs.append(f"job:{job.job_id}")
    return job_refs
```

## 8.3 proposal governance

```python
def dispatch_governance_jobs(identity, worker_results):
    proposal_jobs = []
    for candidate in collect_proposal_candidates(worker_results):
        envelope = build_worker_governance_envelope(identity, candidate)
        decision = resolve_post_write_policy(candidate, envelope)
        receipt = proposal_workflow_service.submit_and_route(
            input_model=candidate.to_submit_input(),
            session_id=identity.session_id,
            submit_source="post_write_worker",
            governance_metadata=envelope,
        )
        proposal_jobs.append(f"proposal:{receipt.proposal_id}")
    return proposal_jobs
```

## 8.4 turn settlement

```python
def try_settle_turn(turn_id: str):
    turn = load_turn(turn_id)
    jobs = list_jobs(turn_id)
    if turn.acceptance_state not in {"accepted", "auto_accepted"}:
        return False
    if any(job.required_for_turn_completion and job.status not in {"completed", "deferred"} for job in jobs):
        return False
    turn.status = "settled"
    turn.settlement_reason = (
        "required_jobs_deferred_by_policy"
        if any(job.required_for_turn_completion and job.status == "deferred" for job in jobs)
        else "all_required_jobs_completed"
    )
    save_turn(turn)
    return True
```

## 9. 测试点

1. writer 返回后 creation-time obligations 一定存在
2. 未触发完整调度时，最小 turn materials 仍会保留
3. retrieval-triggered turn 会进入完整 post-write 调度
4. projection refresh 先于 recall / archival 沉淀可用
5. user direct edit 会让命中的 worker candidate 失效，而不是被覆盖
6. 必需 post-write failed 时 turn 不能 settled

## 10. 已知风险

1. 当前 `LongformRegressionService` 里混合了 longform 产品细节与治理行为，后续实现时要防止把它继续当通用 post-write orchestrator
2. `PostWriteMaintenancePolicy` 当前规则命名仍偏 MVP domain path，需要与新的 domain/block registry 映射收敛
3. 如果 post-write 直接读取自然语言而不依赖 structured usage / worker results，下游治理会再次退化成不可验证逻辑
