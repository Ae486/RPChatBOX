# Research: runtime-tech-research-repo-wheel-map

- Query: 对 `backend/rp/models`、`backend/rp/services`、`backend/rp/graphs` 中 story runtime 相关文件做“可复用轮子清单”调研，给后续实现提供最现实的加速地图；输出必须区分可直接复用、适合作 adapter、应废弃/绕开、最易踩坑点。
- Scope: internal
- Date: 2026-05-07

## Files Found

- `backend/rp/models/memory_contract_registry.py` - 定义 `MemoryRuntimeIdentity`，是 runtime 内部跨 retrieval / workspace / proposal 的统一身份锚点。
- `backend/rp/models/runtime_identity.py` - 定义 `RuntimeProfileSnapshotCompiledProfile` 等 snapshot 合同，适合承载冻结后的 profile truth。
- `backend/rp/models/runtime_read_contract.py` - 定义 `RuntimeBranchReadScope` 与 `RuntimeReadManifest`，是 branch visibility 和 packet read trace 的现成合同。
- `backend/rp/models/runtime_workspace_material.py` - 定义 Runtime Workspace material 的 kind / lifecycle / visibility / receipt，是 runtime scratch 的 typed 外壳。
- `backend/rp/models/story_runtime.py` - 现有 longform MVP 主合同，仍然承载 `StorySession` / `ChapterWorkspace` / `LongformTurnRequest` / `OrchestratorPlan` / `SpecialistResultBundle`。
- `backend/rp/models/writing_runtime.py` - 定义当前 `WritingPacket`，是 writer packet 的最小现成 DTO。
- `backend/rp/services/story_runtime_identity_service.py` - 已有 persistent branch / turn / snapshot pinning 服务，可直接作为 runtime identity spine。
- `backend/rp/services/runtime_profile_snapshot_service.py` - 已有 snapshot compile / publish / ensure-active 流程，可直接承接 runtime profile 固化。
- `backend/rp/services/runtime_workspace_material_service.py` - Runtime Workspace 的默认持久化服务，仍保留 in-process fallback seam。
- `backend/rp/services/runtime_memory_persistence_repository.py` - Runtime Workspace / memory event 的 repository，已经按 full identity 过滤。
- `backend/rp/services/runtime_read_manifest_service.py` - 已有 branch lineage 解析与 writer read-manifest 生成逻辑。
- `backend/rp/services/runtime_retrieval_card_service.py` - 已有 retrieval search -> card / expansion / usage materialization 闭环。
- `backend/rp/services/story_turn_domain_service.py` - 当前 graph shell 与具体 longform 行为之间的主要 facade，也是后续最适合收编新 runtime 编排的位置。
- `backend/rp/services/longform_orchestrator_service.py` - 旧 longform planner，可做临时 planner adapter。
- `backend/rp/services/longform_specialist_service.py` - 旧 single-specialist 执行器，但已接上 runtime retrieval card materialization。
- `backend/rp/services/writing_packet_builder.py` - 当前 deterministic packet builder，适合薄封装复用。
- `backend/rp/services/writing_worker_execution_service.py` - 当前 writer LLM 执行器，适合直接复用为最小 writer executor。
- `backend/rp/services/story_llm_gateway.py` - 现有 provider/model 路由网关，后续 worker / writer 都不必重造这一层。
- `backend/rp/services/proposal_workflow_service.py` - 已有 governed submit / policy / apply 编排，可直接作为 mutation 主路径。
- `backend/rp/services/proposal_apply_service.py` - 已有 authoritative proposal apply、mirror sync、event / workspace outcome 记录。
- `backend/rp/services/longform_regression_service.py` - 旧 post-write regression 主体，可只做过渡 adapter，不应继续扩成新 runtime 主链。
- `backend/rp/services/retrieval_broker.py` - 真实 retrieval read boundary，支持 `search_recall` / `search_archival`，并开始吃 `runtime_identity` 过滤。
- `backend/rp/services/retrieval_runtime_config_service.py` - 当前 retrieval config 读取服务，仍偏 setup + latest-session overlay。
- `backend/rp/services/story_runtime_controller.py` - 现成 runtime config patch / memory inspect / block read facade，适合承接 debug / admin adapter。
- `backend/rp/graphs/story_graph_state.py` - 当前 graph state shell，已经为 `runtime_identity / branch_head_id / turn_id / runtime_profile_snapshot_id` 留位。
- `backend/rp/graphs/story_graph_nodes.py` - 把 graph node 映射到 `StoryTurnDomainService`，可复用为新 shell 的 adapter 层。
- `backend/rp/graphs/story_graph_runner.py` - 现成 LangGraph shell、checkpoint、stream / debug 外壳，但内部 edge 仍是 fixed longform chain。

