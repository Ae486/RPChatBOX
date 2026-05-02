# RP Setup Agent Action Decision Policy

> Executable contract for a lightweight SetupAgent action-decision policy: runtime-authored expectations for high-certainty cases where the model must read draft detail before answering or writing after stage-local compaction.

## Scenario: SetupAgent Uses Compact Recovery Hints Before Acting On Missing Exact Detail

### 1. Scope / Trigger

- Trigger: add or edit `backend/rp/agent_runtime/contracts.py`, `backend/rp/agent_runtime/state.py`, `backend/rp/agent_runtime/policies.py`, `backend/rp/agent_runtime/executor.py`, or setup runtime tests when the change affects whether SetupAgent may finalize with text, execute a tool batch, or must first observe a specific setup tool result.
- Applies only to setup/prestory runtime-v2 per-turn execution.
- This slice is internal agent capability work. It does not change `SetupWorkspace`, draft schema, commit/review contracts, typed-SSE event names, prior-stage handoff packets, or setup tool provider contracts.
- This slice must stay lightweight:
  - no new durable state table
  - no broad semantic classifier
  - no extra task manager
  - no replacement for LangGraph
  - no new multi-agent planner

### 2. Source Policy

- Borrow from Claude Code:
  - explicit continue/stop decisions after model output
  - guard-triggered retry instead of accepting false success
  - tool observations as the source of recoverable detail
- Borrow from Pi mono:
  - small loop-level policy hooks around an existing agent loop
  - context transformation before provider request, not a separate state subsystem
- Borrow from OpenAI Agents SDK / Anthropic Claude Code SDK:
  - guardrails and tracing as harness surfaces around agent actions
- Borrow from LangGraph:
  - graph routing remains execution substrate
- Customize for RP setup:
  - exact compacted setup detail must be recovered from current draft truth through `setup.read.draft_refs`
  - setup draft truth remains the retrieval/detail store after compact
- Do not copy:
  - Claude Code's full coding-agent recovery taxonomy
  - Pi's file-operation compaction details
  - generic agent handoff frameworks
  - LangGraph's generic "no tool call means end" rule as sufficient setup correctness

### 3. Signatures

- `SetupActionExpectation`
  - `expectation_type: Literal["read_draft_refs"]`
  - `reason: str`
  - `required_tools: list[str]`
  - `draft_refs: list[str]`
  - `allow_text_finalize: bool = False`
  - `requires_observation_first: bool = True`
- `ActionDecisionPolicy.assess(...) -> SetupActionExpectation | None`
  - inputs:
    - `user_prompt: str`
    - `turn_goal: SetupTurnGoal | None`
    - `working_plan: SetupWorkingPlan | None`
    - `pending_obligation: SetupPendingObligation | None`
    - `compact_summary: SetupContextCompactSummary | None`
    - `tool_results: list[RuntimeToolResult]`
- `ActionDecisionPolicy.tool_batch_violation(...) -> dict[str, Any] | None`
  - inputs:
    - `expectation: SetupActionExpectation | None`
    - `tool_names: list[str]`
- `CompletionGuardPolicy.assess(...)`
  - add optional input:
    - `action_expectation: SetupActionExpectation | None = None`
- `RpAgentRunState`
  - add `action_expectation: dict[str, Any] | None`
- `RpAgentTurnResult.structured_payload`
  - add `action_expectation`
- `SetupReActTraceFrame.decision`
  - may include `action_expectation` additively

### 4. Contracts

#### 4.1 Action Expectation Is Turn-Transient

- `action_expectation` is runtime-private and turn-transient.
- It may appear in:
  - runtime overlay prompt message
  - `RpAgentTurnResult.structured_payload`
  - `loop_trace`
  - eval/debug/Langfuse metadata
- It must not be written into `SetupWorkspace`.
- It must not be written into `SetupAgentRuntimeStateRecord.snapshot_json`.
- It must not replace `working_digest`, `tool_outcomes`, or `compact_summary`.

#### 4.2 First Enforced Expectation Is Compact Draft Detail Readback

- `ActionDecisionPolicy.assess(...)` returns a `read_draft_refs` expectation only when all are true:
  - `compact_summary` exists
  - `compact_summary.draft_refs` or `compact_summary.recovery_hints[*].ref` has at least one ref
  - the user prompt asks for exact, full, concrete, previous, current, or draft detail
  - no successful same-turn `setup.read.draft_refs` result has already observed the relevant ref
- If those conditions are not met, the policy returns `None`.
- The policy must prefer high precision over recall. Ambiguous design/opinion questions must remain pure-text capable.

#### 4.3 Existing Repair And Ask-User Semantics Stay Owned By Existing Policies

- `repair_tool_call`, `ask_user_for_missing_info`, `reassess_commit_readiness`, and `reconcile_after_user_edit` remain governed by:
  - `RepairDecisionPolicy`
  - `CompletionGuardPolicy`
  - `ReflectionTriggerPolicy`
- This slice must not duplicate or replace those policies.
- `ActionDecisionPolicy` may inspect `pending_obligation` but should not create new obligations for already-covered repair cases.

#### 4.4 Text Finalization Is Blocked Only For Active Expectations

