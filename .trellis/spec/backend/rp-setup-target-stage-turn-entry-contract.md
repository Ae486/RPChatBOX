# RP Setup Target Stage Turn Entry Contract

> Executable contract for carrying canonical `SetupStageId` through setup turn ingress while preserving `SetupStepId` only as a compatibility mirror.

## 1. Scope / Trigger

- Trigger: add or edit `backend/rp/models/setup_agent.py`, `backend/rp/graphs/setup_graph_state.py`, `backend/rp/graphs/setup_graph_runner.py`, `backend/rp/services/setup_agent_execution_service.py`, `backend/rp/agent_runtime/adapters.py`, setup API/trace surfaces, setup eval request fixtures, or the prestory setup frontend when the change affects how one setup turn chooses its target stage.
- Applies only to setup/prestory turn ingress and the immediate runtime turn-launch path.
- This slice fixes canonical stage selection at turn ingress. It does not add new stage-specific patch tools, remove legacy draft mirrors, redesign setup lifecycle persistence, or rewrite eval taxonomy.
- Source:
  - User-confirmed product rule: setup discussion follows user-facing stages such as `world_background` and `character_design`, not only old 4-step buckets.
  - Existing code evidence: frontend already renders canonical `stage_plan`, but turn submission still sends only `target_step`, which collapses multiple canonical stages back into the same legacy bucket.
  - Existing spec evidence: setup runtime/context/handoff contracts already treat `current_stage` as the canonical lifecycle signal whenever it is present.

## 2. Signatures

- `SetupAgentTurnRequest`
  - keep `target_step: SetupStepId | None = None`
  - add `target_stage: SetupStageId | None = None`
- `SetupGraphState`
  - keep `target_step: str | None`
  - add `target_stage: str | None`
- `_SetupTurnLaunch`
  - keep `current_step: SetupStepId`
  - add `current_stage: SetupStageId | None`
- setup API / trace / eval request payloads
  - may carry both `target_step` and `target_stage`
  - `target_stage` is the canonical interactive selection when present
- prestory setup frontend request builder
  - submit canonical snake_case `target_stage`
  - may continue to send `target_step` as compatibility data during migration

## 3. Contracts

### 3.1 Canonical Interactive Selection Uses `target_stage`

- When a setup turn targets a canonical stage, `target_stage` is the authoritative turn-ingress field.
- `target_step` remains a compatibility mirror for old step-scoped logic and old eval fixtures.
- If `target_stage` is absent, legacy `target_step` behavior remains valid.
- This slice exists because `world_background` and `character_design` both map to legacy `foundation`, so `target_step` alone cannot express which canonical stage the user selected.

### 3.2 Effective Turn Launch Resolves Stage First

- Turn launch must resolve effective selection in this order:
  - `current_stage = request.target_stage`
  - else `workspace.current_stage`
- Effective `current_step` must resolve in this order:
  - if `request.target_step` is present, use it
  - else if effective `current_stage` is present, map it through `SetupWorkspaceService._LEGACY_STEP_FOR_STAGE`
  - else use `workspace.current_step`
- If both `target_stage` and `target_step` are provided and `target_step` does not equal the legacy mapping of `target_stage`, reject the request before runtime execution.

### 3.3 Stage Override Must Survive The Entire Turn Chain

- `SetupAgentExecutionService._prepare_turn_launch(...)` must preserve the effective canonical `current_stage` on the launch object.
- `SetupContextBuilderInput.current_stage` must receive the effective canonical stage, not only `workspace.current_stage`.
- `SetupRuntimeAdapter.build_turn_input(...)` must expose the effective canonical stage in:
  - `context_bundle.current_stage`
  - stage-aware tool scope
  - stage-state / readiness metadata
  - prior-stage handoff selection
- `SetupGraphState.target_stage` must mirror the request so graph-shell tracing/debugging does not lose the canonical selection.

### 3.4 Frontend / API Serialization Uses Snake Case Over The Wire

- Frontend may keep internal enum names such as `characterDesign`, but the request payload sent to backend must use canonical snake_case `target_stage` values such as `character_design`.
- New canonical stages must be added once to the stage-id mapping used by the setup request builder.
- Backend is not required to accept camelCase stage ids in this slice.

### 3.5 This Slice Does Not Add Stage-Specific Patch Tools

- Known canonical stages may continue to use shared `setup.truth.write` with runtime-owned `stage_draft` injection.
- Empty `SETUP_STAGE_PATCH_TOOLS` for canonical stages is not itself a bug in this slice.
- Do not widen this ingress slice into a new stage-specific patch-tool family.

### 3.6 Compatibility Boundary During Dual-Track Migration

- `current_stage` is the canonical lifecycle signal for new code when present.
- `current_step` remains required while:
  - provider/runtime-state persistence still keys some logic by legacy step
  - old eval fixtures still submit `target_step`
  - old setup read/write mirrors still exist
- New turn-ingress code must prefer `target_stage` for stage identity and use `current_step` only where a legacy bridge is still required.

## 4. Validation & Error Matrix

| Condition | Expected Handling |
| --- | --- |
| `target_stage = character_design`, `target_step = foundation` | valid; effective stage is `character_design`, effective step is `foundation` |
| `target_stage = character_design`, `target_step = story_config` | reject request before runtime execution |
| `target_stage` missing, `target_step = foundation` | keep legacy behavior |
| `target_stage` missing, `workspace.current_stage = world_background` | use workspace current stage |
| `target_stage` not in `workspace.stage_plan` | reject request before runtime execution |
| `target_stage = overview`, `target_step` omitted | valid; effective step uses legacy mapping only as compatibility fallback |
| frontend selects `characterDesign` view | request payload sends `target_stage = "character_design"` |
| trace / eval request capture records setup turn target | preserve `target_stage` when present |

## 5. Good / Base / Bad Cases

Good:

- User clicks `character_design` while the workspace is still on legacy `foundation`; the request carries `target_stage="character_design"`, runtime preserves that stage through context/tool scope/handoff selection, and only uses `foundation` as a compatibility step.

Base:

- Old tests or callers continue to send only `target_step="story_config"`; runtime behavior remains unchanged.

Bad:

- Frontend selects `character_design`, but only `target_step="foundation"` is sent, causing runtime to keep `current_stage="world_background"` from workspace state.
- New code compares canonical stage intent only through `current_step`.

## 6. Tests Required

- `backend/tests/test_rp_setup_agent_api.py`
  - request accepts `target_stage`
  - mismatched `target_stage` / `target_step` is rejected
  - `target_stage` override survives response payload / trace metadata
- `backend/rp/tests/test_setup_agent_execution_service_v2.py`
  - `target_stage` overrides `workspace.current_stage` even when the legacy `target_step` bucket is the same
  - effective `current_step` still maps from stage for compatibility
  - context packet / context bundle expose the overridden `current_stage`
- `backend/rp/tests/test_setup_agent_tool_scope.py`
  - canonical stage override still yields the expected stage-aware tool scope
- frontend request tests or targeted widget/model tests
  - selected setup stage serializes to snake_case `target_stage`

## 7. Wrong vs Correct

Wrong:

- Keep `target_step` as the only turn-ingress selector after canonical stage rendering already exists in the frontend.
- Add stage-specific patch tools as a prerequisite for fixing stage selection.
- Treat camelCase frontend enum names as the protocol truth.

Correct:

- Carry canonical `target_stage` end-to-end through request, graph shell, runtime launch, context assembly, and trace surfaces.
- Keep `target_step` only as a compatibility mirror where legacy step-based code still exists.
