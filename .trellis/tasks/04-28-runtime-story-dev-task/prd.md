# runtime story dev task

## Goal

把 active story runtime 从当前 longform MVP 流水线，收敛为以 worker 为核心的运行时编排骨架。第一阶段不从零重写、不扩成完整多模式系统，而是在现有 `StoryGraphRunner -> LongformOrchestratorService -> LongformSpecialistService -> WritingPacketBuilder -> WritingWorker` 链路上补清楚 worker 合同、调度语义和 runtime context 边界。

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
- `Orchestrator Worker`：语义提案者。它根据本轮命令、用户输入、writer 产出或 mode-specific signals，提出本轮 worker 调度意图和上下文需求；它不直接执行 worker，也不拥有最终 workflow 主权。
- `Context Orchestration Layer`：专门的上下文编排层。它整合 writer / worker 已触发的检索结果、已有 memory refs、token budget 和 workspace refs，生成 `WorkerContextPacket`，避免全量上下文派发；它本身不是主路径上的“写前预检检索决策层”。
- `Specialist Workers`：memory block 和 runtime 上下文的领域管理者。它们读取和消化 state、projection、recall、archival、runtime workspace，并产出结构化结果。
- `WritingPacketBuilder`：确定性组包层，只消费稳定 slot 和 worker 消化后的 hints/constraints/digests，不直接消费 raw retrieval hits。
- `WritingWorker`：唯一生成用户可见正文或回应的 worker。
- `Post-write Turn Processing`：在 `WritingWorker` 输出后处理本轮整体材料，派发 block owner worker。worker 完成整体分析后，优先递交 writer 下一轮需要的 Core State 当前视图 / projection block views；随后继续完成 proposal、`Recall Memory` materialization 或 `Archival Knowledge` 相关维护。这里不是另起一条“视图优先”的独立流程，而是同一轮 worker 分析完成后的递交和写入顺序。

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

为减少 longform / roleplay / trpg 的流程分叉，story runtime 使用统一的 `Runtime Workspace` turn lifecycle。这里不是新增 memory 层，也不是替代 worker；它只是把每轮已有材料组织成 scheduler、worker、builder 都能消费的稳定形状。

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

这里的 `WritingWorker` 输出不是两条线路，也不是在现有流程外另起一个轻量流程。`WritingWorker` 只有一个用户可见产出；该产出与 user input、sidecars、packet refs 一起组成同一份 turn result material，进入同一个 post-write workflow。post-write workflow 内部可以有递交顺序：worker 整体分析和产出工作已经完成后，先递交 writer 下一轮最需要的 Core State 当前视图 / projection block views，再继续完成 proposal、`Recall Memory` materialization、`Archival Knowledge` 维护等更谨慎或更重的写入。第一阶段不设计“writer 同时产出两份结果”或“当前 runtime 外并行一条独立维护链”。

Core State 当前视图 / projection block views 也不能替代近几轮原文。Context Orchestration Layer 给 writer 组包时，至少应同时考虑：

- Core State 当前事实与当前视图 / projection block views：提供稳定、压缩、可跨轮消费的当前状态。
- 近几轮 user input / writer output 原文窗口：保留措辞、语气、细节、用户即时意图、角色互动节奏和刚刚发生但还不适合沉淀进视图的内容。
- 已有 Recall Memory / Archival Knowledge 检索卡片、refs 或展开内容：补充更远历史和外部设定。
- Runtime Workspace 中本轮 sidecars / tool outputs / worker hints：表达本轮临时材料和未决信号。

因此 writer packet 不能完全依赖当前视图；当前视图负责“当前事实和可见重点”，近几轮原文负责“现场连续性和细节保真”。Context Orchestration Layer 的职责是按 mode、turn、token budget 决定两者比例，而不是二选一。

Core State 当前视图的形成不是纯确定性策略，也不是让调度器每轮读取完整 writer packet 后二次判断。rp / trpg 的推荐流程是：writer 输出后，由调度器或专用轻量节点生成一份本轮简报，通常只概括本轮 user input + writer output + sidecars 的关键变化，并携带 source refs。该简报不是事实来源，只是任务入口和压缩索引；启用的 block-owner worker 基于简报和 source refs，判断自己负责的 block 中哪些事实应进入当前视图 / projection block views。最终 writer packet 具体包含哪些视图 slot、近几轮原文、Recall / Archival 结果，仍由 Context Orchestration Layer 根据 packet policy、token budget 和 window 配置组装。

