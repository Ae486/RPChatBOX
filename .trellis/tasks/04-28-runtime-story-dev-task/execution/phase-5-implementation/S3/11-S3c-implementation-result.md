# S3c Implementation Result

Status: gate passed
Date: 2026-06-23

## Scope Completed

S3c implemented the bounded governance/proposal handoff slice:

- added a named S3 memory candidate to proposal adapter;
- connected `s3_memory_maintenance_candidate` into
  `PostWriteGovernanceService`;
- preserved the existing `legacy_state_patch` compatibility path;
- bridged `base_block_revision_id` into `ProposalSubmitInput.base_refs`;
- added a generic `RuntimeWorkflowJobService.mark_job_failed()` helper;
- made invalid S3 handoff terminal and readable instead of leaving a running
  proposal governance job.

Out of scope remained untouched:

- full S3d maintenance lock matrix;
- review UI editing;
- branch rollback invalidation;
- broad five-domain apply backend migration;
- new apply engine;
- setup-agent or harness-core changes.

## Code Added Or Changed

- `backend/rp/services/proposal/memory_candidate_proposal_adapter.py`
- `backend/rp/services/proposal/post_write_governance_service.py`
- `backend/rp/services/runtime/workflow_job_service.py`
- `backend/rp/tests/services/proposal/test_memory_candidate_proposal_adapter.py`
- `backend/rp/tests/services/proposal/test_memory_candidate_governance_routing.py`

## Implemented Target Subset

S3c intentionally implements one honest first direct-apply target subset:

```text
S3 domain/block: plot_threads / plot.active_threads
Current apply target: Domain.PLOT_THREAD / plot_thread.active
Operation: append_item -> AppendEventOp
```

Unsupported S3 targets and operations fail closed with stable reason codes.
This avoids pretending the full five-domain S3 schema is already backed by the
current apply backend.

## Governance Mapping

- `review_required` maps to `PolicyDecision.REVIEW_REQUIRED`: proposal is
  persisted and not applied.
- `direct_apply_allowed` maps to `PolicyDecision.NOTIFY_APPLY`: proposal routes
  through `ProposalApplyService`; apply remains the only truth mutation path.
- invalid/blocked handoff records a failed proposal governance job and no
  proposal/apply.
- no-op remains handled by S3b as a skipped worker result with no proposal.
- legacy `legacy_state_patch` remains unchanged.

## Review

Fresh check record:

- `execution/phase-5-implementation/S3/S3c-check-record.md`

Review result:

- P1 accepted and fixed: failed handoff now persists a terminal failed job
  without re-raising and causing transaction rollback.
- P3 ignored as unrelated: `.trellis/.template-hashes.json` pycache entries are
  pre-existing visible worktree noise and not part of S3c.

## Verification

Command run by main-brain from `H:\chatboxapp\backend`:

```powershell
python -m pytest rp/tests/services/proposal/test_memory_candidate_proposal_adapter.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py rp/tests/services/proposal/test_proposal_workflow_service.py rp/tests/services/writer/test_memory_maintenance_worker_adapter.py rp/tests/services/memory/test_runtime_memory_contract_registry.py rp/tests/models/memory/test_memory_maintenance_candidate_contracts.py rp/tests/services/memory/test_memory_candidate_validation_service.py rp/tests/agent_runtime/test_s0_harness_substrate.py rp/tests/services/story/test_story_runtime_adapter_service.py rp/tests/services/writer/test_worker_scheduler_service.py
```

Result:

```text
69 passed, 1 warning in 77.63s
```

The warning is the existing Pydantic class-based `config` deprecation in
`backend/config.py`, outside S3c.

## Remaining Work

S3d should build on this by implementing the maintenance lock matrix and
stale-base integration at the broader runtime boundary:

- lock/unlock behavior for pending review-required proposals and failed
  maintenance;
- proposal accept/reject/edit allowed during lock;
- ordinary story progression/edit/rollback blocked during current-branch
  maintenance;
- broader S3 domain/block apply backend support only after explicit design.
