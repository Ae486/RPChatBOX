# RP Setup Agent Loop Semantics ReAct Trace

> Executable contract for SetupAgent runtime-v2 semantic turn-loop ordering, explicit continue/finish reasons, and a thin structured ReAct trace above the current LangGraph node graph.

## Scenario: SetupAgent Keeps Semantic Loop Meaning Explicit Above LangGraph

### 1. Scope / Trigger

- Trigger: add or edit `backend/rp/agent_runtime/executor.py`, `backend/rp/agent_runtime/graph.py`, `backend/rp/agent_runtime/state.py`, `backend/rp/agent_runtime/contracts.py`, `backend/rp/agent_runtime/policies.py`, `backend/rp/agent_runtime/adapters.py`, `backend/rp/services/setup_agent_execution_service.py`, `backend/rp/graphs/setup_graph_runner.py`, or setup eval/trace capture code when the change affects per-turn loop order, graph-routing meaning, continue/finish semantics, or runtime trace surfaces.
- Applies only to setup/prestory runtime-v2 per-turn execution.
- This slice is internal runtime semantics only. It does not change `SetupWorkspace` business truth, prior-stage handoff packets, stage-local digest/compact policy, explicit user commit authority, or outer preset stage progression rules.
- This slice must optimize and formalize the existing setup runtime loop. It must not be framed or implemented as a rewrite to a different agent framework.

### 2. Signatures

- `SetupLoopSemanticStep`
  - `prepare_input`
  - `derive_turn_goal`
  - `plan_step_slice`
  - `build_model_request`
  - `call_model`
  - `inspect_model_output`
  - `execute_tools`
  - `apply_tool_results`
  - `assess_progress`
  - `reflect_if_needed`
  - `finalize_success`
  - `finalize_failure`
- `SetupLoopContinueReason`
  - `tool_call_batch_pending`
  - `tool_result_follow_up`
  - `tool_failure_follow_up`
  - `commit_reassess_reflection`
  - `completion_guard_retry`
  - `reflection_retry`
- `SetupLoopFinishReason`
  - `completed_text`
  - `awaiting_user_input`
  - `continue_discussion`
  - `tool_error_unrecoverable`
  - `tool_schema_validation_failed`
  - `repair_obligation_unfulfilled`
  - `max_rounds_exceeded`
  - `upstream_error`
  - `runtime_execution_failed`
  - `runtime_failed`
- `SetupOutputClassification`
  - `real_tool_call`
  - `normal_text`
  - `pseudo_tool_text`
  - `malformed_tool_call`
  - `empty_output`
  - `provider_schema_error`
  - `mixed_text_and_tool_call`
- `SetupOutputInspection`
  - `classification: SetupOutputClassification`
  - `public_text_candidate: str`
  - `tool_calls: list[RuntimeToolCall]`
  - `repair_observation: dict[str, Any] | None`
  - `private_diagnostics: dict[str, Any]`
  - `continue_reason_candidate: str | None`
  - `finish_reason_candidate: str | None`
- `SetupModelGatewayDiagnostics`
  - `failure_layer: Literal["model_gateway"]`
  - `failure_kind: str`
  - `message: str`
  - `provider_error_type: str | None`
  - `private_details: dict[str, Any]`
- `SetupEventSinkSnapshot`
  - `public_event_types: list[str]`
  - `private_event_surfaces: list[str]`
  - `transcript_boundary: str`
- `SetupReActTraceFrame`
  - `round_no: int`
  - `decision_site: Literal["inspect_model_output", "assess_progress", "reflect_if_needed", "finalize_success", "finalize_failure"]`
  - `goal: dict[str, Any] | None`
    - derived from `SetupTurnGoal`
  - `plan: dict[str, Any] | None`
    - derived from `SetupWorkingPlan`
  - `action: dict[str, Any]`
    - `kind: Literal["assistant_text", "tool_batch", "empty", "error"]`
    - `tool_names: list[str]`
    - `assistant_text_kind: Literal["question", "text", "empty"] | None`
  - `observation: dict[str, Any]`
    - `tool_result_count: int`
    - `tool_failure_count: int`
    - `updated_refs: list[str]`
    - `warnings: list[str]`
  - `reflection: dict[str, Any] | None`
    - derived from `SetupReflectionTicket`
  - `decision: dict[str, Any]`
    - `next_action: str`
    - `continue_reason: SetupLoopContinueReason | None`
    - `finish_reason: SetupLoopFinishReason | None`
    - `repair_route: str | None`
