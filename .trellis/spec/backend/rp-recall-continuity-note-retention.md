# RP Recall Continuity Note Retention

## Scenario: Heavy regression materializes continuity notes into Recall without promoting runtime scratch

### 1. Scope / Trigger

- Trigger: Recall now preserves chapter summaries and accepted prose details, and Recall search preserves source-family metadata. The next safe source family is `continuity_note` because `SpecialistResultBundle.summary_updates` already exists as a maintenance output and does not require defining scene transcript rules.
- Applies to:
  - `SpecialistResultBundle.summary_updates`
  - `LongformRegressionService.run_heavy_regression`
  - a new continuity-note recall ingestion service
  - retrieval-core source asset / parsed document / chunk ingestion
  - focused regression and retrieval tests
- This slice does not implement scene transcript promotion. It does not treat `StoryDiscussionEntry` as transcript material.

### 2. Signatures / Surfaces

Service:

```python
class RecallContinuityNoteIngestionService:
    def ingest_continuity_notes(
        self,
        *,
        session_id: str,
        story_id: str,
        chapter_index: int,
        source_workspace_id: str,
        summary_updates: list[str],
    ) -> list[str]: ...
```

Regression wiring:

```python
class LongformRegressionService:
    def __init__(
        ...,
        recall_continuity_note_ingestion_service: RecallContinuityNoteIngestionService | None = None,
        ...
    ) -> None: ...
```

Recall metadata:

```python
{
    "layer": "recall",
    "source_family": "longform_story_runtime",
    "materialization_event": "heavy_regression.chapter_close",
    "materialization_kind": "continuity_note",
    "materialized_to_recall": True,
    "chapter_index": int,
    "note_index": int,
    "source_type": "continuity_note",
}
```

### 3. Contracts

- `summary_updates` are transport/maintenance output, not authoritative truth and not settled projection slots.
- During heavy regression / chapter close, non-empty `summary_updates` may be materialized as Recall `continuity_note` assets.
- Continuity-note ingestion must stay additive:
  - no Core State authoritative mutation;
  - no projection refresh;
  - no proposal/apply path;
  - no Runtime Workspace promotion.
- Empty/blank notes are skipped.
- Repeated heavy regression with the same note text for the same session/chapter must reuse deterministic asset identity rather than creating duplicate continuity-note assets.
- `note_index` is source metadata only and must not participate in deterministic asset identity.
- Different note text in the same chapter must create distinct deterministic assets.
- The physical storage path remains retrieval-core:
  - `rp_source_assets`
  - `rp_parsed_documents`
  - `rp_knowledge_chunks`
  - `rp_embedding_records`
  - `rp_index_jobs`
- Ingestion failure must surface from returned `IndexJob`; do not report false success.
- Runtime Workspace discussion entries remain outside this path.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Heavy regression bundle has non-empty `summary_updates` | Persist one Recall `continuity_note` asset per distinct note |
| Note is blank | Skip it |
| Same note appears twice in one bundle | Ingest once |
| Same note appears on a rerun for the same session/chapter | Reindex/reuse the same deterministic asset id |
| Same note appears at a different `note_index` on rerun | Reindex/reuse the same deterministic asset id; update metadata with the latest source note index |
| Different note appears in same chapter | Create a separate continuity-note asset |
| Retrieval-core ingestion fails | Raise `recall_continuity_note_ingestion_failed:{asset_id}:{detail}` |
| Runtime discussion entry exists | Do not ingest it as continuity note |
| `summary_updates` exists during light regression | Do not materialize continuity notes in this slice |

### 5. Good / Base / Bad Cases

- Good: chapter close emits "The masked envoy now knows the seal phrase"; Recall search later returns it with `materialization_kind="continuity_note"`.
- Good: re-running chapter close does not duplicate the same continuity note asset.
- Base: no `summary_updates` means no continuity-note ingestion.
- Bad: writing continuity notes into `Core State.authoritative_state` directly.
- Bad: adding continuity notes to `Core State.derived_projection` merely because they are summaries.
- Bad: indexing current-turn discussion text as continuity notes.
- Bad: treating continuity notes as scene transcripts.

### 6. Tests Required

- New ingestion service tests:
  - non-empty notes produce deterministic Recall source assets with metadata and seed section metadata;
  - duplicate notes are deduplicated;
  - repeated ingestion reuses/reindexes deterministic assets;
  - changed `note_index` for the same note does not create a duplicate asset;
  - failed `IndexJob` raises explicit error.
- Retrieval integration:
  - `memory.search_recall` can retrieve continuity-note text and preserves `source_family`, `materialization_event`, `materialization_kind`, `materialized_to_recall`, and `note_index`.
- Regression integration:
  - heavy regression materializes `summary_updates` as continuity notes when the continuity-note service is wired;
  - light regression does not materialize continuity notes;
  - draft/superseded artifacts and discussion entries remain outside Recall continuity-note ingestion.

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: summary_updates silently disappear after heavy regression.
if bundle.summary_updates:
    pass
```

#### Correct

```python
# Correct: heavy-regression maintenance may persist summary_updates as historical
# continuity notes in Recall, without mutating Core State or Runtime Workspace.
if bundle.summary_updates:
    recall_continuity_note_ingestion_service.ingest_continuity_notes(...)
```
