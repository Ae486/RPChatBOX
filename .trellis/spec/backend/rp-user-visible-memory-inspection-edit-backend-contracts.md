# RP User-Visible Memory Inspection Edit Backend Contracts

## Scenario: users can inspect and correct memory through branch-aware backend contracts without bypassing governed Core, Recall, or Archival boundaries

### 1. Scope / Trigger

- Trigger: the repo already exposes Core/Projection memory reads and governed authoritative block mutation, but full runtime foundation still lacks one stable backend contract for branch-aware inspection plus user-visible correction paths across Core, Recall, and Archival.
- Applies to backend RP memory contract work for:
  - branch-aware inspection queries across visible layers;
  - Core direct edit commands routed through the shared mutation kernel;
  - Recall review/recompute/invalidate/supersede commands;
  - Archival evolution edit/version/reindex commands;
  - focused inspection/edit contract tests.
- This slice must not:
  - collapse all layers into one generic CRUD path;
  - create a raw user-only Core write path;
  - bypass Recall/Archival lifecycle services with direct storage edits;
  - require finished UI polish before the backend contract exists.

### 2. Surfaces

Inspection query surface:

```python
class MemoryInspectionService:
    def inspect_visible_memory(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        layers: list[str] | None = None,
        domains: list[str] | None = None,
        include_hidden_audit: bool = False,
    ) -> dict[str, Any]: ...
    def direct_core_edit(self, *, request: CoreDirectEditRequest) -> ProposalReceipt: ...
    def review_recall(self, *, command: RecallReviewCommand) -> dict[str, Any]: ...
    def evolve_archival(self, *, request: ArchivalEvolutionRequest) -> dict[str, Any]: ...
```

Representative command surfaces:

```python
class CoreDirectEditRequest(BaseModel):
    identity: MemoryRuntimeIdentity
    actor: str
    domain: str
    operations: list[StatePatchOperation]
    base_refs: list[ObjectRef]
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    reason: str | None = None


class RecallReviewCommand(BaseModel):
    identity: MemoryRuntimeIdentity
    actor: str
    action: str
    material_refs: list[str]
    reason: str | None = None


class ArchivalEvolutionRequest(BaseModel):
    ...
```

Representative API family:

```text
GET  /api/rp/story-sessions/{session_id}/memory/inspection
POST /api/rp/story-sessions/{session_id}/memory/core/direct-edit
POST /api/rp/story-sessions/{session_id}/memory/recall/actions
POST /api/rp/story-sessions/{session_id}/memory/archival/evolution
```

### 3. Contracts

#### Inspection contract

- Users must be able to inspect visible memory through one branch-aware backend query surface.
- Inspection must respect active visibility across:
  - Core authoritative
  - Projection/current view
  - Runtime Workspace
  - Recall
  - Archival
- The same inspection contract may provide optional audit-only access to hidden/superseded material when explicitly requested and authorized, but normal active inspection must not leak unrelated branch material.

#### Core direct-edit contract

- Product may call the action `direct edit`.
- Backend must route it through the shared governed Core mutation kernel.
- A Core direct edit must:
  - carry full identity;
  - preserve actor/origin/source refs;
  - perform conflict checks;
  - emit events;
  - refresh or invalidate affected Projection/View targets;
  - invalidate related Runtime Workspace candidates when appropriate.

#### Recall review contract

- Recall user actions are layer-specific lifecycle actions, not generic truth writes.
- Supported user-review actions must include the governed subset needed by the product:
  - recompute
  - invalidate
  - supersede
- These actions must route through the Recall lifecycle service and stay branch-aware.
- Material-ref validation must fail closed on story ownership before visibility checks complete:
  - even `story_global` Recall material from another story must not be operable from the current story/session identity.

#### Archival evolution contract

- User corrections to Archival Knowledge must route through the governed Archival evolution/version/reindex path.
- They must not directly mutate active source/chunk rows outside the evolution service.
- The same fail-closed story ownership rule applies to Archival source/material refs before visibility scope is considered.

#### Shared backend contract

- Setup/runtime/longform/roleplay/TRPG should be able to reuse the same backend inspection/edit services.
- UI-specific differences should sit above these backend contracts, not inside them.

#### API namespace contract

- The existing `/memory/*` route family remains the preferred outward namespace.
- New user-visible capabilities should extend that family rather than inventing a disconnected correction API surface.

### 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| User inspects active visible memory under one identity | Only branch-visible Core/Projection/Workspace/Recall/Archival material is returned |
| User performs Core direct edit | Shared mutation kernel handles it; revision/provenance/event/dirty/refresh outcomes are recorded |
| User performs Recall review action | Action routes through Recall lifecycle governance and remains traceable |
| User performs Archival correction | Action routes through Archival evolution/reindex governance and remains traceable |
| Hidden/superseded material exists on another branch | Normal inspection does not leak it |
| Setup/runtime reuse the backend contract | They call the same inspection/edit service surfaces, not separate parallel implementations |

### 5. Good / Base / Bad Cases

- Good: a user inspects active branch-visible memory, corrects a Core fact, and the backend records the governed mutation plus downstream refresh/invalidation.
- Good: a user marks a stale Recall item superseded through a governed review command rather than directly deleting chunks.
- Good: a user edits Archival source material through evolution/reindex, and later retrieval/search explains which source version is active.
- Base: existing authoritative/projection/block read routes remain useful and can be composed into the broader inspection surface.
- Bad: exposing one generic “edit memory” endpoint that writes Core, Recall, and Archival through the same raw storage path.
- Bad: direct Core edit mutates session JSON or store rows without conflict/provenance/event handling.
- Bad: Recall and Archival user actions bypass their lifecycle/reindex governance because they are “just admin tools”.

### 6. Tests Required

- Inspection tests cover:
  - branch-aware visible-layer queries;
  - no unrelated branch leakage;
  - optional audit read behavior where applicable.
- Core direct-edit tests cover:
  - shared mutation-kernel routing;
  - conflict handling;
  - dirty/refresh/event outcomes.
- Recall/Archival action tests cover:
  - lifecycle/evolution service routing;
  - traceability and branch-awareness.
- Compatibility tests cover:
  - existing memory route family remains coherent while new inspection/edit capabilities are added.
- Focused lint/type checks must include the inspection/edit backend contract and tests.

### 7. Wrong vs Correct

#### Wrong

```python
session.current_state_json["character_state_digest"] = payload
session.commit()
```

This bypasses the shared mutation kernel and makes branch-aware inspection/debug inconsistent.

#### Correct

```python
receipt = memory_inspection_service.direct_core_edit(
    request=CoreDirectEditRequest(
        identity=identity,
        actor=user_id,
        domain="character",
        operations=operations,
        base_refs=base_refs,
    )
)
```

Core correction stays governed, while Recall and Archival corrections use their own lifecycle/evolution commands under the same user-visible memory backend family.
