# S3.5 Post-Fix Review Brief

Status: ready for final fresh review after bounded repair
Owner: main-brain
Date: 2026-06-23

## Reviewer Role

Perform a fresh read-only adversarial review of the current S3.5 implementation
after the bounded repair from `17-implementation-fix-brief.md` and the
follow-up `trellis-check`.

Do not edit files.
Do not commit.
Do not run pytest.
Do not use YCE.
Do not use ACE.

Use direct file reads first. If you truly need search, use only narrow exact
`rg`.

## Requirement Authority

- `.trellis/tasks/04-28-runtime-story-dev-task/research/index.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-agent-harness.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-worker-family.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/modules/runtime-scheduler-governance.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/main-brain/implementation-leadership-rules.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3.5/01-PRD.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3.5/02-SDD-and-implementation-plan.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3.5/03-test-and-gate-plan.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3.5/07-implementation-brief.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3.5/16-implementation-review-adjudication.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3.5/17-implementation-fix-brief.md`

## Code In Scope

- `backend/rp/models/writer/worker_runtime_contracts.py`
- `backend/rp/runtime/rp_runtime_factory.py`
- `backend/rp/services/runtime/structured_output_runner.py`
- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- `backend/rp/services/writer/production_memory_maintenance_structured_output_runner.py`
- `backend/rp/services/writer/worker_execution_service.py`
- `backend/rp/tests/services/runtime/test_structured_output_runner.py`
- `backend/rp/tests/services/writer/test_memory_maintenance_worker_adapter.py`
- `backend/rp/tests/services/writer/test_worker_scheduler_service.py`

## Out Of Scope

Do not treat these unrelated dirty files as S3.5 review findings:

- `.gitignore`
- `.trellis/.template-hashes.json`
- `backend/rp/services/story/runtime_controller.py`
- `backend/rp/services/story/turn_domain_service.py`
- `backend/rp/tests/services/writer/test_longform_chapter_runtime_service.py`
- `backend/services/conversation_source.py`
- `backend/tests/test_conversation_source_api.py`

## What Was Repaired

The bounded repair slice targeted only these review findings:

1. top-level schema-version mismatch reason code now must surface as
   `memory_worker_output_schema_version_unsupported`;
2. production runner disabled + legacy compatibility disabled now must have an
   execution-level test proving explicit fail/degrade without legacy specialist;
3. production runner metadata now must be system-owned for runner mode / trace
   truth;
4. adapter trace summary now should expose the key safe runner trace fields.

`trellis-check` then additionally cleaned:

- one targeted mypy typing issue in
  `backend/rp/services/runtime/structured_output_runner.py`;
- one typed test helper issue in
  `backend/rp/tests/services/runtime/test_structured_output_runner.py`;
- three stale `type: ignore` comments in
  `backend/rp/tests/services/writer/test_worker_scheduler_service.py`.

## Gate Evidence Already Run

The latest recorded local verification for the repair slice is:

```text
python -m pytest -n auto \
  rp/tests/services/runtime/test_structured_output_runner.py \
  rp/tests/services/writer/test_memory_maintenance_worker_adapter.py \
  rp/tests/services/writer/test_worker_scheduler_service.py
```

Result:

```text
32 passed, 15 warnings
```

```text
python -m ruff check \
  backend/rp/services/writer/memory_maintenance_worker_adapter.py \
  backend/rp/services/writer/production_memory_maintenance_structured_output_runner.py \
  backend/rp/tests/services/writer/test_memory_maintenance_worker_adapter.py \
  backend/rp/tests/services/writer/test_worker_scheduler_service.py \
  backend/rp/tests/services/runtime/test_structured_output_runner.py
```

Result:

```text
All checks passed
```

## Reason-Code Closure Expectations

Review against the frozen S3.5 contract with this intended closure:

- `memory_worker_unknown_tool`: first runner unreachable because tool calls are
  disabled in S3.5;
- `memory_worker_repair_exhausted`: first runner unreachable because bounded
  repair is not implemented in S3.5;
- `memory_worker_stale_base`: owned by downstream governance/apply stale-base
  rejection rather than the runner/adapter itself.

Treat these as acceptable only if the current code/docs do not contradict that
ownership model.

## Review Questions

1. Are the previously accepted repair items now actually closed in code/tests?
2. Does the implementation now satisfy the S3.5 reason-code and trace contract
   without fresh drift?
3. Does the disabled-runner negative path now have honest execution proof?
4. Is there any remaining blocker before main-brain can treat S3.5 as
   code-complete pending final commit hygiene?

## Output Format

Return findings first:

```text
Verdict: GO | GO_WITH_FIXES | NO_GO

Blockers:
- ...

Concerns:
- ...

Non-blocking notes:
- ...

Required fixes before acceptance:
- ...

Evidence:
- cite specific files / line anchors where possible
```
