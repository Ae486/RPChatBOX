# S3 SDD And Implementation Plan

Status: planning draft for assistant review
Owner: main-brain
Date: 2026-06-23

## 1. Design Objective

S3 connects four existing runtime layers into one honest vertical path:

```text
scheduler/job spine
  -> story-agent worker execution
  -> memory candidate validation/materialization
  -> proposal governance/apply
```

The design must prove the shared story-agent harness by using it for a real
MemoryMaintenanceWorker path, while keeping memory/proposal/apply business
policy outside the harness core.

## 2. Architecture Boundary

| Layer | Owns | Must Not Own |
| --- | --- | --- |
| Harness core | model call mechanics, normalized tool loop, structured-output parsing, stop reason, trace envelope, fake model/tool surfaces | memory domain rules, proposal policy, source/base ref semantics, truth mutation |
| Worker adapter / definition | prompt, worker packet, tool allowlist, output schema, retry policy, authority declaration | final scheduler decision, final apply |
| Memory services | domain/block registry, fact/projection refs, candidate validation, source/base mapping | model/tool loop |
| Scheduler/governance | dispatch validation, lock, policy routing, proposal review/apply handoff, failure receipts | LLM semantic judgment |
| Apply service | deterministic Core/projection mutation, receipts, stale base rejection | candidate generation |
| Workspace/trace | candidate material, job/material lifecycle, read manifests, debug links | story truth |

## 3. Current Code Fit

Current useful assets:

- `SchedulerDecisionService` already validates orchestrator dispatch against a
  worker registry and source unit count.
- `PostWriteSchedulerService` already selects bootstrap or orchestrator-routed
  worker plans.
- `PostWriteGovernanceService` already dispatches WorkerResult projection and
  proposal candidates into jobs.
- `ProposalWorkflowService` already validates proposal submit, persists
  proposal, routes review-required vs auto-apply, and calls apply.
- `ProposalApplyService` already checks `base_refs`, writes apply receipts,
  invalidates matching worker candidates, and records memory change events.

Current gaps:

- proposal governance only accepts `candidate_kind="legacy_state_patch"`;
- worker output shape is not yet a clean S3 memory candidate contract;
- memory contract registry / five-domain block contract needs first-class
  runtime tests and service surface;
- story harness is still mostly test substrate, not a production worker
  adapter path;
- common runtime tool interface is defined in docs but not yet proven by S3;
- review/direct/blocked policy naming is not aligned with W5 language;
- lock matrix coverage for S3 is not yet complete.

## 4. Proposed Component Plan

### 4.1 Memory contract registry

Create or formalize a runtime memory contract registry that exposes:

- exact five domains;
- fixed blocks and `group_by`;
- allowed field shape: optional group/collection -> `facts[]`;
- operation support per block/field;
- lookup by domain/block/field id.

Responsibilities:

- return read-only contract definitions;
- reject unknown domains/blocks/fields;
- provide enough metadata for worker context and candidate validation;
- avoid UI/database-driven schema shortcuts.

Tests:

- exact domain set;
- exact block set for at least initial registry snapshot;
- unknown domain/block rejected;
- schema creation operation unavailable.

### 4.2 S3 candidate DTOs and validator

Define S3 candidate input/output contracts separately from proposal persistence.

Candidate batch variant:

```text
MemoryMaintenanceCandidateBatch
  schema_version
  worker_id
  phase
  candidates[]
  no_op_reason?

MemoryMaintenanceCandidate
  target_domain
  target_block_ref
  base_block_revision_id
  operations[]
  source_refs[]
  change_summary

MemoryOperation
  kind
  target_fact_handle? / target_fact_id?
  content?
  location?
```

The exact names can change during implementation, but the semantics must not:

- backend owns durable ids;
- LLM-visible handles are run-scoped;
- candidate is not truth;
- operations cannot create/delete schema or blocks;
- `base_block_revision_id` is the stale-check authority.

Initial operation subset recommendation:

- `append_item`;
- `update_item`;
- `remove_item`;
- optional `set_field` only if a first-slice block genuinely needs scalar field
  replacement.

Do not implement all operation kinds unless tests and consumers justify them.

### 4.3 Memory worker adapter

Add a worker adapter for `MemoryMaintenanceWorker` that:

- receives a `WorkerContextPacket` or equivalent internal packet;
- exposes only allowlisted internal memory tools or deterministic adapter
  functions;
- runs through the story-agent harness when model/tool loop is needed;
- validates structured output;
- returns one `WorkerResult` variant:
  - candidate batch;
  - no-op;
  - failure receipt.

The adapter owns memory-specific prompt/context/output schema. The harness owns
mechanical execution only.

### 4.4 Internal runtime tools

First-slice tools should be internal project tools only:

1. `memory.batch_read_blocks`
   - input: target block handles/refs selected by worker definition and packet;
   - output: LLM-visible facts and run-scoped handles;
   - errors: unknown block, permission denied, stale packet.

