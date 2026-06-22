# S3d Implementation Brief — Maintenance Lock And Stale-Base Integration

Status: ready for implement worker
Date: 2026-06-23

## Mission

Implement the S3d slice only:

```text
current-branch maintenance blockers
  -> deterministic lock read model
  -> operation guard for blocked/allowed action families
  -> stale-base failure remains deterministic proposal/apply behavior
  -> terminal proposal/job state clears the blocker
```

S3d builds on:

- S3a memory registry / candidate DTO / validation service;
- S3b memory worker adapter and structured result variants;
- S3c named S3 candidate to proposal handoff and explicit base-ref bridge.

S3d must not rework the S3 candidate contract, worker adapter, harness core,
proposal apply engine, or UI review editor. This slice adds the missing
deterministic lock decision surface around the already-landed S3 path.

## Required Reading

Read before editing code:

- `execution/phase-5-implementation/S3/01-PRD.md`
- `execution/phase-5-implementation/S3/02-SDD-and-implementation-plan.md`
- `execution/phase-5-implementation/S3/03-test-and-gate-plan.md`
- `execution/phase-5-implementation/S3/10-S3c-implementation-brief.md`
- `execution/phase-5-implementation/S3/11-S3c-implementation-result.md`
- `execution/phase-5-implementation/S3/S3c-check-record.md`
- `research/modules/runtime-scheduler-governance.md`
- `research/modules/runtime-turn-intake-settlement.md`
- `research/modules/runtime-workspace-ledger-trace.md`
- `research/modules/runtime-memory-domain-block.md`
- `research/story-runtime-stage-w5-scheduler-layer-development-spec.md`
- `research/story-runtime-maintenance-lock-and-kx-window-analysis.md`
- `.trellis/spec/backend/rp-core-state-base-revision-conflict-enforcement.md`
- `.trellis/spec/backend/rp-shared-core-mutation-kernel-direct-edit.md`
- `.trellis/spec/backend/rp-worker-memory-tool-permission-boot-contract.md`

Use YCE for codebase search. Do not use ACE. Known file reads are allowed after
paths are known.

## Current Code Evidence

Relevant current files:

- `backend/rp/services/runtime/workflow_job_service.py`
- `backend/rp/services/proposal/post_write_governance_service.py`
- `backend/rp/services/proposal/workflow_service.py`
- `backend/rp/services/proposal/repository.py`
- `backend/rp/services/proposal/apply_service.py`
- `backend/rp/services/story/runtime_identity_service.py`
- `backend/rp/services/story/turn_domain_service.py`
- `backend/rp/models/runtime/workflow_job.py`
- `backend/rp/models/runtime/reason_codes.py`
- `backend/models/rp_memory_store.py`
- `backend/models/rp_story_store.py`
- `backend/rp/tests/services/proposal/test_memory_candidate_governance_routing.py`
- `backend/rp/tests/services/proposal/test_proposal_workflow_service.py`
- `backend/rp/tests/services/runtime/test_s1core_settlement_matrix.py`
- `backend/rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py`

Current-state findings:

- `RuntimeWorkflowJobService.ensure_scheduler_maintenance_gate()` already
  prevents a second active scheduler gate on the same anchor and uses the
  central `maintenance_in_progress` reason code.
- `RuntimeWorkflowJobKind.SCHEDULER_MAINTENANCE_GATE` already exists and the
  S1 settlement matrix covers gate blocking/terminal behavior.
- `PostWriteGovernanceService` now records invalid S3 handoff as a terminal
  failed job instead of leaving it running.
- `ProposalWorkflowService` persists `review_required` proposals and does not
  apply them.
- `ProposalApplyService` already rejects stale `base_refs` before mutation and
  marks the proposal failed with no apply receipt.
- Missing piece: a current-branch pending review proposal is not yet exposed as
  a maintenance blocker through a central lock service/read model.
- Missing piece: operation families do not yet share one deterministic
  allow/block matrix for S3/W5-A maintenance lock decisions.
- Missing piece: stale-base failures need S3-focused integration coverage proving
  no model repair loop or worker rerun is triggered.

## Required Design

### 1. Add a deterministic maintenance lock service

Suggested placement:

- `backend/rp/services/runtime/maintenance_lock_service.py`
- tests under:
  - `backend/rp/tests/services/runtime/test_maintenance_lock_service.py`
  - or `backend/rp/tests/services/proposal/test_memory_maintenance_lock_matrix.py`
    if the tests need proposal fixtures.

The service should read current persisted state and return a structured lock
decision. Suggested DTOs may live in the same service module unless they become
shared enough to justify a model file.

Minimum service surface:

```text
RuntimeMaintenanceLockService.evaluate(
  story_id,
  session_id,
  branch_head_id,
) -> RuntimeMaintenanceLockState

RuntimeMaintenanceLockService.require_allowed(
  story_id,
  session_id,
  branch_head_id,
  operation,
) -> RuntimeMaintenanceLockDecision
```

The exact names can change during implementation, but the semantics must not:

- lock decisions are deterministic backend code;
- lock decisions do not ask the model, worker, harness, or tool layer;
- lock decisions are scoped to story/session/current branch;
- lock causes are inspectable and carry stable reason codes.

### 2. Define operation families explicitly

