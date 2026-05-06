# Memory Contract Registry + Identity/Event Skeleton Slice Plan

> Date: 2026-05-04
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Source alignment:
> - `.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-strengthening-proposal.md`
> - `.trellis/tasks/04-28-runtime-story-dev-task/research/memory-strengthening-preflight-grill-questions.md`
> - `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-memory-domain-preliminary-design.md`

## Slice

Implement the first memory strengthening slice:

```text
Memory Contract Registry
  + StorySession / BranchHead / Turn / RuntimeProfileSnapshot identity DTO
  + lightweight memory change event model
```

This slice provides executable contracts for later Runtime Workspace, worker tools, projection refresh, retrieval-card usage, and branch-ready filtering. It does not implement those later behaviors.

## Why This Slice First

- Runtime Workspace materials, worker proposals, projection refreshes, retrieval usage records, and branch filters all need the same domain / block / identity vocabulary.
- If this registry is delayed, services will keep adding local domain allowlists and longform field assumptions.
- The preflight answers confirm there is no need for more user grill before coding this slice.

## Implementation Plan

1. Add backend spec:
   - `.trellis/spec/backend/rp-memory-contract-registry-identity-event-skeleton.md`
   - Register it in `.trellis/spec/backend/index.md`.
2. Add contract models:
   - `backend/rp/models/memory_contract_registry.py`
   - Include registry domain/block models, runtime identity model, source refs, dirty targets, and change event model.
3. Add registry service:
   - `backend/rp/services/memory_contract_registry.py`
   - Load a versioned declarative bootstrap registry with 13 domains.
   - Expose narrow resolver/list methods.
4. Preserve current compatibility:
   - Add `knowledge_boundary` and `rule_state` to typed DSL domain compatibility if needed by current DTO boundaries.
   - Do not rewrite Core State reads, proposal/apply, RetrievalBroker, or public memory tools in this slice.
5. Add tests:
   - `backend/rp/tests/test_memory_contract_registry.py`
   - Cover bootstrap domains, lifecycle filtering, alias resolution, mode activation, extensibility, identity validation, and event identity/source/dirty metadata.

## Explicit Non-Goals

- No universal durable `rp_blocks` table.
- No public memory tool/MCP widening.
- No full Runtime Workspace typed material store.
- No branch UI or whole-store memory copy.
- No automatic promotion of Recall / Archival evidence into Core State.
- No rewrite of existing proposal/apply persistence.

## Verification Plan

Focused commands for the implement slice:

```powershell
pytest backend\rp\tests\test_memory_contract_registry.py -q
ruff check backend\rp\models\memory_contract_registry.py backend\rp\services\memory_contract_registry.py backend\rp\tests\test_memory_contract_registry.py backend\rp\models\dsl.py
ruff format --check backend\rp\models\memory_contract_registry.py backend\rp\services\memory_contract_registry.py backend\rp\tests\test_memory_contract_registry.py backend\rp\models\dsl.py
mypy --follow-imports=skip --check-untyped-defs backend\rp\models\memory_contract_registry.py backend\rp\services\memory_contract_registry.py backend\rp\tests\test_memory_contract_registry.py backend\rp\models\dsl.py
git diff --check
```

After the slice is implemented, run `trellis-check` before starting the next memory strengthening slice.
