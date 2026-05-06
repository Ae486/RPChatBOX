# Story Runtime Dependency Readiness Audit

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Date: 2026-05-05
>
> Purpose: 审查 story runtime 依赖模块的现状，判断哪些能力已经足以支撑开发，哪些属于前置漏洞或前置缺口。

## 1. 一句话结论

当前仓库**已经具备** story runtime 开发的骨架基础，但**还不具备**直接承接完整新 runtime 的底层完备性。

更准确地说：

- `retrieval` 主骨架是可用的，不应该推翻
- `proposal/apply`、`projection refresh`、`LLM gateway`、`debug endpoint` 都已有可借能力
- `memory` 已经有正式方向，但还处在 `compatibility bridge + strengthening in progress`
- `Runtime Workspace` 已经有 typed contract，但仍是**进程内临时存储**
- `story graph` 已经有 LangGraph shell，但仍是 `longform fixed chain`

因此，story runtime 可以继续设计和拆模块，但真正进入实现时，必须把几个前置缺口补到位，否则会把新 runtime 写回旧 MVP 的缝缝补补状态。

---

## 2. 总体判断表

| 依赖模块 | 当前状态 | 是否可直接承接新 runtime | 结论 |
|---|---|---|---|
| Memory OS / Core State | 有真实 read/proposal/projection 体系，但仍有 legacy mirror | 否 | 需要补强后再深度依赖 |
| Retrieval Layer | 主骨架成熟，测试较多 | 部分可以 | 保留主骨架，补 runtime identity / usage / promotion |
| Proposal / Apply Governance | 可用 | 可以 | 直接复用 |
| Runtime Workspace | 有类型合同和服务，但只在进程内 | 否 | 必须持久化 |
| Story Session / Chapter Persistence | 可用，但明显 longform-first | 部分可以 | 可借用，但需要扩 turn/branch/profile snapshot |
| LangGraph Runtime Shell | 可用 | 部分可以 | 可作为外壳，但要重构内部流程 |
| LLM / Provider Gateway | 可用 | 可以 | 直接复用，并补 usage / worker 配置化 |
| Debug / Observability | 已有基础 | 可以 | 直接扩，不必另起系统 |

---

## 3. 分模块审查

## 3.1 Memory OS / Core State / Projection

### 已有能力

- `Core State` 已有正式 read side
- `projection` 已有 read/refresh 服务
- `proposal.submit / proposal.apply` 已打通
- `memory contract registry`、`memory change event`、`runtime identity model` 已经存在
- `rp block` 读侧和 `memory inspection` 已经能对外暴露较完整视图
- 有测试：
  - `test_memory_contract_registry.py`
  - `test_memory_change_event_service.py`
  - `test_memory_lineage_services.py`
  - `test_memory_boundary_guards.py`
  - `test_core_state_dual_write_services.py`

### 明确漏洞 / 缺口

1. **identity 只在模型层存在，没有贯穿主链**
   - `MemoryRuntimeIdentity` 已存在
   - 但 `MemoryGetStateInput`、`MemorySearchRecallInput`、`ProposalSubmitInput` 等主用合同还没有强制携带它
   - 结果是 story runtime 想做 `session + branch + turn + snapshot` 绑定时，memory 主工具面还不够硬

2. **authoritative / projection 仍有旧镜像负担**
   - `StorySession.current_state_json` 仍是 legacy authoritative mirror
   - `ChapterWorkspace.builder_snapshot_json` 仍是 projection mirror
   - `ProjectionStateService` / `ProjectionRefreshService` 已支持 dual-write，但还不是纯正式 store 主导

3. **projection refresh 还不是 worker-first 合同**
   - 现在 `ProjectionRefreshService.refresh_from_bundle()` 仍偏向从 `SpecialistResultBundle` 刷新
   - 对新 runtime 来说，需要的是 `projection refresh request` 成为一等输出，而不是继续依赖旧 specialist bundle 语义

4. **worker-facing memory tools 还没成型**
   - 目前有 read/proposal/provenance 组件
   - 但“worker 专家如何按权限读取 block、提交 proposal、刷新 view、记录 usage”还没有形成统一工具合同

### 结论

Memory 层**方向正确**，但仍是 story runtime 的**前置补强模块**，不能直接当成已经完全稳定的底盘。

### 风险等级

`P0`

---

## 3.2 Retrieval Layer

### 已有能力

- store / ingestion / query / broker 四层主骨架都存在
- `keyword + semantic + hybrid + RRF` 已实现
- `RetrievalBroker.search_recall/search_archival` 已是真实路径
- `RetrievalObservabilityService` 已有
- `RetrievalRuntimeConfigService` 已能从 setup / story config 读取 embedding / rerank / graph extraction 配置
- 有大量测试：
  - `test_retrieval_service.py`
  - `test_retrieval_broker.py`
  - `test_retrieval_runtime_config_service.py`
  - `test_retrieval_reranker.py`
  - `test_retrieval_maintenance_service.py`
  - `test_retrieval_observability_service.py`

