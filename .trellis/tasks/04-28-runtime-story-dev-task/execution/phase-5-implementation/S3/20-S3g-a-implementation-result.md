# S3g-a Implementation Result

Status: implementation accepted
Date: 2026-06-23
Owner: main-brain

## Scope Completed

S3g-a mechanically split the three S3-owned service-size hard function
offenders without changing S3 behavior:

- `MemoryCandidateValidationService._validate_operation`
- `MemoryMaintenanceWorkerAdapter._candidate_batch_result`
- `PostWriteGovernanceService._dispatch_proposal_governance`

No executor migration was done in this slice. S3g-b remains separate.

## Code Changed

- `backend/rp/services/memory/memory_candidate_validation_service.py`
- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- `backend/rp/services/proposal/post_write_governance_service.py`

## Behavior Boundary

This slice does not add:

- new memory operation kinds;
- new proposal/apply semantics;
- production `WorkerExecutionService` migration;
- setup-agent imports;
- direct truth mutation paths;
- reason-code aliases.

## Verification

Focused S3b/S3c command:

```powershell
cd H:\chatboxapp\backend
python -m pytest rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
```

Result:

```text
15 passed, 1 warning
```

S3f E2E command:

```powershell
python -m pytest tests/test_story_runtime_s3_memory_worker_e2e.py
```

Result:

```text
4 passed, 5 warnings
```

S3a / proposal adapter command:

```powershell
python -m pytest rp/tests/services/memory/test_memory_candidate_validation_service.py rp/tests/services/proposal/test_memory_candidate_proposal_adapter.py
```

Result:

```text
23 passed, 1 warning
```

S3d/S2b regression command:

```powershell
python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py
```

Result:

```text
29 passed, 1 warning
```

Focused ruff command:

```powershell
python -m ruff check rp/services/memory/memory_candidate_validation_service.py rp/services/writer/memory_maintenance_worker_adapter.py rp/services/proposal/post_write_governance_service.py
```

Result:

```text
All checks passed.
```

Diff whitespace check:

```powershell
git diff --check -- backend/rp/services/memory/memory_candidate_validation_service.py backend/rp/services/proposal/post_write_governance_service.py backend/rp/services/writer/memory_maintenance_worker_adapter.py
```

Result:

```text
PASS; only CRLF conversion warnings.
```

Service-size command:

```powershell
python backend/rp/devtools/check_service_sizes.py
```

Result:

```text
FAIL
```

Important detail:

```text
hard offenders: file=11 function=41 class=23
hard baseline: file=11 function=41 class=23
```

The S3-owned new hard function offenders are gone. The remaining errors are the
known older story-service baseline drift in `story/runtime_identity_service.py`
and `story/turn_domain_service.py`.

## Residual Gaps

S3g-a does not complete production executor migration. S3g-b must still address
`WorkerExecutionService`, normal runtime assembly, and the legacy specialist
fallback boundary.

Global service-size remains red until the older story-service baseline drift is
handled. This slice only removed the S3-owned new hard function offenders.

## Review

Fresh read-only review session:

```text
019ef1e5-616f-77e1-b7fb-4e3e89fd26e6
```

Verdict:

```text
PASS
```

Main-brain accepted the result. No code changes were required after review.
