# Story Runtime Stage W5 Scheduler Layer Development Spec

> Task: `.trellis/tasks/04-28-runtime-story-dev-task`
>
> Stage: W5
>
> Scope: Scheduler layer foundation + first runtime triggers
>
> Status: discussion-confirmed-draft-v1

## 1. Current Confirmed Direction

W5 is not a brainstorm-only consumer. W5 starts the real scheduler layer and
worker layer implementation for story runtime. Brainstorm `pending_processing`
batches are only the first product trigger.

The scheduler layer must be designed as core runtime infrastructure:

- it serves multiple triggers, not only brainstorm;
- it keeps orchestrator, scheduler decision, worker execution, and result
  ingestion separate;
- it is registry-driven and profile/snapshot-aware;
- it must not hardcode mode -> worker branches in the scheduler main path;
- it must keep LLM judgment in orchestrator / worker roles, not in final
  scheduler decision or mutation apply.

### 1.1 Milestone Language

Terms such as "initial implementation" or "Milestone A" are not allowed to mean
"permanent MVP".

Whenever this document uses an incremental milestone, it means:

- the current milestone must ship a real contract that will survive later
  iterations;
- deferred work must have an explicit follow-up milestone;
- no temporary shortcut may become the hidden long-term architecture.
- design discussion must state the overall target first, then select the W5-A
  implementation slice from that target.

Confirmed scheduler-layer evolution:

```text
W5-A: async job semantics + durable job/item/receipt contracts + lightweight
      in-process runner / test drain path.

W5-B: recoverable background execution: job recovery after restart, stale
      running-job detection, concurrency guard, and replaceable queue adapter.

W5-C: operational retry policy: narrow automatic retry for classified transient
      failures, retry budget, cancellation, admin/debug controls, and metrics.
```

W5-A is only the first delivery milestone. It must not block W5-B / W5-C by
encoding synchronous assumptions, hidden brainstorm coupling, or runner-specific
state into scheduler contracts.

For any future wording such as "first implementation", "initial slice", or
"W5-A", the spec / discussion must include:

- the complete intended capability family;
- which subset is implemented now;
- which subset is explicitly deferred;
- what contract prevents the initial subset from becoming a dead-end.

### 1.2 Requirement Translation Discipline

User discussion may describe product needs in informal or feature-first terms.
Implementation must translate those needs into professional engineering
contracts before coding.

For W5, this means:

- product phrases are not automatically service names, DTO names, or storage
  boundaries;
- "proposal", "accept", "version comparison", and "worker edits memory" must be
  implemented through scheduler / governance / Core apply contracts, not literal
  UI-driven shortcuts;
- the scheduler layer owns durable job / worker item / receipt semantics;
- proposal review owns user accept / reject / edit state;
- Core apply owns official memory revision adoption.

When product wording and engineering boundaries differ, implementation follows
the engineering contract documented here.

## 2. Layer Ownership

### 2.1 Orchestrator Worker

The orchestrator is primarily LLM-driven.

It may read a context window at least comparable to writer-visible context. For
post-write maintenance, it focuses on the latest canonical story prose window
or submitted brainstorm items and proposes which workers should inspect which
source units.

The orchestrator does not own truth and does not mutate memory.

It must not copy article text into dispatch output. Instead, it uses a structured
tool or equivalent strict structured output to select:

- target worker;
- source unit numbers from the current scheduler window;
- optional non-authoritative focus / reason hints.

The orchestrator's source routing is evidence selection, not a final semantic
judgment. It must not output memory updates, rewritten source content, Core
patches, or worker candidate content. Workers must still read the actual source
units and decide what to maintain for their own Core memory blocks.

### 2.2 Scheduler Decision

`SchedulerDecision` is a deterministic interpretation and裁决 layer between
orchestrator and workers.

It owns:

- trigger validation;
- source-window validation;
- source-unit-number to stable source-ref mapping;
- worker registry / profile / phase validation;
- permission / budget / context-policy validation;
- fallback / skip / degrade / async decisions;
- final `WorkerExecutionPlan`;
- trace / receipt reasons.

