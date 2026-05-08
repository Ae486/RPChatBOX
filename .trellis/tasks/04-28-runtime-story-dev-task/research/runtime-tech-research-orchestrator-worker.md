# Research: runtime-tech-research-orchestrator-worker

- Query: 对 story runtime 的 orchestrator / scheduler / worker 架构做技术调研，结合当前 task spec、已有 research、本地 `how-claude-code-works-main` 材料，以及 Anthropic / OpenAI 官方模式，判断当前项目应采用的职责边界与可借用模式。
- Scope: mixed
- Date: 2026-05-07

## Findings

### 1. 结论先说：当前“重 workflow，轻 agent”方向是对的，而且对当前项目几乎是唯一合理路线

结论：**正确，而且应继续收紧。**

原因不是抽象偏好，而是当前项目的真实约束决定了这件事：

1. 当前 story runtime 已经不是“从零拼一个 agent demo”。
   - 它已经有 `StorySession / BranchHead / Turn / RuntimeProfileSnapshot` 这套 runtime 身份和生命周期目标，见 [prd.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/prd.md) 与 [story-runtime-development-master-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-development-master-spec.md)。
   - 它还已经有自己的 Memory OS、proposal/apply、retrieval、runtime workspace、projection/view 刷新语义。这里的核心难题不是“让模型会调工具”，而是“让 story truth、worker 权限、分支/回退、post-write 治理可控”。

2. 当前代码链本身已经证明：真正需要重构的是 workflow 主链，而不是再包一层 agent runtime。
   - 现在的执行链仍是固定顺序：`orchestrator_plan -> specialist_analyze -> build_packet -> writer_run -> persist_generated_artifact -> post_write_regression`，见 [story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py:148)、[story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py:164)、[story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py:187)、[story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py:206)、[story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py:256)。
   - `post_write_regression` 现在还是 `skipped`，说明问题不在“agent 不够智能”，而在 workflow 主链还没有把 post-write worker/scheduler 变成正式合同。
   - `StoryTurnDomainService` 也是直接把 orchestrator、specialist、writer、artifact persistence 串成固定流程，见 [story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py:131)、[story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py:158)、[story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py:235)、[story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py:309)、[story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py:336)。

3. Anthropic 官方模式与当前设计方向一致，而且指向的是“先 workflow，后 agent autonomy”。
   - Anthropic 把 workflow 定义为“LLM 和工具沿预定义代码路径编排”，把 agents 定义为“LLM 动态控制自己的流程和工具”，并明确建议先找最简单可行方案，再增加复杂度。
   - 它把 orchestrator-workers 定位为“子任务结构不可预先写死时”的 workflow 模式，而不是要求你引入更重框架或更自治的 agent runtime。
   - 对当前项目来说，story turn 主链、post-write、proposal/apply、projection refresh、branch/rollback、writer packet 这些都必须是**代码主权**，不该让 LLM 自治 loop 反客为主。

4. OpenAI 官方最新 agents 文档也在给同一个信号。
   - 官方把第一设计问题定义为“谁拥有最终用户回复的所有权”。
   - handoff 适合 specialist 接管会话；agents-as-tools 适合 manager 保持主权，把 specialist 当 bounded capability。
   - 当前 story runtime 明显属于后者：最终用户可见产出只能由 `WritingWorker` 负责，memory workers 不应接管对话主权。

因此，对当前项目更准确的说法不是泛泛的“轻 agent”，而是：

- **重 deterministic workflow / runtime contracts**
- **轻会话主权转移**
- **把 LLM specialist 限制为 proposal / digest / bounded analysis producer**
- **把 story truth、worker enable/disable、权限、budget、phase、post-write 触发，全都留在代码侧**

这和现有 spec 是一致的，也和当前代码现状的缺口正好对齐。

### 2. 当前项目里 scheduler / orchestrator / worker 的最合理职责边界

#### 2.1 Scheduler：唯一 workflow 裁决者

