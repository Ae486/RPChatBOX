# Setup Stage Module / Draft / Retrieval Contract

> Status: task-level spec draft  
> Scope: SetupAgent setup-domain contract redesign after agent-body capability work  
> Date: 2026-05-04  
> Source: user design review + current implementation check

## 1. Scope / Trigger

This spec captures the agreed direction for splitting setup stage granularity and draft truth surfaces.

The trigger is a real lifecycle mismatch:

- Frontend UX treats setup as user-facing stages such as `worldBackground`, `characterDesign`, `plotBlueprint`, `writerConfig`, and `workerConfig`.
- Backend currently treats setup as four coarse `SetupStepId` values: `foundation`, `longform_blueprint`, `writing_contract`, and `story_config`.
- This mismatch breaks the desired context-engineering boundary. For example, after the worldbuilding stage commits, the system should compact/handoff into the character stage. With the current backend shape, worldbuilding and character design remain inside one `foundation` step.

The new contract must make stage boundaries, draft structure, compact handoff, and retrieval materialization maintainable under multiple modes: `longform`, `roleplay`, and `trpg`.

Database migration is not a constraint for this redesign. The user has explicitly allowed deleting the existing setup database/state if the clean design is cheaper and more maintainable than patching legacy shape.

## 2. Core Decisions

### 2.0 Terminology

Use these terms consistently:

- `draft`: editable setup-stage truth before user commit.
- `committed foundation truth` / `foundation`: user-accepted setup truth after commit.
- `Setup Truth Index`: deterministic read model generated from committed foundation truth.
- `retrieval`: asynchronous materialized semantic recall layer over indexed/embedded Archival and other source material.

This avoids mixing editable draft, committed setup truth, direct committed-truth reads, and retrieval-layer semantic recall.

### 2.1 Stage Is The Canonical Lifecycle Unit

Backend lifecycle should align with user-facing setup stages.

Confirmed direction:

- Replace the old coarse main-path lifecycle unit with canonical setup stages.
- Old `foundation` must not remain the lifecycle boundary for both worldbuilding and character design.
- Stage completion, commit, compact, handoff, tool scope, prompt overlay, and future skills should bind to stage ID.

Recommended longform MVP stages:

```text
world_background
character_design
plot_blueprint
writer_config
worker_config
overview
activate
```

`overview` and `activate` may remain system/UI stages with special behavior, but they must not obscure the discussion-stage lifecycle.

### 2.2 Stage Modules Are Reused By Mode Plans

Different modes should not each copy a full hardcoded stage list. Setup should use reusable stage modules composed into mode-specific plans.

Example:

```text
Stage Module Catalog
- world_background
- character_design
- plot_blueprint
- writer_config
- worker_config
- rp_interaction_contract
- trpg_rules

Mode Stage Plans
- longform: world_background -> character_design -> plot_blueprint -> writer_config -> worker_config -> overview -> activate
- roleplay: world_background -> character_design -> rp_interaction_contract -> writer_config -> worker_config -> overview -> activate
- trpg: world_background -> character_design -> trpg_rules -> writer_config -> worker_config -> overview -> activate
```

Shared stages such as `writer_config` should be implemented once and reused across modes.

### 2.3 Draft Blocks Should Also Split

The draft truth surface should not keep the old `foundation_draft` bucket as the main path.

Reason:

- If only stage is split but draft stays in a large `foundation` bucket, longform MVP assumptions continue to leak into RP/TRPG.
- Worldbuilding, character design, plot blueprint, writer config, and worker config need distinct ownership and review surfaces.

Confirmed direction:

- Split draft modules along stage/domain lines.
- Do not expose every draft as a rigid top-level workspace field.
- Prefer a registry/collection shape driven by stage/draft modules.

Candidate workspace response shape:

```json
{
  "current_stage": "character_design",
  "stage_plan": ["world_background", "character_design", "plot_blueprint"],
  "stage_states": [],
  "draft_blocks": {
    "world_background": {},
    "character_design": {},
    "plot_blueprint": {}
  }
}
```

