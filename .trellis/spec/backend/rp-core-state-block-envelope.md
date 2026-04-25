# RP Core State Block Envelope

## Scenario: Read-Only Block Envelope over Core State

### 1. Scope / Trigger

- Trigger: RP memory work needs a Block-shaped container view over existing Core State data.
- Applies to backend RP memory services that expose Core State authoritative objects or projection slots as Block envelopes.
- This spec is for a read model only. It is not a storage migration and not a mutation path.

### 2. Signatures

Model:

```python
class RpBlockView(BaseModel):
    block_id: str
    label: str
    layer: Layer
    domain: Domain
    domain_path: str
    scope: str
    revision: int = 1
    source: Literal["core_state_store", "compatibility_mirror"]
    payload_schema_ref: str | None = None
    data_json: Any = None
    items_json: list[Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Service:

```python
class RpBlockReadService:
    def list_blocks(self, *, session_id: str) -> list[RpBlockView]: ...
    def get_block(self, *, session_id: str, block_id: str) -> RpBlockView | None: ...
    def list_authoritative_blocks(self, *, session_id: str) -> list[RpBlockView]: ...
    def list_projection_blocks(self, *, session_id: str) -> list[RpBlockView]: ...
```

API:

```http
GET /api/rp/story-sessions/{session_id}/memory/blocks
```

Response:

```python
{
    "session_id": str,
    "items": list[RpBlockView],
}
```

### 3. Contracts

- No `rp_blocks` table is created for this stage.
- Authoritative Core State blocks come from:
  - formal store: `rp_core_state_authoritative_objects`
  - fallback mirror: `StorySession.current_state_json`
- When formal-store read is enabled, authoritative blocks must include every
  current row for the session, including rows that do not have a legacy
  compatibility-mirror binding in `memory_object_mapper`.
- Compatibility-mirror authoritative fallback is only for mapped legacy fields
  that do not already have a formal-store row.
- Projection blocks come from:
  - formal store: `rp_core_state_projection_slots`
  - fallback mirror: `ChapterWorkspace.builder_snapshot_json`
- `layer`, `domain`, `domain_path`, `scope`, and `revision` must preserve existing Core State identity.
- `domain` is classification only. Do not use it as full Block identity.
- `label` must be exact object identity:
  - authoritative example: `chapter.current`
  - projection example: `projection.current_outline_digest`
- Payload must stay raw and non-lossy:
  - authoritative payload goes to `data_json`
  - projection payload goes to `items_json`
- `source` and `metadata.route` must show whether the envelope came from formal store or compatibility mirror.
- Compatibility mirror IDs must be deterministic, stable within the owning session/chapter, and namespaced with `compatibility_mirror:`.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Unknown `session_id` | Return an empty list or `None` for `get_block` |
| Unknown API `session_id` | Return HTTP 404 with `story_session_not_found` |
| Formal store enabled and row exists | Return `source="core_state_store"` for every session row, including unmapped authoritative rows |
| Formal store enabled but a mapped row is missing | Include the mapped mirror item as `source="compatibility_mirror"` |
| Formal store disabled | Ignore existing formal rows and return mirror-backed envelopes |
| Projection section `items` is not a list/tuple | Treat as empty list, do not leak mutable or invalid data |
| Unknown projection summary id | Skip it until a binding exists in `memory_object_mapper` |

### 5. Good/Base/Bad Cases

- Good: formal authoritative row `chapter.current@3` becomes a Block envelope with `revision=3`, `data_json`, `source_row_id`, and `latest_apply_id`.
- Good: formal authoritative row `world_rule.archive_policy@7` with no legacy mirror field still appears as a Block envelope with `label="world_rule.archive_policy"` and `source="core_state_store"`.
- Good: formal projection slot `projection.current_outline_digest@4` becomes a Block envelope with `items_json`, `chapter_workspace_id`, and `last_refresh_kind`.
- Base: empty formal store still exposes mapped mirror values from `current_state_json` and `builder_snapshot_json`.
- Bad: adding a generic `rp_blocks` table before the Core State envelope contract is proven.
- Bad: converting projection `items_json` into prompt text inside the read model.
- Bad: letting Block read services bypass proposal/apply for authoritative mutation.

### 6. Tests Required

- Formal store authoritative envelope:
  - asserts `block_id`, `label`, `layer`, `domain`, `domain_path`, `scope`, `revision`
  - asserts `data_json`, `payload_schema_ref`, `source`, `source_row_id`
- Unmapped formal authoritative row:
  - asserts a formal row outside legacy mirror bindings is still included
  - asserts exact label/domain/domain_path/revision/payload/source metadata
- Formal store projection envelope:
  - asserts `items_json`, `chapter_workspace_id`, `last_refresh_kind`
- Mirror fallback envelope:
  - asserts deterministic compatibility block id
  - asserts `source="compatibility_mirror"` and correct mirror route
- API visibility:
  - asserts `/memory/blocks` returns `session_id` and serialized Block items
  - asserts missing session returns the same 404 shape as other memory read routes
- Store read switch:
  - when disabled, existing formal rows must not override mirror output
- Boundary regression:
  - no new durable Block table
  - no writer packet, setup cognition, Recall/Archival storage coupling

### 7. Wrong vs Correct

#### Wrong

```python
# Wrong: only mapped legacy bindings are emitted, so formal rows that
# do not exist in StorySession.current_state_json disappear.
for binding in authoritative_bindings():
    row = store_rows.get(binding.object_id)
    if row is not None:
        blocks.append(_authoritative_store_block(row))
```

#### Correct

```python
# Correct: emit all formal rows first, then fill only missing mapped
# compatibility fields from the mirror.
blocks = [_authoritative_store_block(row) for row in store_rows.values()]
for binding in authoritative_bindings():
    if binding.object_id in store_rows:
        continue
    blocks.append(_compatibility_authoritative_block(binding))
```

## Design Decision: Core State First, Block Later

**Context**: Letta-style Block containers are useful, but this project already has formal Core State tables and retrieval-core storage.

**Decision**: Start with a read-only Block envelope over Core State. Do not create a universal Block storage layer for Recall/Archival, and do not replace `WritingPacketBuilder`.

**Consequences**: Future attach/fan-out/compiler work gets a stable container shape without duplicating storage or collapsing business boundaries.