It must not parse free text from the orchestrator. It consumes only structured
tool results / structured proposal payloads.

### 2.3 Worker

Workers are bounded domain specialists.

They receive actual source text, stable source refs, branch-aware Core state
snapshots, and allowed tools. They may use Retrieval Broker / tools to read
Recall or Archival evidence.

Workers primarily maintain Core State authoritative facts and current
projections. They do not directly write Recall / Archival durable layers.
Recall lifecycle and Archival Evolution remain separate product paths.

Worker output is structured `WorkerResult`: proposal candidates, Core field
change candidates, projection refresh requests, findings, evidence refs, and
review/redirect receipts. Final mutation still goes through deterministic
governance / proposal / apply / projection services.

Workers must produce structured candidate new versions or explicit no-op
findings. A worker may "speculatively execute" by building the version it thinks
the owned memory block should become, but that candidate is not truth by itself.

Proposal is not primarily a worker-owned tool. In the scheduler layer, proposal
means the fixed governance path used when permissions require user review before
a worker-produced candidate version can become active truth.

The worker does not decide by itself whether a candidate is directly applied,
shown as a proposal, routed to review, or blocked. That decision is governed by
setup-configured worker permissions, runtime profile snapshot, domain policy,
and deterministic governance.

Confirmed permission outcomes:

```text
direct_apply_allowed
proposal_required
review_required
blocked
```

Brainstorm items, accepted prose windows, manual flush, and chapter flush all
use the same worker permission / governance path. Brainstorm does not get a
private direct-write path.

When review is required, fixed logic must materialize old/new block references
for frontend comparison:

- old version: current branch-visible Core block revision;
- new version: worker-produced candidate block revision;
- comparison surface: block-level version comparison, diff-style UI, or
  side-by-side block view;
- initial actions: accept or reject;
- reject leaves active Core unchanged;
- accept applies the candidate unless the user edited a block in the review
  surface, in which case the user-edited version wins.

This proposal review surface should be compatible with the broader runtime
version-comparison direction also needed for writer prose review, but W5-A only
needs the scheduler / memory-block contract and minimal accept/reject semantics.

W5-A worker candidates are block-level new versions. Field-level diffs / patches
may be derived for display or future optimization, but they are not the primary
worker output contract.

Recommended block-level candidate shape:

```text
target_block_ref
base_block_revision_id
candidate_revision_id
candidate_content
source_refs
evidence_refs
change_summary
no_op_reason
```

Rules:

- `base_block_revision_id` must match the current branch-visible block revision
  before apply / accept;
- if the base revision changed, the candidate is stale/conflicted and must not
  be directly accepted;
- one worker result may contain multiple block candidates;
- workers may only produce candidates for permitted / owned blocks;
- frontend diff rendering derives from old/current content and candidate
  content;
- if the user edits during proposal review, the user-edited block candidate
  becomes the accepted version.

When a proposal review contains multiple block candidates, accept / reject is
block-level. Batch actions such as "accept all" or "reject all" are UI
convenience only; the persisted semantics remain per block.

Recommended per-block review statuses:

```text
pending_review
accepted
rejected
edited
stale
applied
```

Recommended proposal review aggregate statuses:

```text
pending_review
partially_accepted
accepted
rejected
partially_stale
```

A stale/conflicted block candidate blocks only that block candidate. It must not
force unrelated candidates in the same scheduler job / proposal review to fail.

Worker-produced candidate new versions are stored as Runtime Workspace material,
not as active Core truth and not as frontend-only state.

W5-A storage contract:

```text
RuntimeWorkspaceMaterial.kind = WORKER_CANDIDATE
visibility = review_visible or worker_visible
metadata.source_of_truth = false
metadata.authoritative_mutation = false
```

The candidate material payload contains the block-level candidate fields such as
`target_block_ref`, `base_block_revision_id`, `candidate_content`, `source_refs`,
`evidence_refs`, and `change_summary`.

