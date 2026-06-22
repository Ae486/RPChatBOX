# S3b Check Record

Date: 2026-06-23
Reviewer: PLeiA / Codex fresh reviewer
Scope: S3b memory-maintenance worker adapter only

## Inputs Read

- `.trellis/tasks/04-28-runtime-story-dev-task/check.jsonl`
- `.trellis/tasks/04-28-runtime-story-dev-task/execution/phase-5-implementation/S3/08-S3b-implementation-brief.md`
- S3 planning and prior-slice anchors:
  - `01-PRD.md`
  - `02-SDD-and-implementation-plan.md`
  - `03-test-and-gate-plan.md`
  - `06-S3a-implementation-brief.md`
  - `07-S3a-implementation-result.md`
  - `S3a-check-record.md`
- Runtime/module anchors:
  - `research/modules/runtime-agent-harness.md`
  - `research/modules/runtime-worker-family.md`
  - `research/modules/runtime-memory-domain-block.md`
  - `research/modules/runtime-context-packet.md`
  - `execution/phase-1-spec-freeze/acceptance-criteria.md`
- Backend quality index:
  - `.trellis/spec/backend/index.md`
- S3b code and tests:
  - `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
  - `backend/rp/tests/services/writer/test_memory_maintenance_worker_adapter.py`

YCE note:

- The required YCE wrapper was invoked from
  `C:\Users\55473\.codex\skills\yce` with `--cwd "H:/chatboxapp"`, but the
  wrapper returned `spawn EPERM`.
- `node .\vendor\yce-engine\yce-engine.mjs --project "H:/chatboxapp" --query ...`
  was then used as the YCE direct engine fallback and returned a code-context
  result. No ACE search was used.

## Findings Fixed

1. Candidate batch schema version was fail-open.

   The adapter validated the outer worker output schema version, but accepted
   any non-empty `MemoryMaintenanceCandidateBatch.schema_version`. That allowed
   an unsupported candidate-batch contract to reach a completed
   `proposal_candidates[]` result.

   Fix:

   - added `S3_MEMORY_MAINTENANCE_CANDIDATE_BATCH_SCHEMA_VERSION`;
   - fail-closed mismatched candidate-batch schema versions with
     `memory_worker_candidate_batch_schema_version_unsupported`;
   - aligned the S3b candidate payload fixture with the S3a candidate contract
     version;
   - added regression coverage for candidate-batch schema mismatch.

2. Worker-output schema and identity fail-closed coverage was too thin.

   The adapter already handled unsupported outer worker output schema versions
   and worker identity mismatches, but S3b tests covered only missing schema
   version and candidate-batch identity mismatch.

   Fix:

   - added explicit unsupported worker-output schema version coverage;
   - added explicit worker-output `worker_id` mismatch coverage.

## Findings Not Fixed

- None in the bounded S3b review scope.

## Scope Discipline

- Adapter-only boundary is preserved.
- No setup-agent import, setup executor reuse, proposal/apply service call, Core
  truth mutation, projection truth mutation, or Runtime Workspace truth write was
  introduced.
- Candidate, no-op, and failure mappings remain `WorkerResult` mappings only.
- Non-truth metadata remains explicit with `source_of_truth=false` and
  `authoritative_mutation=false`.
- Existing legacy `legacy_state_patch` scheduler/execution behavior remains
  untouched.
- No git commit was made.
- Unrelated visible worktree changes were not modified.

## Verification

Command run from `H:\chatboxapp\backend`:

```powershell
python -m pytest rp/tests/services/writer/test_memory_maintenance_worker_adapter.py
```

Result:

```text
11 passed, 2 warnings in 0.71s
```

Required gate command run from `H:\chatboxapp\backend`:

```powershell
python -m pytest rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/memory/test_runtime_memory_contract_registry.py rp/tests/models/memory/test_memory_maintenance_candidate_contracts.py rp/tests/services/memory/test_memory_candidate_validation_service.py rp/tests/agent_runtime/test_s0_harness_substrate.py rp/tests/services/story/test_story_runtime_adapter_service.py rp/tests/services/writer/test_worker_scheduler_service.py
```

Direct run initially produced environment errors in
`test_worker_scheduler_service.py` because this Windows sandbox could not access
pytest-created mode-700 temp directories under the default temp root, and SQLite
could not write on `H:` paths. The same gate was rerun in one Python process
that:

- patched `os.mkdir` for pytest-created temp directories to use normal Windows
  permissions;
- set `TMP` / `TEMP` and `--basetemp` under
  `C:\Users\55473\.codex\skills\yce\tmp`, where SQLite write probes succeed.

Result:

```text
45 passed, 2 warnings in 20.87s
```

Warnings:

- existing Pydantic class-based `config` deprecation in `backend/config.py`;
- pytest cache write warning for `backend/.pytest_cache` access denied.

Both warnings are outside the S3b review scope and did not affect the gate.

## Main-Brain Final Rerun

After the reviewer fixes, main-brain reran the required gate directly from
`H:\chatboxapp\backend` using the standard command:

```powershell
python -m pytest rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/memory/test_runtime_memory_contract_registry.py rp/tests/models/memory/test_memory_maintenance_candidate_contracts.py rp/tests/services/memory/test_memory_candidate_validation_service.py rp/tests/agent_runtime/test_s0_harness_substrate.py rp/tests/services/story/test_story_runtime_adapter_service.py rp/tests/services/writer/test_worker_scheduler_service.py
```

Result:

```text
45 passed, 1 warning in 17.80s
```

The final main-brain gate does not depend on the temp-directory workaround. The
remaining warning is the existing Pydantic class-based `config` deprecation in
`backend/config.py`, outside S3b.
