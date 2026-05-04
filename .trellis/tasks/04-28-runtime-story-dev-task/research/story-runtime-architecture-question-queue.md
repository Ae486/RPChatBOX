# Story Runtime Architecture Question Queue

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Purpose: maintain the FIFO grill-me queue for story runtime requirements, design, and architecture discussion.
>
> Last updated: 2026-05-04

## Queue Rules

- This document tracks discussion questions by architecture/module.
- Question status uses `[ ]` for pending and `[x]` for confirmed.
- Discussion follows FIFO order.
- If a question produces a new question in the same module, append it to that module.
- If a question produces a cross-module question, append it to the target module.
- If a later module produces a new question for an earlier module, do not jump back immediately; finish the current forward pass, then start another pass from the beginning.
- Task-level confirmed decisions override older upstream design docs when there is a conflict.
- This queue is for design clarification only; it does not by itself authorize code implementation.

## Current Pointer

Next discussion batch: Module 4 / Q3 always-run and scheduled workers coexistence. ModeProfile parent Q2 remains pending for final parent-level closure.

## Module 1: Overall Boundary / First-stage Goal

- [x] Q1. 第一阶段到底要交付“可运行骨架升级”，还是只交付“spec coding 方案”？
  - Confirmed direction: 先把完整 spec coding 方案讨论完并落稳，再进入最小实现。
  - Confirmed direction: 当前 longform 只是极其简陋的 MVP。实现切片可以借它承载，但它不是硬约束；如果它阻碍新的完整 story runtime 设计，允许推翻重建。
- [x] Q2. 第一阶段是否允许改变产品行为，还是只补 runtime 合同和内部状态？
  - Confirmed direction: spec coding 方案不受当前 longform MVP 行为约束。进入代码实施时，也不把“保持当前 longform MVP 行为完全不变”作为硬约束。
  - Confirmed direction: 允许改变当前 MVP 的用户可见行为，但必须是为了靠近新的 story runtime 产品目标和核心合同，不能只是临时改坏体验或制造新分叉。

## Module 2: ModeProfile / StorySession / Branch / Turn Identity

- [x] Q1. runtime 每轮执行时，最小身份锚点是否冻结为 StorySession + active branch + turn + runtime profile snapshot？
  - Recommended direction: 冻结。否则 memory、retrieval、回退、分支都会混线。
  - Discussion note: 用户认为这可能是“理所当然”的实现前提，但当前需要用更通俗方式解释其架构意义，再决定是否标记为确认。
  - Confirmed direction: 冻结。每轮 runtime memory 操作都必须绑定 `StorySession + active BranchHead + Turn + runtime profile snapshot`。对外 API 可以仍以 session 为入口，但内部 memory read/write/search、proposal/apply、retrieval cards、Runtime Workspace materials、projection refresh、packet/window metadata 都必须解析并携带 active branch / turn identity。详细实现合同见 `research/memory-layer-strengthening-proposal.md` 的 "Identity Anchor Contract"。
- [ ] Q2. ModeProfile 在 active runtime 中应被编译成哪些可执行 policy，而不是只保留 mode 字符串？
  - Recommended direction: 至少 worker policy、retrieval policy、packet policy、writer policy、post-write policy、latency/budget policy。
  - Discussion note: 用户要求 ModeProfile 单独细谈，因为它是区分 longform / roleplay / trpg 等功能的重要关键。父问题在 ModeProfile detailed subqueue 完成后再确认。

### Module 2 / ModeProfile Detailed Subqueue

- [x] Q2.1. ModeProfile 的生命周期是否冻结为：创建 story / setup 前选择，activation 时编译成 runtime snapshot，active runtime 只读 snapshot？
  - Confirmed direction: 是。ModeProfile 在 story/setup 前选择；activation 时编译成 runtime snapshot；active runtime 不直接修改 mode identity。
- [x] Q2.2. ModeProfile 是否明确拆成 setup_profile、memory_profile、runtime_profile，而不是一个大 prompt 配置？
  - Confirmed direction: 可以拆，但要用产品语义理解：主要管 setup 阶段流程、Core Memory / Memory OS 展示和激活哪些 block、story runtime 的调度器 + worker 层怎么走。
- [x] Q2.3. ModeProfile 与 worker 配置 stage 的关系是什么？
  - Confirmed direction: ModeProfile 给默认 worker 选择和默认路线；worker 配置 stage 负责具体启用 worker、调整该 worker 对各 block 的权限 level，并包含供应商 / 模型配置等用户可调项。
