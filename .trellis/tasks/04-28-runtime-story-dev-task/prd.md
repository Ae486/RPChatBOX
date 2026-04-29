# runtime story dev task

## Goal

把 active story runtime 从当前 longform MVP 流水线，收敛为以 worker 为核心的运行时编排骨架。第一阶段不从零重写、不扩成完整多模式系统，而是在现有 `StoryGraphRunner -> LongformOrchestratorService -> LongformSpecialistService -> WritingPacketBuilder -> WritingWorker` 链路上补清楚 worker 合同、调度语义和 runtime context 边界。

本任务的核心定位是：worker 层是 memory 层和 runtime 上下文的管理者。worker 首先从 `Core State` / `derived_projection` / recall / archival 的 block ownership 推导，而不是从零散 prompt 技能推导。worker 负责决定如何读取、消化、维护 memory 与当前轮上下文；不同 mode 的差异主要通过 worker 的差异化实现体现。反过来，`ModeProfile` 在 setup 之前就被选择，它不仅影响 setup 流程，也决定 active runtime 的 memory schema、worker 默认路线、retrieval policy、packet policy 和 writer 姿态。

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

- `Deterministic Scheduler`：代码层 workflow 裁决者。它读取 mode/profile/phase/budget/worker catalog，校验 LLM 提案，决定哪些 worker 真正执行、同步还是异步、是否降级或跳过。
- `Orchestrator Worker`：语义提案者。它根据本轮命令、用户输入、writer 产出或 mode-specific signals，提出本轮 worker 调度意图和上下文需求；它不直接执行 worker，也不拥有最终 workflow 主权。
- `Context Orchestration Layer`：专门的上下文编排层。它通过 `RetrievalBroker` / Memory OS 工具读取或检索 memory，按 worker 的 block 权限、token budget 和 workspace refs 生成 `WorkerContextPacket`，避免全量上下文派发。
- `Specialist Workers`：memory block 和 runtime 上下文的领域管理者。它们读取和消化 state、projection、recall、archival、runtime workspace，并产出结构化结果。
- `WritingPacketBuilder`：确定性组包层，只消费稳定 slot 和 worker 消化后的 hints/constraints/digests，不直接消费 raw retrieval hits。
- `WritingWorker`：唯一生成用户可见正文或回应的 worker。
- `Post-write Turn Processing`：在 `WritingWorker` 输出后处理本轮整体材料，派发 block owner worker，刷新下一轮 writer-facing view，并在符合 mode / permission / accept policy 时进入 proposal、`Core State.derived_projection` refresh 或 `Recall Memory` materialization。

## Updated Design Principles

### Worker definition

`Worker` 是拥有特定 memory block 读写责任、runtime workspace、工具权限、上下文输入合同和结构化输出合同的专家执行单元。worker 可以是 LLM、deterministic service 或 hybrid executor；它是 runtime 语义单位，不等于一次 LLM 调用。

每个 worker 至少需要声明：

- `owned_blocks`：主责维护哪些 Core State / Projection block。
- `read_blocks`：可读取哪些其他 block。
- `retrieval_scope`：可搜索哪些 recall / archival domain。
- `workspace_scope`：当前 turn 的 raw hits、tool outputs、中间结果放在哪里。
- `tools`：可用的 Memory OS / retrieval / proposal / workspace 工具。
- `execution_policy`：`always_run`、`scheduled`、`post_write`、`async` 等。
- `output_contract`：writer hints、constraints、validation findings、state proposal、summary candidate、recall candidate 等。

### Worker configuration and permission levels

Setup 阶段应存在 worker 配置 stage。当前阶段 worker 选择主要由 `ModeProfile` 决定；未来可以考虑用户可选增量 worker，但那会要求 memory 层、worker 层、context orchestration、runtime 调度链一起适配，暂不作为本任务目标。

Worker 配置粒度应是：

```text
enable worker
  -> configure per-domain/block permission level
  -> compile into runtime permission profile
  -> restrict actual tools and mutation behavior
```

这意味着 UI 第一版可以简化，但底层数据结构必须支持 `per-worker + per-domain/block permission`，不能只存一个 longform-only 或 worker-wide 的粗粒度 level。

推荐权限 level：

