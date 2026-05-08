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

Next discussion batch: Module 21 branch operation semantics. Continue in FIFO order.

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
- [x] Q2. ModeProfile 在 active runtime 中应被编译成哪些可执行 policy，而不是只保留 mode 字符串？
  - Recommended direction: 至少 worker policy、retrieval policy、packet policy、writer policy、post-write policy、latency/budget policy。
  - Discussion note: 用户要求 ModeProfile 单独细谈，因为它是区分 longform / roleplay / trpg 等功能的重要关键。父问题在 ModeProfile detailed subqueue 完成后再确认。
  - Confirmed direction: 冻结。ModeProfile 必须编译成可执行 policy，而不是只保留 mode 字符串。确认清单来自 PRD / 既有讨论：`setup_profile`、`memory_profile`、`runtime_profile`，并在 runtime_profile 内明确 worker policy、retrieval policy、packet / context policy、writer policy、post-write policy、budget / latency policy、permission profile。这些项目都能在 PRD 的 ModeProfile scope、mode differentiation、worker configuration、runtime snapshot、writer packet、writer-side retrieval、execution categories 和 trace 章节找到对应口径。

### Module 2 / ModeProfile Detailed Subqueue

- [x] Q2.1. ModeProfile 的生命周期是否冻结为：创建 story / setup 前选择，activation 时编译成 runtime snapshot，active runtime 只读 snapshot？
  - Confirmed direction: 是。ModeProfile 在 story/setup 前选择；activation 时编译成 runtime snapshot；active runtime 不直接修改 mode identity。
- [x] Q2.2. ModeProfile 是否明确拆成 setup_profile、memory_profile、runtime_profile，而不是一个大 prompt 配置？
  - Confirmed direction: 可以拆，但要用产品语义理解：主要管 setup 阶段流程、Core Memory / Memory OS 展示和激活哪些 block、story runtime 的调度器 + worker 层怎么走。
- [x] Q2.3. ModeProfile 与 worker 配置 stage 的关系是什么？
  - Confirmed direction: ModeProfile 给默认 worker 选择和默认路线；worker 配置 stage 负责具体启用 worker、调整该 worker 对各 block 的权限 level，并包含供应商 / 模型配置等用户可调项。
- [x] Q2.4. ModeProfile 如何规定“哪些 memory domain/block 在该 mode 下默认展示 / 激活”？
  - Confirmed direction: 是，需要设计。用户要求先盘清当前 memory 层已有 block/domain 设计，再讨论各 mode 默认展示和激活策略。
  - Current finding: `core-state-memory-detailed-design.md` 的 MVP domain 集包含 `scene`、`character`、`relation`、`goal`、`plot_thread`、`foreshadow`、`timeline`、`world_rule`、`inventory`、`chapter`、`narrative_progress`。`x08-memory-os-redesign-draft.md` 仍有“9 个 memory block domain”的旧表述，后续 spec 需要统一口径。
  - Confirmed direction: TRPG 的 `rule_state` / `mechanics_state` 可以作为独立 domain，不归入 `world_rule` 或 `inventory`。
  - Confirmed direction: worker 按 `domain` 划分，不按 `block` 划分。`block` 是 domain 在某一层 Memory OS 里的具体容器；worker 负责 domain，权限再细分到 layer / block。
  - Research artifact: `research/story-runtime-memory-domain-preliminary-design.md`
  - Final confirmed direction: 第一版采用“必要默认配置 + 用户可调 + registry / config 驱动”。ModeProfile 给各 mode 的默认 domain / block 展示和激活集合，但实现不能把 longform / roleplay / trpg 的 domain、worker、block 写死在调度器或服务里。调度器、Memory OS、worker catalog、Context Orchestration Layer、writer packet builder 和权限链都必须通过 registry / config / RuntimeProfileSnapshot 读取配置。后期增加、隐藏、废弃、删除或迁移 worker / domain / block 后，相关链路应仍能按配置发现和调用对应功能。
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
- [x] Q2.12. ModeProfile preset 后续升级时，旧 story session 是否自动跟随升级？
  - Recommended direction: 不自动升级。`ModeProfile preset` 可以升级；`RuntimeProfileSnapshot` 必须不可变；旧 session 继续使用 activation 时编译的 snapshot。新 runtime 必须通过 compatibility adapter 读取旧 snapshot。旧 session 升级必须显式执行 migration / refresh，并生成新 snapshot，从下一轮开始生效。
  - Confirmed direction: 可以。专业口径是快照不可变 + 新代码能读旧配置 + 显式迁移。新版系统要能打开旧故事，但不能偷偷改变旧故事运行规则。

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
  - Engineering wording: worker 系统应采用 contract-first、registry-driven、plugin-style worker catalog。每个 worker 基于统一 `WorkerDescriptor` / `WorkerExecutor` / `WorkerContextPacket` / `WorkerResult` 合同实现；不同 worker 主要通过 descriptor、domain binding、phase policy、tool allowlist、prompt/profile、permission policy 和 output schema 配置差异表达，而不是每个 worker 手写一套调用链。Scheduler 只依赖统一合同和 registry，不直接 hardcode 某个 worker 类名或 mode 分支。Worker 应支持按 RuntimeProfileSnapshot enable / disable / bind domains / configure provider-model，做到可装卸、可替换、可测试。
- [x] Q2. worker 是按 block ownership 划分，但同一 worker 是否允许在 pre-write 和 post-write 两个 phase 做不同任务？
  - Recommended direction: 允许。不要拆成两套 worker，phase 决定输入、权限、输出。
  - Confirmed direction: 允许，并且已有 task PRD 已给出流程设计。同一 worker 是 domain / block ownership 下的专家执行单元，不等于一次 LLM 调用，也不按 pre-write / post-write 拆成两套 worker。phase 决定该 worker 本轮输入、权限、工具、输出合同和递交流向：`pre_write_context` 负责读取 block / retrieval / recent turns 并产出 writer hints / packet slot / constraints；`post_write_maintenance` 负责读取 user input + writer output + sidecars 并产出 projection refresh、state proposal、Recall candidate、trace 等。实现必须保持模块化，可通过 worker catalog / phase policy / RuntimeProfileSnapshot 扩展 `manual_refresh`、`story_evolution` 等 phase 行为。
- [x] Q3. “每轮必做 worker”和“调度决定 worker”如何共存？
  - Recommended direction: 必做项编入 workflow；调度项由 Orchestrator 提案、确定性 Scheduler 裁决。
  - Confirmed direction: “每轮必做 worker”应理解为 workflow 级必经能力，而不是执行级无条件重跑。只要本轮进入对应 workflow，它必须被 Scheduler 纳入计划和治理；但 Scheduler 可以根据 mode、budget、dirty 状态、内容变化、manual refresh、retrieval 行为和调度频率，把它降级为只读预取、复用上一版结果、标记 pending，或执行轻量检查。真正重 LLM / mutation / projection refresh 仍需满足触发条件和权限。调度决定 worker 仍由 Orchestrator 提案、Scheduler 裁决和派发。这样可以保留 mode workflow 的稳定骨架，同时避免 interactive mode 每轮都强制跑重 worker。

## Module 5: Scheduler / Orchestrator / Workflow

- [x] Q1. Orchestrator Worker 和 Deterministic Scheduler 的边界是否冻结？
  - Recommended direction: Orchestrator 只提案，Scheduler 裁决和执行，不能让 LLM 直接拥有 workflow 主权。
  - Confirmed direction: 是。LLM 只负责提出调度提案，且提案必须以结构化形式输出，供后端直接解析与校验；这个结构化形式可以通过 tool 输出，也可以通过严格 schema 的文本输出，本质上都是同一类“机器可解析提案”。真正是否执行、是否降级、是否跳过、是否并行，以及是否允许写入，全部由 Deterministic Scheduler 裁决。
