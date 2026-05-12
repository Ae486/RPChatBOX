# SetupAgent Architecture Execution Plan

> Task: `.trellis/tasks/05-11-setup-agent-architecture-improve`
>
> Purpose: implementation-stage execution plan for SetupAgent architecture optimization.
>
> Status: active

## 1. Plan Role

This document is not the PRD and not the architecture HLD.

It owns execution discipline for the implementation stage:

1. freeze how main-brain, implement agents, check agents, and docs interact
2. freeze slice order and completion criteria
3. track current progress so later sessions do not drift
4. provide engineering rules specific to SetupAgent architecture optimization

Authoritative design details still live in:

- `setup-agent-module-prd.md`
- `research/setup-agent-target-architecture-hld.md`
- `research/setup-agent-contract-spine-spec.md`
- `research/setup-agent-a1-loop-output-boundary-development-spec.md`
- active backend specs under `.trellis/spec/backend/rp-setup-agent-*.md`

## 2. Main-Brain Rules

1. Main-brain owns scheduling, scope control, integration, plan maintenance, and final summary.
2. Main-brain must check this plan before dispatching implementation, check, or spec-update work.
3. Main-brain should keep backend implementation edits inside coherent Trellis slices; for code slices, dispatch `trellis-implement` per the active workflow unless the user explicitly changes the process.
4. Main-brain must not let implementation agents override current task docs with old `05-09` handoff details.
5. `trellis-check` is required after one coherent slice; do not replace it with informal self-review.
6. Same module/function family should stay with the same implement agent until that slice is complete when subagents are used.
7. At most `2` subagents may run concurrently.
8. Default execution is one implement agent at a time. Use a second agent only for independent review/research/check work or clearly disjoint implementation ownership.
9. Questions are not escalated to the user until the agent has checked, in order:
   - current task PRD / HLD / contract spine / A1 spec / question queue
   - active backend specs
   - current SetupAgent code as requirement and migration evidence
   - local pi-mono and Claude Code references
   - primary/current provider or framework docs when concrete external behavior matters
10. If the issue changes setup product semantics, stop and `$grill-me`.
11. If the issue is only implementation mechanics and the sources above give a reliable answer, decide and document it rather than asking the user.
12. New implementation knowledge should be written back to task docs or `.trellis/spec/` only after the relevant slice is coherent and checked.

## 3. Execution Flow

Each implementation slice uses this flow:

1. Main-brain confirms the slice boundary, owned contracts, expected files, forbidden scope, and tests.
2. Main-brain dispatches or performs only the work allowed by the active Trellis workflow for that phase.
3. The implement owner completes the whole coherent slice, not only a small helper rename.
4. Main-brain reviews the output against this plan and the active slice spec.
5. Focused local tests are run for the changed contract.
6. `trellis-check` runs after the coherent slice is complete.
7. Findings are fixed or explicitly routed back to spec/question queue.
8. This plan is updated before moving to the next slice.

For A1 specifically, implementation starts from:

- `research/setup-agent-a1-loop-output-boundary-development-spec.md`

## 4. Concurrency Rules

### 4.1 Hard Limit

- Maximum concurrent subagents: `2`.

### 4.2 Default Mode

- Default: `1` implement agent.
- Optional second agent:
  - check agent after a coherent slice
  - explorer/research agent for a narrow, non-blocking question
  - second implement agent only if the write set and contract ownership are disjoint

### 4.3 Parallel Dispatch Requirements

Before using two implement agents at once, main-brain must write down:

- agent A owned files / owned contract
- agent B owned files / owned contract
- why file writes do not overlap
- why contract decisions do not overlap
- why neither task depends on the other agent's unfinished output
- how the outputs will be checked and merged

If that cannot be proven, run serially.

## 5. Status Markers

Use these markers in this plan:

- `[ ]` not started
- `[>]` in progress
- `[x]` completed
- `[!]` blocked; needs `$grill-me`, spec update, or external primary-doc confirmation

Current status:

```text
[x] A0 Architecture/spec freeze
[x] A1 Loop stop / repair / output boundary
[x] A2 CapabilityPlan tool-surface spine
[x] A3 ContextPipeline contract consolidation
[x] A4 ModelGateway + EventSink hardening
[x] A5 RuntimeStateStore / trace / transcript separation
[x] B  Tool module integration protocol / canonical draft-write path
[x] C  Setup lightweight retrieval roadmap
[x] D  SkillPack governance
```

## 6. Engineering Development Norms

These rules are specific to SetupAgent architecture optimization. They are stricter than generic refactor advice because the task is about architecture ownership.

