# S3g Planning Review Output

Date: 2026-06-23
Review session: `019ef1cb-2b72-7a80-9136-36154b38854c`
Mode: read-only Codex reviewer

## Verdict

```text
PASS_WITH_CONCERNS
```

## Findings

- `[medium]` S3g-b could still be implemented as "adapter path only when a test
  injects a runner," while default product wiring remains legacy. The reviewer
  pointed to:
  - `18-S3g-production-executor-and-service-size-brief.md`, where the first
    draft allowed using the S3 adapter only when a runner is provided;
  - `backend/rp/runtime/rp_runtime_factory.py`, where normal construction still
    passes only `longform_specialist_service`;
  - `backend/rp/services/writer/worker_execution_service.py`, where production
    execution still calls `LongformSpecialistService.analyze()`;
  - `backend/rp/tests/services/writer/test_worker_scheduler_service.py`, where
    the existing test still pins the legacy executor bridge behavior.

## Recommended Changes

- Tighten S3g-b acceptance so the default runtime assembly cannot silently remain
  legacy. Require either production wiring of `MemoryMaintenanceWorkerAdapter`
  and runner in `rp_runtime_factory.py`, or an explicit named compatibility
  mode/config flag with trace evidence.
- Add a required test update for
  `backend/rp/tests/services/writer/test_worker_scheduler_service.py::test_worker_execution_service_adapts_longform_memory_worker_to_legacy_bundle`,
  not only a new injected-path test.

## Residual Risks

- Reviewer attempted YCE but hit `spawn EPERM` in the read-only environment. It
  used direct read-only file reads and `check_service_sizes.py` evidence instead
  and did not use ACE.
- Live-provider execution can remain deferred if deterministic adapter/runner
  coverage is explicit and the brief does not claim universal harness
  completion.

## Main-Brain Adjudication

Accepted.

The concern is valid. A test-only injected adapter path would not be enough; it
would repeat the exact S3f limitation. The S3g brief has been amended so
S3g-b must prove the normal production construction path uses the S3 adapter /
runner, or else explicitly record compatibility mode and keep production
executor migration open.