2. `memory.apply_candidate_field_ops`
   - input: target block ref, base revision, operations, source handles;
   - output: `WORKER_CANDIDATE` material ref or validation errors;
   - errors: unsupported op, missing source ref, stale base, unknown handle,
     forbidden target.

If first implementation can validate structured output without model-callable
tools, still define the tool interface contract and fake provider, then decide
whether tool calls are enabled in the worker definition.

Required normalized tool result contract:

```text
RuntimeToolResult
  status: ok | error
  tool_name
  call_id
  trace_id
  data?             # present only when status=ok
  error?            # present only when status=error

RuntimeToolError
  code              # stable reason code, not provider prose
  message           # readable non-secret summary
  retryable: bool
  details?          # structured safe details for debug
```

Required worker output variants:

```text
MemoryMaintenanceWorkerResult
  status: candidate_batch | no_op | failure
  worker_id
  phase
  trace_id
  candidate_batch?  # only for candidate_batch
  no_op?            # only for no_op
  failure?          # only for failure

MemoryMaintenanceNoOp
  reason_code
  message
  source_refs[]
  inspected_block_refs[]

MemoryMaintenanceFailure
  reason_code
  message
  retryable
  tool_call_id?
  invalid_output_path?
  source_refs[]
```

Structured-output handling:

- invalid schema becomes a normalized `failure` result with an
  `invalid_structured_output` reason code;
- repair/retry may happen only inside the harness mechanical budget and must not
  invent new domain policy;
- repair exhaustion becomes a terminal `failure` result with readable trace;
- no-op is a first-class successful worker outcome, not an exception;
- tool errors are never treated as truth mutation and never bypass governance.

### 4.5 Governance handoff

Preferred design direction:

- introduce a normalized S3 memory candidate path instead of hiding under
  `legacy_state_patch`;
- adapt normalized valid candidates into `ProposalSubmitInput` or
  `CoreMutationEnvelope` at a clearly named boundary;
- preserve legacy `legacy_state_patch` only as compatibility/migration path.

Minimum required outcomes:

- valid candidate can become proposal input;
- review-required proposal remains pending and blocks as required;
- direct-apply-allowed proposal applies through `ProposalApplyService`;
- blocked/invalid candidate writes readable failure/rejection evidence;
- stale base rejection occurs before or during apply and never asks model to
  repair itself.

Governance mapping table for the first S3 handoff:

| S3 / W5 term | Current-code bridge | Proposal state | Apply behavior | Lock behavior | Required reason / trace |
| --- | --- | --- | --- | --- | --- |
| `review_required` | existing `REVIEW_REQUIRED` policy outcome | pending review proposal | no apply until accept | blocker remains until accept/reject/discard | proposal id, candidate material ref, policy reason |
| `direct_apply_allowed` | existing `NOTIFY_APPLY` auto-apply branch, renamed at S3 boundary | applied proposal or apply receipt, according to existing workflow shape | call `ProposalApplyService`; mutation only there | blocker clears on apply terminal receipt | apply receipt id, source/base refs |
| `proposal_required` | explicit proposal creation path when deterministic policy says human review is needed | pending review proposal | no auto-apply | blocker remains while proposal pending | policy reason and review surface refs |
| `blocked` / invalid | existing failure / rejection job state, not `SILENT` success | no proposal, or terminal rejected/invalid proposal if persistence is needed for UX | no apply | blocker clears only when terminal invalid/rejected state is recorded | stable invalid/stale/forbidden reason code |
| `no_op` | worker result terminal no-op | no proposal | no apply | no blocker, or blocker clears with no-op receipt if a job already exists | no-op reason and inspected refs |

`SILENT` must not become a generic hiding place for invalid S3 outcomes. If it
is kept for legacy compatibility, the S3 boundary must map it to an explicit
no-op or terminal non-apply state with trace.

### 4.5.1 Legacy candidate boundary

S3 must not expose new memory-worker candidates as `legacy_state_patch` in their
public semantic contract.

Allowed temporary bridge:

```text
MemoryMaintenanceCandidateBatch
  -> named S3-to-proposal adapter
  -> existing proposal submit/apply input shape
```

The adapter may reuse existing proposal persistence/apply service inputs, but
trace/debug evidence must preserve the original S3 candidate kind and worker
metadata. Tests must fail if the new path is only visible as an undifferentiated
legacy candidate with no named S3 boundary.

### 4.5.2 Base revision bridge

Frozen S3 semantics use `base_block_revision_id` as the authoritative stale-base
field. Current apply code enforces stale/conflict state through proposal
`base_refs`. The S3 adapter must therefore make this bridge explicit:

```text
candidate.base_block_revision_id
  -> proposal/apply base_refs entry for the target block/fact/projection
  -> ProposalApplyService base-ref validation
  -> apply receipt or stale/conflict rejection
```

Required behavior:

- missing `base_block_revision_id` fails candidate validation before proposal
  handoff;