### 明确漏洞 / 缺口

1. **retrieval 仍是 story-scoped，不是 branch/turn-scoped**
   - `MemorySearchRecallInput.scope` 只是字符串
   - `RetrievalQuery` 只有 `story_id / scope / filters`
   - 当前没有强制 branch/turn/profile snapshot 参与过滤

2. **retrieval runtime config 没有 snapshot pinning**
   - `RetrievalRuntimeConfigService.resolve_story_config(story_id=...)`
   - 读取策略是：setup story config + 最新 session runtime config overlay
   - 对新 runtime 来说，这不够，因为 turn 应该绑定 `RuntimeProfileSnapshot`，而不是动态拿“当前最新配置”

3. **writer-side retrieval 的 runtime 合同还没接上**
   - 当前 retrieval 只解决“查得到”
   - 还没解决：
     - retrieval card 短编号
     - expand card
     - writer usage hook
     - used_cards -> post-write promotion

4. **`get_state / get_summary` 不是完整 runtime authoritative read 面**
   - 虽然 broker 已开始 merge block / store read
   - 但它还不是新 runtime 期望的“统一 identity-bound memory tool surface”

### 结论

Retrieval 层**可以继续用**，而且应该继续用；不需要另引 RAG 框架。

真正要做的是：

- 不换 retrieval 核心
- 给 retrieval 补 runtime identity、usage、promotion、branch visibility

### 风险等级

`P1`

---

## 3.3 Proposal / Apply Governance

### 已有能力

- `ProposalWorkflowService.submit_and_route()`
- `ProposalApplyService`
- persisted proposal repository
- post-write policy decision
- provenance / version history read side
- 有测试：`test_proposal_workflow_service.py`

### 明确漏洞 / 缺口

1. **当前 proposal 输入未强制绑定 runtime identity**
   - `ProposalSubmitInput` 有 `story_id/mode/domain/base_refs/trace_id`
   - 但还没有强制 `session_id/branch_head_id/turn_id/profile_snapshot_id`

2. **还没和 future worker permission profile 正式汇合**
   - 当前有 mode policy
   - 但还没有 story runtime 级的 `per-worker + per-domain/block permission` 编译结果接进治理链

### 结论

proposal/apply **可以直接复用**，不需要新造一套 mutation 系统。

后续只要：

- 把 identity 补全
- 把 worker permission profile 编进来

### 风险等级

`P1`

---

## 3.4 Runtime Workspace

### 已有能力

- `RuntimeWorkspaceMaterial` typed contract 已存在
- `RuntimeWorkspaceMaterialService` 已有：
  - record
  - list / read
  - lifecycle update
  - short id 冲突校验
  - trace event skeleton
- 有测试：`test_runtime_workspace_material_service.py`

### 明确漏洞 / 缺口

1. **当前是 in-process store**
   - `RuntimeWorkspaceMaterialStore` 使用 `dict/list`
   - 只在当前 Python 进程里有效
   - 重启就丢
   - 多实例不共享

2. **还没有和真实 story runtime 主链集成**
   - writer 当前不会写 retrieval cards
   - post-write 当前不会读 Runtime Workspace 做 worker maintenance
   - debug endpoint 也还没把它作为一等材料面暴露

3. **没有 branch/turn 级持久审计价值**
   - 模型里虽然已有 `identity`
   - 但因为没落持久层，回退、分支、跨请求 pending、补调度都靠不住

### 结论

这是当前最明确的**前置漏洞**之一。

story runtime 真正实现前，`Runtime Workspace` 必须从“进程内缓存”升级为“正式持久化的 turn material store”。

### 风险等级

`P0`

---

## 3.5 Story Session / Chapter / Artifact Persistence

### 已有能力

- `StorySessionService`
- `ChapterWorkspace`
- `StoryArtifact`
- `StoryDiscussionEntry`
- longform outline / segment / chapter 生命周期已能跑

### 明确漏洞 / 缺口

1. **明显是 longform-first persistence**
   - `current_chapter_index`
   - `LongformChapterPhase`
   - `accepted_outline_json`
   - `pending_segment_artifact_id`
   - 这些都很偏长文

2. **缺少 branch / turn / snapshot 一等实体**
   - 还没有正式 `BranchHeadRecord`
   - 还没有正式 `StoryTurnRecord`
   - 还没有正式 `RuntimeProfileSnapshotRecord`

3. **discussion / artifact 还是分裂的**
   - 当前 discussion 和 draft artifact 各有各的表
   - 新 runtime 更适合有统一 turn 主记录，再挂 artifact / overlay / workspace refs

### 结论

当前持久层能支撑 longform MVP，但不足以直接成为 mode-neutral runtime persistence。

### 风险等级

`P1`

---

## 3.6 LangGraph Runtime Shell

### 已有能力

