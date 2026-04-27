# RP Core State Block Envelope

## Scenario: Read-Only Block Envelope over Core State

### 1. Scope / Trigger

- Trigger: RP memory work needs a Block-shaped container view over existing Core State data.
- Applies to backend RP memory services that expose Core State authoritative objects or projection slots as Block envelopes.
- This spec is for a read model only. It is not a storage migration and not a mutation path.

### 2. Signatures

Model:

```python
BlockSource = Literal[
    "core_state_store",
    "compatibility_mirror",
    "retrieval_store",
    "runtime_workspace_store",
]


class RpBlockView(BaseModel):
    block_id: str
    label: str
    layer: Layer
    domain: Domain
    domain_path: str
    scope: str
    revision: int = 1
    source: Literal[
        "core_state_store",
        "compatibility_mirror",
        "retrieval_store",
        "runtime_workspace_store",
    ]
    payload_schema_ref: str | None = None
    data_json: Any = None
    items_json: list[Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Service:

```python
class RpBlockReadService:
    def list_blocks(
        self,
        *,
        session_id: str,
        layer: Layer | None = None,
        source: BlockSource | None = None,
    ) -> list[RpBlockView]: ...
    def get_block(self, *, session_id: str, block_id: str) -> RpBlockView | None: ...
    def list_authoritative_blocks(self, *, session_id: str) -> list[RpBlockView]: ...
    def list_projection_blocks(self, *, session_id: str) -> list[RpBlockView]: ...
```

API:

```http
GET /api/rp/story-sessions/{session_id}/memory/blocks
GET /api/rp/story-sessions/{session_id}/memory/blocks/{block_id}
GET /api/rp/story-sessions/{session_id}/memory/blocks/{block_id}/versions
GET /api/rp/story-sessions/{session_id}/memory/blocks/{block_id}/provenance
GET /api/rp/story-sessions/{session_id}/memory/blocks/{block_id}/proposals
```

List query params:

- `layer`: optional `Layer` enum value such as `core_state.authoritative` or `core_state.projection`.
- `source`: optional Block source value. Core State Block envelopes use `core_state_store` or `compatibility_mirror`; the shared API may also emit `runtime_workspace_store` from the Runtime Workspace slice, while `retrieval_store` remains outside this route in the current rollout.

List response:

```python
{
    "session_id": str,
    "items": list[RpBlockView],
}
```

Single-block response:

```python
{
    "session_id": str,
    "item": RpBlockView,
}
```

Block-addressed version response:

```python
{
    "session_id": str,
    "block_id": str,
    "versions": list[str],
    "current_ref": str | None,
}
```

Block-addressed provenance response:

```python
{
    "session_id": str,
    "block_id": str,
    "target_ref": ObjectRef,
    "source_refs": list[str],
    "proposal_refs": list[str],
    "ingestion_refs": list[str],
}
```

Block-addressed proposal response:

```python
{
    "session_id": str,
    "block_id": str,
    "items": list[dict],
}
```

Block-addressed proposal query params:

- `status`: optional proposal status filter aligned with
  `/memory/proposals?status=...`.

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
- `retrieval_store` and `runtime_workspace_store` are part of the shared `BlockSource` type for non-Core-State Block-compatible views, but they do not change the Core State payload identity rules in this slice.
- List filters are read-only view filters. They must not mutate storage, normalize payloads, or strip raw `data_json` / `items_json` / metadata.
- `get_block` must resolve one Block envelope by exact `block_id` within the explicit `session_id` scope.
- Block-addressed history/provenance routes must first resolve `{block_id}` through `RpBlockReadService.get_block(session_id=..., block_id=...)`, not by re-querying Core State storage directly.
- Block-addressed proposal routes must also first resolve `{block_id}` through `RpBlockReadService.get_block(session_id=..., block_id=...)`.
- Authoritative Block history/provenance must delegate to `VersionHistoryReadService` / `ProvenanceReadService` using the Block identity fields as the target `ObjectRef`: `label` as `object_id`, plus `layer`, `domain`, `domain_path`, `scope`, and `revision`.
- Projection Block history/provenance must delegate to existing projection read-side support when available. The current supported path is `ProjectionReadService.list_versions(..., session_id=...)` and `ProjectionReadService.read_provenance(..., session_id=...)`, using the same Block-derived `ObjectRef`.
- If a future Block layer has no read-only history/provenance backend, the API must return HTTP 400 with error code `memory_block_history_unsupported` instead of inventing ad hoc storage reads or mutating state.
- Authoritative Block proposals must be read-only visibility over existing proposal records in the same story/session. Match operations by the authoritative target-ref identity derived from the Block (`label`/`layer`/`domain`/`domain_path`/`scope`), not by a loose domain-only check.
- Proposal target matching does not create or mutate apply receipts, revisions, Block storage, or proposal storage. It only filters existing proposal `operations_json`.
- Projection Block proposals are conservative for this stage. Until a direct projection proposal model exists, the route returns an empty `items` list instead of inventing projection proposal semantics.
- Compatibility mirror IDs must be deterministic, stable within the owning session/chapter, and namespaced with `compatibility_mirror:`.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Unknown `session_id` | Return an empty list or `None` for `get_block` |
| Unknown API `session_id` | Return HTTP 404 with `story_session_not_found` |
| Unknown API `block_id` for an existing session | Return HTTP 404 with `memory_block_not_found` |
| Unknown API `block_id` on `/versions` or `/provenance` | Return HTTP 404 with `memory_block_not_found` |
| Unknown API `block_id` on `/proposals` | Return HTTP 404 with `memory_block_not_found` |
| Unsupported Block layer on `/versions` or `/provenance` | Return HTTP 400 with `memory_block_history_unsupported` |
| Authoritative Block `/proposals` | Return same-session proposal items whose operations target the exact authoritative ref identity |
| Authoritative Block `/proposals?status=...` | Apply the same status filter as `/memory/proposals` after exact target matching |
| Projection Block `/proposals` | Return HTTP 200 with an empty `items` list |
| List `layer` filter is provided | Return only blocks whose `layer` equals the requested `Layer` enum value |
| List `source` filter is provided | Return only blocks whose source matches the requested Block source; the current `/memory/blocks` route may emit `core_state_store`, `compatibility_mirror`, or `runtime_workspace_store`, while `retrieval_store` stays outside this route |
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
  - asserts `/memory/blocks?layer=...` and `/memory/blocks?source=...` filter without changing payload shape
  - asserts `/memory/blocks/{block_id}` returns the exact serialized Block item for a formal row
  - asserts `/memory/blocks/{block_id}/versions` returns authoritative and projection versions from existing read services
  - asserts `/memory/blocks/{block_id}/provenance` returns authoritative and projection provenance from existing read services
  - asserts `/memory/blocks/{block_id}/proposals` resolves the Block first, returns authoritative proposals that target the exact Block ref identity, and does not include same-domain proposals for other object identities
  - asserts `/memory/blocks/{block_id}/proposals?status=...` applies the same status filtering behavior as `/memory/proposals`
  - asserts projection Block `/proposals` returns an empty list
  - asserts missing session returns the same 404 shape as other memory read routes
  - asserts missing block under an existing session returns `memory_block_not_found`
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