| Level | Runtime 能力 |
|---|---|
| `observe` | 只能读取 memory / retrieval，产出 hints 或 findings |
| `suggest` | 可写 runtime workspace，可提交 writer hints / validation findings |
| `propose` | 可对 authoritative Core State 提交 proposal |
| `maintain_projection` | 可刷新 derived projection，但不能直接改 authoritative truth |
| `trusted_maintainer` | 未来高级占位：可对低风险 block 自动 apply，但需要严格版本、trace、回滚；第一阶段不开放 |

默认硬边界：

- `owned_blocks` 表示主责维护、解释权和 proposal 优先权，不表示 direct authoritative mutation 权限。
- authoritative Core State 默认只能走 governed proposal/apply。
- Runtime Workspace 可以作为当前 turn scratch 写入。
- derived projection 的刷新必须带 source refs、版本和 trace，且不得替代 authoritative truth。
- runtime 配置面板可以修改 worker 配置，但修改结果必须重新编译为 runtime permission profile，并受同一硬边界约束。

### Runtime profile snapshot and hot update

Worker / profile 配置采用版本化 snapshot，而不是让 runtime 每轮直接读取 setup draft。

```text
Setup Worker Config Draft
  -> validate / compile during activation
  -> RuntimeProfileSnapshot v1
  -> StorySession points to active snapshot

Runtime panel edit
  -> RuntimeWorkerConfigDraft
  -> validate / compile
  -> RuntimeProfileSnapshot v2
  -> atomically activate v2 for future turns
```

硬规则：

- runtime 执行只读取已验证、已发布、带版本号的 active snapshot，不读取 setup draft。
- turn 开始时 pin 当前 snapshot version；本轮执行中不受后续配置修改影响。
- runtime 面板热更新只影响下一轮或之后的 turn。
- artifact、trace、worker result、proposal、projection refresh 应能追溯当时使用的 worker/profile snapshot version。

### Block ownership first

Worker catalog 应先从 Core Store domain/block ownership 推导，而不是先按 prompt 技能拆分。当前候选 domain 包括：

```text
scene
character
relation
goal
plot_thread
foreshadow
timeline
world_rule
inventory
chapter
narrative_progress
```

第一版不要一对一拆成大量 worker，而应合并为少量 macro worker：

| Worker | 主责 block | 适用 mode |
|---|---|---|
| `LongformMemoryWorker` | `chapter`、`narrative_progress`、`plot_thread`、`foreshadow`、`timeline`、`goal` | longform |
| `CharacterMemoryWorker` | `character`、`relation`、knowledge boundary、character-local memory | roleplay / longform |
| `SceneInteractionWorker` | `scene`、current goal、recent interaction、participant intent | roleplay / trpg |
| `RuleStateWorker` | `world_rule`、`inventory`、mechanics state、consequences | trpg |
| `MaintenanceWorker` | accepted output -> proposal / projection / recall candidate | all |
| `WritingWorker` | writer-facing packet -> user-visible prose / response | all |

第一阶段实际实现仍以现有 `LongformSpecialistService` 作为 `LongformMemoryWorker` compatibility execution，不立即拆出全部 worker。

### Execution categories

Worker 不应全部进入同一个开放调度池。按执行策略分为：

| 类型 | 是否进入 LLM 调度 | 典型执行 | 说明 |
|---|---|---|---|
| baseline context prefetch | 否 | deterministic | 当前 session、phase、scene、projection、最近对话、必要 refs |
| always-run worker | 否或仅窄门控 | deterministic / hybrid | 由 mode workflow 直接编入流程，可与 orchestrator 或 prefetch 并行 |
| scheduled worker | 是 | hybrid / LLM | 由 OrchestratorWorker 提案，Scheduler 裁决 |
| post-write observer | 否 | cheap deterministic / small model | 判断是否需要维护，不默认触发完整 worker 调度 |
| maintenance worker | 门控触发 | async / proposal-producing | 只对 accepted output 或明确可沉淀事件生效 |

Interactive mode 的默认性能约束：每轮最多一个 blocking analysis LLM worker 加一个 `WritingWorker`。投机执行只能用于低成本、可丢弃、无 mutation 的 read/search/prefetch，不用于提前跑多个大 LLM worker。

### ModeProfile scope

`ModeProfile` 是 story 创建/setup 前就选择的产品级 profile，不是 runtime 末端开关。它至少包含三层：

```text
ModeProfile
  setup_profile
    - setup steps
    - required drafts
    - worker configuration stage
    - activation requirements
    - initial memory blocks

  memory_profile
    - active domains
    - core block schema
    - projection slots
    - recall / archival policy
    - optional external memory integrations

  runtime_profile
    - workflow route
    - always-run workers
    - schedulable workers
    - worker permission profile
    - post-write maintenance policy
    - writer policy
    - latency / budget policy
```

