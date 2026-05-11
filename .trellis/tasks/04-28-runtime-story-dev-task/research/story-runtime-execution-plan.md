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
   - `agent_type = default`（prompt 中按 trellis-implement 标准执行）
   - `model = gpt-5.4`
   - `reasoning_effort = xhigh`
6. check subagent 固定使用：
   - `agent_type = default`（prompt 中按 trellis-check 标准执行）
   - `model = gpt-5.5`
   - `reasoning_effort = xhigh`
   - 注意：当前 `agent_type = trellis-check` 会被角色配置覆盖成 `gpt-5.4 high`，不能用于需要 `gpt-5.5 xhigh` 的 check 派发。
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
18. subagent 在 implement/check 中遇到口径、需求或设计问题时，必须先穷尽当前 task 文档、PRD、spec、开发规格书、项目既有实现和成熟框架/项目的常见处理方式；只有确认现有材料无法安全推出、且该问题会影响实现或验证时，才向主脑升级为 grill-me 问题，并写入 question queue。不得把拿不准的问题临场拍成新口径。
19. subagent 必须遵守当前工程规范：有项目内框架/服务/轮子优先复用；glue coding 只是规范之一，不是目标本身；新增抽象或新依赖必须证明它减少工作量且不破坏已冻结 runtime truth / snapshot / branch / memory governance 边界。

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

### Phase J: LangGraph Branch / Rollback Preflight

- `[x]` J1. LangGraph Branch / Rollback Preflight
  - 结果：
    - 已产出 `research/story-runtime-langgraph-branch-rollback-preflight.md`
    - 结论：LangGraph 可继续作为 checkpoint / replay / fork / debug history 的薄执行壳，但不能替代 RP 应用层 branch / rollback 真相
    - 当前代码已具备应用层 branch / rollback、turn-scoped job ledger、Runtime Workspace invalidation、branch-aware read scope 和 debug inspect surface
    - 下一最小实现 slice 应聚焦 `GraphCheckpointPointer capture / binding`，把 settled turn 与 LangGraph checkpoint pointer 自动绑定
    - 模块级 check 已补齐后续能力验证要求：checkpoint binding、rollback receipt binding / missing reason、branch create/switch 不造 turn、rollback 后 later materials 不污染当前主线、LangGraph debug/replay/fork 不替代 RP 应用层 truth
    - 暂不进入完整 branch UI、physical purge、branch merge、跨分支 Evolution 管理或 R 模块功能改动

- `[x]` J2. GraphCheckpointPointer capture / binding
  - 结果：
    - `StoryGraphRunner` 在 non-stream `ainvoke` finalize 后、stream `aupdate_state(... as_node="finalize_turn")` 后捕获 LangGraph snapshot checkpoint pointer
    - checkpoint pointer 只写入已 `settled` turn 对应 branch metadata：`graph_checkpoint_binding` 与 `graph_checkpoint_bindings_by_turn_id[turn_id]`
    - binding 字段包含 `graph_thread_id / checkpoint_ns / checkpoint_id / parent_checkpoint_id / captured_after_node / captured_at / turn_id / branch_head_id / runtime_profile_snapshot_id`
    - `rollback_to_turn()` 从目标 settled turn 所属 branch metadata 自动解析 checkpoint binding；调用方传入的 checkpoint id / binding 只记录为 ignored input，不作为 truth
    - 目标 turn 缺少 binding 时，rollback 仍按应用层 visibility contract 成功，并在 receipt metadata 写入 `checkpoint_binding_missing_reason=target_turn_has_no_graph_checkpoint_binding`
    - 同一 settled turn 的 checkpoint pointer 一次绑定后保持幂等；后续 debug/replay/fork 或重复 finalize 捕获到的新 LangGraph checkpoint 不覆盖原应用层回退锚点
    - branch create / switch 不创建 story turn 的既有合同保持不变；rollback 后 later turns / Runtime Workspace materials / branch-visible read head 的既有合同保持不变
    - LangGraph checkpoint pointer 只作为技术锚点；settled / job-ledger / visibility 判定仍由 RP 应用层负责
  - 验证：
    - `pytest backend\rp\tests\test_story_runtime_identity_service.py -q`
    - `pytest backend\rp\tests\test_projection_builder_services.py::test_story_graph_runner_stream_persists_usage_metadata_into_writing_result backend\rp\tests\test_projection_builder_services.py::test_graph_thread_binding_reports_rollback_visible_turn_head -q`
    - `ruff check backend\rp\services\story_runtime_identity_service.py backend\rp\services\story_turn_domain_service.py backend\rp\graphs\story_graph_nodes.py backend\rp\graphs\story_graph_runner.py backend\rp\tests\test_story_runtime_identity_service.py backend\rp\tests\test_projection_builder_services.py`
    - `mypy --follow-imports=skip --check-untyped-defs backend\rp\services\story_runtime_identity_service.py backend\rp\services\story_turn_domain_service.py backend\rp\graphs\story_graph_nodes.py backend\rp\graphs\story_graph_runner.py`

- `[x]` J3. J module-level trellis-check
  - 结果：
    - check 修复同一 settled turn 的 `graph_checkpoint_binding` 可被后续 capture 覆盖的问题
    - checkpoint binding 现在一次绑定后幂等返回原 binding，debug / replay / fork 产生的新 LangGraph checkpoint 不能替代 RP 应用层 rollback 锚点
    - 补充“重复 capture 不覆盖 settled turn binding”的回归测试
    - 同步补充 J 模块相关文档与 `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md` 的幂等边界
  - 验证：
    - `ruff check backend\rp\services\story_runtime_identity_service.py backend\rp\services\story_turn_domain_service.py backend\rp\graphs\story_graph_nodes.py backend\rp\graphs\story_graph_runner.py backend\rp\tests\test_story_runtime_identity_service.py backend\rp\tests\test_projection_builder_services.py`
    - `mypy --follow-imports=skip --check-untyped-defs backend\rp\services\story_runtime_identity_service.py backend\rp\services\story_turn_domain_service.py backend\rp\graphs\story_graph_nodes.py backend\rp\graphs\story_graph_runner.py`
    - `pytest backend\rp\tests\test_story_runtime_identity_service.py -q`
    - `pytest backend\rp\tests\test_projection_builder_services.py::test_story_graph_runner_stream_persists_usage_metadata_into_writing_result backend\rp\tests\test_projection_builder_services.py::test_graph_thread_binding_reports_rollback_visible_turn_head backend\rp\tests\test_projection_builder_services.py::test_story_graph_runner_pins_runtime_identity_before_special_command -q`
    - `pytest backend\rp\tests\test_memory_lineage_services.py::test_branch_visibility_resolver_hides_rollback_future_but_allows_new_future -q`
    - `pytest backend\rp\tests\test_memory_lineage_services.py::test_runtime_read_manifest_service_is_deterministic_and_separates_visible_selected_omitted -q`
    - `pytest backend\tests\test_rp_story_api.py::test_story_runtime_debug_exposes_checkpoint_state -q`

### Phase K: Runtime Acceptance / Minimal Runnable Loop

