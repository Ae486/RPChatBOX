# RP Runtime Profile Snapshot Minimal Compiler

## Scenario: Boot-bar runtime needs a pinned immutable profile before retrieval, permissions, and context policy can stop drifting with latest session config

### 1. Scope / Trigger

- Trigger: current memory/runtime work already has a registry skeleton, mode defaults, and story-level retrieval config resolution, but there is no persisted immutable `RuntimeProfileSnapshot` that pins worker activation, permission, retrieval, and context policy at turn start. Boot-bar runtime cannot safely depend on latest mutable session config.
- Applies to backend RP runtime/memory contract work for:
  - persistent `RuntimeProfileSnapshot` records;
  - deterministic compile/publish/activate service boundaries;
  - minimal registry/config-driven profile compilation;
  - turn-start pinning semantics;
  - focused compile/pinning tests.
- This slice must not implement:
  - full registry CRUD UI or marketplace-like worker management;
  - branch visibility resolver;
  - full worker tool surfaces;
  - direct retrieval usage loop;
  - full packet/read-manifest implementation.

### 2. Surfaces

Persistent record shape:

```python
class RuntimeProfileSnapshotRecord(SQLModel, table=True):
    runtime_profile_snapshot_id: str
    story_id: str
    session_id: str
    mode: str
    source_config_revision: str | None
    compiled_profile_json: dict[str, Any]
    created_from: str
    status: str
    created_at: datetime
    activated_at: datetime | None
    superseded_at: datetime | None
```

Compiler/activation surface:

```python
class RuntimeProfileSnapshotService:
    def compile_snapshot(
        self,
        *,
        story_id: str,
        session_id: str,
        mode: str,
        created_from: str,
    ) -> RuntimeProfileSnapshotRecord: ...
    def publish_snapshot(self, snapshot_id: str) -> RuntimeProfileSnapshotRecord: ...
    def require_snapshot(self, snapshot_id: str) -> RuntimeProfileSnapshotRecord: ...
    def require_active_snapshot(self, *, session_id: str) -> RuntimeProfileSnapshotRecord: ...
```

Compiled profile minimum content:

```python
{
    "mode_profile": {...},
    "domain_activation": {...},
    "block_activation": {...},
    "worker_activation": {...},
    "permission_profile": {...},
    "retrieval_policy": {...},
    "context_policy": {...},
    "packet_policy": {...},
    "writer_model_profile": {...},
    "worker_model_profiles": {...},
    "mode_specific_settings": {...},
}
```

Stable error codes:

```text
runtime_profile_snapshot_not_found
runtime_profile_snapshot_compile_failed
runtime_profile_snapshot_activation_conflict
runtime_profile_snapshot_no_active_snapshot
```

### 3. Contracts

#### Snapshot ownership

- `RuntimeProfileSnapshot` is the immutable compiled runtime profile for one future turn or set of future turns.
- It is not a draft config block.
- It is not the live mutable runtime panel payload.
- It is the compiled/published backend contract consumed by turn-start identity resolution.

#### Compile contract

- Compilation must be deterministic from:
  - registry/bootstrap defaults;
  - persisted story/runtime config inputs;
  - explicit overrides or published runtime settings.
- Boot-bar scope may use default descriptors and minimal persisted overrides.
- The compiler must already be descriptor-driven enough that later roleplay/TRPG domains or workers do not require rewriting core memory mutation/read services.
- Full dynamic management can arrive later; deterministic compilation cannot wait for it.

#### Pinning contract

- Setup activation or first runtime publish must create the first snapshot.
- Later runtime config changes create a new snapshot instead of mutating old snapshots.
- Every turn must pin one active snapshot at turn start.
- A turn in progress must not drift to the newest snapshot after it has started.
- Hot config updates affect future turns by default.

#### Policy contract

- The compiled snapshot must minimally pin:
  - mode profile;
  - domain/block activation;
  - worker activation;
  - worker permission profile;
  - retrieval policy;
  - context/packet policy;
  - writer/worker model-provider configuration;
  - mode-specific settings needed by boot workers.
