# S3g Planning Review Brief

Status: ready for fresh read-only reviewer
Date: 2026-06-23
Owner: main-brain

## Reviewer Role

Perform a read-only review of the S3g planning draft before any production code
implementation starts.

Do not edit files. Do not commit. Do not use ACE. Use YCE for codebase search if
you need additional code context.

## Files To Read

Requirement authority:

- `.trellis/tasks/04-28-runtime-story-dev-task/research/index.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-module-breakdown-index.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-worker-family.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-scheduler-governance.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-agent-harness.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/main-brain/operating-rules.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/main-brain/harness-gap-and-completion-plan.md`

S3 documents:

- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/01-PRD.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/02-SDD-and-implementation-plan.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/17-S3f-implementation-result.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/S3f-check-record.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/18-S3g-production-executor-and-service-size-brief.md`

Current code anchors:

- `backend/rp/services/writer/worker_execution_service.py`
- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- `backend/rp/services/writer/worker_registry_service.py`
- `backend/rp/services/proposal/post_write_governance_service.py`
- `backend/rp/services/proposal/memory_candidate_proposal_adapter.py`
- `backend/rp/services/memory/memory_candidate_validation_service.py`
- `backend/rp/agent_runtime/story/story_harness.py`
- `backend/tests/test_story_runtime_s3_memory_worker_e2e.py`

## Review Questions

1. Is the S3g scope correct, or does it accidentally add S4/S5/S6 product scope?
2. Does the brief accurately distinguish S3f's deterministic fake-executor gate
   from production `WorkerExecutionService` migration?
3. Is the service-size cleanup plan narrow and behavior-preserving?
4. Does the production executor plan respect the harness/product boundary?
5. Is the proposed legacy fallback boundary explicit enough?
6. Are the required tests sufficient to prevent later agents from building on a
   compatibility-only path?

## Expected Output

Return:

```text
Verdict: PASS | PASS_WITH_CONCERNS | BLOCKED

Findings:
- [severity] finding with file/path evidence

Recommended changes:
- concrete edits to the brief, if any

Residual risks:
- risks that can be deferred, if any
```
