# Story Runtime 设计差距分析

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> 日期: 2026-04-28
>
> 目的: 记录当前对 RP story runtime 的大局理解，对照设计稿与现有实现，明确下一步实施前必须确认的口径。

---

## 1. 当前大局理解

RP 功能不是一个单点 agent，而是一条生命周期：

```text
Story creation
  -> prestory / setup
  -> commit + minimal retrieval ingestion
  -> activation readiness
  -> activation into StorySession
  -> active story runtime
  -> post-write maintenance / memory update
```

过去一段时间的重点主要在 `SetupAgent`。这些工作不是浪费，因为 setup agent 已经提供了很多 active runtime 也会复用的能力雏形：结构化工具调用、runtime state、retrieval ingestion、activation handoff、trace/eval、proposal/apply 的雏形。

但长期产品价值的主战场在 active story runtime。setup 的职责是给 runtime 准备初始底盘：story config、writing contract、foundation truth、longform blueprint、archival ingestion、activation seed。激活后，系统不应继续以 `SetupAgent` 为中心，而应转入 Memory OS + worker orchestration。

设计目标中的 active runtime 主链是：

```text
User input / task input
  -> Orchestrator Worker
  -> Retrieval Broker + deterministic packet assembly
  -> optional pre-write specialists
  -> WritingPacketBuilder
  -> WritingWorker
  -> user-visible output
  -> post-write maintenance / proposal / projection / recall update
```

这里有三条强边界：

1. `Orchestrator Worker` 选择本轮需要哪些 worker、给哪些事实型上下文；它不写正文，也不直接裁决最终真相。
2. `Specialist Workers` 消化各自 domain 的证据，产出结构化结果：proposal、writer hints、logs、summary updates。
3. `WritingPacketBuilder` 是确定性拼装层，只喂稳定 slot 给 `WritingWorker`，不把 raw retrieval hits 或 raw authoritative JSON 直接扔给 writer。

---

## 2. 设计基线

### 2.1 Memory OS

目标 memory 形状：

```text
Memory OS
├─ Core State
│  ├─ authoritative_state
│  └─ derived_projection
├─ Recall Memory
├─ Archival Knowledge
└─ Runtime Workspace
```

关键边界：

- `Core State.authoritative_state` 是运行时真相，承载 timeline、relations、goals、character state、knowledge boundary、inventory/mechanics、branch/canon state。
- `Core State.derived_projection` 是 writer / orchestrator / UI 默认可读的当前视图。它不是临时缓存，而是可跨轮消费的 settled projection。
- `Recall Memory` 保存过去已经发生的历史材料，例如 accepted prose、scene/chapter summary、transcript。
- `Archival Knowledge` 保存 setup/import 导入的长期资料，例如世界书、角色档案、规则、参考资料。
- `Runtime Workspace` 保存当前 turn 的临时推理、raw hits、tool outputs、中间素材，不能意外变成 durable truth。

### 2.2 Retrieval

设计目标：

- `Retrieval Broker` 是统一 memory read/query surface。
- worker 决定 retrieval 意图；broker 只负责执行路由、structured read、search、filter、rerank、provenance、trace。
- `structured` query 走 Core State / Projection read service。
- `search` query 走 Recall / Archival retrieval core。
- `memory.get_state`、`memory.get_summary`、`memory.search_recall`、`memory.search_archival` 这类工具都应由 broker 承接。

当前 retrieval 规格的核心判断是：不推翻现有 retrieval 层。保留 PostgreSQL + FTS + pgvector + RRF 主骨架，把隐式结构显式化、插槽化，再逐步补 chunk/context enhancement、rerank、trace、maintenance。

### 2.3 Worker

目标 worker 模型：

- `Orchestrator Worker`：主持人 / 路由器 / 证据分发器。
- 通用 specialist 骨架 + mode overlay：
  - `NarrativeStateWorker`
  - `CharacterContinuityWorker`
  - `SynopsisWorker`
  - `ContinuityReviewWorker`
- 只有机制差异足够大时才拆 mode-specialized worker：
  - longform 偏 blueprint / chapter planning
  - roleplay 偏 interaction / reaction / knowledge boundary
  - trpg 偏 rule adjudication / mechanics
- `WritingWorker` 是唯一用户可见正文生成者。

模式差异不能只靠 prompt。`ModeProfile` 应同时调控 authority、worker、memory、retrieval、packet、tool allowlist、proposal、validation。

### 2.4 Post-write

