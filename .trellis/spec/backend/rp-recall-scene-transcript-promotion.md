# RP Recall Scene Transcript Promotion

## Scenario: Closed-scene transcript can enter Recall only after explicit selection, filtering, and scene-close identity exist

### 1. Scope / Trigger

- Trigger: Recall now preserves multiple runtime-generated source families (`chapter_summary`, `accepted_story_segment`, `continuity_note`) and callers can search them via metadata filters, but the next apparent history gap, `scene_transcript`, still lacks executable promotion rules.
- Applies to future RP backend implementation across:
  - `StoryDiscussionEntry` runtime traces
  - accepted `story_segment` artifacts
  - future scene-close maintenance wiring
  - future Recall transcript ingestion service
  - retrieval-core Recall asset/document/chunk ingestion
  - focused transcript-promotion tests
- This slice exists to freeze the promotion contract before code. It does not authorize treating current chapter discussion as transcript history, and it does not add a new public memory tool/API.

### 2. Signatures / Surfaces

Current source models:

```python
class StoryDiscussionEntry(BaseModel):
    entry_id: str
    session_id: str
    chapter_workspace_id: str
    role: Literal["user", "assistant", "system"]
    content_text: str
    linked_artifact_id: str | None = None
    created_at: datetime

class StoryArtifact(BaseModel):
    artifact_id: str
    artifact_kind: StoryArtifactKind
    status: StoryArtifactStatus
    content_text: str
    metadata: dict[str, Any]
```

Future promotion input must include an explicit closed-scene identity:

```python
class SceneTranscriptPromotionInput(BaseModel):
    session_id: str
    story_id: str
    chapter_index: int
    scene_ref: str
    source_workspace_id: str
    discussion_entries: list[StoryDiscussionEntry]
    accepted_segments: list[StoryArtifact]
```

Future Recall metadata shape:

```python
{
    "layer": "recall",
    "source_family": "longform_story_runtime",
    "materialization_event": "scene_close",
    "materialization_kind": "scene_transcript",
    "materialized_to_recall": True,
    "chapter_index": int,
    "scene_ref": str,
    "transcript_source_count": int,
    "transcript_includes_discussion": bool,
    "transcript_includes_accepted_segments": bool,
}
```

### 3. Contracts

- `scene_transcript` is historical Recall material, not `Core State.authoritative_state`, not `Core State.derived_projection`, and not Runtime Workspace by default.
- `StoryDiscussionEntry` remains runtime trace unless a later implementation receives:
  - explicit closed-scene identity (`scene_ref`);
  - ordered candidate entries;
  - transcript filtering/normalization rules;
  - a defined materialization trigger for scene close.
- Chapter close alone is not sufficient to infer a scene transcript.
- Transcript promotion must be opt-in maintenance, not a byproduct of ordinary discussion persistence.
- Candidate source filtering rules:
  - keep ordered `user` / `assistant` discussion entries by `created_at`;
  - exclude `system` discussion entries by default;
  - exclude tool chatter, raw retrieval hits, block metadata, and runtime scratch;
  - allow accepted `story_segment` artifacts only when they belong to the same closed scene;
  - exclude draft and superseded artifacts.
- Transcript normalization rules:
  - strip blank items;
  - preserve source order;
  - preserve speaker/source labels in the rendered transcript;
  - do not silently merge multiple scenes into one transcript asset.
- Transcript asset identity rules:
  - one deterministic Recall asset per `(session_id, chapter_index, scene_ref)`;
  - rerun/reindex of the same closed scene must reuse the same logical asset;
  - chapter index alone must not be treated as scene identity.
- Public tool boundaries remain frozen:
  - no `memory.search_scene_transcript` tool in this slice;
  - transcript retrieval must continue to flow through `memory.search_recall` once the source family is actually materialized.
