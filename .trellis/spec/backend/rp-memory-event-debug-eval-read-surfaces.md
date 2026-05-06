# RP Memory Event Debug Eval Read Surfaces

## Scenario: persistent memory evidence is readable as exact-identity trace bundles for runtime debug and eval without turning the event spine into a truth store

### 1. Scope / Trigger

- Trigger: boot-bar work establishes persistent memory event records, persistent Runtime Workspace materials, and deterministic read manifests, but full runtime foundation still lacks stable backend read surfaces that join this evidence into turn/branch/source/proposal traces. Debug and eval cannot stay process-local or ad hoc if runtime memory behavior must be explainable after restart.
- Applies to backend RP memory contract work for:
  - exact-identity turn trace reads;
  - branch/source/proposal/material trace reads;
  - joined readback across events, workspace materials, proposals, and manifests;
  - eval-friendly deterministic evidence bundles;
  - focused trace query tests.
- This slice must not:
  - replay events as the source of truth;
  - replace Core/Projection/Recall/Archival stores with trace reads;
  - require external observability systems to answer product memory questions;
  - widen public mutation tools.

### 2. Surfaces

Trace read service:

```python
class MemoryTraceReadService:
    def get_turn_trace(self, *, identity: MemoryRuntimeIdentity) -> dict[str, Any]: ...
    def get_branch_trace(self, *, story_id: str, branch_head_id: str, limit: int = 100) -> dict[str, Any]: ...
    def get_source_ref_trace(self, *, source_ref: str, story_id: str) -> dict[str, Any]: ...
    def get_proposal_trace(self, *, proposal_id: str, story_id: str) -> dict[str, Any]: ...
    def get_material_trace(self, *, material_ref: str, story_id: str) -> dict[str, Any]: ...
```

Representative turn trace shape:

```json
{
  "identity": {
    "story_id": "story_1",
    "session_id": "session_1",
    "branch_head_id": "branch_main",
    "turn_id": "turn_17",
    "runtime_profile_snapshot_id": "profile_4"
  },
  "events": [],
  "runtime_workspace_materials": [],
  "read_manifests": [],
  "proposal_receipts": [],
  "retrieval_usage_refs": [],
  "dirty_targets": []
}
```

### 3. Contracts

#### Trace-only contract

- These surfaces are inspection/debug/eval reads only.
- They must not rebuild or replace business truth.
- Truth remains in the underlying stores:
  - Core / Projection
  - Recall / Archival retrieval storage
  - Runtime Workspace records
  - proposal/apply persistence
  - persistent event records

#### Exact-identity contract

- `get_turn_trace(...)` requires full `MemoryRuntimeIdentity`.
- Runtime traces keyed by `session_id` alone are insufficient.
- Returned evidence must be limited to the exact identity unless the query explicitly asks for a broader branch/source/proposal view.

#### Join contract

- Turn traces must be able to join the persisted evidence that explains one runtime turn:
  - memory events
  - Runtime Workspace materials
  - deterministic read manifests
  - proposal/apply receipts
  - retrieval usage refs when present
  - dirty targets / invalidation evidence
- Proposal traces must be able to join Runtime Workspace material evidence from proposal/apply governance source refs even when no memory event row separately points at that material yet.
- The service should centralize this joining logic so eval and future UI do not each reimplement it.

#### Restart durability contract

- Trace reads must work after process restart from the persisted memory evidence.
- In-process-only data is not sufficient for the full-foundation trace surface.

#### Debug/eval contract

- Runtime debug should be able to answer:
  - what changed this turn;
  - what the runtime/workers saw;
  - which retrieval cards or source refs were used;
  - which proposal/apply actions happened;
  - why downstream consumers became dirty or were refreshed.
- Eval should be able to pull the same evidence deterministically for replay and scoring.

#### Observability boundary contract

- Generic model/request observability systems may supplement these traces.
- They do not replace the backend memory trace contract, because they do not own branch visibility, governed mutation provenance, or memory-layer truth boundaries.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| A turn has persistent events, workspace materials, and read manifests | `get_turn_trace(...)` joins them under one exact identity |
| Process restarts after the turn | The same turn trace remains readable from persisted evidence |
| A caller asks for a different branch or turn identity | Evidence does not leak across identities |
| Proposal trace is requested | Returned data joins proposal/apply receipts with related memory events/source refs |
| Source ref trace is requested | Returned data can show related events, materials, and proposal usage for that source |
| Eval requests deterministic memory evidence for one generated artifact | The read surface can return the relevant manifest/usage/event/proposal chain |

### 5. Good / Base / Bad Cases

- Good: a turn trace shows the event sequence, the selected retrieval cards, the read manifest, the proposal that applied, and the resulting dirty targets.
- Good: a proposal trace can explain which source refs and branch identity were involved in the mutation.
- Good: a material trace can explain why a Runtime Workspace card was later invalidated.
- Base: raw event and workspace repositories still exist, but callers use a stable backend trace read surface instead of manually joining them.
- Bad: treating event rows alone as enough for replay while ignoring manifests/materials/proposal receipts.
- Bad: querying traces only by `session_id` and mixing sibling branches together.
- Bad: requiring external span storage to explain product memory behavior.

### 6. Tests Required

- Trace tests cover:
  - exact-identity turn trace joining;
  - branch isolation;
  - proposal/material/source trace query behavior;
  - restart-safe reads from persisted evidence.
- Eval-oriented tests cover:
  - deterministic evidence bundle extraction for one generated artifact or turn.
- Boundary tests cover:
  - trace reads do not mutate stores;
  - trace service does not derive truth by replaying events.
- Focused lint/type checks must include the trace read contract and tests.

### 7. Wrong vs Correct

#### Wrong

```python
events = event_repository.list_by_session(session_id)
return {"events": events}
```

This loses branch/turn/profile isolation and leaves every caller to guess how to join the rest of the evidence.

#### Correct

```python
trace = memory_trace_read_service.get_turn_trace(identity=identity)
```

The backend joins persisted turn evidence under the exact memory identity while keeping the underlying stores as the source of truth.
