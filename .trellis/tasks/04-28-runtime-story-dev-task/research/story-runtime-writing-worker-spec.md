# Story Runtime WritingWorker Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: WritingWorker / Longform Action Surface
>
> Status: draft-v1

## 1. 范围

本规格书负责冻结：

- `WritingWorker` 的职责边界
- writer operation modes
- longform action surface
- writer 执行请求/结果合同
- longform / roleplay / trpg 在 writer 层的共性和差异
- writer 与 review overlay / brainstorm / acceptance signal 的关系

这份文档不负责：

- retrieval card 结构
- worker registry/scheduler 公共合同
- packet 组装细节
- post-write memory 治理逻辑

## 2. 设计目标

这一层要解决 7 个问题：

1. `WritingWorker` 为什么是唯一用户可见输出 worker
2. brainstorm / discussion 和 writing / rewrite 为什么是同一 worker 的两种 operation mode
3. longform 为什么需要显式 draft adoption，而 RP/TRPG 不需要
4. writer 为什么不能直接改 `Core State`
5. writer 完成后怎样与 turn / workspace / post-write 对接
6. RP/TRPG 的 acceptance signal 如何在 writer 层体现
7. 为什么 writer-side retrieval 只作为受控工具能力，而不是自由 agent

## 3. 当前实现判断

当前后端里：

- `writing_worker_execution_service.py`
  - 已提供基础 LLM 调用与 streaming 壳

- `writing_runtime.py`
  - 已有 MVP `WritingPacket`

- `story_turn_domain_service.py`
  - 当前把 longform 的 orchestrator / specialist / writer 串成固定链

结论：

- 现有 `WritingWorkerExecutionService` 可复用为底层 LLM transport
- 但 `WritingWorker` 的真正合同、模式、状态与 adoption 语义，需要在规格书中独立冻结

## 4. 文件落位建议

## 4.1 复用现有文件

- `backend/rp/models/writing_runtime.py`
- `backend/rp/services/writing_worker_execution_service.py`
- `backend/rp/services/story_turn_domain_service.py`

## 4.2 新增文件建议

- `backend/rp/models/writing_worker_contracts.py`
- `backend/rp/services/writing_worker_service.py`
- `backend/rp/services/writing_output_selection_service.py`
- `backend/rp/services/longform_action_surface_service.py`

说明：

- `writing_worker_execution_service.py` 建议退化为 transport executor
- `writing_worker_service.py` 负责 operation mode、工具边界、结果封装

## 5. 核心职责

## 5.1 WritingWorker 负责什么

1. 消费 `WritingPacket`
2. 在受控边界内执行：
   - `writing`
   - `rewrite`
   - `discussion`
3. 如 policy 允许，可调用 writer-side retrieval loop
4. 产出结构化 writer result
5. 把结构化结果交回 turn-domain finalize API

## 5.2 WritingWorker 不负责什么

1. 不决定 block 路由
2. 不直接写 `Core State` authoritative truth
3. 不直接提交 proposal/apply
4. 不直接刷新 projection
5. 不负责选择 worker catalog

## 5.3 为什么是唯一用户可见输出 worker

冻结口径：

- story runtime 中，用户默认只看 `WritingWorker` 的可见输出
- orchestrator、memory worker、retrieval、post-write 都不直接把内部文本流给用户
- 这样才能保证：
  - 单一用户可见主链
  - 清晰的 turn 可见文本边界
  - rollback / branch 的恢复锚点稳定

## 6. Operation Modes

## 6.1 最小 operation modes

建议冻结：

- `writing`
- `rewrite`
- `discussion`

说明：

- `discussion` 即当前 longform 的 brainstorm/discussion 人格
- 不需要再新增一个独立 `brainstorm worker`
- `discussion` 的结果进入 summary/apply 链，而不是直接进入 writer 正文上下文

## 6.2 longform 下的行为

### writing

- 根据 accepted outline / chapter goal / core view / recent turns 输出正文

### rewrite

- 在当前 draft / review overlay / core view 基础上重写
- 产出新的 draft candidate
- 不自动替换 canonical version
- 当前阶段只保留两种 rewrite 语义：
  - `full rewrite`
  - `paragraph rewrite`
- `full rewrite` 只保留一种产品动作，但输入分两种：
  - 仅有全文批注、没有额外全文要求时：允许携带旧正文全文与全文批注，作为整篇重写参考。
  - 存在明确全文要求（即使为空字符串以外的任意要求）时：不携带旧正文全文，不做逐段对照底稿，而是基于当前确定版本的摘要/必要上下文和该要求重写整段正文。
- 其余场景统一落入 `paragraph rewrite`；review overlay / tracked changes / comments 主要服务这一类局部重写。

### discussion

- 回应用户对设定、大纲、伏笔、章节目标、当前段落方向的讨论
- 输出讨论文本
- 同时可形成 `brainstorm summary`
- 讨论结果不直接进入正文真相
- `discussion` 只服务 writer brainstorm，不承接明确修订/批注。明确的段落修改要求应进入 `review overlay -> rewrite`，而不是混入 discussion。

