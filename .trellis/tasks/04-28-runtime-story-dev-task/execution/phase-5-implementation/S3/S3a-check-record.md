# S3a Check Record

Date: 2026-06-23
Reviewer: PLeiA / Codex fresh reviewer
Scope: S3a registry and candidate contracts only

## Inputs Read

- `.trellis/tasks/04-28-runtime-story-dev-task/prd.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/check.jsonl`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/06-S3a-implementation-brief.md`
- S3 direct planning docs:
  - `01-PRD.md`
  - `02-SDD-and-implementation-plan.md`
  - `03-test-and-gate-plan.md`
  - `review-record.md`
  - `05-main-brain-adjudication.md`
- S3a direct source/spec anchors:
  - `research/modules/runtime-memory-domain-block.md`
  - `research/modules/runtime-worker-family.md`
  - `research/story-runtime-stage-w5-scheduler-layer-development-spec.md`
  - `research/story-runtime-memory-domain-block-worker-discussion.md`
  - `execution/phase-1-spec-freeze/acceptance-criteria.md`
- S3a code and tests in the requested review scope.

YCE note: the required YCE entrypoint was invoked from
`C:\Users\55473\.codex\skills\yce` with `--cwd "H:\chatboxapp"`, but returned
`spawn EPERM` before search execution. No ACE search was used. Review proceeded
through the user-allowed direct reads of known paths.

## Findings Fixed

1. Runtime registry tests computed expected five-domain/block topology from the
   implementation constants under test, which could hide a bad constant edit.
   Fixed by asserting the literal S3a brief topology in
   `test_runtime_memory_contract_registry.py`.

2. Extra-field rejection tests could pass for the wrong reason because one batch
   payload also had an empty `candidates` list. Fixed the DTO and validator tests
   to use otherwise valid candidate payloads when checking unknown extra fields.

3. `append_item` accepted `target_fact_id` / `target_fact_handle`, allowing a
   worker to preselect a backend-owned fact identity for an append. Fixed the
   validator to reject append operations that target an existing fact, and added
   regression coverage.

## Findings Not Fixed

- None in the S3a bounded review scope.

## Verification

Command run from `H:\chatboxapp\backend`:

```powershell
python -m pytest rp/tests/services/memory/test_memory_contract_registry.py rp/tests/services/memory/test_runtime_memory_contract_registry.py rp/tests/models/memory/test_memory_maintenance_candidate_contracts.py rp/tests/services/memory/test_memory_candidate_validation_service.py
```

Result:

```text
45 passed, 2 warnings in 0.40s
```

Warnings:

- Pydantic class-based `config` deprecation in `backend/config.py`.
- Pytest cache write warning for `backend/.pytest_cache` access denied.

Both warnings are outside the S3a review scope and did not affect the gate.

## Scope Discipline

No git commit was made. The review touched only S3a files plus this check
record. Unrelated visible worktree changes were not modified.