因此 longform / roleplay / trpg 不是三套完全不同系统，但也不是只换 prompt。它们共享 Memory OS、Retrieval Broker、scheduler、packet builder、writer runtime；差异由 profile 决定 setup 采集、memory block 激活、worker 心智、调度策略和 writer policy。

### Mode differentiation and abstraction boundary

Runtime 中不再额外抽象一层独立的“能力层”来承接 mode 差异。当前设计中，mode 差异的主表达面已经存在：

```text
ModeProfile
  -> setup_profile
  -> memory_profile
  -> runtime_profile
       -> workflow route
       -> worker catalog / worker policy
       -> retrieval / packet policy
       -> writer policy
```

因此 mode profile 的区分度应主要落在 worker 及其周边 policy 上，但不只落在 worker 上。更准确地说：

- setup 阶段由 `setup_profile` 决定要采集什么、配置什么 worker、激活哪些初始 block。
- memory 层由 `memory_profile` 决定 active domains、Core State block schema、projection slots、recall / archival policy。
- runtime 阶段由 `runtime_profile` 决定工作流路线、worker 默认组合、哪些 worker always-run、哪些 worker 可调度、权限 level、post-write maintenance policy、writer policy 和 latency budget。
- worker 是 mode 差异最明显的执行表达：longform 更重 `LongformMemoryWorker`、chapter / plot / foreshadow / timeline；roleplay 更重 `CharacterMemoryWorker`、`SceneInteractionWorker`、character-local memory；trpg 额外启用 `RuleStateWorker` 和 rule card / state card。

不新增独立“能力层”的理由：

- worker 已经是 memory block ownership、工具权限、上下文合同和结构化输出合同的聚合点；再拆一层能力 registry 会和 worker catalog 重叠。
- `Context Orchestration Layer` 已经负责上下文编排、refs、budget、provenance、forbidden context，它是确定性编排层，不应膨胀成另一个小 agent 池。
- 小能力应优先作为 macro worker 内部工具、deterministic helper 或 context orchestration policy，而不是变成每次都需要调度器决策的独立 worker。
- 对 interactive mode 来说，过多独立 LLM worker 会增加调度负担、上下文派发成本和延迟；第一阶段应保持少量 macro worker，并用 permission / policy 限制能力边界。

允许新增抽象的条件应很严格：只有当某个能力跨多个 worker 复用、具有稳定输入输出合同、并且不承担 memory block ownership 时，才可以作为工具/helper 抽出；否则先放入对应 block-owner worker 内部。

### Nocturne-style memory integration

`docs/research/nocturne_memory-main` 可作为角色局部记忆和触发式 recall 的参考，但不应直接替代 story-wide authoritative truth。其定位应是：

```text
Nocturne-style memory
  -> character-local memory view
  -> CharacterMemoryWorker / RoleplayMemoryWorker 的外部 memory backend 或工具来源
```

它适合支持角色局部记忆、触发条件式召回、人设/关系/长期互动记忆和 review/audit 参考；不直接替代 Core State authoritative truth、proposal/apply、TRPG mechanics state 或 story-wide timeline truth。

### Runtime Workspace turn lifecycle

为减少 longform / roleplay / trpg 的流程分叉，story runtime 使用统一的 `Runtime Workspace` turn lifecycle。这里不是新增 memory 层，也不是替代 worker；它只是把每轮已有材料组织成 scheduler、worker、builder 都能消费的稳定形状。

统一生命周期：

```text
1. collect turn material
   - user input
   - optional existing draft / review overlay
   - optional TRPG rule card / state card
   - previous prepared writer-facing view

2. build writer packet
   - Core State.derived_projection
   - Recall / Archival refs
   - worker hints / constraints
   - writing contract / mode policy

3. WritingWorker runs
   - prose / response / discussion / rewrite

4. compose turn result material
   - raw user input
   - writer output
   - optional review overlay
   - optional rule card / state card
   - packet refs and profile snapshot version

5. post-write turn processing
   - scheduler analyzes the whole turn result material
   - dispatches block owner workers
   - produces proposal / projection refresh / Recall materialization input
   - prepares next-turn writer-facing view

6. next turn starts
   - merge prepared view with new user input and optional sidecars
```

Mode 差异通过 turn material sidecar、worker policy、packet policy 表达：