## 6.3 roleplay / trpg 下的行为

RP/TRPG 不做 longform 的显式多 draft adoption 流程。

冻结口径：

- 单个 `Turn` 只有当前一版正式可见结果
- 用户不满意时，走 branch，不走同 turn candidate tree
- writer 输出先作为 tentative visible material
- 用户下一条消息到来后，上一轮 output 进入 accepted-for-maintenance 语义

## 7. Action Surface

## 7.1 longform 产品动作

第一阶段冻结：

- `discussion / brainstorm`
- `rewrite`
- `accept_and_continue`
- `complete_chapter`

### 语义

- `discussion`
  - 进入 `discussion` operation mode

- `rewrite`
  - 进入 `rewrite` operation mode
  - 可以携带 review overlay
  - 默认先把修订/批注积累在 review overlay 中，不自动触发 rewrite
  - 用户显式执行“重写”动作后，review overlay 才被整理成 rewrite packet

- `accept_and_continue`
  - 不是新一轮写作结果
  - 是 deterministic action
  - 需要形成正式 `Turn`
  - 也是 longform draft adoption 的唯一确认动作

- `complete_chapter`
  - 是 deterministic action
  - 需要形成正式 `Turn`

## 7.2 RP/TRPG 产品动作

第一阶段最小动作：

- `user_input`
- `manual_refresh`
- `rule_card_submit`（TRPG）

其中：

- `user_input` 触发 writer 正文/互动输出
- `manual_refresh` 不直接进入 writer generation turn
- `rule_card_submit` 作为 sidecar 输入

## 8. 数据模型

## 8.1 WritingWorkerExecutionRequest

建议字段：

- `request_id: str`
- `identity: MemoryRuntimeIdentity`
- `operation_mode: str`
- `packet_ref: str | None`
- `packet: WritingPacket | dict`
- `writer_model_id: str`
- `writer_provider_id: str | None`
- `streaming: bool`
- `retrieval_allowed: bool`
- `max_retrieval_attempts: int`
- `metadata_json: dict`

## 8.2 WritingWorkerExecutionResult

建议字段：

- `turn_id: str`
- `operation_mode: str`
- `output_text: str`
- `output_kind: str`
- `usage_metadata: dict`
- `visible_output_ref: str | None`
- `candidate_output_ref: str | None`
- `selected_output_ref: str | None`
- `trace_refs: list[str]`
- `writer_tool_trace_refs: list[str]`
- `brainstorm_summary_ref: str | None`
- `result_status: str`
  - `completed`
  - `failed`

- `failure_reason: str | None`
- `metadata_json: dict`

关键约束：

- longform `rewrite` 结果不自动成为 canonical output
- RP/TRPG 结果默认就是当前 turn 的正式可见输出
- creation-time obligations 与 turn 状态推进不由 raw writer executor 直接拥有

## 8.3 LongformDraftSelectionReceipt

建议字段：

- `receipt_id: str`
- `turn_id: str`
- `candidate_output_refs: list[str]`
- `selected_output_ref: str`
- `selection_source: str`
  - `user_explicit_select`

- `selected_at: datetime`
- `metadata_json: dict`

关键约束：

- 只用于 longform
- RP/TRPG 不需要这套显式 adoption receipt
- 它表示“当前暂定选中的正文版本”，不等于已经 adopted 的 canonical continuation base

## 8.4 LongformDraftAdoptionReceipt

建议字段：

- `receipt_id: str`
- `turn_id: str`
- `adopted_output_ref: str`
- `adopted_at: datetime`
- `adoption_source: str`
  - `accept_and_continue`

- `metadata_json: dict`

关键约束：

- 只在用户点击 `accept_and_continue / 续写` 时生成
- 这是 longform canonical continuation base 的正式记录
- 下一轮 writer / post-write / branch-visible continuation 只认 adoption receipt，不认单纯 selection state

## 8.5 BrainstormSummaryRecord

建议字段：

- `summary_id: str`
- `turn_id: str`
- `summary_items: list[SummaryItem]`
- `status: str`
  - `draft`
  - `applied`
  - `stale`
  - `rejected`

- `created_at: datetime`
- `updated_at: datetime`

### SummaryItem

建议字段：

- `summary_item_id: str`
- `type: str`
  - `setting_change`
  - `outline_change`
  - `chapter_goal_change`
  - `foreshadow_change`
  - `open_idea`

- `text: str`
- `rejected: bool`
- `edited_text: str | None`

## 9. 运行规则

## 9.1 longform rewrite 规则

1. rewrite 产生新的 draft candidate
2. 旧版本不删除
3. 用户可以暂定选择当前正文版本，但该选择可解除、可改选
4. 只有点击 `accept_and_continue / 续写` 时，当前被选中的版本才真正 adopted
5. 若当前轮只有唯一一版候选，点击 `accept_and_continue / 续写` 即视为采用该唯一候选
6. 若当前轮存在多个候选，必须先显式选择一版，再点击 `accept_and_continue / 续写`
7. `accept_and_continue` 只能基于点击时的 adopted draft 进入下一轮继续写作