- `RpAgentRunState`
  - add `continue_reason: str | None`
  - add `loop_trace: list[dict[str, Any]]`
  - add `output_inspection: dict[str, Any] | None`
  - add `model_gateway_diagnostics: dict[str, Any] | None`
- `RpAgentTurnResult.structured_payload`
  - add `loop_trace: list[SetupReActTraceFrame]`
  - continue to expose:
    - `context_report`
    - `turn_goal`
    - `working_plan`
    - `pending_obligation`
    - `last_failure`
    - `reflection_ticket`
    - `completion_guard`
    - `working_digest`
    - `tool_outcomes`
    - `compact_summary`
    - `repair_route`
    - `output_inspection`
    - `event_sink`
    - `model_gateway_diagnostics`
- `RuntimeEvent`
  - keep current typed-SSE event names unchanged:
    - `thinking_delta`
    - `text_delta`
    - `tool_call`
    - `tool_started`
    - `tool_result`
    - `tool_error`
    - `usage`
    - `error`
    - `done`

### 3. Contracts

#### 3.1 Outer Harness And Inner Loop Stay Separate

- `backend/rp/graphs/setup_graph_runner.py` remains the outer setup harness:
  - `load_workspace`
  - `build_context`
  - `run_turn`
- Only `run_turn` owns the inner per-turn agent loop described in this slice.
- Outer harness status such as stage switching, explicit user commit, and step handoff remains outside this loop-semantic contract.

#### 3.2 Semantic Loop Order Is Fixed

- The semantic turn loop order is:
  1. `prepare_input`
  2. `derive_turn_goal`
  3. `plan_step_slice`
  4. `build_model_request`
  5. `call_model`
  6. `inspect_model_output`
  7. `execute_tools` when tool calls exist
  8. `apply_tool_results` when tool results exist
  9. `assess_progress`
  10. `reflect_if_needed` when a reflection/guard route is active
  11. `finalize_success` or `finalize_failure`
- The semantic loop must stay explicit even though LangGraph executes it through node routing.
- The current graph-node mapping is strict:

| Semantic step | Current node/function | Notes |
|---|---|---|
| `prepare_input` | `prepare_input` | injects system prompt, prior messages, latest user request |
| `derive_turn_goal` | `derive_turn_goal` | derives goal from pending obligation, invalidation, user request, current draft state |
| `plan_step_slice` | `plan_step_slice` | derives missing info, discussion actions, patch/question/commit targets |
| `build_model_request` | `build_model_request` | compiles visible tools plus runtime overlay message |
| `call_model` | `call_model` | executes normal or streaming model request |
| `inspect_model_output` | `inspect_model_output` | interprets assistant text and tool calls, chooses immediate route |
| `execute_tools` | `execute_tools` | runs accepted tool calls and emits tool lifecycle events |
| `apply_tool_results` | `apply_tool_results` | appends tool messages, updates cognitive state, merges retained outcomes |
| `assess_progress` | `assess_progress` | decides follow-up, repair, reflect, or finish after observations |
| `reflect_if_needed` | `reflect_if_needed` | handles retry/ask/block-commit reflection ticket routing |
| `finalize_success` | `finalize_success` | emits `done`, returns completed status |
| `finalize_failure` | `finalize_failure` | emits `error` when needed, then `done`, returns failed status |

#### 3.3 `next_action` Is Graph Routing, Not The Semantic Reason

- `next_action` remains a low-level LangGraph route token.
- Allowed `next_action` values in this slice are limited to:
  - `execute_tools`
  - `derive_turn_goal`
  - `reflect_if_needed`
  - `finalize_success`
  - `finalize_failure`
