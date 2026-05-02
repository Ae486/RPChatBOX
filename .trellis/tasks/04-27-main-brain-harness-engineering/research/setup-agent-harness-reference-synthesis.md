# SetupAgent Harness Reference Synthesis

Date: 2026-04-27

## 1. Conclusion

The next SetupAgent design slice should not be a narrow "loop" or "no tool call completion" slice.

The correct unit is **stage-local harness semantics**:

- how context is assembled before each model call
- how stage-local raw history, digest, compact summary, tool outcomes, and draft truth are separated
- how tools are exposed, validated, executed, and summarized back into context
- how repair / continue / finish decisions are represented
- how skills and stage resources are injected without prompt bloat
- how checkpoint / resume / user edit / human commit boundaries stay clean
- how eval and Langfuse can reconstruct the trajectory without becoming runtime state

This keeps the scope broad enough to learn from mature agents, but still narrow enough to implement without creating a new Memory OS or a speculative state-management subsystem.

## 2. Reference Baseline

### Claude Code

Local references:

- `docs/research/how-claude-code-works-main/docs/02-agent-loop.md`
- `docs/research/how-claude-code-works-main/docs/03-context-engineering.md`
- `docs/research/how-claude-code-works-main/docs/04-tool-system.md`
- `docs/research/how-claude-code-works-main/docs/09-skills-system.md`

Useful patterns:

- Session lifecycle and inner query loop are separate.
- Context is constructed as a pipeline: stable system prompt, system/user context, normalized messages, tool result budget, compact/collapse/autocompact.
- Tool results are budgeted before the next model call; large results become references/previews instead of polluting context.
- Tool interfaces carry safety and scheduling semantics: read-only, destructive, concurrency-safe, validation, permission, result limits.
- Skills are prompt resources with metadata; full content is loaded on demand, and invoked skills are re-injected after compact.
- "No tool call" is only a natural stop condition for one loop iteration, not a business completion proof.

### Pi mono

Local references:

- `docs/research/pi-mono-main/packages/agent/src/agent.ts`
- `docs/research/pi-mono-main/packages/agent/src/agent-loop.ts`
- `docs/research/pi-mono-main/packages/coding-agent/src/core/compaction/compaction.ts`

Useful patterns:

- `Agent` wrapper owns transcript, lifecycle, queues, and events; low-level loop only drives model/tool turns.
- `transformContext -> convertToLlm` is an explicit pre-LLM boundary. This is the cleanest pattern to borrow for SetupAgent context engineering.
- Tool calls support before/after middleware and sequential/parallel execution policy.
- Steering and follow-up queues allow user input or queued messages to enter the loop without pretending they are model cognition.
- Compaction is a first-class session operation with cut-point validity, previous summary update, split-turn summary, and file-operation carry-forward.

### LangGraph / LangChain

Relevant existing project note:

- `docs/research/rp-redesign/agent/implementation-spec/technology-selection-overview-rp-agent-2026-04-20.md`

Official docs reviewed:

- LangGraph overview and graph API
- LangGraph interrupts / persistence / durable execution docs
- LangChain agent docs and middleware concepts

Useful patterns:

- LangGraph is a workflow/state/checkpoint substrate. It should host the loop, not define the business semantics.
- Node boundaries matter for resilience and observability because durable execution checkpoints at those boundaries.
- `interrupt()` is suitable for true human-in-loop pause/resume, but resume restarts the node, so node side effects must be idempotent or occur after the interrupt boundary.
- LangChain agents are higher-level abstractions built on LangGraph; useful as design reference for middleware, summarization, and human-in-loop, not as the main SetupAgent runtime.

### OpenAI Agents SDK

Official docs reviewed:

- Agents, Runner, tools, handoffs, guardrails, sessions, results, tracing

Useful patterns:

- Small primitive set: `Agent`, `Runner`, tools, handoffs, guardrails, sessions, tracing.
- Guardrails run before/after input, output, or tool execution and can halt or modify execution.
- Results expose final output plus structured run items such as tool calls, handoffs, approvals, and raw responses.
- Tracing captures LLM generations, tool calls, handoffs, guardrails, and custom spans.
- The SDK is not the right runtime dependency for this project now, but its contracts are good references for result surfaces and trace boundaries.

### Claude Agent SDK

Official docs and local references reviewed:

- Anthropic Claude Agent SDK docs (`allowedTools`, `disallowedTools`, tool search, MCP integration, streaming/event surfaces)
- `docs/research/oh-my-claudecode-main/src/index.ts`
- `docs/research/oh-my-claudecode-main/src/tools/index.ts`

Useful patterns:

- Per-run allowed-tool narrowing is a first-class control surface; the runtime does not need to expose the full registry every turn.
- Tool search exists to avoid paying prompt budget for every tool definition up front; only a relevant subset needs to be surfaced to the model.
- MCP/tool integration can stay registry-based underneath while the agent-facing tool scope remains a smaller turn-level allowlist.
- This is a good reference for SetupAgent step-aware tool visibility, but not a reason to import the whole SDK or replace the current runtime.

