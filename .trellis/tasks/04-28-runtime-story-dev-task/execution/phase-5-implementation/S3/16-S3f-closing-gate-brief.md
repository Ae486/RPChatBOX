# S3f Closing Gate Brief - End-To-End Memory Maintenance Path

Status: ready for implementation after assistant review
Date: 2026-06-23

## Mission

Close S3 by proving that the pieces implemented in S3a-S3e work as one runtime
path, not only as separate contract/service tests.

The required S3 product chain is:

```text
accepted source material / post-write trigger
  -> orchestrator or deterministic scheduler selects LongformMemoryWorker
  -> MemoryMaintenanceWorker adapter produces structured candidate / no-op / failure
  -> PostWriteGovernanceService ingests the WorkerResult
  -> ProposalWorkflowService routes review-required or direct-apply
  -> ProposalApplyService is the only truth mutation path
  -> RuntimeMaintenanceLockService exposes blockers while review is pending
  -> proposal accept/apply clears the blocker
```

S3f is a closing gate. It must not add new product semantics just to make a
test pass. If the current implementation cannot connect the chain honestly,
record the gap and implement the smallest missing wiring in a separate helper
or adapter, not inside oversized story services.

Important boundary:

- If S3f does not change production `WorkerExecutionService`, the S3f result
  must explicitly say so. In that case S3f proves the selected-worker to
  governance/apply contract through a deterministic test execution seam; it does
  not prove that the production `LongformMemoryWorker` executor has fully moved
  from the legacy specialist adapter to `MemoryMaintenanceWorkerAdapter`.

## Source Authority

Primary requirement sources:

- `research/index.md`
- `research/modules/runtime-worker-family.md`
- `research/modules/runtime-scheduler-governance.md`
- `research/modules/runtime-agent-harness.md`
- `research/modules/runtime-workspace-ledger-trace.md`
- `execution/phase-3-slicing/slice-plan.md`
- `execution/phase-5-implementation/S3/01-PRD.md`
- `execution/phase-5-implementation/S3/02-SDD-and-implementation-plan.md`
- `execution/phase-5-implementation/S3/03-test-and-gate-plan.md`
- `execution/main-brain/harness-gap-and-completion-plan.md`
- `execution/main-brain/operating-rules.md`

Current implementation evidence:

- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- `backend/rp/services/proposal/post_write_scheduler_service.py`
- `backend/rp/services/proposal/post_write_governance_service.py`
- `backend/rp/services/proposal/memory_candidate_proposal_adapter.py`
- `backend/rp/services/proposal/workflow_service.py`
- `backend/rp/services/proposal/apply_service.py`
- `backend/rp/services/runtime/maintenance_lock_service.py`
- `backend/rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py`
- `backend/rp/tests/services/writer/test_memory_maintenance_worker_adapter.py`
- `backend/rp/tests/services/proposal/test_memory_candidate_governance_routing.py`

YCE note:

- Main-brain used YCE for S3f planning search.
- No ACE search is allowed.

## Why This Slice Exists

The original S3 SDD described the final S3e as an end-to-end and review gate.
During implementation, S3e became the maintenance-lock entrypoint wiring slice.
That wiring was necessary, but it did not replace the final S3 closing gate.

Current test coverage proves many parts:

- S3b proves structured worker output maps to non-truth worker candidates.
- S3c proves S3 candidate handoff can create review-required proposals, direct
  apply proposals, invalid failure jobs, and stale-base apply failure.
- S3d proves the lock read model and stale-base behavior.
- S3e proves selected real mutation entrypoints reject while locked.
- S2b proves post-write scheduler/orchestrator gate behavior, but uses a fake
  governance service with empty dispatch.

The missing proof is the connected path:

```text
post-write trigger / scheduler-selected worker
  -> actual S3 worker adapter result
  -> actual governance/proposal/apply services
  -> lock/apply observable state
```

## In Scope

1. Add or update an integration/service test that connects S2b and S3c instead
   of calling only one layer directly.

2. The preferred test shape:

```text
seed story session + chapter + runtime profile snapshot
  -> seed post-write-ready turn and source material / retrieval usage trigger
  -> orchestrator proposal selects LongformMemoryWorker
  -> worker execution fake uses MemoryMaintenanceWorkerAdapter with scripted output
  -> real PostWriteGovernanceService receives the WorkerResult
  -> real ProposalWorkflowService / ProposalApplyService route it
```

Hard entrypoint rule:

- The main S3f connected test must enter through
  `StoryTurnDomainService.trigger_post_write()` when feasible.
- If that cannot be done without broad production refactor, the fallback entry
  must be public `PostWriteGovernanceService.dispatch_worker_results()`, with
  the missing `trigger_post_write()` seam recorded as a residual gap.
- The main S3f connected test must not use private
  `_dispatch_proposal_governance()` as its primary entrypoint. That is already
  covered by S3c and would not close the E2E gap.

Worker execution assertions:

- Verify the worker plan selects `LongformMemoryWorker`.
- Verify the test executor consumes the selected worker before calling
  `MemoryMaintenanceWorkerAdapter.execute()`.
- Assert adapter runner call count, worker id, phase, and `context_packet_ref`.

3. Required scenarios:

- `review_required`:
  - proposal is persisted as review-required;
  - no apply receipt is created before accept;
  - branch maintenance lock is active;
  - proposal accept/apply goes through governed apply;
  - lock clears after terminal apply.

- `direct_apply_allowed`:
  - proposal routes through governed apply;
  - apply receipt exists;
  - Core compatibility state reflects the deterministic mutation;
  - no review lock remains active.

- `adapter_failure`:
  - invalid structured worker output returns `WorkerResultStatus.FAILED`;
  - no proposal candidate is emitted;
  - no proposal/apply occurs;
  - no truth mutation occurs.