`ProposalReview` stores old/current Core block refs and candidate material refs.
It does not duplicate Core truth and does not own candidate payload truth.

Lifecycle mapping:

- accepted / applied candidate: material lifecycle becomes `promoted`;
- rejected candidate: material lifecycle becomes `discarded`;
- stale / conflicted candidate: material lifecycle becomes `invalidated`.

Runtime Workspace storage for worker candidates must be repository-backed and
identity-scoped. In-process-only storage is not acceptable for W5-A because the
proposal review must survive refreshes and later requests.

Accepting a proposal does not cause the proposal UI to write Core directly.
Accepting means the user-approved candidate version is handed to the shared
governed Core mutation / apply path as the version to adopt.

Because the worker has already speculatively produced the complete candidate new
version, accept does not rerun the worker and does not ask the worker to produce
a second patch. The remaining work is formal adoption:

- re-check `base_block_revision_id` against the current branch-visible revision;
- create the official Core block revision from the accepted candidate or
  user-edited version;
- update the branch-visible manifest / pointer;
- record MemoryChangeEvent / apply receipt / audit refs;
- mark projection dirty or request projection refresh when needed.

Scheduler, proposal review, and Core apply have separate lifecycles:

- `SchedulerJob` / `SchedulerWorkerItem`: worker execution and candidate
  production lifecycle;
- `ProposalReview`: user review / accept / reject / edit lifecycle;
- `CoreApplyReceipt`: official Core adoption lifecycle.

User accept / reject must not rewrite a completed scheduler job into proposal or
apply status. The records should link by ids, but each owns its own state.

## 3. Trigger Semantics

The scheduler layer supports multiple trigger families. Current confirmed W5
families:

```text
brainstorm_batch_submitted
accepted_prose_k_window
manual_flush
chapter_close_flush
```

### 3.1 Brainstorm Trigger

`brainstorm_batch_submitted` consumes only frozen batches and active items that
became `pending_processing`.

Deleted brainstorm items are visible history only. They must never be uploaded
to scheduler decision or worker context.

Brainstorm items are plain user intent source refs. They are not Core patches,
not target layers, and not worker routing fields.

### 3.2 Accepted Prose K-Window Trigger

`K` counts only confirmed canonical story segments.

It does not count:

- chapter outline;
- draft writer output;
- unaccepted pending segment;
- rewrite candidate;
- repeated rewrites before final adoption;
- discussion;
- brainstorm discussion or unsubmitted brainstorm batch.

The count should be recorded as a branch-aware accepted segment index, not as a
global turn count. Recommended naming:

```text
canonical_segment_index
accepted_story_segment_index
```

When a third segment is rewritten several times before acceptance, the count
stays at `2` until the final segment is accepted. Only then does it become `3`.

For branch / rollback, the active branch's current accepted segment index is
the source of truth:

- branch from segment 2 starts from count `2`;
- rollback to segment 1 resets the active view to count `1`;
- source-branch future segments do not affect the child branch count.

The accepted/adoption turn should carry the accepted segment index metadata so
window computation is replayable.

### 3.3 K-Window Boundaries

Normal trigger:

- if `K=3`, accepted segments `1,2,3` form window 1;
- `4,5,6` form window 2;
- `7,8,9` form window 3.

Scene close does not trigger maintenance and does not cut a window. Windows may
cross scene boundaries. Workers inspect scene / source metadata and decide how
to maintain memory.

Chapter close may force-flush an incomplete tail window. For example, if `K=3`
and the chapter ends at segment 5, segments `4,5` are flushed as an incomplete
tail window.

Manual flush is allowed. In W5-A it may be exposed only as an internal / debug
trigger, but product UI support remains a planned W5-B/W5-C follow-up. Manual
flush must not change the canonical segment index; it only submits the current
unprocessed window.

## 4. Scheduler Source Unit Mapping