- [x] Q2. post-write processing 是否是 active runtime 的核心主线，而不是附属维护任务？
  - Recommended direction: 是。writer 输出后处理本轮材料、派发 block worker、准备下一轮 writer view，这是 runtime 主链之一。
  - Confirmed direction: 是。active runtime 的整体流程冻结为：Context Orchestration Layer 准备 writer packet，WritingWorker 输出唯一用户可见内容；writer 输出后，在满足调度频率、retrieval 行为或其他触发条件时进入 post-write 调度。调度器管理 worker，决定本轮启用哪些 worker，并向 worker 交付上一轮后产生的轮次区间材料和 worker 相关上下文。worker 整理 memory / projection / Runtime Workspace，并为下一轮 writer view 做准备。post-write processing 是 runtime 主链，不是可有可无的附属维护任务。
- [x] Q3. 调度频率配置应该作用于“完整 post-write worker 调度”，还是也影响最小必要状态更新？
  - Recommended direction: 只影响完整调度；最低限度的 turn 记录、usage record、pending 标记不能跳过。
  - Confirmed direction: 只影响完整调度。即使本轮不跑重 worker 分析、projection refresh 或 proposal 生成，也必须把本轮最低限度的运行材料写入 Runtime Workspace / 当前轮日志层，包括 user input、writer output、retrieval usage、profile snapshot version、branch / turn identity、pending / dirty 标记和 token usage metadata。这个日志层不是 Core State / Recall / Archival 中的剧情真相层，但它是后续补调度、回退、分支、trace 和 worker 追溯的基础。

## Module 6: Context Orchestration Layer / WritingPacketBuilder

- [x] Q1. Context Orchestration Layer 的职责是否冻结为组包、refs、budget、裁剪、整合已有结果，而不是新增智能预检层？
  - Recommended direction: 冻结。
  - Confirmed direction: 是。Context Orchestration Layer 是确定逻辑，职责是组包、refs、budget、裁剪和整合已有结果，不负责智能预检，不负责判断是否检索，也不负责决定 worker 主权。它只把已经存在的材料按 mode / turn / window / token policy 编排成 writer packet 和 worker context packet。
- [x] Q2. writer packet 的最小稳定组成是否冻结？
  - Recommended direction: Core State 当前视图 + 近几轮原文 + 必要 refs/cards + worker hints + mode writer policy。
  - Corrected direction: writer packet 不应塞入 Runtime Workspace 的日志、工具调用过程、trace、usage 等内部材料。冻结为更窄的 writer 输入：Core State 当前视图 / projection block views、近 X 轮 user input / writer output 原文窗口、mode 特殊内容、可能的检索卡片 / 展开内容，以及绝对必须有的 system prompt / writer contract（写作规范、文风、输出约束等）。Context Orchestration Layer 必须把日志、工具过程和多余内部材料剪裁掉，不能污染 writer 上下文。
- [x] Q3. builder 是否绝不直接吃 raw retrieval hits / raw authoritative JSON？
  - Recommended direction: 是。builder 只吃稳定 slot 和结构化结果。
  - Confirmed direction: 是。builder 只能消费已经整理好的稳定 slot，例如 Core State 当前视图 / projection block views、近 X 轮原文、检索卡片 / 展开内容、mode sidecar 和 system prompt / writer contract。raw retrieval hits、Core State 原始 JSON、工具 trace、worker 中间态、Runtime Workspace 日志和 usage metadata 都必须先经过对应层整理，不能直接塞给 builder 或 writer packet。

## Module 7: WritingWorker

- [x] Q1. writer 是否允许受控工具 loop 做检索、展开、usage record，再输出唯一正文？
  - Confirmed direction: 允许，但不是开放 agent；不能写 memory；最终只有一份用户可见输出。
- [x] Q2. 工具阶段和最终输出阶段的流式策略是否冻结？
  - Recommended direction: 工具阶段内部执行不流式，最终正文阶段再流式，避免半成品工具过程暴露给用户。
  - Confirmed direction: 是。writer 工具阶段不对用户流式展示，最终正文阶段才对用户可见 / 流式。工具调用过程、retrieval / expand / usage record、tool result 和相关 trace 必须记录到 Runtime Workspace / 当前轮日志层，用于 scheduler、worker、回放、eval 和后期调试；但默认不暴露给用户。后续如果产品需要调试面板或 eval 面板，可以从日志层取出展示。
- [x] Q3. usage record 是独立工具调用、final sidecar，还是两者都支持？
  - Recommended direction: 第一阶段做独立工具调用，便于 runtime guard；后续可兼容 final sidecar。
  - Confirmed direction: 第一版强制用独立工具调用提交 retrieval usage record。后端可以用 runtime guard 校验：本轮发生 retrieval 时，缺 usage record 就不接受 final output 或触发 repair；提交后直接写入 Runtime Workspace / 当前轮日志层，供 post-write scheduler 稳定读取。final sidecar 后续可兼容，但不作为第一版主路径。
  - Confirmed terminology: 这里的“卡片”不是 UI 卡片，而是结构固定、后端可解析、可追溯的召回条目结构体。它需要包含短编号、真实 retrieval refs、摘要 / 摘录、可展开入口和 provenance 等字段，使 writer 能精确引用 `used_cards` / `expanded_cards`，post-write 调度能直接拿到准确字段，不再额外判断 writer 用到了哪些召回内容。

## Module 8: Retrieval / Runtime Workspace

- [x] Q1. writer-side retrieval 的召回内容进入 Runtime Workspace 后，生命周期到什么时候结束？
  - Recommended direction: 本 turn 有效；post-write 后只保留 trace、usage、必要 provenance，raw 内容压缩或丢弃。
  - Confirmed direction: retrieval raw content 放在 Runtime Workspace 临时区，只服务本轮 writer 和随后那次 post-write 调度。调度完成且 worker 整理完成后，真正需要长期保留的内容由 worker 按权限进入 Core State / Recall Memory / Archival Knowledge；Runtime Workspace 只保留 usage record、短编号映射、provenance refs、trace summary 等 eval / 回放 / 审计需要的结构化记录。raw hit、展开全文、工具中间结果默认删除、标记 discarded / expired，或只保留可重建引用。如果 worker 未完成或失败，则临时材料不能删，应保留 pending，等待补调度或 repair。
- [x] Q2. 检索 miss 在不同 mode 下是否需要不同策略？
  - Recommended direction: 需要。longform 可要求保守停写/询问，roleplay 可保守绕开，trpg 硬规则缺失时不能编造。
  - Confirmed direction: 需要，但第一版不要做复杂。主要通过 writer prompt / system prompt / writer contract 表达 mode-specific miss policy，再由 runtime guard 强制 knowledge_gap 记录。longform 可保守继续写，必要时在交流栏提示信息不足；roleplay 可继续互动但绕开缺失细节，不编造明确角色历史 / 设定事实；TRPG 如果缺的是硬规则、数值或判定依据，不能编造，应暂停、要求补规则或走规则 worker fallback。所有 mode 都必须记录 `knowledge_gap`，供 post-write 调度和 eval 使用。
- [x] Q3. retrieval 层是否只做召回和结构化卡片，不做结合剧情上下文的创作性总结？
  - Recommended direction: 是。
  - Confirmed direction: 是。retrieval 层只负责 RAG 能力本身：query augment、search、filter、rerank、score、provenance、摘要 / 摘录 / refs、结构化召回条目和短编号映射。它不结合当前剧情上下文做创作性总结，不替 writer 判断“这条资料该如何写进当前场景”，也不替 worker 判断“这条资料是否应沉淀为事实”。retrieval 给材料；writer 判断怎么用；worker 写后判断是否治理进入 Core State / Recall / Archival。

## Module 9: Post-write Maintenance / Proposal / User-edit Conflict

- [x] Q1. worker 候选更新和用户手改 Core State 冲突时，统一处理规则是否冻结？
  - Recommended direction: 用户编辑优先；worker 候选带 base revision，apply 时发现目标已变更就失效或重算。
  - Confirmed direction: 冻结。用户显式编辑 Core State 优先级最高。worker candidate / proposal 必须带 base revision；apply / projection update 时如果目标 block 已被用户或其他更高 revision 修改，worker 候选必须失效、进入 review 或重算，不能覆盖用户编辑。高权限 worker 可自动 apply，但仍必须经过权限、base revision、provenance、event / trace 和 dirty / invalidation 治理链。
