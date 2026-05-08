# Story Runtime Spec Review GPT-5.5

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Scope: review-only. This document reviews the current story runtime specification system and does not modify existing spec bodies.
>
> Date: 2026-05-07

## Conclusion

当前规格书体系的总体方向是稳定的：`turn-as-anchor`、`immutable snapshot`、`Runtime Workspace is not truth`、`writer-side bounded retrieval`、`post-write governance`、`branch/control actions not story turns` 这些核心口径已经多处一致。

但目前还不能说“并行开发边界已经低冲突”。主要问题不是架构概念缺失，而是几个公共合同在多份文档里重复定义且字段不完全一致，部分状态/写入时机没有唯一 owner。若现在直接分多组并行实现，后续很容易出现 boundary leakage、contract duplication、write-surface overlap、lifecycle inconsistency 和 configuration truth drift。

严重度统计：

- High: 2
- Medium: 6
- Low: 1
- Residual suggestions: 3

建议立即收口 High 和 Medium-1/2/3；其余可以在实现前的 contract pass 中一起整理。

## Findings

### High-1. `creation-time obligations` 的登记时机和 owner 不唯一，会留下崩溃恢复缺口

为什么是真问题：

规格书反复强调 `required_post_write_analysis` 和 `runtime_workspace_finalize` 必须在 writer 文本允许返回时与 `Turn` 同事务登记，目的是防止“文本已给用户，但服务崩溃后不知道这轮还有后处理责任”。但不同文档把登记动作放在不同位置：

- `story-runtime-spec-coding-plan.md:609-630` 明确说 creation-time obligations 是 writer 文本一旦允许返回时必须与 `Turn` 同事务登记。
- `story-runtime-workspace-ledger-trace-spec.md:360-383` 的 `finalize_writer_output()` 在保存 writer output 时创建两个 job，并把 turn 置为 `post_write_pending`。
- `story-runtime-postwrite-memory-governance-spec.md:338-347` 的 `run_post_write()` 入口又调用 `ensure_creation_time_obligations()`。
- `story-runtime-writing-worker-spec.md:79-92` 说 WritingWorker 负责写回 visible output、usage metadata、最小 turn material，但其伪代码 `story-runtime-writing-worker-spec.md:333-361` 只 persist visible output 并返回 result，没有创建 obligations，也没有推进 turn 状态。

如果不修会造成什么实现后果：

开发者可能把 obligation 创建放到后台 post-write 入口里。这样 writer output 已经返回给前台后，如果进程在调用 `run_post_write()` 前崩溃，系统重启后不会知道该 turn 至少需要补跑 `required_post_write_analysis` 和 `runtime_workspace_finalize`。这会直接破坏恢复、settlement、rollback anchor 和下一轮 gating。

建议如何收口：

冻结一个唯一 owner：建议由 `StoryTurnDomainService.finalize_writer_output(...)` 或等价 turn-domain facade 负责在同一事务内完成以下动作：

1. 持久化 visible output ref / packet ref / usage metadata 的最小 workspace material。
2. 创建两个 creation-time obligation jobs。
3. 把 `Turn.status` 推进到 `post_write_pending`。
4. 返回前台可见 output。

`WritingWorker` 只返回结构化 result，不直接拥有 job ledger；`run_post_write()` 只能 idempotent verify obligations already exist，不应成为首次创建 owner。

### High-2. `RuntimeWorkflowJobRecord` 与 turn 完成判定字段重复且不一致，会让状态机各写各的

为什么是真问题：

job ledger 是 turn settlement 的核心依据，但字段合同在不同规格书里不一致：

- `story-runtime-workspace-ledger-trace-spec.md:203-268` 定义 `RuntimeWorkflowJobRecord`，使用 `required_by_policy`、`creation_mode`、`job_category`、`source_ref_ids/result_ref_ids/trace_refs`。
- `story-runtime-spec-coding-plan.md:462-499` 定义同一类记录，使用 `required_for_turn_completion`、`idempotency_key`、`result_refs_json`、`completion_reason/failure_reason`，但没有 `creation_mode/job_category`。
- `story-runtime-spec-coding-plan.md:652-659` 的完成判定读取 `required_for_turn_completion = true`。
- `story-runtime-workspace-ledger-trace-spec.md:408-423` 和 `story-runtime-postwrite-memory-governance-spec.md:412-425` 的伪代码读取 `job.required_by_policy`。

