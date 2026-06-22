# S3f Planning Review Record

Date: 2026-06-23
Reviewer: Codex exec read-only review
Session: `019ef1a1-6741-7680-9a0d-81720f81cf76`
Scope: `16-S3f-closing-gate-brief.md`

## Verdict

```text
PASS_WITH_CONCERNS
```

The reviewer agreed that S3f is the correct next slice after S3e. S3e wired
maintenance lock entrypoints, but it did not replace the original S3
end-to-end closing gate.

## Findings And Main-Brain Adjudication

### 1. Production worker execution seam could be overstated

Finding:

- Current production `WorkerExecutionService` still selects
  `LongformMemoryWorker` through the legacy specialist adapter path.
- A S3f fake execution seam can prove selected-worker-to-governance behavior,
  but it must not be described as proof that the production worker executor has
  fully switched to `MemoryMaintenanceWorkerAdapter`.

Adjudication: accepted.

Document update:

- S3f brief now requires the result record to state the residual production
  executor gap if production `WorkerExecutionService` is not changed.

### 2. New E2E test must not keep using only private governance entrypoints

Finding:

- S3c already calls `_dispatch_proposal_governance()` directly.
- S3f must enter from `StoryTurnDomainService.trigger_post_write()` or, if that
  proves impossible without broader code changes, at least from public
  `PostWriteGovernanceService.dispatch_worker_results()`.

Adjudication: accepted.

Document update:

- S3f brief now forbids using `_dispatch_proposal_governance()` as the main E2E
  entrypoint.

### 3. Failure scenarios need two levels

Finding:

- Adapter invalid structured output fails before a proposal candidate exists and
  may not create a proposal-governance job.
- Governance handoff failure happens after a proposal candidate exists and
  should create a failed proposal-governance job.

Adjudication: accepted.

Document update:

- S3f brief now separates adapter failure and governance handoff failure.

### 4. Branch delete wording must stay bounded

Finding:

- Branch delete is correctly deferred.
- S3f result must not claim complete branch lock policy.

Adjudication: accepted.

Document update:

- S3f brief now requires result wording to say only the current-branch S3
  maintenance blocker path is closed; branch delete remains deferred.

### 5. Service-size rule is correct

Finding:

- Service-size constraints are appropriate.
- New production wiring, if required, must use small helper/adapter components
  and avoid growing oversized story services.

Adjudication: accepted.

Document update:

- S3f brief already had this rule; wording was tightened around no new logic in
  oversized services.

## Review Constraints

- Reviewer did not edit files.
- Reviewer did not run tests.
- Reviewer reported that YCE CLI was unavailable inside its read-only
  PowerShell environment. It did not use ACE. Main-brain had already run YCE
  searches for S3f planning before dispatching the reviewer.
