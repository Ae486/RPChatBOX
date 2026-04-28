# Research: 2026-04-28-memory-layer-necessity-capability-review

- Query: 审查当前 `H:/chatboxapp` 中 memory layer / memory block 主线实现，判断是否存在过度设计或过度实现，区分哪些能力已经真实落地、哪些只是 adapter/compatibility 级能力，并回答“当前 memory 层是否已经足以支撑最初设计所要求的能力”。
- Scope: internal
- Date: 2026-04-28

## Findings

### 1. 先给结论

结论可以压成一句话：

> **当前 memory 层已经足以支撑“当前冻结口径下”的 longform Memory OS / memory block 需求，但前提是需求口径以 `Core State-first`、`adapter-first`、`public tool family 不扩张`、`WritingPacketBuilder` 不被替换、`setup cognition 不进入 durable memory` 为准。**

如果把“最初设计所要求的能力”理解成 2026-04-18 那批总纲文档里的**分层 Memory OS、统一 Retrieval Broker、governed mutation、Recall/Archival/Runtime Workspace 的明确分工**，那么当前代码已经基本够用，且很多能力是真实现，不再是 04-21 提案里批评的 placeholder 状态。

但如果把“最初设计”进一步抬高到 2026-04-21 `claude-memory-os-block-container-proposal.md` 里那组**更激进的 Block 基础设施目标**，例如：

- universal durable block registry
- shared / isolated attach policy
- branch-aware canon
- read_only 硬保护
- cross-agent fan-out
- agent-facing block edit tool family
- 完整 memory visibility overview

那么当前实现**还不够**，而且很多地方仍然只是 read-model、fallback、compatibility、observability 级能力，不应误判成“完整 Memory OS container runtime 已完成”。

### 2. 总体判断

#### 2.1 是否存在明显过度设计 / 过度实现

**没有发现“明显错误方向上的重型过度实现”。**

当前主线最重要的工程判断是对的：

- 没有引入新的 universal durable `rp_blocks` 物理表；
- 没有替换 retrieval-core 的 Recall / Archival 物理真值；
- 没有把 `WritingPacketBuilder` 合并进通用 memory compile；
- 没有把 setup runtime-private cognition 塞进 durable story memory；
- 没有把 Runtime Workspace discussion 默认提升成 Recall history；
- 没有扩大 public tool family。

换句话说，当前代码的“扩张”主要发生在：

- read-only Block envelope
- compatibility fallback
- controller read-side visibility
- retrieval / runtime / recall 的 additive metadata
- active-story consumer dirty / compile 缓存

这些大多是**适配层和读侧层的扩张**，不是新的 durable truth 子系统，因此成本和风险都被控制住了。

#### 2.2 是否有“可能略超出最小需要”的部分

有，但属于**轻度超前铺路**，不是方向性过度：

1. `Runtime Workspace` 的 `/memory/blocks` 读侧暴露与 controller 读接口。
2. active-story consumer registry + lazy dirty + prompt overlay cache。
3. retrieval hit -> Block-compatible view 的统一适配。

如果只对照 04-18 最早总纲，它们都不是“最小可运行 longform memory”必需项；但对照当前 `04-25-rp-memory-block-planning-dev` PRD 和 D4b close-out，它们已经属于**当前 task 明确纳入的 block-compatible 能力收束**，因此不能简单定性为过度实现。

### 3. 分类结论

#### 3.1 已实现且必要

1. **Memory read boundary 已经真实统一到 `RetrievalBroker`。**
   - `get_state` / `get_summary` 不再只是纯占位，而是先走既有 authoritative/projection read，再按需要用 Block read fallback/enrichment 修补未物化 target。
   - `search_recall` / `search_archival` 继续稳定走 retrieval-core。

2. **Core State 的 current truth / current projection 已经有真实可读对象链。**
   - formal store + compatibility mirror 双路径都在；
   - `RpBlockView` / `RpBlockReadService` 已把它们收敛成稳定 Block-shaped read envelope。

3. **authoritative proposal/apply 治理链已经真实 work。**
   - proposal 是持久化的；
   - apply receipt、revision、before/after snapshot、dual-write / mirror sync 都在真实链路里；
   - 不再是 04-21 提案里批评的“进程内 dict + apply 不存在”状态。

