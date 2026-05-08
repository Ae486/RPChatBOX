# Story Runtime Execution Plan

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Purpose: 作为实现阶段的总执行计划。后续的派遣、开发、check、spec 回写，都按本文件推进和维护。
>
> Status: active

## 1. 计划作用

这份文档不是 PRD，也不是架构规格书。

它只负责三件事：

1. 冻结实现阶段的执行纪律
2. 冻结切片顺序与完成定义
3. 维护当前推进状态，避免主脑和 subagent 漂移

## 2. 主脑必须遵守的规则

1. 主脑负责调度、收口、集成、维护计划，不把开发流程放飞给 subagent。
2. 主脑后续派遣、开发、check、spec 回写，都必须先对照本计划。
3. 主脑禁止直接编写或修改 runtime 业务实现代码、测试代码、前后端功能代码；实现类改动只能派发给 subagent 完成。主脑只负责派发、审阅、计划维护、规格/PRD回写、check 协调与结果收口。
4. 主脑一次最多只允许 `2` 个 subagent 同时运行。
5. 开发 subagent 固定使用：
   - `agent_type = trellis-implement`
   - `model = gpt-5.4`
   - `reasoning_effort = xhigh`
6. check subagent 固定使用：
   - `agent_type = trellis-check`
   - `model = GPT-5.5`
   - `reasoning_effort = xhigh`
7. 同一模块/功能下的连续子切片（例如 `F1/F2/.../Fx`）必须交给同一个开发 subagent 持续负责，直到该模块完成。
8. `trellis-check` 的粒度默认是模块级，而不是子切片级；例如 `F` 模块要等 `F1/F2/.../Fx` 全部完成后，再统一派一次模块级 check。
9. 不允许跳过 `trellis-check`；只是 check 的派发时点从“每个子切片后”调整为“每个完整模块后”。
10. 允许最多 `2` 个开发 subagent 并行，但主脑必须先确认它们各自负责不同模块/功能，且彼此无文件/合同/数据流冲突，也不存在前后依赖；无法证明独立时必须串行。
11. 本 task 的需求讨论、PRD、spec、开发规格书是唯一优先口径；旧 runtime / MVP 实现只作为迁移素材或反例参考，不作为合同来源。
12. 若当前正在开发的模块/功能被旧 runtime 链路阻碍，允许删除、绕过或替换旧链路；判断标准是是否更贴近当前 task 文档冻结的合同，而不是是否延续旧实现。
13. 主脑不因普通进展向用户停下来汇报；只有遇到真正的需求/设计问题，才进入 grill 队列。
14. 若问题能从已有 task 文档、spec、research、代码中直接推出，主脑直接定稿，不再反复提问。
15. 任何新发现的需求/设计问题，统一记录到：
   - [story-runtime-architecture-question-queue.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-architecture-question-queue.md)
16. 任何实现中获得的新工程知识，先继续完成当前模块；在模块通过 check 后，再判断是否进入 spec 更新。
17. 旧 longform MVP 代码只能作为 adapter 或迁移素材，不能反向定义新 runtime 合同。

## 3. 执行流

每个模块固定走下面的流程：

1. 主脑确认当前模块边界、子切片顺序、目标文件、完成标准
2. 派固定 `trellis-implement` subagent 持续完成该模块的各子切片
3. 主脑在每个子切片后审阅并集成产出，但不在模块中途切换开发 owner
4. 运行必要本地验证，继续推进该模块后续子切片
5. 模块全部完成后，派 `trellis-check` subagent 做一次模块级 check
6. 主脑处理 check findings
7. 更新本计划状态
8. 决定进入下一模块，或回到 grill/spec

## 4. 并发规则

### 4.1 硬限制

- 同时最多 `2` 个 subagent 在跑

### 4.2 默认模式

