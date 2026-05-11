# SetupAgent A1 Loop / Output Boundary Development Spec

> Task: `.trellis/tasks/05-11-setup-agent-architecture-improve`
>
> Slice: A1 `Loop stop / repair / output boundary`
>
> Status: development spec before backend implementation

## 1. Purpose

A1 turns the A0 architecture into the first executable slice. It closes the old setup-tool recursion / pseudo-tool leakage bug class by making the inner loop boundary explicit:

```text
ModelGateway normalized output
  -> OutputInspector typed classification
  -> SetupTurnLoop transition rule
  -> SetupToolRuntime execution or repair/finalize path
  -> SetupEventSink public/private event boundary
```

This is not a rewrite. It is an optimization and convergence of the existing runtime-v2 loop.

## 2. Source Authority

Use these sources in order:

1. Current user decisions and this task's A0 docs.
2. Active backend specs:
   - `.trellis/spec/backend/rp-setup-agent-loop-semantics-react-trace.md`
   - `.trellis/spec/backend/rp-setup-agent-structured-output-schema-repair.md`
   - `.trellis/spec/backend/rp-setup-agent-stage-aware-tool-scope.md`
   - `.trellis/spec/backend/rp-setup-agent-stage-local-context-governance.md`
   - `.trellis/spec/backend/rp-setup-agent-execution-service-outer-harness-thin-boundary.md`
3. Current `backend/rp/agent_runtime/...` and `backend/rp/tools/setup_tool_provider.py` as implementation/migration evidence.
4. pi-mono for the minimal loop shape: model response -> inspect -> execute tools -> append result -> continue/stop.
5. Claude Code for mature output/tool/transcript separation and active tool filtering.
6. Primary/current provider/framework docs only if A1 implementation changes concrete provider API, stream chunk, structured-output, or LangGraph semantics.

No network research is required before A1 coding unless implementation starts relying on exact OpenAI / Anthropic / LangGraph / LangChain behavior not already proven by local source/specs.

## 3. Non-Goals

A1 must not:

- introduce the full A2 `SetupCapabilityPlan` object as a prerequisite
- expose `setup.world_background.*`
- migrate to stage-local draft CRUD
- introduce setup retrieval
- alter review/commit/readiness or explicit user commit authority
- persist `loop_trace` / `continue_reason` into runtime governance snapshots
- redesign frontend transcript/UI
- add subagents or broader framework abstractions
- replace LangGraph or introduce a new Python agent framework

A1 may use the current `RuntimeProfile.visible_tool_names` / `build_setup_agent_tool_scope(...)` path as the provisional capability source.

## 4. Current Code Anchors

Primary implementation anchors:

| Concern | Current file / symbol |
| --- | --- |
| loop owner | `backend/rp/agent_runtime/executor.py::RpAgentRuntimeExecutor` |
| state schema | `backend/rp/agent_runtime/state.py::RpAgentRunState` |
| graph routing substrate | `backend/rp/agent_runtime/graph.py` |
| output inspection candidate | `RpAgentRuntimeExecutor._inspect_model_output(...)` |
| pseudo-tool detector candidate | `RpAgentRuntimeExecutor._looks_like_pseudo_tool_call_text(...)` |
| stream text/tool event path | `RpAgentRuntimeExecutor._call_model_stream(...)` |
| repair/tool failure policy | `backend/rp/agent_runtime/policies.py::RepairDecisionPolicy` |
| completion guard | `CompletionGuardPolicy` |
| reflection routing | `ReflectionTriggerPolicy` |
| tool execution | `backend/rp/agent_runtime/tools.py::RuntimeToolExecutor` |
| deterministic tool provider | `backend/rp/tools/setup_tool_provider.py::SetupToolProvider` |
| typed events | `backend/rp/agent_runtime/events.py::RuntimeEvent`, `TypedSseEventAdapter` |
| runtime contracts | `backend/rp/agent_runtime/contracts.py` |

Working-tree candidate code already contains some A1 behavior. Treat it as migration material:

- pseudo tool text filtering
- `pseudo_tool_retry_count`
- retry-budget terminal candidate `invalid_tool_output_retry_budget_exhausted`
- repeated recoverable tool failure terminal candidate `tool_recovery_budget_exhausted`
- typed SSE pseudo-text suppression candidate

Do not preserve candidate names or shapes merely because they exist. Reconcile them with this spec and active backend specs.

## 5. Required Architecture Outcome

After A1, the loop must be explainable as:

```text
CALL_MODEL
  -> INSPECT_OUTPUT
      -> real tool call: EXECUTE_TOOL
      -> public text and obligations satisfied: FINALIZE_TEXT
      -> pseudo/malformed/empty/recoverable issue: REPAIR_OUTPUT
      -> user input required: ASK_USER
      -> exhausted/non-recoverable: FAIL_STRUCTURED
  -> OBSERVE_TOOL_RESULT
      -> continue or finalize by explicit transition
```

`GRAPH_RECURSION_LIMIT` must not be the intended stop condition. Runtime `max_rounds` or a more specific terminal reason must stop bad paths first.

