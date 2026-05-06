# Memory Inspection Edit Backend Technical Research

> Date: 2026-05-06
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Goal: capture the narrow decisions that matter before writing the full user-visible inspection/edit backend contract.

## 1. Current Repo Evidence

Current code/spec anchors:

- `backend/rp/services/memory_inspection_read_service.py`
- `backend/rp/services/story_block_mutation_service.py`
- `backend/rp/services/proposal_workflow_service.py`
- `backend/rp/services/proposal_apply_service.py`
- `backend/rp/services/retrieval_maintenance_service.py`
- `.trellis/spec/backend/rp-memory-visibility-overview.md`
- `.trellis/spec/backend/rp-shared-core-mutation-kernel-direct-edit.md`

What the repo already has:

1. read-side Core/Projection inspection already exists in service/controller form.
2. block-addressed governed mutation already exists for authoritative Core blocks.
3. proposal/apply and retrieval maintenance already give real mutation backbones for Core and retrieval-backed layers.

What is still missing:

1. one stable branch-aware inspection query across Core/Projection/Recall/Archival/Workspace;
2. user-visible Recall lifecycle actions;
3. user-visible Archival evolution actions;
4. strict reuse of the shared governed mutation kernel when product says “direct edit”.

## 2. Reuse Decision

Keep and extend:

- `MemoryInspectionReadService` as the seed for inspection reads;
- existing `/memory/*` route family as the likely outward API namespace;
- block-addressed governed mutation for Core;
- retrieval maintenance and later archival evolution services for retrieval-backed changes.

Do not add:

- a raw user-only Core write path;
- separate UI-only business logic that bypasses backend lifecycle services;
- a monolithic “edit anything” mutation endpoint that hides layer differences.

Why:

- current services already express the right ownership split;
- the missing work is widening them into branch-aware, layer-specific user-visible contracts.

## 3. Mature Wheel / Framework Decision

No external admin framework or generic CRUD layer is appropriate here.

Reason:

- the required behavior is governed, layer-specific, branch-aware correction;
- generic CRUD would erase the distinction between Core truth, Recall history, and Archival source material.

## 4. Spec Consequences

The inspection/edit backend spec should:

1. keep separate commands for Core direct edit, Recall review actions, and Archival evolution;
2. require branch-aware inspection queries that respect active visibility;
3. route Core edits through the shared mutation kernel;
4. route Recall and Archival actions through their own lifecycle/governance services;
5. reuse the existing memory route family instead of inventing an unrelated API namespace.

## 5. Rejected Alternatives

Rejected: expose current read services only and let the frontend improvise write flows.

- That would recreate mutation policy on the client.
- It would also make traceability and branch visibility inconsistent across products.

Rejected: collapse Recall and Archival corrections into the same generic action.

- Their truth model and physical storage responsibilities differ.
- They need separate governance paths even if they share inspection surfaces.