## Findings

### 模块一：Identity / Snapshot Spine

#### 1. 可以直接复用的现有轮子

- `MemoryRuntimeIdentity` 已经是完整的五段式 runtime 身份合同：`story_id + session_id + branch_head_id + turn_id + runtime_profile_snapshot_id`，不需要再发明第二套 identity（`backend/rp/models/memory_contract_registry.py:331`）。
- `StoryRuntimeIdentityService` 已经把“默认 branch 创建 -> turn 创建 -> full identity 解析 -> turn status 完成/失败更新”串起来了，后续 scheduler / worker registry 可以直接站在这条 spine 上（`backend/rp/services/story_runtime_identity_service.py:54`, `backend/rp/services/story_runtime_identity_service.py:97`, `backend/rp/services/story_runtime_identity_service.py:220`）。
- `RuntimeProfileSnapshotService` 已经具备 `compile_snapshot / ensure_active_snapshot / _compile_profile`，而且编译产物就是 `RuntimeProfileSnapshotCompiledProfile`，足够充当冻结后的 profile truth（`backend/rp/services/runtime_profile_snapshot_service.py:64`, `backend/rp/services/runtime_profile_snapshot_service.py:159`, `backend/rp/services/runtime_profile_snapshot_service.py:194`, `backend/rp/models/runtime_identity.py:65`）。

#### 2. 适合作 adapter 的现有实现

- `StoryGraphNodes.pin_runtime_identity` 已经把 graph 入口从 `session_id` 升到 full runtime identity，这一段可以原样保留，后面只替换 graph 内部 worker 链（`backend/rp/graphs/story_graph_nodes.py:34`）。
- `StoryRuntimeController.update_runtime_story_config` 已经具备“patch session config -> compile snapshot -> publish snapshot”的薄管理面，适合作为后续 runtime profile 管理/调试的过渡 admin adapter（`backend/rp/services/story_runtime_controller.py:109`）。

#### 3. 应该废弃 / 绕开的旧 MVP 固定链

- `story_runtime.py` 里的核心合同仍然明显是 longform-first：`ChapterWorkspace` 内含 `accepted_outline_json`、`builder_snapshot_json`、`pending_segment_artifact_id`，这些都说明它还是 chapter workflow 载体，不该再被当成新 runtime 的长期真相模型继续长（`backend/rp/models/story_runtime.py:76`, `backend/rp/models/story_runtime.py:85`, `backend/rp/models/story_runtime.py:86`, `backend/rp/models/story_runtime.py:89`）。
- `LongformTurnRequest` 仍以 `model_id/provider_id/user_prompt/target_artifact_id` 为主，属于旧“单 writer 请求”入口，不够表达未来 worker plan / branch control / runtime-native tool loop（`backend/rp/models/story_runtime.py:144`）。

#### 4. 开工时最容易踩坑的地方

- 如果新模块绕开 `StoryRuntimeIdentityService` 自己生成 branch / turn id，很快就会把 retrieval / workspace / proposal 的 identity 重新打散。
- `RetrievalRuntimeConfigService.resolve_story_config()` 仍是 story + latest session overlay 语义，不是 turn pinned 语义；runtime 内部逻辑应该优先站在 snapshot service 的 compile/publish/pin 链上，而不是直接拿“当前最新配置”（`backend/rp/services/retrieval_runtime_config_service.py:22`）。

### 模块二：Runtime Workspace / Retrieval Trace Spine

#### 1. 可以直接复用的现有轮子