- 默认只跑 `1` 个开发 subagent
- 允许同时跑 `2` 个开发 subagent，但必须满足：
  - 两个 agent 分别负责不同模块/功能，而不是同一模块下的两个子切片
  - 两个任务的写入文件集合明确且不重叠
  - 两个任务不共享同一个未冻结合同
  - 一个任务的实现结果不是另一个任务的输入前置条件
  - 两个模块后续可以各自独立进入模块级 check
- 第 `2` 个名额也可用于：
  - explorer / research 辅助
  - trellis-check
  - 明确不冲突的并行子任务

### 4.3 当前推荐

- 实现阶段默认：
  - `1` 个 dev subagent
  - `0` 或 `1` 个 check/explorer subagent
- 若要启用第 `2` 个 dev subagent，主脑必须在派发前写清：
  - 各自负责的模块/功能
  - 各自 owned files / owned responsibility
  - 为什么无冲突
  - 为什么无依赖
  - 汇合后的验证方式

## 5. 状态标记

- `[ ]` 未开始
- `[>]` 进行中
- `[x]` 已完成
- `[!]` 阻塞，需 grill/spec

## 6. 切片总表

### Phase A: Runtime Identity / Snapshot / Entry Spine

- `[x]` A1. Session active anchor 收敛
  - 目标：
    - `StorySessionRecord` 持有 `active_branch_head_id`
    - `StorySessionRecord` 持有 `active_runtime_profile_snapshot_id`
    - session create / snapshot activate / default branch 创建后，这两个锚点有确定值
  - 主要文件：
    - `backend/models/rp_story_store.py`
    - `backend/rp/services/story_session_service.py`
    - `backend/rp/services/runtime_profile_snapshot_service.py`
    - `backend/rp/services/story_runtime_identity_service.py`
    - `backend/rp/tests/test_runtime_profile_snapshot_service.py`
    - `backend/rp/tests/test_story_runtime_identity_service.py`
  - 完成标准：
    - 新 session 不再只靠隐式默认
    - turn start 读取 session 的 active branch / active snapshot
    - 测试覆盖 session anchor 与 snapshot pin
  - 结果：
    - 已完成
    - `trellis-check` 通过
    - 未扩散到 branch control / rollback / scheduler

- `[x]` A2. Runtime profile compiled schema 收敛
  - 目标：
    - `compiled_profile_json` 对齐当前冻结最小 schema
    - 至少补齐：
      - `writer_policy`
      - `post_write_policy`
      - `budget_latency_policy`
  - 主要文件：
    - `backend/rp/models/runtime_identity.py`
    - `backend/rp/services/runtime_profile_snapshot_service.py`
    - `backend/rp/tests/test_runtime_profile_snapshot_service.py`
  - 结果：
    - 已完成
    - `trellis-check` 通过
    - writer contract 变化已纳入 snapshot revision 计算
    - 未提前接 scheduler / writer retrieval / post-write 消费链

- `[x]` A3. Graph entry identity / thread binding 收敛
  - 目标：
    - graph state 与 runtime identity 的入口一致
    - 不再把 graph thread 简单等同于 `session_id`
    - 为后续 branch-aware checkpoint 绑定留出正式入口
  - 主要文件：
    - `backend/rp/graphs/story_graph_state.py`
    - `backend/rp/graphs/story_graph_runner.py`
    - `backend/rp/graphs/story_graph_nodes.py`
    - `backend/rp/services/story_turn_domain_service.py`
  - 结果：
    - 已完成
    - `trellis-check` 通过
    - graph thread 已提升为 active-branch aware
    - 未引入 double turn allocation

### Phase B: Worker Registry / Scheduler Skeleton

- `[x]` B1. Worker contract / registry bootstrap
  - 结果：
    - 已完成
    - `trellis-check` 通过
    - runtime-centric worker contracts 已冻结第一版
    - bootstrap registry 只暴露 `LongformMemoryWorker` / `WritingWorker`

- `[x]` B2. Scheduler skeleton 接管固定 longform specialist 链
  - 结果：
    - 已完成
    - `trellis-check` 通过
    - `specialist_analyze` 已优先走 `WorkerSchedulerService -> WorkerExecutionService`
    - downstream 仍兼容 `SpecialistResultBundle`