设计目标：

- longform：writer 产出的 draft 不立即进入 memory；用户接受后再触发维护链。
- roleplay / trpg：可以更快触发，但仍应只把被采纳的最终输出沉淀进 durable memory。
- 维护链应产出 proposal，走 governed apply 更新 authoritative state，刷新 derived projection，并物化 recall 记录。

---

## 3. 当前实现地图

### 3.1 Active story runtime

当前主链是 longform MVP：

- `backend/rp/graphs/story_graph_runner.py`
  - graph 节点：`load_session_and_chapter -> validate_command -> prepare_generation_inputs -> orchestrator_plan -> specialist_analyze -> build_packet -> writer_run -> persist_generated_artifact -> post_write_regression`
  - `accept_outline`、`accept_pending_segment`、`complete_chapter` 属于 special command，会绕过生成链直接结束。
- `backend/rp/graphs/story_graph_nodes.py`
  - 把粗粒度 domain service 调用包成 LangGraph node。
  - graph 内的 `post_write_regression` 当前返回 `post_write_regression_skipped`。
- `backend/rp/services/story_turn_domain_service.py`
  - 承担命令语义。
  - `accept_pending_segment` 会在用户接受片段后触发 light regression。
  - `complete_chapter` 会触发 heavy regression 并创建下一章。
- `backend/rp/services/longform_orchestrator_service.py`
  - longform MVP 的 LLM planner。
  - 输出 `OrchestratorPlan`：`output_kind`、retrieval queries、`specialist_focus`、`writer_instruction`、`notes`。
- `backend/rp/services/longform_specialist_service.py`
  - 当前唯一 specialist，本质是 single-generalist specialist。
  - 执行 archival/recall search，读取 authoritative/projection state，产出 `SpecialistResultBundle`。
- `backend/rp/services/writing_packet_builder.py`
  - 确定性构造 `WritingPacket`。
  - 消费 projection context sections 与 `writer_hints`。
- `backend/rp/services/writing_worker_execution_service.py`
  - 把 packet 渲染成 chat messages，调用 writer 模型。
- `backend/rp/services/longform_regression_service.py`
  - accepted segment / chapter close 后的维护链。
  - 提交 patch proposal，刷新 projection，写入 recall summary/detail/continuity notes。

### 3.2 Memory / projection 实现

当前实现处于 compatibility bridge 状态：

- `StorySession.current_state_json` 仍是 legacy authoritative mirror。
- `ChapterWorkspace.builder_snapshot_json` 仍是 projection mirror。
- `ProjectionStateService` 可以在开关启用时从 Core State store 读 projection slot，否则读兼容镜像。
- `ProjectionRefreshService` 从 specialist bundle 刷新 settled projection，并可 dual-write 到正式 Core State store。
- `StorySessionCoreStateAdapter` 读取 legacy authoritative state。
- `RetrievalBroker.get_state/get_summary/list_versions/read_provenance` 已接入 read services，并带 block/store merge 与 fallback。

结论：这里已经不是纯 placeholder，但仍是过渡态。正式 Core State store 已经存在于旧 mirror 周围，后续实施要避免继续加深旧 mirror 耦合。

### 3.3 Retrieval 实现

retrieval 相比 story 编排更成熟：

- Store objects 已存在：collection、asset、parsed document、chunk、embedding、index job。
- Ingestion chain 已存在：parser -> chunker -> embedder -> indexer。
- Query chain 已存在：query preprocessor -> retrievers -> RRF fusion -> reranker -> result builder。
- `RetrievalService` 已经暴露 slot-injected pipeline。
- `RetrievalBroker` 已用 retrieval core 承接 `search_archival` / `search_recall`。
- reranker 接口和 backend 已存在，但运行时默认与产品使用仍较保守。

### 3.4 Eval 边界

当前 eval runner 支持：

- `setup`
- `retrieval`
- `activation`

它还没有 first-class 的 `story_runtime` eval scope，但 eval 模块由其他 session 负责。本 task 只把它作为外部依赖边界记录：story runtime 的合同、状态与调试输出应足够清晰，方便后续 eval session 接入；本 task 不实施 eval runner / case / grader。

---

## 4. 设计与实现差距

