# SetupAgent Architecture Implementation Slices

> Task: `.trellis/tasks/05-11-setup-agent-architecture-improve`
>
> Status: A0 rollout plan

## 1. Rollout Principle

Implement contract spine first, then reorganize files only where ownership remains scattered.

Do not start with broad file moves. A slice is complete only when it changes one coherent architecture contract and has tests/checks that prove the contract.

## 2. Slice Order

```text
A0 Architecture/spec freeze
A1 Loop stop / repair / output boundary
A2 CapabilityPlan tool-surface spine
A3 ContextPipeline contract consolidation
A4 ModelGateway + EventSink hardening
A5 RuntimeStateStore / trace / transcript separation
B  Draft CRUD migration
C  Setup lightweight retrieval roadmap
D  SkillPack governance
```

## 3. A0: Architecture / Spec Freeze

Goal:

- finish planning docs before backend/frontend implementation

Deliverables:

- PRD
- current architecture audit
- pi-mono / Claude Code reference lessons
- grill decisions record
- grounding matrix
- target HLD
- contract spine spec
- implementation slices
- test/eval plan
- question queue

Checks:

- `python .\.trellis\scripts\task.py validate 05-11-setup-agent-architecture-improve`
- `git diff --check -- .trellis/tasks/05-11-setup-agent-architecture-improve`

Backend tests:

- not required for A0 because no backend implementation changes are allowed

## 4. A1: Loop Stop / Repair / Output Boundary

Goal:

- make `SetupTurnLoop` state-machine boundaries real enough to stop old bug classes from recurring
- use the current tool-scope/profile path as the provisional capability source; do not require the A2 `SetupCapabilityPlan` object before A1 can land

Primary contracts:

- `SetupTurnLoop`
- `OutputInspector`
- `SetupToolRuntime` error observation
- `SetupEventSink` visibility

Likely files:

- `backend/rp/agent_runtime/executor.py`
- `backend/rp/agent_runtime/state.py`
- `backend/rp/agent_runtime/graph.py`
- `backend/rp/agent_runtime/policies.py`
- `backend/rp/agent_runtime/contracts.py`
- `backend/rp/agent_runtime/events.py`
- existing runtime executor/policy tests

Allowed changes:

- introduce typed inspect result
- isolate pseudo tool text classification behind OutputInspector contract
- route recoverable tool errors as observations before public terminal failure
- enforce retry budgets with explicit finish/continue reasons
- preserve typed tool SSE events

Forbidden scope:

- introduce the full A2 `SetupCapabilityPlan` extraction as a prerequisite
- expose `setup.world_background.*`
- full draft CRUD migration
- setup retrieval
- prompt-only fix as final solution
- broad directory reorganization
- subagent feature work

Acceptance:

- pseudo tool text never appears as assistant content
- repeated pseudo tool text stops by explicit business finish reason before graph recursion
- recoverable tool failure retries once or within configured budget before terminal/user-required path
- real successful tool call can stop cleanly when obligations are satisfied
- typed SSE tool events still appear
- A1 does not change accepted tool exposure except where required to keep current active-spec tool scope intact

Suggested tests:

- `test_setup_agent_runtime_executor.py`
- `test_setup_agent_runtime_policies.py`
- focused OutputInspector tests if extracted
- typed SSE stream-path regression if existing tests allow

## 5. A2: CapabilityPlan Tool-Surface Spine

Goal:

- make tool exposure one coherent contract instead of scattered prompt/profile/provider/test edits

Primary contracts:

- `SetupCapabilityPlan`
- `SetupToolRuntime`
- prompt guidance consistency

Likely files:

- `backend/rp/agent_runtime/profiles.py`
- `backend/rp/agent_runtime/adapters.py`
- `backend/rp/agent_runtime/tools.py`
- `backend/rp/tools/setup_tool_provider.py`
- `backend/rp/services/setup_agent_prompt_service.py`
- `backend/rp/tests/test_setup_agent_tool_scope.py`
- prompt service tests

Allowed changes:

- introduce explicit capability package object or equivalent contract boundary
- derive prompt guidance from active capability package
- generate model-visible schemas and runtime allowlist from the same plan
- assert candidate tools remain hidden
- snapshot stage/step capability packages
- assert accepted shared/read tools remain present, including `setup.read.draft_refs`

Forbidden scope:

- duplicate pydantic business schemas in CapabilityPlan
- move workspace mutation into CapabilityPlan
- expose all provider-registered tools by default
- use prompt guidance as permission
- remove or narrow active-spec shared/read tools without updating the authoritative spec first

Acceptance:

- adding/changing a setup tool starts from one capability contract
- prompt/schema/allowlist drift fails tests
- `setup.world_background.*` remains candidate-only unless a later slice accepts it
- stage defaults, step overrides, and turn filters are visible in test snapshots
- shared setup tools and stage-local read/recovery tools required by active specs remain visible in capability snapshots

