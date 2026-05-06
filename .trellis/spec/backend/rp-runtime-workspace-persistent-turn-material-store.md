# RP Runtime Workspace Persistent Turn Material Store

## Scenario: Durable Runtime Workspace turn material before retrieval usage, branch visibility, and post-write maintenance depend on cross-request state

### 1. Scope / Trigger

- Trigger: `RuntimeWorkspaceMaterial` and `RuntimeWorkspaceMaterialService` already freeze the typed current-turn material envelope, but storage is still process-local. Boot-bar runtime cannot depend on writer retrieval cards, usage records, worker candidates, or post-write traces if they disappear on restart or stay invisible across requests.
- Applies to backend RP Runtime Workspace contract work for:
  - persistent Runtime Workspace material records;
  - repository-backed material reads/writes keyed by full runtime identity;
  - lifecycle persistence and query filters;
  - short-id uniqueness per identity;
  - integration with the later persistent memory event foundation;
  - focused persistence tests.
- This slice must not:
  - turn Runtime Workspace into story truth;
  - reuse `StoryArtifactRecord` or `StoryDiscussionEntryRecord` as the persistent material store;
  - replace existing Runtime Workspace draft/discussion Block views;
  - add public mutation tools;
  - implement branch merge or full visibility resolver logic.

### 2. Surfaces

Persistent record shape:

```python
class RuntimeWorkspaceMaterialRecord(SQLModel, table=True):
    material_id: str
    story_id: str
    session_id: str
    branch_head_id: str
    turn_id: str
    runtime_profile_snapshot_id: str
    material_kind: str
    domain: str
    domain_path: str | None
    short_id: str | None
    lifecycle: str
    visibility: str
    created_by: str
    expiration_ref: str | None
    materialization_ref: str | None
    payload_json: dict[str, Any]
    source_refs_json: list[dict[str, Any]]
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    expired_at: datetime | None
    invalidated_at: datetime | None
```

Repository/service surface:

```python
class RuntimeWorkspaceMaterialRepository:
    def insert(self, record: RuntimeWorkspaceMaterialRecord) -> RuntimeWorkspaceMaterialRecord: ...
    def get(self, *, identity: MemoryRuntimeIdentity, material_id: str) -> RuntimeWorkspaceMaterialRecord | None: ...
    def list(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_kind: str | None = None,
        domain: str | None = None,
        lifecycle: str | None = None,
    ) -> list[RuntimeWorkspaceMaterialRecord]: ...
    def update_lifecycle(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        material_id: str,
        lifecycle: str,
        updated_at: datetime,
    ) -> RuntimeWorkspaceMaterialRecord: ...
```

Extended service contract:

```python
class RuntimeWorkspaceMaterialService:
    def record_material(self, material: RuntimeWorkspaceMaterial) -> RuntimeWorkspaceMaterialReceipt: ...
    def get_material(self, *, identity: MemoryRuntimeIdentity, material_id: str) -> RuntimeWorkspaceMaterial | None: ...
    def require_material(self, *, identity: MemoryRuntimeIdentity, material_id: str) -> RuntimeWorkspaceMaterial: ...
    def list_materials(self, *, identity: MemoryRuntimeIdentity, material_kind: RuntimeWorkspaceMaterialKind | None = None, domain: str | None = None, lifecycle: RuntimeWorkspaceMaterialLifecycle | None = None) -> list[RuntimeWorkspaceMaterial]: ...
    def update_lifecycle(self, *, identity: MemoryRuntimeIdentity, material_id: str, lifecycle: RuntimeWorkspaceMaterialLifecycle, reason: str) -> RuntimeWorkspaceMaterialReceipt: ...
```

Stable error codes remain:

```text
runtime_workspace_domain_not_registered
runtime_workspace_material_id_conflict
runtime_workspace_material_not_found
runtime_workspace_short_id_conflict
```

### 3. Contracts

#### Ownership contract

- Runtime Workspace remains current-turn scratch/evidence/candidate/trace material only.
- Persistence does not promote Runtime Workspace into:
  - `Core State.authoritative_state`
  - `Core State.derived_projection`
  - `Recall Memory`
  - `Archival Knowledge`
- Promotion to those layers remains a later governed path.

#### Persistence contract

- The persistent store is the source of Runtime Workspace material truth for boot-bar runtime behavior.
- The old injected in-process store becomes an implementation fallback/test seam, not the long-term boot path.
- A material created in one request/process must be readable in a later request/process through repository-backed storage.

#### Identity contract