4. **Recall Memory 已经不只是 chapter summary。**
   - 代码与测试显示当前 Recall 已覆盖：
     - `chapter_summary`
     - `accepted_story_segment`
     - `continuity_note`
     - `scene_transcript`
     - `character_long_history_summary`
     - `retired_foreshadow_summary`
   - 这已经足以支撑 long-context 目标下“历史层不只剩摘要”的核心需求。

5. **Runtime Workspace 的边界已经被清楚落实成“读侧 scratch surface”，而不是新 durable truth。**
   - draft artifact / discussion entry 能以 Block view 暴露；
   - 但不支持 proposal/history/provenance，也不会进入 active-story Core State consumer attachments。

6. **`WritingPacketBuilder` 边界被保住了。**
   - 内部 Block compile 只服务 orchestrator / specialist；
   - writer 仍然消费 deterministic packet，而不是 raw memory compile。

#### 3.2 已实现但可能过度

1. **active-story consumer registry + compile cache** 可能比“只让 memory 能读”更往前走了一步。
   - 但它直接服务当前 block prompt overlay / lazy rebuild 任务，不是无谓复杂度。

2. **Runtime Workspace `/memory/blocks` 暴露面** 对最早总纲而言偏超前。
   - 但当前实现严格只读、只限 current chapter、明确不进 prompt attach，因此风险可控。

3. **retrieval Block-compatible views**
   - 对 runtime payload / observability 有价值，但本质上只是统一视图，并未形成新的治理/attach/runtime semantics。
   - 如果后续产品不需要 block-shaped retrieval observability，这层会显得比纯检索结果多一层包装。

#### 3.3 尚未实现但需求仍需要

1. **shared / isolated attach policy**
   - 当前只有 active-story 默认 consumer attachment，没有真正的 shared vs isolated mount 策略。
   - 对 future roleplay / trpg multi-worker 仍然是缺口。

2. **branch-aware canon / branch-aware memory identity**
   - 当前 `StorySession.current_state_json` 与现有 Core State store 语义仍以当前 session / story current truth 为主，没有真正 branch 级差异表达。

3. **read_only 硬保护**
   - 当前 block/view/proposal 路径里没有看到 block-level `read_only` enforce。
   - 如果未来要把 canon 保护前置到 block semantics，这仍是缺失项。

4. **完整 memory visibility layer / context overview**
   - 当前已有 `/memory/blocks`、proposal list、consumer state、retrieval observability top hits；
   - 但还没有 04-21 提案所说那种完整的 `context-overview` 级观察 DTO，把 core state / pending proposals / recall hits / archival hits / promotion 统一收口。

5. **通用化的 agent-facing block edit family**
   - 当前面向外部保持 `proposal.submit` 稳定；
   - 但还没有 `memory.block.append / replace / read` 之类面向 agent 的显式 block tool family。

6. **更完整的 authoritative mutation 语义**
   - `ProposalApplyService` 当前支持的 operation 仍有限；
   - `RemoveRecordOp`、`AddRelationOp`、`RemoveRelationOp`、`SetStatusOp` 都会被明确拒绝。
   - 这意味着“governed mutation 已存在”，但“通用 authoritative object editing”还没完成。

7. **超出 6 个 longform MVP authoritative 字段的更完整 domain coverage**
   - 当前写侧核心仍然通过 `StoryStateApplyService` 的 6 个 allowlist key 进入。
   - 这足够支撑当前 longform 主线，但还称不上所有冻结 domain 都已经进入统一可写能力。

#### 3.4 可以继续 deferred

1. **universal durable `rp_blocks` registry / 新的 block 物理真值层**
   - 当前没有证据证明现在就需要。

2. **Recall / Archival 的物理层 block 化**
   - 现在的 retrieval-core 物理链已经够用，block-compatible adapter 就能满足当前任务。

3. **替换 `WritingPacketBuilder`**
   - 不应做，而且继续 deferred 是正确的。

4. **把 setup runtime-private cognition 纳入 Memory OS durable layer**
   - 不应做，而且继续 deferred / 排除是正确的。

