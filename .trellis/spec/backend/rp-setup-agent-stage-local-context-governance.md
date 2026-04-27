# RP Setup Agent Stage-Local Context Governance

> Executable contract for SetupAgent runtime-v2 stage-local context governance: thin working digest, retained tool outcomes, compacted older step history, and minimal no-progress guards.

## Scenario: SetupAgent Keeps Only Live Step Control State And Compacts Old Step History

### 1. Scope / Trigger

- Trigger: add or edit `backend/rp/agent_runtime/contracts.py`, `backend/rp/agent_runtime/state.py`, `backend/rp/agent_runtime/executor.py`, `backend/rp/agent_runtime/policies.py`, `backend/rp/agent_runtime/adapters.py`, `backend/rp/services/setup_agent_execution_service.py`, `backend/rp/services/setup_agent_runtime_state_service.py`, `backend/rp/services/setup_agent_prompt_service.py`, or the setup stage-local context governor / compaction services when the change affects what current-step context is visible to SetupAgent.
- Applies only to setup/prestory runtime-v2 current-step context inside one setup stage.
- This slice is internal only. It does not change `SetupWorkspace` business truth, prior-stage handoff packets, Memory OS, retrieval contracts, or user manual commit authority.
- This slice must not introduce a new durable setup-memory subsystem. Runtime-private governance state stays inside the existing `SetupAgentRuntimeStateRecord.snapshot_json`.

### 2. Signatures

- `SetupWorkingDigest`
  - `current_goal: str | None`
  - `next_focus: str | None`
  - `open_questions: list[str]`
  - `rejected_directions: list[str]`
  - `draft_refs: list[str]`
  - `pending_obligation: str | None`
  - `commit_blockers: list[str]`
- `SetupToolOutcome`
  - `tool_name: str`
  - `success: bool`
  - `summary: str`
  - `updated_refs: list[str]`
  - `error_code: str | None`
  - `relevance: Literal["cognitive", "draft", "question", "proposal", "read", "asset", "failure", "other"]`
  - `recorded_at: datetime`
- `SetupContextCompactSummary`
  - `source_fingerprint: str`
  - `source_message_count: int`
  - `summary_lines: list[str]`
  - `open_threads: list[str]`
  - `draft_refs: list[str]`
- `SetupCognitiveStateSnapshot`
  - add `working_digest: SetupWorkingDigest | None`
  - add `tool_outcomes: list[SetupToolOutcome]`
  - add `compact_summary: SetupContextCompactSummary | None`
- `SetupCognitiveStateSummary`
  - add `working_digest: SetupWorkingDigest | None`
  - add `tool_outcomes: list[SetupToolOutcome]`
  - add `compact_summary: SetupContextCompactSummary | None`
- `SetupContextCompactionService.build_summary(...) -> SetupContextCompactSummary | None`
  - inputs:
    - `history: list[SetupAgentDialogueMessage]`
    - `retained_tool_outcomes: list[SetupToolOutcome]`
    - `working_digest: SetupWorkingDigest | None`
    - `existing_summary: SetupContextCompactSummary | None`
    - `context_profile: Literal["standard", "compact"]`
- `SetupContextGovernorService.govern_history(...) -> tuple[list[SetupAgentDialogueMessage], SetupContextCompactSummary | None, dict[str, int]]`
  - inputs:
    - `history: list[SetupAgentDialogueMessage]`
    - `retained_tool_outcomes: list[SetupToolOutcome]`
    - `working_digest: SetupWorkingDigest | None`
    - `existing_summary: SetupContextCompactSummary | None`
    - `context_profile: Literal["standard", "compact"]`
- `SetupContextGovernorService.build_initial_digest(...) -> SetupWorkingDigest | None`
- `SetupContextGovernorService.retain_tool_outcomes(...) -> list[SetupToolOutcome]`
- `SetupAgentRuntimeStateService.persist_turn_governance(...) -> SetupCognitiveStateSnapshot`
  - inputs:
    - `workspace`
    - `context_packet`
    - `step_id: SetupStepId`
    - `working_digest: SetupWorkingDigest | None`
    - `tool_outcomes: list[SetupToolOutcome]`
    - `compact_summary: SetupContextCompactSummary | None`