如果不修会造成什么实现后果：

不同开发切片会自然落出两套字段：一边用 `required_by_policy` 判定，一边用 `required_for_turn_completion` 判定。结果是同一个 job 是否阻塞 settlement、是否允许 deferred、是否参与 retry/repair，会在 repository、post-write scheduler、debug page、test fixture 中产生 hidden coupling。最坏情况下，turn 被错误标记为 `settled`，或者永远无法 settled。

建议如何收口：

把 `RuntimeWorkflowJobRecord` 提升为唯一公共合同，字段只保留一套命名。建议：

- 用 `required_for_turn_completion: bool` 表达 settlement 语义。
- 用 `creation_mode: creation_time_obligation | derived` 表达 job 来源。
- 保留 `job_category` 作为查询/统计分类，但不参与 settlement。
- 保留 `idempotency_key`，因为 obligation 创建和 repair/retry 都需要幂等。
- 统一 settlement 伪代码只读取 `required_for_turn_completion`，不要再出现 `required_by_policy`。

### Medium-1. `WorkerContextPacket` 重复定义且字段不同，`WritingPacket` 还没有进入 master freeze list

为什么是真问题：

master spec 说公共合同冻结后，下游模块只能引用这些合同，不能私自增删核心字段语义：

- `story-runtime-development-master-spec.md:169-189` 冻结公共合同列表，其中包含 `WorkerContextPacket`，但不包含 `WritingPacket`。
- `story-runtime-worker-scheduler-spec.md:229-254` 定义 `WorkerContextPacket`，字段包含 `packet_metadata`，但没有 `trace_refs`。
- `story-runtime-context-packet-spec.md:117-138` 再次定义 `WorkerContextPacket`，字段额外包含 `trace_refs`。
- `story-runtime-context-packet-spec.md:78-105` 定义 `WritingPacket`，而 writing worker 直接消费它，见 `story-runtime-writing-worker-spec.md:79-87` 和 `story-runtime-writing-worker-spec.md:203-217`。

如果不修会造成什么实现后果：

Worker/scheduler 组和 context-packet 组会各自实现一个 packet DTO。一个版本带 trace refs，一个版本不带；debug/eval/replay 侧会发现 worker packet 的 trace 关联不稳定。同时 `WritingPacket` 虽然是 writer 主输入合同，却没有被 master 作为公共冻结对象列出，导致 writing worker、packet builder、retrieval loop 可能各自补字段。

建议如何收口：

在 master freeze list 中增加 `WritingPacket`、`PacketSection`、`RuntimeReadManifestRecord`，并指定唯一合同文件。`story-runtime-worker-scheduler-spec.md` 不再重复列完整 `WorkerContextPacket` 字段，只引用 context-packet spec；若必须保留摘要，明确“字段以 context-packet spec 为准”。

### Medium-2. longform rewrite 的 `selected_output_ref` 伪代码违反“draft 不自动采用”口径

为什么是真问题：

文档明确区分 longform draft candidate 和 canonical selected draft：

- `story-runtime-writing-worker-spec.md:240-243` 写明 longform `rewrite` 结果不自动成为 canonical output。
- `story-runtime-writing-worker-spec.md:298-304` 写明 rewrite 产生新 draft candidate，用户必须显式选择采用哪一版，`accept_and_continue` 只能基于 canonical selected draft。
- 但 `story-runtime-writing-worker-spec.md:333-361` 的 `run_writing_worker()` 对 writing/rewrite 共用逻辑，并直接设置 `selected_output_ref=output_ref`。

如果不修会造成什么实现后果：

