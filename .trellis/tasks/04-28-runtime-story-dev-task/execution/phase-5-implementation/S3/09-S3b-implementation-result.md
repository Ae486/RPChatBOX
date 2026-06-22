# S3b Implementation Result

Status: gate passed
Date: 2026-06-23

## Scope Completed

S3b implemented the bounded memory worker adapter / fake structured-output
slice:

- `MemoryMaintenanceWorkerAdapter` maps strict structured output into existing
  `WorkerResult` values;
- candidate batch, no-op, worker failure, schema failure, fake runner failure,
  and validator failure are all explicit outcomes;
- valid candidates use the named S3 candidate kind
  `s3_memory_maintenance_candidate`;
- candidate outputs carry `source_of_truth=false` and
  `authoritative_mutation=false`;
- a deterministic scripted runner seam exists for tests and later harness
  wiring.

Out of scope remained untouched:

- proposal workflow and governed apply;
- Core/projection truth mutation;
- Runtime Workspace persistence;
- maintenance lock;
- legacy longform `legacy_state_patch` execution compatibility.

## Code Added

- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- `backend/rp/tests/services/writer/test_memory_maintenance_worker_adapter.py`

## Implementation Notes

- S3b is adapter-only. It is not yet wired into
  `WorkerExecutionService`; the existing longform specialist compatibility path
  remains unchanged.
- The adapter validates two schema levels:
  - outer worker output schema:
    `story-runtime.memory-maintenance-worker-output.v1`;
  - inner candidate batch schema:
    `s3a.memory-maintenance-candidate.v1`.
- No-op is represented as `WorkerResultStatus.SKIPPED` with readable no-op
  trace metadata and no proposal candidate.
- Invalid structured output, worker/phase mismatch, candidate-batch mismatch,
  validator rejection, and worker-reported failure all fail closed with stable
  reason codes and no proposal candidate.
- The adapter depends on S3a
  `MemoryCandidateValidationService`; memory policy is not moved into harness
  core.

## Review

Fresh check record:

- `execution/phase-5-implementation/S3/S3b-check-record.md`

Findings fixed by the check pass:

- candidate batch schema version now fails closed;
- unsupported worker-output schema version has explicit coverage;
- worker-output worker id mismatch has explicit coverage;
- candidate batch schema mismatch has explicit coverage.

## Verification

Command run by main-brain from `H:\chatboxapp\backend`:

```powershell
python -m pytest rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/memory/test_runtime_memory_contract_registry.py rp/tests/models/memory/test_memory_maintenance_candidate_contracts.py rp/tests/services/memory/test_memory_candidate_validation_service.py rp/tests/agent_runtime/test_s0_harness_substrate.py rp/tests/services/story/test_story_runtime_adapter_service.py rp/tests/services/writer/test_worker_scheduler_service.py
```

Result:

```text
45 passed, 1 warning in 17.80s
```

The warning is the existing Pydantic class-based `config` deprecation in
`backend/config.py`, outside S3b.

## Remaining Work

S3c should connect the named S3 candidate boundary into proposal/governance:

- map `s3_memory_maintenance_candidate` into proposal input without exposing it
  as an undifferentiated `legacy_state_patch`;
- preserve deterministic apply as the only truth mutation path;
- implement review-required / direct-apply / blocked routing evidence;
- keep stale-base enforcement for S3d on the deterministic apply side.