- `[x]` K1. first-stage runtime acceptance
  - 结果：
    - longform writing turn 最小闭环已通过现有 stream 主链测试验证：用户 `WRITE_NEXT_SEGMENT` 输入进入 writer，产出 `story_segment` draft artifact，Runtime Workspace 记录 `writer_input_ref / packet_ref / writer_output_ref / token_usage_metadata` 的具体 payload 和引用链，turn 以 `settled` 状态完成，并保留 post-write/job settlement 与 graph checkpoint binding。
    - 下一轮 continuation base 的 canonical 入口已用 revision/adoption 测试收口：selection 不等于 adoption；只有 `accept_and_continue` 采用的 candidate 才会成为 `canonical_continuation_base`，未采用 candidate 不进入续写基底。
    - rollback 回归已验证：目标 checkpoint binding 作为技术锚点随 receipt 携带；重复 capture 不覆盖首个 settled turn binding；rollback 后 later turns / workspace materials / branch-visible chapter reads 不污染当前主线。
    - PRD 剩余两项 acceptance criteria 已在测试通过后勾选。
    - 本阶段未进入完整 branch UI、physical purge、branch merge、跨分支 Evolution 或完整 roleplay/TRPG runtime。
  - 验证：
    - `pytest backend\rp\tests\test_projection_builder_services.py::test_story_graph_runner_stream_persists_usage_metadata_into_writing_result -q`
    - `pytest backend\rp\tests\test_draft_selection_service.py::test_next_continuation_base_ignores_unadopted_revision_candidates -q`
    - `pytest backend\rp\tests\test_story_runtime_identity_service.py::test_rollback_read_scope_hides_later_materials_and_keeps_checkpoint_anchor -q`

- `[x]` K2. K module-level trellis-check
  - 结果：
    - check 补强 `test_story_graph_runner_stream_persists_usage_metadata_into_writing_result`，让 Runtime Workspace 的 `writer_input_ref / packet_ref / writer_output_ref / token_usage_metadata` 验证具体 payload、`source_refs` 和用户写作指令进入 writer packet 的证据，而不是只验证材料数量。
    - check 补强 `test_rollback_read_scope_hides_later_materials_and_keeps_checkpoint_anchor`，显式验证 rollback 后 active branch head / last settled turn 回到目标 turn，later turn 进入 `hidden_by_rollback`，workspace material 被 invalidated，branch-visible chapter snapshot 不暴露 cutoff 之后的 artifact / discussion / pending pointer。
    - PRD 两个剩余勾选项保持有效：K focused tests、相关 identity / draft selection 回归、branch visibility/debug 回归、lint 和 typecheck 均通过。
    - 本阶段未扩大到完整 branch UI、physical purge、branch merge、跨分支 Evolution、完整 roleplay/TRPG runtime。
  - 验证：
    - `pytest backend\rp\tests\test_projection_builder_services.py::test_story_graph_runner_stream_persists_usage_metadata_into_writing_result backend\rp\tests\test_draft_selection_service.py::test_next_continuation_base_ignores_unadopted_revision_candidates backend\rp\tests\test_story_runtime_identity_service.py::test_rollback_read_scope_hides_later_materials_and_keeps_checkpoint_anchor -q`
    - `pytest backend\rp\tests\test_story_runtime_identity_service.py -q`
    - `pytest backend\rp\tests\test_draft_selection_service.py -q`
    - `pytest backend\rp\tests\test_projection_builder_services.py::test_story_graph_runner_stream_persists_usage_metadata_into_writing_result backend\rp\tests\test_projection_builder_services.py::test_graph_thread_binding_reports_rollback_visible_turn_head backend\rp\tests\test_projection_builder_services.py::test_story_turn_domain_service_marks_consumers_synced -q`
    - `pytest backend\rp\tests\test_memory_lineage_services.py::test_branch_visibility_resolver_hides_rollback_future_but_allows_new_future backend\rp\tests\test_memory_lineage_services.py::test_runtime_read_manifest_service_is_deterministic_and_separates_visible_selected_omitted backend\tests\test_rp_story_api.py::test_story_runtime_debug_exposes_checkpoint_state -q`
    - `ruff check backend\rp\services\story_runtime_identity_service.py backend\rp\services\story_turn_domain_service.py backend\rp\graphs\story_graph_nodes.py backend\rp\graphs\story_graph_runner.py backend\rp\tests\test_story_runtime_identity_service.py backend\rp\tests\test_projection_builder_services.py backend\rp\tests\test_draft_selection_service.py`
    - `mypy --follow-imports=skip --check-untyped-defs backend\rp\services\story_runtime_identity_service.py backend\rp\services\story_turn_domain_service.py backend\rp\graphs\story_graph_nodes.py backend\rp\graphs\story_graph_runner.py`

- `[x]` K3. trellis-update-spec
  - 结果：
    - 已更新 `.trellis/spec/backend/rp-runtime-workspace-turn-material-store.md`
    - 新增 first-stage longform runtime acceptance 合同，明确最小可运行闭环不能只验证 Workspace rows 存在，必须验证 writer input / packet / output / token usage / source refs / settlement / checkpoint binding
    - 补入 revision/adoption continuation base、rollback read-scope 回归、checkpoint binding 技术锚点的测试要求与 wrong/correct 示例

### Phase L: Runtime Config Surface

- `[x]` L1. runtime config control plane / snapshot publish
  - 目标：
    - runtime 配置侧只改变系统怎么跑，不进入 story turn，不参与 story rollback
    - runtime panel patch 发布新 `RuntimeProfileSnapshot`
    - 配置变更进入 control history
    - 已开始 turn / pending post-write job 继续使用旧 snapshot
  - 规格：
    - [story-runtime-runtime-config-surface-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-runtime-config-surface-development-spec.md)
  - 主要文件候选：
    - `backend/rp/models/runtime_config_contracts.py`
    - `backend/rp/services/runtime_config_control_service.py`
    - `backend/rp/services/runtime_profile_snapshot_service.py`
    - `backend/rp/services/story_runtime_controller.py`
    - `backend/api/rp_story.py`
  - 完成标准：
    - 新 snapshot publish / activate 有聚焦测试
    - in-progress turn / pending job snapshot pin 不漂移
    - control history 可读且不被 story rollback 回退
  - 结果：
    - 已完成
    - runtime config patch 通过 control service 做 fail-closed 校验，写入既有 `StorySession.runtime_story_config_json`，再发布新的 immutable `RuntimeProfileSnapshot`
    - 新增 control history receipt，记录 previous/new snapshot、changed fields、actor/source/reason，并提供 history read API
    - 已开始 turn 与 pending workflow job 保持创建时 pinned snapshot；story rollback 不删除、不回退 runtime config history
    - 旧 snapshot 的 `compiled_profile_json` 不原地修改
  - 验证：
    - `pytest backend\rp\tests\test_runtime_config_control_service.py backend\tests\test_rp_story_api.py::test_story_runtime_config_patch_updates_session_snapshot backend\rp\tests\test_runtime_profile_snapshot_service.py backend\rp\tests\test_story_runtime_controller_memory_read_side.py::test_story_runtime_controller_patch_publishes_new_active_snapshot -q`
    - `ruff check backend\rp\models\runtime_config_contracts.py backend\rp\services\runtime_config_control_service.py backend\rp\services\runtime_profile_snapshot_service.py backend\rp\services\story_runtime_controller.py backend\rp\runtime\rp_runtime_factory.py backend\api\rp_story.py backend\models\rp_story_store.py backend\services\database.py backend\rp\tests\test_runtime_config_control_service.py backend\tests\test_rp_story_api.py`
    - `mypy --follow-imports=skip --check-untyped-defs backend\rp\models\runtime_config_contracts.py backend\rp\services\runtime_config_control_service.py backend\rp\services\runtime_profile_snapshot_service.py backend\rp\services\story_runtime_controller.py backend\rp\runtime\rp_runtime_factory.py backend\api\rp_story.py`