Scheduler 在当前项目里应当是最强主权层，职责应冻结为：

1. 读取 runtime identity 与 active snapshot。
2. 读取 worker registry / activation / permission / phase policy。
3. 决定本轮是否需要请求 orchestrator proposal。
4. 校验 orchestrator proposal。
5. 生成最终 `WorkerExecutionPlan`。
6. 决定 worker 执行、跳过、降级、延后、async/pending。
7. 在 post-write 阶段决定是否重新调度 maintenance workers。

这部分已经在 spec 明确得比较对，见 [story-runtime-worker-scheduler-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-worker-scheduler-spec.md)：

- orchestrator 只提案，scheduler 裁决，见该文档“7.2 Orchestrator 与 Scheduler 边界”
- fallback 必须 deterministic，见“7.3 Deterministic fallback”
- scheduler 不允许硬编码 worker 名称，见“6.2 Scheduler 不允许硬编码”

对当前实现的直接修正点：

- 现在 `story_graph_nodes.py` 里并不存在独立 scheduler node；`orchestrator_plan` 后面直接进 `specialist_analyze`，说明“LLM 提案 -> 程序裁决”这一步还没真正落地。
- 这意味着下一阶段不该继续给 `LongformOrchestratorService` 加更多输出字段来假装扩展，而是应该先把 `WorkerExecutionPlan` 变成主链真相。

#### 2.2 Orchestrator：只负责语义提案，不负责执行裁决

Orchestrator 在当前项目里最合理的职责是：

1. 根据当前 turn、mode、phase、user input、runtime signals，提出候选 worker。
2. 提出 context 需求和建议原因。
3. 提出 must-run / allow-degrade / budget hint / phase hint。
4. 输出严格结构化 plan。

它**不负责**：

- 直接调用 worker
- 决定 worker 是否真的启用
- 决定是否越过权限或 budget
- 直接拼 writer packet
- 直接驱动 post-write mutation

当前实现 `LongformOrchestratorService` 的问题不是“存在 LLM orchestrator”，而是它现在仍偏 MVP planner，而不是新合同下的 proposal producer：

- 当前 `plan()` 返回的是旧 `OrchestratorPlan`，核心仍是 `needs_retrieval / archival_queries / recall_queries / specialist_focus / writer_instruction / notes`，见 [longform_orchestrator_service.py](H:/chatboxapp/backend/rp/services/longform_orchestrator_service.py:48)、[longform_orchestrator_service.py](H:/chatboxapp/backend/rp/services/longform_orchestrator_service.py:119)、[longform_orchestrator_service.py](H:/chatboxapp/backend/rp/services/longform_orchestrator_service.py:246)。
- 这更像“planner for one fixed specialist + writer”，还不是对多 worker runtime 的结构化提案。

因此，当前项目中 orchestrator 的正确演化方向是：

- 保留 LLM 作为“语义拆解器”
- 升级输出为 `OrchestratorPlanEnvelope / CandidateWorkerPlan`
- 让它只描述“建议”，不再描述“已经决定”

#### 2.3 Worker：bounded specialist，不是会话主脑

当前项目里 worker 的正确定位不是“一个个独立 agent”，而是：

- 对某些 domain / block / layer 有稳定 ownership
- 拥有自己的输入合同、工具 allowlist、权限上限、输出 schema
- 可由 LLM / deterministic / hybrid executor 实现
- 只在受控 phase 下执行某类分析或维护任务

这与 OpenAI agents 文档里的 “agents as tools” 更接近，而不是 handoff：

- manager 保持主权
- specialist 作为有边界的 capability 被调用
- 只有当“下一步真要让 specialist 拥有最终用户回复”时才该 handoff

当前项目里：

- `LongformMemoryWorker`、未来的 `CharacterMemoryWorker / SceneInteractionWorker / RuleStateWorker / MaintenanceWorker` 都应属于 bounded specialist。
- `WritingWorker` 才是唯一可拥有用户可见输出的 worker。
- 所以这里本质不是“多 agent 对话所有权切换”，而是“一个 runtime workflow 调多个受控 worker”。

