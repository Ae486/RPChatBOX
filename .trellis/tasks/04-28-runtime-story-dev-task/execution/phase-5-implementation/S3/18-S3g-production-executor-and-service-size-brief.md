# S3g Production Executor And Service-Size Brief

Status: planning draft for reviewer
Date: 2026-06-23
Owner: main-brain

## 1. Why This Slice Exists

S3f closed the deterministic functional path from a scheduler-selected memory
worker to proposal governance, apply, and maintenance lock behavior. It did not
finish two engineering obligations that must be addressed before S4/S5/S6 build
more behavior on top of S3:

1. Production `LongformMemoryWorker` execution still runs through the legacy
   `LongformSpecialistService` adapter and then adapts that bundle into a
   `WorkerResult`.
2. The service-size gate is red because S3a/S3b/S3c introduced three new hard
   function offenders, alongside older story-service baseline drift.

S3g is a cleanup and production-readiness slice. It should not add new product
scope. Its job is to make the existing S3 path honest enough to be used as the
base for later runtime work.

## 2. Requirement Authority

Primary requirement sources:

- `research/index.md`
- `research/modules/runtime-module-breakdown-index.md`
- `research/modules/runtime-worker-family.md`
- `research/modules/runtime-scheduler-governance.md`
- `research/modules/runtime-agent-harness.md`
- `research/modules/runtime-workspace-ledger-trace.md`
- `execution/main-brain/operating-rules.md`
- `execution/main-brain/harness-gap-and-completion-plan.md`
- `execution/phase-5-implementation/S3/01-PRD.md`
- `execution/phase-5-implementation/S3/02-SDD-and-implementation-plan.md`
- `execution/phase-5-implementation/S3/03-test-and-gate-plan.md`
- `execution/phase-5-implementation/S3/17-S3f-implementation-result.md`
- `execution/phase-5-implementation/S3/S3f-check-record.md`

Current code evidence was located with YCE only. No ACE search was used.

Important anchors:

- `backend/rp/services/writer/worker_execution_service.py`
- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- `backend/rp/services/writer/worker_registry_service.py`
- `backend/rp/services/proposal/post_write_governance_service.py`
- `backend/rp/services/proposal/memory_candidate_proposal_adapter.py`
- `backend/rp/services/memory/memory_candidate_validation_service.py`
- `backend/rp/agent_runtime/story/story_harness.py`
- `backend/tests/test_story_runtime_s3_memory_worker_e2e.py`
- `backend/rp/tests/services/writer/test_memory_maintenance_worker_adapter.py`

## 3. Current Facts

### 3.1 Functional S3 path is proven through a test seam

S3f proves this path:

```text
StoryTurnDomainService.trigger_post_write()
  -> scheduler/orchestrator selects LongformMemoryWorker
  -> fake executor consumes selected worker request
  -> MemoryMaintenanceWorkerAdapter returns candidate / no-op / failure
  -> PostWriteGovernanceService
  -> ProposalWorkflowService
  -> ProposalApplyService
  -> RuntimeMaintenanceLockService
```

That is a valid deterministic gate, but it is not the production executor path.

### 3.2 Production executor still uses legacy specialist execution

`WorkerExecutionService._run_longform_memory_worker()` currently does:

```text
WorkerContextPacket
  -> LongformSpecialistService.analyze(...)
  -> StoryRuntimeAdapterService.adapt_specialist_bundle_to_worker_result(...)
```

This keeps S3 production behavior behind a compatibility adapter. S3g must
either replace that path for `LongformMemoryWorker` with
`MemoryMaintenanceWorkerAdapter`, or introduce a clearly named compatibility
mode that cannot be mistaken for the final S3 executor.

### 3.3 Story harness is still minimal

`backend/rp/agent_runtime/story/story_harness.py` currently provides a small
S0 test substrate with a scripted LLM and a no-op tool executor. It does not yet
provide a production structured-output runner for the memory worker.

S3g therefore should not claim universal harness completion. The production
executor migration must be scoped to a practical seam:

```text
WorkerExecutionService
  -> MemoryMaintenanceWorkerAdapter
  -> MemoryMaintenanceStructuredOutputRunner
```

If the runner is not ready for live model calls in this slice, the slice must
make that explicit and keep legacy fallback clearly labeled.

### 3.4 Service-size is currently red

`python backend/rp/devtools/check_service_sizes.py` currently fails with:

- older baseline drift:
  - `story/runtime_identity_service.py`
  - `story/turn_domain_service.py`
  - `StoryTurnDomainService.__init__`
  - `StoryTurnDomainService.trigger_post_write`
