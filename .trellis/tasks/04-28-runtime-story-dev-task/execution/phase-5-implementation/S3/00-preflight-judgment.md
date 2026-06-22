# S3 Preflight Judgment — story agent harness and memory worker path

> Date: 2026-06-22
> Status: current execution judgment, not final S3 design
> Scope: story agent framework / harness, S3 risks, attention points, and next work

## 0. How to read this document

This document is a preflight judgment before writing the real S3 slice brief and
design. It does not replace the frozen SoT, module docs, or the phase-5 process
spec. It records the current implementation reading and the recommended next
move.

Use it as input for:

- `S3/00-slice-brief.md`
- `S3/01-impact-sweep.md`
- `S3/02-design.md`
- later P3 / P4.5 review prompts

Primary evidence checked:

- `execution/00-INDEX.md`
- `execution/phase-3-slicing/slice-plan.md`
- `execution/phase-5-implementation/00-PROCESS-SPEC.md`
- `execution/phase-5-implementation/S0/01-design.md`
- `execution/phase-5-implementation/S2b/00-slice-brief.md`
- `execution/phase-5-implementation/S2b/02-design.md`
- `research/modules/runtime-agent-harness.md`
- `research/modules/runtime-worker-family.md`
- `research/modules/runtime-memory-domain-block.md`
- `research/modules/runtime-scheduler-governance.md`
- `backend/rp/agent_runtime/story/story_harness.py`
- `backend/rp/agent_runtime/kernel/runtime_tool_contracts.py`
- `backend/rp/services/writer/worker_execution_service.py`
- `backend/rp/services/story/runtime_adapter_service.py`
- `backend/rp/services/proposal/post_write_governance_service.py`

YCE was run for code context and found the current story harness, S0 harness
test, zone-boundary lint, and generic graph builder. ACE search was cancelled by
the user, so this judgment is grounded in local file reads plus YCE's code
locator result.

## 1. Current judgment

The next step should be S3, but S3 should start by making the first real worker
consume the shared story-agent harness. Do not detour into building a complete
generic agent framework first, and do not bypass the harness by adding another
private worker loop.

The recommended direction is:

```text
S0 test harness substrate
-> S1/S2 turn and scheduler spine
-> S3 first real memory-maintenance worker consumer
-> minimal production harness additions required by that consumer
-> proposal/governance handoff
```

This means "完善基座" and "进入 S3" are not separate tracks. S3 should be the
first production pressure test for the base harness.

## 2. Current implementation state

### 2.1 What already exists

Current agent-runtime code is split into zones:

- `kernel/`: shared generic substrate.
- `setup/`: setup-only runtime code.
- `story/`: story-owned harness substrate.

The useful landed base pieces are:

- `build_runtime_graph`: a project-owned LangGraph state-machine builder with
  injected node callables.
- `RuntimeToolCall` / `RuntimeToolResult`: setup-free tool call/result contracts
  under `kernel/runtime_tool_contracts.py`.
- `story/story_harness.py`: a story-owned test harness over the shared graph.
- S0 tests: import-clean story harness path and fake model/tool loop.
- zone-boundary lint: guards setup/story/kernel import direction.

The current `story_harness.py` can run this loop:

```text
scripted model response
-> inspect tool call
-> execute allowlisted noop tool
-> append tool result to messages
-> continue model round
-> finalize text or fail by max rounds
```

This is enough as a substrate and test oracle seed.

### 2.2 What does not exist yet

The current harness is explicitly test-only. It is not yet the production story
agent harness required by S3.

Missing production pieces include:

- role / worker adapter interface;
- real model gateway integration for story workers;
- structured output parsing and validation for worker candidates;
- bounded repair policy for invalid structured output;
- production story tool provider or executor interface;
- per-worker tool allowlist;
- source-ref and base-ref attachment;
- candidate-to-governance handoff;
- readable trace / event shape for worker results;
- consumer-backed failure injection beyond the S0 noop loop.

Current S3-adjacent production flow still uses the legacy bridge:

```text
WorkerExecutionService
-> LongformSpecialistService.analyze(...)
-> StoryRuntimeAdapterService.adapt_specialist_bundle_to_worker_result(...)
-> proposal candidate kind = legacy_state_patch
-> PostWriteGovernanceService accepts legacy_state_patch only
```

That path is useful as migration evidence, but it should not become the final S3
worker architecture.

## 3. What S3 is actually about