这也解释了为什么你现在 spec 中坚持“同一 worker 不按 phase 拆身份”是对的：phase 改的是输入、工具、权限、输出，不该把同一 domain owner 拆成多个伪 agent 身份。

### 3. 哪些模式可直接借用，而且对当前项目有实际价值

#### 3.1 Anthropic 的 workflow pattern 分层，可直接借

最值得借的不是某个 SDK，而是分层思路：

1. **Prompt chaining**
   - 可借到 setup / review / post-write evaluator 这类固定顺序流程。
   - 对当前 story runtime 主链，只适合局部，不适合拿来描述整个 story turn。

2. **Routing**
   - 可借到 mode/profile/command/phase 决策。
   - 当前 `LongformTurnCommandKind`、special commands、不同 post-write policy，本质都适合 deterministic routing，而不是让 LLM 自由决定流程。

3. **Parallelization**
   - 可借到 future post-write fan-out。
   - 但只能用于低耦合、可并发的 maintenance 或 read/search 类工作，不能现在就把所有 worker 并行化。

4. **Orchestrator-workers**
   - 这是最贴近当前项目的主模式。
   - 但必须是“LLM 负责拆解，代码负责裁决与汇总”的版本，而不是“LLM 自治多 agent”版本。

5. **Evaluator-optimizer**
   - 可直接用于 post-write review、quality guard、retrieval sufficiency check、summary/refinement 这类有明确评估标准的局部子流程。
   - 不应用来替代主 runtime scheduler。

#### 3.2 OpenAI 的 “agents as tools” 模式，可直接借

这点对当前项目很重要。

OpenAI 官方明确区分：

- `handoffs`: specialist 接管分支的最终对话
- `agents as tools`: manager 保持对最终回复的主权，只把 specialist 当 bounded capability 调用

当前项目的正确映射应是：

- `Scheduler + Graph shell + Turn runtime` = manager
- `OrchestratorWorker` = proposal producer
- `LongformMemoryWorker / CharacterMemoryWorker / SceneInteractionWorker / RuleStateWorker / MaintenanceWorker` = agents as tools / bounded specialists
- `WritingWorker` = final user-visible answer owner

这能直接指导一个关键设计选择：

- **不要让 memory worker handoff 到前台。**
- **不要让 orchestrator handoff 到 writer。**
- **不要让 runtime 在一个 turn 内发生多次对话主权转移。**

否则 trace、turn identity、approval、SSE、packet provenance、post-write 都会被搞乱。

#### 3.3 Claude Code 本地材料里的“主循环与上下文分层”模式，可直接借

本地 `how-claude-code-works-main` 虽然不是 story runtime 文档，但里面有几条模式对当前项目非常有用：

1. **主循环是显式阶段，不是糊成一个大 prompt**
   - `用户输入 -> 上下文组装 -> 模型决策 -> 工具执行 -> 结果注入 -> 继续/停止`，见 [02-agent-loop.md](H:/chatboxapp/docs/research/how-claude-code-works-main/docs/02-agent-loop.md)。
   - 对当前项目的借法：story runtime turn 应继续保持 graph/node/stage 显式化，而不是把 scheduler + worker selection + writer + post-write 塞进一个大 model call。

2. **上下文是 pipeline，不是 dump bucket**
   - 系统上下文、用户上下文、消息历史、压缩、附件都有明确层次，见 [03-context-engineering.md](H:/chatboxapp/docs/research/how-claude-code-works-main/docs/03-context-engineering.md)。
   - 对当前项目的借法：`Context Orchestration Layer` 应明确分 worker packet 与 writer packet，避免“全量 state + 全量 retrieval + 全量 workspace 一股脑塞给 writer”。