- If `action_expectation.expectation_type == "read_draft_refs"` and `allow_text_finalize == false`, text-only finalization must be blocked.
- Blocking shape:
  - `completion_guard.allow_finalize = false`
  - `completion_guard.reason = "required_draft_ref_read_missing"`
  - `completion_guard.required_action = "retry"`
  - `reflection_ticket.trigger = "tool_failure"`
  - `reflection_ticket.required_decision = "retry"`
  - `continue_reason = "completion_guard_retry"`
- This is a retry within the existing loop, not a user-facing failure.

#### 4.5 Tool Batches That Skip Required Readback Are Blocked

- If a `read_draft_refs` expectation is active and no relevant successful read has happened:
  - a tool batch containing no `setup.read.draft_refs` call must be blocked before execution
  - a mixed batch containing `setup.read.draft_refs` plus mutation tools must be blocked before execution
- The required read must happen as an observation-first batch.
- The runtime should then retry so the model can act with the read result visible.

#### 4.6 Once The Read Observation Exists, The Expectation Clears

- A successful same-turn result from `setup.read.draft_refs` clears the `read_draft_refs` expectation when it overlaps the expected refs.
- Observed refs may be read from either `RuntimeToolResult.structured_payload` or JSON `content_text`, including nested `content_payload` / `result_payload` wrappers produced by provider adapters.
- After the read succeeds, normal `CompletionGuardPolicy`, tool repair, commit guard, and finish-reason behavior applies.
- The runtime does not require repeated reads for the same refs in the same turn.

#### 4.7 Runtime Overlay Must Be Explicit But Small

- If `action_expectation` exists, `_runtime_overlay_message(...)` must include it in the JSON payload.
- The overlay must include a short instruction:
  - if `action_expectation` requires `setup.read.draft_refs`, call that tool before answering or writing exact draft details.
- The overlay must not expand full draft payloads or compact history.

### 5. Validation & Error Matrix

- compact summary absent -> `action_expectation = None`; pure text can finalize through normal completion guard.
- compact summary exists but user asks for general design opinion -> `action_expectation = None`; pure text can finalize.
- compact summary exists, has one draft ref, and user asks for exact/full/current draft detail -> `action_expectation.expectation_type = "read_draft_refs"`.
- active read expectation + text-only assistant output -> block finalization with `required_draft_ref_read_missing`, route to `reflect_if_needed`, then retry.
- active read expectation + `setup.truth.write` tool call without prior read -> block tool execution with `required_draft_ref_read_missing`, route to `reflect_if_needed`, then retry.
- active read expectation + mixed `setup.read.draft_refs` and mutation tool calls in one batch -> block tool execution because read observation must happen first.
- active read expectation + only `setup.read.draft_refs` call -> execute normally.
- `setup.read.draft_refs` succeeds for expected ref -> clear action expectation and continue normal loop.
- `setup.read.draft_refs` succeeds but does not observe the expected ref -> keep the action expectation active.
- `setup.read.draft_refs` fails validation or provider execution -> existing repair/failure policies handle the tool result; this slice does not add a second repair system.
- model repeats text-only answer after guard retry until round budget is exhausted -> fail through existing `max_rounds_exceeded` or `repair_obligation_unfulfilled` route, not a new terminal reason.

### 6. Good / Base / Bad Cases

- Good: after compact, user asks "之前写入草稿的 magic-law 完整内容是什么？"; compact summary only contains `foundation:magic-law`; the model first calls `setup.read.draft_refs`, then answers using the tool result.
- Good: after compact, the model tries to write `setup.truth.write` from summary alone; runtime blocks the mutation, retries, and the model reads draft refs first.
- Base: user asks "你对这个设计有什么看法？"; the model answers directly without tools.
- Base: no compact summary exists; existing loop / repair / completion semantics remain unchanged.
- Bad: accepting a precise answer from compact summary when exact detail is absent from visible context.
- Bad: adding a general semantic classifier that decides all future tool choices without eval evidence.
- Bad: persisting `action_expectation` as durable setup truth.

### 7. Tests Required

- `backend/rp/tests/test_setup_agent_runtime_policies.py`
  - assert compact exact-detail prompt produces a `read_draft_refs` expectation.
  - assert general opinion prompt produces no expectation.
  - assert a successful same-turn read result clears the expectation.
  - assert a successful read whose expected ref appears only in nested JSON `content_text` clears the expectation.
  - assert a successful read that omits the expected ref does not clear the expectation.
  - assert `CompletionGuardPolicy` blocks text finalization when read expectation is active.
- `backend/rp/tests/test_setup_agent_runtime_executor.py`
  - assert text-only answer under compact exact-detail expectation is guarded and retried.
  - assert `setup.read.draft_refs` executes when the model follows the expectation.
  - assert mutation tool batches are blocked before required readback.
  - assert structured payload and loop trace expose `action_expectation` additively.
- Existing setup runtime tests must remain green.

### 8. Wrong vs Correct

#### Wrong

- Treat `action_expectation` as another persistent state-management layer.
- Require draft reads for every compacted turn.
- Force tool calls for opinion/design discussion.
- Let a mutation tool run before the required draft read observation.
- Add model-semantic "similarity" classifiers before eval proves they are needed.
- Make LangGraph's generic tool/no-tool branch the only completion rule.

#### Correct

- Compute one small transient expectation from existing goal/plan/context surfaces.
- Enforce only high-certainty compact recovery cases in this slice.
- Let existing repair, reflection, and completion policies continue owning their established obligations.
- Use `setup.read.draft_refs` as the detail recovery surface after compact.
- Keep trace/debug visibility additive and bounded.
