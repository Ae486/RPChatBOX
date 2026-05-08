# RP Memory Proposal Coverage Audit And Completion Follow-Up

## Goal

Audit the archived `rp-memory-block-planning-dev` delivery against
`.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-story-runtime-blockers-dev-proposal.md`
and related memory/runtime design notes, then complete any still-uncovered
requirement through the normal Trellis spec -> implement -> check loop.

## What I Already Know

- The archived task
  `.trellis/tasks/archive/2026-05/04-25-rp-memory-block-planning-dev/prd.md`
  records all runtime boot bar slices complete and all planned full-foundation
  slices complete.
- The blocker proposal defines the main memory target as:
  - runtime boot bar;
  - full runtime foundation bar;
  - slices `A` through `K`;
  - P0/P1 rows as the full runtime foundation bar.
- The archived task status blocks confirm completion for:
  - Runtime Boot Bar Implementation;
  - Recall Branch-Aware Lifecycle;
  - Archival Evolution Reindex Governance;
  - Memory Event Debug Eval Read Surfaces;
  - Registry Profile Snapshot Full Management;
  - User-Visible Memory Inspection Edit Backend Contracts.
- The related proposal
  `.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-strengthening-proposal.md`
  adds an extra requirement not fully absorbed by the archived A-K delivery:
  `UI canonical JSON governance`.
- The current inspection/edit backend contract exposes branch-aware inspection
  and governed actions, but it does not yet freeze one canonical block/entry
  envelope with:
  - editable fields;
  - validation summary;
  - allowed actions;
  - entry-level base revision/conflict state;
  - a shared shape for UI editing and worker proposal trace.

## Audit Conclusion

Current coverage result:

- `runtime boot bar`: covered.
- `full runtime foundation bar` A-K slices: covered.
- related-doc supplemental requirement `UI canonical JSON governance`: not yet
  fully covered.

Therefore this follow-up task is not a re-open of the whole memory rollout.
It is one narrow completion slice to absorb the remaining canonical
user-visible memory envelope contract into the backend spec/implementation.

## Requirements

- Prove the archived task already covers blocker proposal P0/P1 and slices A-K.
- Add one explicit backend spec for user-visible canonical memory block/entry
  JSON governance.
- Bind that canonical envelope to the existing governed inspection/edit backend
  rather than inventing a second memory editor contract.
- Keep the shared `/memory/*` route family and existing governance boundaries:
  - Core direct edit through shared mutation kernel;
  - Recall review through lifecycle service;
  - Archival edit through evolution/reindex governance.
- Add or adjust implementation so inspection payloads can serve as the stable
  UI/worker-governance envelope where required by the proposal.

## Acceptance Criteria

- [x] Archived task coverage of blocker proposal A-K and P0/P1 is explicitly
  documented.
- [x] One backend spec freezes canonical block/entry envelope requirements for
  user-visible memory.
- [x] Implementation exposes or adapts a canonical inspection/edit envelope that
  includes block metadata, stable entry ids, editable fields, validation
  summary/errors, permission level, lifecycle, source/provenance, revision/base
  revision, conflict state, and allowed actions where applicable.
- [x] Focused tests cover Core / Recall / Archival envelope behavior and prove
  UI editing and governed backend actions use the same canonical shape.
- [x] trellis-check passes for this follow-up slice.

## Out Of Scope

- Re-auditing or rewriting already completed boot/full-foundation slices.
- New story runtime worker orchestration.
- Full UI polish or frontend redesign.
- Broad repo-wide regression unrelated to the slice.

## Technical Notes

- Archived task source of truth:
  `.trellis/tasks/archive/2026-05/04-25-rp-memory-block-planning-dev/prd.md`
- Coverage driver docs:
  - `.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-story-runtime-blockers-dev-proposal.md`
  - `.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-strengthening-proposal.md`
  - `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-architecture-question-queue.md`
- Existing likely implementation anchors:
  - `backend/rp/models/memory_inspection.py`
  - `backend/rp/services/memory_inspection_service.py`
  - `backend/api/rp_story.py`
  - `.trellis/spec/backend/rp-user-visible-memory-inspection-edit-backend-contracts.md`

## Status on 2026-05-06

Audit result:

- blocker proposal runtime boot bar: covered by the archived task;
- blocker proposal full runtime foundation bar A-K: covered by the archived
  task;
- related-doc supplemental requirement `UI canonical JSON governance`: was not
  fully covered at task archive time, and is now completed by this follow-up
  slice.

Completed follow-up slice:

- added `.trellis/spec/backend/rp-user-visible-memory-canonical-json-governance.md`
  as the missing executable contract;
- updated backend spec index to register the new canonical-envelope contract and
  quality-check expectations;
- `MemoryInspectionService.inspect_visible_memory()` now returns a
  backend-owned canonical `blocks` envelope plus `canonical_envelope` metadata,
  while preserving old `layers` for compatibility;
- canonical block/entry payloads now expose stable ids, editable/action
  metadata, revision/base revision, permission, lifecycle, source/provenance,
  validation, and governed entrypoints across Core / Recall / Archival /
  Runtime Workspace;
- focused tests and trellis-check passed for this follow-up slice.

Verification:

- `python -m pytest backend/rp/tests/test_memory_inspection_service.py backend/tests/test_rp_story_api.py -q -k "memory_inspection or story_memory"`
  - result: `12 passed, 12 deselected`
- `python -m pytest backend/rp/tests/test_memory_inspection_service.py -q`
  - result: `4 passed`
- `python -m ruff check backend/rp/models/memory_inspection.py backend/rp/services/memory_inspection_service.py backend/rp/tests/test_memory_inspection_service.py backend/tests/test_rp_story_api.py`
- `python -m ruff format --check backend/rp/models/memory_inspection.py backend/rp/services/memory_inspection_service.py backend/rp/tests/test_memory_inspection_service.py backend/tests/test_rp_story_api.py`
- `python -m mypy --follow-imports=skip --check-untyped-defs backend/rp/models/memory_inspection.py backend/rp/services/memory_inspection_service.py backend/rp/tests/test_memory_inspection_service.py backend/tests/test_rp_story_api.py`
- `gpt-5.4 xhigh` trellis-check result:
  - no new slice-local defects after focused inspection;
  - noted only that full-repo mypy still expands into pre-existing unrelated
    repository errors, while slice-scoped mypy is green.

Final conclusion:

- Against `.trellis/tasks/04-28-runtime-story-dev-task/research/memory-layer-story-runtime-blockers-dev-proposal.md`,
  all P0/P1 rows and A-K slices are already covered.
- Against related memory/runtime docs, the only real uncovered requirement was
  `UI canonical JSON governance`, and it is now covered as well.
- There is no additional uncovered requirement left in this audit scope.
