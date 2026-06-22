# S3c Check Record

Date: 2026-06-23
Reviewer: Codex exec review / main-brain adjudication
Scope: S3c governance routing and proposal handoff

## Inputs Read

- `execution/phase-5-implementation/S3/10-S3c-implementation-brief.md`
- S3 planning and prior-slice anchors:
  - `01-PRD.md`
  - `02-SDD-and-implementation-plan.md`
  - `03-test-and-gate-plan.md`
  - `09-S3b-implementation-result.md`
  - `S3b-check-record.md`
- Runtime/module anchors:
  - `research/modules/runtime-scheduler-governance.md`
  - `research/modules/runtime-memory-domain-block.md`
  - `research/modules/runtime-worker-family.md`
  - `research/story-runtime-stage-w5-scheduler-layer-development-spec.md`
- S3c code and tests:
  - `backend/rp/services/proposal/memory_candidate_proposal_adapter.py`
  - `backend/rp/services/proposal/post_write_governance_service.py`
  - `backend/rp/services/runtime/workflow_job_service.py`
  - `backend/rp/tests/services/proposal/test_memory_candidate_proposal_adapter.py`
  - `backend/rp/tests/services/proposal/test_memory_candidate_governance_routing.py`

YCE note:

- Main-brain ran YCE search before S3c implementation to locate proposal,
  governance, apply, base-ref, and legacy candidate handling code. No ACE search
  was used.

## Review Findings

### P1. Failed handoff was not durable if the request transaction rolled back

Reviewer finding:

- `PostWriteGovernanceService` marked the proposal job failed and then
  re-raised the exception.
- Under the normal request transaction model, re-raising can roll back the
  `mark_job_failed()` update, losing the terminal readable failure record and
  potentially leaving the job non-terminal.

Main-brain decision: accepted and fixed.

Fix:

- `_dispatch_proposal_governance()` now records `mark_job_failed(...)` and
  returns the failed job ref instead of re-raising.
- Added `_failure_code_from_exception()` so S3/apply failures preserve stable
  reason codes such as `memory_candidate_base_revision_unparseable`.
- Updated the invalid handoff test to assert a failed job ref and persisted
  failed job state without expecting an exception.

### P3. `.trellis/.template-hashes.json` includes local pycache entries

Reviewer finding:

- `.trellis/.template-hashes.json` contains local `__pycache__/*.pyc` hash
  entries.

Main-brain decision: not S3c scope; do not touch in this slice.

Reason:

- The file was already a visible unrelated worktree modification before S3c.
- The user explicitly requires not touching unrelated dirty files.
- It remains an external cleanup item, not part of S3c implementation.

## Scope Discipline

- S3 candidate kind remains `s3_memory_maintenance_candidate`; it is not hidden
  as `legacy_state_patch`.
- Existing `legacy_state_patch` behavior remains supported through the legacy
  builder path.
- Truth mutation still goes only through `ProposalApplyService`.
- S3c implements one honest first target subset:
  - S3 `plot_threads / plot.active_threads`
  - current apply target `Domain.PLOT_THREAD / plot_thread.active`
  - `append_item -> AppendEventOp`
- Unsupported S3 targets and operations fail closed.
- `base_block_revision_id` is converted to `base_refs[].revision`; it is never
  silently omitted.
- No setup-agent imports or harness-core changes were introduced.

## Verification

Focused command run from `H:\chatboxapp\backend` after the P1 fix:

```powershell
python -m pytest rp/tests/services/proposal/test_memory_candidate_proposal_adapter.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
```

Result:

```text
9 passed, 1 warning in 11.69s
```

Full S3c gate run from `H:\chatboxapp\backend` after the P1 fix:

```powershell
python -m pytest rp/tests/services/proposal/test_memory_candidate_proposal_adapter.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py rp/tests/services/proposal/test_proposal_workflow_service.py rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/memory/test_runtime_memory_contract_registry.py rp/tests/models/memory/test_memory_maintenance_candidate_contracts.py rp/tests/services/memory/test_memory_candidate_validation_service.py rp/tests/agent_runtime/test_s0_harness_substrate.py rp/tests/services/story/test_story_runtime_adapter_service.py rp/tests/services/writer/test_worker_scheduler_service.py
```

Result:

```text
69 passed, 1 warning in 77.63s
```

The warning is the existing Pydantic class-based `config` deprecation in
`backend/config.py`, outside S3c.