- `RuntimeWorkspaceMaterial` 已经把 runtime scratch 的边界写得很清楚：temporary、非 truth、非 authoritative mutation、非 recall / archival truth；kind/lifecycle/visibility 也已经足够细（`backend/rp/models/runtime_workspace_material.py:20`, `backend/rp/models/runtime_workspace_material.py:40`, `backend/rp/models/runtime_workspace_material.py:59`, `backend/rp/models/runtime_workspace_material.py:81`）。
- `RuntimeWorkspaceMaterialService` 现在默认就是“persistent repository-backed storage”，不再是纯内存玩具；对于 turn material store，这是后续实现最该直接吃的轮子（`backend/rp/services/runtime_workspace_material_service.py:66`, `backend/rp/services/runtime_workspace_material_service.py:69`, `backend/rp/services/runtime_workspace_material_service.py:96`, `backend/rp/services/runtime_workspace_material_service.py:135`, `backend/rp/services/runtime_workspace_material_service.py:170`）。
- `RuntimeWorkspaceMaterialRepository.identity_filters()` 已经把 story/session/branch/turn/profile 五段 identity 下推到查询条件，隔离语义现成可用（`backend/rp/services/runtime_memory_persistence_repository.py:36`, `backend/rp/services/runtime_memory_persistence_repository.py:101`）。
- `RuntimeRetrievalCardService` 已经具备 `search_*_to_cards -> expand_cards -> record_writer_usage -> build_source_ref_bundle` 闭环，这是后续 bounded retrieval loop 最现实的加速器（`backend/rp/services/runtime_retrieval_card_service.py:53`, `backend/rp/services/runtime_retrieval_card_service.py:73`, `backend/rp/services/runtime_retrieval_card_service.py:114`, `backend/rp/services/runtime_retrieval_card_service.py:156`, `backend/rp/services/runtime_retrieval_card_service.py:229`）。
- `RuntimeReadManifestService` 已经能做 branch visibility 和 writer manifest，能直接复用到 packet-visible evidence trace，而不必再设计一套新审计面（`backend/rp/services/runtime_read_manifest_service.py:31`, `backend/rp/services/runtime_read_manifest_service.py:38`, `backend/rp/services/runtime_read_manifest_service.py:90`, `backend/rp/services/runtime_read_manifest_service.py:245`, `backend/rp/models/runtime_read_contract.py:73`）。

#### 2. 适合作 adapter 的现有实现

- `StoryTurnDomainService._build_runtime_retrieval_packet_context()` 已经能把 writer-visible cards / expanded chunks 变成 `retrieval_context` packet section；这是旧 `WritingPacket` 接新 retrieval material 的现成桥（`backend/rp/services/story_turn_domain_service.py:842`）。
- `StoryTurnDomainService._record_runtime_retrieval_usage_for_artifact()` 已经能在 artifact 持久化时回填 `retrieval_usage_record`，适合在第一阶段继续作为“旧 writer -> 新 usage trace”的桥接点（`backend/rp/services/story_turn_domain_service.py:888`）。
- `StoryTurnDomainService._runtime_turn_source_refs()` 已经把 turn/source ref 统一成 memory-layer source refs，后续 post-write / recall / proposal 都能沿用这一锚点（`backend/rp/services/story_turn_domain_service.py:705`）。

#### 3. 应该废弃 / 绕开的旧 MVP 固定链

- 不要再把 runtime scratch 埋回 `ChapterWorkspace.builder_snapshot_json` 或其他 longform projection mirror；`builder_snapshot_json` 是兼容镜像，不是 runtime material store（`backend/rp/models/story_runtime.py:86`）。
- 不要让 retrieval 命中直接变成 writer raw dump 或直接写 Core truth。仓库里已经有 card/usage/material 路径，继续绕开它只会回到“有结果但无 trace”的旧坑。

#### 4. 开工时最容易踩坑的地方

- `RuntimeWorkspaceMaterialService` 仍保留 `_persistent_enabled` 和 injected store fallback；如果新代码在测试/组装时误传了 `store=` 而没带 session/repository，会悄悄退回 in-process 语义（`backend/rp/services/runtime_workspace_material_service.py:88`）。
- retrieval usage 现在是在 artifact 持久化阶段补记。如果未来某个 worker 在 writer 前就结束，或者 turn 在 writer 后失败，usage trace 可能不完整，需要在新 runtime 里更早明确“何时视为 used”。

### 模块三：Graph Shell / Runtime Orchestration

#### 1. 可以直接复用的现有轮子