5. **把 `proposal.apply` 暴露成 public external tool**
   - 目前保持 internal 更符合当前冻结边界。

### 4. 能力边界判断

#### 4.1 已经具备的真实能力

1. **Core State exact read**
   - authoritative / projection current read 都是真实现。

2. **Core State Block-shaped read model**
   - 这是真实现，但它是真实现于“read envelope”，不是新 durable store。

3. **`memory.get_state` / `memory.get_summary` 的真实可用性**
   - 对当前 longform 主线已不再是 placeholder。

4. **versions / provenance over formal Core State**
   - 是真实能力，不是伪值。

5. **authoritative proposal submit + policy route + apply**
   - 是真实能力，且有持久化 apply receipt。

6. **Recall retention 与 source-family / materialization metadata**
   - 是真实能力，不只是搜索文段。

7. **Runtime Workspace read-only block views**
   - 是真实读侧能力，但严格不扩展为 history / mutation / attach。

8. **active-story consumer dirty / compile cache**
   - 是真实能力，但作用域只限 orchestrator / specialist / writer packet 这组 active-story consumer。

#### 4.2 只是 adapter / compatibility 级能力

1. **`RpBlockView` 不是新 persistence model，而是 read model。**
2. **`RetrievalBlockAdapterService` 只是把 retrieval hit 包装成 block-compatible envelope。**
3. **`Runtime Workspace` blocks 只是 read-only inspection view。**
4. **`MemoryOsService` 仍然只是 facade。**
5. **`RetrievalBroker.get_state/get_summary` 的 Block 逻辑本质上是 fallback/enrichment，而不是 Block-native canonical read path。**
6. **`current_state_json` / `builder_snapshot_json` 仍然保留 compatibility mirror 角色。**

这类能力都不该被描述成“完整 Block runtime 已完成”；它们是当前阶段非常有价值、但仍然受边界限制的中间层能力。

### 5. 关键依据

#### 5.1 设计与任务口径

- `docs/research/rp-redesign/new-architecture-overview.md`
  - 冻结统一 runtime 骨架，强调 `Memory OS + Writing Runtime`，且 writer packet 独立。
- `docs/research/rp-redesign/x08-memory-os-redesign-draft.md`
  - 冻结四层 Memory OS：Core State / Recall / Archival / Runtime Workspace。
- `docs/research/rp-redesign/core-state-memory-detailed-design.md`
  - 冻结 `authoritative_state` / `derived_projection`、governed mutation、retrieval/storage 分离。
- `docs/research/rp-redesign/agent/cooperation/claude-memory-os-block-container-proposal.md`
  - 提出了更激进的 Block container / compile / fan-out / read_only / shared-isolated / visibility 目标。
- `docs/research/rp-redesign/agent/cooperation/codex-memory-os-block-proposal-review-and-alignment.md`
  - 收紧边界：不能侵蚀 `WritingPacketBuilder`、不能把 setup cognition 放进 durable memory、不能把 Recall/Archival 物理层整体 block 化。
- `.trellis/tasks/04-25-rp-memory-block-planning-dev/prd.md`
  - 当前 task 已明确把目标定义为：在冻结边界内完成 logical containerization，而不是新建 universal durable block store。

#### 5.2 代码模式与测试证据

- `backend/rp/models/block_view.py:20`
  - `RpBlockView` 被明确定义为 **read envelope**，不是新的 persistence model。
- `backend/rp/services/rp_block_read_service.py:45`
  - `list_blocks()` 把 `Core State` 与 `Runtime Workspace` 统一到读侧 Block view。
- `backend/rp/services/rp_block_read_service.py:82`
  - authoritative blocks 优先 formal store，缺失时再退回 compatibility mirror。
- `backend/rp/services/rp_block_read_service.py:150`
  - projection blocks 同样保持 formal store + compatibility mirror 双读。
- `backend/rp/services/rp_block_read_service.py:246`
  - Runtime Workspace block 只覆盖 current chapter 的 draft artifact / discussion entry。
- `backend/rp/services/rp_block_read_service.py:355`
  - runtime artifact block 明确标记 `materialized_to_recall=False`、`scene_transcript=False`。
