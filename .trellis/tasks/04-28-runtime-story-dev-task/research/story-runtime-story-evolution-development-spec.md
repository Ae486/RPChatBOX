# Story Runtime Story Evolution Development Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Story Evolution / Archival Evolution / Memory Change Governance
>
> Status: development-spec-v1

## 1. Scope

Story Evolution is the explicit user/system workflow for changing the story foundation after activation.

This spec covers the next implementation planning layer for:

- branch-scoped Story Evolution by default;
- Archival Knowledge versioned edit / import / reindex governance;
- visibility scopes for evolved material;
- provenance from evolved Archival source versions to later retrieval hits and Core proposals;
- memory change events and debug/eval trace.

It does not cover:

- creating a new parallel `StoryEvolutionWorker` system;
- direct Core State truth overwrite;
- treating Recall Memory as a settings CRUD layer;
- cross-branch automatic propagation without explicit user scope.

## 2. Design Rules

Story Evolution reuses existing Memory OS capabilities:

- Memory Inspection;
- governed Core mutation / proposal/apply;
- Archival ingestion and retrieval maintenance;
- block-owner worker analysis when needed;
- memory change event spine;
- branch visibility resolver.

Default visibility is current branch only.

Broader scopes must be explicit:

- `selected_branches`
- `all_existing_branches`
- `story_global`

Only `story_global` affects future branches created after the evolution action.
`selected_branches` is a fail-closed scope over already existing branch heads in
the same story/session; it must not accept arbitrary future or cross-story
branch ids as a latent visibility grant.

## 3. Suggested Files

Backend:

- `backend/rp/models/story_evolution_contracts.py`
- `backend/rp/services/story_evolution_service.py`
- `backend/rp/services/archival_evolution_service.py`
- `backend/rp/services/runtime_memory_persistence_repository.py`
- `backend/rp/services/retrieval_maintenance_service.py`
- `backend/rp/services/branch_visibility_resolver.py`

Tests:

- `backend/rp/tests/test_story_evolution_service.py`
- retrieval visibility tests
- memory event/debug read tests

Related code specs:

- `.trellis/spec/backend/rp-archival-evolution-reindex-governance.md`
- `.trellis/spec/backend/rp-user-visible-memory-inspection-edit-backend-contracts.md`
- `.trellis/spec/backend/rp-memory-change-event-spine.md`
- `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md`

## 4. DTOs

```python
class StoryEvolutionRequest(BaseModel):
    identity: MemoryRuntimeIdentity
    actor_id: str | None = None
    target_layer: Literal["core", "recall", "archival"]
    operation: Literal["edit", "import", "invalidate", "recompute", "promote_visibility"]
    visibility_scope: Literal[
        "current_branch",
        "selected_branches",
        "all_existing_branches",
        "story_global",
    ] = "current_branch"
    selected_branch_head_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[MemorySourceRef] = Field(default_factory=list)
    reason: str | None = None
```

```python
class StoryEvolutionReceipt(BaseModel):
    evolution_id: str
    identity: MemoryRuntimeIdentity
    target_layer: str
    operation: str
    visibility_scope: str
    affected_refs: list[MemorySourceRef] = Field(default_factory=list)
    reindex_job_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    status: Literal["accepted", "pending_reindex", "failed"]
    metadata_json: dict[str, Any] = Field(default_factory=dict)
```

## 5. Layer Rules

### Core State

Core State changes do not primarily use Story Evolution.

Allowed paths:

- user direct edit through governed Core mutation kernel;
- worker proposal/apply;
- brainstorm summary apply.

If Story Evolution needs to affect Core, it must produce a governed proposal or direct-edit envelope. It must not write raw authoritative state.

### Recall Memory

Recall is historical material.

Allowed actions:

- review;
- invalidate;
- supersede;
- recompute;
- branch-aware filter.

Recall is not the default setting-edit layer.

### Archival Knowledge

Archival is the primary Story Evolution target.

Allowed actions:

- import new source material;
- edit source material by creating a version/supersession chain;
- reindex evolved source/chunks;
- change visibility through governed receipt.

In-place source/chunk overwrite is forbidden as the authoritative edit path.

## 6. Service Contract

```python
class StoryEvolutionService:
    def apply_evolution(
        self,
        request: StoryEvolutionRequest,
    ) -> StoryEvolutionReceipt: ...

    def promote_visibility(
        self,
        *,
        identity: MemoryRuntimeIdentity,
        evolution_id: str,
        visibility_scope: str,
        selected_branch_head_ids: list[str],
        reason: str | None = None,
    ) -> StoryEvolutionReceipt: ...

    def read_evolution_history(
        self,
        *,
        session_id: str,
        branch_head_id: str | None = None,
    ) -> list[StoryEvolutionReceipt]: ...
```

## 7. Runtime Effects

Successful evolution must:

1. create a receipt;
2. emit memory change events;
3. invalidate dirty packet/read-manifest/projection targets;
4. trigger reindex when Archival source/chunk material changes;
5. make future retrieval respect branch visibility and supersession state;
6. preserve source-version provenance for later Core proposals.

## 8. Validation

Stable errors:

- `story_evolution_invalid_scope`
- `story_evolution_selected_branches_required`
- `story_evolution_cross_branch_scope_forbidden`
- `story_evolution_target_layer_unsupported`
- `story_evolution_core_raw_write_forbidden`
- `story_evolution_archival_version_conflict`
- `story_evolution_reindex_failed`

## 9. Tests Required

1. Archival edit creates a new version/supersession chain.
2. Active runtime evolution defaults to current-branch visibility.
3. Selected-branch visibility exposes material only to selected branches.
4. `all_existing_branches` does not automatically include future branches.
5. `story_global` is visible to future branches.
6. Runtime retrieval excludes superseded/hidden evolved chunks.
7. Later Core proposal source refs can point to exact evolved Archival version.
8. Evolution emits memory change events and dirty targets.
9. Story rollback does not erase global control/evolution history, but branch-visible reads obey the target branch/head.
10. Selected-branch requests reject unknown or cross-story branch ids before creating a new source version.

## 10. Out of Scope

- Complete Story Evolution UI.
- Cross-branch merge/conflict resolution.
- Automatic story-global propagation.
- New standalone Story Evolution worker.