- [ ] Q2.4. ModeProfile 如何规定“哪些 memory domain/block 在该 mode 下默认展示 / 激活”？
  - Confirmed direction: 是，需要设计。用户要求先盘清当前 memory 层已有 block/domain 设计，再讨论各 mode 默认展示和激活策略。
  - Current finding: `core-state-memory-detailed-design.md` 的 MVP domain 集包含 `scene`、`character`、`relation`、`goal`、`plot_thread`、`foreshadow`、`timeline`、`world_rule`、`inventory`、`chapter`、`narrative_progress`。`x08-memory-os-redesign-draft.md` 仍有“9 个 memory block domain”的旧表述，后续 spec 需要统一口径。
  - Confirmed direction: TRPG 的 `rule_state` / `mechanics_state` 可以作为独立 domain，不归入 `world_rule` 或 `inventory`。
  - Confirmed direction: worker 按 `domain` 划分，不按 `block` 划分。`block` 是 domain 在某一层 Memory OS 里的具体容器；worker 负责 domain，权限再细分到 layer / block。
  - Research artifact: `research/story-runtime-memory-domain-preliminary-design.md`
- [x] Q2.4.1. `knowledge_boundary` 应该作为独立 domain，还是作为 `character` domain 下的 sub-block？
  - Recommended direction: 独立 domain，但默认由 `CharacterMemoryWorker` 主责维护。理由是角色知道/不知道什么会跨 character、relation、scene、timeline 发生变化，独立后更容易做冲突检查、可见性过滤和 roleplay/trpg 的上下文控制。
  - Confirmed direction: `knowledge_boundary` 独立成 domain；roleplay / TRPG 默认启用，longform 默认可选启用；第一版不单独拆执行 worker，默认由 `CharacterMemoryWorker` 一起维护，但输出必须按 `knowledge_boundary` 独立写 proposal / projection / trace。
- [x] Q2.4.2. 第一版 domain 候选全集是否采用 13 个：`scene`、`character`、`knowledge_boundary`、`relation`、`goal`、`timeline`、`plot_thread`、`foreshadow`、`world_rule`、`inventory`、`rule_state`、`chapter`、`narrative_progress`？
  - Recommended direction: 暂按 13 个冻结为 spec 候选全集；实现可按 mode 只启用子集。后续若发现 `knowledge_boundary` 不独立，则收回到 12 个。
  - Confirmed direction: 采用 13 个作为第一版 domain bootstrap set。该全集不是永久写死枚举；memory 层必须模块化、可维护，并支持后期 domain / block 的增删查改、隐藏、废弃、迁移、mode 默认值调整和 UI 可见性调整。后续实现应优先 registry / config 驱动，而不是把 13 个 domain 散落硬编码到服务和 worker 里。
- [x] Q2.4.3. “worker 按 domain 划分”是否要求一个 worker 只能负责一个 domain，还是允许一个执行 worker 负责多个相关 domain？
  - Discussion note: 用户指出当前说法存在冲突：如果 `CharacterMemoryWorker` 同时负责 `character` 和 `knowledge_boundary`，就不是严格的一 worker 一 domain。
  - Recommended direction: 冻结为“责任按 domain 登记；执行 worker 可以绑定多个强相关 domain”。也就是每个 domain 必须有清晰主责 worker，但不要求一个 worker 只能负责一个 domain。若用户坚持严格一对一，则应把 `knowledge_boundary` 作为独立 domain + 独立 worker。
  - Current research note: Letta local source shows one agent can hold and manage multiple core memory blocks through labeled memory tools, prompt compile, read-only flags, history, and git-backed source-of-truth / PostgreSQL cache sync. This supports "one memory actor can handle multiple blocks", but it does not remove this project's need for domain ownership, permission checks, and per-domain / per-block structured worker output.
  - Confirmed direction: 接受 Letta 证明这种设计可行，并确认本项目是在模仿 Letta 的 memory actor / multiple blocks / tool-managed memory 思路，同时按 RP 需求保留自己的 domain ownership、权限、用户编辑、分支回退和 worker 输出合同。因此冻结为“责任按 domain 登记；执行 worker 可以聚合少量强相关 domain；输出必须按 domain / block 拆结构化结果”。
