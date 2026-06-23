# S3g-b Implementation Result

Status: implemented and reviewed
Date: 2026-06-23
Owner: main-brain

## Scope

S3g-b makes the production worker execution boundary honest for
`LongformMemoryWorker`:

- use the S3 `MemoryMaintenanceWorkerAdapter` path when a structured-output
  runner exists;
- keep legacy specialist execution only as explicit compatibility fallback when
  the production runner is missing;
- wire the normal runtime factory so the adapter/compatibility boundary is
  visible instead of silently preserving the old bridge.

## Changed Files

Production:

- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- `backend/rp/services/writer/worker_execution_service.py`
- `backend/rp/runtime/rp_runtime_factory.py`

Tests:

- `backend/rp/tests/services/writer/test_worker_scheduler_service.py`

Task/control docs:

- `execution/main-brain/codex-subagent-dispatch-research-2026-06-23.md`
- `execution/main-brain/operating-rules.md`
- `execution/main-brain/implementation-leadership-rules.md`
- `execution/phase-5-implementation/S3/22-S3g-b-fresh-review-brief.md`
- `execution/phase-5-implementation/S3/S3g-b-fresh-review-report.md`
- `execution/phase-5-implementation/S3/S3g-b-check-record.md`

## Behavior Landed

### Adapter availability

`MemoryMaintenanceWorkerAdapter` now exposes:

```python
has_structured_output_runner
```

This is only a mechanical capability check. It does not encode product policy.

### Worker execution boundary

`WorkerExecutionService` now accepts:

- `longform_memory_worker_adapter`;
- `enable_legacy_longform_memory_worker_specialist_fallback`.

For `LongformMemoryWorker`:

```text
adapter exists and has runner
  -> MemoryMaintenanceWorkerAdapter.execute(...)
  -> no LongformSpecialistService.analyze()
  -> empty SpecialistResultBundle

no runner and explicit compatibility enabled
  -> legacy LongformSpecialistService.analyze(...)
  -> old bundle adaptation
  -> explicit compatibility metadata and trace

no runner and compatibility disabled
  -> adapter failure result if adapter exists
  -> missing executor degraded result if no adapter exists
```

Legacy compatibility metadata/trace includes:

- `executor_mode="legacy_specialist_compatibility"`;
- `compatibility_reason="memory_worker_structured_output_runner_missing"`;
- `s3_executor_migration_complete=False`.

### Runtime factory wiring

`rp_runtime_factory.py` now constructs `MemoryMaintenanceWorkerAdapter()` and
passes it into `WorkerExecutionService` with explicit legacy compatibility
enabled. This does not claim full production executor migration; it records the
current boundary as adapter-ready but still fallback-backed.

### Test coverage

`test_worker_scheduler_service.py` now covers:

- adapter runner path with `ScriptedMemoryMaintenanceStructuredOutputRunner`;
- no specialist call when adapter runner exists;
- explicit legacy compatibility fallback and stable metadata/trace;
- factory wiring of adapter + compatibility switch.

## Fresh Review

Fresh review was run through a direct main-brain-launched `codex exec` child
session, because the current non-interactive environment does not expose true
internal subagent spawn tools.

Review session:

- command family: `codex exec --cd H:\chatboxapp --sandbox read-only ...`
- thread id: `019ef21b-3558-7d83-bdd8-8ea7f5ab9040`
- report: `S3g-b-fresh-review-report.md`
- verdict: `GO`

Reviewer noted:

- no blockers;
- no concerns;
- no setup-agent dependency, direct truth mutation, proposal/apply behavior
  change, or framework/product leakage found;
- residual production structured-output runner gap is correctly left explicit.

## Residual Gap

The production structured-output runner for memory maintenance is still missing.
S3g-b intentionally does not create it. The current normal runtime path is:

```text
adapter-ready seam + explicit legacy compatibility fallback
```

This is acceptable for S3g-b but must not be described as full production
executor migration.
