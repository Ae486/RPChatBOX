# S3.5 Test And Gate Plan

Status: planning draft for review
Owner: main-brain
Date: 2026-06-23

## Test Strategy

S3.5 is a productionization slice. Its tests must prove that normal runtime can
use a structured-output runner path without relying on the legacy specialist
fallback, while still preserving fallback as explicit compatibility.

Deterministic tests are required. Live-provider smoke is optional.

## Required Test Layers

### 1. Generic runner port tests

Required cases:

- valid structured output returns completed result;
- invalid provider output returns structured failure / parse error;
- provider exception returns stable failure;
- timeout/cancellation shape is represented if supported by the local gateway;
- trace includes runner id, schema name, and safe provider/model metadata.

### 2. Memory-maintenance runner tests

Required cases:

- valid fake model output becomes `MemoryMaintenanceWorkerStructuredOutput`;
- candidate batch path reaches `MemoryMaintenanceWorkerAdapter`;
- no-op path reaches adapter and produces skipped result;
- worker failure path reaches adapter and produces failed result;
- malformed output becomes failed `WorkerResult` with stable reason code;
- runner does not mutate Core, Projection, Recall, Archival, or proposal/apply.

### 3. WorkerExecutionService integration tests

Required cases:

- when production runner is wired, `LongformSpecialistService.analyze()` is not
  called;
- result contains S3 memory candidate kind and adapter metadata;
- when runner is disabled/unavailable and compatibility is enabled, legacy
  specialist fallback is called and compatibility metadata remains;
- when runner is disabled and compatibility is disabled, execution fails or
  degrades through existing explicit missing-runner behavior.

### 4. Runtime factory wiring tests

Required cases:

- factory wires `MemoryMaintenanceWorkerAdapter` with production runner when the
  runner is enabled/configured;
- factory keeps explicit compatibility fallback metadata path when runner is not
  enabled/configured;
- factory tests do not require a live provider.

### 5. Regression tests

Run existing S3/S3g-b gates:

```powershell
cd H:\chatboxapp\backend
python -m pytest -n auto rp/tests/services/writer/test_worker_scheduler_service.py
python -m pytest -n auto rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
python -m pytest -n auto tests/test_story_runtime_s3_memory_worker_e2e.py
python -m ruff check <changed files>
```

From repo root:

```powershell
python backend/rp/devtools/check_service_sizes.py
```

Expected service-size rule:

- no new S3.5 hard offender;
- if global command fails on known unrelated story-service drift, record exact
  offenders and do not mix cleanup into S3.5 unless S3.5 owns the file.

## Optional Live Smoke

After deterministic tests pass, an optional live-provider smoke may be run
through existing project configuration.

Rules:

- do not print secrets;
- keep prompt/input small and non-sensitive;
- smoke result is advisory only;
- deterministic tests remain the gate of record;
- failure does not justify weakening deterministic requirements.

## Review Gate

Before code:

- dispatch a reviewer to read:
  - `runtime-agent-harness.md`;
  - `runtime-worker-family.md`;
  - `runtime-scheduler-governance.md`;
  - `S3.5-harness-productionization-decision.md`;
  - this PRD/SDD/test plan.

After code:

- dispatch a fresh reviewer that did not implement S3.5.
- reviewer must check:
  - no setup-agent executor import/reuse;
  - no memory policy in generic harness core;
  - no direct truth mutation;
  - no proposal/apply bypass;
  - failure and trace behavior;
  - tests cover fake runner and fallback paths.

## Commit Gate

Commit only after:

- focused tests pass or expected unrelated failures are documented;
- fresh review findings are adjudicated;
- staged diff includes only S3.5-owned files;
- worklog/check record capture command results.
