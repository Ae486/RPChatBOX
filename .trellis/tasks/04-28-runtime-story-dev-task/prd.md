# runtime story dev task

## Goal

把 active story runtime 重建为以 worker 为核心的运行时编排骨架。当前 longform MVP 只作为行为观察和产品布局参考，不作为后端链路、API 形状、SSE 字段、数据模型或实现方式的硬约束。若旧链路阻碍新 `Turn / BranchHead / RuntimeProfileSnapshot / Runtime Workspace / Scheduler / Worker` 合同，或在旧链路上继续搭建的收益低于按新设计重写，允许删除旧链路并按当前设计重写一版 runtime。

本任务的核心定位是：worker 层是 memory 层和 runtime 上下文的管理者。worker 首先从 `Core State` 当前事实、Core State 当前视图 / projection block views、Recall Memory、Archival Knowledge 的 block ownership 推导，而不是从零散 prompt 技能推导。worker 负责决定如何读取、消化、维护 memory 与当前轮上下文；不同 mode 的差异主要通过 worker 的差异化实现体现。反过来，`ModeProfile` 在 setup 之前就被选择，它不仅影响 setup 流程，也决定 active runtime 的 memory schema、worker 默认路线、retrieval policy、packet policy 和 writer 姿态。

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
- `Orchestrator Worker`：语义提案者。它根据本轮命令、用户输入、writer 产出或 mode-specific signals，提出本轮 worker 调度意图和上下文需求；它不直接执行 worker，也不拥有最终 workflow 主权。它输出的不是自由文本口胡，而是机器可解析的结构化调度提案，允许通过 tool call 或严格 schema 文本表达，二者在语义上等价。
- `Context Orchestration Layer`：专门的确定性上下文编排层。它整合 writer / worker 已触发的检索结果、已有 memory refs、token budget 和 workspace refs，生成 `WorkerContextPacket`，避免全量上下文派发；它本身不是主路径上的“写前预检检索决策层”，不判断是否检索，也不决定本轮启用哪些 worker。
- `Specialist Workers`：memory block 和 runtime 上下文的领域管理者。它们读取和消化 state、projection、recall、archival、runtime workspace，并产出结构化结果。
- `WritingPacketBuilder`：确定性组包层，只消费稳定 slot 和 worker 消化后的 hints/constraints/digests，不直接消费 raw retrieval hits、Core State 原始 JSON、工具 trace、worker 中间态、Runtime Workspace 日志或 usage metadata。
- `WritingWorker`：唯一生成用户可见正文或回应的 worker。
- `Post-write Turn Processing`：在 `WritingWorker` 输出后处理本轮整体材料，派发 block owner worker。worker 完成整体分析后，优先递交 writer 下一轮需要的 Core State 当前视图 / projection block views；随后继续完成 proposal、`Recall Memory` materialization 或 `Archival Knowledge` 相关维护。这里不是另起一条“视图优先”的独立流程，而是同一轮 worker 分析完成后的递交和写入顺序。

## Development Doctrine

这条 task 不只是 longform 实现任务，而是 RP story runtime 的总架构任务。后续所有实现都应遵守同一套开发方式：

- `contract-first`：先冻结合同，再写实现。先定 DTO、权限、生命周期、输入输出和状态边界，再写具体代码。
- `registry-driven`：domain、block、worker、mode、provider、policy 都必须可注册、可配置、可替换，不允许散落硬编码分支。
- `plugin-style composition`：worker、章间承接材料、review overlay、evolution、retrieval 扩展都应通过可插拔实现承接，而不是改主流程 if/else。
- `immutable snapshot`：`ModeProfile preset` 可以升级，但 `RuntimeProfileSnapshot` 必须不可变；旧 session 只能通过显式 migration 进入新 snapshot。
- `policy over prompt`：mode 差异主要体现在 worker policy、retrieval policy、packet policy、writer policy、permission policy，而不是只换 prompt。
- `worker over ad hoc logic`：脑暴、修订、规则判定、角色模拟、章间承接、evolution 都优先落到明确 worker / helper / provider / policy，不要混成临时脚本逻辑。
- `eval-gated optimization`：可以先做最简单、最稳的默认实现，但只要 eval 反馈差，就通过替换模块或策略升级，不改主流程骨架。
- `runtime-first rebuild with selective reuse`：以新 runtime 合同为准设计和实现；旧 longform MVP 的服务、命令、SSE、数据模型、前端布局都只能作为可参考材料。若某段旧实现仍有复用价值，可以通过明确 adapter 接入；若它制造硬编码、longform-only 或非模块化阻塞，应直接替换或删除。

工程上，这意味着后续所有 feature slice 都应回答同一组问题：

- 这个能力的合同是什么？
- 这个能力是固定在主流程里，还是可以通过 registry/provider/policy 替换？
- 这个能力的默认实现是什么？
- 如果 eval 不佳，要替换哪一层，而不是重写哪一段主流程？

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
- Core State 当前视图 / projection block views 的更新必须带 source refs、版本和 trace，且不得替代 authoritative truth。
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
- `ModeProfile preset` 可以升级，但 `RuntimeProfileSnapshot` 必须不可变。旧 story session 不自动跟随新版 preset 改变运行规则；新 runtime 必须能通过 compatibility adapter 读取旧 snapshot。旧 session 如果要升级配置，必须显式执行 profile migration / refresh，生成新的 snapshot，并从下一轮开始生效。换句话说：新版系统要能打开旧故事，但不能偷偷改变旧故事的运行规则。

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

第一阶段实际实现只要求存在 registered `LongformMemoryWorker`，不要求立即拆出全部 worker。它的 executor 可以参考或复用现有 `LongformSpecialistService`，也可以按新 worker 合同重写；判断标准是是否服务于 `WorkerDescriptor / WorkerExecutor / WorkerContextPacket / WorkerResult`，不能让旧 service 反向约束新 runtime。

Worker 系统的工程化口径是 contract-first、registry-driven、plugin-style worker catalog。也就是说，worker 不是“每个 worker 一套完全不同代码链”，而是共享统一基础合同：

```text
WorkerDescriptor
  -> 声明 worker id、domain binding、phase、权限、工具、模型/供应商、输入输出 schema

WorkerExecutor
  -> 统一执行入口

WorkerContextPacket
  -> Context Orchestration Layer 组好的 worker 输入

WorkerResult
  -> 结构化输出：hints、projection refresh、proposal、evidence、trace、pending 等
```

不同 worker 的差异应主要通过 descriptor、domain binding、phase policy、tool allowlist、prompt / profile、permission policy 和 output schema 表达，而不是把每个 worker 写成一条独立流程。Scheduler 只依赖 worker registry 和统一合同，不直接写死某个 worker 类名、mode 分支或 domain 列表。worker 应能通过 `RuntimeProfileSnapshot` 启用 / 禁用、绑定 domain、调整权限、选择 provider / model，并在测试中用 fake executor 替换。用户说的“基础模板 + 按需小修小改 + 可装卸”，工程化表述就是：统一 worker contract + declarative descriptor + pluggable executor + registry / config driven discovery。

### Execution categories

Worker 不应全部进入同一个开放调度池。按执行策略分为：

| 类型 | 是否进入 LLM 调度 | 典型执行 | 说明 |
|---|---|---|---|
| baseline context prefetch | 否 | deterministic | 当前 session、phase、scene、projection、最近对话、必要 refs |
| always-run worker | 否或仅窄门控 | deterministic / hybrid | 由 mode workflow 直接编入流程，可与 orchestrator 或 prefetch 并行 |
| scheduled worker | 是 | hybrid / LLM | 由 OrchestratorWorker 提案，Scheduler 裁决 |
| post-write observer | 否 | cheap deterministic / small model | 判断是否需要维护，不默认触发完整 worker 调度 |
| maintenance worker | 门控触发 | async / proposal-producing | 只对 accepted output 或明确可沉淀事件生效 |

`always-run worker` 表示 workflow 级必经能力，不表示每次触发调度都必须无条件重跑一次重 worker。只要本轮进入该 mode 的对应 workflow，Scheduler 必须纳入该能力并记录裁决；但可以按 mode、budget、dirty blocks、内容变化、manual refresh、retrieval 行为和调度频率，将其执行方式裁成只读预取、复用上一版结果、轻量检查、pending 标记或完整执行。真正会消耗大模型、产生 mutation、刷新 projection 或提交 proposal 的动作仍必须满足触发条件、权限和 base revision / trace 约束。

`scheduled worker` 则不在 workflow 中天然必经。它由 OrchestratorWorker 根据本轮材料提出启用建议，再由 Deterministic Scheduler 结合 worker catalog、权限、budget、phase、mode profile 和冲突状态进行裁决、派发、降级或拒绝。LLM 提案不能直接等于 worker 执行。

`OrchestratorWorker` 的提案合同必须稳定、可解析、可回放。至少要表达：候选 worker、建议 phase、建议上下文 slot / refs、理由、预算占用、是否必须执行、是否允许降级、以及需要后端校验的约束条件。后端不能依赖自由文本语义去猜它想表达什么。

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

ModeProfile 的实现不能依赖写死分支。第一版应采用“必要默认配置 + 用户可调 + registry / config 驱动”：ModeProfile 负责给各 mode 预设默认 domain / block 激活集合和默认 worker 路线，但调度器、Memory OS、worker catalog、Context Orchestration Layer、packet builder 和权限链都必须通过 registry / config / RuntimeProfileSnapshot 读取，而不是在代码里硬编码 longform / roleplay / trpg 各自的固定列表。这样后续增加、隐藏、废弃、删除或迁移 worker / domain / block 后，相关链路仍能按配置发现和调用对应功能。

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

ModeProfile 的默认 domain / block 展示和激活集合也必须是 registry-driven，而不是写死在调度器里。第一版可以有必要默认配置，例如 longform 偏 `chapter / narrative_progress / timeline / plot_thread / foreshadow / character / scene / knowledge_boundary`，roleplay 偏 `scene / character / knowledge_boundary / relation / goal / timeline / world_rule`，trpg 额外启用 `rule_state / inventory / world_rule`，但这些只应作为默认值和模板，不是硬编码常量。

不新增独立“能力层”的理由：

- worker 已经是 memory block ownership、工具权限、上下文合同和结构化输出合同的聚合点；再拆一层能力 registry 会和 worker catalog 重叠。
- `Context Orchestration Layer` 已经负责上下文编排、refs、budget、provenance、forbidden context，它是确定性编排层，不应膨胀成另一个小 agent 池；它只消费已有材料和结构化结果，按 mode / turn / window / token policy 组包。
- 小能力应优先作为 macro worker 内部工具、deterministic helper 或 context orchestration policy，而不是变成每次都需要调度器决策的独立 worker。
- 对 interactive mode 来说，过多独立 LLM worker 会增加调度负担、上下文派发成本和延迟；第一阶段应保持少量 macro worker，并用 permission / policy 限制能力边界。

允许新增抽象的条件应很严格：只有当某个能力跨多个 worker 复用、具有稳定输入输出合同、并且不承担 memory block ownership 时，才可以作为工具/helper 抽出；否则先放入对应 block-owner worker 内部。

