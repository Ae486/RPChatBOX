# S3g-a Fresh Review Brief

Status: ready for read-only reviewer
Date: 2026-06-23
Owner: main-brain

## Reviewer Role

Perform a read-only review of the current S3g-a implementation diff.

Do not edit files. Do not commit. Do not run destructive commands. Do not use
ACE. Use YCE for codebase search if you need additional search context; if the
YCE remote key is unavailable, rerun YCE with `YCE_LOCAL_FALLBACK=true`.

Directly reading the files named below is allowed and preferred.

## Scope

S3g-a is a mechanical service-size cleanup. It must not change behavior or start
S3g-b production executor migration.

In-scope changed production files:

- `backend/rp/services/memory/memory_candidate_validation_service.py`
- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- `backend/rp/services/proposal/post_write_governance_service.py`

Out of scope:

- `backend/rp/services/writer/worker_execution_service.py`
- `backend/rp/runtime/rp_runtime_factory.py`
- `backend/rp/tests/services/writer/test_worker_scheduler_service.py`
- story service dirty files
- unrelated visible dirty files

## Requirement Documents

Read these if you need the planning context:

- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/18-S3g-production-executor-and-service-size-brief.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/19-S3g-a-service-size-cleanup-implementation-brief.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/main-brain/operating-rules.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-worker-family.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-scheduler-governance.md`

## Leader-Verified Evidence

Current `git diff --stat` for S3g-a target files:

```text
memory/memory_candidate_validation_service.py  | 150 +++++++---
proposal/post_write_governance_service.py      | 322 ++++++++++++++-------
writer/memory_maintenance_worker_adapter.py    | 222 +++++++++-----
3 files changed, 477 insertions(+), 217 deletions(-)
```

Verification already run:

```text
python -m pytest rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
15 passed, 1 warning

python -m pytest tests/test_story_runtime_s3_memory_worker_e2e.py
4 passed, 5 warnings

python -m pytest rp/tests/services/memory/test_memory_candidate_validation_service.py rp/tests/services/proposal/test_memory_candidate_proposal_adapter.py
23 passed, 1 warning

python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py
29 passed, 1 warning

python -m ruff check rp/services/memory/memory_candidate_validation_service.py rp/services/writer/memory_maintenance_worker_adapter.py rp/services/proposal/post_write_governance_service.py
All checks passed.

git diff --check -- <three S3g-a target files>
No whitespace errors; only CRLF conversion warnings.
```

Service-size evidence:

```text
python backend/rp/devtools/check_service_sizes.py
result: FAIL
hard offenders: file=11 function=41 class=23
hard baseline: file=11 function=41 class=23
```

The S3-owned new hard function offenders are gone. The remaining errors are the
known older story-service baseline drift:

- `story/runtime_identity_service.py`
- `story/turn_domain_service.py`
- `StoryTurnDomainService.__init__`
- `StoryTurnDomainService.trigger_post_write`

## Review Questions

1. Does the diff stay inside S3g-a scope?
2. Is the refactor behavior-preserving for validation errors, worker result
   payloads, proposal governance job status, failure metadata, proposal refs,
   and trace metadata?
3. Did the implementation avoid S3g-b executor migration and avoid setup-agent
   imports?
4. Does service-size evidence prove the S3-owned hard function offenders were
   removed?
5. Are any tests missing for this mechanical cleanup before commit?

## Expected Output

Return:

```text
Verdict: PASS | PASS_WITH_CONCERNS | BLOCKED

Findings:
- [severity] finding with file/path evidence

Recommended changes:
- concrete changes, if any

Residual risks:
- deferrable risks, if any
```