- `character_long_history_summary` and `retired_foreshadow_summary` remain deferred until the repo has a real maintenance producer for them. They must not be faked by overloading transcript promotion.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Scene lifecycle / `scene_ref` does not exist in current repo state | Do not materialize `scene_transcript` yet |
| Discussion entries exist but no explicit closed-scene identity is provided | Keep them as Runtime Workspace traces only |
| Discussion entry role is `system` | Exclude it by default from transcript materialization |
| Accepted artifact is `draft` or `superseded` | Exclude it from transcript materialization |
| Multiple scenes are mixed in one candidate list | Reject or split before ingestion; do not emit one merged transcript asset |
| Same closed scene is re-materialized | Reuse/reindex the deterministic asset id |
| Transcript text becomes empty after filtering blanks/system-only content | Skip ingestion rather than create empty Recall history |
| Retrieval-core ingestion fails | Raise `recall_scene_transcript_ingestion_failed:{asset_id}:{detail}` |

### 5. Good / Base / Bad Cases

- Good: a future explicit scene-close path passes ordered `user`/`assistant` discussion plus accepted scene prose for `scene_ref="chapter-3-scene-2"`, and Recall stores one `scene_transcript` asset for that closed scene.
- Good: rerunning the same scene-close maintenance updates/reindexes the same transcript asset instead of duplicating history.
- Base: chapter close without scene identity may still produce `chapter_summary`, `accepted_story_segment`, and a `continuity_note` when heavy regression emits non-empty maintenance output, but it produces no transcript.
- Bad: treating every `StoryDiscussionEntry` in a chapter as one transcript because discussion rows already exist.
- Bad: mixing tool output, retrieval debug text, or runtime scratch into a historical transcript.
- Bad: using transcript promotion to synthesize long-history summaries that do not yet have a dedicated maintenance producer.

### 6. Tests Required

- Contract/boundary tests:
  - prove current repo state does not materialize transcripts while scene lifecycle/identity is absent;
  - prove Runtime Workspace discussion/draft blocks remain marked `scene_transcript = False`.
- Future transcript promotion tests:
  - ordered `user` / `assistant` entries normalize into deterministic transcript text;
  - `system` entries and blank content are excluded;
  - draft/superseded artifacts are excluded;
  - rerun for the same `(session_id, chapter_index, scene_ref)` reuses the same asset identity;
  - retrieval search returns `materialization_kind="scene_transcript"` with `scene_ref` metadata and existing Recall search filters can target it.
- Failure-path tests:
  - retrieval-core `IndexJob` failure raises explicit transcript-ingestion error;
  - missing `scene_ref` or mixed-scene candidate sets do not silently ingest malformed history.

## Status on 2026-04-28

- Implemented `RecallSceneTranscriptIngestionService` on top of the existing retrieval-core asset/document/chunk ingestion chain.
- The current repo now materializes `scene_transcript` through explicit scene-close paths:
  - `StoryRuntimeController.close_current_scene(...)` materializes the just-closed scene transcript;
  - `StoryTurnDomainService.complete_chapter(...)` materializes the last open scene transcript before the chapter is finalized;
  - `StoryTurnDomainService.accept_pending_segment(...)` reruns transcript ingestion when a scene was already closed and its segment is accepted later.
- The rendered transcript currently merges ordered source items by `created_at`, preserves source labels (`User`, `Assistant`, `Accepted Segment rN`), and excludes blank/system/draft/superseded inputs.
- Service boundary protection is now explicit:
  - `build_promotion_input(...)` rejects eligible candidates with missing `scene_ref`;
  - `ingest_scene_transcript(...)` also rejects blank `scene_ref` even when a caller bypasses the builder and constructs `SceneTranscriptPromotionInput` directly.
- Public boundaries remain unchanged:
  - no new public memory tool/API was added;
  - retrieval access stays on `memory.search_recall`.

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: discussion rows exist, therefore they are already Recall transcript history.
recall_scene_transcript_ingestion_service.ingest(
    discussion_entries=story_session_service.list_discussion_entries(...),
)
```

#### Correct

```python
# Correct: transcript promotion waits for an explicit closed-scene trigger plus
# filtered, ordered source material.
if scene_ref and scene_is_closed:
    recall_scene_transcript_ingestion_service.ingest(
        SceneTranscriptPromotionInput(
            session_id=session_id,
            story_id=story_id,
            chapter_index=chapter_index,
            scene_ref=scene_ref,
            source_workspace_id=source_workspace_id,
            discussion_entries=filtered_entries,
            accepted_segments=scene_segments,
        )
    )
```
