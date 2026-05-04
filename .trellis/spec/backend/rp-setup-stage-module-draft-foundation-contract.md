# RP Setup Stage Module Draft Foundation Contract

> Executable contract for canonical setup stages, reusable stage modules, data-driven draft blocks, and the committed foundation truth source surface.

## 1. Scope / Trigger

- Trigger: add or edit `backend/rp/models/setup_workspace.py`, `backend/rp/models/setup_drafts.py`, setup stage/module registries, `backend/rp/services/setup_workspace_service.py`, setup commit flow, setup draft patch flow, setup truth index/foundation read surfaces, or related tests when the change affects setup lifecycle granularity or draft storage shape.
- Applies to setup/prestory domain truth before active story runtime.
- This contract is about backend setup lifecycle and draft truth surfaces. It does not implement frontend stage rendering, skills, full retrieval materialization, or evolution UI in the first slice.
- Source:
  - User-confirmed product requirement: backend stage boundaries must match user-facing setup stages; `foundation` must not be the lifecycle bucket for both worldbuilding and character design.
  - Existing code evidence: Flutter wizard already exposes `worldBackground`, `characterDesign`, `plotBlueprint`, `writerConfig`, `workerConfig`, `overview`, and `activate`, while backend still uses coarse `SetupStepId`.
  - Existing backend pattern: setup truth is already persisted as JSON draft blocks plus accepted commit snapshots, so the least disruptive path is to generalize this block model instead of creating a new database subsystem.
  - Mature agent-framework borrowing: context handoff and stage-local compact stay stage-scoped as in prior SetupAgent specs; this contract does not borrow a heavy state-management layer.

## 2. Signatures

- `SetupStageId`
  - `world_background`
  - `character_design`
  - `plot_blueprint`
  - `writer_config`
  - `worker_config`
  - `overview`
  - `activate`
  - future module examples: `rp_interaction_contract`, `trpg_rules`
- `SetupStageModule`
  - `stage_id: SetupStageId`
  - `display_name: str`
  - `draft_block_type: str`
  - `default_entry_types: list[str]`
  - `default_section_templates: list[SetupDraftSectionTemplate]`
  - `allow_commit: bool`
  - `discussion_stage: bool`
- `SetupModeStagePlan`
  - `mode: StoryMode`
  - `stage_ids: list[SetupStageId]`
- `SetupDraftSectionKind`
  - `text`
  - `list`
  - `key_value`
- `SetupDraftSection`
  - `section_id: str`
  - `title: str`
  - `kind: SetupDraftSectionKind`
  - `content: dict[str, Any]`
  - `retrieval_role: Literal["summary", "detail", "rule", "relationship", "note"] = "detail"`
  - `tags: list[str]`
- `SetupDraftEntry`
  - `entry_id: str`
  - `entry_type: str`
  - `semantic_path: str`
  - `title: str`
  - `display_label: str | None`
  - `summary: str | None`
  - `aliases: list[str]`
  - `tags: list[str]`
  - `sections: list[SetupDraftSection]`
- `SetupStageDraftBlock`
  - `stage_id: SetupStageId`
  - `entries: list[SetupDraftEntry]`
  - `notes: str | None`
- `SetupWorkspace`
  - add `current_stage: SetupStageId | None`
  - add `stage_plan: list[SetupStageId]`
  - add `stage_states: list[SetupStageState]`
  - add `draft_blocks: dict[str, SetupStageDraftBlock]`
  - keep legacy fixed draft fields only as compatibility mirrors until later slices remove callers
- `SetupWorkspaceService`
  - `get_stage_plan(mode: StoryMode) -> SetupModeStagePlan`
  - `patch_stage_draft(workspace_id: str, stage_id: SetupStageId, draft: SetupStageDraftBlock | dict) -> SetupWorkspace`
  - `propose_stage_commit(workspace_id: str, stage_id: SetupStageId, target_draft_refs: list[str], reason: str | None = None) -> CommitProposal`
  - `accept_commit(...)` must accept canonical stage proposals as well as legacy step proposals during migration.

## 3. Contracts

- `SetupStageId` is the new canonical setup lifecycle unit.
- The longform MVP stage plan is:
  - `world_background`
  - `character_design`
  - `plot_blueprint`
  - `writer_config`
  - `worker_config`
  - `overview`
  - `activate`
- Shared stage modules, such as `writer_config`, must be reusable by later `longform`, `roleplay`, and `trpg` mode plans.
- Stage modules are composition units, not one-off frontend labels. A mode plan selects modules from the catalog.
- Draft blocks must be data-driven by stage/module ID:
  - `draft_blocks["world_background"]`
  - `draft_blocks["character_design"]`
  - `draft_blocks["plot_blueprint"]`
  - and so on