### Phase M: Story Evolution Foundation

- `[x]` M1. Story Evolution / Archival evolution governance
  - 目标：
    - Story Evolution 默认 current-branch visible
    - Archival edits 走 version / supersession / reindex receipt
    - retrieval 排除 hidden / superseded evolved chunks
    - Core proposal 可追溯到 evolved archival version
  - 规格：
    - [story-runtime-story-evolution-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-story-evolution-development-spec.md)
  - 主要文件候选：
    - `backend/rp/models/story_evolution_contracts.py`
    - `backend/rp/services/story_evolution_service.py`
    - `backend/rp/services/archival_evolution_service.py`
    - `backend/rp/services/runtime_memory_persistence_repository.py`
    - `backend/rp/services/retrieval_maintenance_service.py`
  - 完成标准：
    - branch-scoped evolution / selected branches / story-global visibility 均有测试
    - reindex job 和 memory event 与 evolution receipt 可追溯
    - 不新增平行 StoryEvolutionWorker 主链
  - 结果：
    - 已完成 M1 最小后端 foundation
    - 新增 story-level `StoryEvolutionRequest / StoryEvolutionReceipt` 与 `StoryEvolutionService` facade，只路由 Archival edit/import 到现有 `ArchivalEvolutionService`
    - Core raw write 通过 story evolution facade fail-closed，仍要求走 governed Core mutation / proposal/apply
    - Archival evolution 已覆盖 current-branch default、selected branches、all existing branches、story-global、version/supersession、reindex job、memory event、hidden/superseded retrieval filtering
    - 后续 Core proposal 可携带 evolved archival source/chunk version refs，并通过既有 proposal governance metadata 追溯
    - 未新增平行 StoryEvolutionWorker、平行 retrieval-core、平行 proposal/apply 或平行 truth
  - 验证：
    - `pytest backend/rp/tests/test_archival_evolution_service.py -q`
    - `pytest backend/rp/tests/test_memory_inspection_service.py::test_archival_evolution_routes_through_governed_service -q`
    - `pytest backend/rp/tests/test_memory_lineage_services.py::test_branch_visibility_resolver_tracks_active_lineage_and_parent_cutoff backend/rp/tests/test_memory_lineage_services.py::test_branch_visibility_resolver_hides_rollback_future_but_allows_new_future -q`
    - `ruff check backend/rp/models/story_evolution_contracts.py backend/rp/services/story_evolution_service.py backend/rp/services/archival_evolution_service.py backend/rp/tests/test_archival_evolution_service.py`
    - `mypy --follow-imports=skip --check-untyped-defs backend/rp/models/story_evolution_contracts.py backend/rp/services/story_evolution_service.py backend/rp/services/archival_evolution_service.py backend/rp/tests/test_archival_evolution_service.py`

### Phase N: Longform Chapter / Review Adapter

- `[x]` N1. longform chapter lifecycle provider / adapter
  - 目标：
    - chapter bridge provider 只消费 adopted draft / accepted outline / chapter goal
    - `complete_chapter` 不读取未采用 candidate
    - 旧 longform MVP 入口只能作为 adapter，不能反向定义 truth
  - 规格：
    - [story-runtime-longform-chapter-review-adapter-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-longform-chapter-review-adapter-development-spec.md)
  - 主要文件候选：
    - `backend/rp/models/longform_chapter_contracts.py`
    - `backend/rp/services/chapter_bridge_provider.py`
    - `backend/rp/services/longform_chapter_runtime_service.py`
    - `backend/rp/services/story_turn_domain_service.py`
    - `backend/rp/services/draft_selection_service.py`
  - 完成标准：
    - complete chapter / next chapter base 使用 adoption receipt
    - discussion/rewrite/review 与 chapter transition 不混线
    - branch switch 不泄漏其他分支 pending revision/chapter bridge
  - 结果：
    - 已完成并通过模块级 check
    - `complete_chapter` 已从 legacy pending draft 收口到只认 adopted draft / accepted outline / chapter goal
    - 有 pending rewrite candidate 时，没有 adoption receipt 会 fail-closed；无 pending draft 时保留已接受 segment 的兼容路径
    - chapter bridge 作为 branch/turn-scoped Runtime Workspace sidecar 记录，不创建平行 chapter truth
    - check 修复了 bridge material 未进入下一轮 writer packet 的问题：Context Orchestration 现在按 current branch + target chapter 读取最新 bridge，并组装 `mode_sidecar_sections`
    - runtime factory / turn-domain 注入链已接入 `LongformChapterRuntimeService`
  - 验证：
    - `pytest backend\rp\tests\test_longform_chapter_runtime_service.py -q`
    - `pytest backend\rp\tests\test_draft_selection_service.py -q`
    - `pytest backend\rp\tests\test_projection_builder_services.py::test_writing_packet_builder_uses_projection_sections_and_runtime_hints backend\rp\tests\test_projection_builder_services.py::test_writing_packet_builder_has_no_raw_retrieval_hit_surface backend\rp\tests\test_projection_builder_services.py::test_context_orchestration_service_builds_minimal_worker_context_packet backend\rp\tests\test_projection_builder_services.py::test_story_turn_domain_service_build_packet_routes_through_context_orchestration_service backend\rp\tests\test_mode_extension_slots.py::test_context_orchestration_mounts_trpg_sidecars_without_new_packet_fields -q`
    - `ruff check backend\rp\services\longform_chapter_runtime_service.py backend\rp\services\context_orchestration_service.py backend\rp\services\story_turn_domain_service.py backend\rp\runtime\rp_runtime_factory.py backend\rp\tests\test_longform_chapter_runtime_service.py`
    - `mypy --follow-imports=skip --check-untyped-defs backend\rp\services\longform_chapter_runtime_service.py backend\rp\services\context_orchestration_service.py backend\rp\services\story_turn_domain_service.py backend\rp\runtime\rp_runtime_factory.py`

### Phase O: Roleplay / TRPG Extension Slots

