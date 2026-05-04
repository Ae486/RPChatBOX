# RP Setup Agent Prior-Stage Handoff Context

> Executable contract for SetupAgent stage-scoped context assembly, compact earlier-stage truth handoffs, and budget-driven context compaction.

## Scenario: SetupAgent Later Stages Consume Only Compact Earlier-Stage Truth

### 1. Scope / Trigger

- Trigger: add or edit `backend/rp/models/setup_handoff.py`, `backend/rp/services/setup_context_builder.py`, `backend/rp/services/setup_agent_prompt_service.py`, `backend/rp/agent_runtime/adapters.py`, or `backend/rp/services/setup_agent_execution_service.py` when the change affects setup context packet shape, prior-stage handoffs, or setup context compaction heuristics.
- Applies only to setup/prestory runtime context assembly.
- This slice is internal only. It does not change `SetupWorkspace` business truth, activation handoff shape, Memory OS, retrieval contracts, or active-story prompt compilation.

### 2. Signatures

- `SetupContextBuilderInput`
  - `workspace_id: str`
  - `current_step: str`
  - `current_stage: str | None`
  - `user_prompt: str`
  - `user_edit_delta_ids: list[str]`
  - `token_budget: int | None`
- `SetupContextPacket`
  - `current_step: str`
  - `current_stage: str | None`
  - `context_profile: Literal["standard", "compact"]`
  - `committed_summaries: list[str]`
  - `current_draft_snapshot: dict[str, Any]`
  - `user_edit_deltas: list[dict[str, Any]]`
  - `prior_stage_handoffs: list[SetupStageHandoffPacket]`
- `SetupStageHandoffPacket`
  - `workspace_id: str`
  - `from_step: SetupStepId`
  - `to_step: SetupStepId`
  - `step_id: SetupStepId`
  - `from_stage: SetupStageId | None`
  - `to_stage: SetupStageId | None`
  - `stage_id: SetupStageId | None`
  - `commit_id: str`
  - `summary: str`
  - `summary_tier_0: str | None`
  - `summary_tier_1: str | None`
  - `committed_refs: list[str]`
  - `spotlights: list[str]`
  - `chunk_descriptions: list[SetupStageChunkDescription]`
  - `open_issues: list[str]`
  - `retrieval_refs: list[str]`
  - `warnings: list[str]`
  - `source_basis: SetupStageHandoffSourceBasis`
  - `created_at: datetime`
- `SetupStageChunkDescription`
  - `chunk_ref: str`
  - `block_type: str`
  - `title: str`
  - `description: str`
  - `metadata: dict[str, Any]`
- `SetupStageHandoffSourceBasis`
  - `workspace_id: str`
  - `commit_id: str`
  - `snapshot_block_types: list[str]`
- `SetupAgentExecutionService._context_token_budget(request) -> int`
- `SetupRuntimeAdapter.build_turn_input(...).context_bundle`
  - `has_prior_stage_handoffs: bool`
  - `prior_stage_handoff_count: int`
  - `prior_stage_handoff_steps: list[str]`

### 3. Contracts

- `prior_stage_handoffs` is the only earlier-stage truth surface passed into later setup stages.
- `prior_stage_handoffs` must be built only from `workspace.accepted_commits`.
- For each earlier setup step, only the latest accepted commit is eligible for handoff.
- The current step must never appear inside `prior_stage_handoffs`, even if the current step already has accepted commits.
- Legacy step ordering must follow `SetupWorkspaceService._STEP_ORDER`. If a legacy step is not earlier than the current step, it is not a prior-stage handoff candidate.
- Canonical stage ordering must follow `SetupWorkspace.stage_plan`. If `current_stage` is present, handoff selection uses accepted canonical stage commits before that stage; it must not wait for the old coarse `foundation` step to include both world and character setup.
- Each handoff packet must stay explicitly stage-scoped:
  - `workspace_id = workspace.workspace_id`
  - legacy compatibility fields (`from_step`, `to_step`, `step_id`) remain populated with the mapped legacy step when the accepted source is a canonical stage
  - stage-aware fields (`from_stage`, `to_stage`, `stage_id`) carry the canonical stage ids when available
- `SetupContextPacket.context_profile` is derived from `SetupContextBuilderInput.token_budget`:
  - `compact` when `token_budget < 1200`
  - otherwise `standard`
- `SetupAgentExecutionService._context_token_budget(...)` drives the builder input budget:
  - return `600` when any of the following is true:
    - `len(request.history) >= 8`
    - total `history` character count `>= 4000`
    - `len(request.user_edit_delta_ids) >= 3`
  - otherwise return `2400`
- Summary selection for each handoff must remain deterministic:
  - `compact` prefers `summary_tier_0`
  - `standard` prefers `summary_tier_1`, then `summary_tier_2`
  - both modes fall back to `summary_tier_0`, then `Committed {step_id}`
- Handoff packets must preserve both the active summary and the underlying accepted summary tiers:
  - `summary` = budget-selected active summary for prompt use
  - `summary_tier_0` = one-line accepted summary
  - `summary_tier_1` = richer accepted summary, using `summary_tier_1` then `summary_tier_2`