- `backend/rp/services/retrieval_broker.py:82`
  - `get_state()` 先走既有 read service，再进入 Block fallback merge。
- `backend/rp/services/retrieval_broker.py:122`
  - `get_summary()` 同样是 existing read + Block enrichment/fallback。
- `backend/rp/services/retrieval_broker.py:317`
  - state Block fallback 只修 explicit unresolved authoritative refs，不替代 domain-wide canonical read。
- `backend/rp/services/retrieval_block_adapter_service.py:13`
  - retrieval block adapter 只是把 recall/archival hit 投影成 Block-compatible envelope。
- `backend/rp/services/proposal_workflow_service.py:34`
  - proposal submit 已经真实经过 validation -> policy -> persist -> optional apply route。
- `backend/rp/services/proposal_apply_service.py:57`
  - apply 已能读取 persisted proposal，并创建 apply receipt。
- `backend/rp/services/proposal_apply_service.py:210`
  - apply 支持的 operation 仍受限，说明“治理链已真，但编辑语义未全”。
- `backend/rp/services/story_state_apply_service.py:11`
  - 当前 authoritative mutation 仍只允许 6 个 longform MVP key。
- `backend/rp/services/longform_specialist_service.py:98`
  - retrieval hits 已被转成 block views 供 specialist payload / overlay 使用。
- `backend/rp/services/longform_specialist_service.py:105`
  - active-story internal block compile 只进入 specialist 内部上下文。
- `backend/rp/services/longform_specialist_service.py:257`
  - fallback bundle 仍是 longform-specific digest / patch / recall summary 逻辑，不是通用 memory kernel。
- `backend/rp/services/story_block_consumer_state_service.py:214`
  - writer packet consumer 只附着 projection blocks；其余 consumer 只读 core-state blocks。
- `backend/rp/services/story_block_prompt_compile_service.py:33`
  - prompt overlay compile 是 active-story internal compile cache，不是替换 writer packet。
- `backend/rp/services/story_runtime_controller.py:137`
  - `/memory/blocks*` 已形成 controller read-side surface。
- `backend/rp/services/story_runtime_controller.py:178`
  - versions/provenance 只支持 Core State authoritative/projection。
- `backend/rp/services/story_runtime_controller.py:220`
  - Runtime Workspace block proposal/history 支持明确受限，不被伪装成“已实现”。
- `backend/rp/tests/test_retrieval_broker.py:356`
  - 证明显式未映射 authoritative ref 已可从 block/store fallback 读到真实数据与 revision。
- `backend/rp/tests/test_retrieval_broker.py:455`
  - 证明未映射 projection slot 已可从 formal block/store fallback 读到真实 summary。
- `backend/rp/tests/test_retrieval_broker.py:637`
  - 证明 Recall 命中保留 `source_family / materialization_kind / materialization_event` 元数据。
- `backend/rp/tests/test_retrieval_broker.py:712`
  - 证明 Recall source-family/materialization filter 已可工作。
- `backend/rp/tests/test_memory_crud_provider.py:134`
  - 证明 provider 侧 canonical JSON 在 block fallback state read 下仍保持稳定。
- `backend/rp/tests/test_memory_crud_provider.py:279`
  - 证明 `memory.list_versions` / `memory.read_provenance` 已对 formal state 返回真实结果。
- `backend/rp/tests/test_memory_crud_provider.py:346`
  - 证明 `proposal.submit` canonical receipt 与持久化输入一致。
- `backend/rp/tests/test_story_runtime_controller_memory_read_side.py:527`
  - 证明 Runtime Workspace block view 已暴露且 accepted artifact 被排除在外。
- `backend/rp/tests/test_story_runtime_controller_memory_read_side.py:651`
  - 证明 controller 侧 authoritative block proposal submit 已 work。
- `backend/rp/tests/test_story_runtime_controller_memory_read_side.py:730`
  - 证明 authoritative block proposal review/apply 已 work，且保持 session-scoped 约束。
- `backend/rp/tests/test_story_block_consumer_state_service.py:108`
  - 证明 consumer dirty tracking 真正比较 revision snapshot，而不是假标记。