3. **工具/能力要有稳定接口与默认安全边界**
   - 工具接口、只读/破坏性/并发安全等元数据是显式的，见 [04-tool-system.md](H:/chatboxapp/docs/research/how-claude-code-works-main/docs/04-tool-system.md)。
   - 对当前项目的借法：worker registry / execution policy / permission profile 就应该像 tool descriptor 一样 declarative，而不是 scattered if/else。

4. **按需加载而不是常驻膨胀**
   - Claude Code 的 skills/resources 是 on-demand，而不是永久塞满上下文。
   - 对当前项目的借法：不要把所有 domain worker 的上下文都默认组出来。context packet 应按 worker、phase、plan 组装。

#### 3.4 “runtime context 与 model context 分离”模式，可直接借

OpenAI 官方定义 agents 时明确区分：

- conversation history 是 model sees
- run context 是 runtime code sees

这与当前项目非常贴合：

- `MemoryRuntimeIdentity`、snapshot version、permission profile、branch routing、budget ledger、workspace lifecycle rule，很多都属于 runtime context，不应无脑暴露给模型。
- 模型真正需要看到的是裁剪后的 instructions、selected refs、retrieval cards、projection views、writer hints。

对当前项目的直接设计含义：

- `WorkerContextPacket` 和 `WritingPacket` 都要是“给模型看的上下文”
- scheduler constraints / permission verdict / manifest ledger / retry counters / trace ids 等，多数是“给代码看的上下文”
- 不能因为它们都叫 context，就混在同一个 packet

### 4. 哪些常见框架/抽象反而会拖慢当前项目

#### 4.1 把 OpenAI Agents SDK / Anthropic Agent SDK / Letta runtime 当主 runtime：会拖慢

不是说这些东西没价值，而是**当前项目的主难点不在它们能解决的地方**。

它们擅长解决：

- handoff
- tool loop
- approvals / pauses
- trace
- hosted state / session continuation

而当前项目真正难的是：

- story truth 与 projection 的双层治理
- branch / rollback 与 runtime workspace 的统一回放边界
- post-write maintenance 的 domain ownership
- proposal/apply 与 user-edit 优先级
- writer packet 与 worker packet 的裁剪边界
- runtime profile snapshot pinning

如果现在切到这些 SDK 做主 runtime，代价会是：

1. 需要把现有 `Memory OS / proposal / retrieval / runtime identity / branch rules` 重新适配到它们的会话模型。
2. 会把你当前“需要设计 story runtime contract”的任务，变成“如何把 story runtime 迁进某个 agent SDK”的迁移任务。
3. 很多“主权本应在代码侧”的地方，会被 handoff / session / run loop 语义反客为主。

所以它们最多适合作为参考样本，不适合作为当前主 runtime。

#### 4.2 把 worker 细拆成大量小 agent：会拖慢

OpenAI 官方明确说，只有当 contract、tool surface、policy、ownership 真变了，才值得拆 agent。

当前项目如果过早把 worker 细拆，会带来几类直接成本：

1. 更多 prompt surface
2. 更多 context packet 构建
3. 更多 trace 和评估复杂度
4. 更多 scheduler decision points
5. 更高 turn latency
6. 更难维护 domain ownership 一致性

特别是 interactive mode 里，你已经明确限制“最多一个 blocking analysis LLM worker + 一个 WritingWorker”，这和“先少量 macro worker”完全一致。

所以当前阶段应该坚持：

- domain ownership 优先
- macro worker 优先
- 小能力落到 helper / tool / policy / deterministic service

而不是把每个 block / capability 都 agent 化。

#### 4.3 新增一个常驻“能力层 / meta-orchestrator 层”：会拖慢

当前 spec 已经明确不希望新增独立能力层，这个判断是对的。

原因很具体：

1. worker 已经是 ownership、工具权限、上下文合同、输出合同的聚合点。
2. Context Orchestration Layer 已经是确定性组包层。
3. Scheduler 已经是 deterministic workflow 裁决层。

这三层已经够了。

如果再加一个“能力编排层”或“meta orchestrator”：