- `[x]` O1. roleplay / TRPG extension slot contract
  - 目标：
    - roleplay / TRPG 通过 ModeProfile / snapshot / registry 扩展，不新建 longform-only 分支链
    - 预留 `CharacterMemoryWorker / SceneInteractionWorker / RuleStateWorker`
    - 预留 `RULE_CARD / RULE_STATE_CARD` Runtime Workspace material
    - 验证 extension slot 可挂载，不要求完整 RP/TRPG runtime
  - 规格：
    - [story-runtime-roleplay-trpg-extension-slots-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-roleplay-trpg-extension-slots-development-spec.md)
  - 主要文件候选：
    - `backend/rp/models/mode_extension_contracts.py`
    - `backend/rp/models/runtime_workspace_material.py`
    - `backend/rp/services/story_worker_registry_service.py`
    - `backend/rp/services/worker_scheduler_service.py`
    - `backend/rp/services/context_orchestration_service.py`
    - `backend/rp/services/story_runtime_workspace_facade.py`
  - 完成标准：
    - roleplay / TRPG descriptors 可编译进 snapshot
    - scheduler 不通过 mode hardcode 识别 extension worker
    - rule card/state card 作为 branch-scoped turn materials 保存，不进入 truth
  - 结果：
    - 已完成并通过模块级 check
    - roleplay / TRPG extension slots 已编译进 pinned snapshot
    - worker registry / scheduler 可通过 snapshot + registry 发现 extension worker，不靠 mode hardcode
    - 缺失 executor 时会 degrade 并保留 trace
    - `RULE_CARD / RULE_STATE_CARD` 可作为 branch-scoped Runtime Workspace turn material 挂入 packet sidecar，不进入 Core / Recall / Archival truth
    - check 修复了 `WorkerContextPacket.sidecar_refs` 未按 `context_requirements.sidecar_slot_ids` 过滤的问题
    - check 修复了 rule card / state card provenance 只存在 payload、未进入 Runtime Workspace 正式 `source_refs` 的问题
  - 验证：
    - `pytest backend\rp\tests\test_mode_extension_slots.py -q`
    - `pytest backend\rp\tests\test_runtime_profile_snapshot_service.py backend\rp\tests\test_worker_registry_service.py backend\rp\tests\test_worker_scheduler_service.py -q`
    - `ruff check backend\rp\models\mode_extension_contracts.py backend\rp\services\runtime_profile_snapshot_service.py backend\rp\services\worker_registry_service.py backend\rp\services\worker_execution_service.py backend\rp\services\story_runtime_workspace_facade.py backend\rp\services\context_orchestration_service.py backend\rp\tests\test_mode_extension_slots.py`
    - `mypy --follow-imports=skip --check-untyped-defs backend\rp\services\context_orchestration_service.py backend\rp\services\story_runtime_workspace_facade.py`

### Phase P: Runtime Surface / Debug / API Hardening

- `[x]` P1. runtime config / story evolution / chapter bridge / extension sidecar read surfaces
  - 目标：
    - 已实现的 L/M/N/O 后端能力必须有可审查的 read/debug/API 面
    - runtime config control history 可从 story session 读取
    - story evolution history / archival evolution receipts 可通过现有 memory inspection 或 thin API 读取
    - chapter bridge material 可在 debug/inspect surface 中按 branch/target chapter 查看
    - extension sidecars 的 packet/debug/provenance read 不需要解析 payload 内部私有字段
    - check 收紧 debug packet section family，仅保留 `section_family` / `source_kind` / `section_id` 作为稳定分类入口
  - 规格：
    - [story-runtime-adapter-debug-test-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-adapter-debug-test-spec.md)
    - [story-runtime-runtime-config-surface-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-runtime-config-surface-development-spec.md)
    - [story-runtime-story-evolution-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-story-evolution-development-spec.md)
    - [story-runtime-longform-chapter-review-adapter-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-longform-chapter-review-adapter-development-spec.md)
    - [story-runtime-roleplay-trpg-extension-slots-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-roleplay-trpg-extension-slots-development-spec.md)
  - 主要文件候选：
    - `backend/rp/services/story_runtime_debug_query_service.py`
    - `backend/rp/services/story_runtime_controller.py`
    - `backend/api/rp_story.py`
    - `backend/rp/tests/test_story_runtime_debug_query_service.py`
    - `backend/tests/test_rp_story_api.py`
  - 完成标准：
    - read/debug/API surfaces 只读，不新增 truth
    - exact identity / branch scoped reads 不泄漏 sibling branch material
    - L/M/N/O 的 receipts/materials/source_refs 能被 inspect/debug 查询到

- `[x]` P2. second-stage regression matrix
  - 目标：
    - 为 L/M/N/O 建立一组跨模块回归，证明第二阶段能力组合后不互相污染
    - 覆盖 snapshot hot update、Story Evolution visibility、chapter bridge packet、TRPG sidecar packet/source_refs
  - 规格：
    - [story-runtime-adapter-debug-test-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-adapter-debug-test-spec.md)
    - [story-runtime-context-packet-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-context-packet-spec.md)
    - [story-runtime-workspace-ledger-trace-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-workspace-ledger-trace-spec.md)
  - 主要文件候选：
    - `backend/rp/tests/test_story_runtime_second_stage_regression.py`
    - existing focused tests only when needed
  - 完成标准：
    - focused regression proves second-stage surfaces compose without story truth drift
    - no full roleplay/TRPG runtime, no full UI, no new worker executor implementation
    - final check 验证了 O/P strict recheck 回归、runtime surface API、以及 L/M/N 相关服务验证

### Phase Q: Runtime Product Acceptance / User-facing Integration Gate

- `[x]` Q1. product acceptance matrix / backend scenario tests
  - 目标：
    - 用 product-like backend scenario tests 验收已完成 runtime foundation
    - 覆盖 longform review/rewrite/adopt/continue、chapter bridge、runtime config hot update、Story Evolution visibility、mode sidecar isolation、inspect debug/read bundle
    - 绑定现有 `/api/rp/story-sessions/{session_id}/runtime/inspect` route，不新增 debug truth store 或新 public mutation command
  - 主要文件：
    - `backend/rp/tests/test_story_runtime_product_acceptance.py`
  - 结果：
    - 新增 6 条 Q1 backend acceptance tests
    - `accept_and_continue` 语义通过既有 draft adoption / `accept_pending_segment` flow 验证，没有新增 command name
    - debug/read 验收走既有 inspect route
    - 未进入 Q2，未新增 SuperDoc/WebView、debug panel、branch UI、active RP/TRPG runtime 或 eval runner
  - 验证：
    - `pytest backend\rp\tests\test_story_runtime_product_acceptance.py -q`
    - `pytest backend\rp\tests\test_story_runtime_product_acceptance.py backend\rp\tests\test_draft_selection_service.py backend\rp\tests\test_longform_chapter_runtime_service.py backend\rp\tests\test_runtime_config_control_service.py backend\rp\tests\test_archival_evolution_service.py backend\rp\tests\test_mode_extension_slots.py -q`
    - `ruff check backend\rp\tests\test_story_runtime_product_acceptance.py`
    - `mypy --follow-imports=skip --check-untyped-defs backend\rp\tests\test_story_runtime_product_acceptance.py`