- New setup-domain code must not write worldbuilding and character design into one shared `foundation_draft` bucket.
- Legacy fixed draft fields may remain as read compatibility mirrors during migration, but they must not be the new canonical path.
- `SetupStageDraftBlock` is the stable renderable grammar:
  - stable entry metadata
  - stable section grammar
  - flexible domain content inside the allowed `section.kind` payload
- Backend core validates syntax and renderability. It must not encode genre-specific requirements such as "wuxia faction must have sect leader" or "cyberpunk gang must have territory".
- Commit boundary:
  - before commit, LLM and user may jointly edit draft blocks;
  - commit requires syntactically valid stage draft JSON;
  - blank/incomplete semantic content may still commit if the user chooses;
  - structurally invalid JSON must not commit;
  - after commit, the agent does not reprocess that stage draft.
- Accepted setup truth is the source for later foundation/read/retrieval materialization. Retrieval jobs and truth-index rows must be derived deterministically from accepted snapshots, not from raw setup discussion.
- Stage progression must be stage-scoped:
  - accepting `world_background` advances `current_stage` to `character_design`;
  - it must not wait for old coarse `foundation` to include both worldbuilding and character design.

## 4. Validation & Error Matrix

| Condition | Boundary | Expected Handling |
| --- | --- | --- |
| Unknown `stage_id` | request/service | reject before mutation |
| Stage not in current mode plan | request/service | reject before mutation |
| Draft block `stage_id` differs from requested `stage_id` | patch/commit | reject before mutation |
| Missing `entry_id` | pydantic/service | reject with validation error |
| Missing `entry_type` | pydantic/service | reject with validation error |
| Missing `semantic_path` | pydantic/service | reject with validation error |
| Missing `section_id` | pydantic/service | reject with validation error |
| Unsupported `section.kind` | pydantic/service | reject with validation error |
| `text` section without text content | pydantic/service | reject with validation error |
| `list` section without list items | pydantic/service | reject with validation error |
| `key_value` section without dict values | pydantic/service | reject with validation error |
| Stage draft missing entirely and user commits blank stage | commit | allowed if no invalid draft exists |
| Stored stage draft payload is structurally invalid | commit | reject before accepted snapshot |
| Accepted stage has retrieval materialization pending | next stage | does not block next stage |
| Legacy callers still read fixed fields | migration | keep mirrors until slice explicitly removes them |

## 5. Good / Base / Bad Cases

Good:

- `world_background` writes `world_background.race.elf` with `lifespan`, `culture`, and `taboo` sections, commits, and the next current stage becomes `character_design`.
- `character_design` writes `character_design.protagonist.lin_yue` into a separate block and does not mutate `world_background`.
- `writer_config` is one shared module that later mode plans can reuse.

Base:

- A blank `worker_config` stage has no entries but is structurally valid and can be committed by explicit user action.

Bad:

- `world_background` and `character_design` both write into `foundation_draft.entries`.
- Backend keeps `foundation` as the lifecycle boundary and treats frontend stages as labels only.
- Commit accepts malformed section payloads that the backend cannot render or materialize.
- Retrieval calls an LLM after commit to rewrite the user's accepted draft into semantic entries.

## 6. Tests Required

- Backend model/service tests:
  - longform `create_workspace` exposes the canonical stage plan and starts at `world_background`;
  - `world_background` and `character_design` draft blocks are separate and do not share `foundation_draft`;
  - reusable `writer_config` stage module exists in the catalog and is included by longform plan;
  - `patch_stage_draft` rejects a stage not present in the workspace mode plan;
  - `patch_stage_draft` rejects missing IDs, empty semantic paths, unsupported section kind, and invalid section content shape;
  - `propose_stage_commit` or `accept_commit` rejects structurally invalid stored stage draft payloads;
  - accepting `world_background` advances canonical `current_stage` to `character_design`;
  - accepted stage snapshot preserves `stage_id`, block payload, committed refs, and source block type.
- Later-slice tests:
  - setup tools use stage-aware refs and draft blocks;
  - prior-stage handoff is generated from canonical stage commits;
  - Setup Truth Index can rebuild from committed snapshots;
  - retrieval materialization starts from entry/section boundaries;
  - frontend renders stage plan and draft blocks from data-driven response shape.

## 7. Wrong vs Correct

Wrong:

- Keep `SetupStepId.FOUNDATION` as the actual backend lifecycle and only rename UI tabs.
- Add one hardcoded top-level Pydantic field per future setup stage.
- Validate by prompt instruction only and let malformed draft JSON reach commit.
- Force every mode to duplicate a complete stage list even when modules are shared.

Correct:

- Introduce canonical `SetupStageId` and mode-specific plans composed from reusable stage modules.
- Store current/future setup drafts in data-driven `draft_blocks` keyed by stage/module.
- Keep legacy fields only as explicit migration compatibility until dependent callers move.
- Validate the generic entry/section grammar at patch and commit boundaries.
- Treat retrieval readiness as asynchronous and non-blocking for setup stage progression.