- 它会和 scheduler 争裁决权
- 会和 worker catalog 重叠
- 会和 context orchestration 抢“谁决定要给谁上下文”
- 最终让 trace 与调试面更模糊

对当前项目来说，这不是抽象增益，而是额外调度层级和调用成本。

#### 4.4 把上下文编排做成“写前总控预检 agent”：会拖慢

这点和用户此前偏好也一致。

当前项目里，writer-side retrieval 已明确应由 writer 自己在 bounded policy 下判断是否缺信息并发起检索；Context Orchestration Layer 不负责“判断要不要检索”。

如果把 context orchestration 膨胀成一个写前预检 agent，会出现：

- 再多一次模型调用
- 再多一次上下文复制
- 抢走 writer 对“缺不缺信息”的判断
- 让主路径复杂度和成本上升

所以 context orchestration 应保持确定性组包，不升级成新 agent。

### 5. 对当前项目的具体建议：下一步该怎么落

#### 5.1 先把“旧 orchestrator + specialist 固定链”改成“scheduler 主链 + adapter worker”

当前代码最需要的不是再增强 `LongformOrchestratorService` 或 `LongformSpecialistService`，而是：

1. 新建 `WorkerDescriptor / WorkerExecutionPlan / WorkerContextPacket / WorkerResult` 真正进主链。
2. 新建 `WorkerSchedulerService` 作为图里的显式节点或 domain service 主入口。
3. 把 `LongformOrchestratorService` 降级成 `OrchestratorPlanAdapterService` 候选。
4. 把 `LongformSpecialistService` 包成 `LongformMemoryWorkerExecutor` adapter。

否则即便 spec 写得再漂亮，主链仍然是旧 fixed chain。

#### 5.2 把 `StoryGraphNodes` 从“阶段顺序调用器”升级为“runtime workflow shell”

现在 graph 壳子已经有了，但还只是粗粒度 node adapter。

下一阶段它应负责表达：

- pin runtime identity
- select route by command/phase
- invoke scheduler
- execute selected workers
- build writing packet
- run writer
- persist visible artifact
- post-write maintenance scheduling
- finalize turn

这样 LangGraph 才是 workflow shell，而不是旧流程的包装壳。

#### 5.3 `WritingWorker` 保持唯一用户可见输出 owner

OpenAI 官方“先决定谁拥有最终回复”这条，对当前项目很关键。

建议冻结：

- 所有 memory / maintenance / rule / scene / character worker 都不产出最终用户正文
- 只有 `WritingWorker` 产出前台文本
- 其他 worker 只能产出结构化 hints / findings / proposal candidates / projection refresh requests

这样 turn trace、packet provenance、acceptance signal、retrieval usage record 才会稳定。

#### 5.4 将 post-write 真正升级为 runtime 主链，而不是“回归任务”

当前 `post_write_regression` 还是 skipped，说明名字和实现都还停留在 MVP 思维。

建议直接从术语和设计上切换：

- 不再把它理解成 regression 附属维护
- 它就是 active runtime 主链后半段
- 它负责准备 next-turn writer-facing view、proposal/apply、recall/archival maintenance、pending/deferred jobs

这点在当前 spec 已经是对的，缺的是实现落位。

### 6. 最终判断

围绕你要求的四个问题，给一个直接答案：

1. 当前“重 workflow，轻 agent”方向是否正确？
   - **正确。**
   - 更准确地说，应是“重 deterministic workflow、轻会话主权转移、轻框架自治、重 contract 和 runtime governance”。

2. scheduler / orchestrator / worker 最合理的职责边界？
   - **Scheduler**：唯一 workflow 裁决者，拥有执行主权。
   - **Orchestrator**：只做结构化提案，不做裁决，不做执行主权拥有者。
   - **Worker**：bounded specialist，按 domain ownership 承担分析/维护任务；除 `WritingWorker` 外，不拥有最终用户回复。