- [x] Q2. roleplay/trpg 中用户下一条消息作为接受信号时，后台 post-write 尚未完成怎么办？
  - Recommended direction: 下一轮可用上一版 settled view + pending 标记，不让后台无限阻塞 writer。
  - Confirmed direction: 可以。系统不应无界等待后台 post-write。下一轮可以使用上一版稳定视图、近 X 轮原文窗口和 pending 标记继续 writer；未完成的 post-write 保持 pending，完成后刷新后续 writer packet。当前设计中的“每 X 轮完整调度一次 + 近几轮原文窗口”正是这个问题的主要缓冲：即使 projection 尚未刷新，近轮原文也能保留刚刚发生的互动、用户意图和 writer 输出细节，避免 writer 因后台整理未完成而断上下文。
- [x] Q3. post-write 写入 Core State、刷新当前视图、物化 Recall 的顺序是否需要冻结？
  - Recommended direction: 先完成 worker 分析，再优先递交下一轮视图，其余 proposal/Recall 可后续完成。
  - Confirmed direction: 确定，这是一直的口径。post-write 内部先由 worker 完整分析本轮材料；在 worker 整体分析完成后，优先递交下一轮 writer 需要的 Core State 当前视图 / projection block views；随后再处理 Core State proposal / apply、Recall materialization、Archival maintenance 等更重或更谨慎的长期沉淀。Runtime Workspace 日志和 trace 始终保留，用于补调度、eval、回退和审计。这是同一个 post-write workflow 内部的递交优先级，不是 writer 双输出，也不是独立轻量流程。
- [x] Q4. writer 输出后，是否必须同步等待完整 post-write 完成才能把文本返回给用户？
  - Recommended direction: 不必须。第一版允许 writer 文本先返回，post-write 在后台继续；但必需刷新状态必须进入下一轮 gating，不能让后台无限悬空。
  - Confirmed direction: 是。writer 文本可以先返回给用户，完整 post-write 在后台执行，并把 `pending / pending-deferred / settled` 状态写入 Runtime Workspace / 当前轮日志层。若用户下一轮输入到来而上一轮仍有必需刷新未完成，系统必须按这些状态决定等待、提示 pending，或在允许时先用上一版稳定视图加近几轮原文窗口继续。该口径来自既有 PRD 对“用户阅读和输入间隙用于后台整理”的设计，不新增独立轻量流程。

## Module 10: Longform / Roleplay / TRPG Mode Differences

- [x] Q1. longform 的 draft review overlay 是否应进入统一 turn material，而不是另起一套流程？
  - Recommended direction: 是，作为 sidecar 进入同一 runtime lifecycle。
  - Confirmed direction: 是，并且这套系统不只给 longform runtime 用。setup 阶段用户手动修改 draft 时也应复用同一套 review / revision overlay 语义，只是 UI 入口和触发时机不同。longform 的 `WritingWorker` 也不应是一个单人格写手，而应在同一 worker / 同一合同下支持两种操作模式：`discussion / brainstorm` 和 `writing / rewrite`。讨论区由 brainstorm 模式承接，产出区由 writing 模式承接；章节开始时可先 summary 上一章、产出本章大纲，再允许用户在交互区对大纲和设定继续头脑风暴、修订和确认。
- [x] Q2. TRPG rule card / state card 是否也作为 sidecar 进入 writer packet 和 post-write？
  - Recommended direction: 是，规则判定不让 worker 从自然语言里重新猜。
  - Confirmed direction: 是，PRD 已覆盖。TRPG rule card / state card 作为结构化 sidecar 进入 writer packet 和 post-write processing，规则判定不让 worker 从自然语言里重新猜。
- [x] Q3. roleplay 用户主动操控角色行为时，是否仍统一为 user input + writer output 的一轮材料？
  - Recommended direction: 是，由 writer 润色/承接后，post-write 再整理。
  - Confirmed direction: 是，PRD 已覆盖。roleplay 用户主动操控角色行为仍统一视为 user input + writer output 的一轮材料，由 writer 润色/承接后，post-write 再整理。

## Module 11: Branch / Rollback / Versioning

- [x] Q1. branch-aware read 是否必须成为第一阶段合同，即使不完整实现分支 UI？
  - Recommended direction: 合同必须预留，否则后续 memory/retrieval 很难补。
  - Confirmed direction: 是，PRD 已覆盖。branch / turn 可见性必须贯穿 memory read/write、retrieval filter、Runtime Workspace 和 packet/window metadata；第一阶段即使不完整实现分支 UI，也必须预留 branch-aware read 合同。
- [x] Q1.1. 分支切换时，未完成的 Runtime Workspace、worker candidate 和 pending 记录是否跟随切到新分支？
  - Recommended direction: 不跟随。它们应继续留在原 `BranchHead` 下，作为原分支自己的临时材料、候选更新和 trace。
  - Confirmed direction: 是，不携带。分支切换后，新分支只读取新分支自身的 Runtime Workspace / pending / worker candidate，以及 fork 前共享的 settled memory；原分支 fork 后的临时 workspace、pending 标记、worker candidate 和未完成调度结果不能污染新分支。
- [x] Q1.2. 分支删除时，分支专属 Runtime Workspace、worker candidate、pending、Core / Projection / Recall materialization 是否只隐藏，还是最终要物理删除？
  - Recommended direction: 第一版可以先做 deleted / hidden 可见性标记，后续后台清理；但最终能力必须支持物理删除分支专属材料。
  - Confirmed direction: 可以。最终一定要做物理删除。删除范围只包括 fork 后该分支专属的 Runtime Workspace、worker candidate、pending、Core / Projection revision、Recall materialization、packet/window metadata、retrieval derived records 等；不能删除 fork 前共享 settled memory，也不能误删 story-global Archival Knowledge。
- [x] Q1.3. Story Evolution 内容的可见性，是用一份内容挂 visibility scope，还是按分支复制多份副本？
  - Recommended direction: 一份内容挂 visibility scope。可见性规则支持当前分支、选定分支集合、所有已有分支、story-global；分支读取时按 branch / turn visibility 过滤。
  - Confirmed direction: 一份内容 + visibility scope。不是按分支复制多份副本。这样 provenance、治理、回收和删除都更清楚，复杂度也更可控。
- [x] Q1.4. 分支 / 回退模块是否优先依赖 LangGraph 现成能力，框架不支持的语义是否第一阶段先不做？
  - Recommended direction: 是，优先依赖 LangGraph 的 checkpoint / replay / fork 基础；框架不支持的语义先不硬补。
  - Confirmed direction: 是。分支 / 回退模块先吃 LangGraph 现成能力，Story runtime 只在框架支持的边界上向上设计；若某个 branch / rollback 语义当前框架不支持，第一阶段先不强行补齐。
- [x] Q2. rollback 后的失效内容是否只做当前主线不可见，不物理删除？
  - Recommended direction: 产品语义可说失效；底层先 tombstone/visibility 处理，便于审计和未来 branch。
  - Confirmed direction: 是，PRD 已覆盖。rollback 后目标 turn 之后内容在当前主线失效 / 不可见，底层优先采用 tombstone / visibility 处理，便于审计和未来 branch。
- [x] Q2.1. rollback 的统一回溯锚点是什么？是 memory 各层各自版本，还是统一以某一轮对话为准？
  - Recommended direction: 统一以 `Turn` 为回溯锚点。其他所有带版本内容都依附于该 `Turn`，回退时恢复该 `Turn` 完成后的最终可见状态，而不是分别选择 writer 版本、Core State 版本或 Recall 版本。
  - Confirmed direction: 是。以 user + writer 的一轮对话，也就是当前 `BranchHead` 上的 `Turn`，作为统一回溯锚点。`Core State revision`、projection block views、Recall / Archival materialization、Runtime Workspace 等都属于该 `Turn` 的内部版本。若同一轮里 `Core State` 改了多版，回退时取该轮最终有效的一版；回到轮次二，就恢复轮次二完成后的最终状态，包含该轮用户手动修改过的 `Core State`；轮次三的所有内容隐藏 / 失效。
