# RP Recall Character Long-History Retention

## Scenario: Chapter-close authoritative character snapshots become historical Recall summaries

### 1. Scope / Trigger

- Trigger: Recall now preserves `chapter_summary`, `accepted_story_segment`, `continuity_note`, and `scene_transcript`, but the next long-context quality gap is character history that can survive beyond the current hot projection window.
- Applies to RP backend implementation across:
  - heavy regression / chapter close maintenance;
  - authoritative `character_state_digest` snapshots inside `StorySession.current_state_json`;
  - future `RecallCharacterLongHistoryIngestionService`;
  - retrieval-core Recall asset/document/chunk ingestion;
  - focused character-history tests.
- This slice does **not** add a new public memory tool or a new durable Block store.
- This slice must not overload `summary_updates[]`; those remain current-summary refresh material, not historical character Recall by default.

### 2. Signatures / Surfaces

Current authoritative snapshot source:

```python
StorySession.current_state_json["character_state_digest"]
```

Future ingestion input:

```python
class CharacterLongHistorySummaryInput(BaseModel):
    session_id: str
    story_id: str
    chapter_index: int
    source_workspace_id: str
    character_key: str
    character_snapshot: Any
    chapter_summary_text: str | None = None
    continuity_notes: list[str] = Field(default_factory=list)
    accepted_segments: list[StoryArtifact] = Field(default_factory=list)
```

Future service surface:

```python
class RecallCharacterLongHistoryIngestionService:
    def ingest_character_summaries(
        self,
        *,
        session_id: str,
        story_id: str,
        chapter_index: int,
        source_workspace_id: str,
        character_state_digest: dict[str, Any],
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
    "materialization_kind": "character_long_history_summary",
    "materialized_to_recall": True,
    "chapter_index": int,
    "character_key": str,
    "includes_chapter_summary": bool,
    "continuity_note_count": int,
    "accepted_segment_evidence_count": int,
}
```

### 3. Contracts

- `character_long_history_summary` belongs to `Recall Memory`, not `Core State.authoritative_state`, not `Core State.derived_projection`, and not `Runtime Workspace`.
- Producer boundary:
  - current repo state does **not** yet have a dedicated specialist output family for long-history summaries;
  - therefore this slice must use the authoritative chapter-close snapshot in `character_state_digest` as the producer root;
  - optional context may include chapter summary text, continuity notes, and accepted segment evidence, but those are supporting inputs, not the root source of truth.
- Trigger boundary:
  - ingest only on heavy regression / chapter close;
  - do not materialize on light regression;
  - do not materialize per turn merely because `character_state_digest` exists.
- Candidate rules:
  - one Recall asset per non-empty `character_key` in `character_state_digest`;
  - skip blank keys;
  - skip entries whose normalized snapshot and supporting evidence are both empty;
  - supporting accepted segments must remain `StoryArtifactStatus.ACCEPTED`;
  - draft/superseded artifacts must not appear as character-history evidence.
- Rendering rules:
  - render one deterministic summary per `(session_id, chapter_index, character_key)`;
  - preserve the character key in the rendered text and metadata;
  - render authoritative snapshot content first, then optional chapter-close context/evidence;
  - evidence matching may be heuristic in this slice, but it must be deterministic.
- Identity rules:
  - asset identity must be deterministic per `(session_id, chapter_index, character_key)`;
  - rerun of the same chapter-close input must reindex/reuse the same asset id.
- Public boundaries remain frozen:
  - no `memory.search_character_long_history` tool in this slice;
  - retrieval continues through `memory.search_recall`.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| `character_state_digest` is empty or missing | Skip character-history ingestion |
| `character_key` is blank after normalization | Skip that character |
| Character snapshot is empty and no supporting context exists | Skip that character |
| Accepted artifact is `draft` or `superseded` | Exclude it from evidence |
| Same chapter-close reruns for the same character | Reuse/reindex the same logical asset |
| Retrieval-core ingestion fails | Raise `recall_character_long_history_ingestion_failed:{asset_id}:{detail}` |

### 5. Good / Base / Bad Cases

- Good: chapter close updates `character_state_digest["hero"]`, and Recall stores one `character_long_history_summary` asset for `hero`, with chapter-close evidence attached.
- Good: rerunning the same chapter close after no identity change reindexes the same per-character asset instead of duplicating it.
- Base: no character snapshot means this slice writes no character-history Recall and reports no false success.
- Bad: treating `summary_updates[]` as a historical character-summary producer.
- Bad: materializing raw runtime discussion or draft prose as a character-history summary.
- Bad: writing one story-wide character blob instead of per-character summaries.

### 6. Tests Required

- Producer tests:
  - heavy regression ingests one asset per non-empty character snapshot entry;
  - light regression does not ingest character-history summaries;
  - blank keys and empty snapshots are skipped.
- Content tests:
  - summary text includes the character key and authoritative snapshot content;
  - accepted-segment evidence only includes `ACCEPTED` artifacts;
  - continuity note context can be attached without becoming the producer root.
- Identity / retrieval tests:
  - rerun for the same `(session_id, chapter_index, character_key)` reuses the same asset id;
  - `memory.search_recall` can retrieve `materialization_kind="character_long_history_summary"` hits.
- Failure-path tests:
  - retrieval-core failure raises the explicit `recall_character_long_history_ingestion_failed:*` error.

## Status on 2026-04-28

- Implemented `RecallCharacterLongHistoryIngestionService` on top of the existing retrieval-core asset/document/chunk ingestion chain.
- The current repo now materializes `character_long_history_summary` only on heavy regression / chapter close.
- Producer root is the post-apply authoritative `updated_session.current_state_json["character_state_digest"]` snapshot; `summary_updates` and chapter-close prose remain supporting context only.
- Current rendering keeps the summary deterministic by:
  - preserving one Recall asset per `(session_id, chapter_index, character_key)`;
  - rendering authoritative snapshot content first;
  - attaching optional chapter summary text, deduplicated continuity notes, and accepted-segment evidence.
- Current evidence matching is intentionally conservative:
  - accepted-segment evidence uses case-insensitive `character_key` substring matching over `ACCEPTED` story segments only;
  - it does not attempt semantic character attribution in this slice.
- Public boundaries remain unchanged:
  - no new public memory tool/API was added;
  - retrieval access stays on `memory.search_recall`.

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: summary_updates already exist, so use them as the character-history producer.
if bundle.summary_updates:
    ingest_character_long_history(bundle.summary_updates)
```

#### Correct

```python
# Correct: chapter-close character history is rooted in authoritative
# character_state_digest, with chapter-close context only as supporting evidence.
ingest_character_summaries(
    character_state_digest=updated_session.current_state_json["character_state_digest"],
    chapter_summary_text=bundle.recall_summary_text,
    continuity_notes=bundle.summary_updates,
    accepted_segments=accepted_segments,
)
```