3. 哪些模式可直接借用？
   - Anthropic 的 `orchestrator-workers`、`routing`、局部 `parallelization`、局部 `evaluator-optimizer`
   - OpenAI 的 `agents as tools`、运行时 loop、run context vs model context 分离
   - Claude Code 本地材料里的显式主循环、上下文 pipeline、能力 descriptor、按需加载

4. 哪些常见框架/抽象反而会拖慢当前项目？
   - 把 Agents SDK / Letta runtime / Anthropic Agent SDK 当主 runtime
   - 过早把 worker 拆成大量小 agent
   - 新增常驻 meta-orchestrator / 能力层
   - 把 Context Orchestration Layer 做成写前预检 agent

## Files found

- [H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/prd.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/prd.md): 当前 story runtime 总 PRD，明确 workflow、worker、mode profile、runtime contract 方向。
- [H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-worker-scheduler-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-worker-scheduler-spec.md): worker / scheduler / orchestrator 合同草案与边界。
- [H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-development-master-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-development-master-spec.md): 总控开发规格与模块依赖顺序。
- [H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-technical-research-and-pseudocode.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-technical-research-and-pseudocode.md): 既有外部研究与初步伪代码。
- [H:/chatboxapp/backend/rp/services/story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py): 当前 story turn 领域服务，体现固定 orchestrator/specialist/writer 链。
- [H:/chatboxapp/backend/rp/services/longform_orchestrator_service.py](H:/chatboxapp/backend/rp/services/longform_orchestrator_service.py): 当前 longform orchestrator，实现旧 `OrchestratorPlan`。
- [H:/chatboxapp/backend/rp/services/longform_specialist_service.py](H:/chatboxapp/backend/rp/services/longform_specialist_service.py): 当前唯一 specialist，实现 retrieval + digest + hints。
- [H:/chatboxapp/backend/rp/services/writing_packet_builder.py](H:/chatboxapp/backend/rp/services/writing_packet_builder.py): 当前确定性 writer packet builder。
- [H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py): 当前 graph node 壳子，体现固定节点链。
- [H:/chatboxapp/docs/research/how-claude-code-works-main/docs/02-agent-loop.md](H:/chatboxapp/docs/research/how-claude-code-works-main/docs/02-agent-loop.md): Claude Code 主循环与阶段化执行。
- [H:/chatboxapp/docs/research/how-claude-code-works-main/docs/03-context-engineering.md](H:/chatboxapp/docs/research/how-claude-code-works-main/docs/03-context-engineering.md): 上下文分层、组装 pipeline 与压缩思路。
- [H:/chatboxapp/docs/research/how-claude-code-works-main/docs/04-tool-system.md](H:/chatboxapp/docs/research/how-claude-code-works-main/docs/04-tool-system.md): 工具 descriptor、权限/并发/只读边界与 on-demand loading。

## Code patterns