- `SetupRuntimeAdapter.build_turn_input(...)`
  - add optional inputs:
    - `governed_history: list[SetupAgentDialogueMessage] | None`
    - `working_digest: SetupWorkingDigest | None`
    - `tool_outcomes: list[SetupToolOutcome] | None`
    - `compact_summary: SetupContextCompactSummary | None`
    - `governance_metadata: dict[str, int] | None`
- `RpAgentRunState`
  - add `working_digest: dict[str, Any] | None`
  - add `tool_outcomes: list[dict[str, Any]]`
  - add `compact_summary: dict[str, Any] | None`
- `RepairDecisionPolicy.assess(...)`
  - add `prior_tool_outcomes: list[SetupToolOutcome] | None = None`
- `CompletionGuardPolicy.assess(...)`
  - add `prior_assistant_questions: list[str] | None = None`
  - add `working_digest: SetupWorkingDigest | None = None`

### 3. Contracts

- `working_digest` is live current-step control state. It is not a compact history summary.
- `compact_summary` is only the compressed carry-forward view of older current-step raw discussion that was removed from the prompt-visible message list.
- `tool_outcomes` keep final outcomes only:
  - keep one summarized outcome per completed tool result
  - never keep retry chains, intermediate argument fixes, or raw tool execution process as cross-turn prompt context
- Stage-local context remains step-scoped:
  - `context_packet.current_draft_snapshot`
  - `context_packet.user_edit_deltas`
  - runtime-private cognition
  - retained tool outcomes
  - compacted older current-step history
  - these are current-step only and must not be folded into `prior_stage_handoffs`
- Prior-stage truth still comes only from `prior_stage_handoffs`. Stage-local compact history never replaces that handoff contract.
- `SetupContextGovernorService.govern_history(...)` must keep only recent raw current-step messages:
  - `standard` profile keeps the last `6` history messages raw
  - `compact` profile keeps the last `4` history messages raw
  - older messages are excluded from raw prompt history and may only survive through `compact_summary`
- `SetupContextCompactionService.build_summary(...)` must rebuild only when the dropped-history prefix changes:
  - fingerprint source = dropped-history prefix only
  - if `existing_summary.source_fingerprint` and `existing_summary.source_message_count` still match the dropped prefix, reuse it
  - if no dropped history exists, return `None`
- `compact_summary` must stay thin:
  - `summary_lines` max `6`
  - `open_threads` max `4`
  - `draft_refs` max `6`
  - it must not replay long verbatim discussion blocks
- `retain_tool_outcomes(...)` must keep at most `6` outcomes after prune:
  - unresolved failures are retained first
  - then the newest successful outcomes that touched draft/cognitive/question/proposal refs
  - duplicate success outcomes for the same `tool_name + updated_refs` should collapse to the newest one
- `build_initial_digest(...)` must stay thin and deterministic:
  - `current_goal` derives from existing runtime goal / current-step convergence state
  - `next_focus` prefers `discussion_state.next_focus`, then working-plan priority
  - `open_questions` prefer current cognitive summary open questions
  - `rejected_directions` derive only from discarded discussion directions
  - `draft_refs` come from current truth-write target and retained tool outcomes
  - `pending_obligation` mirrors unresolved runtime obligation reason
  - `commit_blockers` come from blocking questions, invalidated cognitive state, unresolved truth-write issues, or commit-block reflection state
- The runtime-visible context stack is strict:
  - system prompt from `SetupAgentPromptService`
  - runtime overlay containing `turn_goal`, `working_plan`, `pending_obligation`, `last_failure`, `reflection_ticket`, `cognitive_state_summary`, `working_digest`, `tool_outcomes`, and `compact_summary`
  - governed raw conversation history
  - current-turn raw tool result messages for the latest batch only