- [x] Q3. retrieval index 是否明确只是派生产物，不进入版本真相？
  - Recommended direction: 是。版本管理正文、memory、可见性；索引按可见性过滤和重建。
  - Confirmed direction: 是，PRD 已覆盖。retrieval index、embedding、HNSW、top hits 和检索缓存都是派生产物，不进入版本真相。

## Module 12: Story Evolution / Memory Visibility And Editability

- [x] Q1. Story Evolution 是否复用 active runtime 的 worker/memory 工具，而不新增平行 agent 系统？
  - Recommended direction: 复用，只增加明确 flow 和 UI 入口。
  - Confirmed direction: 是，PRD 已覆盖。Story Evolution 复用 active runtime 的 worker / memory 工具，不新增平行 agent 系统，只增加明确 flow 和 UI 入口。
- [x] Q2. memory DSL / canonical JSON block format 是否必须作为 UI 编辑和 worker 写入的共同格式？
  - Recommended direction: 必须，否则用户可编辑、worker proposal、trace 会断裂。
  - Confirmed direction: 是，PRD 已覆盖。memory DSL / canonical JSON block format 必须作为 UI 编辑和 worker 写入的共同格式。
- [x] Q3. Recall / Archival 的用户编辑是否都必须走 ingestion/reindex，而不是直接改文本？
  - Recommended direction: 是，尤其进入 retrieval 的内容必须维护 provenance 和索引一致性。
  - Confirmed direction: 是，PRD 已覆盖。Recall / Archival 的用户编辑必须走 ingestion / reindex，尤其进入 retrieval 的内容必须维护 provenance 和索引一致性。
- [x] Q4. Memory OS 各层是否都对用户公开，且不同层采用不同编辑方式？
  - Confirmed direction: 是。所有 memory 层都对用户公开。Core State 可直接编辑；Recall Memory 主要保留已有事实 / 历史材料，基本只回顾、失效、重算，不作为常规编辑层；Archival Knowledge 可修改，但必须通过 Story Evolution / ingestion / reindex 流程，因为会经过 retrieval 层。
- [x] Q5. Story Evolution 内容如果只对某些已有分支可见，这个可见性是否会自动继承到之后从这些分支 fork 出来的新分支？
  - Recommended direction: 不自动继承。可见性只作用于被显式选中的分支集合；之后新 fork 出来的分支默认不自动获得该可见性，除非用户再次显式选择或将其提升为 story-global。
  - Confirmed direction: 是，不自动继承。
- [x] Q6. Story Evolution 的 visibility scope 是否允许后续修改，还是只能创建时一次性确定？
  - Recommended direction: 允许后续修改，但必须作为一次受治理的 visibility change 记录，而不是直接改旧记录。这样用户可以后续把内容扩展到更多分支或从某些分支移除可见性，同时保留 provenance、trace 和 reindex / purge 机会。
  - Confirmed direction: 可以。Story Evolution 可见范围后续允许修改；后端合同需要预留 visibility change 记录，用于 trace、retrieval visibility refresh 和后续 purge。

## Module 13: Observability / Trace / Eval Boundary

- [x] Q1. story runtime 第一阶段必须暴露哪些 trace，才能让 eval session 后续接入？
  - Recommended direction: turn material refs、profile snapshot、worker plan、packet summary、retrieval usage、proposal/apply 结果。
  - Confirmed direction: 第一阶段最小 trace 合同包括 `StorySession / BranchHead / Turn` 身份、runtime profile snapshot version、writer packet summary、worker plan + worker execution result、retrieval usage record、proposal / apply 结果、Runtime Workspace 材料生命周期变更。eval session 可按需要在此基础上修改或补充。
- [x] Q2. 本 task 是否完全不做 eval runner，只保证产物可观测？
  - Recommended direction: 是，eval 模块由其他 session 负责。
  - Confirmed direction: 是。eval 模块由其他 session 负责，本任务不实现 eval runner / case / grader，只保证产物可观测和可接入。另需预留开发期 debug 页面，用于查看 Runtime Workspace、worker plan、retrieval usage、proposal/apply、pending 和其他日志，方便人工审核；如果后续 eval 成熟，可减少人工依赖。

## Module 14: Implementation Slice / Current Implementation Migration

- [x] Q1. 第一个代码切片应该先改 OrchestratorPlan/WorkerPlan，还是先改 WritingWorker tool loop？
  - Recommended direction: 先改 worker/scheduler/context 合同，再接 writer tool loop；否则 writer 检索会缺 Runtime Workspace 和 post-write 承接。
  - Confirmed direction: PRD 已覆盖。第一阶段先改 worker/scheduler/context 合同，再接 writer tool loop；否则 writer 检索会缺 Runtime Workspace 和 post-write 承接。
- [x] Q2. 现有 LongformSpecialistService 第一阶段是否作为 LongformMemoryWorker 兼容执行？
  - Recommended direction: 是，避免重写。
  - Confirmed direction: 已被后续 Q4.1 / Q4.2 修正。现有 `LongformSpecialistService` 可以作为 `LongformMemoryWorker` 的参考或 adapter 来源，但不强制兼容执行；若它阻碍新 `WorkerDescriptor / WorkerExecutor / WorkerContextPacket / WorkerResult` 合同，应按新合同重写。
- [x] Q3. 当前 legacy mirror 和正式 Core State store 的关系，第一阶段是否只读写现有兼容层，不扩大耦合？
  - Recommended direction: 是，新增合同尽量指向正式 Store/Broker 口径。
  - Confirmed direction: 是，PRD 已覆盖。第一阶段只读写现有兼容层，新增合同尽量指向正式 Store/Broker 口径。
- [x] Q4. 如果现有 longform MVP 链路阻碍完整 story runtime 合同，第一阶段是否允许从新 runtime 骨架起一条替代实现，而不是继续包旧链路？
  - Recommended direction: 允许，但必须在 spec coding 方案中明确迁移边界、旧链路保留/废弃策略、最小可验证路径和回滚方式。
  - Confirmed direction: 是，PRD 已覆盖。若现有 longform MVP 链路阻碍完整 story runtime 合同，或在旧链路上继续向上搭建的收益低于按新设计重写，第一阶段允许直接以新 runtime 设计链路为主，删除或替换旧 longform fixed chain。旧链路只作为行为参考和迁移参考，不是必须兼容的承载物；实施时仍需明确迁移边界、废弃策略、最小可验证路径和必要回退方式。
- [x] Q4.1. 如果新的 runtime 数据模型和旧 longform MVP 数据模型差距较大，是否仍要强行保留旧模型兼容？
  - Recommended direction: 不强行保留。旧模型可以作为迁移参考，但如果它会把新 runtime 继续绑回硬编码、longform-only、非模块化结构，应允许删除或替换。
  - Confirmed direction: 是。旧版本只是简陋 MVP，工程口径和当前设计不一致，可能存在大量硬编码和非模块化设计。若旧数据模型与新 `Turn / BranchHead / RuntimeProfileSnapshot / Runtime Workspace` 主模型差距较大，或兼容旧模型会阻塞新架构，可以删除旧模型或旧链路，按当前设计重写一版 runtime。是否删除由实施时根据真实阻塞、迁移成本、前端引用和数据保留需求判断。
- [x] Q4.2. 如果允许重写 runtime，现有后端 API / 前端调用形状是否仍必须兼容？
  - Recommended direction: 不作为硬约束。可以保留对用户有价值的交互入口和布局参考，但不能为了兼容旧 API / 旧 SSE / 旧状态字段扭曲新 runtime 内部模型。
  - Confirmed direction: 是。完全允许重写，可以当旧后端链路不存在。旧前端布局和交互设计可以作为参考，但旧 API 形状、旧后端 command surface、旧 SSE 字段和旧状态模型都不是必须兼容的约束；若它们阻碍新 runtime 合同，应按新设计重建。