- Later services may expose richer views, but these fields are the boot minimum.

#### Integration contract

- Runtime-owned retrieval must migrate from `story_id` latest-config resolution toward snapshot-pinned policy resolution.
- Proposal/apply and worker permission checks must later consume the pinned permission profile instead of scattered defaults.
- Runtime identity resolution must fail closed if a boot-bar runtime turn cannot pin a snapshot id.

#### Compatibility contract

- Existing latest-story-config resolution may remain temporarily for legacy/debug paths.
- Boot-bar runtime-owned turns must use a real persisted snapshot id.
- Snapshot publish/activate semantics must supersede older active snapshots rather than mutating them in place.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Story/runtime config is compiled twice with the same inputs | Same effective compiled profile content is produced |
| A new runtime config is published | A new snapshot record is created; old snapshot remains immutable |
| Turn starts after publish | Turn pins the newly active snapshot |
| Turn started before later publish | Existing turn keeps its original snapshot id |
| Session active snapshot pointer is missing or stale at turn start | Runtime entry resolution must call `ensure_active_snapshot(...)`, create/publish a fresh immutable snapshot for the same compiled content, and re-pin the session instead of silently reusing the old active row |
| Runtime-owned path cannot compile or publish a snapshot | Reject with a stable runtime profile snapshot error such as `runtime_profile_snapshot_compile_failed` or `runtime_profile_snapshot_no_active_snapshot` |
| Snapshot id is requested directly and missing | Reject with `runtime_profile_snapshot_not_found` |

### 5. Good / Base / Bad Cases

- Good: a roleplay session publishes a new snapshot that changes active domains and retrieval policy, but only future turns use it.
- Good: a turn starts after the session pointer was corrupted or points to a missing snapshot; the runtime rebuilds/publishes a fresh snapshot and pins the turn to that new id.
- Good: boot runtime uses bootstrap registry defaults plus explicit story/runtime overrides without needing a full config UI.
- Base: old story-level config services may still exist temporarily, but boot runtime no longer relies on them directly once a turn is pinned.
- Bad: mutating the active snapshot record in place when the runtime panel changes.
- Bad: resolving a turn by calling `require_active_snapshot(...)` first and re-pinning the session to an old active row after detecting a stale pointer; turn-start recovery must go through `ensure_active_snapshot(...)`.
- Bad: reading “latest session config” during a turn and silently drifting retrieval or permission behavior.
- Bad: hardcoding longform worker activation in the compiler instead of compiling descriptors from registry/config inputs.

### 6. Tests Required

- Compiler tests cover:
  - deterministic compile output from the same inputs;
  - minimum compiled profile fields;
  - default descriptor-driven mode output for longform/roleplay/TRPG.
- Persistence tests cover:
  - snapshot record creation;
  - publish/activate behavior;
  - superseding previous active snapshot without mutating it.
- Pinning tests cover:
  - turn-start uses the active snapshot;
  - later config publish does not change an in-progress turn's snapshot id.
  - stale session active-snapshot pointers are rebuilt through `ensure_active_snapshot(...)` in both the service-level path and the story turn API stream path.
- Focused lint/type checks must include the new record/service/tests.

### 7. Wrong vs Correct

#### Wrong

```python
config = RetrievalRuntimeConfigService(session).resolve_story_config(story_id=story_id)
```

This reads the latest story/session config and allows runtime behavior to drift during or after turn start.

#### Correct

```python
snapshot = runtime_profile_snapshot_service.require_active_snapshot(session_id=session_id)
identity = runtime_identity_service.resolve_runtime_entry_identity(
    session_id=session_id,
    command_kind="continue",
    actor="story_runtime",
    requested_runtime_profile_snapshot_id=snapshot.runtime_profile_snapshot_id,
)
```

The runtime first pins one immutable compiled snapshot, then later retrieval, permission, and packet policy consumers can resolve behavior from that snapshot id.
