# S3f Implementation Result

Status: functional closing gate passed with residual service-size debt
Date: 2026-06-23

## Scope Completed

S3f adds a deterministic end-to-end gate for the S3 memory-maintenance path.
The gate proves the S3a-S3e pieces work together from the public story turn
post-write entrypoint:

```text
StoryTurnDomainService.trigger_post_write()
  -> orchestrator-selected LongformMemoryWorker
  -> fake executor consumes selected worker plan
  -> MemoryMaintenanceWorkerAdapter structured output
  -> PostWriteGovernanceService.dispatch_worker_results()
  -> ProposalWorkflowService routes review/direct apply
  -> ProposalApplyService performs the only Core truth mutation
  -> RuntimeMaintenanceLockService exposes/clears review blockers
```

No production code was changed in S3f. The only implementation file is a new
backend integration/service test.

## Code Added Or Changed

- `backend/tests/test_story_runtime_s3_memory_worker_e2e.py`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/S3f-fresh-review-brief.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/S3f-fresh-review-output.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/S3f-check-record.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/17-S3f-implementation-result.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/worklog.md`

## Implemented Test Behavior

The new S3f test file covers four connected scenarios:

- `review_required`
  - enters through `trigger_post_write()`;
  - scheduler/orchestrator selects `LongformMemoryWorker`;
  - fake executor records the selected worker request and calls
    `MemoryMaintenanceWorkerAdapter`;
  - proposal governance job completes;
  - proposal is persisted as `review_required`;
  - no apply receipt exists before accept;
  - current-branch lock is active while review is pending;
  - manual proposal apply goes through `ProposalApplyService`;
  - Core compatibility mirror mutates only after apply;
  - lock clears after terminal apply.

- `direct_apply_allowed`
  - enters through the same post-write path;
  - proposal governance job completes;
  - proposal routes through governed apply;
  - apply receipt exists with revision advance;
  - Core compatibility mirror contains the appended active thread;
  - no review lock remains.

- `adapter_failure`
  - invalid structured worker output returns `WorkerResultStatus.FAILED`;
  - no proposal candidate is emitted;
  - no proposal job/proposal/apply receipt is created;
  - Core compatibility mirror remains unchanged;
  - current-branch lock remains inactive.

- `governance_handoff_failure`
  - adapter emits a completed WorkerResult with an invalid S3 candidate handoff;
  - public governance dispatch creates a proposal job and marks it failed;
  - stable reason code is `memory_candidate_base_revision_unparseable`;
  - no proposal/apply receipt is created;
  - Core compatibility mirror remains unchanged;
  - current-branch lock remains inactive.

Observable assertions include scheduler maintenance gate status, proposal
governance job status, proposal/apply receipts, lock state, selected worker
request/packet evidence, and Core compatibility state.

## Review

Fresh read-only review session:

```text
019ef1b7-663a-7dc0-8ff3-3b69a9aace33
```

Review verdict:

```text
PASS_WITH_CONCERNS
```

Main-brain adjudication:

- Accepted the success-path governance job observability finding. Added
  `_assert_proposal_job_completed()` and called it from both success tests.
- Accepted the adapter-failure lock-state finding. Added an explicit inactive
  lock assertion for adapter failure.
- Deferred the production executor migration finding as an expected residual
  gap, and recorded it below.

The reviewer attempted YCE but hit `spawn EPERM` inside its read-only
environment. It used the paths pre-fed in the review brief and did not use ACE.
Main-brain had already run YCE successfully for S3f planning and code
localization.

## Verification

Focused S3f command from `H:\chatboxapp\backend`:

```powershell
python -m pytest tests/test_story_runtime_s3_memory_worker_e2e.py
```

Result after review fixes:

```text
4 passed, 5 warnings
```

S3b/S3c regression command:

```powershell
python -m pytest rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
```

Result:

```text
15 passed, 1 warning
```

S3d/S2b regression command:

```powershell
python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py
```

Result:

```text
29 passed, 1 warning
```

Focused ruff command before review:

```powershell
python -m ruff check tests/test_story_runtime_s3_memory_worker_e2e.py rp/services/writer/memory_maintenance_worker_adapter.py rp/services/proposal/post_write_governance_service.py rp/services/proposal/memory_candidate_proposal_adapter.py
```

Result:

```text
All checks passed!
```

Focused ruff command after review fixes:

```powershell
python -m ruff check tests/test_story_runtime_s3_memory_worker_e2e.py
```

Result:

```text
All checks passed!
```

Diff whitespace check:

```powershell
git diff --check -- backend/tests/test_story_runtime_s3_memory_worker_e2e.py .trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3
```

Result:

```text
PASS
```

Service-size command:

```powershell
python backend/rp/devtools/check_service_sizes.py
```

Result:

```text
FAIL
```

The service-size failure is residual debt, not a new S3f production-code
offender. It reports:

- baseline drift in `story/runtime_identity_service.py`;
- baseline drift in `story/turn_domain_service.py`;
- already-committed S3a/S3b/S3c hard function offenders:
  - `memory/memory_candidate_validation_service.py::_validate_operation`;
  - `proposal/post_write_governance_service.py::_dispatch_proposal_governance`;
  - `writer/memory_maintenance_worker_adapter.py::_candidate_batch_result`.

## Residual Gaps

Production LongformMemoryWorker execution still uses the legacy specialist
adapter. S3f deterministic gate proves the selected-worker-to-governance
contract through a test execution seam, not full production executor migration.

Current-branch S3 maintenance blocker path is closed. Branch delete remains
deferred to a later branch/audit policy slice.

Service-size remains red and must be handled as the next engineering cleanup
slice before later S4/S5/S6 work normalizes the oversized story/proposal/writer
functions as permanent structure.

S3f did not add frontend lock UX, Recall lifecycle lock policy, branch delete
policy, or live-provider smoke tests.