- `[x]` Q2. thin product/API wiring
  - 判定：
    - Q1 没有暴露必须新增 route / controller / frontend wiring 才能验收的 reachability gap。
    - 既有 `/api/rp/story-sessions/{session_id}/runtime/inspect` route 已能覆盖 debug/read 验收。
    - 既有 `/turn` command surface 已能覆盖 write/rewrite/accept/complete chapter product-like flow。
    - 因此 Q2 按规格 skipped / not needed，不做新 product/API wiring。
  - 结果：
    - 未新增 route / controller / frontend 文件改动。
    - 未新增 debug panel 或第二套 debug truth store。
    - 未新增 SuperDoc/WebView、branch UI、active RP/TRPG runtime 或 eval runner。
    - 未新增 public mutation command；`accept_and_continue` 仍只是语义名，映射既有 `accept_pending_segment` / Accept & Continue flow。
    - debug/read 继续绑定既有 `/api/rp/story-sessions/{session_id}/runtime/inspect`。

- `[x]` Q3. manual QA checklist / handoff
  - 主要文件：
    - [story-runtime-product-acceptance-manual-qa.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-product-acceptance-manual-qa.md)
  - 结果：
    - 已补可执行手工 QA 清单，用于 Q1 自动测试通过后的人工验收。
    - 清单覆盖 open session、write next segment、suggesting/rewrite、select/adopt/continue、complete chapter、runtime config patch、Story Evolution visibility、runtime inspect、sidecar isolation、branch-visible read behavior。
    - 每步记录 action、route/command、product evidence、inspect/debug evidence、pass/fail 和 failure classification。
    - 清单仅使用既有 runtime surface，不要求新增 debug panel、SuperDoc/WebView、branch UI、active RP/TRPG runtime 或 eval runner。
  - 模块状态：
    - Q1/Q2/Q3 已由同一 module owner 收口。
    - Q 模块已完成模块级 `gpt-5.5 xhigh` check，未发现 blocking findings。
    - 自动验证证据：`pytest backend\rp\tests\test_story_runtime_product_acceptance.py -q` 为 `6 passed`；Q + 既有 draft selection / chapter runtime / runtime config / archival evolution / mode extension slots 组合回归为 `51 passed`；`ruff check backend\rp\tests\test_story_runtime_product_acceptance.py` 通过；`mypy --follow-imports=skip --check-untyped-defs backend\rp\tests\test_story_runtime_product_acceptance.py` 通过。
    - 剩余边界：Q3 manual QA 是人工产品验收清单，尚需人工按 checklist 执行后才能声明完整 UI/product path 已人工跑通。

- `[!]` Q4. manual QA correction
  - 结论：
    - Q 自动化和模块级 check 只能证明后端 foundation acceptance，不等于产品路径验收通过。
    - 手动 QA 发现产品级阻塞：前端无 inspect/runtime config/branch/mode 入口；rewrite 未遵循批注/修订；continue 未遵循大纲进度和上一段上下文。
    - 之前 Q2 “thin product/API wiring not needed” 的判断被手动 QA 推翻。后续不得继续把隐藏后端 route 当作产品可达能力。
  - 处理：
    - 新增 Phase S：Product Wiring / Writer Constraint Closure。
    - Q 保留为后端 foundation acceptance 记录；产品可用性进入 S 阶段重新验收。

### Phase S: Product Wiring / Writer Constraint Closure

- `[x]` S0. spec and planning correction
  - 目标：
    - 将 Q manual QA 失败反馈固化为正式规格。
    - 明确 S1/S2/S3 模块边界、并行规则、完成标准。
  - 主要文件：
    - [story-runtime-product-wiring-writer-constraint-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-product-wiring-writer-constraint-spec.md)
    - [story-runtime-product-wiring-writer-constraint-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-product-wiring-writer-constraint-development-spec.md)
    - [story-runtime-development-master-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-development-master-spec.md)
    - [story-runtime-execution-plan.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-execution-plan.md)
  - 完成标准：
    - Q 状态被修正为后端 foundation acceptance，而不是产品验收通过。
    - S1/S2 可以并行，且文件 owner 不冲突。
    - implement/check 上下文包含 S 规格。
  - 结果：
    - 已新增 Phase S requirement spec 和 development spec。
    - 已更新 master spec、execution plan、implement.jsonl、check.jsonl。
    - JSONL 已验证可解析且引用文件存在。

- `[x]` S1. backend writer constraint closure
  - owner：单一 backend implement agent。
  - 目标：
    - `rewrite_pending_segment` 读取 active review overlay，并把 comment / tracked change 写入 `WritingPacket.review_overlay_sections`。
    - `write_next_segment` 写入章节进度与上一段承接强约束，不能只靠 `writer_hints`。
    - 有 active review constraints 但无法组装 writer sidecar 时 fail closed。
  - 主要文件候选：
    - `backend/rp/services/story_turn_domain_service.py`
    - `backend/rp/services/context_orchestration_service.py`
    - `backend/rp/services/writing_packet_builder.py`
    - `backend/rp/services/rewrite_request_builder_service.py`
    - `backend/rp/services/rewrite_packet_constraint_service.py`
    - `backend/rp/tests/test_story_runtime_product_wiring_writer_constraints.py`
  - 完成标准：
    - 真实 graph/domain rewrite path 的 writer packet 包含 review overlay constraints。
    - writer prompt 包含 review overlay 和 mandatory rewrite instruction。
    - 真实 write-next packet 包含 continuity/progress section。
    - focused backend tests pass。
  - 结果：
    - 已完成并通过模块级 `gpt-5.5 xhigh` check。
    - `rewrite_pending_segment` 真实 graph/domain 路径已读取 active review overlay，并将 comment / tracked change 约束写入 `WritingPacket.review_overlay_sections`。
    - rewrite 且存在 review overlay 时，writer prompt 已注入 mandatory rewrite instruction。
    - `write_next_segment` 已写入 `chapter_progress` section，包含已采用段落数量、上一段摘录、章节目标、outline ref/digest 与承接指令。
    - check 阶段修复 rollback/branch governance 缺口：rollback 后隐藏的 future accepted segment 不再进入 `specialist_analyze` / generation inputs。
    - 验证通过：
      - `pytest backend\rp\tests\test_story_runtime_product_wiring_writer_constraints.py -q`：4 passed
      - `pytest backend\rp\tests\test_rewrite_request_builder_service.py -q`：8 passed
      - `pytest backend\rp\tests\test_rewrite_candidate_service.py -q`：6 passed
      - `pytest backend\rp\tests\test_draft_selection_service.py -q`：8 passed
      - `pytest backend\rp\tests\test_longform_chapter_runtime_service.py -q`：6 passed
      - `pytest backend\rp\tests\test_story_runtime_product_acceptance.py -q`：6 passed
      - `ruff check ...`：passed
      - `mypy --follow-imports=skip --check-untyped-defs ...`：passed