实现者按伪代码写，会把 rewrite candidate 自动当成 selected output。这样 longform 的 review/rewrite/accept 语义会被绕过，`LongformDraftSelectionReceipt` 变成可有可无，后续 `accept_and_continue` 可能基于未被用户确认的 draft 继续生成。

建议如何收口：

把 writing 和 rewrite 的 result 规则拆开：

- `operation_mode=writing` 可以设置 `visible_output_ref`，是否 `selected_output_ref` 取决于该 mode 的 first draft policy。
- `operation_mode=rewrite` 只写 `candidate_output_ref` 或 `visible_output_ref`，`selected_output_ref` 必须为空，直到 `LongformDraftSelectionReceipt` 产生。
- `accept_and_continue` 只读取 selection receipt 或 turn 上的 canonical selected ref。

### Medium-3. retrieval usage 字段命名在多份文档中漂移，post-write 消费合同不稳定

为什么是真问题：

retrieval usage 是 writer-side retrieval 到 post-write governance 的唯一桥，但字段名不统一：

- PRD 示例使用 `used_cards`、`expanded_cards`、`unused_cards`、`knowledge_gaps`，见 `prd.md:397-414`。
- `story-runtime-retrieval-spec.md:135-153` 定义 `RetrievalUsageRecord` 使用 `used_card_material_ids`、`used_expanded_chunk_material_ids`、`unused_card_material_ids`、`missed_query_material_ids`。
- `story-runtime-retrieval-spec.md:267-279` 的 post-write 消费规则又写 `used_cards`、`used_expanded_chunks`、`knowledge_gaps`。
- `story-runtime-workspace-ledger-trace-spec.md:344-356` 使用 `used_cards`、`expanded_cards`、`knowledge_gaps`。
- `story-runtime-postwrite-memory-governance-spec.md:252-268` 使用 `used_cards`、`used_expanded_chunks`、`knowledge_gaps`。

如果不修会造成什么实现后果：

writer retrieval loop、Runtime Workspace material、post-write scheduler、worker governance 之间会出现序列化不匹配。某处写 `expanded_cards`，另一处读 `used_expanded_chunks`；某处传 short id，另一处期待 material id。最终可能导致 post-write 没有处理实际使用的检索卡，或把未使用卡错误沉淀。

建议如何收口：

冻结 `RetrievalUsageRecord` 的唯一 schema，并区分“writer-facing short id”和“backend material id”：

- writer-facing: `used_card_short_ids`、`expanded_card_short_ids`、`unused_card_short_ids`
- backend-resolved: `used_card_material_ids`、`used_expanded_chunk_material_ids`
- gaps: `knowledge_gaps`

post-write 只读取 backend-resolved 字段；writer tool API 可以提交 short id，由 runtime guard resolve 成 material id 后持久化。

### Medium-4. 并行开发边界宣称低冲突，但实际写入文件和模块 ownership 有明显重叠

为什么是真问题：

master spec 给了并行组：

- Group A 负责 identity/profile、turn/workspace/ledger/trace、worker/scheduler contract，见 `story-runtime-development-master-spec.md:193-214`。
- Group B 负责 worker registry/scheduler、context orchestration、writing worker，见 `story-runtime-development-master-spec.md:216-226`。
- Group C 负责 retrieval/post-write/memory governance，见 `story-runtime-development-master-spec.md:228-239`。

但 coding plan 的文件级切片显示多个 slice 都会改同一批核心文件：

- Slice A 改 `story_turn_domain_service.py`、`story_graph_runner.py`、`story_graph_nodes.py`，见 `story-runtime-spec-coding-plan.md:684-692`。
- Slice B 继续改 `story_turn_domain_service.py`、`story_graph_nodes.py`，见 `story-runtime-spec-coding-plan.md:712-720`。
- Slice C 继续改 `story_turn_domain_service.py`、`writing_packet_builder.py`，见 `story-runtime-spec-coding-plan.md:752-758`。
- Slice D 改 `runtime_workspace_material_service.py`，见 `story-runtime-spec-coding-plan.md:780-785`。
- Slice F 又改 `runtime_workspace_material_service.py`，见 `story-runtime-spec-coding-plan.md:958-964`。
- Slice G 改 `story_turn_domain_service.py`、`story_graph_nodes.py`，见 `story-runtime-spec-coding-plan.md:1004-1010`。