- `StoryGraphRunner` 作为 LangGraph 外壳、checkpoint、stream 入口、runtime debug 入口，都是现成可用的，不值得重造（`backend/rp/graphs/story_graph_runner.py:30`, `backend/rp/graphs/story_graph_runner.py:195`）。
- `StoryGraphState` 已经为 `runtime_identity / branch_head_id / turn_id / runtime_profile_snapshot_id` 预留了显式字段，说明现有 graph shell 已经在向 branch-ready runtime 迁移（`backend/rp/graphs/story_graph_state.py:8`）。
- `StoryGraphNodes` 已经把 graph 逻辑压成 coarse node adapter，后续只要替换 domain service 内部语义，不一定要推翻 graph 外壳（`backend/rp/graphs/story_graph_nodes.py:22`, `backend/rp/graphs/story_graph_nodes.py:187`, `backend/rp/graphs/story_graph_nodes.py:228`）。
- `StoryTurnDomainService` 已经是当前 controller / graph shell 之下最集中的业务 facade，是后续塞进 scheduler / worker registry / context orchestration 的最佳落点（`backend/rp/services/story_turn_domain_service.py:41`, `backend/rp/services/story_turn_domain_service.py:235`）。

#### 2. 适合作 adapter 的现有实现

- 第一阶段完全可以保留 `StoryGraphRunner + StoryGraphNodes`，仅把 node 内部从“固定 longform steps”慢慢切换成“scheduler -> worker plan -> worker result -> finalize”的新主链。
- `StoryGraphRunner.get_runtime_debug()` 已经提供 checkpoint 历史和 meaningful snapshot 读取，这很适合作为后续 runtime debug page 的底层 adapter（`backend/rp/graphs/story_graph_runner.py:195`）。

#### 3. 应该废弃 / 绕开的旧 MVP 固定链

- 当前 graph edge 仍是硬编码 fixed chain：`prepare_generation_inputs -> orchestrator_plan -> specialist_analyze -> build_packet -> writer_run -> persist_generated_artifact -> post_write_regression`。这是最应该明确绕开的旧链，不应在此基础上继续叠 worker 名称和 mode 分支（`backend/rp/graphs/story_graph_runner.py:255`, `backend/rp/graphs/story_graph_runner.py:256`, `backend/rp/graphs/story_graph_runner.py:257`, `backend/rp/graphs/story_graph_runner.py:266`, `backend/rp/graphs/story_graph_runner.py:267`, `backend/rp/graphs/story_graph_runner.py:268`）。
- `_SPECIAL_COMMANDS` 仍把 `ACCEPT_OUTLINE / ACCEPT_PENDING_SEGMENT / COMPLETE_CHAPTER` 当特殊控制分流；这对旧 longform 合理，但对新 branch/control 体系不能直接照抄成长期设计（`backend/rp/graphs/story_graph_runner.py:33`, `backend/rp/graphs/story_graph_nodes.py:25`）。

#### 4. 开工时最容易踩坑的地方

- graph thread 仍按 `session_id` 绑死，branch/rollback/fork 一旦进入真实运行态，这会让不同 branch 共用同一 checkpoint thread（`backend/rp/graphs/story_graph_runner.py:315`, `backend/rp/graphs/story_graph_runner.py:321`）。
- 现在 graph shell 已经 pin runtime identity，但真正的 branch visibility / turn cutoff 语义是在 read-manifest 侧，若未来 scheduler 直接跳过这层，会再次出现“turn material 和 packet trace 对不上”的问题。

### 模块四：Planner / Specialist / Writer Execution

#### 1. 可以直接复用的现有轮子

- `StoryLlmGateway` 已经是干净的 provider/model 路由与请求构造层，支持 `complete_text`、`complete_text_with_usage`、`stream_text`，后续 worker / writer 不必重造模型网关（`backend/rp/services/story_llm_gateway.py:20`, `backend/rp/services/story_llm_gateway.py:49`, `backend/rp/services/story_llm_gateway.py:81`, `backend/rp/services/story_llm_gateway.py:102`）。
- `WritingPacketBuilder` 是稳定的 deterministic packet builder，当前已经支持 projection sections、runtime retrieval sections、writer hints、packet metadata 拼装，很适合作为第一版 packet builder 保留（`backend/rp/services/writing_packet_builder.py:11`, `backend/rp/services/writing_packet_builder.py:14`）。
- `WritingWorkerExecutionService` 已经把 packet 渲染为 messages 并跑同步/流式 LLM，作为最小 writer executor 足够直接复用（`backend/rp/services/writing_worker_execution_service.py:13`, `backend/rp/services/writing_worker_execution_service.py:19`, `backend/rp/services/writing_worker_execution_service.py:34`）。

#### 2. 适合作 adapter 的现有实现