- `[x]` S2. frontend runtime visibility
  - owner：单一 frontend implement agent。
  - 目标：
    - Longform 页面暴露最小 Runtime/Inspect 只读入口。
    - 展示 active branch、selected turn、snapshot、mode、runtime config history、writer/review/job/retrieval/mode sidecar 摘要。
    - 明确 candidate preview 与 adoption 的区别。
  - 主要文件候选：
    - `lib/services/backend_story_service.dart`
    - `lib/models/story_runtime.dart`
    - `lib/pages/longform_story_page.dart`
    - optional `lib/widgets/*`
  - 完成标准：
    - 前端可打开 inspect/runtime panel。
    - 缺失字段不崩溃，显示为 unavailable / not available。
    - Flutter analyzer/build focused check pass。
  - 结果：
    - 已完成并通过模块级 `gpt-5.5 xhigh` check。
    - Longform 页面已新增明显的 `运行态` 只读入口。
    - 新增 runtime inspection bottom sheet，展示 mode、active branch、selected turn、snapshot、runtime config/history、writer packet、review overlay、chapter bridge、job ledger、retrieval、mode sidecars、branch receipts、graph checkpoint summary。
    - candidate selector 文案已收敛为 preview-only 语义；按钮已统一为 `Accept & Continue`，避免把单纯选择误读为 adoption。
    - 未新增 branch mutation UI、runtime mode switch、SuperDoc/WebView 或 inspect/debug mutation；S2 只做产品可见的读面板。
    - 验证通过：
      - `dart format --output=none --set-exit-if-changed lib\models\story_runtime.dart lib\services\backend_story_service.dart lib\pages\longform_story_page.dart lib\widgets\story_runtime_inspection_sheet.dart`：passed，0 changed
      - `flutter analyze lib\models\story_runtime.dart lib\services\backend_story_service.dart lib\pages\longform_story_page.dart lib\widgets\story_runtime_inspection_sheet.dart`：No issues found

- `[x]` S3. product acceptance re-run
  - 依赖：
    - S1 完成并通过模块级 check。
    - S2 完成并通过模块级 check。
  - 目标：
    - 重新跑用户手测失败链路：批注/修订 -> rewrite -> candidate -> accept -> continue -> inspect evidence。
  - 完成标准：
    - 产品路径可以看见 writer 是否收到修订约束。
    - 续写至少可以证明收到上一段承接和章节进度约束。
    - 若模型仍生成差，能够通过 inspect 判断是模型未遵循还是系统未传约束。
  - 当前状态：
    - S1/S2 前置已完成并通过模块级 check。
    - 用户复测确认：批注/修订 -> rewrite 的大方向基本可用，模型确实能看到并遵循修订约束。
    - 复测同时暴露：续写承接和大纲遵循仍弱。根因是当前只有 `chapter_progress` / outline digest，没有稳定 structured outline beat cursor，writer 未被约束到“当前 beat 只写一个 segment”。
    - S3 不能被解释为完整产品验收通过；它完成了复测和故障归类，并将 blocker 转入 Phase T。

### Phase T: Longform Outline Progress / Chapter Summary Closure

- `[x]` T0. spec and planning correction
  - 目标：
    - 将 Phase S 复测暴露的 continuation / outline-following 问题固化为正式规格。
    - 明确 structured outline JSON、beat cursor、one-segment-one-beat、chapter summary provider 的开发边界。
    - 防止后续测试继续断言未实现的 manual beat editing、paragraph rewrite product UI、SuperDoc/WebView。
  - 主要文件：
    - [story-runtime-longform-outline-progress-chapter-summary-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-longform-outline-progress-chapter-summary-spec.md)
    - [story-runtime-longform-outline-progress-chapter-summary-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-longform-outline-progress-chapter-summary-development-spec.md)
    - [story-runtime-development-master-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-development-master-spec.md)
    - [story-runtime-execution-plan.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-execution-plan.md)
  - 当前冻结口径：
    - outline progress 采用结构化 outline JSON，不以 Markdown `\n` 后处理作为 canonical beat 来源。
    - 一段 accepted segment 覆盖一个 beat。
    - chapter summary 由可替换 provider 生成；第一版 provider 可复用 WritingWorker / writer model gateway 的执行能力和 summary prompt，但 summary 是 chapter bridge sidecar，不是用户可见正文或 Core/Recall truth。
    - 暂不做 manual beat status editing；当前问题是 beat 约束不足，手动修正属于后续细节补强。
  - 文档复查结果：
    - Phase T 已准确承接 Module 23 的确认口径。
    - 已补充说明：旧 chapter bridge lightweight provider 口径被 Phase T 后续强化，不构成冲突；`complete_chapter` 仍是 deterministic product action，summary LLM 调用只属于 provider 内部 bridge maintenance。
    - 无需新增 grill-me 问题；可进入 T1/T2/T3 同一 implement agent 连续实现，完成 T 模块后再统一 check。

- `[x]` T1. structured outline and beat cursor backend closure
  - owner：单一 backend/product implement agent，T1/T2/T3 不拆 owner。
  - 目标：
    - `generate_outline` 输出或规范化为 typed structured outline JSON。
    - `accept_outline` 初始化 beat progress。
    - `write_next_segment` packet 明确 current beat，并要求只写当前 beat。
    - segment candidate 记录 `target_beat_id`。
    - `accept_and_continue` 只在 adoption 后推进 beat cursor。
  - 主要文件候选：
    - `backend/rp/models/longform_chapter_contracts.py`
    - `backend/rp/models/story_runtime.py`
    - `backend/rp/models/writing_runtime.py`
    - `backend/rp/services/longform_chapter_runtime_service.py`
    - `backend/rp/services/story_turn_domain_service.py`
    - `backend/rp/services/context_orchestration_service.py`
    - `backend/rp/services/writing_packet_builder.py`
    - `backend/rp/tests/test_longform_chapter_runtime_service.py`
    - optional `backend/rp/tests/test_longform_outline_progress_chapter_summary.py`
  - 完成标准：
    - accepted outline 有稳定 beat ids。
    - write-next packet 每次只绑定一个 current beat。
    - adoption 后 cursor 进入下一 beat；rewrite/selection 不推进 cursor。
    - focused backend tests pass。
  - 当前结果：
    - 已完成并通过模块级 check。
    - accepted outline 会规范化为 `longform_outline_v1` structured outline，并初始化 branch-scoped outline progress。
    - `write_next_segment` packet 暴露 current beat / covered beats / latest accepted excerpt，并写入 candidate `target_beat_id`。
    - rewrite 和 selection 不推进 cursor；`accept_pending_segment` adoption 后推进到下一 beat或标记 ready for completion。