### Worker phases

Worker catalog 按 block/domain ownership 划分，不按流程阶段拆成两套 worker。同一个 worker 可以在不同 phase 下执行不同任务：

```text
Worker
  phase = pre_write_context
    -> read block / retrieval / recent turns
    -> produce writer hints / packet slot / constraints

  phase = post_write_maintenance
    -> read user input + writer output + sidecars
    -> produce block view update / proposal / recall candidate
```

例如 `CharacterMemoryWorker` 在写前负责给 writer 当前角色状态、语气、关系和知识边界；在写后负责整理角色状态、关系变化和可见信息。worker 身份不变，phase 决定工具权限、输入合同、输出合同和是否阻塞。这样避免拆出 `CharacterPreWriteWorker` / `CharacterPostWriteWorker` 这类重复 worker，保持 worker 配置、mode overlay、block ownership 和外部角色记忆集成的一致性。

### Nocturne-style memory integration

`docs/research/nocturne_memory-main` 可作为角色局部记忆和触发式 recall 的参考，但不应直接替代 story-wide authoritative truth。其定位应是：

```text
Nocturne-style memory
  -> character-local memory view
  -> CharacterMemoryWorker / RoleplayMemoryWorker 的外部 memory backend 或工具来源
```

它适合支持角色局部记忆、触发条件式召回、人设/关系/长期互动记忆和 review/audit 参考；不直接替代 Core State authoritative truth、proposal/apply、TRPG mechanics state 或 story-wide timeline truth。

### Runtime Workspace turn lifecycle

为减少 longform / roleplay / trpg 的流程分叉，story runtime 使用统一的 `Runtime Workspace` turn lifecycle。它不是长期事实层，也不是剧情真相层，而是当前轮的日志 / 工作区层：把每轮已有材料组织成 scheduler、worker、builder 都能消费的稳定形状。

统一生命周期：

```text
1. collect turn material
   - user input
   - optional existing draft / review overlay
   - optional TRPG rule card / state card
   - previous prepared writer-facing view

2. build writer packet
   - Core State current facts and projection block views
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
   - worker finishes whole-turn analysis
   - worker first submits projection block view updates needed by the next writer turn
   - worker then completes proposal / Recall materialization / Archival Knowledge maintenance when allowed
   - runtime workspace keeps the minimum turn log, usage, refs, pending marks and trace for later replay / rollback / branch / supplementary scheduling

6. next turn starts
   - merge prepared view with new user input and optional sidecars
```

Mode 差异通过 turn material sidecar、worker policy、packet policy 表达：

| Mode | 特殊 turn material / policy | Writer 后整理点 |
|---|---|---|
| longform | draft artifact、review overlay、discussion / brainstorm input、outline or blueprint edits | writer output 后等待用户 review / rewrite / accept；accept 后进入较重维护 |
| roleplay | user input + writer output 作为同一轮 story material | writer 输出后后台整理本轮，并预编排下一轮 writer view |
| trpg | user input + rule card / state card + writer output | writer 输出后整理规则卡片和叙事结果，并预编排下一轮 writer view |

Roleplay / trpg 的主整理点在 `WritingWorker` 输出后，而不是下一轮 user input 到达后临时整理。用户阅读 writer 输出、思考和输入下一轮 prompt 的时间，应被后台调度层用于处理本轮材料、派发 worker、整理 block、预编排下一轮 writer view。若用户输入太快，下一轮可以使用上一版 prepared view，并把未完成整理标记为 pending，不能让后台整理无界阻塞 writer。

这种 pending 情况依赖“每 X 轮完整调度一次 + 近几轮原文窗口”共同兜底。完整调度可以异步或延后完成；近 X 轮 user input / writer output 原文窗口则保留刚发生的互动、用户意图、语气和细节。即使 Core State 当前视图 / projection block views 暂时还没刷新，writer 仍能通过近轮原文保持现场连续性。pending 标记必须进入 Runtime Workspace / 当前轮日志层，供后续补调度和 trace 使用。

这里的 `WritingWorker` 输出不是两条线路，也不是在现有流程外另起一个轻量流程。`WritingWorker` 只有一个用户可见产出；该产出与 user input、sidecars、packet refs 一起组成同一份 turn result material，进入同一个 post-write workflow。第一版前台可以先把 writer 文本返回给用户，不要求同步等待完整 post-write 完成；但后台必须立即继续 post-write，并把 pending / deferred / settled 状态写入 Runtime Workspace / 当前轮日志层。若用户下一轮输入到来而上一轮仍有必需刷新未完成，系统必须按这些状态决定等待、提示 pending，或在允许的前提下先使用上一版稳定视图加近几轮原文窗口继续，不能让后台整理无限悬空。

第一版应把这些状态收成显式 turn 合同，而不是只放在局部 graph state 中。最小需要能区分：writer 已完成但 post-write 还没跑完、post-write 正在跑、post-write 被允许延后、turn 已 settled、turn 失败。branch/fork 只允许从 settled turn 派生；pending / deferred 状态必须能通过 `StorySession / BranchHead / Turn` 精确追溯，并进入下一轮 gating。

Core State 当前视图 / projection block views 也不能替代近几轮原文。Context Orchestration Layer 给 writer 组包时，应保持 writer packet 窄而干净，默认只包含：

- Core State 当前视图 / projection block views：提供稳定、压缩、可跨轮消费的当前状态。
- 近 X 轮 user input / writer output 原文窗口：保留措辞、语气、细节、用户即时意图、角色互动节奏和刚刚发生但还不适合沉淀进视图的内容。
- mode 特殊内容：例如 longform review overlay、roleplay 角色相关材料、TRPG rule card / state card 等。
- 可能的 Recall Memory / Archival Knowledge 检索卡片、refs 或已经展开的内容：补充更远历史和外部设定。
- system prompt / writer contract：写作规范、文风、输出约束和 setup 阶段形成的 writer 规则。

因此 writer packet 不能完全依赖当前视图；当前视图负责“当前事实和可见重点”，近几轮原文负责“现场连续性和细节保真”。Runtime Workspace 中的日志、工具调用过程、trace、usage metadata、worker 内部中间态默认不进入 writer packet，只服务 scheduler、worker、回退、分支、审计和补调度。Context Orchestration Layer 的职责是按 mode、turn、token budget 和窗口策略决定上述材料比例，并剪掉不应污染 writer 上下文的内部材料。

Core State 当前视图的形成不是纯确定性策略，也不是让调度器每轮读取完整 writer packet 后二次判断。rp / trpg 的推荐流程是：writer 输出后，由调度器或专用轻量节点生成一份本轮简报，通常只概括本轮 user input + writer output + sidecars 的关键变化，并携带 source refs。该简报不是事实来源，只是任务入口和压缩索引；启用的 block-owner worker 基于简报和 source refs，判断自己负责的 block 中哪些事实应进入当前视图 / projection block views。最终 writer packet 具体包含哪些视图 slot、近几轮原文、Recall / Archival 结果，仍由 Context Orchestration Layer 根据 packet policy、token budget 和 window 配置组装。

调度频率应可配置。既然 writer 输入由“Core State 当前视图 / projection block views + 近几轮原文窗口”共同构成，就不一定每轮都需要完整调度和 worker 视图刷新。ModeProfile / runtime config 应允许配置每 N 轮做一次完整调度，或在出现 user edit、rule card、scene switch、明显状态变化、manual refresh、window overflow、dirty block 等事件时触发调度。未触发完整调度的 turn 可以继续使用上一版当前视图，并依靠近几轮原文窗口保留现场连续性；但不能跳过 Runtime Workspace / 当前轮日志层的最小记录，因为后续补调度、回退、分支和 trace 都依赖它。

上下文窗口和 token 统计的口径：story runtime 不应把 token 使用量当作纯本地估算。已有 chat 侧设计已经从上游 LLM 返回内容的 metadata / usage 中读取实际 token 消费量，story runtime 应沿用这一原则。Context Orchestration Layer 可以在组包前使用预算和预估辅助裁剪，但本轮实际消费量应来自 writer / worker LLM 调用返回的 usage metadata，并在 `WritingWorker` 输出后回写为当前窗口的可观测结果。用户调整窗口大小时，影响后续 turn 的上下文编排策略，不回改已经完成的 turn。

### Writer-side bounded retrieval for knowledge gaps

writer 检索知识的主路径必须避免混淆：Context Orchestration Layer 是既有上下文编排层，不是新加的写前预检调度层。它负责把已有材料、工具结果、卡片、refs、预算和窗口策略组包给 writer / worker；它不在主路径上主动判断“本轮是否缺知识”，也不替 writer 决定发起新检索。

知识不足场景的主流程是：

```text
writer receives normal packet
  -> writer judges current information is insufficient
  -> writer calls a controlled retrieval tool
  -> retrieval layer performs query augment / search / rerank
  -> runtime stores returned cards and refs in Runtime Workspace
  -> writer receives summary cards first
  -> writer may request full content for selected cards
  -> writer produces the only user-visible output
  -> retrieval happened, so post-write scheduling is required
  -> block-owner workers process the actually used retrieval cards
  -> governed facts may enter Core State authoritative state and projection views
```

这里的 writer 可以触发受控检索，但不是自由 agent。它只能通过统一 retrieval 工具进入 RetrievalBroker / retrieval service，必须受 branch visibility、mode policy、retrieval budget、attempt limit 和 tool schema 约束。它不能绕过工具直接读取 Recall / Archival store，也不能把召回材料直接写入 Core State。

retrieval 层负责 RAG 能力本身：query augment、search、filters、rerank、score、provenance、摘要 / 摘录 / refs 返回。query augment 是 retrieval 层的合理职责，例如把“打工”扩展为“工作、打工地点、雇主、同事、排班、最近工作冲突”等检索表达。retrieval 层不负责结合 writer 当前上下文做剧情理解型总结或创作性总结；它不替 writer 判断“这条资料该如何写进当前场景”，也不替 worker 判断“这条资料是否应沉淀为事实”。retrieval 给材料，writer 判断怎么用，worker 写后判断是否治理进入 Core State / Recall / Archival。

召回材料的临时存储位置是 Runtime Workspace，不是 Recall Memory，也不是 Context Orchestration Layer。Runtime Workspace 应保存本轮检索卡片、短编号映射、真实 query / hit / chunk / provenance refs、摘要、展开内容、missed query、attempt trace 和 usage record。Recall Memory 是历史材料层；Context Orchestration Layer 是编排能力；二者都不应承担“本轮 raw retrieval hit 暂存区”的语义。

writer 可见的检索结果应采用“卡片”和短编号，而不是底层随机 id。这里的“卡片”不是 UI 卡片，而是结构固定、后端可解析、可追溯的召回条目结构体。runtime 可以把底层 `hit_id` / `chunk_id` / `block_id` 映射成 `R1`、`R2`、`R3` 这类本轮短编号，并在结构体中保留真实 retrieval refs、摘要 / 摘录、可展开入口和 provenance。writer 如果摘要不够，只能通过受控展开工具请求指定卡片全文或邻近 chunk。展开请求仍按 Runtime Workspace 的映射回到真实 retrieval ref，并返回稳定结构；writer 不需要记忆随机字符串。