- mismatched `base_block_revision_id` becomes stale/conflict at validation or
  apply, with no model repair prompt;
- stale/conflict state is visible in review/debug traces with target block,
  expected base, and current revision refs when safe to expose;
- direct-apply and review-accept paths share the same deterministic stale-base
  enforcement.

### 4.6 Maintenance lock

Lock behavior should be enforced by deterministic services, not by worker prompt
or harness.

S3 must connect proposal/job states to lock decisions:

- pending review-required proposal keeps blocker active;
- accepted/applied proposal clears its blocker;
- rejected/discarded proposal clears its blocker;
- stale/invalid proposal reaches terminal non-apply state with readable reason;
- read-only inspect remains allowed.

### 4.7 Observability

Every important result needs a readable trace:

- worker run summary;
- selected source unit refs;
- candidate material ref;
- proposal id;
- apply id or rejection reason;
- stale base conflict reason;
- lock cause and unblock reason.

Debug should not require raw JSON spelunking for the normal S3 path.

## 5. Proposed Implementation Sub-Slices

### S3a — Registry and candidate contracts

Scope:

- memory contract registry service/model;
- candidate DTOs and validators;
- base/source ref validation helpers;
- unit tests.

Gate:

- `D-S3-01` satisfied at unit/service level;
- invalid create/delete schema operations rejected;
- candidate validation rejects unsupported operation, missing source refs,
  unknown targets, and missing base revision.

### S3b — Memory worker adapter and fake harness path

Scope:

- MemoryMaintenanceWorker definition/adapter;
- fake model/fake tool path;
- structured output parse and no-op/failure variants;
- worker result creation.

Gate:

- fake worker run returns candidate batch / no-op / invalid schema failure;
- no memory truth is mutated;
- no setup-agent import or setup executor reuse.

### S3c — Governance routing and proposal handoff

Scope:

- normalized candidate -> proposal input mapping;
- policy outcome mapping:
  - W5 `review_required`;
  - W5 `direct_apply_allowed`;
  - W5 `blocked` / invalid;
- avoid misleading legacy labels for new S3 semantics.

Gate:

- review-required persists proposal without apply;
- direct-apply route calls governed apply;
- blocked/invalid fails closed with readable trace;
- `ProposalWorkflowService` and `ProposalApplyService` remain deterministic
  mutation owners.

### S3d — Lock matrix and stale base integration

Scope:

- maintenance lock integration for S3 blockers;
- stale base conflict behavior;
- proposal accept/reject/edit allowed during lock;
- inspect/debug allowed during lock.

Gate:

- `D-S3-03` and `D-S3-04` service/integration tests pass;
- stale base does not trigger model repair;
- terminal reject/discard/apply clears lock as designed.

### S3e — End-to-end and review gate

Scope:

- integration test from accepted source through worker/governance/apply;
- regression coverage for S0/S1/S2 paths touched by S3;
- optional bounded DeepSeek smoke after deterministic tests pass;
- fresh reviewer audit.

Gate:

- S3 integration path passes;
- relevant regression tests pass;
- `trellis-check` run for coherent slice;
- fresh reviewer findings adjudicated by main-brain.

## 6. SDD Decisions To Confirm With Assistant, Not User

The standing assistant should review these before implementation:

- exact package/module placement for registry, candidate DTOs, and validators;
- whether first path uses model-callable tools or structured output only;
- whether to introduce new candidate kind immediately;
- exact mapping of W5 governance terms to existing policy enum values;
- first operation subset;
- first target block/domain for the vertical slice;
- exact tests and fixtures.

These are engineering choices unless they change product behavior.

## 7. Rollback Plan

Each sub-slice must be path-level revertable.

Commit discipline:

- commit after each coherent planning / implementation / verification slice,
  not after every tiny edit;
- keep commit messages scoped to the runtime slice, for example
  `docs(rp-runtime): plan S3 memory worker governed apply`;
- stage only the files touched for that slice, using explicit paths;
- if task-local S3 documents must be versioned, use explicit force-add because
  `.trellis/tasks/` is ignored;
- do not include unrelated visible worktree changes in S3 commits;
- if a slice fails its gate, fix forward while small or revert only that slice's
  commit instead of resetting the whole worktree.

Preferred file grouping:

- registry/contracts in memory model/service modules;
- worker adapter/harness additions in story/worker runtime modules;
- governance mapping in proposal/governance modules;
- tests grouped by unit/service/integration responsibility.

Avoid broad edits in shared services without a consumer-backed test and importer
sweep.

## 8. Implementation Guardrails

- Do not import `rp.services.setup_agent`.
- Do not reuse setup executor or setup pseudo-tools.
- Do not add memory-specific behavior to harness core.
- Do not invent local reason-code aliases.
- Do not weaken existing S0/S1/S2 tests.
- Do not use ACE search.
- Do not touch unrelated user changes.
- Do not commit until green and explicitly authorized by the main-brain gate.