### 6.1 Source And Reference Discipline

1. Existing SetupAgent code is product-semantics evidence, not architecture authority.
2. pi-mono is the minimal framework reference:
   - learn session/state/context/loop/tool/event/continue-stop layering
   - do not copy generic coding-agent assumptions
3. Claude Code is the mature module/function reference:
   - learn tool lifecycle, active tool filtering, fail-closed defaults, output separation, context engineering, recovery transitions, and observability
   - do not copy terminal UI, file-editing permission semantics, full tool breadth, or subagent feature richness into A1/A2
4. Secondary engineering articles are background only. Concrete provider/tool-calling/streaming/structured-output/graph/framework behavior requires primary/current docs or local source evidence.
5. New Python frameworks or dependencies are not allowed unless they solve a concrete local boundary problem and the task docs explicitly accept them. Current default is to keep LangGraph as substrate and improve ownership above it.

### 6.2 Contract-First Implementation

1. Before editing code, name the contract owner:
   - `SetupTurnLoop`
   - `OutputInspector`
   - `SetupToolRuntime`
   - `SetupEventSink`
   - `SetupCapabilityPlan`
   - `SetupContextPipeline`
   - `ModelGateway`
   - `SetupRuntimeStateStore`
2. Each changed behavior must have:
   - one owning contract
   - explicit invariants
   - focused tests
   - forbidden adjacent layers
3. Do not begin with broad file moves. Extract files only after contracts prove the ownership remains scattered.
4. Do not add a larger `DecisionPolicy` object. Transition rules live inside `SetupTurnLoop` and may use small helpers.

### 6.3 Tool-Surface Rules

1. Tool calling remains standard provider/model tool calling.
2. Prompt guidance cannot open a tool.
3. Provider registration cannot expose a tool to the model.
4. A2 `SetupCapabilityPlan` owns schema/prompt/allowlist consistency.
5. `SetupToolProvider` owns schema validation, deterministic business validation, workspace mutation, and structured result/error payloads.
6. A1 may use current profile/tool-scope as provisional capability source, but it must not change accepted tool exposure except to preserve active specs.
7. `setup.world_background.*` remains candidate-only until a later product/tool slice explicitly accepts it.
8. Active-spec shared/read tools, including `setup.read.draft_refs`, must not be accidentally removed by capability narrowing.
9. B-stage tool work must stabilize the integration protocol, not hardwire one concrete CRUD family into the agent loop.

### 6.4 Output / Event / Transcript Rules

1. Model output must pass through `OutputInspector` before tool runtime or transcript visibility.
2. Pseudo tool text must never become assistant content.
3. Raw provider deltas, raw validation stacks, debug JSON, and repair traces are private unless mapped to a public-safe typed event.
4. Typed SSE event names must remain stable unless a separate UI/backend contract accepts a change.
5. Public assistant text is only finalized after loop obligations and completion guards pass.

### 6.5 Repair / Retry Rules

1. Retry is a fuse, not the normal success path.
2. Schema validation repair budget remains exactly one correction attempt unless the active backend spec is updated.
3. Recoverable tool failures become structured observations before public terminal failure.
4. `finish_reason` strings must come from active specs or be added to active specs in the same slice.
5. `GRAPH_RECURSION_LIMIT` is never an intended stop condition.

### 6.6 State And Truth Rules

1. `SetupWorkspace` remains business truth.
2. Runtime cognition, working digest, compact summary, retained outcomes, and loop trace are runtime aids.
3. `loop_trace` and `continue_reason` may appear in result/debug/eval surfaces but must not be persisted into governance snapshots under current specs.
4. User-editable drafts and edit deltas remain product semantics; runtime cognition must reconcile around them, not overwrite them.

### 6.7 Test And Eval Rules

1. Every architecture boundary change needs focused tests.
2. Tests should assert contracts and visible behavior, not implementation file names.
3. Eval/diagnostics must distinguish:
   - provider/gateway failure
   - model emitted pseudo tool text
   - model failed to emit a real tool call
   - tool schema validation failure
   - setup business terminal failure
   - successful tool/repair path
4. Live model smoke is optional and never replaces deterministic contract tests.

## 7. Rollout Principle

Implement contract spine first, then reorganize files only where ownership remains scattered.

Do not start with broad file moves. A slice is complete only when it changes one coherent architecture contract and has tests/checks that prove the contract.

## 8. Slice Order

