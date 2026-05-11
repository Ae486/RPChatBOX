# Story Runtime Product Acceptance Development Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Module: Phase Q / Runtime Product Acceptance / User-facing Integration Gate
>
> Status: development-spec-v1

## 1. Scope

This development spec converts the Q acceptance spec into implementation-ready
slices.

Q is an integration and acceptance phase. It must prefer existing framework,
service, API, test, and UI paths over new abstractions.

The implementation target for Q is the existing runtime inspect/read path and
the current longform review surface. Q must not add a separate debug panel or a
new truth store.

It covers:

1. product-like backend acceptance tests;
2. thin API/frontend wiring only where an existing implemented surface is not
   reachable;
3. debug/read bundle verification;
4. manual QA checklist documentation.

It does not cover:

1. new story truth semantics;
2. large UI redesign;
3. complete branch UI;
4. complete SuperDoc/WebView integration;
5. complete roleplay/TRPG runtime;
6. eval runner implementation.

## 2. Module Slices

### Q1. Product Acceptance Matrix / Backend Scenario Tests

Owner scope:

- acceptance matrix;
- backend product-like tests;
- no frontend code unless a route is impossible to call without a minor API fix.

Primary files:

- `backend/rp/tests/test_story_runtime_product_acceptance.py`
- existing focused test helpers under `backend/rp/tests/`
- existing services only when a missing integration path is discovered

Required scenarios:

1. longform write/review/rewrite/adopt/continue;
2. chapter completion and next chapter bridge;
3. runtime config hot update and snapshot pin;
4. story evolution visibility and reindex evidence;
5. mode sidecar isolation;
6. debug bundle exact-identity readback.

Each scenario must be classified as one of:

- automated backend assertion;
- manual QA step;
- reuse of an existing focused test;
- or a thin route exposure needed only to reach an existing surface.

Rules:

- Tests must assert payload content and source refs, not only row counts.
- Tests must fail if old MVP paths redefine runtime truth.
- Tests must not depend on external LLM calls.
- Where product paths use LLM output, use existing fake writer/worker fixtures or
  deterministic adapters already used by runtime tests.
- Prefer route/controller tests over service-only tests when the user-visible
  contract already exists as a route.

### Q2. Thin Product/API Wiring Check

Owner scope:

- make existing implemented surfaces reachable from current product/API paths;
- keep changes thin and contract-preserving.

Potential backend files:

- `backend/api/rp_story.py`
- `backend/rp/services/story_runtime_controller.py`
- `backend/rp/services/story_runtime_debug_query_service.py`

Potential frontend files:

- existing longform story page and models only if Q1 proves backend is reachable
  but the product path cannot expose required state.

Rules:

- Do not introduce a new frontend architecture.
- Do not introduce a new debug panel.
- Do not introduce SuperDoc/WebView here.
- Do not add new public mutation semantics.
- Any debug/read endpoint stays read-only.
- Any frontend change must be minimal: surface existing state, invoke existing
  command/API, or document how to call the existing inspect route during manual
  QA. Q must not add a new debug page, panel, drawer, or developer console.

### Q3. Manual QA Checklist / Handoff

Owner scope:

- write a checklist that a human can run after automated tests;
- record expected debug evidence and screenshots/observations if needed.

Primary files:

- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-product-acceptance-manual-qa.md`
- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-execution-plan.md`

Checklist must include:

1. create or open a longform story runtime session;
2. write next segment;
3. enter suggesting mode and add a comment/tracked change;
4. run rewrite;
5. select/adopt/continue;
6. complete chapter and start next chapter;
7. apply a runtime config patch and verify future-turn behavior;
8. inspect runtime debug/read bundle;
9. verify no mode sidecars appear unless requested;
10. verify rollback/branch-visible read behavior from existing controls if
    exposed.

This checklist is required for Q completion even if all automated tests pass.

## 3. Data / Contract Rules

Q must reuse these existing contracts:

- `StorySession / BranchHead / Turn`
- `RuntimeProfileSnapshot`
- `MemoryRuntimeIdentity`
- `RuntimeWorkspaceMaterial`
- `WorkerDescriptor / WorkerExecutionPlan / WorkerContextPacket / WorkerResult`
- `WritingPacket`
- `RuntimeReadManifestRecord`
- revision overlay contracts
- chapter bridge contracts
- story evolution contracts
- mode sidecar contracts

Q must not alter the core meaning of those contracts. If an acceptance scenario
seems to require changing a core contract, stop and write a grill question before
implementation.

Q should map the semantic acceptance phrase `accept_and_continue` to the existing
`accept_pending_segment` command / Accept & Continue UI flow. It should not add a
new public command name.

## 4. Validation Matrix

| Condition | Expected behavior |
|---|---|
| Rewrite candidate exists but is not adopted | It does not become canonical continuation base |
| A single candidate is adopted via continue | Adoption receipt becomes the continuation source |
| Multiple candidates exist without explicit selected/adopted ref | Continue fails closed or requires explicit selection per existing contract |
| Chapter completion sees pending rewrite without adoption | Fail closed |
| Runtime config patch happens mid-flow | Existing turn/job keeps old snapshot; next turn uses new snapshot |
| Story evolution applies to current branch | Retrieval/read surface respects branch visibility |
| Rule card exists but no sidecar slot is requested | Packet `sidecar_refs` is empty and generic `workspace_refs` does not include rule card |
| Debug section label suggests sidecar but lacks stable classifier | Debug reader treats it as ordinary packet section |
| Debug bundle requested for sibling branch | Exact-identity or branch-scope filtering prevents leakage |

Route binding:

- use the existing `/api/rp/story-sessions/{session_id}/runtime/inspect` route;
- if a field is missing, extend the read-only response shape rather than adding a
  second debug truth source.

## 5. Good / Base / Bad Cases

- Good: one product-like test proves a user can write, review, rewrite, adopt,
  continue, and inspect the resulting runtime evidence.
- Good: a debug bundle answers why the next writer packet saw a chapter bridge
  or did not see a rule sidecar.
- Good: Q discovers a missing API path and adds a thin route to an existing
  service without changing truth semantics.
- Base: some UI interactions remain manual checklist items if automating them
  would require unrelated frontend test infrastructure.
- Bad: starting SuperDoc/WebView integration before proving the current minimal
  review path works end to end.
- Bad: adding a new debug truth store because reading the current persisted
  evidence is inconvenient.
- Bad: treating Q as license to implement full branch UI or active TRPG runtime.

## 6. Tests Required

Q1 backend tests:

- `pytest backend/rp/tests/test_story_runtime_product_acceptance.py -q`
- focused existing tests for impacted services if Q1 finds a missing integration.

Q2 API/frontend checks:

- API tests in `backend/tests/test_rp_story_api.py` for any new or adjusted route.
- Frontend build/check only if frontend files change.

Q3 manual QA:

- `.trellis/tasks/04-28-runtime-story-dev-task/research/story-runtime-product-acceptance-manual-qa.md`

Q final check:

- module-level `gpt-5.5 xhigh` check agent after Q1-Q3 complete.
- final check must verify that Q did not expand into full branch UI, SuperDoc, or
  active RP/TRPG runtime unless the plan was explicitly revised.

## 7. Implementation Order

1. Q1 first: write the backend acceptance matrix and product-like tests.
2. Q2 only after Q1 exposes a reachability gap.
3. Q3 after Q1/Q2: write manual QA and update execution plan.
4. Module-level check after Q1-Q3 are complete.

## 8. Parallelism

Default: run Q serially with one implementation owner.

Parallel work is allowed only if Q2 becomes clearly frontend-only while Q1 remains
backend-only, and the two write sets are disjoint. If that happens:

- agent 1 owns Q1 backend acceptance tests;
- agent 2 owns Q2 frontend/API product wiring;
- no agent may edit the same route/model/service file in parallel.

If this cannot be proven, keep Q serial.