W5-A must normalize different trigger inputs into one internal source-window
shape instead of creating one scheduler path for brainstorm and another for
accepted prose.

The internal source unit contract is:

```text
SchedulerSourceUnit
- source_unit_number: 1..N, window-local only
- source_unit_type: accepted_story_paragraph | brainstorm_item | future kinds
- source_text: the text visible to orchestrator / worker for this unit
- stable_source_ref: persisted reference used by trace / worker / receipts
- source_hash: replay / idempotency evidence
- metadata: branch, turn, segment, beat, brainstorm batch/item refs as needed
```

The abstraction is allowed only as a positive optimization:

- it reduces duplicate trigger-specific scheduler logic;
- it keeps orchestrator input simple by exposing `1..N`;
- it must not leak into writer, brainstorm UI, or proposal UI contracts;
- if implementation becomes heavier than direct mapping, it should shrink to a
  lightweight intake helper instead of becoming a broad framework.

W5-A acceptance must prove this is a shared scheduler abstraction by supporting
both `brainstorm_batch_submitted` and `accepted_prose_k_window` as real product
triggers.

### 4.1 Accepted Prose Mapping

Every accepted story segment should be deterministically normalized into
paragraph blocks immediately after adoption.

For each scheduler window, the intake layer creates a short-number mapping:

```text
1 -> stable source ref for paragraph/block A
2 -> stable source ref for paragraph/block B
...
N -> stable source ref for paragraph/block N
```

The orchestrator sees source unit numbers `1..N` and the corresponding paragraph
texts. It does not need to see complex refs such as `seg_018#p02`.

The mapping is window-local and temporary:

- `source_unit_number=7` is valid only inside the current scheduler window;
- persisted trace, worker result, proposal, and mutation receipts must store the
  stable source ref, not the short number.

Stable source refs should retain enough information for branch/debug/replay:

- story/session/branch/turn identity;
- accepted story segment artifact id;
- paragraph block id;
- order;
- text hash;
- optional scene / beat metadata when available.

The mapping layer can be implemented as an ordered array plus validation:

- orchestrator passes integer numbers;
- the scheduler rejects numbers outside `1..N`;
- duplicates are deduped deterministically;
- final worker packets receive stable refs and actual text.

### 4.2 Brainstorm Item Mapping

For `brainstorm_batch_submitted`, the source window is the frozen submitted
brainstorm batch after user review.

Only active items are mapped:

```text
1 -> stable source ref for brainstorm item A
2 -> stable source ref for brainstorm item B
...
N -> stable source ref for brainstorm item N
```

Deleted / struck-through brainstorm items remain review history only. They must
not become scheduler source units and must not be uploaded to workers.

Brainstorm source units are user-intent evidence. They are not Core patches,
target layers, memory operations, or worker routing instructions.

## 5. Job Idempotency, Async Execution, And Retry Semantics

The scheduler layer must be idempotent from W5-A.

The goal is simple: the same source window must not run workers twice and must
not create duplicate Core maintenance results.

### 5.1 Window Fingerprint

Before creating a scheduler job, intake / decision logic must compute a stable
`window_fingerprint`.

Recommended minimum inputs:

- `story_id`;
- `branch_id`;
- `trigger_type`;
- stable source refs included in the window;
- source text hashes;
- scheduler profile / policy version;
- `maintenance_window_index` when available.

If the same fingerprint already exists:

- `completed`: return the existing receipt or write a linked no-op receipt;
- `running`: report the existing in-flight job instead of creating another job;
- `failed` / `partial_failed`: retry only failed worker items;
- changed source refs / hashes / profile version: create a new fingerprint and a
  new job, linked to the previous receipt for traceability.

`manual_flush` and `accepted_prose_k_window` may arrive through different
trigger paths. If they resolve to the same branch-visible source window and the
same profile version, they must dedupe through the same fingerprint instead of
dispatching duplicate worker execution.

### 5.2 Minimal Job State

W5-A does not need a full external workflow engine, but it does need durable
scheduler job and worker-item state.