```text
A0 Architecture/spec freeze
A1 Loop stop / repair / output boundary
A2 CapabilityPlan tool-surface spine
A3 ContextPipeline contract consolidation
A4 ModelGateway + EventSink hardening
A5 RuntimeStateStore / trace / transcript separation
B  Tool module integration protocol / canonical draft-write path
C  Setup lightweight retrieval roadmap
D  SkillPack governance
```

## 9. A0: Architecture / Spec Freeze

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

## 10. A1: Loop Stop / Repair / Output Boundary

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

Implementation result:

- A1 completed on 2026-05-12.
- Added typed `SetupOutputInspection` / `SetupOutputClassification` as the explicit boundary before tool runtime and transcript visibility.
- `_inspect_model_output(...)` now consumes the typed inspection result for pseudo tool text, malformed tool calls, empty output, mixed text/tool output, and normal text.
- Pseudo tool text and mixed text + real tool calls keep unsafe text out of `assistant_text`; stream mode suppresses pending text once a real tool call appears.
- Candidate finish reasons from the old attempt were reconciled with active specs:
  - pseudo / invalid tool-output retry exhaustion maps to `repair_obligation_unfulfilled`
  - repeated recoverable tool failure maps to `tool_error_unrecoverable` with private details
- `output_inspection` is result/debug scoped; `loop_trace` and `continue_reason` remain outside persisted runtime-governance snapshots.

Checks:

- `python -m pytest -q backend/rp/tests/test_setup_agent_runtime_executor.py backend/rp/tests/test_setup_agent_runtime_policies.py` -> `65 passed`
- `python -m pytest -q backend/rp/tests/test_setup_agent_runtime_state_service.py` -> `10 passed`
- `python -m pytest -q backend/rp/tests/test_eval_setup_cognitive_cases.py` -> `6 passed, 5 xfailed, 3 xpassed`
- `python -m py_compile backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/state.py backend/rp/agent_runtime/executor.py backend/rp/agent_runtime/policies.py` -> passed
- `python -m ruff check backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/state.py backend/rp/agent_runtime/executor.py backend/rp/agent_runtime/policies.py backend/rp/tests/test_setup_agent_runtime_executor.py backend/rp/tests/test_setup_agent_runtime_policies.py` -> passed
- `python -m mypy --follow-imports=skip --ignore-missing-imports backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/state.py backend/rp/agent_runtime/executor.py backend/rp/agent_runtime/policies.py` -> passed
- full mypy without import skipping timed out at 240 seconds; do not treat it as passed
- `python .\.trellis\scripts\task.py validate 05-11-setup-agent-architecture-improve` -> passed
- `git diff --check -- <A1 changed paths>` -> no whitespace errors; Git reported CRLF conversion warnings only
- `trellis-check` found and fixed one stream mixed-output leak before A1 was marked complete

## 11. A2: CapabilityPlan Tool-Surface Spine

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

Implementation result:

- A2 completed on 2026-05-12.
- Added `SetupCapabilityPlan` / `SetupCapabilityGuidanceFragment` as the turn-level contract for active tool names, runtime allowlist, schema modes, prompt guidance fragments, candidate exclusions, and snapshot expectations.
- `build_setup_agent_tool_scope(...)` remains as the compatibility API, but delegates to `build_setup_agent_capability_plan(...)`.
- `SetupRuntimeAdapter.build_turn_input(...)` now builds one capability plan and uses it for both:
  - `RpAgentTurnInput.tool_scope`
  - `SetupAgentPromptService.build_system_prompt(..., capability_plan=...)`
- The adapter stores a debug/eval snapshot in `turn_input.metadata["capability_plan"]`; this is not business truth and does not mutate `SetupWorkspace`.
- `SetupAgentPromptService` renders tool guidance from capability fragments and rechecks that every guidance fragment references only active tools before rendering.
- `RpAgentRuntimeExecutor` reads `metadata["capability_plan"]["model_schema_modes"]` to decide whether `setup.truth.write` uses the runtime-adapted slim model-facing schema; missing capability metadata keeps legacy fallback behavior, while an explicit provider-default mode disables the adapter.
- `setup.world_background.*` remains candidate-only, canonical stages continue to hide legacy patch tools, and active shared/read tools such as `setup.read.draft_refs`, `setup.truth.write`, and `setup.proposal.commit` remain visible.
- `trellis-check` found and fixed two A2 drift gaps before completion:
  - schema adaptation still depended only on hard-coded executor tool-name checks
  - prompt guidance trusted supplied fragments without a final active-tool subset guard

Checks:

- `python -m pytest -q backend/rp/tests/test_setup_agent_tool_scope.py backend/rp/tests/test_setup_agent_prompt_service.py backend/rp/tests/test_setup_agent_execution_service_v2.py` -> `59 passed`
- `python -m pytest -q backend/rp/tests/test_setup_agent_runtime_executor.py backend/rp/tests/test_setup_agent_runtime_policies.py` -> `66 passed`
- `python -m ruff check backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/profiles.py backend/rp/agent_runtime/adapters.py backend/rp/agent_runtime/executor.py backend/rp/services/setup_agent_prompt_service.py backend/rp/tests/test_setup_agent_tool_scope.py backend/rp/tests/test_setup_agent_prompt_service.py backend/rp/tests/test_setup_agent_execution_service_v2.py backend/rp/tests/test_setup_agent_runtime_executor.py` -> passed
- `python -m py_compile backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/profiles.py backend/rp/agent_runtime/adapters.py backend/rp/agent_runtime/executor.py backend/rp/services/setup_agent_prompt_service.py` -> passed
- `python -m mypy --follow-imports=skip --ignore-missing-imports backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/profiles.py backend/rp/agent_runtime/adapters.py backend/rp/agent_runtime/executor.py backend/rp/services/setup_agent_prompt_service.py` -> passed
- `python .\.trellis\scripts\task.py validate 05-11-setup-agent-architecture-improve` -> passed
- `git diff --check -- <A2 changed paths>` -> no whitespace errors; Git reported LF/CRLF conversion warnings only
- Full import-following mypy remains blocked by existing repository type debt and missing stubs outside A2, including `markitdown`, SQLAlchemy model typing, and provider/LiteLLM surfaces. Do not count full mypy as passed for this slice.

## 12. A3: ContextPipeline Contract Consolidation

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

Implementation result:

- A3 completed on 2026-05-12.
- Added `SetupContextPipelineSnapshot` / `SetupPromptAssemblySnapshot` as debug/eval metadata contracts for the pre-model context pipeline and stable prompt assembly.
- Kept the useful existing layers instead of flattening them:
  - `SetupContextPacket` remains workspace-truth context.
  - `SetupContextGovernorService.govern_history(...)` remains the stage-local history governor.
  - `SetupRuntimeAdapter.build_turn_input(...)` remains the turn-input adapter.
  - `RpAgentRuntimeExecutor` remains the final request-message assembler.
- Moved `context_report` out of `RpAgentTurnInput.context_bundle` and into `turn_input.metadata`.
- Preserved `context_report` in runtime structured payload / observation metadata for debug, eval, and result attribution.
- Ensured `context_report` and `context_pipeline` do not enter the stable prompt, runtime overlay, or runtime-state snapshot.
- Stable system prompt inputs are now explicitly documented as `context_packet`, `capability_plan`, and SkillPack prompt layer.
- SkillPack remains prompt-only and does not modify `SetupCapabilityPlan`, `tool_scope`, or runtime allowlist.
- Final model-visible request order is covered as:
  1. stable setup system prompt
  2. runtime overlay system message
  3. governed history
  4. current user request
- `trellis-check` found and fixed one A3 type-contract drift:
  - `_build_context_report(...)` had cast `context_profile`, `summary_strategy`, and `summary_action` through plain `str`, weakening the `SetupContextGovernanceReport` literal contract.
  - The fix keeps those fields on the controlled literal surfaces with `typing.Literal` / `cast(...)`.

Checks:

- `python -m pytest -q backend/rp/tests/test_setup_agent_prompt_service.py backend/rp/tests/test_setup_agent_tool_scope.py` -> `44 passed`
- `python -m pytest -q backend/rp/tests/test_setup_agent_runtime_executor.py` -> `41 passed`
- `python -m pytest -q backend/rp/tests/test_setup_agent_execution_service_v2.py` -> `17 passed`
- `python -m pytest -q backend/rp/tests/test_setup_agent_runtime_state_service.py` -> `10 passed`
- `python -m ruff check backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/adapters.py backend/rp/agent_runtime/executor.py backend/rp/services/setup_agent_prompt_service.py backend/rp/services/setup_agent_execution_service.py backend/rp/tests/test_setup_agent_prompt_service.py backend/rp/tests/test_setup_agent_tool_scope.py backend/rp/tests/test_setup_agent_runtime_executor.py backend/rp/tests/test_setup_agent_execution_service_v2.py` -> passed
- `python -m py_compile backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/adapters.py backend/rp/agent_runtime/executor.py backend/rp/services/setup_agent_prompt_service.py backend/rp/services/setup_agent_execution_service.py` -> passed
- `python -m mypy --follow-imports=skip --ignore-missing-imports backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/adapters.py backend/rp/agent_runtime/executor.py backend/rp/services/setup_agent_prompt_service.py backend/rp/services/setup_agent_execution_service.py` -> passed
- `python .\.trellis\scripts\task.py validate 05-11-setup-agent-architecture-improve` -> passed
- `git diff --check -- <A3 changed paths>` -> no whitespace errors; Git reported LF/CRLF conversion warnings only
- Full import-following mypy remains out of scope for this task. Use scoped mypy with `--follow-imports=skip --ignore-missing-imports` for SetupAgent architecture slices unless a later task explicitly accepts repository-wide type-debt cleanup.

