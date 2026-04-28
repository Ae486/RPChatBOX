# RP Recall Retired Foreshadow Retention

## Scenario: Chapter-close authoritative foreshadow retirement snapshots become historical Recall summaries

### 1. Scope / Trigger

- Trigger: Recall now preserves `chapter_summary`, `accepted_story_segment`, `continuity_note`, `scene_transcript`, and `character_long_history_summary`, but long-context continuity still lacks a durable path for foreshadow chains that have already been settled.
- Applies to RP backend implementation across:
  - heavy regression / chapter close maintenance;
  - authoritative `foreshadow_registry` snapshots inside `StorySession.current_state_json`;
  - future `RecallRetiredForeshadowIngestionService`;
  - retrieval-core Recall asset/document/chunk ingestion;
  - focused retired-foreshadow tests.
- This slice does **not** add a new public memory tool or a new durable Block store.
- This slice does **not** add a new authoritative mutation surface for foreshadow records. It only materializes explicit terminal snapshots that already exist in authoritative state.
- This slice must not infer retirement from `summary_updates[]`, runtime discussion, or retrieval text.

### 2. Signatures / Surfaces

Current authoritative snapshot source:

```python
StorySession.current_state_json["foreshadow_registry"]
```

Future ingestion input:

```python
class RetiredForeshadowSummaryInput(BaseModel):
    session_id: str
    story_id: str
    chapter_index: int
    source_workspace_id: str
    foreshadow_id: str
    foreshadow_snapshot: dict[str, Any]
    terminal_status: str
    chapter_summary_text: str | None = None
    continuity_notes: list[str] = Field(default_factory=list)
    accepted_segments: list[StoryArtifact] = Field(default_factory=list)
```

Future service surface:

```python
class RecallRetiredForeshadowIngestionService:
    def ingest_retired_foreshadow_summaries(
        self,
        *,
        session_id: str,
        story_id: str,
        chapter_index: int,
        source_workspace_id: str,
        foreshadow_registry: list[dict[str, Any]],
        chapter_summary_text: str | None,
        continuity_notes: list[str],
        accepted_segments: list[StoryArtifact],
    ) -> list[str]: ...
```

Future Recall metadata shape:

```python
{
    "layer": "recall",
    "source_family": "longform_story_runtime",
    "materialization_event": "heavy_regression.chapter_close",
    "materialization_kind": "retired_foreshadow_summary",
    "materialized_to_recall": True,
    "chapter_index": int,
    "foreshadow_id": str,
    "terminal_status": str,
    "includes_chapter_summary": bool,
    "continuity_note_count": int,
    "accepted_segment_evidence_count": int,
}
```

### 3. Contracts

- `retired_foreshadow_summary` belongs to `Recall Memory`, not `Core State.authoritative_state`, not `Core State.derived_projection`, and not `Runtime Workspace`.
- Producer boundary:
  - current repo state does **not** yet have a dedicated specialist output family for retired-foreshadow summaries;
  - current authoritative apply flow does not support in-place `set_status` for `foreshadow_registry`;
  - therefore this slice must use the authoritative chapter-close `foreshadow_registry` as an append-order snapshot source and only materialize entries that already carry an explicit terminal marker.
- Candidate rules:
  - only `dict` items inside `foreshadow_registry` are eligible;
  - require non-blank `foreshadow_id`;
  - require explicit terminal marker at `status` or `state`;
  - recognized terminal values in this slice are `resolved`, `retired`, and `closed`;
  - non-terminal or markerless entries are skipped;
  - if multiple registry entries describe the same `foreshadow_id`, the last terminal snapshot in registry order wins;
  - supporting accepted segments must remain `StoryArtifactStatus.ACCEPTED`;
  - draft/superseded artifacts must not appear as retired-foreshadow evidence.
- Rendering rules:
  - render one deterministic summary per `(session_id, chapter_index, foreshadow_id)`;
  - preserve the `foreshadow_id` and `terminal_status` in rendered text and metadata;
  - render the terminal authoritative snapshot first, then optional chapter-close context/evidence;
  - accepted-segment evidence matching may remain conservative in this slice, but it must be deterministic and rooted in explicit snapshot text rather than semantic guesswork.