- `backend/rp/tests/test_story_block_consumer_state_service.py:410`
  - 证明 Runtime Workspace 变化不会污染 core-state consumer attachment。

### 6. Files Found

#### 6.1 设计 / 提案 / 交接

- `docs/research/rp-redesign/new-architecture-overview.md`
  - 统一 runtime 总纲，定义 Memory OS 与 Writing Runtime 的大边界。
- `docs/research/rp-redesign/x08-memory-os-redesign-draft.md`
  - Memory OS 四层语义总纲。
- `docs/research/rp-redesign/core-state-memory-detailed-design.md`
  - Core State / Recall / Archival / Runtime Workspace 的详细职责冻结。
- `docs/research/rp-redesign/agent/cooperation/claude-memory-os-block-container-proposal.md`
  - 更激进的 Block container / compile / fan-out / read_only / visibility 提案。
- `docs/research/rp-redesign/agent/cooperation/codex-memory-os-block-proposal-review-and-alignment.md`
  - 对提案的边界收缩与对齐说明。
- `docs/research/rp-redesign/agent/cooperation/codex-memory-block-session-handoff-2026-04-28.md`
  - 当前 memory block task 的主线交接与阶段判断。

#### 6.2 Task / Spec

- `.trellis/tasks/04-25-rp-memory-block-planning-dev/prd.md`
  - 当前 task 的 rollout 范围、已完成阶段与 deferred 判断。
- `.trellis/tasks/04-25-rp-memory-block-planning-dev/research/current-memory-context.md`
  - 历史研究上下文，说明 compatibility mirror 与推荐 block-first 阶段。
- `.trellis/spec/backend/index.md`
  - backend memory 相关 spec 索引。
- `.trellis/spec/backend/rp-memory-os-block-rollout.md`
  - block rollout 总体 contract。
- `.trellis/spec/backend/rp-memory-container-gap-inventory.md`
  - “暂不引入新 durable container layer”的 decision gate。
- `.trellis/spec/backend/rp-core-state-block-envelope.md`
  - Core State block envelope 的 read-only contract。
- `.trellis/spec/backend/rp-memory-tool-chain-block-compatibility.md`
  - public tool family contract-stable gate。
- `.trellis/spec/backend/rp-memory-get-state-summary-block-read-surface.md`
  - `get_state/get_summary` 的 Block fallback contract。
- `.trellis/spec/backend/rp-retrieval-block-compatible-views.md`
  - retrieval hit -> Block-compatible view 的 additive contract。
- `.trellis/spec/backend/rp-runtime-workspace-block-views.md`
  - Runtime Workspace read-only Block view contract。
- `.trellis/spec/backend/rp-memory-temporal-materialization.md`
  - 各类材料所属 memory layer 与 boundary rules。

#### 6.3 实现

- `backend/rp/services/retrieval_broker.py`
  - 统一 memory read boundary；Block fallback/enrichment；retrieval search。
- `backend/rp/services/retrieval_block_adapter_service.py`
  - retrieval hit -> `RpBlockView` 适配器。
- `backend/rp/services/rp_block_read_service.py`
  - Core State / Runtime Workspace read-only Block envelope 入口。
- `backend/rp/services/story_turn_domain_service.py`
  - longform turn 主流程，保护 writer packet 边界，并驱动 regression / scene transcript promotion。
- `backend/rp/services/longform_specialist_service.py`
  - specialist 内部读取 block context、retrieval hits、metadata/patch/recall summary 生成。
- `backend/rp/services/proposal_workflow_service.py`
  - persisted proposal submit / policy route。
- `backend/rp/services/proposal_apply_service.py`
  - authoritative apply receipt / dual-write / revision 链。
- `backend/rp/services/story_state_apply_service.py`
  - 当前 longform MVP authoritative allowlist 写入器。
- `backend/rp/services/story_runtime_controller.py`
  - `/memory/blocks*` 读面与 block-scoped proposal/apply read side。
- `backend/rp/services/story_block_consumer_state_service.py`
  - active-story consumer dirty/sync registry。