- `next_action` must not be treated as the user-facing explanation of why the loop continued or stopped.
- `continue_reason` is the higher-level semantic explanation for same-turn continuation.
- `finish_reason` is the higher-level terminal explanation for this turn.

#### 3.4 Continue Reasons Are Explicit And Thin

- `tool_call_batch_pending`
  - set when `inspect_model_output` sees tool calls and accepts them for execution
  - implies `next_action = "execute_tools"`
- `tool_result_follow_up`
  - set when `assess_progress` sees a non-failing latest tool batch and the turn should continue with new observations
  - implies `next_action = "derive_turn_goal"`
- `tool_failure_follow_up`
  - set when `assess_progress` sees a recoverable or discussion-continue tool failure and the turn should continue
  - implies `next_action = "derive_turn_goal"` unless a reflection ticket is also raised
  - the precise recovery flavor is carried by `repair_route`, not by exploding the continue-reason taxonomy
- `commit_reassess_reflection`
  - set when the runtime blocks a premature commit proposal or another block-commit reflection route is raised
  - implies `next_action = "reflect_if_needed"`
- `completion_guard_retry`
  - set when the model tries to finish but `CompletionGuardPolicy` requires retry/reflect instead
  - examples:
    - unresolved `repair_tool_call`
    - repeated question without progress
    - empty terminal output
  - implies `next_action = "reflect_if_needed"`
- `reflection_retry`
  - set when `reflect_if_needed` clears the current reflection ticket and resumes the loop
  - implies `next_action = "derive_turn_goal"`
- `reconcile_after_user_edit` and other step-local intent labels stay represented by `turn_goal.goal_type` or `pending_obligation.obligation_type`; they must not create extra continue-reason enums in this slice.

#### 3.5 Finish Reasons Are Turn-Local, Not Step/Harness Outcomes

- `RpAgentTurnResult.status` remains the coarse terminal state:
  - `completed`
  - `failed`
- `finish_reason` carries the detailed turn-local outcome.
- `completed_text`
  - means the current turn ended with ordinary text and no blocking runtime obligation
  - does **not** mean the current setup step is complete
- `awaiting_user_input`
  - means the turn ended because the user must answer or confirm something next
- `continue_discussion`
  - means the turn ended intentionally while the current setup step remains open
  - this is a valid successful turn ending, not a failure
- `tool_error_unrecoverable`
  - terminal tool failure category
- `tool_schema_validation_failed`
  - terminal schema/tool-input validation failure after the runtime retry budget is exhausted
- `repair_obligation_unfulfilled`
  - terminal failure when the runtime required a corrected repair action but the assistant attempted to finish instead
- `max_rounds_exceeded`
  - terminal loop failure on round-budget exhaustion
- `upstream_error`
  - model-stream or upstream provider error already surfaced during `call_model`
- `runtime_execution_failed`
  - top-level runtime safety-net failure outside the normal graph result path
- `runtime_failed`
  - generic fallback when the runtime cannot produce a stronger finish reason
- Commit acceptance, stage handoff, activation success, or review-success labels do not belong in this turn-loop finish taxonomy. Those belong to outer harness or other runtime slices.

#### 3.6 OutputInspector Owns Model-Output Classification Before Transcript Visibility

- `inspect_model_output` must first convert the normalized provider message into a typed `SetupOutputInspection`.
- The inspector is the only boundary that decides whether raw assistant text is a public candidate or private invalid/mixed output.
- Classification rules:
  - `real_tool_call`: valid tool calls and no public assistant text.
  - `mixed_text_and_tool_call`: valid tool calls plus any assistant text; the text remains private and tool calls drive routing.
  - `pseudo_tool_text`: text that looks like a provider/tool-call transcript but contains no real tool call; it must not enter `assistant_text`.
  - `malformed_tool_call`: provider supplied tool-call structure exists but has missing tool name, non-object arguments, or invalid JSON arguments; no malformed call executes.
  - `empty_output`: no valid tool call and no non-blank text; it cannot finalize as success.
  - `provider_schema_error`: upstream/provider failure already attributed during model call.
  - `normal_text`: non-empty text with no tool calls or invalid-tool pattern; it still must pass completion guards before finalization.
