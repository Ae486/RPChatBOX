# Memory Change Event Spine Slice Plan

> Date: 2026-05-04
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Depends on:
> - `.trellis/spec/backend/rp-memory-contract-registry-identity-event-skeleton.md`
> - `.trellis/spec/backend/rp-runtime-workspace-turn-material-store.md`
> - `backend/rp/models/memory_contract_registry.py`
> - `backend/rp/services/runtime_workspace_material_service.py`

## Slice

Implement the third memory strengthening slice:

```text
Memory Change Event Spine
  + reusable event record/list service
  + full MemoryRuntimeIdentity scoping
  + registry-backed domain validation and alias normalization
  + dirty-target readback
  + optional Runtime Workspace publishing into the shared spine
```

## Why This Slice Now

The first two slices created:

- the declarative registry and `MemoryChangeEvent` DTO;
- the typed Runtime Workspace material service, which already emits receipt events locally.

The next proposal priority is to make lightweight memory events usable as a shared trace/invalidation spine before Core State conflict enforcement, projection refresh, writer retrieval usage hooks, or worker dirty checks depend on local event lists.

## Implementation Plan

1. Add backend spec:
   - `.trellis/spec/backend/rp-memory-change-event-spine.md`
   - Register it in `.trellis/spec/backend/index.md`.
2. Add service:
   - `backend/rp/services/memory_change_event_service.py`
   - Use an injected in-process store for this first contract slice.
   - Validate / normalize event domains through `MemoryContractRegistryService`.
   - Key events by full `MemoryRuntimeIdentity`.
   - Reject duplicate event ids.
   - Support list filters and dirty-target flattening.
3. Integrate Runtime Workspace lightly:
   - Add optional `memory_change_event_service` injection to `RuntimeWorkspaceMaterialService`.
   - Publish successful material create / lifecycle events to the shared service when injected.
   - Preserve the existing local receipt and `RuntimeWorkspaceMaterialStore.events` behavior.
4. Add focused tests:
   - `backend/rp/tests/test_memory_change_event_service.py`
   - Cover identity isolation, alias normalization, unknown domains, duplicate ids, filters, dirty targets, and Runtime Workspace publishing.
5. Preserve boundaries:
   - no DB event table;
   - no full event sourcing;
   - no Core State apply rewrite;
   - no projection refresh write contract;
   - no public memory tool widening;
   - no branch UI or Runtime Workspace promotion.

## Verification

Run at minimum:

```powershell
pytest backend\rp\tests\test_memory_change_event_service.py backend\rp\tests\test_runtime_workspace_material_service.py -q
ruff check backend\rp\services\memory_change_event_service.py backend\rp\services\runtime_workspace_material_service.py backend\rp\tests\test_memory_change_event_service.py
ruff format --check backend\rp\services\memory_change_event_service.py backend\rp\services\runtime_workspace_material_service.py backend\rp\tests\test_memory_change_event_service.py
mypy --follow-imports=skip --check-untyped-defs backend\rp\services\memory_change_event_service.py backend\rp\services\runtime_workspace_material_service.py backend\rp\tests\test_memory_change_event_service.py
git diff --check
```

After implementation, run `trellis-check` before starting the next slice.
