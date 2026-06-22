# S3d Implementation Result

Status: gate passed with service-size residual
Date: 2026-06-23

## Scope Completed

S3d implemented the bounded maintenance-lock / stale-base integration slice:

- added a deterministic `RuntimeMaintenanceLockService`;
- added operation families for blocked and allowed actions during maintenance;
- treats current-branch non-terminal required workflow jobs as lock blockers;
- treats current-branch non-terminal proposals with runtime branch identity as
  lock blockers;
- allows inspect/debug and proposal review operations while locked;
- keeps stale-base mutation conflict handling in `ProposalApplyService`;
- verifies that stale review proposal apply fails, marks the proposal `failed`,
  creates no apply receipt, and clears the lock;
- restores the S3c direct-apply governance test to the worker governance path.

Out of scope remained untouched:

- router/API entrypoint enforcement;
- frontend lock display or proposal review UI;
- setup-agent permission logic;
- LLM permission design;
- broad S3 five-domain apply backend migration;
- branch rollback invalidation and full branch visibility integration.

## Code Added Or Changed

- `backend/rp/services/runtime/maintenance_lock_service.py`
- `backend/rp/tests/services/runtime/test_maintenance_lock_service.py`
- `backend/rp/tests/services/proposal/test_memory_candidate_governance_routing.py`

## Implemented Behavior

The lock read model now returns one current lock state for:

```text
story_id + session_id + branch_head_id
```

Lock causes:

- required runtime workflow jobs that are not terminal;
- proposals for the same story/session whose governance metadata contains the
  same `branch_head_id` and whose status is not terminal.

Blocked operation families include:

- Core memory edit;
- projection edit;
- manual accepted-prose edit;
- story progression;
- rollback;
- branch switch/create;
- rewrite/regenerate;
- chapter complete;
- story evolution / archival edit.

Allowed operation families include:

- inspect/debug;
- proposal accept/reject/discard/edit;
- failed worker retry;
- runtime config edit.

Unknown operation values are caller input errors:

```text
runtime_maintenance_operation_unknown:<operation>
```

They do not masquerade as `maintenance_in_progress`.

Malformed or missing proposal identity metadata is ignored by the current-branch
lock. This preserves the S3d rule that old/no-identity proposals are not branch
blockers, while requiring future S3 producers to write identity if they expect
lock participation.

## Review

Fresh check record:

- `execution/phase-5-implementation/S3/S3d-check-record.md`

Review result:

- independent read-only Codex review returned `NO BLOCKING FINDINGS`;
- main-brain accepted and fixed the malformed metadata compatibility suggestion;
- remaining integration risk is that future entrypoint wiring must call the lock
  service consistently before story progression / branch / rewrite actions.

## Verification

Focused command run by main-brain from `H:\chatboxapp\backend`:

```powershell
python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py
```

Result:

```text
22 passed, 1 warning in 73.74s
```

Full S3d gate run by main-brain from `H:\chatboxapp\backend`:

```powershell
python -m pytest rp/tests/services/runtime/test_maintenance_lock_service.py rp/tests/services/proposal/test_memory_candidate_governance_routing.py rp/tests/services/proposal/test_proposal_workflow_service.py rp/tests/services/runtime/test_s1core_settlement_matrix.py rp/tests/services/story/test_s2b_post_write_orchestrator_gate.py
```

Result:

```text
54 passed, 1 warning in 183.67s
```

Focused ruff command:

```powershell
python -m ruff check backend/rp/services/runtime/maintenance_lock_service.py backend/rp/tests/services/runtime/test_maintenance_lock_service.py backend/rp/tests/services/proposal/test_memory_candidate_governance_routing.py
```

Result:

```text
All checks passed!
```

Service-size command:

```powershell
python backend/rp/devtools/check_service_sizes.py
```

Result:

```text
FAIL
```

The failure is a residual gate risk outside the new S3d service. It reports
pre-existing baseline drift in story services and hard function offenders from
already-committed S3a/S3b/S3c slices. S3d did not add a new hard service-size
offender.

## Remaining Work

Next implementation should decide and wire the enforcement points that consume
`RuntimeMaintenanceLockService.require_allowed()`:

- story progression commands;
- branch switch/create/rollback commands;
- rewrite/regenerate/chapter-complete commands;
- proposal review commands that should remain allowed during lock.

The integration pass should keep the same rule as S3d: the scheduler/governance
layer decides whether an operation may proceed; the LLM never mutates external
truth directly.
