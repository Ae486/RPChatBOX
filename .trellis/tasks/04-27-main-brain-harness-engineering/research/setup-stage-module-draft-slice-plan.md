# Setup Stage Module / Draft Slice Plan

> Status: implementation plan  
> Scope: next setup-domain backend redesign after agent-body capability slices  
> Date: 2026-05-04

## Source And Boundary

This plan implements the user-confirmed direction captured in:

- `.trellis/tasks/04-27-main-brain-harness-engineering/research/setup-stage-module-draft-retrieval-contract.md`
- `.trellis/spec/backend/rp-setup-stage-module-draft-foundation-contract.md`

Design source summary:

- User/product requirement: setup lifecycle must follow user-facing stages, not old backend `foundation`/`longform_blueprint`/`writing_contract`/`story_config` buckets.
- Existing code source: frontend wizard already has `worldBackground`, `characterDesign`, `plotBlueprint`, `writerConfig`, `workerConfig`, `overview`, `activate`; backend still stores a coarse `SetupStepId`.
- Existing backend pattern: setup draft blocks and accepted commits already exist as JSON records, so the maintainable path is to generalize them into stage-keyed blocks first.
- Mature project borrowing: keep stage-local compact/handoff principles from previous SetupAgent specs; do not introduce a heavy state-management layer.

## Slice 1: Backend Canonical Stage + Draft Block Contract

Goal:

- Introduce canonical setup stages and reusable module/mode plan registry.
- Add generic `SetupStageDraftBlock` / entry / section grammar.
- Add data-driven `draft_blocks` and canonical `current_stage` / `stage_plan` / `stage_states` to `SetupWorkspace`.
- Keep legacy fields as compatibility mirrors for old tests and callers.
- Prove `world_background` and `character_design` are separate lifecycle/draft blocks.

Implementation:

- Add models:
  - `SetupStageId`
  - `SetupStageModule`
  - `SetupModeStagePlan`
  - `SetupStageDraftBlock`
  - `SetupDraftEntry`
  - `SetupDraftSection`
- Add registry helper/module for stage plans.
- Update `SetupWorkspaceService.create_workspace` to initialize stage records for the longform plan and start at `world_background`.
- Add `patch_stage_draft(...)` for generic stage draft writes.
- Add stage-aware commit proposal/accept path for stage draft blocks.
- Keep old `patch_foundation_entry`, `patch_longform_blueprint`, etc. untouched except where compatibility requires no breakage.

Verification:

- Focused pytest for workspace service/model behavior.
- No frontend work in this slice.

## Slice 2A: Stage-Aware Context / Handoff / Draft-Ref Read Migration

Goal:

- Update setup context builder, prompt/runtime adapter metadata, draft-ref reads, and tool-scope mapping to consume canonical stage IDs and stage draft refs.
- Preserve old ref support temporarily where tests still rely on it.
- Keep setup write tools on the legacy compatibility path in this slice.

Implementation:

- Extend `setup.read.draft_refs` with stage draft refs such as `draft:world_background` and exact entry/section refs.
- Make current-stage context packet prefer `draft_blocks[current_stage]`.
- Update prior-stage handoff builder to use accepted canonical stage commits.
- Update runtime tool scope mapping from old step names to new stage modules.
- Add stage-aware fields to context packets and handoff packets without removing current `current_step` / `step_id` compatibility fields.
- Keep `setup.truth.write`, `setup.patch.foundation_entry`, and `setup.patch.longform_blueprint` unchanged except where read/context compatibility requires it.

Verification:

- Context/handoff tests prove `character_design` sees world handoff only from accepted `world_background`, not raw discussion and not old `foundation`.
- Draft-ref tests prove `draft:world_background`, `stage:world_background:race_elf`, and `stage:world_background:race_elf:summary` read from `draft_blocks`, while old refs such as `foundation:<entry_id>` still work.

## Slice 2B: Stage-Native Setup Write Tools

Goal:

- Move model-facing setup draft writes onto canonical stage draft blocks.
- Keep structured-output reliability from the existing `setup.truth.write` pilot instead of widening tool contracts casually.

Implementation:

- Extend the existing `setup.truth.write` path rather than adding `setup.patch.stage_draft`.
  - Source: the structured-output pilot already proved `setup.truth.write` has the strongest model-facing slim schema, runtime-owned argument injection, pydantic validation, and bounded repair behavior.
  - Reason: a new stage patch tool would bypass that hardened path or duplicate it.