## 6. OutputInspector Contract

A1 should introduce an explicit typed inspection boundary. It can start as classes in `contracts.py` plus helper methods in `executor.py`; it does not require a large new module if that would create churn.

Minimum contract:

```text
SetupOutputClassification:
  real_tool_call
  normal_text
  pseudo_tool_text
  malformed_tool_call
  empty_output
  provider_schema_error
  mixed_text_and_tool_call

SetupOutputInspection:
  classification
  public_text_candidate
  tool_calls
  repair_observation
  private_diagnostics
  continue_reason_candidate
  finish_reason_candidate
```

Rules:

- `pseudo_tool_text` never becomes `assistant_text`.
- `pseudo_tool_text` never emits public `text_delta`.
- `normal_text` only finalizes after completion-guard obligations pass.
- `empty_output` cannot finalize as success.
- `malformed_tool_call` enters bounded repair or structured failure.
- `mixed_text_and_tool_call` must not double-emit unsafe text; real tool calls win for routing.
- provider/gateway errors must remain distinguishable from setup business failure.

If implementation keeps logic inside `_inspect_model_output(...)` in A1, it must still return/use a typed inspection result internally. The goal is a real boundary, not only a renamed helper.

## 7. SetupTurnLoop Transition Rules

A1 keeps transition rules inside `SetupTurnLoop`. Existing policy classes may remain only as small helpers.

Required transitions:

| Input | Transition | Required reason surface |
| --- | --- | --- |
| real tool call accepted | execute tools | `continue_reason = "tool_call_batch_pending"` |
| successful latest tool batch and follow-up needed | continue loop | `continue_reason = "tool_result_follow_up"` |
| recoverable latest tool failure | continue loop with observation | `continue_reason = "tool_failure_follow_up"` and `repair_route` |
| schema validation failure first time | repair obligation | `tool_schema_validation_retry` warning and `pending_obligation = repair_tool_call` |
| schema validation failure second time | terminal failure | `finish_reason = "tool_schema_validation_failed"` |
| unresolved repair obligation plus assistant text | block false success | `continue_reason = "completion_guard_retry"` or terminal `repair_obligation_unfulfilled` |
| repeated question without progress | reflection/terminal by budget | `completion_guard.reason = "repeated_question_without_progress"` |
| runtime round budget exhausted | terminal failure | `finish_reason = "max_rounds_exceeded"` |
| provider/upstream error | terminal failure | `finish_reason = "upstream_error"` |

Pure text remains valid only through:

- `completed_text`
- `awaiting_user_input`
- `continue_discussion`

It does not mean the setup step is complete.

## 8. Repair Budget And Finish-Reason Taxonomy

Active specs already freeze:

- schema auto-repair budget is exactly one correction attempt
- unresolved repair must not finalize as ordinary text success
- `continue_reason` and `finish_reason` are semantic surfaces above `next_action`

A1 must reconcile working-tree candidate terminal names with active specs before final implementation.

Accepted options:

1. Prefer existing active finish reasons when they preserve diagnostic clarity:
   - `tool_schema_validation_failed`
   - `repair_obligation_unfulfilled`
   - `max_rounds_exceeded`
   - `tool_error_unrecoverable`
   - `upstream_error`
   - `runtime_failed`
2. If A1 keeps or adds precise terminal reasons such as:
   - `invalid_tool_output_retry_budget_exhausted`
   - `tool_recovery_budget_exhausted`
   then the same A1 slice must update the authoritative backend loop/eval specs and tests so the taxonomy is not working-tree folklore.

Recommendation:

- Keep `tool_recovery_budget_exhausted` only if repeated same-class recoverable tool failures need a distinct eval/diagnostic bucket from `tool_error_unrecoverable`.
- Keep `invalid_tool_output_retry_budget_exhausted` only if pseudo tool text needs a distinct eval/diagnostic bucket from `repair_obligation_unfulfilled`.
- Otherwise map exhausted pseudo/malformed output repair to `repair_obligation_unfulfilled` and repeated recoverable tool failure to `tool_error_unrecoverable` with structured private diagnostics.

Do not silently introduce unlisted `finish_reason` strings.

## 9. SetupToolRuntime Error Observation

Structured tool errors should reach the model as observations before public terminal failure when recoverable.

Required behavior:

```text
RuntimeToolResult(success=False)
  -> ToolFailureClassifier
  -> RepairDecisionPolicy / transition helper
  -> pending_obligation or reflection_ticket
  -> normalized tool/error observation in messages
  -> next model call
```

Provider/tool error payloads must preserve:

- `code`
- `message`
- `failure_origin`
- `repair_strategy`
- `required_fields` when applicable
- `errors` / pydantic details when applicable
- public-safe summary only when terminal or user-required

User-visible terminal failure is allowed only after:

- repair budget exhausted
- failure is unrecoverable
- user input is required
- provider/runtime failure prevents continuation

## 10. EventSink / Typed SSE Requirements