- `public_text_candidate` may populate `assistant_text` only for `normal_text`.
- `tool_calls` may populate `pending_tool_calls` only for `real_tool_call` and `mixed_text_and_tool_call`.
- `repair_observation` / `private_diagnostics` are debug/eval material. They must not be emitted as public assistant content.
- Invalid output retry exhaustion must use active finish reasons:
  - pseudo or malformed output exhaustion maps to `repair_obligation_unfulfilled`
  - repeated recoverable tool failure maps to `tool_error_unrecoverable` with private details
- Stream mode must follow the same boundary:
  - pending text may be buffered before public emission
  - once a real `tool_call` appears in the same provider response, all pending and later text from that response stays private
  - typed `tool_call`, `tool_started`, `tool_result`, `tool_error`, `error`, and `done` event names stay unchanged

#### 3.7 "No Tool Call" Is Only One Inspect/Assess Branch

- The absence of tool calls must not be treated as a standalone product feature or success proof.
- `inspect_model_output` without tool calls must always go through completion-guard semantics:
  - finalize successfully when the guard allows it
  - otherwise reflect/retry
- The `inspect_model_output` completion-guard call must receive the same guard evidence used by the later no-latest-tool `assess_progress` branch:
  - prior assistant questions from current conversation history
  - current `working_digest`
  - current action expectation when present
  This prevents an initial text-only response from bypassing repeated-question or compact-readback guards that would have fired after an observation cycle.
- `assess_progress` without a latest tool batch uses the same completion-guard path.
- Pure-text termination remains valid, but only through an explicit `finish_reason` such as:
  - `awaiting_user_input`
  - `completed_text`
  - `continue_discussion`

#### 3.8 ReAct Trace Is Runtime-Authored, Not Hidden Reasoning

- `loop_trace` is a thin runtime-authored decision trace, not chain-of-thought capture.
- Every turn must produce trace frames at the decision sites that materially change loop routing:
  - after `inspect_model_output`
  - after `assess_progress`
  - after `reflect_if_needed`
  - at finalization
- Trace fields must be derived from existing structured runtime state:
  - `goal` from `turn_goal`
  - `plan` from `working_plan`
  - `action.tool_names` from current tool-call batch
  - `observation` from `latest_tool_batch`, retained outcome summaries, warnings, and state-invalidated flags
  - `reflection` from `reflection_ticket`
  - `decision` from `next_action`, `continue_reason`, `finish_reason`, and `repair_route`
- Trace summaries must stay terse and contract-driven:
  - no free-form model reasoning dump
  - no token-by-token thought transcript
  - no raw retry process history
- `repair_route` should continue to reuse the current failure-category vocabulary:
  - `auto_repair`
  - `ask_user`
  - `continue_discussion`
  - `block_commit`
  - `unrecoverable`

#### 3.9 Structured Payload, Runtime Debug, And Events Stay Additive

- Final structured payload must expose `loop_trace` additively alongside the current cognition fields.
- Final structured payload may expose `output_inspection` additively for debug/eval attribution.
- Final structured payload may expose `event_sink` and `model_gateway_diagnostics` for debug/eval attribution.
- Setup runtime debug surfaces may mirror `loop_trace` and `continue_reason`, but must not require consumers to inspect raw LangGraph state transitions.
- Setup runtime result/debug/eval surfaces may expose `context_report`, but it must remain a transient runtime explanation rather than durable setup truth.
- `loop_trace` and `continue_reason` are turn-transient loop-semantics surfaces:
  - they may appear in `RpAgentTurnResult.structured_payload`
  - they may appear in setup runtime debug output
  - they may appear in eval / Langfuse / offline replay artifacts
  - they must not be added to `SetupAgentRuntimeStateRecord.snapshot_json`
  - they must not be written through `SetupAgentRuntimeStateService.persist_turn_governance(...)`
