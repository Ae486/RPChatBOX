# S3e Implementation Result

Status: gate passed with residual service-size debt
Date: 2026-06-23

## Scope Completed

S3e wired the S3d runtime maintenance lock into real backend entrypoints:

- story graph command validation now checks the current-branch maintenance
  lock before mutating story progress;
- branch create, branch switch, rollback, direct Core memory edit, and Archival
  evolution are guarded through a service-layer controller wrapper;
- API lock rejection is mapped to stable `409 maintenance_in_progress` output;
- proposal detail/apply remains available while locked, so a review-required
  blocker can still be accepted or rejected and clear the lock;
- the lock decision remains outside prompts, harness code, setup-agent logic,
  and LLM permission policy.

The slice deliberately used small guard components instead of adding more code
to already oversized story services.

## Code Added Or Changed

- `backend/api/rp_story.py`
- `backend/rp/graphs/story_graph_nodes.py`
- `backend/rp/runtime/rp_runtime_factory.py`
- `backend/rp/services/story/command_policy.py`
- `backend/rp/services/story/maintenance_guard_service.py`
- `backend/rp/services/story/maintenance_guarded_runtime_controller.py`
- `backend/rp/tests/services/story/test_story_runtime_product_wiring_writer_constraints.py`
- `backend/rp/tests/services/story/test_story_runtime_controller_memory_read_side.py`
- `backend/tests/test_rp_story_api.py`

## Implemented Behavior

Story graph command guard:

- `generate_outline`, `discuss_outline`, `accept_outline`,
  `write_next_segment`, and `accept_pending_segment` map to
  `story_progression`;
- `rewrite_pending_segment` maps to `rewrite`;
- `complete_chapter` maps to `chapter_complete`;
- locked current branch commands fail during validation before mutation nodes.

Controller guard:

- `create_branch_from_turn` maps to `branch_create`;
- `switch_branch` maps to `branch_switch`;
- `rollback_to_turn` maps to `rollback`;
- `direct_edit_memory_block` and `direct_edit_core_memory` map to
  `core_memory_edit`;
- `evolve_archival_memory` maps to `story_evolution_or_archival_edit`.

Allowed while locked:

- read/inspect/debug flows;
- proposal detail and governed proposal apply;
- `apply_memory_block_proposal()`;
- Recall review and runtime config edit remain outside this S3e policy slice,
  matching `14-S3e-implementation-brief.md`.

API behavior:

```text
status_code = 409
code = maintenance_in_progress
message = maintenance_in_progress:<operation>
```

When available, blocker metadata is surfaced in the error details so clients
and tests can identify the lock cause.

## Review

Fresh check record:

- `execution/phase-5-implementation/S3/S3e-check-record.md`

Independent read-only review session:

```text
019ef18d-3a56-7a11-9479-fd2fe19e5b0d
```

Reviewer findings and adjudication:

- Branch delete remains unguarded. Main-brain did not accept this as a S3e
  blocker because branch delete policy was explicitly out of scope in the S3e
  brief and needs separate lineage/audit treatment.
- Proposal apply needed direct locked-branch contract coverage. Main-brain
  accepted this finding and added API coverage that asserts the branch is
  locked before proposal apply and unlocked after governed apply.

## Verification

Focused graph/controller/API commands run from `H:\chatboxapp\backend`:

```powershell
python -m pytest rp/tests/services/story/test_story_runtime_product_wiring_writer_constraints.py -k locked_current_branch_commands
python -m pytest rp/tests/services/story/test_story_runtime_controller_memory_read_side.py -k "blocks_branch_controls_when_locked or blocks_memory_mutations_when_locked"
python -m pytest ../backend/tests/test_rp_story_api.py -k "maintenance_lock_to_409 or proposal_detail_and_apply"
```

Results:

```text
4 passed, 14 deselected, 1 warning
2 passed, 14 deselected, 1 warning
3 passed, 36 deselected, 17 warnings
```

S3d/S3c and S1/S2 regression commands:

```powershell
python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
python -m pytest rp/tests/services/runtime/test_s1core_settlement_matrix.py rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py
```

Results:

```text
22 passed, 1 warning
17 passed, 1 warning
```

Focused ruff command:

```powershell
python -m ruff check api/rp_story.py rp/graphs/story_graph_nodes.py rp/runtime/rp_runtime_factory.py rp/services/story/command_policy.py rp/services/story/maintenance_guard_service.py rp/services/story/maintenance_guarded_runtime_controller.py rp/tests/services/story/test_story_runtime_product_wiring_writer_constraints.py rp/tests/services/story/test_story_runtime_controller_memory_read_side.py tests/test_rp_story_api.py
```

Result:

```text
All checks passed!
```

Service-size command:

```powershell
python backend/rp/devtools/check_service_sizes.py
```

Result:

```text
FAIL
```

The remaining service-size failure is residual project debt, not a new S3e
offender. It reports pre-existing baseline drift in
`story/runtime_identity_service.py` and `story/turn_domain_service.py`, plus
already-committed S3a/S3b/S3c hard function offenders.

Final main-brain rerun before commit:

```text
S3e focused selector: 9 passed, 64 deselected, 17 warnings
S3d/S3c/S1/S2 regression set: 39 passed, 1 warning
ruff: All checks passed!
service-size: FAIL on the residual debt described above
```

## Deviations From Brief

The S3e brief named `StoryTurnDomainService` and `StoryRuntimeController` as
likely injection points. During implementation, expanding those classes made
the service-size problem worse. The final design keeps lock policy in the
service layer but isolates it in:

- `StoryRuntimeMaintenanceGuardService`;
- `MaintenanceGuardedStoryRuntimeController`;
- `StoryGraphNodes.validate_command()` injection.

This preserves the intended entrypoint behavior while avoiding more code in
large story services.

## Remaining Work

- Decide branch delete lock policy in a later branch/audit slice.
- Fix the broader service-size baseline before later S3/S4 work depends on
  oversized story services.
- Run a separate Recall lifecycle policy pass before treating Recall review
  actions as locked or unlocked.
- Continue frontend/API UX work for lock display and disabled controls after
  backend contract stabilization.
