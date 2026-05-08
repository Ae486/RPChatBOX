# Story Runtime Workspace / Ledger / Trace Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Runtime Workspace / Turn Ledger / Trace
>
> Status: draft-v1

## 1. 范围

本规格书负责冻结：

- `StoryTurnRecord`
- `RuntimeWorkspaceMaterial`
- `RuntimeWorkflowJobRecord`
- unified trace / audit spine
- turn child material / refs / receipts 的归属规则

这份文档不负责：

- worker descriptor 细节
- writer packet 内容选择细节
- retrieval card 的生成策略
- post-write 业务判断逻辑

## 2. 设计目标

这一层要解决 6 个问题：

1. `Turn` 如何成为唯一主锚点
2. 本轮临时材料和长期真相如何分层
3. 后台任务如何判断“这轮是否完全完成”
4. debug / trace / eval 如何有统一留痕，而不搞重型 event sourcing
5. branch 切换为什么不会把别的分支 pending 材料带过来
6. retrieval / review overlay / proposal / worker evidence 如何统一挂到 turn 下

## 3. 文件落位建议

## 3.1 复用现有文件

- `backend/rp/models/runtime_workspace_material.py`
- `backend/rp/models/memory_contract_registry.py`
- `backend/rp/services/runtime_workspace_material_service.py`
- `backend/rp/services/runtime_memory_persistence_repository.py`
- `backend/rp/services/memory_change_event_service.py`
- `backend/rp/services/runtime_read_manifest_service.py`

## 3.2 新增文件建议

- `backend/rp/models/runtime_workflow_job.py`
- `backend/rp/models/runtime_trace_records.py`
- `backend/rp/services/runtime_workflow_job_service.py`
- `backend/rp/services/runtime_trace_service.py`

说明：

- `StoryTurnRecord` 可以与 identity 相关 record 放在同一 `story_runtime_records.py`，但其状态字段和子材料归属语义由本规格书定义。

## 4. Turn 作为唯一主锚点

冻结规则：

- `StoryTurnRecord` 是唯一主锚点
- 下列对象都只能作为 `Turn` 的子材料或关联记录存在：
  - review overlay
  - brainstorm change summary
  - brainstorm apply receipt
  - retrieval cards / expanded chunks / usage
  - worker candidate / evidence bundle
  - proposal/apply receipts
  - packet refs / packet summary

禁止：

- 再长一套“平行主记录系统”
- 让 review / retrieval / proposal 自己变成产品级时间线

## 5. 数据模型

## 5.1 StoryTurnRecord

建议字段：

- `turn_id: str`
  - 主键

- `session_id: str`
- `story_id: str`
- `branch_head_id: str`

- `parent_turn_id: str | None`

- `runtime_profile_snapshot_id: str`

- `turn_kind: str`
  - 推荐最小枚举：
    - `writing`
    - `discussion`
    - `review`
    - `interaction`
    - `deterministic`

- `command_kind: str`
  - 前端动作入口语义

- `status: str`
  - `received`
  - `packet_built`
  - `writer_running`
  - `writer_completed`
  - `post_write_pending`
  - `post_write_running`
  - `post_write_deferred`
  - `settled`
  - `failed`

- `acceptance_state: str`
  - 推荐最小枚举：
    - `pending`
    - `accepted`
    - `rejected`
    - `auto_accepted`

- `settlement_reason: str | None`
- `failure_reason: str | None`

- `current_packet_ref: str | None`
- `visible_output_ref: str | None`
- `selected_output_ref: str | None`

- `metadata_json: dict`

- `received_at: datetime`
- `writer_started_at: datetime | None`
- `writer_completed_at: datetime | None`
- `post_write_started_at: datetime | None`
- `settled_at: datetime | None`
- `failed_at: datetime | None`
- `updated_at: datetime`

关键约束：

- `Turn` 是正文推进事件，不是所有控制动作
- `acceptance_state` 和 `status` 不是一回事
- 只有 acceptance 条件满足且必需 post-write 条件满足时，才能 `settled`

## 5.2 RuntimeWorkspaceMaterial

当前 [runtime_workspace_material.py](H:/chatboxapp/backend/rp/models/runtime_workspace_material.py) 已有良好基础，第一阶段直接沿用并扩展。

建议字段：

