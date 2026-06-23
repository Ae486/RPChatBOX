# S3g-a Check Record

Date: 2026-06-23
Owner: main-brain
Scope: S3g-a service-size cleanup

## Inputs

- `18-S3g-production-executor-and-service-size-brief.md`
- `19-S3g-a-service-size-cleanup-implementation-brief.md`
- `S3g-a-fresh-review-brief.md`
- current diff in:
  - `backend/rp/services/memory/memory_candidate_validation_service.py`
  - `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
  - `backend/rp/services/proposal/post_write_governance_service.py`

## Review

Fresh read-only review session:

```text
019ef1e5-616f-77e1-b7fb-4e3e89fd26e6
```

Verdict:

```text
PASS
```

Full review output is recorded in `S3g-a-fresh-review-output.md`.

Main-brain adjudication:

```text
Accepted. No follow-up code change required.
```

## Verification

Focused S3b/S3c:

```text
python -m pytest rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
15 passed, 1 warning
```

S3f E2E:

```text
python -m pytest tests/test_story_runtime_s3_memory_worker_e2e.py
4 passed, 5 warnings
```

S3a/proposal adapter:

```text
python -m pytest rp/tests/services/memory/test_memory_candidate_validation_service.py rp/tests/services/proposal/test_memory_candidate_proposal_adapter.py
23 passed, 1 warning
```

S3d/S2b:

```text
python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py
29 passed, 1 warning
```

Ruff:

```text
python -m ruff check rp/services/memory/memory_candidate_validation_service.py rp/services/writer/memory_maintenance_worker_adapter.py rp/services/proposal/post_write_governance_service.py
All checks passed.
```

Service-size:

```text
python backend/rp/devtools/check_service_sizes.py
FAIL
hard offenders: file=11 function=41 class=23
hard baseline: file=11 function=41 class=23
```

Interpretation:

- S3-owned hard function offenders have been removed.
- Remaining failures are older story-service baseline drift:
  - `story/runtime_identity_service.py`
  - `story/turn_domain_service.py`
  - `StoryTurnDomainService.__init__`
  - `StoryTurnDomainService.trigger_post_write`

## Gate Decision

S3g-a is accepted.

It may be committed as a service-size cleanup slice with the residual
story-service baseline drift explicitly open for a later cleanup.