## 13. A4: ModelGateway + EventSink Hardening

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

Implementation result:

- A4 completed on 2026-05-12.
- Added `SetupEventSink` as the public typed-SSE boundary. It allowlists event types and payload keys instead of passing provider/runtime payloads through unchanged.
- Preserved the active typed-SSE event names:
  - `thinking_delta`
  - `text_delta`
  - `tool_call`
  - `tool_started`
  - `tool_result`
  - `tool_error`
  - `usage`
  - `error`
  - `done`
- `thinking_delta` remains public, but only the public `delta` field survives; raw/debug/provider/private fields are stripped recursively.
- Added `SetupModelGatewayDiagnostics` and `SetupEventSinkSnapshot` as debug/eval contracts.
- Provider request exceptions, stream provider errors, stream exceptions, and malformed stream JSON now normalize to:
  - `failure_layer = "model_gateway"`
  - public error type `model_gateway_failed`
  - `finish_reason = "upstream_error"`
  - `output_inspection.classification = "provider_schema_error"`
- Private provider details stay in `structured_payload["model_gateway_diagnostics"]`; public SSE only receives a public-safe error summary.
- Stream tool-call reconstruction remains inside the model-gateway side of executor behavior, while `OutputInspector` still owns final normalized-output classification before tool runtime or public transcript.
- `trellis-check` found and fixed one A4 drift gap:
  - malformed provider stream `data:` JSON was previously ignored and could fall into empty-output/setup repair behavior.
  - `_ProviderStreamPayloadError` now maps malformed stream payloads to `provider_stream_parse_error` under `model_gateway`.

Checks:

- `python -m pytest -q backend/rp/tests/test_setup_agent_runtime_executor.py` -> `47 passed`
- `python -m pytest -q backend/tests/test_rp_setup_agent_api.py` -> `16 passed`
- `python -m ruff check backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/events.py backend/rp/agent_runtime/executor.py backend/rp/agent_runtime/state.py backend/rp/tests/test_setup_agent_runtime_executor.py` -> passed
- `python -m py_compile backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/events.py backend/rp/agent_runtime/executor.py backend/rp/agent_runtime/state.py backend/rp/tests/test_setup_agent_runtime_executor.py` -> passed
- `python -m mypy --follow-imports=skip --ignore-missing-imports backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/events.py backend/rp/agent_runtime/executor.py backend/rp/agent_runtime/state.py` -> passed
- `git diff --check -- <A4 changed paths>` -> no whitespace errors; Git reported LF/CRLF conversion warnings only
- Full import-following mypy remains out of scope for this task. Use scoped mypy with `--follow-imports=skip --ignore-missing-imports` for SetupAgent architecture slices unless a later task explicitly accepts repository-wide type-debt cleanup.

## 14. A5: RuntimeStateStore / Trace / Transcript Separation

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

Implementation result:

- A5 completed on 2026-05-12.
- Added explicit durable runtime-state root allowlist:
  - `SETUP_RUNTIME_STATE_DURABLE_FIELDS`
- Added explicit transient/debug/provider surface denylist:
  - `SETUP_RUNTIME_STATE_TRANSIENT_EXCLUDED_FIELDS`
- `SetupAgentRuntimeStateService.save_snapshot(...)` now writes through `durable_snapshot_payload(...)`, which validates before writing `SetupAgentRuntimeStateRecord.snapshot_json`.
- Durable snapshot validation is root-field fail-closed:
  - forbidden transient/debug fields raise `setup_runtime_state_snapshot_forbidden_fields`
  - unknown root fields also raise the same error
  - validation does not recursively scan nested business payloads, avoiding false positives in user draft content
- A1-A4 result/debug/eval/transcript fields remain transient and cannot be accidentally merged into durable runtime governance snapshots:
  - `loop_trace`
  - `continue_reason`
  - `context_report`
  - `output_inspection`
  - `event_sink`
  - `model_gateway_diagnostics`
  - raw provider/private/debug payload fields