| Mode | 特殊 turn material / policy | Writer 后整理点 |
|---|---|---|
| longform | draft artifact、review overlay、discussion / brainstorm input、outline or blueprint edits | writer output 后等待用户 review / rewrite / accept；accept 后进入较重维护 |
| roleplay | user input + writer output 作为同一轮 story material | writer 输出后后台整理本轮，并预编排下一轮 writer view |
| trpg | user input + rule card / state card + writer output | writer 输出后整理规则卡片和叙事结果，并预编排下一轮 writer view |

Roleplay / trpg 的主整理点在 `WritingWorker` 输出后，而不是下一轮 user input 到达后临时整理。用户阅读 writer 输出、思考和输入下一轮 prompt 的时间，应被后台调度层用于处理本轮材料、派发 worker、刷新 block、预编排下一轮 writer view。若用户输入太快，下一轮可以使用上一版 prepared view，并把未完成整理标记为 pending，不能让后台整理无界阻塞 writer。

### Longform review overlay and discussion turn

Longform 与 roleplay / trpg 的主要差异是 writer output 默认是 draft artifact，并允许用户对产出文本做留痕式修订和批注。该能力参考 Word 的修订/批注语义：用户不是直接覆盖正文，而是生成 review overlay，供后续 discussion / rewrite turn 使用。

Review overlay 属于 turn material，不是 active truth，不直接进入 `Core State.authoritative_state`。它应至少表达：

- 原文引用或范围。
- 用户建议的插入 / 删除 / 替换。
- 批注或重写意图。
- 与 draft artifact / revision / packet 的 provenance 关系。

Longform runtime 需要同时支持：

- `writing turn`：产出、续写或重写正文 artifact。
- `discussion turn`：用户与 writer 即时头脑风暴，讨论不满意点，提出修改方向，或调整当前剧情大纲 / chapter intent 的候选表达。
- `review turn`：用户以 review overlay 方式标注 draft，writer 在后续 rewrite 时可见。

这些 turn 不需要拆成独立大 agent。它们应共用 `WritingWorker`，由 `command_kind` / `output_kind` / packet policy / review overlay 决定 writer 行为。

### TRPG rule card / state card

TRPG 在统一 turn lifecycle 上额外携带规则判定卡片或状态卡片。规则相关内容不要求 scheduler / worker 从散文中反推，而应通过结构化 sidecar 进入 writer packet 和 post-write processing。

Rule card / state card 可表达：

- player action / target。
- check type / difficulty / roll result。
- cost / damage / effect。
- state_delta_candidate。
- source rule refs。

`WritingWorker` 根据卡片叙述结果，不自行暗中裁定规则。`RuleStateWorker` 和 block owner worker 在 writer 输出后读取 `user input + rule card + writer output` 的本轮材料，整理对应 `world_rule`、`inventory`、mechanics state、scene state 的 proposal / projection refresh。

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
- 当前 specialist 是 single-generalist specialist，不能清晰承载不同 memory block ownership 和 mode-specific expert 心智。
- 当前 runtime workspace 仍是隐式的 graph state / 函数局部变量，没有明确 refs、生命周期和可观测中间产物。
- 当前 `ModeProfile` 尚未作为 setup-before-runtime 的产品级 profile 驱动 setup、memory schema 和 story runtime。session 有 mode，但 prompt 和 policy 多处仍写死 longform。
- 当前缺少独立 `Context Orchestration Layer`：worker 需要的上下文仍散落在 service prompt payload、projection read、retrieval hits 和 builder inputs 之间，尚未形成 refs/budget/provenance/workspace 统一合同。
- 当前缺少统一 `Runtime Workspace` turn lifecycle：longform draft / review、roleplay continuous turn、trpg rule card 尚未有共同的 turn material / post-write processing / next-turn view 合同。
- 当前 longform 只有基础 draft artifact 和 discussion entry，尚未定义 review overlay / tracked change / comment 如何进入 rewrite packet。
- 当前 roleplay / trpg 还没有利用 writer 输出后的用户阅读和输入间隙进行后台整理、block refresh 和 next-turn view prebuild 的策略。

## Requirements