- Identity rules:
  - asset identity must be deterministic per `(session_id, chapter_index, foreshadow_id)`;
  - rerun of the same chapter-close input must reindex/reuse the same asset id.
- Public boundaries remain frozen:
  - no `memory.search_retired_foreshadow` tool in this slice;
  - retrieval continues through `memory.search_recall`.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| `foreshadow_registry` is empty or missing | Skip retired-foreshadow ingestion |
| Registry item is not a dict | Skip that item |
| `foreshadow_id` is blank after normalization | Skip that item |
| Registry item has no `status` / `state` terminal marker | Skip that item |
| Same `foreshadow_id` has both active and resolved snapshots | Materialize only the last terminal snapshot |
| Accepted artifact is `draft` or `superseded` | Exclude it from evidence |
| Same chapter-close reruns for the same `foreshadow_id` | Reuse/reindex the same logical asset |
| Retrieval-core ingestion fails | Raise `recall_retired_foreshadow_ingestion_failed:{asset_id}:{detail}` |

### 5. Good / Base / Bad Cases

- Good: chapter close leaves `foreshadow_registry` with an earlier `status="active"` entry and a later `status="resolved"` entry for the same `foreshadow_id`; Recall stores one `retired_foreshadow_summary` asset from the resolved snapshot.
- Good: rerunning the same chapter close after changing only supporting context reindexes the same per-foreshadow asset instead of duplicating it.
- Base: a registry full of active or markerless foreshadow entries produces no retired-foreshadow Recall.
- Bad: inferring retired foreshadow directly from `summary_updates[]`.
- Bad: materializing still-active foreshadow entries into `retired_foreshadow_summary`.
- Bad: inventing a new foreshadow mutation path or public tool as part of this slice.

### 6. Tests Required

- Producer tests:
  - heavy regression ingests one asset per terminal `foreshadow_id`;
  - light regression does not ingest retired-foreshadow summaries;
  - blank ids, non-dict items, and non-terminal snapshots are skipped;
  - latest terminal snapshot wins for repeated `foreshadow_id`.
- Content tests:
  - summary text includes the `foreshadow_id`, terminal status, and authoritative snapshot content;
  - accepted-segment evidence only includes `ACCEPTED` artifacts;
  - continuity note context can be attached without becoming the producer root.
- Identity / retrieval tests:
  - rerun for the same `(session_id, chapter_index, foreshadow_id)` reuses the same asset id;
  - `memory.search_recall` can retrieve `materialization_kind="retired_foreshadow_summary"` hits.
- Failure-path tests:
  - retrieval-core failure raises the explicit `recall_retired_foreshadow_ingestion_failed:*` error.

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: any foreshadow mention in summary_updates becomes retired Recall.
if bundle.summary_updates:
    ingest_retired_foreshadow(bundle.summary_updates)
```

#### Correct

```python
# Correct: retired foreshadow Recall is rooted in authoritative
# foreshadow_registry entries that already carry an explicit terminal marker.
ingest_retired_foreshadow_summaries(
    foreshadow_registry=updated_session.current_state_json["foreshadow_registry"],
    chapter_summary_text=bundle.recall_summary_text,
    continuity_notes=bundle.summary_updates,
    accepted_segments=accepted_segments,
)
```

## Status on 2026-04-28

- Implemented `RecallRetiredForeshadowIngestionService` on top of the existing retrieval-core asset/document/chunk ingestion chain.
- The current repo now materializes `retired_foreshadow_summary` only on heavy regression / chapter close.
- Producer root is the post-apply authoritative `updated_session.current_state_json["foreshadow_registry"]` snapshot list.
- Current terminal detection is intentionally explicit and conservative:
  - only entries with non-blank `foreshadow_id`;
  - only `status` / `state` values `resolved`, `retired`, or `closed`;
  - later terminal entry wins for the same `foreshadow_id` in append order.
- Current evidence matching is intentionally narrow:
  - accepted-segment evidence uses deterministic case-insensitive substring matching against stable textual snapshot fields such as `summary`, `title`, `description`, and `resolution`;
  - it does not attempt semantic foreshadow inference in this slice.
- Public boundaries remain unchanged:
  - no new public memory tool/API was added;
  - retrieval access stays on `memory.search_recall`.