- Add a provider-side stage-native truth-write mode:
  - `truth_write.block_type = "stage_draft"`
  - `truth_write.stage_id = <current canonical stage>`
  - `truth_write.payload` may be either one `SetupDraftEntry` payload or a full `SetupStageDraftBlock` payload.
  - Entry writes merge/replace/create one entry inside the existing stage block, then call `SetupWorkspaceService.patch_stage_draft(...)`.
  - Full-block writes validate the block and call `SetupWorkspaceService.patch_stage_draft(...)`.
- Update runtime slim truth-write argument injection:
  - when `current_stage` is available, inject `truth_write.block_type = "stage_draft"` and `truth_write.stage_id = current_stage`
  - keep provider-side `step_id` as the legacy compatibility step for runtime-state persistence
  - keep the model-facing slim schema unchanged except for description text; the model still supplies `payload_json`
- Update stage-aware tool scope:
  - canonical stages should rely on shared `setup.truth.write`
  - canonical stage scopes should stop exposing the old legacy patch-family tools by default
  - legacy steps still expose their old patch tools for compatibility when `current_stage` is absent
- Update `setup.proposal.commit` minimally:
  - if target refs are canonical stage refs such as `draft:world_background` or `stage:world_background:race_elf`, route to `propose_stage_commit(...)`
  - keep legacy refs such as `draft:story_config` on the old `propose_commit(...)` path

Verification:

- Provider tests prove `setup.truth.write` can write `stage:world_background:<entry_id>` into `draft_blocks["world_background"]` without mutating `foundation_draft`.
- Runtime tests prove a canonical stage turn exposes slim `setup.truth.write`, injects `stage_draft` / `stage_id`, and does not expose legacy patch-family tools by default.
- Commit-tool tests prove stage refs create stage commit proposals, while legacy refs still create legacy step proposals.

## Slice 3: Setup Truth Index Foundation

Goal:

- Generate deterministic read model over accepted setup stage snapshots.
- Support exact/path/filter/lexical direct read separate from semantic retrieval.
- Keep committed foundation reads separate from editable draft reads.

Implementation:

- Build index rows from accepted snapshots.
- Add search/read helpers.
- Keep this as a structural index, not an embedding/RAG replacement.
- Add read-only setup tools:
  - `setup.truth_index.search` for small lexical/path/filter candidate refs.
  - `setup.truth_index.read_refs` for bounded exact committed payload reads.
- Default reads use the latest accepted commit per canonical stage; explicit `commit_id` can target a specific accepted snapshot.
- Supported committed refs:
  - `foundation:<stage_id>`
  - `foundation:<stage_id>:<entry_id>`
  - `foundation:<stage_id>:<entry_id>:<section_id>`
  - `stage:<stage_id>:<entry_id>` and section variants as aliases for committed proposal refs.

Verification:

- Search by title/alias/tag/path.
- Exact read by ref.
- Rebuild from accepted snapshot.
- No reads from uncommitted draft changes or raw prior discussion.

## Slice 4: Retrieval Materialization From Entry/Section Tree

Executable spec:

- `.trellis/spec/backend/rp-setup-retrieval-seed-materialization.md`

Goal:

- Use committed structured draft entries/sections as retrieval seed material.
- Avoid any agent/LLM semantic rewrite after commit.

Implementation:

- Derive seed sections from stage entry/section tree.
- Reuse retrieval-core's existing paragraph/window chunker for oversized section text instead of adding a setup-side splitter.
- Preserve stage/entry/section anchors in diagnostics.

Verification:

- Seed section shape and oversized split tests.
- Retrieval-not-ready remains non-blocking for next setup stage.

## Slice 5: Frontend Data-Driven Stage Rendering

Goal:

- Replace old frontend mapping where multiple UX stages share backend `foundation`.
- Render stage plan and stage draft blocks from backend response shape.

Implementation:

- Replace fixed wizard-to-backend step mapping.
- Render generic entry/section draft blocks.
- Keep UI MVP-level, not a visual redesign.

Verification:

- Frontend/unit or API integration tests for stage plan response and draft rendering inputs.

## Implementation Stop Points

- Slice 1 stops after canonical stage/draft-block service behavior passes focused backend tests and Trellis check.
- Slice 2A stops after stage-aware context, handoff, draft-ref reads, and tool-scope mapping pass focused backend tests and Trellis check.
- Slice 2B must be a separate write-tool migration slice because `setup.truth.write` and legacy patch tools intentionally remain on the compatibility path in 2A.
