# Runtime Story Overall Implementation Roadmap

Status: mandatory pre-implementation gate
Task: `04-28-runtime-story-dev-task`
Created: 2026-06-23
Last updated: 2026-06-23

## Process Correction

This document is the main construction map for the new story runtime work.
It must exist and be consulted before new implementation slices start.

The earlier S3 work had useful local inputs:

- Node-1 grill and module requirement documents;
- S3 PRD / SDD / test plan;
- per-slice briefs, results, checks, and reviews.

Those inputs were not enough as a project-level construction map. A local
slice plan can explain how to implement one piece, but it cannot replace the
overall sequencing, dependency, boundary, test, and rollback plan. Treat this
as a process correction: do not continue feature implementation or commit
pending S3g-b work until this roadmap and the S3 retrospective gate have been
checked.

## Requirement Authority

Use this order when planning or reviewing implementation:

```text
research/index.md
  -> research/modules/*
  -> indexed Node-1 grill/source documents
  -> execution/phase-1-spec-freeze/*
  -> execution/phase-3-slicing/*
  -> execution/main-brain/*
  -> current slice PRD / SDD / test plan / brief
  -> current code evidence
```

If requirements appear unclear, read the documents above before asking the
user. Ask only when the requirement is still missing, contradictory, or
infeasible after reading the documents.

## Target Architecture

The target runtime is a story-agent framework plus product-specific adapters
and deterministic services.

```text
story-agent harness
  -> role / worker definitions
  -> compiled runtime profile snapshot
  -> context packet and read manifest
  -> allowlisted tools with structured input/output/error
  -> structured model output validation
  -> scheduler / governance / review policy
  -> deterministic apply services
  -> trace, debug, and test evidence
```

Boundary rule:

```text
Harness core owns reusable execution mechanics.
Role adapters, worker definitions, tools, profiles, and product services own
story policy, memory semantics, proposal routing, review policy, and state
mutation.
```

The harness must not become a memory-specific or setup-style custom executor.
The product services must not hide model or tool output as authoritative state.

## Work Authorization Gate

Before any new implementation slice starts, the main-brain must confirm that
all items below exist in writing:

| Gate item | Required content |
| --- | --- |
| Source requirements | Exact `research/`, `modules/`, freeze, and slice documents to use. |
| Target behavior | What the feature must do in product terms. |
| Architecture boundary | Harness core vs role adapter vs tool vs deterministic service. |
| Old path policy | Which MVP/legacy paths are preserved, adapted, replaced, or quarantined. |
| Data/state path | Records, material, proposals, locks, receipts, and branch-visible state touched. |
| Tool contract | Structured input, structured output, error shape, retryability, trace metadata, and governance path. |
| Failure behavior | Invalid schema, unknown target/tool, stale base, permission/policy denial, timeout, partial failure, and no-op. |
| Tests | Unit, service, integration, regression, and optional live-provider smoke coverage. |
| Review | Assistant/reviewer review before code and fresh reviewer after milestone. |
| Commit plan | Slice-owned file list, expected dirty-file exclusions, rollback boundary. |

If a slice lacks these items, it is not ready for implementation. It may only
proceed as planning or audit work.

## Phase Map

### Phase 0: Overall Construction Control

Purpose:

- freeze this roadmap as the project-level construction map;
- audit already-landed S3 work against it;
- prevent further implementation from being driven only by local briefs.

Entry:

- Node-1 grill and module documents are readable and indexed.
- Current worktree status is known.

Exit:

- this roadmap is updated;
- S3 retrospective exists;
- pending S3g-b is either committed as a bounded compatibility slice or revised;
- next slice cannot start without passing the work authorization gate.

### Phase S0: Story-Agent Harness Substrate

Purpose:

- provide setup-free generic execution contracts and fake test surfaces;
- prove no setup-agent imports or setup executor coupling.

Status:

- minimum substrate exists;
- not a complete production executor for every story role.

Must remain true:

- no setup-agent executor reuse;
- generic contracts stay free of memory/proposal policy.

### Phase S1: Identity / Profile / Turn Base

Purpose:

- pin runtime identity, branch, turn, and profile snapshot;
- provide stable material for packet and scheduler decisions.

Status:

- base exists and is used by later slices.

Later dependency:

- S4 retrieval, S5 chapter close, and S6 rewrite must preserve the same
  branch/profile/turn identity discipline.