若检索无命中或低置信，不应立刻失败。writer 可在受控 attempt limit 内调整 query 再检索。多次 miss 后，writer 必须记录 `knowledge_gap`，并按 mode / hard-constraint policy 选择保守写作、提示信息不足或停止生成。第一版不要把 miss policy 做复杂，主要通过 writer prompt / system prompt / writer contract 表达 mode-specific 行为，再由 runtime guard 强制记录 `knowledge_gap`。longform 可保守继续写，必要时在交流栏提示信息不足；roleplay 可继续互动但绕开缺失细节，不编造明确角色历史 / 设定事实；TRPG 如果缺的是硬规则、数值或判定依据，不能编造，应暂停、要求补规则或走规则 worker fallback。所有 mode 都必须留下 gap trace，供 post-write 调度和 eval 使用。

只要本轮发生 retrieval，runtime 必须强制一条 retrieval usage hook。第一版 usage record 必须通过独立工具调用提交，不能混在最终正文里。writer 在最终输出前必须提交结构化 usage record，说明哪些卡片被使用、哪些被展开但未使用、哪些 query miss、是否带着 knowledge gap 继续写。这个 hook 只有“用到哪些条目 / gap 对输出有什么影响”需要 writer 判断；卡片映射、存储、展开、attempt limit、trace 和 post-write routing 都是固定代码逻辑。后端可以用 runtime guard 校验：发生 retrieval 但缺 usage record 时，不接受 final output 或触发 repair。

usage record 的最小合同：

```json
{
  "used_card_short_ids": ["R1", "R3"],
  "expanded_card_short_ids": ["R3"],
  "unused_card_short_ids": ["R2"],
  "knowledge_gaps": [
    {
      "query": "Taki 打工地点",
      "status": "missed",
      "impact": "无法确定具体店名，只保守写为夜班打工"
    }
  ]
}
```

上面是 writer-facing 的短编号示例。持久化后的 `RetrievalUsageRecord` 还必须包含 backend-resolved 的 `used_card_material_ids`、`used_expanded_chunk_material_ids`、`unused_card_material_ids` 和 `missed_query_material_ids`，供 post-write 直接消费，而不是从自然语言或短编号重新猜测。

如果本轮发生 retrieval 但 usage record 缺失，runtime 不应直接接受 writer final output，应要求 writer 补交 usage record 或走一次受控 repair。post-write scheduler 只读取 usage record 中 backend-resolved 的 `used_card_material_ids`、必要的 `used_expanded_chunk_material_ids` 和 `knowledge_gaps`；未使用卡片只保留 turn trace，不沉淀进 Core State。因为“卡片”是稳定结构体，post-write scheduler 应直接读取这些结构化字段，不再通过自然语言二次判断 writer 实际使用了哪些召回内容。

writer 工具阶段默认不对用户展示，也不对用户流式输出。retrieval、expand、usage record、tool result 和相关 trace 必须进入 Runtime Workspace / 当前轮日志层，供 scheduler、worker、回放、eval 和后期调试使用；用户默认只看到最终正文阶段的流式输出。后续如果需要调试面板或 eval 面板，可以从日志层取出这些工具过程，但它们不污染 writer packet，也不作为普通用户界面的一部分。

写后处理的核心规则：检索卡片和展开 chunk 是证据，不是事实。worker 应追溯原始 chunk / provenance，把真正需要长期遵守的内容整理为 Core State 当前事实候选，再按 permission level、proposal / apply 或用户审查写入。下一轮 writer packet 应裁剪或压缩 raw retrieval 内容，优先使用已经进入 Core State 当前事实 / 当前视图的信息；未沉淀的 raw hit 仅按 Runtime Workspace / turn trace 保留。

retrieval raw content 在 Runtime Workspace 中只是临时材料，只服务本轮 writer 和随后那次 post-write 调度。调度完成且 worker 整理完成后，真正需要长期保留的内容由 worker 按权限进入 Core State、Recall Memory 或 Archival Knowledge；Runtime Workspace 只保留 usage record、短编号映射、provenance refs、trace summary 等 eval / 回放 / 审计需要的结构化记录。raw hit、展开全文、工具中间结果默认删除、标记 `discarded` / `expired`，或只保留可重建引用。如果 worker 未完成或失败，临时材料不能删除，应保持 pending，等待补调度或 repair。

### Acceptance signal, rollback, and branch semantics

Roleplay / trpg 的 writer output 使用“可见即暂定成立，下一轮输入后稳定成立”的语义。当前阶段 acceptance signal 直接以用户发送下一条消息为准：

```text
turn N writer output shown to user
  -> immediately visible to next-turn context as tentative story material
  -> user sends turn N+1 message
  -> turn N writer output becomes accepted for maintenance
```

这意味着 writer output 出现后，可以进入下一轮可见的 Core State 当前视图 / projection block views 和近几轮原文窗口；但在用户还可能重试、回滚或要求改写时，不应立即做不可回退的重型沉淀。等用户发送下一条消息、显式接受，或 mode policy 规定自动接受后，上一轮 output 才进入更稳定的 proposal、Recall Memory materialization、Archival Knowledge 维护等链路。Longform 默认仍以 draft artifact / accept / review overlay 为门槛，不把未接受 draft 当作稳定故事事实。

回退能力是 story runtime 的核心架构要求，不是 UI 小功能。使用 LangGraph 作为外壳的一个重要原因，就是保留 turn-level 版本回溯能力。回退和分支必须分清：

```text
回退 rollback:
  当前主线从 turn 15 回到 turn 12。
  turn 13-15 对当前主线失效，默认不能再前进回去。
  后续如果继续写，就是从 turn 12 重新往后走。

分支 branch:
  在 turn 12 保留两条未来。
  旧的 turn 13-15 是一个分支，新的 turn 13' 之后是另一个分支。
  两条未来都可以被保存、切换、继续。
```

当前阶段优先实现 / 设计的是回退，不是完整分支管理。初步口径：

- runtime 应保留最近 X 轮的 memory 层版本，具体 X 由后续配置决定。
- 回退到某一轮后，各个文本储存层、Core State 当前事实、Core State 当前视图 / projection block views、Recall Memory materialization 状态、Runtime Workspace 可观测结果，都应回到对应 turn 的一致状态。
- 回退是单向的：往回走后，目标 turn 之后的内容对当前主线都没有用了，默认应标记为失效 / 不可见，而不是继续参与检索、组包或维护。
- 回退后不应该还能在同一条主线里“前进回 turn 15”。如果用户确实要保留原来的 turn 13-15，那不是回退，而是分支能力。
- 分支能力暂不作为第一阶段完整目标，但底层不能把未来扩展堵死。后续如果做分支，需要能把旧路径作为另一条故事线保存并继续。
- chat 侧的多版本 / 重试只能视为当前消息或当前 turn 内的候选，不等同于完整 story branch。只有当某个候选被用户继续输入确认后，它才进入主线维护。
- `fork created`、`branch switched`、`branch deleted` 这类分支控制动作不应创建新的 story turn。它们只写 branch/control receipts 与必要 trace，不进入正文时间线，也不成为正文回退锚点。

架构含义：版本回溯不能只保存 graph checkpoint，也不能只保存文本消息。story runtime 需要把 turn checkpoint、artifact / discussion 文本层、Core State revision、projection block views、Recall / Archival materialization 结果、packet/window metadata 放在同一个可回溯边界下。第一阶段可以先把回退合同和 trace 打通，不要求完整 branch UI，但不能把 memory 写入设计成无法让 turn 13-15 在回退后对当前主线失效的单向覆盖。

统一回溯锚点应冻结为 `Turn`，更具体地说，是当前 `BranchHead` 上的已完成 `Turn`。用户看到的“回到轮次一 / 轮次二”，本质上都是把当前主线切回某个 `Turn` 的完成状态，而不是分别回退 writer 文本、Core State、Recall 或 Runtime Workspace。所有带版本的内容都应依附这个 `Turn` 回溯：

- writer / user 的这一轮对话结果，是 `Turn` 的正文与可见交互材料。
- 同一 `Turn` 内如果 `Core State` 改了多版、projection 刷了多版、Runtime Workspace 写了多批材料、Recall / Archival 做了多次受治理更新，这些都属于该 `Turn` 内部版本，不单独成为回溯锚点。
- 回退到某个 `Turn` 时，应恢复该 `Turn` 的最终可见状态，也就是该轮结束后用户实际看到并确认可继续的状态。
- 因此，如果轮次二中 writer 完成一版输出、调度完成一轮、Core State 更新一版、随后用户又手动修改了一版 `Core State`，那么“回到轮次二”应回到这整个轮次二完成后的最终状态，包含用户手动修改后的 `Core State`；轮次三产生的 writer 输出、retrieval 卡片、Core State 更新、Runtime Workspace 材料都对当前主线隐藏 / 失效。
- 如果回到轮次一，则轮次二和轮次三的所有后续内容都对当前主线隐藏 / 失效。

换句话说：`Turn` 是统一回溯锚点；`Core State revision`、`projection block view revision`、`Recall materialization revision`、`Runtime Workspace material lifecycle`、writer output revision 都是附属于该 `Turn` 的内部版本。实现上需要记录这些内部版本的 provenance 和最终落点，但产品语义上的“回到哪一轮”只认 `Turn`。

这里要特别排除一个误解：用户手动修改 `Core State` 不单独成为新的 story turn。它是当前 `StorySession / BranchHead` 下、两次可视对话轮次之间的一次受治理状态变化，需要有 revision、trace、provenance、冲突检查和视图刷新，但产品语义上的回退锚点仍然只认可视对话轮次对应的 `Turn`。因此回退到轮次二时，如果轮次二完成后、轮次三开始前用户又手动改了一次 `Core State`，该修改应被视为轮次二完成状态的一部分。

为了让“该轮是否已经完全完成、能否正式回退”可判定，story runtime 需要一层按轮次归属的后台任务账本。工程上可理解为 `turn-scoped workflow job ledger`：凡是属于某个可视对话轮次后处理链的后台任务，都必须带上该 `Turn` 的标识。它们不是新的回退锚点，而是归属于该 `Turn` 的工作项。只有当该 `Turn` 下所有“必需完成”的后台任务都完成，或被 mode policy 明确标记为可延后，且不存在未处理的关键失败，该 `Turn` 才算“该轮完全完成”，才能成为正式回退点。

这里也必须坚持“先有全局口径，再裁第一版最小集合”。后台任务账本不应只按第一版当前需要的几个任务硬编码，而应先冻结一套全局 `job_kind` 设计：至少区分 `turn-finalization`、`state-governance`、`memory-materialization`、`maintenance-and-repair` 四类。然后再决定第一版真正落地哪些 `job_kind`、哪些是预留合同。这样后续新增 proposal/apply、Recall / Archival 沉淀、repair/retry、cleanup/reindex 时，不需要推翻 job ledger 和 turn 完成判定模型。

