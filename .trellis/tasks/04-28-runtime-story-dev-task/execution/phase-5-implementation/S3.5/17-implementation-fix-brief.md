# S3.5 Implementation Fix Brief

Status: ready for bounded implement-worker repair
Owner: main-brain
Date: 2026-06-23

## Implementer Role

Repair only the accepted S3.5 review findings from
`16-implementation-review-adjudication.md`.

Do not broaden scope.
Do not use YCE.
Do not use ACE.
Do not mutate git history.
Do not edit unrelated dirty files.

Use direct file reads and exact `rg` only.

## In Scope

### 1. Fix the top-level schema-version reason code

When worker output fails because
`schema_version != S3_MEMORY_WORKER_OUTPUT_SCHEMA_VERSION`, the top-level
failure reason seen by the adapter result must be
`memory_worker_output_schema_version_unsupported`, not
`memory_worker_structured_output_identity_mismatch`.

Preserve the current identity-mismatch behavior for the other confirmed
identity fields unless you need a tiny local refactor to keep the code clean.

### 2. Make system-owned runner metadata authoritative

Fix the production memory runner so model-provided metadata cannot override the
system-owned runner mode / runner trace truth.

Tests must assert the system-owned trace surface rather than a model-controlled
metadata field.

### 3. Add the missing disabled-runner + disabled-compatibility execution test

Add an execution-level test proving:

- production runner disabled or unavailable;
- `enable_legacy_longform_memory_worker_specialist_fallback=False`;
- result is an explicit failure/degrade path;
- `LongformSpecialistService.analyze()` is **not** called.

### 4. If locally cheap, surface key runner trace fields into adapter trace_summary

If this can be done without broad churn, surface the key system-owned fields
needed by the S3.5 trace contract into `WorkerResult.trace_summary`:

- runner mode
- schema name / schema version
- provider id / model id when safe

Do not turn this into a large trace redesign.

## Out Of Scope

Do not do any of the following in this repair slice:

- implement a real tool loop;
- implement bounded repair logic;
- add a new closed-world taxonomy for all worker failure codes;
- redesign proposal/apply or stale-base ownership;
- change unrelated story/runtime/product behavior;
- touch these unrelated dirty files:
  - `.gitignore`
  - `.trellis/.template-hashes.json`
  - `backend/rp/services/story/runtime_controller.py`
  - `backend/rp/services/story/turn_domain_service.py`
  - `backend/rp/tests/services/writer/test_longform_chapter_runtime_service.py`
  - `backend/services/conversation_source.py`
  - `backend/tests/test_conversation_source_api.py`

## Primary File Targets

- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- `backend/rp/services/writer/production_memory_maintenance_structured_output_runner.py`
- `backend/rp/tests/services/writer/test_memory_maintenance_worker_adapter.py`
- `backend/rp/tests/services/writer/test_worker_scheduler_service.py`

Possible small test touch if needed:

- `backend/rp/tests/services/runtime/test_structured_output_runner.py`

## Required Verification

Run only narrow local verification if needed, and use `-n auto` for pytest.

Target commands:

```text
python -m pytest -n auto \
  rp/tests/services/runtime/test_structured_output_runner.py \
  rp/tests/services/writer/test_memory_maintenance_worker_adapter.py \
  rp/tests/services/writer/test_worker_scheduler_service.py
```

```text
python -m ruff check \
  backend/rp/services/writer/memory_maintenance_worker_adapter.py \
  backend/rp/services/writer/production_memory_maintenance_structured_output_runner.py \
  backend/rp/tests/services/writer/test_memory_maintenance_worker_adapter.py \
  backend/rp/tests/services/writer/test_worker_scheduler_service.py \
  backend/rp/tests/services/runtime/test_structured_output_runner.py
```

## Expected Response

Return:

```text
Changed files:
- ...

What changed:
- ...

Local verification run:
- exact command / result

Known limitations:
- ...
```