- 当前 graph 主链仍是固定节点顺序，而非 scheduler 驱动的 worker runtime: [story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py:148), [story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py:164), [story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py:187), [story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py:206), [story_graph_nodes.py](H:/chatboxapp/backend/rp/graphs/story_graph_nodes.py:256)
- 当前 domain service 直接串 orchestrator -> specialist -> packet -> writer -> persist: [story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py:131), [story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py:158), [story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py:235), [story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py:309), [story_turn_domain_service.py](H:/chatboxapp/backend/rp/services/story_turn_domain_service.py:336)
- 当前 orchestrator 仍输出旧 MVP `OrchestratorPlan`，偏 retrieval + specialist focus + writer instruction: [longform_orchestrator_service.py](H:/chatboxapp/backend/rp/services/longform_orchestrator_service.py:48), [longform_orchestrator_service.py](H:/chatboxapp/backend/rp/services/longform_orchestrator_service.py:119), [longform_orchestrator_service.py](H:/chatboxapp/backend/rp/services/longform_orchestrator_service.py:246)
- 当前 specialist 本质是单 generalist worker，先做 retrieval，再 digest 成 writer hints / state patch proposals: [longform_specialist_service.py](H:/chatboxapp/backend/rp/services/longform_specialist_service.py:77), [longform_specialist_service.py](H:/chatboxapp/backend/rp/services/longform_specialist_service.py:98), [longform_specialist_service.py](H:/chatboxapp/backend/rp/services/longform_specialist_service.py:109), [longform_specialist_service.py](H:/chatboxapp/backend/rp/services/longform_specialist_service.py:204), [longform_specialist_service.py](H:/chatboxapp/backend/rp/services/longform_specialist_service.py:417)
- 当前 writer packet builder 已经是稳定 deterministic builder，适合作为新 runtime 的 writer 组包基底: [writing_packet_builder.py](H:/chatboxapp/backend/rp/services/writing_packet_builder.py:14), [writing_packet_builder.py](H:/chatboxapp/backend/rp/services/writing_packet_builder.py:47), [writing_packet_builder.py](H:/chatboxapp/backend/rp/services/writing_packet_builder.py:51)
- Claude Code 参考材料显示：显式主循环、上下文组装 pipeline、工具 descriptor/on-demand loading 都是成熟形态: [02-agent-loop.md](H:/chatboxapp/docs/research/how-claude-code-works-main/docs/02-agent-loop.md), [03-context-engineering.md](H:/chatboxapp/docs/research/how-claude-code-works-main/docs/03-context-engineering.md), [04-tool-system.md](H:/chatboxapp/docs/research/how-claude-code-works-main/docs/04-tool-system.md)

## External references

- Anthropic, *Building Effective AI Agents* (published 2024-12-19): https://www.anthropic.com/research/building-effective-agents
  - 关键点：先简单后复杂；workflow 与 agents 区分；orchestrator-workers 是复杂但仍可控的 workflow 模式；框架会带来抽象成本。
- OpenAI API Docs, *Orchestration and handoffs*: https://developers.openai.com/api/docs/guides/agents/orchestration
  - 关键点：先决定谁拥有最终用户回复；handoff 与 agents-as-tools 要区分；specialist 只在 contract 真变化时再拆。
- OpenAI API Docs, *Running agents*: https://developers.openai.com/api/docs/guides/agents/running-agents
  - 关键点：runtime loop 是 call model -> inspect -> tools/handoff -> continue/final；pause/resume 应保持同一 turn/run 连续性。
- OpenAI API Docs, *Agent definitions*: https://developers.openai.com/api/docs/guides/agents/define-agents
  - 关键点：定义最小 specialist；local context 和 model context 分离；只有在 tool/policy/ownership/trace 真变时才拆 agent。
- OpenAI Cookbook, *Orchestrating Agents: Routines and Handoffs* (2024-10-10): https://cookbook.openai.com/examples/orchestrating_agents
  - 关键点：routine 本质是步骤 + 工具；handoff 是 conversation ownership transfer；样例更多适合参考思想而非直接拿来做当前主 runtime。

## Related specs

- [prd.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/prd.md)
- [story-runtime-worker-scheduler-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-worker-scheduler-spec.md)
- [story-runtime-development-master-spec.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-development-master-spec.md)
- [story-runtime-technical-research-and-pseudocode.md](H:/chatboxapp/.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-technical-research-and-pseudocode.md)

## Caveats / Not Found

- 本次主要用的是官方模式文档与当前仓库 spec/代码链做映射，没有额外深入某个第三方成熟开源 agent 框架源码；这是刻意收窄，因为你的要求是“重点看成熟项目和官方设计模式，而不是泛泛找 agent 框架”，且当前项目的关键判断已经足够由官方模式 + 现有代码现状得出。
- `how-claude-code-works-main` 是本地研究材料，不是 Anthropic 官方源码文档；这里把它当作“成熟产品形态的本地拆解笔记”使用，用来借鉴主循环、上下文分层、工具 descriptor 等工程模式，而不是当作一手官方规范。
