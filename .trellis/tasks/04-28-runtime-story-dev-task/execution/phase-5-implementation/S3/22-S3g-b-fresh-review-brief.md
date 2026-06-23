# S3g-b Fresh Review Brief

Status: ready for read-only Codex review
Date: 2026-06-23
Owner: main-brain

## Role

You are a fresh reviewer. You did not implement S3g-b. Review the current
working tree against the S3g-b brief and report GO / NO-GO.

Use YCE for codebase search. Do not use ACE. Exact known file reads and `git
diff`/`git status` are allowed. Do not modify files. Do not run pytest. Do not
run git mutation commands.

## Source Documents

Read:

- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/21-S3g-b-production-executor-compatibility-brief.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/main-brain/operating-rules.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/main-brain/implementation-leadership-rules.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-worker-family.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-agent-harness.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-scheduler-governance.md`

## In-Scope Diff

Review only these S3g-b files:

- `backend/rp/services/writer/worker_execution_service.py`
- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- `backend/rp/runtime/rp_runtime_factory.py`
- `backend/rp/tests/services/writer/test_worker_scheduler_service.py`

Known unrelated dirty files must not affect the verdict unless the S3g-b diff
depends on them:

- `.gitignore`
- `.trellis/.template-hashes.json`
- `backend/rp/services/story/runtime_controller.py`
- `backend/rp/services/story/turn_domain_service.py`
- `backend/rp/tests/services/writer/test_longform_chapter_runtime_service.py`
- `backend/services/conversation_source.py`
- `backend/tests/test_conversation_source_api.py`

## Pre-Fed Verification Evidence

Main-brain ran these commands from the current working tree:

```text
H:\chatboxapp\backend> python -m pytest -n auto rp/tests/services/writer/test_worker_scheduler_service.py
Result: 4 passed, 15 warnings.

H:\chatboxapp\backend> python -m pytest -n auto rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
Result: 15 passed, 15 warnings.

H:\chatboxapp\backend> python -m pytest -n auto tests/test_story_runtime_s3_memory_worker_e2e.py
Result: 4 passed, 75 warnings.

H:\chatboxapp\backend> python -m ruff check rp/services/writer/worker_execution_service.py rp/services/writer/memory_maintenance_worker_adapter.py rp/runtime/rp_runtime_factory.py rp/tests/services/writer/test_worker_scheduler_service.py
Result: All checks passed.

H:\chatboxapp> python backend/rp/devtools/check_service_sizes.py
Result: FAIL only because known story-service baseline grew:
- story/runtime_identity_service.py::StoryRuntimeIdentityService is 1662 lines, baseline allows 1578
- story/turn_domain_service.py::StoryTurnDomainService is 1848 lines, baseline allows 1743
- story/runtime_identity_service.py is 1714 lines, baseline allows 1628
- story/turn_domain_service.py is 1960 lines, baseline allows 1826
- story/turn_domain_service.py::StoryTurnDomainService.__init__ is 144 lines, baseline allows 142
- story/turn_domain_service.py::StoryTurnDomainService.trigger_post_write is 200 lines, baseline allows 150
No S3g-b target file appeared in service-size errors.
```

## Review Checklist

Answer these points directly:

1. Does `WorkerExecutionService` use `MemoryMaintenanceWorkerAdapter` for
   `LongformMemoryWorker` when an adapter structured-output runner exists?
2. Does the adapter path avoid `LongformSpecialistService.analyze()` and return
   an empty `SpecialistResultBundle`?
3. Is legacy specialist execution now explicit compatibility mode only, with
   stable metadata/trace including executor mode, compatibility reason, and
   `s3_executor_migration_complete=False`?
4. Does `rp_runtime_factory.py` explicitly wire the adapter and compatibility
   boundary without claiming full production executor migration?
5. Do tests cover adapter-runner path, explicit legacy fallback, and factory
   wiring?
6. Is there any framework/product leakage, setup-agent dependency, direct truth
   mutation, or proposal/apply behavior change?
7. Is the remaining production structured-output runner gap correctly left as a
   residual compatibility gap?

## Output Format

Return:

```text
Verdict: GO or NO-GO

Blockers:
- ...

Concerns:
- ...

Evidence:
- ...

Residual gap:
- ...
```

If there are no blockers or concerns, say so explicitly.