### Phase C: Context Packet / Writer Entry

- `[x]` C1. WorkerContextPacket / WritingPacket contract 收敛
  - 结果：
    - 已完成
    - `trellis-check` 通过
    - `WritingPacket` 已具备 section family + 兼容扁平 `context_sections`
    - 最小 recent raw turn window 已接入

- `[x]` C2. Deterministic context orchestration 接入主链
  - 结果：
    - 已完成
    - 聚焦测试与 lint 通过
    - `WritingPacket` 组装已收敛到独立 `ContextOrchestrationService`
    - pre-write `WorkerContextPacket` 已从同一 deterministic orchestration 层产出并挂入 worker request
    - 未实现 writer retrieval loop、post-write scheduling、branch/rollback 扩展
  - 注意：
    - 当前相关文件与 A3 的 branch/thread 绑定改动共用部分文件；这是工作树重叠，不是新的需求漂移

### Phase D: Runtime Workspace / Retrieval Trace

- `[x]` D1. Runtime Workspace 主链化
  - 结果：
    - 已完成
    - `trellis-check` 通过
    - Runtime Workspace 已承接 `writer_input_ref / packet_ref / worker_evidence_bundle / worker_candidate / writer_output_ref`
    - 这些材料仍保持 scratch/evidence 语义，不进入 story truth

- `[x]` D2. retrieval card / expand / usage 主链化
  - 说明：
    - D2 先做 retrieval card / expand / usage 的 Runtime Workspace 数据契约与持久化闭环
    - E2 再接 writer-side retrieval loop 和 final usage gate
  - 结果：
    - 已完成
    - `trellis-check` 通过，无阻塞问题
    - retrieval usage record 已补齐 writer-facing short ids、backend-resolved material ids、derivable unused card refs、missed query refs 与可选 structured knowledge gaps
    - RuntimeReadManifest / trace 现已保留 runtime-private retrieval usage refs
    - 已补充两类边界回归测试：
      - `runtime_private` retrieval usage / miss 不进入 `visible_refs / selected_refs`
      - `record_writer_usage()` 对 missing ref / wrong kind / broken expanded parent 走 fail-closed
    - 未进入 writer retrieval loop、final usage gate、post-write scheduling 或 rollback

### Phase E: Writing Worker / Retrieval Loop

- `[x]` E1. WritingWorker runtime 收敛
  - 结果：
    - 已完成
    - `trellis-check` 通过，无阻塞问题
    - 主链已切到 structured `WritingWorkerExecutionRequest / WritingWorkerExecutionResult`
    - `WritingPacket` 已补齐 `identity / branch_head_id / turn_id / operation_mode / trace_refs`
    - `WritingWorkerExecutionService` 已退回 transport/executor 角色；turn-domain 负责 finalize 语义
    - Runtime Workspace 已主链记录 `writer_output_ref` 与 `token_usage_metadata`
    - 流式 writer 路径已补 usage capture，并通过 `writing_result` 落到 token usage material
    - longform rewrite 已改为：
      - rewrite 不再立刻 supersede 旧 draft
      - accept 才显式采用目标 draft，并把其他未采用 draft 收为 `SUPERSEDED`
      - longform 页面已暴露并显式选择 pending draft candidates
    - 本地验证通过：
      - `ruff check` 聚焦文件通过
      - `mypy --follow-imports=skip --check-untyped-defs` 聚焦文件通过
    - `pytest backend/rp/tests/test_projection_builder_services.py -q` 通过（30 passed）
    - `pytest backend/tests/test_rp_story_api.py -q` 通过（20 passed）
    - `dart analyze lib/models/story_runtime.dart lib/pages/longform_story_page.dart` 通过
    - 未进入 bounded retrieval loop、usage gate、post-write obligations/scheduler 重构