同样需要区分“创建轮次时就必须登记的后台责任”和“分析后再派发的任务”。第一版建议把 `required_post_write_analysis`、`runtime_workspace_finalize` 作为 `creation-time obligations`：一旦该轮 writer 文本允许返回，这两个责任就必须和 `Turn` 同事务登记。其余如 `projection_refresh`、proposal/apply、Recall / Archival 沉淀、repair/retry、cleanup 等，默认作为 `derived jobs`，在 post-write 分析结果出来后按需派发。这样即使服务在 writer 返回后立刻崩溃，系统重启后仍知道该 `Turn` 有哪些最低限度的后处理责任未完成；同时避免在 turn 创建时预建大量根本不会执行的空任务。

失败恢复也必须明确分层。story runtime 中大多数真正高频的失败通常不在确定性逻辑，而在 LLM / worker 输出上：结构化结果不合法、缺字段、tool 调用链未收口、worker 产出无法通过校验。因此第一版应区分：

- `deterministic failure`：存储、约束、状态机推进、持久化失败。优先记录失败 job，不做复杂自愈，通过 retry、人工修复或显式用户决策恢复。
- `LLM / worker failure`：允许 worker 走一次轻量 repair / bounded retry / schema 修复，可参考现有 setup agent 的受控自恢复思路；超过受控次数后才进入明确失败。

无论哪类失败，只要 writer 文本已经成功返回给用户，该文本都不自动撤回；但只要必需 post-write 失败，该 `Turn` 就不能进入 `settled`，下一轮必须经过错误提示、retry / repair 或显式用户决策的 gating。longform 默认更严格，下一轮正文写作通常等待恢复成功或用户明确决定；roleplay 可在 failure 被显式标记时继续，并优先使用上一版稳定视图；TRPG 如果失败涉及规则判定或状态推进，默认不能静默继续。

为了便于追溯问题，但又不把状态系统做得过重，`Turn` 和后台 job 都应采用“状态 + 轻量 reason 字段”模式，而不是把所有语义都塞进状态本身，也不是做一整套自由文本诊断体系。推荐做法是：

- `StoryTurnRecord.status` 表示生命周期状态。
- `StoryTurnRecord.settlement_reason` 只解释为什么该轮被判定为正式完成 / 可回退点。
- `StoryTurnRecord.failure_reason` 只解释为什么该轮进入失败终态。
- `RuntimeWorkflowJobRecord.status` 表示任务状态。
- `RuntimeWorkflowJobRecord.completion_reason / failure_reason` 只解释任务终态。

这些 reason 字段应优先使用稳定枚举值，保持轻量，便于追溯、统计、调试、eval 和恢复策略分流；更细的错误文本放在 `last_error`、trace、event 或 metadata 中，而不是把 reason 字段膨胀成第二套复杂状态机。

留痕基础设施也必须按成熟工程方式设计：不让 `eval` 反向拥有业务日志，不做一个“什么都懂”的超级日志模块，而是采用“统一基础设施，分散业务产出”的结构。也就是说：

- `Turn`、job ledger、Runtime Workspace、memory change event、proposal/apply receipt、brainstorm apply receipt 都进入同一片 runtime `trace/audit` 基础设施区域。
- 各业务模块继续拥有自己的语义和状态推进权，只按统一 DTO、统一 repository、统一 identity、统一 reason/status 字段把记录写进去。
- debug 页面和 eval 模块统一从这片 `trace/audit` 区域读取。
- `eval` 是消费者，不是日志主拥有者；它不反向定义业务主记录，也不作为业务模块写留痕的入口。

推荐的工程分层是：

- `anchor records`：`StoryTurnRecord`、`BranchHeadRecord`、`RuntimeProfileSnapshotRecord`
- `workflow job ledger`：`RuntimeWorkflowJobRecord`
- `turn material trace`：`RuntimeWorkspaceMaterialRecord`
- `memory event spine`：`MemoryChangeEventRecord`
- `governance receipts`：proposal/apply receipt、brainstorm apply receipt
- `read side`：debug/eval query surfaces

这套分层的目标是：语义归业务模块，存储与查询归统一基础设施，消费者统一读取，而不是每个模块各写各查，或反过来全部耦合到 eval。

为了让这套基础设施真正可查、可恢复、可审计，还应冻结一套轻量统一引用规范。成熟工程通常不会让各模块只靠 `metadata_json` 里散落的字符串来关联记录，也不需要一开始就上重型 tracing 平台。更合理的做法是：

- 每类主记录保留自己的主键，例如 `turn_id`、`job_id`、`material_id`、`event_id`、`proposal_id`、`apply_id`、`summary_item_id`。
- 再统一约定少量标准关联字段，例如 `turn_id`、`job_id`、`parent_job_id`、`source_ref_ids`、`result_ref_ids`、`trace_refs`。
- `trace_refs` 采用稳定前缀式 ref，例如 `turn:<id>`、`job:<id>`、`material:<id>`、`event:<id>`、`proposal:<id>`、`apply:<id>`、`summary_item:<id>`。

原则上：业务主关系优先使用显式字段，不依赖 `metadata_json` 猜；`metadata_json` 只放补充细节。这样 debug、eval、repair、retry、rollback 查询都能沿着统一 ref 稳定追溯，而不会因为各模块各自留痕风格不同而越做越乱。

分支能力属于比回退更强的版本能力。分支不是“回退后还能前进回旧未来”，而是从某一 turn 开始保留多条互相隔离的故事线。分支可以随时切换或删除；两条分支的 memory 层、上下文窗口、Runtime Workspace、Recall materialization 和 writer-facing packet 必须互相隔离。后续进入分支能力时，应采用类似 Git / Dolt / lakeFS 的 copy-on-write 思路：创建分支不复制整套 memory，只创建新的分支头；分支之间共享 fork 之前的历史，fork 之后只为新增或修改的文本、Core State revision、projection block views、Recall / Archival materialization、packet/window metadata 写入分支专属记录。

第一版产品展示不要求把主聊天流直接画成复杂树状图。当前口径是：主聊天流始终展示当前 active branch 的线性 `Turn` 列表；分支能力先只提供“从这里分支”的入口和一个最小 branch 面板，用来查看 / 切换分支以及看到 fork 起点。点击“从这里分支”后，系统立即切换到新 branch，主聊天区按新 branch 线性重建；fork 点之后旧分支的后续消息从主视图消失，避免把“旧未来”误显示成“新分支后续”。为避免用户误以为消息丢失，第一版前端应至少提供三种轻量提示：顶部常驻当前 branch 标识、fork 点处的轻量提示条，以及 branch 面板中的 origin/fork 起点信息。更重的消息树可视化、树杈布局和对比分支体验后续再单独设计和优化。

分支切换时，原分支尚未完成的 Runtime Workspace 材料、worker candidate、pending 标记和后台调度结果不跟随切到新分支。这些材料继续挂在原 `BranchHead` 下，作为原分支自己的临时材料、候选更新和 trace。新分支只读取 fork 前共享的 settled memory、自己分支上的 memory / context / workspace，以及自己后续产生的 pending / worker candidate。这样可以避免两个未来互相污染，也让分支切换、删除、回退和补调度的边界保持清楚。

分支删除的第一版可以先做 deleted / hidden 可见性标记，让产品语义表现为“该分支已删除、不可见”。但最终能力必须支持物理删除分支专属材料。物理删除只清理 fork 后该分支独占的 Runtime Workspace、worker candidate、pending、Core State revision、projection block views、Recall materialization、packet/window metadata、retrieval 派生记录和其他分支专属 trace；不能删除 fork 前共享 settled memory，也不能误删 story-global Archival Knowledge 或其他分支仍可见的资料。

LangGraph 可以提供 checkpoint / time travel / fork 的 workflow 外壳，但不能自动让外部 memory store、retrieval index 或文本 artifact 具备分支隔离。RP runtime 必须在应用层把 branch / turn 可见性贯穿到 Core State、Recall Memory、Archival Knowledge、Runtime Workspace、retrieval metadata filter、artifact / discussion entry 和 packet/window metadata。第一阶段不实现完整分支 UI，但数据合同不能堵死后续分支隔离。

分支 / 回退模块的实现优先依赖 LangGraph 现成能力和它已有的 checkpoint / replay / fork 基础。Story runtime 只在框架支持的边界上向上设计；如果某个 branch / rollback 语义当前框架不支持，第一阶段先不强行补齐，不为了追功能去硬造一套替代时序引擎。

Letta 源码调研确认：Letta 和本项目一样，核心记忆操作并不是“存储层自动搬运”，而是由 agent 通过工具管理 memory。Letta 的 core memory blocks 常驻上下文；archival memory 通过工具搜索 / 写入；conversation history 通过 conversation search 查询；当前 context window 超限时由 summarizer / eviction 裁剪。block 变化后会触发 system prompt / context rebuild。对 RP runtime 的启发是：worker 也应该通过统一 Memory OS / Retrieval Broker 工具读取、检索和提交候选更新；差异在于 RP runtime 还必须把剧情真相、用户编辑、worker 权限、mode profile、回退、分支和 Context Orchestration Layer 放进同一个受治理 workflow。

Letta 的 Git memory 能力也更适合作为“正文版本 + 快读缓存”的参考，而不是完整照搬。开启 git memory 后，Letta 将 block 以 markdown + frontmatter 写入 git，git 是 source of truth，PostgreSQL 是读取缓存；push 或 API 写入后再同步回 PostgreSQL。普通 block history 是线性的 checkpoint / undo / redo：从旧 checkpoint 后继续写，会截断未来 checkpoint。这与本项目已确认的 rollback 口径一致。但 Letta 当前主路径仍主要围绕 agent block 文件历史，不等同于本项目需要的 story branch：Core State、Recall Memory、Archival Knowledge 引用、Runtime Workspace、writer packet 和 turn tree 的完整隔离。

Git 式版本管理在本项目中管理的是 Memory OS 的正文状态、分支可见性、失效 / 遮蔽关系和可回放引用，不直接管理检索索引。实际内容包括 Core State 当前事实、Core State 当前视图 / projection block views、Recall Memory 条目、Archival Knowledge 文档和已接受文本；索引是由这些内容派生出来的搜索加速结构，例如 chunk、embedding、关键词索引、HNSW 索引或检索缓存。索引不可读、不可手工审查、会随 embedding 模型或检索参数变化而大面积改变，因此不能成为 story truth。切分支或回退时，系统应先确定当前 branch / turn 下哪些 memory 条目可见，再让检索层按可见性过滤并按需 reindex；不应该为每个分支复制一整套向量库。

缓存未命中流程也按这个口径处理：writer 需要某信息时，先基于当前 writer packet 判断是否缺知识；若缺失，由 writer 通过受控 retrieval 工具查询 Recall Memory / Archival Knowledge。检索命中结果先作为卡片、摘要、refs 和可展开材料进入 Runtime Workspace，并可被 Context Orchestration Layer 纳入本轮 writer 上下文。写后只有当 block-owner worker 判断该信息已经成为当前剧情必须遵守的事实，并经过对应 permission level、proposal / apply 或用户审查后，才更新到 Core State 当前事实，随后影响 Core State 当前视图 / projection block views。换句话说，Recall / Archival 命中不是自动进入 Core State，必须经过 writer usage record 和 worker 整理治理链路。