- [x] Q2.5. ModeProfile 是否应该规定 writer packet 的组成比例和优先级？
  - Corrected direction: 不应这样问。writer 主要负责写作；文风、写作风格等在 setup 阶段讨论。writer 输入由 Context Orchestration Layer 组包，来源包括近几轮原文窗口、Core State 当前视图、特殊 worker 内容等。ModeProfile 可以影响上下文编排策略的默认值，但主要区分度在 worker。
- [x] Q2.6. ModeProfile 是否应该规定 writer 可用工具与工具限制？
  - Corrected direction: 不应这样问。检索等能力会在 worker 配置 stage 做好；writer 不应被理解成自由工具 agent。writer-side retrieval 已确认是受控能力，但其开关、模型和权限应通过 worker / runtime 配置合同表达。
- [x] Q2.7. ModeProfile 是否应该规定 post-write processing 的触发和接受信号？
  - Corrected direction: 不再重复提问。task PRD 已经设计：roleplay / trpg 以 writer 输出后为整理点；用户下一条消息当前作为 acceptance signal；完整调度频率可配置；post-write 是同一 workflow 内部处理，不是新增 writer 输出线。
- [x] Q2.8. ModeProfile 是否应该规定性能预算，而不是让所有 mode 用同一套调度强度？
  - Corrected direction: 当前不继续讨论。task PRD 已有 interactive mode 性能约束和调度频率设计；后续进入具体 spec 时再按已有口径细化，不作为 grill-me 重复问题。
- [x] Q2.9. ModeProfile 是否应该规定 proposal / review / permission 默认策略？
  - Corrected direction: 不再重复提问。worker 权限已经确认在 worker 配置 stage 中设置，粒度为启用 worker + 调整该 worker 对各 block 的权限 level。
- [x] Q2.10. ModeProfile 是否应该规定 Story Evolution 的默认范围？
  - Confirmed direction: 默认只进当前分支。
- [x] Q2.11. ModeProfile 第一版是否只做“合同和默认策略”，不一次性做完整 longform / roleplay / trpg 行为？
  - Confirmed direction: 可以不全做完，但必须预留，而不是全量按照 longform 行为设计编码。

## Module 3: Memory OS Layer Responsibilities

- [x] Q1. Recall Memory 的产品职责需要重新讲清楚：它到底是“历史回忆层”，还是“半当前缓存层”？
  - Confirmed direction: Recall 只管过去已发生材料和摘要，不承担当前事实缓存；当前事实仍进 Core State，当前轮临时材料进 Runtime Workspace。
  - Confirmed direction: Recall 被检索命中后只是历史证据，不自动变成当前事实；要进入 Core State 必须经过 writer usage record、block-owner worker 整理、权限 / proposal / apply / user review 链路。
- [x] Q2. Core State 当前事实和当前视图的写入边界是否足够硬？
  - Recommended direction: 当前事实走 proposal/apply 或用户显式编辑；当前视图由 block-owner worker 刷新，但必须可追溯 source refs。
  - Confirmed direction: 冻结强边界。`Core State.authoritative_state` 是 story truth，`Core State.derived_projection` 是从事实层抽取出来的 writer / orchestrator / UI 可消费视图，视图必须严格来源于事实层，不能反过来冒充事实。worker 写当前事实由权限决定：低权限走用户 review，高权限可无需用户审核自动 apply；但无论权限高低，都必须经过受治理的权限检查、base revision / conflict check、provenance、memory change event / trace，不允许裸写库或把自然语言分析结果直接塞成 truth。projection refresh 是维护操作，必须带 source refs / base revision / refresh actor / dirty / invalidation 语义。

## Module 4: Worker System

- [x] Q1. worker catalog 第一版按哪些 macro worker 落地，避免过度拆分？
  - Recommended direction: 先 LongformMemoryWorker 兼容现有 specialist，再预留 CharacterMemoryWorker、SceneInteractionWorker、RuleStateWorker，不马上全实现。
  - Confirmed direction: 第一版 worker catalog 采用少量 macro worker，而不是按微功能过度拆分。建议启动集合为 `LongformMemoryWorker` 兼容现有 specialist，并预留 `CharacterMemoryWorker`、`SceneInteractionWorker`、`RuleStateWorker`。该集合是 bootstrap set，不是永久写死结构；worker 设计必须模块化、可维护，支持后续 worker 增删、domain 绑定调整、mode 默认启用调整、权限调整、模型/供应商调整、phase 行为扩展和输出合同演进。实现应优先 registry / config / contract 驱动，避免把 worker 名称、domain 绑定、mode 判断散落硬编码在 runtime 服务里。
