# Research: runtime-tech-research-retrieval-loop

- Query: 对 story runtime 的 writer-side retrieval / tool loop / packet 技术路径做调研，优先审视现有仓库与必要官方模式，明确 retrieval core 是否足够、writer-side bounded retrieval 的最稳实现方式、可复用轮子、不值得现在引入的“先进方案”，并判断是否建议新增框架。
- Scope: mixed
- Date: 2026-05-07

## Findings

### 结论先行

- 不建议替换当前 retrieval core，也不建议为这条链路新增一层“agent framework”或独立 retrieval framework。
- 当前 retrieval core 已经够用来支撑 story runtime 的 writer-side retrieval boot path；真正缺的不是检索引擎，而是 writer 侧的受控 tool loop、usage gate、short-id-facing tool contract、以及 packet/read-manifest 级接线。
- 最稳的落地方式是：保留 `RetrievalBroker -> RetrievalService -> RuntimeRetrievalCardService` 主链，在 writer 侧新增一个很薄的 bounded tool loop service，把 `search / expand / usage` 作为唯一开放工具，最多 1-3 次 retrieval attempt，最后由 usage guard 决定能否 final output。

### 1. 当前 retrieval core 是否足够，不足在哪里

判断：够用，但“够用”的含义是“足够作为 runtime 内部受控检索底座”，不是“writer retrieval 已经完整闭环”。

足够的部分：

- `RetrievalService` 已经具备 query preprocess、keyword + semantic 双路召回、fusion、可选 graph expansion、rerank、result build 的完整 retrieval core，不需要另起一套检索引擎。
- `RetrievalBroker` 已经负责 runtime identity 注入、branch visibility 过滤、runtime snapshot pinned retrieval config、observability/tracing；这正是 writer retrieval 应继续经过的 read boundary。
- `RuntimeRetrievalCardService` 已经把 search result 物化为 Runtime Workspace `retrieval_card`，并支持 `expand`、`miss`、`usage_record`，这正是 writer-side retrieval 最关键的“runtime trace path”。

不足的部分，主要都在 runtime 接线层：

1. writer 还没有真正的 tool loop
   - `WritingWorkerExecutionService` 目前只是把 `WritingPacket` 渲染成单次 messages，然后直接 `complete_text` / `stream_text`，没有 tool call 循环，也没有 tool trace 收口。
2. gateway 还没有开工具能力
   - `StoryLlmGateway.build_request()` 当前固定 `enable_tools=False`，说明现在缺的是“tool-enabled writer adapter”，不是 retrieval core。
3. usage contract 还不完整
   - `RuntimeRetrievalCardService.record_writer_usage()` 目前记录的是 backend material ids，尚未补齐 spec 里要求的 writer-facing short ids、unused cards、structured knowledge gaps。
4. short-id 面向模型的薄工具契约还没补
   - 当前 `expand_cards()` / `record_writer_usage()` 都以 material id 为主；这对 backend 内部是合理的，但 model-facing tool 最稳的口径应是 short id -> runtime resolve。
5. packet/read-manifest 还没形成完整 runtime 闭环
   - spec 已经冻结“writer packet 只吃 card summary/selected expansion，不吃 raw dump”，但当前实现层还没有明确的“每次 tool loop 后如何刷新 packet retrieval sections / manifest refs”。

所以结论不是“retrieval 不行”，而是：

- retrieval core 足够
- writer runtime contract 还不够

### 2. writer-side bounded retrieval 最稳的实现方式是什么

最稳方案：薄 runtime loop，而不是自由 agent。

建议形态：

1. 保留现有 packet 主骨架
   - writer packet 继续保持窄上下文，只放 `retrieval_card_sections` 和必要的 expanded sections，不放 raw hits，不放 workspace 日志。
2. 在 writer 侧新增一个薄的 `WritingWorkerRetrievalLoopService`
   - 输入仍然是 `WritingPacket + model/provider + retrieval policy`
   - 对模型只开放 3 个工具：
     - `retrieval.search`
     - `retrieval.expand`
     - `retrieval.usage`
