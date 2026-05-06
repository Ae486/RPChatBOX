# RP Persistent Memory Event Record Foundation

## Scenario: Durable event records before branch visibility, direct-edit governance, retrieval usage, and debug/eval need cross-request traceability

### 1. Scope / Trigger

- Trigger: `MemoryChangeEvent` and `MemoryChangeEventService` already define the correct lightweight trace/invalidation shape, but storage is still process-local. Boot-bar runtime cannot rely on restart-safe trace, dirty-target lookup, or identity-scoped audit if events disappear after one request.
- Applies to backend RP memory/runtime contract work for:
  - persistent memory event records;
  - repository-backed event writes and focused identity queries;
  - integration from Runtime Workspace and later mutation/refresh callers;
  - event persistence as audit/invalidation infrastructure only;
  - focused boot-bar query tests.
- This slice must not:
  - turn the event spine into the source of business truth;
  - introduce distributed event streaming or replay-based state reconstruction;
  - require rich debug UI/eval dashboards;
  - replace proposal/apply receipts or Core/Projection/Recall/Archival truth stores.

### 2. Surfaces

Persistent record shape:

```python
class MemoryChangeEventRecord(SQLModel, table=True):
    event_id: str
    story_id: str
    session_id: str
    branch_head_id: str
    turn_id: str
    runtime_profile_snapshot_id: str
    actor: str
    event_kind: str
    layer: str
    domain: str
    block_id: str | None
    entry_id: str | None
    operation_kind: str
    visibility_effect: str
    source_refs_json: list[dict[str, Any]]
    dirty_targets_json: list[dict[str, Any]]
    metadata_json: dict[str, Any]
    created_at: datetime
```

Repository/service surface:

```python
class MemoryChangeEventRepository:
    def insert(self, record: MemoryChangeEventRecord) -> MemoryChangeEventRecord: ...
    def list_events(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        domain: str | None = None,
        layer: str | None = None,
        event_kind: str | None = None,
        operation_kind: str | None = None,
        visibility_effect: str | None = None,
    ) -> list[MemoryChangeEventRecord]: ...
```

Extended service contract:

```python
class MemoryChangeEventService:
    def record_event(self, event: MemoryChangeEvent) -> MemoryChangeEvent: ...
    def list_events(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        domain: str | None = None,
        layer: str | None = None,
        event_kind: str | None = None,
        operation_kind: str | None = None,
        source_type: str | None = None,
        dirty_target_kind: str | None = None,
        visibility_effect: str | None = None,
    ) -> list[MemoryChangeEvent]: ...
    def list_dirty_targets(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        domain: str | None = None,
        layer: str | None = None,
        target_kind: str | None = None,
    ) -> list[MemoryDirtyTarget]: ...
```

Stable error codes remain:

```text
memory_change_event_domain_not_registered
memory_change_event_id_conflict
```

### 3. Contracts

#### Ownership contract

- Persistent event records are an audit/invalidation side store.
- They do not become:
  - Core State truth
  - Projection truth
  - Recall truth
  - Archival truth
  - Runtime Workspace truth
- Event replay must not be required to reconstruct current story state.

#### Persistence contract

- Boot-bar runtime paths must persist event records across request/process restart.
- Focused identity queries must survive restart and cross-request inspection.
- The old in-process store can remain as a test seam or short-lived fallback, but persistent storage is the required boot path.

#### Queryability contract

- The following fields must be first-class columns:
  - full runtime identity
  - `actor`
  - `event_kind`
  - `layer`
  - `domain`
  - `block_id`
  - `entry_id`
  - `operation_kind`
  - `visibility_effect`
  - `created_at`
- `source_refs`, `dirty_targets`, and flexible metadata may remain JSON-backed in this slice.
- Focused boot-bar queries must support:
  - exact `MemoryRuntimeIdentity`
  - optional `domain`
  - optional `layer`
  - optional `event_kind`
  - optional `operation_kind`
  - optional `visibility_effect`
- `source_type` and `dirty_target_kind` filtering may continue to inspect JSON-backed arrays in service logic for this slice.

#### Domain contract

- `domain` must resolve through `MemoryContractRegistryService`.
- Aliases normalize to canonical ids before storage.
- Unknown domains fail closed.

#### Event uniqueness contract

- `event_id` stays globally unique within the persistent event store.
- Duplicate event ids fail closed.
- This is a durable trace uniqueness contract, not a cross-system delivery/idempotency system.

#### Boot minimum contract

- Boot-bar minimum requires:
  - persistent event record writes;
  - exact-identity event queries;
  - dirty-target readback from persistent events;
  - Runtime Workspace material create/lifecycle events flowing into the persistent event store.
- Rich debug pages, proposal trace expansion, retrieval usage dashboards, and eval-oriented trace joins are later work.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Event is recorded, process restarts, query runs later | Event is still returned |
| Event has unknown domain | Reject with `memory_change_event_domain_not_registered` |
| Event uses alias domain | Store/query canonical domain id |
| Duplicate `event_id` is inserted | Reject with `memory_change_event_id_conflict` |
| Query uses exact identity | Returns matching events in record order |
| Query uses different branch / turn / profile | Returns nothing for those events |
| `list_dirty_targets` is called after restart | Returns the same persisted dirty targets |
| Runtime Workspace publishes a receipt event | Persistent event record exists and query returns it later |

### 5. Good / Base / Bad Cases

- Good: after a writer turn completes, later debug can still query the turn's Workspace material lifecycle events and projection refresh events by identity.
- Good: direct-edit or proposal/apply later can reuse the same persistent event foundation without inventing a second trace path.
- Base: service-level `source_type` and `dirty_target_kind` filtering can still inspect JSON-backed arrays for the boot slice.
- Bad: using Redis-only/in-memory event buffers as the required boot trace path.
- Bad: rebuilding projection or Runtime Workspace truth from the event list.
- Bad: forcing a distributed event bus into the first boot-bar memory slice.

### 6. Tests Required

- Record/repository tests cover:
  - persistent insert/list behavior;
  - identity isolation across branch/turn/profile;
  - record ordering by insert/create time;
  - duplicate event id rejection.
- Service tests cover:
  - domain alias normalization;
  - `source_type` and `dirty_target_kind` filtering against persisted records;
  - `list_dirty_targets` after persistence round-trip.
- Integration tests cover:
  - `RuntimeWorkspaceMaterialService` create/lifecycle events are queryable after persistence round-trip;
  - boot-bar exact-identity queries survive process restart semantics.
- Focused lint/type checks must include the new record, repository, service integration changes, and tests.

### 7. Wrong vs Correct

#### Wrong

```python
events_by_identity[identity_key].append(event)
```

This disappears on restart and cannot support cross-request audit or boot-bar invalidation queries.

#### Correct

```python
record = MemoryChangeEventRecord(
    event_id=event.event_id,
    story_id=event.identity.story_id,
    session_id=event.identity.session_id,
    branch_head_id=event.identity.branch_head_id,
    turn_id=event.identity.turn_id,
    runtime_profile_snapshot_id=event.identity.runtime_profile_snapshot_id,
    actor=event.actor,
    event_kind=event.event_kind,
    layer=event.layer,
    domain=event.domain,
    operation_kind=event.operation_kind,
    visibility_effect=event.visibility_effect,
    source_refs_json=[ref.model_dump(mode="json") for ref in event.source_refs],
    dirty_targets_json=[target.model_dump(mode="json") for target in event.dirty_targets],
)
```

The event remains lightweight trace/invalidation data, but it becomes durable and queryable enough for the boot bar.
