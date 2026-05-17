# Current SetupAgent Memory Audit

Date: 2026-05-13

## Conclusion

当前 SetupAgent 已经有一套跨 turn 的 runtime-private cognition 和 context governance，但它还不是当前任务所需的 session-scoped setup fact memory / retrieval system。

原因很明确：

- 它是 `workspace_id + step_id` 作用域的运行期治理状态，不是给模型检索 setup facts 的 folder-like index / open 工作流。
- 它服务于当前 setup draft convergence、工具修复、commit readiness 和 compact recovery；这些 context assembly / compaction recovery artifacts 不应变成 `setup.memory.search` 的 agent-facing 命中来源。
- 它被设计为与 RP Memory OS 隔离，不能进入 Memory OS durable layer，也不应复用 story runtime 的 recall / archival 机制来承载 setup fact recovery。

因此，本任务不是从零补“状态”，而是在现有 runtime cognition 之外增加一层独立的 SetupAgent session memory：从 editable draft 与 accepted setup truth 这些 setup fact sources 派生可重建索引，通过 `setup.memory.search` 定位 ref，再通过 `setup.memory.open` 打开三级 entry 目录或四级 section clean content。`setup.memory.read_refs` 只保留兼容 / 内部读取语义。

## Existing Memory-Like Mechanisms

| Mechanism | Evidence | What it remembers | Why it is not agent memory |
| --- | --- | --- | --- |
| `SetupAgentRuntimeStateService` | `backend/rp/services/setup_agent_runtime_state_service.py` | 当前 workspace + step 的 discussion state、chunk candidates、truth write、working digest、tool outcomes、compact summary | 是 setup step runtime-private cognitive state，不是 agent-facing setup fact index/open 来源 |
| `SetupCognitiveStateSnapshot` / `Summary` | `backend/rp/agent_runtime/contracts.py` | 当前 setup step 的讨论、候选、open questions、commit readiness 辅助状态 | 是当前业务流程的治理快照，不是 editable draft / accepted truth 事实索引 |
| `SetupContextBuilder` | `backend/rp/services/setup_context_builder.py` | 从 `SetupWorkspace` 组装 current draft、user edit deltas、prior stage handoffs | 这是业务上下文构建器，source of truth 是 workspace，不是记忆索引与召回系统 |
| `SetupAgentPromptService` | `backend/rp/services/setup_agent_prompt_service.py` | 稳定系统提示词、capability guidance、stage overlay、context packet JSON | 只消费当前 context packet；没有独立 memory index / topic files / recall selector |
| `SetupRuntimeAdapter` | `backend/rp/agent_runtime/adapters.py` | 把 context packet、cognitive summary、working digest、compact summary 放入 runtime context bundle | 是 turn input adapter，不做 memory discovery、persistence 或 relevance selection |
| runtime overlay | `backend/rp/agent_runtime/executor.py` | turn goal、working plan、pending obligation、failure、cognitive summary、compact summary | 明确是 internal execution guidance，且 working digest 被提示为 thin step-local control state |
| context governor / compaction | `backend/rp/services/setup_context_governor.py`, `backend/rp/services/setup_context_compaction_service.py` | 历史裁剪、compact summary、draft ref recovery hints | 解决上下文预算与当前 step 恢复；可提示 agent 去 open refs，但自身不是 memory index/open source |
| Trellis / task PRD / research docs | `.trellis/tasks/*` | 开发任务过程、研究材料、handoff | 服务开发者协作，不是运行中的 SetupAgent 可读 memory subsystem |

## Key Current Boundaries

### SetupWorkspace remains business truth

`SetupContextBuilder` 从 `SetupWorkspace` 读取 current draft、pending user edit deltas、accepted commits 和 prior stage handoffs，再组装 `SetupContextPacket`。这条链路说明 SetupAgent 的业务事实仍在 workspace 和 accepted commit 中，而不是 agent memory。

### Runtime cognition is private and step-local