Use one central operation enum/string set for this slice. The names should be
plain and product-readable, for example:

Blocked while a current-branch blocker is active:

- `core_memory_edit`
- `projection_edit`
- `manual_accepted_prose_edit`
- `story_progression`
- `rollback`
- `branch_switch`
- `branch_create`
- `rewrite`
- `regenerate`
- `chapter_complete`
- `story_evolution_or_archival_edit`

Allowed while a blocker is active:

- `inspect_debug`
- `proposal_accept`
- `proposal_reject`
- `proposal_discard`
- `proposal_edit`
- `failed_worker_retry`
- `runtime_config_edit`

Do not scatter this matrix across story, proposal, and memory services. S3d may
only wire one or two existing call sites if a safe call site is obvious, but the
service tests must prove the full matrix.

### 3. Treat pending review proposals as blockers

S3c creates `MemoryProposalRecord` rows with:

```text
status = review_required
session_id = current session
governance_metadata_json.identity.branch_head_id = current branch
```

S3d must treat those rows as active blockers until they become terminal.

Terminal proposal statuses for the first slice:

- `applied`
- `rejected`
- `discarded`
- `failed`
- `invalid`
- `superseded`
- `cancelled`

If current code lacks reject/discard/edit services, S3d should add only the
minimal repository status helper and tests needed to prove lock clearing. Do not
build the full review UI/editor.

### 4. Treat non-terminal required maintenance jobs as blockers

Current W5/S3 blockers also include non-terminal required workflow jobs on the
current branch, especially:

- `scheduler_maintenance_gate`;
- `proposal_submit`;
- `proposal_apply`;
- other `required_for_turn_completion=True` jobs that are not settlement
  terminal.

Terminal job statuses that clear the lock:

- `completed`
- `deferred`
- `failed`
- `cancelled`

This lock read model may use the same terminal definition as settlement plus
failed/cancelled for unlock semantics. Do not mark failed maintenance as
successful; it is terminal but still visible as a failure cause in debug.

### 5. Preserve stale-base enforcement as apply-owned

S3d must not add an LLM repair loop for stale base revisions.

Required behavior:

- S3 candidate base refs still bridge through S3c adapter into proposal
  `base_refs`;
- proposal apply rejects stale base through `ProposalApplyService`;
- stale apply failure marks the proposal failed and writes no apply receipt;
- the S3 governance job reaches terminal failed/completed evidence according to
  existing S3c behavior;
- lock clears only after the stale proposal/job reaches terminal state;
- no worker adapter or harness retry is invoked for stale base.

Tests can prove this by mutating the target once, then trying to accept/apply a
review-required proposal built against the old base revision.

### 6. Keep inspect/debug and review actions available

While the lock is active:

- read-only inspect/debug must return the blocker causes;
- proposal accept must be allowed and route to governed apply;
- proposal reject/discard must be allowed and clear the blocker;
- proposal edit is allowed as a review-surface operation if a concrete edit
  service exists; otherwise prove the operation guard allows it and document that
  full candidate-edit persistence is deferred.

Do not implement broad UI routes in this slice.

## Lock Cause Contract

Each blocker should produce a readable cause with at least:

```text
reason_code = maintenance_in_progress
source_kind = runtime_job | proposal
source_id
story_id
session_id
branch_head_id
turn_id?
status
operation?
metadata
```

The user-facing error path may expose a short message, but tests should assert
the stable reason code and source ids.

## Tests Required

Minimum new tests:

- pending S3 review-required proposal activates the lock;
- applied proposal clears the lock;
- rejected or discarded proposal clears the lock;
- failed stale-base proposal clears the lock while preserving failure evidence;
- non-terminal scheduler maintenance gate blocks;
- completed/deferred/failed/cancelled gate clears;
- each blocked operation family returns `maintenance_in_progress`;
- each allowed operation family remains allowed;
- inspect/debug returns blocker causes while locked;
- proposal accept/reject/discard/edit are allowed while locked;
- stale-base apply fails through `ProposalApplyService` and does not call worker
  adapter or harness repair.

Focused regression should include:

```powershell
python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py
python -m pytest rp/tests/services/proposal/test_memory_candidate_governance_routing.py
python -m pytest rp/tests/services/proposal/test_proposal_workflow_service.py
python -m pytest rp/tests/services/runtime/test_s1core_settlement_matrix.py
python -m pytest rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py
```

Add exact new test paths after implementation.

## Forbidden In S3d

- Do not move maintenance lock logic into harness prompts or worker adapters.
- Do not ask the model to repair stale base revisions.
- Do not implement broad review UI editing.
- Do not rewrite `ProposalWorkflowService` or `ProposalApplyService`.
- Do not weaken S3a/S3b/S3c tests.
- Do not introduce local aliases for `maintenance_in_progress`.
- Do not broaden the S3 direct-apply target subset unless a separate brief
  explicitly authorizes it.
- Do not touch unrelated visible worktree changes.

## Expected Implementer Output

Summarize:

- files changed;
- lock service surface and operation-family names;
- exact blocker sources implemented;
- exact terminal statuses used for unlock;
- stale-base behavior and evidence;
- exact tests run and results;
- any deviations from this brief;
- remaining risks for S3e integration.
