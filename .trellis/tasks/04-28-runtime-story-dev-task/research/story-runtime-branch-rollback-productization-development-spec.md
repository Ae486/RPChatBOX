# Story Runtime Branch / Rollback Productization Development Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Branch / Rollback
>
> Stage: productization closure after Phase T
>
> Status: draft-v1

## 1. Development Goal

把既有 Branch / Rollback service 能力接到真实产品路径：

```text
Longform UI action
  -> BackendStoryService
  -> backend/api/rp_story.py route
  -> StoryRuntimeIdentityService
  -> refreshed RpChapterSnapshot
  -> Longform UI active branch linear view
  -> runtime inspect evidence
```

本阶段不是重做底层 branch truth。实现必须复用：

- `StoryRuntimeIdentityService`
- `BranchVisibilityResolver`
- `StorySessionService` / `StoryRuntimeController` snapshot read path
- `RuntimeWorkspaceMaterialService`
- existing runtime inspect sheet
- existing `BackendStoryService` request style
- existing longform page layout and snack/error patterns

## 2. Ownership / Agent Rule

Branch / Rollback productization is one coherent module. Do not split create/switch/delete/rollback across different implement agents.

Allowed split:

- one implement agent owns the whole module implementation;
- after all productization slices are complete, one check agent performs module-level check.

Subagent instruction must include:

> Existing runtime implementation is only a reference. The authoritative source is the current requirement discussion, task PRD, specs, and development specs. If old runtime-side design blocks the new spec, remove or bypass the old path in a scoped, test-backed way. Reuse mature framework/project capabilities and existing project services where they match the spec; do not build a parallel framework or truth layer.

## 3. Files / Surfaces

Expected backend write scope:

- `backend/api/rp_story.py`
- `backend/rp/controllers/story_runtime_controller.py` or existing controller facade if present
- `backend/rp/models/...` only if a route DTO does not already exist
- `backend/tests/test_rp_story_api.py`
- optionally focused backend tests under `backend/rp/tests/`

Expected frontend write scope:

- `lib/services/backend_story_service.dart`
- `lib/models/story_runtime.dart`
- `lib/pages/longform_story_page.dart`
- optionally a small widget under `lib/widgets/` if branch panel becomes too large for the page

Expected docs/tests write scope:

- this spec pair
- `story-runtime-execution-plan.md`
- targeted test files

Do not touch unrelated setup-agent / MCP / request-normalization dirty files.

## 4. Backend Implementation Plan

### B1. Route DTOs

Add minimal request / response DTOs:

```python
class StoryBranchCreateRequest(BaseModel):
    origin_turn_id: str
    branch_name: str | None = None

class StoryRollbackRequest(BaseModel):
    target_turn_id: str

class StoryBranchControlResponse(BaseModel):
    data: dict
    receipt: dict
```

`data.chapter_snapshot` should use the same JSON shape returned by existing session/chapter routes. Do not invent a second snapshot shape.

### B2. Controller facade

Add controller methods:

- `create_branch_from_turn(session_id, origin_turn_id, branch_name, actor)`
- `switch_branch(session_id, branch_head_id, actor)`
- `delete_branch(session_id, branch_head_id, actor)`
- `rollback_to_turn(session_id, target_turn_id, actor)`

Each method:

1. calls `StoryRuntimeIdentityService`;
2. flushes/commits through the existing session lifecycle pattern;
3. reads the refreshed chapter/session snapshot through existing read path;
4. returns `{snapshot, receipt}`.

Do not duplicate branch/rollback validation in the API layer. Let `StoryRuntimeIdentityService` remain the validation owner.

### B3. API routes

Add routes:

```text
POST   /api/rp/story-sessions/{session_id}/branches
POST   /api/rp/story-sessions/{session_id}/branches/{branch_head_id}/switch
DELETE /api/rp/story-sessions/{session_id}/branches/{branch_head_id}
POST   /api/rp/story-sessions/{session_id}/rollback
```

Error handling:

- map known service errors to 400 with stable `code`;
- map missing session to 404;
- do not swallow metadata such as `target_hidden_by_rollback` / `target_branch_mismatch` because it is useful for debugging.

### B4. Backend tests

Add/extend API tests proving:

- branch create from settled turn returns receipt and new active branch snapshot;
- branch create does not create a story turn;
- switch returns origin branch snapshot and writes only receipt;
- delete rejects current/default branch if that is the service contract;
- rollback returns snapshot without hidden future;
- rollback does not change active snapshot;
- writer packet / inspect after rollback do not include hidden future material.