- `StoryGraphRunner` 已使用 LangGraph checkpointer
- 已有 runtime debug 接口：`/api/rp/story-sessions/{session_id}/runtime/debug`
- graph shell 已能跑流式和非流式
- special command 分支已存在

### 明确漏洞 / 缺口

1. **graph thread 还是按 `session_id` 绑定**
   - `self._thread_config(request.session_id)`
   - 对分支/回退设计来说，这还不够

2. **graph 仍是固定 longform chain**
   - `prepare_generation_inputs -> orchestrator_plan -> specialist_analyze -> build_packet -> writer_run -> persist_generated_artifact -> post_write_regression`
   - 还没有 scheduler / worker registry / context packet / writer retrieval loop

3. **`post_write_regression` 在 graph 主链上仍是弱实现**
   - 设计上它应该是主链之一
   - 现实里还是偏 legacy longform regression

### 结论

LangGraph 外壳可以继续用，而且应该继续用；但里面的 node/edge 需要重构成 story runtime 新骨架。

### 风险等级

`P0`

---

## 3.7 LLM / Provider Routing

### 已有能力

- `StoryLlmGateway`
- `complete_text_with_usage()`
- 走现有 model/provider registry
- 与 LiteLLM 栈已对齐

### 明确漏洞 / 缺口

1. **当前 writer 路径还没把 usage metadata 真正写回主链**
2. **没有 per-worker provider/model 配置合同**
3. **没有 writer bounded tool loop**

### 结论

这层本身没问题，主要缺 story runtime 上层接法。

### 风险等级

`P2`

---

## 3.8 Debug / Observability

### 已有能力

- story runtime debug endpoint 已存在
- retrieval observability 已存在
- memory overview / block / proposal / provenance read surfaces 已存在

### 明确漏洞 / 缺口

1. **当前 debug 看不到 future Runtime Workspace 主材料**
2. **看不到 worker plan / worker result / retrieval usage hook**
3. **trace 合同还没统一到新 runtime**

### 结论

不需要重新设计 debug 系统，直接在现有 debug/read side 上扩 story runtime 新材料即可。

### 风险等级

`P2`

---

## 4. 前置漏洞清单

## P0：不补就会卡住 story runtime

1. `Runtime Workspace` 还是 in-process store，必须持久化
2. `session -> branch -> turn -> profile snapshot` identity 还没贯穿 memory/retrieval/proposal/runtime
3. `StoryGraphRunner` 仍是固定 longform chain，没有 scheduler / worker registry / context packet
4. `Core State / Projection` 仍有 legacy mirror 负担，新 runtime 如果直接深绑会继续污染实现

## P1：不补会让实现扭曲或后面返工

1. retrieval 还是 `story_id` / `latest session` 思维，不是 snapshot-pinned runtime
2. story persistence 缺 `BranchHead / Turn / RuntimeProfileSnapshot` 一等实体
3. proposal/apply 还没接 worker permission profile
4. worker-facing memory tools 还没正式化

---

## 5. 总结判断

如果问一句最直接的话：

**现有其他模块能不能支撑 story runtime 开发和运行？**

回答是：

**能支撑“继续设计与拆模块”，也能支撑“按前置顺序开工”；但不能在不补底层缺口的情况下，直接安全承接完整新 runtime 实现。**

推荐顺序：

1. 先完成 memory strengthening 的关键前置项
2. 同步准备 Runtime Workspace 持久化
3. 再进入 story runtime 的 identity/scheduler/context/worker 骨架实现

---

## 6. 关键实现锚点

- [story_runtime.py](H:/chatboxapp/backend/rp/models/story_runtime.py)
- [memory_contract_registry.py](H:/chatboxapp/backend/rp/models/memory_contract_registry.py)
- [memory_crud.py](H:/chatboxapp/backend/rp/models/memory_crud.py)
- [runtime_workspace_material.py](H:/chatboxapp/backend/rp/models/runtime_workspace_material.py)
- [story_graph_runner.py](H:/chatboxapp/backend/rp/graphs/story_graph_runner.py)
- [story_session_service.py](H:/chatboxapp/backend/rp/services/story_session_service.py)
- [retrieval_broker.py](H:/chatboxapp/backend/rp/services/retrieval_broker.py)
- [retrieval_runtime_config_service.py](H:/chatboxapp/backend/rp/services/retrieval_runtime_config_service.py)
- [proposal_workflow_service.py](H:/chatboxapp/backend/rp/services/proposal_workflow_service.py)
- [projection_state_service.py](H:/chatboxapp/backend/rp/services/projection_state_service.py)
- [projection_refresh_service.py](H:/chatboxapp/backend/rp/services/projection_refresh_service.py)
- [runtime_workspace_material_service.py](H:/chatboxapp/backend/rp/services/runtime_workspace_material_service.py)
- [story_llm_gateway.py](H:/chatboxapp/backend/rp/services/story_llm_gateway.py)
