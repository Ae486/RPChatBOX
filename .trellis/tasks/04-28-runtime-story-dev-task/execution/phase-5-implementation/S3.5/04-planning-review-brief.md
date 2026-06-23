# S3.5 Planning Review Brief

Status: ready for read-only adversarial review
Owner: main-brain
Date: 2026-06-23

## Reviewer Role

Perform a read-only adversarial review of the S3.5 planning documents.

Your job is to find blockers, weak assumptions, missing gates, framework/product
leakage, old-MVP leakage, unclear acceptance criteria, and places where a future
agent could still implement the wrong thing.

Do not edit files.
Do not commit.
Do not run pytest.
Do not run broad shell searches.
Do not use ACE.

If you need code search, use YCE only. If YCE is unavailable in your sandbox,
use the pre-fed file list and direct known-file reads. Exact known-file reads are
allowed.

## Documents To Review

Primary planning documents:

- `.trellis/tasks/04-28-runtime-story-dev-task/execution/main-brain/S3.5-harness-productionization-decision.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3.5/01-PRD.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3.5/02-SDD-and-implementation-plan.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3.5/03-test-and-gate-plan.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/main-brain/overall-implementation-roadmap.md`

Requirement authority:

- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-agent-harness.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-worker-family.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-scheduler-governance.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/main-brain/harness-gap-and-completion-plan.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/main-brain/S3-retrospective-against-overall-roadmap.md`

Relevant current code / tests:

- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- `backend/rp/services/writer/worker_execution_service.py`
- `backend/rp/runtime/rp_runtime_factory.py`
- `backend/rp/tests/services/writer/test_memory_maintenance_worker_adapter.py`
- `backend/rp/tests/services/writer/test_worker_scheduler_service.py`
- `backend/tests/test_story_runtime_s3_memory_worker_e2e.py`

Anti-pattern reference only:

- `backend/rp/services/setup_agent/agent_execution_service.py`
- `backend/rp/agent_runtime/setup/executor.py`

Do not treat setup-agent code as a source to copy. It is only useful for spotting
coupling risks and avoiding setup-specific executor policy leakage.

## Current State Evidence From Main-Brain

Recent commits:

```text
bfcb50b docs(rp-runtime): plan S3.5 harness productionization
cab9368 docs(rp-runtime): record S3g-b recovery gate commit
51bc53c refactor(rp-runtime): wire S3 memory executor compatibility
```

Current unrelated dirty files that are out of scope:

```text
.gitignore
.trellis/.template-hashes.json
backend/rp/services/story/runtime_controller.py
backend/rp/services/story/turn_domain_service.py
backend/rp/tests/services/writer/test_longform_chapter_runtime_service.py
backend/services/conversation_source.py
backend/tests/test_conversation_source_api.py
```

YCE search from main-brain located these relevant S3.5 files:

```text
backend/rp/services/writer/worker_execution_service.py
backend/rp/services/writer/memory_maintenance_worker_adapter.py
backend/rp/runtime/rp_runtime_factory.py
backend/rp/tests/services/writer/test_memory_maintenance_worker_adapter.py
backend/rp/tests/services/writer/test_worker_scheduler_service.py
backend/tests/test_story_runtime_s3_memory_worker_e2e.py
backend/rp/services/setup_agent/agent_execution_service.py
backend/rp/agent_runtime/setup/executor.py
```

YCE remote failed because no YCE key is configured, but
`YCE_LOCAL_FALLBACK=true` returned the file list above. Do not use ACE.

## Questions To Answer

1. Is the decision "S3.5 required before S4 implementation" justified by the
   requirement documents and current code?
2. Is the scope correctly narrow, or does it still risk becoming a broad
   universal executor rewrite?
3. Are harness core, memory worker runner, memory adapter, worker execution,
   and governance/apply boundaries clear enough for implementation?
4. Are tool/structured-output/failure/trace requirements specific enough?
5. Are the test gates strong enough to prevent false-green implementation?
6. Does the plan prevent setup-agent executor copying and setup-specific policy
   leakage?
7. Does the plan preserve old MVP compatibility only as explicit fallback rather
   than target architecture?
8. What is missing before implementation can safely start?

## Output Format

Return a concise review report with:

```text
Verdict: GO | GO_WITH_FIXES | NO_GO

Blockers:
- ...

Concerns:
- ...

Non-blocking notes:
- ...

Required document fixes before implementation:
- ...

Optional improvements:
- ...

Evidence:
- cite specific files / sections / line anchors where possible
```

Do not include broad summaries before findings. Findings first.
