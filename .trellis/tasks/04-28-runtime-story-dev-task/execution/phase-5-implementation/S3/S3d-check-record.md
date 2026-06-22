# S3d Check Record

Date: 2026-06-23
Reviewer: Codex exec read-only review / main-brain adjudication
Scope: S3d maintenance lock and stale-base integration

## Inputs Read

- `execution/phase-5-implementation/S3/12-S3d-implementation-brief.md`
- S3 planning and prior-slice anchors:
  - `01-PRD.md`
  - `02-SDD-and-implementation-plan.md`
  - `03-test-and-gate-plan.md`
  - `11-S3c-implementation-result.md`
  - `S3c-check-record.md`
- Backend specs:
  - `.trellis/spec/backend/rp-services-organization-contract.md`
  - `.trellis/spec/backend/rp-core-state-base-revision-conflict-enforcement.md`
  - `.trellis/spec/backend/rp-shared-core-mutation-kernel-direct-edit.md`
  - `.trellis/spec/backend/rp-runtime-identity-persistence-propagation.md`
- S3d code and tests:
  - `backend/rp/services/runtime/maintenance_lock_service.py`
  - `backend/rp/tests/services/runtime/test_maintenance_lock_service.py`
  - `backend/rp/tests/services/proposal/test_memory_candidate_governance_routing.py`

YCE note:

- Main-brain ran YCE search before code changes for
  `ProposalWorkflowService`, `ProposalApplyService`, stale base conflicts, and
  S3 governance-routing tests.
- The first broad YCE query returned an empty wrapper result despite internal
  readfile hints. A narrower YCE query returned concrete anchors. No ACE search
  was used.

## Review Findings

Independent read-only review result:

```text
NO BLOCKING FINDINGS.
```

Reviewer residual risks:

- The review only covered the three S3d files; later integration work must
  confirm all story progression / branch / rewrite entrypoints call the lock
  with the right `RuntimeMaintenanceOperation`.
- Malformed historical proposal metadata could crash the read model.
- Proposals without branch identity are ignored by the current-branch lock.

Main-brain decisions:

- Accepted and fixed the malformed metadata risk. `_proposal_identity()` now
  ignores non-dict metadata instead of throwing, and the behavior is covered by
  `test_malformed_proposal_metadata_does_not_crash_lock_read`.
- Kept the missing-identity behavior as designed for this slice: old/no-identity
  proposals are not current-branch blockers. Future producers must write runtime
  identity if they expect lock participation.
- Recorded entrypoint wiring as later integration work. S3d is the deterministic
  lock read model and stale-base integration slice, not the full router/API
  enforcement pass.

Codex review session:

```text
019ef158-2b7a-70f0-a819-68c50e35b2ac
```

## Scope Discipline

- No setup-agent imports or setup-agent tool semantics were introduced.
- No LLM permission system was added. The lock is deterministic state reading
  over persisted jobs and proposals.
- No proposal/apply rewrite was introduced. Stale-base conflict remains owned by
  `ProposalApplyService`.
- No Core State, Projection, Recall, Archival, or Runtime Workspace truth writes
  were added by the lock service.
- Existing S3c direct-apply governance test was restored to the worker
  governance path; only the stale-base regression uses direct
  `ProposalWorkflowService.submit_and_route()` to advance revision.

## Verification

Focused command run from `H:\chatboxapp\backend` after the review fix:

```powershell
python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
```

Result:

```text
22 passed, 1 warning in 73.74s
```

Full S3d gate run from `H:\chatboxapp\backend` after the review fix:

```powershell
python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py rp/tests/services/proposal/test_proposal_workflow_service.py rp/tests/services/runtime/test_s1core_settlement_matrix.py rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py
```

Result:

```text
54 passed, 1 warning in 183.67s
```

The warning is the existing Pydantic class-based `config` deprecation in
`backend/config.py`, outside S3d.

Focused lint command run from `H:\chatboxapp`:

```powershell
python -m ruff check backend/rp/services/runtime/maintenance_lock_service.py backend/rp/tests/services/runtime/test_maintenance_lock_service.py backend/rp/tests/services/proposal/test_memory_candidate_governance_routing.py
```

Result:

```text
All checks passed!
```

Service-size command run from `H:\chatboxapp`:

```powershell
python backend/rp/devtools/check_service_sizes.py
```

Result:

```text
FAIL
```

This failure is not caused by the new S3d service. The reported blockers are
pre-existing baseline drift in `story/runtime_identity_service.py` and
`story/turn_domain_service.py`, plus already-committed S3a/S3b/S3c functions
that exceed the hard function limit. The new
`runtime/maintenance_lock_service.py` is not reported as a hard offender.