- Existing governed runtime aids remain durable under the active specs:
  - cognitive state
  - `working_digest`
  - `tool_outcomes`
  - `compact_summary`
- User draft edit reconciliation invalidates runtime cognition and review readiness without mutating `SetupWorkspace` business truth or workspace version.
- `trellis-check` found no A5 issues after implementation.

Checks:

- `python -m pytest -q backend/rp/tests/test_setup_agent_runtime_state_service.py` -> `11 passed`
- `python -m pytest -q backend/rp/tests/test_setup_agent_execution_service_v2.py backend/rp/tests/test_setup_agent_runtime_executor.py` -> `64 passed`
- `python -m ruff check backend/rp/agent_runtime/contracts.py backend/rp/services/setup_agent_runtime_state_service.py backend/rp/tests/test_setup_agent_runtime_state_service.py` -> passed
- `python -m py_compile backend/rp/agent_runtime/contracts.py backend/rp/services/setup_agent_runtime_state_service.py backend/rp/tests/test_setup_agent_runtime_state_service.py` -> passed
- `python -m mypy --follow-imports=skip --ignore-missing-imports backend/rp/agent_runtime/contracts.py backend/rp/services/setup_agent_runtime_state_service.py` -> passed
- `git diff --check -- backend/rp/agent_runtime/contracts.py backend/rp/services/setup_agent_runtime_state_service.py backend/rp/tests/test_setup_agent_runtime_state_service.py` -> no whitespace errors; Git reported LF/CRLF conversion warnings only
- Full import-following mypy remains out of scope for this task. Use scoped mypy with `--follow-imports=skip --ignore-missing-imports` for SetupAgent architecture slices unless a later task explicitly accepts repository-wide type-debt cleanup.

## 15. Later Slices

### B: Tool Module Integration Protocol / Canonical Draft-Write Path

Only after CapabilityPlan is stable.

Purpose:

- solidify the protocol by which setup tools are registered, selected into one turn, described to the model, allowed at runtime, executed, and tested
- keep model-visible canonical draft writes on the hardened slim `setup.truth.write` stage-draft path by default
- prove that stage-local CRUD families such as `setup.world_background.*` can remain registered/candidate-only without leaking into prompt/schema/runtime allowlists
- make future tool-set changes local to tool implementation, registration/capability package, prompt guidance fragments, and snapshot tests

Guard:

- do not expose candidate CRUD tools merely because B exists
- do not make `RpAgentRuntimeExecutor` or the main loop depend on any concrete setup business tool name beyond generic tool protocol handling and accepted schema-adapter hooks
- do not duplicate provider-side pydantic business schemas inside `SetupCapabilityPlan`

Implementation result:

- B completed on 2026-05-12.
- Rechecked local pi-mono source and Claude Code local source/docs for the B-stage question:
  - pi-mono keeps tools as `AgentContext.tools` selected into the loop context.
  - Claude Code keeps concrete tools as external capability modules and assembles/filters an active tool pool before model calls.
  - Both point to protocol stability rather than hardwiring a concrete setup CRUD family into the agent loop.
- Reframed B from "choose/build Draft CRUD tools" to "stabilize the tool module integration protocol":
  - concrete setup tools live in `SetupToolProvider` / provider-side modules
  - `SetupCapabilityPlan` owns model-visible exposure, prompt guidance, schema mode, runtime allowlist, and candidate exclusion
  - provider registration alone does not expose a tool to the model
  - `RpAgentRuntimeExecutor` stays on generic tool protocol handling and the accepted `setup.truth.write` schema adapter hook
- Kept canonical stage model-visible writes on the hardened slim `setup.truth.write` stage-draft path.
- Kept `setup.world_background.*` as candidate tools: registered in `SetupToolProvider` for direct/provider tests and future product slices, but hidden from SetupAgent model scope by `SetupCapabilityPlan`.
- Fixed a provider-registration gap where the existing world_background candidate tool methods/tests existed but were not wired into `_schemas`, `list_tools()`, or `_dispatch(...)`, causing direct provider calls to return `unknown_tool`.
- Added a regression proving provider registration does not make `setup.world_background.write_entry` model-visible in the `world_background` SetupAgent scope.
- No `$grill-me` question remains for B. The final concrete tool set can change later as long as new tools enter through the same protocol.

Checks:

