# S3c Implementation Brief — Governance Routing And Proposal Handoff

Status: ready for implement worker
Date: 2026-06-23

## Mission

Implement the S3c slice only:

```text
s3_memory_maintenance_candidate WorkerResult
  -> explicit S3 candidate to proposal adapter
  -> governance routing through existing ProposalWorkflowService
  -> review-required / direct-apply / blocked-failure evidence
  -> no truth mutation outside ProposalApplyService
```

S3c builds on:

- S3a registry / candidate DTO / validation service;
- S3b memory worker adapter and candidate kind
  `s3_memory_maintenance_candidate`.

S3c must not implement the full maintenance lock matrix, review UI editing,
branch rollback invalidation, broad schema migration, or a new apply engine.

## Required Reading

Read before editing code:

- `execution/phase-5-implementation/S3/01-PRD.md`
- `execution/phase-5-implementation/S3/02-SDD-and-implementation-plan.md`
- `execution/phase-5-implementation/S3/03-test-and-gate-plan.md`
- `execution/phase-5-implementation/S3/08-S3b-implementation-brief.md`
- `execution/phase-5-implementation/S3/09-S3b-implementation-result.md`
- `execution/phase-5-implementation/S3/S3b-check-record.md`
- `research/modules/runtime-scheduler-governance.md`
- `research/modules/runtime-memory-domain-block.md`
- `research/modules/runtime-worker-family.md`
- `research/modules/runtime-workspace-ledger-trace.md`
- `research/story-runtime-stage-w5-scheduler-layer-development-spec.md`
- `.trellis/spec/backend/rp-shared-core-mutation-kernel-direct-edit.md`
- `.trellis/spec/backend/rp-core-state-base-revision-conflict-enforcement.md`
- `.trellis/spec/backend/rp-worker-memory-tool-permission-boot-contract.md`

Use YCE for codebase search. Do not use ACE.

## Current Code Evidence

Relevant current files:

- `backend/rp/services/proposal/post_write_governance_service.py`
- `backend/rp/services/proposal/workflow_service.py`
- `backend/rp/services/proposal/apply_service.py`
- `backend/rp/services/core_state/legacy_state_patch_proposal_builder.py`
- `backend/rp/services/runtime/workflow_job_service.py`
- `backend/rp/services/memory/object_mapper.py`
- `backend/rp/services/story/state_apply_service.py`
- `backend/rp/models/proposal/post_write_policy.py`
- `backend/rp/models/memory/crud.py`
- `backend/rp/models/proposal/core_mutation.py`
- `backend/rp/tests/services/proposal/test_proposal_workflow_service.py`

Current-state findings:

- `PostWriteGovernanceService._proposal_inputs_from_candidate()` accepts only
  `candidate_kind="legacy_state_patch"`.
- `ProposalWorkflowService.submit_and_route()` already persists proposals,
  routes `REVIEW_REQUIRED` without apply, and routes `NOTIFY_APPLY` / `SILENT`
  to `ProposalApplyService`.
- `ProposalApplyService` already enforces `base_refs` revision conflicts and is
  the only deterministic authoritative mutation owner.
- Existing apply backend still uses old `Domain` enum and
  `ObjectRef.revision: int`; S3a candidate `target_domain` strings and
  `base_block_revision_id: str` need an explicit adapter bridge.
- `StoryStateApplyService` currently allows only legacy backend fields. S3c
  must not pretend a direct apply succeeded if the target cannot be applied by
  the current backend.
- When `_dispatch_proposal_governance()` raises after marking the job running,
  the current code has no generic `mark_job_failed(job_id=...)` path. S3c must
  not leave invalid S3 handoff failures as permanently running jobs.

## Required Design

### 1. Add a named S3 proposal adapter

Suggested placement:

- `backend/rp/services/proposal/memory_candidate_proposal_adapter.py`
- tests under:
  - `backend/rp/tests/services/proposal/test_memory_candidate_proposal_adapter.py`
  - focused governance integration tests beside existing proposal tests.

The adapter should consume:

- `MemoryRuntimeIdentity`;
- story id and mode;
- one S3b proposal candidate dict with
  `candidate_kind="s3_memory_maintenance_candidate"`;
- S3a `MemoryMaintenanceCandidateBatch`;
- `MemoryCandidateValidationService`.

The adapter should emit:

- zero or more `ProposalSubmitInput`;
- `WorkerProposalGovernanceMetadata`-compatible source/base/trace metadata;
- stable failure errors for unsupported targets, unsupported operations,
  invalid payloads, and base-revision bridge failures.

Do not hide this under `LegacyStatePatchProposalBuilder`. That builder remains
only for the old compatibility candidate kind.

### 2. Preserve S3 semantic identity

The public semantic boundary for new memory-worker output is:

```text
s3_memory_maintenance_candidate
```

Tests must fail if the new path is visible only as `legacy_state_patch`.

Allowed implementation shape:

```text
S3 candidate batch
  -> MemoryCandidateProposalAdapter
  -> canonical ProposalSubmitInput / CoreMutationEnvelope
  -> existing ProposalWorkflowService
  -> existing ProposalApplyService
```

Required metadata:

- original S3 candidate kind;
- S3 target domain and block id;
- worker id and phase;
- `source_of_truth=false`;
- `authoritative_mutation=false` before apply;
- source refs and trace refs;
- base revision bridge details.

### 3. Make the base-revision bridge explicit

S3a uses:

```text
base_block_revision_id: str
```

Current apply enforcement uses:

```text
ProposalSubmitInput.base_refs[].revision: int
```

S3c must implement one explicit bridge function. Minimum accepted forms:

- `"1"` -> revision `1`;
- `"block-revision-1"` -> revision `1`.