- [x] Q4.3. 第一版新 runtime 的最小可运行闭环是否先聚焦一条 longform writing turn 主链？
  - Recommended direction: 是。第一版先证明 `Turn -> Snapshot -> Context Packet -> Writer Output -> Runtime Workspace -> Post-write Scheduler/Worker -> Projection/View Refresh -> Next Writer Packet` 这条主链成立；其他 longform 完整体验、roleplay、TRPG 先做合同表达和扩展位。
  - Confirmed direction: 可以，但 spec 必须写好。第一版最小闭环是：用户发起一次 longform 写作 turn，系统创建并绑定 `StorySession / BranchHead / Turn / RuntimeProfileSnapshot`，编排 writer packet，writer 输出文本，Runtime Workspace 记录 turn 材料，post-write 触发 Scheduler / Worker 处理本轮材料，优先刷新下一轮 writer 需要的 Core State 当前视图 / projection block views，下一轮 writer packet 能读取新视图和近几轮原文窗口。未进入第一闭环的能力必须保持合同可表达，不允许写成长文专用硬编码。
- [x] Q5. 完成 grill 清单后，是否需要对 LangGraph rollback / branch / checkpoint / fork 能力做专项技术调研，再决定本项目第一阶段实际能做多少？
  - Recommended direction: 需要。分支 / 回退能力优先依赖 LangGraph 现有实现；专项调研要验证框架能支持哪些预期效果，哪些需要暂缓，避免把工作区 / 存储区状态做乱。
  - Confirmed direction: 需要，作为实施前置。专项调研要重点验证当前项目接法下的 checkpoint、replay、fork、切回旧 checkpoint 后继续、外部存储同步边界；验证不了或框架不支持的能力第一阶段暂缓。
- [x] Q6. 第一阶段 runtime 实施是否只做分支 / 回退合同预留，不做完整分支 UI 和物理删除？
  - Recommended direction: 是。合同里保留 `BranchHead / Turn / profile snapshot`、visibility、trace、workspace 归属；完整分支 UI、分支删除物理 purge、跨分支 Evolution 管理先不做。
  - Confirmed direction: 是。
- [x] Q7. 进入 spec coding 方案前，是否冻结第一阶段实现顺序为三段？
  - Recommended direction: 是。第一段 memory/runtime identity + worker/scheduler/context 合同；第二段建立 longform writing turn 最小闭环，并按价值选择旧 service adapter 或新实现；第三段 writer-side retrieval + Runtime Workspace usage record + post-write trigger。
  - Confirmed direction: 是。该顺序已被后续“允许重写 runtime”的口径修正为 runtime-first rebuild with selective reuse，不强制把现有 longform 链路接入。
- [x] Q8. 第一版验收是否以 longform 可运行为主，但合同必须能表达 roleplay / trpg？
  - Recommended direction: 是。实际行为 longform-first；但 ModeProfile、domain registry、worker catalog、packet policy、Runtime Workspace material type 不能写死成长文专用。
  - Confirmed direction: 是。必须模块化、解耦化、高可维护，尽量避免硬编码；worker 设计要可装卸、可替换，而不是硬绑在一起。

## Module 15: Implementation Preflight / Spec Coding Readiness

- [x] Q1. 第一版 longform 章节生命周期是否冻结为“章节进入 summary -> 章节大纲 -> 用户确认/头脑风暴 -> 写作/重写 -> 接受后 post-write 维护”？
  - Recommended direction: 是。这条要作为 longform runtime 的主流程骨架；细节 UI 可后续迭代，但 runtime 合同要先固定。
  - Confirmed direction: 是。
- [x] Q2. review overlay / 修订批注系统是否采用同一个 turn material sidecar 语义，覆盖 setup draft 编辑和 longform runtime 修订？
  - Recommended direction: 是。不要 setup 一套、longform 一套；应共享 revision / comment overlay envelope，只是入口和触发不同。
  - Confirmed direction: 是，UI 上可以有差异，但后端功能走同一套。
- [x] Q3. WritingWorker 的 `brainstorm` 和 `writing/rewrite` 是否是同一 worker 的两种 operation mode，而不是拆成两个 worker？
  - Recommended direction: 是。统一 writer worker + operation mode；brainstorm 走讨论输出，不进入 accepted prose；writing / rewrite 才产出 draft artifact。
  - Confirmed direction: 是。但这里不是“用户手动切换 writer 模式”的设计。`brainstorm` 由讨论区交互触发；`writing/rewrite` 由产出区的明确动作触发，例如“同意 / 重写”，并且重写时可携带用户修订内容。UI 入口不同，但后端仍是同一 WritingWorker、同一基础上下文和同一治理链。头脑风暴的有效结果目标是命中对应 `Core State` block，但 brainstorm 不直接提出 block proposal，而是先产出面向调度器的 change summary，并在提交前给用户审阅和编辑；用户确认后，再触发一次专门的 worker 调度去修改对应 block。
- [x] Q4. worker registry 第一版是否必须有一组 contract tests，证明新增 / 禁用 worker 不需要改 scheduler 主逻辑？
  - Recommended direction: 是。这是防止“伪 registry、真硬编码”的关键验收。
  - Confirmed direction: 是。
- [x] Q4.1. brainstorm / discussion 的结果，是否应先形成给调度器的 summary，而不是直接形成 block proposal？
  - Recommended direction: 是。brainstorm writer 负责讨论和总结 change intent，不直接改 memory；用户先审阅 / 编辑 summary，确认后再触发调度器派发对应 worker 修改 block。
  - Confirmed direction: 是。brainstorm 只负责把讨论结果总结成条目，不负责 block 路由，也不负责 worker 路由。
- [x] Q4.2. 用户确认 discussion 结论后，这次“应用到 block”的调度是否必须在下一次写作前完成？
  - Recommended direction: 是。既然用户已经确认改大纲 / 设定，下一次正文必须基于更新后的 core。
  - Confirmed direction: 是。longform 允许“时间换质量”。
- [x] Q4.3. discussion 生成但未确认的 summary / proposal，若用户进入下一段 / 下一章 / 继续写作，是否自动失效？
  - Recommended direction: 是，先用一刀切规则。未确认就继续写作，则自动 stale。
  - Confirmed direction: 是。
- [x] Q4.4. discussion summary 的用户确认是否支持部分确认，而不是只能整份通过？
  - Recommended direction: 支持部分确认。summary 里可有多条 block 级修改意图，用户可以逐条确认、编辑或拒绝，调度器只处理确认后的那部分。
  - Confirmed direction: 是。
- [x] Q4.5. brainstorm 产出的讨论结果条目，第一版是否应带少量固定类型？
  - Recommended direction: 要，但只做少量固定类型，例如设定修改 / 大纲修改 / 章节目标修改 / 伏笔修改 / 开放想法。
  - Confirmed direction: 是。
- [x] Q4.6. brainstorm 产出的条目，第一版是否应使用稳定编号，且尽量输出确定性清晰描述？
  - Recommended direction: 要。条目用本轮短编号或顺序号即可，避免随机字符串；描述应尽量确定性、清晰、可编辑。
  - Confirmed direction: 是。
- [x] Q4.7. brainstorm 条目在用户审阅阶段，第一版支持哪些操作？
  - Recommended direction: 只支持编辑、拒绝；暂不支持用户手动新增条目。点击 `apply` 后，所有未拒绝条目整体交付调度层。
  - Confirmed direction: 是。
- [x] Q4.8. brainstorm summary 的最小数据结构是否现在冻结？
  - Recommended direction: 是。第一版只冻结最小集合，例如稳定编号、轻量类型、条目文本、拒绝状态、用户编辑后的最终文本。
  - Confirmed direction: 是。UI 上编辑直接在条目上原地修改；拒绝的条目以划掉态显示。
- [x] Q5. LangGraph branch / rollback 专项调研的交付物是否必须包含当前项目接法下的可行 / 不可行矩阵？
  - Recommended direction: 是。至少列 checkpoint、replay、fork、从旧 checkpoint 继续、外部 memory/text/workspace 同步这几项；不可行的第一阶段暂缓。
  - Confirmed direction: 是。