| 区域 | 设计目标 | 当前实现 | 差距 |
|---|---|---|---|
| Runtime 范围 | longform / roleplay / trpg 共用统一 runtime 骨架，由 mode policy 调控 | 当前基本是 longform MVP 命令与章节 phase | 需要先确认下一步是 longform-first，还是先冻结 mode-neutral 合同 |
| Orchestrator 输出 | `WorkerPlan`：selected workers、context slots、refs、priority、blocking/async | `OrchestratorPlan` 只有 output kind、retrieval queries、focus、writer instruction | 输出太薄，表达不了真实 worker 编排 |
| Worker 调度 | orchestrator 选择并调度 domain workers | graph 固定调用一个 `LongformSpecialistService` | 没有 worker registry/catalog、没有 selected worker execution、没有 per-worker contract |
| Worker 边界 | specialist 负责 domain analysis，输出 proposal/hints/logs/summary updates | single generalist 输出一个大 bundle | MVP 有用，但无法承载 domain accountability 与 mode-specific expert 心智 |
| ModeProfile | 调控 authority、worker、memory、retrieval、packet、proposal、validation | session 有 `mode`，prompt 多处写 longform，policy 多为硬编码 | mode 还不是真正的 runtime policy layer |
| Retrieval 意图 | worker 决定查什么；broker 执行 | orchestrator 给 query 字符串，specialist 执行 broker search | 方向正确，但没有 worker-specific retrieval plan / workspace refs |
| Broker 统一读取 | 所有 memory read 统一经 broker/tool surface | orchestrator/specialist 仍直接读 projection / authoritative service 或 block prompt context | broker 已进步，但 story runtime 仍有不少直接读 |
| Runtime Workspace | 当前轮 raw hits/tool outputs/intermediate result 隔离存放 | graph state 有 `plan`、`specialist_bundle`、`writing_packet`，raw hits 在 specialist 内部消化 | 只有隐式工作区，没有命名对象、refs、traceable materialization |
| Builder 合同 | deterministic stable slots，不接 raw retrieval hits/raw JSON | builder 读 projection context + writer hints；raw hits 被 specialist 消化 | 主方向正确，但 slot policy 薄，`writer_hints` 容易变成松散旁路 |
| WritingWorker | 唯一 prose generator，受 ModeProfile writer policy 调控 | longform writer prompt + writing contract + output kind/phase | longform MVP 可用，但没有 mode-aware writer policy |
| Post-write | accepted output -> proposal/apply/projection/recall，异步友好 | accepted segment 触发 light regression；chapter completion 触发 heavy regression | longform 基础不错，但 async scheduling、proposal governance 粒度仍不完整 |
| Proposal/apply | governed mutation 覆盖 Core State object families | proposal workflow 存在，legacy patch builder 把 bundle patch 转 proposal | 治理链存在，但 patch 仍偏 coarse legacy fields |
| Core State store | formal authoritative/projection store primary | dual write/read switches + compatibility mirrors | 仍是切换期，需要避免新功能继续绑定旧字段 |
| Recall materialization | scene/chapter close 写入 accepted prose 与 summaries | summary/detail/continuity/character/foreshadow recall ingestion services 已有 | 进展强，但本 task 只关注 story runtime 内部 policy 与沉淀链路 |
| Eval 边界 | eval 由独立 session 承接 | 当前 runner 只支持 setup/retrieval/activation | 本 task 不改 eval，只保证 story runtime 产物便于后续观测 |

---

## 5. 实施含义

### 5.1 不应从零重写

当前 story runtime 已有正确骨架：

```text
graph shell
  -> domain service
  -> orchestrator
  -> specialist
  -> packet builder
  -> writer
  -> accept/regression
```

正确方向是收敛和强化，而不是推倒重来。弱点主要在合同与边界，不在“完全没有架构”。

### 5.2 最有价值的第一个 spec slice

建议第一个实施切片是：

```text
OrchestratorPlan
  -> WorkerPlan / WorkerContextPacket
  -> single-specialist compatibility execution
  -> trace/debug exposure
```

理由：

- 直接命中核心差距：当前 orchestrator 还不能真正编排 worker。
- 不需要立即实现所有 specialist worker。
- 给未来 worker catalog、retrieval refs、runtime workspace 留出附着点。
- 给调试、日志和后续外部 eval 接入留下清晰中间产物。

口径说明：

- `WorkerPlan / WorkerContextPacket` 是本分析给出的工程化落地命名，不是设计文档中已经冻结的代码对象名。
- 它来自设计稿里对 `Orchestrator Worker` 的职责抽象：编排器应决定本轮找谁干活、给它什么事实材料、拿回什么结构化结果，而不是只给 writer 一句生成指令。
- 如果后续实现时发现当前 `OrchestratorPlan` 增量扩展更稳，可以保留旧名并补足同等语义；关键不是名字，而是“编排计划”和“worker 输入包”这两个合同必须变清楚。