A1 must preserve typed SSE event names:

- `thinking_delta`
- `text_delta`
- `tool_call`
- `tool_started`
- `tool_result`
- `tool_error`
- `usage`
- `error`
- `done`

Public transcript rules:

- natural finalized assistant text may be emitted
- typed tool activity may be emitted
- public-safe terminal errors may be emitted
- pseudo tool text, raw provider deltas, raw validation stacks, and repair debug JSON must not become assistant content

Stream-specific rule:

- buffered text chunks that later classify as pseudo tool text must be suppressed before public `text_delta`.
- if a real tool call arrives after pending text, pending text may flush only when it is safe natural text; unsafe mixed text/tool output must remain private.

## 11. State And Persistence Boundary

A1 may expose:

- `loop_trace`
- `continue_reason`
- `finish_reason`
- `completion_guard`
- `reflection_ticket`
- `last_failure`

through:

- `RpAgentTurnResult.structured_payload`
- runtime debug output
- eval / Langfuse / offline replay surfaces

A1 must not persist `loop_trace` or `continue_reason` into `SetupAgentRuntimeStateRecord.snapshot_json` or through `SetupAgentRuntimeStateService.persist_turn_governance(...)`.

Persisted governance remains limited to the active specs' governed surfaces such as:

- cognitive state / summary
- working digest
- retained tool outcomes
- compact summary

## 12. Tests Required For A1

Minimum focused tests:

1. Output inspection:
   - pseudo tool text is classified and not visible
   - mixed text + real tool call does not leak unsafe text
   - empty output cannot finalize success
   - malformed tool call routes to repair/failure

2. Loop transitions:
   - real tool call -> execute -> observation -> follow-up/stop
   - successful tool call can stop cleanly without graph recursion
   - repeated question / no-progress path stops by runtime max rounds before LangGraph recursion
   - `next_action` remains routing, `continue_reason` / `finish_reason` carry semantics

3. Repair:
   - schema validation failure gets one retry
   - unresolved `repair_tool_call` blocks explanatory false success
   - ask-user schema branch finalizes as `awaiting_user_input`
   - repeated recoverable non-schema failure either maps to accepted taxonomy or updates active specs

4. EventSink:
   - stream pseudo tool text emits no public `text_delta`
   - typed tool events remain stable
   - terminal error event is public-safe

5. Persistence:
   - runtime-governance snapshot does not grow `loop_trace` or `continue_reason`

Likely test files:

- `backend/rp/tests/test_setup_agent_runtime_executor.py`
- `backend/rp/tests/test_setup_agent_runtime_policies.py`
- `backend/rp/tests/test_setup_agent_runtime_state_service.py`
- `backend/rp/tests/test_eval_setup_cognitive_cases.py`
- add `backend/rp/tests/test_setup_agent_output_inspector.py` only if `OutputInspector` becomes a separate importable unit

## 13. Suggested Implementation Order

Follow this order to reduce churn:

1. Contracts first:
   - add typed output inspection contracts in `contracts.py` or a small runtime-local contract module
   - update state typing only where the loop already carries the fields

2. Output inspection:
   - make `_inspect_model_output(...)` produce/consume `SetupOutputInspection`
   - keep pseudo-tool detector as a detector, not the architecture owner
   - ensure stream text suppression follows the same classification rule

3. Loop transition cleanup:
   - map inspection results to `next_action`, `continue_reason`, `finish_reason`, `completion_guard`, and `reflection_ticket`
   - keep transition helpers small and loop-owned

4. Repair/error observation:
   - ensure recoverable tool failures become observations before public terminal failure
   - reconcile repeated-failure taxonomy with active specs

5. Events and persistence:
   - verify typed SSE public/private boundary
   - verify `loop_trace` remains result/debug/eval scoped

6. Tests:
   - add focused tests for bad paths before broad refactor
   - update eval expectations only after finish-reason taxonomy is settled

## 14. Check Commands

After A1 implementation:

```powershell
python -m pytest backend/rp/tests/test_setup_agent_runtime_executor.py backend/rp/tests/test_setup_agent_runtime_policies.py
python -m pytest backend/rp/tests/test_setup_agent_runtime_state_service.py
python -m pytest backend/rp/tests/test_eval_setup_cognitive_cases.py
python .\.trellis\scripts\task.py validate 05-11-setup-agent-architecture-improve
git diff --check -- backend/rp .trellis/tasks/05-11-setup-agent-architecture-improve .trellis/spec/backend
```

If A1 touches active backend specs, run the focused tests named by those specs.

## 15. Stop / `$grill-me` Triggers

Stop and ask before implementing if A1 would require any of these:

- changing review/commit/readiness semantics
- changing setup stage handoff semantics
- exposing `setup.world_background.*`
- moving business schema validation into a capability plan
- persisting loop trace/cognition as product truth
- replacing LangGraph or introducing a new Python agent framework
- changing provider API behavior based on non-primary sources
- choosing a new user-visible error taxonomy that affects product copy or UI semantics

No such blocker is known at the time this spec is written.