调度频率应可配置。既然 writer 输入由“Core State 当前视图 / projection block views + 近几轮原文窗口”共同构成，就不一定每轮都需要完整调度和 worker 视图刷新。ModeProfile / runtime config 应允许配置每 N 轮做一次完整调度，或在出现 user edit、rule card、scene switch、明显状态变化、manual refresh、window overflow、dirty block 等事件时触发调度。未触发完整调度的 turn 可以继续使用上一版当前视图，并依靠近几轮原文窗口保留现场连续性。

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

retrieval 层负责 RAG 能力本身：query augment、search、filters、rerank、score、provenance、摘要 / 摘录 / refs 返回。query augment 是 retrieval 层的合理职责，例如把“打工”扩展为“工作、打工地点、雇主、同事、排班、最近工作冲突”等检索表达。retrieval 层不负责结合 writer 当前上下文做剧情理解型总结；这类判断属于 writer / worker / 上下文编排链路。

召回材料的临时存储位置是 Runtime Workspace，不是 Recall Memory，也不是 Context Orchestration Layer。Runtime Workspace 应保存本轮检索卡片、短编号映射、真实 query / hit / chunk / provenance refs、摘要、展开内容、missed query、attempt trace 和 usage record。Recall Memory 是历史材料层；Context Orchestration Layer 是编排能力；二者都不应承担“本轮 raw retrieval hit 暂存区”的语义。

writer 可见的检索结果应采用卡片和短编号，而不是底层随机 id。runtime 可以把底层 `hit_id` / `chunk_id` / `block_id` 映射成 `R1`、`R2`、`R3` 这类本轮短编号。writer 如果摘要不够，只能通过受控展开工具请求指定卡片全文或邻近 chunk。展开请求仍按 Runtime Workspace 的映射回到真实 retrieval ref，并返回稳定结构；writer 不需要记忆随机字符串。

若检索无命中或低置信，不应立刻失败。writer 可在受控 attempt limit 内调整 query 再检索。多次 miss 后，writer 必须记录 `knowledge_gap`，并按 mode / hard-constraint policy 选择保守写作、提示信息不足或停止生成。TRPG 规则、明确角色历史和世界设定硬约束不能靠编造补齐；普通 RP 对话可以更柔性，但必须留下 gap trace。

只要本轮发生 retrieval，runtime 必须强制一条 retrieval usage hook。writer 在最终输出前必须提交结构化 usage record，说明哪些卡片被使用、哪些被展开但未使用、哪些 query miss、是否带着 knowledge gap 继续写。这个 hook 只有“用到哪些条目 / gap 对输出有什么影响”需要 writer 判断；卡片映射、存储、展开、attempt limit、trace 和 post-write routing 都是固定代码逻辑。

usage record 的最小合同：

```json
{
  "used_cards": ["R1", "R3"],
  "expanded_cards": ["R3"],
  "unused_cards": ["R2"],
  "knowledge_gaps": [
    {
      "query": "Taki 打工地点",
      "status": "missed",
      "impact": "无法确定具体店名，只保守写为夜班打工"
    }
  ]
}
```

如果本轮发生 retrieval 但 usage record 缺失，runtime 不应直接接受 writer final output，应要求 writer 补交 usage record 或走一次受控 repair。post-write scheduler 只把 `used_cards`、必要的 `expanded_cards` 和 `knowledge_gaps` 交给对应 block-owner worker；未使用卡片只保留 turn trace，不沉淀进 Core State。

写后处理的核心规则：检索卡片和展开 chunk 是证据，不是事实。worker 应追溯原始 chunk / provenance，把真正需要长期遵守的内容整理为 Core State 当前事实候选，再按 permission level、proposal / apply 或用户审查写入。下一轮 writer packet 应裁剪或压缩 raw retrieval 内容，优先使用已经进入 Core State 当前事实 / 当前视图的信息；未沉淀的 raw hit 仅按 Runtime Workspace / turn trace 保留。

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

架构含义：版本回溯不能只保存 graph checkpoint，也不能只保存文本消息。story runtime 需要把 turn checkpoint、artifact / discussion 文本层、Core State revision、projection block views、Recall / Archival materialization 结果、packet/window metadata 放在同一个可回溯边界下。第一阶段可以先把回退合同和 trace 打通，不要求完整 branch UI，但不能把 memory 写入设计成无法让 turn 13-15 在回退后对当前主线失效的单向覆盖。