兼容规则：

- 一个 selected worker 仍可映射到现有 `LongformSpecialistService`。
- 但 graph/domain service 应开始把它当成“被选中的 worker execution”，而不是硬编码永远调用 single specialist。

### 5.3 第二个有价值的 spec slice

先把 `ModeProfile` 作为 policy/config 引入，而不是一上来把所有行为都改完：

- 定义最小 runtime policy object。
- activation/session runtime 加载它。
- 暴露给 orchestrator/specialist/builder/writer。
- 第一轮只接少量字段：`authority_profile`、`worker_profile`、`retrieval_profile`、`packet_profile`、`proposal_profile`。

这样可以避免后续继续把 longform 语义硬编码进统一 runtime。

这里的 `mode-neutral` 不是要求先做一个大而空的通用框架。它只表示：story runtime 的关键合同不要写死成长篇小说专用，至少应能表达 longform / roleplay / trpg 的共同骨架；第一轮实际行为仍然可以只跑 longform。

---

## 6. 需要主 session 确认的问题

这些问题应在编码前确认：

1. 下一步实现是继续 **longform-first**，还是立即做 longform / roleplay / trpg 都能承接的 mode-neutral 合同？

   我的建议：合同先 mode-neutral，行为仍 longform-first。这样切片小，但不会把 runtime 锁死成长篇小说专用。
   
   当前口径：`mode-neutral` 只约束合同边界，不代表第一轮要实现多模式完整行为。

2. `WorkerPlan / WorkerContextPacket` 是否作为下一步 orchestrator 的直接输出？还是只给当前 `OrchestratorPlan` 增加几个字段？

   我的建议：现在就引入新合同，并用 compatibility adapter 承接现有语义。当前 `OrchestratorPlan` 太偏 writer 指令，不适合作为真正的 worker dispatcher。
   
   当前口径：这两个名字是工程建议名，来源于设计文档中的 orchestrator/worker 职责，不是已有冻结设计对象。

3. story runtime 内部的 state/projection 读取，下一步是否强制全部走 `RetrievalBroker`？

   我的建议：不要一刀切。先让 `WorkerContextPacket` 能携带 broker-backed refs，再逐步迁移直接读。

4. 后续文档与实现是否只把 eval 当作外部依赖边界？

   当前用户已明确：eval 模块由其他 session 负责。本 task 只关注 story runtime，不再规划 eval runner / case / grader。

---

## 7. 已读文档与代码锚点

已读核心设计文档：

- `docs/research/rp-redesign/new-architecture-overview.md`
- `docs/research/rp-redesign/x08-memory-os-redesign-draft.md`
- `docs/research/rp-redesign/core-state-memory-detailed-design.md`
- `docs/research/rp-redesign/agent/development-spec/setup-agent-development-spec.md`
- `docs/research/rp-redesign/agent/development-spec/prestory-retrieval-and-story-evolution-spec.md`
- `docs/research/rp-redesign/agent/implementation-spec/retrieval-layer-development-spec-2026-04-21.md`

已读但本 task 不负责实施的外部边界文档：

- `docs/research/rp-redesign/agent/agent-eval/00-rp-agent-eval-global-overview.md`
- `docs/research/rp-redesign/agent/agent-eval/07-rp-agent-eval-trace-schema.md`
- `docs/research/rp-redesign/agent/agent-eval/10-rp-agent-eval-gap-driven-development-spec.md`

已读关键实现锚点：

- `backend/rp/graphs/story_graph_runner.py`
- `backend/rp/graphs/story_graph_nodes.py`
- `backend/rp/services/story_turn_domain_service.py`
- `backend/rp/services/longform_orchestrator_service.py`
- `backend/rp/services/longform_specialist_service.py`
- `backend/rp/services/writing_packet_builder.py`
- `backend/rp/services/writing_worker_execution_service.py`
- `backend/rp/services/longform_regression_service.py`
- `backend/rp/services/proposal_workflow_service.py`
- `backend/rp/services/projection_state_service.py`
- `backend/rp/services/projection_refresh_service.py`
- `backend/rp/services/retrieval_broker.py`
- `backend/rp/services/retrieval_service.py`
- `backend/rp/eval/runner.py`
