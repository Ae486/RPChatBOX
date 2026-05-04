# RP Setup Agent Pre-Model Context Assembly

> Executable contract for SetupAgent runtime-v2 pre-model context assembly: workspace-derived context packet, stage-local governed history, runtime overlay, and final request message ordering.

## Scenario: SetupAgent Assembles A Bounded Model Context Through Explicit Layers

### 1. Scope / Trigger

- Trigger: add or edit `backend/rp/models/setup_handoff.py`, `backend/rp/services/setup_context_builder.py`, `backend/rp/services/setup_context_governor.py`, `backend/rp/services/setup_agent_execution_service.py`, `backend/rp/services/setup_agent_prompt_service.py`, `backend/rp/agent_runtime/adapters.py`, or `backend/rp/agent_runtime/executor.py` when the change affects what reaches the model before one setup round starts.
- Applies only to setup/prestory runtime-v2 pre-model context assembly.
- This slice is internal runtime contract work. It does not change `SetupWorkspace` business truth, prior-stage handoff schema, stage-local retention policy, stage-skill runtime, or typed-SSE event taxonomy.
- This slice must keep borrowing focused on mature context pipelines such as Claude Code and `pi-mono`, but it must stay an optimization of the current setup runtime rather than a framework rewrite.

### 2. Signatures

- `SetupContextBuilderInput`
  - `mode: str`
  - `workspace_id: str`
  - `current_step: str`
  - `current_stage: str | None`
  - `user_prompt: str`
  - `user_edit_delta_ids: list[str]`
  - `token_budget: int | None`
- `SetupContextPacket`
  - `workspace_id: str`
  - `current_step: str`
  - `current_stage: str | None`
  - `context_profile: Literal["standard", "compact"]`
  - `committed_summaries: list[str]`
  - `current_draft_snapshot: dict[str, Any]`
  - `step_asset_preview: list[dict[str, Any]]`
  - `user_prompt: str`
  - `user_edit_deltas: list[dict[str, Any]]`
  - `spotlights: list[str]`
  - `prior_stage_handoffs: list[SetupStageHandoffPacket]`
- `SetupAgentExecutionService._context_token_budget(...) -> int`
  - returns `2400` or `600` per the budget heuristics already defined by the setup handoff and stage-local compact slices
  - must consider message count, estimated pre-call token pressure, observed previous usage when available, and user-edit pressure
- `SetupContextGovernanceReport`
  - `context_profile: Literal["standard", "compact"]`
  - `profile_reasons: list[str]`
  - `raw_history_count: int`
  - `raw_history_chars: int`
  - `estimated_input_tokens: int | None`
  - `previous_prompt_tokens: int | None`
  - `previous_total_tokens: int | None`
  - `user_edit_delta_count: int`
  - `prior_stage_handoff_count: int`
  - `raw_history_limit: int`
  - `kept_history_count: int`
  - `compacted_history_count: int`
  - `retained_tool_outcome_count: int`
  - `summary_strategy: Literal["none", "deterministic_prefix_summary", "compact_prompt_summary"]`
  - `summary_action: Literal["none", "reused_existing", "updated_existing", "rebuilt"]`
  - `summary_line_count: int`
  - `fallback_reason: str | None`
- `SetupContextGovernorService.govern_history(...) -> tuple[list[SetupAgentDialogueMessage], SetupContextCompactSummary | None, dict[str, int]]`
  - `governance_metadata` required keys:
    - `raw_history_limit: int`
    - `kept_history_count: int`
    - `compacted_history_count: int`
    - `estimated_input_tokens: int | None`
    - `previous_prompt_tokens: int | None`
    - `previous_total_tokens: int | None`
    - `summary_strategy: str`
    - `fallback_reason: str | None`
- `SetupRuntimeAdapter.build_turn_input(...)`
  - required additive inputs:
    - `governed_history: list[SetupAgentDialogueMessage] | None`
    - `working_digest: SetupWorkingDigest | None`
    - `tool_outcomes: list[SetupToolOutcome] | None`
    - `compact_summary: SetupContextCompactSummary | None`
    - `governance_metadata: dict[str, int] | None`
    - `context_report: SetupContextGovernanceReport | None`
    - `cognitive_state: SetupCognitiveStateSnapshot | None`
    - `cognitive_state_summary: SetupCognitiveStateSummary | None`
