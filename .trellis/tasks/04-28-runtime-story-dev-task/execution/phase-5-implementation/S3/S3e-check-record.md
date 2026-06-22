# S3e Check Record

Date: 2026-06-23
Reviewer: Codex exec read-only review / main-brain adjudication
Scope: S3e maintenance lock entrypoint wiring

## Inputs Read

- `execution/phase-5-implementation/S3/14-S3e-implementation-brief.md`
- `execution/phase-5-implementation/S3/13-S3d-implementation-result.md`
- `execution/phase-5-implementation/S3/S3d-check-record.md`
- `.trellis/spec/backend/rp-services-organization-contract.md`
- `.trellis/spec/backend/rp-runtime-identity-persistence-propagation.md`
- `.trellis/spec/backend/rp-branch-visibility-resolver-lineage.md`
- `.trellis/spec/backend/rp-user-visible-memory-inspection-edit-backend-contracts.md`
- `.trellis/spec/backend/rp-shared-core-mutation-kernel-direct-edit.md`
- changed S3e code and tests listed in `15-S3e-implementation-result.md`

YCE note:

- Main-brain ran YCE before code edits for S3e entrypoint wiring:
  `RuntimeMaintenanceLockService`, `StoryGraphNodes.validate_command`,
  `StoryTurnDomainService`, `StoryRuntimeController`, `RpRuntimeFactory`,
  `api/rp_story.py`, and related tests.
- No ACE search was used.

## Review Findings

Independent read-only Codex review session:

```text
019ef18d-3a56-7a11-9479-fd2fe19e5b0d
```

Reviewer findings:

1. Branch delete remains unguarded while locked.
2. Proposal apply needed a direct "allowed while locked" contract test.

Main-brain adjudication:

- Branch delete is not accepted as a S3e blocker. The S3e brief explicitly
  defers branch delete policy. S3e guards only branch create, branch switch,
  and rollback. Branch delete remains a later policy decision because delete
  semantics need separate lineage/audit treatment.
- Accepted the proposal-apply test gap. The API proposal detail/apply test now
  seeds a branch-identified review-required proposal, asserts the current branch
  lock is active before apply, applies through the proposal route, and asserts
  the lock clears after apply.
- Confirmed that `apply_memory_block_proposal()` remains unguarded by S3e.

## Scope Discipline

- No LLM permission layer was added.
- No setup-agent path was changed.
- No prompt/harness policy was used to enforce the lock.
- The lock guard is implemented as a small service-layer guard and controller
  wrapper instead of adding more code to oversized story services.
- `StoryTurnDomainService` and `StoryRuntimeController` were intentionally not
  expanded after the service-size check showed that doing so would worsen the
  hard baseline.

## Verification

Focused graph/controller/API S3e commands run from `H:\chatboxapp\backend`:

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

Focused lint command:

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

The remaining service-size failure is not introduced by S3e. It reports
pre-existing baseline drift in `story/runtime_identity_service.py` and
`story/turn_domain_service.py`, plus already-committed S3a/S3b/S3c function
offenders.

Final main-brain rerun before commit:

```powershell
python -m pytest rp/tests/services/story/test_story_runtime_product_wiring_writer_constraints.py rp/tests/services/story/test_story_runtime_controller_memory_read_side.py ../backend/tests/test_rp_story_api.py -k "locked_current_branch_commands or blocks_branch_controls_when_locked or blocks_memory_mutations_when_locked or maintenance_lock_to_409 or proposal_detail_and_apply"
python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py rp/tests/services/runtime/test_s1core_settlement_matrix.py rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py
python -m ruff check api/rp_story.py rp/graphs/story_graph_nodes.py rp/runtime/rp_runtime_factory.py rp/services/story/command_policy.py rp/services/story/maintenance_guard_service.py rp/services/story/maintenance_guarded_runtime_controller.py rp/tests/services/story/test_story_runtime_product_wiring_writer_constraints.py rp/tests/services/story/test_story_runtime_controller_memory_read_side.py tests/test_rp_story_api.py
python backend/rp/devtools/check_service_sizes.py
```

Results:

```text
9 passed, 64 deselected, 17 warnings
39 passed, 1 warning
ruff: All checks passed!
service-size: FAIL on existing baseline/function debt listed above
```

## Residual Risks

- Branch delete lock policy remains deferred.
- Full `test_story_runtime_product_wiring_writer_constraints.py` still has
  existing `turn_in_flight` failures outside the S3e selector. The first failure
  occurs before the S3e locked-command test, so it is recorded as existing
  suite debt rather than S3e behavior.
- Service-size baseline remains red until the S3a-S3c/story-service debt is
  addressed.