`SetupAgentRuntimeStateService` 的文件注释已经把它定义为 runtime-private cross-turn cognitive state storage。它的 durable payload 白名单只允许 `workspace_id`、`current_step`、`discussion_state`、`chunk_candidates`、`active_truth_write`、`working_digest`、`tool_outcomes`、`compact_summary`、`source_basis` 等字段。

测试 `test_runtime_state_service_turn_governance_snapshot_excludes_loop_trace_fields` 和 `test_runtime_state_service_rejects_accidental_structured_payload_merge` 进一步验证：`loop_trace`、`continue_reason`、`context_report`、provider debug 等 transient 字段不得进入持久状态。

### Prompt injection currently has no agent memory layer

`SetupAgentPromptService.build_system_prompt()` 只拼接：

- SetupAgent 固定身份和规则；
- stage specialist preamble / stage overlay；
- capability guidance；
- `SetupContextPacket` JSON。

它没有类似 Claude Code 的 `MEMORY.md` index，也没有 topic file recall、freshness warning、already surfaced filtering 或 side query selector。

### RP Memory OS is a different memory

已有设计文档明确：

- `SetupAgent` 不直接操纵 Memory OS，而是先操纵 `SetupWorkspace`，commit 后由 controller 驱动 retrieval ingestion。
- SetupAgent MVP 允许的 memory tool family 是只读：`memory.get_state`、`memory.get_summary`、`memory.search_recall`、`memory.search_archival`。
- SetupAgent 不允许 `proposal.submit` 或 `memory.patch_state`。
- Phase F 硬约束要求 setup runtime-private cognition 不进入 Memory OS durable layer。

这说明 story runtime / RP Memory OS 的 recall、archival、proposal、projection 体系不能承载本任务的 SetupAgent session memory。当前功能应只做 setup fact recovery：editable draft 与 accepted setup truth 在 agent-facing 语义上都是 setup fact sources，进入同一 folder-like index/open workflow；handoff、runtime compact summary、recovery hints 只属于 context assembly / compaction recovery。

## Gap

当前缺少的不是“把更多 setup 状态持久化”，而是 Claude Code 风格的受控索引 / 打开工作流：

1. **可重建索引**：从 editable draft 与 accepted setup truth 派生 manifest / folder-like index，不复制事实全文为第二 truth。
2. **统一事实来源语义**：accepted truth 和 editable draft 在当前 memory 功能视角都是 setup fact sources，source 区分只作为内部/debug metadata。
3. **按需定位与打开**：visible index 不足时用 `setup.memory.search` 定位 entry/section refs，再用 `setup.memory.open` 获取三级目录或四级 clean content。
4. **上下文恢复边界**：compact summary、recovery hints、handoff 可在 context layer 提醒 agent 需要恢复细节，但不产生 `setup.memory.search` hits。

## Design Implications

初版不应复用 RP Memory OS，也不应扩大 `SetupAgentRuntimeStateService` 的语义。更稳的方向是：

- 在 SetupAgent runtime 外围保留模块化 `SetupSessionMemoryService`；
- manifest / index 从 DB-backed setup fact sources 按需重建，避免文件型主存储、新依赖和向量数据库；
- 由 context assembly 提供 folder-like index view 与轻量 guidance，而不是硬编码 runtime expectation；
- `setup.memory.search` 只返回导航候选，`setup.memory.open` 才返回可作为事实依据的 clean content；
- 不做长期 user/feedback/project memory 写入；后续如需 raw discussion distillation，应进入 context/compaction artifact，而不是 memory index/open source。

## Source Notes

- `backend/rp/services/setup_agent_runtime_state_service.py`
- `backend/rp/agent_runtime/contracts.py`
- `backend/rp/services/setup_context_builder.py`
- `backend/rp/services/setup_agent_prompt_service.py`
- `backend/rp/agent_runtime/adapters.py`
- `backend/rp/agent_runtime/executor.py`
- `backend/rp/tests/test_setup_agent_runtime_state_service.py`
- `docs/research/rp-redesign/agent/implementation-spec/phase-b-setup-agent-mvp/02-setup-private-tool-contract-v2.md`
- `docs/research/rp-redesign/agent/implementation-spec/phase-f-memory-boundary-cleanup/README.md`