- `[x]` E2. writer-side bounded retrieval loop
  - 结果：
    - 已完成
    - `trellis-check` 通过
    - 真实用户主链 `/api/rp/story-sessions/{session_id}/turn/stream` 不再绕开 writer-side bounded retrieval loop
    - 当前实现采用窄路径：
      - 普通 one-shot non-retrieval stream 继续走 raw `stream_text`
      - 仅当 packet metadata 显式开启 `writer_retrieval_allowed=True` 且模型支持 tools 时，流式 turn 才走 buffered retrieval loop
    - buffered stream path 已直接复用完整 `WritingWorkerExecutionResult` 主链，不再依赖简化回填结果
    - artifact persistence / usage metadata / retrieval usage refs 已在 stream path 上保持完整
    - `Lorentz` 在 check 阶段修正了默认误分流问题：
      - `WritingWorkerExecutionService` 默认 `writer_retrieval_allowed=False`
      - `StoryTurnDomainService` 只接受显式 `writer_retrieval_allowed=True`
    - 补充并通过的验证包括：
      - `backend/rp/tests/test_writing_worker_retrieval_loop_service.py`
      - `backend/rp/tests/test_projection_builder_services.py`
      - `backend/tests/test_rp_story_api.py`
      - `ruff check ...`
      - `mypy --follow-imports=skip --check-untyped-defs ...`

### Phase F: Post-write Governance

- `[x]` F1. post-write trigger / creation-time obligations
- `[x]` F2. worker maintenance / governance / settlement

### Phase G: Branch / Rollback

- `[x]` G1. branch control receipt / active branch semantics
- `[x]` G2. rollback anchor / visibility transition / checkpoint binding

### Phase H: Adapter / Debug / Migration

- `[x]` H1. longform adapter 收敛
- `[x]` H2. debug / inspect / migration read surface

### Phase I: Finish

- `[x]` I1. final trellis-check
- `[x]` I2. trellis-update-spec

### Phase R: Longform Revision Overlay / Rewrite

- `[x]` R1. Draft Materialization / Anchor Contract
  - 结果：
    - writer markdown/plain text 已物化为稳定 `DraftDocumentRecord / DraftDocumentBlock`
    - anchor 不以 raw `\n` 作为 canonical 语义
    - block id、source range、excerpt fallback 已有聚焦测试覆盖

- `[x]` R2. Review Overlay Persistence
  - 结果：
    - overlay / comment / tracked change 已作为 Runtime Workspace sidecar 持久化
    - resolve/delete lifecycle 已覆盖
    - SuperDoc id 只作为 adapter metadata，不作为 runtime truth
    - 同 identity + same draft document + same mode 的 ensure/read 已保持幂等

- `[x]` R3. Rewrite Request / Packet Sidecar
  - 结果：
    - full rewrite / paragraph rewrite request builder 已完成
    - `review_overlay_sections` 通过既有 WritingPacket sidecar 注入，不新增 packet 顶层字段
    - full rewrite 无 explicit global instruction 时强制携带旧全文；有 explicit global instruction 时禁止携带旧全文
    - request metadata 已带 full runtime identity，并在后续服务 fail-closed 校验

- `[x]` R4. Rewrite Candidate / Patch Composer
  - 结果：
    - full rewrite candidate 与 paragraph patch-shaped candidate 已完成
    - paragraph rewrite 只支持单一 target scope，不做 batch rewrite
    - candidate 不自动 selected/adopted，不写 canonical truth
    - candidate record 自身 metadata 已带 full runtime identity

- `[x]` R5. Selection / Adoption / Continue
  - 结果：
    - selection receipt 可更改、可清除，不是 adoption
    - adoption 只由 `accept_and_continue` 语义产生
    - 单一 candidate 可直接采用；多个 candidate 必须 selection 或 explicit selected ref
    - adoption receipt 作为 Runtime Workspace sidecar 保存，并记录 active selection source refs