### Anthropic Harness Writing

Existing research:

- `.trellis/tasks/04-27-main-brain-harness-engineering/research/harness-engineering-openai-anthropic.md`

Official engineering articles reviewed:

- Agent harness vs eval harness framing
- Long-running harness / initializer-agent and coding-agent split
- Brain / hands / sandbox separation

Useful patterns:

- Model plus harness is the evaluated system; weak harness design can look like model weakness.
- Long-running work benefits from clear handoff artifacts and context reset strategy.
- Harness components encode assumptions about model weakness and should be revisited, not ritualized.
- Session, harness, and sandbox are separable concepts; do not mix semantic truth with execution environment bookkeeping.

## 3. Current SetupAgent Status

Current implementation is not fake. It already has a real finite runtime loop:

- `backend/rp/agent_runtime/executor.py`
- `backend/rp/agent_runtime/graph.py`
- `backend/rp/agent_runtime/policies.py`
- `backend/rp/agent_runtime/contracts.py`
- `backend/rp/services/setup_agent_execution_service.py`
- `backend/rp/services/setup_context_governor.py`
- `backend/rp/services/setup_context_compaction_service.py`
- `backend/rp/services/setup_agent_prompt_service.py`
- `backend/rp/graphs/setup_graph_runner.py`

Already present:

- LangGraph-backed nodes: prepare input, derive goal, plan, build request, call model, inspect output, execute tools, apply results, assess progress, reflect, finalize.
- Runtime-private cognition: `turn_goal`, `working_plan`, `pending_obligation`, `last_failure`, `reflection_ticket`, `completion_guard`.
- Thin control state: `SetupWorkingDigest`.
- Final-result-only tool retention: `SetupToolOutcome`.
- Stage-local current-step summary: `SetupContextCompactSummary`.
- Tool failure classification and repair policy.
- Completion guard that separates pure text turn endings from step readiness.
- Langfuse observations for agent run and tool execution.

Main gaps:

- Context construction is not yet named as a first-class transform contract.
- Current compaction is deterministic trimming/summarization, not a real compact-expert LLM pass.
- Tool semantics are partially in schemas/results but not exposed as a unified policy surface.
- ReAct trajectory is inferable from state/events but not a stable trace contract.
- Skills are still embedded prompt guidance, not lazy/budgeted stage resources.
- Checkpoint/resume exists at graph level, but transient state reset and semantic resume boundaries need to remain explicit.
- Human takeover through user draft edits exists conceptually, but the agent-side reconciliation path should be formalized.

## 4. Multi-Dimension Borrow / Defer Matrix

| Dimension | Mature pattern | Current SetupAgent | Borrow now | Defer / reject |
|---|---|---|---|---|
| Session vs loop | Claude Code / Pi split outer lifecycle from inner loop | Setup execution service wraps runtime executor; graph runner adds checkpoint | Name stage-local harness layer and keep loop semantic contract explicit | Do not build full branching/forking session tree now |
| Context transform | Claude Code context pipeline; Pi `transformContext -> convertToLlm` | `SetupContextPacket` plus runtime overlay plus governed history | Define `build_context_packet -> govern_context -> build_runtime_overlay -> build_llm_messages` as contract | Do not create Memory OS or broad retrieval-first context |
| Compact | Claude Code progressive compact; Pi previous-summary update | deterministic current-step summary and raw history limit | Define real compact service interface and trigger policy; keep current deterministic path as MVP fallback | Do not compact every turn or replace draft truth with summaries |
| Tool result retention | Claude Code result budget; Pi tool result messages | retains final outcomes, not retry process | Keep final outcome only; include latest batch in immediate loop; retain bounded historical outcomes | Do not inject retry/process trace into prompt context |
| Tool semantics | Tool metadata, validation, permission, concurrency, result limits; Claude Agent SDK allowed-tools narrowing | runtime executor has visible tool scope; tool failures have repair categories | Add unified metadata/policy view for setup tools: read/write, truth mutation, failure class, retryability, commit impact; immediately land step-aware tool-scope narrowing | Do not split one tool per micro-stage |
| Loop / ReAct | goal/action/observation/recover/finish | graph nodes implement this implicitly | Emit structured semantic trace fields without exposing chain-of-thought | Do not make no-tool-call a standalone feature |
| Repair | Guardrails and tool validation enforce correction | schema failure and repair obligation exist | Harden taxonomy and max retry policy around existing signals | Do not add speculative semantic stall classifiers |
| Skills | Lazy-loaded prompt resources, fork/inline, post-compact recovery | stage guidance is embedded in prompt | Design stage skill resource contract and budgeted injection placeholder | Do not implement full skills runtime before context contract is stable |
| Checkpoint/resume | LangGraph persistence, interrupts, durable node boundaries | setup graph runner uses thread config/checkpoints | Preserve transient-state reset and define which fields are durable vs per-run | Do not persist every internal thought-like trace as product state |
| Human takeover | interrupt / approvals / editable artifacts | user can edit draft and commit manually | Treat user edit deltas as invalidation/reconciliation inputs | Do not block explicit user commit with readiness warnings |
| Observability | OpenAI tracing, Langfuse/LangSmith, eval harness separation | Langfuse observations already exist | Add fields needed to reconstruct context decision, action, observation, repair, finish | Do not move eval logic into runtime autonomy |

