# SetupAgent Action Decision Reference Notes

Date: 2026-04-30

## Scope

This note supports the next SetupAgent slice: a lightweight action-decision policy that helps the runtime decide when a text-only finish is acceptable and when a specific tool observation is required first.

This is not a new task manager, durable state layer, or broad classifier. The slice is limited to high-certainty setup-runtime obligations.

## Sources And What To Borrow

| Source | Observed pattern | Borrow for RP setup | Do not copy |
|---|---|---|---|
| Claude Code local architecture notes, `docs/research/how-claude-code-works-main/docs/02-agent-loop.md` | A stable loop alternates context assembly, model decision, tool execution, result injection, and continue/stop; continue sites are explicit and recoverable errors may be withheld until recovery fails. | Keep SetupAgent loop reasons explicit and make guard-triggered retry a runtime decision, not hidden prompt hope. | Do not copy Claude Code's full coding-agent session manager, file edit tracking, or broad recovery taxonomy. |
| Claude Code local tool notes, `docs/research/how-claude-code-works-main/docs/04-tool-system.md` | Tool results are observations; oversized/old details should be available on demand rather than always injected. | After compact, keep draft refs in context and force `setup.read.draft_refs` only when exact current draft detail is needed. | Do not keep tool retry chains or historical tool process in prompt context. |
| Pi mono low-level loop, `docs/research/pi-mono-main/packages/agent/src/agent-loop.ts` | Minimal inner loop: model response -> execute tool calls -> append tool results -> continue; no heavy semantic state machine is required for a usable agent core. | Add a small policy hook around SetupAgent's existing loop instead of introducing another orchestration framework. | Do not add Pi's generic steering/follow-up queues to setup; setup already has its own turn boundary. |
| Pi mono context boundary, `docs/research/pi-mono-main/packages/agent/src/agent.ts` and `packages/coding-agent/src/core/compaction/compaction.ts` | Context transforms happen before provider conversion; compaction keeps a summary plus recent entries and uses token pressure as a trigger. | Keep `action_expectation` in the runtime overlay and structured payload; let context governance continue owning compact/digest. | Do not copy Pi's coding/file-operation compaction details into RP setup. |
| LangGraph official docs | LangGraph is a low-level graph/runtime where nodes do work and edges decide routing; prebuilt tool conditions route to tools when the last AI message has tool calls, otherwise end. | Keep LangGraph as execution substrate, but make SetupAgent semantic policy explicit above graph routes. | Do not treat LangGraph's generic "no tool calls -> END" as sufficient for setup-specific correctness. |
| OpenAI Agents SDK official docs | Agents are configured with instructions/tools/guardrails/handoffs/tracing; tool guardrails wrap function tools and tracing records agent/model/tool spans. | Treat `ActionDecisionPolicy` as a local guardrail around final output and tool batches; keep tracing/eval surfaces additive. | Do not split SetupAgent into multiple managed-agent handoffs for this slice. |
| Anthropic Claude Code SDK official docs | The SDK exposes an agent harness with tools, permissions, sessions, error handling, and monitoring. | Keep this slice as harness behavior inside the current SetupAgent runtime: small, observable, and bounded. | Do not replace the existing Python/LangGraph runtime with Claude SDK. |

## Project-Specific Decision

SetupAgent already has:

- `SetupTurnGoal`
- `SetupWorkingPlan`
- `SetupPendingObligation`
- `CompletionGuardPolicy`
- `ReflectionTriggerPolicy`
- `RepairDecisionPolicy`
- `loop_trace`
- stage-local `working_digest`, `tool_outcomes`, and `compact_summary`

The missing piece is not "more state". The missing piece is a small runtime-authored expectation that says:

- "This turn may end as text."
- "This turn must ask the user."
- "This turn must repair a tool call."
- "This compacted turn needs a draft read before answering or writing exact details."

For this slice, only the last case needs new enforcement because the existing repair and ask-user cases are already covered by `CompletionGuardPolicy`.

## Chosen MVP

Add a transient `SetupActionExpectation` computed after `turn_goal` and `working_plan`.

The first enforced expectation is:

- if current-step compact context exists,
- and compact summary or recovery hints expose draft refs,
- and the current user prompt asks for exact / full / concrete draft detail,
- and no successful `setup.read.draft_refs` observation for those refs has occurred in this same turn,
- then text finalization and non-read mutation tool batches are blocked until the model calls `setup.read.draft_refs`.

This is intentionally narrower than a semantic planner. It protects the real RP failure mode: after compact, the model may answer from a thin summary instead of reading the current draft truth.

## Why Not More

- Broad "similar task" or "should have written draft" classifiers are not added because they are hard to prove and likely to become noisy.
- Tool choice is not replaced with a new planner because the current setup tool set is small.
- No durable state is added because `working_digest` and `compact_summary` already own cross-turn context surfaces.
- No new external framework is introduced because current LangGraph runtime is sufficient as an execution substrate; the missing behavior is local policy, not framework capability.
