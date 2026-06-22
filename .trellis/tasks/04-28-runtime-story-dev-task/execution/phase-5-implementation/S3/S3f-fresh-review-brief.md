# S3f Fresh Review Brief

Status: ready for read-only review
Date: 2026-06-23

## Role

You are a fresh read-only reviewer for S3f. Do not edit files. Do not commit.

Use YCE for codebase search if you need to discover code. Do not use ACE. The
main-brain has already provided the relevant paths below, so prefer reading the
listed files directly over broad searches.

## Scope To Review

S3f is a closing gate for S3. It should prove the connected runtime path:

```text
accepted source material / post-write trigger
  -> orchestrator-selected LongformMemoryWorker
  -> MemoryMaintenanceWorkerAdapter structured output
  -> PostWriteGovernanceService.dispatch_worker_results()
  -> ProposalWorkflowService review/direct routing
  -> ProposalApplyService as the only truth mutation path
  -> RuntimeMaintenanceLockService pending-review lock and terminal clear
```

This is not a production executor migration slice. If production
`WorkerExecutionService` still uses the legacy specialist adapter, that must be
recorded as a residual gap, not hidden.

## Files To Read

Authoritative planning/result docs:

- `.trellis/tasks/04-28-runtime-story-dev-task/research/index.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-worker-family.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-scheduler-governance.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-agent-harness.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/16-S3f-closing-gate-brief.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/S3f-planning-review-record.md`

Implementation under review:

- `backend/tests/test_story_runtime_s3_memory_worker_e2e.py`

Supporting code paths:

- `backend/rp/services/story/turn_domain_service.py`
- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- `backend/rp/services/proposal/post_write_governance_service.py`
- `backend/rp/services/proposal/memory_candidate_proposal_adapter.py`
- `backend/rp/services/proposal/workflow_service.py`
- `backend/rp/services/proposal/apply_service.py`
- `backend/rp/services/runtime/maintenance_lock_service.py`
- `backend/rp/services/writer/worker_execution_service.py`

## Main-Brain Verification Already Run

From `H:\chatboxapp\backend`:

```text
python -m pytest tests/test_story_runtime_s3_memory_worker_e2e.py
=> 4 passed, 5 warnings

python -m pytest rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
=> 15 passed, 1 warning

python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py
=> 29 passed, 1 warning

python -m ruff check tests/test_story_runtime_s3_memory_worker_e2e.py rp/services/writer/memory_maintenance_worker_adapter.py rp/services/proposal/post_write_governance_service.py rp/services/proposal/memory_candidate_proposal_adapter.py
=> All checks passed
```

From `H:\chatboxapp`:

```text
python backend/rp/devtools/check_service_sizes.py
=> FAIL
```

The service-size failure is expected residual debt listed in
`16-S3f-closing-gate-brief.md`: baseline drift in oversized story services and
already-committed S3a/S3b/S3c hard function offenders. S3f should not introduce
new production service-size offenders because it only adds a backend test file.

## Questions To Answer

1. Does the new S3f test enter through
   `StoryTurnDomainService.trigger_post_write()` rather than the private
   `_dispatch_proposal_governance()`?
2. Does the fake executor consume the scheduler-selected
   `LongformMemoryWorker` before calling `MemoryMaintenanceWorkerAdapter`?
3. Are all required S3f scenarios covered:
   `review_required`, `direct_apply_allowed`, adapter failure, governance
   handoff failure?
4. Do assertions check observable state, not just call order:
   scheduler gate, proposal governance job, proposal/apply receipts, lock state,
   and Core compatibility mirror mutation timing?
5. Does any LLM/harness/worker output mutate truth directly?
6. Does proposal/apply remain the only truth mutation path?
7. Does the implementation avoid adding product policy to harness core or
   setup-agent paths?
8. Does it avoid overclaiming production `WorkerExecutionService` migration?
9. Are branch delete, Recall policy, frontend UX, and broad service-size refactor
   kept out of scope?
10. Are there any false-green risks or missing tests that should block the S3f
    commit?

## Expected Output

Return a concise review with:

```text
Verdict: PASS | PASS_WITH_CONCERNS | NO_GO

Findings:
- severity, file/path, exact issue, why it matters, suggested action

Adjudication Advice:
- what the main-brain should accept, reject, or defer
```