The exact API field name can still change. The important contract is maintainability: adding, removing, or reordering stages should not require adding a new hardcoded top-level workspace draft field.

### 2.4 Common Draft Schemas May Have Mode Overlays

Reusable stages should share a base draft schema but allow mode-specific overlays.

Example:

```text
WriterConfigDraftBase
- pov_rules
- style_rules
- writing_constraints
- notes

Longform overlay
- chapter_style_rules
- narration_density

Roleplay overlay
- dialogue_turn_style
- player_agency_constraints

TRPG overlay
- gm_narration_style
- rule_text_style
```

This avoids both extremes:

- not one rigid schema that forces all modes into longform fields;
- not one duplicated writer draft schema per mode.

## 3. Draft Entry / Section Contract

### 3.1 Stable Renderable Skeleton, Flexible Domain Content

Draft content must be structured enough for backend parsing and UI rendering, but flexible enough for many genres and settings.

The user examples:

- In wuxia, a faction-like concept may be called `宗门`.
- In cyberpunk, the same upper-level concept may be a `帮派` or corporation.
- In fantasy, it may be a kingdom, church, guild, or race.

Therefore the contract is not pure weak JSON and not rigid genre-specific schema.

The recommended shape is:

```text
Stable entry metadata
+ stable structured sections
+ flexible fields inside allowed syntax
+ templates supplied by stage/mode/skill/user preferences
```

Candidate entry shape:

```json
{
  "entry_id": "faction_qingyun",
  "entry_type": "faction",
  "semantic_path": "world_background.faction.qingyun",
  "title": "青云宗",
  "display_label": "宗门",
  "summary": "正道大宗，掌控青云山脉灵脉。",
  "aliases": ["青云门"],
  "tags": ["world", "faction", "wuxia"],
  "sections": []
}
```

Candidate section shape:

```json
{
  "section_id": "relationships",
  "title": "关系",
  "kind": "list",
  "content": {
    "items": ["与玄阴教敌对", "与天工阁有交易"]
  },
  "retrieval_role": "detail",
  "tags": ["relationship"]
}
```

The backend must be able to parse and render every committed entry/section through fixed logic.

### 3.2 Template Ownership

Templates should not be hardcoded only in backend service branches.

Confirmed direction:

- `StageModule` provides default entry types and section templates.
- Mode config, skills, and user preference can extend or override labels/templates.
- Backend core validates syntax and renderability.
- Backend core should not encode genre-specific assumptions such as "faction must have leader/territory/members".

### 3.3 Commit-Time Structural Guarantees

The agent and user jointly maintain draft content before commit.

Before commit, stage draft must pass structural validation:

- `stage_id` is valid for current mode plan.
- `entry_id` and `section_id` are stable and non-empty.
- `semantic_path` is stable and non-empty.
- `entry_type` is present.
- `section.kind` belongs to a backend-renderable kind set.
- section content is non-empty where required.
- retrieval-facing fields are syntactically valid.

The current SetupAgent already has useful reliability primitives:

- Pydantic tool validation.
- structured-output parameter enhancement where supported.
- validation-error repair retry.
- bounded retry policy.
- draft readback tool for compact recovery.

However, the old draft schemas do not yet implement this new entry/section contract. Implementing the new draft contract is still required.

## 4. Retrieval Materialization Contract

### 4.1 Setup Draft Is Retrieval Source Material

Setup draft is not only user-facing content. It is the structured source material from which retrieval seed sections should be derived.

Current implementation already has a partial path:

- accepted setup commits can be ingested into Archival retrieval;
- old foundation entries become seed sections;
- old `domain_path` is generated from `foundation.{domain}.{path}`;
- old chunk boundary is entry-level and does not understand structured inner sections.

This is insufficient for the new design.

### 4.2 LLM Builds Semantic Tree; Backend Derives Seed Sections

Confirmed direction:

- Before commit, LLM and user produce structured draft entries and sections.
- After commit, agent work for that stage is done.
- Backend/retrieval layer deterministically derives retrieval seed sections from committed snapshot.
- Agent must not perform another post-commit semantic rewrite of that draft.

Recommended division:

```text
LLM/user before commit:
- organize semantic entries
- choose entry type and semantic path
- write renderable sections
- provide retrieval-facing hints where useful

Backend after commit:
- inject runtime-owned IDs/metadata
- generate seed sections from entries/sections
- split oversized sections mechanically
- enqueue embedding and graph extraction
- record diagnostics
```

### 4.3 Chunk Boundary Rule

Retrieval chunks should start from the smallest independently retrievable semantic unit.

Example:

```text
world_background.race              -> usually category/parent summary
world_background.race.elf          -> entity entry, good parent unit
world_background.race.elf.lifespan -> detail section, good child unit if content is substantive
world_background.race.elf.culture  -> detail section, good child unit if content is substantive
```

The system should not blindly choose "race" or "elf" by fixed depth. It should use the structured draft tree:

- entry = semantic entity/rule/truth unit;
- section = independently renderable and potentially retrievable detail under the entry;
- parent category nodes may provide summaries but are not always full retrieval chunks.

### 4.4 Post-Commit Backend Processing

Commit means the stage draft is frozen as user-approved truth.

After commit, backend may perform deterministic processing:

- trim whitespace;
- generate runtime-owned IDs;
- normalize slugs/path formatting where semantics are unchanged;
- inject commit/workspace/stage metadata;
- derive seed sections;
- split oversized sections by paragraph or sliding window with overlap;
- queue embedding and graph extraction.

Backend must not perform semantic repair after commit:

- no inferred missing setting facts;
- no LLM rewrite of committed text;
- no semantic merge/split of entities;
- no renaming of semantic paths;
- no automatic conflict resolution.

The expected residual issue after a good pre-commit path should mainly be oversized-section splitting. Other issue classes are fallback paths, not normal flow.

### 4.5 Setup Truth Index

Accepted setup truth should produce a lightweight deterministic read model after commit.

Name:

```text
Setup Truth Index
```

This is not a second retrieval system. It is a structural index over committed setup draft JSON.

Generation rule:

- generated only from accepted commit snapshots;
- generated by backend deterministic logic;
- rebuildable from committed snapshots;
- not authored or repaired by the agent after commit;
- not maintained as a persisted index during editable draft discussion.

Primary consumers:

- SetupAgent tools for locating exact prior committed truth refs;
- frontend draft directory/search/jump UI;
- retrieval diagnostic anchors;
- future evolution entry points.

Recommended indexed fields:

```text
workspace_id
story_id
mode
stage_id
commit_id
entry_id
section_id
semantic_path
parent_path
entry_type
title
display_label
summary
aliases
tags
section_title
section_kind
retrieval_role
preview_text
content_hash
token_count
created_at
```

The index may include a backend-built `search_text`, assembled from stable fields such as title, aliases, tags, semantic path, summary, section title, and preview text. This supports lexical/path/filter search only. Embedding search remains a retrieval-layer concern.

The index should support two operations:

```text
truth_index.search(query, filters) -> candidate refs + previews
truth_index.read_refs(refs, detail, max_chars) -> exact committed/current payload slices
```

The exact tool/API names can change, but the separation matters:

- search returns small candidate refs and previews to protect context;
- read fetches bounded exact payload only after the caller has selected refs.

Formal persisted indexing is only required after commit. During editable discussion, UI may derive a transient directory from current draft JSON, but that transient projection must not become inter-stage truth.

### 4.6 Direct Foundation Read vs Retrieval

Direct reads from committed setup truth and retrieval serve different purposes.

Use direct setup truth index/read when:

- the caller has a known ref from handoff, compact recovery hints, UI selection, or lexical index search;
- the user asks for exact/full committed setup detail;
- retrieval materialization is not ready or only partially ready;
- the answer should be grounded in the user-approved committed snapshot.