1. Worker 层必须被定义为 memory 层和 runtime 上下文的管理者，而不是单纯的 prompt 节点。
2. Worker catalog 必须优先按 Core Store / memory block ownership 设计，技能型 worker 只能作为补充，不能成为第一拆分原则。
3. 第一阶段必须保持 longform-first 行为，但 runtime 合同不能继续写死为 longform-only。
4. Orchestrator 的职责应从“生成 writer 指令”升级为“提出 worker 调度意图、上下文需求、同步/异步和优先级建议”。确定性 Scheduler 负责校验、裁决和执行 workflow。
5. Specialist worker 的输入应被显式建模为 context packet 或等价合同，表达 message refs、memory refs、summary refs、retrieval queries、workspace refs、constraints、token budget、forbidden context 等内容。
6. Context Orchestration Layer 必须负责 worker context packet 的组装，不允许默认把 raw memory / raw retrieval / raw authoritative JSON 全量派发给 worker 或 writer。
7. Worker 输出应保持结构化，至少覆盖 writer hints、validation findings、state/proposal hints、summary updates、recall summary、可选 structured metadata。
8. 现有 `LongformSpecialistService` 应继续可用，并作为第一阶段的 `LongformMemoryWorker` compatibility execution，不要求立即拆出全部 specialist workers。
9. `WritingPacketBuilder` 必须继续保持确定性边界，只消费 worker 消化后的稳定结果，不直接接收 raw retrieval hits 或 raw authoritative JSON。
10. Worker 配置 stage 必须支持“启用 worker + per-domain/block permission level”的底层粒度，并编译成 runtime permission profile。
11. Worker / profile 配置必须走 validate / compile / versioned snapshot；turn 开始时 pin snapshot version，runtime 热更新只影响下一轮。
12. Story runtime 必须采用统一 `Runtime Workspace` turn lifecycle，支持 `user input + writer output + sidecars + packet refs` 作为 post-write turn processing 的输入。
13. Roleplay / trpg 的主上下文整理点在 writer 输出后，post-write processing 不只做 maintenance，也要提前准备下一轮 writer-facing view。
14. Longform 必须为 review overlay / tracked change / comment 留合同位置，使用户能留痕式修改 draft，writer 在 rewrite / discussion turn 中可见。
15. TRPG 必须为 rule card / state card 留合同位置，使规则判定作为结构化 sidecar 进入 writer packet 和 post-write processing。
16. Mode 差异应通过 `ModeProfile` 影响 setup profile、memory profile、runtime profile、worker 心智、工具范围、retrieval 策略、packet 策略、writer 姿态和 proposal/validation 规则；但第一阶段只需要为这些入口留出合同，不要求完整实现 roleplay/trpg。
17. eval 模块由其他 session 负责。本任务不实现 eval runner、case、grader，只保证 story runtime 产物便于后续观测和接入。
18. Runtime 不新增独立“能力层”作为主抽象。小能力优先放入 macro worker、deterministic helper、Memory OS / retrieval tool 或 Context Orchestration Layer policy；只有跨 worker 复用且不承担 block ownership 的稳定能力才允许抽成共享 helper。
19. ModeProfile 的 runtime 区分度应主要通过 worker catalog / worker policy / packet policy / writer policy 表达，但不能退化成只改 prompt，也不能把 longform / roleplay / trpg 做成三套互不兼容 runtime。

## Acceptance Criteria

- [ ] `prd.md` 明确记录 worker 层定位、当前实现地图、差距和第一阶段边界。
- [ ] 第一阶段实现后，现有 longform 生成链仍可运行。
- [ ] Orchestrator 输出能表达至少一个 selected worker execution，而不只是 writer 指令。
- [ ] Specialist 分析能通过显式 worker/context 合同接收本轮上下文，现有 single specialist 仍兼容。
- [ ] PRD / spec 能表达 Core Store block ownership 到 worker catalog 的映射原则。
- [ ] PRD / spec 能表达 `ModeProfile` 作为 setup-before-runtime 产品级 profile 的三层结构。
- [ ] PRD / spec 能表达 worker 配置 stage 的 per-worker + per-domain/block permission level 粒度。
- [ ] PRD / spec 能表达 runtime profile snapshot 与 turn-start pinning 策略。
- [ ] PRD / spec 能表达统一 `Runtime Workspace` turn lifecycle，并覆盖 longform / roleplay / trpg 的材料差异。
- [ ] PRD / spec 能表达 longform review overlay 和 TRPG rule card / state card 作为 turn material sidecars 的位置。
- [ ] PRD / spec 能表达 post-write processing 负责准备下一轮 writer-facing view。
- [ ] PRD / spec 能表达 Context Orchestration Layer 的职责和“不可全量派发上下文”的约束。
- [ ] PRD / spec 能表达不新增独立能力层的抽象边界，以及小能力应优先归属 macro worker / helper / context orchestration policy。
- [ ] PRD / spec 能表达 mode 差异主要通过 `ModeProfile -> runtime_profile -> worker policy / packet policy / writer policy` 落地，同时仍共享同一套 story runtime 骨架。
- [ ] Builder 仍只消费 worker 消化后的结构化结果，不消费 raw retrieval hits。
- [ ] 新增或调整的 runtime contract 有单元测试或现有 story runtime 测试覆盖。
- [ ] 不修改 eval 模块主流程。