## 9.2 brainstorm 规则

1. `discussion` 只负责讨论和总结 change summary
2. 不直接改 block
3. 不直接进 writer 正文上下文
4. 用户确认后，调度器再派 worker 应用到 core
5. 若未确认而继续写作，则 summary 自动 stale

## 9.3 RP/TRPG acceptance signal

冻结口径：

- writer output 返回后立即可见
- 但只是 tentative material
- 用户发送下一条消息后，上一轮进入 accepted-for-maintenance
- 这不是新的 control action turn，而是新 user turn 创建时顺带推进上一轮 acceptance

## 9.4 writer 与 retrieval 的关系

冻结口径：

- writer 可以判断知识不足
- 可以发起 writer-side retrieval
- 但 retrieval 只在受控 loop 中进行
- writer 不拥有自由工具 agent 权限

## 9.5 review/comment lifecycle

冻结口径：

- review overlay / comment 是修订意图，不是 canonical truth。
- rewrite 之后，comment 默认不自动 resolve，也不自动删除。
- 是否满足由用户显式决定；用户可 resolve、保留或删除。
- resolved comment 默认从主修订视图收起，但仍保留锚点、provenance 和 trace，便于回看与导出。

## 10. 伪代码

## 10.1 Run writing/rewrite

```python
def run_writing_worker(request: WritingWorkerExecutionRequest) -> WritingWorkerExecutionResult:
    packet = ensure_writing_packet(request)
    text, usage, tool_trace_refs = run_writer_with_optional_retrieval_loop(
        packet=packet,
        model_id=request.writer_model_id,
        provider_id=request.writer_provider_id,
        operation_mode=request.operation_mode,
        retrieval_allowed=request.retrieval_allowed,
        max_retrieval_attempts=request.max_retrieval_attempts,
    )
    return WritingWorkerExecutionResult(
        turn_id=request.identity.turn_id,
        operation_mode=request.operation_mode,
        output_text=text,
        output_kind=packet.output_kind,
        usage_metadata=usage,
        writer_tool_trace_refs=tool_trace_refs,
        result_status="completed",
    )
```

## 10.2 Finalize writer output

```python
def finalize_writer_output(identity, worker_result):
    output_ref = persist_visible_output(
        identity=identity,
        text=worker_result.output_text,
        output_kind=worker_result.output_kind,
    )
    persist_usage_metadata(identity, worker_result.usage_metadata)
    ensure_creation_time_obligations(identity.turn_id)
    mark_turn_post_write_pending(identity.turn_id)

    if worker_result.operation_mode == "rewrite":
        worker_result.candidate_output_ref = output_ref
        worker_result.selected_output_ref = None
    else:
        worker_result.visible_output_ref = output_ref
        worker_result.selected_output_ref = output_ref
    return worker_result
```

补充口径：

- `selected_output_ref` 在 longform 下最多表示“当前默认可见版本”或“暂定选中版本”，不是 adoption 本身。
- adoption 必须在 `accept_and_continue` 路径中单独记录。

## 10.3 Run discussion

```python
def run_discussion_mode(request: WritingWorkerExecutionRequest) -> WritingWorkerExecutionResult:
    packet = ensure_writing_packet(request)
    text, usage, tool_trace_refs = run_writer_with_optional_retrieval_loop(
        packet=packet,
        model_id=request.writer_model_id,
        provider_id=request.writer_provider_id,
        operation_mode="discussion",
        retrieval_allowed=request.retrieval_allowed,
        max_retrieval_attempts=request.max_retrieval_attempts,
    )
    summary_ref = build_brainstorm_summary(
        identity=request.identity,
        discussion_text=text,
    )
    return WritingWorkerExecutionResult(
        turn_id=request.identity.turn_id,
        operation_mode="discussion",
        output_text=text,
        output_kind="discussion_message",
        usage_metadata=usage,
        writer_tool_trace_refs=tool_trace_refs,
        brainstorm_summary_ref=summary_ref,
        result_status="completed",
    )
```

## 11. 测试点

1. longform `rewrite` 不自动覆盖 canonical draft
2. discussion 生成 summary，但不直接改 core
3. 未 apply 的 discussion summary 在继续写作后变 stale
4. RP/TRPG 下一条用户消息会推进上一轮 acceptance
5. writer 输出始终是唯一用户可见输出
6. deterministic actions 不走 writer generation

## 12. 已知风险

1. 如果 dev 把 brainstorm summary 直接当作 block proposal，会再次把 writer 和 memory governance 职责混掉
2. 若 longform rewrite 不保留显式 selection receipt，后续继续写作和 rollback 恢复会混乱
3. 若 RP/TRPG 重新引入“同 turn candidate tree”，会与已冻结的 branch 语义冲突
