# Standing Assistant Review Brief — S3 Planning Gate

Status: ready to dispatch when a Trellis review/assistant lane is available
Owner: main-brain
Date: 2026-06-23

## Mission

Act as the standing S3 reviewer / assistant. Your job is to review the S3 PRD,
SDD, and test plan before implementation begins. You are not implementing code
in this review pass.

Report whether the current S3 planning documents are faithful to Node-1 grill
requirements, module docs, frozen SoT, main-brain rules, and current code
evidence. Identify blockers, concerns, and non-blocking notes.

## Search Rule

Use YCE for codebase search. Do not use ACE.

If YCE remote search fails, set:

```text
YCE_LOCAL_FALLBACK=true
```

Then retry. Direct reads of known file paths are allowed after paths are known.

## Required Reading

Read these first:

- `research/index.md`
- `research/modules/runtime-module-breakdown-index.md`
- `research/modules/runtime-memory-domain-block.md`
- `research/modules/runtime-worker-family.md`
- `research/modules/runtime-scheduler-governance.md`
- `research/modules/runtime-agent-harness.md`
- `research/modules/runtime-context-packet.md`
- `research/modules/runtime-workspace-ledger-trace.md`
- `research/modules/runtime-observability-debug-ux.md`
- `research/modules/runtime-adapter-migration-test.md`
- `execution/phase-1-spec-freeze/00-FREEZE-MANIFEST.md`
- `execution/phase-1-spec-freeze/acceptance-criteria.md`
- `execution/phase-1-spec-freeze/seams.md`
- `execution/phase-3-slicing/slice-plan.md`
- `execution/main-brain/implementation-leadership-rules.md`
- `execution/main-brain/decision-queue.md`
- `execution/phase-5-implementation/00-PROCESS-SPEC.md`
- `execution/phase-5-implementation/TEST-QUALITY-STANDARD.md`
- `execution/phase-5-implementation/S3/00-preflight-judgment.md`
- `execution/phase-5-implementation/S3/01-PRD.md`
- `execution/phase-5-implementation/S3/02-SDD-and-implementation-plan.md`
- `execution/phase-5-implementation/S3/03-test-and-gate-plan.md`

Current code anchors to inspect:

- `backend/rp/services/proposal/apply_service.py`
- `backend/rp/services/proposal/post_write_governance_service.py`
- `backend/rp/services/proposal/workflow_service.py`
- `backend/rp/services/proposal/post_write_scheduler_service.py`
- `backend/rp/services/runtime/scheduler_decision_service.py`
- `backend/rp/models/proposal/postwrite_runtime_contracts.py`

## Review Questions

1. Does the PRD faithfully express S3 requirements without narrowing the full
   Node-1/module meaning?
2. Does the SDD keep harness core separate from memory/proposal/apply product
   policy?
3. Does the plan avoid setup-agent reuse and old-MVP semantic authority?
4. Are review-required, direct-apply-allowed, and blocked/invalid governance
   paths all represented?
5. Are source refs and `base_block_revision_id` treated as deterministic backend
   boundaries?
6. Does the plan avoid asking the model to repair stale base revisions?
7. Does the test plan prove functional correctness across unit, service,
   integration, regression, and review/audit layers?
8. Are there missing negative tests?
9. Does the current code evidence contradict any proposed plan?
10. Are any engineering choices actually product decisions that require user
   裁定?

## Expected Output

Write a review report with this structure:

```text
# S3 Standing Assistant Review

## Verdict
PASS / PASS_WITH_CONCERNS / BLOCKED

## Blockers
- [B1] ...

## Concerns
- [C1] ...

## Non-blocking Notes
- [N1] ...

## Required Plan Changes
- ...

## Evidence
- cite document paths and, when available, line references or section names

## Recommendation
- proceed / revise then proceed / stop and ask user
```

The preferred output path is:

```text
execution/phase-5-implementation/S3/review-record.md
```

Do not commit. Do not edit production code. If you propose edits to the PRD/SDD,
state them clearly for the main-brain to adjudicate.

## Review Bar

A PASS means:

- no requirement drift;
- no framework/product leakage;
- no missing mandatory governance path;
- no missing functional test layer;
- no obvious old-MVP/setup leakage;
- no user裁定 required before implementation.

If unsure, report a concern instead of silently accepting the plan.
