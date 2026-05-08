# RP User-Visible Memory Canonical JSON Governance

## Scenario: user-visible memory inspection and governed editing share one canonical block and entry envelope so UI and backend governance never diverge

### 1. Scope / Trigger

- Trigger: the memory inspection/edit backend now exposes branch-aware reads and
  governed Core/Recall/Archival actions, but related runtime design docs still
  require one canonical JSON / DSL envelope that both UI editing and worker
  proposal trace can understand.
- Applies to backend RP memory contract work for:
  - canonical block metadata returned by inspection surfaces;
  - canonical entry metadata used by user edits and proposal trace;
  - validation/error/conflict/action metadata on user-visible memory rows;
  - focused canonical-envelope tests across Core/Recall/Archival/Workspace.
- This slice must not:
  - invent a new raw memory editor path separate from governed services;
  - collapse all layers into one generic mutation API;
  - bypass existing Core direct-edit, Recall lifecycle, or Archival evolution
    governance;
  - require finished frontend polish before the backend envelope is stable.

### 2. Surfaces

Canonical block envelope:

```python
class MemoryDisplayBlock(BaseModel):
    block_id: str
    domain: str
    layer: str
    scope: str | None = None
    visibility: dict[str, Any]
    revision: int | None = None
    permission_level: dict[str, Any] = Field(default_factory=dict)
    lifecycle_state: str | None = None
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    validation_summary: dict[str, Any] = Field(default_factory=dict)
    editable_fields: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    entrypoints: dict[str, Any] = Field(default_factory=dict)
    entries: list[dict[str, Any]] = Field(default_factory=list)
```

Canonical entry envelope:

```python
class MemoryDisplayEntry(BaseModel):
    entry_id: str
    entry_type: str
    label: str | None = None
    current_value: Any = None
    editable_fields: list[str] = Field(default_factory=list)
    field_validation_rules: dict[str, Any] = Field(default_factory=dict)
    base_revision: int | None = None
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    user_edit_metadata: dict[str, Any] = Field(default_factory=dict)
    conflict_state: str | None = None
    last_modified_actor: str | None = None
    last_modified_turn_or_event_id: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
```

Representative producer surface:

```python
class MemoryInspectionService:
    def inspect_visible_memory(...) -> dict[str, Any]: ...
```

### 3. Contracts

#### Shared-envelope contract

- User-visible memory must expose one canonical block/entry envelope.
- The same envelope must be understandable by:
  - inspection UI;
  - governed user-edit UI flows;
  - worker proposal / trace inspection;
  - debug/eval tools when they display user-visible memory state.
- UI-specific composition may differ, but the backend-owned semantic envelope
  must not fork by client.

#### Block-envelope contract

- Each displayed block must include at least:
  - stable `block_id`;
  - `domain`;
  - `layer`;
  - branch/turn/profile visibility summary;
  - revision when meaningful;
  - permission-level summary;
  - lifecycle state when meaningful;
  - source refs / provenance summary;
  - validation summary;
  - editable fields;
  - allowed actions;
  - governed action entrypoints.

#### Entry-envelope contract

- Each displayed editable entry must include at least:
  - stable `entry_id`;
  - `entry_type`;
  - current value;
  - editable fields;
  - field-level validation rules or validation summary;
  - base revision when the layer supports governed conflict checks;
  - source refs;
  - user-edit metadata;
  - conflict state;
  - last modified actor;
  - last modified turn/event id;
  - allowed actions.

#### Layer-specific governance contract

- Core State:
  - canonical envelope may expose direct governed edit;
  - base revision/conflict metadata must be available where applicable;
  - backend action still routes through the shared mutation kernel.
- Projection:
  - mainly inspectable; direct text editing is not the normal path;
  - allowed actions should emphasize refresh/readback rather than raw edit.
- Recall:
  - canonical envelope should primarily expose review/recompute/invalidate/
    supersede actions rather than routine fact editing.
- Archival:
  - canonical envelope should expose governed evolution/reindex entrypoints;
  - direct raw source/chunk mutation remains forbidden.
- Runtime Workspace:
  - canonical envelope may be inspectable and action-limited;
  - durable edits must still go through promotion/proposal/apply or other
    governed paths.

#### Governance-binding contract

- Canonical JSON is not just display data.
- It must bind to the same backend governance used by direct edit / lifecycle /
  evolution actions so UI cannot become a separate incompatible memory editor.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| UI requests visible memory inspection | Backend returns canonical block/entry envelopes, not ad hoc layer payloads only |
| Core entry is editable | Envelope exposes editable fields/base revision/allowed action, and action still routes through shared mutation kernel |
| Recall item is reviewable | Envelope exposes lifecycle actions instead of raw text write semantics |
| Archival item is editable | Envelope exposes governed evolution/reindex entrypoints instead of raw source overwrite |
| Worker trace references one user-visible memory item | The same stable block/entry ids and source refs remain understandable in trace/debug views |
| Different clients consume the same backend surface | They reuse the same semantic envelope instead of inventing incompatible ad hoc shapes |

### 5. Good / Base / Bad Cases

- Good: UI receives one block envelope for a Core block showing revision,
  editable fields, validation summary, and the governed direct-edit action.
- Good: a Recall item displays recompute/invalidate/supersede actions with the
  same stable ids used later in trace/debug.
- Good: an Archival item exposes version/evolution entrypoints rather than raw
  text mutation.
- Base: old read services can still supply the underlying facts, but
  `MemoryInspectionService` becomes the canonical envelope producer.
- Bad: UI builds one JSON shape, worker trace uses another, and neither matches
  the governed backend command surfaces.
- Bad: ad hoc response shapes force every client to rediscover editable fields,
  revision keys, and allowed actions by convention.

### 6. Tests Required

- Inspection tests cover:
  - canonical block metadata on visible Core/Recall/Archival/Workspace items;
  - stable entry ids and action metadata;
  - no unrelated branch leakage.
- Governance-binding tests cover:
  - Core direct-edit envelope fields match governed edit prerequisites;
  - Recall/Archival envelopes expose only their allowed governed actions.
- Trace-compatibility tests cover:
  - source refs and stable ids remain usable across inspection and trace/debug
    surfaces.
- Focused lint/type checks must include the canonical-envelope contract and its
  tests.

### 7. Wrong vs Correct

#### Wrong

```python
return {
    "layers": {
        "core_state.authoritative": raw_core_items,
        "recall": raw_recall_assets,
    }
}
```

This leaves every client to invent its own editing semantics and trace ids.

#### Correct

```python
return memory_inspection_service.inspect_visible_memory(
    identity=identity,
    layers=["core_state.authoritative", "recall", "archival"],
)
```

The inspection surface returns backend-owned canonical block/entry envelopes
that already bind to the governed action model.