- [x] Q2. worker 是按 block ownership 划分，但同一 worker 是否允许在 pre-write 和 post-write 两个 phase 做不同任务？
  - Recommended direction: 允许。不要拆成两套 worker，phase 决定输入、权限、输出。
  - Confirmed direction: 允许，并且已有 task PRD 已给出流程设计。同一 worker 是 domain / block ownership 下的专家执行单元，不等于一次 LLM 调用，也不按 pre-write / post-write 拆成两套 worker。phase 决定该 worker 本轮输入、权限、工具、输出合同和递交流向：`pre_write_context` 负责读取 block / retrieval / recent turns 并产出 writer hints / packet slot / constraints；`post_write_maintenance` 负责读取 user input + writer output + sidecars 并产出 projection refresh、state proposal、Recall candidate、trace 等。实现必须保持模块化，可通过 worker catalog / phase policy / RuntimeProfileSnapshot 扩展 `manual_refresh`、`story_evolution` 等 phase 行为。
- [ ] Q3. “每轮必做 worker”和“调度决定 worker”如何共存？
  - Recommended direction: 必做项编入 workflow；调度项由 Orchestrator 提案、确定性 Scheduler 裁决。

## Module 5: Scheduler / Orchestrator / Workflow

- [ ] Q1. Orchestrator Worker 和 Deterministic Scheduler 的边界是否冻结？
  - Recommended direction: Orchestrator 只提案，Scheduler 裁决和执行，不能让 LLM 直接拥有 workflow 主权。
- [ ] Q2. post-write processing 是否是 active runtime 的核心主线，而不是附属维护任务？
  - Recommended direction: 是。writer 输出后处理本轮材料、派发 block worker、准备下一轮 writer view，这是 runtime 主链之一。
- [ ] Q3. 调度频率配置应该作用于“完整 post-write worker 调度”，还是也影响最小必要状态更新？
  - Recommended direction: 只影响完整调度；最低限度的 turn 记录、usage record、pending 标记不能跳过。

## Module 6: Context Orchestration Layer / WritingPacketBuilder

- [ ] Q1. Context Orchestration Layer 的职责是否冻结为组包、refs、budget、裁剪、整合已有结果，而不是新增智能预检层？
  - Recommended direction: 冻结。
- [ ] Q2. writer packet 的最小稳定组成是否冻结？
  - Recommended direction: Core State 当前视图 + 近几轮原文 + 必要 refs/cards + worker hints + mode writer policy。
- [ ] Q3. builder 是否绝不直接吃 raw retrieval hits / raw authoritative JSON？
  - Recommended direction: 是。builder 只吃稳定 slot 和结构化结果。

## Module 7: WritingWorker

- [x] Q1. writer 是否允许受控工具 loop 做检索、展开、usage record，再输出唯一正文？
  - Confirmed direction: 允许，但不是开放 agent；不能写 memory；最终只有一份用户可见输出。
- [ ] Q2. 工具阶段和最终输出阶段的流式策略是否冻结？
  - Recommended direction: 工具阶段内部执行不流式，最终正文阶段再流式，避免半成品工具过程暴露给用户。
- [ ] Q3. usage record 是独立工具调用、final sidecar，还是两者都支持？
  - Recommended direction: 第一阶段做独立工具调用，便于 runtime guard；后续可兼容 final sidecar。

## Module 8: Retrieval / Runtime Workspace

- [ ] Q1. writer-side retrieval 的召回内容进入 Runtime Workspace 后，生命周期到什么时候结束？
  - Recommended direction: 本 turn 有效；post-write 后只保留 trace、usage、必要 provenance，raw 内容压缩或丢弃。
- [ ] Q2. 检索 miss 在不同 mode 下是否需要不同策略？
  - Recommended direction: 需要。longform 可要求保守停写/询问，roleplay 可保守绕开，trpg 硬规则缺失时不能编造。
- [ ] Q3. retrieval 层是否只做召回和结构化卡片，不做结合剧情上下文的创作性总结？
  - Recommended direction: 是。

## Module 9: Post-write Maintenance / Proposal / User-edit Conflict

- [ ] Q1. worker 候选更新和用户手改 Core State 冲突时，统一处理规则是否冻结？
  - Recommended direction: 用户编辑优先；worker 候选带 base revision，apply 时发现目标已变更就失效或重算。
