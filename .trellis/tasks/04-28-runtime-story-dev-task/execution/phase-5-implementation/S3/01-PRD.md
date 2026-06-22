# S3 PRD — Memory Worker To Governed Apply

Status: planning draft for assistant review
Owner: main-brain
Date: 2026-06-23

## 1. Goal

Implement S3 as the first complete story-runtime memory-maintenance path:

```text
accepted source material
  -> post-write trigger
  -> optional orchestrator dispatch proposal
  -> scheduler-selected MemoryMaintenanceWorker
  -> structured candidate / no-op / failure
  -> deterministic ingestion
  -> review-required, direct-apply-allowed, or blocked governance routing
  -> governed apply or readable rejection
  -> lock/debug/next-packet visibility
```

The key product promise is:

```text
No LLM output directly mutates memory truth. Worker output becomes candidate
material, and only deterministic governed apply can mutate Core/projection
truth.
```

## 2. Requirement Authority

Primary sources:

- `research/index.md`
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
- `execution/phase-5-implementation/S3/00-preflight-judgment.md`

Relevant current-code evidence from YCE and direct reads:

- `backend/rp/services/proposal/apply_service.py`
- `backend/rp/services/proposal/post_write_governance_service.py`
- `backend/rp/services/proposal/workflow_service.py`
- `backend/rp/services/proposal/post_write_scheduler_service.py`
- `backend/rp/services/runtime/scheduler_decision_service.py`
- `backend/rp/models/proposal/postwrite_runtime_contracts.py`

## 3. Problem Statement

S0/S1/S2 established a minimum story-runtime base:

- setup-free harness substrate exists;
- turn lifecycle and interrupt handling exist;
- scheduler decision, job/gate, and worker-plan spine exist.

Current S3-adjacent production code still has a legacy-shaped bridge:

```text
worker execution / specialist bundle
  -> adapted WorkerResult
  -> proposal candidate kind = legacy_state_patch
  -> PostWriteGovernanceService only accepts legacy_state_patch
  -> ProposalWorkflowService routes to review or apply
```

That bridge is useful migration evidence, but it is not enough for the new S3
contract. S3 needs a clear MemoryMaintenanceWorker path with structured
candidate output, source refs, base revisions, readable failure handling, and
governance routing that does not hide new semantics under legacy labels.

## 4. Users And Consumers

Primary consumers:

- writer packets, which need reliable current memory/projection visibility;
- scheduler/governance services, which need deterministic worker result
  ingestion;
- proposal review surfaces, which need readable old/new candidate items;
- inspect/debug surfaces, which need job/proposal/failure/receipt evidence;
- future S5/S7, which depend on memory worker and proposal/apply patterns.

Implementation consumers:

- `PostWriteSchedulerService`
- `SchedulerDecisionService`
- worker registry / worker execution path
- story harness / worker adapter
- proposal workflow / apply services
- workspace material and memory change event services

## 5. In Scope

S3 first implementation must cover:

- fixed memory contract registry for five longform Core domains and block
  topology;
- MemoryMaintenanceWorker definition or adapter shape;
- structured worker candidate batch / no-op / failure output;
- internal project runtime tools or equivalent adapter functions for memory
  reads and candidate materialization;
- source ref and base revision handling;
- candidate material stored as non-truth Runtime Workspace material;
- proposal review read/write model mapping for candidate items;
- governance routing:
  - review-required;
  - direct-apply-allowed;
  - blocked / invalid fail-closed;
- stale base rejection without model self-repair;
- maintenance lock matrix for S3 blockers and allowed review/inspect actions;
- readable trace/debug evidence;
- deterministic fake model/tool tests;
- integration path from post-write trigger to proposal/apply or rejection.

## 6. Out Of Scope For First S3 Slice

Explicitly out of scope:

- full memory editor UI;
- broad contradiction detection layer;
- historical dirty-data repair;
- all possible memory operation kinds if a smaller set proves the contract;
- external MCP/skill tool providers;
- writer retrieval / retrieval usage hard gate (S4);
- chapter close summary and tail flush (S5);
- revision/rewrite implementation (S6);
- brainstorm submit handoff implementation (S7);
- full replacement of every legacy longform service.

Out-of-scope items must not be silently removed from the complete runtime
meaning. They remain later slices or follow-up tasks.

