# Runtime Workspace Turn Material Store Slice Plan

> Date: 2026-05-04
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Depends on:
> - `.trellis/spec/backend/rp-memory-contract-registry-identity-event-skeleton.md`
> - `backend/rp/models/memory_contract_registry.py`
> - `backend/rp/services/memory_contract_registry.py`

## Slice

Implement the second memory strengthening slice:

```text
Runtime Workspace typed turn-material store
  + material envelope DTO
  + lifecycle / kind / visibility enums
  + identity-scoped in-process service skeleton
  + domain registry validation
  + lightweight MemoryChangeEvent receipts
```

This creates the common current-turn material shape needed by future writer retrieval usage, rule cards, review overlays, worker candidates, evidence bundles, packet refs, and token usage traces.

## Why This Slice Now

- The registry / identity slice exists, so Runtime Workspace materials can now carry the correct domain and story/branch/turn/profile identity.
- Writer-side retrieval and post-write workers need one shared material lifecycle before either path is implemented.
- The current Runtime Workspace Block views only expose draft artifacts and discussion entries; they do not provide a generic turn-material model.

## Implementation Plan

1. Add backend spec:
   - `.trellis/spec/backend/rp-runtime-workspace-turn-material-store.md`
   - Register it in `.trellis/spec/backend/index.md`.
2. Add models:
   - `backend/rp/models/runtime_workspace_material.py`
   - Include material kind enum, lifecycle enum, material DTO, query DTO if useful, service receipt DTO, and validation for blank fields.
3. Add service:
   - `backend/rp/services/runtime_workspace_material_service.py`
   - Use an injected in-process store for this first contract slice.
   - Validate domain via `MemoryContractRegistryService`.
   - Key material by full `MemoryRuntimeIdentity`.
   - Enforce `short_id` uniqueness per identity.
   - Return `MemoryChangeEvent` receipts for create and lifecycle update.
4. Preserve current boundaries:
   - Do not replace `StoryArtifact` / `StoryDiscussionEntry`.
   - Do not modify `RpBlockReadService` Runtime Workspace Block view behavior.
   - Do not add DB tables or public memory tools.
   - Do not promote material into Core State / Recall / Archival.
5. Add tests:
   - `backend/rp/tests/test_runtime_workspace_material_service.py`
   - Cover identity isolation, domain validation, test-only registry domain, short-id behavior, lifecycle update events, and material-not-truth metadata.

## Explicit Non-Goals

- No persistent DB table in this slice.
- No writer final-output usage gate.
- No retrieval tool integration.
- No worker orchestration.
- No proposal/apply integration.
- No public MCP/tool surface.
- No changes to current draft/discussion Block views.

## Verification Plan

Focused commands for the implement slice:

```powershell
pytest backend\rp\tests\test_runtime_workspace_material_service.py -q
ruff check backend\rp\models\runtime_workspace_material.py backend\rp\services\runtime_workspace_material_service.py backend\rp\tests\test_runtime_workspace_material_service.py
ruff format --check backend\rp\models\runtime_workspace_material.py backend\rp\services\runtime_workspace_material_service.py backend\rp\tests\test_runtime_workspace_material_service.py
mypy --follow-imports=skip --check-untyped-defs backend\rp\models\runtime_workspace_material.py backend\rp\services\runtime_workspace_material_service.py backend\rp\tests\test_runtime_workspace_material_service.py
git diff --check
```

After this slice is implemented, run `trellis-check` before starting the next memory strengthening slice.