- [x] Q6. 下一章节的章间承接材料，第一版是否冻结为“单一 provider 接口 + 默认实现返回 accepted outline / chapter goal，不额外做 compact”？
  - Recommended direction: 是。先把章间承接材料做成可替换接口位，当前默认实现直接返回 accepted outline / chapter goal；后续如果 eval 不佳，再增加 compact 模块替换实现，不改主流程。
  - Confirmed direction: 是。

## Module 16: Residual Spec-Coding Ambiguities

- [x] Q1. longform 讨论入口的后端命令面，第一阶段是否接受复用 `DISCUSS_OUTLINE`，把它先当作通用 `brainstorm/discussion` 入口？
  - Recommended direction: 已修正。旧命令可以作为产品语义参考，但不应作为必须兼容的后端约束。
  - Confirmed direction: 已被后续 Q4.2 修正。旧 command surface 不作为硬约束，`DISCUSS_OUTLINE` 只能作为产品语义参考；若旧命令面阻碍新 runtime 合同，应按新 command surface 重建。
- [x] Q2. Runtime Workspace 在进入真正 story runtime 开发时，是否必须从当前 in-process store 升级到持久化存储？
  - Recommended direction: 必须最终升级，并应优先纳入 story runtime 或 memory 补强前置切片。否则会直接限制 writer retrieval 跨请求可靠性、debug 页面价值、pending/post-write 可追溯性，以及后续 branch/rollback 衔接。
  - Confirmed direction: 必须升级。这里的“当前 in-process store”明确指 `RuntimeWorkspaceMaterialService` 内部的 `RuntimeWorkspaceMaterialStore` 进程内字典存储；它只能作为过渡实现，不能作为 story runtime 正式底座。

## Module 17: Module Detail Grill Queue

- [x] Q1. `Turn` 是否要在第一阶段就成为独立持久化实体，而不是继续把“本轮”拆散在 artifact / discussion / graph checkpoint 里？
  - Recommended direction: 要。没有一等 `Turn`，Runtime Workspace、proposal/apply、retrieval usage、rollback、branch visibility、debug trace 都会继续缺统一锚点。
  - Confirmed direction: 要。`Turn` 第一阶段就应成为独立持久化实体；其分配、编号、身份绑定和生命周期推进都由确定性逻辑实现，不由 LLM 决定。artifact、discussion、review overlay、retrieval usage、worker candidate、packet refs、post-write trace 都应作为该 `Turn` 的子材料或关联材料，而不是继续散落在多套主记录里。
- [x] Q2. `RuntimeProfileSnapshot` 是否要在第一阶段就成为独立持久化实体，而不是继续挂在 `StorySession.runtime_story_config_json` 里做动态读取？
  - Recommended direction: 要。当前 story-scoped 最新配置读取无法满足“turn start pin + immutable snapshot + replay/audit”要求。
  - Confirmed direction: 要。`RuntimeProfileSnapshot` 第一阶段就应成为独立持久化实体；turn 开始时确定性地绑定 snapshot，运行中不跟随配置热更新漂移。`StorySession.runtime_story_config_json` 可以继续作为兼容入口或草稿来源，但不能继续充当 active runtime 的真实执行配置源。
- [x] Q3. longform 的 `discussion / review / writing` 是否要统一挂到同一 `StoryTurnRecord.turn_kind` 主记录之下，再由 artifact / overlay / workspace refs 作为子材料，而不是继续维持“两套主记录”？
  - Recommended direction: 要。统一 turn 主记录更符合新 runtime；artifact、review overlay、discussion summary、writer retrieval materials 都应成为 turn 的子材料。
  - Confirmed direction: 要。longform 的 `discussion / review / writing` 都统一挂到同一 `StoryTurnRecord` 主记录之下，通过 `turn_kind` 区分具体行为。artifact、review overlay、discussion summary、retrieval cards、worker trace、workspace refs 都作为该 turn 的子材料，而不是继续维持多套平行主记录。
- [x] Q3.1. review overlay、brainstorm summary、rewrite 采用结果、retrieval materials 等是否继续统一挂在 `Turn` 之下，而不是再长一套平行主记录？
  - Recommended direction: 是。允许有各自的记录类型，但都只作为 `Turn` 的子材料或关联记录，不形成新的主时间线。
  - Confirmed direction: 是。`Turn` 继续是唯一主锚点；review overlay、brainstorm change summary、brainstorm apply receipt、rewrite 候选与确定版本选择结果、retrieval cards / usage、worker trace、proposal/apply receipts 都统一从 `Turn` 归属和追溯，不再长成平行主记录系统。
- [x] Q4. `BranchHead` 是否也要在第一阶段就成为独立持久化实体，而不是先假装永远只有一条主线，等分支功能来了再补？
  - Recommended direction: 要。即使第一阶段不做完整分支 UI，`BranchHead` 也应先成为正式持久化实体，并默认只有一条 active 分支。否则 `Turn`、Runtime Workspace、rollback、未来 fork 都会继续挂在 session 上，后面很难无痛补齐。
  - Confirmed direction: 要。`BranchHead` 第一阶段就成为独立持久化实体；即使产品层暂时只有一条默认 active 分支，底层也按 branch-aware 方式建模，避免 turn、workspace、rollback 和 retrieval visibility 继续硬绑到 session。
- [x] Q5. longform 里的“接受并继续”这类**纯确定性动作**，是否也要形成一条正式 `Turn` 记录，而不是只改状态不留单独轮次？
  - Recommended direction: 要。凡是会改变当前故事线可见状态、推进章节/段落生命周期、影响回退/审计/trace 的动作，都应成为正式 turn；只是不需要走 LLM 生成链，而是走 deterministic turn kind。
  - Confirmed direction: 要。`Turn` 不是“必须有一次 LLM 文本生成”，而是“一次正式的故事线推进事件”。因此 `accept_and_continue`、`complete_chapter` 这类纯确定性动作也要形成正式 `Turn` 记录，只是它们属于 deterministic turn kind，而不是 writer generation turn。
- [x] Q6. roleplay / trpg 中“用户下一条消息就是上一轮 acceptance signal”这一规则，是否需要单独生成一条 `accept_transition` turn，还是直接在创建新 user-input turn 时顺手把上一轮标记为 accepted？
  - Recommended direction: 不单独再造一条 accept turn。创建新 user-input turn 时，以确定性逻辑顺手完成“上一轮 accepted / settled”的状态推进，避免 turn 膨胀。
  - Confirmed direction: 不单独生成 `accept_transition` turn。创建新 user-input turn 时，由确定性逻辑顺手把上一轮标记为 accepted / settled，并把这次 acceptance 作为该新 turn 的状态推进一部分记录下来。
- [x] Q7. branch/fork 是否只允许从 **settled turn** 派生，而不允许直接从 longform 未接受 draft、未确认 discussion summary、或 pending post-write 状态上分叉？
  - Recommended direction: 是。默认只允许从 settled turn 派生 branch。未接受 draft、未确认 summary、pending worker candidate、未完成 post-write 结果都只作为 branch-local 辅助材料存在，不应直接成为正式 fork base。
  - Confirmed direction: 是。正式 branch/fork 只允许从 settled turn 派生。未接受 draft、未确认 summary、pending worker candidate、未完成 post-write 结果都不作为正式 fork base，只能作为 branch-local 辅助材料存在。
- [x] Q8. 如果 runtime 配置在上一轮 post-write 还没跑完时被用户热更新，旧的 pending job 应该继续使用旧 snapshot 跑完，还是被强制迁移到新 snapshot？
  - Recommended direction: 继续使用旧 snapshot。任何已开始的 turn / pending post-write job 都绑定产生它的 snapshot，不做中途迁移；新 snapshot 只影响之后新开的 turn。
  - Confirmed direction: 继续使用旧 snapshot。任何已开始的 turn / pending post-write job 都绑定创建它时的 snapshot，不做中途迁移；新 snapshot 只影响之后新开的 turn。