Use retrieval when:

- the caller does not know the ref;
- the user asks a broad natural-language or cross-source semantic question;
- the task needs fuzzy association across setup truth, imported assets, runtime material, or graph-derived relationships.

Analogy:

```text
known path -> direct read
unknown semantic location -> retrieval
```

Direct foundation read should never read prior raw discussion. It may read:

- current editable stage draft;
- prior committed stage snapshots;
- latest accepted commit by default;
- a specific commit only when explicitly requested.

It must not read:

- uncommitted drafts from other stages;
- prior-stage raw dialogue;
- runtime Memory OS state;
- retrieval index data.

Every read result must identify its source:

```text
source = current_draft | committed_snapshot
stage_id
commit_id
ref
found
summary
payload
truncated
```

### 4.7 Retrieval Tool Availability And Partial Coverage

Retrieval tools should not be hidden or split by prior stage readiness.

Reason:

- retrieval is one unified layer, not one tool per setup stage;
- a later stage may run when `world_background` materialization is ready but `character_design` materialization is still pending;
- hiding the whole retrieval tool would lose ready coverage from earlier materialized stages.

Confirmed direction:

- retrieval tools may stay visible throughout setup/runtime where the stage policy allows retrieval;
- what can be found depends on retrieval-layer materialization progress;
- retrieval results should be friendly when coverage is partial or not ready;
- setup progression and commit must not be blocked by retrieval materialization status;
- retrieval-not-ready state should not create setup commit warnings.

The UI should later expose retrieval progress and coverage. This is a UX requirement, not a setup commit gate.

### 4.8 Async Diagnostics

Retrieval materialization runs after commit and may fail asynchronously.

Diagnostics should be stored outside the committed draft snapshot.

Diagnostic records should point to:

```text
workspace_id
commit_id
stage_id
entry_id
section_id
semantic_path
severity
code
message
suggested_fix
created_at
```

The committed snapshot remains immutable. UI can use diagnostics to show the user which stage/entry/section needs attention and provide a repair entry point.

If semantic repair is needed, the diagnostic should point to the right maintenance entry point. In the current setup phase, committed setup stages are not reopened for direct mutation. Later maintenance belongs to the evolution surface.

The broader memory principle is:

- setup produces initial committed foundation truth;
- core memory can be directly user-maintained where the product allows it;
- recall memory is rarely edited manually;
- archival/foundation truth should be maintained through evolution, not by mutating old setup commits;
- all user-visible memory should remain visible, maintainable, and traceable through the correct entry point.

This is compatible with revision/new-commit semantics: old committed truth remains traceable, and maintenance creates a new accepted change rather than silently overwriting history.

## 5. Agent Discussion Persistence Note

Current setup agent discussion messages are not product-level persisted messages.

Current checked behavior:

- Flutter page stores setup discussion entries in an in-memory `_dialogues` map keyed by workspace ID.
- Each turn sends the frontend-held history to backend in `SetupAgentTurnRequest.history`.
- Backend and LangGraph checkpoints may retain request state, but this is not a user-facing durable setup session message store.
- Drafts, commits, pending user edit deltas, and runtime cognition have backend persistence; discussion messages themselves need a separate product-level persistence slice.

This is not part of the current agent-body capability slice, but it affects setup UX and session management.

## 6. Validation & Error Matrix

| Condition | Boundary | Expected Handling |
| --- | --- | --- |
| Unknown stage ID | request/tool/commit | reject before mutation |
| Stage not in current mode plan | request/tool/commit | reject before mutation |
| Draft block not owned by current stage | tool/commit | reject or require explicit cross-stage rule |
| Missing `entry_id` / `section_id` | tool/commit | Pydantic validation error and repair retry |
| Missing or invalid `semantic_path` | tool/commit | validation error; no commit |
| Unsupported `section.kind` | tool/commit | validation error; no commit |
| Empty required section content | tool/commit | validation error or readiness warning depending severity |
| Oversized section | post-commit retrieval | deterministic paragraph/window split |
| Truth index stale/missing | post-commit read model | rebuild from committed snapshot |
| Truth index search has no lexical match | agent/UI lookup | return no candidates; caller may use retrieval for semantic search |
| Retrieval materialization not ready | retrieval tool | return normal partial/no-result behavior; do not block setup commit |
| Retrieval materialization failure | async job | diagnostic record, draft snapshot unchanged |
| Semantic inconsistency detected after commit | async diagnostic/review | diagnostic only; route to future evolution/maintenance entry point |

