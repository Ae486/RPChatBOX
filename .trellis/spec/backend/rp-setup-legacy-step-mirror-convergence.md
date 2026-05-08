# RP Setup Legacy Step Mirror Convergence

> Executable contract for keeping `current_step` as a deterministic compatibility mirror of canonical stage progression, and for converging duplicated stage-to-step bridge logic onto one backend authority.

## 1. Scope / Trigger

- Trigger: add or edit `backend/rp/services/setup_workspace_service.py`, `backend/rp/tools/setup_tool_provider.py`, `backend/rp/services/setup_context_builder.py`, setup lifecycle tests, or setup runtime code when the change affects legacy `SetupStepId` mirror behavior after canonical stage progression.
- Applies only to setup/prestory dual-track coexistence after canonical `SetupStageId` has already become the authoritative lifecycle signal.
- This slice does not delete legacy step fields, does not redesign proposal/delta/question storage, and does not add stage-specific patch tools.
- Source:
  - Existing code evidence: `current_stage` already drives canonical setup progression, but `current_step` can remain stale when stage advancement crosses a legacy bucket boundary.
  - Existing coexistence rule: `current_stage` is canonical when present; `current_step` remains a compatibility mirror for old runtime/provider/eval surfaces.
  - User-confirmed engineering direction: clean up the real migration debt, not ghost work such as one patch tool per stage.

## 2. Signatures

- `SetupWorkspaceService._LEGACY_STEP_FOR_STAGE: dict[SetupStageId, SetupStepId]`
  - remains the single authoritative stage-to-step compatibility map
- add authoritative helper:
  - `SetupWorkspaceService.legacy_step_for_stage(stage_id: SetupStageId) -> SetupStepId`
- `SetupWorkspaceService._advance_current_stage(...)`
  - continues to choose the next canonical unfrozen stage
  - must also update `workspace.current_step` to the legacy mirror of the resulting canonical stage
- bridge consumers that need stage-to-step mapping
  - `SetupToolProvider`
  - `SetupContextBuilder`
  - other setup lifecycle helpers
  - should delegate to `SetupWorkspaceService.legacy_step_for_stage(...)` instead of maintaining local duplicate maps

## 3. Contracts

### 3.1 `current_stage` Stays Authoritative

- Canonical setup progression remains stage-first.
- `current_stage` is the lifecycle truth whenever it is present.
- This slice does not reintroduce legacy step-first routing.

### 3.2 `current_step` Must Mirror The Effective Canonical Stage

- `current_step` is a compatibility mirror, not an independently progressed lifecycle.
- Whenever canonical stage advancement changes the effective current stage, `current_step` must be synchronized to the legacy step bucket of that resulting stage.
- Example for longform:
  - after `world_background` commit, current stage becomes `character_design`, and `current_step` remains `foundation`
  - after `character_design` commit, current stage becomes `plot_blueprint`, and `current_step` must become `longform_blueprint`
  - after `plot_blueprint` commit, current stage becomes `writer_config`, and `current_step` must become `writing_contract`

### 3.3 Stage-To-Step Bridge Logic Must Be Single-Sourced

- `SetupWorkspaceService._LEGACY_STEP_FOR_STAGE` is the only map that defines legacy step mirrors for canonical stages.
- Other setup components must not keep handwritten local copies of the same mapping.
- Local helper methods may remain only as thin delegation wrappers if needed for call-site ergonomics.

### 3.4 This Slice Cleans Bridge Debt, Not Tool Semantics

- Canonical setup writes still use shared `setup.truth.write` with `stage_draft`.
- Empty `SETUP_STAGE_PATCH_TOOLS` remains acceptable in this slice.
- Do not expand this cleanup into a new family of stage-specific patch tools.

### 3.5 Overview / Activate Compatibility Mapping Must Stay Explicit

- Some canonical stages such as `overview` and `activate` still need a legacy compatibility step for old surfaces.
- If those stages map to `story_config` for compatibility, that mapping must come from the single shared authority and should be treated as compatibility-only behavior, not business meaning.
- This slice does not have to redesign those mappings, but it must avoid scattering them across multiple duplicated maps.

## 4. Validation & Error Matrix

| Condition | Expected Handling |
| --- | --- |
| advancing from `character_design` to `plot_blueprint` | `current_stage = plot_blueprint`, `current_step = longform_blueprint` |
| advancing from `worker_config` to `overview` | `current_stage = overview`, `current_step = story_config` compatibility mirror |
| tool-provider stage draft write for `character_design` | stage-to-step validation uses shared `legacy_step_for_stage(character_design)` |
| context builder needs fallback step for canonical stage | uses shared `legacy_step_for_stage(...)` |
| no unfrozen stage remains | `current_stage` and `current_step` stay on the final committed stage / mirror |

## 5. Good / Base / Bad Cases

Good:

- After the last foundation-mapped stage is frozen, the next stage is `plot_blueprint` and legacy `current_step` moves to `longform_blueprint` automatically.

Base:

- While the next canonical stage still belongs to the same legacy bucket, `current_step` stays unchanged.

Bad:

- `current_stage = plot_blueprint` while `current_step = foundation` after stage advancement.
- `SetupToolProvider` and `SetupWorkspaceService` each maintain different private copies of the stage-to-step mapping.

## 6. Tests Required

- `backend/rp/tests/test_setup_stage_module_draft_contract.py`
  - assert multi-stage advancement updates `current_step` when the canonical next stage crosses into a different legacy step bucket
- `backend/rp/tests/test_setup_tool_provider.py` or provider lifecycle tests
  - assert stage-draft validation still uses the shared stage-to-step authority
- any affected context/runtime tests
  - assert stage-aware context still resolves legacy compatibility step correctly through the shared helper

## 7. Wrong vs Correct

Wrong:

- Leave `current_step` frozen on the original legacy bucket even after canonical stage progression has crossed into a new bucket.
- Keep duplicate stage-to-step maps in provider, context builder, and workspace service.
- Treat cleanup of this bridge debt as permission to redesign the full setup lifecycle or add stage-specific patch tools.

Correct:

- Keep canonical lifecycle stage-first.
- Synchronize `current_step` deterministically as a mirror of the currently effective canonical stage.
- Centralize stage-to-step compatibility mapping in one backend authority and reuse it everywhere.