如果不修会造成什么实现后果：

所谓并行组会在 `story_turn_domain_service.py`、`story_graph_nodes.py`、`runtime_workspace_material_service.py` 等核心文件上相互覆盖。更严重的是 scheduler、context、post-write 都可能往同一个 turn-domain service 塞逻辑，最后形成 hidden coupling 和 God service。

建议如何收口：

把“并行边界”从模块名改成“contract owner + write owner”：

- `story_turn_domain_service.py` 只保留 turn 状态机和事务性 finalize/settle API，不承载 scheduler/context/retrieval 逻辑。
- scheduler/context/post-write 各自只通过 facade 调 turn-domain API。
- coding plan 为每个共享文件指定单一 primary owner；其他 slice 只能调用，不直接扩展。
- 若某文件必须跨 slice 修改，标记为 sequential integration file，不再声称可并行低冲突。

### Medium-5. `RuntimeProfileSnapshotCompiledProfile` 被多处依赖，但编译后 schema 没有冻结，存在 configuration truth drift

为什么是真问题：

PRD 明确说 mode 差异应通过 `ModeProfile -> runtime_profile -> worker policy / packet policy / writer policy` 落地：

- `prd.md:230-249` 说明 runtime profile 决定 worker 默认组合、权限、post-write policy、writer policy、latency budget。
- `prd.md:777-826` 把 ModeProfile、domain registry、worker catalog、packet policy、Runtime Workspace material type 作为验收约束。

但具体可执行 snapshot schema 没有冻结：

- `story-runtime-identity-profile-spec.md:217-254` 只给 `RuntimeProfileSnapshotRecord.compiled_profile_json: RuntimeProfileSnapshotCompiledProfile`，没有展开该 type 的字段。
- `story-runtime-worker-scheduler-spec.md:284-304` 依赖 `RuntimeProfileSnapshotCompiledProfile.worker_activation` 判断 worker active。
- `story-runtime-context-packet-spec.md:214-227` 需要 packet policy 和 token budget。
- `story-runtime-worker-scheduler-spec.md:103-118` 的 WorkerDescriptor 又有 `provider_defaults`、`model_defaults`、`context_slot_policy`、`permission_profile_ref`。

如果不修会造成什么实现后果：

不同服务会各自从 descriptor、session draft、writer_contract_json、packet policy service 或 metadata 里读配置。这样 snapshot 虽然名义上 immutable，但实际运行真相可能漂移：scheduler 读一套 active worker，packet builder 读另一套 slot policy，writer 读第三套 writer contract。

建议如何收口：

在 identity/profile spec 或单独 contract spec 中冻结 `RuntimeProfileSnapshotCompiledProfile` 最小 schema，至少包括：

- `mode`
- `worker_activation`
- `worker_execution_policies`
- `permission_profile`
- `retrieval_policy`
- `packet_policy`
- `writer_policy`
- `post_write_policy`
- `budget_latency_policy`
- `model_provider_policy`

同时明确 `StorySession.runtime_story_config_json` 和 `writer_contract_json` 只能是 draft/cache，不允许 runtime execution 直接读取。

### Medium-6. `post_write_deferred` 既像 turn 状态又像 settlement 条件，下一轮 gating 没完全闭合

为什么是真问题：

文档中 `deferred` 同时出现在 turn status 和 job status：

- `story-runtime-workspace-ledger-trace-spec.md:106-116` 把 `post_write_deferred` 定义为 `StoryTurnRecord.status`。
- `story-runtime-spec-coding-plan.md:391-398` 又说 `settled` 可以在必需 post-write completed/skipped/显式 `post_write_deferred` 后成立。
- `story-runtime-spec-coding-plan.md:400-405` 下一轮 gating 只明确处理 `post_write_pending`、`post_write_running`、`failed`，没有说明 turn 处于 `post_write_deferred` 时是继续保持 deferred、转 settled，还是在下一轮前补调度。
- `story-runtime-postwrite-memory-governance-spec.md:338-347` 的 `minimal_only` 分支调用 `mark_turn_post_write_deferred_if_allowed()` 后直接返回 envelope，没有展示 settlement 或补调度登记。