Minimum job statuses:

```text
pending
running
completed
partial_failed
failed
skipped
```

Minimum worker item statuses:

```text
pending
running
completed
failed
skipped
```

If some worker items succeed and some fail, the scheduler job status is
`partial_failed`, not `failed`.

Successful worker items must not be rerun during retry. Failed worker items must
be retryable as separate child attempts linked to the original scheduler job /
receipt.

W5-A uses manual retry as the default and expected retry path. Worker failure
should expose the failure reason, preserve the failed receipt, and wait for
explicit developer / operator retry after the cause is understood. Blind
automatic retry is out of scope for W5-A, but W5-C must add a narrow automatic
retry policy for classified transient failures.

Required W5-A objects:

- `SchedulerJob`;
- `SchedulerWorkerItem`;
- `SchedulerReceipt`;
- `SchedulerRetryReceipt`.

Storage should enforce uniqueness for active `window_fingerprint` records where
possible, so concurrent trigger paths cannot create duplicate jobs.

### 5.3 Async Job Execution

Scheduler execution has async job semantics from W5-A.

Trigger submission should create or reuse a `SchedulerJob` and return job /
receipt status. It must not require the caller to wait for all orchestrator and
worker work to finish inside the request path.

W5-A runner can be lightweight:

- in-process background runner;
- explicit `run_pending_once()` / test drain path;
- no external queue dependency required.

This is an implementation choice, not a contract shortcut. Scheduler contracts
must already support:

- `pending` / `running` / terminal job states;
- worker item attempts;
- idempotent re-entry by `window_fingerprint`;
- manual retry of failed worker items;
- status / receipt queries by job id.

W5-B must make the runner recoverable and replaceable:

- recover pending/running-recoverable jobs after process restart;
- detect stale `running` jobs;
- enforce concurrency guards;
- isolate queue adapter behind scheduler runner interfaces.

External queue systems are a W5-B/W5-C implementation detail. They must not
change trigger, job, worker item, failure, or receipt contracts.

### 5.4 Job Completion And Result Ingestion Boundary

`SchedulerJob.status=completed` does not mean Core memory definitely changed.

It means:

- selected worker items reached terminal success or accepted skip/degrade states;
- every completed worker result passed structured schema validation;
- `WorkerResultIngestion` accepted the result and produced structured downstream
  artifacts such as proposal candidates, Core change candidates, projection
  refresh requests, findings, or governance receipts;
- scheduler receipts record what was handed to governance / proposal / apply.

Actual Core mutation remains owned by deterministic governance / proposal /
apply / projection services. A completed scheduler job may produce:

- applied Core changes;
- pending review proposals;
- rejected governance decisions;
- no-op findings;
- projection refresh requests without immediate Core field changes.

Therefore UI, debug tools, and tests must not infer "memory updated" from
`SchedulerJob.completed` alone. They must inspect downstream governance / apply
receipts when they need to know whether Core State changed.

If worker execution succeeds but result ingestion fails, the job is not
`completed`. It is `failed` or `partial_failed` with a `governance_error`,
`persistence_error`, or another specific failure reason.

WorkerResultIngestion must not hardcode direct apply versus proposal behavior.
It resolves the active worker permission profile and domain policy, then routes
structured candidates to governed direct apply, proposal creation, review, or
blocked receipt.

For review-required permissions, WorkerResultIngestion creates a proposal review
record that points to the old/current block revision and the worker-produced new
candidate revision. The frontend owns comparison rendering. The worker only
needs to produce a valid candidate new version or choose no-op.

When a review block is accepted, the accepted candidate or user-edited candidate
must enter the same governed Core apply path used by direct edit / worker apply
entrypoints. Proposal review UI never owns Core writes.

### 5.5 Failure Classification And Observability

W5-A starts with a small, known set of failure categories and reason codes, then
W5-B/W5-C expand classification rules from real test / development failures.

