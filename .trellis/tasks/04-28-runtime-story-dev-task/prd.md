# runtime story dev task

## Goal

把 active story runtime 从当前 longform MVP 流水线，收敛为以 worker 为核心的运行时编排骨架。第一阶段不从零重写、不扩成完整多模式系统，而是在现有 `StoryGraphRunner -> LongformOrchestratorService -> LongformSpecialistService -> WritingPacketBuilder -> WritingWorker` 链路上补清楚 worker 合同、调度语义和 runtime context 边界。

本任务的核心定位是：worker 层是 memory 层和 runtime 上下文的管理者。worker 负责决定如何读取、消化、维护 memory 与当前轮上下文；不同 mode 的差异主要通过 worker 的差异化实现体现。反过来，`ModeProfile` 首先用于规定 worker 的心智、工具、上下文、packet 和 writer 姿态，但它不只决定 worker。

## Current Understanding

当前 RP 生命周期是：

```text
prestory/setup
  -> activation
  -> active story runtime
  -> accepted output maintenance
  -> memory/projection/recall update
```

setup agent 已经提供了工具调用、state、retrieval ingestion、activation handoff、proposal/apply 等能力雏形，但 active story runtime 不应继续以 setup agent 为中心。激活后的主线应转入 Memory OS + worker orchestration。

目标 runtime 的基本分工是：

- `Orchestrator Worker`：主持人、路由器、证据分发器。它选择本轮需要哪些 worker，并为 worker 派发事实型上下文。
- `Specialist Workers`：memory 层和 runtime 上下文的领域管理者。它们读取和消化 state、projection、recall、archival、runtime workspace，并产出结构化结果。
- `WritingPacketBuilder`：确定性组包层，只消费稳定 slot 和 worker 消化后的 hints/constraints/digests，不直接消费 raw retrieval hits。
- `WritingWorker`：唯一生成用户可见正文或回应的 worker。
- `Post-write Maintenance`：只在输出被用户接受后，把结果沉淀到 proposal、authoritative state、derived projection、recall memory。

## Existing Implementation

当前已有 longform MVP 主链：

```text
StoryGraphRunner
  -> load_session_and_chapter
  -> validate_command
  -> prepare_generation_inputs
  -> orchestrator_plan
  -> specialist_analyze
  -> build_packet
  -> writer_run
  -> persist_generated_artifact
  -> post_write_regression
```

已实现基础：

- `backend/rp/graphs/story_graph_runner.py` 已有 active story graph shell。
- `backend/rp/graphs/story_graph_nodes.py` 已把 graph 节点映射到 domain service。
- `backend/rp/services/story_turn_domain_service.py` 承担 longform turn 命令语义。
- `backend/rp/services/longform_orchestrator_service.py` 已有 longform planner，输出 `OrchestratorPlan`。
- `backend/rp/services/longform_specialist_service.py` 已有唯一 specialist，会执行 archival/recall search，读取 state/projection，产出 `SpecialistResultBundle`。
- `backend/rp/services/writing_packet_builder.py` 已有确定性 `WritingPacket` 构造。
- `backend/rp/services/writing_worker_execution_service.py` 已有 writer 模型调用。
- `backend/rp/services/longform_regression_service.py` 已在 accepted segment / chapter close 后做维护链。

主要差距：

- 当前 orchestrator 输出仍偏 writer 指令和检索 query，不是真正的 worker 调度计划。
- 当前 graph 固定调用一个 `LongformSpecialistService`，还没有 worker registry/catalog、selected worker execution、per-worker contract。
- 当前 specialist 是 single-generalist specialist，不能清晰承载不同 memory domain 的责任边界。
- 当前 runtime workspace 仍是隐式的 graph state / 函数局部变量，没有明确 refs、生命周期和可观测中间产物。
- 当前 `ModeProfile` 尚未真正驱动 story runtime。session 有 mode，但 prompt 和 policy 多处仍写死 longform。

## Requirements

1. Worker 层必须被定义为 memory 层和 runtime 上下文的管理者，而不是单纯的 prompt 节点。
2. 第一阶段必须保持 longform-first 行为，但 runtime 合同不能继续写死为 longform-only。
3. Orchestrator 的职责应从“生成 writer 指令”升级为“选择 worker、派发事实型上下文、声明同步/异步和优先级意图”。
4. Specialist worker 的输入应被显式建模为 context packet 或等价合同，表达 message refs、memory refs、summary refs、retrieval queries、workspace refs、constraints 等内容。
5. 现有 `LongformSpecialistService` 应继续可用，并作为第一阶段的 compatibility worker execution，不要求立即拆出全部 specialist workers。
6. Worker 输出应保持结构化，至少覆盖 writer hints、validation findings、state/proposal hints、summary updates、recall summary、可选 structured metadata。
7. `WritingPacketBuilder` 必须继续保持确定性边界，不直接接收 raw retrieval hits 或 raw authoritative JSON。
8. Mode 差异应通过 `ModeProfile` 影响 worker 心智、工具范围、retrieval 策略、packet 策略、writer 姿态和 proposal/validation 规则；但第一阶段只需要为这些入口留出合同，不要求完整实现 roleplay/trpg。
9. eval 模块由其他 session 负责。本任务不实现 eval runner、case、grader，只保证 story runtime 产物便于后续观测和接入。