## Module 18: Turn Settling / Direct Edit / Control History

- [x] Q1. `settled turn` 的判定要不要在第一阶段就冻结成确定性规则？
  - Recommended direction: 要。否则 branch/fork、rollback、acceptance、pending job 清理都没有稳定锚点。建议：当该 turn 的 acceptance 条件满足，且该 turn 的必需 post-write 结果已经完成、被跳过、或被显式标记为 pending-deferred 时，才可判定为 settled。
  - Confirmed direction: 要。`settled turn` 第一阶段就采用确定性判定规则：当该 turn 的 acceptance 条件满足，且该 turn 的必需 post-write 结果已经完成、被跳过、或被显式标记为 `pending-deferred` 时，才判定为 settled。
- [x] Q2. 用户直接修改 `Core State` 或应用一批 Story Evolution 结果后，是否要求同步刷新当前视图 / projection，而不是等下一次 worker 调度再慢慢补？
  - Recommended direction: 要。用户显式修改是最高优先级，系统应在该 deterministic turn 内同步刷新受影响的 view / projection，至少保证 UI 与下一轮 writer 输入不会继续看到旧事实。
  - Confirmed direction: 原则上要，但要修正适用边界。`Story Evolution` 主要针对 `Archival Knowledge` 的设定补充、修改、增加，不是 `Core State` 的主修改路径。`Core State` 的主修改路径是：用户手动修改、调度器自动维护、brainstorm 流程修改。对这些 `Core State` 改动，系统应同步刷新受影响的 view / projection，避免 UI 与下一轮 writer 继续看到旧事实；但用户手动修改 `Core State` 不单独形成 story turn。它应作为当前 `StorySession / BranchHead` 下、两次可视对话轮次之间的一次受治理状态变化被记录，并在回退时归入“目标 Turn 完成后的最终状态”。用户在自己确定的情况下手动修改 `Core State`，风险由用户自行承担，系统提供 rewrite / rollback / revision 冲突检查 / trace 作为兜底。
- [x] Q3. runtime 配置热更新、worker 权限调整、snapshot 发布，这类“控制面”变化，是否应存成独立的 control history，而不是 story turn？
  - Recommended direction: 是。它们影响运行规则，但不属于故事线推进本身。应有独立的 config/control history，并和 `RuntimeProfileSnapshot` 建立引用关系；story turn 只引用生效时所绑定的 snapshot。
  - Confirmed direction: 是。配置侧不进入 story turn，也不参与 story rollback。运行配置、worker 权限、snapshot 发布与启用应进入独立 control history；前端上，这类配置统一放在单独页面内，该页面内配置不受故事线回溯影响。
- [x] Q4. 用户手动修改 `Core State` 后，视图刷新范围第一阶段是否只刷新“受影响的 projection slot / block view”，而不是每次都全量重算整个 projection？
  - Recommended direction: 是。第一阶段优先按受影响 slot / block view 精准刷新；只有当依赖分析不清晰或 dirty 范围过大时，才退化为全量重算。
  - Confirmed direction: 是。第一阶段优先按受影响 slot / block view 精准刷新；只有当依赖分析不清晰或 dirty 范围过大时，才退化为全量重算整个 projection。
- [x] Q5. 用户手动修改 `Core State` 时，如果后台已有 pending worker candidate / pending post-write，第一阶段是否只失效“命中的相关候选”，而不是粗暴取消整批后台任务？
  - Recommended direction: 是。优先基于 affected domain / block / base revision 只失效相关候选；只有当依赖关系无法确定时，才允许升级为整批 pending 标脏并重算。
  - Confirmed direction: 是。优先基于 affected domain / block / base revision 只失效相关候选；只有当依赖关系无法确定时，才允许升级为整批 pending 标脏并重算。并且这主要是用户体验问题：用户完全可以先中止任务再去改，也可以修改后直接 rewrite，因此系统不必为了保护后台任务而过度阻塞用户编辑。

## Module 19: Runtime Config Surface

- [x] Q1. “配置侧”是否明确指“改变系统怎么跑”，而不是“改变故事发生了什么”？
  - Recommended direction: 是。凡是修改后改变的是 worker、调度、模型、retrieval、上下文编排、预算、权限等运行规则，而不是 Core State / Recall / Archival / artifact / branch line 本身，都属于配置侧。
  - Confirmed direction: 是。配置侧的变化不进入 story turn，不参与 story rollback，统一进入独立 control history，并通过 `RuntimeProfileSnapshot` 对后续 turn 生效。
- [x] Q2. 运行时可随时修改的配置，是否主要包括调度频率、worker 启停与权限、provider/model 选择、retrieval 配置、上下文窗口与预算等？
  - Recommended direction: 是。优先开放这类“改变系统怎么跑”的运行时配置，并统一放进独立页面；修改后发布新 snapshot，从下一轮生效。
  - Confirmed direction: 是。运行时可随时调整的配置主要包括：调度频率、worker 启用/禁用、worker 权限 level、writer/worker/retrieval 的 provider-model 选择、retrieval rerank / graph extraction 配置、上下文窗口大小、packet/token budget、manual refresh / trigger 策略等；这些统一归入独立配置页面，不受故事线回溯影响。

## Module 20: Roleplay / TRPG Message Tree And Branch Contract

- [x] Q1. RP / TRPG 的“重试/切换候选回复”，到底只是同一轮里的候选切换，还是要直接长成正式分支？
  - Why it matters: 这决定消息树是“轻量候选树”还是“真正带 memory / rollback / branch 语义的故事树”。如果不先定清楚，后面 `Turn`、`BranchHead`、回退和 UI 都会混。
  - Recommended direction: 当前设计不采用“同一 Turn 候选切换”这条路。RP/TRPG 单个 `Turn` 只保留当前正式可见结果；若要改写未来，必须手动从历史消息创建正式分支。
  - Confirmed direction: 是。按照当前设计，同一个 `Turn` 中不会出现其他候选，只有手动触发的分支；因此 RP/TRPG 的核心结构是 branch/rollback tree，而不是同 turn candidate tree。

- [x] Q2. 当某一 `Turn` 产出分支时，分支锚点应当落在“该 turn 开始前的状态”，还是“该 turn 结束后的状态”？
  - Why it matters: 这决定 fork 后继承的是上一轮 settled state，还是把当前 turn 的输出一并算作分支基底，也会影响前端“从这里分支”按钮的直觉和后端恢复逻辑。
  - Recommended direction: 以“该 turn 开始前，也就是上一 turn 结束后”的状态作为分支锚点，更符合直觉，也更容易和 settled-turn / branch-head 恢复逻辑对齐。
  - Confirmed direction: 是。当前冻结为“以该 turn 开始前、也就是上一 turn 结束后的 settled 状态作为分支锚点”。这意味着在某个历史 turn 上手动创建分支，本质上是“从这一轮开始改写未来”，而不是“保留这一轮并从下一轮开始改写未来”。

- [x] Q3. RP / TRPG 的消息树，产品上最小需要暴露到什么粒度：只显示 turn 级节点，还是还要显示额外树杈节点？
  - Why it matters: 这决定第一版前端树控件和 branch 入口复杂度。若一开始把主聊天流画成重树状，前端和状态管理都会明显变厚。
  - Recommended direction: 第一版主聊天流保持当前 active branch 的线性 `Turn` 列表；分支信息单独放到 branch 入口 / 面板中，只先把“从这里分支”的入口做出来，后续再做更重的树形设计和优化。
  - Confirmed direction: 是。第一版只做 branch 入口和最小 branch 面板，不在主聊天流里直接渲染复杂树杈；后续再做专门的树形设计与优化。

- [x] Q4. RP / TRPG 的“回退”与“切分支”在产品语义上是否必须强区分？
  - Why it matters: 这决定用户操作后旧未来是“隐藏失效”还是“保留为另一个未来”。如果语义不分清，后端会把 rollback 和 fork 做成一团。
  - Recommended direction: 必须强区分。`rollback` 是当前分支回到旧 `Turn`，之后内容对当前主线失效；`fork/branch` 是保留旧未来，同时从旧 `Turn` 派生新未来。
  - Confirmed direction: 是。第一版产品动作就必须明确区分 `回退到这里` 和 `从这里分支`，不能混成一个模糊的“从这里继续”按钮。