## Technical Approach

第一阶段采用“最小合同升级，不扩多 worker”的方式。实现目标不是立刻拆出多 specialist，而是先让现有 longform 链路具备 block-owner worker、context packet 和 deterministic scheduler 的合同位置：

```text
existing OrchestratorPlan
  -> scheduler-validated selected worker / worker context semantics
  -> Context Orchestration Layer builds WorkerContextPacket
  -> single LongformSpecialist compatibility execution as LongformMemoryWorker
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
- worker 拥有哪些 memory block，能读取哪些 block。
- worker 需要哪些 retrieval / memory refs。
- worker 的 context packet 如何由 Context Orchestration Layer 组装，不能由 orchestrator 直接塞全量上下文。
- worker 是 always-run、scheduled、post-write 还是 async。
- turn material 如何组合 user input、writer output、review overlay、rule card、packet refs。
- writer 输出后的 post-write processing 如何派发 block owner workers，并准备 next-turn writer-facing view。
- worker/profile snapshot version 如何被 pin、追溯和热更新。
- worker 输出如何进入 writer packet 或 post-write maintenance。

## Decision (ADR-lite)

**Context**：当前 story runtime 已有 longform MVP 骨架，但 orchestrator/specialist 关系仍是固定顺序调用，无法表达未来 worker catalog、mode overlay、runtime workspace refs。新的讨论进一步确认：worker catalog 应从 memory/Core Store block ownership 推导，而不是从 prompt 技能或零散小 agent 推导；`ModeProfile` 也应上提为 setup-before-runtime 的产品级 profile。

**Decision**：第一阶段不重写 runtime，不引入完整多 worker 并发，不实现 roleplay/trpg 行为。先把现有 single specialist 包装成 `LongformMemoryWorker` compatibility execution，并补清楚 deterministic scheduler、block-owner worker、Context Orchestration Layer 和 worker context packet 的合同。

**Consequences**：

- 好处：改动面小，能保持 longform MVP 可运行，同时为后续 `CharacterMemoryWorker`、`SceneInteractionWorker`、`RuleStateWorker`、`MaintenanceWorker` 留出清晰 block ownership 和 mode profile 位置。
- 代价：第一阶段仍然只有一个实际 specialist，domain accountability 不会一次到位；roleplay/trpg 的 worker 只做设计占位，不做行为实现。
- 风险：如果合同只新增字段但调用链仍硬编码 single specialist，后续会继续退化成伪调度。因此实现必须至少让 graph/domain service 开始消费 selected worker execution 和 context packet 语义。
- 风险：如果 worker 被拆得过细，会导致调度复杂、LLM 调用过多、interactive mode 延迟不可接受。因此 worker 必须保持 macro-worker 优先，小能力挂在 worker 内部或 Context Orchestration Layer 下。
- 边界：不新增独立“能力层”作为 mode 差异的主承载面。mode 差异通过 `ModeProfile` 编译成 memory profile、worker policy、packet policy 和 writer policy；worker 仍是 runtime 中最主要的 mode-specific 执行表达。

## Out of Scope

- 不实现完整 roleplay / trpg active runtime。
- 不一次性拆出全部 specialist worker。
- 不把每个能力点拆成独立 LLM worker。
- 不引入开放式大 worker catalog 自由调度。
- 不重写 retrieval core。
- 不重写 Memory OS / Core State store。
- 不把 Nocturne Memory 作为 story-wide authoritative truth 的替代品。
- 不实施 eval runner / eval case / grader。
- 不改变 setup agent 的既有冻结口径。
- 不把未被用户接受的 draft 写入 `Core State.authoritative_state`、`Recall Memory` 或 `Archival Knowledge`。

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
- `docs/research/nocturne_memory-main/README_EN.md`
- `docs/research/nocturne_memory-main/docs/TOOLS.md`

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