- `LongformOrchestratorService.plan()` 适合作为临时 planner adapter：它已经能结合 projection / authoritative state / block prompt overlay，并生成最小 `OrchestratorPlan`（`backend/rp/services/longform_orchestrator_service.py:24`, `backend/rp/services/longform_orchestrator_service.py:48`）。
- `LongformSpecialistService.analyze()` 适合作为临时 specialist adapter：它已经能跑 recall / archival retrieval，并把 hits materialize 成 runtime retrieval cards，再生成 `SpecialistResultBundle`（`backend/rp/services/longform_specialist_service.py:34`, `backend/rp/services/longform_specialist_service.py:77`）。
- `StoryTurnDomainService.build_packet()` 已经能把 projection、retrieval context、writer hints、worker source refs、read manifest 拼到一个 packet 上，这一层非常适合作为新 worker packet facade（`backend/rp/services/story_turn_domain_service.py:235`）。

#### 3. 应该废弃 / 绕开的旧 MVP 固定链

- `WritingPacket` 当前 `output_kind` 只允许 `chapter_outline / discussion_message / story_segment`，这说明它还是 longform writer packet，而不是 mode-neutral worker packet（`backend/rp/models/writing_runtime.py:10`, `backend/rp/models/writing_runtime.py:16`）。
- `OrchestratorPlan` 和 `SpecialistResultBundle` 仍紧贴长文写作语义，例如 `archival_queries / recall_queries / writer_hints / state_patch_proposals / summary_updates / recall_summary_text`；这些字段可以借，但不该反向定义未来 runtime 合同（`backend/rp/models/story_runtime.py:179`, `backend/rp/models/story_runtime.py:183`, `backend/rp/models/story_runtime.py:184`, `backend/rp/models/story_runtime.py:185`, `backend/rp/models/story_runtime.py:278`, `backend/rp/models/story_runtime.py:280`, `backend/rp/models/story_runtime.py:281`, `backend/rp/models/story_runtime.py:282`）。
- `WritingWorkerExecutionService` 当前只是“render messages -> LLM call”，没有 bounded tool loop、没有 explicit usage commit、没有 worker retry / repair 语义，不能把它误判成“新 writer runtime 已经完成”。

#### 4. 开工时最容易踩坑的地方

- `LongformOrchestratorService` / `LongformSpecialistService` 的 fallback 逻辑和 system prompt 都写死了 longform 口径；如果不加 adapter 边界，旧 prompt 词汇会悄悄污染新 runtime 语义（`backend/rp/services/longform_orchestrator_service.py:96`, `backend/rp/services/longform_specialist_service.py:177`）。
- `WritingPacket` 的 `context_sections` 仍是 `label + items[str]` 级别，适合早期 writer packet，不适合后续 richer packet/section contract；如果直接继续堆字段，最后只会让 packet 变成无类型字符串桶。

### 模块五：Governed Mutation / Post-write Maintenance

#### 1. 可以直接复用的现有轮子

- `ProposalWorkflowService.submit_and_route()` 已经把 validation、policy、receipt、auto-apply 串在一起，是后续 runtime worker 写 truth 的现成主路径（`backend/rp/services/proposal_workflow_service.py:25`, `backend/rp/services/proposal_workflow_service.py:43`）。
- `ProposalApplyService.apply_proposal()` 已经把 authoritative apply、dual-write、compatibility mirror、apply receipt、outcome record 放在一个事务边界里，这是明确可直接复用的 mutation kernel 外壳（`backend/rp/services/proposal_apply_service.py:54`, `backend/rp/services/proposal_apply_service.py:89`）。

#### 2. 适合作 adapter 的现有实现

- `LongformRegressionService` 目前已经接 proposal workflow、projection refresh、recall ingestion 家族。对于新 runtime 的第一阶段，它适合作为“旧 accept/complete 行为 -> 新 governed maintenance” 的临时 adapter（`backend/rp/services/longform_regression_service.py:37`, `backend/rp/services/longform_regression_service.py:87`, `backend/rp/services/longform_regression_service.py:122`）。

#### 3. 应该废弃 / 绕开的旧 MVP 固定链

- `LongformRegressionService` 仍通过 `LegacyStatePatchProposalBuilder` 把 `SpecialistResultBundle.state_patch_proposals` 喂回 proposal/apply，这说明它还是旧 longform post-write regression 逻辑，不该继续长成新 runtime 的标准 maintenance 主链（`backend/rp/services/longform_regression_service.py:17`, `backend/rp/services/longform_regression_service.py:231`）。
- 不要把 `accept_pending_segment / complete_chapter` 的 regression 路线直接等同于未来 mode-neutral post-write worker；它们只是旧 longform 章节收口语义的过渡壳。

