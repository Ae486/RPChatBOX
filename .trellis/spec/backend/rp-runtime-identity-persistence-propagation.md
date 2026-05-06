# RP Runtime Identity Persistence And Propagation

## Scenario: Persistent `BranchHead` and `StoryTurn` identity before branch visibility, persistent Workspace, and boot-bar runtime reads

### 1. Scope / Trigger

- Trigger: current memory strengthening established the `MemoryRuntimeIdentity` DTO, but story runtime still lacks first-class persistent `BranchHead` / `StoryTurn` records and deterministic internal identity propagation. Boot-bar memory work cannot stay session-only if later branch visibility, persistent Runtime Workspace, retrieval usage, and proposal traces must remain coherent.
- Applies to backend RP runtime/memory contract work for:
  - persistent `BranchHead` records;
  - persistent `StoryTurn` records;
  - deterministic identity allocation/resolution services;
  - propagation of full runtime identity into memory/retrieval/proposal/workspace/event paths on runtime-owned calls;
  - focused persistence and resolver tests.
- This slice must not implement:
  - branch UI or branch merge;
  - full branch visibility resolver logic;
  - persistent Runtime Workspace tables;
  - full `RuntimeProfileSnapshot` compilation logic beyond consuming a snapshot id;
  - retrieval usage loop or worker orchestration.

### 2. Surfaces

Persistent record shapes:

```python
class BranchHeadRecord(SQLModel, table=True):
    branch_head_id: str
    story_id: str
    session_id: str
    branch_name: str
    parent_branch_head_id: str | None
    forked_from_turn_id: str | None
    head_turn_id: str | None
    status: str
    visibility_scope: str
    created_at: datetime
    updated_at: datetime


class StoryTurnRecord(SQLModel, table=True):
    turn_id: str
    story_id: str
    session_id: str
    branch_head_id: str
    runtime_profile_snapshot_id: str
    turn_kind: str
    command_kind: str
    actor: str
    status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
```

Resolver/allocation surface:

```python
class StoryRuntimeIdentityService:
    def ensure_default_branch(self, *, session_id: str, story_id: str) -> BranchHeadRecord: ...
    def require_branch_head(self, branch_head_id: str) -> BranchHeadRecord: ...
    def create_turn(
        self,
        *,
        session_id: str,
        story_id: str,
        branch_head_id: str,
        runtime_profile_snapshot_id: str,
        turn_kind: str,
        command_kind: str,
        actor: str,
    ) -> StoryTurnRecord: ...
    def resolve_memory_identity(
        self,
        *,
        session_id: str,
        story_id: str,
        branch_head_id: str,
        turn_id: str,
        runtime_profile_snapshot_id: str,
    ) -> MemoryRuntimeIdentity: ...
```

Compatibility entry surface:

```python
class StoryRuntimeIdentityService:
    def resolve_runtime_entry_identity(
        self,
        *,
        session_id: str,
        command_kind: str,
        actor: str,
        requested_branch_head_id: str | None = None,
        requested_runtime_profile_snapshot_id: str | None = None,
    ) -> MemoryRuntimeIdentity: ...
```

Stable error codes:

```text
runtime_branch_head_not_found
runtime_turn_not_found
runtime_identity_resolution_failed
runtime_branch_head_conflict
runtime_turn_conflict
runtime_runtime_profile_snapshot_required
```

### 3. Contracts

#### Identity ownership

- Runtime-owned memory/retrieval/proposal/workspace/event operations must not invent local identity fragments.
- The canonical internal identity remains:

```text
StorySession + BranchHead + Turn + RuntimeProfileSnapshot
```

- External APIs may still enter by `session_id`.
- Internal runtime-owned paths must resolve full identity before touching:
  - Runtime Workspace materials;
  - RetrievalBroker runtime searches;
  - proposal submit/apply runtime paths;
  - projection refresh runtime paths;
  - runtime memory events.

#### Branch head contract

- Every active story session must have at least one persistent default branch head.
- Boot-bar scope only requires:
  - default branch creation;
  - explicit branch head lookup;
  - lineage-ready fields for later fork/rollback visibility work.