## 7. Functional Requirements

### FR1. Registry-driven memory schema

Runtime code must expose the exact five longform Core domains:

- `current_scene`
- `character_state`
- `knowledge_state`
- `plot_threads`
- `world_constraints`

Runtime workers must not create/delete domains, create/delete blocks, or change
schemas. Unknown domain/block/field ids fail closed.

Acceptance source: `D-S3-01`, `MEM-009`, `MEM-010`.

### FR2. Worker output is candidate material, not truth

MemoryMaintenanceWorker output must terminate as exactly one of:

- structured candidate batch;
- explicit no-op;
- normalized failure receipt.

Candidate material must be persisted or routed with:

- `source_of_truth=false`;
- `authoritative_mutation=false`;
- source refs;
- base revision refs;
- worker/phase/trace metadata.

Acceptance source: `D-S3-02`, `MEM-016`, `AUTH-001`.

### FR3. Governed apply is the only truth mutation path

Core/projection truth changes only through deterministic governed apply.

The LLM/harness/worker/tool layer cannot directly mutate Core truth.

Acceptance source: `AUTH-001`, `MEM-016`.

### FR4. Governance routing is complete enough

The first S3 slice must implement minimal complete routing:

- `review_required`: candidate waits for review and explicit accept;
- `direct_apply_allowed`: deterministic policy allows apply after validation;
- `blocked` / `invalid`: candidate is rejected/fails closed with readable trace.

The implementation must explicitly map or rename existing code terms
`REVIEW_REQUIRED`, `NOTIFY_APPLY`, `SILENT` against W5 terms
`review_required`, `direct_apply_allowed`, `proposal_required`, `blocked`.

Acceptance source: main-brain D6/D8/D9, W5 governance paths.

### FR5. Maintenance lock matrix

While current-branch maintenance blockers are active:

- ordinary Core/projection/manual accepted-prose edits are blocked;
- story progression is blocked;
- rollback / branch switch / branch create are blocked in W5-A;
- rewrite / regenerate / chapter complete are blocked;
- read-only inspect/debug remains allowed;
- proposal accept/reject/edit remains allowed.

Acceptance source: `D-S3-03`, `AUTH-005`, `AUTH-006`, `AUTH-007`.

### FR6. Stale base rejection

If `base_block_revision_id` or equivalent authoritative base ref does not match
current branch-visible revision, accept/apply must fail with explicit stale or
conflict state.

The model must not be asked to repair stale base revisions.

Acceptance source: `D-S3-04`, `AUTH-008`, `HAR-007`.

### FR7. Readable observability

Debug and inspect evidence must show:

- job state and lock cause;
- worker id / phase / result status;
- source refs and base refs;
- candidate material refs;
- proposal status;
- apply/change receipts;
- stale/invalid/failure reason codes in readable form.

Normal UI should not expose raw provider/tool internals by default.

## 8. Non-Functional Requirements

- Keep harness core thin: model call, tool loop, structured validation, retry,
  trace, timeout/cancellation, fakes.
- Keep memory policy in memory/proposal/apply services, worker definitions, and
  role adapters.
- Do not import or reuse setup-agent executor logic.
- Do not create private per-module tool protocols.
- Keep files small enough to review; split DTOs, services, validators, and tests
  by responsibility.
- Use project naming and service patterns.
- Use deterministic tests first; live-provider smoke is optional and secondary.

## 9. Definition Of Done

S3 can be considered implemented only when:

- PRD / SDD / test plan have passed standing assistant review;
- implementation diff follows reviewed plan or has documented deviation;
- fresh reviewer audits the landed code/docs against Node-1/module/SoT docs;
- S3 unit/service/integration tests pass;
- relevant S0/S1/S2 regression tests pass;
- `trellis-check` is run for the coherent implementation slice;
- decision log / worklog / gate record the evidence;
- no unrelated user changes are touched.

## 10. Current Open Engineering Items

These are implementation-owned, not user裁定:

- exact DTO names and module placement for S3 candidate/proposal review models;
- exact mapping from W5 governance language to existing policy enums;
- whether to introduce a non-legacy candidate kind or map normalized candidates
  before `legacy_state_patch`;
- first-slice operation subset;
- exact fake model/tool fixture layout;
- exact integration test file placement.

The standing assistant must review these choices before implementation.