The goal is not to eliminate `unknown_error`. The goal is to make every failure
inspectable, retry-safe, and easy to promote from unknown to a known code later.

Initial failure categories:

```text
validation_error
permission_error
source_error
orchestrator_error
worker_error
retrieval_error
governance_error
persistence_error
upstream_error
unknown_error
```

Initial reason codes that W5 is expected to hit:

```text
window_fingerprint_conflict
source_window_empty
source_ref_not_found
paragraph_number_out_of_range
worker_not_active
worker_permission_denied
orchestrator_schema_invalid
orchestrator_provider_error
worker_output_schema_invalid
worker_provider_error
retrieval_query_failed
governance_rejected
receipt_write_failed
unknown_error
```

Every scheduler / worker failure receipt must keep both normalized fields and
raw evidence:

- `failure_id`;
- `category`;
- `reason_code`;
- user / developer readable `message`;
- `retryable`;
- `retry_mode`: `manual`, `auto_allowed`, or `never`;
- `component`: scheduler / orchestrator / worker / retrieval / governance /
  persistence;
- `job_id`, `worker_item_id`, `worker_id`, and `attempt` when available;
- related stable source refs;
- raw exception type / raw message;
- provider name, upstream status code, upstream error code, and request id when
  available.

Unknown failures must default to manual inspection, not automatic retry. During
development, high-frequency unknown failures should be promoted into explicit
reason codes with regression tests.

## 6. Orchestrator Tool Shape

The orchestrator should use a structured tool or equivalent strict structured
output. Recommended first shape:

```python
class OrchestratorDispatchSelection(BaseModel):
    worker_id: str
    source_unit_numbers: list[int]
    focus_hint: str | None = None
    reason_codes: list[str] = Field(default_factory=list)


class OrchestratorDispatchToolInput(BaseModel):
    selections: list[OrchestratorDispatchSelection]
```

Rules:

- `worker_id` must resolve through registry/profile;
- `source_unit_numbers` must be non-empty and window-valid;
- `focus_hint` is non-authoritative. It may say "possible relation change" but
  must not be treated as fact;
- the orchestrator cannot submit field paths, old values, new values, target
  layers, memory operations, rewritten source text, or candidate memory content.

## 7. Modular Engineering Boundary

The scheduler layer is a core module. It must not be implemented as one large
service file or as a brainstorm-private path.

Recommended modules:

```text
backend/rp/models/scheduler_runtime_contracts.py
backend/rp/services/scheduler_trigger_intake_service.py
backend/rp/services/orchestrator_execution_service.py
backend/rp/services/scheduler_decision_service.py
backend/rp/services/worker_context_builder_service.py
backend/rp/services/worker_execution_service.py
backend/rp/services/worker_result_ingestion_service.py
backend/rp/services/scheduler_job_store_service.py
backend/rp/services/scheduler_runner_service.py
backend/rp/services/scheduler_receipt_service.py
```

`worker_scheduler_service.py`, if kept, should be a facade / coordinator. It
must not own intake, source mapping, orchestrator execution, decision validation,
worker context building, worker execution, result ingestion, and receipt
persistence all at once.

Cross-module contracts must be typed DTOs, not loose dicts:

- `SchedulerTrigger`;
- `SchedulerJob`;
- `SchedulerWorkerItem`;
- `SchedulerFailure`;
- `MaintenanceWindow`;
- `WindowParagraphRef`;
- `OrchestratorPlanProposal`;
- `SchedulerDecision`;
- `WorkerExecutionPlan`;
- `WorkerExecutionItem`;
- `WorkerContextPacket`;
- `WorkerResult`;
- `SchedulerReceipt`.

## 8. Non-Negotiable Constraints

- Scheduler main path is registry-driven. No hardcoded mode -> worker mapping.
- Trigger intake does not decide memory mutations.
- Orchestrator does not write memory and does not copy source prose into output.
- Scheduler Decision is deterministic and owns final裁决.
- Workers do not directly write truth.
- Workers submit structured block-level candidate new versions or no-op
  findings; runtime profile and governance decide direct apply / proposal /
  review / block.