- `backend/rp/services/story_block_prompt_compile_service.py`
  - internal block overlay lazy compile cache。
- `backend/rp/runtime/rp_runtime_factory.py`
  - 当前 runtime wiring，证明这些能力已进真实主链。
- `backend/rp/models/block_view.py`
  - Block read envelope 模型。
- `backend/rp/models/story_runtime.py`
  - `current_state_json` / `builder_snapshot_json` / artifact / discussion / metadata contracts。

#### 6.4 测试

- `backend/rp/tests/test_retrieval_broker.py`
  - broker read/search/materialization metadata/fallback 行为。
- `backend/rp/tests/test_memory_crud_provider.py`
  - public tool/provider contract stability。
- `backend/rp/tests/test_story_runtime_controller_memory_read_side.py`
  - `/memory/blocks*`、governed mutation read side、Runtime Workspace 只读边界。
- `backend/rp/tests/test_story_block_consumer_state_service.py`
  - consumer dirty / chapter change / runtime workspace exclusion。
- `backend/rp/tests/test_story_block_prompt_compile_service.py`
  - overlay compile cache 的 rebuild / reuse 语义。
- `backend/rp/tests/test_retrieval_block_adapter_service.py`
  - retrieval block adapter 的 shape 与 layer 守卫。
- `backend/rp/tests/test_proposal_workflow_service.py`
  - persisted proposal/apply 行为。
- `backend/rp/tests/test_recall_detail_ingestion_service.py`
  - accepted prose -> Recall detail retention。
- `backend/rp/tests/test_recall_scene_transcript_ingestion_service.py`
  - scene transcript promotion。
- `backend/rp/tests/test_recall_character_long_history_ingestion_service.py`
  - character long history retention。
- `backend/rp/tests/test_recall_retired_foreshadow_ingestion_service.py`
  - retired foreshadow retention。
- `backend/rp/tests/test_recall_continuity_note_ingestion_service.py`
  - continuity note retention。

### 7. External References

- 本次审查未使用外部联网资料。
- 仅基于仓内设计文档、Trellis spec、代码和测试进行判断。

### 8. Related Specs

- `.trellis/spec/backend/rp-memory-os-block-rollout.md`
- `.trellis/spec/backend/rp-memory-container-gap-inventory.md`
- `.trellis/spec/backend/rp-core-state-block-envelope.md`
- `.trellis/spec/backend/rp-memory-tool-chain-block-compatibility.md`
- `.trellis/spec/backend/rp-memory-get-state-summary-block-read-surface.md`
- `.trellis/spec/backend/rp-retrieval-block-compatible-views.md`
- `.trellis/spec/backend/rp-runtime-workspace-block-views.md`
- `.trellis/spec/backend/rp-memory-temporal-materialization.md`

### 9. 最终判断

**判断：当前 memory 层已经足以支撑需求。**

但这个判断只在以下前提下成立：

1. 需求口径是当前冻结的 longform / memory-block 主线，而不是 04-21 提案里更激进的“完整通用 Block runtime”。
2. `Core State` 被视为第一落点，Recall / Archival / Runtime Workspace 继续保持 adapter-first。
3. writer 仍然通过 `WritingPacketBuilder` 间接消费 memory，而不是直接吃 raw memory compile。
4. setup cognition 继续留在 setup runtime，而不是并入 story durable memory。
5. public tool family 继续保持稳定，不把 `proposal.apply` / block edit family 贸然外放。

如果这五条前提不成立，那么“当前 memory 层已足够”这个判断就不再成立。

## Caveats / Not Found

- 本次是只读审查，没有执行新的运行时验证；结论依赖仓内现有测试与代码真值。
- `task.py current --path-only` 在当前 shell 返回 repo 默认 task，但用户已明确说明本次 effective task 以 `04-25-rp-memory-block-planning-dev` 的 session override 为准，因此报告按该 task 落点。
- 没有在当前代码里看到：
  - shared / isolated attach policy
  - branch-aware canon identity
  - block-level `read_only` enforcement
  - 完整 `context-overview` 观察 DTO
- 因此如果后续有人把当前实现描述成“完整 Block container runtime 已完成”，这个表述会过头。
