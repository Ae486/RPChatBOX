# S3g-a Service-Size Cleanup Implementation Brief

Status: ready for implement sub-agent
Date: 2026-06-23
Owner: main-brain

## Implementer Role

You are implementing S3g-a only. This is a mechanical service-size cleanup slice.

Do not redesign S3. Do not start S3g-b production executor migration. Do not
change behavior intentionally.

Use YCE for codebase search. Do not use ACE. Do not load external skills.

Do not run git mutation commands: no `git add`, `git commit`, `git checkout`,
`git reset`, or `git stash`. Read-only git commands are allowed if needed.

Make the edit and return. The main-brain will run the full verification gate and
own the commit.

## Files In Scope

Only these production files are in scope:

- `backend/rp/services/memory/memory_candidate_validation_service.py`
- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- `backend/rp/services/proposal/post_write_governance_service.py`

Tests may be adjusted only if the mechanical refactor requires import or helper
name updates, but the preferred outcome is no test-file edits.

## Files Out Of Scope

Do not edit:

- `backend/rp/services/writer/worker_execution_service.py`
- `backend/rp/runtime/rp_runtime_factory.py`
- `backend/rp/tests/services/writer/test_worker_scheduler_service.py`
- any story service dirty in the current worktree;
- any unrelated visible dirty file.

Known unrelated dirty files that must not be staged, reverted, or edited:

- `.gitignore`
- `.trellis/.template-hashes.json`
- `backend/rp/services/story/runtime_controller.py`
- `backend/rp/services/story/turn_domain_service.py`
- `backend/rp/tests/services/writer/test_longform_chapter_runtime_service.py`
- `backend/services/conversation_source.py`
- `backend/tests/test_conversation_source_api.py`

## Current Service-Size Failures To Fix

`python backend/rp/devtools/check_service_sizes.py` reports these S3-owned new
hard offenders:

- `memory/memory_candidate_validation_service.py::MemoryCandidateValidationService._validate_operation`
- `proposal/post_write_governance_service.py::PostWriteGovernanceService._dispatch_proposal_governance`
- `writer/memory_maintenance_worker_adapter.py::MemoryMaintenanceWorkerAdapter._candidate_batch_result`

The goal is to reduce those functions under the hard function limit by splitting
helper methods without changing behavior.

Older baseline drift in `story/runtime_identity_service.py` and
`story/turn_domain_service.py` is not part of S3g-a.

## Required Refactor Shape

### 1. MemoryCandidateValidationService

Split `_validate_operation` into smaller private helpers. Recommended helper
boundaries:

- forbidden/unsupported operation kind;
- field support and registry operation support;
- append/update/remove payload validation;
- duplicate target detection.

Keep existing error codes, messages, and ordering unless the current tests force
a different but equivalent ordering.

### 2. MemoryMaintenanceWorkerAdapter

Split `_candidate_batch_result` into smaller private helpers. Recommended helper
boundaries:

- candidate-batch schema version validation;
- candidate-batch worker/phase identity validation;
- validation-error `WorkerResult` construction;
- successful proposal-candidate payload construction.

Keep the successful `WorkerResult` payload, metadata, and trace shape identical.

### 3. PostWriteGovernanceService

Split `_dispatch_proposal_governance` into smaller private helpers. Recommended
helper boundaries:

- select proposal results;
- create/start proposal governance job;
- route worker results to proposal handoffs;
- complete or fail the proposal governance job.

Keep the job status, failure metadata, failure reason codes, proposal refs, and
governance metadata shape identical.

## Behavior Guardrails

- No new proposal/apply semantics.
- No new memory operation kinds.
- No runner/harness/executor migration.
- No setup-agent import.
- No reason-code alias changes.
- No changes to public method signatures.
- No direct truth mutation path.
- No broad formatting churn.

## Expected Local Verification For Main-Brain

The implementer may skip running the full gate and simply report changed files.
The main-brain will run:

```powershell
cd H:\chatboxapp\backend
python -m pytest rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
python -m pytest tests/test_story_runtime_s3_memory_worker_e2e.py
python -m ruff check rp/services/memory/memory_candidate_validation_service.py rp/services/writer/memory_maintenance_worker_adapter.py rp/services/proposal/post_write_governance_service.py
```

From repo root:

```powershell
python backend/rp/devtools/check_service_sizes.py
```

## Expected Response

Return:

```text
Changed files:
- ...

What changed:
- ...

Notes:
- any skipped verification or risk
```
