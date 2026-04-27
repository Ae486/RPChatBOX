# RP Retrieval Block-Compatible Views

## Scenario: Recall / Archival Retrieval Hits Expose Additive Block-Compatible Read Views

### 1. Scope / Trigger

- Trigger: Phase C gap inventory concluded that the repo does not yet need a new durable container layer, but Recall / Archival still need container-compatible runtime views.
- Applies to:
  - `RetrievalBlockAdapterService`
  - `LongformSpecialistService`
  - focused runtime-facing tests
- This slice is additive and read-only. It does not change retrieval-core storage, public memory tool contracts, or active-story Block consumer attachment.

### 2. Signatures

Shared source enum:

```python
BlockSource = Literal[
    "core_state_store",
    "compatibility_mirror",
    "retrieval_store",
    "runtime_workspace_store",
]
```

Adapter entry:

```python
class RetrievalBlockAdapterService:
    def build_block_views(self, *, hits: Sequence[RetrievalHit]) -> list[RpBlockView]: ...
```

Internal specialist payload additions:

```python
{
    "archival_hits": list[dict],
    "recall_hits": list[dict],
    "archival_block_views": list[dict],
    "recall_block_views": list[dict],
}
```

### 3. Contracts

- The adapter is a read-only projection over `RetrievalHit`; it must not create storage rows, proposals, or history records.
- Supported retrieval layers are only:
  - `recall`
  - `archival`
- Unsupported retrieval-hit layers must fail fast instead of silently mapping to the wrong `Layer`.
- `RpBlockView.source` for these views must be `retrieval_store`.
- `block_id` must be deterministic from retrieval-query identity plus hit identity.
- `label` should preserve underlying object identity when available (`knowledge_ref.object_id`); otherwise fall back to `hit_id`.
- `layer`, `domain`, and `domain_path` must preserve retrieval-hit classification.
- `scope` and `revision` should use `knowledge_ref` when present; when missing, normalize to safe read-only defaults and keep the raw retrieval reference visible in metadata.
- `data_json` must keep the raw retrieval payload readable without prompt rendering:
  - `excerpt_text`
  - `score`
  - `rank`
  - `knowledge_ref`
  - `provenance_refs`
- `metadata` must reuse the retrieval-hit metadata as the main truth source and add route/source/query/hit identity.

Specialist integration contract:

- `LongformSpecialistService` keeps the existing raw `archival_hits` / `recall_hits` fields.
- `LongformSpecialistService` additionally includes `archival_block_views` / `recall_block_views` in its internal LLM payload.
- `block_context` remains the active-story Core State compile view; retrieval-backed Block views do not replace it in this slice.

### 4. Boundary Rules

- Do not change `MemorySearchRecallInput`, `MemorySearchArchivalInput`, `RetrievalHit`, or `RetrievalSearchResult` public contracts in this slice.
- Do not bypass `MemoryOsService` / retrieval search by constructing Block views from some other store.
- Do not attach retrieval Block views into `StoryBlockConsumerStateService` or persist consumer sync state for them in this slice.
- Do not add API endpoints, version-history routes, or provenance routes for retrieval Block views in this slice.
- Do not replace raw `archival_hits` / `recall_hits`; Block-compatible views are additive.

### 5. Tests Required

- Adapter maps archival and recall hits into `RpBlockView` with the correct `layer`, `source`, identity, and payload metadata.
- Adapter preserves hit metadata without mutating the original retrieval-hit object.
- Unsupported retrieval-hit layer raises an explicit error.
- Specialist payload includes both raw retrieval hits and retrieval-backed Block-compatible views.
- Existing Core State `block_context` payload remains unchanged.

### 6. Wrong vs Correct

#### Wrong

```python
# Wrong: replace the existing retrieval payload with Block views only.
user_payload["archival_hits"] = [
    block.model_dump(mode="json")
    for block in retrieval_block_adapter_service.build_block_views(hits=archival_hits)
]
```

#### Correct

```python
# Correct: keep the raw retrieval-hit payload and add Block-compatible views beside it.
user_payload["archival_hits"] = [...]
user_payload["archival_block_views"] = [
    block.model_dump(mode="json")
    for block in retrieval_block_adapter_service.build_block_views(hits=archival_hits)
]
```