- `python -m pytest -q backend/rp/tests/test_setup_agent_tool_scope.py backend/rp/tests/test_setup_agent_prompt_service.py backend/rp/tests/test_setup_agent_execution_service_v2.py backend/rp/tests/test_setup_agent_runtime_executor.py backend/rp/tests/test_setup_tool_provider.py backend/rp/tests/test_setup_world_background_tools.py` -> `133 passed, 1 warning`
- `python -m ruff check backend/rp/tools/setup_tool_provider.py backend/rp/agent_runtime/profiles.py backend/rp/tests/test_setup_agent_tool_scope.py backend/rp/tests/test_setup_world_background_tools.py` -> passed
- `python -m py_compile backend/rp/tools/setup_tool_provider.py backend/rp/agent_runtime/profiles.py` -> passed
- `python -m mypy --follow-imports=skip --ignore-missing-imports backend/rp/tools/setup_tool_provider.py backend/rp/agent_runtime/profiles.py` -> passed

### C: Setup Lightweight Retrieval Roadmap

Only after context/capability boundaries are stable.

Purpose:

- freeze the boundary between setup-owned lightweight readback during prestory editing and retrieval-core materialization after accepted setup truth is committed
- keep current editable draft recovery, compact-summary recovery hints, prior-stage handoff refs, lexical/path/filter committed setup truth search, and exact committed setup truth reads inside setup-owned surfaces
- name the accepted current read surfaces:
  - `setup.read.draft_refs`
  - `setup.truth_index.search`
  - `setup.truth_index.read_refs`
  - `SetupTruthIndexService`
- leave semantic/vector retrieval, hybrid search, reranking, active-story retrieval policy, Recall/Memory OS retrieval, and runtime story retrieval outside SetupAgent

Guard:

- do not mix setup retrieval with active-story retrieval-core truth ingestion
- do not call Memory OS / retrieval-core to recover editable setup draft truth
- do not add embedding/RAG wiring to SetupAgent in this slice
- do not make retrieval materialization readiness a setup-stage commit gate
- do not introduce new model-visible retrieval tools unless a future product/tool slice accepts them through `SetupCapabilityPlan`

Implementation result:

- C completed on 2026-05-12 as a roadmap/spec boundary slice.
- No backend logic change was needed because the current accepted surfaces already match the desired split:
  - `setup.read.draft_refs` reads exact current editable setup draft refs for compact recovery and current-stage detail recovery.
  - `setup.truth_index.search` returns small lexical/path/filter candidate refs from accepted setup commits.
  - `setup.truth_index.read_refs` reads bounded exact committed setup truth by selected refs.
  - `SetupTruthIndexService` rebuilds deterministic committed truth rows from accepted snapshots only.
- The setup/retrieval boundary is now explicit:
  - setup owns prestory editing readback and exact foundation truth lookup;
  - retrieval-core starts after accepted setup truth is materialized into seed sections and then owns chunking, indexing, embeddings, hybrid/rerank, Recall/Archival search, and active-story runtime retrieval policy.
- The bridge remains deterministic post-commit materialization. The agent does not write retrieval index rows, call retrieval-core to recover drafts, or depend on retrieval readiness before the next setup stage can proceed.
- Reference rationale:
  - pi-mono supports the separation by keeping context/tool surfaces selected into the agent context instead of folding external stores into the loop.
  - Claude Code supports the separation by treating memory/context readback, active tool pools, and tool-result reinjection as explicit boundaries rather than ad hoc prompt text.
  - current setup specs add the project-specific rule that editable draft truth and committed setup truth are setup-owned, while semantic/runtime retrieval belongs to retrieval-core after commit.
- No `$grill-me` question remains for C. A future slice may add richer setup readback tools or retrieval diagnostics, but only through the same capability/tool protocol and without changing the setup-vs-retrieval ownership boundary.

Checks:

- `python .\.trellis\scripts\task.py validate 05-11-setup-agent-architecture-improve` -> passed
- `git diff --check -- <C changed docs/specs>` -> no whitespace errors; Git reported LF/CRLF conversion warnings only

### D: SkillPack Governance

Only after CapabilityPlan and ContextPipeline agree.

Purpose:

- formalize prompt-pack governance and observability

Guard:

- SkillPack remains prompt/context packaging, not business or tool-scope authority
- SkillPack selection is deterministic and stage-keyed from the resolved
  `SetupStageId`; the model never selects or activates a pack.
- `skill_pack_name` is observability metadata only. It must not affect
  behavior, durable state, `context_bundle`, `SetupWorkspace` truth, runtime
  overlay, tool scope, or truth-write injection.

Result:

- Current code already satisfied the D contract. One minimal type-narrowing fix
  was made in `backend/rp/agent_runtime/skill_packs/registry.py` so scoped mypy
  can prove the multiline frontmatter parser does not compare against a
  possible `None` indent after flushing a block.
- `backend/rp/agent_runtime/skill_packs/registry.py` keeps a deterministic
  stage-keyed registry and the `SkillPackRecord` shape has no tool or business
  authority fields.
- `SetupAgentPromptService` loads SkillPack text only through the stable system
  prompt stage overlay, inserts the specialist preamble only for a registered
  pack, and hard-unloads on stage change by resolving the prompt from the new
  `current_stage`.
- `SetupRuntimeAdapter`, `RpAgentRuntimeExecutor`,
  `SetupAgentExecutionService`, and `eval/trace_capture.py` propagate
  `skill_pack_name` only as metadata / structured payload / trace attributes.
- CapabilityPlan and tool scope remain independent: SkillPack does not mutate
  `SetupCapabilityPlan`, `tool_scope`, runtime allowlist, or
  `setup.truth.write` runtime-owned argument injection.
- No new SkillPack content, dependency, stage CRUD surface, retrieval surface,
  or durable runtime state was added.

Checks:

- `python -m pytest -q backend/rp/tests/test_skill_packs_registry.py backend/rp/tests/test_setup_agent_prompt_service.py backend/rp/tests/test_setup_agent_tool_scope.py backend/rp/tests/test_setup_agent_execution_service_v2.py backend/rp/tests/test_eval_trace_capture.py backend/rp/tests/test_eval_diagnostics.py` -> `103 passed, 1 xfailed, 2 warnings`
- `python -m ruff check backend/rp/agent_runtime/skill_packs/registry.py backend/rp/services/setup_agent_prompt_service.py backend/rp/agent_runtime/adapters.py backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/executor.py backend/rp/services/setup_agent_execution_service.py backend/rp/eval/trace_capture.py backend/rp/eval/models.py backend/rp/eval/graders/deterministic.py backend/rp/tests/test_skill_packs_registry.py backend/rp/tests/test_setup_agent_prompt_service.py backend/rp/tests/test_setup_agent_tool_scope.py backend/rp/tests/test_setup_agent_execution_service_v2.py backend/rp/tests/test_eval_trace_capture.py backend/rp/tests/test_eval_diagnostics.py` -> passed
- `python -m py_compile backend/rp/agent_runtime/skill_packs/registry.py backend/rp/services/setup_agent_prompt_service.py backend/rp/agent_runtime/adapters.py backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/executor.py backend/rp/services/setup_agent_execution_service.py backend/rp/eval/trace_capture.py backend/rp/eval/models.py backend/rp/eval/graders/deterministic.py` -> passed
- `python -m mypy --follow-imports=skip --ignore-missing-imports backend/rp/agent_runtime/skill_packs/registry.py backend/rp/services/setup_agent_prompt_service.py backend/rp/agent_runtime/adapters.py backend/rp/agent_runtime/contracts.py backend/rp/agent_runtime/executor.py backend/rp/services/setup_agent_execution_service.py backend/rp/eval/trace_capture.py backend/rp/eval/models.py backend/rp/eval/graders/deterministic.py` -> passed
- `python .\.trellis\scripts\task.py validate 05-11-setup-agent-architecture-improve` -> passed
- `git diff --check -- <D changed docs/code/tests>` -> no whitespace errors; Git reported LF/CRLF conversion warnings only

## 16. Check Cadence

After each coherent slice:

1. Run focused tests for changed contracts.
2. Run `python .\.trellis\scripts\task.py validate 05-11-setup-agent-architecture-improve` if task context changes.
3. Run `git diff --check -- <changed paths>`.
4. Use `trellis-check` before starting the next slice.

Do not run full checks after every tiny edit. Do run checks after each complete spec slice.

## 17. Legacy 05-09 Interpretation Guard

The old `05-09` handoff is investigation evidence only. It must not override this task's PRD, HLD, contract spine, or active backend specs.

Treat these old-hand-off details as superseded unless a current `05-11` document explicitly re-accepts them:

- the standalone `DecisionPolicy` target module; current direction is loop-owned transition rules inside `SetupTurnLoop`
- any A1 path that pulls `world_background` CRUD, draft CRUD migration, setup retrieval, or SkillPack governance into the loop/output slice
- uncommitted working-tree retry reason names from the old attempt unless they are reconciled with the active loop semantics taxonomy before implementation
- any prompt/tool/provider/test fix that bypasses the A2 `SetupCapabilityPlan` consistency contract