- `[x]` T2. chapter summary provider closure
  - owner：与 T1 同一 implement agent。
  - 目标：
    - `complete_chapter` 通过 provider 生成 chapter summary / bridge material。
    - provider 可复用 writer/model gateway 执行 summary prompt，但结果作为 Runtime Workspace / chapter bridge sidecar 保存。
    - next chapter packet 读取当前 branch 的 bridge summary，不泄漏 sibling branch 或 hidden future materials。
  - 主要文件候选：
    - `backend/rp/services/chapter_bridge_provider.py`
    - `backend/rp/services/longform_chapter_runtime_service.py`
    - `backend/rp/services/context_orchestration_service.py`
    - `backend/rp/tests/test_longform_chapter_runtime_service.py`
  - 完成标准：
    - provider receives adopted segment refs and covered beat ids.
    - summary material records full identity / branch / source refs / provider metadata.
    - next chapter packet includes only current branch bridge summary.
  - 当前结果：
    - 已完成并通过模块级 check。
    - `complete_chapter` 通过 `ChapterBridgeProvider.build_bridge_material_with_summary(...)` 生成 summary bridge sidecar。
    - provider 接收 adopted segment texts、covered beat ids、covered beat records、source refs 和 model/provider metadata。
    - next chapter packet 只读取当前 branch 可见的 latest chapter bridge summary；sibling branch / hidden future material 不进入 packet。

- `[x]` T3. minimal product visibility and acceptance
  - owner：与 T1/T2 同一 implement agent；仅在需要展示新字段时触碰 Flutter。
  - 目标：
    - inspect/runtime panel 或 longform 页面能看到 current beat / covered beat count（如果 backend 已暴露）。
    - manual QA 清单只覆盖已实现的 beat cursor / summary provider 行为。
    - 不新增 manual beat editor、paragraph rewrite UI、SuperDoc/WebView。
  - 主要文件候选：
    - `lib/models/story_runtime.dart`
    - `lib/services/backend_story_service.dart`
    - `lib/pages/longform_story_page.dart`
    - `lib/widgets/story_runtime_inspection_sheet.dart`
    - [story-runtime-product-acceptance-manual-qa.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-product-acceptance-manual-qa.md)
  - 完成标准：
    - product evidence 能说明当前 segment 对应哪个 beat。
    - 测试和手测不再覆盖未实现功能。
    - T 模块完成后统一派 `gpt-5.5 xhigh` check。
  - 当前结果：
    - 已完成并通过模块级 check。
    - runtime inspection / longform page DTO 已暴露 chapter progress / beat evidence / chapter bridge summary 相关只读字段。
    - 未新增 manual beat editor、paragraph rewrite UI、SuperDoc/WebView。

- `[x]` T4. T module-level trellis-check / spec update
  - 当前结果：
    - 已完成模块级 check；check 阶段修复了 story turn stream stale active snapshot recovery：turn entry snapshot resolution 现在直接走 `ensure_active_snapshot(...)`，避免 session pointer 缺失时重新 pin 回旧 active snapshot。
    - 独立 `gpt-5.5 xhigh` 模块级 check 继续修复了 `ChapterBridgeProvider` 真实 product path 缺口：`complete_chapter` 常只传 `model_id` 而省略 `provider_id`，provider 现在只要有 `model_id` 和 adopted segment 即调用 `StoryLlmGateway`，由 gateway 解析 provider；补充了 provider_id 省略时仍生成 LLM bridge summary 的回归测试。
    - 已将 stale snapshot turn-start recovery 写回 backend code-spec：[rp-runtime-profile-snapshot-minimal-compiler.md](H:/chatboxapp/.trellis/spec/backend/rp-runtime-profile-snapshot-minimal-compiler.md)。
  - 自动验证证据：
    - `pytest backend/rp/tests/test_longform_chapter_runtime_service.py backend/rp/tests/test_story_runtime_product_wiring_writer_constraints.py backend/tests/test_rp_story_api.py -q --tb=short`：`43 passed`
    - `pytest backend/rp/tests/test_longform_chapter_runtime_service.py backend/rp/tests/test_story_runtime_product_wiring_writer_constraints.py backend/tests/test_rp_story_api.py::test_story_turn_stream_backfills_stale_active_snapshot_and_completes -q --tb=short`：`15 passed`
    - `pytest backend/tests/test_rp_story_api.py::test_story_turn_stream_backfills_stale_active_snapshot_and_completes backend/rp/tests/test_runtime_profile_snapshot_service.py::test_ensure_active_snapshot_rebuilds_when_session_pointer_is_stale -q --tb=short`：`2 passed`
    - 独立 check 复跑 `pytest backend/rp/tests/test_longform_chapter_runtime_service.py backend/rp/tests/test_story_runtime_product_wiring_writer_constraints.py -q`：`15 passed`
    - 独立 check 复跑 `pytest backend/tests/test_rp_story_api.py -q`：`29 passed`
    - `ruff check backend/rp/models/longform_chapter_contracts.py backend/rp/services/chapter_bridge_provider.py backend/rp/services/longform_chapter_runtime_service.py backend/rp/services/story_turn_domain_service.py backend/rp/services/writing_worker_execution_service.py backend/rp/services/story_runtime_identity_service.py`：passed
    - `mypy --follow-imports=skip backend/rp/models/longform_chapter_contracts.py backend/rp/services/chapter_bridge_provider.py backend/rp/services/longform_chapter_runtime_service.py backend/rp/services/story_turn_domain_service.py backend/rp/services/writing_worker_execution_service.py backend/rp/services/story_runtime_identity_service.py`：passed
    - `flutter analyze lib/models/story_runtime.dart lib/pages/longform_story_page.dart lib/services/backend_story_service.dart lib/widgets/story_runtime_inspection_sheet.dart`：passed
  - 剩余边界：
    - 全量 mypy 仍被仓库既有 baseline 阻塞，本轮只修复了 Phase T touched files 的窄类型问题。

## 7. 当前执行策略

当前第一阶段最终 K 模块已完成模块级 `trellis-check`，并已完成 `trellis-update-spec`。`R1-R6` 已完成并通过模块级 check；`J1/J2/J3` 已完成并通过模块级 check。本阶段不重开 R/J/K 模块，不进入完整 branch UI、physical purge、branch merge、跨分支 Evolution 管理或完整 roleplay/TRPG runtime。

第二阶段由主脑规划为 `L/M/N/O` 四个模块：

1. `L Runtime Config Surface` 已完成并通过模块级 check，因为它会影响后续所有 turn 的运行规则、worker 权限、retrieval / packet policy 和 snapshot pinning。
2. `M Story Evolution Foundation` 已完成并通过模块级 check；它依赖 branch visibility / memory event / archival governance，和 L 的主要写入文件不同。
3. `N Longform Chapter / Review Adapter` 已完成并通过模块级 check。
4. `O Roleplay / TRPG Extension Slots` 已完成并通过模块级 check；它不做完整 RP/TRPG runtime。
5. 第三阶段 `P Runtime Surface / Debug / API Hardening` 已完成并通过 final check。
6. `Q Runtime Product Acceptance / User-facing Integration Gate` 已完成后端 foundation acceptance 并通过模块级 check；但 manual QA 发现产品路径未通过，不能声明产品可用。
7. `S Product Wiring / Writer Constraint Closure` 作为 Q manual QA 后续阶段启动，负责补前端可见入口和 writer 约束闭环。
8. `T Longform Outline Progress / Chapter Summary Closure` 已完成并通过模块级 check，负责解决 outline beat 约束和章节承接 summary 问题。

当前可并行策略：