3. loop 只允许 bounded client-side tool roundtrip
   - `tool_choice=auto`
   - `parallel_tool_calls=false`
   - `strict=true`
   - `max_retrieval_attempts` 建议 1-3，不做开放式多轮自治
4. tool arguments 面向 writer 只暴露稳定 short ids
   - `search` 返回 `R1/R2/...`
   - `expand` 只允许传已返回的 `R*`
   - `usage` 提交 `used_card_short_ids / used_expanded_short_ids / missed_query_short_ids / knowledge_gaps`
   - runtime 在 backend 内部把 short ids resolve 成 material ids
5. final output 之前强制 usage gate
   - 如果本 turn 出现过 retrieval cards / expanded chunks / miss materials，但没有 usage record，则 fail closed，不让 final output 通过
6. miss / gap 按 mode 分流，而不是引入更聪明的 planner
   - longform：可以保守继续写
   - roleplay：继续互动，但禁止编造缺失细节
   - trpg：缺硬规则时应显式 gap，不静默编造

为什么这是最稳的：

- 它直接复用仓内已经存在的 retrieval trace path，而不是再造状态机
- 它把“模型判断是否缺信息”留给 writer，把“搜索/展开/usage 记录”留给 runtime
- 它最符合现有 spec 对 packet、workspace、post-write governance 的冻结边界

### 3. 哪些轮子/模式可以复用

仓内可直接复用：

- `RuntimeRetrievalCardService`
  - 现成的 `search -> cards`、`expand -> expanded chunk`、`usage -> retrieval_usage_record` 主链，应该继续作为 retrieval runtime 的核心工具执行器。
- `RetrievalBroker`
  - 已经处理 runtime identity、branch visibility、snapshot-pinned retrieval config、retrieval observability。
- `RetrievalService`
  - 现成 retrieval core，不应再包一层替代品。
- `StoryLlmGateway.complete_text_with_usage()`
  - 说明 usage 收口已经有基础；需要补的是 tool-enabled request path，不是新的 provider abstraction。
- SetupAgent 的 capability / tool loop guard 模式
  - `SetupAgentExecutionService` 已经验证过模型兼容性检查这条路：先校验模型是否支持 function calling、`tools`、`tool_choice`，再进入 tool runtime。writer retrieval 可以直接借用这套“先 capability gate，再 loop”的防错模式。

官方模式里值得借的，只有模式，不是框架：

- OpenAI function calling guide
  - 标准 client-side tool loop：模型返回 tool call，应用执行，再把 tool result 回灌；这和 writer-side bounded retrieval 完全同型。
- OpenAI 对 `strict=true`、`parallel_tool_calls=false` 的建议
  - 非常适合这种“工具少、合同薄、必须稳定”的 retrieval loop。
- Anthropic tool-use loop
  - 也是标准 `while stop_reason == tool_use` 的 client-side loop；说明这条技术路径本身是主流基础设施能力，不需要再造宏大框架。

### 4. 哪些“看上去先进”的方案现在不值得引入

当前不值得引入：

1. 新 agent framework / SDK 托管 loop
   - 现在缺的是一个很薄的 writer retrieval loop，不是缺一个全家桶 agent runtime。
   - 引入新 framework 会把 packet、workspace、usage、post-write trace 再包一层，增加调试成本和语义漂移。
2. server-side web/tool loop
   - 你的 retrieval 是 repo 内部的 memory/retrieval core，不是开放互联网检索；把 loop 交给外部 server-side tool 既不匹配数据边界，也破坏 runtime traceability。
3. “让 retrieval 自己总结剧情”的 retrieval-agent
   - spec 明确 retrieval 只做 evidence delivery，不做创作性总结；否则 retrieval 和 writer 职责会重新缠在一起。
4. tool search / 动态发现大工具集
   - writer retrieval 只需要 2-3 个稳定工具，不需要动态工具发现。把这种复杂度引进来只会增加 schema、观测、兼容性负担。