- `material_id: str`
- `material_kind: RuntimeWorkspaceMaterialKind`
- `identity: MemoryRuntimeIdentity`
- `domain: str`
- `domain_path: str | None`
- `source_refs: list[MemorySourceRef]`
- `short_id: str | None`
- `payload: dict`
- `lifecycle: RuntimeWorkspaceMaterialLifecycle`
- `visibility: str`
- `created_by: str`
- `expiration_ref: str | None`
- `materialization_ref: str | None`
- `trace_refs: list[str]`
- `metadata: dict`

推荐保留的 material kinds：

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

推荐 lifecycle：

- `active`
- `used`
- `unused`
- `expanded`
- `promoted`
- `discarded`
- `expired`
- `invalidated`

关键约束：

- Runtime Workspace 永远不是 story truth
- raw retrieval / tool materials 只在 turn 内临时有效
- 被 promote 的只是“治理后结果”，不是 material 本体自动变真相

## 5.3 RuntimeWorkflowJobRecord

建议字段：

- `job_id: str`
  - 主键

- `turn_id: str`
- `session_id: str`
- `branch_head_id: str`
- `runtime_profile_snapshot_id: str`

- `job_kind: str`
  - 当前冻结全局候选集合：
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

- `job_category: str`
  - `turn-finalization`
  - `state-governance`
  - `memory-materialization`
  - `maintenance-and-repair`

- `status: str`
  - `pending | running | completed | failed | cancelled | deferred`

- `creation_mode: str`
  - `creation_time_obligation | derived`

- `required_for_turn_completion: bool`

- `worker_id: str | None`
- `parent_job_id: str | None`
- `idempotency_key: str | None`

- `source_ref_ids: list[str]`
- `result_ref_ids: list[str]`
- `trace_refs: list[str]`

- `attempt_count: int`
- `completion_reason: str | None`
- `failure_reason: str | None`
- `last_error: dict | None`

- `metadata_json: dict`

- `created_at: datetime`
- `started_at: datetime | None`
- `completed_at: datetime | None`
- `updated_at: datetime`

关键约束：

- job 不是新的正文锚点
- job 只服务 turn 完成判定、恢复、补跑、审计
- settlement 只读取 `required_for_turn_completion`
- `job_category` 只服务查询/统计，不参与 settlement 语义

## 5.4 RuntimeReadManifestRecord

建议增加一份确定性读合同记录，服务 debug / replay / packet 审计。

建议字段：

- `manifest_id: str`
- `turn_id: str`
- `session_id: str`
- `branch_head_id: str`
- `runtime_profile_snapshot_id: str`
- `consumer_kind: str`
  - `writer_packet | worker_packet | debug_read`
- `source_ref_ids: list[str]`
- `result_ref_ids: list[str]`
- `trace_refs: list[str]`
- `manifest_json: dict`
- `created_at: datetime`

`manifest_json` 最小应覆盖：

- active branch lineage
- pinned snapshot id
- visible refs
- selected refs
- section source / revision / hash
- retrieval usage refs
- packet policy metadata

## 5.5 MemoryChangeEventRecord

直接复用 [memory_contract_registry.py](H:/chatboxapp/backend/rp/models/memory_contract_registry.py) 中的：

- `MemoryChangeEvent`
- `MemorySourceRef`
- `MemoryDirtyTarget`

但在本层明确其角色：

- 它是 trace/invalidation 脊柱
- 不是 event-sourcing 真相仓库

## 6. 运行规则

## 6.1 Creation-time obligations

第一阶段固定两类 creation-time obligations：

- `required_post_write_analysis`
- `runtime_workspace_finalize`

规则：

- 只要 writer 文本允许返回，这两个 job 就必须与 `Turn` 同事务登记
- 唯一 owner 是 `StoryTurnDomainService.finalize_writer_output(...)` 或等价 turn-domain finalize facade
- `run_post_write()` 只能做幂等校验/补齐，不应成为首次创建 owner
- 后续派发的 jobs 属于 derived jobs

## 6.2 Turn 完成判定

某个 `Turn` 只有在下面两个条件都满足后，才进入正式可回退状态：

1. acceptance 条件满足
2. 所有必需 jobs 达到：
   - `completed`
   - 或 `deferred`
   - 或被 policy 合法跳过