## Acceptance Criteria

- [ ] `prd.md` 明确记录 worker 层定位、当前实现地图、差距和第一阶段边界。
- [ ] 第一阶段实现后，现有 longform 生成链仍可运行。
- [ ] Orchestrator 输出能表达至少一个 selected worker execution，而不只是 writer 指令。
- [ ] Specialist 分析能通过显式 worker/context 合同接收本轮上下文，现有 single specialist 仍兼容。
- [ ] Builder 仍只消费 worker 消化后的结构化结果，不消费 raw retrieval hits。
- [ ] 新增或调整的 runtime contract 有单元测试或现有 story runtime 测试覆盖。
- [ ] 不修改 eval 模块主流程。

## Technical Approach

第一阶段采用“最小合同升级，不扩多 worker”的方式：

```text
existing OrchestratorPlan
  -> selected worker / worker context semantics
  -> single LongformSpecialist compatibility execution
  -> existing SpecialistResultBundle
  -> existing WritingPacketBuilder
  -> existing WritingWorker
```

实现时可以选择两种等价落地方式：

- 在当前 `OrchestratorPlan` 上增量补足 worker 调度语义。
- 或新增轻量 worker plan / context packet 模型，再由 adapter 兼容当前 `OrchestratorPlan`。

关键不是命名，而是合同必须表达：

- 本轮要跑哪个 worker。
- worker 为什么被选中。
- worker 可读取哪些事实型上下文。
- worker 需要哪些 retrieval / memory refs。
- worker 输出如何进入 writer packet 或 post-write maintenance。

## Decision (ADR-lite)

**Context**：当前 story runtime 已有 longform MVP 骨架，但 orchestrator/specialist 关系仍是固定顺序调用，无法表达未来 worker catalog、mode overlay、runtime workspace refs。

**Decision**：第一阶段不重写 runtime，不引入完整多 worker 并发，不实现 roleplay/trpg 行为。先把现有 single specialist 包装成被 orchestrator 选择的 worker execution，并补清楚 worker context 合同。

**Consequences**：

- 好处：改动面小，能保持 longform MVP 可运行，同时为后续拆分 `NarrativeStateWorker`、`CharacterContinuityWorker`、`SynopsisWorker`、`ContinuityReviewWorker` 留位置。
- 代价：第一阶段仍然只有一个实际 specialist，domain accountability 不会一次到位。
- 风险：如果合同只新增字段但调用链仍硬编码 single specialist，后续会继续退化成伪调度。因此实现必须至少让 graph/domain service 开始消费 selected worker execution 语义。

## Out of Scope

- 不实现完整 roleplay / trpg active runtime。
- 不一次性拆出全部 specialist worker。
- 不重写 retrieval core。
- 不重写 Memory OS / Core State store。
- 不实施 eval runner / eval case / grader。
- 不改变 setup agent 的既有冻结口径。
- 不把未被用户接受的 draft 写入 durable memory。

## Technical Notes

已记录的研究文档：

- `research/story-runtime-design-gap-analysis.md`

关键设计文档：

- `docs/research/rp-redesign/new-architecture-overview.md`
- `docs/research/rp-redesign/x08-memory-os-redesign-draft.md`
- `docs/research/rp-redesign/core-state-memory-detailed-design.md`
- `docs/research/rp-redesign/agent/development-spec/setup-agent-development-spec.md`
- `docs/research/rp-redesign/agent/development-spec/prestory-retrieval-and-story-evolution-spec.md`
- `docs/research/rp-redesign/agent/implementation-spec/retrieval-layer-development-spec-2026-04-21.md`

关键实现锚点：

- `backend/rp/models/story_runtime.py`
- `backend/rp/graphs/story_graph_runner.py`
- `backend/rp/graphs/story_graph_nodes.py`
- `backend/rp/services/story_turn_domain_service.py`
- `backend/rp/services/longform_orchestrator_service.py`
- `backend/rp/services/longform_specialist_service.py`
- `backend/rp/services/writing_packet_builder.py`
- `backend/rp/services/writing_worker_execution_service.py`
- `backend/rp/services/longform_regression_service.py`

