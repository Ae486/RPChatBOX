# RP Retrieval Block Observability

## Scenario: Retrieval Observability Exposes Additive Block-Compatible Views for Top Hits

### 1. Scope / Trigger

- Trigger: Recall / Archival retrieval hits already have a read-only Block-compatible adapter, but the retrieval observability chain still exposes only hit-centric fields.
- Applies to:
  - `RetrievalObservabilityHitView`
  - `RetrievalObservabilityService`
  - `RetrievalService` / `RetrievalBroker` observability payloads
  - focused retrieval tests
- This slice is additive. It does not change `RetrievalSearchResult`, public memory search tool outputs, or Block consumer attachment.

### 2. Signatures

Observability hit view:

```python
class RetrievalObservabilityHitView(BaseModel):
    ...
    excerpt_preview: str
    block_view: RpBlockView | None = None
```

Observability service reuse:

```python
class RetrievalObservabilityService:
    def __init__(
        self,
        session=None,
        *,
        maintenance_service: RetrievalMaintenanceService | None = None,
        retrieval_block_adapter_service: RetrievalBlockAdapterService | None = None,
    ) -> None: ...
```

### 3. Contracts

- Retrieval observability remains a hit-centric view first; `block_view` is additive metadata, not a replacement for the existing hit fields.
- `block_view` must be derived through `RetrievalBlockAdapterService`, not reimplemented ad hoc inside observability code.
- Only top-hit entries emitted by `RetrievalObservabilityService` need block-compatible views in this slice.
- The emitted `block_view` must preserve the same `block_id`, `label`, `layer`, `source`, payload, and metadata semantics as other retrieval-backed Block-compatible views.
- `RetrievalService` and `RetrievalBroker` Langfuse observability payloads automatically inherit this additive field through `RetrievalObservabilityService`; they must not special-case or reshape it.

### 4. Boundary Rules

- Do not change `RetrievalHit` / `RetrievalSearchResult` shape in this slice.
- Do not add retrieval Block views to public `memory.search_recall` / `memory.search_archival` tool result bodies in this slice.
- Do not introduce durable storage, history routes, or consumer sync state for retrieval Block views here.
- Do not bypass `RetrievalBlockAdapterService` when building observability payloads.

### 5. Tests Required

- `RetrievalObservabilityService` emits `block_view` for top hits with `source="retrieval_store"` and stable retrieval-backed Block identity.
- `RetrievalService` observation output includes `top_hits[*].block_view`.
- `RetrievalBroker` observation output includes `top_hits[*].block_view`.
- Existing observability fields remain intact.

### 6. Wrong vs Correct

#### Wrong

```python
# Wrong: duplicate Block mapping logic locally inside observability.
block_view = {
    "block_id": f"retrieval.{hit.layer}.{hit.query_id}.{hit.hit_id}",
    ...
}
```

#### Correct

```python
# Correct: reuse the canonical retrieval Block adapter and expose the result additively.
blocks = retrieval_block_adapter_service.build_block_views(hits=result.hits[:max_hits])
```
