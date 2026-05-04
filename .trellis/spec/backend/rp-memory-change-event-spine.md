# RP Memory Change Event Spine

## Scenario: Reusable lightweight memory event spine before conflict and projection slices

### 1. Scope / Trigger

- Trigger: the registry / identity / event DTO skeleton and Runtime Workspace material store exist, but event emission is still local to the caller. Core State conflict handling, projection refresh, writer retrieval usage, branch visibility, worker dirty checks, and UI audit need one shared lightweight event recording surface before they depend on ad hoc event lists.
- Applies to backend RP Memory OS contract work for:
  - reusable `MemoryChangeEvent` recording;
  - full-identity event isolation;
  - registry-backed domain validation and alias normalization;
  - query filters for layer, domain, kind, operation, source refs, dirty targets, and visibility;
  - dirty-target readback for packet/window/worker invalidation planning;
  - optional publishing from existing Runtime Workspace material service.
- This slice must not implement full event sourcing, durable DB persistence, branch UI, Core State apply rewrite, projection refresh write semantics, public memory tools, or Runtime Workspace promotion.

### 2. Signatures

Service surface:

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

Error shape:

```python
class MemoryChangeEventServiceError(ValueError):
    code: str
```

Expected stable error codes:

```text
memory_change_event_domain_not_registered
memory_change_event_id_conflict
```

### 3. Contracts

#### Event spine ownership

- The event spine records trace and invalidation events over memory stores.
- It is not the source of Core State, Recall, Archival, or Runtime Workspace truth.
- It must not be used to rebuild memory state.
- It exists so later slices can ask:
  - what changed in this turn / branch / profile snapshot;
  - which domains or blocks are dirty;
  - which packet/window/worker consumers should recompute;
  - which source refs produced a change;
  - which events should be visible for UI audit.

#### Identity contract

- Events are keyed by full `MemoryRuntimeIdentity`.
- Listing by `session_id` alone is invalid for branch-ready story runtime behavior.
- An event recorded for one branch head, turn, or runtime profile snapshot must not be returned for another identity.

#### Domain contract

- `event.domain` must resolve through `MemoryContractRegistryService`.
- Aliases must be normalized to the canonical domain id before storage.
- Unknown domains fail closed with `memory_change_event_domain_not_registered`.
- The service must not introduce its own domain allowlist.

#### Event id contract

- `event_id` is caller supplied in this slice.
- A single event spine store must reject duplicate `event_id` values.
- This is a trace uniqueness guard, not a persistence-level idempotency design. A later durable store may add stronger idempotency semantics.

#### Query contract

- `list_events` returns events for one exact identity, in record order.
- Optional filters are conjunctive.
- `source_type` matches any `MemorySourceRef.source_type` in the event.
- `dirty_target_kind` matches any `MemoryDirtyTarget.target_kind` in the event.
- Domain filters resolve aliases through the registry before matching.
- `list_dirty_targets` flattens dirty targets from matching events, preserves event order, and does not infer new targets.

#### Runtime Workspace publishing contract

- `RuntimeWorkspaceMaterialService` may receive a shared `MemoryChangeEventService`.
- When injected, successful material creation and lifecycle updates publish the same receipt event to the shared event spine.
- Existing local receipts and local in-process material store behavior must remain intact.
- Missing injected event spine must not change Runtime Workspace behavior.

### 4. Validation & Error Matrix

| Condition | Expected behavior |
|---|---|
| Event has unknown domain | Reject with `memory_change_event_domain_not_registered` |
| Event uses registry alias domain | Store canonical domain id |
| Duplicate `event_id` is recorded | Reject with `memory_change_event_id_conflict` |
| Event is listed with exact identity | Returned in record order |
| Event is listed with different branch / turn / profile identity | Not returned |
| `list_events` filters by layer / kind / operation / source / dirty target / visibility | Returns only matching events |
| `list_dirty_targets` is called | Returns dirty targets already present on matching events; does not fabricate targets |
| Runtime Workspace material service publishes to an injected event spine | Receipt event remains local and also appears in the shared event service |

### 5. Good / Base / Bad Cases

- Good: a Runtime Workspace retrieval-card event is visible through the shared event spine for the exact turn identity.
- Good: a projection refresh event can later record packet/window dirty targets without becoming projection truth.
- Good: a worker can query dirty targets for its domain and receive only recorded invalidation targets.
- Base: current `RuntimeWorkspaceMaterialService` tests still pass when no shared event service is injected.
- Bad: querying events only by `session_id`.
- Bad: adding a second domain allowlist inside the event service.
- Bad: treating event replay as the authoritative memory state.
- Bad: using event spine persistence as a substitute for proposal/apply receipts.

### 6. Tests Required

- Service tests cover:
  - event recording and full-identity listing;
  - branch / turn / profile isolation;
  - registry alias normalization;
  - unknown domain rejection;
  - duplicate event id rejection;
  - filters for layer, event kind, operation kind, source type, dirty target kind, and visibility;
  - dirty-target flattening without fabricated targets.
- Integration tests cover:
  - `RuntimeWorkspaceMaterialService` publishes receipt events to an injected `MemoryChangeEventService`;
  - local Runtime Workspace receipts remain unchanged.
- Focused lint/type checks must include the new event service, Runtime Workspace service change, and tests.

### 7. Wrong vs Correct

#### Wrong

```python
events_by_session[session_id].append(event)
```

This leaks events across branch heads, turns, and runtime profile snapshots.

#### Correct

```python
event_service.record_event(event)
event_service.list_events(identity=turn_identity, domain="knowledge")
```

The service validates the domain through the registry, stores by full identity, and resolves aliases before matching.

#### Wrong

```python
projection = rebuild_projection_from_events(events)
```

This turns the trace spine into hidden event sourcing.

#### Correct

```python
dirty_targets = event_service.list_dirty_targets(identity=turn_identity)
```

The event spine reports invalidation and trace facts while projection/Core State stores remain the source of current memory state.