- `RpAgentTurnInput.context_bundle`
  - required setup keys:
    - `system_prompt`
    - `context_packet`
    - `mode`
    - `current_step`
    - `current_stage`
    - `step_state`
    - `stage_state`
    - `step_readiness`
    - `stage_readiness`
    - `open_question_count`
    - `blocking_open_question_count`
    - `open_question_texts`
    - `has_user_edit_deltas`
    - `has_prior_stage_handoffs`
    - `prior_stage_handoff_count`
    - `prior_stage_handoff_steps`
    - `prior_stage_handoff_stages`
    - `last_proposal_status`
    - `has_rejected_commit_proposal`
    - `cognitive_state`
    - `cognitive_state_summary`
    - `cognitive_state_invalidated`
    - `working_digest`
    - `tool_outcomes`
    - `compact_summary`
    - `governance_metadata`
    - `context_report`
- `_prepare_input(...) -> RpAgentRunState`
  - normalizes message order before any runtime overlay insertion
- `_build_request_messages(...) -> list[ChatMessage]`
  - composes the final model-visible message list for each round

### 3. Contracts

#### 3.1 Pre-Model Context Assembly Uses Four Explicit Layers

- Layer 1: `SetupContextBuilder.build(...)`
  - reads `SetupWorkspace`
  - selects prior-stage handoffs
  - selects current-stage draft snapshot from `draft_blocks[current_stage]` when `current_stage` is present, otherwise falls back to the legacy current-step draft snapshot
  - selects current-step asset preview
  - selects relevant user edit deltas
  - produces `SetupContextPacket`
- Layer 2: `SetupContextGovernorService.govern_history(...)`
  - receives raw request history
  - runs stage-local context engineering only for the current step
  - performs pressure assessment, raw-window retention, tool-outcome retention, deterministic or compact-prompt summary, and draft-ref recovery hint preparation
  - returns governed raw history, `compact_summary`, and `governance_metadata`
- Layer 3: `SetupRuntimeAdapter.build_turn_input(...)`
  - joins context packet, stage-local governance artifacts, context-decision report, step readiness facts, proposal status, and runtime-private cognition into `RpAgentTurnInput.context_bundle`
- Layer 4: runtime request assembly inside `RpAgentRuntimeExecutor`
  - `_prepare_input(...)` normalizes the base message list
  - `_build_request_messages(...)` inserts runtime overlay after the stable system prompt
- Each layer has one job. No layer may silently absorb the responsibilities of another.

#### 3.2 Budget Selection And Context Profile Must Stay Single-Sourced

- `SetupAgentExecutionService._context_token_budget(...)` is the only entry point that decides whether this turn is `standard` or `compact`.
- The compact decision may use:
  - raw current-step message count
  - estimated pre-call input tokens
  - previous observed `usage.prompt_tokens` / `usage.total_tokens`
  - current-step user edit delta pressure
- Previous observed usage must be scoped to the same `(workspace_id, current_step)` as the turn being assembled. A service-level "last runtime result" from a different workspace or setup step must not trigger `observed_usage_threshold`, and must not populate `context_report.previous_prompt_tokens` / `previous_total_tokens`.
- The chosen `token_budget` must flow into `SetupContextBuilderInput.token_budget`.
- `SetupContextBuilder._context_profile(...)` must derive `SetupContextPacket.context_profile` from that budget.
- `SetupContextGovernorService.govern_history(...)` must use `context_packet.context_profile` rather than re-deriving a second compaction mode from raw history length.
- Prompt assembly must not invent a third independent compact/full switch.
- Response-side usage is an observation/calibration signal, not a substitute for pre-call token estimation.

#### 3.3 `SetupContextPacket` Contains Workspace Truth, Not Runtime Control State

- `SetupContextPacket` may contain:
  - prior-stage handoff summaries and chunk descriptions
  - current-step draft snapshot
  - current-step asset preview
  - user edit deltas
  - current-step spotlights and committed summaries
- `SetupContextPacket` must not contain:
  - raw request history
  - `working_digest`
  - retained `tool_outcomes`
  - `compact_summary`
  - `turn_goal`
  - `working_plan`
  - `loop_trace`
  - `continue_reason`
  - latest same-turn tool results
- Prior-stage truth still enters only through `prior_stage_handoffs`; this slice must not rebuild it from historical chat.
- During stage migration, `current_step` remains available for compatibility, but `current_stage` is the canonical lifecycle signal whenever it is present.

#### 3.4 System Prompt And Runtime Overlay Have Different Responsibilities

- `SetupAgentPromptService.build_system_prompt(...)` owns the stable role/boundary instructions:
  - setup-only role
  - stage objective
  - durable setup rules
  - serialized `context_packet` JSON
- The system prompt must not embed:
  - governed raw history
  - `compact_summary`
  - retained `tool_outcomes`
  - `loop_trace`
  - `continue_reason`
  - raw tool retry/process history
- `_runtime_overlay_message(...)` owns turn-local execution guidance only:
  - `turn_goal`
  - `working_plan`
  - `pending_obligation`
  - `last_failure`
  - `reflection_ticket`
  - `cognitive_state_summary`
  - `working_digest`
  - retained `tool_outcomes`
  - `compact_summary`
