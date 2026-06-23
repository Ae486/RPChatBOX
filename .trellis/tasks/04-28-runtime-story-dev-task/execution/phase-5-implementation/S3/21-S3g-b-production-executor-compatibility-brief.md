# S3g-b Production Executor Compatibility Brief

Status: ready for implement sub-agent
Date: 2026-06-23
Owner: main-brain

## Implementer Role

Implement S3g-b only.

This slice must make the production worker execution boundary honest:

- when a `MemoryMaintenanceWorkerAdapter` has a structured-output runner,
  `WorkerExecutionService` must use the S3 adapter path for
  `LongformMemoryWorker`;
- when no production structured-output runner is available, legacy specialist
  execution may remain only as an explicit compatibility mode with stable trace
  metadata;
- the result must not claim full production executor migration if the default
  runtime still relies on compatibility fallback.

Use YCE for codebase search. Do not use ACE. Do not run git mutation commands.
Do not edit unrelated dirty files. Prefer Trellis/Codex-native subagent
dispatch for any follow-up implement/check/review work.

Subagent pytest rule: this implementer should not run pytest by default. The
main-brain or a dedicated check gate normally owns test execution. If the
implementer must run pytest for a narrow local check, use `-n auto` and report
the exact command and result.

## Requirement Authority

- `18-S3g-production-executor-and-service-size-brief.md`
- `S3g-planning-review-record.md`
- `20-S3g-a-implementation-result.md`
- `S3g-a-check-record.md`
- `execution/main-brain/harness-gap-and-completion-plan.md`
- `research/modules/runtime-worker-family.md`
- `research/modules/runtime-agent-harness.md`
- `research/modules/runtime-scheduler-governance.md`

## In Scope

Production files:

- `backend/rp/services/writer/worker_execution_service.py`
- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- `backend/rp/runtime/rp_runtime_factory.py`

Tests:

- `backend/rp/tests/services/writer/test_worker_scheduler_service.py`

Task docs:

- S3g-b result/check/review records after implementation.

## Out Of Scope

- Creating a real live-provider memory-maintenance prompt/runner if it cannot
  be done safely in this slice.
- S4 retrieval, S5 chapter-close, S6 review/rewrite.
- Proposal/apply behavior changes.
- Memory candidate schema changes.
- New memory operation kinds.
- Any setup-agent executor or setup-agent private protocol import.
- Editing unrelated dirty files:
  - `.gitignore`
  - `.trellis/.template-hashes.json`
  - `backend/rp/services/story/runtime_controller.py`
  - `backend/rp/services/story/turn_domain_service.py`
  - `backend/rp/tests/services/writer/test_longform_chapter_runtime_service.py`
  - `backend/services/conversation_source.py`
  - `backend/tests/test_conversation_source_api.py`

## Required Implementation

### 1. Expose adapter runner availability

Add a minimal public capability on `MemoryMaintenanceWorkerAdapter`, for example:

```python
@property
def has_structured_output_runner(self) -> bool:
    return self._structured_output_runner is not None
```

This is a mechanical capability check, not product policy.

### 2. Wire adapter into WorkerExecutionService

Add optional dependencies to `WorkerExecutionService`:

- `longform_memory_worker_adapter: MemoryMaintenanceWorkerAdapter | None`
- an explicit compatibility switch/name for legacy specialist fallback.

Target behavior:

```text
LongformMemoryWorker request
  -> if adapter exists and has runner: adapter.execute(...)
  -> else if compatibility fallback enabled: legacy specialist compatibility path
  -> else: adapter failure or missing executor failure
```

The adapter path must:

- use the existing `WorkerExecutionRequest`;
- pass the parsed `WorkerContextPacket`;
- return the adapter `WorkerResult`;
- not call `LongformSpecialistService.analyze()`;
- return an empty `SpecialistResultBundle`.

The legacy fallback path must:

- call the existing legacy specialist service;
- adapt the bundle as before;
- add explicit metadata and trace such as:
  - `executor_mode="legacy_specialist_compatibility"`;
  - `compatibility_reason="memory_worker_structured_output_runner_missing"` or
    equivalent stable reason;
  - `s3_executor_migration_complete=False`.

Do not silently preserve the old behavior without this trace.

### 3. Wire normal runtime assembly

`rp_runtime_factory.py` must no longer construct `WorkerExecutionService` without
making the S3 compatibility boundary explicit.

Acceptable for this slice:

- construct `MemoryMaintenanceWorkerAdapter()` in the factory;
- pass it into `WorkerExecutionService`;
- pass an explicit compatibility fallback flag/mode because no production
  structured-output runner is wired yet.

Do not claim this is full production migration. It is explicit compatibility
wiring plus the adapter-ready seam.

### 4. Update tests

Update or replace
`test_worker_execution_service_adapts_longform_memory_worker_to_legacy_bundle`
so it no longer pins silent legacy behavior as the S3 default.

Required tests:

1. Adapter runner path:
   - instantiate `MemoryMaintenanceWorkerAdapter` with
     `ScriptedMemoryMaintenanceStructuredOutputRunner`;
   - inject it into `WorkerExecutionService`;
   - execute the selected `LongformMemoryWorker`;
   - assert the specialist service was not called;
   - assert the `WorkerResult` contains S3 candidate kind and adapter metadata.

2. Explicit compatibility fallback:
   - instantiate `WorkerExecutionService` with an adapter that has no runner and
     compatibility enabled;
   - assert legacy specialist service is called;
   - assert result still carries legacy candidate output;
   - assert result metadata/trace contains the explicit compatibility mode and
     reason.

3. Normal runtime assembly:
   - add the smallest feasible assertion that the factory or production assembly
     passes the adapter/compatibility boundary into `WorkerExecutionService`;
   - if direct factory introspection is impractical, record why in the result and
     ensure constructor-level tests cover both adapter and compatibility paths.

## Behavior Guardrails

- No direct Core/projection truth mutation.
- No proposal/apply changes.
- No changes to scheduler worker selection.
- No memory policy in harness core.
- No new setup-agent dependency.
- No broad formatting churn.
- Keep service-size from regressing if possible; if an existing function grows
  near hard limit, split before committing.

## Verification Expected

From `H:\chatboxapp\backend`:

```powershell
python -m pytest -n auto rp/tests/services/writer/test_worker_scheduler_service.py
python -m pytest -n auto rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
python -m pytest -n auto tests/test_story_runtime_s3_memory_worker_e2e.py
python -m ruff check rp/services/writer/worker_execution_service.py rp/services/writer/memory_maintenance_worker_adapter.py rp/runtime/rp_runtime_factory.py rp/tests/services/writer/test_worker_scheduler_service.py
```

From repo root:

```powershell
python backend/rp/devtools/check_service_sizes.py
```

Expected service-size interpretation:

- no new S3g-b hard function offender;
- global command may still fail on known story-service baseline drift.

## Expected Response

Return:

```text
Changed files:
- ...

What changed:
- ...

Verification run:
- ...

Residual gap:
- whether production structured-output runner is still missing
```