- The runtime-private persistence surface stays unchanged at the storage layer:
  - no new setup runtime table
  - `SetupAgentRuntimeStateRecord.snapshot_json` remains the only persistence surface for digest / tool outcomes / compact summary
- `persist_turn_governance(...)` runs after each runtime-v2 turn and updates the current-step snapshot without clearing existing discussion/chunk/truth state.
- Minimal no-progress guard is required:
  - if the assistant emits the same normalized user-facing question that already exists in recent assistant history and the current turn produced no new tool progress, finalization must be blocked with a repeat-question guard
  - if the same tool failure signature repeats against retained failure outcomes, the runtime must warn about repeated failure instead of treating it as fresh progress

### 4. Validation & Error Matrix

- no stored snapshot exists for the current step -> start with empty digest, empty retained tool outcomes, and `compact_summary = None`
- history length does not exceed the raw-history limit for the active profile -> keep full history raw and `compact_summary = None`
- dropped-history prefix exists and matches stored compact fingerprint -> reuse existing `compact_summary`
- dropped-history prefix exists and does not match stored compact fingerprint -> rebuild `compact_summary`
- retained outcomes exceed `6` after merge -> prune successes first, preserve unresolved failures
- tool result has no meaningful `updated_refs` and is a non-failure read/tool artifact -> it may be dropped from retained cross-turn outcomes
- assistant question repeats a recent assistant question and no new tool result succeeded -> `CompletionGuardPolicy` blocks finalization with `reason="repeated_question_without_progress"`
- latest tool failure repeats a retained failure signature -> keep the normal repair route, but append warning `repeated_tool_failure`
- `working_digest` would exceed its field caps -> truncate list fields before prompt injection
- current-step compact summary exists but there is no dropped history anymore -> clear `compact_summary`

### 5. Good / Base / Bad Cases

- Good: a long `foundation` discussion keeps the last 4 raw messages, carries earlier discussion through one compact summary, preserves one unresolved `setup.truth.write` failure outcome, and injects a thin digest that says what still blocks review.
- Base: a short `story_config` turn with 2 prior messages keeps the full raw history, has no compact summary, and carries no retained outcomes.
- Bad: replaying the entire current-step transcript every turn, storing tool retry chains as prompt-visible history, or using `working_digest` as if it were the stage compaction artifact.

### 6. Tests Required

- `backend/rp/tests/test_setup_context_governor.py`
  - assert `standard` keeps the last 6 raw history messages and `compact` keeps the last 4
  - assert dropped history produces a reusable compact summary fingerprint
  - assert retained outcomes keep unresolved failures and prune duplicate/superseded successes
  - assert initial digest stays thin and deterministic
- `backend/rp/tests/test_setup_agent_runtime_state_service.py`
  - assert `persist_turn_governance(...)` stores digest / tool outcomes / compact summary in the existing snapshot
  - assert `summarize_for_prompt(...)` exposes those governance artifacts
- `backend/rp/tests/test_setup_agent_runtime_executor.py`
  - assert runtime structured payload exposes `working_digest`, `tool_outcomes`, and `compact_summary`
  - assert latest tool results merge into retained tool outcomes without carrying raw retry process
- `backend/rp/tests/test_setup_agent_runtime_policies.py`
  - assert repeated question without progress is blocked
  - assert repeated tool failure adds warning `repeated_tool_failure`
- `backend/rp/tests/test_setup_agent_execution_service_v2.py`
  - assert runtime-v2 context assembly uses governed history rather than the raw full request history when compaction is required

### 7. Wrong vs Correct

#### Wrong

- Treat `digest` as the same thing as `compact_summary`.
- Keep raw tool retries, argument-fix attempts, and tool execution process as cross-turn prompt context.
- Add a second durable state layer just to remember setup-stage conversation.

#### Correct

- Keep `working_digest` as thin live control state, separate from the history compaction artifact.
- Keep only final tool outcomes across turns, then drop the process trace.
- Compact only older current-step raw history, keep recent raw turns visible, and persist everything inside the existing runtime snapshot.