Story Evolution 在 active story 之后发生，因此默认归属当前分支，不自动污染其他分支。prestory activation seed 才是 story-global base；active runtime writes 和 post-activation story evolution writes 默认都是 branch-scoped。若用户希望把某个 evolution 改动提升为整个 story 的全局底座，必须显式执行 promote-to-global / apply-to-all-branches 类操作，并检查其他分支是否兼容、是否需要 review。

Story Evolution 的内容本体建议只保留一份，再挂 visibility scope，而不是给每个分支都复制一份内容。可见性规则应支持：当前分支、选定分支集合、所有已有分支、story-global。这样用户可以选择该 evolution 内容对哪些分支可见，同时仍保持一份主记录、统一 provenance 和统一治理链。分支内看到什么由 branch / turn visibility 过滤决定，不由每条分支复制出的独立副本决定。选定分支集合和所有已有分支只作用于当时明确覆盖的分支，不自动继承给之后从这些分支 fork 出来的新分支；只有 story-global 会影响未来新建分支。Story Evolution 可见范围后续允许修改，但应作为一次受治理的 visibility change 记录，而不是无痕覆盖旧可见性，用于 trace、retrieval visibility refresh 和后续 purge。

Story Evolution 不应新增一套平行 worker 系统。它更像一个轻量级、显式触发的 story editing / evolution workspace：复用 Memory OS、Retrieval Broker、Memory Inspection、proposal/apply、Archival ingestion、以及已有 block-owner workers 的能力；区别在于目标不是“本轮生成正文”，而是“修改或补充故事运行底座”。它的主目标层是 `Archival Knowledge`，用于设定补充、设定修改、资料新增与相关 ingestion / reindex；不是 `Core State` 的主修改路径。第一阶段不新增独立 `StoryEvolutionWorker`；只有当后续 evolution 需求稳定到需要独立心智、独立权限和独立输入输出合同时，才考虑从现有 block worker / helper 中抽出。

Memory 可见 / 可改能力不是普通调试面板，而是 story runtime 的正式产品能力。整个 memory 层应使用项目规定的 DSL / canonical JSON block format；前端 UI 解析该格式，把 memory 排版成按 layer、block、entry 组织的列表或编辑表面。用户不是直接编辑底层表，而是在受治理的 memory surface 上查看、编辑、提交、回滚或触发 ingestion / reindex。

Memory OS 需要一条轻量的 memory change event 记录脊柱，但不应过重到完整 event sourcing。用户编辑 Core State 条目、隐藏 / 重算 Recall、导入 / reindex Archival、worker post-write maintenance、Story Evolution 导入资料，本质上都会改变后续 writer 可见上下文。它们的具体写入方式可以不同，但必须至少留下统一变更记录，用于 trace、rollback、branch visibility、worker dirty check 和 packet/window 重算。

轻量 event 应记录最小必要信息：

- actor：user / worker / evolution flow / maintenance。
- layer：Core State / Recall Memory / Archival Knowledge / Runtime Workspace。
- session / branch / turn lineage。
- affected domain / block / refs。
- operation kind：edit / apply / hide / expire / rebuild / import / reindex / materialize。
- downstream invalidation：是否影响 projection block views、writer packet、retrieval index、window metadata。

它不要求把每个底层表更新都重放成事件，也不要求第一阶段实现完整事件溯源。原则是：足够让系统知道“谁在什么时候改了哪块 memory，以及哪些消费者需要失效或重算”。

这条轻量 event 脊柱也用于处理 rp / trpg 的并发编辑窗口：writer 输出后，post-write worker 会立刻基于当时的 Core State 版本整理候选更新；与此同时，用户可能在 memory 面板中手动修改 Core State。用户显式编辑拥有最高优先级。worker 输出必须带 base refs / base revisions，apply 或递交 projection block view update 时必须检查目标 block 是否已经被用户更新。

最小冲突规则：

- worker 候选改同一条目，而用户已在更高 revision 上修改该条目：worker 候选失效，不允许覆盖用户编辑；可丢弃、提示或要求基于新版本重算。
- worker 候选改不同条目，但依赖了用户刚修改的条目：标记 dirty，按需要重算相关 worker、projection block views 或 writer packet。
- worker 候选改不同条目且无依赖冲突：可以继续进入 proposal / projection update / Recall materialization。
- longform 通常不走这个并发冲突路径，因为 longform 在用户 review / edit / discuss / accept 后才触发整理。

因此 memory change event 至少要能让系统判断：worker 是基于哪个版本看的、用户是否在同一时间窗内改过相关 block、哪些消费者需要失效或重算。它不是复杂协同编辑系统，但必须提供乐观并发保护，防止后台 worker 覆盖用户显式事实。

按 Memory OS 层看：

- Core State 层面的改动：用户可以在前端按 block / entry 做受治理 CRUD。若是运行时真相改动，应进入 proposal / apply 或显式 user edit apply；若只是给 writer 的即时修改建议，也可以先通过交流栏影响后续 rewrite / writing packet。
- Recall Memory：用于“过去已经发生”的历史材料，例如已确认正文、scene/chapter summary、transcript、continuity note、角色长期历史摘要。用户更多是回顾、检索、核对和必要时隐藏 / 失效 / 重算摘要 / 重建 transcript / 按分支过滤；它不是默认设定编辑区。Recall 是否向量化仍可讨论，但若进入 retrieval，就需要专门 materialization / reindex 流程。
- Archival Knowledge：保存长期资料、设定原文、规则、导入文档和 active 后新增资料。它通常需要 parse / chunk / embed / index；多数 story evolution 的 CRUD / import / reindex 主要落在这一层，尤其是新增世界观、角色资料、规则文档、参考设定时。
- Runtime Workspace：只承载当前 evolution 操作的临时材料，不成为 truth。

因此 Story Evolution 的第一阶段口径是：不新增额外 flow/worker 大体系，先复用已有 memory 可见/可改能力、proposal/apply、retrieval ingestion 和 block worker；但在产品语义上把它和普通 active writing turn 区分开，避免把底层设定修改伪装成一次普通续写。

active story runtime 的身份模型采用三层：

```text
StorySession = 故事运行容器
BranchHead = 当前故事线状态
Turn = 当前故事线上的一次推进
```

`StorySession` 负责产品层会话身份、mode、runtime profile、worker 配置、模型配置和 UI 入口。`BranchHead` 负责当前故事线的位置：active branch、active turn head、memory 版本、当前上下文窗口、当前可见 Recall / Archival materialization。`Turn` 是该 branch 上的一次推进，承载 user input、writer output、worker outputs、packet/window metadata 和 post-write 结果。运行时主入口仍是 `StorySession`，但每次 turn 必须绑定 active branch head；writer、worker、retrieval 和 post-write maintenance 不能只拿 `session_id`，必须知道当前 branch，否则分支隔离会失效。

### Longform review overlay and discussion turn

Longform 与 roleplay / trpg 的主要差异是 writer output 默认是 draft artifact，并允许用户对产出文本做留痕式修订和批注。该能力参考 Word 的修订/批注语义：用户不是直接覆盖正文，而是生成 review overlay，供后续 discussion / rewrite turn 使用。

第一阶段 longform 修订前端沿用 Word / SuperDoc 风格的三态：

- `viewing`：只读查看当前 draft，不直接修改。
- `editing`：用户直接修改当前 draft candidate，本次修改本身不默认转成给 LLM 的 rewrite 指令，更接近“用户自己改稿”。
- `suggesting`：用户修改以 tracked change / comment 的形式进入 review overlay，供后续 rewrite turn 消费，更接近“给模型看明确修订意图”。

这里的设计原则进一步冻结为：story runtime 借用 SuperDoc/Word 在文档修订、批注、tracked changes、selection 与 block/range 锚点上的成熟能力，把“用户修订内容传递给 writer”作为核心目标；SuperDoc 不是 runtime 真相 owner，而是修订交互 substrate。凡是 SuperDoc 的现成做法与当前 task 需求不冲突，都可以直接参考；一旦冲突，以当前 task 的需求讨论、PRD、spec 和开发规格书为准。

longform 的 rewrite 旧版本不删除，用户可以随时回看和比较。底层必须存在一个显式“确定版本”概念，用于说明当前哪一版 draft / rewrite 结果才是后续 `续写`、post-write 维护、next-turn packet 和可见输出的单一真相。对 longform 来说，存在 rewrite 候选版本时，用户必须显式指定该轮采用哪一版；不能在未明确选择的前提下自动把当前页面版本晋升为确定版本。换句话说，底层必须有 `selected / canonical draft revision`，产品层也必须提供显式采用动作。

需要进一步冻结 longform 的 adoption 语义：当前轮候选版本只有在用户点击 `续写 / accept_and_continue` 时，才会成为后续正文的 canonical truth。明确能确定为正文的只有两种情况：

1. 当前轮只有唯一一版候选，用户点击 `续写 / accept_and_continue`。
2. 当前轮存在多个候选，用户显式选择其中一版，再点击 `续写 / accept_and_continue`。

在点击 `续写 / accept_and_continue` 之前，当前“选中的正文版本”只是可变的暂定选择，不等于已经 adopted 的 canonical truth。用户可以解除选择、重新选择其他版本，或继续对候选版本执行 edit / review 操作。真正进入下一轮写作、post-write 治理和 next-turn packet 的，是**点击续写时**被选中的 draft 内容。

为了便于回看、比较、debug 和 rollback 追溯，系统至少需要保留两类轻量记录：

- `selection receipt`：记录用户当前暂定选择了哪一版，可逆、可清除。
- `adoption receipt`：记录在点击 `续写 / accept_and_continue` 时，最终哪一版被采用为 canonical continuation base。

这些记录不需要发展成重型版本树系统，只需回答：这一轮有哪些 rewrite 候选、当前暂定选中哪一版、最终在什么时候用哪一版进入继续写作。

Review overlay 属于 turn material，不是 active truth，不直接进入 `Core State.authoritative_state`。它应至少表达：

- 原文引用或范围。
- 用户建议的插入 / 删除 / 替换。
- 批注或重写意图。
- 与 draft artifact / revision / packet 的 provenance 关系。

review / comment 生命周期第一阶段也冻结为接近 Word / SuperDoc 语义：rewrite 生成新 candidate 后，原 comment 默认继续保留，不自动删除，也不自动 resolve。是否“这条批注已经被满足”由用户决定；用户可显式 `resolve`、保留继续修改，或删除。resolved comment 默认从主修订工作视图收起，但仍保留留痕、锚点和 provenance，便于回看、导出、debug 和 rollback 审计。

Longform runtime 需要同时支持：

- `writing turn`：产出、续写或重写正文 artifact。
- `discussion turn`：用户与 writer 即时头脑风暴，讨论不满意点，提出修改方向，或调整当前剧情大纲 / chapter intent 的候选表达。
- `review turn`：用户以 review overlay 方式标注 draft，writer 在后续 rewrite 时可见。