- This slice does not require branch merge semantics.
- `head_turn_id` tracks the latest visible turn for that branch head, but later visibility resolver slices decide how reads traverse lineage.

#### Turn contract

- Every runtime turn must have one persistent `StoryTurnRecord`.
- `StoryTurnRecord` is the anchor for:
  - runtime identity;
  - packet/read manifest attribution;
  - workspace materials;
  - retrieval usage;
  - proposal/apply traces;
  - event traces.
- `turn_kind` and `command_kind` must be explicit stored fields, not inferred only from graph state.
- Runtime-owned writes must not create new turn-scoped materials without a persistent turn id.

#### Propagation contract

- Runtime-owned DTOs may remain externally compatible at the route boundary, but the internal runtime path must either:
  - carry `MemoryRuntimeIdentity`; or
  - resolve it before hitting store/service boundaries.
- New runtime-owned material or event records must not be keyed by `session_id` alone.
- Runtime-owned retrieval/search paths must treat the pinned identity as authoritative for story scope as well as branch/turn scope:
  - `RetrievalQuery.story_id` must resolve from `MemoryRuntimeIdentity.story_id` when runtime identity exists;
  - caller-supplied story filters or broker defaults must not override the pinned runtime story.
- Legacy compatibility paths may keep session-only entrypoints, but they must route through an explicit compatibility/default identity resolver.

#### Compatibility contract

- Existing sessions without branch rows must get one deterministic default branch head.
- Existing runtime flows may synthesize a compatibility branch/snapshot only through explicit resolver logic, never through hidden `None` defaults.
- Debug/admin read paths may remain looser temporarily, but runtime-owned reads/writes/searches must move to full identity.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Session has no branch head yet | `ensure_default_branch(...)` creates one deterministic default branch |
| Runtime turn starts with active snapshot id | One `StoryTurnRecord` is created and one `MemoryRuntimeIdentity` is returned |
| Runtime path tries to create turn without snapshot id | Reject with `runtime_runtime_profile_snapshot_required` |
| Runtime material/event search uses session id only | Not allowed on runtime-owned boot-bar path |
| Different branch head / turn ids are used | Resolver returns different `MemoryRuntimeIdentity` values and isolation remains possible |
| Legacy session-only path enters | Explicit compatibility/default identity resolution is used |
| Duplicate branch id or turn id is attempted | Fail closed with conflict error |

### 5. Good / Base / Bad Cases

- Good: a writer turn allocates a persistent branch head + turn + pinned snapshot id before any retrieval, workspace write, or proposal call happens.
- Good: a later event record or retrieval usage record can point back to the exact `turn_id`.
- Base: current external route still receives only `session_id`, but the runtime service resolves full identity immediately.
- Bad: a runtime retrieval query only carries `story_id` and `scope` while the same turn writes branch-scoped workspace material.
- Bad: generating turn ids inside individual services instead of a shared runtime identity service.
- Bad: storing new turn-scoped rows with only `session_id`.

### 6. Tests Required

- Persistence tests cover:
  - default branch creation for legacy sessions;
  - branch head lookup and uniqueness;
  - turn creation with required snapshot id;
  - turn lifecycle status storage.
- Resolver tests cover:
  - deterministic `MemoryRuntimeIdentity` creation;
  - explicit branch/snapshot selection;
  - compatibility/default resolution for session-only entrypoints;
  - failure on missing snapshot id for runtime-owned path.
- Integration tests cover:
  - one runtime-owned flow propagates the same identity through at least Workspace/proposal/event call boundaries.
- Focused lint/type checks must include the new records, resolver service, and tests.

### 7. Wrong vs Correct

#### Wrong

```python
query = RetrievalQuery(
    query_id="q1",
    query_kind="recall",
    story_id=story_id,
)
```

This leaves runtime-owned retrieval work unattached to a turn or branch head.

#### Correct

```python
identity = runtime_identity_service.resolve_runtime_entry_identity(
    session_id=session_id,
    command_kind="continue",
    actor="story_runtime",
)
```

The runtime resolves or creates persistent branch/turn identity first, then later slices can carry that identity into retrieval, workspace, proposal, and event services.