分支能力属于比回退更强的版本能力。分支不是“回退后还能前进回旧未来”，而是从某一 turn 开始保留多条互相隔离的故事线。分支可以随时切换或删除；两条分支的 memory 层、上下文窗口、Runtime Workspace、Recall materialization 和 writer-facing packet 必须互相隔离。后续进入分支能力时，应采用类似 Git / Dolt / lakeFS 的 copy-on-write 思路：创建分支不复制整套 memory，只创建新的分支头；分支之间共享 fork 之前的历史，fork 之后只为新增或修改的文本、Core State revision、projection block views、Recall / Archival materialization、packet/window metadata 写入分支专属记录。

LangGraph 可以提供 checkpoint / time travel / fork 的 workflow 外壳，但不能自动让外部 memory store、retrieval index 或文本 artifact 具备分支隔离。RP runtime 必须在应用层把 branch / turn 可见性贯穿到 Core State、Recall Memory、Archival Knowledge、Runtime Workspace、retrieval metadata filter、artifact / discussion entry 和 packet/window metadata。第一阶段不实现完整分支 UI，但数据合同不能堵死后续分支隔离。

Letta 源码调研确认：Letta 和本项目一样，核心记忆操作并不是“存储层自动搬运”，而是由 agent 通过工具管理 memory。Letta 的 core memory blocks 常驻上下文；archival memory 通过工具搜索 / 写入；conversation history 通过 conversation search 查询；当前 context window 超限时由 summarizer / eviction 裁剪。block 变化后会触发 system prompt / context rebuild。对 RP runtime 的启发是：worker 也应该通过统一 Memory OS / Retrieval Broker 工具读取、检索和提交候选更新；差异在于 RP runtime 还必须把剧情真相、用户编辑、worker 权限、mode profile、回退、分支和 Context Orchestration Layer 放进同一个受治理 workflow。

Letta 的 Git memory 能力也更适合作为“正文版本 + 快读缓存”的参考，而不是完整照搬。开启 git memory 后，Letta 将 block 以 markdown + frontmatter 写入 git，git 是 source of truth，PostgreSQL 是读取缓存；push 或 API 写入后再同步回 PostgreSQL。普通 block history 是线性的 checkpoint / undo / redo：从旧 checkpoint 后继续写，会截断未来 checkpoint。这与本项目已确认的 rollback 口径一致。但 Letta 当前主路径仍主要围绕 agent block 文件历史，不等同于本项目需要的 story branch：Core State、Recall Memory、Archival Knowledge 引用、Runtime Workspace、writer packet 和 turn tree 的完整隔离。

Git 式版本管理在本项目中管理的是 Memory OS 的正文状态、分支可见性、失效 / 遮蔽关系和可回放引用，不直接管理检索索引。实际内容包括 Core State 当前事实、Core State 当前视图 / projection block views、Recall Memory 条目、Archival Knowledge 文档和已接受文本；索引是由这些内容派生出来的搜索加速结构，例如 chunk、embedding、关键词索引、HNSW 索引或检索缓存。索引不可读、不可手工审查、会随 embedding 模型或检索参数变化而大面积改变，因此不能成为 story truth。切分支或回退时，系统应先确定当前 branch / turn 下哪些 memory 条目可见，再让检索层按可见性过滤并按需 reindex；不应该为每个分支复制一整套向量库。

缓存未命中流程也按这个口径处理：writer 需要某信息时，先基于当前 writer packet 判断是否缺知识；若缺失，由 writer 通过受控 retrieval 工具查询 Recall Memory / Archival Knowledge。检索命中结果先作为卡片、摘要、refs 和可展开材料进入 Runtime Workspace，并可被 Context Orchestration Layer 纳入本轮 writer 上下文。写后只有当 block-owner worker 判断该信息已经成为当前剧情必须遵守的事实，并经过对应 permission level、proposal / apply 或用户审查后，才更新到 Core State 当前事实，随后影响 Core State 当前视图 / projection block views。换句话说，Recall / Archival 命中不是自动进入 Core State，必须经过 writer usage record 和 worker 整理治理链路。

Story Evolution 在 active story 之后发生，因此默认归属当前分支，不自动污染其他分支。prestory activation seed 才是 story-global base；active runtime writes 和 post-activation story evolution writes 默认都是 branch-scoped。若用户希望把某个 evolution 改动提升为整个 story 的全局底座，必须显式执行 promote-to-global / apply-to-all-branches 类操作，并检查其他分支是否兼容、是否需要 review。