## 7. Good / Base / Bad Cases

Good:

- `world_background` commits a structured `race.elf` entry with `lifespan`, `culture`, and `taboo` sections.
- Handoff to `character_design` includes committed summary/refs, not raw worldbuilding discussion.
- Retrieval seed sections are derived from entry/section boundaries and preserve `semantic_path`.

Base:

- A section is valid but too long. Retrieval splits it by paragraph or sliding window while keeping parent metadata.

Bad:

- `world_background` and `character_design` both write into a shared `foundation_draft` bucket and compact only after both are done.
- Commit accepts unstructured prose that backend cannot render or materialize deterministically.
- Retrieval calls an LLM after commit to rewrite the user's committed draft into chunks.
- Async retrieval writes warnings or fixes back into the committed snapshot.

## 8. Tests Required For Implementation Slice

Backend model/service tests:

- mode plan initializes the correct stage states for `longform`;
- a reusable `writer_config` module can be referenced by multiple mode plans;
- stage draft write rejects a draft for a stage not present in the current mode plan;
- stage draft write validates entry and section IDs, semantic path, and section kind;
- commit rejects structurally invalid stage drafts;
- commit snapshot remains immutable after retrieval diagnostics are created.

Context/handoff tests:

- after `world_background` commit, `character_design` receives prior-stage handoff from `world_background`;
- raw `world_background` discussion is not injected into `character_design`;
- compact/handoff is stage-scoped, not old `foundation`-scoped.

Retrieval tests:

- committed entry/section tree produces seed sections with stable `semantic_path`;
- parent entry metadata is preserved on child section chunks;
- oversized section is split deterministically without semantic rewrite;
- materialization failure creates diagnostic state with stage/entry/section anchors.
- committed entry/section tree produces Setup Truth Index rows/projections;
- truth index can search by title/alias/tag/path and then exact-read by ref;
- truth index can be rebuilt from committed snapshot;
- retrieval not-ready does not block next-stage commit and does not create setup commit warnings.

Frontend/API tests:

- workspace response is data-driven by stage plan/draft blocks, not fixed old top-level draft fields;
- UI can render draft entries/sections from the generic contract;
- UI can show retrieval diagnostics and route to the anchored stage/entry/section.
- UI/agent read surfaces share the same Setup Truth Index anchors.

## 9. Wrong vs Correct

### Wrong

Treat `foundation` as the backend lifecycle boundary and use frontend stage labels as display-only names.

### Correct

Use canonical stage IDs as backend lifecycle truth. Let draft modules and retrieval materialization hang from the same stage boundary.

### Wrong

Make one rigid schema per genre, such as fixed wuxia faction fields or cyberpunk gang fields.

### Correct

Use stable entry/section grammar with stage/mode/skill templates that can extend labels and suggested fields.

### Wrong

Let retrieval redo semantic organization after user commit.

### Correct

Require agent/user to structure draft before commit; let retrieval perform deterministic materialization after commit.

### Wrong

Treat Setup Truth Index as another embedding/RAG system and let it compete with retrieval.

### Correct

Use Setup Truth Index for exact/path/filter/lexical committed-truth lookup. Use retrieval for semantic, fuzzy, and cross-source recall.

### Wrong

Hide the unified retrieval tool whenever one prior stage has not completed materialization.

### Correct

Keep retrieval as one unified layer. Let ready materialized content be searchable, let missing coverage return normal no-result/partial behavior, and keep setup commit independent from retrieval readiness.
