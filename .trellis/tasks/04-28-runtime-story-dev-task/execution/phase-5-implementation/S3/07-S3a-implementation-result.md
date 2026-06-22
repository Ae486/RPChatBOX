# S3a Implementation Result

Status: gate passed
Date: 2026-06-23

## Scope Completed

S3a implemented the bounded registry/candidate-contract slice:

- S3 longform runtime memory registry with the exact five-domain contract;
- fixed first-pass block topology;
- primary `facts[]` field contract with optional grouping metadata;
- strict memory maintenance candidate DTOs;
- deterministic candidate validator;
- focused tests and old registry regression.

Out of scope remained untouched:

- worker model/tool execution;
- proposal workflow;
- governed apply;
- maintenance lock;
- runtime truth mutation.

## Code Added

- `backend/rp/models/memory/runtime_memory_contract.py`
- `backend/rp/services/memory/runtime_memory_contract_registry.py`
- `backend/rp/models/memory/maintenance_candidate.py`
- `backend/rp/services/memory/memory_candidate_validation_service.py`
- `backend/rp/tests/models/memory/__init__.py`
- `backend/rp/tests/models/memory/test_memory_maintenance_candidate_contracts.py`
- `backend/rp/tests/services/memory/test_runtime_memory_contract_registry.py`
- `backend/rp/tests/services/memory/test_memory_candidate_validation_service.py`

## Implementation Notes

- The old 13-domain bootstrap registry was not replaced. S3a adds an explicit
  longform runtime registry surface so old compatibility behavior and new S3
  longform contracts stay separated.
- Candidate batches must contain at least one candidate. A no-op is a separate
  worker result type for S3b, not an empty candidate batch.
- `append_item` cannot target an existing fact id/handle. Backend-owned fact
  identity remains backend-owned.
- Candidate validation is fail-closed and returns stable reason codes. It does
  not mutate memory truth.

## Review

Fresh check record:

- `execution/phase-5-implementation/S3/S3a-check-record.md`

Findings fixed by the check pass:

- tests no longer compute expected topology from implementation constants;
- extra-field tests no longer pass for the wrong reason;
- append operations cannot preselect existing fact identity.

## Verification

Command run by main-brain from `H:\chatboxapp\backend`:

```powershell
python -m pytest rp/tests/services/memory/test_memory_contract_registry.py rp/tests/services/memory/test_runtime_memory_contract_registry.py rp/tests/models/memory/test_memory_maintenance_candidate_contracts.py rp/tests/services/memory/test_memory_candidate_validation_service.py
```

Result:

```text
45 passed, 1 warning in 0.35s
```

The warning is the existing Pydantic class-based `config` deprecation in
`backend/config.py`, outside S3a.

## Remaining Work

S3b can build on S3a by adding the MemoryMaintenanceWorker adapter / fake
harness path. S3c/S3d must still connect candidates to governance/apply,
maintenance lock, and stale-base enforcement.