- S3-owned new hard function offenders:
  - `memory/memory_candidate_validation_service.py::_validate_operation`
  - `proposal/post_write_governance_service.py::_dispatch_proposal_governance`
  - `writer/memory_maintenance_worker_adapter.py::_candidate_batch_result`

S3g must at minimum remove the S3-owned hard function offenders. The older
story-service baseline drift must not be worsened, and any direct edits to those
files must be bounded because several of them are already dirty in the worktree.

## 4. Goals

### G1. Make the S3-owned service-size offenders green

Split or extract the three S3a/S3b/S3c oversized functions without changing
their behavior.

The preferred implementation is small helper methods or small helper services
inside the existing responsibility boundary:

- candidate operation validation stays in memory candidate validation;
- candidate-batch to `WorkerResult` mapping stays in the memory worker adapter;
- proposal governance dispatch stays in proposal governance, with helper
  extraction for job lifecycle, envelope creation, and handoff routing.

Do not solve the entire repository service-size backlog in this slice.

### G2. Move production `LongformMemoryWorker` toward the S3 adapter path

Replace or clearly route production memory-worker execution through
`MemoryMaintenanceWorkerAdapter` for the S3 memory-maintenance path.

The design must preserve these facts:

- worker output is candidate/no-op/failure material, not authoritative memory;
- proposal/apply remains owned by deterministic governance/apply services;
- stale-base and invalid candidate handling remain deterministic;
- no setup-agent executor or setup-agent private protocol is imported.

### G3. Keep framework and product policy separate

S3g may add or use a structured-output runner seam. It must not move memory
domain/block rules, proposal policy, base-ref semantics, or apply behavior into
the harness core.

Allowed generic harness-facing mechanisms:

- model call gateway or runner interface;
- structured-output validation;
- normalized tool result shape;
- bounded retry/repair hooks;
- trace metadata;
- fake runner/test doubles.

Product-specific behavior remains in:

- worker definition or adapter;
- memory candidate validator;
- proposal handoff adapter;
- governance/apply services;
- compiled runtime profile and policy.

## 5. Non-Goals

S3g must not implement:

- S4 retrieval behavior;
- S5 chapter close / summary / tail flush behavior;
- S6 review/rewrite behavior;
- branch delete policy;
- frontend maintenance-lock UX;
- Recall lifecycle lock policy;
- full universal production executor replacement for writer/orchestrator/
  worker/brainstorm;
- live-provider smoke as a substitute for deterministic tests.

## 6. Proposed Sub-Slices

### S3g-a. Service-size cleanup for S3-owned offenders

Scope:

- split `_validate_operation`;
- split `_candidate_batch_result`;
- split `_dispatch_proposal_governance`;
- preserve current tests and public behavior;
- avoid touching unrelated dirty files.

Acceptance:

- focused S3a/S3b/S3c tests pass;
- S3f E2E test still passes;
- `ruff` passes for touched files;
- `check_service_sizes.py` no longer reports the three S3-owned hard function
  offenders.

If older story-service baseline drift still fails, the result record must say so
explicitly and show that S3-owned new offenders are gone.

### S3g-b. Production executor migration plan and implementation

Scope:

- add a production-facing `MemoryMaintenanceStructuredOutputRunner` seam if
  needed;
- wire `WorkerExecutionService._run_longform_memory_worker()` to use
  `MemoryMaintenanceWorkerAdapter` when the selected request is the S3
  `LongformMemoryWorker` memory-maintenance path;
- wire the default runtime assembly in `rp_runtime_factory.py` or an equivalent
  production construction point so normal product execution cannot silently stay
  on the legacy specialist path;
- keep legacy `LongformSpecialistService` fallback explicitly named and bounded
  if it remains necessary, and only under an explicit compatibility condition;
- keep worker result shape identical to the S3b/S3c governance contract.

Acceptance:

- at least one deterministic test proves the production `WorkerExecutionService`
  path calls `MemoryMaintenanceWorkerAdapter`, not only the S3f fake executor;
- the normal runtime construction path is tested. It must either use the S3
  adapter/runner by default or expose an explicit compatibility mode/config flag
  whose trace says legacy execution is still active;
- `backend/rp/tests/services/writer/test_worker_scheduler_service.py::test_worker_execution_service_adapts_longform_memory_worker_to_legacy_bundle`
  is updated or replaced so it no longer pins silent legacy execution as the
  default completed S3 path;
- legacy specialist fallback, if retained, has an explicit reason and trace;
- review-required, direct-apply, adapter failure, and governance handoff failure
  still pass through real governance/apply/lock services;
- no setup-agent import or setup executor reuse appears.

### S3g-c. Fresh review and gate record

Scope:

- dispatch a fresh reviewer after S3g implementation;
- reviewer must read Node-1/module authority docs and this S3g brief;
- main-brain must adjudicate findings;
- write an S3g result/check record;
- commit the slice after gates pass.

Acceptance:

- review output is persisted;
- main-brain accepted/rejected/deferred findings are recorded;
- commit includes only S3g-owned files.

## 7. Technical Approach Notes

### 7.1 Service-size refactor strategy

Refactor mechanically first. Do not combine service-size cleanup with behavior
changes.

Recommended extraction boundaries:

- `MemoryCandidateValidationService._validate_operation`
  - split field support validation;
  - split operation payload validation;
  - split target conflict validation.
- `MemoryMaintenanceWorkerAdapter._candidate_batch_result`
  - split candidate-batch schema/identity validation;
  - split validation-failure `WorkerResult` building;
  - split successful proposal-candidate payload building.
- `PostWriteGovernanceService._dispatch_proposal_governance`
  - split job creation/running transition;
  - split result-to-handoff routing;
  - split job completion/failure marking.

### 7.2 Production executor migration strategy

The target shape should be:

```text
WorkerExecutionService._execute_one()
  -> _run_longform_memory_worker()
  -> MemoryMaintenanceWorkerAdapter.execute()
  -> WorkerResult
```

Current blocker: `MemoryMaintenanceWorkerAdapter` has a runner protocol and a
scripted fake runner, but no production structured-output runner is visible in
the current harness.

Acceptable first production migration:

- introduce a named runner interface injection point into
  `WorkerExecutionService`;
- wire that runner through the normal production construction path, not only
  through test-only dependency injection;
- make the S3 adapter path the default completed S3 behavior when the runner is
  available;
- keep legacy specialist execution only as an explicit compatibility mode with a
  stable reason code, trace metadata, and tests;
- add tests proving the normal path, the adapter path, and the compatibility
  fallback label.

If no production structured-output runner can be wired in S3g, the slice must
not claim production executor migration complete. In that case, it may only land
an explicit compatibility mode plus tests, and the result document must keep the
production migration gap open.

Risk to avoid:

- silently calling legacy specialist execution and labeling the result as the
  completed S3 agent path;
- embedding memory candidate prompts, domain rules, or proposal policy in the
  generic story harness;
- adding live-provider calls without deterministic fake coverage.

## 8. Test Plan

Minimum deterministic tests:

- existing S3a candidate validation tests;
- existing S3b memory worker adapter tests;
- existing S3c governance routing tests;
- existing S3d/S3e lock and entrypoint guard tests;
- existing S3f E2E tests;
- new focused `WorkerExecutionService` test proving adapter-path execution;
- updated `test_worker_scheduler_service` coverage so legacy bridge behavior is
  either removed as the default expectation or preserved only under an explicit
  compatibility condition;
- runtime factory or production assembly coverage proving the normal
  construction path cannot silently omit the S3 adapter/runner;
- new or updated service-size gate evidence.

Commands expected from `H:\chatboxapp\backend`:

```powershell
python -m pytest rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py
python -m pytest tests/test_story_runtime_s3_memory_worker_e2e.py
python -m ruff check rp/services/memory/memory_candidate_validation_service.py rp/services/writer/memory_maintenance_worker_adapter.py rp/services/proposal/post_write_governance_service.py rp/services/writer/worker_execution_service.py
```

Repository-root gate:

```powershell
python backend/rp/devtools/check_service_sizes.py
```

## 9. Commit And Rollback Plan

Use small commits:

1. planning / review brief commit;
2. service-size cleanup implementation commit after gate;
3. production executor migration commit after gate;
4. review/result docs commit if they are not included in the implementation
   commit.

Stage only explicit paths. `.trellis/tasks/` documents are ignored and must be
force-added with explicit paths when they need to be versioned.

Do not stage or revert unrelated dirty files:

- `.gitignore`
- `.trellis/.template-hashes.json`
- `backend/rp/services/story/runtime_controller.py`
- `backend/rp/services/story/turn_domain_service.py`
- `backend/rp/tests/services/writer/test_longform_chapter_runtime_service.py`
- `backend/services/conversation_source.py`
- `backend/tests/test_conversation_source_api.py`

## 10. Reviewer Questions

The fresh reviewer should answer:

1. Does this brief correctly reflect Node-1/module requirements?
2. Is S3g-a scoped tightly enough to make service-size green without behavior
   churn?
3. Is S3g-b honest about the current lack of a production structured-output
   runner?
4. Is the legacy fallback boundary clear enough that later agents cannot mistake
   it for the completed S3 production executor?
5. Are the proposed tests sufficient before S4/S5/S6 work continues?
