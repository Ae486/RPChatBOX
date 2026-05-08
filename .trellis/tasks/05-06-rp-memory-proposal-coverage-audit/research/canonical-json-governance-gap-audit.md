# Canonical JSON Governance Gap Audit

> Date: 2026-05-06
>
> Task: `.trellis/tasks/05-06-rp-memory-proposal-coverage-audit`

## 1. Audit Question

Does the archived memory task already cover every requirement from the blocker
proposal and related memory/runtime docs?

## 2. Coverage Result

The archived task already covers:

- blocker proposal runtime boot bar;
- blocker proposal full runtime foundation bar A-K slices;
- related story-runtime branch/identity/profile/visibility principles that were
  folded into those slices.

The remaining uncovered requirement is from related docs, not from the main A-K
slice list:

- `UI canonical JSON governance`

## 3. Evidence

Covered by archived task:

- `.trellis/tasks/archive/2026-05/04-25-rp-memory-block-planning-dev/prd.md`
  contains explicit completion blocks for:
  - Runtime Boot Bar Implementation Complete
  - Recall Branch-Aware Lifecycle Complete
  - Archival Evolution Reindex Governance Complete
  - Memory Event Debug Eval Read Surfaces Complete
  - Registry Profile Snapshot Full Management Complete
  - User-Visible Memory Inspection Edit Backend Contracts Complete

Uncovered related-doc requirement:

- `.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-strengthening-proposal.md`
  section `10.8 UI Editable Canonical JSON Governance`
- same file also elevates `UI canonical JSON governance` into the resulting
  memory-dev priorities and acceptance criteria
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-architecture-question-queue.md`
  confirms that memory DSL / canonical JSON block format must be the shared
  format for both UI editing and worker writes

Current implementation gap:

- `backend/rp/services/memory_inspection_service.py` exposes branch-aware
  inspection and governed action routing, but the payload stays an ad hoc layer
  aggregation rather than one canonical block/entry envelope
- `.trellis/spec/backend/rp-user-visible-memory-inspection-edit-backend-contracts.md`
  defines branch-aware inspection and governed action routes, but does not yet
  freeze the canonical JSON block/entry shape itself

## 4. Consequence

The memory layer is not functionally missing major runtime foundations anymore,
but it is still missing one contract needed before the user-visible memory UI
and worker-governance traces can rely on the same stable envelope.

## 5. Follow-Up Slice

Recommended follow-up slice:

- add one backend spec for canonical user-visible memory block/entry JSON
  governance
- adapt `MemoryInspectionService` and related routes/tests to emit or confirm
  that stable envelope
- keep all existing Core/Recall/Archival governance paths intact