补充语义：

- `post_write_deferred` 允许作为短暂的 turn 中间状态
- 但若该 turn 最终可作为正式回退点，必须推进到 `settled`
- 此时使用：
  - `Turn.status = settled`
  - `Turn.settlement_reason = required_jobs_deferred_by_policy`
- 不允许让 `post_write_deferred` 长期充当 rollback anchor 状态

## 6.3 Branch 对 Workspace 的隔离

分支切换时：

- 不携带原分支 fork 后的 pending / candidate / workspace results
- 新分支只读取：
  - fork 前共享 settled memory
  - 本分支自己的 workspace / pending / candidate

## 6.4 Material 生命周期

retrieval raw materials 的推荐规则：

1. 先写入 `Runtime Workspace`
2. writer 产出前补齐 usage record
3. post-write 只处理：
   - `used_card_material_ids`
   - 必要的 `used_expanded_chunk_material_ids`
   - `knowledge_gaps`
4. worker 成功治理后：
   - 相关结果进入 Core / Recall / Archival
   - raw materials 标记 `promoted` / `discarded` / `expired`

## 7. 伪代码

## 7.1 writer 输出返回时的最小登记

```python
def finalize_writer_output(identity, packet_ref, output_ref, usage):
    turn = load_turn(identity.turn_id)
    write_workspace_material(kind="PACKET_REF", identity=identity, payload={"ref": packet_ref})
    write_workspace_material(kind="WRITER_OUTPUT_REF", identity=identity, payload={"ref": output_ref})
    write_workspace_material(kind="TOKEN_USAGE_METADATA", identity=identity, payload=usage)
    create_job(
        turn_id=turn.turn_id,
        job_kind="required_post_write_analysis",
        creation_mode="creation_time_obligation",
        required_for_turn_completion=True,
    )
    create_job(
        turn_id=turn.turn_id,
        job_kind="runtime_workspace_finalize",
        creation_mode="creation_time_obligation",
        required_for_turn_completion=True,
    )
    turn.status = "post_write_pending"
    turn.visible_output_ref = output_ref
    save_turn(turn)
```

## 7.2 post-write job 派发

```python
def dispatch_post_write_jobs(turn_id: str, scheduler_result):
    for item in scheduler_result.selected_worker_executions:
        if item.requires_projection_refresh:
            create_job(
                turn_id=turn_id,
                job_kind="projection_refresh",
                creation_mode="derived",
                worker_id=item.worker_id,
                required_for_turn_completion=item.must_run,
            )
        if item.requires_proposal_submit:
            create_job(
                turn_id=turn_id,
                job_kind="proposal_submit",
                creation_mode="derived",
                worker_id=item.worker_id,
                required_for_turn_completion=False,
            )
```

## 7.3 turn settled 判定

```python
def evaluate_turn_settlement(turn_id: str):
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
    turn.settled_at = now()
    save_turn(turn)
    return True
```

## 8. 测试点

1. writer 返回后，creation-time obligations 必然创建
2. `Turn` child materials 都能通过 `turn_id` 追溯
3. branch switch 不携带别的分支 pending workspace
4. required jobs 未完成时 turn 不能 settled
5. retrieval raw materials 没有 usage record 时不能直接视为可完成
6. `trace_refs / source_ref_ids / result_ref_ids` 能串起一轮完整链路
7. rollback 后 cutoff 之后的 Runtime Workspace materials、pending jobs、packet/window metadata 必须 invalidated、hidden 或被 branch-visible reads 过滤
8. branch-visible read manifest / debug inspect / writer packet 构建必须证明 later branch materials 不会污染当前 active branch
9. LangGraph checkpoint pointer 只能作为 settled turn 的一次性技术锚点；重复捕获、debug replay 或 fork 不能覆盖已用于 rollback receipt 的应用层 binding

## 9. 已知风险

1. `StoryTurnRecord` 若字段塞太多，会再次变成“巨型记录”；实现时应把重内容放 refs，不把所有 payload 直接塞进 turn
2. `RuntimeWorkspaceMaterial` 生命周期枚举必须稳定，否则后续 debug 和 cleanup 规则会漂移
3. 若 job ledger 写得过轻，会丢失恢复能力；写得过重，又会退化成事件系统，必须守住边界