- `output_inspection`, `event_sink`, and `model_gateway_diagnostics` are also turn-transient/debug surfaces and must not be persisted into `SetupAgentRuntimeStateRecord.snapshot_json`.
- Existing typed-SSE/runtime event names remain stable. This slice may enrich final payload/debug/Langfuse metadata, but must not replace the current `tool_*`, `error`, `done`, or stream-delta surfaces with verbose trace events.

#### 3.10 ModelGateway And EventSink Separate Provider Failure From Transcript Visibility

- The runtime model-gateway boundary owns provider request errors, stream provider errors, stream exceptions, stream payload parse errors, streamed tool-call reconstruction, usage capture, and provider-facing diagnostics.
- Provider/gateway failures must normalize to:
  - `failure_layer = "model_gateway"`
  - public error type `model_gateway_failed`
  - terminal `finish_reason = "upstream_error"`
  - `SetupOutputInspection.classification = "provider_schema_error"`
- Provider/gateway failures must not be routed as setup business failures such as `tool_error_unrecoverable`, `tool_schema_validation_failed`, or `repair_obligation_unfulfilled`.
- `SetupModelGatewayDiagnostics.private_details` may retain raw provider errors, malformed stream payload details, private stream events, and provider exception metadata for trace/eval/logging.
- Public SSE must go through `SetupEventSink` / `TypedSseEventAdapter`. The event sink must:
  - preserve typed event names listed in `RuntimeEvent`
  - emit only allowlisted payload fields per event type
  - keep `thinking_delta` public with only `delta`
  - keep `text_delta` public with only `delta`
  - keep `tool_call`, `tool_started`, `tool_result`, `tool_error`, `usage`, `error`, and `done` public with their stable public fields
  - filter raw provider deltas, provider debug payloads, stack traces, private diagnostics, and gateway diagnostics from public SSE
- Unknown provider stream event types are private by default. They may contribute to `model_gateway_diagnostics`, but must not produce user-visible typed SSE.

#### 3.11 Boundary With Existing Context-Governance Slices Must Stay Clean

- `working_digest`, `tool_outcomes`, and `compact_summary` remain governed by [RP Setup Agent Stage-Local Context Governance](./rp-setup-agent-stage-local-context-governance.md).
- Prior-stage accepted truth still comes only from [RP Setup Agent Prior-Stage Handoff Context](./rp-setup-agent-prior-stage-handoff-context.md).
- This slice may read those surfaces to explain loop decisions, but it must not widen their persistence scope, duplicate their storage rules, or fold them into prior-stage handoff packets.
- In particular, this slice must not promote loop-semantic trace data into durable stage cognition:
  - `working_digest`, `tool_outcomes`, and `compact_summary` are the persisted governance surfaces
  - `loop_trace`, `continue_reason`, and other turn-local routing explanation fields stay runtime-transient

### 4. Validation & Error Matrix