这些 turn 不需要拆成独立大 agent。它们应共用 `WritingWorker`，由 `command_kind` / `output_kind` / packet policy / review overlay 决定 writer 行为。

这里还需要冻结一个结构约束：`review overlay`、`brainstorm change summary`、brainstorm apply receipt、rewrite 候选版本与确定版本选择结果、retrieval cards / usage、worker trace 等，都不应各自长成新的平行主记录系统。它们统一作为当前 `Turn` 的子材料或关联记录存在。也就是说，`Turn` 继续是唯一主锚点；其他这些对象只是在语义上服务于该轮的讨论、修订、写作、治理和追溯，而不是再各自争夺一套产品级主时间线。

需要明确一点：longform 的 `rewrite` 版本管理语义更接近 chat 侧的“重试 / 重新生成”，只是进入 rewrite 前可能经过 review overlay 或 brainstorm 触发的 memory 调整。也就是说，多版 rewrite 本质上是同一轮或同一写作目标下的候选输出集合；区别在于 longform 要求用户显式选定采用版本，而不是默认把最新版本直接视为确定版本。roleplay / TRPG 不采用“同一 Turn 下保留多个可切换候选”的设计：对用户来说，单个 `Turn` 只有当前一版正式可见结果；若用户不满意，应通过显式分支从历史 turn 改写未来，而不是在同一 turn 内保留候选树。

不过 RP/TRPG 侧真正更重要的，是**带 memory / branch / rollback 语义的可回溯消息树**。普通 chat 的消息树大多只管理消息候选和分叉显示；RP/TRPG 的消息树必须更重，能够与 `Turn`、`BranchHead`、`Core State`、`Runtime Workspace`、Recall / Archival materialization 和 post-write 状态对齐。换句话说，RP 功能侧需要的是更强的 story-runtime branch/rollback tree，而不是 chat 风格候选树。

Longform 的 `WritingWorker` 在同一 worker 合同下应支持两种操作模式，而不是拆成两个 worker：`brainstorm/discussion` 和 `writing/rewrite`。前者负责头脑风暴、章节大纲协商、设定讨论、伏笔 / 章节意图修订；后者负责按确认后的大纲和 draft 产出正文或重写正文。这里不是要求用户显式切换 writer 模式：讨论区输入天然触发 `brainstorm/discussion`；产出区的明确动作触发 `writing/rewrite`。当前冻结的产品动作口径是：`重写`、`接受并继续`、`完成本章`。其中重写可携带用户修订内容；接受并继续表示认可当前段并进入下一段写作；完成本章表示结束本章并进入下一章准备。UI 入口不同，但底层仍是同一个 worker、同一基础上下文与治理合同。

头脑风暴的有效结果，目标应是修改对应的 `Core State` block，而不是沉淀成一层游离的 discussion 记忆。也就是说，discussion / brainstorm 通常是围绕大纲、设定、章节目标、伏笔等内容形成 change intent；但 brainstorm writer 不直接提出 block proposal，也不直接改 memory。它只负责把讨论结果总结成条目，产出一份面向调度器的 change summary；不负责 block 路由，也不负责 worker 路由。该 summary 在提交前要给用户审阅和编辑；用户确认后，才触发一次专门的调度，由调度器根据 summary 派发对应 worker 去修改 block。若只是对当前段落产出不满意，则优先走 `review overlay / 修订 -> rewrite`，而不是把段落级不满混入 core block 修改流。章节内如果 brainstorm transcript 过长，可以生成一份仅供 brainstorm 自身继续对话和回顾使用的压缩 summary；它不是真相层，也不直接进入 writer 上下文。进入下一章节后，上一章的 brainstorm 原始上下文从活跃讨论上下文中切掉，只保留必要留痕、apply 记录与可选压缩摘要供回顾。

discussion summary 一旦被用户确认，这次“应用到 block”的调度必须在下一次写作前完成。longform 允许“时间换质量”：既然用户已经确认要改大纲 / 设定，下一次正文就应基于更新后的 core。反过来，discussion 生成但未确认的 summary / proposal，如果用户已经进入下一段、下一章或继续写作，则按当前第一版口径一刀切自动 stale，避免遗留过期候选。

discussion summary 还应支持部分确认，而不是只能整份通过。summary 内部应拆成可单独确认 / 编辑 / 拒绝的修改意图条目，调度器只处理用户最终确认的那一部分。这样用户可以保留有用修改，同时丢弃不想要的讨论结果。条目本身不负责 block 路由；具体放入哪些 block、交给哪些 worker，由调度器决定。

brainstorm 产出的讨论结果条目第一版应带少量固定类型，但不要细到 block 路由层。建议只保留少量类型标签，例如设定修改、大纲修改、章节目标修改、伏笔修改、开放想法。类型的作用只是帮助调度器和后续 worker 理解讨论结果的性质，不负责决定具体 block 归属。

brainstorm 产出的条目第一版应使用稳定编号，例如本轮短编号或顺序号，不要用随机字符串。条目描述应尽量写成确定性、清晰、可编辑的表述，便于用户审阅和后续调度，而不是写成模糊口语。

在用户审阅阶段，brainstorm 条目第一版只支持两种操作：编辑、拒绝。暂不支持用户手动新增条目。用户点击 `apply` 后，所有未被拒绝的条目整体交付调度层；调度器再决定如何派发对应 worker 去修改 core。

跨章节时，章间承接材料必须留接口位。第一版冻结为“单一 provider 接口 + 默认实现返回 accepted outline / chapter goal”，不额外引入 compact 模块；若后续 eval 发现连贯性不足，再新增 compact / chapter-bridge 实现替换 provider，而不是改写整条 longform 主流程。

brainstorm summary 的最小数据结构应在第一版冻结为最小集合，不额外膨胀。建议至少包含：稳定编号、轻量类型、条目文本、拒绝状态、用户编辑后的最终文本。UI 上编辑直接在条目上原地修改；被拒绝的条目以划掉态显示。

同一套 review / revision overlay 语义也应复用于 setup 阶段用户手动修改 draft 的场景。也就是说，setup 里的 draft 手改、longform runtime 里的 review overlay、discussion turn 里的头脑风暴，不应是三套互不兼容的编辑系统，只是触发位置、UI 入口和后续路由不同。

当前 MVP 的 longform 交流栏手测效果较差，需要作为实现风险记录，但本阶段不解决。已观察到的问题包括：

- 交流栏没有有效承担“交流、修改、优化当前 draft / 大纲”的职责，更像普通弱上下文聊天。
- 可能出现上下文截断后，用户要求续写时，模型沿着被截断的内容继续输出的情况。
- 这提示后续实现需要区分“截断显示 / 截断传入模型 / 续写锚点 / draft revision context”，不能把被截断的上下文片段直接当作续写起点。

这些属于后续实现和 packet/window 细节问题；当前只记录风险，不展开解决方案。

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

当前已有 longform MVP 主链。它用于说明当前代码形态和可观察行为，不是新 runtime 必须继承的后端架构：

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
- `StoryGraphRunner` 已使用 LangGraph checkpoint shell，这与未来 turn-level rollback / branch 目标方向一致，但当前还没有把 memory/text/packet/window 统一成完整可回溯边界。
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
- 当前 longform 的旧实现只有基础 draft artifact 和 discussion entry；但新规格已经冻结：review overlay / tracked change / comment 作为 turn sidecar 进入 rewrite packet，并与 discussion / rewrite / draft adoption 走统一治理链。后续实现重点不再是“定义语义”，而是按已冻结合同替换旧 MVP 数据流。
- 当前 roleplay / trpg 还没有利用 writer 输出后的用户阅读和输入间隙进行后台整理、block refresh 和 next-turn view prebuild 的策略。

## Requirements