- `compact` handoffs must preserve:
  - `summary`
  - `summary_tier_0`
  - `summary_tier_1`
  - `committed_refs`
  - `spotlights`
  - `open_issues`
  - `retrieval_refs`
  - `warnings`
  - `source_basis`
  - `created_at`
  - but must set `chunk_descriptions = []`
- `standard` handoffs may expose compact retrieval-friendly chunk descriptions:
  - foundation snapshots derive descriptions from `domain`, `path`, `title`, and `content.summary`
  - longform blueprint snapshots derive one overview description plus chapter descriptions
  - canonical stage snapshots derive descriptions from `SetupStageDraftBlock.entries` and their entry/section summaries, using refs such as `stage:world_background:race_elf` and `stage:world_background:race_elf:summary`
  - generic snapshot types may expose concise previews, but only as stable accepted truth summaries
- `open_issues` must be a bounded carry-forward summary derived only from accepted snapshot payload fields such as:
  - `open_issues`
  - `remaining_open_issues`
  - `unresolved_issues`
- `retrieval_refs` must be derived from matching `workspace.retrieval_ingestion_jobs` for the same `commit_id`:
  - keep only stable `target_ref` values
  - preserve first-seen order
  - dedupe exact duplicates
- `warnings` must come only from the original accepted proposal's `unresolved_warnings` when that proposal still exists on the workspace model.
- `source_basis` must expose the minimum lineage needed to understand where the handoff came from:
  - `workspace_id`
  - `commit_id`
  - `snapshot_block_types`
- The prompt contract is strict:
  - `prior_stage_handoffs` is the compact truth handoff from earlier setup stages
  - the agent may use `summary`, `spotlights`, `chunk_descriptions`, `open_issues`, `retrieval_refs`, and `warnings`
  - the agent must not reconstruct or replay raw earlier-stage discussion
- Runtime metadata must stay aligned with the context packet:
  - `has_prior_stage_handoffs` reflects whether any earlier-stage handoff exists
  - `prior_stage_handoff_count` equals `len(context_packet.prior_stage_handoffs)`
  - `prior_stage_handoff_steps` preserves the earlier-step ids in order
- Current-step truth remains step-local:
  - `current_draft_snapshot`
  - selected `user_edit_deltas`
  - runtime-private cognitive state and summary
  - these must not be collapsed into prior-stage handoff data

### 4. Validation & Error Matrix

- `SetupWorkspace` missing for `workspace_id` -> raise `ValueError("SetupWorkspace not found: ...")`
- `current_step` not found in `SetupWorkspaceService._STEP_ORDER` -> return no `prior_stage_handoffs`
- current step is the first step in the order -> return no `prior_stage_handoffs`
- earlier step has no accepted commit -> omit that step from `prior_stage_handoffs`
- `token_budget is None` -> `context_profile = "standard"`
- `context_profile = "compact"` -> keep summaries and spotlights, but drop all `chunk_descriptions`
- accepted commit has matching retrieval jobs -> `retrieval_refs` mirrors those `target_ref` values
- accepted commit has no matching retrieval jobs -> `retrieval_refs = []`
- accepted snapshot exposes `open_issues` / `remaining_open_issues` / `unresolved_issues` -> keep a bounded deduped carry-forward list
- current-step accepted commit exists -> exclude it from `prior_stage_handoffs`; current-step convergence still comes from current draft plus runtime-private cognition

### 5. Good/Base/Bad Cases

- Good: a `longform_blueprint` turn sees accepted `writing_contract` and `foundation` summaries, spotlights, and chunk descriptions, without replaying their raw discussion transcript.
- Base: a small `foundation` turn with no earlier accepted commits yields `context_profile="standard"` and `prior_stage_handoffs=[]`.
- Bad: feeding rejected drafts, raw earlier-stage discussion, or current-step discussion details into `prior_stage_handoffs` as if they were settled truth.

### 6. Tests Required

- `backend/rp/tests/test_setup_agent_runtime_state_service.py`
  - assert foundation handoff descriptions derive from accepted foundation commits
  - assert blueprint handoff descriptions derive from accepted blueprint commits
  - assert compact profile drops `chunk_descriptions`
  - assert handoff packets expose `workspace_id`, `from_step`, `to_step`, `summary_tier_0`, `summary_tier_1`, `retrieval_refs`, and `source_basis`
  - assert accepted snapshot `open_issues` are carried into the handoff packet without pulling raw discussion
- `backend/rp/tests/test_setup_agent_execution_service_v2.py`
  - assert small turns use the standard context budget
  - assert long or edit-heavy turns switch to the compact context budget
- `backend/rp/tests/test_setup_agent_runtime_executor.py`
  - assert runtime context metadata preserves handoff presence, count, and step ids

### 7. Wrong vs Correct

#### Wrong

- Treat earlier-stage raw conversation as durable truth because it might still be useful later.
- Carry the current step's discussion details into `prior_stage_handoffs`.
- Introduce a new durable memory/state layer just to preserve setup stage context.

#### Correct

- Carry only the latest accepted truth from earlier stages, in compact handoff packets.
- Keep current-step discussion and cognition step-local, then summarize them only through explicit commit/handoff boundaries.
- Let budget signals choose `standard` vs `compact` mode instead of ad hoc prompt truncation.