5. 多 agent planner / orchestrator 再包 writer retrieval
   - 这条链路是 writer 内部的 bounded side-loop，不是一个独立多 worker 编排问题。现在新增 planner 只会多一次调度成本。
6. GraphRAG-first 改造
   - `RetrievalService` 已经支持可选 graph expansion；现在的问题不是“缺图检索”，而是 writer-side runtime 闭环没接完。

### 5. 是否建议新增框架

结论：不建议新增框架。

理由：

- 现有 retrieval core 已经成型，替换或外包会直接冲击 `RetrievalBroker`、branch visibility、runtime identity、snapshot pinned config、observability，这些恰好是当前最有价值的稳定资产。
- 当前 writer 侧的缺口是“runtime contract 缺口”，不是“能力栈缺口”。
- 新框架最容易带来的问题不是功能做不到，而是：
  - packet contract 漂移
  - Runtime Workspace trace 路径被绕开
  - usage record / post-write source refs 失真
  - 调试面扩大，兼容性变差

更合适的做法是新增“薄 service / adapter”，不是“新 framework”：

- 可以新增一个 `WritingWorkerRetrievalLoopService`
- 可以新增一个 `WriterRetrievalUsageGuardService`
- 可以在 `StoryLlmGateway` 上补 tool-enabled request path 或单独的 writer-tool adapter
- 但不建议引入外部 agent orchestration framework，也不建议重做 retrieval core

## Files Found

- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-context-packet-spec.md`：冻结 writer/worker packet 的进入内容、顺序、裁剪和 read-manifest 边界。
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-writing-worker-spec.md`：冻结 writer 的 operation modes、唯一用户可见输出边界，以及“retrieval 只作为受控工具能力”。
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-retrieval-spec.md`：冻结 bounded retrieval、short id、usage hook、knowledge gap、workspace 对接。
- `.trellis/spec/backend/rp-retrieval-card-usage-promotion-boot-contract.md`：确认 retrieval boundary 仍是 `RetrievalBroker`，以及 search->card->expand->usage 的 boot 最小闭环。
- `.trellis/spec/backend/rp-runtime-workspace-turn-material-store.md`：确认 retrieval card / expanded chunk / usage record 都只是 Runtime Workspace material，不是 Core truth。
- `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md`：确认 packet-visible retrieval context 只能进入 deterministic manifest/packet 边界，不能把 raw dump 当合同。
- `.trellis/spec/backend/rp-narrative-retrieval-policy-contract.md`：确认 narrative retrieval 的增强方向应该落在 filters / rerank / trace，而不是替换 retrieval core。
- `backend/rp/services/runtime_retrieval_card_service.py`：现有 runtime retrieval materialization、expand、miss、usage record 实现。
- `backend/rp/services/retrieval_broker.py`：现有 runtime-aware retrieval boundary、branch visibility、snapshot pinned config、observability。
- `backend/rp/services/retrieval_service.py`：现有 retrieval core 主链。
- `backend/rp/services/writing_worker_execution_service.py`：当前 writer 执行仍是一-shot text 调用，没有 tool loop。
- `backend/rp/services/story_llm_gateway.py`：当前 shared LLM gateway 支持 usage，但默认关闭 tools。
- `backend/rp/services/setup_agent_execution_service.py`：现成的模型 capability gate 模式，可借给 writer retrieval loop。

## Code Patterns

- `backend/rp/services/runtime_retrieval_card_service.py:53`
  - `search_recall_to_cards()` / `search_archival_to_cards()` 已经形成 search -> card materialization 入口。
- `backend/rp/services/runtime_retrieval_card_service.py:114`
  - `expand_cards()` 强制 expand 目标必须是已存在的 `RETRIEVAL_CARD` material。
- `backend/rp/services/runtime_retrieval_card_service.py:156`
  - `record_writer_usage()` 已有 explicit usage record 路径，但当前只稳定到 material-id 层。
- `backend/rp/services/runtime_retrieval_card_service.py:345`
  - `_record_card()` 已经生成 identity-scoped `R*` short id 和 writer-visible summary card。
- `backend/rp/services/runtime_retrieval_card_service.py:406`
  - `_record_expanded_chunk()` 说明 expanded content 已经走 Runtime Workspace trace path，而不是直接灌包。
- `backend/rp/services/runtime_retrieval_card_service.py:484`
  - `_record_miss()` 已经有 `RETRIEVAL_MISS` material，可作为 knowledge gap 的底层证据。
- `backend/rp/services/retrieval_broker.py:173`
  - `search_recall()` / `search_archival()` 继续是 runtime retrieval 的 canonical read boundary。
- `backend/rp/services/retrieval_broker.py:261`
  - `_build_query()` 会注入 runtime identity，并把 branch override filter 从 caller 侧拿掉，避免冲掉 runtime branch visibility。
- `backend/rp/services/retrieval_broker.py:348`
  - `_query_with_runtime_search_policy()` 已支持 explicit on/off/auto rerank 解析，可直接承接 writer-side profile policy。
- `backend/rp/services/retrieval_broker.py:887`
  - `_filter_runtime_search_result()` 已把 branch visibility 过滤与 trace details 做进结果层。
- `backend/rp/services/retrieval_service.py:165`
  - `_search_chunks_preprocessed()` 已具备 preprocess -> retrieve/fuse -> optional graph expansion -> rerank -> result build 主链。
- `backend/rp/services/writing_worker_execution_service.py:19`
  - `run()` 目前是一次性 `complete_text()`，不是 tool loop executor。
- `backend/rp/services/writing_worker_execution_service.py:34`
  - `run_stream()` 目前只是文本流转发，不支持 tool event / tool result roundtrip。
- `backend/rp/services/story_llm_gateway.py:49`
  - `complete_text_with_usage()` 说明 usage metadata 已可收口到 runtime。
- `backend/rp/services/story_llm_gateway.py:102`
  - `build_request()` 当前固定 `enable_tools=False`，这就是 writer-side tool loop 尚未接上的直接证据。
- `backend/rp/services/setup_agent_execution_service.py:423`
  - `_ensure_agent_model_compatible()` 已验证“先 capability gate，再进 tool loop”是仓内成熟模式，可直接复用到 writer retrieval。

## External References

- OpenAI Function Calling Guide
  - https://platform.openai.com/docs/guides/gpt/function-calling
  - 相关模式：client-side multi-step tool loop、`strict=true`、`tool_choice`、`parallel_tool_calls=false`。
- Anthropic Tool Use Overview / How Tool Use Works
  - https://console.anthropic.com/docs/en/agents-and-tools/tool-use/how-tool-use-works
  - https://docs.anthropic.com/claude/docs/tool-use
  - 相关模式：`while stop_reason == "tool_use"` 的 client-side loop；工具执行始终由应用侧负责，模型只发 structured request。
- Anthropic Tool Runner
  - https://console.anthropic.com/docs/en/agents-and-tools/tool-use/tool-runner
  - 只作为“现成 runner 抽象”的参考；当前仓库不建议引入它来替代现有 runtime 语义。

## Related Specs

- `.trellis/spec/backend/rp-retrieval-card-usage-promotion-boot-contract.md`
- `.trellis/spec/backend/rp-runtime-workspace-turn-material-store.md`
- `.trellis/spec/backend/rp-core-projection-read-manifest-hardening.md`
- `.trellis/spec/backend/rp-narrative-retrieval-policy-contract.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-context-packet-spec.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-writing-worker-spec.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-retrieval-spec.md`

## Caveats / Not Found

- 本次没有发现现成的 writer-side tool loop 实现；当前仓内只有 retrieval materialization、one-shot writer execution、以及 setup-agent 侧可借用的 tool-capability / loop guard 模式。
- 本次没有发现 packet/read-manifest 与 writer retrieval tool loop 的已实现接线；这部分仍主要停留在 spec 层。
- 外部官方资料只用于确认“受控 client-side tool loop”是主流模式，不构成引入新 framework 的理由。