### Phase S2: Scheduler / Job / Governance Spine

Purpose:

- select workers deterministically;
- represent jobs, gates, proposals, and terminal receipts;
- keep model output away from direct state mutation.

Status:

- base exists;
- S3 extends it for memory worker candidate routing and lock behavior.

Later dependency:

- all later worker-like flows must use scheduler/governance boundaries instead
  of direct product-service side effects.

### Phase S3: Memory Worker To Governed Apply

Purpose:

```text
accepted source material
  -> post-write trigger
  -> scheduler-selected memory worker
  -> structured candidate / no-op / failure
  -> runtime workspace candidate material
  -> governance routing
  -> proposal review or direct deterministic apply
  -> lock/debug/next-packet visibility
```

Required outcome:

- worker output is candidate material, not state truth;
- state mutation occurs only through deterministic governed apply;
- review-required, direct-apply-allowed, and blocked/invalid paths exist;
- stale base rejection does not ask the model to self-repair;
- debug evidence is readable.

Current status:

| Slice | Current judgement | Gate implication |
| --- | --- | --- |
| S3a registry / candidate contracts | Completed and committed. | Must be checked in retrospective for exact requirement alignment. |
| S3b worker adapter / structured output | Completed and committed. | Must not be treated as full production harness unification. |
| S3c governance routing / proposal handoff | Completed and committed. | Must preserve named S3 boundary and not hide new semantics as legacy only. |
| S3d lock / stale-base behavior | Completed and committed. | Must verify lock semantics against Node-1/module docs. |
| S3e lock entrypoint wiring | Completed and committed. | Must verify old path compatibility and no route overclaim. |
| S3f end-to-end closing gate | Completed and committed. | Treat as S3 reference gate, not final full-runtime completion. |
| S3g-a service-size cleanup | Completed and committed. | Code-health slice, not a new product behavior claim. |
| S3g-b production executor compatibility | Committed as bounded compatibility slice in `51bc53c`. | Residual production structured-output runner gap remains; do not treat this as full executor migration. |

S3 is not allowed to claim full story-agent runtime completion. It is the first
reference implementation for memory worker governance.

### Phase S3.5: Harness Productionization Decision

Purpose:

- decide whether S3 needs an additional production structured-output runner /
  harness promotion slice before S4;
- promote only cross-role execution mechanisms from S3 into the harness.

Decision as of 2026-06-23:

- S3.5 is required before S4 implementation;
- use a narrow productionization slice, not a universal executor rewrite;
- target the production memory-maintenance structured-output runner plus a
  generic harness runner port;
- tool calls are disabled for the first S3.5 production runner, with
  fail-closed reason codes; the generic port must leave room for later tool-loop
  support without implementing the full loop in this slice;
- keep legacy specialist execution as an explicit fallback only, not the target
  path.

Decision record:

- `execution/main-brain/S3.5-harness-productionization-decision.md`

Candidate promotions:

- structured-output runner port;
- normalized tool loop, deferred unless explicitly added by a later slice;
- tool result/error envelope, deferred unless explicitly added by a later slice;
- bounded retry/repair;
- trace/event envelope;
- fake runner/tool fixtures.

Do not promote:

- memory domain or block rules;
- S3 candidate shape;
- proposal review policy;
- Core/projection apply semantics;
- packet content choices.

Exit:

- either S3g-c or equivalent productionization slice is completed, or the gap is
  explicitly recorded as deferred with reason, owner, and next phase impact.

### Phase S4: Retrieval As Explicit Service/Tool Capability

Purpose:

- retrieval becomes a traceable service/tool capability, not hidden agent prose.

Likely scope:

- retrieval cards and usage records;
- source-family filters and policy/budget trace;
- promotion gates for source refs used by post-write maintenance;
- packet integration that records what was read and why.

Dependencies:

- S1 identity/profile;
- S2 scheduler/governance;
- S3 source-ref, workspace-material, and candidate/governance discipline.

### Phase S5: Chapter Close / Summary Maintenance

Purpose:

- close-chapter summary and long-term memory updates go through deterministic
  material/proposal/apply paths.

Likely scope:

- chapter summary;
- character long-history;
- retired foreshadow retention;
- continuity notes;
- tail flush or close-scene materialization where required by requirements docs.

Dependencies:

- S3 governed apply;
- S4 retrieval/source material discipline.

### Phase S6: Draft Review / Rewrite / Adoption