Anything else must fail closed before proposal submit with a stable reason code,
for example:

```text
memory_candidate_base_revision_unparseable
```

The adapter must never silently omit `base_refs` for S3 candidates. Missing or
unparseable base revision is a blocked/invalid handoff, not a model repair
request.

### 4. Keep direct apply honest

`direct_apply_allowed` may reuse current `PolicyDecision.NOTIFY_APPLY`, but only
if the target maps to a current apply-supported authoritative object and the
apply result actually changes the formal Core state / compatibility mirror.

Do not count a call to `ProposalApplyService` as success if
`StoryStateApplyService` ignores the target field.

For S3c, implement only a small vertical target subset if needed. Acceptable
first target:

```text
S3 domain/block: plot_threads / plot.active_threads
Current apply target: Domain.PLOT_THREAD / plot_thread.active
Operation: append_item -> AppendEventOp
```

Unsupported S3 domains/blocks should fail closed with a readable reason, not
fall back to legacy labels or raw dict mutation.

### 5. Do not leave failed handoff jobs running

If S3 candidate parsing, validation, mapping, or proposal submit fails after
`PostWriteGovernanceService` creates and marks a proposal job running, S3c must
record a terminal readable failure on that job.

Suggested support:

- add a generic `RuntimeWorkflowJobService.mark_job_failed(job_id, reason,
  metadata)` method if no existing method fits;
- catch S3 handoff failures in `_dispatch_proposal_governance()`;
- store stable reason codes and safe details in job metadata;
- re-raise only if the existing calling contract requires it, but never leave
  the job in `running`.

This is not the full S3d lock matrix. It is the minimum failure receipt required
for S3c.

## Governance Mapping For S3c

| S3 term | Current-code route | Required S3c behavior |
| --- | --- | --- |
| `review_required` | `PolicyDecision.REVIEW_REQUIRED` | Persist proposal with review-required status; do not apply; preserve S3 metadata. |
| `direct_apply_allowed` | `PolicyDecision.NOTIFY_APPLY` | Submit proposal and apply through `ProposalApplyService`; apply is the only truth mutation. |
| `no_op` | S3b `WorkerResultStatus.SKIPPED` | No proposal; no apply; existing governance dispatch should skip it. |
| `blocked` / invalid | adapter / validation / mapping failure | No proposal or failed proposal; no apply; job has readable failure reason. |
| legacy compatibility | `legacy_state_patch` | Existing behavior remains untouched and tested. |

`PolicyDecision.SILENT` must not hide invalid S3 outcomes. If S3c sees a valid
S3 candidate that policy maps to `SILENT`, either treat it as a deliberate
direct-apply policy outcome with explicit trace, or keep the first S3 policy
tests on `REVIEW_REQUIRED` / `NOTIFY_APPLY` only and document the deferred
mapping. Invalid S3 output must never become `SILENT` success.

## Tests Required

Minimum new tests:

- adapter parses a S3b candidate payload and emits a canonical
  `ProposalSubmitInput`;
- emitted proposal input preserves the named S3 boundary in metadata/trace;
- `base_block_revision_id="block-revision-1"` becomes a `base_refs` revision
  of `1`;
- missing / unparseable base revision fails closed before proposal submit;
- unsupported S3 domain/block fails closed with stable reason code;
- unsupported S3 operation fails closed with stable reason code;
- review-required S3 candidate persists a proposal and does not apply;
- direct-apply S3 candidate goes through `ProposalApplyService` and mutates only
  through apply;
- invalid S3 handoff marks the proposal governance job failed or otherwise
  terminal with a readable reason, and does not leave it running;
- existing `legacy_state_patch` behavior remains green;
- S3b adapter tests remain green.

Regression commands should include:

```powershell
python -m pytest rp/tests/services/proposal/test_memory_candidate_proposal_adapter.py
python -m pytest rp/tests/services/proposal/test_proposal_workflow_service.py
python -m pytest rp/tests/services/writer/test_memory_maintenance_worker_adapter.py
python -m pytest rp/tests/services/writer/test_worker_scheduler_service.py
python -m pytest rp/tests/services/story/test_story_runtime_adapter_service.py
```

Add exact new test paths after implementation.

## Gate Commands

Run from `H:\chatboxapp\backend`:

```powershell
python -m pytest rp/tests/services/proposal/test_memory_candidate_proposal_adapter.py rp/tests/services/proposal/test_proposal_workflow_service.py rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/memory/test_runtime_memory_contract_registry.py rp/tests/models/memory/test_memory_maintenance_candidate_contracts.py rp/tests/services/memory/test_memory_candidate_validation_service.py rp/tests/agent_runtime/test_s0_harness_substrate.py rp/tests/services/story/test_story_runtime_adapter_service.py rp/tests/services/writer/test_worker_scheduler_service.py
```

Also run any new focused governance test file created during implementation.

## Forbidden In S3c

- Do not replace `ProposalWorkflowService` or `ProposalApplyService`.
- Do not mutate Core/projection truth outside `ProposalApplyService`.
- Do not expose S3 candidates as undifferentiated `legacy_state_patch`.
- Do not broaden harness core.
- Do not import or reuse setup-agent executor logic.
- Do not silently omit base refs for S3 candidates.
- Do not mark ignored direct-apply targets as successful.
- Do not implement the full S3d lock matrix in this slice.
- Do not touch unrelated visible worktree changes.

## Expected Implementer Output

Summarize:

- files changed;
- exact S3 target subset implemented;
- exact governance mapping used for review-required/direct-apply/blocked;
- whether a generic job failure method was added;
- exact tests run and results;
- any deviations from this brief;
- remaining risks for S3d lock/stale-base integration.