- The runtime overlay must stay additive and terse. It must not re-serialize the full `context_packet` JSON again.
- The runtime overlay may mention that `setup.read.draft_refs` should be used when `compact_summary.recovery_hints` points to a draft ref whose details are needed.

#### 3.5 Final Request Message Order Is Fixed

- `_prepare_input(...)` must construct the base order as:
  1. stable setup system prompt
  2. governed raw conversation history
  3. current user request
- `_build_request_messages(...)` must then insert the runtime overlay immediately after the first system message when overlay payload exists.
- Therefore the final model-visible order is:
  1. stable setup system prompt
  2. runtime overlay system message
  3. governed raw conversation history
  4. current user request
- If no runtime overlay payload exists, the second slot disappears and the base order stays intact.

#### 3.6 Tool Observation Policy Must Separate Latest Batch From Retained History

- Same-turn latest tool results may re-enter the loop as raw tool result messages after `execute_tools` / `apply_tool_results`.
- Historical tool information older than the latest batch must survive only through bounded retained `tool_outcomes`.
- Raw tool retry chains, argument-fix attempts, and repeated validation failures must not be replayed as historical prompt context.
- Tool visibility remains outside prompt assembly:
  - callable tool schemas belong in `ChatCompletionRequest.tools`
  - prompt/context layers describe constraints and state, not full tool schema duplication

#### 3.7 `governance_metadata` Is A Small Count Surface, Not Another Summary Layer

- `governance_metadata` exists so runtime debug/eval can understand how much raw history survived.
- Required meanings:
  - `raw_history_limit`: active raw-history cap selected by the context governor
  - `kept_history_count`: number of raw history messages still visible
  - `compacted_history_count`: number of raw history messages removed from the prompt-visible list
- `governance_metadata` must remain deterministic counts only.
- It must not become another prose summary, trace transcript, or hidden reasoning surface.

#### 3.8 `context_report` Is The Richer Transient Decision Surface

- `context_report` exists so runtime debug/eval/result surfaces can explain the stage-local context decision without inspecting raw prompt assembly logic.
- `context_report` must explain:
  - why the runtime selected `standard` vs `compact`
  - what message/token/usage signal caused that profile
  - how much raw history was kept vs compacted
  - whether the compact summary was reused vs rebuilt
  - whether the strategy was deterministic or compact-prompt, and why fallback happened if any
  - how many retained tool outcomes and prior-stage handoffs participated in the turn
- `context_report` may be exposed in:
  - `RpAgentTurnInput.context_bundle`
  - runtime structured result payload
  - debug/eval/trace artifacts
- `context_report` must not be injected into:
  - the stable system prompt
  - the runtime overlay prompt message
  - durable setup cognition snapshots

#### 3.9 Durable Versus Transient Boundaries Must Stay Clean

- Durable setup truth:
  - `SetupWorkspace`
  - accepted prior-stage handoffs
  - `SetupAgentRuntimeStateRecord.snapshot_json` surfaces already allowed by the stage-local governance slice
- Turn-transient assembly/control surfaces:
  - governed raw history
  - runtime overlay
  - `governance_metadata`
  - `context_report`
  - model request message ordering
  - latest same-turn tool result messages
- This slice must not widen persistence by writing request-assembly artifacts into durable setup cognition records.

### 4. Validation & Error Matrix

- request history is short and user edit delta count is below compact threshold -> `_context_token_budget(...) = 2400`, `context_profile = "standard"`
- request history count/size crosses the compact threshold, estimated input tokens cross threshold, observed previous usage crosses threshold, or user edit delta count reaches `3` -> `_context_token_budget(...) = 600`, `context_profile = "compact"`
- observed usage from the same `(workspace_id, current_step)` crosses threshold -> `context_report.profile_reasons` includes `observed_usage_threshold` and previous token counts are surfaced
- observed usage from a different workspace or setup step crosses threshold -> current turn stays governed by its own message/token/edit signals, with no `observed_usage_threshold` and no previous token counts surfaced
- explicit `user_edit_delta_ids` are provided -> `SetupContextPacket.user_edit_deltas` must include those ids even if they are not the default pending set
- no explicit `user_edit_delta_ids` are provided -> `SetupContextPacket.user_edit_deltas` includes only current-step unconsumed pending deltas
- governed history removes older raw messages -> `compact_summary` may carry forward old current-step context, but the removed raw messages must not remain in the final message list
- runtime overlay payload is empty -> `_build_request_messages(...)` must not insert a second system message
- retained tool outcomes exist from previous turns -> they may appear in runtime overlay, but not inside `SetupContextPacket`
- latest same-turn tool batch exists -> raw tool result messages may be visible to the next same-turn round, but they must not be copied into persistent stage-local snapshot fields by this slice
- compact summary is present and equals the existing dropped-prefix fingerprint -> `context_report.summary_action = "reused_existing"`
- compact summary is present and extends an existing valid prefix summary -> `context_report.summary_action = "updated_existing"`
- compact summary is present but cannot reuse an existing prefix -> `context_report.summary_action = "rebuilt"`
- compact prompt pass succeeds -> `context_report.summary_strategy = "compact_prompt_summary"`
- compact prompt pass fails validation or is disabled -> deterministic fallback is allowed, but `context_report.fallback_reason` must explain it
- no dropped history exists -> `context_report.summary_strategy = "none"` and `summary_action = "none"`
- a developer tries to reuse raw request history to reconstruct prior-stage truth -> invalid; prior-stage truth must still come from accepted handoff packets only

