# RP Memory Get State Summary Block Read Surface

## Scenario: RetrievalBroker Resolves Unmapped Core State Targets Through Block Read Adapters

### 1. Scope / Trigger

- Trigger: `memory.get_state` and `memory.get_summary` still enter through `RetrievalBroker`, but some Core State targets are not fully materialized through the old authoritative/projection read path.
- Applies to backend RP services around:
  - `RetrievalBroker.get_state(...)`
  - `RetrievalBroker.get_summary(...)`
  - `MemoryOsService`
  - `MemoryCrudToolProvider`
- This slice makes the read surface real by letting `RetrievalBroker` reuse `RpBlockReadService` as a fallback/metadata-enrichment adapter.
- This slice does not change tool names, provider dispatch, proposal/apply write flow, or retrieval-core storage.

### 2. Signatures

Broker entry points stay unchanged:

```python
class RetrievalBroker:
    async def get_state(self, input_model: MemoryGetStateInput) -> StateReadResult: ...
    async def get_summary(self, input_model: MemoryGetSummaryInput) -> SummaryReadResult: ...
```

Internal helper shape:

```python
def _merge_state_result_from_blocks(
    self,
    *,
    session: Session,
    input_model: MemoryGetStateInput,
    result: StateReadResult,
) -> StateReadResult: ...

def _merge_summary_result_from_blocks(
    self,
    *,
    session: Session,
    input_model: MemoryGetSummaryInput,
    result: SummaryReadResult,
) -> SummaryReadResult: ...
```

Tool/provider surface stays unchanged:

```python
class MemoryOsService:
    async def get_state(self, input_model: MemoryGetStateInput) -> StateReadResult: ...
    async def get_summary(self, input_model: MemoryGetSummaryInput) -> SummaryReadResult: ...
```

### 3. Contracts

- `MemoryOsService` remains a thin facade over `RetrievalBroker`; no new branching or business policy moves into the facade.
- `MemoryCrudToolProvider` keeps the existing `memory.get_state` / `memory.get_summary` tool names and validation/serialization behavior.
- `RetrievalBroker.get_state(...)` must still call the existing authoritative read service first.
- `RetrievalBroker.get_summary(...)` must still call the existing projection read service first.
- Block read logic is only a fallback/enrichment layer inside `RetrievalBroker`, not a replacement entry point.

State read contract:

- Only explicit `refs` requests may be repaired through Block fallback.
- Domain-only `get_state(domain=...)` stays on the existing authoritative read semantics.
- Fallback only applies when the existing read result carries unresolved-authoritative warnings such as `phase_e_authoritative_ref_not_materialized:*`.
- The fallback must resolve against the active story session via `RpBlockReadService.list_authoritative_blocks(...)`.
- When a matching authoritative Block is found, the broker replaces the unresolved item with Block-backed payload + revision and strips the unresolved warning.

Summary read contract:

- `get_summary(...)` may enrich both existing projection items and unmapped summary requests through `RpBlockReadService.list_projection_blocks(...)`.
- Existing projection items keep their summary text, but gain Block/container metadata when a matching projection Block exists.
- Requested summary ids that were previously unresolved may be fulfilled directly from projection Blocks.
- Writer-only mirror artifacts such as `writer_hints` stay excluded from the summary surface.

Metadata contract:

- Summary metadata may include:
  - `block_id`
  - `source`
  - `source_row_id`
  - `revision`
  - `payload_schema_ref`
  - `block_route`
  - `scope`
  - `session_id`
  - `chapter_workspace_id`
  - `slot_name`
- These fields must come from the existing `RpBlockView` / Block metadata; do not invent a second metadata truth source.

### 4. Boundary Rules

- Do not bypass `RetrievalBroker` and read `RpBlockReadService` directly from tool/provider code.
- Do not change `MemoryGetStateInput` / `MemoryGetSummaryInput` public shape in this slice.
- Do not change retrieval recall / archival behavior in this slice.
- Do not replace authoritative/projection read services with direct Block-only reads.
- Do not introduce writes, proposal routing, or compile/fan-out logic here.

### 5. Good / Base / Bad Cases

- Good: `memory.get_state(refs=[world_rule.archive_policy])` can now return real data/revision from authoritative Block fallback when the older read path marks it unmaterialized.
- Good: `memory.get_summary(summary_ids=["projection.side_notes_digest"])` can now return real summary text and Block metadata from projection Block fallback.
- Good: existing resolved summary entries such as `projection.foundation_digest` keep the same summary text, but now also expose Block metadata fields for visibility.
- Base: `MemoryOsService` remains a facade; the actual behavior change lives in `RetrievalBroker`.
- Bad: making `memory.get_state(domain=...)` start scanning Blocks for every domain request.
- Bad: moving summary rendering responsibility into `MemoryCrudToolProvider`.
- Bad: using Block fallback to expose writer-only scratch material or retrieval passages.

### 6. Tests Required

- `RetrievalBroker.get_state(...)` returns existing materialized authoritative data unchanged.
- Explicit unmapped authoritative ref is resolved from Block/store fallback with correct revision and no unresolved warning.
- `RetrievalBroker.get_summary(...)` still resolves mapped aliases and now annotates matched items with Block metadata.
- Unmapped projection summary id can be fulfilled from Block/store fallback with stable metadata.
- `MemoryOsService` remains a pure facade over the broker.
- Existing provider-level canonical JSON contract remains valid.

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: tool/provider bypasses RetrievalBroker and reads Block service directly.
return await rp_block_read_service.list_projection_blocks(session_id=session_id)
```

#### Correct

```python
# Correct: keep RetrievalBroker as the entry point, then let it repair unresolved
# Core State reads through RpBlockReadService inside the broker.
result = await projection_read_service.get_summary(input_model)
return self._merge_summary_result_from_blocks(
    session=session,
    input_model=input_model,
    result=result,
)
```
