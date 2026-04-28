# RP Runtime Scene Lifecycle

## Scenario: Longform runtime needs explicit scene identity and close trigger before transcript promotion can exist

### 1. Scope / Trigger

- Trigger: the repo now has a frozen `scene_transcript` promotion boundary, but current longform runtime still stores only chapter/segment/discussion state and has no explicit scene lifecycle.
- Applies to:
  - active-story runtime models
  - story-store persistence for chapter/artifact/discussion rows
  - story session service scene lifecycle helpers
  - chapter-complete runtime transition
  - Runtime Workspace Block views for draft/discussion state
  - focused runtime/controller tests
- This slice does **not** ingest transcripts into Recall, does not add a new public memory tool, and does not widen Core State authoritative mappings yet.

### 2. Signatures / Surfaces

Runtime models gain explicit scene lifecycle fields:

```python
class ChapterWorkspace(BaseModel):
    ...
    current_scene_ref: str | None = None
    next_scene_index: int = 1
    last_closed_scene_ref: str | None = None
    closed_scene_refs: list[str] = Field(default_factory=list)

class StoryArtifact(BaseModel):
    ...
    scene_ref: str | None = None

class StoryDiscussionEntry(BaseModel):
    ...
    scene_ref: str | None = None
```

Story-store records mirror the same fields:

```python
class ChapterWorkspaceRecord(SQLModel, table=True):
    current_scene_ref: str | None
    next_scene_index: int
    last_closed_scene_ref: str | None
    closed_scene_refs_json: list[str]

class StoryArtifactRecord(SQLModel, table=True):
    scene_ref: str | None

class StoryDiscussionEntryRecord(SQLModel, table=True):
    scene_ref: str | None
```

Scene lifecycle helpers:

```python
class StorySessionService:
    def close_current_scene(self, *, session_id: str) -> ChapterWorkspace: ...

class StoryRuntimeController:
    def close_current_scene(self, *, session_id: str) -> ChapterWorkspaceSnapshot: ...
```

Deterministic runtime scene identity:

```text
chapter:{chapter_index}:scene:{scene_index}
```

### 3. Contracts

- Every chapter workspace must have an explicit open-scene identity once longform chapter runtime exists.
- `create_chapter_workspace(...)` seeds:
  - `current_scene_ref = "chapter:{chapter_index}:scene:1"`
  - `next_scene_index = 2`
  - `last_closed_scene_ref = None`
  - `closed_scene_refs = []`
- Legacy runtime-row compatibility backfill for this slice must be conservative:
  - old chapter workspaces missing scene fields are normalized to the deterministic implicit first scene;
  - old `story_segment` rows and old discussion entries are backfilled to `chapter:{chapter_index}:scene:1`;
  - backfill must not copy the chapter's current open scene ref onto older rows after runtime scene rotation has already happened.
- `StoryArtifact.scene_ref` and `StoryDiscussionEntry.scene_ref` are runtime grouping fields, not Recall history by themselves.
- Default scene-ref assignment:
  - `story_segment` artifacts inherit the chapter workspace `current_scene_ref` unless an explicit scene ref is provided;
  - runtime discussion entries inherit the chapter workspace `current_scene_ref` unless an explicit scene ref is provided;
  - chapter-outline artifacts remain scene-less in this slice unless explicitly overridden.
- `close_current_scene(session_id=...)` must:
  - read the current chapter workspace;
  - require a non-empty `current_scene_ref`;
  - append that ref to `closed_scene_refs` once;
  - set `last_closed_scene_ref` to the closed ref;
  - advance `current_scene_ref` to `chapter:{chapter_index}:scene:{next_scene_index}`;
  - increment `next_scene_index`;
  - keep chapter/session phase unchanged.
- `complete_chapter(...)` must close any remaining open scene in the completed chapter before creating the next chapter workspace.
- Scene close in this slice is runtime lifecycle only:
  - it does not materialize transcripts;
  - it does not write Recall;
  - it does not create Core State `scene.current` / `scene.closed.*` authoritative objects yet;
  - it does not route through proposal/apply.
- Runtime Workspace Block views for artifacts/discussion must preserve `scene_ref` in readable payload/metadata so later transcript promotion can group the correct runtime material.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| New chapter workspace is created | Seed deterministic open `current_scene_ref` and `next_scene_index=2` |
| Story segment draft is created without explicit `scene_ref` | Persist the chapter workspace `current_scene_ref` on the artifact |
| Discussion entry is created without explicit `scene_ref` | Persist the chapter workspace `current_scene_ref` on the discussion entry |
| Outline artifact is created without explicit `scene_ref` | Keep `scene_ref=None` |
| `close_current_scene(...)` runs with an open scene | Move current ref into `closed_scene_refs` and advance to the next deterministic scene ref |
| `close_current_scene(...)` runs twice in a row | Each call closes the then-current open scene and advances once; prior closed refs are not duplicated |
| Schema compatibility reruns on old rows after a chapter already rotated scenes | Old rows stay bound to deterministic implicit scene 1 rather than being relabeled to the latest open scene |
| `complete_chapter(...)` runs with an open scene | Close the remaining scene before moving to the next chapter |
| Runtime block view is built for draft/discussion rows | `scene_ref` remains visible in payload/metadata and non-Recall markers stay intact |

### 5. Good / Base / Bad Cases

- Good: chapter 3 starts with `chapter:3:scene:1`; two draft segments and related discussion entries all carry that `scene_ref`.
- Good: `close_current_scene(session_id=...)` moves the chapter to `chapter:3:scene:2` without touching Recall or Core State.
- Good: chapter completion auto-closes the last open scene, then chapter 4 starts with `chapter:4:scene:1`.
- Base: a chapter outline remains scene-less because it is chapter scaffolding, not scene-local prose.
- Bad: inferring scene identity later from raw timestamps because runtime rows never stored it.
- Bad: writing Recall transcript assets during scene close in this slice.
- Bad: treating chapter close as transcript ingestion rather than only runtime scene lifecycle closure.

### 6. Tests Required

- Story session service tests:
  - new chapter workspace seeds deterministic scene lifecycle fields;
  - story-segment artifacts inherit current `scene_ref`;
  - discussion entries inherit current `scene_ref`;
  - outline artifacts remain scene-less by default;
  - `close_current_scene(...)` rotates `current_scene_ref`, updates `last_closed_scene_ref`, and deduplicates closed refs.
  - compatibility backfill on pre-slice rows keeps legacy rows at deterministic implicit scene 1 even after a later scene rotation.
- Turn-domain/runtime tests:
  - `complete_chapter(...)` closes the remaining open scene before creating the next chapter;
  - next chapter starts at scene 1 with a fresh deterministic ref.
- Runtime Workspace Block view tests:
  - draft artifact and discussion-entry blocks preserve `scene_ref`;
  - existing non-Recall / non-transcript metadata stays unchanged.

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: wait until transcript ingestion time to guess which discussion entries
# belonged to the same scene.
entries = story_session_service.list_discussion_entries(...)
group_by_time_window(entries)
```

#### Correct

```python
# Correct: runtime rows carry explicit scene identity before any transcript
# promotion exists.
chapter = story_session_service.close_current_scene(session_id=session_id)
assert chapter.last_closed_scene_ref is not None
```