1. 若后续重新启动实现，最多同时派发两个开发 agent。
2. 第一批 `L1 / M1` 已完成并通过 check。
3. 第二批 `N1 / O1` 已完成并通过 check。
4. 第三批 `P1 / P2` 已完成并通过 `gpt-5.5 xhigh` final check。
5. 当前 P 阶段已经收口，不继续扩写 P。
6. 当前 Q 阶段 Q1/Q2/Q3 已完成并通过模块级 `gpt-5.5 xhigh` check，但 Q3 manual QA 暴露产品阻塞，当前不进入 finish。
7. S3 product acceptance re-run 已完成复测和故障归类：rewrite 约束路径基本可用，continuation / outline following 暴露 Phase T blocker。
8. T0/T1/T2/T3/T4 已完成，T 模块已通过统一 check；后续不得再把 continuation blocker 归因为“没有 beat cursor / 没有章节 summary provider”，应转入新的产品验收或下一 FIFO 阶段。

## 7.1 下一阶段规划：Branch / Rollback Productization

当前下一阶段不重开旧 session / legacy outline 兼容，不把之前误称的 `Phase U` 作为独立 longform hardening 阶段。T 模块尾部只保留结论：新 session / 新 outline 路径已经由 structured outline + beat cursor + chapter bridge summary 收口；若后续新 session 复测再发现 outline 约束问题，必须作为 T 模块缺陷回归处理，而不是另起旧数据适配阶段。

下一阶段进入既有 `Branch / Rollback` 模块的产品化闭环，规格来源：

- PRD 已要求 rollback 与 branch 严格区分：rollback 后目标 turn 之后内容对当前主线失效；如果要保留旧未来，那是 branch；branch control actions 不创建 story turn。
- PRD 已要求第一版 branch UX：主聊天流展示 active branch 线性 turn；提供“从这里分支”入口和最小 branch 面板；创建后立即切换；fork 点之后旧未来从主视图消失；pending/workspace 不跨 branch。
- `story-runtime-branch-rollback-spec.md` 已冻结最小前端约束：每条历史消息动作菜单提供 `从这里分支`，回退和分支动作必须分开，禁止模糊的“从这里继续”。
- `story-runtime-langgraph-branch-rollback-preflight.md` 已冻结 LangGraph 边界：LangGraph 是 checkpoint / replay / fork 技术壳，不能作为产品 branch / rollback truth。
- 现有代码已有 `StoryRuntimeIdentityService.create_branch_from_turn`、`switch_branch`、`delete_branch`、`rollback_to_turn` 和 `BranchVisibilityResolver`，但 `backend/api/rp_story.py` / `BackendStoryService` / `LongformStoryPage` 尚未提供用户可达的 branch mutation 产品入口。

新增阶段文档：

- [story-runtime-branch-rollback-productization-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-branch-rollback-productization-spec.md)
- [story-runtime-branch-rollback-productization-development-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-branch-rollback-productization-development-spec.md)

执行策略：

1. Branch / Rollback productization 是同一个模块，不能把 create/switch/delete/rollback 拆给多个 implement agent。
2. 模块完成后再做一次模块级 check。
3. 实现 agent 使用 `gpt-5.4 xhigh`；check agent 使用 `gpt-5.5 xhigh`，与本计划 §2 的固定派发规则一致。
4. 当前无 grill blocker；实现中如果发现 snapshot 无法表达 active branch 线性正文、current branch delete fallback、或 branch panel lineage 粒度无法由现有文档决定，再进入 grill。

当前结果：

- `[x]` Branch / Rollback productization spec / development spec 已完成并经独立文档复查；无必须 grill。
- `[x]` Branch / Rollback productization implementation 已由单一 implement owner 完成，未拆分 create/switch/delete/rollback owner。
- `[x]` 后端 product routes 已接入：
  - `POST /api/rp/story-sessions/{session_id}/branches`
  - `POST /api/rp/story-sessions/{session_id}/branches/{branch_head_id}/switch`
  - `DELETE /api/rp/story-sessions/{session_id}/branches/{branch_head_id}`
  - `POST /api/rp/story-sessions/{session_id}/rollback`
- `[x]` routes 通过 `StoryRuntimeController` 调用既有 `StoryRuntimeIdentityService`，返回 refreshed chapter snapshot + branch control receipt envelope。
- `[x]` `delete_branch` 产品合同收敛为：默认分支不可删，当前 active branch 不可删，非当前 branch 做 hide / status transition；本阶段不做 physical purge。
- `[x]` inspect 保持只读，只补 branch panel 所需的可读 branch metadata / latest receipt evidence，不承载 mutation UI。
- `[x]` Longform 前端已新增 branch indicator、branch panel、visible accepted segment 的 `从这里分支` / `回退到这里`、rollback/delete confirmation、snackbar feedback、action 后 snapshot refresh。
- `[x]` 独立 `gpt-5.5 xhigh` 模块级 check 未发现模块内 blocker，未发现必须 grill。
- 验证证据：
  - `pytest backend/tests/test_rp_story_api.py -q`：`33 passed`
  - `pytest backend/rp/tests/test_story_runtime_identity_service.py backend/rp/tests/test_story_runtime_product_wiring_writer_constraints.py -q`：`29 passed`
  - `ruff check backend/api/rp_story.py backend/tests/test_rp_story_api.py backend/rp/services/story_runtime_identity_service.py backend/rp/services/story_runtime_controller.py backend/rp/services/story_runtime_debug_query_service.py`：passed
  - `mypy --follow-imports=skip --check-untyped-defs backend/api/rp_story.py backend/tests/test_rp_story_api.py`：passed
  - `flutter analyze lib/models/story_runtime.dart lib/services/backend_story_service.dart lib/pages/longform_story_page.dart lib/widgets/story_runtime_inspection_sheet.dart`：passed
  - scoped `git diff --check`：无 whitespace error，仅 LF/CRLF 工作区提示。
  - 剩余 warning：Pydantic v2 config deprecation 与 FastAPI `on_event` deprecation，属于仓库既有基础设施 warning，不属于本模块 blocker。

补充历史 P 模块最终检查证据：

- `RULE_CARD / RULE_STATE_CARD` 不得在未显式请求 sidecar slot 时进入 packet `sidecar_refs`，也不得经 generic `workspace_refs` 泄漏。
- debug/read manifest 对 mode sidecar 的识别必须使用稳定 `section_family` / `source_kind` / `section_id`，不能依赖 label 或 payload 私有字段。

第一阶段历史并行记录：

1. R 模块开发期间遵守单模块同一 dev agent 连续负责规则，由 Maxwell 负责 R1-R6。
2. R 模块后端合同完成后已做 R1-R5 模块级 check。
3. R6 frontend/API thin integration 完成后已做第二次 R1-R6 模块级 check。
4. 当前没有正在运行的 subagent。
5. 第一阶段历史记录只作为追溯，不再作为当前下一刀入口。

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

## 10. 第一阶段历史工作树备注

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
- 该备注为第一阶段 E1 历史追溯；当前下一刀已切换为第二阶段 `L1 / M1`。