## 6. A3: ContextPipeline Contract Consolidation

Goal:

- name and stabilize the pre-model context pipeline without collapsing useful existing layers

Primary contracts:

- `SetupContextPipeline`
- `SetupRuntimeStateStore`
- SkillPack prompt-only boundary

Likely files:

- `backend/rp/services/setup_context_builder.py`
- `backend/rp/services/setup_context_governor.py`
- `backend/rp/services/setup_context_compaction_service.py`
- `backend/rp/services/setup_agent_prompt_service.py`
- `backend/rp/agent_runtime/adapters.py`
- context/prompt tests

Allowed changes:

- document/encode context packet order
- centralize context report expectations
- assert SkillPack does not change tool scope
- make final prompt assembly consume CapabilityPlan guidance instead of independent tool prose
- improve retained outcome / working digest handoff naming

Forbidden scope:

- generic memory subsystem
- active-story retrieval integration
- changing business draft truth semantics

Acceptance:

- final request messages have deterministic order
- compact summary and working digest are runtime aids only
- prompt/SkillPack cannot contradict capability plan
- prompt guidance cannot mention tools outside the active CapabilityPlan

## 7. A4: ModelGateway + EventSink Hardening

Goal:

- isolate provider compatibility and user-visible transcript rules

Primary contracts:

- `ModelGateway`
- `SetupEventSink`
- `OutputInspector` integration

Likely files:

- `backend/rp/agent_runtime/executor.py`
- `backend/rp/agent_runtime/events.py`
- provider/model request helpers
- stream tests

Allowed changes:

- normalize provider error attribution
- isolate stream tool-call reconstruction
- keep raw provider deltas private
- add event visibility tests

Forbidden scope:

- provider feature expansion not required by setup runtime
- frontend transcript redesign unless backend event contract requires it

Acceptance:

- provider/schema/stream errors are distinct from setup business failures
- public SSE contains only public-safe assistant/tool/final events
- private diagnostics remain available for trace/eval/logs

## 8. A5: RuntimeStateStore / Trace / Transcript Separation

Goal:

- harden truth levels after loop/capability/event boundaries exist

Primary contracts:

- `SetupRuntimeStateStore`
- `SetupEventSink`
- `SetupWorkspace` truth separation

Likely files:

- `backend/rp/services/setup_agent_runtime_state_service.py`
- runtime contracts/state
- runtime persistence tests

Allowed changes:

- improve trace/digest/cognition persistence boundaries
- clarify invalidation after user draft edits
- align diagnostics/eval reason-code surfaces
- keep `loop_trace` / `continue_reason` result-debug-eval scoped unless a future spec explicitly promotes persistence

Forbidden scope:

- promote runtime trace to product truth by default
- rewrite memory/story runtime state

Acceptance:

- runtime cognition can be rebuilt/invalidation-safe
- loop trace is diagnostic/eval material
- workspace truth is only mutated by business tools/services
- runtime-governance snapshots do not persist `loop_trace` or `continue_reason` under current active specs

## 9. Later Slices

### B: Draft CRUD Migration

Only after CapabilityPlan is stable.

Purpose:

- decide whether model-visible setup draft writes move from slim `setup.truth.write` to stage-local CRUD families

Guard:

- do not expose candidate CRUD tools before capability snapshots and tests accept them

### C: Setup Lightweight Retrieval Roadmap

Only after context/capability boundaries are stable.

Purpose:

- decide setup-owned retrieval/readback aids during prestory editing

Guard:

- do not mix setup retrieval with active-story retrieval-core truth ingestion

### D: SkillPack Governance

Only after CapabilityPlan and ContextPipeline agree.

Purpose:

- formalize prompt-pack governance and observability

Guard:

- SkillPack remains prompt/context packaging, not business or tool-scope authority

## 10. Check Cadence

After each coherent slice:

1. Run focused tests for changed contracts.
2. Run `python .\.trellis\scripts\task.py validate 05-11-setup-agent-architecture-improve` if task context changes.
3. Run `git diff --check -- <changed paths>`.
4. Use `trellis-check` before starting the next slice.

Do not run full checks after every tiny edit. Do run checks after each complete spec slice.

## 11. Legacy 05-09 Interpretation Guard

The old `05-09` handoff is investigation evidence only. It must not override this task's PRD, HLD, contract spine, or active backend specs.

Treat these old-hand-off details as superseded unless a current `05-11` document explicitly re-accepts them:

- the standalone `DecisionPolicy` target module; current direction is loop-owned transition rules inside `SetupTurnLoop`
- any A1 path that pulls `world_background` CRUD, draft CRUD migration, setup retrieval, or SkillPack governance into the loop/output slice
- uncommitted working-tree retry reason names from the old attempt unless they are reconciled with the active loop semantics taxonomy before implementation
- any prompt/tool/provider/test fix that bypasses the A2 `SetupCapabilityPlan` consistency contract
