# RP Recall Detail Retention

## Scenario: Accepted story prose is preserved into Recall Memory through retrieval-core

### 1. Scope / Trigger

- Trigger: the repo can already persist chapter-level recall summaries, but that is not enough to keep longform detail recoverable across very long contexts.
- Applies to:
  - `LongformRegressionService`
  - a new recall-detail ingestion service
  - retrieval-core asset/document/chunk ingestion for recall collections
  - focused regression + retrieval tests
- This slice is about preserving accepted prose detail after a chapter is closed. It does not redesign Recall Memory as a new storage family.

### 2. Signatures

Service:

```python
class RecallDetailIngestionService:
    def ingest_accepted_story_segments(
        self,
        *,
        session_id: str,
        story_id: str,
        chapter_index: int,
        source_workspace_id: str,
        accepted_segments: list[StoryArtifact],
    ) -> list[str]: ...
```

Longform regression wiring:

```python
class LongformRegressionService:
    def __init__(
        ...,
        recall_summary_ingestion_service: RecallSummaryIngestionService | None = None,
        recall_detail_ingestion_service: RecallDetailIngestionService | None = None,
        ...
    ) -> None: ...
```

### 3. Contracts

- This slice preserves **accepted longform story prose** in Recall Memory through the existing retrieval-core path.
- The physical storage path remains:
  - `rp_source_assets`
  - `rp_parsed_documents`
  - `rp_knowledge_chunks`
  - `rp_embedding_records`
  - `rp_index_jobs`
- No new Recall-specific physical tables are introduced.

Accepted prose retention contract:

- Only `StoryArtifact` items that satisfy all of the following are ingested:
  - `artifact_kind == story_segment`
  - `status == accepted`
  - non-empty `content_text`
- This slice does **not** yet ingest:
  - discussion entries
  - draft artifacts
  - superseded artifacts
  - accepted outlines
  - scene transcript aggregation
  - continuity notes

Recall asset contract:

- One deterministic recall asset is created per accepted segment.
- Asset identity must be deterministic from the accepted artifact identity so repeated heavy-regression runs reindex the same logical detail object instead of creating duplicate source assets.
- The current deterministic asset id convention is:
  - `recall_detail_{artifact_id}`
- The recall collection remains `collection_kind="recall"` and `scope="story"`.
- New accepted-detail assets enter retrieval-core through `ingest_asset(...)`; repeated heavy-regression runs for an already-known accepted artifact must reuse the same asset id and reindex through `reindex_asset(...)`.
- The persisted source asset kind for this slice is:
  - `accepted_story_segment`
- The persisted `source_ref` must stay chapter/artifact-addressable, for example:
  - `story_session:{session_id}:chapter:{chapter_index}:artifact:{artifact_id}`
- Asset/source metadata must preserve:
  - `session_id`
  - `chapter_index`
  - `artifact_id`
  - `artifact_revision`
  - `artifact_kind`
  - that the source type is accepted story prose

Parsed-section contract:

- The parsed section path must be deterministic and namespaced under recall chapter detail, for example:
  - `recall.chapter.{chapter_index}.accepted_segment.{artifact_id}`
- The retrieval chunk domain for this slice is `chapter`.
- Raw prose remains the main truth of the recall detail asset; this slice must not pre-collapse it into one summary-only representation.

Regression wiring contract:

- Recall detail ingestion runs only on the **heavy regression / chapter close** path.
- It runs after the existing bundle apply + projection refresh path has produced the updated session/chapter.
- When both summary retention and accepted-detail retention are present, chapter summary ingestion still runs first and accepted-detail retention follows in the same heavy-regression pass.
- Recall detail ingestion stays outside proposal governance because it is a retrieval/recall persistence action, not an authoritative truth mutation.
- This slice keeps current regression ownership boundaries:
  - authoritative truth updates still go through proposal/apply
  - projection refresh still stays separate
  - recall detail persistence is additive post-write retention

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Accepted story segments exist during heavy regression | Persist one recall detail asset per accepted segment and enqueue/complete retrieval ingestion |
| Same chapter heavy regression runs again with the same accepted artifact ids | Reindex the same logical recall detail assets; do not create duplicate source asset identities |
| Artifact is draft or superseded | Skip it |
| Artifact kind is not `story_segment` | Skip it |
| Accepted artifact content is empty/blank | Skip it |
| Recall detail ingestion succeeds | `memory.search_recall(...)` can retrieve accepted prose text through retrieval-core |
| Recall detail ingestion fails | Surface the failure from the retrieval-core path; do not invent a silent success |

### 5. Good / Base / Bad Cases

- Good: completing a chapter with three accepted story segments writes three deterministic recall detail assets, each searchable through Recall Memory later.
- Good: re-running heavy regression after no accepted-segment identity change reindexes the same recall assets instead of appending duplicate source assets.
- Base: chapter summary recall ingestion still exists beside accepted-prose retention; summary does not replace raw detail retention.
- Bad: only persisting chapter summary text and dropping accepted prose detail.
- Bad: ingesting current-turn draft artifacts into Recall Memory as if they were settled history.
- Bad: routing accepted prose retention through proposal/apply as if it were authoritative truth mutation.

### 6. Tests Required

- New service test:
  - accepted story segments produce recall source assets in the recall collection
  - persisted asset metadata preserves artifact/session/chapter identity
  - repeated ingestion keeps deterministic asset ids
- Retrieval integration:
  - `memory.search_recall(...)` can retrieve accepted prose text after recall detail ingestion
- Regression integration:
  - heavy regression triggers recall detail ingestion for accepted story segments
  - heavy regression does not ingest draft/superseded artifacts
- Boundary regression:
  - chapter summary ingestion still works
  - heavy regression produces one chapter-summary recall asset plus one accepted-detail recall asset per accepted story segment
  - proposal/apply and projection refresh paths remain unchanged

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: only keep the chapter summary and drop the accepted prose detail.
if bundle.recall_summary_text:
    recall_summary_ingestion_service.ingest_chapter_summary(...)
```

#### Correct

```python
# Correct: keep chapter summary retention, and additionally persist the
# accepted settled prose into Recall Memory through retrieval-core.
if bundle.recall_summary_text:
    recall_summary_ingestion_service.ingest_chapter_summary(...)
if accepted_segments:
    recall_detail_ingestion_service.ingest_accepted_story_segments(...)
```