- `governance_handoff_failure`:
  - invalid S3 candidate handoff reaches governance with a proposal candidate;
  - no proposal/apply occurs;
  - the proposal governance job is terminal failed with a stable reason code;
  - no truth mutation occurs.

No-op coverage may remain in the S3b adapter test if the connected path would
only duplicate behavior. If adding no-op to the connected path is cheap and
does not expand production code, include it.

4. Confirm S3f does not depend on a live provider. Use fake/scripted worker
output. Optional DeepSeek smoke remains out of gate unless all deterministic
tests pass and the main-brain explicitly chooses to run it.

5. Run a fresh read-only review after implementation.

Observable assertions required across the scenarios:

- scheduler maintenance gate is terminal when the run uses the scheduler path;
- proposal governance job is completed or failed as appropriate;
- proposal status and apply receipts are asserted;
- maintenance lock is active while review-required proposal is pending;
- maintenance lock clears after terminal apply/reject/discard/failure;
- Core compatibility state mutates only after governed apply.

## Out Of Scope

- Branch delete lock policy.
- Physical purge of branch-owned materials.
- Recall lifecycle lock policy.
- Frontend lock banner / disabled controls.
- Full universal production executor replacement for writer/orchestrator/
  worker/brainstorm.
- Broad service-size refactor in the same slice.
- Expanding target domains beyond the current S3 adapter-supported target unless
  the test cannot honestly prove the path without it.

## Service-Size Rule

S3f must not make the service-size red state worse.

The current red state is known:

- `story/runtime_identity_service.py` and `story/turn_domain_service.py` exceed
  their existing baseline;
- S3a/S3b/S3c introduced hard function offenders in:
  - `memory/memory_candidate_validation_service.py::_validate_operation`;
  - `proposal/post_write_governance_service.py::_dispatch_proposal_governance`;
  - `writer/memory_maintenance_worker_adapter.py::_candidate_batch_result`.

S3f should be test-first or helper-only. If implementation needs new wiring,
prefer small adapter/helper components. Do not add more logic to:

- `StoryTurnDomainService`;
- `StoryRuntimeController`;
- `StoryRuntimeIdentityService`.

If the S3f gate cannot pass because one of those services must change, stop and
write a separate service-size remediation brief before touching production code.

## Branch Delete Decision

Branch delete remains deferred for S3f.

Reason:

- Current implementation has soft-delete/hidden branch semantics and API tests.
- S3 maintenance lock currently evaluates current-branch blockers.
- Deleting a non-current branch while another branch is locked requires a
  separate branch/audit decision about branch-owned workspace, candidates,
  pending jobs, materialization, and purge scope.

S3f may record this as remaining work, but it must not silently add or change
branch delete policy.

## Expected Implementation Files

Likely test additions:

- `backend/tests/test_story_runtime_s3_memory_worker_e2e.py`

Possible helper/test fixture additions only if needed:

- local test fakes inside the new test file;
- small helper under existing test helper modules if the setup is duplicated
  across S3 tests.

Production code changes should be zero unless the connected test exposes a real
missing adapter seam. If production changes are required, keep them narrowly
scoped and document the deviation.

If production `WorkerExecutionService` remains on the legacy specialist adapter
path, the S3f result record must include this residual gap verbatim:

```text
Production LongformMemoryWorker execution still uses the legacy specialist
adapter. S3f deterministic gate proves the selected-worker-to-governance
contract through a test execution seam, not full production executor migration.
```

## Verification Gate

Minimum focused commands from `H:\chatboxapp\backend`:

```powershell
python -m pytest tests/test_story_runtime_s3_memory_worker_e2e.py
python -m pytest rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py
python -m ruff check tests/test_story_runtime_s3_memory_worker_e2e.py rp/services/writer/memory_maintenance_worker_adapter.py rp/services/proposal/post_write_governance_service.py rp/services/proposal/memory_candidate_proposal_adapter.py
```

Service-size must be rerun and recorded:

```powershell
python backend/rp/devtools/check_service_sizes.py
```

Expected service-size result for this slice:

- PASS if the later remediation has already landed;
- otherwise FAIL only on the known pre-S3f debt listed above.

The S3f result record must not claim full S3 engineering cleanliness while
service-size remains red. It may claim the S3 runtime path is functionally
closed if the E2E tests pass and the red service-size items are explicitly
scheduled as the next engineering slice.

It also must not claim full branch lock policy. The strongest allowed wording is:

```text
Current-branch S3 maintenance blocker path is closed. Branch delete remains
deferred to a later branch/audit policy slice.
```

## Fresh Review Brief

The reviewer must check:

- Does S3f really connect scheduler-selected worker execution to governance and
  apply, or does it still call only one private layer?
- Does any LLM/harness/worker output mutate truth directly?
- Does proposal accept/apply remain the only truth mutation path?
- Does pending review-required proposal activate the current-branch lock, and
  does terminal apply clear it?
- Are branch delete, Recall policy, frontend UX, and broad service-size refactor
  kept out of scope?
- Did implementation avoid adding logic to oversized story services?
- Are tests asserting observable state/receipts rather than implementation call
  order only?

## Commit Discipline

Commit after the S3f implementation and review gate passes.

Stage only S3f-owned files. Continue to avoid unrelated existing changes:

- `.gitignore`
- `.trellis/.template-hashes.json`
- `backend/rp/services/story/runtime_controller.py`
- `backend/rp/services/story/turn_domain_service.py`
- `backend/rp/tests/services/writer/test_longform_chapter_runtime_service.py`
- `backend/services/conversation_source.py`
- `backend/tests/test_conversation_source_api.py`