#### 4. 开工时最容易踩坑的地方

- proposal workflow 本身是可用的，但 `governance_metadata`、`core_mutation_envelope.identity` 在部分路径仍可能为空；新 worker 侧如果不强制带 identity/source refs，很容易又退化成“apply 能跑，但 trace 不硬”（`backend/rp/services/proposal_workflow_service.py:43`, `backend/rp/services/proposal_workflow_service.py:140`）。
- `LongformRegressionService` 仍默认围绕 chapter / accepted segment / recall summary 语义工作，不能直接拿来承接 roleplay/trpg 或 branch-aware worker maintenance。

### 模块六：Debug / Read / Config Surface

#### 1. 可以直接复用的现有轮子

- `StoryRuntimeController` 已经提供 runtime config patch、visible memory inspect、block list、memory overview 等 facade，不需要为了 story runtime 再造一套 read/debug controller（`backend/rp/services/story_runtime_controller.py:49`, `backend/rp/services/story_runtime_controller.py:109`, `backend/rp/services/story_runtime_controller.py:158`, `backend/rp/services/story_runtime_controller.py:181`, `backend/rp/services/story_runtime_controller.py:198`）。
- `StoryGraphRunner.get_runtime_debug()` 已经能读 checkpoint 历史和 meaningful snapshot，足够充当第一版 graph runtime debug 底层（`backend/rp/graphs/story_graph_runner.py:195`）。
- `RuntimeReadManifest` 已经把 `visible_refs / selected_refs / omitted_refs / retrieval_card_refs / writer_usage_refs / token_usage_metadata` 冻结成现成 DTO，适合直接作为 packet 审计材料（`backend/rp/models/runtime_read_contract.py:73`）。

#### 2. 适合作 adapter 的现有实现

- `StoryRuntimeController` 现在更多是 longform read/list/activate facade，但这正好适合在新 runtime 真正对外开放前，作为一层只读 adapter 先把 debug / inspect 面搭起来。

#### 3. 应该废弃 / 绕开的旧 MVP 固定链

- 不要把 `build_chapter_snapshot()` 或 `ChapterWorkspaceSnapshot` 当成未来 runtime 的权威 read model；它们更像旧 chapter UX snapshot，而不是 runtime-native debug truth（`backend/rp/services/story_runtime_controller.py:96`, `backend/rp/services/story_runtime_controller.py:104`, `backend/rp/services/story_runtime_controller.py:131`）。

#### 4. 开工时最容易踩坑的地方

- 现有 debug/read surface 主要还是 session/chapter 口径；branch/turn/profile 的深度观察能力虽然有底层 identity/read-manifest，但前台 facade 还没有完全对齐。
- 本次范围没有去看 API route、SSE event schema、前端 debug page，只能确认后端 service / graph 层已有可复用 read surfaces，不能直接宣称产品面已就绪。

## Related Specs

- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-development-master-spec.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-adapter-debug-test-spec.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-dependency-readiness-audit.md`
- `.trellis/spec/backend/rp-runtime-identity-persistence-propagation.md`
- `.trellis/spec/backend/rp-runtime-workspace-persistent-turn-material-store.md`
- `.trellis/spec/backend/rp-retrieval-card-usage-promotion-boot-contract.md`

## External References

- 无；本次结论全部来自仓库内 spec、audit 和目标代码。

## Caveats / Not Found

- 本次严格遵守范围，只读了 `backend/rp/models`、`backend/rp/services`、`backend/rp/graphs` 中与 story runtime 直接相关的文件；没有泛扫其他目录。
- 由于范围限制，没有继续下钻 `models.rp_story_store`、`models.rp_memory_store`、API route、前端 debug 页面，因此“持久化表结构是否完整可直接上线”不在本次结论内。
- 本次是静态调研，没有运行 graph / tests；“可复用”表示代码骨架和合同已存在，不等于该模块已完成 story runtime 全量语义。
- 最值得优先拿来加速实现的现成轮子是：`StoryRuntimeIdentityService`、`RuntimeProfileSnapshotService`、`RuntimeWorkspaceMaterialService + Repository`、`RuntimeRetrievalCardService`、`RuntimeReadManifestService`、`ProposalWorkflowService / ProposalApplyService`、`StoryGraphRunner` 外壳、`StoryLlmGateway`、`WritingPacketBuilder`、`WritingWorkerExecutionService`。