- `inspect_model_output` sees tool calls and no blocked commit proposal -> `continue_reason = "tool_call_batch_pending"`, `next_action = "execute_tools"`, `finish_reason = None`
- `inspect_model_output` sees valid tool calls plus assistant text -> classify as `mixed_text_and_tool_call`, keep text private, set `continue_reason = "tool_call_batch_pending"`, `next_action = "execute_tools"`
- `inspect_model_output` sees pseudo tool text with no real tool call -> classify as `pseudo_tool_text`, keep text private, set `continue_reason = "completion_guard_retry"`, `next_action = "reflect_if_needed"`; after bounded retry exhaustion, fail with `repair_obligation_unfulfilled`
- `inspect_model_output` sees malformed tool-call arguments or missing tool name -> classify as `malformed_tool_call`, execute no tool, set `continue_reason = "completion_guard_retry"`, `next_action = "reflect_if_needed"`; after bounded retry exhaustion, fail with `repair_obligation_unfulfilled`
- `inspect_model_output` sees empty output -> classify as `empty_output`, execute no tool, set `continue_reason = "completion_guard_retry"`, `next_action = "reflect_if_needed"`
- `inspect_model_output` sees a blocked commit proposal -> clear pending tool calls, set reflection ticket, `continue_reason = "commit_reassess_reflection"`, `next_action = "reflect_if_needed"`
- no tool calls, assistant text is a user-facing question, no blocking obligation -> `next_action = "finalize_success"`, `finish_reason = "awaiting_user_input"`
- no tool calls, assistant text is ordinary text, no blocking obligation, current cognitive state is clean -> `next_action = "finalize_success"`, `finish_reason = "completed_text"`
- no tool calls, assistant text is ordinary text, but current cognitive state is invalidated / not review-ready / still has open issues -> `next_action = "finalize_success"`, `finish_reason = "continue_discussion"`
- no tool calls while `pending_obligation.obligation_type == "repair_tool_call"` remains unresolved -> `continue_reason = "completion_guard_retry"`, `next_action = "reflect_if_needed"`, must not finalize
- same normalized user-facing question repeats without new progress, including on the first text-only model response before any tool call -> `continue_reason = "completion_guard_retry"`, `completion_guard.reason = "repeated_question_without_progress"`, `next_action = "reflect_if_needed"`
- latest tool batch succeeds under round budget -> `continue_reason = "tool_result_follow_up"`, `next_action = "derive_turn_goal"`
- latest tool batch fails with recoverable failure and no reflection ticket -> `continue_reason = "tool_failure_follow_up"`, `repair_route` derives from `last_failure.failure_category`, `next_action = "derive_turn_goal"`
- latest tool batch fails with `block_commit` / commit-readiness reflection route -> `continue_reason = "commit_reassess_reflection"`, `next_action = "reflect_if_needed"`
- schema/tool-input validation fails after retry budget is exhausted -> `next_action = "finalize_failure"`, `finish_reason = "tool_schema_validation_failed"`
- reflection retry is required while a repair obligation remains unresolved and the repair retry budget is already exhausted -> `next_action = "finalize_failure"`, `finish_reason = "repair_obligation_unfulfilled"`
- `round_no >= max_rounds` during repair or reflection routing -> `next_action = "finalize_failure"`, `finish_reason = "max_rounds_exceeded"`
- upstream/provider stream error is already present after `call_model` -> `finish_reason = "upstream_error"`, `next_action = "finalize_failure"`
- malformed provider stream JSON or non-object `data:` payload -> public error `model_gateway_failed`, code `provider_stream_parse_error`, `finish_reason = "upstream_error"`, private diagnostics retain parse details, and no buffered text is emitted publicly
- provider request exception before any model output -> public error `model_gateway_failed`, code `provider_request_error`, `finish_reason = "upstream_error"`, private diagnostics retain provider exception type/message
- unknown/raw provider stream event type -> public SSE emits nothing for that event, private diagnostics may record it under model-gateway private events
- unexpected exception escapes `run_stream()` safety net -> final result `finish_reason = "runtime_execution_failed"`
- `next_action` is outside the allowed node-label set -> treat as runtime bug, fail the turn with `finish_reason = "runtime_failed"` rather than silently routing to an undefined branch

### 5. Good / Base / Bad Cases

- Good: the model emits one draft patch tool call, the tool succeeds, `assess_progress` records `continue_reason = "tool_result_follow_up"`, the next round updates the goal/plan with fresh observations, and the turn later ends with `finish_reason = "continue_discussion"` because the step is still open.
- Good: a provider stream emits text before a real tool call; the text is buffered and then discarded from public SSE once the tool call arrives, while the typed tool events still appear.
- Good: a provider stream emits malformed JSON after buffered text; the turn fails as `upstream_error`, public SSE emits a safe gateway error, and the buffered text stays private.
- Base: a provider stream emits `thinking_delta`; public SSE keeps the event name and `delta`, while any raw/debug/private fields are stripped.
- Base: the model emits one targeted clarification question with no tool call, `inspect_model_output` finalizes successfully, and the turn ends with `finish_reason = "awaiting_user_input"`.
- Bad: treating any no-tool response as proof that the setup step is finished, exposing pseudo tool text as assistant content, flushing mixed-output text to public SSE before `OutputInspector` can classify it, or leaking raw provider deltas through typed SSE.

### 6. Tests Required