### 5. Good / Base / Bad Cases

- Good: a large `foundation` turn selects `compact`, keeps only the last few raw messages, carries older discussion through `compact_summary`, injects one thin runtime overlay, and keeps prior-stage truth visible only through committed handoff packets.
- Good: a compacted turn preserves `compact_summary.recovery_hints` and the model can use `setup.read.draft_refs` for exact current-draft details rather than relying on stale raw discussion.
- Good: a `foundation` turn can use previous `foundation` usage from the same workspace as calibration, while a separate workspace's large previous turn does not force this turn into `compact`.
- Base: a small `story_config` turn stays `standard`, keeps the short raw history, has no `compact_summary`, and still inserts runtime overlay after the stable system prompt.
- Bad: stuffing runtime control state into `SetupContextPacket`, duplicating the full packet again inside the runtime overlay, replaying old tool retry process as if it were reusable context, or letting compact prompt output mutate business truth.
- Bad: using one execution service's most recent runtime result globally so unrelated workspaces or setup steps inherit each other's observed token pressure.

### 6. Tests Required

- `backend/rp/tests/test_setup_agent_execution_service_v2.py`
  - assert `_context_token_budget(...)` selects `standard` vs `compact` deterministically
  - assert token/message/observed-usage/user-edit compact reasons are surfaced in `context_report.profile_reasons`
  - assert observed usage pressure is scoped by `workspace_id + current_step` and does not cross-contaminate unrelated workspaces or setup steps
  - assert runtime-v2 turn input uses governed history instead of raw full history when compaction is required
  - assert `context_packet.context_profile` and `governance_metadata.raw_history_limit` stay aligned
  - assert `context_report` explains profile reasons and summary action without entering prompt-visible runtime overlay
- `backend/rp/tests/test_setup_context_governor.py`
  - assert `governance_metadata` keys stay stable and deterministic
  - assert compacted history count reflects dropped raw history only
- `backend/rp/tests/test_setup_agent_runtime_executor.py`
  - assert final request message order is `system prompt -> runtime overlay -> governed history -> current user`
  - assert runtime overlay contains thin turn-local control state and does not duplicate full `context_packet`
  - assert historical tool retry process is not replayed into later-round prompt messages
  - assert runtime structured payload exposes `context_report`
- `backend/rp/tests/test_setup_agent_runtime_state_service.py`
  - assert request-assembly artifacts such as `context_report` are not persisted as durable stage-local snapshot truth

### 7. Wrong vs Correct

#### Wrong

- Treat `SetupContextPacket` as a dump bucket for all runtime state.
- Re-derive compact/full mode separately inside the prompt layer after `context_profile` is already chosen.
- Duplicate the full context packet in both the stable system prompt and the runtime overlay.
- Keep historical tool retry/process traces in prompt-visible context because they happened "recently".
- Treat `context_report` as another prompt-injection surface instead of a debug/eval/result surface.
- Let pre-model context assembly quietly widen durable setup persistence.
- Let compact prompt become another tool-using agent loop inside pre-model assembly.
- Treat response-side token usage as enough to protect the next pre-model request without any pre-call estimate.

#### Correct

- Keep workspace truth, stage-local history governance, runtime control overlay, and final message ordering as separate layers.
- Flow one token-budget decision into one `context_profile`, then reuse it consistently through context assembly.
- Keep `SetupContextPacket` truth-oriented and keep runtime overlay turn-oriented.
- Keep only the latest same-turn raw tool observations plus bounded retained tool outcomes.
- Keep `governance_metadata` as raw counts and keep the richer context-decision explanation in transient `context_report`.
- Keep request-assembly artifacts transient and outside durable setup cognition snapshots.
- Scope observed previous usage to the same workspace and setup step before it can influence context-profile selection.
- Keep compact prompt as a no-tools JSON summarizer inside stage-local context engineering, with deterministic fallback.
- Use draft refs plus `setup.read.draft_refs` for detail recovery instead of stuffing all draft details into prompt context.