1. Worker 层必须被定义为 memory 层和 runtime 上下文的管理者，而不是单纯的 prompt 节点。
2. Worker catalog 必须优先按 Core Store / memory block ownership 设计，技能型 worker 只能作为补充，不能成为第一拆分原则。
3. 第一阶段以 longform writing turn 可运行为优先验收目标，但不要求保持旧 longform MVP 的内部链路、API 形状或用户可见行为完全不变；runtime 合同不能继续写死为 longform-only。
4. Orchestrator 的职责应从“生成 writer 指令”升级为“提出 worker 调度意图、上下文需求、同步/异步和优先级建议”。确定性 Scheduler 负责校验、裁决和执行 workflow。
5. Specialist worker 的输入应被显式建模为 context packet 或等价合同，表达 message refs、memory refs、summary refs、retrieval queries、workspace refs、constraints、token budget、forbidden context 等内容。
6. Context Orchestration Layer 必须负责 worker context packet 的组装，不允许默认把 raw memory / raw retrieval / raw authoritative JSON 全量派发给 worker 或 writer。
7. Worker 输出应保持结构化，至少覆盖 writer hints、validation findings、state/proposal hints、summary updates、recall summary、可选 structured metadata。
8. 现有 `LongformSpecialistService` 可以作为第一阶段 `LongformMemoryWorker` 的参考或 adapter 来源，但不强制继续可用；如果包旧 service 会阻碍新 worker 合同，应按 `WorkerDescriptor / WorkerExecutor / WorkerContextPacket / WorkerResult` 重写。
9. `WritingPacketBuilder` 必须继续保持确定性边界，只消费 worker 消化后的稳定结果，不直接接收 raw retrieval hits、raw authoritative JSON、工具 trace、worker 中间态、Runtime Workspace 日志或 usage metadata。
10. Worker 配置 stage 必须支持“启用 worker + per-domain/block permission level”的底层粒度，并编译成 runtime permission profile。
11. Worker / profile 配置必须走 validate / compile / versioned snapshot；turn 开始时 pin snapshot version，runtime 热更新只影响下一轮。
12. Story runtime 必须采用统一 `Runtime Workspace` turn lifecycle，支持 `user input + writer output + sidecars + packet refs` 作为 post-write turn processing 的输入。
13. Roleplay / trpg 的主上下文整理点在 writer 输出后，post-write processing 不只做 maintenance，也要在 worker 整体分析完成后优先递交下一轮可用的 Core State 当前视图 / projection block views；但这必须是同一个 post-write workflow 内部的递交顺序，不允许拆成 writer 双输出或流程外独立轻量链路。
14. Longform 必须为 review overlay / tracked change / comment 留合同位置，使用户能留痕式修改 draft，writer 在 rewrite / discussion turn 中可见。Longform 的 `WritingWorker` 必须支持 `brainstorm/discussion` 与 `writing/rewrite` 两种操作模式，而不是拆成两个 worker；讨论区、大纲协商、设定修订和正文写作共享同一套上下文与治理合同。
15. TRPG 必须为 rule card / state card 留合同位置，使规则判定作为结构化 sidecar 进入 writer packet 和 post-write processing。
16. Mode 差异应通过 `ModeProfile` 影响 setup profile、memory profile、runtime profile、worker 心智、工具范围、retrieval 策略、packet 策略、writer 姿态和 proposal/validation 规则；但第一阶段只需要为这些入口留出合同，不要求完整实现 roleplay/trpg。Longform 与 setup 阶段的 draft 手改应复用同一套 review / revision overlay 语义，只是 UI 入口和触发位置不同。
17. eval 模块由其他 session 负责。本任务不实现 eval runner、case、grader，只保证 story runtime 产物便于后续观测和接入。
18. Runtime 不新增独立“能力层”作为主抽象。小能力优先放入 macro worker、deterministic helper、Memory OS / retrieval tool 或 Context Orchestration Layer policy；只有跨 worker 复用且不承担 block ownership 的稳定能力才允许抽成共享 helper。
19. ModeProfile 的 runtime 区分度应主要通过 worker catalog / worker policy / packet policy / writer policy 表达，但不能退化成只改 prompt，也不能把 longform / roleplay / trpg 做成三套互不兼容 runtime。
20. Writer packet 必须保持窄而干净：Core State 当前视图 / projection block views、近 X 轮 user input / writer output 原文窗口、mode 特殊内容、可能的检索卡片 / 展开内容，以及 system prompt / writer contract。当前视图不能替代近几轮原文；原文窗口用于保留语气、细节、节奏、用户即时意图和刚发生但不宜沉淀的内容。Runtime Workspace 日志、工具调用过程、trace、usage metadata 和 worker 中间态默认不进入 writer 上下文。
21. Token 消费量应优先来自上游 LLM 返回的 usage metadata，而不是本地估算。Context Orchestration Layer 可在组包前做预算和预估，但实际消费量必须在 writer / worker 调用完成后回写到 turn / packet / window metadata，作为下一轮预算与 UI 展示依据。
22. Roleplay / trpg 的 acceptance signal 当前阶段以用户发送下一条消息为准。writer output 可先作为下一轮可见的暂定故事材料，但进入稳定维护链前必须满足用户继续输入、显式接受或 mode policy 自动接受。
23. Story runtime 必须为 turn-level 回退保留架构位置，并为未来分支能力保留扩展余地。回退应恢复文本储存层、Core State 当前事实、Core State 当前视图 / projection block views、Recall / Archival materialization 和 packet/window metadata 的一致状态；从 turn 15 回退到 turn 12 后，turn 13-15 对当前主线默认失效 / 不可见，不能在同一主线里再前进回去。保留 turn 13-15 作为另一条未来属于分支能力，不属于回退能力。
24. 分支能力必须与回退能力区分。分支表示从同一 turn 派生多条可切换、可删除、memory/context 互相隔离的故事线。后续实现应优先采用 copy-on-write / branch visibility 语义，避免创建分支时整套 memory 加倍复制；但 branch-specific 的新增文本、Core State revision、projection block views、Recall / Archival materialization、packet/window metadata 必须归属于对应分支。
25. Story Evolution 默认写入当前分支。只有用户显式选择提升为全局底座或应用到所有分支时，才允许影响 story-global base 或其他分支；该提升必须检查分支兼容性并遵守 review / maintenance policy。
26. Active runtime 身份模型为 `StorySession / BranchHead / Turn` 三层。runtime API 可以以 session 为入口，但每轮执行、memory read/write、retrieval filter、rollback、branch switch/delete 都必须绑定 branch head 和 turn lineage。
27. Worker catalog 按 block/domain ownership 划分，不能按 pre-write / post-write 流程阶段拆成两套 worker。phase 决定同一 worker 本轮是做写前上下文准备，还是写后维护沉淀。
28. Story Evolution 第一阶段不新增一套平行 worker 系统。它应复用 Memory OS、Retrieval Broker、Memory Inspection、proposal/apply、Archival ingestion 和已有 block-owner workers；多数 CRUD / import / reindex 主要落在 Archival Knowledge，Core State 真相改动仍走 proposal/apply 或显式用户编辑，Recall Memory 主要作为历史材料层被重算、失效或过滤，而不是默认设定编辑区。
29. Memory 可见 / 可改是正式产品能力。所有 memory 层对前端暴露时应使用项目规定的 DSL / canonical JSON block format，由 UI 解析成按 layer、block、entry 组织的列表或编辑表面；Core State 支持受治理 CRUD，Recall 以回顾 / 检索 / 失效 / 重算为主，Archival 和进入 retrieval 的 Recall materialization 需要专门 ingestion / reindex 流程。
30. Memory 可编辑能力需要轻量 memory change event 记录脊柱，用于 trace、rollback、branch visibility、worker dirty check 和 packet/window 重算；但不做过重 event sourcing，不要求所有底层表变更都只能通过事件重放。
31. 用户显式编辑 Core State 的优先级高于后台 worker 候选更新。rp / trpg post-write worker 必须基于 base revision 产出候选；如果 apply 时目标 block 已被用户改到更高 revision，worker 候选失效或重算，不能覆盖用户编辑。`Core State` 的主修改路径是：用户手动修改、调度器自动维护、brainstorm 流程修改。用户在自己确定的情况下手动修改 `Core State`，风险由用户自行承担；系统提供 rewrite、rollback、revision 冲突检查和 trace 作为兜底，而不额外把这类显式用户编辑变成过重的阻塞流程。
32. Core State 当前视图 / projection block views 的选择由轻量本轮简报 + block-owner worker 判断共同完成。调度器或专用轻量节点只生成带 source refs 的本轮简报；worker 决定自己 block 的视图事实；Context Orchestration Layer 负责最终 writer packet 全局取舍。
33. 调度频率必须可配置，不要求每轮都做完整调度。ModeProfile / runtime config 可配置每 N 轮完整调度，也可由 user edit、rule card、scene switch、状态变化、manual refresh、window overflow、dirty block 等事件触发。
34. Letta 的源码参考应按“agent / worker 通过工具管理 memory”理解，而不是按“存储层自动搬运”理解。本项目与 Letta 的共同点是工具化 memory 管理；差异是 RP runtime 需要额外治理剧情真相、用户编辑、worker 权限、mode profile、回退、分支和 writer workflow。
35. Git 式版本管理只管理 Memory OS 的正文状态、分支可见性、失效 / 遮蔽关系和可回放引用；检索索引、embedding、HNSW index、top hits 和检索缓存都是派生产物，不作为 story truth，也不直接进入 Git 式版本对象。
35a. 分支切换不携带原分支 fork 后的 Runtime Workspace、worker candidate、pending 标记或未完成调度结果。它们继续归属于原 `BranchHead`；新分支只能看到 fork 前共享的 settled memory 和本分支自己的 workspace / pending / candidate。
35b. 分支删除第一版可先做 deleted / hidden 标记，但最终必须支持物理删除分支专属材料。删除范围只限该分支 fork 后独占的 workspace、candidate、pending、Core / Projection / Recall materialization、packet/window metadata 和 retrieval 派生记录，不能删除共享历史或全局 Archival。
36. Recall / Archival 检索命中默认只是引用材料。只有当 block-owner worker 判断它应成为当前剧情必须遵守的事实，并经过 permission / proposal / apply / user review 链路后，才允许写入 Core State 当前事实并刷新当前视图。
37. writer 检索知识的主路径是 writer 自行判断当前上下文是否缺信息，并通过受控 retrieval 工具发起查询；不新增一个主路径的写前缺口预检层，也不让 Context Orchestration Layer 替 writer 决定是否检索。
38. writer-side retrieval 的召回材料先进入 Runtime Workspace，表现为本轮检索卡片、短编号映射、摘要、refs、展开内容、missed query、attempt trace 和 usage record；Recall Memory 不作为本轮 raw hit 暂存区，Context Orchestration Layer 不承担存储语义。
39. writer 可以在受控 attempt limit 内重试检索，也可以请求展开已返回卡片；但每轮发生 retrieval 后，最终输出前必须有结构化 retrieval usage record。post-write scheduler 只处理 backend-resolved 的 `used_card_material_ids`、必要的 `used_expanded_chunk_material_ids` 和 `knowledge_gaps`。
40. 检索卡片 / 摘要 / 展开 chunk 都是证据，不是事实。写后必须由 block-owner worker 追溯 provenance、抽取事实候选，并通过 permission / proposal / apply / user review 链路后才进入 Core State 当前事实和当前视图。
41. Recall Memory 的职责冻结为历史回忆层，保存过去已经发生的材料，例如已接受正文、历史摘要、transcript、scene / chapter summary。它不承担当前事实缓存，也不是当前视图；当前事实属于 Core State 当前事实，当前视图属于 Core State 当前视图，本轮临时检索和工具结果属于 Runtime Workspace。
42. ModeProfile 是区分 longform / roleplay / trpg 等功能的重要关键，但它不应被理解成一个大 prompt。它主要决定 setup 阶段流程、Core Memory / Memory OS 默认展示和激活哪些 block、story runtime 的调度器 + worker 层怎么走。
43. Writer 主要负责写作。writer 的文风、写作风格等在 setup 阶段讨论；writer 输入由 Context Orchestration Layer 编排，来源包括近几轮原文窗口、Core State 当前视图、特殊 worker 内容等。检索等能力在 worker 配置 stage 和 runtime 配置合同中表达，不能把 writer 设计成自由工具 agent。
44. ModeProfile 第一版可以不完整实现 longform / roleplay / trpg 全部行为，但必须为这些 mode 的差异预留合同和扩展位，不能全量按照 longform 行为设计编码。
45. Memory OS 各层都应对用户公开，但编辑方式不同。Core State 可直接编辑，用户显式编辑优先级最高；Recall Memory 主要保存已有事实、历史摘要、transcript 和已接受正文，基本用于回顾、失效、重算，不作为常规直接编辑层；Archival Knowledge 可修改，但必须通过 Story Evolution / ingestion / reindex 流程，因为它会进入 retrieval 层并影响 provenance、chunk、embedding 和索引。
46. TRPG 的 `rule_state` / `mechanics_state` 可以作为独立 domain，不归入 `world_rule` 或 `inventory`。`world_rule` 更偏规则文本、世界约束和规则知识；`inventory` 更偏物品、资源和持有关系；`rule_state` 更偏当前机械状态、判定结果、状态效果、战斗 / 回合 / 冷却 / HP / 任务状态等当前事实。
47. Worker ownership 按 `domain` 划分，不按 `block` 划分。`domain` 是剧情事实的语义责任边界；`block` 是某个 domain 在某一层 Memory OS 里的具体存储、展示或编辑容器。同一个 domain 可以在 Core State 当前事实、Core State 当前视图、Recall Memory、Archival Knowledge 和 Runtime Workspace 中有不同 block，但默认仍由同一个 domain owner worker 理解和维护；具体能读、能提 proposal、能刷新视图或能修改什么，由 layer / block 权限控制。
48. 第一阶段最小 trace 合同包括：`StorySession / BranchHead / Turn` 身份、runtime profile snapshot version、writer packet summary、worker plan + worker execution result、retrieval usage record、proposal / apply 结果、Runtime Workspace 材料生命周期变更。eval session 可按需要在此基础上修改或补充；本任务不实现 eval runner / case / grader，只保证 story runtime 产物可观测和可接入。另需预留开发期 debug 页面，用于查看这些日志和中间材料，方便人工审核；若后续 eval 成熟，可以减少人工依赖。

## Acceptance Criteria

