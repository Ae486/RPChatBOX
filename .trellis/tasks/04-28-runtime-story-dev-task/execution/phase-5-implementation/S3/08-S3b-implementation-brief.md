# S3b Implementation Brief — Memory Worker Adapter And Fake Harness Path

Status: ready for implement worker
Date: 2026-06-23

## Mission

Implement the S3b slice only:

```text
MemoryMaintenanceWorker adapter
  -> fake/scripted structured-output path
  -> candidate batch / no-op / failure WorkerResult mapping
  -> tests proving no truth mutation and no setup-agent leakage
```

S3b builds on S3a registry/candidate validation. It does not implement proposal
workflow, governed apply, maintenance lock, stale-base apply rejection, or UI.

## Required Reading

Read before editing code:

- `execution/phase-5-implementation/S3/01-PRD.md`
- `execution/phase-5-implementation/S3/02-SDD-and-implementation-plan.md`
- `execution/phase-5-implementation/S3/03-test-and-gate-plan.md`
- `execution/phase-5-implementation/S3/06-S3a-implementation-brief.md`
- `execution/phase-5-implementation/S3/07-S3a-implementation-result.md`
- `execution/phase-5-implementation/S3/S3a-check-record.md`
- `research/modules/runtime-agent-harness.md`
- `research/modules/runtime-worker-family.md`
- `research/modules/runtime-memory-domain-block.md`
- `research/modules/runtime-context-packet.md`
- `execution/phase-1-spec-freeze/acceptance-criteria.md`

Use YCE for codebase search. Do not use ACE.

## Current Code Evidence

Relevant current files:

- `backend/rp/services/writer/worker_execution_service.py`
- `backend/rp/services/writer/worker_registry_service.py`
- `backend/rp/models/writer/worker_runtime_contracts.py`
- `backend/rp/services/story/runtime_adapter_service.py`
- `backend/rp/agent_runtime/story/story_harness.py`
- `backend/rp/agent_runtime/kernel/runtime_tool_contracts.py`
- `backend/rp/tests/services/writer/test_worker_scheduler_service.py`
- `backend/rp/tests/agent_runtime/test_s0_harness_substrate.py`

Current-state finding:

- `WorkerExecutionService._run_longform_memory_worker()` still calls
  `LongformSpecialistService` and adapts `SpecialistResultBundle` to
  `candidate_kind="legacy_state_patch"`.
- `StoryRuntimeAdapterService.adapt_specialist_bundle_to_worker_result()` is a
  compatibility bridge and should remain tested until the new S3 path replaces
  it slice-by-slice.
- `story_harness.py` is still a minimal S0 test harness with scripted LLM and
  `noop` fake tool. Do not move memory policy into this harness core.

## Required Design

Add a new adapter path for S3 memory maintenance worker output.

Suggested placement:

- `backend/rp/services/writer/memory_maintenance_worker_adapter.py`
- tests under:
  - `backend/rp/tests/services/writer/test_memory_maintenance_worker_adapter.py`
  - and, only if wiring into `WorkerExecutionService`, a focused test in
    `backend/rp/tests/services/writer/test_worker_scheduler_service.py` or a new
    adjacent file.

The adapter should consume:

- `WorkerExecutionRequest`;
- `RuntimeWorkerRegistration`;
- optional `WorkerContextPacket`;
- scripted/fake structured output for tests;
- S3a `MemoryMaintenanceCandidateBatch` and
  `MemoryCandidateValidationService`.

The adapter should emit an existing `WorkerResult` with one of these semantic
outcomes:

1. Candidate batch
   - `result_status=COMPLETED`;
   - `proposal_candidates[]` contains a clearly named S3 candidate kind such as
     `s3_memory_maintenance_candidate`;
   - payload carries the validated candidate batch;
   - metadata / trace marks `source_of_truth=false` and
     `authoritative_mutation=false`;
   - no Core/projection mutation occurs.

2. No-op
   - `result_status=SKIPPED` or `COMPLETED` with explicit no-op metadata;
   - no proposal candidate;
   - trace has readable no-op reason.

3. Failure
   - `result_status=FAILED` for invalid structured output or validator failure;
   - `validation_findings[]` carries stable reason codes;
   - no proposal candidate;
   - trace identifies whether failure came from schema parse, validation, or
     fake execution.

Exact enum choice for no-op is engineering-owned, but it must be explicit and
tested.

## Harness Boundary

S3b may introduce a small fake/scripted worker executor or adapter-level
structured-output port. It must not hard-code memory policy into
`rp.agent_runtime.kernel` or generic `story_harness.py`.

Allowed:

- a memory worker adapter that uses harness-shaped inputs/outputs;
- a fake structured-output runner for deterministic tests;
- a future-facing seam that can later be backed by a real story harness/model
  call.

Forbidden:

- setup-agent imports;
- setup executor reuse;
- private tool protocol hidden inside memory service;
- proposal/apply mutation;
- broad rewrite of existing scheduler execution.

## Worker Registry / Execution Wiring

Conservative default:

- Keep existing legacy longform specialist path passing.
- Add new adapter as injectable or separately testable first.
- If wiring into `WorkerExecutionService`, use explicit injection / metadata so
  existing compatibility tests still pass and new S3 path is deliberate, not an
  accidental behavior change.

Do not remove `legacy_state_patch` compatibility in S3b. That boundary is tested
and will be narrowed in S3c.

## Tests Required

Minimum new tests:

- valid structured candidate batch returns a `WorkerResult` candidate with
  `candidate_kind="s3_memory_maintenance_candidate"` or another explicitly named
  S3 kind;
- candidate result carries `source_of_truth=false` and
  `authoritative_mutation=false` in metadata or payload;
- no-op structured output returns explicit no-op result and no proposal
  candidate;
- invalid schema returns failure result with stable reason code;
- validator-rejected candidate returns failure result and forwards validation
  reason codes;
- setup-agent import leak test remains green;
- existing legacy worker execution test remains green.

Regression commands should include S3a tests plus:

```powershell
python -m pytest rp/tests/agent_runtime/test_s0_harness_substrate.py
python -m pytest rp/tests/services/writer/test_worker_scheduler_service.py
python -m pytest rp/tests/services/story/test_story_runtime_adapter_service.py
```

Add exact new test paths after implementation.

## Gate Commands

Run from `H:\chatboxapp\backend`:

```powershell
python -m pytest rp/tests/services/memory/test_runtime_memory_contract_registry.py rp/tests/models/memory/test_memory_maintenance_candidate_contracts.py rp/tests/services/memory/test_memory_candidate_validation_service.py
python -m pytest rp/tests/agent_runtime/test_s0_harness_substrate.py
python -m pytest rp/tests/services/writer/test_worker_scheduler_service.py
python -m pytest rp/tests/services/story/test_story_runtime_adapter_service.py
```

Also run any new S3b test file(s).

## Forbidden In S3b

- Do not implement proposal workflow.
- Do not call `ProposalWorkflowService` or `ProposalApplyService`.
- Do not persist Core/projection truth.
- Do not implement lock matrix.
- Do not remove or rename legacy compatibility behavior.
- Do not commit from the implement worker.
- Do not touch unrelated visible worktree changes.

## Expected Implementer Output

Summarize:

- files changed;
- exact tests run and results;
- whether S3b was adapter-only or wired into `WorkerExecutionService`;
- any deviations from this brief;
- remaining risks for S3c governance handoff.