Purpose:

- preserve explicit selection and adoption semantics for review/rewrite flows.

Likely scope:

- review candidate surfaces;
- rewrite request and packet sidecar;
- rewrite proposal/selection;
- accept-and-continue adoption;
- continuation-base integrity;
- guarantee that an unadopted rewrite does not become state truth.

Dependencies:

- revision/rewrite source documents;
- S1 identity;
- workspace material lifecycle;
- proposal/adoption boundary from S3.

### Phase S7: Brainstorm Runtime Integration

Purpose:

- replace pseudo-brainstorm behavior only where real story-agent behavior is
  required by the requirement documents.

Likely scope:

- brainstorm submit handoff;
- pending-processing batch intent;
- worker/agent routing if required;
- memory update governance after brainstorm material enters runtime.

Dependencies:

- brainstorm product-loop source spec;
- S3/S4/S5/S6 shared tool, packet, workspace, and governance patterns.

## Old MVP Path Policy

Old MVP/runtime code is not automatically wrong. It is also not authoritative
for the new runtime.

Use this classification:

| Classification | Meaning | Allowed action |
| --- | --- | --- |
| Preserve | Existing behavior matches new requirements and has tests. | Keep, add regression coverage if needed. |
| Adapt | Existing path is useful but names, boundaries, or records conflict with new requirements. | Wrap or migrate through a named adapter boundary. |
| Replace | Existing path encodes old semantics that conflict with new requirements. | Build new path and retire the old one deliberately. |
| Quarantine | Existing path is still needed for compatibility but must not be presented as target architecture. | Keep behind explicit compatibility flag/metadata and plan removal or promotion. |

Every slice must state which category applies to each old path it touches.

## Tool Design Gate

Tools are the only way an agent interacts with external/project capabilities.
Tool output is still not authoritative state unless deterministic governance
and apply services accept it.

Every new or changed tool-like capability must state:

- tool name and owner;
- structured input schema;
- structured output schema;
- explicit error schema with stable reason code and retryability;
- allowed caller role/worker;
- trace fields;
- whether output becomes candidate material, review proposal, direct apply
  input, or read-only packet evidence;
- what happens on invalid input, stale base, unknown handle, denied target,
  timeout, and provider/tool failure.

Do not create one-off private protocols per module. If a capability is reused
by more than one role or worker, adapt it through the shared runtime tool
contract.

## Test And Review Gates

Required gate layers:

| Layer | Purpose |
| --- | --- |
| Unit tests | Deterministic registries, validators, DTOs, mappers, policy decisions. |
| Service tests | Persistence and state transitions with real services/fixtures. |
| Integration tests | End-to-end turn/job/worker/proposal/apply or retrieval/rewrite flows. |
| Regression tests | Existing S0/S1/S2 and old compatible routes. |
| Fresh review | Requirement drift, framework/product leakage, missing tests, old-MVP leakage. |
| Optional live smoke | Bounded real-provider confidence only after deterministic tests pass. |

Subagents should not run pytest by default. If a subagent must run focused
pytest, it must use `-n auto` and report the exact command and result.

The main-brain owns final gate decisions. Reviewer reports are evidence, not
automatic approvals.

## Commit And Rollback Discipline

- commit only after a coherent planning, implementation, or verification slice
  reaches its gate;
- stage explicit slice-owned files only;
- do not stage unrelated user or parallel-agent changes;
- use explicit force-add for required ignored Trellis task documents;
- record meaningful milestone commits in worklog/gate docs;
- if a committed slice is wrong, revert that slice commit instead of resetting
  the whole worktree.

Pending work is not ready to commit only because tests passed. It must also
pass the roadmap and retrospective gate when the process order was wrong.

## Immediate Hold And Recovery Plan

Current hold:

- do not continue new feature implementation;
- S3g-b bounded compatibility slice has been committed as `51bc53c`;
- do not start S4.

Recovery steps:

1. Finish this roadmap update.
2. Create the S3 retrospective against this roadmap.
3. Read the S3g-b diff and classify it: commit as bounded compatibility slice,
   revise before commit, or split.
4. Run focused verification for S3g-b and commit only explicit S3g-b-owned
   code/test/docs.
5. Record S3g-b commit hash.
6. Decide whether S3g-c / S3.5 harness productionization is required before S4.
7. Only then resume normal implementation flow.

This is the new execution order. Any later deviation must be recorded with a
reason.