> 当前状态说明：
> - `[x]` 表示现有 `prd/spec` 已明确覆盖该合同或边界。
> - `[ ]` 表示这项需要等后续实现或测试完成后才能勾选。

- [x] `prd.md` 明确记录 worker 层定位、当前实现地图、差距和第一阶段边界。
- [ ] 第一阶段实现后，新 runtime 的 longform writing turn 最小闭环可运行。
- [x] Orchestrator 输出能表达至少一个 selected worker execution，而不只是 writer 指令。
- [x] Memory worker 分析能通过显式 worker/context 合同接收本轮上下文；旧 single specialist 可作为参考或 adapter，但不作为硬约束。
- [x] PRD / spec 能表达 Core Store block ownership 到 worker catalog 的映射原则。
- [x] PRD / spec 能表达 `ModeProfile` 作为 setup-before-runtime 产品级 profile 的三层结构。
- [x] PRD / spec 能表达 worker 配置 stage 的 per-worker + per-domain/block permission level 粒度。
- [x] PRD / spec 能表达 runtime profile snapshot 与 turn-start pinning 策略。
- [x] PRD / spec 能表达统一 `Runtime Workspace` turn lifecycle，并覆盖 longform / roleplay / trpg 的材料差异。
- [x] PRD / spec 能表达 longform review overlay 和 TRPG rule card / state card 作为 turn material sidecars 的位置。
- [x] PRD / spec 能表达 post-write processing 负责准备下一轮 writer-facing view。
- [x] PRD / spec 能表达 Context Orchestration Layer 的职责和“不可全量派发上下文”的约束。
- [x] PRD / spec 能表达不新增独立能力层的抽象边界，以及小能力应优先归属 macro worker / helper / context orchestration policy。
- [x] PRD / spec 能表达 mode 差异主要通过 `ModeProfile -> runtime_profile -> worker policy / packet policy / writer policy` 落地，同时仍共享同一套 story runtime 骨架。
- [x] PRD / spec 能表达 writer packet 不能只依赖 Core State 当前视图，还必须保留近几轮 user input / writer output 原文窗口，并且默认剪裁 Runtime Workspace 日志、工具过程、trace、usage metadata 和 worker 中间态。
- [x] PRD / spec 能表达 token 实际消费量来自上游 LLM usage metadata，本地预算/预估只用于组包前裁剪辅助。
- [x] PRD / spec 能表达 roleplay / trpg 的用户下一条消息作为 acceptance signal，并区分暂定可见材料与稳定维护材料。
- [x] PRD / spec 能清楚区分 rollback 与 branch：rollback 是当前主线单向回到旧 turn，并让目标 turn 之后内容失效；branch 是保留多条未来。memory/text/packet/window 状态必须在同一回溯边界下恢复。
- [x] PRD / spec 能表达 branch 之间 memory/context 隔离、可切换、可删除，以及 copy-on-write / branch visibility 优先于整套 memory 复制的架构方向。
- [x] PRD / spec 能表达 Story Evolution 默认 branch-scoped，只有显式 promote-to-global / apply-to-all-branches 才影响全局底座或其他分支。
- [x] PRD / spec 能表达 `StorySession / BranchHead / Turn` 三层身份模型，并要求 runtime 执行和 memory/retrieval 读取绑定 active branch head。
- [x] PRD / spec 能表达 worker 按 block/domain ownership 划分，同一 worker 通过 phase 区分 pre-write context 与 post-write maintenance。
- [x] PRD / spec 能表达 Story Evolution 复用现有 Memory OS / proposal / ingestion / block worker 能力，不先新增平行 worker 系统；Recall Memory 不是默认设定 CRUD 层。
- [x] PRD / spec 能表达 memory 可见 / 可改是正式产品能力，前端通过项目 DSL / canonical JSON block format 渲染 block / entry，Core / Recall / Archival 的可改方式不同。
- [x] PRD / spec 能表达轻量 memory change event 作为统一 trace / invalidation 脊柱，但避免过重 event sourcing。
- [x] PRD / spec 能表达用户显式 Core State 编辑优先于后台 worker 候选，worker 候选必须带 base revision 并在 apply / projection update 前做冲突检查。
- [x] PRD / spec 能表达轻量本轮简报 + block-owner worker 共同决定当前视图事实，Context Orchestration Layer 负责最终 writer packet 取舍。
- [x] PRD / spec 能表达完整调度频率可配置，不要求每轮调度，并支持事件触发调度。
- [x] PRD / spec 能表达 Letta 参考的真实边界：agent / worker 通过工具管理 memory，Git memory 可参考正文版本和缓存同步，但不能替代本项目的 story branch 隔离。
- [x] PRD / spec 能表达检索索引是由正文派生的搜索加速结构，不是 story truth；rollback / branch 管理正文状态和可见性，检索层按 active branch / turn 可见性过滤并按需 reindex。
- [x] PRD / spec 能表达 Recall / Archival 检索命中到 Core State 当前事实的换入条件：必须由 block-owner worker 整理，并经过权限、proposal/apply 或用户审查。
- [x] PRD / spec 能表达 writer-side bounded retrieval：writer 判断知识不足并通过受控工具检索；Context Orchestration Layer 不作为新增写前预检层。
- [x] PRD / spec 能表达 retrieval cards / short ids / expand tool / Runtime Workspace 映射合同，避免 writer 直接记忆随机 hit_id / chunk_id。
- [x] PRD / spec 能表达 retrieval usage hook：发生 retrieval 后，writer final output 前必须记录 used cards、expanded cards、unused cards 和 knowledge gaps。
- [x] PRD / spec 能表达检索 miss 的受控重试与 gap 记录策略，以及 retrieval-triggered turn 必须走 post-write 调度。
- [x] Builder 仍只消费 worker 消化后的结构化结果，不消费 raw retrieval hits。
- [ ] 新增或调整的 runtime contract 有单元测试或现有 story runtime 测试覆盖。
- [x] 不修改 eval 模块主流程。

## Technical Approach

第一阶段先把完整 spec coding 方案讨论完并落稳，再进入最小实现。实现时采用 `runtime-first rebuild with selective reuse`：先按新 runtime 合同建立最小 longform writing turn 闭环，再判断哪些旧 service 值得 adapter 复用。

```text
Runtime Identity
  -> RuntimeProfileSnapshot pin
  -> Context Orchestration Layer builds WritingPacket / WorkerContextPacket
  -> WritingWorker outputs visible text
  -> Runtime Workspace records turn materials
  -> Scheduler validates OrchestratorWorker structured plan
  -> registered MemoryWorker processes turn materials
  -> Projection/View refresh for next writer packet
```

实现时可以选择两种等价落地方式：

- 若旧 `OrchestratorPlan`、`LongformSpecialistService`、`WritingPacketBuilder` 等能低成本复用且不污染新合同，可以通过 adapter 接入。
- 若 adapter 复杂度高、语义扭曲或继续制造 hardcoded fixed chain，应直接按新模型重写。
- 如果现有 longform MVP 链路阻碍新的完整 story runtime 合同，也允许从新 runtime 骨架起一条替代实现，而不是被旧 MVP 绑定。spec coding 方案必须明确废弃策略、最小可验证路径和回滚方式。
- 第一阶段不以“保持当前 longform MVP 的用户可见行为完全不变”为硬约束。允许改变当前 MVP 行为，但必须服务于新的 story runtime 产品目标和核心合同，例如唯一 writer 输出、Memory OS 分层、worker 管理 memory、post-write workflow、可回退和可追溯；不能为了临时实现方便制造新的行为分叉。
- 分支 / 回退能力第一阶段只做合同预留和 LangGraph 能力边界验证，不做完整分支 UI、分支删除物理 purge、跨分支 Evolution 管理。正式实施前必须专项调研当前项目接法下 LangGraph 的 checkpoint、replay、fork、切回旧 checkpoint 后继续和外部存储同步边界；验证不了或框架不支持的能力第一阶段暂缓。
- 第一阶段实现顺序冻结为：先做 memory/runtime identity + worker/scheduler/context 合同；再建立 longform writing turn 最小闭环；随后按价值选择旧 service adapter 或重写；最后接 writer-side retrieval + Runtime Workspace usage record + post-write trigger。
- 第一版验收以 longform 可运行为主，但合同必须能表达 roleplay / trpg。ModeProfile、domain registry、worker catalog、packet policy 和 Runtime Workspace material type 不能写死成长文专用。模块化、解耦、高可维护是硬约束，worker 必须 registry / config driven、可装卸、可替换、可测试。

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

**Decision**：第一阶段允许重写 runtime，不以旧 longform MVP 链路、API、SSE、数据模型为硬约束；但也不为了重写而重写。先建立新 runtime 的最小 longform writing turn 闭环，并补清楚 deterministic scheduler、block-owner worker、Context Orchestration Layer、Runtime Workspace 和 worker context packet 的合同。旧 single specialist 只有在能低成本服务新合同的情况下才作为 adapter 接入。

**Consequences**：

- 好处：新 runtime 不被旧 MVP 固定链路、硬编码状态机和 longform-only 数据模型污染，同时仍能选择性复用有价值代码；后续 `CharacterMemoryWorker`、`SceneInteractionWorker`、`RuleStateWorker`、`MaintenanceWorker` 有清晰 block ownership 和 mode profile 位置。
- 代价：第一阶段仍然只有一个实际 specialist，domain accountability 不会一次到位；roleplay/trpg 的 worker 只做设计占位，不做行为实现。
- 风险：如果为了省事继续把调用链硬编码成 single specialist，后续会退化成伪调度。因此实现必须让 runtime 主链消费 worker registry、selected worker execution 和 context packet 语义；旧 service adapter 只能挂在 worker executor 背后。
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
- `research/story-runtime-architecture-question-queue.md`
- `research/story-runtime-memory-domain-preliminary-design.md`
- `research/story-runtime-spec-coding-plan.md`
- `research/story-runtime-dependency-readiness-audit.md`
- `research/story-runtime-module-architecture.md`
- `research/story-runtime-technical-research-and-pseudocode.md`

关键设计文档：

- `docs/research/rp-redesign/new-architecture-overview.md`
- `docs/research/rp-redesign/x08-memory-os-redesign-draft.md`
- `docs/research/rp-redesign/core-state-memory-detailed-design.md`
- `docs/research/rp-redesign/agent/development-spec/setup-agent-development-spec.md`
- `docs/research/rp-redesign/agent/development-spec/prestory-retrieval-and-story-evolution-spec.md`
- `docs/research/rp-redesign/agent/implementation-spec/retrieval-layer-development-spec-2026-04-21.md`
- `docs/research/nocturne_memory-main/README_EN.md`
- `docs/research/nocturne_memory-main/docs/TOOLS.md`
- `docs/research/letta-main/letta/orm/block.py`
- `docs/research/letta-main/letta/orm/block_history.py`
- `docs/research/letta-main/letta/services/block_manager.py`
- `docs/research/letta-main/letta/services/block_manager_git.py`
- `docs/research/letta-main/letta/services/tool_executor/core_tool_executor.py`
- `docs/research/letta-main/letta/services/memory_repo/git_operations.py`
- `research/branching-memory-framework-research.md`

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