Per the ratified slice plan, S3 is:

```text
Memory domain/block + worker family + proposal/apply
```

Dependencies:

- S0: harness substrate.
- S1-core / S1b: turn lifecycle and interruption behavior.
- S2/S2b: scheduler decision, gate, job lifecycle, and fail-closed dispatch.

S3 should supply the worker body and candidate path that S2 intentionally left
out. S2 already creates the scheduler-visible request/job/gate surface; S3 must
make the selected memory-maintenance worker produce structured, governed
candidate material.

The complete target should remain:

```text
scheduler-selected worker context
-> bounded maintenance worker
-> structured candidates / findings / no-op / failure receipt
-> deterministic ingestion
-> proposal/governance
```

The worker must not directly apply memory, projection, Recall, or Archival
changes.

## 4. Main S3 difficulties

These are not "hard AI research" problems. They are integration and contract
problems. The risk is mostly building the wrong boundary.

### 4.1 First production harness consumer

S3 is likely the first real consumer of the story harness. That makes it
tempting to add a worker-specific private loop just to get the slice moving.
That should be avoided.

S3 should add only the minimal shared harness capabilities needed by the first
maintenance worker:

- normalized input/output envelope;
- fake model support;
- optional tool loop through the common tool interface;
- structured output parse result;
- stop reason;
- invalid schema handling;
- traceable result or failure receipt.

Anything specific to memory rules belongs in the maintenance role adapter, not
in the generic harness core.

### 4.2 Candidate schema and validation

The model should not emit final proposal records, proposal IDs, policy decisions,
priority, confidence, scheduler status, or free-form metadata.

The narrow first candidate shape should be close to:

```text
MaintenanceProposalCandidateBatch
  schema_version
  candidates[]

MaintenanceProposalCandidate
  operations[]
  base_refs[]
  source_refs[]
  reason
```

The adapter and deterministic validator should own:

- mapping handles to real source refs;
- attaching base refs;
- checking operation kinds;
- checking domain/block targets;
- rejecting stale or missing revisions;
- rejecting forbidden operations;
- converting valid candidates into the existing proposal/governance input.

The model supplies candidate content. Backend code decides whether it is valid.

### 4.3 Source refs and base refs

This is the most important S3 correctness boundary.

Workers must not invent persistent IDs. LLM-facing handles can be temporary, but
the adapter must map them back to accepted source units, runtime materials,
memory facts, and known base revisions.

Stale base revision is not a model self-repair problem. If the base is stale,
the backend should reject, invalidate, replan, or rerun with fresh context.

### 4.4 Tool design

Tool support is a shared harness capability, but S3 does not have to enable
model-callable tools in the first worker if the first behavior can be done from
the worker packet.

If tools are enabled, they must enter through a normalized story runtime tool
provider:

- name;
- description;
- JSON-schema-like input schema;
- allowlist;
- normalized success result;
- normalized error result;
- timeout/cancellation behavior;
- readable trace metadata;
- fake provider for tests.

Do not expose setup pseudo-tools, setup tool scopes, or setup recovery policy as
story runtime contracts. Also do not expose another worker as an immediate peer
tool. If cross-agent work is needed, represent it as a scheduler-visible worker
request.

### 4.5 Governance handoff

Current `PostWriteGovernanceService` accepts `legacy_state_patch`. S3 needs a
cleaner candidate handoff.

There are two possible implementation paths:

1. Add a new candidate kind for normalized maintenance candidates.
2. Convert the normalized S3 candidate into existing proposal submit inputs
   before reaching the old `legacy_state_patch` branch.

The second path may be less disruptive if it keeps legacy compatibility, but it
must not hide S3 semantics inside a misleading `legacy_state_patch` label.

Whichever path is chosen, final apply remains deterministic backend governance.

### 4.6 Legacy bridge boundary

`LongformSpecialistService` currently survives behind the memory-worker path.
S3 should decide explicitly whether the first worker:

- replaces the legacy bridge for the selected path; or
- runs in parallel behind a feature/profile gate; or
- wraps legacy output only as a temporary migration adapter.

It should not silently add a second candidate source that makes governance
inputs hard to explain.

### 4.7 Tests and oracle shape

S3 must be consumer-backed. Passing unit tests around DTO parsing is not enough.

The RED oracle should drive the real post-write worker path with fakes:

