# RP Recall Source Family Retrieval Contract

## Scenario: Recall search keeps materialization source family visible to runtime workers

### 1. Scope / Trigger

- Trigger: Recall summary/detail ingestion now writes temporal materialization metadata, but retrieval consumers still need that metadata to survive search, Block-compatible views, and specialist runtime payloads.
- Applies to:
  - `rp.retrieval.search_utils.build_chunk_hit`
  - `RetrievalBroker.search_recall`
  - `RetrievalBlockAdapterService`
  - `LongformSpecialistService`
  - focused retrieval/specialist tests
- This slice is read-only. It must not introduce new storage, new public tool families, or a universal durable `rp_blocks` table.

### 2. Signatures / Surfaces

Recall hit metadata fields:

```python
{
    "layer": "recall",
    "source_family": "longform_story_runtime",
    "materialization_event": "heavy_regression.chapter_close",
    "materialization_kind": "chapter_summary" | "accepted_story_segment" | str,
    "materialized_to_recall": True,
    "asset_id": str,
    "asset_kind": str,
    "chapter_index": int | None,
    "artifact_id": str | None,
    "artifact_revision": int | None,
    "source_ref": str | None,
}
```

Block-compatible view surfaces:

```python
class RetrievalBlockAdapterService:
    def build_block_views(self, *, hits: Sequence[RetrievalHit]) -> list[RpBlockView]: ...
```

Specialist internal payload surfaces:

```python
{
    "recall_hits": [
        {
            "excerpt_text": str,
            "domain": str,
            "domain_path": str | None,
            "metadata": dict,
            "source_family": str | None,
            "materialization_kind": str | None,
            "materialization_event": str | None,
        }
    ],
    "recall_block_views": [RpBlockView.model_dump(mode="json")],
}
```

### 3. Contracts

- `memory.search_recall` must preserve source-family metadata from retrieval-core chunks/assets into each `RetrievalHit.metadata`.
- When retrieval chunk metadata does not include a materialization field, `build_chunk_hit` may fill it from the owning `SourceAsset.metadata_json`.
- Source-asset fallback must not override an explicit chunk metadata value.
- `chapter_summary` and `accepted_story_segment` must be distinguishable after search.
- Missing or old metadata must not break retrieval. Unknown recall hits may omit these fields, but newer materialized Recall hits must keep them.
- Retrieval Block-compatible views must preserve the same metadata and must not flatten all Recall into one generic block kind.
- Retrieval Block-compatible `data_json` may include read-only routing summaries such as `source_family` and `materialization_kind`; canonical truth remains `metadata`.
- `LongformSpecialistService` must keep raw `recall_hits` and additive `recall_block_views`.
- Specialist payloads may duplicate key source-family fields beside `metadata` for easier worker routing, but the canonical truth remains `hit.metadata`.
- Runtime Workspace discussion/draft blocks must not appear in Recall search unless a future promotion/materialization spec explicitly writes selected content into Recall.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Recall hit came from `chapter_summary` asset | Hit metadata contains `materialization_kind="chapter_summary"` and `source_family="longform_story_runtime"` |
| Recall hit came from `accepted_story_segment` asset | Hit metadata contains `materialization_kind="accepted_story_segment"` and artifact identity fields |
| Chunk metadata and asset metadata disagree | Chunk metadata wins; asset metadata only fills missing fields |
| Recall hit is adapted into `RpBlockView` | Block metadata keeps the same materialization fields and `source="retrieval_store"` |
| Specialist receives recall hits | Payload keeps raw `recall_hits`, additive `recall_block_views`, and easy-access source-family fields |
| Recall hit lacks new metadata | Retrieval still succeeds; metadata remains best-effort rather than causing an error |
| Runtime Workspace discussion exists | It remains outside Recall search and cannot masquerade as `scene_transcript` |

### 5. Good / Base / Bad Cases

- Good: a worker can see that one Recall hit is a compact `chapter_summary` while another is raw accepted prose detail.
- Good: `recall_block_views[*].metadata.materialization_kind` matches the raw `recall_hits[*].metadata.materialization_kind`.
- Base: legacy Recall chunks without source-family metadata still return as ordinary Recall hits.
- Bad: specialist sees only generic excerpts and cannot tell whether a hit is summary, accepted prose, future transcript, or continuity note.
- Bad: retrieval block adapter drops `materialization_event` or `artifact_id` when building `RpBlockView`.
- Bad: discussion entries appear in Recall merely because they are visible as Runtime Workspace Blocks.

### 6. Tests Required

- Retrieval search:
  - ingest one `chapter_summary` and one `accepted_story_segment`;
  - verify `memory.search_recall` returns metadata that distinguishes both source families/materialization kinds.
  - verify legacy Recall chunks without source-family metadata still return without fabricated materialization fields.
- Retrieval block adapter:
  - verify materialization metadata survives into `RpBlockView.metadata`;
  - verify original hit metadata is not mutated.
- Specialist payload:
  - verify `recall_hits` and `recall_block_views` both preserve materialization fields;
  - verify raw retrieval-hit payload is not replaced by block views.
- Boundary regression:
  - verify Runtime Workspace discussion/draft material does not appear in Recall search unless explicitly materialized by a Recall ingestion path.

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: hide source family inside an opaque metadata blob the worker never sees.
payload["recall_hits"] = [{"excerpt_text": hit.excerpt_text}]
```

#### Correct

```python
# Correct: keep the canonical metadata and expose the routing fields beside it.
payload["recall_hits"] = [
    {
        "excerpt_text": hit.excerpt_text,
        "metadata": hit.metadata,
        "source_family": hit.metadata.get("source_family"),
        "materialization_kind": hit.metadata.get("materialization_kind"),
        "materialization_event": hit.metadata.get("materialization_event"),
    }
]
```