- [ ] Q2. roleplay/trpg 中用户下一条消息作为接受信号时，后台 post-write 尚未完成怎么办？
  - Recommended direction: 下一轮可用上一版 settled view + pending 标记，不让后台无限阻塞 writer。
- [ ] Q3. post-write 写入 Core State、刷新当前视图、物化 Recall 的顺序是否需要冻结？
  - Recommended direction: 先完成 worker 分析，再优先递交下一轮视图，其余 proposal/Recall 可后续完成。

## Module 10: Longform / Roleplay / TRPG Mode Differences

- [ ] Q1. longform 的 draft review overlay 是否应进入统一 turn material，而不是另起一套流程？
  - Recommended direction: 是，作为 sidecar 进入同一 runtime lifecycle。
- [ ] Q2. TRPG rule card / state card 是否也作为 sidecar 进入 writer packet 和 post-write？
  - Recommended direction: 是，规则判定不让 worker 从自然语言里重新猜。
- [ ] Q3. roleplay 用户主动操控角色行为时，是否仍统一为 user input + writer output 的一轮材料？
  - Recommended direction: 是，由 writer 润色/承接后，post-write 再整理。

## Module 11: Branch / Rollback / Versioning

- [ ] Q1. branch-aware read 是否必须成为第一阶段合同，即使不完整实现分支 UI？
  - Recommended direction: 合同必须预留，否则后续 memory/retrieval 很难补。
- [ ] Q2. rollback 后的失效内容是否只做当前主线不可见，不物理删除？
  - Recommended direction: 产品语义可说失效；底层先 tombstone/visibility 处理，便于审计和未来 branch。
- [ ] Q3. retrieval index 是否明确只是派生产物，不进入版本真相？
  - Recommended direction: 是。版本管理正文、memory、可见性；索引按可见性过滤和重建。

## Module 12: Story Evolution / Memory Visibility And Editability

- [ ] Q1. Story Evolution 是否复用 active runtime 的 worker/memory 工具，而不新增平行 agent 系统？
  - Recommended direction: 复用，只增加明确 flow 和 UI 入口。
- [ ] Q2. memory DSL / canonical JSON block format 是否必须作为 UI 编辑和 worker 写入的共同格式？
  - Recommended direction: 必须，否则用户可编辑、worker proposal、trace 会断裂。
- [ ] Q3. Recall / Archival 的用户编辑是否都必须走 ingestion/reindex，而不是直接改文本？
  - Recommended direction: 是，尤其进入 retrieval 的内容必须维护 provenance 和索引一致性。
- [x] Q4. Memory OS 各层是否都对用户公开，且不同层采用不同编辑方式？
  - Confirmed direction: 是。所有 memory 层都对用户公开。Core State 可直接编辑；Recall Memory 主要保留已有事实 / 历史材料，基本只回顾、失效、重算，不作为常规编辑层；Archival Knowledge 可修改，但必须通过 Story Evolution / ingestion / reindex 流程，因为会经过 retrieval 层。

## Module 13: Observability / Trace / Eval Boundary

- [ ] Q1. story runtime 第一阶段必须暴露哪些 trace，才能让 eval session 后续接入？
  - Recommended direction: turn material refs、profile snapshot、worker plan、packet summary、retrieval usage、proposal/apply 结果。
- [ ] Q2. 本 task 是否完全不做 eval runner，只保证产物可观测？
  - Recommended direction: 是，eval 模块由其他 session 负责。

## Module 14: Implementation Slice / Current Implementation Migration

- [ ] Q1. 第一个代码切片应该先改 OrchestratorPlan/WorkerPlan，还是先改 WritingWorker tool loop？
  - Recommended direction: 先改 worker/scheduler/context 合同，再接 writer tool loop；否则 writer 检索会缺 Runtime Workspace 和 post-write 承接。
- [ ] Q2. 现有 LongformSpecialistService 第一阶段是否作为 LongformMemoryWorker 兼容执行？
  - Recommended direction: 是，避免重写。
- [ ] Q3. 当前 legacy mirror 和正式 Core State store 的关系，第一阶段是否只读写现有兼容层，不扩大耦合？
  - Recommended direction: 是，新增合同尽量指向正式 Store/Broker 口径。
- [ ] Q4. 如果现有 longform MVP 链路阻碍完整 story runtime 合同，第一阶段是否允许从新 runtime 骨架起一条替代实现，而不是继续包旧链路？
  - Recommended direction: 允许，但必须在 spec coding 方案中明确迁移边界、旧链路保留/废弃策略、最小可验证路径和回滚方式。