- Proposal review is a fixed governance path with old/new block version refs,
  not a worker-private freeform tool.
- Proposal accept adopts an already-produced candidate through the shared Core
  apply path; it does not rerun worker logic and does not let UI write Core.
- Worker candidate new versions are stored as repository-backed Runtime
  Workspace `WORKER_CANDIDATE` material before adoption.
- SchedulerJob, ProposalReview, and CoreApplyReceipt lifecycles are separate and
  linked by ids; accept / reject does not mutate scheduler job status.
- Field-level diffs / patches are derived views or future optimization, not the
  W5-A worker output contract.
- Multi-block proposal review is persisted as per-block accept / reject state;
  batch actions are UI convenience only.
- Stable source refs, not temporary paragraph numbers, are persisted.
- Same window / trigger rerun must be idempotent or produce a clearly linked
  retry receipt.
- `window_fingerprint` dedupe must prevent duplicate worker execution for the
  same source window.
- Worker retry must rerun only failed worker items, not completed items.
- W5-A defaults to manual retry; automatic retry must not hide worker failures
  during development, and W5-C must introduce only classified transient
  automatic retry.
- Unknown failures must retain raw evidence and default to manual inspection.
- Scheduler has async job semantics from W5-A even if the runner is lightweight
  and in-process.
- `SchedulerJob.completed` means scheduling / worker result ingestion completed;
  it does not guarantee Core mutation.
- Writer packet must not include pending scheduler scratch by fallback.

## 9. Required Tests

Minimum W5 scheduler-layer tests:

- accepted segment adoption increments branch-aware `canonical_segment_index`;
- outline, draft output, unaccepted rewrite candidates, and brainstorm discussion
  do not increment the count;
- branch from segment N starts with count N;
- rollback to segment N resets active visible count to N;
- K-window normal trigger selects segments by branch-visible accepted index;
- chapter close flushes incomplete tail window;
- scene close does not flush and does not cut windows;
- manual flush submits the current tail window without changing segment index;
- paragraph numbers `1..N` map to correct stable source refs;
- invalid paragraph numbers are rejected by Scheduler Decision;
- duplicate paragraph numbers are deduped deterministically;
- inactive / unknown worker ids from orchestrator output are rejected or
  fallbacked with trace;
- deleted brainstorm items never enter scheduler decision;
- worker result ingestion refuses free-text mutation and only accepts structured
  candidates / requests / receipts.
- same `window_fingerprint` cannot create duplicate scheduler jobs;
- `completed` job rerun returns existing / linked no-op receipt without rerunning
  workers;
- `running` job rerun reports the existing in-flight job;
- `partial_failed` retry reruns only failed worker items;
- worker failure records an inspectable error reason before manual retry;
- known failure categories / reason codes are written to failure receipts;
- unknown failures preserve raw evidence and are not auto-retried;
- trigger submission creates / reuses a job and can return before worker
  execution finishes;
- lightweight runner can drain pending jobs without changing scheduler
  contracts;
- completed scheduler job can correspond to applied, pending-review, rejected,
  no-op, or projection-refresh-only downstream outcomes;
- ingestion failure prevents job from becoming `completed`;
- worker permission outcomes are derived from runtime profile / domain policy,
  not hardcoded by scheduler or trigger source;
- worker candidate apply checks `base_block_revision_id` against the current
  branch-visible block revision and rejects stale/conflicted candidates;
- stale/conflicted block candidates do not block unrelated block candidates in
  the same proposal review;
- proposal accept uses the shared governed Core apply path and records apply /
  change receipts;
- proposal accept / reject updates proposal review and apply receipts, not the
  already-completed scheduler job status;
- worker candidate material lifecycle becomes `promoted`, `discarded`, or
  `invalidated` according to accept / reject / stale outcomes;
- manual flush and K-window triggers dedupe when they resolve to the same source
  window.