- `backend/rp/tests/test_setup_agent_runtime_executor.py`
  - assert the semantic loop-to-graph mapping remains intact for inspect -> execute-tools, inspect -> reflect, inspect -> finalize, assess -> derive-goal, assess -> reflect, and reflect -> derive-goal routes
  - assert `SetupOutputInspection` classifies pseudo tool text, malformed tool calls, empty output, mixed text/tool output, and normal text
  - assert pseudo tool text and mixed-output text never become public assistant text
  - assert stream mixed text/tool output suppresses pre-tool-call pending `text_delta` while preserving typed tool events
  - assert `SetupEventSink` preserves typed event names, including `thinking_delta`, while filtering raw/debug/private payload keys
  - assert provider stream errors, malformed stream payloads, and provider request exceptions are classified as `model_gateway` / `upstream_error`
  - assert model-gateway private diagnostics are present in structured payload but absent from public SSE
  - assert `loop_trace` is present in final structured payload and carries `continue_reason` / `finish_reason` without dropping existing cognition fields
  - assert typed-SSE event names remain unchanged and trace is additive rather than replacing current event types
  - assert an initial text-only repeated question is blocked at `inspect_model_output`, reflected, and finalized with an explicit failure when the round budget is exhausted
- `backend/rp/tests/test_setup_agent_runtime_policies.py`
  - assert `completed_text`, `awaiting_user_input`, and `continue_discussion` remain correctly separated
  - assert repeated-question-without-progress routes through `completion_guard_retry`
  - assert `repair_obligation_unfulfilled` and `max_rounds_exceeded` remain explicit terminal reasons
- `backend/rp/tests/test_eval_trace_capture.py`
  - assert setup runtime trace/export surfaces can retain `loop_trace` semantics for offline replay or inspection
- `backend/rp/tests/test_setup_agent_runtime_state_service.py`
  - assert persisted runtime-governance snapshots do not grow `loop_trace` or `continue_reason` fields
- `backend/rp/tests/test_eval_setup_cognitive_cases.py`
  - assert finish-reason and repair-route expectations remain aligned after the loop taxonomy is formalized
- `backend/tests/test_rp_setup_agent_api.py`
  - assert setup runtime debug output can reconstruct the current loop decision surface without exposing raw LangGraph implementation details

### 7. Wrong vs Correct

#### Wrong

- Treat `next_action` as the semantic explanation consumed by users, eval, or future harness slices.
- Treat "no tool call" as a standalone completion feature instead of one inspect/guard branch.
- Treat regex pseudo-tool detection as the architecture owner instead of an implementation detail behind `SetupOutputInspection`.
- Flush stream text publicly before knowing whether the same provider response also contains a real tool call.
- Treat malformed provider stream payloads as empty assistant output or setup repair work.
- Pass raw provider stream events, stack traces, or gateway diagnostics through public typed SSE.
- Mix outer harness outcomes such as commit acceptance or stage handoff into per-turn loop finish reasons.
- Emit verbose hidden-reasoning traces or replay raw retry process as if that were the ReAct trace.
- Persist `loop_trace` or `continue_reason` into setup cognitive snapshots as if debug/eval trace were product truth.

#### Correct

- Keep graph routing separate from semantic `continue_reason` and `finish_reason`.
- Treat no-tool output as one branch that still passes through completion-guard semantics.
- Put all normalized model output through `SetupOutputInspection` before tool execution or public transcript visibility.
- Keep mixed-output text private and let real tool calls drive routing.
- Normalize provider/gateway failures before setup business policy sees them, and terminate with `upstream_error`.
- Keep `SetupEventSink` as the public transcript gate; expose raw provider/gateway diagnostics only through private result/debug/eval surfaces.
- Keep turn-local finish reasons focused on the agent loop; leave commit/handoff/stage outcomes to outer setup-harness slices.
- Emit a thin runtime-authored `loop_trace` that is useful for policy, debug, and eval without becoming chain-of-thought.
- Keep loop-semantic trace surfaces transient; persist only the governed stage-local context artifacts defined by the context-governance slice.
