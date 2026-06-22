# S3 Test And Gate Plan

Status: planning draft for assistant review
Owner: main-brain
Date: 2026-06-23

## 1. Test Principle

S3 tests must prove runtime behavior, not just that new DTOs can be constructed.

Every expected result should come from Node-1/module/SoT requirements, not from
the implementation being written. Do not compute expected values using the same
helper under test.

## 2. Required Test Layers

### Unit tests

Purpose: deterministic local contracts.

Required behaviors:

- memory registry exports exactly five domains;
- registry exports fixed block topology;
- unknown domain/block/field rejected;
- candidate schema rejects extra fields where strictness is required;
- candidate validator rejects:
  - create/delete domain;
  - create/delete block;
  - schema change;
  - unsupported operation;
  - missing source ref;
  - missing base revision;
  - unknown target handle;
  - contradictory operations on same fact;
- governance policy mapper produces review/direct/blocked outcomes without
  relying on LLM/tool names alone.
- S3-to-current governance mapping produces explicit review/direct/proposal/
  blocked/no-op outcomes; invalid output cannot disappear into a generic
  `SILENT` success.
- `base_block_revision_id` conversion to apply `base_refs` rejects missing,
  stale, and conflicting bases without model repair.

### Service tests

Purpose: persistence and state transition truth.

Required behaviors:

- worker candidate is stored as Runtime Workspace material with
  `source_of_truth=false` and `authoritative_mutation=false`;
- candidate material does not change Core truth before apply;
- valid candidate can become proposal input;
- review-required candidate persists proposal and does not apply;
- direct-apply candidate goes through governed apply and writes receipts;
- rejected/discarded candidate leaves Core unchanged;
- stale base candidate becomes stale/invalid/conflict and does not apply;
- memory change event / dirty target is recorded only after governed apply.
- normalized S3 memory candidates retain a named S3 boundary even if an adapter
  reuses existing proposal submit/apply inputs; they are not publicly exposed as
  undifferentiated `legacy_state_patch`.

### Integration tests

Purpose: connected runtime path.

Required paths:

1. Post-write review-required path
   - accepted segment source exists;
   - scheduler selects MemoryMaintenanceWorker;
   - fake worker returns candidate;
   - proposal is persisted as review-required;
   - maintenance lock blocks progression;
   - accept applies through governed apply;
   - lock clears.

2. Post-write direct-apply path
   - fake worker returns candidate allowed by deterministic policy;
   - governed apply writes Core receipt;
   - projection refs remain resolvable;
   - lock releases.

3. Invalid/blocked path
   - fake worker returns forbidden target or invalid op;
   - no proposal/apply occurs;
   - readable failure/rejection receipt exists.

4. No-op path
   - fake worker returns no-op;
   - job terminal state is completed/deferred according to design;
   - no proposal/apply occurs;
   - trace explains no-op reason.

5. Stale base path
   - candidate created against base revision;
   - block revision changes before accept/apply;
   - accept/apply rejects stale base;
   - no model repair prompt is emitted.

6. Full maintenance lock matrix path
   - pending review-required proposal activates the blocker;
   - each blocked operation below is rejected with a readable lock reason;
   - each allowed operation below remains available;
   - accept/reject/discard/apply terminal state clears the blocker as designed.

### Maintenance lock matrix coverage

S3 tests must cover D-S3-03 explicitly.

Blocked while current-branch S3 maintenance blocker is active:

| Operation family | Required assertion |
| --- | --- |
| Core/projection truth edit | ordinary Core/projection mutation is rejected with lock reason |
| Manual accepted-prose edit | manual accepted-prose edit is rejected with lock reason |
| Story progression | next write/progress action is rejected with lock reason |
| Rollback | rollback is rejected in W5-A/S3 blocker scope |
| Branch switch | branch switch is rejected in W5-A/S3 blocker scope |
| Branch create | branch create is rejected in W5-A/S3 blocker scope |
| Rewrite/regenerate | rewrite or regenerate is rejected with lock reason |
| Chapter complete | chapter completion is rejected with lock reason |

Allowed while blocker is active:

| Operation family | Required assertion |
| --- | --- |
| Inspect/debug | read-only inspect/debug succeeds and shows blocker cause |
| Proposal accept | accept remains available and routes to governed apply |
| Proposal reject/discard | reject/discard remains available and clears blocker |
| Proposal edit | review-surface candidate edit remains available where supported |

### Regression tests

Run relevant existing tests for:

- S0 harness import-clean / fake tool path;
- S1 turn lifecycle and interrupt behavior;
- S2 scheduler decision and job/gate behavior;
- proposal workflow/apply tests;
- `backend/tests/test_rp_story_api.py` if API-facing behavior changes.

### Fresh reviewer audit

After each milestone, dispatch a fresh reviewer to check:

- requirement drift;
- framework/product leakage;
- old-MVP or setup leakage;
- false-green tests;
- missing negative cases;
- file organization and naming;
- whether tests serve production behavior.

The main-brain must accept/reject/defer each finding with reasons.

### Optional live-provider smoke

DeepSeek-backed smoke tests are allowed only after deterministic tests pass.

Rules:

- use existing project provider configuration;
- never print or expose keys;
- keep run bounded and non-flaky;
- treat as supporting evidence, not replacement for deterministic tests.

Potential smoke:

```text
MemoryMaintenanceWorker with real provider
  -> small fixed WorkerContextPacket
  -> structured candidate or no-op
  -> deterministic validator accepts/rejects
  -> no automatic truth mutation outside governed path
```

## 3. Proposed Test File Groups

Exact names may change after impact sweep, but keep responsibilities separated.

Unit / contract:

- `backend/rp/tests/models/memory/test_runtime_memory_contract_registry.py`
- `backend/rp/tests/models/memory/test_memory_maintenance_candidate_contracts.py`
- `backend/rp/tests/services/memory/test_memory_candidate_validation_service.py`

Worker / harness:

- `backend/rp/tests/agent_runtime/story/test_memory_maintenance_worker_adapter.py`
- `backend/rp/tests/services/writer/test_memory_maintenance_worker_execution.py`

Governance / apply:

- `backend/rp/tests/services/proposal/test_memory_candidate_governance_routing.py`
- `backend/rp/tests/services/proposal/test_memory_candidate_stale_base.py`
- `backend/rp/tests/services/proposal/test_memory_candidate_legacy_boundary.py`
- `backend/rp/tests/services/proposal/test_memory_maintenance_lock_matrix.py`

Integration:

- `backend/tests/test_story_runtime_s3_memory_worker_e2e.py`

Regression gates:

- existing S0/S1/S2 oracle files;
- existing proposal workflow/apply tests;
- `backend/tests/test_rp_story_api.py` when API contract changes.

## 4. Gate Commands

Final commands must be decided after implementation files are known. Minimum
expected gate:

```powershell
cd H:\chatboxapp\backend
python -m pytest -n auto rp
python -m pytest tests/test_rp_story_api.py
python -m pytest tests/test_story_runtime_s3_memory_worker_e2e.py
```

If no API surface changes, `test_rp_story_api.py` may remain regression support
rather than a mandatory per-edit run, but final S3 gate should include it unless
runtime cost becomes unreasonable and the main-brain records a narrower gate.

`trellis-check` must run once a coherent implementation slice is ready.

## 5. Red/Green Expectations

Before implementation:

- new S3 oracle tests may be RED if they assert absent behavior;
- RED must be clean assertion/contract failure, not collection/import typos;
- do not mark oracle-first REDs as `xfail`.

After implementation:

- all S3 oracle tests must be green;
- existing S0/S1/S2 tests must not regress;
- any pre-existing failures must be reproduced without S3 changes or recorded
  with evidence.

## 6. Test Review Checklist

Reject tests that:

- assert current legacy behavior instead of SoT behavior;
- compute expected output using the same code under test;
- mock away the service behavior being tested;
- verify call order when state/receipt/output can be asserted;
- skip/xfail oracle-first requirements;
- weaken existing assertions;
- hide failure detail in generic `Exception`;
- rely on live provider for deterministic correctness.