- scheduler selects memory worker;
- worker receives a realistic context packet;
- fake model emits candidate batch;
- adapter validates and maps refs;
- governance receives valid proposal input or a clear rejection/failure receipt.

The first oracle should cover at least:

- valid candidate -> proposal/governance input created;
- `candidates: []` -> legal no-op;
- invalid schema -> rejected;
- unsupported operation kind -> rejected;
- missing source ref -> rejected;
- missing or stale base ref -> rejected;
- domain/block mismatch -> rejected;
- permission-denied operation -> rejected;
- legacy path remains bounded and does not become the new public contract.

## 5. Things to be careful about

### 5.1 Do not read old S0 documents blindly

`S0/00-slice-brief.md` still contains an earlier wider extraction idea. The
authoritative correction is `S0/01-design.md` rev.3: story-owned harness, no
setup executor reuse, split only genuinely generic tool contracts.

When in doubt, follow rev.3 and the node-2 frozen SoT, not the earlier brief.

### 5.2 Do not make the harness too thick

The harness should not know memory domain rules, proposal authority, source-ref
semantics, or stale-base policy. Those belong to role adapters, scheduler, and
governance.

The harness should know how to run a bounded agent call and produce normalized
mechanical outcomes.

### 5.3 Do not put product authority in tool names

A tool name such as `memory.patch` or `proposal.create` must not imply final
apply authority. Authority must be checked by runtime profile, worker
definition, scheduler policy, and governance.

### 5.4 Do not reopen settled framework debates during S3

The research/module docs already settle these points:

- `retrieval` is a service/tool capability, not an agent family.
- `persona` is a context-worker subtype, not a top-level family.
- direct agent-to-agent handoff is not the core path.
- external frameworks stay below project-owned contracts.
- setup is reference-first and extraction-last.

S3 should use those as constraints, not reopen them as product questions.

### 5.5 Keep S3 narrow

The first S3 implementation should not include:

- full domain/block editor UX;
- broad contradiction detection;
- historical dirty-data repair;
- all memory operation kinds;
- writer self-retrieval;
- async multi-job retry policy;
- full proposal review UI.

Those may come later. The first slice should prove the worker/candidate/governance
path with a small set of operations.

## 6. Recommended next work

### P0: write the S3 slice brief

Define the first S3 consumer as a narrow memory-maintenance proposal producer.

Suggested in-scope:

- worker body for selected longform memory maintenance;
- minimal production harness surface needed by that worker;
- structured candidate batch schema;
- adapter validation and ref mapping;
- proposal/governance handoff;
- no direct apply.

Suggested out-of-scope:

- full UI;
- broad retrieval;
- chapter-close flush;
- brainstorm submission processing;
- revision/rewrite flow;
- all operation kinds.

### P1: impact sweep

Read and enumerate at least:

- `WorkerExecutionService`
- `StoryRuntimeAdapterService`
- `PostWriteGovernanceService`
- proposal input builder / submit models
- memory/domain/block model records
- worker registry and selected worker definitions
- context packet builder for worker packets
- runtime tool provider references, if tools are enabled
- current tests around S2b worker execution and governance

The sweep must answer what is legacy bridge, what is reusable contract, and what
must be replaced for S3.

### P2: design + pseudocode

The S3 design should explicitly define:

- production harness entrypoint or adapter interface used by the worker;
- maintenance role adapter responsibilities;
- candidate batch schema;
- validation pipeline;
- source/base ref mapping;
- allowed operation kinds;
- governance handoff shape;
- no-op and failure receipt shape;
- fake model/tool test interfaces;
- rollback plan.

### P3/P4.5 review prompts

Reviewers should be asked to check against:

- HAR-003 / HAR-004 setup boundary;
- runtime-agent-harness module responsibilities;
- worker-family output expectations;
- memory/domain/block constraints;
- scheduler/governance authority boundary;
- S2b consumer path and gate lifecycle;
- no curve-fit / no weakened assertions.

## 7. Proposed first S3 acceptance shape

The first acceptance should be phrased in user-visible engineering terms:

```text
After a post-write maintenance trigger, the scheduler can select the memory
worker. The worker runs through the story runtime harness with a fake model,
returns structured maintenance candidates, and deterministic backend code either
turns those candidates into governance-ready proposal input or rejects them with
a readable reason. No LLM output directly mutates memory.
```

This is the smallest useful proof that the story agent harness, worker family,
memory/domain contracts, and governance boundary are connected correctly.