Story Evolution 不应新增一套平行 worker 系统。它更像一个轻量级、显式触发的 story editing / evolution workspace：复用 Memory OS、Retrieval Broker、Memory Inspection、proposal/apply、Archival ingestion、以及已有 block-owner workers 的能力；区别在于目标不是“本轮生成正文”，而是“修改或补充故事运行底座”。第一阶段不新增独立 `StoryEvolutionWorker`；只有当后续 evolution 需求稳定到需要独立心智、独立权限和独立输入输出合同时，才考虑从现有 block worker / helper 中抽出。

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
13. Roleplay / trpg 的主上下文整理点在 writer 输出后，post-write processing 不只做 maintenance，也要在 worker 整体分析完成后优先递交下一轮可用的 Core State 当前视图 / projection block views；但这必须是同一个 post-write workflow 内部的递交顺序，不允许拆成 writer 双输出或流程外独立轻量链路。
14. Longform 必须为 review overlay / tracked change / comment 留合同位置，使用户能留痕式修改 draft，writer 在 rewrite / discussion turn 中可见。
15. TRPG 必须为 rule card / state card 留合同位置，使规则判定作为结构化 sidecar 进入 writer packet 和 post-write processing。
16. Mode 差异应通过 `ModeProfile` 影响 setup profile、memory profile、runtime profile、worker 心智、工具范围、retrieval 策略、packet 策略、writer 姿态和 proposal/validation 规则；但第一阶段只需要为这些入口留出合同，不要求完整实现 roleplay/trpg。
17. eval 模块由其他 session 负责。本任务不实现 eval runner、case、grader，只保证 story runtime 产物便于后续观测和接入。
18. Runtime 不新增独立“能力层”作为主抽象。小能力优先放入 macro worker、deterministic helper、Memory OS / retrieval tool 或 Context Orchestration Layer policy；只有跨 worker 复用且不承担 block ownership 的稳定能力才允许抽成共享 helper。
19. ModeProfile 的 runtime 区分度应主要通过 worker catalog / worker policy / packet policy / writer policy 表达，但不能退化成只改 prompt，也不能把 longform / roleplay / trpg 做成三套互不兼容 runtime。
20. Writer packet 必须同时支持 Core State 当前事实 / 当前视图与近几轮 user input / writer output 原文窗口。当前视图不能替代近几轮原文；原文窗口用于保留语气、细节、节奏、用户即时意图和刚发生但不宜沉淀的内容。
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
31. 用户显式编辑 Core State 的优先级高于后台 worker 候选更新。rp / trpg post-write worker 必须基于 base revision 产出候选；如果 apply 时目标 block 已被用户改到更高 revision，worker 候选失效或重算，不能覆盖用户编辑。
32. Core State 当前视图 / projection block views 的选择由轻量本轮简报 + block-owner worker 判断共同完成。调度器或专用轻量节点只生成带 source refs 的本轮简报；worker 决定自己 block 的视图事实；Context Orchestration Layer 负责最终 writer packet 全局取舍。
33. 调度频率必须可配置，不要求每轮都做完整调度。ModeProfile / runtime config 可配置每 N 轮完整调度，也可由 user edit、rule card、scene switch、状态变化、manual refresh、window overflow、dirty block 等事件触发。
34. Letta 的源码参考应按“agent / worker 通过工具管理 memory”理解，而不是按“存储层自动搬运”理解。本项目与 Letta 的共同点是工具化 memory 管理；差异是 RP runtime 需要额外治理剧情真相、用户编辑、worker 权限、mode profile、回退、分支和 writer workflow。
35. Git 式版本管理只管理 Memory OS 的正文状态、分支可见性、失效 / 遮蔽关系和可回放引用；检索索引、embedding、HNSW index、top hits 和检索缓存都是派生产物，不作为 story truth，也不直接进入 Git 式版本对象。
36. Recall / Archival 检索命中默认只是引用材料。只有当 block-owner worker 判断它应成为当前剧情必须遵守的事实，并经过 permission / proposal / apply / user review 链路后，才允许写入 Core State 当前事实并刷新当前视图。
37. writer 检索知识的主路径是 writer 自行判断当前上下文是否缺信息，并通过受控 retrieval 工具发起查询；不新增一个主路径的写前缺口预检层，也不让 Context Orchestration Layer 替 writer 决定是否检索。
38. writer-side retrieval 的召回材料先进入 Runtime Workspace，表现为本轮检索卡片、短编号映射、摘要、refs、展开内容、missed query、attempt trace 和 usage record；Recall Memory 不作为本轮 raw hit 暂存区，Context Orchestration Layer 不承担存储语义。
39. writer 可以在受控 attempt limit 内重试检索，也可以请求展开已返回卡片；但每轮发生 retrieval 后，最终输出前必须有结构化 retrieval usage record。post-write scheduler 只处理 `used_cards`、必要 `expanded_cards` 和 `knowledge_gaps`。
40. 检索卡片 / 摘要 / 展开 chunk 都是证据，不是事实。写后必须由 block-owner worker 追溯 provenance、抽取事实候选，并通过 permission / proposal / apply / user review 链路后才进入 Core State 当前事实和当前视图。

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
- [ ] PRD / spec 能表达 writer packet 不能只依赖 Core State 当前视图，还必须保留近几轮 user input / writer output 原文窗口。
- [ ] PRD / spec 能表达 token 实际消费量来自上游 LLM usage metadata，本地预算/预估只用于组包前裁剪辅助。
- [ ] PRD / spec 能表达 roleplay / trpg 的用户下一条消息作为 acceptance signal，并区分暂定可见材料与稳定维护材料。
- [ ] PRD / spec 能清楚区分 rollback 与 branch：rollback 是当前主线单向回到旧 turn，并让目标 turn 之后内容失效；branch 是保留多条未来。memory/text/packet/window 状态必须在同一回溯边界下恢复。
- [ ] PRD / spec 能表达 branch 之间 memory/context 隔离、可切换、可删除，以及 copy-on-write / branch visibility 优先于整套 memory 复制的架构方向。
- [ ] PRD / spec 能表达 Story Evolution 默认 branch-scoped，只有显式 promote-to-global / apply-to-all-branches 才影响全局底座或其他分支。
- [ ] PRD / spec 能表达 `StorySession / BranchHead / Turn` 三层身份模型，并要求 runtime 执行和 memory/retrieval 读取绑定 active branch head。
- [ ] PRD / spec 能表达 worker 按 block/domain ownership 划分，同一 worker 通过 phase 区分 pre-write context 与 post-write maintenance。
- [ ] PRD / spec 能表达 Story Evolution 复用现有 Memory OS / proposal / ingestion / block worker 能力，不先新增平行 worker 系统；Recall Memory 不是默认设定 CRUD 层。
- [ ] PRD / spec 能表达 memory 可见 / 可改是正式产品能力，前端通过项目 DSL / canonical JSON block format 渲染 block / entry，Core / Recall / Archival 的可改方式不同。
- [ ] PRD / spec 能表达轻量 memory change event 作为统一 trace / invalidation 脊柱，但避免过重 event sourcing。
- [ ] PRD / spec 能表达用户显式 Core State 编辑优先于后台 worker 候选，worker 候选必须带 base revision 并在 apply / projection update 前做冲突检查。
- [ ] PRD / spec 能表达轻量本轮简报 + block-owner worker 共同决定当前视图事实，Context Orchestration Layer 负责最终 writer packet 取舍。
- [ ] PRD / spec 能表达完整调度频率可配置，不要求每轮调度，并支持事件触发调度。
- [ ] PRD / spec 能表达 Letta 参考的真实边界：agent / worker 通过工具管理 memory，Git memory 可参考正文版本和缓存同步，但不能替代本项目的 story branch 隔离。
- [ ] PRD / spec 能表达检索索引是由正文派生的搜索加速结构，不是 story truth；rollback / branch 管理正文状态和可见性，检索层按 active branch / turn 可见性过滤并按需 reindex。
- [ ] PRD / spec 能表达 Recall / Archival 检索命中到 Core State 当前事实的换入条件：必须由 block-owner worker 整理，并经过权限、proposal/apply 或用户审查。
- [ ] PRD / spec 能表达 writer-side bounded retrieval：writer 判断知识不足并通过受控工具检索；Context Orchestration Layer 不作为新增写前预检层。
- [ ] PRD / spec 能表达 retrieval cards / short ids / expand tool / Runtime Workspace 映射合同，避免 writer 直接记忆随机 hit_id / chunk_id。
- [ ] PRD / spec 能表达 retrieval usage hook：发生 retrieval 后，writer final output 前必须记录 used cards、expanded cards、unused cards 和 knowledge gaps。
- [ ] PRD / spec 能表达检索 miss 的受控重试与 gap 记录策略，以及 retrieval-triggered turn 必须走 post-write 调度。
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