## 5. Recommended Next Spec Slice

Name:

**SetupAgent Stage-Local Harness Semantics**

This is broader than a loop patch but still one coherent implementation slice.

### 5.1 In Scope

1. **Pre-model context transform contract**
   - Formalize the sequence:
     - `SetupWorkspace / SetupContextPacket`
     - prior-stage handoffs
     - current-step draft and user edit deltas
     - cognitive summary
     - working digest
     - compact summary
     - retained tool outcomes
     - governed raw current-step history
     - runtime overlay
     - final LLM messages
   - Add a traceable context report with counts/budgets/source decisions.

2. **Stage-local compact boundary**
   - Preserve rule: new stage does not inherit raw prior-stage discussion.
   - Stage-local compact may compress old current-step discussion.
   - Draft truth and committed handoff remain retrieval / truth source for details.
   - Define interface for compact-expert LLM pass, while allowing deterministic fallback until implementation is ready.

3. **Tool outcome and latest observation policy**
   - Retain final outcomes only, not tool retry process.
   - Latest tool batch can be fed back immediately as observation.
   - Historical retained outcomes are bounded and relevance-filtered.
   - Error outcomes are retained enough to avoid repeating the same current-stage mistake, but eval remains the main long-term tuning layer.

4. **Tool semantics policy surface**
   - Make existing setup tool semantics explicit:
     - read-only vs mutation
     - draft/truth mutation vs runtime-private cognition
     - commit-affecting
     - retryable / ask-user / block-commit / unrecoverable
     - sequential-only vs potentially parallel
   - Use this to guide runtime decisions and traces, not to multiply tools.

5. **ReAct trajectory trace**
   - Stable trace fields:
     - goal
     - plan
     - context report
     - action type and tool names
     - observation summary
     - repair route
     - continue reason
     - finish reason
   - This is for policy, eval, and debugging; it is not chain-of-thought exposure.

6. **Stage skill/resource placeholder**
   - Define a small contract for stage resources:
     - name
     - stage/mode applicability
     - summary/when-to-use
     - prompt body
     - tool visibility hints
     - budget
   - Borrow Claude Code lazy-loading principle.
   - The first implementation can still use current embedded prompt guidance, but the spec should stop hardcoding this as the desired end state.

7. **Checkpoint/resume and human edit boundary**
   - Preserve graph checkpointing, but state which fields are durable semantic state and which are per-run transient state.
   - User draft edit deltas invalidate/reconcile runtime cognition before commit proposal.
   - Explicit user commit remains allowed even when readiness is weak; warnings do not become hard blockers.

### 5.2 Out of Scope

- Full Memory OS redesign.
- Full retrieval-layer redesign.
- Full multi-agent handoff/runtime branching.
- Replacing current runtime with OpenAI Agents SDK or LangChain agent abstraction.
- New durable event log as source of truth.
- Semantic-similarity anti-stall heuristics.
- Tool-per-micro-stage explosion.
- Treating no-tool-call completion as an isolated design problem.

## 6. Why This Is Not Overgrown State Management

The proposed slice does not add a new state store.

It mainly makes existing runtime surfaces explicit:

- `working_digest` remains a thin control digest.
- `compact_summary` remains compacted current-step discussion carry-forward.
- `tool_outcomes` remain bounded final outcomes.
- `cognitive_state_summary` remains the current-step discussion/truth map.
- `SetupWorkspace` remains product truth.
- eval traces remain external observation, not agent-owned memory.

The new work is mostly naming, ordering, reporting, and policy hardening around surfaces that already exist.

## 7. Proposed Review Questions

Before implementation, the user should review these decisions:

1. Is "SetupAgent Stage-Local Harness Semantics" the right next slice name and boundary?
2. Should compact prompt LLM summarization be specified now as an interface with deterministic fallback, or implemented immediately in the same slice?
3. Should stage skill/resource injection remain a contract-only placeholder in this slice, or should the first longform stage skill be included?

My recommendation:

- Implement compact as contract + fallback first, because current deterministic summary is not a real compact prompt summary and rushing it will blur design.
- Keep skills as contract + prompt extraction path first, unless the next implementation slice specifically targets skills.
- Prioritize context transform, tool outcome policy, tool semantics, and trace report because they improve the agent body without adding a heavy state subsystem.
