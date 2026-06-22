# S3e Implementation Brief - Maintenance Lock Entrypoint Wiring

Status: ready for implementation
Date: 2026-06-23

## Mission

Wire the S3d deterministic maintenance lock into the first real backend
entrypoints that can mutate story progress or branch/runtime memory state:

```text
S3d lock read model
  -> service-layer operation guard
  -> story turn / branch / memory edit entrypoints
  -> API-visible stable maintenance_in_progress errors
```

S3e must prove that the lock is no longer only a standalone read model. It must
affect real runtime operations without moving policy into prompts, harness code,
or API-only checks.

## Required Reading

- `execution/phase-5-implementation/S3/12-S3d-implementation-brief.md`
- `execution/phase-5-implementation/S3/13-S3d-implementation-result.md`
- `execution/phase-5-implementation/S3/S3d-check-record.md`
- `research/modules/runtime-scheduler-governance.md`
- `research/modules/runtime-turn-intake-settlement.md`
- `research/story-runtime-maintenance-lock-and-kx-window-analysis.md`
- `.trellis/spec/backend/rp-services-organization-contract.md`
- `.trellis/spec/backend/rp-runtime-identity-persistence-propagation.md`
- `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md`

Use YCE for codebase search. Do not use ACE.

## Current Code Evidence

YCE and direct file reads identified these entrypoints:

- `backend/rp/graphs/story_graph_nodes.py`
  - `pin_runtime_identity()` resolves full runtime identity before command
    validation.
  - `validate_command()` runs before any graph mutation node.
- `backend/rp/services/story/turn_domain_service.py`
  - owns story turn domain logic and already receives runtime identity,
    workflow job, post-write scheduler, and worker services.
  - good service-layer location for story-turn guard logic.
- `backend/rp/services/story/runtime_controller.py`
  - owns branch create/switch/rollback, memory direct edit, Recall review,
    Archival evolution, brainstorm, and memory proposal apply surfaces.
  - good service-layer location for non-graph route guards.
- `backend/rp/runtime/rp_runtime_factory.py`
  - constructs both `StoryTurnDomainService` and `StoryRuntimeController`.
  - should inject `RuntimeMaintenanceLockService` from the shared DB session.
- `backend/api/rp_story.py`
  - should map `maintenance_in_progress` to a stable API error, but should not
    own the allow/block policy.

## Scope

### In scope

1. Inject `RuntimeMaintenanceLockService` into:
   - `StoryTurnDomainService`
   - `StoryRuntimeController`

2. Add service-layer guard helpers:
   - story turn command guard in `StoryTurnDomainService`
   - branch/memory guard in `StoryRuntimeController`

3. Map longform commands to maintenance operations:

| Command | Operation |
|---|---|
| `generate_outline` | `story_progression` |
| `discuss_outline` | `story_progression` |
| `accept_outline` | `story_progression` |
| `write_next_segment` | `story_progression` |
| `accept_pending_segment` | `story_progression` |
| `rewrite_pending_segment` | `rewrite` |
| `complete_chapter` | `chapter_complete` |

Important: `accept_pending_segment` is not memory proposal accept. It mutates
story progress and can trigger post-write maintenance, so it is blocked while
the current branch is under maintenance.

4. Guard these controller operations:

| Controller operation | Operation |
|---|---|
| `create_branch_from_turn` | `branch_create` |
| `switch_branch` | `branch_switch` |
| `rollback_to_turn` | `rollback` |
| `direct_edit_memory_block` | `core_memory_edit` |
| `direct_edit_core_memory` | `core_memory_edit` |
| `evolve_archival_memory` | `story_evolution_or_archival_edit` |

5. Keep these actions allowed:

- read/inspect/debug routes;
- `apply_memory_block_proposal()` because it is proposal accept / governed
  apply and must remain available to clear the lock;
- Recall review commands for this slice, because their current actions are not
  Core truth progression and need a separate Recall lifecycle policy pass;
- runtime config edit, matching S3d's allowed operation matrix.

6. Expose stable API error details for lock rejection:

```text
status_code = 409
code = maintenance_in_progress
message = maintenance_in_progress:<operation>
```

The API response should include enough cause metadata for clients/tests to
identify blocker source ids if the exception exposes them.

### Out of scope

- Full frontend lock banner / disabled controls.
- Proposal edit persistence or review UI.
- New branch delete policy.
- Recall lifecycle lock policy.
- Reworking `ProposalApplyService` or S3 proposal adapter.
- Moving the lock decision into LangGraph prompt/harness or LLM permission
  logic.
- Fixing global service-size failures from earlier slices.

## Design Notes

The guard belongs in the service layer:

- Graph/API shells may call it, but they do not decide policy.
- `StoryGraphNodes.validate_command()` is the right graph insertion point
  because `pin_runtime_identity()` already ran and mutation nodes have not run.
- Controller methods should use the active session branch for branch operations,
  and request identity for memory operations when the request carries a
  `MemoryRuntimeIdentity`.

For branch create/switch/rollback, evaluate the lock against the currently
active branch before changing branch state. This preserves the S3d "current
branch blocker" contract.

## Tests Required

Add focused tests before/with implementation:

- A locked current branch rejects `write_next_segment` / `accept_pending_segment`
  / `complete_chapter` through story graph validation before mutation.
- A locked current branch rejects branch create/switch/rollback through
  `StoryRuntimeController`.
- A locked current branch rejects Core direct edit and Archival evolution.
- `apply_memory_block_proposal()` remains allowed while locked and can clear a
  review-required blocker through governed apply.
- API error mapping returns `409` and `maintenance_in_progress`.

Preferred focused command set:

```powershell
python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py
python -m pytest rp/tests/services/proposal/test_memory_candidate_governance_routing.py
python -m pytest ../tests/test_rp_story_api.py -k "maintenance_lock or proposal_detail_and_apply"
```

Broader S3e gate should also include:

```powershell
python -m pytest rp/tests/services/runtime/test_s1core_settlement_matrix.py rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py
```

## Expected Output

- files changed;
- exact entrypoints guarded;
- exact operations still allowed;
- exact tests run and results;
- any deviations from this brief;
- remaining risks for next S3/S4 work.