- Every persistent record must carry full runtime identity as first-class columns:
  - `story_id`
  - `session_id`
  - `branch_head_id`
  - `turn_id`
  - `runtime_profile_snapshot_id`
- Repository reads must filter by the full identity, not `session_id` alone.
- Materials from another branch/turn/profile must not appear in runtime-owned reads for the active identity.

#### Queryability contract

- The following fields must be queryable columns, not hidden only inside JSON:
  - identity columns
  - `material_kind`
  - `domain`
  - `short_id`
  - `lifecycle`
  - `visibility`
  - `created_by`
- `payload`, `source_refs`, and flexible metadata may remain JSON-backed in this slice.

#### Short-id contract

- `short_id` uniqueness is enforced per exact runtime identity.
- The same `short_id` may be reused in another branch, turn, or runtime profile snapshot.
- A durable uniqueness rule is required so writer retrieval cards such as `R1` stay deterministic inside one turn.

#### Lifecycle contract

- Lifecycle transitions must persist:
  - `active`
  - `used`
  - `unused`
  - `expanded`
  - `promoted`
  - `discarded`
  - `expired`
  - `invalidated`
- `expired_at` and `invalidated_at` should be persisted when relevant.
- The service still returns `RuntimeWorkspaceMaterialReceipt` with an event-compatible receipt shape, but durable event recording is defined by the persistent event foundation spec.

#### Compatibility contract

- Existing Runtime Workspace draft/discussion Block views continue unchanged.
- Existing typed DTOs remain the boundary contract; repository records adapt to them rather than replacing them.
- This slice does not require the full branch visibility resolver, but it must preserve enough identity and lifecycle state for that later slice to work.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Material is recorded through one process/request | A later process/request can read it through persistent storage |
| Material has unknown domain | Reject with `runtime_workspace_domain_not_registered` |
| Same `material_id` is inserted twice | Reject with `runtime_workspace_material_id_conflict` |
| Same `short_id` is inserted twice under one identity | Reject with `runtime_workspace_short_id_conflict` |
| Same `short_id` is inserted under another identity | Allowed |
| Material is queried with a different branch / turn / profile | Not returned |
| Lifecycle update succeeds | Persisted record changes and a receipt event is returned |
| Retrieval card is stored | Remains Runtime Workspace material only; no truth-layer mutation occurs |

### 5. Good / Base / Bad Cases

- Good: a writer retrieval search stores `retrieval_card` rows with `R1`, `R2`, then later stores `retrieval_usage_record` rows under the same identity.
- Good: a worker candidate survives process restart and is still available to post-write maintenance for that exact turn identity.
- Good: token usage metadata and packet refs can be inspected after the request ends.
- Base: current typed DTOs and local tests can remain while repository-backed storage is introduced.
- Bad: persisting Runtime Workspace material by mutating `builder_snapshot_json`.
- Bad: querying a retrieval card by `session_id` only.
- Bad: reusing `StoryArtifactRecord` to store retrieval cards or usage records.

### 6. Tests Required

- Record/repository tests cover:
  - insert/get/list by full identity;
  - cross-process durability semantics through the persistent repository layer;
  - short-id uniqueness within one identity and reuse across different identities;
  - lifecycle persistence including `expired_at` / `invalidated_at` when relevant.
- Service tests cover:
  - DTO-to-record and record-to-DTO adaptation;
  - domain registry validation;
  - retrieval card, retrieval usage record, and worker candidate examples.
- Integration tests cover:
  - a material recorded in one session/request context is readable later by exact identity;
  - runtime-owned reads do not leak materials from another branch/turn/profile.
- Focused lint/type checks must include the new record, repository, service integration changes, and tests.

### 7. Wrong vs Correct

#### Wrong

```python
chapter.builder_snapshot_json["retrieval_cards"] = cards
```

This buries turn material in a projection compatibility mirror and destroys branch/turn queryability.

#### Correct

```python
record = RuntimeWorkspaceMaterialRecord(
    material_id="mat-1",
    story_id=identity.story_id,
    session_id=identity.session_id,
    branch_head_id=identity.branch_head_id,
    turn_id=identity.turn_id,
    runtime_profile_snapshot_id=identity.runtime_profile_snapshot_id,
    material_kind="retrieval_card",
    domain="knowledge_boundary",
    short_id="R1",
    lifecycle="active",
    visibility="writer_visible",
    payload_json=payload,
    source_refs_json=source_refs,
)
```

The material stays typed, identity-scoped, durable, and still clearly not story truth.