如果不修会造成什么实现后果：

实现可能出现三种互不兼容行为：一类把 deferred turn 直接视为 settled；一类让 turn 卡在 `post_write_deferred`；一类下一轮继续但没有明确补调度。debug/eval 也难以判断 deferred 是“合法完成原因”还是“仍需补跑的中间态”。

建议如何收口：

明确区分：

- `Job.status = deferred`：某个 job 被 policy 合法延后。
- `Turn.status = settled` + `settlement_reason = required_jobs_deferred_by_policy`：该 turn 已是正式回退点，但有延后责任。
- 或者 `Turn.status = post_write_deferred`：不是正式回退点，下一轮必须 gating。

两者只能选一种作为第一阶段主语义。若选择允许 deferred turn 成为 rollback anchor，就不要让 `post_write_deferred` 作为长期 turn status；改用 settled reason + outstanding deferred job refs。

### Low-1. branch/rollback 的第一阶段边界在文档间不够一致

为什么是真问题：

PRD 说当前阶段优先实现/设计 rollback，不是完整 branch 管理：

- `prd.md:449-459` 说明第一阶段优先回退，不要求完整 branch UI，但底层不能堵死未来分支。

但模块规格和测试计划已经写入较完整 branch 动作：

- `story-runtime-branch-rollback-spec.md:184-208` 冻结 branch create/switch 行为。
- `story-runtime-branch-rollback-spec.md:274-317` 定义前端最小约束。
- `story-runtime-adapter-debug-test-spec.md:174-184` 把 branch create -> immediate switch 和 rollback -> later content hidden 放进运行链路测试。
- `story-runtime-adapter-debug-test-spec.md:214-223` 的迁移顺序又把 branch/debug/product UX 放到最后。
- `story-runtime-spec-coding-plan.md:1074-1093` 只安排 LangGraph Branch/Rollback Preflight，而不是直接实现完整 branch。

如果不修会造成什么实现后果：

实现者可能不清楚第一阶段到底要交付 rollback 合同、branch 数据预留、branch create/switch 后端、还是最小前端 branch panel。这个问题当前不是架构硬冲突，因为多处都承认完整 branch 不是第一阶段核心，但会影响 task 拆分和验收范围。

建议如何收口：

在 master spec 或 coding plan 增加一个明确支持矩阵：

- Phase 1 must implement: rollback contract + later-content hidden + branch visibility fields required for future.
- Phase 1 may implement: branch create/switch backend preflight if LangGraph/store alignment passes.
- Phase 1 not required: full branch UI/tree/diff/delete physical purge.

同时把 adapter-debug-test 中的 branch create test 标成 preflight/contract test，避免被当成必须产品交付。

## Residual Suggestions

### R-1. 把“建议字段”改成“冻结字段 / optional 字段 / future 字段”三段

当前很多公共合同都写“建议字段”。对于实现前的 specs，这会让开发者不确定哪些字段必须落地、哪些只是预留。建议公共合同对象统一改成：

- required fields
- optional fields
- reserved/future fields

这不构成结构性问题，但能显著降低实现误差。

### R-2. 给每个公共合同加 owner 和 canonical spec

建议在 master spec 中加一张表：

- Contract
- Canonical spec file
- Owner module
- Allowed writers
- Allowed readers

这样可以直接压住 contract duplication 和 write-surface overlap。

### R-3. adapter 策略可以再补一条“不得新增状态真相”

adapter spec 已经明确 adapter 不能反向定义新合同、不能复制 truth model。可以再补一句：adapter 不得创建独立生命周期状态，只能映射新 runtime 已有状态。这个建议是防退化，不是当前已发生的问题。