Prefer extending existing `test_rp_story_api.py` and `test_story_runtime_identity_service.py` instead of creating a parallel branch test harness.

## 5. Frontend Implementation Plan

### F1. Models / service

Add a typed envelope model:

```dart
class RpBranchControlResult {
  final RpChapterSnapshot snapshot;
  final Map<String, dynamic> receipt;
}
```

Add service methods mirroring backend routes:

- `createBranchFromTurn`
- `switchBranch`
- `deleteBranch`
- `rollbackToTurn`

Follow existing `_ensureSuccess` and `Map<String, dynamic>.from(...)` style.

### F2. Branch indicator

In `LongformStoryPage` header:

- show current branch name / short id;
- show fork origin if present in snapshot / inspect data;
- provide button to open branch panel.

If available branch metadata is only present in inspect, first implementation may fetch inspect lazily when branch panel opens. Do not make every page refresh depend on inspect unless needed.

### F3. Per-turn actions

Add a compact action menu on visible accepted story segments:

- `从这里分支`
- `回退到这里`

Use the segment's runtime metadata to find `runtime_turn_id`. If a visible segment lacks a turn id, hide branch/rollback actions and show no broken control.

### F4. Branch panel

Implement a minimal bottom sheet / side sheet:

- list available branches from inspect or snapshot-backed metadata;
- mark current branch;
- show origin/fork/head summary;
- expose switch and delete actions where allowed;
- refresh after each control action.

The panel is a product control surface. Runtime inspect remains separate and read-only.

### F5. Rollback confirmation

Before calling rollback:

- show a confirmation dialog;
- explain that later content is hidden from the current branch, not physically deleted;
- on success, replace `_snapshot` with returned snapshot and clear selected pending/review state if it points to hidden content.

## 6. Reuse / Framework Decisions

### LangGraph

Reuse only as graph shell:

- keep checkpoint pointer / debug history as technical evidence;
- do not use LangGraph replay/fork as product branch/rollback action;
- do not add cross-thread checkpoint copy in this stage.

### OpenAI / Anthropic structured outputs

No new LLM call is needed for deterministic branch actions.

If later a branch summary is introduced, use provider structured output support or existing project pydantic validation pattern. That is not in this stage and must not expand into branch compare / merge work.

### Pi mono

Borrow product ideas, not code:

- current view is one linear active branch;
- branch panel lets user switch branch;
- fork preserves old history as lineage;
- lineage metadata can be inspectable without requiring a full tree UI.

Do not import `pi-mono`, copy its session store, or implement its tree UI.

## 7. Quality Gate

Required before module check:

```powershell
pytest backend/tests/test_rp_story_api.py -q
pytest backend/rp/tests/test_story_runtime_identity_service.py backend/rp/tests/test_story_runtime_product_wiring_writer_constraints.py -q
ruff check backend/api/rp_story.py backend/tests/test_rp_story_api.py backend/rp/services/story_runtime_identity_service.py
mypy --follow-imports=skip --check-untyped-defs backend/api/rp_story.py backend/tests/test_rp_story_api.py
flutter analyze lib/models/story_runtime.dart lib/services/backend_story_service.dart lib/pages/longform_story_page.dart lib/widgets/story_runtime_inspection_sheet.dart
```

If frontend tests exist for the touched widgets, run the focused widget tests as well. Do not create manual QA for unimplemented branch compare / merge / LangGraph replay features.

## 8. Completion Definition

The module is complete when:

1. branch create/switch/delete/rollback have product routes or explicitly documented unsupported first-version cases;
2. longform UI exposes branch indicator, branch panel, and per-turn branch/rollback actions;
3. every branch control action refreshes to a branch-visible chapter snapshot;
4. tests prove branch control actions do not create story turns;
5. rollback tests prove hidden future does not leak to snapshot / inspect / writer packet;
6. inspect remains read-only and can verify action evidence;
7. module-level `gpt-5.5 xhigh` check passes.

## 9. Known Non-Goals

- no old session compatibility;
- no legacy outline adaptation;
- no full branch tree view;
- no branch compare / merge;
- no physical purge;
- no LangGraph fork product route;
- no cross-branch Story Evolution propagation;
- no RP/TRPG active runtime;
- no eval runner / grader;
- no new worker;
- no new LLM prompt path for branch actions.