- `[x]` R6. Minimal Frontend Review Surface
  - 结果：
    - 后端新增 thin revision-review API，围绕 pending `story_segment` draft artifact 读取/保存修订面
    - Flutter native review surface 支持 `viewing / editing / suggesting`
    - 支持 candidate selector、draft 编辑保存、comment / tracked change 添加、comment resolve/delete
    - 未引入 SuperDoc/WebView/npm 新依赖；SuperDoc 仅作为 Word-style interaction substrate 参考
    - `Rewrite` / `Accept & Continue` 继续复用现有 longform command surface，不创建单独 rewrite worker
    - 模块级 check 两轮完成：
      - R1-R5 backend contract check 修复 identity collision、full rewrite old-text gate、request identity metadata、adoption source refs
      - R1-R6 check 修复 read ensure 幂等、candidate identity metadata、R6 API 专项测试覆盖

## 7. 当前执行策略

当前 `Longform Revision Overlay / Rewrite` 模块已完成 `R1-R6`，并通过两轮模块级 `trellis-check`。后续不应继续在 R 模块内扩 scope，下一步应切换到新的批次规划或由用户指定下一模块。

当前并行策略：

1. R 模块开发期间遵守单模块同一 dev agent 连续负责规则，由 Maxwell 负责 R1-R6。
2. R 模块后端合同完成后已做 R1-R5 模块级 check。
3. R6 frontend/API thin integration 完成后已做第二次 R1-R6 模块级 check。
4. 当前没有正在运行的 subagent。
5. 下一批如能证明与 R 模块无依赖/无文件冲突，可重新按并行规则派发。

此前 `F1/F2` 的推进理由保留如下：

1. `E2` 已收口，writer / retrieval / stream path 的主链语义已经站稳。
2. `Aquinas` 的只读摸底已经确认：
   - 当前没有现成的 obligation ledger
   - `StoryTurnDomainService.persist_generated_artifact(...)` 是最接近 creation-time obligations 的唯一 owner 边界
3. `F1` 应只做：
   - post-write trigger
   - creation-time obligations
   - 与 turn finalization 的衔接
4. `F1` 不应提前把完整 worker maintenance / projection / proposal / recall / archival 治理链一起拉进来；这些属于 `F2`。

## 8. A1 的额外纪律

1. A1 不进入 branch create/switch/delete 全量实现
2. A1 不进入完整 rollback 实现
3. A1 只解决：
   - session active branch / snapshot anchor
   - turn-start pin
   - 基本 identity propagation 所需的数据面
4. A1 完成后必须先跑 `trellis-check`
5. A1 通过前，不启动 A2

## 9. 维护规则

每次 slice 状态变化时，主脑必须同步更新本文件：

1. 把对应条目从 `[ ]` 改成 `[>]` 或 `[x]`
2. 若发现 blocker，改成 `[!]` 并写明原因
3. 若实现中拆出了新的必要子项，追加到所属 phase 的队尾
4. 若实现发现设计问题，先记入 grill 队列，再决定是否暂停

## 10. 当前工作树备注

E1 当前工作树的关键新增/收口点：

- 新增结构化 writer 合同：
  - `backend/rp/models/writing_worker_contracts.py`
- writer packet / turn-domain / graph 已切到 structured writer result 主链：
  - `backend/rp/models/writing_runtime.py`
  - `backend/rp/models/story_runtime.py`
  - `backend/rp/services/writing_worker_execution_service.py`
  - `backend/rp/services/story_turn_domain_service.py`
  - `backend/rp/graphs/story_graph_state.py`
  - `backend/rp/graphs/story_graph_nodes.py`
  - `backend/rp/graphs/story_graph_runner.py`
- Runtime Workspace 已补 writer output / token usage surface：
  - `backend/rp/services/story_runtime_workspace_facade.py`
- longform rewrite 语义已收口到“多 draft 候选 + 显式采用”：
  - `backend/rp/services/story_turn_domain_service.py`
  - `lib/models/story_runtime.dart`
  - `lib/pages/longform_story_page.dart`
- 当前下一刀入口已切换为 `F1. post-write trigger / creation-time obligations`
