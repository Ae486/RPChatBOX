# Core State Base Revision Conflict Enforcement Slice Plan

> Date: 2026-05-04
>
> Task: `.trellis/tasks/04-25-rp-memory-block-planning-dev`
>
> Depends on:
> - `.trellis/spec/backend/rp-core-state-base-revision-conflict-enforcement.md`
> - `.trellis/spec/backend/rp-authoritative-block-governed-mutation.md`
> - `.trellis/spec/backend/rp-authoritative-block-proposal-review-apply-visibility.md`
> - `backend/rp/services/proposal_apply_service.py`
> - `backend/rp/services/proposal_repository.py`
> - `backend/rp/services/core_state_dual_write_service.py`

## Slice

Implement the next memory governance slice:

```text
Core State base revision conflict enforcement
  + apply-side stale revision validation
  + missing base revision rejection
  + fail-closed status transition on conflict
  + regression coverage for stale and matching proposals
```

## Why This Slice Now

The memory stack already persists authoritative proposals and apply receipts, but stale proposals can still flow through the apply path without an explicit revision guard. The prior slices established identity, materialization, and trace infrastructure; this slice closes the first hard governance gap before worker/user conflict handling grows more complex.

## Implementation Plan

1. Add backend spec:
   - `.trellis/spec/backend/rp-core-state-base-revision-conflict-enforcement.md`
   - Register it in `.trellis/spec/backend/index.md`.
2. Add apply-side validation:
   - `backend/rp/services/proposal_apply_service.py`
   - Add a helper that resolves each authoritative target's current revision from the same source already used by the apply path.
   - Compare matching `base_refs` against that current revision before mutation.
   - Reject missing base revision data and stale matches with stable `phase_e_apply_base_revision_*` errors.
3. Preserve current behavior:
   - proposals with no `base_refs` continue to use the existing legacy path in this slice;
   - already-applied proposals keep their idempotent reapply behavior;
   - no direct write path changes outside the apply service.
4. Add focused tests:
   - one regression proving a stale base revision fails closed and leaves no apply receipt;
   - one positive test proving a matching base revision still applies;
   - optionally one test for missing revision on a supplied base ref.
5. Keep scope bounded:
   - no new revision store;
   - no new merge policy;
   - no projection refresh semantics;
   - no user-edit apply path yet;
   - no public tool widening.

## Verification

Run at minimum:

```powershell
pytest backend\rp\tests\test_proposal_workflow_service.py backend\tests\test_rp_story_api.py -q
ruff check backend\rp\services\proposal_apply_service.py backend\rp\tests\test_proposal_workflow_service.py backend\tests\test_rp_story_api.py
ruff format --check backend\rp\services\proposal_apply_service.py backend\rp\tests\test_proposal_workflow_service.py backend\tests\test_rp_story_api.py
mypy --follow-imports=skip --check-untyped-defs backend\rp\services\proposal_apply_service.py backend\rp\tests\test_proposal_workflow_service.py backend\tests\test_rp_story_api.py
git diff --check
```

After implementation, run `trellis-check` before starting the next slice.