- [x] Q5. RP / TRPG 第一版是否需要额外记录“查看/尝试/切换”这类非状态变更历史？
  - Why it matters: 要判断哪些留痕真有工程价值，哪些只是额外工序和噪音。
  - Recommended direction: 不需要额外做。第一版只保留真正改变状态的正式动作记录，例如 `fork created`、`branch switched`、`rollback applied`。像“看过哪条分支”“点开过哪个历史消息”“准备分支但取消了”这类不改变 story state 的浏览/尝试行为，不单独入 trace。
  - Confirmed direction: 是。第一版不额外记录浏览/尝试类历史；现有正式动作 receipts 和 job/event trace 已足够支撑 debug、恢复和审计。

## Module 21: Branch Operation Semantics

- [x] Q1. 用户在历史消息上点击“从这里分支”后，系统是否应立即切换到新分支？
  - Why it matters: 这决定前端交互和 runtime active branch 的切换时机。如果创建后不自动切过去，用户还停留在旧分支继续输入，很容易把“我以为正在新线写作”和“实际还在旧线”混在一起。
  - Recommended direction: 默认立即切换到新分支。创建分支本身就是一次明确的“我要从这里改写未来”动作；保留旧分支作为历史线，但当前活跃上下文、后续输入和 writer packet 都切到新 branch。
  - Confirmed direction: 是。创建分支后立即切换到新 branch；主聊天区只保留当前 active branch 的线性历史，fork 点之后原路径的后续消息从主视图消失。第一版前端只做轻量 branch UX：消息级 `从这里分支` 入口、顶部当前分支标识、fork 点提示条、最小 branch 面板；不在主聊天流里直接做重树状图。

- [x] Q2. `fork created` / `branch switched` 这类分支操作，本身是否应算作新的 story turn？
  - Why it matters: 这会直接影响 `Turn` 模型、回退锚点、branch receipts 和前端“当前线变化但正文没变”的处理方式。如果把分支切换也做成 turn，产品时间线会混入大量非正文动作；如果不做成 turn，就需要独立的 control/receipt 记录。
  - Recommended direction: 不算 story turn。`fork created`、`branch switched`、`branch deleted` 属于 branch control actions，应写 branch/control receipts 和 trace，但不创建新的 `Turn`，也不成为正文回退锚点。
  - Confirmed direction: 是。分支创建、切换、删除都不算新的 story turn；它们属于 branch/control actions，只写 branch/control receipts 与必要 trace，不进入正文时间线，也不成为正文回退锚点。

## Module 22: Longform Revision / Rewrite Scope

- [x] Q1. longform 的 `discussion / brainstorm` 是否与 `review overlay / 修订 -> rewrite` 严格分流？
  - Recommended direction: 是。discussion 只承接用户不确定、想讨论、想改设定/方向的内容；明确段落修改要求走 review overlay / tracked changes / comments，再进入 rewrite。
  - Confirmed direction: 是。`discussion` 只服务 writer brainstorm；明确修订/批注不进入 discussion，而是进入 `review overlay -> rewrite`。

- [x] Q2. longform 修订前端第一阶段是否冻结为 `viewing / editing / suggesting` 三态？
  - Recommended direction: 是。`viewing` 只读，`editing` 表示用户自己改稿不默认形成 LLM 修订指令，`suggesting` 表示 tracked changes / comments 进入 review overlay 供 rewrite 消费。
  - Confirmed direction: 是。longform 修订前端第一阶段冻结为 `viewing / editing / suggesting` 三态，风格尽量靠近 Word / SuperDoc，但仅保留修订/批注相关功能。

- [x] Q3. longform draft 的 adoption 是否只在用户点击 `accept_and_continue / 续写` 时正式发生？
  - Recommended direction: 是。selection 只是暂定状态，adoption 只在继续写作动作发生时确认。
  - Confirmed direction: 是。只有点击 `accept_and_continue / 续写` 时，当前被选中的 draft 才正式成为 canonical continuation base；当前 selection 可变、可解除，不等于 adoption。

- [ ] Q4. 第一阶段 `rewrite` 是否只保留两种语义：`full rewrite` 与 `paragraph rewrite`？
  - Why it matters: 这决定产品动作数量、packet 组织方式和后端实现复杂度。如果分类过多，容易把 rewrite 流程做成到处散落的 if/else。
  - Recommended direction: 是。第一阶段只保留 `full rewrite` 与 `paragraph rewrite` 两种语义：`full rewrite` 用于整篇改写，`paragraph rewrite` 用于局部 block 重写。`full rewrite` 内部再区分两种输入形态：仅有全文批注时允许携带旧正文全文；存在明确全文要求时不携带旧正文全文。

- [ ] Q5. `full rewrite` 与 `paragraph rewrite` 的正式触发入口是否要在 UI 上显式区分？
  - Why it matters: 如果入口不清楚，用户很难知道这次重写会作用于整篇还是局部；如果入口过多，又会使 longform 动作面膨胀。
  - Recommended direction: 第一阶段显式区分。普通 `rewrite` 默认表示“按当前 review overlay 做 paragraph rewrite”；另给一个明确的“带要求 rewrite”或等价入口，表示全文重写。

- [ ] Q6. 当局部修订很多、几乎覆盖全篇时，第一阶段是否仍坚持按 `paragraph rewrite` 处理，而不是自动升级为 `full rewrite`？
  - Why it matters: 自动升级能减少 packet 膨胀，但会引入隐藏规则；坚持局部 rewrite 则实现更直白，但可能在大批量修订时变重。
  - Recommended direction: 第一阶段先不做自动升级。是否全文 rewrite 只由用户显式入口决定，避免出现难解释的隐式切换。

- [ ] Q7. `paragraph rewrite` 是一次性处理当前轮所有局部修订，还是允许一轮里分多次局部 rewrite？
  - Why it matters: 这决定 turn 语义、candidate 数量和上下文组织。分多次会让同轮候选树和 overlay 生命周期迅速变复杂。
  - Recommended direction: 第一阶段按“一次性处理当前轮所有已选局部修订”为一轮 paragraph rewrite，不在同一轮里再拆多次局部 rewrite。

- [ ] Q8. `paragraph rewrite` 给 writer 的上下文，第一阶段是“只发被命中的段落”，还是“命中段落 + 前后窗口 + 全局 rewrite 要求”？
  - Why it matters: 只发命中段落容易丢过渡和语气；发整篇又违背局部 rewrite 的控域目标。
  - Recommended direction: 发送“命中段落 + 有限前后窗口 + 全局 rewrite 要求 + 对应 review overlay annotations”，不直接发整篇旧正文。

- [x] Q9. 修订模块是否以 SuperDoc/Word 能力为 substrate，只聚焦“把修订内容传给 writer”，而不重造整套文档编辑语义？
  - Recommended direction: 是。优先借用 SuperDoc/Word 已成熟的修订、批注、tracked changes、selection、block/range 锚点能力；只要不与本 task 需求冲突，就直接参考其行为。
  - Confirmed direction: 是。修订模块的重点是需求功能：将修订内容传递给 writer。SuperDoc 作为修订交互 substrate，其他行为若与需求不冲突，可直接参考；发生冲突时，以当前 task 文档和讨论结论为准。

- [x] Q10. comment 在 rewrite 生成新 candidate 后，第一阶段是否默认保留并由用户手动 resolve，而不是系统自动 resolve？
  - Recommended direction: 是。自动判断“已经满足批注”会过早替用户做主观决定；更稳的语义是保持 comment active，等待用户显式 resolve。
  - Confirmed direction: 是。rewrite 后 comment 默认继续保留，不自动删除、不自动 resolve；resolved comment 从主修订视图收起，但保留留痕、锚点和 provenance。
